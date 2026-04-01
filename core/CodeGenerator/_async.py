from __future__ import annotations
from CodeGenerator._proto import _CodeGeneratorBase
from Ast import TypeNode

class CodeGeneratorAsyncMixin(_CodeGeneratorBase):
    """非同期ステートマシン生成を担当する Mixin
    _sm_let_c_type / _split_by_await /
    _generate_async_state_machine / _emit_await_setup /
    _generate_sm_stmt /
    _emit_task_complete / _emit_task_factory /
    _emit_main_sm_entry / _emit_task_runtime
    """

    def _sm_let_c_type(self, stmt) -> str:
        """SM フィールドの C 型を LetDecl ノードから決定する """
        init_cls = stmt.init_expr.__class__.__name__ if stmt.init_expr else None
        if init_cls == 'Lambda':
            return 'void*'
        if init_cls == 'FunctionCall':
            f = self.program_functions.get(stmt.init_expr.name)
            if f and getattr(f, 'is_async', False):
                return 'MrylTask*'
            for scope in reversed(self.env):
                if stmt.init_expr.name in scope and scope[stmt.init_expr.name] == 'async_fn':
                    return 'MrylTask*'
        if init_cls == 'AwaitExpr' and stmt.type_node:
            return self._type_to_c(stmt.type_node)
        if stmt.type_node:
            return self._type_to_c(stmt.type_node)
        return 'int32_t'

    def _split_by_await(self, stmts):
        """文リストを await ごとにセグメント分割する
        戻り値: [(pre_stmts, await_stmt_or_None)]
        """
        segments = []
        current  = []
        for stmt in stmts:
            cls      = stmt.__class__.__name__
            is_await = (
                (cls == 'LetDecl' and stmt.init_expr and
                 stmt.init_expr.__class__.__name__ == 'AwaitExpr') or
                (cls == 'ExprStmt' and stmt.expr.__class__.__name__ == 'AwaitExpr')
            )
            if is_await:
                segments.append((current, stmt))
                current = []
            else:
                current.append(stmt)
        segments.append((current, None))
        return segments

    # ------------------------------------------------------------------ #
    #  SM state builder helpers                                           #
    # ------------------------------------------------------------------ #

    def _collect_sm_fields_recursive(self, stmts, sm_fields, seen_names=None):
        """stmts を再帰走査して SM フィールドを収集する (ループ変数も含む)。"""
        if seen_names is None:
            seen_names = set()
        for stmt in stmts:
            cls = stmt.__class__.__name__
            if cls == 'LetDecl':
                if stmt.name not in seen_names:
                    seen_names.add(stmt.name)
                    # 動的配列型（i32[] 等）は "vec_T" として登録し、メソッド呼び出し時に正確な型が取れるようにする
                    t = stmt.type_node
                    if t and getattr(t, 'array_size', None) == -1:
                        mtype = f"vec_{t.name}"
                    else:
                        mtype = 'any'
                    sm_fields.append((self._sm_let_c_type(stmt), stmt.name, mtype))
            elif cls == 'ForStmt':
                if stmt.variable and stmt.variable not in seen_names:
                    seen_names.add(stmt.variable)
                    sm_fields.append(('int32_t', stmt.variable, 'i32'))
                if stmt.body:
                    self._collect_sm_fields_recursive(stmt.body.statements, sm_fields, seen_names)
            elif cls == 'WhileStmt':
                if stmt.body:
                    self._collect_sm_fields_recursive(stmt.body.statements, sm_fields, seen_names)
            elif cls == 'IfStmt':
                if stmt.then_block:
                    self._collect_sm_fields_recursive(stmt.then_block.statements, sm_fields, seen_names)
                if stmt.else_block:
                    eb_cls = stmt.else_block.__class__.__name__
                    eb_stmts = [stmt.else_block] if eb_cls == 'IfStmt' \
                               else stmt.else_block.statements
                    self._collect_sm_fields_recursive(eb_stmts, sm_fields, seen_names)

    def _build_sm_states(self, stmts):
        """stmts から SM state リストと for ループ初期化リストを返す。

        state dict:
          'id'    : int
          'items' : [('S', stmt)
                    |('LC', cond_expr, end_id)
                    |('LU', update_expr)
                    |('AR', await_stmt, handle_name)]
          'term'  : ('C',)
                  | ('G', target_id)
                  | ('A', await_stmt, handle_name, resume_id)

        for_inits : [(var_name, init_expr_node)]
        """
        states     = []
        for_inits  = []

        def new_s():
            s = {'id': len(states), 'items': [], 'term': None}
            states.append(s)
            return s

        def process(stmts_in, cur):
            for stmt in stmts_in:
                cls = stmt.__class__.__name__
                is_await = (
                    (cls == 'LetDecl' and stmt.init_expr and
                     stmt.init_expr.__class__.__name__ == 'AwaitExpr') or
                    (cls == 'ExprStmt' and stmt.expr.__class__.__name__ == 'AwaitExpr')
                )
                if is_await:
                    resume = new_s()
                    handle = f"__h_{cur['id']}"
                    self.sm_await_handles[cur['id']] = handle
                    resume['items'].append(('AR', stmt, handle))
                    cur['term'] = ('A', stmt, handle, resume['id'])
                    cur = resume
                elif cls == 'ForStmt' and stmt.is_c_style and \
                        self._stmts_have_await(stmt.body.statements):
                    # ループ変数を cur state の LI アイテムとして追加
                    # (外側ループが再実行されるたびに再初期化される)
                    cur['items'].append(('LI', stmt.variable, stmt.iterable))
                    head       = new_s()   # loop head  (condition check)
                    end        = new_s()   # after loop
                    cur['term'] = ('G', head['id'])
                    body_entry = new_s()   # loop body
                    head['items'].append(('LC', stmt.condition, end['id']))
                    head['term'] = ('G', body_entry['id'])
                    body_exit   = process(stmt.body.statements, body_entry)
                    if body_exit is not None:
                        body_exit['items'].append(('LU', stmt.update))
                        body_exit['term'] = ('G', head['id'])
                    cur = end
                elif cls == 'WhileStmt' and \
                        self._stmts_have_await(stmt.body.statements):
                    head       = new_s()
                    end        = new_s()
                    cur['term'] = ('G', head['id'])
                    body_entry = new_s()
                    head['items'].append(('LC', stmt.condition, end['id']))
                    head['term'] = ('G', body_entry['id'])
                    body_exit   = process(stmt.body.statements, body_entry)
                    if body_exit is not None:
                        body_exit['term'] = ('G', head['id'])
                    cur = end
                else:
                    cur['items'].append(('S', stmt))
            return cur

        cur0  = new_s()
        final = process(stmts, cur0)
        if final is not None and final['term'] is None:
            final['term'] = ('C',)
        return states, for_inits

    def _emit_single_sm_state(self, state, func, has_return_val: bool):
        """1 つの SM state の C コードを出力する。"""
        self._emit(f"__state_{state['id']}: {{")
        self.indent_level += 1

        for item in state['items']:
            kind = item[0]
            if kind == 'S':
                self._generate_sm_stmt(item[1], func, has_return_val)

            elif kind == 'LI':
                # ループ変数の初期化 (毎イテレーション実行)
                var_name  = item[1]
                init_expr = item[2]
                init_code = self._generate_expr(init_expr)
                self._emit(f"__sm->{var_name} = {init_code};")

            elif kind == 'LC':
                # ループ条件チェック: 偽なら end_id へジャンプ
                cond_code = self._strip_outer_parens(self._generate_expr(item[1]))
                end_id    = item[2]
                self._emit(f"if (!({cond_code})) {{")
                self.indent_level += 1
                self._emit(f"__sm->__state = {end_id};")
                self._emit(f"goto __state_{end_id};")
                self.indent_level -= 1
                self._emit("}")

            elif kind == 'LU':
                # ループ更新式
                update = item[1]
                u_cls  = update.__class__.__name__
                if u_cls == 'Assignment':
                    target = self._generate_expr(update.target)
                    val    = self._generate_expr(update.expr)
                    self._emit(f"{target} = {val};")
                else:
                    code = self._strip_outer_parens(self._generate_expr(update))
                    self._emit(f"{code};")

            elif kind == 'AR':
                # await resume: 結果取得 + handle release
                await_stmt  = item[1]
                handle_name = item[2]        # '__h_N'
                handle      = f"__sm->{handle_name}"
                a_cls       = await_stmt.__class__.__name__
                if a_cls == 'LetDecl':
                    var = await_stmt.name
                    if await_stmt.type_node and await_stmt.type_node.name != 'void':
                        ctype = self._type_to_c(await_stmt.type_node)
                        self._emit(f"if ({handle}->state == MRYL_TASK_CANCELLED) {{")
                        self.indent_level += 1
                        # struct 型（Result/Option 等）は "= 0" では代入できないため
                        # memset でゼロ初期化する。is_ok=0 となり Err 扱いになる (#51)
                        self._emit(f"memset(&__sm->{var}, 0, sizeof({ctype}));")
                        self.indent_level -= 1
                        self._emit("} else {")
                        self.indent_level += 1
                        self._emit(f"__sm->{var} = *({ctype}*){handle}->result;")
                        self.indent_level -= 1
                        self._emit("}")
                self._emit(f"__task_release({handle});")

        # ターミネータ
        term = state['term']
        if term is None or term[0] == 'C':
            has_explicit_return = any(
                item[0] == 'S' and item[1].__class__.__name__ == 'ReturnStmt'
                for item in state['items']
            )
            if not has_explicit_return:
                self._emit_task_complete(func, has_return_val)
        elif term[0] == 'G':
            self._emit(f"goto __state_{term[1]};")
        elif term[0] == 'A':
            # term = ('A', await_stmt, handle_name, resume_id)
            self._emit_await_setup(term[1], term[3], state['id'])
            self._emit(f"goto __state_{term[3]};")

        self.indent_level -= 1
        self._emit("}")

    # ------------------------------------------------------------------ #
    #  Main SM generator                                                   #
    # ------------------------------------------------------------------ #

    def _generate_async_state_machine(self, func):
        """async 関数をステートマシン形式の C コードとして出力する。
        for/while ループ内の await も完全対応。"""
        func_name      = func.name
        is_main        = (func_name == 'main')
        has_return_val = (not is_main) and \
                         func.return_type and func.return_type.name != 'void'
        sm_struct  = f"__{self._to_pascal(func_name)}_SM"
        move_next  = f"__{func_name}_move_next"

        # --- SM フィールド収集 (ループ変数も再帰的に収集) ---
        sm_fields = []
        if not is_main:
            for p in (func.params or []):
                sm_fields.append((
                    self._type_to_c(p.type_node),
                    p.name,
                    p.type_node.name if p.type_node else 'any',
                ))
        stmts = func.body.statements if func.body else []
        self.sm_await_handles = {}
        self._collect_sm_fields_recursive(stmts, sm_fields)
        for (_, fname, mtype) in sm_fields:
            self.env[-1][fname] = mtype
            # 動的配列 SM フィールドは vec_var_types にも登録（ArrayAccess の .data[i] 生成に必要）
            if mtype.startswith("vec_"):
                self.vec_var_types[fname] = mtype[4:]

        # --- SM ステート構築 ---
        states, for_inits = self._build_sm_states(stmts)
        num_states = len(states)

        # --- 1. SM 構造体を出力 ---
        self._emit(f"// === State machine for {func_name} ===")
        self._emit(f"typedef struct {{")
        self.indent_level += 1
        self._emit("int __state;")
        for (ctype, fname, _) in sm_fields:
            self._emit(f"{ctype} {fname};")
        for handle_name in self.sm_await_handles.values():
            self._emit(f"MrylTask* {handle_name};")
        self._emit("MrylTask* __task;")
        self.indent_level -= 1
        self._emit(f"}} {sm_struct};")
        self._emit("")

        # --- 2. move_next 関数を出力 ---
        self._emit(f"void {move_next}(MrylTask* __task) {{")
        self.indent_level += 1
        self._emit(f"{sm_struct}* __sm = ({sm_struct}*)__task->sm;")
        self._emit("if (__task->state == MRYL_TASK_CANCELLED) return;")
        self._emit(f"switch (__sm->__state) {{")
        self.indent_level += 1
        for i in range(num_states):
            self._emit(f"case {i}: goto __state_{i};")
        self._emit("default: return;")
        self.indent_level -= 1
        self._emit("}")

        self.sm_mode = True
        self.sm_vars = {fname for (_, fname, _) in sm_fields}
        for handle_name in self.sm_await_handles.values():
            self.sm_vars.add(handle_name)

        for state in states:
            self._emit_single_sm_state(state, func, has_return_val)

        self.sm_mode = False
        self.sm_vars = set()
        self.indent_level -= 1
        self._emit("}")
        self._emit("")

        # --- 3. ファクトリ関数 or main エントリポイントを出力 ---
        if is_main:
            self._emit_main_sm_entry(sm_struct, move_next, for_inits)
        else:
            self._emit_task_factory(func, sm_struct, move_next, for_inits)

    def _emit_await_setup(self, await_stmt, next_state: int, await_index: int = 0):
        """await セットアップ(タスクの awaiter 設定 + サスペンド)を出力する """
        cls = await_stmt.__class__.__name__
        if await_index in self.sm_await_handles:
            hf         = self.sm_await_handles[await_index]
            inner      = await_stmt.expr.expr if cls == 'ExprStmt' else await_stmt.init_expr.expr
            call_code  = self._generate_expr(inner)
            self._emit(f"__sm->{hf} = {call_code};")
            self._emit(f"__task_retain(__sm->{hf});")
            handle = f"__sm->{hf}"
        else:
            if cls == 'ExprStmt':
                handle = self._generate_expr(await_stmt.expr.expr)
            else:
                handle = self._generate_expr(await_stmt.init_expr.expr)

        self._emit(f"{handle}->awaiter = __task;")
        # COMPLETED / FAULTED どちらもタスク終了済み → resume コードへ続行
        # それ以外（PENDING/RUNNING/CANCELLED）はサスペンドして再スケジュールを待つ (#51)
        self._emit(f"if ({handle}->state != MRYL_TASK_COMPLETED && {handle}->state != MRYL_TASK_FAULTED) {{")
        self.indent_level += 1
        self._emit(f"__sm->__state = {next_state};")
        self._emit("return;")
        self.indent_level -= 1
        self._emit("}")

    def _generate_sm_stmt(self, stmt, func, has_return_val: bool):
        """SM 内文を出力する (LetDecl/ReturnStmt は SM フィールドへ代入) """
        cls      = stmt.__class__.__name__
        if cls == 'LetDecl':
            init_cls     = stmt.init_expr.__class__.__name__ if stmt.init_expr else None
            if init_cls == 'Lambda':
                lam_func = self._generate_expr(stmt.init_expr)
                self._emit(f"__sm->{stmt.name} = (void*){lam_func};")
                if getattr(stmt.init_expr, 'is_async', False):
                    self.env[-1][stmt.name] = "async_fn"
                    self.async_lambda_factories[stmt.name] = lam_func
                else:
                    self.env[-1][stmt.name] = "fn"
                return
            if init_cls == 'FunctionCall':
                f            = self.program_functions.get(stmt.init_expr.name)
                is_async_call = f and getattr(f, 'is_async', False)
                if not is_async_call:
                    for scope in reversed(self.env):
                        if stmt.init_expr.name in scope and scope[stmt.init_expr.name] == 'async_fn':
                            is_async_call = True
                            break
                if is_async_call:
                    args        = [self._generate_expr(a) for a in stmt.init_expr.args]
                    args_str    = ", ".join(args)
                    call_target = self.async_lambda_factories.get(stmt.init_expr.name, stmt.init_expr.name)
                    self._emit(f"__sm->{stmt.name} = {call_target}({args_str});")
                    self._emit(f"__task_retain(__sm->{stmt.name});")
                    return
            if stmt.init_expr:
                init_code = self._generate_expr(stmt.init_expr)
                self._emit(f"__sm->{stmt.name} = {init_code};")
        elif cls == 'ReturnStmt':
            if has_return_val and stmt.expr:
                ret_ctype = self._type_to_c(func.return_type)
                ret_code  = self._generate_expr(stmt.expr)
                self._emit(f"{ret_ctype}* __res = ({ret_ctype}*)malloc(sizeof({ret_ctype}));")
                self._emit(f"*__res = {ret_code};")
                self._emit(f"__task->result = (void*)__res;")
                # Result<T,E> の場合: is_ok フラグで FAULTED/COMPLETED を切り替え
                # Err を返した場合に await 側でエラー値を受け取れるようにする (#51)
                if func.return_type and func.return_type.name == "Result":
                    self._emit("__task->state = __res->is_ok ? MRYL_TASK_COMPLETED : MRYL_TASK_FAULTED;")
                else:
                    self._emit("__task->state = MRYL_TASK_COMPLETED;")
            else:
                self._emit("__task->state = MRYL_TASK_COMPLETED;")
            self._emit("__task_release(__task);")
            self._emit("if (__task->awaiter) __scheduler_post(__task->awaiter);")
            self._emit("return;")
        elif cls == 'IfStmt':
            # SM 内 if 文: 分岐内の return も SM 対応の void return に変換するため再帰
            cond_code = self._strip_outer_parens(self._generate_expr(stmt.condition))
            self._emit(f"if ({cond_code}) {{")
            self.indent_level += 1
            for s in (stmt.then_block.statements if stmt.then_block else []):
                self._generate_sm_stmt(s, func, has_return_val)
            self.indent_level -= 1
            if stmt.else_block:
                eb_cls = stmt.else_block.__class__.__name__
                if eb_cls == 'IfStmt':
                    # else if チェーン: "} else {" を emit して再帰
                    self._emit("} else {")
                    self.indent_level += 1
                    self._generate_sm_stmt(stmt.else_block, func, has_return_val)
                    self.indent_level -= 1
                else:
                    self._emit("} else {")
                    self.indent_level += 1
                    for s in stmt.else_block.statements:
                        self._generate_sm_stmt(s, func, has_return_val)
                    self.indent_level -= 1
            self._emit("}")
        else:
            self._generate_statement(stmt)

    def _emit_task_complete(self, func, has_return_val: bool):
        """タスク完了コードを出力する (戻り値なしの場合) """
        if not has_return_val:
            self._emit("__task->state = MRYL_TASK_COMPLETED;")
            self._emit("__task_release(__task);")
            self._emit("if (__task->awaiter) __scheduler_post(__task->awaiter);")
            self._emit("return;")

    def _emit_task_factory(self, func, sm_struct: str, move_next: str, for_inits=None):
        """タスクファクトリ関数を出力する (async fn の entry point) """
        func_name  = func.name
        params     = [f"{'const ' if getattr(p, 'is_fix', False) else ''}{self._type_to_c(p.type_node)} {p.name}" for p in (func.params or [])]
        params_str = ", ".join(params) if params else "void"
        self._emit(f"MrylTask* {func_name}({params_str}) {{") 
        self.indent_level += 1
        self._emit(f"MrylTask* __task = (MrylTask*)malloc(sizeof(MrylTask));")
        self._emit(f"{sm_struct}* __sm = ({sm_struct}*)malloc(sizeof({sm_struct}));")
        self._emit(f"memset(__sm, 0, sizeof({sm_struct}));")
        for p in (func.params or []):
            self._emit(f"__sm->{p.name} = {p.name};")
        for (var_name, init_expr) in (for_inits or []):
            init_code = self._generate_expr(init_expr)
            self._emit(f"__sm->{var_name} = {init_code};")
        self._emit(f"__sm->__task  = __task;")
        self._emit(f"__task->strong_count = 1;")
        self._emit(f"__task->weak_count   = 0;")
        self._emit(f"__task->state        = MRYL_TASK_PENDING;")
        self._emit(f"__task->result       = NULL;")
        self._emit(f"__task->move_next    = {move_next};")
        self._emit(f"__task->on_cancel    = NULL;")
        self._emit(f"__task->awaiter      = NULL;")
        self._emit(f"__task->sm           = __sm;")
        self._emit(f"__scheduler_post(__task);")
        self._emit(f"return __task;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")

    def _emit_main_sm_entry(self, sm_struct: str, move_next: str, for_inits=None):
        """main 関数のスケジューラエントリポイントを出力する """
        self._emit("int main(void) {")
        self.indent_level += 1
        self._emit("__scheduler_init();")
        self._emit(f"MrylTask* __main_task = (MrylTask*)malloc(sizeof(MrylTask));")
        self._emit(f"{sm_struct}* __main_sm = ({sm_struct}*)malloc(sizeof({sm_struct}));")
        self._emit(f"memset(__main_sm, 0, sizeof({sm_struct}));")
        for (var_name, init_expr) in (for_inits or []):
            init_code = self._generate_expr(init_expr)
            self._emit(f"__main_sm->{var_name} = {init_code};")
        self._emit(f"__main_sm->__task  = __main_task;")
        self._emit(f"__main_task->strong_count = 2;")
        self._emit(f"__main_task->weak_count   = 0;")
        self._emit(f"__main_task->state        = MRYL_TASK_PENDING;")
        self._emit(f"__main_task->result       = NULL;")
        self._emit(f"__main_task->move_next    = {move_next};")
        self._emit(f"__main_task->on_cancel    = NULL;")
        self._emit(f"__main_task->awaiter      = NULL;")
        self._emit(f"__main_task->sm           = __main_sm;")
        self._emit(f"__scheduler_post(__main_task);")
        self._emit(f"__scheduler_run();")
        self._emit(f"__task_release(__main_task);")
        self._emit("return 0;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")

    def _emit_task_runtime(self):
        """Mryl Task Runtime (MrylTask 構造体・スケジューラ) を出力する """
        lines = [
            "// ============================================================",
            "// Mryl Task Runtime",
            "// ============================================================",
            "",
            "typedef enum {",
            "    MRYL_TASK_PENDING,",
            "    MRYL_TASK_RUNNING,",
            "    MRYL_TASK_COMPLETED,",
            "    MRYL_TASK_CANCELLED,",
            "    MRYL_TASK_FAULTED",
            "} MrylTaskState;",
            "",
            "typedef struct MrylTask {",
            "    int           strong_count;",
            "    int           weak_count;",
            "    MrylTaskState state;",
            "    void*         result;",
            "    void        (*move_next)(struct MrylTask*);",
            "    void        (*on_cancel)(struct MrylTask*);",
            "    void*         sm;",
            "    struct MrylTask* awaiter;",
            "} MrylTask;",
            "",
            "#define __SCHEDULER_CAP 65536",
            "typedef struct {",
            "    MrylTask* queue[__SCHEDULER_CAP];",
            "    uint32_t head, tail;",
            "} MrylScheduler;",
            "",
            "static MrylScheduler __scheduler;",
            "",
            "static inline void __scheduler_init(void) {",
            "    __scheduler.head = __scheduler.tail = 0;",
            "}",
            "static inline void __scheduler_post(MrylTask* t) {",
            "    __scheduler.queue[__scheduler.tail++ % __SCHEDULER_CAP] = t;",
            "}",
            "static inline void __scheduler_run(void) {",
            "    while (__scheduler.head != __scheduler.tail) {",
            "        MrylTask* t = __scheduler.queue[__scheduler.head++  % __SCHEDULER_CAP];",
            "        if (t->state != MRYL_TASK_CANCELLED) t->move_next(t);",
            "    }",
            "}",
            "",
            "static inline MrylTask* __task_retain(MrylTask* t) {",
            "    if (t) t->strong_count++;",
            "    return t;",
            "}",
            "static inline void __task_release(MrylTask* t) {",
            "    if (!t) return;",
            "    if (--t->strong_count == 0) {",
            "        if (t->result) { free(t->result); t->result = NULL; }",
            "        if (t->sm)     { free(t->sm);     t->sm     = NULL; }",
            "        if (t->weak_count == 0) free(t);",
            "    }",
            "}",
            "static inline MrylTask* __task_weak_retain(MrylTask* t) {",
            "    if (t) t->weak_count++;",
            "    return t;",
            "}",
            "static inline void __task_weak_release(MrylTask* t) {",
            "    if (!t) return;",
            "    if (--t->weak_count == 0 && t->strong_count == 0) free(t);",
            "}",
            "static inline MrylTask* __task_lock(MrylTask* t) {",
            "    if (!t) return NULL;",
            "    if (t->state == MRYL_TASK_CANCELLED ||",
            "        t->state == MRYL_TASK_COMPLETED) return NULL;",
            "    t->strong_count++;",
            "    return t;",
            "}",
            "static inline void __task_cancel(MrylTask* t) {",
            "    if (!t) return;",
            "    if (t->state == MRYL_TASK_PENDING || t->state == MRYL_TASK_RUNNING) {",
            "        t->state = MRYL_TASK_CANCELLED;",
            "        if (t->on_cancel) t->on_cancel(t);",
            "        if (t->awaiter)  __scheduler_post(t->awaiter);",
            "    }",
            "}",
            "",
        ]
        for line in lines:
            self._emit(line)

    def _emit_combinator_helpers(self, combinator_types: dict):
        """Task::when_all / Task::when_any の型別 C ランタイム関数を出力する。

        combinator_types: { mryl_type_name: set_of_combinators }
          例: {"i32": {"when_all", "when_any"}, "f64": {"when_all"}}
        MrylVec_<T> ヘルパーより後に呼ぶこと（mryl_vec_<T>_push を使用するため）。
        """
        if not combinator_types:
            return
        self._emit("// ============================================================")
        self._emit("// Task Combinator Helpers (when_all / when_any)")
        self._emit("// ============================================================")
        self._emit("")

        for T, combinators in sorted(combinator_types.items()):
            # T は文字列（例 "i32"）、C は対応する C 型名
            C = self._type_to_c(TypeNode(T))

            if "when_all" in combinators:
                sm  = f"__WhenAll_{T}_SM"
                fn  = f"__when_all_{T}_move_next"
                fac = f"__mryl_when_all_{T}"
                self._emit(f"typedef struct {{ MrylTask** __tasks; int __count; MrylVec_{T} __result; }} {sm};")
                self._emit(f"static void {fn}(MrylTask* __task) {{")
                self.indent_level += 1
                self._emit(f"{sm}* __sm = ({sm}*)__task->sm;")
                # 全タスク完了チェック（CANCELLED も終了扱い）
                self._emit("for (int __i = 0; __i < __sm->__count; __i++) {")
                self.indent_level += 1
                self._emit("MrylTaskState __s = __sm->__tasks[__i]->state;")
                self._emit("if (__s == MRYL_TASK_PENDING || __s == MRYL_TASK_RUNNING) {")
                self.indent_level += 1
                self._emit("__scheduler_post(__task);")
                self._emit("return;")
                self.indent_level -= 1
                self._emit("}")
                self.indent_level -= 1
                self._emit("}")
                # 全完了 — 結果を MrylVec_T に収集
                self._emit(f"__sm->__result = mryl_vec_{T}_new();")
                self._emit("for (int __i = 0; __i < __sm->__count; __i++) {")
                self.indent_level += 1
                self._emit(f"MrylTaskState __s = __sm->__tasks[__i]->state;")
                self._emit(f"{C} __val = (__s == MRYL_TASK_COMPLETED) ? *({C}*)__sm->__tasks[__i]->result : ({C}){{0}};")
                self._emit(f"mryl_vec_{T}_push(&__sm->__result, __val);")
                self._emit("__task_release(__sm->__tasks[__i]);")
                self.indent_level -= 1
                self._emit("}")
                self._emit("free(__sm->__tasks);")
                self._emit(f"MrylVec_{T}* __res = (MrylVec_{T}*)malloc(sizeof(MrylVec_{T}));")
                self._emit("*__res = __sm->__result;")
                self._emit("__task->result = (void*)__res;")
                self._emit("__task->state = MRYL_TASK_COMPLETED;")
                self._emit("__task_release(__task);")
                self._emit("if (__task->awaiter) __scheduler_post(__task->awaiter);")
                self.indent_level -= 1
                self._emit("}")
                self._emit(f"static MrylTask* {fac}(MrylTask** __src, int __count) {{")
                self.indent_level += 1
                self._emit(f"MrylTask* __task = (MrylTask*)malloc(sizeof(MrylTask));")
                self._emit(f"{sm}* __sm = ({sm}*)malloc(sizeof({sm}));")
                self._emit(f"memset(__sm, 0, sizeof({sm}));")
                # tasks をコピーして retain
                self._emit("MrylTask** __tc = (MrylTask**)malloc(__count * sizeof(MrylTask*));")
                self._emit("for (int __i = 0; __i < __count; __i++) { __tc[__i] = __src[__i]; __task_retain(__tc[__i]); }")
                self._emit("__sm->__tasks = __tc;")
                self._emit("__sm->__count = __count;")
                self._emit("__task->strong_count = 1; __task->weak_count = 0;")
                self._emit("__task->state = MRYL_TASK_PENDING; __task->result = NULL;")
                self._emit(f"__task->move_next = {fn}; __task->on_cancel = NULL; __task->awaiter = NULL;")
                self._emit("__task->sm = __sm;")
                self._emit("__scheduler_post(__task);")
                self._emit("return __task;")
                self.indent_level -= 1
                self._emit("}")
                self._emit("")

            if "when_any" in combinators:
                sm  = f"__WhenAny_{T}_SM"
                fn  = f"__when_any_{T}_move_next"
                fac = f"__mryl_when_any_{T}"
                self._emit(f"typedef struct {{ MrylTask** __tasks; int __count; }} {sm};")
                self._emit(f"static void {fn}(MrylTask* __task) {{")
                self.indent_level += 1
                self._emit(f"{sm}* __sm = ({sm}*)__task->sm;")
                self._emit("for (int __i = 0; __i < __sm->__count; __i++) {")
                self.indent_level += 1
                self._emit("MrylTaskState __s = __sm->__tasks[__i]->state;")
                self._emit("if (__s == MRYL_TASK_COMPLETED || __s == MRYL_TASK_FAULTED || __s == MRYL_TASK_CANCELLED) {")
                self.indent_level += 1
                # 最初に終了したタスクの結果を返す（COMPLETED のみ値あり）
                self._emit(f"{C}* __res = ({C}*)malloc(sizeof({C}));")
                self._emit(f"*__res = (__s == MRYL_TASK_COMPLETED) ? *({C}*)__sm->__tasks[__i]->result : ({C}){{0}};")
                self._emit("for (int __j = 0; __j < __sm->__count; __j++) __task_release(__sm->__tasks[__j]);")
                self._emit("free(__sm->__tasks);")
                self._emit("__task->result = (void*)__res;")
                self._emit("__task->state = MRYL_TASK_COMPLETED;")
                self._emit("__task_release(__task);")
                self._emit("if (__task->awaiter) __scheduler_post(__task->awaiter);")
                self._emit("return;")
                self.indent_level -= 1
                self._emit("}")
                self.indent_level -= 1
                self._emit("}")
                self._emit("__scheduler_post(__task);")
                self.indent_level -= 1
                self._emit("}")
                self._emit(f"static MrylTask* {fac}(MrylTask** __src, int __count) {{")
                self.indent_level += 1
                self._emit(f"MrylTask* __task = (MrylTask*)malloc(sizeof(MrylTask));")
                self._emit(f"{sm}* __sm = ({sm}*)malloc(sizeof({sm}));")
                self._emit(f"memset(__sm, 0, sizeof({sm}));")
                self._emit("MrylTask** __tc = (MrylTask**)malloc(__count * sizeof(MrylTask*));")
                self._emit("for (int __i = 0; __i < __count; __i++) { __tc[__i] = __src[__i]; __task_retain(__tc[__i]); }")
                self._emit("__sm->__tasks = __tc;")
                self._emit("__sm->__count = __count;")
                self._emit("__task->strong_count = 1; __task->weak_count = 0;")
                self._emit("__task->state = MRYL_TASK_PENDING; __task->result = NULL;")
                self._emit(f"__task->move_next = {fn}; __task->on_cancel = NULL; __task->awaiter = NULL;")
                self._emit("__task->sm = __sm;")
                self._emit("__scheduler_post(__task);")
                self._emit("return __task;")
                self.indent_level -= 1
                self._emit("}")
                self._emit("")
