from __future__ import annotations
import re as _re
from Ast import BindingPattern, EnumPattern, StructPattern
from CodeGenerator._util import _safe_c_name
from CodeGenerator._proto import _CodeGeneratorBase

class CodeGeneratorExprMixin(_CodeGeneratorBase):
    """式(Expression)レベルの C コード生成を担当する Mixin
    _generate_expr / _generate_expr_with_temps /
    _generate_function_call / _generate_print_call /
    _generate_struct_init / _generate_match_expr /
    _infer_match_result_c_type / _pattern_binding_types /
    _match_pattern_to_c / _generate_method_call
    """

    def _generate_expr(self, expr) -> str:
        """式ノードを C 式文字列として返す (ディスパッチャ) """
        if expr is None:
            return ""

        expr_class = expr.__class__.__name__

        if expr_class == "NumberLiteral":
            return str(expr.value)

        if expr_class == "FloatLiteral":
            return str(expr.value)

        if expr_class == "StringLiteral":
            escaped = self._c_escape(expr.value)
            return f'make_mryl_string("{escaped}")'

        if expr_class == "BoolLiteral":
            return "1" if expr.value else "0"

        if expr_class == "VarRef":
            if expr.name == "None":
                struct_name = self.current_return_type or "MrylOption_int32_t"
                return f"({struct_name}){{0, 0}}"
            if self.sm_mode and expr.name in self.sm_vars:
                return f"__sm->{expr.name}"
            if expr.name in self.capture_map:
                return self.capture_map[expr.name]
            if expr.name in self.ident_renames:
                return self.ident_renames[expr.name]
            return _safe_c_name(expr.name)

        if expr_class == "BinaryOp":
            left       = self._generate_expr(expr.left)
            right      = self._generate_expr(expr.right)
            op         = expr.op
            left_type  = self._infer_expr_type(expr.left)
            right_type = self._infer_expr_type(expr.right)
            if left_type == "string" and right_type == "string":
                if op == "+":
                    return f"mryl_string_concat({left}, {right})"
                if op == "==":
                    return f"(strcmp({self._strip_outer_parens(left)}.data, {self._strip_outer_parens(right)}.data) == 0)"
                if op == "!=":
                    return f"(strcmp({self._strip_outer_parens(left)}.data, {self._strip_outer_parens(right)}.data) != 0)"
            # ゼロ除算チェック: 整数 / と % はランタイムチェック付きヘルパーに変換
            if op in ("/", "%") and left_type not in ("f32", "f64") and right_type not in ("f32", "f64"):
                helper = "mryl_safe_div" if op == "/" else "mryl_safe_mod"
                return f"{helper}({left}, {right})"
            # && / || を明示的にマップ(他は同一)
            c_op = {"&&": "&&", "||": "||"}.get(op, op)
            return f"({left} {c_op} {right})"

        if expr_class == "UnaryOp":
            operand = self._generate_expr(expr.operand)
            if expr.op == "post++":
                return f"({operand}++)"
            elif expr.op == "post--":
                return f"({operand}--)"
            elif expr.op == "!":
                return f"(!{operand})"
            elif expr.op == "~":
                return f"(~{operand})"
            elif expr.op == "deref":
                return f"(*{operand})"
            else:
                return f"({expr.op}{operand})"

        if expr_class == "FunctionCall":
            return self._generate_function_call(expr)

        if expr_class == "StructAccess":
            obj = self._generate_expr(expr.obj)
            # self はポインタ渡しなので -> を使用 (Bug#28)
            op = "->" if (expr.obj.__class__.__name__ == "VarRef" and expr.obj.name == "self") else "."
            return f"{obj}{op}{expr.field}"

        if expr_class == "ArrayAccess":
            arr      = self._generate_expr(expr.array)
            idx      = self._generate_expr(expr.index)
            arr_name = expr.array.name if expr.array.__class__.__name__ == 'VarRef' else None
            if arr_name and arr_name in self.vec_var_types:
                return f"{arr}.data[{idx}]"
            return f"{arr}[{idx}]"

        if expr_class == "StructInit":
            return self._generate_struct_init(expr)

        if expr_class == "EnumVariantExpr":
            return self._generate_enum_variant_expr(expr)

        if expr_class == "MatchExpr":
            return self._generate_match_expr(expr)

        if expr_class == "MethodCall":
            return self._generate_method_call(expr)

        if expr_class == "Lambda":
            return self._generate_lambda(expr)

        if expr_class == "ArrayLiteral":
            # 動的配列リテラルを式として生成する。
            # LetDecl 以外（ラムダの return 式など）で配列リテラルが使われた場合に対応。
            # mryl_vec_{et}_from((ct[]){elems...}, n) として新規 MrylVec を返す。
            if not expr.elements:
                return "/* empty array literal */"
            elem_t  = self._infer_expr_type(expr.elements[0])
            ct      = self._type_to_c_base(elem_t)
            elems_c = ", ".join(f"({ct}){self._generate_expr(e)}" for e in expr.elements)
            n       = len(expr.elements)
            return f"mryl_vec_{elem_t}_from(({ct}[]){{{elems_c}}}, {n})"

        if expr_class == "AwaitExpr":
            return "/* await - use let statement for typed await */"

        return "0"

    def _generate_expr_with_temps(self, expr, temp_string_mapping: dict) -> str:
        """一時文字列変数マッピングを考慮して式を生成する """
        if expr is None:
            return ""

        expr_class = expr.__class__.__name__

        if expr_class == "StringLiteral":
            if id(expr) in temp_string_mapping:
                return temp_string_mapping[id(expr)]
            return self._generate_expr(expr)

        if expr_class == "FunctionCall":
            for scope in reversed(self.env):
                if expr.name in scope and scope[expr.name] in ('fn', 'fn_closure'):
                    return self._generate_function_call(expr)
            # Lambda / static メソッド参照 / 名前付き関数参照 を含む場合は
            # fat pointer 変換が必要なので _generate_function_call に委譲（issue ②, #75, #76）
            if any(
                arg.__class__.__name__ == "Lambda"
                or (arg.__class__.__name__ == "EnumVariantExpr" and not arg.has_parens)
                for arg in expr.args
            ):
                return self._generate_function_call(expr)
            # Ok/Err/Some は compound literal 生成が必要なので _generate_function_call に委譲
            if expr.name in ("Ok", "Err", "Some"):
                return self._generate_function_call(expr)
            args = [self._generate_expr_with_temps(arg, temp_string_mapping) for arg in expr.args]
            if expr.name in ["print", "println"]:
                return self._generate_print_call(expr)
            func = self.program_functions.get(expr.name)
            if func and func.type_params:
                type_args       = self._infer_generic_type_args(func, expr.args)
                type_args_tuple = tuple(str(t) for t in type_args)
                self._register_generic_instantiation(expr.name, type_args)
                instantiated_name = self._get_instantiated_func_name(expr.name, type_args_tuple)
                return f"{instantiated_name}({', '.join(args)})"
            # to_string(bool) → _mryl_to_string_bool を直接呼び出す
            if expr.name == "to_string" and len(expr.args) == 1:
                arg_type = self._infer_expr_type(expr.args[0])
                if arg_type == "bool":
                    return f"_mryl_to_string_bool({', '.join(args)})"
            return f"{expr.name}({', '.join(args)})"

        if expr_class == "BinaryOp":
            left       = self._generate_expr_with_temps(expr.left,  temp_string_mapping)
            right      = self._generate_expr_with_temps(expr.right, temp_string_mapping)
            left_type  = self._infer_expr_type(expr.left)
            right_type = self._infer_expr_type(expr.right)
            if left_type == "string" and right_type == "string":
                if expr.op == "+":
                    return f"mryl_string_concat({left}, {right})"
                if expr.op == "==":
                    return f"(strcmp(({left}).data, ({right}).data) == 0)"
                if expr.op == "!=":
                    return f"(strcmp(({left}).data, ({right}).data) != 0)"
            return f"({left} {expr.op} {right})"

        return self._generate_expr(expr)

    def _generate_function_call(self, expr) -> str:
        """FunctionCall を C 式文字列として返す """
        if expr.name in ["print", "println"]:
            return self._generate_print_call(expr)

        if expr.name in ("Ok", "Err"):
            val_code    = self._generate_expr(expr.args[0]) if expr.args else "0"
            struct_name = self.current_return_type or "MrylResult_i32_i32"
            if expr.name == "Ok":
                return f"({struct_name}){{1, {{.ok_val = {val_code}}}}}"
            else:
                return f"({struct_name}){{0, {{.err_val = {val_code}}}}}"

        if expr.name == "Some":
            val_code    = self._generate_expr(expr.args[0]) if expr.args else "0"
            struct_name = self.current_return_type or "MrylOption_int32_t"
            return f"({struct_name}){{{val_code}, 1}}"

        for scope in reversed(self.env):
            if expr.name in scope and scope[expr.name] == "async_fn":
                factory = self.async_lambda_factories.get(expr.name, expr.name)
                args    = ", ".join(self._generate_expr(arg) for arg in expr.args)
                return f"{factory}({args})"
            if expr.name in scope and scope[expr.name] in ("fn", "fn_closure"):
                # fat pointer 規約で統一: c_name.fn(args, c_name.env)
                c_name   = self.ident_renames.get(expr.name, _safe_c_name(expr.name))
                args     = ", ".join(self._generate_expr(arg) for arg in expr.args)
                all_args = f"{args}, {c_name}.env" if args else f"{c_name}.env"
                return f"{c_name}.fn({all_args})"

        func = self.program_functions.get(expr.name)
        if func and func.type_params:
            type_args         = self._infer_generic_type_args(func, expr.args)
            type_args_tuple   = tuple(str(t) for t in type_args)
            self._register_generic_instantiation(expr.name, type_args)
            instantiated_name = self._get_instantiated_func_name(expr.name, type_args_tuple)
            args              = ", ".join(self._generate_expr(arg) for arg in expr.args)
            return f"{instantiated_name}({args})"

        # to_string(bool) → _mryl_to_string_bool を直接呼び出す
        # (Mryl の bool は C の int にマップされるため _Generic の _Bool ブランチに
        #  マッチしない。引数の Mryl 型を見て直接ディスパッチする)
        if expr.name == "to_string" and len(expr.args) == 1:
            arg_type = self._infer_expr_type(expr.args[0])
            if arg_type == "bool":
                arg_code = self._generate_expr(expr.args[0])
                return f"_mryl_to_string_bool({arg_code})"

        # Lambda 引数を fat pointer struct に変換（issue ②⑧: ブロックスコープ変数でアドレス確保）
        # 名前付き関数を fn(T)->U 型引数へ渡す場合も fat pointer ラッパーを生成（#75）
        called_func = self.program_functions.get(expr.name)

        # static メソッドのルックアップ: {C名 -> method} （例: "Point_origin" -> method）
        # static fn も名前付き関数と同様に fat pointer ラッパーが必要（#76）
        static_methods = {
            f"{s.name}_{m.name}": m
            for s in self.structs
            for m in s.methods
            if getattr(m, 'is_static', False)
        }

        def _is_named_fn_arg(idx: int, arg) -> bool:
            """引数が名前付き関数参照（またはstatic メソッド参照）かつ
            対応パラメータが fn(T)->U 型なら True を返す。
            ローカル変数スコープに同名がある場合は既に MrylFn_* 構造体のため対象外。"""
            cls = arg.__class__.__name__
            # static メソッド参照: Point::origin（has_parens=False の EnumVariantExpr）
            if cls == "EnumVariantExpr" and not arg.has_parens:
                c_name = f"{arg.enum_name}_{arg.variant_name}"
                if c_name not in static_methods:
                    return False
            elif cls == "VarRef":
                if any(arg.name in scope for scope in self.env):
                    return False   # ローカル fn 変数は既に MrylFn_* 構造体
                if arg.name not in self.program_functions and arg.name not in static_methods:
                    return False
            else:
                return False
            if called_func is None or idx >= len(called_func.params):
                return False
            pt = called_func.params[idx].type_node
            return pt is not None and pt.name == "fn" and bool(getattr(pt, 'type_args', None))

        has_lambda_arg   = any(arg.__class__.__name__ == "Lambda" for arg in expr.args)
        has_named_fn_arg = any(_is_named_fn_arg(i, arg) for i, arg in enumerate(expr.args))
        if has_lambda_arg or has_named_fn_arg:
            args_list = []
            for i, arg in enumerate(expr.args):
                if arg.__class__.__name__ == "Lambda":
                    lam_name_v = self._generate_lambda(arg)
                    info       = self.lambda_captures.get(lam_name_v, {})
                    caps       = info.get('captures', {})
                    ret_c_v    = info.get('ret_c', 'int32_t')
                    arg_cs_v   = info.get('arg_cs', [])
                    arg_part   = "_".join(c.replace("*", "Ptr").replace(" ", "_") for c in arg_cs_v) if arg_cs_v else "void"
                    ret_part   = ret_c_v.replace("*", "Ptr").replace(" ", "_")
                    fn_c_type  = f"MrylFn_{arg_part}_ret_{ret_part}"
                    self.fn_type_registry.add((tuple(arg_cs_v), ret_c_v, fn_c_type))
                    if caps:
                        env_struct = f"{lam_name_v}_env_t"
                        env_var    = f"__lam_e_{lam_name_v}"
                        fields     = ", ".join(
                            f".{n} = {self.ident_renames.get(n, _safe_c_name(n))}" for n in caps
                        )
                        # ⑧ ブロックスコープのローカル変数として emit（stmt expr より安全）
                        self._emit(f"{env_struct} {env_var} = {{{fields}}};")
                        args_list.append(f"({fn_c_type}){{{lam_name_v}, &{env_var}}}")
                    else:
                        args_list.append(f"({fn_c_type}){{{lam_name_v}, NULL}}")
                elif _is_named_fn_arg(i, arg):
                    # 名前付き関数 / static メソッド → void* __e 付き thunk を生成して fat pointer に包む（#75, #76）
                    # pending_lambdas により thunk は関数前方に static 関数として出力される
                    # EnumVariantExpr(Point::origin) は c_func_name="Point_origin", fn_decl=static method
                    if arg.__class__.__name__ == "EnumVariantExpr":
                        c_func_name = f"{arg.enum_name}_{arg.variant_name}"
                        fn_decl     = static_methods[c_func_name]
                    else:
                        c_func_name = arg.name
                        fn_decl     = self.program_functions.get(arg.name) or static_methods[arg.name]
                    thunk_name   = f"__thunk_{self.thunk_counter}"
                    self.thunk_counter += 1
                    t_params_c   = [
                        f"{self._type_to_c(p.type_node) if p.type_node else 'int32_t'} {p.name}"
                        for p in fn_decl.params
                    ]
                    t_params_str = ", ".join(t_params_c)
                    t_ret        = self._type_to_c(fn_decl.return_type) if fn_decl.return_type else "void"
                    call_args    = ", ".join(p.name for p in fn_decl.params)
                    ret_kw       = "return " if t_ret != "void" else ""
                    # thunk 本体: c_func_name = C 関数名（static メソッドは "Struct_method" 形式）
                    self.pending_lambdas.append(
                        (thunk_name, t_ret, t_params_str, [f"    {ret_kw}{c_func_name}({call_args});"], {})
                    )
                    arg_cs_t = [self._type_to_c(p.type_node) if p.type_node else "int32_t" for p in fn_decl.params]
                    self.lambda_captures[thunk_name] = {'captures': {}, 'ret_c': t_ret, 'arg_cs': arg_cs_t}
                    pt        = called_func.params[i].type_node
                    fn_c_type = self._type_to_c(pt)
                    wrap_var  = f"__wrap_{_safe_c_name(c_func_name)}_{self.thunk_counter - 1}"
                    self._emit(f"{fn_c_type} {wrap_var} = {{{thunk_name}, NULL}};")
                    args_list.append(wrap_var)
                else:
                    args_list.append(self._generate_expr(arg))
            return f"{expr.name}({', '.join(args_list)})"

        args = ", ".join(self._generate_expr(arg) for arg in expr.args)
        return f"{expr.name}({args})"

    def _generate_print_call(self, expr) -> str:
        """print/println 呼び出しを C printf/printf+\n 呼び出しに変換する """
        if not expr.args:
            return f'{expr.name}("")'

        first_arg = expr.args[0]

        if first_arg.__class__.__name__ == "StringLiteral":
            if len(expr.args) > 1:
                fmt_str     = first_arg.value
                format_args = expr.args[1:]
                parts       = fmt_str.split("{}")
                if len(parts) != len(format_args) + 1:
                    # {} の数と引数が一致しない: 各 {} に対して型に応じた spec を使用
                    raw_parts = fmt_str.split("{}")
                    fmt_c = ""
                    for j, rp in enumerate(raw_parts[:-1]):
                        spec = self._type_to_fmt_spec(format_args[j]) if j < len(format_args) else "%d"
                        fmt_c += rp.replace("%", "%%") + spec
                    fmt_c += raw_parts[-1].replace("%", "%%")
                    fmt_c  = fmt_c.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
                    args  = [f'"{fmt_c}"']
                    for a in format_args:
                        arg_type = self._infer_expr_type(a)
                        arg_code = self._generate_expr(a)
                        if arg_type in ("string", "str"):
                            args.append(f"{arg_code}.data")
                        elif arg_type == "bool":
                            args.append(f"({arg_code} ? \"true\" : \"false\")")
                        else:
                            args.append(arg_code)
                    return f'{expr.name}({", ".join(args)})'
                fmt_c = ""
                for i, part in enumerate(parts[:-1]):
                    spec   = self._type_to_fmt_spec(format_args[i])
                    fmt_c += part.replace("%", "%%") + spec
                fmt_c += parts[-1].replace("%", "%%")
                fmt_c  = fmt_c.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
                c_args = [f'"{fmt_c}"']
                for a in format_args:
                    arg_type = self._infer_expr_type(a)
                    arg_code = self._generate_expr(a)
                    if arg_type in ("string", "str"):
                        c_args.append(f"{arg_code}.data")
                    elif arg_type == "bool":
                        c_args.append(f"({arg_code} ? \"true\" : \"false\")")
                    else:
                        c_args.append(arg_code)
                return f'{expr.name}({", ".join(c_args)})'
            else:
                escaped = self._c_escape(first_arg.value)
                return f'{expr.name}("{escaped}")'
        else:
            arg_type = self._infer_expr_type(first_arg)
            if arg_type in ("string", "str"):
                arg_code = self._generate_expr(first_arg)
                return f'{expr.name}("%s", {arg_code}.data)'
            elif arg_type in ("f32", "f64", "float"):
                arg_code = self._generate_expr(first_arg)
                return f'{expr.name}("%g", {arg_code})'
            elif arg_type == "bool":
                arg_code = self._generate_expr(first_arg)
                return f'{expr.name}("%s", ({arg_code} ? "true" : "false"))'
            else:
                # i64→%lld / u64→%llu / u32→%u / i32→%d など
                fmt      = self._type_to_fmt_spec(first_arg)
                arg_code = self._generate_expr(first_arg)
                return f'{expr.name}("{fmt}", {arg_code})'

    def _generate_struct_init(self, expr) -> str:
        """StructInit を C99 Compound literal として返す """
        fields = ", ".join(
            f".{name} = {self._generate_expr(value)}"
            for name, value in expr.fields
        )
        # ジェネリック構造体の具体化名を使用 (例: Box<i32> → Box_i32)
        if getattr(expr, 'type_args', []):
            suffix = "_".join(t if isinstance(t, str) else t.name for t in expr.type_args)
            struct_c_name = f"{expr.struct_name}_{suffix}"
        else:
            struct_c_name = expr.struct_name
        return f"({struct_c_name}){{ {fields} }}"

    def _generate_match_expr(self, expr) -> str:
        """match 式を GCC compound statement 式として生成する """
        n  = self.lambda_counter
        self.lambda_counter += 1
        mv = f"__mv_{n}"
        mr = f"__mr_{n}"

        scrutinee_c         = self._generate_expr(expr.scrutinee)
        scrutinee_type      = self._infer_expr_type(expr.scrutinee)
        scrutinee_is_string = (scrutinee_type == "string")
        result_c_type       = self._infer_match_result_c_type(expr.arms, scrutinee_type)
        match_is_void       = (result_c_type == "void")

        zero_val = (
            '""'               if result_c_type == "const char*" else
            'make_mryl_string("")' if result_c_type == "MrylString" else
            "0"
        )

        scrutinee_c_wrapped = scrutinee_c

        # インデントレベルに基づいてスペースを計算する。
        # ind0: 閉じ } の位置 (indent_level と同列)
        # ind1: __auto_type / if / __mr0; などブロック直下
        # ind2: if ブロック内の bindings / body
        ind0 = "    " * self.indent_level
        ind1 = "    " * (self.indent_level + 1)
        ind2 = "    " * (self.indent_level + 2)

        lines = [
            "({",
            f"{ind1}__auto_type {mv} = {scrutinee_c_wrapped};",
        ]
        if not match_is_void:
            lines.append(f"{ind1}{result_c_type} {mr} = {zero_val};")

        has_catch_all = False
        first = True
        for arm in expr.arms:
            pattern = arm.pattern
            klass   = pattern.__class__.__name__

            if klass == "BindingPattern" and pattern.name == "_":
                has_catch_all = True
                kw = "else" if not first else ""
                lines.append(f"{ind1}{kw} {{" if kw else f"{ind1}{{")
                self.env.append({})
                body_c       = self._generate_expr(arm.body)
                body_is_void = (self._infer_expr_type(arm.body) == "void")
                self.env.pop()
                if body_is_void:
                    lines.append(f"{ind2}{body_c};")
                else:
                    lines.append(f"{ind2}{mr} = {body_c};")
                lines.append(f"{ind1}}}")
                first = False
                continue

            cond, bindings = self._match_pattern_to_c(mv, pattern, scrutinee_is_string)

            if isinstance(pattern, (BindingPattern, StructPattern)):
                has_catch_all = True

            if cond == "1":
                kw        = "else" if not first else ""
                cond_part = ""
            else:
                kw        = "else if" if not first else "if"
                cond_part = f" ({cond})"
            if kw:
                lines.append(f"{ind1}{kw}{cond_part} {{")
            else:
                lines.append(f"{ind1}{{")
            for b in bindings:
                lines.append(f"{ind2}{b}")
            # binding 変数を env に登録してから body を生成する（型推論に必要）
            _arm_scope = self._pattern_binding_types(arm.pattern, scrutinee_type)
            self.env.append(_arm_scope)
            body_c      = self._generate_expr(arm.body)
            body_is_void = (self._infer_expr_type(arm.body) == "void")
            self.env.pop()
            if body_is_void:
                lines.append(f"{ind2}{body_c};")
            else:
                lines.append(f"{ind2}{mr} = {body_c};")
            lines.append(f"{ind1}}}")
            first = False

        if not has_catch_all:
            kw = "else" if len(expr.arms) > 0 else ""
            lines.append(f"{ind1}{kw} {{" if kw else f"{ind1}{{")
            lines.append(
                f'{ind2}mryl_panic("MatchError", "no arm matched", '
                f'__func__, __FILE__, __LINE__);'
            )
            lines.append(f"{ind1}}}")

        if not match_is_void:
            lines.append(f"{ind1}{mr};")
        lines.append(f"{ind0}}})")
        return "\n".join(lines)

    def _infer_match_result_c_type(self, arms, scrutinee_type: str = "") -> str:
        """match 式のアーム群から結果の C 型を推論する。
        全アームを走査して最も具体的な型を選ぶ（double > int32_t）。
        全アームが void の場合は "void" を返す。"""
        candidates = []
        has_non_wildcard = False
        for arm in arms:
            is_wildcard = isinstance(arm.pattern, BindingPattern) and arm.pattern.name == "_"
            if not is_wildcard:
                has_non_wildcard = True
            scope = self._pattern_binding_types(arm.pattern, scrutinee_type)
            self.env.append(scope)
            t = self._infer_expr_type(arm.body)
            self.env.pop()
            if t == "string":
                return "MrylString"
            if t == "void":
                continue  # void アームは candidates に加えない
            c = self._type_to_c_base(t)
            if c not in ("any", ""):
                candidates.append(c)
        # 全アームが void → match 式全体も void
        if not candidates and has_non_wildcard:
            return "void"
        # double が1つでもあれば double を採用（int32_t より具体的）
        if "double" in candidates:
            return "double"
        if candidates:
            return candidates[0]
        return "int32_t"

    def _pattern_binding_types(self, pattern, scrutinee_type: str = "") -> dict:
        """パターンのバインディング変数とその型のマップを返す。
        scrutinee_type: スクルティニーの型（"Result_i32", "Result_f64" 等）。
        Ok(v)/Err(e) の binding 型を解決するのに使用する。"""
        if isinstance(pattern, EnumPattern):
            # Ok(v) / Err(e) は Result 系の組み込みパターンとして特別扱い
            if pattern.enum_name == "Ok" and pattern.bindings:
                ok_type = "i32"
                if scrutinee_type.startswith("Result_"):
                    ok_part = scrutinee_type[len("Result_"):]
                    # "f64_string" → "f64", "i32_string" → "i32", "f64" → "f64"
                    ok_type = ok_part.split("_")[0] if "_" in ok_part else ok_part
                return {pattern.bindings[0]: ok_type}
            if pattern.enum_name == "Err" and pattern.bindings:
                return {pattern.bindings[0]: "string"}
            # Option<T> の Some(v) パターン
            if pattern.enum_name == "Some" and pattern.bindings:
                inner_type = "i32"
                if scrutinee_type.startswith("MrylOption_"):
                    inner_type = scrutinee_type[len("MrylOption_"):]
                return {pattern.bindings[0]: inner_type}
            enum_decl = self.enums.get(pattern.enum_name)
            if enum_decl:
                variant = next(
                    (v for v in enum_decl.variants if v.name == pattern.variant_name), None
                )
                if variant:
                    return {
                        name: (variant.fields[i].name if i < len(variant.fields) else "any")
                        for i, name in enumerate(pattern.bindings)
                    }
        if isinstance(pattern, BindingPattern):
            return {pattern.name: "any"}
        if isinstance(pattern, StructPattern):
            return {f: "any" for f in pattern.fields}
        return {}

    def _match_pattern_to_c(self, mv: str, pattern, scrutinee_is_string: bool):
        """パターンを (条件式文字列, バインディング文字列リスト) に変換する """
        klass = pattern.__class__.__name__

        if klass == "LiteralPattern":
            val = pattern.value
            if isinstance(val, bool):
                cond = f"{mv} == {1 if val else 0}"
            elif isinstance(val, str):
                escaped = val.replace('"', '\\"')
                cond = (
                    f'strcmp({mv}.data, "{escaped}") == 0'
                    if scrutinee_is_string else
                    f'strcmp({mv}, "{escaped}") == 0'
                )
            elif isinstance(val, float):
                cond = f"{mv} == {val}"
            else:
                cond = f"{mv} == {val}"
            return cond, []

        if klass == "BindingPattern":
            return "1", [f"__auto_type {pattern.name} = {mv};"]

        if klass == "EnumPattern":
            enum_name    = pattern.enum_name
            variant_name = pattern.variant_name
            # Result<T,E> の Ok/Err パターン
            if enum_name in ("Ok", "Err"):
                is_ok    = (enum_name == "Ok")
                cond     = f"{mv}.is_ok" if is_ok else f"!{mv}.is_ok"
                field    = "ok_val" if is_ok else "err_val"
                bindings = [f"__auto_type {name} = {mv}.data.{field};" for name in pattern.bindings]
                return cond, bindings
            # Option<T> の Some(v) / None パターン
            if enum_name == "Some":
                cond     = f"{mv}.has_value"
                bindings = [f"__auto_type {name} = {mv}.value;" for name in pattern.bindings]
                return cond, bindings
            if enum_name == "None":
                return f"!{mv}.has_value", []
            enum_decl    = self.enums.get(enum_name)
            has_data     = enum_decl and any(v.fields for v in enum_decl.variants)
            if has_data:
                cond     = f"{mv}.tag == {enum_name}_Tag_{variant_name}"
                bindings = [
                    f"__auto_type {name} = {mv}.data.{variant_name}._{i};"
                    for i, name in enumerate(pattern.bindings)
                ]
            else:
                cond     = f"{mv} == {enum_name}_{variant_name}"
                bindings = []
            return cond, bindings

        if klass == "StructPattern":
            bindings = [f"__auto_type {f} = {mv}.{f};" for f in pattern.fields]
            return "1", bindings

        if klass == "RegexPattern":
            pat_escaped = pattern.pattern_str.replace("\\", "\\\\").replace('"', '\\"')
            mv_data     = f"{mv}.data" if scrutinee_is_string else mv
            uid         = id(pattern) & 0xFFFF
            cond = (
                f"({{ regex_t __re_{uid}; "
                f"regcomp(&__re_{uid}, \"{pat_escaped}\", REG_EXTENDED | REG_NOSUB); "
                f"int __rc_{uid} = regexec(&__re_{uid}, {mv_data}, 0, NULL, 0); "
                f"regfree(&__re_{uid}); "
                f"__rc_{uid} == 0; }})"
            )
            return cond, []

        return "0", []

    def _generate_method_call(self, expr) -> str:
        """MethodCall を C 式文字列として返す (Vec/Result 特殊対応含む) """
        obj_type = self._infer_expr_type(expr.obj)

        # 動的配列 (MrylVec_<T>) のメソッド
        if obj_type.startswith("vec_"):
            et       = obj_type[4:]
            # SM モードでは VarRef に __sm-> プレフィックスが必要なため常に _generate_expr を使用する
            obj_name = self._generate_expr(expr.obj)
            if expr.method == 'push':
                arg = self._generate_expr(expr.args[0])
                return f"mryl_vec_{et}_push(&{obj_name}, {arg})"
            elif expr.method == 'pop':
                return f"mryl_vec_{et}_pop(&{obj_name})"
            elif expr.method == 'len':
                return f"{obj_name}.len"
            elif expr.method == 'is_empty':
                return f"({obj_name}.len == 0)"
            elif expr.method == 'remove':
                arg = self._generate_expr(expr.args[0])
                return f"mryl_vec_{et}_remove(&{obj_name}, {arg})"
            elif expr.method == 'insert':
                idx = self._generate_expr(expr.args[0])
                val = self._generate_expr(expr.args[1])
                return f"mryl_vec_{et}_insert(&{obj_name}, {idx}, {val})"

            # ── Iter<T> / LINQ 系メソッド ──────────────────────────
            elif expr.method in ('select', 'filter', 'take', 'skip',
                                 'select_many', 'to_array',
                                 'aggregate', 'for_each',
                                 'count', 'first', 'any', 'all'):
                # レシーバが MethodCall（中間 iter 結果）のとき src_is_temp=True とし、
                # _generate_iter_method 内でソースを1回評価してキャプチャ・free する。
                src_is_temp = expr.obj.__class__.__name__ == 'MethodCall'
                return self._generate_iter_method(expr, et, obj_name, src_is_temp)

        # Result<T,E> のメソッド
        obj_type = self._infer_expr_type(expr.obj)
        if obj_type == "Result" or obj_type.startswith("Result_"):
            obj_code = self._generate_expr(expr.obj)
            if expr.method == "is_ok":
                return f"({obj_code}.is_ok)"
            if expr.method == "is_err":
                return f"(!{obj_code}.is_ok)"
            if expr.method in ("try", "unwrap", "err"):
                return (
                    f"({{ __auto_type __uw = {obj_code}; "
                    f"if (!__uw.is_ok) {{ "
                    f'mryl_panic("Error", "try() called on Err value", __func__, __FILE__, __LINE__); }} '
                    f"__uw.data.ok_val; }})"
                )
            if expr.method == "unwrap_err":
                return (
                    f"({{ __auto_type __uw = {obj_code}; "
                    f"if (__uw.is_ok) {{ "
                    f'mryl_panic("UnwrapError", "unwrap_err() called on Ok value", '
                    f'__func__, __FILE__, __LINE__); }} '
                    f"__uw.data.err_val; }})"
                )
            if expr.method == "unwrap_or":
                default_code = self._generate_expr(expr.args[0]) if expr.args else "0"
                return f"({obj_code}.is_ok ? {obj_code}.data.ok_val : {default_code})"

        # Box<T> の .unbox() メソッド
        if obj_type.endswith("*") or obj_type == "Box" or obj_type.startswith("Box_"):
            if expr.method == "unbox":
                obj_code = self._generate_expr(expr.obj)
                return f"(*{obj_code})"

        # string 型の組み込みメソッド
        if obj_type == "string":
            obj_code = self._generate_expr(expr.obj)
            if expr.method == 'len':
                return f"mryl_str_len({obj_code})"
            elif expr.method == 'contains':
                arg = self._generate_expr(expr.args[0])
                return f"mryl_str_contains({obj_code}, {arg})"
            elif expr.method == 'starts_with':
                arg = self._generate_expr(expr.args[0])
                return f"mryl_str_starts_with({obj_code}, {arg})"
            elif expr.method == 'ends_with':
                arg = self._generate_expr(expr.args[0])
                return f"mryl_str_ends_with({obj_code}, {arg})"
            elif expr.method == 'trim':
                return f"mryl_str_trim({obj_code})"
            elif expr.method == 'to_upper':
                return f"mryl_str_to_upper({obj_code})"
            elif expr.method == 'to_lower':
                return f"mryl_str_to_lower({obj_code})"
            elif expr.method == 'replace':
                a0 = self._generate_expr(expr.args[0])
                a1 = self._generate_expr(expr.args[1])
                return f"mryl_str_replace({obj_code}, {a0}, {a1})"
            elif expr.method == 'find':
                self.uses_str_find = True
                self.option_type_registry.add(("int32_t", "MrylOption_int32_t"))
                arg = self._generate_expr(expr.args[0])
                return f"mryl_str_find({obj_code}, {arg})"
            elif expr.method == 'split':
                self.uses_str_split = True
                arg = self._generate_expr(expr.args[0])
                return f"mryl_str_split({obj_code}, {arg})"


        obj         = self._generate_expr(expr.obj)
        args_list   = [self._generate_expr(arg) for arg in expr.args]
        struct_name = obj_type   # Bug#27: obj の型から struct 名を解決
        all_args    = [f"&{obj}"] + args_list   # Bug#28: ポインタ渡し
        return f"{struct_name}_{expr.method}({', '.join(all_args)})"

    def _generate_iter_method(
        self, expr, et: str, obj_c: str, src_is_temp: bool = False
    ) -> str:
        """Iter<T> / LINQ メソッドの C statement expression を生成する。

        Args:
            expr        : MethodCall ノード
            et          : レシーバ要素の Mryl 型名 (e.g. "i32", "string")
            obj_c       : レシーバの C 式文字列
            src_is_temp : True のとき obj_c は MethodCall 由来の中間 MrylVec。
                          ソースをローカル変数にキャプチャし、使用後 free する。
        """
        from Ast import Lambda

        method = expr.method
        idx    = self.loop_counter
        self.loop_counter += 1
        ct     = self._type_to_c_base(et)    # Mryl 型 → C 型 (e.g. "int32_t")
        i_var  = f"__i_{idx}"

        # ── 中間ソース管理（#62 メモリリーク修正） ────────────────
        # src_is_temp=True のとき:
        #   obj_c を1回だけ評価してローカル変数に代入し、使用後に data を free する。
        # src_is_temp=False のとき:
        #   ユーザー変数を指しているため free しない。
        src_var  = f"__src_{idx}"
        src_ref  = src_var if src_is_temp else obj_c

        # ── 生成 C コード用インデント ────────────────────────────
        # statement expression 内の各文を読みやすいよう改行＋インデントを付ける。
        # base_indent: 呼び出し元のインデント（statement expression の開閉括弧位置）
        # NL         : statement expression 内の文区切り（改行＋1段深いインデント）
        base_indent = "    " * self.indent_level
        NL          = "\n" + "    " * (self.indent_level + 1)

        # src_cap / src_free もそれぞれ1文として改行を付ける
        src_cap  = f"MrylVec_{et} {src_var} = {obj_c};{NL}" if src_is_temp else ""
        # string 要素の場合は各要素の char* も解放する専用関数を使う。
        # 通常の free(v.data) だと MrylString 構造体の配列のみ解放され char* がリークする。
        if src_is_temp:
            src_free = (f"mryl_vec_string_free({src_var});{NL}" if et == "string"
                        else f"free({src_var}.data);{NL}")
        else:
            src_free = ""

        # statement expression の開閉テンプレート
        OPEN  = f"({{{NL}"
        CLOSE = f"\n{base_indent}}})"

        def _lam_full(arg_idx: int) -> tuple:
            """(env_setup, fn_expr, env_arg) を返す。fat pointer 規約対応。
            env_setup: ループ前に emit すべき env 初期化コード（"" or "TYPE var = {...};{NL}"）
            fn_expr:   呼び出す C 関数式（lam_name or c_name.fn）
            env_arg:   env 引数の C 式（"&var", "c_name.env", "NULL"）
            """
            arg = expr.args[arg_idx]
            if isinstance(arg, Lambda):
                lam_name_v = self._generate_lambda(arg)
                info       = self.lambda_captures.get(lam_name_v, {})
                captures   = info.get('captures', {})
                if captures:
                    env_struct = f"{lam_name_v}_env_t"
                    env_var    = f"__lam_env_{idx}_{arg_idx}"
                    fields     = ", ".join(
                        f".{n} = {self.ident_renames.get(n, _safe_c_name(n))}" for n in captures
                    )
                    env_setup  = f"{env_struct} {env_var} = {{{fields}}};{NL}"
                    env_arg    = f"&{env_var}"
                else:
                    env_setup = ""
                    env_arg   = "NULL"
                return env_setup, lam_name_v, env_arg
            else:
                # 変数参照: fn/fn_closure なら fat pointer から取得
                var_type = None
                if hasattr(arg, 'name'):
                    for scope in reversed(self.env):
                        if arg.name in scope:
                            var_type = scope[arg.name]
                            break
                if var_type in ('fn', 'fn_closure'):
                    c_name = self.ident_renames.get(arg.name, _safe_c_name(arg.name))
                    return "", f"{c_name}.fn", f"{c_name}.env"
                # 関数参照（issue ③）: thunk を自動生成して void* __e に対応
                c_expr   = self._generate_expr(arg)
                fn_decl  = self.program_functions.get(getattr(arg, 'name', ''))
                if fn_decl:
                    thunk_name = f"__thunk_{self.thunk_counter}"
                    self.thunk_counter += 1
                    t_params_c  = [
                        f"{self._type_to_c(p.type_node) if p.type_node else 'int32_t'} {p.name}"
                        for p in fn_decl.params
                    ]
                    t_params_str = ", ".join(t_params_c)
                    t_ret        = self._type_to_c(fn_decl.return_type) if fn_decl.return_type else "void"
                    call_args    = ", ".join(p.name for p in fn_decl.params)
                    ret_kw       = "return " if t_ret != "void" else ""
                    thunk_body   = [f"    {ret_kw}{fn_decl.name}({call_args});"]
                    self.pending_lambdas.append((thunk_name, t_ret, t_params_str, thunk_body, {}))
                    arg_cs_t = [self._type_to_c(p.type_node) if p.type_node else "int32_t" for p in fn_decl.params]
                    self.lambda_captures[thunk_name] = {'captures': {}, 'ret_c': t_ret, 'arg_cs': arg_cs_t}
                    return "", thunk_name, "NULL"
                # fallback: env 引数なし（コンパイル警告が出る可能性あり）
                return "", c_expr, "NULL"

        # ── select ──────────────────────────────────────────────
        if method == 'select':
            lam_setup, lam_fn, lam_env = _lam_full(0)
            # 出力型推論: Lambda の inferred_return_type か fallback で et
            lam_arg = expr.args[0]
            if isinstance(lam_arg, Lambda):
                inferred = getattr(lam_arg, 'inferred_return_type', None)
                out_et = inferred.name if inferred else et
            else:
                out_et = et
            out_ct = self._type_to_c_base(out_et)
            r = f"__iter_{idx}"
            return (
                f"{OPEN}"
                f"{src_cap}"
                f"{lam_setup}"
                f"MrylVec_{out_et} {r} = mryl_vec_{out_et}_new();{NL}"
                f"for (int32_t {i_var} = 0; {i_var} < {src_ref}.len; {i_var}++) {{"
                f" mryl_vec_{out_et}_push(&{r}, {lam_fn}({src_ref}.data[{i_var}], {lam_env})); }}{NL}"
                f"{src_free}"
                f"{r};"
                f"{CLOSE}"
            )

        # ── filter ──────────────────────────────────────────────
        if method == 'filter':
            lam_setup, lam_fn, lam_env = _lam_full(0)
            r = f"__iter_{idx}"
            # string 要素の場合は push 時に deep copy する。
            # src_free で元 vec の char* が解放された後も結果 vec の要素が有効であるために必要。
            push_val = (f"make_mryl_string({src_ref}.data[{i_var}].data)"
                        if et == "string" else f"{src_ref}.data[{i_var}]")
            return (
                f"{OPEN}"
                + f"{src_cap}"
                + f"{lam_setup}"
                + f"MrylVec_{et} {r} = mryl_vec_{et}_new();{NL}"
                + f"for (int32_t {i_var} = 0; {i_var} < {src_ref}.len; {i_var}++) {{"
                + f" if ({lam_fn}({src_ref}.data[{i_var}], {lam_env})) {{"
                + f" mryl_vec_{et}_push(&{r}, {push_val}); }} }}{NL}"
                + f"{src_free}"
                + f"{r};"
                + f"{CLOSE}"
            )

        # ── take ─────────────────────────────────────────────────
        # take は .len を縮めるだけでポインタ移動なし。
        # src_is_temp=True のとき: ソースをキャプチャし、所有権を結果に移す（free しない）。
        if method == 'take':
            n = self._generate_expr(expr.args[0])
            r = f"__iter_{idx}"
            return (
                f"{OPEN}"
                f"{src_cap}"
                f"MrylVec_{et} {r} = {src_ref};{NL}"
                f"if ({n} < {r}.len) {r}.len = {n};{NL}"
                f"{r};"
                f"{CLOSE}"
            )

        # ── skip ─────────────────────────────────────────────────
        # src_is_temp=False: ユーザー変数が対象 → view 方式（従来どおり）。
        # src_is_temp=True : 中間 MrylVec が対象 → オフセットポインタを free すると
        #                    UB になるため、コピー方式に変更して安全に free する。
        if method == 'skip':
            n = self._generate_expr(expr.args[0])
            s = f"__s_{idx}"
            r = f"__iter_{idx}"
            if src_is_temp:
                # string 要素の場合は push 時に deep copy する（filter と同じ理由）。
                push_val = (f"make_mryl_string({src_ref}.data[{i_var}].data)"
                            if et == "string" else f"{src_ref}.data[{i_var}]")
                return (
                    f"{OPEN}"
                    + f"{src_cap}"
                    + f"int32_t {s} = ({n} < {src_ref}.len ? {n} : {src_ref}.len);{NL}"
                    + f"MrylVec_{et} {r} = mryl_vec_{et}_new();{NL}"
                    + f"for (int32_t {i_var} = {s}; {i_var} < {src_ref}.len; {i_var}++) {{"
                    + f" mryl_vec_{et}_push(&{r}, {push_val}); }}{NL}"
                    + f"{src_free}"
                    + f"{r};"
                    + f"{CLOSE}"
                )
            else:
                # ユーザー変数に対しても view（ポインタ算術）ではなくコピー方式を使う。
                # view の .data はオリジナルの途中ポインタのため、後続の first() 等が
                # src_is_temp=True と判断して free すると UB になるため。
                push_val = (f"make_mryl_string({obj_c}.data[{i_var}].data)"
                            if et == "string" else f"{obj_c}.data[{i_var}]")
                return (
                    f"{OPEN}"
                    + f"int32_t {s} = ({n} < {obj_c}.len ? {n} : {obj_c}.len);{NL}"
                    + f"MrylVec_{et} {r} = mryl_vec_{et}_new();{NL}"
                    + f"for (int32_t {i_var} = {s}; {i_var} < {obj_c}.len; {i_var}++) {{"
                    + f" mryl_vec_{et}_push(&{r}, {push_val}); }}{NL}"
                    + f"{r};"
                    + f"{CLOSE}"
                )

        # ── to_array ─────────────────────────────────────────────
        # 所有権を呼び出し側に移す。free しない。
        if method == 'to_array':
            return obj_c

        # ── count ────────────────────────────────────────────────
        if method == 'count':
            if src_is_temp:
                cnt = f"__cnt_{idx}"
                return (
                    f"{OPEN}"
                    f"MrylVec_{et} {src_var} = {obj_c};{NL}"
                    f"int32_t {cnt} = {src_var}.len;{NL}"
                    f"free({src_var}.data);{NL}"
                    f"{cnt};"
                    f"{CLOSE}"
                )
            return f"{obj_c}.len"

        # ── any ──────────────────────────────────────────────────
        if method == 'any':
            lam_setup, lam_fn, lam_env = _lam_full(0)
            found = f"__found_{idx}"
            return (
                f"{OPEN}"
                f"{src_cap}"
                f"{lam_setup}"
                f"int {found} = 0;{NL}"
                f"for (int32_t {i_var} = 0; {i_var} < {src_ref}.len; {i_var}++) {{"
                f" if ({lam_fn}({src_ref}.data[{i_var}], {lam_env})) {{ {found} = 1; break; }} }}{NL}"
                f"{src_free}"
                f"{found};"
                f"{CLOSE}"
            )

        # ── all ──────────────────────────────────────────────────
        if method == 'all':
            lam_setup, lam_fn, lam_env = _lam_full(0)
            ok  = f"__ok_{idx}"
            return (
                f"{OPEN}"
                f"{src_cap}"
                f"{lam_setup}"
                f"int {ok} = 1;{NL}"
                f"for (int32_t {i_var} = 0; {i_var} < {src_ref}.len; {i_var}++) {{"
                f" if (!{lam_fn}({src_ref}.data[{i_var}], {lam_env})) {{ {ok} = 0; break; }} }}{NL}"
                f"{src_free}"
                f"{ok};"
                f"{CLOSE}"
            )

        # ── for_each ─────────────────────────────────────────────
        # GCC statement expression ({...}) を使わず通常ブロック {..} として返す。
        # for_each は void 専用（TypeChecker が式コンテキストでの使用を禁止）なので
        # 末尾の値式 (void)0; は不要。ExprStmt ハンドラ側で ; を付与しない。
        if method == 'for_each':
            lam_setup, lam_fn, lam_env = _lam_full(0)
            # src_free は末尾に NL を持つため、ある場合はその前に for ループを置く
            src_free_block = f"{NL}free({src_var}.data);" if src_is_temp else ""
            return (
                f"{{{NL}"
                f"{src_cap}"
                f"{lam_setup}"
                f"for (int32_t {i_var} = 0; {i_var} < {src_ref}.len; {i_var}++) {{"
                f" {lam_fn}({src_ref}.data[{i_var}], {lam_env}); }}"
                f"{src_free_block}"
                f"\n{base_indent}}}"
            )

        # ── first ────────────────────────────────────────────────
        if method == 'first':
            struct = f"MrylResult_{ct}_MrylString"
            self.result_type_registry.add((ct, "MrylString", struct))
            r = f"__first_{idx}"
            # string 要素の場合は src_free で char* が解放される前に deep copy する。
            # shallow copy のまま src_free すると ok_val.data がダングリングになる。
            ok_line = (
                f"else {{ {r}.is_ok = 1; {r}.data.ok_val = make_mryl_string({src_ref}.data[0].data); }}{NL}"
                if et == "string" else
                f"else {{ {r}.is_ok = 1; {r}.data.ok_val = {src_ref}.data[0]; }}{NL}"
            )
            return (
                f"{OPEN}"
                + f"{src_cap}"
                + f"{struct} {r};{NL}"
                + f"if ({src_ref}.len == 0) {{"
                + f" {r}.is_ok = 0; {r}.data.err_val = make_mryl_string(\"empty sequence\"); }}{NL}"
                + ok_line
                + f"{src_free}"
                + f"{r};"
                + f"{CLOSE}"
            )

        # ── aggregate ────────────────────────────────────────────
        if method == 'aggregate':
            if len(expr.args) == 1:
                # 初期値なし: Result<T, string>
                lam_setup, lam_fn, lam_env = _lam_full(0)
                struct = f"MrylResult_{ct}_MrylString"
                self.result_type_registry.add((ct, "MrylString", struct))
                r   = f"__agg_{idx}"
                acc = f"__acc_{idx}"
                return (
                    f"{OPEN}"
                    f"{src_cap}"
                    f"{lam_setup}"
                    f"{struct} {r};{NL}"
                    f"if ({src_ref}.len == 0) {{"
                    f" {r}.is_ok = 0; {r}.data.err_val = make_mryl_string(\"empty sequence\"); }}{NL}"
                    f"else {{{NL}"
                    f"    {ct} {acc} = {src_ref}.data[0];{NL}"
                    f"    for (int32_t {i_var} = 1; {i_var} < {src_ref}.len; {i_var}++) {{"
                    f" {acc} = {lam_fn}({acc}, {src_ref}.data[{i_var}], {lam_env}); }}{NL}"
                    f"    {r}.is_ok = 1; {r}.data.ok_val = {acc};{NL}}}{NL}"
                    f"{src_free}"
                    f"{r};"
                    f"{CLOSE}"
                )
            else:
                # 初期値あり: aggregate(init, fn) -> U
                init_c  = self._generate_expr(expr.args[0])
                lam_setup, lam_fn, lam_env = _lam_full(1)
                init_t  = self._infer_expr_type(expr.args[0])
                init_ct = self._type_to_c_base(init_t) if init_t not in ("i32", "any") else ct
                acc     = f"__acc_{idx}"
                return (
                    f"{OPEN}"
                    f"{src_cap}"
                    f"{lam_setup}"
                    f"{init_ct} {acc} = {init_c};{NL}"
                    f"for (int32_t {i_var} = 0; {i_var} < {src_ref}.len; {i_var}++) {{"
                    f" {acc} = {lam_fn}({acc}, {src_ref}.data[{i_var}], {lam_env}); }}{NL}"
                    f"{src_free}"
                    f"{acc};"
                    f"{CLOSE}"
                )

        # ── select_many ──────────────────────────────────────────────
        # Lambda: fn(T) -> U[]  →  output: Iter<U>
        # 外側ループ: 各 T 要素にラムダを適用 → MrylVec_U __inner を取得
        # 内側ループ: __inner の各要素を __result に push
        # __inner.data の free: ラムダが新規確保した場合のみ行う。
        #   VarRef を返す場合はポインタ共有のため free 不可（UB 防止）。
        if method == 'select_many':
            lam_setup, lam_fn, lam_env = _lam_full(0)

            # out_et: 展開後の要素型 (U)。Lambda の inferred_return_type.name から取得。
            lam_arg = expr.args[0] if expr.args else None
            if isinstance(lam_arg, Lambda):
                inferred = getattr(lam_arg, 'inferred_return_type', None)
                if inferred is not None:
                    out_et = inferred.name
                else:
                    # フォールバック: et が vec_U なら U を取り出す
                    out_et = et[4:] if et.startswith("vec_") else et
            else:
                out_et = et[4:] if et.startswith("vec_") else et

            inner  = f"__inner_{idx}"
            result = f"__result_{idx}"
            j_var  = f"__j_{idx}"
            # NL2: 外側 for ループ本体のインデント（statement expression 内より1段深い）
            NL2 = NL + "    "

            # ラムダの body 種別から __inner.data を free すべきか判定する。
            # - VarRef: 既存配列の参照を返す → ポインタ共有 → free 不可（UB）
            # - ArrayLiteral / FunctionCall / MethodCall: 新規確保 → free 可
            # - 関数参照渡し（Lambda 以外）やその他: 不明 → 安全側で free しない
            if isinstance(lam_arg, Lambda) and lam_arg.body is not None:
                body_cls = lam_arg.body.__class__.__name__
                inner_needs_free = body_cls in ('ArrayLiteral', 'FunctionCall', 'MethodCall')
            else:
                inner_needs_free = False
            inner_free = f"free({inner}.data);{NL2}" if inner_needs_free else ""

            return (
                f"{OPEN}"
                f"{src_cap}"
                f"{lam_setup}"
                f"MrylVec_{out_et} {result} = mryl_vec_{out_et}_new();{NL}"
                f"for (int32_t {i_var} = 0; {i_var} < {src_ref}.len; {i_var}++) {{{NL2}"
                f"MrylVec_{out_et} {inner} = {lam_fn}({src_ref}.data[{i_var}], {lam_env});{NL2}"
                f"for (int32_t {j_var} = 0; {j_var} < {inner}.len; {j_var}++) {{"
                f" mryl_vec_{out_et}_push(&{result}, {inner}.data[{j_var}]); }}{NL2}"
                f"{inner_free}"
                f"{NL}}}{NL}"
                f"{src_free}"
                f"{result};"
                f"{CLOSE}"
            )

        raise RuntimeError(f"Unknown iter method in codegen: {method}")

