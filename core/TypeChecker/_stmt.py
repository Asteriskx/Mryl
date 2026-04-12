from Ast import *
from MrylError import *
from TypeChecker._proto import _TypeCheckerBase


class TypeCheckerStmtMixin(_TypeCheckerBase):
    """文（Statement）レベルの型チェックを担当する Mixin。

    check_block / check_statement / check_let / check_const_decl /
    check_conditional_block / check_assignment /
    check_if / check_while / check_for / check_return
    """

    # ============================================
    # ブロック
    # ============================================
    def check_block(self, block: Block, expected_return_type):
        self.env.append({})

        for stmt in block.statements:
            self.check_statement(stmt, expected_return_type)

        self.env.pop()

    # ============================================
    # 文ディスパッチャ
    # ============================================
    def check_statement(self, stmt, expected_return_type):
        if isinstance(stmt, LetDecl):
            self.check_let(stmt)

        elif isinstance(stmt, FixDecl):
            self.check_fix(stmt)

        elif isinstance(stmt, Assignment):
            self.check_assignment(stmt)

        elif isinstance(stmt, IfStmt):
            self.check_if(stmt, expected_return_type)

        elif isinstance(stmt, WhileStmt):
            self.check_while(stmt, expected_return_type)

        elif isinstance(stmt, ForStmt):
            self.check_for(stmt, expected_return_type)

        elif isinstance(stmt, ReturnStmt):
            self.check_return(stmt, expected_return_type)

        elif isinstance(stmt, BreakStmt):
            pass  # 型チェック不要

        elif isinstance(stmt, ContinueStmt):
            pass  # 型チェック不要

        elif isinstance(stmt, ExprStmt):
            self.check_expr(stmt.expr)

        elif isinstance(stmt, ConditionalBlock):
            self.check_conditional_block(stmt, expected_return_type)

        else:
            raise TypeError_(f"Unknown statement type: {stmt}", stmt)

    # ============================================
    # let
    # ============================================
    def check_let(self, stmt: LetDecl):
        if stmt.type_node is None:
            # 型推論
            if stmt.init_expr is None:
                raise TypeError_(f"Cannot infer type of '{stmt.name}' without initializer", stmt)
            inferred = self.check_expr(stmt.init_expr)
            # void 型は変数に代入できない（for_each 等の副作用専用操作を let に使うのを禁止）
            if inferred.name == 'void':
                raise TypeError_(f"Cannot assign void-typed expression to '{stmt.name}'", stmt.init_expr)
            stmt.type_node = inferred
        else:
            # 動的配列の空リテラル初期化: let arr: T[] = [] → 型チェックをスキップ
            if (stmt.type_node.array_size == -1 and
                    stmt.init_expr is not None and
                    stmt.init_expr.__class__.__name__ == "ArrayLiteral" and
                    len(stmt.init_expr.elements) == 0):
                self.env[-1][stmt.name] = stmt.type_node
                return
            expr_type = self.check_expr(stmt.init_expr)
            if not self.types_equal(expr_type, stmt.type_node):
                raise TypeError_(
                    f"Type mismatch in let {stmt.name}: expected {stmt.type_node}, got {expr_type}",
                    stmt.init_expr
                )

        # 変数をスコープに登録
        self.env[-1][stmt.name] = stmt.type_node

    # ============================================
    # fix (不変変数)
    # ============================================
    def check_fix(self, stmt: FixDecl):
        if stmt.init_expr is None:
            raise TypeError_(f"'fix' declaration '{stmt.name}' must have an initializer", stmt)

        if stmt.type_node is None:
            # 型推論
            inferred = self.check_expr(stmt.init_expr)
            # void 型は変数に代入できない（for_each 等の副作用専用操作を fix に使うのを禁止）
            if inferred.name == 'void':
                raise TypeError_(f"Cannot assign void-typed expression to '{stmt.name}'", stmt.init_expr)
            stmt.type_node = inferred
        else:
            expr_type = self.check_expr(stmt.init_expr)
            if not self.types_equal(expr_type, stmt.type_node):
                raise TypeError_(
                    f"Type mismatch in fix {stmt.name}: expected {stmt.type_node}, got {expr_type}",
                    stmt.init_expr
                )

        # 変数をスコープに登録 + 不変セットに追加
        self.env[-1][stmt.name] = stmt.type_node
        self.fix_vars.add(stmt.name)
    def check_const_decl(self, stmt: ConstDecl):
        """Check const declaration and evaluate its value"""
        try:
            expr_type = self.check_expr(stmt.init_expr)
            # Store const value with its type
            self.const_table[stmt.name] = {
                'type': expr_type,
                'expr': stmt.init_expr
            }
        except Exception as e:
            raise TypeError_(f"Error in const declaration '{stmt.name}': {e}", stmt)

    # ============================================
    # conditional block (#ifdef / #if 等)
    # ============================================
    def check_conditional_block(self, stmt: ConditionalBlock, expected_return_type):
        """Check conditional compilation block"""
        # For conditional blocks, we check both branches
        # (The actual condition evaluation happens at runtime/code gen)
        self.check_block(stmt.then_block, expected_return_type)

        if stmt.else_block is not None:
            self.check_block(stmt.else_block, expected_return_type)

    # ============================================
    # 代入
    # ============================================
    def check_assignment(self, stmt: Assignment):
        # 不変変数への再代入チェック
        if isinstance(stmt.target, VarRef) and stmt.target.name in self.fix_vars:
            raise TypeError_(f"Cannot assign to immutable variable '{stmt.target.name}' (declared with 'fix')", stmt)

        target_type = self.check_expr(stmt.target)
        expr_type = self.check_expr(stmt.expr)

        # void 式への代入は明示的にエラー（型不一致より先に検出して分かりやすいメッセージを出す）
        if expr_type.name == 'void':
            raise TypeError_("Cannot assign void-typed expression", stmt.expr)

        if not self.types_equal(target_type, expr_type):
            raise TypeError_(
                f"Type mismatch in assignment: {target_type} = {expr_type}",
                stmt
            )

    # ============================================
    # if
    # ============================================
    def check_if(self, stmt: IfStmt, expected_return_type):
        cond_type = self.check_expr(stmt.condition)
        if cond_type.name != "bool":
            raise TypeError_("Condition of if must be bool", stmt.condition)

        # then は必ず Block
        self.check_block(stmt.then_block, expected_return_type)

        # else は Block または IfStmt
        if stmt.else_block:
            if isinstance(stmt.else_block, IfStmt):
                self.check_if(stmt.else_block, expected_return_type)
            else:
                self.check_block(stmt.else_block, expected_return_type)

    # ============================================
    # while
    # ============================================
    def check_while(self, stmt: WhileStmt, expected_return_type):
        cond_type = self.check_expr(stmt.condition)
        if cond_type.name != "bool":
            raise TypeError_("Condition of while must be bool", stmt.condition)

        self.check_block(stmt.body, expected_return_type)

    # ============================================
    # for (Rust 風 / C 風)
    # ============================================
    def check_for(self, stmt: ForStmt, expected_return_type):
        if stmt.is_c_style:
            # C-style: for (let i = 0; i < 10; i++)
            init_type = self.check_expr(stmt.iterable)  # init_expr stored in iterable
            self.env[-1][stmt.variable] = init_type

            # 条件式は bool
            cond_type = self.check_expr(stmt.condition)
            if cond_type.name != "bool":
                raise TypeError_("Loop condition must be bool", stmt.condition)

            # 更新式
            if isinstance(stmt.update, Assignment):
                self.check_assignment(stmt.update)
            else:
                self.check_expr(stmt.update)
        else:
            # Rust-style: for x in iterable
            iterable_type = self.check_expr(stmt.iterable)

            # 要素型を決定
            if isinstance(stmt.iterable, Range):
                element_type = TypeNode("i32")  # range は整数
            elif iterable_type.array_size is not None:
                # 多次元配列 (Array ラッパー) の場合、要素型は type_args[0]
                if iterable_type.name == "Array" and iterable_type.type_args:
                    element_type = iterable_type.type_args[0]
                else:
                    element_type = TypeNode(iterable_type.name, array_size=None, type_args=iterable_type.type_args)
            else:
                raise TypeError_(f"Cannot iterate over {iterable_type}", stmt.iterable)

            # ループ変数をスコープに登録
            self.env[-1][stmt.variable] = element_type

        # ループ本体をチェック
        self.check_block(stmt.body, expected_return_type)

        # ループ変数をスコープから除去
        if stmt.variable in self.env[-1]:
            del self.env[-1][stmt.variable]

    # ============================================
    # return
    # ============================================
    def check_return(self, stmt: ReturnStmt, expected_return_type):
        expr_type = self.check_expr(stmt.expr)
        # void 式を return に渡すのは禁止（for_each 等の副作用専用操作を返せない）
        if expr_type.name == 'void':
            raise TypeError_("Cannot return void-typed expression", stmt.expr)
        if expected_return_type is not None and not self.types_equal(expr_type, expected_return_type):
            raise TypeError_(
                f"Return type mismatch: expected {expected_return_type}, got {expr_type}",
                stmt.expr
            )
