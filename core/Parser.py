from Lexer import TokenKind, Token
from Ast import *
from MrylError import SyntaxError_

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.current = tokens[0]
        self.const_table = {}  # const name -> value (for compile-time evaluation)

    # ============================================================
    # Basic operations: token consumption
    # ============================================================
    def advance(self):
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current = self.tokens[self.pos]

    def expect(self, kind):
        tok = self.current
        if tok.kind != kind:
            raise SyntaxError_(f"Expected {kind}, got {tok.kind}", tok)
        self.advance()
        return tok

    def match(self, kind):
        if self.current.kind == kind:
            self.advance()
            return True
        return False

    # ============================================================
    # Top-level parsing: program, structs, functions
    # ============================================================
    def parse_program(self):
        structs = {}    # name -> StructDecl (for method addition)
        functions = []
        consts = []     # List of ConstDecl
        enums = {}      # name -> EnumDecl

        # Skip initial non-significant tokens
        self.skip_non_declaration()

        while self.current.kind != TokenKind.EOF:
            # Parse const declarations first
            if self.current.kind == TokenKind.CONST:
                const_decl = self.parse_const_decl()
                consts.append(const_decl)
            elif self.current.kind == TokenKind.ENUM:
                enum_decl = self.parse_enum_decl()
                enums[enum_decl.name] = enum_decl
            elif self.current.kind == TokenKind.STRUCT:
                struct = self.parse_struct_decl()
                structs[struct.name] = struct
            elif self.current.kind == TokenKind.IMPL:
                self.parse_impl_decl(structs)
            elif self.current.kind == TokenKind.FN:
                functions.append(self.parse_function_decl())
            elif self.current.kind == TokenKind.ASYNC:
                functions.append(self.parse_async_function_decl())
            else:
                raise SyntaxError_("Unexpected token at top level", self.current)

        return Program(list(structs.values()), functions, consts, list(enums.values()),
                       self.current.line, self.current.column)

    # ============================================================
    # Struct declaration parsing
    # ============================================================
    def parse_struct_decl(self):
        tok = self.current
        self.expect(TokenKind.STRUCT)

        name = self.current.value
        line, col = self.current.line, self.current.column
        self.expect(TokenKind.IDENT)

        # Generic type parameters (optional)
        type_params = []
        if self.match(TokenKind.LT):
            type_params.append(self.current.value)
            self.expect(TokenKind.IDENT)
            while self.match(TokenKind.COMMA):
                type_params.append(self.current.value)
                self.expect(TokenKind.IDENT)
            self.expect(TokenKind.GT)

        self.expect(TokenKind.LBRACE)

        fields = []
        while self.current.kind != TokenKind.RBRACE:
            fields.append(self.parse_struct_field())

        self.expect(TokenKind.RBRACE)
        return StructDecl(name, type_params, fields, line=line, column=col)

    def parse_struct_field(self):
        tok = self.current
        name = tok.value
        line, col = tok.line, tok.column
        self.expect(TokenKind.IDENT)

        self.expect(TokenKind.COLON)
        type_node = self.parse_type()
        self.expect(TokenKind.SEMICOLON)

        return StructField(name, type_node, line, col)

    # ============================================================
    # Enum declaration parsing
    # ============================================================
    def parse_enum_decl(self):
        """Parse: enum Name { Variant, Variant(T1, T2), ... }"""
        tok = self.current
        self.expect(TokenKind.ENUM)

        name = self.current.value
        line, col = self.current.line, self.current.column
        self.expect(TokenKind.IDENT)

        self.expect(TokenKind.LBRACE)

        variants = []
        while self.current.kind != TokenKind.RBRACE:
            v_name = self.current.value
            v_line, v_col = self.current.line, self.current.column
            self.expect(TokenKind.IDENT)

            # Optional payload: VariantName(T1, T2, ...)
            fields = []
            if self.match(TokenKind.LPAREN):
                while self.current.kind != TokenKind.RPAREN:
                    fields.append(self.parse_type())
                    if not self.match(TokenKind.COMMA):
                        break
                self.expect(TokenKind.RPAREN)

            variants.append(EnumVariant(v_name, fields, v_line, v_col))

            # Trailing comma is optional
            self.match(TokenKind.COMMA)

        self.expect(TokenKind.RBRACE)
        return EnumDecl(name, variants, line, col)

    def parse_impl_decl(self, structs):
        """Parse impl StructName { fn method(...) { ... } }
        Also handles generic syntax: impl Box<T> { ... }
        """
        self.expect(TokenKind.IMPL)

        struct_name = self.current.value
        self.expect(TokenKind.IDENT)

        # ジェネリック型引数 <T, U, ...> をスキップ (impl Box<T> など) (#32)
        if self.current.kind == TokenKind.LT:
            self.advance()  # consume <
            while self.current.kind != TokenKind.GT:
                self.expect(TokenKind.IDENT)  # type param name
                if self.current.kind == TokenKind.COMMA:
                    self.advance()
            self.expect(TokenKind.GT)  # consume >

        if struct_name not in structs:
            raise SyntaxError_(f"Struct {struct_name} not found", self.current)

        struct = structs[struct_name]

        self.expect(TokenKind.LBRACE)

        # Method definitions
        while self.current.kind != TokenKind.RBRACE:
            if self.current.kind == TokenKind.FN:
                method = self.parse_method_decl()
                struct.methods.append(method)
            elif self.current.kind == TokenKind.STATIC:
                self.advance()  # consume 'static'
                method = self.parse_static_method_decl()
                struct.methods.append(method)
            else:
                raise SyntaxError_("Expected fn or static fn in impl block", self.current)

        self.expect(TokenKind.RBRACE)

    def parse_static_method_decl(self):
        """Parse static fn method_name(params) -> ReturnType { ... }
        'static' keyword has already been consumed by parse_impl_decl.
        No 'self' parameter.
        """
        self.expect(TokenKind.FN)
        name_tok = self.current
        name = self.expect(TokenKind.IDENT).value
        line, col = name_tok.line, name_tok.column

        self.expect(TokenKind.LPAREN)
        params = []
        while self.current.kind != TokenKind.RPAREN:
            if self.current.kind == TokenKind.IDENT and self.current.value == "self":
                raise SyntaxError_("static fn cannot have 'self' parameter", self.current)
            pname = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.COLON)
            ptype = self.parse_type()
            params.append(Param(pname, ptype, line, col))
            if not self.match(TokenKind.COMMA):
                break
        self.expect(TokenKind.RPAREN)

        return_type = TypeNode("void")
        if self.match(TokenKind.ARROW):
            return_type = self.parse_type()

        body = self.parse_block()
        return MethodDecl(name, params, return_type, body, is_static=True, line=line, column=col)

    def parse_method_decl(self):
        """Parse fn method_name(self, ...) -> ReturnType { ... }"""
        self.expect(TokenKind.FN)
        name = self.expect(TokenKind.IDENT).value
        line, col = self.current.line, self.current.column

        self.expect(TokenKind.LPAREN)

        params = []
        # First parameter must be self
        if self.current.kind == TokenKind.IDENT and self.current.value == "self":
            self.advance()
            # Create self parameter (type resolved later)
            params.append(Param("self", TypeNode("Self"), line, col))
        else:
            raise SyntaxError_("First parameter of method must be self", self.current)

        # その他のパラメータ
        while self.match(TokenKind.COMMA):
            if self.current.kind == TokenKind.RPAREN:
                break
            pname = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.COLON)
            ptype = self.parse_type()
            params.append(Param(pname, ptype, line, col))

        self.expect(TokenKind.RPAREN)

        # Return type
        return_type = TypeNode("void")
        if self.match(TokenKind.ARROW):
            return_type = self.parse_type()

        # Method body
        body = self.parse_block()

        return MethodDecl(name, params, return_type, body, line=line, column=col)

    # ============================================================
    # Function declaration parsing
    # ============================================================
    def parse_function_decl(self):
        self.expect(TokenKind.FN)
        name_tok = self.current  # capture function name token for line info
        name = self.expect(TokenKind.IDENT).value
        line, col = name_tok.line, name_tok.column

        # Generic type parameters
        type_params = []
        if self.match(TokenKind.LT):
            type_params = self.parse_type_params()
            self.expect(TokenKind.GT)

        self.expect(TokenKind.LPAREN)
        params = self.parse_params()
        self.expect(TokenKind.RPAREN)

        return_type = None
        if self.match(TokenKind.ARROW):
            return_type = self.parse_type()

        # 前方宣言: fn name(...) -> T;  (ボディなし)
        if self.match(TokenKind.SEMICOLON):
            return FunctionDecl(
                name=name,
                params=params,
                return_type=return_type,
                body=None,
                type_params=type_params,
                line=line,
                column=col,
            )

        body = self.parse_block()
        return FunctionDecl(
            name=name, 
            params=params, 
            return_type=return_type, 
            body=body,
            type_params=type_params,
            line=line,
            column=col,
        )

    def parse_async_function_decl(self):
        """Parse: async fn name(params) -> return_type { body }"""
        self.expect(TokenKind.ASYNC)
        self.expect(TokenKind.FN)
        name_tok = self.current  # capture function name token for line info
        name = self.expect(TokenKind.IDENT).value
        line, col = name_tok.line, name_tok.column

        # Generic type parameters
        type_params = []
        if self.match(TokenKind.LT):
            type_params = self.parse_type_params()
            self.expect(TokenKind.GT)

        self.expect(TokenKind.LPAREN)
        params = self.parse_params()
        self.expect(TokenKind.RPAREN)

        return_type = None
        if self.match(TokenKind.ARROW):
            return_type = self.parse_type()

        body = self.parse_block()
        return FunctionDecl(
            name=name,
            params=params,
            return_type=return_type,
            body=body,
            type_params=type_params,
            is_async=True,
            line=line,
            column=col,
        )

    def parse_params(self):
        params = []
        if self.current.kind == TokenKind.RPAREN:
            return params

        params.append(self.parse_param())
        while self.match(TokenKind.COMMA):
            params.append(self.parse_param())

        return params

    def parse_param(self):
        # fix 修飾子のチェック: fn foo(fix x: i32)
        is_fix = False
        if self.current.kind == TokenKind.FIX:
            is_fix = True
            self.advance()  # consume fix

        tok = self.current
        name = tok.value
        line, col = tok.line, tok.column
        self.expect(TokenKind.IDENT)

        self.expect(TokenKind.COLON)
        type_node = self.parse_type()

        return Param(name, type_node, line, col, is_fix=is_fix)

    # ============================================================
    # Type parsing
    # ============================================================
    def parse_type(self):
        # fn(T, U) -> V  /  async fn(T) -> V  (#41)
        if self.current.kind in (TokenKind.FN, TokenKind.ASYNC):
            is_async = self.current.kind == TokenKind.ASYNC
            if is_async:
                self.advance()  # consume async
            self.advance()  # consume fn
            self.expect(TokenKind.LPAREN)
            param_types = []
            while self.current.kind != TokenKind.RPAREN:
                param_types.append(self.parse_type())
                if self.current.kind == TokenKind.COMMA:
                    self.advance()
            self.expect(TokenKind.RPAREN)
            self.expect(TokenKind.ARROW)
            ret_type = self.parse_type()
            type_name = "async_fn" if is_async else "fn"
            return TypeNode(type_name, type_args=param_types + [ret_type])

        tok = self.current
        name = tok.value
        line, col = tok.line, tok.column
        self.expect(TokenKind.IDENT)

        if self.match(TokenKind.LBRACKET):
            # i32[] = dynamic array, i32[N] = fixed array
            if self.current.kind == TokenKind.RBRACKET:
                self.expect(TokenKind.RBRACKET)
                inner = TypeNode(name, array_size=-1, line=line, column=col)
                # i32[][] / i32[][][] など多次元動的配列: 追加 [] を再帰的にラップ
                # 各次元を TypeNode("Array", array_size=-1, type_args=[inner]) として表現する
                while self.current.kind == TokenKind.LBRACKET:
                    self.advance()  # consume '['
                    if self.current.kind == TokenKind.RBRACKET:
                        self.advance()  # consume ']'
                        inner = TypeNode("Array", array_size=-1, type_args=[inner], line=line, column=col)
                    else:
                        break  # 固定長の多次元は未対応（T[][N] 等）
                return inner
            size_tok = self.current
            size = int(size_tok.value)
            self.expect(TokenKind.NUMBER)
            self.expect(TokenKind.RBRACKET)
            return TypeNode(name, array_size=size, line=line, column=col)

        # Generic type arguments: Result<T, E>, Vec<T>, etc.
        if self.current.kind == TokenKind.LT:
            self.advance()  # consume '<'
            type_args = []
            while self.current.kind not in (TokenKind.GT, TokenKind.RSHIFT):
                type_args.append(self.parse_type())
                if self.current.kind == TokenKind.COMMA:
                    self.advance()  # consume ','
            # RSHIFT ">>" は入れ子型の閉じ括弧 2 つ分: 1 つ消費して残り 1 つを GT に書き換える
            if self.current.kind == TokenKind.RSHIFT:
                self.current = Token(TokenKind.GT, ">", self.current.line, self.current.column)
            else:
                self.expect(TokenKind.GT)
            # Box<T>[] など「ジェネリック型の動的配列」をサポート（多次元も同様に対応）
            if self.match(TokenKind.LBRACKET):
                if self.current.kind == TokenKind.RBRACKET:
                    self.expect(TokenKind.RBRACKET)
                    inner = TypeNode(name, type_args=type_args, array_size=-1, line=line, column=col)
                    # Box<T>[][] など多次元: 追加 [] をラップ
                    while self.current.kind == TokenKind.LBRACKET:
                        self.advance()
                        if self.current.kind == TokenKind.RBRACKET:
                            self.advance()
                            inner = TypeNode("Array", array_size=-1, type_args=[inner], line=line, column=col)
                        else:
                            break
                    return inner
            return TypeNode(name, type_args=type_args, line=line, column=col)

        return TypeNode(name, line=line, column=col)

    # ============================================================
    # Statement parsing
    # ============================================================
    def parse_statement(self):
        tok = self.current.kind

        if tok == TokenKind.LET:
            return self.parse_let_decl()

        if tok == TokenKind.FIX:
            return self.parse_fix_decl()

        if tok == TokenKind.IF:
            return self.parse_if_stmt()

        if tok == TokenKind.WHILE:
            return self.parse_while_stmt()

        if tok == TokenKind.FOR:
            return self.parse_for_stmt()

        if tok == TokenKind.RETURN:
            return self.parse_return_stmt()

        if tok == TokenKind.BREAK:
            return self.parse_break_stmt()

        if tok == TokenKind.CONTINUE:
            return self.parse_continue_stmt()

        if tok == TokenKind.LBRACE:
            return self.parse_block()
        
        # Conditional compilation directives
        if tok == TokenKind.HASH_IFDEF:
            return self.parse_hash_ifdef()
        
        if tok == TokenKind.HASH_IFNDEF:
            return self.parse_hash_ifndef()
        
        if tok == TokenKind.HASH_IF:
            return self.parse_hash_if()

        return self.parse_expr_or_assignment()

    def parse_let_decl(self):
        tok = self.current
        self.expect(TokenKind.LET)

        name = self.current.value
        line, col = self.current.line, self.current.column
        self.expect(TokenKind.IDENT)

        type_node = None
        if self.match(TokenKind.COLON):
            type_node = self.parse_type()

        init_expr = None
        if self.match(TokenKind.EQ):
            init_expr = self.parse_expr()

        self.expect(TokenKind.SEMICOLON)
        return LetDecl(name, type_node, init_expr, line, col)

    def parse_fix_decl(self):
        """Parse: fix name: Type = expr;"""
        tok = self.current
        self.expect(TokenKind.FIX)

        name = self.current.value
        line, col = self.current.line, self.current.column
        self.expect(TokenKind.IDENT)

        type_node = None
        if self.match(TokenKind.COLON):
            type_node = self.parse_type()

        init_expr = None
        if self.match(TokenKind.EQ):
            init_expr = self.parse_expr()
        else:
            raise SyntaxError_(f"'fix' declaration '{name}' must have an initializer", self.current)

        self.expect(TokenKind.SEMICOLON)
        return FixDecl(name, type_node, init_expr, line, col)

    def parse_const_decl(self):
        tok = self.current
        self.expect(TokenKind.CONST)

        name = self.current.value
        line, col = self.current.line, self.current.column
        self.expect(TokenKind.IDENT)

        self.expect(TokenKind.EQ)
        init_expr = self.parse_expr()

        self.expect(TokenKind.SEMICOLON)
        
        # Evaluate const at parse time and store in const_table
        try:
            const_value = self._eval_const_expr(init_expr)
            self.const_table[name] = const_value
        except Exception as e:
            # Const expression could not be evaluated at parse time
            self.const_table[name] = None
        
        return ConstDecl(name, init_expr, line, col)

    def _eval_const_expr(self, expr):
        """Evaluate a const expression at parse time"""
        from Ast import NumberLiteral, StringLiteral, BoolLiteral, Identifier, BinaryOp
        
        if isinstance(expr, NumberLiteral):
            return expr.value
        elif isinstance(expr, StringLiteral):
            return expr.value
        elif isinstance(expr, BoolLiteral):
            return expr.value
        elif isinstance(expr, Identifier):
            # Reference to a previously defined const
            if expr.name in self.const_table:
                return self.const_table[expr.name]
            else:
                raise ValueError(f"Undefined const: {expr.name}")
        elif isinstance(expr, BinaryOp):
            left_val = self._eval_const_expr(expr.left)
            right_val = self._eval_const_expr(expr.right)
            
            if expr.op == '+':
                return left_val + right_val
            elif expr.op == '-':
                return left_val - right_val
            elif expr.op == '*':
                return left_val * right_val
            elif expr.op == '/':
                if right_val == 0:
                    raise ValueError("Division by zero in const expression")
                return left_val // right_val if isinstance(left_val, int) else left_val / right_val
            elif expr.op == '%':
                return left_val % right_val
            elif expr.op == '==':
                return left_val == right_val
            elif expr.op == '!=':
                return left_val != right_val
            elif expr.op == '<':
                return left_val < right_val
            elif expr.op == '>':
                return left_val > right_val
            elif expr.op == '<=':
                return left_val <= right_val
            elif expr.op == '>=':
                return left_val >= right_val
            elif expr.op == '&&':
                return left_val and right_val
            elif expr.op == '||':
                return left_val or right_val
            elif expr.op == '&':
                return left_val & right_val
            elif expr.op == '|':
                return left_val | right_val
            elif expr.op == '^':
                return left_val ^ right_val
            elif expr.op == '<<':
                return left_val << right_val
            elif expr.op == '>>':
                return left_val >> right_val
            else:
                raise ValueError(f"Unsupported operator in const expression: {expr.op}")
        else:
            raise ValueError(f"Cannot evaluate expression type in const context: {type(expr)}")

    def parse_hash_ifdef(self):
        """Parse #ifdef CONST_NAME ... #endif block"""
        self.expect(TokenKind.HASH_IFDEF)
        
        const_name = self.current.value
        line, col = self.current.line, self.current.column
        self.expect(TokenKind.IDENT)
        
        # Parse then block
        then_block = self._parse_conditional_block()
        
        # Check for #else
        else_block = None
        if self.current.kind == TokenKind.HASH_ELSE:
            self.advance()
            else_block = self._parse_conditional_block()
        
        # Expect #endif
        self.expect(TokenKind.HASH_ENDIF)
        
        return ConditionalBlock(const_name, then_block, else_block, line, col)

    def parse_hash_ifndef(self):
        """Parse #ifndef CONST_NAME ... #endif block"""
        self.expect(TokenKind.HASH_IFNDEF)
        
        const_name = self.current.value
        line, col = self.current.line, self.current.column
        self.expect(TokenKind.IDENT)
        
        # Parse then block
        then_block = self._parse_conditional_block()
        
        # Check for #else
        else_block = None
        if self.current.kind == TokenKind.HASH_ELSE:
            self.advance()
            else_block = self._parse_conditional_block()
        
        # Expect #endif
        self.expect(TokenKind.HASH_ENDIF)
        
        # For #ifndef, negate the condition
        return ConditionalBlock(('not', const_name), then_block, else_block, line, col)

    def parse_hash_if(self):
        """Parse #if EXPR ... #endif block"""
        self.expect(TokenKind.HASH_IF)
        
        line, col = self.current.line, self.current.column
        # Parse condition expression (like a const expression)
        condition_expr = self.parse_expr()
        
        # Parse then block
        then_block = self._parse_conditional_block()
        
        # Check for #else
        else_block = None
        if self.current.kind == TokenKind.HASH_ELSE:
            self.advance()
            else_block = self._parse_conditional_block()
        
        # Expect #endif
        self.expect(TokenKind.HASH_ENDIF)
        
        return ConditionalBlock(condition_expr, then_block, else_block, line, col)

    def _parse_conditional_block(self):
        """Parse statements until #endif or #else"""
        statements = []
        
        while self.current.kind not in (TokenKind.HASH_ENDIF, TokenKind.HASH_ELSE, TokenKind.EOF):
            statements.append(self.parse_statement())
        
        return Block(statements)

    def parse_expr_or_assignment(self):
        # まず普通に式としてパース
        expr = self.parse_expr()

        # 代入文かどうかを判定
        if isinstance(expr, VarRef) or isinstance(expr, ArrayAccess) or isinstance(expr, StructAccess):
            # Simple assignment
            if self.match(TokenKind.EQ):
                value = self.parse_expr()
                self.expect(TokenKind.SEMICOLON)
                return Assignment(expr, value, expr.line, expr.column)
            
            # Compound assignment operators
            compound_ops = {
                TokenKind.PLUS_EQ: "+=",
                TokenKind.MINUS_EQ: "-=",
                TokenKind.STAR_EQ: "*=",
                TokenKind.SLASH_EQ: "/=",
                TokenKind.MOD_EQ: "%=",
                TokenKind.LSHIFT_EQ: "<<=",
                TokenKind.RSHIFT_EQ: ">>=",
                TokenKind.CARET_EQ: "^=",
            }
            
            for token_kind, op_str in compound_ops.items():
                if self.current.kind == token_kind:
                    self.advance()
                    value = self.parse_expr()
                    self.expect(TokenKind.SEMICOLON)
                    # Convert compound assignment to binary operation
                    # e.g., x += 1 becomes x = x + 1
                    base_op = op_str[:-1]  # Remove the '='
                    binary_expr = BinaryOp(base_op, expr, value, expr.line, expr.column)
                    return Assignment(expr, binary_expr, expr.line, expr.column)

        # 代入でなければ式文
        self.expect(TokenKind.SEMICOLON)
        return ExprStmt(expr, expr.line, expr.column)

    # ============================================================
    # Control flow statements: if, while, for, return, block
    # ============================================================
    def parse_if_stmt(self):
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.IF)

        self.expect(TokenKind.LPAREN)
        condition = self.parse_expr()
        self.expect(TokenKind.RPAREN)

        then_block = self.parse_block()

        else_block = None
        if self.match(TokenKind.ELSE):
            # Peek if next is IF without consuming
            if self.current.kind == TokenKind.IF:
                # IF will be consumed by parse_if_stmt
                else_block = self.parse_if_stmt()
            else:
                else_block = self.parse_block()

        return IfStmt(condition, then_block, else_block, line, col)

    def parse_while_stmt(self):
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.WHILE)

        self.expect(TokenKind.LPAREN)
        condition = self.parse_expr()
        self.expect(TokenKind.RPAREN)

        body = self.parse_block()
        return WhileStmt(condition, body, line, col)

    def parse_for_stmt(self):
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.FOR)

        # Check if C-style: for (let i = 0; i < 10; i++)
        if self.current.kind == TokenKind.LPAREN:
            # Could be C-style. Peek for "let"
            return self._parse_c_style_for(line, col)
        
        # Rust-style: for x in iterable
        return self._parse_rust_style_for(line, col)

    def _parse_rust_style_for(self, line, col):
        """Parse: for variable in iterable { ... }"""
        var_name = self.current.value
        self.expect(TokenKind.IDENT)

        self.expect(TokenKind.IN)

        # Parse the iterable (could be a range or an array)
        iterable = self.parse_expr()

        body = self.parse_block()

        return ForStmt(
            variable=var_name,
            iterable=iterable,
            condition=None,
            update=None,
            body=body,
            is_c_style=False,
            line=line,
            column=col
        )

    def _parse_c_style_for(self, line, col):
        """Parse: for (let i = 0; i < 10; i++) { ... }"""
        self.expect(TokenKind.LPAREN)

        # Parse initialization: let i = 0
        self.expect(TokenKind.LET)
        var_name = self.current.value
        self.expect(TokenKind.IDENT)
        self.expect(TokenKind.EQ)
        init_expr = self.parse_expr()
        self.expect(TokenKind.SEMICOLON)

        # Parse condition: i < 10
        condition = self.parse_expr()
        self.expect(TokenKind.SEMICOLON)

        # Parse update expression
        update = self.parse_update_expr()
        self.expect(TokenKind.RPAREN)

        body = self.parse_block()

        return ForStmt(
            variable=var_name,
            iterable=init_expr,  # Store init as iterable for runtime use
            condition=condition,
            update=update,
            body=body,
            is_c_style=True,
            line=line,
            column=col
        )

    def parse_update_expr(self):
        """Parse update expression (can be assignment like i = i + 1, or compound like i += 1)"""
        expr = self.parse_expr()

        line = expr.line if hasattr(expr, 'line') else None
        col  = expr.column if hasattr(expr, 'column') else None

        # Simple assignment
        if self.current.kind == TokenKind.EQ:
            self.advance()
            value = self.parse_expr()
            return Assignment(expr, value, line, col)

        # Compound assignment operators (+=, -=, *=, /=, %=, <<=, >>=, ^=)
        compound_ops = {
            TokenKind.PLUS_EQ:   "+=",
            TokenKind.MINUS_EQ:  "-=",
            TokenKind.STAR_EQ:   "*=",
            TokenKind.SLASH_EQ:  "/=",
            TokenKind.MOD_EQ:    "%=",
            TokenKind.LSHIFT_EQ: "<<=",
            TokenKind.RSHIFT_EQ: ">>=",
            TokenKind.CARET_EQ:  "^=",
        }
        for token_kind, op_str in compound_ops.items():
            if self.current.kind == token_kind:
                self.advance()
                value    = self.parse_expr()
                base_op  = op_str[:-1]  # Remove trailing '='
                bin_expr = BinaryOp(base_op, expr, value, line, col)
                return Assignment(expr, bin_expr, line, col)

        return expr

    def parse_return_stmt(self):
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.RETURN)

        expr = self.parse_expr()
        self.expect(TokenKind.SEMICOLON)
        return ReturnStmt(expr, line, col)

    def parse_break_stmt(self):
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.BREAK)
        self.expect(TokenKind.SEMICOLON)
        return BreakStmt(line, col)

    def parse_continue_stmt(self):
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.CONTINUE)
        self.expect(TokenKind.SEMICOLON)
        return ContinueStmt(line, col)

    def parse_block(self):
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.LBRACE)

        statements = []
        while self.current.kind != TokenKind.RBRACE:
            statements.append(self.parse_statement())

        self.expect(TokenKind.RBRACE)
        return Block(statements, line, col)

    # ============================================================
    # Expression parsing: operator precedence climbing
    # ============================================================
    def parse_expr(self):
        return self.parse_logical_or()

    def parse_logical_or(self):
        """Parse logical OR (||) - lowest precedence"""
        node = self.parse_logical_and()

        while self.current.kind == TokenKind.OR:
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_logical_and()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_logical_and(self):
        """Parse logical AND (&&)"""
        node = self.parse_bitwise_or()

        while self.current.kind == TokenKind.AND:
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_bitwise_or()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_bitwise_or(self):
        """Parse bitwise OR (|)"""
        node = self.parse_bitwise_xor()

        while self.current.kind == TokenKind.PIPE:
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_bitwise_xor()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_bitwise_xor(self):
        """Parse bitwise XOR (^)"""
        node = self.parse_bitwise_and()

        while self.current.kind == TokenKind.CARET:
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_bitwise_and()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_bitwise_and(self):
        """Parse bitwise AND (&)"""
        node = self.parse_equality()

        while self.current.kind == TokenKind.AMPERSAND:
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_equality()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_equality(self):
        node = self.parse_comparison()

        while self.current.kind in (TokenKind.EQ_EQ, TokenKind.BANG_EQ):
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_comparison()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_comparison(self):
        node = self.parse_shift()

        while self.current.kind in (
            TokenKind.LT, TokenKind.GT,
            TokenKind.LT_EQ, TokenKind.GT_EQ
        ):
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_shift()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_shift(self):
        """Parse bitwise shift operators (<< >>)"""
        node = self.parse_range()

        while self.current.kind in (TokenKind.LSHIFT, TokenKind.RSHIFT):
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_range()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_range(self):
        """Parse range expressions: 0..10 (exclusive) or 0 to 10 (inclusive)"""
        node = self.parse_term()

        if self.current.kind == TokenKind.DOTDOT:
            tok = self.current
            self.advance()
            end = self.parse_term()
            node = Range(node, end, inclusive=False, line=tok.line, column=tok.column)

        elif self.current.kind == TokenKind.TO:
            tok = self.current
            self.advance()
            end = self.parse_term()
            node = Range(node, end, inclusive=True, line=tok.line, column=tok.column)

        return node

    def parse_term(self):
        node = self.parse_factor()

        while self.current.kind in (TokenKind.PLUS, TokenKind.MINUS):
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_factor()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_factor(self):
        node = self.parse_unary()

        while self.current.kind in (TokenKind.STAR, TokenKind.SLASH, TokenKind.MOD):
            tok = self.current
            op = tok.value
            self.advance()
            right = self.parse_unary()
            node = BinaryOp(op, node, right, tok.line, tok.column)

        return node

    def parse_unary(self):
        tok = self.current
        if self.match(TokenKind.PLUS):
            return UnaryOp("+", self.parse_unary(), tok.line, tok.column)
        if self.match(TokenKind.MINUS):
            return UnaryOp("-", self.parse_unary(), tok.line, tok.column)
        if self.match(TokenKind.PLUS_PLUS):
            return UnaryOp("++", self.parse_unary(), tok.line, tok.column)
        if self.match(TokenKind.MINUS_MINUS):
            return UnaryOp("--", self.parse_unary(), tok.line, tok.column)
        if self.match(TokenKind.NOT):
            return UnaryOp("!", self.parse_unary(), tok.line, tok.column)
        if self.match(TokenKind.TILDE):
            return UnaryOp("~", self.parse_unary(), tok.line, tok.column)
        if self.match(TokenKind.STAR):
            return UnaryOp("deref", self.parse_unary(), tok.line, tok.column)
        if tok.kind == TokenKind.AWAIT:
            self.advance()
            expr = self.parse_unary()
            return AwaitExpr(expr, tok.line, tok.column)
        if tok.kind == TokenKind.WEAK:
            self.advance()
            self.expect(TokenKind.LPAREN)
            expr = self.parse_expr()
            self.expect(TokenKind.RPAREN)
            return WeakExpr(expr, tok.line, tok.column)
        return self.parse_postfix()

    def parse_postfix(self):
        """Parse postfix operators (i++, i--, .method(), .field, [index])"""
        expr = self.parse_primary()

        while True:
            # Postfix ++ and --
            if self.current.kind in (TokenKind.PLUS_PLUS, TokenKind.MINUS_MINUS):
                tok = self.current
                if self.current.kind == TokenKind.PLUS_PLUS:
                    self.advance()
                    expr = UnaryOp("post++", expr, tok.line, tok.column)
                else:
                    self.advance()
                    expr = UnaryOp("post--", expr, tok.line, tok.column)

            # Method call / field access chaining:  expr.name(...)  or  expr.name
            elif self.current.kind == TokenKind.DOT:
                dot_tok = self.current
                self.advance()  # consume '.'
                field_tok = self.current
                field = field_tok.value
                fline, fcol = field_tok.line, field_tok.column
                # accept IDENT; 'try' is not a keyword so it comes as IDENT
                if field_tok.kind != TokenKind.IDENT:
                    # Roll back the dot and break
                    self.pos -= 1
                    self.current = self.tokens[self.pos]
                    break
                self.advance()  # consume field name
                if self.current.kind == TokenKind.LPAREN:
                    self.advance()  # consume '('
                    args = self.parse_args()
                    self.expect(TokenKind.RPAREN)
                    expr = MethodCall(expr, field, args, fline, fcol)
                else:
                    expr = StructAccess(expr, field, fline, fcol)

            # Index access chaining:  expr[idx]
            elif self.current.kind == TokenKind.LBRACKET:
                self.advance()
                index = self.parse_expr()
                self.expect(TokenKind.RBRACKET)
                from Ast import ArrayAccess
                expr = ArrayAccess(expr, index, self.current.line, self.current.column)

            else:
                break

        return expr

    def parse_primary(self):
        tok = self.current

        if tok.kind == TokenKind.NUMBER:
            # "123(u32)" や "123u32" などから数値と型を分解
            num_str = tok.value
            explicit_type = None
            
            # パターン1: 5(u8) 形式
            if '(' in num_str and ')' in num_str:
                paren_start = num_str.index('(')
                paren_end = num_str.index(')')
                explicit_type = num_str[paren_start+1:paren_end]
                num_str = num_str[:paren_start]
            # パターン2: 5u8 形式（従来式）
            else:
                for i, ch in enumerate(num_str):
                    if ch.isalpha():
                        explicit_type = num_str[i:]
                        num_str = num_str[:i]
                        break
            
            # アンダースコア区切り除去（例: 1_000_000 → 1000000）
            num_str = num_str.replace('_', '')
            
            # 浮動小数点か整数か判定
            if '.' in num_str:
                value = float(num_str)
                node = FloatLiteral(value, explicit_type=explicit_type, line=tok.line, column=tok.column)
            else:
                value = int(num_str)
                node = NumberLiteral(value, explicit_type=explicit_type, line=tok.line, column=tok.column)
            
            self.advance()
            return node

        if tok.kind == TokenKind.STRING:
            node = StringLiteral(tok.value, tok.line, tok.column)
            self.advance()
            return node

        if tok.kind == TokenKind.TRUE:
            node = BoolLiteral(True, tok.line, tok.column)
            self.advance()
            return node

        if tok.kind == TokenKind.FALSE:
            node = BoolLiteral(False, tok.line, tok.column)
            self.advance()
            return node

        if tok.kind == TokenKind.LPAREN:
            # Check if this is a lambda: (params) => body
            if self._is_lambda_start():
                return self.parse_lambda()
            line, col = tok.line, tok.column
            self.advance()
            expr = self.parse_expr()
            self.expect(TokenKind.RPAREN)
            expr.line = line
            expr.column = col
            return expr

        if tok.kind == TokenKind.ASYNC:
            # async (params) => body  → async lambda
            next_pos = self.pos + 1
            if next_pos < len(self.tokens) and self.tokens[next_pos].kind == TokenKind.LPAREN:
                self.advance()  # consume ASYNC, current is now LPAREN
                if self._is_lambda_start():
                    return self.parse_lambda(is_async=True)
            raise SyntaxError_("Unexpected 'async' outside of async lambda or async fn", tok)

        if tok.kind == TokenKind.IDENT:
            return self.parse_ident_primary()

        if tok.kind == TokenKind.LBRACKET:
            return self.parse_array_literal()

        if tok.kind == TokenKind.MATCH:
            return self.parse_match_expr()

        raise SyntaxError_("Unexpected token in primary", tok)

    # ============================================================
    # Lambda parsing: (params) => expr  or  (params) => { block }
    # ============================================================
    def _is_lambda_start(self):
        """Lookahead to determine if the current ( starts a lambda expression."""
        saved_pos = self.pos
        saved_current = self.current
        try:
            self.advance()  # consume (

            # Empty params: () =>
            if self.current.kind == TokenKind.RPAREN:
                self.advance()  # )
                return self.current.kind == TokenKind.FAT_ARROW

            # First param: optional 'fix' modifier, then identifier
            if self.current.kind == TokenKind.FIX:
                self.advance()  # consume fix
            if self.current.kind != TokenKind.IDENT:
                return False
            self.advance()  # param name

            # Optional type annotation
            if self.current.kind == TokenKind.COLON:
                self.advance()  # :
                if self.current.kind != TokenKind.IDENT:
                    return False
                self.advance()  # type name

            # Additional params
            while self.current.kind == TokenKind.COMMA:
                self.advance()  # ,
                if self.current.kind == TokenKind.FIX:
                    self.advance()  # consume fix
                if self.current.kind != TokenKind.IDENT:
                    return False
                self.advance()  # param name
                if self.current.kind == TokenKind.COLON:
                    self.advance()  # :
                    if self.current.kind != TokenKind.IDENT:
                        return False
                    self.advance()  # type name

            # Must close with ) =>
            if self.current.kind != TokenKind.RPAREN:
                return False
            self.advance()  # )
            return self.current.kind == TokenKind.FAT_ARROW
        finally:
            self.pos = saved_pos
            self.current = self.tokens[saved_pos]

    def parse_lambda(self, is_async: bool = False):
        """Parse: (params) => expr  or  (params) => { block }  or  async (params) => { block }"""
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.LPAREN)

        params = []
        if self.current.kind != TokenKind.RPAREN:
            p_is_fix = self.current.kind == TokenKind.FIX
            if p_is_fix: self.advance()
            pname = self.current.value
            pline, pcol = self.current.line, self.current.column
            self.expect(TokenKind.IDENT)
            ptype = None
            if self.match(TokenKind.COLON):
                ptype = self.parse_type()
            params.append(Param(pname, ptype, pline, pcol, is_fix=p_is_fix))

            while self.match(TokenKind.COMMA):
                p_is_fix = self.current.kind == TokenKind.FIX
                if p_is_fix: self.advance()
                pname = self.current.value
                pline, pcol = self.current.line, self.current.column
                self.expect(TokenKind.IDENT)
                ptype = None
                if self.match(TokenKind.COLON):
                    ptype = self.parse_type()
                params.append(Param(pname, ptype, pline, pcol, is_fix=p_is_fix))

        self.expect(TokenKind.RPAREN)
        self.expect(TokenKind.FAT_ARROW)

        # Body: block or expression
        if self.current.kind == TokenKind.LBRACE:
            body = self.parse_block()
        else:
            body = self.parse_expr()

        return Lambda(params, body, is_async, line, col)

    # ============================================================
    # Identifier primary: function calls, field access, struct init
    # ============================================================
    def parse_ident_primary(self):
        ident = self.current.value
        line, col = self.current.line, self.current.column
        self.expect(TokenKind.IDENT)

        # Function call
        if self.match(TokenKind.LPAREN):
            args = self.parse_args()
            self.expect(TokenKind.RPAREN)
            return FunctionCall(ident, [], args, line, col)

        # Array access
        if self.match(TokenKind.LBRACKET):
            index = self.parse_expr()
            self.expect(TokenKind.RBRACKET)
            return ArrayAccess(VarRef(ident, line, col), index, line, col)

        # Struct initialization (identifier is a type name if starts with uppercase)
        # type_params はジェネリック型引数（Subject<i32>::new() 等でも使用）
        type_params = []
        if ident[0].isupper():
            if self.current.kind == TokenKind.LT:
                saved_pos = self.pos
                # Speculatively parse <T, U, ...>
                try:
                    self.advance()  # <
                    while self.current.kind != TokenKind.GT:
                        tp_name = self.current.value
                        self.advance()
                        type_params.append(tp_name)
                        if not self.match(TokenKind.COMMA):
                            break
                    self.expect(TokenKind.GT)
                    # Commit if followed by { (struct init) or :: (TypeName<T>::method())
                    if self.current.kind not in (TokenKind.LBRACE, TokenKind.DOUBLE_COLON):
                        # Not a struct init or generic static call, roll back
                        self.pos = saved_pos
                        self.current = self.tokens[self.pos]
                        type_params = []
                except Exception:
                    self.pos = saved_pos
                    self.current = self.tokens[self.pos]
                    type_params = []

            if self.match(TokenKind.LBRACE):
                fields = []
                while self.current.kind != TokenKind.RBRACE:
                    fname = self.current.value
                    self.expect(TokenKind.IDENT)
                    self.expect(TokenKind.COLON)
                    expr = self.parse_expr()
                    fields.append((fname, expr))
                    if not self.match(TokenKind.COMMA):
                        break
                self.expect(TokenKind.RBRACE)
                return StructInit(ident, type_params, fields, line, col)

        # Enum variant / Static method: TypeName::member  or  TypeName::member(args)
        # TypeName<T>::member(args) も type_params がセットされた状態でここに来る
        if self.current.kind == TokenKind.DOUBLE_COLON:
            self.advance()  # consume ::
            variant_name = self.current.value
            self.expect(TokenKind.IDENT)
            args = []
            has_parens = False
            if self.match(TokenKind.LPAREN):
                has_parens = True
                args = self.parse_args()
                self.expect(TokenKind.RPAREN)
            return EnumVariantExpr(ident, variant_name, args, line, col,
                                   has_parens=has_parens, type_args=type_params)

        return VarRef(ident, line, col)

    # ============================================================
    # Match expression
    # ============================================================
    def parse_match_expr(self):
        """match scrutinee { Pattern => expr, ... }"""
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.MATCH)
        scrutinee = self.parse_expr()
        self.expect(TokenKind.LBRACE)
        arms = []
        while self.current.kind != TokenKind.RBRACE:
            pattern = self.parse_match_pattern()
            self.expect(TokenKind.FAT_ARROW)
            # アームのボディ：ブロック式 { ... } または単純な式
            if self.current.kind == TokenKind.LBRACE:
                body = self.parse_block_expr()
            else:
                body = self.parse_expr()
            arms.append(MatchArm(pattern, body, pattern.line, pattern.column))
            self.match(TokenKind.COMMA)
        self.expect(TokenKind.RBRACE)
        return MatchExpr(scrutinee, arms, line, col)

    def parse_block_expr(self):
        """ブロック式 { stmt; ... expr } をパースして BlockExpr を返す"""
        from Ast import BlockExpr
        tok = self.current
        line, col = tok.line, tok.column
        self.expect(TokenKind.LBRACE)
        stmts = []
        result_expr = None
        while self.current.kind != TokenKind.RBRACE:
            # 次が文になれるかチェック（セミコロン終わり以外 = 末尾の式）
            # 単純戦略：セミコロンで終わるものは文、そうでなければ式として result_expr に
            saved_pos = self.pos
            try:
                stmt = self.parse_statement()
                stmts.append(stmt)
            except Exception:
                # パース失敗時はバックトラックして式として扱う
                self.pos = saved_pos
                self.current = self.tokens[self.pos]
                result_expr = self.parse_expr()
                break
        self.expect(TokenKind.RBRACE)
        return BlockExpr(stmts, result_expr, line, col)

    def parse_match_pattern(self):
        tok = self.current
        line, col = tok.line, tok.column

        # regex("...") pattern
        if tok.kind == TokenKind.IDENT and tok.value == "regex":
            self.advance()
            self.expect(TokenKind.LPAREN)
            pat_tok = self.current
            self.expect(TokenKind.STRING)
            self.expect(TokenKind.RPAREN)
            return RegexPattern(pat_tok.value, line, col)

        # Literal patterns
        if tok.kind == TokenKind.NUMBER:
            self.advance()
            val = float(tok.value) if '.' in tok.value else int(tok.value)
            return LiteralPattern(val, line, col)
        if tok.kind == TokenKind.STRING:
            self.advance()
            return LiteralPattern(tok.value, line, col)
        if tok.kind == TokenKind.TRUE:
            self.advance()
            return LiteralPattern(True, line, col)
        if tok.kind == TokenKind.FALSE:
            self.advance()
            return LiteralPattern(False, line, col)

        # IDENT-based patterns
        if tok.kind == TokenKind.IDENT:
            name = tok.value
            self.advance()

            # _ is parsed as a special BindingPattern; at runtime it raises MatchError
            if name == "_":
                return BindingPattern("_", line, col)

            if name[0].isupper():
                # EnumPattern: Name::Variant or Name::Variant(bindings)
                if self.current.kind == TokenKind.DOUBLE_COLON:
                    self.advance()  # consume ::
                    variant_tok = self.current
                    self.expect(TokenKind.IDENT)
                    variant = variant_tok.value
                    bindings = []
                    if self.match(TokenKind.LPAREN):
                        while self.current.kind != TokenKind.RPAREN:
                            bindings.append(self.current.value)
                            self.expect(TokenKind.IDENT)
                            self.match(TokenKind.COMMA)
                        self.expect(TokenKind.RPAREN)
                    return EnumPattern(name, variant, bindings, line, col)

                # Constructor pattern: Ok(v) / Err(e)  (no :: prefix)
                if self.current.kind == TokenKind.LPAREN:
                    self.advance()  # consume (
                    bindings = []
                    while self.current.kind != TokenKind.RPAREN:
                        bindings.append(self.current.value)
                        self.expect(TokenKind.IDENT)
                        self.match(TokenKind.COMMA)
                    self.expect(TokenKind.RPAREN)
                    # Treat as EnumPattern with the constructor name as both type and variant
                    return EnumPattern(name, name, bindings, line, col)

                # StructPattern: Name { field1, field2 }
                if self.current.kind == TokenKind.LBRACE:
                    self.advance()  # consume {
                    fields = []
                    while self.current.kind != TokenKind.RBRACE:
                        fields.append(self.current.value)
                        self.expect(TokenKind.IDENT)
                        self.match(TokenKind.COMMA)
                    self.expect(TokenKind.RBRACE)
                    return StructPattern(name, fields, line, col)

            # Bare uppercase ident with no suffix → Option None (or unknown enum)
            if name == "None":
                return EnumPattern("None", "None", [], line, col)

            # BindingPattern: lowercase → always matches, binds value
            return BindingPattern(name, line, col)

        raise SyntaxError_("Invalid match pattern", tok)

    # ============================================================
    # Array literal
    # ============================================================
    def parse_array_literal(self):
        tok = self.current
        line, col = tok.line, tok.column

        self.expect(TokenKind.LBRACKET)
        elements = []

        if self.current.kind != TokenKind.RBRACKET:
            elements.append(self.parse_expr())
            while self.match(TokenKind.COMMA):
                elements.append(self.parse_expr())

        self.expect(TokenKind.RBRACKET)
        return ArrayLiteral(elements, line, col)

    # ============================================================
    # Argument list
    # ============================================================
    def parse_args(self):
        args = []
        if self.current.kind == TokenKind.RPAREN:
            return args

        args.append(self.parse_expr())
        while self.match(TokenKind.COMMA):
            args.append(self.parse_expr())

        return args

    def parse_type_params(self):
        params = []
        params.append(self.expect(TokenKind.IDENT).value)
        while self.match(TokenKind.COMMA):
            params.append(self.expect(TokenKind.IDENT).value)
        return params

    def skip_non_declaration(self):
        while self.current.kind not in (TokenKind.FN, TokenKind.STRUCT, TokenKind.CONST,
                                        TokenKind.ASYNC, TokenKind.ENUM, TokenKind.EOF):
            self.advance()