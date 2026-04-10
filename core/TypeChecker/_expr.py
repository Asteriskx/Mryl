from Ast import *
from MrylError import *
from TypeChecker._proto import _TypeCheckerBase
from TypeChecker._util import (
    INTEGER_TYPES, FLOAT_TYPES,
    is_integer_type as _is_integer_type,
    is_float_type as _is_float_type,
    is_numeric_type as _is_numeric_type,
)


class TypeCheckerExprMixin(_TypeCheckerBase):
    """式（Expression）レベルの型チェックを担当する Mixin。

    check_expr / lookup_var / _pattern_bindings_scope /
    check_lambda / check_await /
    check_unary / check_binary /
    check_array_access / check_array_literal /
    is_integer_type / is_float_type / is_numeric_type
    """

    # ============================================
    # 式ディスパッチャ
    # ============================================
    def check_expr(self, expr):
        if isinstance(expr, NumberLiteral):
            if hasattr(expr, 'explicit_type') and expr.explicit_type:
                return TypeNode(expr.explicit_type)
            return TypeNode("i32")

        if isinstance(expr, FloatLiteral):
            if hasattr(expr, 'explicit_type') and expr.explicit_type:
                return TypeNode(expr.explicit_type)
            return TypeNode("f64")

        if isinstance(expr, StringLiteral):
            return TypeNode("string")

        if isinstance(expr, BoolLiteral):
            return TypeNode("bool")

        if isinstance(expr, VarRef):
            return self.lookup_var(expr.name, expr)

        if isinstance(expr, BinaryOp):
            return self.check_binary(expr)

        if isinstance(expr, UnaryOp):
            return self.check_unary(expr)

        if isinstance(expr, ArrayAccess):
            return self.check_array_access(expr)

        if isinstance(expr, StructAccess):
            return self.check_struct_access(expr)

        if isinstance(expr, FunctionCall):
            return self.check_call(expr)

        if isinstance(expr, MethodCall):
            return self.check_method_call(expr)

        if isinstance(expr, StructInit):
            return self.check_struct_init(expr)

        if isinstance(expr, ArrayLiteral):
            return self.check_array_literal(expr)

        if isinstance(expr, Range):
            start_type = self.check_expr(expr.start)
            end_type   = self.check_expr(expr.end)

            if not self.is_numeric_type(start_type.name):
                raise TypeError_(f"Range start must be numeric, got {start_type}", expr.start)
            if not self.is_numeric_type(end_type.name):
                raise TypeError_(f"Range end must be numeric, got {end_type}", expr.end)
            if not self.types_equal(start_type, end_type):
                raise TypeError_(f"Range bounds must be same type: {start_type} vs {end_type}", expr)

            return TypeNode("Range", type_args=[start_type])

        if isinstance(expr, AwaitExpr):
            return self.check_await(expr)

        if isinstance(expr, WeakExpr):
            return self.check_weak(expr)

        if isinstance(expr, Lambda):
            return self.check_lambda(expr)

        if isinstance(expr, EnumVariantExpr):
            # Task::when_all / Task::when_any — ユーザー定義 struct Task がない場合のみ
            if expr.enum_name == "Task" and expr.variant_name in ("when_all", "when_any") \
                    and not self.structs.get("Task"):
                if not expr.args or not expr.has_parens:
                    raise TypeError_(f"Task::{expr.variant_name} requires an array argument", expr)
                arr = expr.args[0]
                if not isinstance(arr, ArrayLiteral) or not arr.elements:
                    raise TypeError_(f"Task::{expr.variant_name} argument must be a non-empty array literal", expr)
                # 各要素が Future<T> であることを確認、T を取得
                elem_type = self.check_expr(arr.elements[0])
                if elem_type.name != "Future" or not elem_type.type_args:
                    raise TypeError_(f"Task::{expr.variant_name}: elements must be async task (Future<T>), got {elem_type}", arr.elements[0])
                T = elem_type.type_args[0]
                if T.name == "void":
                    raise TypeError_(f"Task::{expr.variant_name}: void Task is not supported", expr)
                # 全要素の型が一致することを確認
                for elem in arr.elements[1:]:
                    et = self.check_expr(elem)
                    if not self.types_equal(et, elem_type):
                        raise TypeError_(f"Task::{expr.variant_name}: all tasks must have the same type, got {et} and {elem_type}", elem)
                # CodeGenerator で型別ランタイム関数を選択できるよう T キーと TypeNode を AST に付与
                # _tc_type_key: Result<i32,string> → "Result_i32_string"（再帰的複合キー）
                def _tc_type_key(t):
                    if not getattr(t, 'type_args', None):
                        return t.name
                    return t.name + "_" + "_".join(_tc_type_key(a) for a in t.type_args)
                expr._combinator_elem_type = _tc_type_key(T)
                expr._combinator_elem_type_node = T  # CodeGenerator の _type_to_c 用
                if expr.variant_name == "when_all":
                    # Future<T[]>: type_args を保持して Result の型引数を失わない
                    return TypeNode("Future", type_args=[TypeNode(T.name, array_size=-1, type_args=list(T.type_args))])
                else:
                    # Future<T>
                    return TypeNode("Future", type_args=[T])

            # Subject<T>::new() — Subject<T> を返す（ユーザー定義 struct Subject がない場合のみ）
            if expr.enum_name == "Subject" and expr.variant_name == "new" \
                    and not self.structs.get("Subject"):
                # 型引数 T を取得（Subject<i32>::new() の i32 部分）
                if not expr.type_args:
                    raise TypeError_("Subject::new() requires a type argument, e.g. Subject<i32>::new()", expr)
                T = expr.type_args[0] if isinstance(expr.type_args[0], TypeNode) else TypeNode(expr.type_args[0])
                # AST ノードに型引数を付与（CodeGenerator で使用）
                expr._subject_elem_type = T.name
                return TypeNode("Subject", type_args=[T])

            # Box::new(v) — Box<T> を返す（ユーザー定義 struct Box がない場合のみ）
            if expr.enum_name == "Box" and expr.variant_name == "new" and expr.args \
                    and not self.structs.get("Box"):
                inner = self.check_expr(expr.args[0])
                return TypeNode("Box", type_args=[inner])

            # TypeName::member が static fn の呼び出し/参照か enum variant かを判定する
            struct = self.structs.get(expr.enum_name)
            if struct:
                # struct の static fn を探す
                method = next(
                    (m for m in struct.methods if m.name == expr.variant_name and getattr(m, 'is_static', False)),
                    None
                )
                if method:
                    if expr.has_parens:
                        # TypeName::method(args) — 呼び出し、戻り値型を返す
                        return method.return_type if method.return_type else TypeNode("void")
                    else:
                        # TypeName::method — fn 型変数への参照
                        param_types = [p.type_node for p in method.params]
                        ret_type    = method.return_type if method.return_type else TypeNode("void")
                        return TypeNode("fn", type_args=param_types + [ret_type])
            return TypeNode(expr.enum_name)

        if isinstance(expr, MatchExpr):
            self.check_expr(expr.scrutinee)
            arm_types = []
            for arm in expr.arms:
                scope = self._pattern_bindings_scope(arm.pattern)
                self.env.append(scope)
                try:
                    t = self.check_expr(arm.body)
                except Exception:
                    t = TypeNode("any")
                self.env.pop()
                arm_types.append(t)
            return arm_types[0] if arm_types else TypeNode("void")

        if isinstance(expr, BlockExpr):
            self.env.append({})
            try:
                for stmt in expr.stmts:
                    self.check_statement(stmt, TypeNode("any"))
                ret = TypeNode("any")
                if expr.result_expr is not None:
                    ret = self.check_expr(expr.result_expr)
            finally:
                self.env.pop()
            return ret

        raise TypeError_(f"Unknown expression type: {expr}", expr)

    # ============================================
    # パターンバインディングスコープ
    # ============================================
    def _pattern_bindings_scope(self, pattern):
        """Return a scope dict with binding names introduced by the pattern."""
        if isinstance(pattern, BindingPattern):
            return {pattern.name: TypeNode("any")}
        if isinstance(pattern, EnumPattern):
            return {name: TypeNode("any") for name in pattern.bindings}
        if isinstance(pattern, StructPattern):
            return {f: TypeNode("any") for f in pattern.fields}
        return {}

    # ============================================
    # 変数解決
    # ============================================
    def lookup_var(self, name, expr):
        # ローカルスコープを内側から検索
        for scope in reversed(self.env):
            if name in scope:
                return scope[name]

        # const テーブルを検索
        if name in self.const_table:
            return self.const_table[name]['type']

        # トップレベル関数をコールバックとして渡す場合は fn 型として解決
        if name in self.functions:
            fn_decl = self.functions[name]
            param_types = [p.type_node if p.type_node else TypeNode("any")
                           for p in (fn_decl.params or [])]
            ret_type = fn_decl.return_type if fn_decl.return_type else TypeNode("void")
            return TypeNode("fn", type_args=param_types + [ret_type])

        # None はビルトインの Option 値
        if name == "None":
            return TypeNode("Option")

        raise TypeError_(f"Undefined variable: {name}", expr)

    # ============================================
    # Lambda
    # ============================================
    def check_lambda(self, expr: Lambda):
        """ラムダ式の型チェック。TypeNode("fn") を返す。"""
        self.env.append({})
        param_types = []
        for p in expr.params:
            ptype = p.type_node if p.type_node is not None else TypeNode("any")
            self.env[-1][p.name] = ptype
            param_types.append(ptype)

        if isinstance(expr.body, Block):
            inferred_rt = None
            for stmt in expr.body.statements:
                try:
                    self.check_statement(stmt, None)
                except Exception:
                    pass
                if stmt.__class__.__name__ == 'ReturnStmt' and stmt.expr is not None:
                    if inferred_rt is None:
                        try:
                            inferred_rt = self.check_expr(stmt.expr)
                        except Exception:
                            pass
            return_type = inferred_rt if inferred_rt is not None else TypeNode("void")
        else:
            try:
                return_type = self.check_expr(expr.body)
            except Exception:
                return_type = TypeNode("any")

        self.env.pop()

        # 推論した戻り値型をノードに保存（CodeGenerator が参照）
        expr.inferred_return_type = return_type
        return TypeNode("fn", type_args=param_types + [return_type])

    # ============================================
    # AwaitExpr
    # ============================================
    def check_await(self, expr: AwaitExpr):
        """await 式の型チェック。Future<T> を T にアンラップ。"""
        handle_type = self.check_expr(expr.expr)
        # WeakTask<T> を await しようとしたらエラー（設計規約: cancel 後は await しない）
        if handle_type.name == "WeakTask":
            raise TypeError_("cannot await WeakTask<T>; use Future<T> handle for await", expr)
        if handle_type.name == "Future" and handle_type.type_args:
            return handle_type.type_args[0]
        return TypeNode("void")

    # ============================================
    # WeakExpr
    # ============================================
    def check_weak(self, expr: WeakExpr):
        """weak(handle) の型チェック。Future<T> → WeakTask<T>。"""
        inner = self.check_expr(expr.expr)
        if inner.name != "Future" or not inner.type_args:
            raise TypeError_(f"weak() requires Future<T>, got {inner}", expr)
        return TypeNode("WeakTask", type_args=[inner.type_args[0]])

    # ============================================
    # 型分類ヘルパー
    # ============================================
    def is_integer_type(self, type_name: str) -> bool:
        return _is_integer_type(type_name)

    def is_float_type(self, type_name: str) -> bool:
        return _is_float_type(type_name)

    def is_numeric_type(self, type_name: str) -> bool:
        return _is_numeric_type(type_name)

    # ============================================
    # 単項演算
    # ============================================
    def check_unary(self, expr: UnaryOp):
        operand = self.check_expr(expr.operand)

        if expr.op == "!":
            if not (operand.name == "bool" or self.is_numeric_type(operand.name)):
                raise TypeError_("Unary ! requires bool or numeric type", expr)
            return TypeNode("bool")

        if expr.op == "~":
            if not self.is_numeric_type(operand.name):
                raise TypeError_("Unary ~ requires numeric type", expr)
            return operand

        if expr.op == "-":
            if not self.is_numeric_type(operand.name):
                raise TypeError_("Unary - requires numeric type", expr)
            return operand

        if expr.op == "+":
            if not self.is_numeric_type(operand.name):
                raise TypeError_("Unary + requires numeric type", expr)
            return operand

        if expr.op in ("++", "--"):
            if not self.is_numeric_type(operand.name):
                raise TypeError_(f"Unary {expr.op} requires numeric type", expr)
            return operand

        if expr.op in ("post++", "post--"):
            if not self.is_numeric_type(operand.name):
                raise TypeError_(f"Postfix {expr.op} requires numeric type", expr)
            return operand

        if expr.op == "deref":
            if operand.name == "Box" and operand.type_args:
                return operand.type_args[0]
            raise TypeError_("Deref (*) requires Box<T>", expr)

        return operand

    # ============================================
    # 二項演算
    # ============================================
    def check_binary(self, expr: BinaryOp):
        left  = self.check_expr(expr.left)
        right = self.check_expr(expr.right)
        op    = expr.op

        # 算術演算（+, -, *, /, %）
        if op in ("+", "-", "*", "/", "%"):
            if self.types_equal(left, right):
                if self.is_numeric_type(left.name) or left.name == "string":
                    return left
                raise TypeError_(f"Invalid operands for {op}", expr)

            if self.is_numeric_type(left.name) and self.is_numeric_type(right.name):
                common = self.find_common_numeric_type(left, right)
                if common:
                    return common
                raise TypeError_(
                    f"Binary {op}: incompatible numeric types. got {left.name} and {right.name}", expr
                )

            if self.is_numeric_type(left.name) or self.is_numeric_type(right.name):
                raise TypeError_(
                    f"Binary {op}: operands must have compatible types. got {left.name} and {right.name}", expr
                )

            raise TypeError_(f"Invalid operands for {op}", expr)

        # 比較演算（<, <=, >, >=）
        if op in ("<", "<=", ">", ">="):
            if self.is_numeric_type(left.name) and self.is_numeric_type(right.name):
                if self.types_equal(left, right):
                    return TypeNode("bool")
                common = self.find_common_numeric_type(left, right)
                if common:
                    return TypeNode("bool")
            raise TypeError_(f"Comparison {op}: operands must be same or compatible numeric types", expr)

        # 等価演算（==, !=）
        if op in ("==", "!="):
            if self.types_equal(left, right):
                return TypeNode("bool")
            if self.is_numeric_type(left.name) and self.is_numeric_type(right.name):
                common = self.find_common_numeric_type(left, right)
                if common:
                    return TypeNode("bool")
            raise TypeError_(f"Equality {op}: operands must have compatible types", expr)

        # 論理演算（&&, ||）
        if op in ("&&", "||"):
            if (self.is_numeric_type(left.name) or left.name == "bool") and \
               (self.is_numeric_type(right.name) or right.name == "bool"):
                return TypeNode("bool")
            raise TypeError_(f"Logical {op}: operands must be numeric or bool types", expr)

        # ビット演算（&, |, ^, <<, >>）
        if op in ("&", "|", "^", "<<", ">>"):
            if self.is_numeric_type(left.name) and self.is_numeric_type(right.name):
                if self.types_equal(left, right):
                    return left
                common = self.find_common_numeric_type(left, right)
                if common:
                    return common
            raise TypeError_(f"Bitwise {op}: operands must be compatible numeric types", expr)

        raise TypeError_(f"Unknown operator {op}", expr)

    # ============================================
    # 配列アクセス
    # ============================================
    def check_array_access(self, expr: ArrayAccess):
        array_type = self.check_expr(expr.array)
        index_type = self.check_expr(expr.index)

        if index_type.name not in {"int", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"}:
            raise TypeError_("Array index must be an integer type", expr.index)

        if array_type.array_size is None:
            raise TypeError_("Not an array", expr.array)

        return TypeNode(array_type.name)

    # ============================================
    # 配列リテラル
    # ============================================
    def check_array_literal(self, expr: ArrayLiteral):
        if not expr.elements:
            raise TypeError_("Empty array literal not supported yet", expr)

        first_type = self.check_expr(expr.elements[0])

        for e in expr.elements[1:]:
            t = self.check_expr(e)
            if not self.types_equal(t, first_type):
                raise TypeError_("All elements in array literal must have same type", e)

        return TypeNode(first_type.name, len(expr.elements))
