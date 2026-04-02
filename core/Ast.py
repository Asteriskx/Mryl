# ============================================================
# AST: Base class for all AST nodes with position information
# ============================================================
class AST:
    def __init__(self, line=None, column=None):
        self.line = line
        self.column = column

# ============================================================
# Program: Top-level program node
# ============================================================
class Program(AST):
    def __init__(self, structs, functions, consts=None, enums=None, line=None, column=None):
        super().__init__(line, column)
        self.structs = structs
        self.functions = functions
        self.consts = consts or []    # List of ConstDecl
        self.enums = enums or []      # List of EnumDecl

# ============================================================
# Struct: Structure declaration and related nodes
# ============================================================
class StructDecl(AST):
    def __init__(self, name, type_params, fields, methods=None, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.type_params = type_params  # list of type parameter names (e.g., ["T", "U"])
        self.fields = fields            # list of FieldDecl
        self.methods = methods or []    # list of MethodDecl from impl block

class StructField(AST):
    def __init__(self, name, type_node, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.type_node = type_node

class MethodDecl(AST):
    """Method declaration within Rust-style impl block"""
    def __init__(self, name, params, return_type, body, type_params=None, is_static=False, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.params = params            # list of Param (first param may be self, or empty for static)
        self.return_type = return_type
        self.body = body
        self.type_params = type_params or []
        self.is_static = is_static      # True for static fn declarations

# ============================================================
# Function: Function declaration and parameters
# ============================================================
class FunctionDecl(AST):
    def __init__(self, name, params, return_type, body, type_params=None, is_async=False, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.params = params
        self.return_type = return_type
        self.body = body
        self.type_params = type_params or []
        self.is_async = is_async

class Param(AST):
    def __init__(self, name, type_node, line=None, column=None, is_fix=False):
        super().__init__(line, column)
        self.name = name
        self.type_node = type_node
        self.is_fix = is_fix  # True if declared with fix keyword

# ============================================================
# Type: Type representation with generics and arrays
# ============================================================
class TypeNode(AST):
    def __init__(self, name, array_size=None, type_args=None, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.array_size = array_size

        if type_args is None:
            self.type_args = []
        elif isinstance(type_args, list):
            self.type_args = type_args
        else:
            # DEBUG: unexpected type_args format
            print("DEBUG TypeNode: invalid type_args:", name, array_size, type_args, type(type_args))
            self.type_args = []

    def __repr__(self):
        if self.array_size is not None:
            if self.array_size == -1:
                return f"{self.name}[]"
            return f"{self.name}[{self.array_size}]"
        if self.type_args:
            args = ", ".join(repr(a) for a in self.type_args)
            return f"{self.name}<{args}>"
        return self.name

# ============================================================
# Statement: All statement types
# ============================================================
class Statement(AST):
    def __init__(self, line=None, column=None):
        super().__init__(line, column)

class LetDecl(Statement):
    def __init__(self, name, type_node, init_expr, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.type_node = type_node
        self.init_expr = init_expr

class FixDecl(Statement):
    """Immutable local variable declaration: fix x: T = expr;"""
    def __init__(self, name, type_node, init_expr, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.type_node = type_node
        self.init_expr = init_expr

class ConstDecl(Statement):
    def __init__(self, name, init_expr, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.init_expr = init_expr
        # Constants are evaluated at parse/type-check time

class ConditionalBlock(Statement):
    """Block that is conditionally included based on compile-time constants"""
    def __init__(self, condition_expr, then_block, else_block=None, line=None, column=None):
        super().__init__(line, column)
        self.condition_expr = condition_expr  # String (const name) or Expression
        self.then_block = then_block
        self.else_block = else_block

class Assignment(Statement):
    def __init__(self, target, expr, line=None, column=None):
        super().__init__(line, column)
        self.target = target
        self.expr = expr

class IfStmt(Statement):
    def __init__(self, condition, then_block, else_block, line=None, column=None):
        super().__init__(line, column)
        self.condition = condition
        self.then_block = then_block
        self.else_block = else_block

class WhileStmt(Statement):
    def __init__(self, condition, body, line=None, column=None):
        super().__init__(line, column)
        self.condition = condition
        self.body = body

class ForStmt(Statement):
    def __init__(self, variable, iterable, condition, update, body, is_c_style, line=None, column=None):
        super().__init__(line, column)
        self.variable = variable        # loop variable name (e.g., "i")
        self.iterable = iterable        # Rust-style: range or array expression
        self.condition = condition      # C-style: loop condition
        self.update = update            # C-style: update expression
        self.body = body                # loop body (Block)
        self.is_c_style = is_c_style    # True for C-style, False for Rust-style

class ReturnStmt(Statement):
    def __init__(self, expr, line=None, column=None):
        super().__init__(line, column)
        self.expr = expr

class BreakStmt(Statement):
    def __init__(self, line=None, column=None):
        super().__init__(line, column)

class ContinueStmt(Statement):
    def __init__(self, line=None, column=None):
        super().__init__(line, column)

class ExprStmt(Statement):
    def __init__(self, expr, line=None, column=None):
        super().__init__(line, column)
        self.expr = expr

class Block(Statement):
    def __init__(self, statements, line=None, column=None):
        super().__init__(line, column)
        self.statements = statements

# ============================================================
# Expression: All expression types
# ============================================================
class Expr(AST):
    def __init__(self, line=None, column=None):
        super().__init__(line, column)

class BinaryOp(Expr):
    def __init__(self, op, left, right, line=None, column=None):
        super().__init__(line, column)
        self.op = op
        self.left = left
        self.right = right

class UnaryOp(Expr):
    def __init__(self, op, operand, line=None, column=None):
        super().__init__(line, column)
        self.op = op
        self.operand = operand

class NumberLiteral(Expr):
    def __init__(self, value, explicit_type=None, line=None, column=None):
        super().__init__(line, column)
        self.value = value
        self.explicit_type = explicit_type  # explicit type like "i8", "u32", or None

class FloatLiteral(Expr):
    def __init__(self, value, explicit_type=None, line=None, column=None):
        super().__init__(line, column)
        self.value = value
        self.explicit_type = explicit_type  # explicit type like "f32", "f64", or None

class StringLiteral(Expr):
    def __init__(self, value, line=None, column=None):
        super().__init__(line, column)
        self.value = value

class BoolLiteral(Expr):
    def __init__(self, value, line=None, column=None):
        super().__init__(line, column)
        self.value = value

class VarRef(Expr):
    def __init__(self, name, line=None, column=None):
        super().__init__(line, column)
        self.name = name

class ArrayAccess(Expr):
    def __init__(self, array, index, line=None, column=None):
        super().__init__(line, column)
        self.array = array
        self.index = index

class StructAccess(Expr):
    def __init__(self, obj, field, line=None, column=None):
        super().__init__(line, column)
        self.obj = obj
        self.field = field

class FunctionCall(Expr):
    def __init__(self, name, type_args, args, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.type_args = type_args  # generic type arguments: [] or [TypeNode("int")]

        # Ensure args is a list
        if not isinstance(args, list):
            args = [args]

        self.args = args

class MethodCall(Expr):
    def __init__(self, obj, method, args, line=None, column=None):
        super().__init__(line, column)
        self.obj = obj              # object expression (e.g., VarRef("p"))
        self.method = method        # method name (string)
        self.args = args            # additional arguments (without self)

class StructInit(Expr):
    def __init__(self, struct_name, type_args, fields, line=None, column=None):
        super().__init__(line, column)
        self.struct_name = struct_name
        self.type_args = type_args  # generic type arguments: [TypeNode("int")] etc.
        self.fields = fields        # list of (field_name, init_expr)

class ArrayLiteral(Expr):
    def __init__(self, elements, line=None, column=None):
        super().__init__(line, column)
        self.elements = elements

class Range(Expr):
    def __init__(self, start, end, inclusive=False, line=None, column=None):
        super().__init__(line, column)
        self.start = start              # range start expression
        self.end = end                  # range end expression
        self.inclusive = inclusive      # True for ..= (inclusive), False for .. (exclusive)

class Lambda(Expr):
    """Anonymous function expression: (params) => body  or  async (params) => body"""
    def __init__(self, params, body, is_async=False, line=None, column=None):
        super().__init__(line, column)
        self.params = params   # list of Param (type_node may be None)
        self.body = body       # Expression or Block
        self.is_async = is_async  # True for async lambda

class AwaitExpr(Expr):
    """Await expression: await expr"""
    def __init__(self, expr, line=None, column=None):
        super().__init__(line, column)
        self.expr = expr       # The expression being awaited (should be an async handle)

class WeakExpr(Expr):
    """Weak expression: weak(expr) — Future<T> から WeakTask<T> を取得する"""
    def __init__(self, expr, line=None, column=None):
        super().__init__(line, column)
        self.expr = expr       # Future<T> を返す式

# ============================================================
# Enum: Enumeration declaration and variant expression
# ============================================================
class EnumVariant(AST):
    """Single variant of an enum: Name  or  Name(T1, T2, ...)"""
    def __init__(self, name, fields=None, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.fields = fields or []   # list of TypeNode (empty = no data)

class EnumDecl(AST):
    """Enum declaration: enum Name { Variant, Variant(T), ... }"""
    def __init__(self, name, variants, line=None, column=None):
        super().__init__(line, column)
        self.name = name
        self.variants = variants     # list of EnumVariant

class EnumVariantExpr(Expr):
    """Enum variant construction expression: EnumName::VariantName  or  EnumName::VariantName(args)
    Also used for static method call/reference: TypeName::method(args)  or  TypeName::method
    has_parens=True means () was explicitly written (call site), False means no parentheses (reference).
    """
    def __init__(self, enum_name, variant_name, args=None, line=None, column=None, has_parens=False):
        super().__init__(line, column)
        self.enum_name = enum_name
        self.variant_name = variant_name
        self.args = args or []       # list of Expr (one per payload field)
        self.has_parens = has_parens # True if () was written (call), False if no parens (reference)

# ============================================================
# Match: match expression nodes
# ============================================================
class MatchArm(AST):
    """Single arm of a match: pattern => body_expr"""
    def __init__(self, pattern, body, line=None, column=None):
        super().__init__(line, column)
        self.pattern = pattern   # one of the Pattern classes below
        self.body = body         # Expr (the arm's value)

class MatchExpr(Expr):
    """match scrutinee { pattern => expr, ... }
    If no arm matches, raises MatchError at runtime.
    """
    def __init__(self, scrutinee, arms, line=None, column=None):
        super().__init__(line, column)
        self.scrutinee = scrutinee   # Expr being matched
        self.arms = arms             # list of MatchArm

class BlockExpr(Expr):
    """ブロック式: { stmt; stmt; expr }
    最後の要素が式の場合はその値がブロック全体の値になる。
    """
    def __init__(self, stmts, result_expr, line=None, column=None):
        super().__init__(line, column)
        self.stmts = stmts            # list of Statement (最後以外)
        self.result_expr = result_expr  # Expr or None (最後の式)

# --- Pattern nodes ---
class LiteralPattern(AST):
    """Matches a literal value: 42, "hello", true, false"""
    def __init__(self, value, line=None, column=None):
        super().__init__(line, column)
        self.value = value  # Python value (int / float / str / bool)

class EnumPattern(AST):
    """Matches an enum variant: Enum::Variant  or  Enum::Variant(a, b)"""
    def __init__(self, enum_name, variant_name, bindings=None, line=None, column=None):
        super().__init__(line, column)
        self.enum_name    = enum_name
        self.variant_name = variant_name
        self.bindings     = bindings or []  # list of str (variable names to bind)

class StructPattern(AST):
    """Matches a struct and binds fields: Point { x, y }"""
    def __init__(self, struct_name, fields, line=None, column=None):
        super().__init__(line, column)
        self.struct_name = struct_name
        self.fields      = fields  # list of str (field names; each also becomes a binding)

class RegexPattern(AST):
    """Matches a string against a regex: regex("^[0-9]+$")"""
    def __init__(self, pattern_str, line=None, column=None):
        super().__init__(line, column)
        self.pattern_str = pattern_str  # str: the regex pattern

class BindingPattern(AST):
    """Catches-all and binds value to name: n  (lowercase ident)
    Always matches; binds the scrutinee value to the given name inside the arm body.
    """
    def __init__(self, name, line=None, column=None):
        super().__init__(line, column)
        self.name = name
