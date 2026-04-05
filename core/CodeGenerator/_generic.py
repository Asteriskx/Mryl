from __future__ import annotations
from Ast import TypeNode, FunctionDecl, Param
from CodeGenerator._proto import _CodeGeneratorBase

class CodeGeneratorGenericMixin(_CodeGeneratorBase):
    """ジェネリック関数のスキャン・特殊化・型推論を担当する Mixin
    _register_generic_instantiation / _substitute_function /
    _substitute_type_node / _get_instantiated_func_name /
    _infer_generic_type_args / _infer_expr_type /
    _scan_generic_calls / _scan_statement_for_generic_calls /
    _scan_expr_for_generic_calls
    """

    def _register_generic_instantiation(self, func_name: str, type_args):
        """(Implementation detail)"""
        func = self.program_functions.get(func_name)
        if not func or not func.type_params:
            return

        type_args_tuple = tuple(str(t) for t in type_args)
        key = (func_name, type_args_tuple)

        if key in self.generic_instantiations:
            return

        subst = dict(zip(func.type_params, type_args))
        instantiated_func = self._substitute_function(func, subst, type_args_tuple)
        self.generic_instantiations[key] = instantiated_func

    def _substitute_function(self, func: FunctionDecl, subst: dict, type_args_tuple):
        """(Implementation detail)"""
        new_name = self._get_instantiated_func_name(func.name, type_args_tuple)

        new_params = []
        for param in func.params:
            new_type = self._substitute_type_node(param.type_node, subst)
            new_p = Param(param.name, new_type, param.line, param.column)
            new_p.is_fix = getattr(param, 'is_fix', False)
            new_params.append(new_p)

        new_return_type = self._substitute_type_node(func.return_type, subst) if func.return_type else None

        new_func = FunctionDecl(
            new_name, new_params, new_return_type, func.body,
            [], func.is_async, func.line, func.column
        )
        return new_func

    def _substitute_type_node(self, type_node, subst):
        """(Implementation detail)"""
        if not type_node:
            return type_node

        if type_node.name in subst:
            replacement = subst[type_node.name]
            if isinstance(replacement, TypeNode):
                return replacement
            else:
                return TypeNode(str(replacement).split('[')[0])

        if type_node.array_size:
            return TypeNode(type_node.name, type_node.array_size, None)

        if type_node.type_args:
            new_type_args = [self._substitute_type_node(arg, subst) for arg in type_node.type_args]
            return TypeNode(type_node.name, type_node.array_size, new_type_args)

        return type_node

    def _get_instantiated_func_name(self, func_name: str, type_args_tuple) -> str:
        """(Implementation detail)"""
        type_str = "_".join(
            str(t).replace("<", "_").replace(">", "").replace(",", "_")
            for t in type_args_tuple
        )
        return f"{func_name}_{type_str}"

    def _infer_generic_type_args(self, func: FunctionDecl, arg_exprs):
        """(Implementation detail)"""
        type_args: list[str | None] = [None] * len(func.type_params)

        for i, arg_expr in enumerate(arg_exprs):
            if i >= len(func.params):
                break

            param_type = func.params[i].type_node
            arg_type   = self._infer_expr_type(arg_expr)

            if param_type.name in func.type_params:
                param_idx = func.type_params.index(param_type.name)
                if type_args[param_idx] is None:
                    type_args[param_idx] = arg_type

        return [t if t else "int32_t" for t in type_args]

    def _infer_expr_type(self, expr):
        """(Implementation detail)"""
        expr_class = expr.__class__.__name__

        if expr_class == "NumberLiteral":
            if expr.explicit_type:
                return expr.explicit_type
            return "i32"

        if expr_class == "FloatLiteral":
            if expr.explicit_type:
                return expr.explicit_type
            return "f64"

        if expr_class == "StringLiteral":
            return "string"

        if expr_class == "BoolLiteral":
            return "bool"

        if expr_class == "VarRef":
            if expr.name == "None":
                return "Option"
            for env_dict in reversed(self.env):
                if expr.name in env_dict:
                    return env_dict[expr.name]
            return "i32"

        if expr_class == "BinaryOp":
            left_t  = self._infer_expr_type(expr.left)
            right_t = self._infer_expr_type(expr.right)
            if left_t == right_t:
                return left_t
            # 数値昇格: f64 > f32 > u64 > u32 > i64 > i32 > ...
            _RANK = {"i8":1,"i16":2,"i32":3,"i64":4,
                     "u8":5,"u16":6,"u32":7,"u64":8,"f32":9,"f64":10}
            if left_t in _RANK and right_t in _RANK:
                return left_t if _RANK[left_t] >= _RANK[right_t] else right_t
            return left_t  # string 連結など

        if expr_class == "FunctionCall":
            if expr.name in ("Ok", "Err"):
                return "Result"
            if expr.name == "Some":
                return "Option"
            # 組み込みマクロ/関数の戻り値型を直接解決 (#25 to_string 対応)
            _builtin_return_types = {
                "to_string": "string",
                "read_line": "string",
                "parse_int": "Result_i32",
                "parse_f64": "Result_f64",
                "checked_div": "Result_i32",
                "print": "void",
                "println": "void",
            }
            if expr.name in _builtin_return_types:
                return _builtin_return_types[expr.name]
            fn = self.program_functions.get(expr.name)
            if fn and fn.return_type:
                if fn.return_type.name == "Result":
                    # type_args が取れる場合は ok 型を付加する (例: "Result_f64")
                    type_args = getattr(fn.return_type, 'type_args', None)
                    if type_args:
                        ok_name = type_args[0].name if hasattr(type_args[0], 'name') else str(type_args[0])
                        return f"Result_{ok_name}"
                    return "Result"
                if fn.return_type.name == "Option":
                    type_args = getattr(fn.return_type, 'type_args', None)
                    if type_args:
                        inner_name = type_args[0].name if hasattr(type_args[0], 'name') else str(type_args[0])
                        return f"MrylOption_{inner_name}"
                    return "Option"
                # ジェネリック関数: 型引数を推論して戻り値型を解決 (#26)
                if fn.type_params and fn.return_type.name in fn.type_params:
                    type_args = self._infer_generic_type_args(fn, expr.args)
                    subst = dict(zip(fn.type_params, type_args))
                    resolved = subst.get(fn.return_type.name, fn.return_type.name)
                    return resolved
                return fn.return_type.name
            return "i32"

        if expr_class == "MethodCall":
            obj_t = self._infer_expr_type(expr.obj)

            # Subject<T> / Observable<T> のメソッド戻り値型
            # env には "Subject_T" / "Observable_T" 形式で登録される
            if (obj_t.startswith("Subject_") or obj_t.startswith("Observable_") or
                    obj_t.startswith("MrylSubject_")):
                if "_" in obj_t:
                    T_suffix = obj_t.split("_", 1)[1].rstrip("*").strip()
                else:
                    T_suffix = "i32"
                if expr.method in ("filter", "map", "take", "skip", "merge"):
                    return f"Observable_{T_suffix}"
                if expr.method == "subscribe":
                    return "Subscription"
                if expr.method in ("emit", "complete", "error", "unsubscribe"):
                    return "void"

            if obj_t == "Result" or obj_t.startswith("Result_"):
                if expr.method in ("is_ok", "is_err"):
                    return "bool"
                if expr.method in ("try", "unwrap", "unwrap_or", "err"):
                    # Result_<ok>_<err> の形式から ok 型を取り出す
                    if obj_t.startswith("Result_") and obj_t != "Result_i32_i32":
                        parts = obj_t[len("Result_"):].split("_", 1)
                        return parts[0]  # e.g. "f64", "i32", "string"
                    return "i32"
                if expr.method in ("unwrap_err",):
                    if obj_t.startswith("Result_") and len(obj_t.split("_")) >= 3:
                        return obj_t.split("_", 2)[2]  # err 型
                    return "i32"
            # string 組み込みメソッド
            if obj_t == "string":
                if expr.method == 'len':
                    return "i32"
                if expr.method in ('contains', 'starts_with', 'ends_with'):
                    return "bool"
                if expr.method in ('trim', 'to_upper', 'to_lower', 'replace'):
                    return "string"
            # 動的配列 / Iter<T> の LINQ 系メソッド
            if obj_t.startswith("vec_") or obj_t.startswith("MrylVec_"):
                prefix = "vec_" if obj_t.startswith("vec_") else "MrylVec_"
                elem_c = obj_t[len(prefix):]
                m = expr.method
                if m in ('select', 'filter', 'take', 'skip', 'to_array'):
                    return f"vec_{elem_c}"   # Iter<T> / T[] は vec_T で表す
                if m == 'select_many':
                    # select_many(fn(T)->U[]) -> Iter<U>
                    # Lambda の inferred_return_type から U を取得して vec_U を返す。
                    # elem_c が "vec_U" 形式（外側配列の要素型）の場合は elem_c をそのまま返す。
                    if expr.args:
                        from Ast import Lambda
                        lam_arg = expr.args[0]
                        if isinstance(lam_arg, Lambda):
                            inferred = getattr(lam_arg, 'inferred_return_type', None)
                            if inferred is not None:
                                return f"vec_{inferred.name}"
                    # フォールバック: elem_c が "vec_U" なら U の vec (flatten 1段)
                    return elem_c if elem_c.startswith("vec_") else f"vec_{elem_c}"
                if m == 'count':
                    return "i32"
                if m in ('any', 'all'):
                    return "bool"
                if m in ('first', 'aggregate'):
                    return f"Result_{elem_c}_string"
                if m == 'for_each':
                    return "void"
            # struct メソッドの戻り値型を検索 (#29/#30 正確な型推論)
            for struct in self.structs:
                if struct.name == obj_t:
                    for method in struct.methods:
                        if method.name == expr.method and method.return_type:
                            return method.return_type.name
            # ジェネリック具体化名 "Box_string" からのメソッド戻り値型推論 (#32)
            for struct in self.structs:
                if getattr(struct, 'type_params', None) and obj_t.startswith(struct.name + '_'):
                    suffix = obj_t[len(struct.name) + 1:]
                    targs  = suffix.split('_')
                    subst  = dict(zip(struct.type_params, targs))
                    for method in struct.methods:
                        if method.name == expr.method and method.return_type:
                            rt = method.return_type.name
                            return subst.get(rt, rt)
            return "i32"

        if expr_class == "MatchExpr":
            _scrutinee_type = self._infer_expr_type(expr.scrutinee)
            for arm in expr.arms:
                from Ast import BindingPattern
                if isinstance(arm.pattern, BindingPattern) and arm.pattern.name == "_":
                    continue
                scope = self._pattern_binding_types(arm.pattern, _scrutinee_type)
                self.env.append(scope)
                t = self._infer_expr_type(arm.body)
                self.env.pop()
                if t not in ("any", "i32"):
                    return t
            for arm in expr.arms:
                from Ast import BindingPattern
                if isinstance(arm.pattern, BindingPattern) and arm.pattern.name == "_":
                    continue
                scope = self._pattern_binding_types(arm.pattern, _scrutinee_type)
                self.env.append(scope)
                t = self._infer_expr_type(arm.body)
                self.env.pop()
                return t
            return "i32"

        if expr_class == "StructAccess":
            obj_type = self._infer_expr_type(expr.obj)
            for struct in self.structs:
                if struct.name == obj_type:
                    for field in struct.fields:
                        if field.name == expr.field:
                            return field.type_node.name
            # ジェネリック具体化名 (例: "Box_string") からの型推論 (#31)
            for struct in self.structs:
                if getattr(struct, 'type_params', None) and obj_type.startswith(struct.name + '_'):
                    suffix = obj_type[len(struct.name)+1:]
                    targs = suffix.split('_')
                    subst = dict(zip(struct.type_params, targs))
                    for field in struct.fields:
                        if field.name == expr.field:
                            return subst.get(field.type_node.name, field.type_node.name)
            return "i32"

        if expr_class == "ArrayAccess":
            # 配列要素の型を推論する (Bug#7/Bug#8 fix)
            # 動的配列 vec_var_types[name] → 要素型
            # 固定長配列 env[name] → 要素型が直接登録されている
            arr_name = expr.array.name if expr.array.__class__.__name__ == 'VarRef' else None
            if arr_name:
                if arr_name in self.vec_var_types:
                    return self.vec_var_types[arr_name]
                for scope in reversed(self.env):
                    if arr_name in scope:
                        t = scope[arr_name]
                        if t.startswith("vec_"):
                            return t[4:]
                        return t
            return "i32"

        if expr_class == "EnumVariantExpr":
            # Box::new(v) → ポインタ型を返す
            if expr.enum_name == "Box" and expr.variant_name == "new" and expr.args:
                inner = self._infer_expr_type(expr.args[0])
                return f"{self._type_to_c_base(inner)}*"
            # TypeName::member が static fn ならその戻り値型を返す
            for struct in self.structs:
                if struct.name == expr.enum_name:
                    method = next(
                        (m for m in struct.methods if m.name == expr.variant_name and getattr(m, 'is_static', False)),
                        None
                    )
                    if method and method.return_type:
                        return method.return_type.name
            return expr.enum_name  # enum variant の場合は enum 名を型とする

        if expr_class == "UnaryOp":
            if expr.op == "deref":
                operand_t = self._infer_expr_type(expr.operand)
                # C pointer: "int32_t*" → "int32_t"
                if operand_t.endswith("*"):
                    return operand_t[:-1]
                # Box_T 形式: "Box_i32" → "i32"
                if operand_t.startswith("Box_"):
                    return operand_t[4:]
                return "i32"
            return self._infer_expr_type(expr.operand)

        return "i32"

    def _scan_generic_calls(self, block):
        """(Implementation detail)"""
        if not block or not hasattr(block, 'statements'):
            return

        for stmt in block.statements:
            self._scan_statement_for_generic_calls(stmt)

    def _scan_statement_for_generic_calls(self, stmt):
        """(Implementation detail)"""
        stmt_class = stmt.__class__.__name__

        if stmt_class == "ExprStmt":
            self._scan_expr_for_generic_calls(stmt.expr)
        elif stmt_class == "LetDecl":
            if stmt.init_expr:
                self._scan_expr_for_generic_calls(stmt.init_expr)
        elif stmt_class == "IfStmt":
            self._scan_expr_for_generic_calls(stmt.condition)
            self._scan_generic_calls(stmt.then_block)
            if stmt.else_block:
                self._scan_generic_calls(stmt.else_block)
        elif stmt_class == "WhileStmt":
            self._scan_expr_for_generic_calls(stmt.condition)
            self._scan_generic_calls(stmt.body)
        elif stmt_class == "ForStmt":
            self._scan_expr_for_generic_calls(stmt.iterable)
            if stmt.condition:
                self._scan_expr_for_generic_calls(stmt.condition)
            if stmt.update:
                self._scan_expr_for_generic_calls(stmt.update)
            self._scan_generic_calls(stmt.body)
        elif stmt_class == "ReturnStmt":
            if stmt.expr:
                self._scan_expr_for_generic_calls(stmt.expr)
        elif stmt_class == "Block":
            self._scan_generic_calls(stmt)

    def _scan_expr_for_generic_calls(self, expr):
        """(Implementation detail)"""
        if not expr:
            return

        expr_class = expr.__class__.__name__

        if expr_class == "FunctionCall":
            func = self.program_functions.get(expr.name)
            if func and func.type_params:
                type_args = self._infer_generic_type_args(func, expr.args)
                self._register_generic_instantiation(expr.name, type_args)
            for arg in expr.args:
                self._scan_expr_for_generic_calls(arg)
        elif expr_class == "BinaryOp":
            self._scan_expr_for_generic_calls(expr.left)
            self._scan_expr_for_generic_calls(expr.right)
        elif expr_class == "UnaryOp":
            self._scan_expr_for_generic_calls(expr.operand)
        elif expr_class == "StructInit":
            if hasattr(expr, 'fields'):
                for _, value_expr in expr.fields:
                    self._scan_expr_for_generic_calls(value_expr)
        elif expr_class == "ArrayLiteral":
            if hasattr(expr, 'elements'):
                for elem in expr.elements:
                    self._scan_expr_for_generic_calls(elem)
        elif expr_class == "MethodCall":
            self._scan_expr_for_generic_calls(expr.obj)
            for arg in expr.args:
                self._scan_expr_for_generic_calls(arg)
        elif expr_class == "ArrayAccess":
            self._scan_expr_for_generic_calls(expr.array)
            self._scan_expr_for_generic_calls(expr.index)

    # ------------------------------------------------------------------
    # ジェネリック構造体の具体化収集
    # ------------------------------------------------------------------
    def _scan_generic_struct_uses(self, program):
        """プログラム全体を走査してジェネリック構造体の具体化を収集する。
        戻り値: OrderedDict  {(struct_name, (type_arg_names...)): [(c_type, field_name), ...]}
        """
        from collections import OrderedDict
        result = OrderedDict()
        struct_map = {s.name: s for s in program.structs}

        def scan_expr(e):
            if e is None:
                return
            cls = e.__class__.__name__
            if cls == "StructInit" and getattr(e, 'type_args', []):
                key = (e.struct_name, tuple(t if isinstance(t, str) else t.name for t in e.type_args))
                if key not in result:
                    s = struct_map.get(e.struct_name)
                    if s and getattr(s, 'type_params', None):
                        subst = dict(zip(s.type_params, [
                            (t if isinstance(t, str) else t.name) for t in e.type_args
                        ]))
                        fields = []
                        for f in s.fields:
                            resolved_name = subst.get(f.type_node.name, None)
                            if resolved_name:
                                c_type = self._type_to_c_base(resolved_name)
                            else:
                                c_type = self._type_to_c(f.type_node)
                            fields.append((c_type, f.name))
                        result[key] = fields
                for _, v in (e.fields or []):
                    scan_expr(v)
            elif cls == "FunctionCall":
                for a in (e.args or []):
                    scan_expr(a)
            elif cls == "BinaryOp":
                scan_expr(e.left)
                scan_expr(e.right)
            elif cls == "UnaryOp":
                scan_expr(getattr(e, 'operand', None))
            elif cls == "MethodCall":
                scan_expr(e.obj)
                for a in (e.args or []):
                    scan_expr(a)
            elif cls == "ArrayLiteral":
                for elem in (e.elements or []):
                    scan_expr(elem)
            elif cls == "MatchExpr":
                scan_expr(e.scrutinee)
                for arm in e.arms:
                    scan_expr(arm.body)

        def scan_stmt(s):
            if s is None:
                return
            cls = s.__class__.__name__
            if cls == "LetDecl":
                scan_expr(s.init_expr)
            elif cls == "ExprStmt":
                scan_expr(s.expr)
            elif cls == "ReturnStmt":
                scan_expr(s.expr)
            elif cls == "AssignStmt":
                scan_expr(getattr(s, 'value', None))
            elif cls == "IfStmt":
                scan_expr(s.condition)
                if s.then_block:
                    for st in s.then_block.statements:
                        scan_stmt(st)
                if s.else_block:
                    eb = s.else_block
                    if eb.__class__.__name__ == "IfStmt":
                        scan_stmt(eb)
                    else:
                        for st in eb.statements:
                            scan_stmt(st)
            elif cls in ("ForStmt", "WhileStmt"):
                if s.body:
                    for st in s.body.statements:
                        scan_stmt(st)
            elif cls == "Block":
                for st in s.statements:
                    scan_stmt(st)

        for func in program.functions:
            if func.body:
                for stmt in func.body.statements:
                    scan_stmt(stmt)
        return result
