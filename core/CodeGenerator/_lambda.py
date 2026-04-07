from __future__ import annotations
from Ast import Block, ExprStmt, FunctionDecl, TypeNode
from CodeGenerator._proto import _CodeGeneratorBase

class CodeGeneratorLambdaMixin(_CodeGeneratorBase):
    """ラムダ・クロージャの C コード生成を担当する Mixin。
    _body_has_await / _collect_captures /
    _generate_lambda / _generate_lambda_inline / _generate_async_lambda
    """

    def _body_has_await(self, body) -> bool:
        """関数ボディに await 文が含まれるかどうかを返す（ループ内も再帰検索）。"""
        if not body:
            return False
        return self._stmts_have_await(body.statements)

    def _stmts_have_await(self, stmts) -> bool:
        """文リストに await が含まれるかを再帰的に検査する。"""
        for stmt in stmts:
            cls = stmt.__class__.__name__
            if cls == 'LetDecl' and stmt.init_expr and \
               stmt.init_expr.__class__.__name__ == 'AwaitExpr':
                return True
            if cls == 'ExprStmt' and stmt.expr.__class__.__name__ == 'AwaitExpr':
                return True
            if cls in ('ForStmt', 'WhileStmt') and stmt.body:
                if self._stmts_have_await(stmt.body.statements):
                    return True
            if cls == 'IfStmt':
                if stmt.then_block and self._stmts_have_await(stmt.then_block.statements):
                    return True
                if stmt.else_block:
                    eb_cls = stmt.else_block.__class__.__name__
                    eb_stmts = [stmt.else_block] if eb_cls == 'IfStmt' \
                               else stmt.else_block.statements
                    if self._stmts_have_await(eb_stmts):
                        return True
        return False

    def _collect_mutable_captures(self, node, param_names: set) -> set:
        """ラムダ本体で代入される外部変数名を収集する（ミュータブルキャプチャ判定）。
        Assignment の LHS が param_names 外の VarRef であればミュータブルと判定する。
        """
        mutable = set()

        def walk(n):
            if n is None:
                return
            cls = n.__class__.__name__
            if cls == 'Assignment':
                # LHS がラムダパラメータ外の変数参照 → ミュータブルキャプチャ
                if n.target.__class__.__name__ == 'VarRef' and n.target.name not in param_names:
                    mutable.add(n.target.name)
                walk(n.expr)
            elif cls == 'Block':
                for s in n.statements:
                    walk(s)
            elif cls == 'ExprStmt':
                walk(n.expr)
            elif cls in ('IfStmt', 'IfExpr'):
                walk(n.condition)
                walk(n.then_block)
                if n.else_block:
                    walk(n.else_block)
            elif cls in ('ForStmt', 'WhileStmt'):
                if n.body:
                    walk(n.body)
            elif cls == 'LetDecl':
                if n.init_expr:
                    walk(n.init_expr)

        walk(node)
        return mutable

    def _collect_captures(self, node, param_names: set) -> dict:
        """ラムダ本体からクロージャキャプチャ変数を収集する。
        戻り値: {変数名: C型文字列}
        """
        captures = {}

        def walk(n):
            if n is None:
                return
            cls = n.__class__.__name__
            if cls == 'VarRef' and n.name not in param_names and n.name not in captures:
                for scope in reversed(self.env):
                    if n.name in scope:
                        t   = scope[n.name]
                        # fn/fn_closure 型は fn_var_c_types から実際の MrylFn_* 型を取得
                        if t in ("fn", "fn_closure"):
                            c_t = self.fn_var_c_types.get(n.name, "void*")
                        else:
                            c_t = {
                                "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
                                "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t",
                                "f32": "float",  "f64": "double",
                                "string": "MrylString", "bool": "int", "int": "int32_t",
                            }.get(t, "int32_t")
                        captures[n.name] = c_t
                        break
            elif cls in ('BinaryOp', 'CompareOp'):
                walk(n.left); walk(n.right)
            elif cls == 'UnaryOp':
                walk(n.operand)
            elif cls == 'FunctionCall':
                for a in n.args:
                    walk(a)
            elif cls == 'Block':
                for s in n.statements:
                    walk(s)
            elif cls == 'Assignment':
                walk(n.target)
                walk(n.expr)
            elif cls == 'LetDecl':
                if n.init_expr:
                    walk(n.init_expr)
            elif cls == 'ReturnStmt':
                if n.expr:
                    walk(n.expr)
            elif cls == 'ExprStmt':
                walk(n.expr)
            elif cls in ('IfStmt', 'IfExpr'):
                walk(n.condition)
                walk(n.then_block)
                if n.else_block:
                    walk(n.else_block)
            elif cls == 'MethodCall':
                walk(n.obj)
                for a in (n.args or []):
                    walk(a)

        walk(node)
        return captures

    def _generate_lambda(self, expr) -> str:
        """Lambda ノードを static ヘルパー関数として pending_lambdas に追加し関数名を返す。"""
        lam_name = f"__lambda_{self.lambda_counter}"
        self.lambda_counter += 1

        if getattr(expr, 'is_async', False):
            return self._generate_async_lambda(expr, lam_name)

        param_names  = {p.name for p in expr.params}
        captures     = self._collect_captures(expr.body, param_names)
        # ミュータブルキャプチャ（ラムダ内で代入される変数）をポインタ経由で渡す（#83）
        mutable_set  = self._collect_mutable_captures(expr.body, param_names)

        params_c = []
        for p in expr.params:
            ptype = self._type_to_c(p.type_node) if p.type_node else "int32_t"
            params_c.append(f"{ptype} {p.name}")
        params_str = ", ".join(params_c) if params_c else "void"

        saved_code             = self.code
        saved_indent           = self.indent_level
        saved_capture_map      = dict(self.capture_map)
        saved_local_str_vars   = list(getattr(self, 'local_string_vars', []))
        saved_temp_str_ctr     = getattr(self, 'temp_string_counter', 0)
        self.code              = []
        self.indent_level      = 1
        self.local_string_vars = []
        self.temp_string_counter = 0
        if captures:
            # ミュータブル変数は *(__env->n)、読み取り専用は __env->n でアクセス
            self.capture_map = {
                n: (f"*(__env->{n})" if n in mutable_set else f"__env->{n}")
                for n in captures
            }

        # ラムダパラメータを env に一時追加し、body 内の型推論を正確にする
        # (例: (xs: i32[]) => xs で xs の型 vec_i32 が _infer_expr_type から取れるようにする)
        lam_env = {}
        for p in expr.params:
            if p.type_node:
                if p.type_node.array_size == -1:
                    lam_env[p.name] = f"vec_{p.type_node.name}"
                else:
                    lam_env[p.name] = p.type_node.name
        self.env.append(lam_env)

        if isinstance(expr.body, Block):
            for stmt in expr.body.statements:
                self._generate_statement(stmt)
            inferred = getattr(expr, 'inferred_return_type', None)
            if inferred is None or inferred.name == 'void':
                ret_type = "void"
            elif getattr(inferred, 'array_size', None) == -1:
                # 動的配列を返す block lambda → MrylVec_<T> を返り値型にする
                ret_type = f"MrylVec_{inferred.name}"
            else:
                ret_type = self._type_to_c(inferred)
        else:
            body_expr = self._generate_expr(expr.body)
            body_t    = self._infer_expr_type(expr.body)
            if body_t == "void":
                self._emit(f"{body_expr};")
                ret_type = "void"
            else:
                self._emit(f"return {body_expr};")
                inferred = getattr(expr, 'inferred_return_type', None)
                body_cls = expr.body.__class__.__name__
                if body_cls == 'ArrayLiteral' and expr.body.elements:
                    # ArrayLiteral を返す式ラムダ: 要素型から MrylVec_<T> を決定
                    elem_t   = self._infer_expr_type(expr.body.elements[0])
                    ret_type = f"MrylVec_{elem_t}"
                elif inferred is not None and getattr(inferred, 'array_size', None) == -1:
                    # 動的配列を返す式ラムダ (例: (xs: i32[]) => xs)
                    ret_type = f"MrylVec_{inferred.name}"
                else:
                    # inferred_return_type が未設定の場合は body_t から C 型を決定する（#81）
                    # 例: (a: string, b: string) => a + b → body_t="string" → "MrylString"
                    if body_t and body_t not in ("any", "void", "unknown"):
                        ret_type = self._type_to_c_base(body_t)
                    else:
                        ret_type = "int32_t"

        self.env.pop()

        body_lines             = self.code
        self.code              = saved_code
        self.indent_level      = saved_indent
        self.capture_map       = saved_capture_map
        self.local_string_vars = saved_local_str_vars
        self.temp_string_counter = saved_temp_str_ctr

        self.pending_lambdas.append((lam_name, ret_type, params_str, body_lines, captures, mutable_set))
        # fat pointer のため arg_cs / ret_c / captures / mutable_captures を登録（_stmt.py / _expr.py が参照）
        arg_cs = [self._type_to_c(p.type_node) if p.type_node else "int32_t" for p in expr.params]
        self.lambda_captures[lam_name] = {
            'captures':         captures,
            'mutable_captures': mutable_set,
            'ret_c':            ret_type,
            'arg_cs':           arg_cs,
        }
        return lam_name

    def _generate_lambda_inline(self, expr, var_name: str):
        """let 宣言のラムダ初期値を生成する。
        戻り値: (lam_name, ret_type, params_str, captures)
        """
        lam_name = f"__lambda_{self.lambda_counter}"
        self.lambda_counter += 1

        if getattr(expr, 'is_async', False):
            self._generate_async_lambda(expr, lam_name)
            params_c = []
            for p in expr.params:
                ptype = self._type_to_c(p.type_node) if p.type_node else "int32_t"
                params_c.append(f"{ptype} {p.name}")
            params_str = ", ".join(params_c) if params_c else "void"
            return lam_name, "MrylTask*", params_str, {}

        param_names  = {p.name for p in expr.params}
        captures     = self._collect_captures(expr.body, param_names)
        # ミュータブルキャプチャ（ラムダ内で代入される変数）をポインタ経由で渡す（#83）
        mutable_set  = self._collect_mutable_captures(expr.body, param_names)

        params_c = []
        for p in expr.params:
            ptype = self._type_to_c(p.type_node) if p.type_node else "int32_t"
            params_c.append(f"{ptype} {p.name}")
        params_str = ", ".join(params_c) if params_c else "void"

        if isinstance(expr.body, Block):
            inferred = getattr(expr, 'inferred_return_type', None)
            ret_type = self._type_to_c(inferred) if inferred and inferred.name != 'void' else "void"
        else:
            # body_t から C 型を決定する（inferred_return_type が設定されていない場合の fallback）（#81）
            body_t = self._infer_expr_type(expr.body)
            if body_t and body_t not in ("any", "void", "unknown"):
                ret_type = self._type_to_c_base(body_t)
            else:
                ret_type = "int32_t"

        saved_code             = self.code
        saved_indent           = self.indent_level
        saved_capture_map      = dict(self.capture_map)
        saved_local_str_vars   = list(getattr(self, 'local_string_vars', []))
        saved_temp_str_ctr     = getattr(self, 'temp_string_counter', 0)
        body_lines_code        = []
        self.code              = body_lines_code
        self.indent_level      = 1
        self.local_string_vars = []
        self.temp_string_counter = 0
        if captures:
            # ミュータブル変数は *(__env->n)、読み取り専用は __env->n でアクセス
            self.capture_map = {
                n: (f"*(__env->{n})" if n in mutable_set else f"__env->{n}")
                for n in captures
            }

        if isinstance(expr.body, Block):
            for stmt in expr.body.statements:
                self._generate_statement(stmt)
        else:
            body_expr_code = self._generate_expr(expr.body)
            self._emit(f"return {body_expr_code};")

        self.code              = saved_code
        self.indent_level      = saved_indent
        self.capture_map       = saved_capture_map
        self.local_string_vars = saved_local_str_vars
        self.temp_string_counter = saved_temp_str_ctr

        self.pending_lambdas.append((lam_name, ret_type, params_str, body_lines_code, captures, mutable_set))
        # fat pointer のため arg_cs / ret_c / captures / mutable_captures を登録
        arg_cs = [self._type_to_c(p.type_node) if p.type_node else "int32_t" for p in expr.params]
        self.lambda_captures[lam_name] = {
            'captures':         captures,
            'mutable_captures': mutable_set,
            'ret_c':            ret_type,
            'arg_cs':           arg_cs,
        }
        return lam_name, ret_type, params_str, captures

    def _generate_async_lambda(self, expr, lam_name: str) -> str:
        """async lambda を状態機械 C コードとして生成し pending_async_lambda_blocks に追加する。
        戻り値: ファクトリ関数名 (MrylTask* lam_name(params))
        """
        body_block = expr.body if isinstance(expr.body, Block) else Block([ExprStmt(expr.body)])
        inferred   = getattr(expr, 'inferred_return_type', None)
        ret_type   = inferred if inferred else TypeNode("void")

        synth_func = FunctionDecl(
            name=lam_name,
            params=expr.params,
            return_type=ret_type,
            body=body_block,
            is_async=True,
        )

        saved_code             = self.code
        saved_indent           = self.indent_level
        saved_sm_mode          = self.sm_mode
        saved_sm_vars          = self.sm_vars
        saved_sm_await_handles = getattr(self, 'sm_await_handles', {})
        saved_lambda_counter   = self.lambda_counter
        saved_capture_map      = dict(self.capture_map)
        saved_ident_renames    = dict(self.ident_renames)
        saved_return_type      = self.current_return_type

        self.code         = []
        self.indent_level = 0
        self.capture_map  = {}
        self.ident_renames = {}

        self.env.append({})
        for p in expr.params:
            ptype_name            = p.type_node.name if p.type_node else 'i32'
            self.env[-1][p.name] = ptype_name

        self._generate_async_state_machine(synth_func)
        self.env.pop()

        async_lines              = self.code
        self.code                = saved_code
        self.indent_level        = saved_indent
        self.sm_mode             = saved_sm_mode
        self.sm_vars             = saved_sm_vars
        self.sm_await_handles    = saved_sm_await_handles
        self.capture_map         = saved_capture_map
        self.ident_renames       = saved_ident_renames
        self.current_return_type = saved_return_type

        self.pending_async_lambda_blocks.append(async_lines)
        return lam_name
