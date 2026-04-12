from __future__ import annotations
from CodeGenerator._util import _safe_c_name
from CodeGenerator._proto import _CodeGeneratorBase


def _iter_chain_owns_alloc(expr) -> bool:
    """Iter チェーンの末端 to_array() 結果が独立した malloc を持つかを判定する。

    - filter / select / select_many: 常に新 alloc → owned
    - skip: src_is_temp / user var いずれも mryl_vec_new() で新規確保 → owned
    - take: source の .data を共有（struct コピー） → source の ownership を継承
    - その他 / VarRef: ユーザー変数の borrow の可能性 → unsafe
    """
    cls = expr.__class__.__name__
    if cls != "MethodCall":
        # VarRef などのユーザー変数直接 → borrow の可能性あり
        return False
    method = expr.method
    if method in ('filter', 'select', 'select_many'):
        return True
    if method == 'take':
        # take は struct コピーで source の .data を共有するため source の ownership を継承
        return _iter_chain_owns_alloc(expr.obj)
    if method == 'skip':
        # skip は src_is_temp / user var どちらの場合も mryl_vec_new() で独立確保 → owned
        return True
    return False

class CodeGeneratorStmtMixin(_CodeGeneratorBase):
    """文(Statement)レベルの C コード生成を担当する Mixin
    _generate_statement / _generate_conditional_block / _generate_let /
    _generate_return / _generate_if / _generate_if_inline /
    _generate_while / _generate_for / _generate_array_element /
    _box_nesting_depth / _emit_box_free / _emit_box_vec_free
    """

    # ------------------------------------------------------------------
    # Box メモリ管理ヘルパー
    # ------------------------------------------------------------------

    def _box_nesting_depth(self, type_node) -> int:
        """Box<Box<...<T>...>> のネスト深度を返す。
        Box<i32> = 1, Box<Box<i32>> = 2, Box<Box<Box<i32>>> = 3
        type_args 要素が文字列の場合も安全に処理する。
        """
        depth = 0
        t = type_node
        while (t is not None and not isinstance(t, str)
               and hasattr(t, 'name') and t.name == "Box"
               and getattr(t, 'type_args', None)):
            depth += 1
            t = t.type_args[0]
        return max(depth, 1)

    def _emit_box_free(self, c_var_name: str, type_node) -> None:
        """Box 変数の free 文を生成する。
        inner_moved（内部ポインタが別変数に移動済み）の場合は最外層のみ free。
        それ以外は深い層から順に free して最後に外層を free する。
        例: Box<Box<Box<i32>>> box → free(**box); free(*box); free(box);
        """
        if c_var_name in self.box_inner_moved:
            # 内部ポインタは移動先変数で解放済み → 外層のポインタ配置のみ解放
            self._emit(f"free({c_var_name});")
            return
        depth = self._box_nesting_depth(type_node)
        # 最深部から順に free: depth=3 → free(**p); free(*p); free(p)
        for d in range(depth - 1, 0, -1):
            self._emit(f"free({'*' * d}{c_var_name});")
        self._emit(f"free({c_var_name});")

    def _emit_box_vec_free(self, c_var_name: str) -> None:
        """Vec<Box<T>> 変数の free 文を生成する。
        各要素（Box ポインタ）を先に free してから .data を free する。
        ループ変数は loop_counter で一意化する（変数名依存の衝突を防ぐ）。
        """
        loop_var = f"__bv_i_{self.loop_counter}"
        self.loop_counter += 1
        self._emit(f"for (int32_t {loop_var} = 0; {loop_var} < {c_var_name}.len; {loop_var}++) {{")
        self.indent_level += 1
        self._emit(f"free({c_var_name}.data[{loop_var}]);")
        self.indent_level -= 1
        self._emit("}")
        self._emit(f"free({c_var_name}.data);")

    def _emit_toarray_vec_free(self, c_var_name: str, et: str) -> None:
        """to_array() / ArrayLiteral 結果 Vec の free 文を生成する。
        string 要素の場合は mryl_vec_string_free で各要素の char* も解放する。
        それ以外はプリミティブ値のため free(vn.data) のみ（#97）。
        """
        if et == "string":
            self._emit(f"mryl_vec_string_free({c_var_name});")
        else:
            self._emit(f"free({c_var_name}.data);")

    def _emit_loop_iteration_cleanup(
        self, saved_str_vars: list, saved_box_count: int, saved_bv_count: int,
        saved_tav_count: int = 0, saved_sbv_count: int = 0, saved_obv_count: int = 0
    ) -> None:
        """ループイテレーション内で宣言された変数を解放し、保存状態に復元する。
        while / for の各ブランチで共通して使用する（DRY）。
        saved_sbv_count: struct Box 変数リストの保存長（#68）
        saved_obv_count: Option<Box<T>> 変数リストの保存長（#67）
        """
        for vn in self.local_string_vars:
            if vn not in saved_str_vars:
                self._emit(f"free_mryl_string({vn});")
        self.local_string_vars = saved_str_vars
        for (vn, tn) in reversed(self.local_box_vars[saved_box_count:]):
            self._emit_box_free(vn, tn)
        self.local_box_vars = self.local_box_vars[:saved_box_count]
        for (vn, _tn) in reversed(self.local_box_vec_vars[saved_bv_count:]):
            self._emit_box_vec_free(vn)
        self.local_box_vec_vars = self.local_box_vec_vars[:saved_bv_count]
        # to_array() 結果 Vec 変数: ループ内で宣言されたものを解放（#71, #97）
        for (vn, et) in reversed(self.local_toarray_vec_vars[saved_tav_count:]):
            self._emit_toarray_vec_free(vn, et)
        self.local_toarray_vec_vars = self.local_toarray_vec_vars[:saved_tav_count]
        # Box フィールド持ち struct 変数: デストラクタを呼ぶ（#68）
        for (vn, sname) in reversed(self.local_struct_box_vars[saved_sbv_count:]):
            self._emit(f"mryl_free_{sname}({vn});")
        self.local_struct_box_vars = self.local_struct_box_vars[:saved_sbv_count]
        # Option<Box<T>> 変数: has_value なら Box を free（#67）
        for vn in reversed(self.local_option_box_vars[saved_obv_count:]):
            self._emit(f"if ({vn}.has_value) {{ free({vn}.value); }}")
        self.local_option_box_vars = self.local_option_box_vars[:saved_obv_count]

    def _generate_statement(self, stmt):
        """文ノードを C コードとして出力する (ディスパッチャ) """
        stmt_class = stmt.__class__.__name__

        if stmt_class == "LetDecl":
            self._generate_let(stmt)
        elif stmt_class == "FixDecl":
            self._generate_fix(stmt)
        elif stmt_class == "ReturnStmt":
            self._generate_return(stmt)
        elif stmt_class == "BreakStmt":
            self._emit("break;")
        elif stmt_class == "ContinueStmt":
            self._emit("continue;")
        elif stmt_class == "IfStmt":
            self._generate_if(stmt)
        elif stmt_class == "WhileStmt":
            self._generate_while(stmt)
        elif stmt_class == "ForStmt":
            self._generate_for(stmt)
        elif stmt_class == "ExprStmt":
            expr_code = self._generate_expr(stmt.expr)
            # for_each は void 専用のブロック文 {..} を返すため ; 不要
            # （他の iter メソッドは値を返す statement expression ({..}) なので ; が必要）
            if hasattr(stmt.expr, 'method') and stmt.expr.method == 'for_each':
                self._emit(expr_code)
            else:
                self._emit(f"{self._strip_outer_parens(expr_code)};")
        elif stmt_class == "Assignment":
            target = self._generate_expr(stmt.target)
            value  = self._generate_expr(stmt.expr)
            self._emit(f"{target} = {self._strip_outer_parens(value)};")
        elif stmt_class == "ConditionalBlock":
            self._generate_conditional_block(stmt)
        else:
            self._emit(f"// Unknown statement: {stmt_class}")

    def _generate_conditional_block(self, stmt):
        """条件コンパイルブロック (#if 相当) を評価して出力する """
        condition_value = False

        if isinstance(stmt.condition_expr, str):
            if stmt.condition_expr in self.const_table:
                condition_value = bool(self.const_table[stmt.condition_expr])
        elif isinstance(stmt.condition_expr, tuple) and stmt.condition_expr[0] == 'not':
            const_name = stmt.condition_expr[1]
            condition_value = (const_name not in self.const_table) or \
                              not bool(self.const_table[const_name])
        else:
            try:
                result = self._eval_const_expr(stmt.condition_expr)
                condition_value = bool(result)
            except Exception:
                condition_value = False

        if condition_value:
            for s in stmt.then_block.statements:
                self._generate_statement(s)
        elif stmt.else_block:
            for s in stmt.else_block.statements:
                self._generate_statement(s)

    def _generate_let(self, stmt):
        """let 宣言を C 変数宣言として出力する """
        type_node       = stmt.type_node
        init_expr_class = stmt.init_expr.__class__.__name__ if stmt.init_expr else None

        var_type = self._type_to_c(type_node)

        # ラムダ式: fat pointer struct 変数として宣言
        if init_expr_class == "Lambda":
            lam_name, ret_type, params_str, _ = self._generate_lambda_inline(stmt.init_expr, stmt.name)
            c_var_name = _safe_c_name(stmt.name)
            if c_var_name != stmt.name:
                self.ident_renames[stmt.name] = c_var_name

            if ret_type == "MrylTask*":
                # async lambda: 旧挙動を維持
                self._emit(f"{ret_type} (*{c_var_name})({params_str}) = {lam_name};")
                self.env[-1][stmt.name] = "async_fn"
                self.async_lambda_factories[stmt.name] = lam_name
                return

            info     = self.lambda_captures.get(lam_name, {})
            captures = info.get('captures', {})
            ret_c    = info.get('ret_c', ret_type)
            arg_cs   = info.get('arg_cs', [])

            # MrylFn_* struct 型名を決定
            if type_node and type_node.name == "fn" and getattr(type_node, 'type_args', None):
                fn_c_type = self._type_to_c(type_node)
            else:
                arg_part  = "_".join(c.replace("*", "Ptr").replace(" ", "_") for c in arg_cs) if arg_cs else "void"
                ret_part  = ret_c.replace("*", "Ptr").replace(" ", "_")
                fn_c_type = f"MrylFn_{arg_part}_ret_{ret_part}"
                self.fn_type_registry.add((tuple(arg_cs), ret_c, fn_c_type))

            if captures:
                env_struct = f"{lam_name}_env_t"
                # ⑨ lam_name ベースで一意な env ポインタ名（変数名衝突を回避）
                env_ptr    = f"__env_{lam_name}"
                self._emit(f"{env_struct}* {env_ptr} = ({env_struct}*)malloc(sizeof({env_struct}));")
                for cap_name in captures:
                    c_cap = self.ident_renames.get(cap_name, _safe_c_name(cap_name))
                    self._emit(f"{env_ptr}->{cap_name} = {c_cap};")
                self._emit(f"{fn_c_type} {c_var_name} = {{{lam_name}, {env_ptr}}};")
                # ⑥ 返値にならない closure env を追跡（関数末尾で free）
                self.local_closure_envs.append(env_ptr)
                # ⑥ var_name → env_ptr の逆引き（return 時に free スキップするため）
                self.closure_var_env_ptrs[stmt.name] = env_ptr
            else:
                self._emit(f"{fn_c_type} {c_var_name} = {{{lam_name}, NULL}};")

            self.env[-1][stmt.name] = "fn"
            # ⑦ キャプチャ型解決用に MrylFn_* 型名を登録
            self.fn_var_c_types[stmt.name] = fn_c_type
            return

        # FunctionCall が fn(T)->U を返す場合（型注釈なし）: MrylFn_* struct として宣言（issue ①）
        if init_expr_class == "FunctionCall" and type_node is None:
            fn_decl = self.program_functions.get(stmt.init_expr.name)
            if fn_decl and fn_decl.return_type and fn_decl.return_type.name == "fn" \
                    and getattr(fn_decl.return_type, 'type_args', None):
                fn_c_type  = self._type_to_c(fn_decl.return_type)
                c_var_name = _safe_c_name(stmt.name)
                if c_var_name != stmt.name:
                    self.ident_renames[stmt.name] = c_var_name
                rhs = self._generate_expr(stmt.init_expr)
                self._emit(f"{fn_c_type} {c_var_name} = {rhs};")
                self.env[-1][stmt.name] = "fn"
                self.fn_var_c_types[stmt.name] = fn_c_type
                return

        # static fn 参照（has_parens=False の EnumVariantExpr）を fn 型変数として宣言
        # fn(T)->U 型注釈がある場合は thunk + fat pointer (MrylFn_*) として生成する（#76）
        # ※ raw 関数ポインタ形式だと呼び出し側の `var.fn(...)` 規約と不整合になる
        if init_expr_class == "EnumVariantExpr" and not stmt.init_expr.has_parens:
            if type_node and type_node.name == "fn" and getattr(type_node, 'type_args', None):
                c_func_name = f"{stmt.init_expr.enum_name}_{stmt.init_expr.variant_name}"
                method = next(
                    (m for s in self.structs for m in s.methods
                     if getattr(m, 'is_static', False) and f"{s.name}_{m.name}" == c_func_name),
                    None
                )
                c_var_name = _safe_c_name(stmt.name)
                if c_var_name != stmt.name:
                    self.ident_renames[stmt.name] = c_var_name
                fn_c_type  = self._type_to_c(type_node)
                if method is not None:
                    # thunk を生成して fat pointer に包む（method.params は static fn なので self なし）
                    thunk_name   = f"__thunk_{self.thunk_counter}"
                    self.thunk_counter += 1
                    t_params_c   = [
                        f"{self._type_to_c(p.type_node) if p.type_node else 'int32_t'} {p.name}"
                        for p in method.params
                    ]
                    t_params_str = ", ".join(t_params_c)
                    t_ret        = self._type_to_c(method.return_type) if method.return_type else "void"
                    call_args    = ", ".join(p.name for p in method.params)
                    ret_kw       = "return " if t_ret != "void" else ""
                    self.pending_lambdas.append(
                        (thunk_name, t_ret, t_params_str, [f"    {ret_kw}{c_func_name}({call_args});"], {}, set())
                    )
                    arg_cs_t = [self._type_to_c(p.type_node) if p.type_node else "int32_t" for p in method.params]
                    self.lambda_captures[thunk_name] = {'captures': {}, 'ret_c': t_ret, 'arg_cs': arg_cs_t}
                    self.fn_type_registry.add((tuple(arg_cs_t), t_ret, fn_c_type))
                    self._emit(f"{fn_c_type} {c_var_name} = {{{thunk_name}, NULL}};")
                else:
                    # static method が見つからない場合はフォールバック（既存挙動）
                    c_func = self._generate_expr(stmt.init_expr)
                    self._emit(f"{fn_c_type} {c_var_name};")
                    self._emit(f"{c_var_name}.fn = (void*){c_func};")
                    self._emit(f"{c_var_name}.env = NULL;")
                self.env[-1][stmt.name] = "fn"
                self.fn_var_c_types[stmt.name] = fn_c_type
                return

        # FunctionCall 引数の StringLiteral を一時変数化
        temp_string_mapping = {}
        if init_expr_class == "FunctionCall":
            for i, arg in enumerate(stmt.init_expr.args):
                if arg.__class__.__name__ == "StringLiteral":
                    temp_var_name = f"__temp_str_{self.temp_string_counter}"
                    self.temp_string_counter += 1
                    escaped = self._c_escape(arg.value)
                    self._emit(f'MrylString {temp_var_name} = make_mryl_string("{escaped}");')
                    self.local_string_vars.append(temp_var_name)
                    temp_string_mapping[id(arg)] = temp_var_name

        init_expr = self._generate_expr_with_temps(stmt.init_expr, temp_string_mapping)

        # Option<T> の init_expr 生成時に current_return_type を一時設定する
        if type_node and type_node.name == "Option":
            _saved_rt = self.current_return_type
            self.current_return_type = var_type
            init_expr = self._generate_expr_with_temps(stmt.init_expr, temp_string_mapping)
            self.current_return_type = _saved_rt

        # Result<T, E> の init_expr 生成時に current_return_type を一時設定する
        if type_node and type_node.name == "Result":
            _saved_rt = self.current_return_type
            self.current_return_type = var_type
            init_expr = self._generate_expr_with_temps(stmt.init_expr, temp_string_mapping)
            self.current_return_type = _saved_rt

        # 動的配列 (array_size == -1): MrylVec_<T>
        if type_node and type_node.array_size == -1:
            et = type_node.name
            _c_map = {
                "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
                "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t",
                "f32": "float", "f64": "double", "bool": "int",
                "string": "MrylString",
            }
            # 多次元配列ラッパー Array<T[]> の場合: 要素 C 型は内側の MrylVec_T
            # 例: i32[][] → TypeNode("Array", -1, [TypeNode("i32",-1)]) → et="MrylVec_i32", ct="MrylVec_i32"
            if et == "Array" and getattr(type_node, 'type_args', None):
                inner_c = self._type_to_c(type_node.type_args[0])
                et      = inner_c.replace("*", "Ptr").replace(" ", "_")
                ct      = inner_c
            # Box<T>[] の場合: 要素型 "Box_T"、C 型は T*
            elif et == "Box" and getattr(type_node, 'type_args', None):
                inner_tn   = type_node.type_args[0]
                inner_mryl = inner_tn.name if inner_tn else "i32"
                et         = f"Box_{inner_mryl}"
                ct         = _c_map.get(inner_mryl, "int32_t") + "*"
                # Vec<Box<T>> 変数を追跡（スコープ終了時に要素 + .data を free）
                self.local_box_vec_vars.append((stmt.name, inner_tn))
            else:
                ct = _c_map.get(et, "int32_t")
            # to_array() 呼び出しかどうか（ownership 有無に関わらず）
            is_to_array_call = (stmt.init_expr is not None
                    and init_expr_class != "ArrayLiteral"
                    and stmt.init_expr.__class__.__name__ == "MethodCall"
                    and stmt.init_expr.method == "to_array")
            # ownership あり: filter/select/skip(chain) 等 → 解放が必要（#71）
            # ownership なし: take(user_var) 等 → ソースと .data を共有するため free 不可（#96）
            if is_to_array_call and _iter_chain_owns_alloc(stmt.init_expr.obj):
                self.local_toarray_vec_vars.append((_safe_c_name(stmt.name), et))
            if init_expr_class == "ArrayLiteral" and stmt.init_expr.elements:
                elements  = [self._generate_expr(elem) for elem in stmt.init_expr.elements]
                elems_str = ", ".join(elements)
                n         = len(stmt.init_expr.elements)
                self._emit(f"MrylVec_{et} {stmt.name} = mryl_vec_{et}_from(({ct}[]){{{elems_str}}}, {n});")
                # mryl_vec_from() は malloc するため、Box<T>[] 以外はスコープ終了時に解放する（#78, #97）
                # Box<T>[] は local_box_vec_vars で管理済みなので除外する
                if not et.startswith("Box_"):
                    self.local_toarray_vec_vars.append((_safe_c_name(stmt.name), et))
            elif stmt.init_expr is not None and init_expr_class != "ArrayLiteral":
                # split() など Vec を返す式で初期化（例: mryl_str_split(...)）
                # これらも新規 malloc が発生するため解放が必要（#78, #97）
                rhs = self._generate_expr(stmt.init_expr)
                self._emit(f"MrylVec_{et} {stmt.name} = {rhs};")
                # to_array() 呼び出しはすべて上のブロックで処理済みか free 不可なため除外（#96）
                if not et.startswith("Box_") and not is_to_array_call:
                    self.local_toarray_vec_vars.append((_safe_c_name(stmt.name), et))
            else:
                self._emit(f"MrylVec_{et} {stmt.name} = mryl_vec_{et}_new();")
            self.vec_var_types[stmt.name] = et
            self.env[-1][stmt.name] = f"vec_{et}"
            return

        # 固定長配列
        if type_node and type_node.array_size is not None and type_node.array_size > 0:
            base_type = self._type_to_c_base(type_node.name)
            if init_expr_class == "ArrayLiteral":
                elements    = [self._generate_expr(elem) for elem in stmt.init_expr.elements]
                init_values = "{" + ", ".join(elements) + "}"
                self._emit(f"{base_type} {stmt.name}[{type_node.array_size}] = {init_values};")
            else:
                self._emit(f"{base_type} {stmt.name}[{type_node.array_size}] = {{0}};")
            self.array_sizes[stmt.name] = type_node.array_size
            self.env[-1][stmt.name] = type_node.name
        elif init_expr_class == "ArrayLiteral":
            array_lit   = stmt.init_expr
            array_size  = len(array_lit.elements)
            elements    = [self._generate_expr(elem) for elem in array_lit.elements]
            init_values = "{" + ", ".join(elements) + "}"
            # 要素型を推論する (文字列配列は MrylString、数値配列は int32_t など)
            _c_elem_map = {
                "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
                "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t",
                "f32": "float", "f64": "double", "string": "MrylString", "bool": "int",
            }
            if array_lit.elements:
                elem_mryl = self._infer_expr_type(array_lit.elements[0])
            else:
                elem_mryl = "i32"
            elem_c = _c_elem_map.get(elem_mryl, "int32_t")
            self._emit(f"{elem_c} {stmt.name}[{array_size}] = {init_values};")
            self.array_sizes[stmt.name] = array_size
            self.env[-1][stmt.name] = elem_mryl
        else:
            # ジェネリック構造体の具体化 (例: Box<i32> → var_type = "Box_i32")
            if init_expr_class == "StructInit" and getattr(stmt.init_expr, 'type_args', []):
                suffix = "_".join(t if isinstance(t, str) else t.name for t in stmt.init_expr.type_args)
                var_type = f"{stmt.init_expr.struct_name}_{suffix}"
            elif var_type in ("any",) and stmt.init_expr is not None:
                inferred_mryl = self._infer_expr_type(stmt.init_expr)
                if inferred_mryl == "string":
                    var_type = "MrylString"
                else:
                    c = self._type_to_c_base(inferred_mryl)
                    var_type = c if c not in ("any", "") else "int32_t"
            self._emit(f"{var_type} {stmt.name} = {self._strip_outer_parens(init_expr)};")
            # ユーザー定義の struct Box がある場合は built-in Box<T>（heap 確保）ではないため除外。
            # generate() でキャッシュ済みの has_user_box を使用（O(N) → O(1)）。
            if type_node and type_node.name == "Box" and not self.has_user_box:
                # built-in Box<T> 変数を追跡（スコープ終了・return 前に free を生成するため）
                c_var = self.ident_renames.get(stmt.name, stmt.name)
                # let X: Box<T> = *Y の場合: Y の内部ポインタが X に移動したことをマーク
                # → Y の free は最外層のみになり、内部 free は X 側で行われる
                if (stmt.init_expr is not None
                        and stmt.init_expr.__class__.__name__ == "UnaryOp"
                        and getattr(stmt.init_expr, 'op', None) in ("*", "deref")
                        and stmt.init_expr.operand.__class__.__name__ == "VarRef"):
                    src_c = self.ident_renames.get(stmt.init_expr.operand.name,
                                                   stmt.init_expr.operand.name)
                    self.box_inner_moved.add(src_c)
                self.local_box_vars.append((c_var, type_node))
            # Option<Box<T>> 変数を追跡: スコープ終了時に has_value なら Box を free（#67）
            if (type_node and type_node.name == "Option"
                    and getattr(type_node, 'type_args', None) and not self.has_user_box):
                inner = type_node.type_args[0]
                if (inner is not None and not isinstance(inner, str)
                        and hasattr(inner, 'name') and inner.name == "Box"):
                    c_var = self.ident_renames.get(stmt.name, stmt.name)
                    self.local_option_box_vars.append(c_var)
            # Box<T> フィールドを持つ struct 変数を追跡: スコープ終了時にデストラクタを呼ぶ（#68）
            if type_node and not self.has_user_box:
                struct_decl = next((s for s in self.structs if s.name == type_node.name), None)
                if struct_decl and self._struct_has_box_fields(struct_decl):
                    c_var = self.ident_renames.get(stmt.name, stmt.name)
                    # StructInit フィールド値が VarRef の場合: 元の struct 変数は所有権移動とみなす。
                    # C の値コピーで Box ポインタが共有されるため、元変数のデストラクタ呼び出しを
                    # 除外して double free を防ぐ（#68 既知制約への対処）。
                    if init_expr_class == "StructInit":
                        for (_fname, fval) in getattr(stmt.init_expr, 'fields', []):
                            if fval.__class__.__name__ == "VarRef":
                                moved_c = self.ident_renames.get(fval.name, fval.name)
                                self.local_struct_box_vars = [
                                    (vn, sn) for (vn, sn) in self.local_struct_box_vars
                                    if vn != moved_c
                                ]
                    self.local_struct_box_vars.append((c_var, type_node.name))
            if type_node:
                # Result<T, E> は "Result_T" 形式で env 登録する（_pattern_binding_types が ok_type を参照するため）
                if type_node.name == "Result" and getattr(type_node, 'type_args', None):
                    ok_name = type_node.type_args[0].name if type_node.type_args else "i32"
                    mryl_name = f"Result_{ok_name}"
                # Option<T> は "MrylOption_<inner>" 形式で env 登録する
                elif type_node.name == "Option" and getattr(type_node, 'type_args', None):
                    inner_name = type_node.type_args[0].name if type_node.type_args else "int32_t"
                    mryl_name = f"MrylOption_{inner_name}"
                # fn 型: TypeChecker が type_node を付与した場合も fat pointer 呼び出しを正しく解決できるよう
                # env を "fn" で登録し fn_var_c_types に C 型名を記録する
                elif type_node.name == "fn":
                    self.env[-1][stmt.name] = "fn"
                    self.fn_var_c_types[stmt.name] = var_type
                    return
                else:
                    # ジェネリック具体化名 (例: Box_string) で env 登録 (#31)
                    mryl_name = type_node.name
                    if getattr(type_node, 'type_args', None):
                        suffix = "_".join(t if isinstance(t, str) else t.name for t in type_node.type_args)
                        mryl_name = f"{type_node.name}_{suffix}"
                self.env[-1][stmt.name] = mryl_name
                if type_node.name == "string":
                    self.local_string_vars.append(stmt.name)
            else:
                inferred_type = self._infer_expr_type(stmt.init_expr)
                self.env[-1][stmt.name] = inferred_type
                if inferred_type == "string":
                    self.local_string_vars.append(stmt.name)

    def _generate_fix(self, stmt):
        """fix 宣言を C の const 変数宣言として出力する。
        let と同じロジックだが、出力に const 修飾子を付ける。
        配列・動的配列・文字列も対応。
        """
        type_node       = stmt.type_node
        init_expr_class = stmt.init_expr.__class__.__name__ if stmt.init_expr else None

        var_type = self._type_to_c(type_node)
        init_expr = self._generate_expr_with_temps(stmt.init_expr, {})

        # Option<T> の init_expr 生成時に current_return_type を一時設定する
        if type_node and type_node.name == "Option":
            _saved_rt = self.current_return_type
            self.current_return_type = var_type
            init_expr = self._generate_expr_with_temps(stmt.init_expr, {})
            self.current_return_type = _saved_rt

        # 固定長配列
        if type_node and type_node.array_size is not None and type_node.array_size > 0:
            base_type = self._type_to_c_base(type_node.name)
            if init_expr_class == "ArrayLiteral":
                elements    = [self._generate_expr(elem) for elem in stmt.init_expr.elements]
                init_values = "{" + ", ".join(elements) + "}"
                self._emit(f"const {base_type} {stmt.name}[{type_node.array_size}] = {init_values};")
            else:
                self._emit(f"const {base_type} {stmt.name}[{type_node.array_size}] = {{0}};")
            self.array_sizes[stmt.name] = type_node.array_size
            self.env[-1][stmt.name] = type_node.name
            return

        # 通常の scalar / struct 型
        self._emit(f"const {var_type} {stmt.name} = {self._strip_outer_parens(init_expr)};")
        if type_node:
            # Result<T, E> は "Result_T" 形式で env 登録する
            if type_node.name == "Result" and getattr(type_node, 'type_args', None):
                ok_name = type_node.type_args[0].name if type_node.type_args else "i32"
                mryl_name = f"Result_{ok_name}"
            # Option<T> は "MrylOption_<inner>" 形式で env 登録する
            elif type_node.name == "Option" and getattr(type_node, 'type_args', None):
                inner_name = type_node.type_args[0].name if type_node.type_args else "int32_t"
                mryl_name = f"MrylOption_{inner_name}"
            else:
                mryl_name = type_node.name
                if getattr(type_node, 'type_args', None):
                    suffix = "_".join(t if isinstance(t, str) else t.name for t in type_node.type_args)
                    mryl_name = f"{type_node.name}_{suffix}"
            self.env[-1][stmt.name] = mryl_name
            # string は fix では所有権管理しない (const 文字列リテラルが多い想定)
        else:
            inferred_type = self._infer_expr_type(stmt.init_expr)
            self.env[-1][stmt.name] = inferred_type

    def _generate_return(self, stmt):
        """return 文を出力する。
        return を emit する直前に、現在のスコープで追跡している文字列変数を
        すべて解放する（return の後ろに free が並ぶメモリリークを防ぐ）。
        Ok/Err は Result compound literal に変換する。
        string VarRef を返す場合は make_mryl_string でディープコピーして返す
        （パラメータ alias による double free を防止）。
        """
        # string VarRef を返す場合: ディープコピーで返し local_string_vars から除外
        return_var_to_deep_copy = None
        if stmt.expr and stmt.expr.__class__.__name__ == "VarRef":
            inferred = self._infer_expr_type(stmt.expr)
            if inferred == "string":
                return_var_to_deep_copy = stmt.expr.name

        # --- cleanup: return より前に文字列変数・closure env・Box 変数を解放 ---
        # 返値となる変数は use-after-free を防ぐためここでは解放しない
        for var_name in list(self.local_string_vars):
            if var_name != return_var_to_deep_copy:
                self._emit(f"free_mryl_string({var_name});")
        # 返値にならない closure env を解放（⑥: 返却される fn 変数の env は free 不可）
        return_var_name = stmt.expr.name if stmt.expr and stmt.expr.__class__.__name__ == "VarRef" else None
        skip_env_ptr = self.closure_var_env_ptrs.get(return_var_name) if return_var_name else None
        for env_ptr in list(self.local_closure_envs):
            if env_ptr != skip_env_ptr:
                self._emit(f"free({env_ptr});")
        # Box 変数を宣言の逆順で解放（返値 Box はスキップ）
        return_var_c = self.ident_renames.get(return_var_name, return_var_name) if return_var_name else None
        for (vn, tn) in reversed(self.local_box_vars):
            if vn != return_var_c:
                self._emit_box_free(vn, tn)
        # Vec<Box<T>> 変数: 要素を先に free してから .data を free
        for (vn, _inner_tn) in reversed(self.local_box_vec_vars):
            self._emit_box_vec_free(vn)
        # to_array() 結果 Vec 変数: 返値はスキップして解放（#71, #97）
        for (vn, et) in reversed(self.local_toarray_vec_vars):
            if vn != return_var_c:
                self._emit_toarray_vec_free(vn, et)
        # Box フィールド持ち struct 変数: 返値はスキップしてデストラクタを呼ぶ（#68）
        for (vn, sname) in reversed(self.local_struct_box_vars):
            if vn != return_var_c:
                self._emit(f"mryl_free_{sname}({vn});")
        # Option<Box<T>> 変数: 返値はスキップして has_value なら Box を free（#67）
        # return_var_c が Some(b) バインド変数の場合は、その元になった option 変数のフリーもスキップする（#79）
        # （b = mv.value のエイリアスのため、free(mv.value) は use-after-free になる）
        skipped_option_var = self.match_box_bindings.get(return_var_c) if return_var_c else None
        for vn in reversed(self.local_option_box_vars):
            if vn != return_var_c and vn != skipped_option_var:
                self._emit(f"if ({vn}.has_value) {{ free({vn}.value); }}")

        if stmt.expr:
            expr_class = stmt.expr.__class__.__name__

            # Lambda を直接 return: heap alloc env + fat pointer struct を返す
            if expr_class == "Lambda":
                lam_name = self._generate_lambda(stmt.expr)
                info     = self.lambda_captures.get(lam_name, {})
                captures = info.get('captures', {})
                ret_c    = info.get('ret_c', 'int32_t')
                arg_cs   = info.get('arg_cs', [])
                ret_type_str = self.current_return_type
                if not ret_type_str:
                    arg_part     = "_".join(c.replace("*", "Ptr").replace(" ", "_") for c in arg_cs) if arg_cs else "void"
                    ret_part     = ret_c.replace("*", "Ptr").replace(" ", "_")
                    ret_type_str = f"MrylFn_{arg_part}_ret_{ret_part}"
                    self.fn_type_registry.add((tuple(arg_cs), ret_c, ret_type_str))
                if captures:
                    env_struct = f"{lam_name}_env_t"
                    env_ptr    = f"__ret_env_{lam_name}"
                    self._emit(f"{env_struct}* {env_ptr} = ({env_struct}*)malloc(sizeof({env_struct}));")
                    for n in captures:
                        c_n = self.ident_renames.get(n, _safe_c_name(n))
                        self._emit(f"{env_ptr}->{n} = {c_n};")
                    self._emit(f"return ({ret_type_str}){{{lam_name}, {env_ptr}}};")
                else:
                    self._emit(f"return ({ret_type_str}){{{lam_name}, NULL}};")
                return

            if expr_class == "FunctionCall" and stmt.expr.name in ("Ok", "Err") \
                    and self.current_return_type:
                val_code    = self._generate_expr(stmt.expr.args[0]) if stmt.expr.args else "0"
                struct_name = self.current_return_type
                for (ok_c, err_c, sname) in self.result_type_registry:
                    if sname == struct_name:
                        if stmt.expr.name == "Ok":
                            self._emit(f"return ({struct_name}){{1, {{.ok_val = {val_code}}}}};")
                        else:
                            self._emit(f"return ({struct_name}){{0, {{.err_val = {val_code}}}}};")
                        return
                # fallback
                if stmt.expr.name == "Ok":
                    self._emit(f"return ({struct_name}){{1, {{.ok_val = {val_code}}}}};")
                else:
                    self._emit(f"return ({struct_name}){{0, {{.err_val = {val_code}}}}};")
                return
            expr_code = self._generate_expr(stmt.expr)
            # string VarRef をそのまま返すと呼び元でディープコピーが共有されて
            # double free が起きるため make_mryl_string でコピーして返す
            if return_var_to_deep_copy:
                # 返値変数は cleanup を skip しているので、コピーを返した後に解放
                if return_var_to_deep_copy in self.local_string_vars:
                    tmp = f"__ret_str_{return_var_to_deep_copy}"
                    self._emit(f"MrylString {tmp} = make_mryl_string({expr_code}.data);")
                    self._emit(f"free_mryl_string({expr_code});")
                    self._emit(f"return {tmp};")
                else:
                    # パラメータの場合: 呼び元が引数の所有権を持つのでコピーだけ返す
                    self._emit(f"return make_mryl_string({expr_code}.data);")
            else:
                self._emit(f"return {self._strip_outer_parens(expr_code)};")
        else:
            self._emit("return;")

    def _save_block_state(self):
        """ブロック開始前の追跡リスト長をスナップショットとして返す（#94）。
        _restore_block_state とペアで使い、ブロック終端でスコープ内変数を解放する。"""
        return (
            list(self.local_string_vars),
            len(self.local_box_vars),
            len(self.local_box_vec_vars),
            len(self.local_toarray_vec_vars),
            len(self.local_struct_box_vars),
            len(self.local_option_box_vars),
        )

    def _restore_block_state(self, state):
        """ブロック終端でスコープ内変数を解放し、追跡リストを保存時の状態に復元する（#94）。
        _emit_loop_iteration_cleanup と同じ処理だが if ブロック向けに命名を分けている。"""
        saved_str, saved_box, saved_bv, saved_tav, saved_sbv, saved_obv = state
        self._emit_loop_iteration_cleanup(
            saved_str, saved_box, saved_bv, saved_tav, saved_sbv, saved_obv
        )

    def _generate_if(self, stmt):
        """if/else if/else 文を出力する。
        各ブランチのスコープ内で宣言された Box / Vec / Option<Box> 等のリソースを
        ブランチ終端で解放する（#94: if ブロック内変数のスコープ外アクセス防止）。
        """
        cond = self._generate_expr(stmt.condition)
        self._emit(f"if ({self._strip_outer_parens(cond)}) {{")
        self.indent_level += 1
        state = self._save_block_state()
        for s in stmt.then_block.statements:
            self._generate_statement(s)
        self._restore_block_state(state)
        self.indent_level -= 1

        cur = stmt.else_block
        while cur is not None:
            if cur.__class__.__name__ == 'IfStmt':
                cur_cond = self._generate_expr(cur.condition)
                self._emit(f"}} else if ({self._strip_outer_parens(cur_cond)}) {{")
                self.indent_level += 1
                state = self._save_block_state()
                for s in cur.then_block.statements:
                    self._generate_statement(s)
                self._restore_block_state(state)
                self.indent_level -= 1
                cur = cur.else_block
            else:
                self._emit("} else {")
                self.indent_level += 1
                state = self._save_block_state()
                for s in cur.statements:
                    self._generate_statement(s)
                self._restore_block_state(state)
                self.indent_level -= 1
                cur = None

        self._emit("}")

    def _generate_if_inline(self, stmt):
        """インライン if 式 (内部利用; _generate_if に委譲) """
        self._generate_if(stmt)

    def _generate_while(self, stmt):
        """while ループを出力する。"""
        cond = self._generate_expr(stmt.condition)
        self._emit(f"while ({self._strip_outer_parens(cond)}) {{")
        self.indent_level += 1
        saved_str_vars  = list(self.local_string_vars)
        saved_box_count = len(self.local_box_vars)
        saved_bv_count  = len(self.local_box_vec_vars)
        saved_tav_count = len(self.local_toarray_vec_vars)
        saved_sbv_count = len(self.local_struct_box_vars)
        saved_obv_count = len(self.local_option_box_vars)
        for s in stmt.body.statements:
            self._generate_statement(s)
        # ループ内で宣言された文字列・Box・Vec・struct Box・Option<Box> 変数をイテレーション末に解放
        self._emit_loop_iteration_cleanup(
            saved_str_vars, saved_box_count, saved_bv_count, saved_tav_count,
            saved_sbv_count, saved_obv_count
        )
        self.indent_level -= 1
        self._emit("}")

    def _generate_for(self, stmt):
        """for ループを出力する (C スタイル / Range / 配列 / Vec) """
        if stmt.is_c_style:
            var_name  = stmt.variable
            init_expr = self._generate_expr(stmt.iterable)
            init_code = f"int32_t {var_name} = {init_expr}"

            cond_code = self._generate_expr(stmt.condition) if stmt.condition else "1"
            if stmt.update:
                if stmt.update.__class__.__name__ == "Assignment":
                    target_c  = self._generate_expr(stmt.update.target)
                    value_c   = self._generate_expr(stmt.update.expr)
                    update_code = f"{target_c} = {value_c}"
                else:
                    update_code = self._generate_expr(stmt.update)
                update_code = self._strip_outer_parens(update_code)
            else:
                update_code = ""
            cond_code = self._strip_outer_parens(cond_code)
            self._emit(f"for ({init_code}; {cond_code}; {update_code}) {{")
        else:
            if stmt.iterable.__class__.__name__ == "Range":
                range_expr = stmt.iterable
                start  = self._generate_expr(range_expr.start)
                end    = self._generate_expr(range_expr.end)
                cmp_op = "<=" if range_expr.inclusive else "<"
                self._emit(
                    f"for (int {stmt.variable} = {start}; "
                    f"{stmt.variable} {cmp_op} {end}; {stmt.variable}++) {{"
                )
            elif stmt.iterable.__class__.__name__ == "ArrayLiteral":
                array_size    = len(stmt.iterable.elements)
                loop_var_name = f"__i{self.loop_counter}"
                self.loop_counter += 1
                self._emit(
                    f"for (int {loop_var_name} = 0; "
                    f"{loop_var_name} < {array_size}; {loop_var_name}++) {{"
                )
                self.indent_level += 1
                self._emit(
                    f"int32_t {stmt.variable} = "
                    f"({self._generate_array_element(stmt.iterable, loop_var_name)});"
                )
                for s in stmt.body.statements:
                    self._generate_statement(s)
                self.indent_level -= 1
                self._emit("}")
                return
            elif stmt.iterable.__class__.__name__ == "VarRef":
                var_name = stmt.iterable.name
                if var_name in self.vec_var_types:
                    et            = self.vec_var_types[var_name]
                    loop_var_name = f"__i{self.loop_counter}"
                    self.loop_counter += 1
                    self._emit(
                        f"for (int32_t {loop_var_name} = 0; "
                        f"{loop_var_name} < {var_name}.len; {loop_var_name}++) {{"
                    )
                    self.indent_level += 1
                    # フォールバックを et 自身にすることで MrylVec_X / struct 名も正しく扱える
                    ct = {
                        "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
                        "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t",
                        "f32": "float",  "f64": "double",   "bool": "int",
                        "string": "MrylString",
                    }.get(et, et)
                    self._emit(f"{ct} {stmt.variable} = {var_name}.data[{loop_var_name}];")
                    self.env[-1][stmt.variable] = et
                    # 多次元配列の中間次元: 要素型が MrylVec_X の場合、ネストした
                    # for ループでも vec_var_types を参照できるよう登録する
                    # 例: string[][] → row の et = "MrylVec_MrylString"
                    #     for v in row → vec_var_types["row"] = "MrylString"
                    if et.startswith("MrylVec_"):
                        self.vec_var_types[stmt.variable] = et[len("MrylVec_"):]
                    saved_str_vars  = list(self.local_string_vars)
                    saved_box_count = len(self.local_box_vars)
                    saved_bv_count  = len(self.local_box_vec_vars)
                    saved_tav_count = len(self.local_toarray_vec_vars)
                    saved_sbv_count = len(self.local_struct_box_vars)
                    saved_obv_count = len(self.local_option_box_vars)
                    for s in stmt.body.statements:
                        self._generate_statement(s)
                    self._emit_loop_iteration_cleanup(
                        saved_str_vars, saved_box_count, saved_bv_count, saved_tav_count,
                        saved_sbv_count, saved_obv_count
                    )
                    self.indent_level -= 1
                    self._emit("}")
                    return
                elif var_name in self.array_sizes:
                    array_size    = self.array_sizes[var_name]
                    loop_var_name = f"__i{self.loop_counter}"
                    self.loop_counter += 1
                    self._emit(
                        f"for (int {loop_var_name} = 0; "
                        f"{loop_var_name} < {array_size}; {loop_var_name}++) {{"
                    )
                    self.indent_level += 1
                    _c_arr_map = {
                        "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
                        "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t",
                        "f32": "float", "f64": "double", "string": "MrylString", "bool": "int",
                    }
                    arr_elem_type = self.env[-1].get(var_name, 'i32')
                    arr_elem_c    = _c_arr_map.get(arr_elem_type, arr_elem_type)
                    self._emit(f"{arr_elem_c} {stmt.variable} = {var_name}[{loop_var_name}];")
                    self.env[-1][stmt.variable] = arr_elem_type
                    saved_str_vars  = list(self.local_string_vars)
                    saved_box_count = len(self.local_box_vars)
                    saved_bv_count  = len(self.local_box_vec_vars)
                    saved_tav_count = len(self.local_toarray_vec_vars)
                    saved_sbv_count = len(self.local_struct_box_vars)
                    saved_obv_count = len(self.local_option_box_vars)
                    for s in stmt.body.statements:
                        self._generate_statement(s)
                    self._emit_loop_iteration_cleanup(
                        saved_str_vars, saved_box_count, saved_bv_count, saved_tav_count,
                        saved_sbv_count, saved_obv_count
                    )
                    self.indent_level -= 1
                    self._emit("}")
                    return
                else:
                    self._emit(f"// WARNING: Array size unknown for {var_name}, using fallback")
                    self._emit(
                        f"for (int {stmt.variable} = 0; "
                        f"{stmt.variable} < sizeof({var_name})/sizeof({var_name}[0]); "
                        f"{stmt.variable}++) {{"
                    )
            else:
                iterable = self._generate_expr(stmt.iterable)
                self._emit(f"// for ({stmt.variable} in {iterable})")
                self._emit(
                    f"for (int {stmt.variable} = 0; {stmt.variable} < 10; {stmt.variable}++) {{"
                )

        self.indent_level += 1
        saved_str_vars  = list(self.local_string_vars)
        saved_box_count = len(self.local_box_vars)
        saved_bv_count  = len(self.local_box_vec_vars)
        saved_tav_count = len(self.local_toarray_vec_vars)
        saved_sbv_count = len(self.local_struct_box_vars)
        saved_obv_count = len(self.local_option_box_vars)
        for s in stmt.body.statements:
            self._generate_statement(s)
        self._emit_loop_iteration_cleanup(
            saved_str_vars, saved_box_count, saved_bv_count, saved_tav_count,
            saved_sbv_count, saved_obv_count
        )
        self.indent_level -= 1
        self._emit("}")

    def _generate_array_element(self, array_expr, index) -> str:
        """配列式とインデックスから要素アクセス式を生成する """
        arr_code = self._generate_expr(array_expr)
        return f"{arr_code}[{index}]"
