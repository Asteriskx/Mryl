from Ast import *
from MrylError import *


class TypeCheckerCallMixin:
    """構造体・関数・メソッド呼び出しおよびジェネリクス解決を担当する Mixin。

    check_struct_init / check_struct_access /
    check_method_call /
    check_call / check_call_non_generic
    """

    # ============================================
    # StructInit（ジェネリクス対応）
    # ============================================
    def check_struct_init(self, expr: StructInit):
        struct = self.structs.get(expr.struct_name)
        if not struct:
            raise TypeError_(f"Undefined struct: {expr.struct_name}", expr)

        # 型パラメータ数チェック
        if len(expr.type_args) != len(struct.type_params):
            raise TypeError_(
                f"Struct {expr.struct_name} expects {len(struct.type_params)} type args, "
                f"got {len(expr.type_args)}",
                expr
            )

        # T → int のような置換マップ作成
        subst = {}
        for param, arg in zip(struct.type_params, expr.type_args):
            arg_node = TypeNode(arg) if isinstance(arg, str) else arg
            subst[param] = arg_node

        # フィールドチェック
        for field in struct.fields:
            expected = self.substitute_type(field.type_node, subst)

            found = False
            for name, value_expr in expr.fields:
                if name == field.name:
                    found = True
                    value_type = self.check_expr(value_expr)
                    if not self.types_equal(value_type, expected):
                        raise TypeError_(
                            f"Field {expr.struct_name}.{name} type mismatch: "
                            f"expected {expected}, got {value_type}",
                            value_expr
                        )
            if not found:
                raise TypeError_(f"Missing field {field.name} in struct init", expr)

        return TypeNode(expr.struct_name, type_args=expr.type_args)

    # ============================================
    # StructAccess（ジェネリクス対応）
    # ============================================
    def check_struct_access(self, expr: StructAccess):
        obj_type = self.check_expr(expr.obj)
        struct   = self.structs.get(obj_type.name)

        if not struct:
            raise TypeError_(f"{obj_type.name} is not a struct", expr.obj)

        # ジェネリクス置換マップ
        subst = {}
        for param, arg in zip(struct.type_params, obj_type.type_args):
            subst[param] = arg

        for field in struct.fields:
            if field.name == expr.field:
                return self.substitute_type(field.type_node, subst)

        raise TypeError_(f"Struct {obj_type.name} has no field {expr.field}", expr)

    # ============================================
    # MethodCall
    # ============================================
    def check_method_call(self, expr: MethodCall):
        obj_type = self.check_expr(expr.obj)

        # 動的配列 (T[]) / Iter<T> のメソッド
        if obj_type.array_size == -1:
            # Iter<T> は type_args[0] が要素型、それ以外は name が要素型
            if obj_type.name == "Iter" and obj_type.type_args:
                raw = obj_type.type_args[0]
                elem_type = raw if isinstance(raw, TypeNode) else TypeNode(raw)
            else:
                elem_type = TypeNode(obj_type.name, type_args=obj_type.type_args)

            # ── 既存の配列操作 ──
            if expr.method == 'push':
                return TypeNode('void')
            elif expr.method == 'pop':
                return elem_type
            elif expr.method == 'len':
                return TypeNode('i32')
            elif expr.method == 'is_empty':
                return TypeNode('bool')
            elif expr.method == 'remove':
                return elem_type
            elif expr.method == 'insert':
                return TypeNode('void')

            # ── Iter<T> / LINQ 操作 ──
            elif expr.method in ('select', 'filter', 'take', 'skip', 'select_many', 'to_array',
                                 'aggregate', 'for_each', 'count', 'first', 'any', 'all'):
                return self._check_iter_method(expr, elem_type)

            else:
                raise TypeError_(f"Dynamic array has no method '{expr.method}'", expr)

        # string 型の組み込みメソッド
        if obj_type.name == "string":
            if expr.method == 'len':
                return TypeNode('i32')
            elif expr.method in ('contains', 'starts_with', 'ends_with'):
                return TypeNode('bool')
            elif expr.method in ('trim', 'to_upper', 'to_lower'):
                return TypeNode('string')
            elif expr.method == 'replace':
                return TypeNode('string')
            elif expr.method == 'find':
                return TypeNode('Option', type_args=[TypeNode('i32')])
            elif expr.method == 'split':
                return TypeNode('string', array_size=-1)
            else:
                raise TypeError_(f"string has no method '{expr.method}'", expr)

        # Box<T> の .unbox() メソッド（ユーザー定義 struct Box がない場合のみ）
        if obj_type.name == "Box" and not self.structs.get("Box"):
            if expr.method == 'unbox':
                if obj_type.type_args:
                    t = obj_type.type_args[0]
                    return t if isinstance(t, TypeNode) else TypeNode(t)
                return TypeNode("any")
            raise TypeError_(f"Box has no method '{expr.method}'", expr)

        # Result<T,E> のメソッド
        if obj_type.name == "Result":
            if expr.method in ("is_ok", "is_err"):
                return TypeNode("bool")
            if expr.method in ("try", "unwrap"):
                # Ok 型 (第1型引数) を返す
                if obj_type.type_args:
                    return obj_type.type_args[0] if isinstance(obj_type.type_args[0], TypeNode) else TypeNode(obj_type.type_args[0])
                return TypeNode("i32")
            if expr.method in ("unwrap_err", "err"):
                # Err 型 (第2型引数) を返す
                if len(obj_type.type_args) >= 2:
                    t = obj_type.type_args[1]
                    return t if isinstance(t, TypeNode) else TypeNode(t)
                return TypeNode("i32")
            if expr.method == "unwrap_or":
                if obj_type.type_args:
                    return obj_type.type_args[0] if isinstance(obj_type.type_args[0], TypeNode) else TypeNode(obj_type.type_args[0])
                return TypeNode("i32")
            raise TypeError_(f"Result has no method '{expr.method}'", expr)

        # 構造体のメソッド
        struct = self.structs.get(obj_type.name)
        if not struct:
            raise TypeError_(
                f"{obj_type.name} is not a struct, cannot call method {expr.method}", expr.obj
            )

        method = next((m for m in struct.methods if m.name == expr.method), None)
        if not method:
            raise TypeError_(f"Struct {obj_type.name} has no method {expr.method}", expr)

        # 引数数チェック（self を除外）
        expected_arg_count = len(method.params) - 1
        if len(expr.args) != expected_arg_count:
            raise TypeError_(
                f"Method {expr.method} expects {expected_arg_count} arguments, "
                f"got {len(expr.args)}",
                expr
            )

        arg_types = [self.check_expr(arg) for arg in expr.args]

        # ジェネリクス置換マップ（構造体の型引数）
        subst = {}
        for param, arg in zip(struct.type_params, obj_type.type_args):
            # type_args が str の場合は TypeNode に変換しておく (#32)
            subst[param] = TypeNode(arg) if isinstance(arg, str) else arg

        # 各引数の型をメソッドのパラメータと照合（self を除外）
        for i, (arg_t, param) in enumerate(zip(arg_types, method.params[1:])):
            param_t = self.substitute_type(param.type_node, subst)
            if not self.types_equal(arg_t, param_t):
                raise TypeError_(
                    f"Argument {i} to {expr.method}: expected {param_t}, got {arg_t}",
                    expr.args[i]
                )

        return self.substitute_type(method.return_type, subst)

    # ============================================
    # FunctionCall（ジェネリクス解決含む）
    # ============================================
    def check_call(self, expr: FunctionCall):
        # cancel(token) — 組み込み関数: WeakTask<T> を受け取り void を返す
        if expr.name == "cancel":
            if len(expr.args) != 1:
                raise TypeError_("cancel() requires exactly 1 argument", expr)
            arg_type = self.check_expr(expr.args[0])
            if arg_type.name != "WeakTask":
                raise TypeError_(f"cancel() requires WeakTask<T>, got {arg_type}", expr.args[0])
            return TypeNode("void")

        # ラムダ変数 / fn型パラメータへの呼び出し (#41)
        for scope in reversed(self.env):
            if expr.name in scope:
                var_type = scope[expr.name]
                if isinstance(var_type, TypeNode) and var_type.name in ("fn", "async_fn"):
                    if var_type.type_args:
                        return var_type.type_args[-1]
                    return TypeNode("void")

        func = self.functions.get(expr.name)
        if not func:
            # Ok/Err/Some はビルトイン扱い
            if expr.name in ("Ok", "Err"):
                return TypeNode("Result")
            if expr.name == "Some":
                return TypeNode("Option")
            raise TypeError_(f"Undefined function: {expr.name}", expr)

        # 1. 引数数チェック（builtin は除外）
        if func.body is not None and len(expr.args) != len(func.params):
            raise TypeError_("Argument count mismatch", expr)

        # 2. 非ジェネリック関数
        if not func.type_params:
            return self.check_call_non_generic(expr, func)

        # 3. ジェネリック関数 ─ 明示的型引数
        if expr.type_args:
            if len(expr.type_args) != len(func.type_params):
                raise TypeError_(
                    f"Function {func.name} expects {len(func.type_params)} type args, "
                    f"got {len(expr.type_args)}",
                    expr
                )
            subst = dict(zip(func.type_params, expr.type_args))

        else:
            # 4. 型推論（制約解決）
            subst = {}
            for arg_expr, param in zip(expr.args, func.params):
                arg_type   = self.check_expr(arg_expr)
                param_type = param.type_node

                if param_type.name in func.type_params:
                    if param_type.name not in subst:
                        subst[param_type.name] = arg_type
                    else:
                        if not self.types_equal(subst[param_type.name], arg_type):
                            raise TypeError_(
                                f"Type inference failed for {func.name}: "
                                f"conflicting types for {param_type.name}",
                                arg_expr
                            )
                else:
                    if not self.types_equal(arg_type, param_type):
                        raise TypeError_(
                            f"Argument type mismatch in call to {func.name}", arg_expr
                        )

            # 全型パラメータが解決されたか確認
            for t in func.type_params:
                if t not in subst:
                    raise TypeError_(
                        f"Cannot infer type parameter {t} in call to {func.name}", expr
                    )

        # 5. パラメータ型チェック（置換後）
        for arg_expr, param in zip(expr.args, func.params):
            arg_type = self.check_expr(arg_expr)
            expected = self.substitute_type(param.type_node, subst)
            if not self.types_equal(arg_type, expected):
                raise TypeError_(
                    f"Argument type mismatch in call to {func.name}: "
                    f"expected {expected}, got {arg_type}",
                    arg_expr
                )

        # 6. 戻り値型（置換後）
        ret_type = self.substitute_type(func.return_type, subst)
        if getattr(func, 'is_async', False):
            return TypeNode("Future", type_args=[ret_type] if ret_type else [TypeNode("void")])
        return ret_type

    # ============================================
    # 非ジェネリック関数呼び出し
    # ============================================
    def check_call_non_generic(self, expr: FunctionCall, func: FunctionDecl):
        # builtin 関数（body=None）は引数型チェックをスキップ
        if func.body is None:
            for arg in expr.args:
                self.check_expr(arg)
            return func.return_type

        # ユーザー定義関数
        arg_types = [self.check_expr(arg) for arg in expr.args]

        for arg_t, param in zip(arg_types, func.params):
            param_t = param.type_node
            if not self.types_equal(arg_t, param_t):
                raise TypeError_(
                    f"Argument type mismatch in call to {func.name}: "
                    f"expected {param_t}, got {arg_t}",
                    expr
                )

        if getattr(func, 'is_async', False):
            rt = func.return_type if func.return_type is not None else TypeNode("void")
            return TypeNode("Future", type_args=[rt])
        return func.return_type

    # ============================================
    # Iter<T> メソッドの型検査
    # ============================================
    def _check_iter_method(self, expr: MethodCall, elem_type: 'TypeNode'):
        """動的配列 / Iter<T> の LINQ 系メソッドの戻り値型を返す。"""

        def _iter(t: 'TypeNode') -> 'TypeNode':
            """Iter<T> を表す TypeNode を生成する（内部表現は array_size=-1）。"""
            return TypeNode(t.name, type_args=t.type_args, array_size=-1)

        def _check_lambda_sig(arg_idx, expected_param=None, expected_ret=None, expected_count=None):
            """ラムダ/関数引数の fn 型を取得し、引数数・引数型・戻り値型を検査する。

            check_expr を呼ぶことでラムダの inferred_return_type もセットされる。
            expected_count: None → スキップ。int → パラメータ数を照合。
            expected_param: None → スキップ。TypeNode → elem_type と照合。
            expected_ret:   None → スキップ。TypeNode → 戻り値型と照合。
            戻り値: fn TypeNode（type_args = [param..., return_type]）
            """
            if arg_idx >= len(expr.args):
                return None
            arg_expr = expr.args[arg_idx]
            fn_type = self.check_expr(arg_expr)

            if not (isinstance(fn_type, TypeNode) and fn_type.name in ('fn', 'async_fn')):
                raise TypeError_(f"'{method}': argument {arg_idx} must be a function", arg_expr)

            type_args = fn_type.type_args or []
            # type_args = [param0_type, ..., return_type]（最後が戻り値型）

            # パラメータ数検査: type_args の末尾が戻り値型なので len-1 がパラメータ数
            if expected_count is not None and type_args:
                actual_count = len(type_args) - 1
                if actual_count != expected_count:
                    raise TypeError_(
                        f"'{method}': lambda expects {expected_count} parameter(s), got {actual_count}",
                        arg_expr
                    )

            # パラメータ型検査: 'any'（アノテーションなしラムダ）はスキップ
            if expected_param is not None and len(type_args) >= 2:
                actual_param = type_args[0]
                if not self.types_equal(actual_param, expected_param):
                    raise TypeError_(
                        f"'{method}': lambda parameter type mismatch: "
                        f"expected {expected_param}, got {actual_param}",
                        arg_expr
                    )

            # 戻り値型検査
            if expected_ret is not None and type_args:
                actual_ret = type_args[-1]
                if actual_ret.name != 'any' and not self.types_equal(actual_ret, expected_ret):
                    raise TypeError_(
                        f"'{method}': lambda return type mismatch: "
                        f"expected {expected_ret}, got {actual_ret}",
                        arg_expr
                    )

            return fn_type

        method = expr.method

        if method == 'select':
            # select(fn(T)->U) -> Iter<U>
            fn_type = _check_lambda_sig(0, expected_param=elem_type, expected_ret=None, expected_count=1)
            if fn_type and fn_type.type_args:
                raw = fn_type.type_args[-1]
                u = raw if isinstance(raw, TypeNode) else TypeNode(raw)
            else:
                u = elem_type
            return _iter(u)

        if method == 'filter':
            # filter(fn(T)->bool) -> Iter<T>
            _check_lambda_sig(0, expected_param=elem_type, expected_ret=TypeNode('bool'), expected_count=1)
            return _iter(elem_type)

        if method in ('take', 'skip'):
            # take/skip(i32) -> Iter<T>: ラムダなし
            return _iter(elem_type)

        if method == 'select_many':
            # select_many(fn(T)->U[]) -> Iter<U>
            fn_type = _check_lambda_sig(0, expected_param=elem_type, expected_ret=None, expected_count=1)
            if fn_type and fn_type.type_args:
                raw = fn_type.type_args[-1]
                u = raw if isinstance(raw, TypeNode) else TypeNode(raw)
            else:
                u = elem_type
            return _iter(u)

        if method == 'to_array':
            # to_array() -> T[]
            return TypeNode(elem_type.name, type_args=elem_type.type_args, array_size=-1)

        if method == 'aggregate':
            if len(expr.args) == 1:
                # 初期値なし: aggregate(fn(T,T)->T) -> Result<T, string>
                _check_lambda_sig(0, expected_param=None, expected_ret=None, expected_count=2)
                return TypeNode('Result', type_args=[elem_type, TypeNode('string')])
            else:
                # 初期値あり: aggregate(seed: U, fn(U,T)->U) -> U
                u = self.check_expr(expr.args[0]) if expr.args else elem_type
                _check_lambda_sig(1, expected_param=None, expected_ret=None, expected_count=2)
                return u

        if method == 'for_each':
            # for_each(fn(T)->void) -> void: 戻り値型は強制しない（値が捨てられるため）
            _check_lambda_sig(0, expected_param=elem_type, expected_ret=None, expected_count=1)
            return TypeNode('void')

        if method == 'count':
            return TypeNode('i32')

        if method == 'first':
            return TypeNode('Result', type_args=[elem_type, TypeNode('string')])

        if method in ('any', 'all'):
            # any/all(fn(T)->bool) -> bool
            _check_lambda_sig(0, expected_param=elem_type, expected_ret=TypeNode('bool'), expected_count=1)
            return TypeNode('bool')

        raise TypeError_(f"Unknown iter method '{method}'", expr)
