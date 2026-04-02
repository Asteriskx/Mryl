from Ast import *
import asyncio
try:
    import nest_asyncio
    nest_asyncio.apply()    # ネストした run_until_complete 許可
except ImportError:
    pass                    # nest_asyncio 未インストール時はフォールバック
import datetime
import os

# 数値型のセット（型推論に使用）
INTEGER_TYPES = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"}
FLOAT_TYPES = {"f32", "f64"}
NUMERIC_TYPES = INTEGER_TYPES | FLOAT_TYPES

class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value

class BreakSignal(Exception):
    pass

class ContinueSignal(Exception):
    pass

class CallFrame:
    """Represents a single stack frame in a Mryl runtime error trace."""
    def __init__(self, function: str, file: str = "<unknown>", line=None):
        self.function = function
        self.file = file
        self.line = line


class MrylRuntimeError(Exception):
    """Fatal Mryl runtime error with structured call stack info.

    Carries a snapshot of the call stack at the moment the error was raised,
    so it can be formatted even after the interpreter has unwound.
    """
    def __init__(self, message: str, error_type: str = "RuntimeError", call_stack=None):
        self.message = message
        self.error_type = error_type
        # Snapshot: copy so later stack changes don't affect this record
        self.stack: list = list(call_stack) if call_stack else []
        super().__init__(message)

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------
    def format_detail(self) -> str:
        """Return the full multi-line error report (write to log / stderr)."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        top = self.stack[-1] if self.stack else None
        func  = top.function if top else "<unknown>"
        file_ = top.file    if top else "<unknown>"
        line  = top.line    if top else "?"
        module = os.path.splitext(os.path.basename(file_))[0] if file_ != "<unknown>" else "<unknown>"

        lines = [
            f"[{now}] ERROR {self.error_type}: {self.message}",
            f"  module: {module}",
            f"  function: {func}",
            f"  file: {file_}",
            f"  line: {line if line is not None else '?'}",
            "",
            "Stacktrace:",
        ]
        for frame in reversed(self.stack):
            lines.append(f"  {frame.function}({frame.file}:{frame.line if frame.line is not None else '?'})")
        return "\n".join(lines)

    def format_brief(self) -> str:
        """One-line summary for the console."""
        return f"{self.error_type}: {self.message}"


class MatchError(Exception):
    """Raised when no match arm matches the scrutinee."""
    pass

class Interpreter:
    """Mryl language interpreter: executes AST and manages runtime state.
    
    Responsible for:
    - Statement execution (let, if, while, for, return, assignment)
    - Expression evaluation (literals, operators, function calls, methods)
    - Variable and struct management via scope stack
    - Generic function instantiation and type inference
    - Built-in function support (print, println, to_string)
    
    Runtime representation:
    - Variables: stored in scope stack (list of dicts)
    - Structures: represented as dicts with __struct_name__ key
    - Ranges: represented as dicts with __range__ key
    
    Notes:
    - Exception-based control flow for returns (ReturnSignal)
    - Supports C-style and Rust-style for loops
    - Implements generic type inference for polymorphic functions
    """
    def __init__(self):
        """Initialize interpreter with built-in functions and empty state."""
        self.functions = {}   # name -> FunctionDecl or ("builtin", func)
        self.structs = {}     # name -> StructDecl
        self.enums = {}       # name -> EnumDecl
        self.env = []         # list of dict (scope stack)
        self.const_table = {} # name -> {type, value}
        self.fix_vars = set() # fix 宣言された不変変数名のセット
        self.call_stack: list = []          # list of CallFrame (runtime call trace)
        self.source_file: str = "<unknown>" # current source file name (set from runner)

        # Built-in function definitions
        self.builtins = {
            "print": self.builtin_print,
            "println": self.builtin_println,
            "to_string": self.builtin_to_string,
            "read_line": self.builtin_read_line,
            "parse_int": self.builtin_parse_int,
            "parse_f64": self.builtin_parse_f64,
            "checked_div": self.builtin_checked_div,
        }

        # Register built-in functions
        for name, func in self.builtins.items():
            self.functions[name] = ("builtin", func)

        # Build dispatch tables for exec_stmt / eval_expr
        self._build_dispatch_tables()

    # ============================================================
    # プログラム実行
    # ============================================================
    def run(self, program: Program):
        """Execute Mryl program: load all structs and functions, then call main().
        
        Args:
            program (Program): AST of complete Mryl program
        
        Returns:
            Any: Return value of main() function
        
        Raises:
            RuntimeError: If main() function is not found
        
        Notes:
            - Built-in function declarations (body=None) are skipped
            - All user-defined functions and structs are registered
            - Entry point is always main() with no arguments
        """
        # Process const declarations
        env = [{}]  # Temporary scope for const evaluation
        for const_decl in program.consts:
            const_value = self.eval_expr(const_decl.init_expr, env)
            self.const_table[const_decl.name] = const_value

        # Register all structures
        for s in program.structs:
            self.structs[s.name] = s

        # Register all enums
        for e in program.enums:
            self.enums[e.name] = e

        # Register all functions (skip built-in declarations)
        for f in program.functions:
            # Skip built-in function declarations (body=None)
            if f.name in self.builtins and f.body is None:
                continue

            self.functions[f.name] = f

        if "main" not in self.functions:
            raise RuntimeError("main() function not found")

        return self.call_function("main", [], subst=None)

    # ============================================================
    # 関数呼び出し
    # ============================================================
    def call_function(self, name, args, subst=None):
        """Call a function by name with evaluated arguments.
        
        Args:
            name (str): Function name to call
            args (list): Evaluated argument values
            subst (dict, optional): Type substitution map for generics
        
        Returns:
            Any: Return value from function or None if no return
        
        Raises:
            RuntimeError: If function not found or body is None
        
        Notes:
            - Built-in functions bypass scope creation
            - Parameter binding is positional via zip
            - Generic type parameters added to environment
        """
        if name not in self.functions:
            # Ok/Err は内蔵関数
            if name == "Ok":
                return {'__result_tag__': 'ok', 'value': args[0] if args else None}
            if name == "Err":
                return {'__result_tag__': 'err', 'value': args[0] if args else None}
            if name == "Some":
                return {'__option_tag__': 'some', 'value': args[0] if args else None}
            if name == "Box":
                # Box::new(v) は EnumVariantExpr で処理されるが、
                # FunctionCall("Box", [v]) として来る場合も対応
                return {'__box__': True, 'value': args[0] if args else None}
            # cancel(token) — WeakTask の asyncio.Task をキャンセルする
            if name == "cancel":
                token = args[0] if args else None
                if isinstance(token, dict) and token.get('__weak_task__'):
                    task = token.get('task')
                    if task is not None:
                        task.cancel()
                return None
            raise RuntimeError(f"Undefined function: {name}")

        entry = self.functions[name]

        # Handle built-in functions
        if isinstance(entry, tuple) and entry[0] == "builtin":
            builtin_func = entry[1]
            return builtin_func(args)

        # Handle user-defined functions
        func = entry
        if not isinstance(func, FunctionDecl):
            raise RuntimeError(f"Invalid function entry for {name}")

        if func.body is None:
            raise RuntimeError(f"Function {name} has no body (body=None)")

        # Create new scope for function
        new_env = {}

        # Bind parameters to arguments
        for param, arg_value in zip(func.params, args):
            new_env[param.name] = arg_value

        # Add generic type substitutions to environment
        if subst:
            for tname, ttype in subst.items():
                new_env[tname] = ttype

        # Async function: run as asyncio coroutine and return a Future
        if getattr(func, 'is_async', False):
            async def _run_async_coro(captured_env=new_env, captured_func=func):
                self.env.append(captured_env)
                try:
                    self.eval_block(captured_func.body)
                except ReturnSignal as rs:
                    return rs.value
                finally:
                    if captured_env in self.env:
                        self.env.remove(captured_env)
                return None

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    raise RuntimeError("already running")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            task = loop.create_task(_run_async_coro())
            return {'__future__': True, 'task': task, 'loop': loop}

        # Push call frame (snapshot source location from FunctionDecl)
        frame = CallFrame(
            function=name,
            file=self.source_file,
            line=getattr(func, 'line', None),
        )
        self.call_stack.append(frame)

        # Push new scope and execute
        self.env.append(new_env)
        saved_fix_vars = self.fix_vars      # 呼び出し元の fix_vars を退避
        self.fix_vars = set()               # 関数スコープは新しいセット
        for param in func.params:           # fix 仮引数を登録
            if getattr(param, 'is_fix', False):
                self.fix_vars.add(param.name)

        try:
            _ = self.eval_block(func.body)
        except ReturnSignal as rs:
            return rs.value
        finally:
            # Always clean up scope and frame
            if self.env and self.env[-1] is new_env:
                self.env.pop()
            self.call_stack.pop()
            self.fix_vars = saved_fix_vars  # 呼び出し元の fix_vars を復元

        return None

    # ============================================================
    # Lambda 呼び出し
    # ============================================================
    def call_lambda(self, closure, args):
        """Call a lambda closure with evaluated arguments.

        Args:
            closure (dict): Lambda closure {'params', 'body', 'captured_env'}
            args (list): Evaluated argument values

        Returns:
            Any: Return value from lambda body
        """
        params = closure['params']
        body = closure['body']
        captured_env = [dict(scope) for scope in closure['captured_env']]
        is_async = closure.get('is_async', False)

        # Create a new scope for lambda params (on top of captured env)
        new_scope = {}
        for param, arg_value in zip(params, args):
            new_scope[param.name] = arg_value
        captured_env.append(new_scope)

        # Async lambda: run body as asyncio coroutine and return a Future
        if is_async:
            async def _run_async_lambda(env=captured_env, b=body):
                try:
                    self.exec_block(b, env)
                except ReturnSignal as rs:
                    return rs.value
                return None
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    raise RuntimeError("already running")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            task = loop.create_task(_run_async_lambda())
            return {'__future__': True, 'task': task, 'loop': loop}

        if isinstance(body, Block):
            saved_fix_vars = self.fix_vars  # lambda スコープ用に退避
            self.fix_vars = set()
            for param in params:            # fix 仮引数を登録
                if getattr(param, 'is_fix', False):
                    self.fix_vars.add(param.name)
            try:
                self.exec_block(body, captured_env)
            except ReturnSignal as rs:
                return rs.value
            finally:
                self.fix_vars = saved_fix_vars
            return None
        else:
            return self.eval_expr(body, captured_env)

    # ============================================================
    # スコープ操作
    # ============================================================
    def push_scope(self, env):
        """Create and push new empty scope onto scope stack.
        
        Args:
            env (list): Scope stack to push onto
        """
        env.append({})

    def pop_scope(self, env):
        """Remove and discard the innermost scope.
        
        Args:
            env (list): Scope stack to pop from
        """
        env.pop()

    def set_var(self, env, name, value):
        """Create variable in innermost scope (always defines new).
        
        Args:
            env (list): Scope stack
            name (str): Variable name
            value (Any): Value to bind
        
        Notes:
            - Always creates in innermost scope, shadows outer scopes
            - Used for local variable declarations
        """
        env[-1][name] = value

    def assign_var(self, env, name, value):
        """Assign to existing variable in any visible scope.
        
        Args:
            env (list): Scope stack
            name (str): Variable name to assign
            value (Any): New value
        
        Raises:
            RuntimeError: If variable not found in any scope
            RuntimeError: If variable is immutable (declared with fix)
        
        Notes:
            - Searches from innermost to outermost scope
            - Updates first matching variable (shadowing)
        """
        if name in self.fix_vars:
            raise RuntimeError(f"Cannot assign to immutable variable '{name}' (declared with 'fix')")
        for scope in reversed(env):
            if name in scope:
                scope[name] = value
                return
        raise RuntimeError(f"Undefined variable: {name}")

    def get_var(self, env, name):
        """Retrieve variable value from any visible scope.
        
        Args:
            env (list): Scope stack
            name (str): Variable name
        
        Returns:
            Any: Variable value
        
        Raises:
            RuntimeError: If variable not found
        
        Notes:
            - Searches from innermost to outermost
            - Returns first match (shadowing)
        """
        # Check local scopes first
        for scope in reversed(env):
            if name in scope:
                return scope[name]
        
        # Check const table
        if name in self.const_table:
            return self.const_table[name]

        # トップレベル関数を第一級値（コールバック）として参照する場合
        if name in self.functions:
            entry = self.functions[name]
            if not (isinstance(entry, tuple) and entry[0] == "builtin"):
                # FunctionDecl をラムダ互換 dict で包む
                func = entry
                return {
                    '__lambda__': True,
                    '__named_fn__': name,  # デバッグ用
                    'params': func.params,
                    'body': func.body,
                    'is_async': getattr(func, 'is_async', False),
                    'captured_env': [],  # トップレベルなのでキャプチャなし
                }

        raise RuntimeError(f"Undefined variable: {name}")

    # ============================================================
    # 文の実行
    # ============================================================
    def _build_dispatch_tables(self):
        """exec_stmt / eval_expr 用の dispatch table を構築する。"""
        self._stmt_dispatch = {
            LetDecl:          self._exec_let_decl,
            FixDecl:          self._exec_fix_decl,
            Assignment:       self.exec_assignment,
            IfStmt:           self._exec_if_stmt,
            WhileStmt:        self._exec_while_stmt,
            ForStmt:          self.exec_for,
            ReturnStmt:       self._exec_return_stmt,
            BreakStmt:        self._exec_break_stmt,
            ContinueStmt:     self._exec_continue_stmt,
            ExprStmt:         self._exec_expr_stmt,
            Block:            self._exec_block_stmt,
            ConditionalBlock: self.exec_conditional_block,
        }
        self._expr_dispatch = {
            NumberLiteral:   self._eval_number_literal,
            FloatLiteral:    self._eval_float_literal,
            StringLiteral:   self._eval_string_literal,
            BoolLiteral:     self._eval_bool_literal,
            VarRef:          self._eval_varref,
            UnaryOp:         self._eval_unary_op,
            BinaryOp:        self._eval_binary_op,
            ArrayAccess:     self._eval_array_access,
            StructAccess:    self._eval_struct_access,
            FunctionCall:    self._eval_function_call,
            StructInit:      self.eval_struct_init,
            ArrayLiteral:    self._eval_array_literal,
            MethodCall:      self.eval_method_call,
            Range:           self._eval_range,
            Lambda:          self._eval_lambda,
            AwaitExpr:       self._eval_await_expr,
            WeakExpr:        self._eval_weak_expr,
            EnumVariantExpr: self._eval_enum_variant_expr,
            MatchExpr:       self._eval_match_expr,
            BlockExpr:       self._eval_block_expr,
        }

    def exec_block(self, block: Block, env):
        """Execute block of statements with new scope.
        
        Args:
            block (Block): Block AST node containing statements
            env (list): Current scope stack
        
        Notes:
            - Creates new scope at entry, removes at exit (guaranteed)
            - Uses try/finally to ensure scope cleanup
        """
        self.push_scope(env)
        try:
            for stmt in block.statements:
                self.exec_stmt(stmt, env)
        finally:
            self.pop_scope(env)

    def exec_stmt(self, stmt, env):
        """Execute a single statement via dispatch table."""
        handler = self._stmt_dispatch.get(type(stmt))
        if handler is None:
            raise RuntimeError(f"Unknown statement: {stmt}")
        handler(stmt, env)

    # --- exec_stmt ハンドラ群 ---

    def _exec_let_decl(self, stmt: LetDecl, env):
        value = self.eval_expr(stmt.init_expr, env) if stmt.init_expr else None
        self.set_var(env, stmt.name, value)

    def _exec_fix_decl(self, stmt: FixDecl, env):
        value = self.eval_expr(stmt.init_expr, env)
        self.set_var(env, stmt.name, value)
        self.fix_vars.add(stmt.name)

    def _exec_if_stmt(self, stmt: IfStmt, env):
        cond = self.eval_expr(stmt.condition, env)
        if cond:
            self.exec_block(stmt.then_block, env)
        elif stmt.else_block:
            if isinstance(stmt.else_block, IfStmt):
                self.exec_stmt(stmt.else_block, env)
            else:
                self.exec_block(stmt.else_block, env)

    def _exec_while_stmt(self, stmt: WhileStmt, env):
        while self.eval_expr(stmt.condition, env):
            try:
                self.exec_block(stmt.body, env)
            except BreakSignal:
                break
            except ContinueSignal:
                continue

    def _exec_return_stmt(self, stmt: ReturnStmt, env):
        raise ReturnSignal(self.eval_expr(stmt.expr, env))

    def _exec_break_stmt(self, stmt: BreakStmt, env):
        raise BreakSignal()

    def _exec_continue_stmt(self, stmt: ContinueStmt, env):
        raise ContinueSignal()

    def _exec_expr_stmt(self, stmt: ExprStmt, env):
        self.eval_expr(stmt.expr, env)

    def _exec_block_stmt(self, stmt: Block, env):
        self.exec_block(stmt, env)


    def exec_conditional_block(self, stmt: ConditionalBlock, env):
        """Execute conditional compilation block"""
        # Evaluate condition
        condition_value = False
        
        if isinstance(stmt.condition_expr, str):
            # Simple const name: #ifdef CONST_NAME
            if stmt.condition_expr in self.const_table:
                condition_value = bool(self.const_table[stmt.condition_expr])
        elif isinstance(stmt.condition_expr, tuple) and stmt.condition_expr[0] == 'not':
            # #ifndef: negated condition
            const_name = stmt.condition_expr[1]
            if const_name not in self.const_table:
                condition_value = True
            else:
                condition_value = not bool(self.const_table[const_name])
        else:
            # Expression: #if EXPR
            condition_value = bool(self.eval_expr(stmt.condition_expr, env))
        
        # Execute appropriate block
        if condition_value:
            self.exec_block(stmt.then_block, env)
        elif stmt.else_block:
            self.exec_block(stmt.else_block, env)

    def exec_for(self, stmt: ForStmt, env):
        """Execute for loop (both Rust-style and C-style).
        
        Args:
            stmt (ForStmt): For loop statement (is_c_style flag determines type)
            env (list): Scope stack
        
        Processing:
            C-style: for (let i = 0; i < 10; i++)
                1. Execute initialization in outer scope
                2. Create new scope with loop variable
                3. Evaluate condition, execute body, evaluate update
            
            Rust-style: for x in iterable
                1. Evaluate iterable expression
                2. Create new scope
                3. Iterate over range OR array elements
        
        Supported iterables:
            - Range (dict with __range__ key): exclusive or inclusive
            - List: element-by-element iteration
        
        Raises:
            RuntimeError: If iterable type not supported
        
        Notes:
            - Loop scope includes only the loop variable
            - Updates can be assignments or expressions (++/--)
        """
        if stmt.is_c_style:
            # C-style: for (let i = 0; i < 10; i++)
            # Create new scope for loop variable
            loop_env = env + [{}]
            
            # Execute init: let i = 0
            init_value = self.eval_expr(stmt.iterable, env)  # init_expr stored in iterable
            self.set_var(loop_env, stmt.variable, init_value)
            
            # Loop: condition -> body -> update
            while self.eval_expr(stmt.condition, loop_env):
                try:
                    self.exec_block(stmt.body, loop_env)
                except BreakSignal:
                    break
                except ContinueSignal:
                    pass  # continue でも update は実行する
                # Handle update (could be assignment or ++/--)
                if isinstance(stmt.update, Assignment):
                    self.exec_assignment(stmt.update, loop_env)
                else:
                    self.eval_expr(stmt.update, loop_env)
        else:
            # Rust-style: for x in iterable
            iterable_val = self.eval_expr(stmt.iterable, env)
            
            # Create new scope for loop variable
            loop_env = env + [{}]
            
            # Determine what to iterate over
            if isinstance(iterable_val, dict) and iterable_val.get("__range__"):
                # Range type: iterate from start to end (exclusive or inclusive)
                start = iterable_val["start"]
                end = iterable_val["end"]
                if iterable_val.get("inclusive"):
                    for i in range(start, end + 1):
                        self.set_var(loop_env, stmt.variable, i)
                        try:
                            self.exec_block(stmt.body, loop_env)
                        except BreakSignal:
                            return
                        except ContinueSignal:
                            continue
                else:
                    # Exclusive upper bound (default)
                    for i in range(start, end):
                        self.set_var(loop_env, stmt.variable, i)
                        try:
                            self.exec_block(stmt.body, loop_env)
                        except BreakSignal:
                            return
                        except ContinueSignal:
                            continue
            elif isinstance(iterable_val, list):
                # Array: iterate over elements
                for element in iterable_val:
                    self.set_var(loop_env, stmt.variable, element)
                    try:
                        self.exec_block(stmt.body, loop_env)
                    except BreakSignal:
                        return
                    except ContinueSignal:
                        continue
            else:
                raise RuntimeError(f"Cannot iterate over {type(iterable_val)}")

    def exec_assignment(self, stmt: Assignment, env):
        """Execute assignment to variable, array element, or struct field.
        
        Args:
            stmt (Assignment): Assignment statement with target and value
            env (list): Scope stack
        
        Processing:
            Variable assignment: name = expr
                1. Evaluate right-hand side
                2. Assign value to variable in scope
            
            Array element assignment: name[index] = expr
                1. Evaluate index and value
                2. Set array element by index
            
            Struct field assignment: obj.field = expr
                1. Evaluate field value
                2. Set field in struct dict
        
        Returns:
            None
        
        Raises:
            NameError: If variable not found in scope
            TypeError: If assignment target type mismatch (if type checking enabled)
            IndexError: If array index out of bounds
        
        Notes:
            - Type checker is notified of assignments for type inference
            - Struct fields created dynamically if not present
        """
        target = stmt.target

        # x = expr
        if isinstance(target, VarRef):
            value = self.eval_expr(stmt.expr, env)
            self.assign_var(env, target.name, value)
            return

        # arr[i] = expr
        if isinstance(target, ArrayAccess):
            arr = self.eval_expr(target.array, env)
            index = self.eval_expr(target.index, env)
            value = self.eval_expr(stmt.expr, env)
            arr[index] = value
            return

        # obj.field = expr
        if isinstance(target, StructAccess):
            obj = self.eval_expr(target.obj, env)
            value = self.eval_expr(stmt.expr, env)
            obj[target.field] = value
            return

        raise RuntimeError(f"Invalid assignment target: {target}")

    # ============================================================
    # Expression Evaluation
    # ============================================================
    def eval_expr(self, expr, env):
        """Evaluate expression to its runtime value via dispatch table."""
        handler = self._expr_dispatch.get(type(expr))
        if handler is None:
            raise RuntimeError(f"Unknown expression: {expr}")
        return handler(expr, env)

    # --- eval_expr ハンドラ群 ---

    def _eval_number_literal(self, expr: NumberLiteral, env):
        return expr.value

    def _eval_float_literal(self, expr: FloatLiteral, env):
        return expr.value

    def _eval_string_literal(self, expr: StringLiteral, env):
        return expr.value

    def _eval_bool_literal(self, expr: BoolLiteral, env):
        return expr.value

    def _eval_varref(self, expr: VarRef, env):
        if expr.name == "None":
            return {'__option_tag__': 'none'}
        return self.get_var(env, expr.name)

    def _eval_binary_op(self, expr: BinaryOp, env):
        if expr.op == "&&":
            left = self.eval_expr(expr.left, env)
            if not self.is_truthy(left):
                return False
            return self.is_truthy(self.eval_expr(expr.right, env))
        if expr.op == "||":
            left = self.eval_expr(expr.left, env)
            if self.is_truthy(left):
                return True
            return self.is_truthy(self.eval_expr(expr.right, env))
        left  = self.eval_expr(expr.left, env)
        right = self.eval_expr(expr.right, env)
        return self.eval_binary(expr.op, left, right)

    def _eval_array_access(self, expr: ArrayAccess, env):
        arr   = self.eval_expr(expr.array, env)
        index = self.eval_expr(expr.index, env)
        return arr[index]

    def _eval_struct_access(self, expr: StructAccess, env):
        obj = self.eval_expr(expr.obj, env)
        return obj[expr.field]

    def _eval_function_call(self, expr: FunctionCall, env):
        try:
            maybe_lambda = self.get_var(env, expr.name)
            if isinstance(maybe_lambda, dict) and maybe_lambda.get('__lambda__'):
                args = [self.eval_expr(a, env) for a in expr.args]
                return self.call_lambda(maybe_lambda, args)
            if callable(maybe_lambda):
                args = [self.eval_expr(a, env) for a in expr.args]
                return maybe_lambda(*args)
        except RuntimeError:
            pass
        subst = self.infer_call_subst(expr, env)
        args  = [self.eval_expr(a, env) for a in expr.args]
        return self.call_function(expr.name, args, subst)

    def _eval_array_literal(self, expr: ArrayLiteral, env):
        return [self.eval_expr(e, env) for e in expr.elements]

    def _eval_range(self, expr: Range, env):
        start = self.eval_expr(expr.start, env)
        end   = self.eval_expr(expr.end, env)
        return {"__range__": True, "start": start, "end": end, "inclusive": expr.inclusive}

    def _eval_lambda(self, expr: Lambda, env):
        captured_env = [dict(scope) for scope in env]
        return {
            '__lambda__': True,
            'params': expr.params,
            'body': expr.body,
            'is_async': getattr(expr, 'is_async', False),
            'captured_env': captured_env,
        }

    def _eval_weak_expr(self, expr: WeakExpr, env):
        """weak(handle) — Future の asyncio.Task を弱参照として包んで返す。"""
        future = self.eval_expr(expr.expr, env)
        if isinstance(future, dict) and future.get('__future__'):
            return {'__weak_task__': True, 'task': future.get('task'), 'loop': future.get('loop')}
        raise RuntimeError("weak(): expression is not a Future")

    def _eval_await_expr(self, expr: AwaitExpr, env):
        future = self.eval_expr(expr.expr, env)
        if isinstance(future, dict) and future.get('__future__'):
            loop = future.get('loop')
            if loop is None:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        raise RuntimeError("already running")
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            return loop.run_until_complete(future['task'])
        raise RuntimeError("await: expression is not a Future")

    def _eval_enum_variant_expr(self, expr: EnumVariantExpr, env):
        # Task::when_all / Task::when_any — ユーザー定義 struct Task がない場合のみ
        if expr.enum_name == "Task" and expr.variant_name in ("when_all", "when_any") \
                and "Task" not in self.structs:
            arr = self.eval_expr(expr.args[0], env)  # list of futures
            futures = arr if isinstance(arr, list) else list(arr)

            # 子タスクと同一 loop を使用する（loop が混在しないよう先頭 future から取得）
            loop = futures[0]['loop'] if futures and futures[0].get('loop') else None
            if loop is None:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        raise RuntimeError("already running")
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

            if expr.variant_name == "when_all":
                async def _when_all_coro(fs=futures):
                    tasks = [f['task'] for f in fs]
                    results = await asyncio.gather(*tasks)
                    return list(results)
                return {'__future__': True, 'task': loop.create_task(_when_all_coro()), 'loop': loop}
            else:
                async def _when_any_coro(fs=futures):
                    tasks = [f['task'] for f in fs]
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for t in pending:
                        t.cancel()
                    return next(iter(done)).result()
                return {'__future__': True, 'task': loop.create_task(_when_any_coro()), 'loop': loop}

        # Box::new(v) — ヒープアロケーション相当（ユーザー定義 struct Box がない場合のみ）
        if expr.enum_name == "Box" and expr.variant_name == "new" \
                and "Box" not in self.structs:
            val = self.eval_expr(expr.args[0], env) if expr.args else None
            return {'__box__': True, 'value': val}

        struct = self.structs.get(expr.enum_name)
        if struct:
            method = next(
                (m for m in struct.methods if m.name == expr.variant_name and getattr(m, 'is_static', False)),
                None
            )
            if method:
                if expr.has_parens:
                    args_eval = [self.eval_expr(a, env) for a in expr.args]
                    new_env = {}
                    for param, val in zip(method.params, args_eval):
                        new_env[param.name] = val
                    self.env.append(new_env)
                    try:
                        for stmt in method.body.statements:
                            self.exec_stmt(stmt, self.env)
                    except ReturnSignal as ret:
                        return ret.value
                    finally:
                        self.env.pop()
                    return None
                else:
                    def _make_static_ref(m, interp):
                        def _call(*args_eval):
                            new_env = {}
                            for param, val in zip(m.params, args_eval):
                                new_env[param.name] = val
                            interp.env.append(new_env)
                            try:
                                for stmt in m.body.statements:
                                    interp.exec_stmt(stmt, interp.env)
                            except ReturnSignal as ret:
                                return ret.value
                            finally:
                                interp.env.pop()
                            return None
                        return _call
                    return _make_static_ref(method, self)
        data = [self.eval_expr(a, env) for a in expr.args]
        return {'__enum__': expr.enum_name, '__variant__': expr.variant_name, '__data__': data}

    def _eval_match_expr(self, expr: MatchExpr, env):
        val = self.eval_expr(expr.scrutinee, env)
        for arm in expr.arms:
            bound, matched = self._match_pattern(arm.pattern, val)
            if matched:
                arm_env = env + [bound]
                return self.eval_expr(arm.body, arm_env)
        raise MrylRuntimeError(
            f"no arm matched value: {val!r}",
            error_type="MatchError",
            call_stack=self.call_stack,
        )

    def _eval_block_expr(self, expr: BlockExpr, env):
        block_env = env + [{}]
        for stmt in expr.stmts:
            self.exec_stmt(stmt, block_env)
        if expr.result_expr is not None:
            return self.eval_expr(expr.result_expr, block_env)
        return None

    def _eval_unary_op(self, expr, env):
        """単項演算子を評価する。eval_expr から委譲される。"""
        if expr.op == "++":
            if isinstance(expr.operand, VarRef):
                var_name = expr.operand.name
                new_val = self.get_var(env, var_name) + 1
                self.assign_var(env, var_name, new_val)
                return new_val
            raise RuntimeError("++ can only be applied to variables")

        if expr.op == "--":
            if isinstance(expr.operand, VarRef):
                var_name = expr.operand.name
                new_val = self.get_var(env, var_name) - 1
                self.assign_var(env, var_name, new_val)
                return new_val
            raise RuntimeError("-- can only be applied to variables")

        if expr.op == "post++":
            if isinstance(expr.operand, VarRef):
                var_name = expr.operand.name
                old = self.get_var(env, var_name)
                self.assign_var(env, var_name, old + 1)
                return old
            raise RuntimeError("++ can only be applied to variables")

        if expr.op == "post--":
            if isinstance(expr.operand, VarRef):
                var_name = expr.operand.name
                old = self.get_var(env, var_name)
                self.assign_var(env, var_name, old - 1)
                return old
            raise RuntimeError("-- can only be applied to variables")

        v = self.eval_expr(expr.operand, env)
        if expr.op == "+":  return +v
        if expr.op == "-":  return -v
        if expr.op == "!":  return not self.is_truthy(v)
        if expr.op == "~":  return ~int(v)
        if expr.op == "deref":
            if isinstance(v, dict) and v.get('__box__'):
                return v['value']
            raise RuntimeError(f"Deref (*) requires a Box value, got: {v!r}")
        raise RuntimeError(f"Unknown unary operator: {expr.op}")

    def _match_pattern(self, pattern, val):
        """Try to match pattern against val. Returns (bindings_dict, matched_bool)."""
        import re
        if isinstance(pattern, LiteralPattern):
            return {}, (val == pattern.value)
        if isinstance(pattern, BindingPattern):
            if pattern.name == "_":
                return {}, True
            return {pattern.name: val}, True
        if isinstance(pattern, EnumPattern):
            # Result型 Ok(v) / Err(e) パターン
            if pattern.enum_name in ('Ok', 'Err') and pattern.variant_name in ('Ok', 'Err'):
                tag = 'ok' if pattern.enum_name == 'Ok' else 'err'
                if not (isinstance(val, dict) and val.get('__result_tag__') == tag):
                    return {}, False
                bindings = {}
                if pattern.bindings:
                    bindings[pattern.bindings[0]] = val.get('value')
                return bindings, True
            # Option型 Some(v) / None パターン
            if pattern.enum_name == 'Some' and pattern.variant_name == 'Some':
                if not (isinstance(val, dict) and val.get('__option_tag__') == 'some'):
                    return {}, False
                bindings = {}
                if pattern.bindings:
                    bindings[pattern.bindings[0]] = val.get('value')
                return bindings, True
            if pattern.enum_name == 'None' and pattern.variant_name == 'None':
                if not (isinstance(val, dict) and val.get('__option_tag__') == 'none'):
                    return {}, False
                return {}, True
            # 通常の enum パターン
            if not (isinstance(val, dict)
                    and val.get('__enum__') == pattern.enum_name
                    and val.get('__variant__') == pattern.variant_name):
                return {}, False
            bindings = {}
            for i, name in enumerate(pattern.bindings):
                data = val.get('__data__', [])
                bindings[name] = data[i] if i < len(data) else None
            return bindings, True
        if isinstance(pattern, StructPattern):
            if not isinstance(val, dict):
                return {}, False
            bindings = {f: val[f] for f in pattern.fields if f in val}
            return bindings, len(bindings) == len(pattern.fields)
        if isinstance(pattern, RegexPattern):
            matched = bool(re.fullmatch(pattern.pattern_str, str(val)))
            return {}, matched
        return {}, False

    # ============================================================
    # Binary Operations
    # ============================================================
    def eval_binary(self, op, left, right):
        """Evaluate binary operation on two operands.
        
        Args:
            op (str): Operator symbol (+, -, *, /, %, ==, !=, <, <=, >, >=, &&, ||, &, |, ^, <<, >>)
            left: Left operand value
            right: Right operand value
        
        Supported operations:
            Arithmetic: +, -, *, /, %
            Comparison: ==, !=, <, <=, >, >=
            Logical: && (short-circuit), || (short-circuit)
            Bitwise: & (and), | (or), ^ (xor), << (left shift), >> (right shift)
        
        Returns:
            Result of operation (numeric, boolean, or string)
        
        Raises:
            RuntimeError: If operator unknown or type mismatch
            ZeroDivisionError: If division by zero
        
        Notes:
            - Division (/) is integer division (// in Python)
            - String concatenation via + operator supported
            - Type coercion follows Python semantics
            - Logical operators handled with short-circuit evaluation in eval_expr
            - Bitwise operators work on integer operands
        """
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                from MrylError import RuntimeError_ as MrylRuntimeError
                raise MrylRuntimeError("division by zero")
            if isinstance(left, float) or isinstance(right, float):
                return left / right
            return left // right  # Integer division
        if op == "%":
            if right == 0:
                from MrylError import RuntimeError_ as MrylRuntimeError
                raise MrylRuntimeError("division by zero")
            return left % right

        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right

        # Bitwise operators
        if op == "&":
            return int(left) & int(right)
        if op == "|":
            return int(left) | int(right)
        if op == "^":
            return int(left) ^ int(right)
        if op == "<<":
            return int(left) << int(right)
        if op == ">>":
            return int(left) >> int(right)

        raise RuntimeError(f"Unknown binary operator: {op}")

    def is_truthy(self, value):
        """Determine if value is truthy in conditional context.
        
        Args:
            value: Value to evaluate for truthiness
        
        Returns:
            bool: True if value is considered truthy, False otherwise
        
        Truthiness rules:
            - False, 0, empty string (""), None: falsy
            - True, non-zero numbers, non-empty strings: truthy
        """
        if value is False or value is None:
            return False
        if value == 0 or value == "":
            return False
        return True

    # ============================================================
    # Struct
    # ============================================================
    def eval_struct_init(self, expr: StructInit, env):
        """Initialize struct instance with field values.
        
        Args:
            expr (StructInit): Struct initialization expression with name and fields
            env (list): Scope stack for field expression evaluation
        
        Processing:
            1. Look up struct definition by name
            2. Create dict with __struct_name__ key
            3. Store type_args if generic struct
            4. Evaluate each provided field expression
            5. Fill missing fields with None (default value)
        
        Returns:
            dict: Struct instance with __struct_name__, optional __type_args__, and fields
        
        Raises:
            RuntimeError: If struct type not defined
        
        Notes:
            - Generic structs store type arguments in __type_args__ for runtime dispatch
            - Fields not provided in constructor initialized to None
            - Struct instance is mutable (fields can be reassigned)
        """
        struct = self.structs.get(expr.struct_name)
        if not struct:
            raise RuntimeError(f"Undefined struct: {expr.struct_name}")

        obj = {"__struct_name__": expr.struct_name}

        # Store type_args if generic struct
        if expr.type_args:
            obj["__type_args__"] = expr.type_args

        for name, value_expr in expr.fields:
            obj[name] = self.eval_expr(value_expr, env)

        # Fill missing fields with None
        for field in struct.fields:
            if field.name not in obj:
                obj[field.name] = None

        return obj

    # ============================================================
    # Method Call
    # ============================================================
    def eval_method_call(self, expr: MethodCall, env):
        """メソッド呼び出しをオブジェクト種別に応じてディスパッチする。"""
        obj = self.eval_expr(expr.obj, env)
        args_eval = [self.eval_expr(a, env) for a in expr.args]

        if isinstance(obj, list):
            return self._eval_array_method(obj, expr.method, args_eval)

        if isinstance(obj, str):
            return self._eval_string_method(obj, expr.method, args_eval)

        if isinstance(obj, dict) and '__result_tag__' in obj:
            return self._eval_result_method(obj, expr.method, args_eval)

        if isinstance(obj, dict) and '__box__' in obj:
            if expr.method == 'unbox':
                return obj['value']
            raise RuntimeError(f"Unknown Box method: {expr.method}")

        if isinstance(obj, dict) and '__struct_name__' in obj:
            return self._eval_struct_method(obj, expr.method, args_eval)

        raise RuntimeError(f"Cannot call method on non-struct value")

    def _eval_array_method(self, obj: list, method: str, args_eval: list):
        """動的配列（Python list）のメソッドを処理する。"""
        if method == 'push':
            obj.append(args_eval[0])
            return None
        if method == 'pop':
            if not obj:
                raise MrylRuntimeError("pop() called on empty array", "IndexError", self.call_stack)
            return obj.pop()
        if method == 'len':
            return len(obj)
        if method == 'is_empty':
            return len(obj) == 0
        if method == 'remove':
            idx = int(args_eval[0])
            if idx < 0 or idx >= len(obj):
                raise MrylRuntimeError(f"remove() index {idx} out of bounds", "IndexError", self.call_stack)
            return obj.pop(idx)
        if method == 'insert':
            obj.insert(int(args_eval[0]), args_eval[1])
            return None

        # ── Iter<T> / LINQ スタイル操作 ──────────────────────────
        def _call(fn_val, *a):
            if isinstance(fn_val, dict) and 'params' in fn_val:
                return self.call_lambda(fn_val, list(a))
            if callable(fn_val):
                return fn_val(*a)
            raise RuntimeError(f"Not callable: {fn_val!r}")

        if method == 'select':
            return [_call(args_eval[0], x) for x in obj]
        if method == 'filter':
            return [x for x in obj if _call(args_eval[0], x)]
        if method == 'take':
            n = int(args_eval[0])
            return obj[:n]
        if method == 'skip':
            n = int(args_eval[0])
            return obj[n:]
        if method == 'select_many':
            return [y for x in obj for y in _call(args_eval[0], x)]
        if method == 'to_array':
            return list(obj)
        if method == 'for_each':
            for x in obj:
                _call(args_eval[0], x)
            return None
        if method == 'count':
            return len(obj)
        if method == 'first':
            if not obj:
                return {'__result_tag__': 'err', 'value': 'empty sequence'}
            return {'__result_tag__': 'ok', 'value': obj[0]}
        if method == 'any':
            return any(_call(args_eval[0], x) for x in obj)
        if method == 'all':
            return all(_call(args_eval[0], x) for x in obj)
        if method == 'aggregate':
            import functools
            if len(args_eval) == 1:
                # 初期値なし: fn(T, T) -> T
                if not obj:
                    return {'__result_tag__': 'err', 'value': 'empty sequence'}
                try:
                    result = functools.reduce(lambda a, b: _call(args_eval[0], a, b), obj)
                    return {'__result_tag__': 'ok', 'value': result}
                except Exception as e:
                    return {'__result_tag__': 'err', 'value': str(e)}
            else:
                # 初期値あり: aggregate(init, fn(U, T) -> U)
                init = args_eval[0]
                fn   = args_eval[1]
                return functools.reduce(lambda a, b: _call(fn, a, b), obj, init)

        raise RuntimeError(f"Unknown array method: {method}")

    def _eval_string_method(self, obj: str, method: str, args_eval: list):
        """string 型の組み込みメソッドを処理する。"""
        if method == 'len':
            return len(obj)
        if method == 'contains':
            return args_eval[0] in obj
        if method == 'starts_with':
            return obj.startswith(args_eval[0])
        if method == 'ends_with':
            return obj.endswith(args_eval[0])
        if method == 'trim':
            return obj.strip()
        if method == 'to_upper':
            return obj.upper()
        if method == 'to_lower':
            return obj.lower()
        if method == 'replace':
            return obj.replace(args_eval[0], args_eval[1])
        if method == 'find':
            idx = obj.find(args_eval[0])
            if idx == -1:
                return {'__option_tag__': 'none'}
            return {'__option_tag__': 'some', 'value': idx}
        if method == 'split':
            delim = args_eval[0]
            if delim == '':
                return list(obj)
            return obj.split(delim)
        raise RuntimeError(f"Unknown string method: {method}")

    def _eval_result_method(self, obj: dict, method: str, args_eval: list):
        """Result 型（Ok/Err）のメソッドを処理する。"""
        is_ok = obj['__result_tag__'] == 'ok'
        if method == 'is_ok':    return is_ok
        if method == 'is_err':   return not is_ok
        if method in ('try', 'err'):
            if is_ok: return obj['value']
            raise MrylRuntimeError(f"Err({obj['value']!r})", error_type="Error", call_stack=self.call_stack)
        if method == 'unwrap':
            if is_ok: return obj['value']
            raise MrylRuntimeError(f"unwrap() called on Err value: {obj['value']!r}", error_type="UnwrapError", call_stack=self.call_stack)
        if method == 'unwrap_err':
            if not is_ok: return obj['value']
            raise MrylRuntimeError(f"unwrap_err() called on Ok value: {obj['value']!r}", error_type="UnwrapError", call_stack=self.call_stack)
        if method == 'unwrap_or':
            return obj['value'] if is_ok else (args_eval[0] if args_eval else None)
        raise RuntimeError(f"Unknown Result method: {method}")

    def _eval_struct_method(self, obj: dict, method_name: str, args_eval: list):
        """ユーザー定義 struct のメソッドを実行する。"""
        struct_name = obj['__struct_name__']
        struct = self.structs.get(struct_name)
        if not struct:
            raise RuntimeError(f"Undefined struct: {struct_name}")

        method = next((m for m in struct.methods if m.name == method_name), None)
        if not method:
            raise RuntimeError(f"Struct {struct_name} has no method {method_name}")

        new_env = {method.params[0].name: obj}
        for param, val in zip(method.params[1:], args_eval):
            new_env[param.name] = val

        self.env.append(new_env)
        try:
            for stmt in method.body.statements:
                self.exec_stmt(stmt, self.env)
        except ReturnSignal as ret:
            return ret.value
        finally:
            self.env.pop()
        return None

    # ============================================================
    # Function Block Evaluation (for call_function)
    # ============================================================
    def eval_block(self, block: Block):
        """Execute function/method body block with scope management.
        
        Args:
            block (Block): Block of statements to execute
        
        Processing:
            1. Push new scope (empty environment dict)
            2. Execute all statements in block
            3. Pop scope (cleanup on exception via finally)
        
        Returns:
            None (statement execution only, no return value)
        
        Notes:
            - Used by call_function to evaluate function bodies
            - Return values handled by ReturnSignal exception
            - New scope isolates local variables from caller
        """
        # Create new scope for function/method
        self.env.append({})
        try:
            for stmt in block.statements:
                # ステートメントの行番号でコールフレームを更新
                if self.call_stack and getattr(stmt, 'line', None) is not None:
                    self.call_stack[-1].line = stmt.line
                self.exec_stmt(stmt, self.env)
        finally:
            self.env.pop()

    # ============================================================
    # Built-in Functions
    # ============================================================
    def builtin_print(self, args):
        """Print formatted string without newline.
        
        Args:
            args (list): List of values to print
        
        Processing:
            1. Format arguments using format_string()
            2. Print result without trailing newline
        
        Returns:
            None
        
        Notes:
            - Output goes directly to stdout (unbuffered)
            - No trailing newline (unlike println)
        """
        result = self.format_string(args)
        print(result, end="")
        return None

    def builtin_println(self, args):
        """Print formatted string with newline.
        
        Args:
            args (list): List of values to print
        
        Processing:
            1. Format arguments using format_string()
            2. Print result with trailing newline
        
        Returns:
            None
        
        Notes:
            - Output goes directly to stdout
            - Automatically adds newline at end
        """
        result = self.format_string(args)
        print(result)
        return None

    def builtin_to_string(self, args):
        """Convert value to string representation.
        
        Args:
            args (list): Must have at least 1 element (value to convert)
        
        Processing:
            1. If first arg is format string (contains "{}"), apply format_string()
            2. Otherwise, simple Python str() conversion
        
        Returns:
            str: String representation of value
        
        Raises:
            RuntimeError: If args is empty
        
        Notes:
            - Supports format string syntax: "Value: {}" with multiple arguments
            - Falls back to standard Python str() for simple conversion
        """
        if len(args) < 1:
            raise RuntimeError("to_string expects at least 1 argument")
        
        # If first arg is format string with placeholders, apply formatting
        if isinstance(args[0], str) and "{}" in args[0]:
            return self.format_string(args)
        
        # Simple string conversion
        if isinstance(args[0], bool):
            return "true" if args[0] else "false"
        return str(args[0])

    def builtin_read_line(self, args):
        """Read one line from stdin, returning it with leading/trailing whitespace stripped."""
        return input()

    def builtin_parse_int(self, args):
        """Parse a string to Result<i32, string>. Returns Ok(v) or Err(msg)."""
        if len(args) < 1:
            raise RuntimeError("parse_int expects 1 argument")
        s = str(args[0]).strip()
        try:
            return {'__result_tag__': 'ok', 'value': int(s)}
        except ValueError:
            return {'__result_tag__': 'err', 'value': f"cannot parse '{s}' as i32"}

    def builtin_parse_f64(self, args):
        """Parse a string to Result<f64, string>. Returns Ok(v) or Err(msg)."""
        if len(args) < 1:
            raise RuntimeError("parse_f64 expects 1 argument")
        s = str(args[0]).strip()
        try:
            return {'__result_tag__': 'ok', 'value': float(s)}
        except ValueError:
            return {'__result_tag__': 'err', 'value': f"cannot parse '{s}' as f64"}

    def builtin_checked_div(self, args):
        """Safe division: returns Ok(result) or Err("division by zero").
        checked_div(a, b) -> Result<i32, string>
        """
        if len(args) < 2:
            raise RuntimeError("checked_div expects 2 arguments")
        a, b = args[0], args[1]
        if b == 0:
            return {'__result_tag__': 'err', 'value': 'division by zero'}
        if isinstance(a, float) or isinstance(b, float):
            return {'__result_tag__': 'ok', 'value': a / b}
        return {'__result_tag__': 'ok', 'value': a // b}

    def format_string(self, args):
        """Format string with placeholder substitution.
        
        Args:
            args (list): [format_str, arg1, arg2, ...] where format_str contains {}
        
        Processing:
            1. First arg is format string with {} placeholders
            2. Remaining args substitute into placeholders left-to-right
            3. Handle escape sequences: \\n, \\t, etc.
        
        Returns:
            str: Formatted string with placeholders replaced by values
        
        Raises:
            IndexError: If not enough arguments for placeholders
        
        Notes:
            - Each {} is replaced by next argument in order
            - All values converted to string via str()
            - Escape sequences processed in final string
        """
        if len(args) == 0:
            return ""
        
        if not isinstance(args[0], str):
            # If no format string, concatenate all arguments
            def _val_to_str(v):
                if isinstance(v, bool):
                    return "true" if v else "false"
                elif isinstance(v, float):
                    return f"{v:g}"
                return str(v)
            return "".join(_val_to_str(a) for a in args)
        
        format_str = args[0]
        rest_args = args[1:]
        
        # Find and replace {} placeholders
        result = []
        i = 0
        arg_index = 0
        
        while i < len(format_str):
            if i < len(format_str) - 1 and format_str[i:i+2] == "{}":
                # Found {} placeholder
                if arg_index >= len(rest_args):
                    raise RuntimeError("Not enough arguments for format string")
                v = rest_args[arg_index]
                if isinstance(v, bool):
                    result.append("true" if v else "false")
                elif isinstance(v, float):
                    result.append(f"{v:g}")
                else:
                    result.append(str(v))
                arg_index += 1
                i += 2
            elif format_str[i] == '\\' and i < len(format_str) - 1:
                # Escape sequences
                if format_str[i+1] == 'n':
                    result.append('\n')
                    i += 2
                elif format_str[i+1] == 't':
                    result.append('\t')
                    i += 2
                elif format_str[i+1] == '\\':
                    result.append('\\')
                    i += 2
                else:
                    result.append(format_str[i])
                    i += 1
            else:
                result.append(format_str[i])
                i += 1
        
        return "".join(result)

    # ============================================================
    # Type Rank (Numeric Type Compatibility)
    # ============================================================
    def numeric_type_rank(self, type_name: str) -> int:
        """Get numeric type rank for implicit type coercion.
        
        Args:
            type_name (str): Type name (i8, i16, i32, i64, u8, u16, u32, u64, f32, f64)
        
        Returns:
            int: Rank where higher value = larger type capacity
        
        Notes:
            - Signed int: i8(1) < i16(2) < i32(3) < i64(4)
            - Unsigned int: u8(5) < u16(6) < u32(7) < u64(8)
            - Float: f32(9) < f64(10)
            - Used in find_common_numeric_type() for type promotion
        """
        if type_name == "i8":   return 1
        if type_name == "i16":  return 2
        if type_name == "i32":  return 3
        if type_name == "i64":  return 4
        if type_name == "u8":   return 5
        if type_name == "u16":  return 6
        if type_name == "u32":  return 7
        if type_name == "u64":  return 8
        if type_name == "f32":  return 9
        if type_name == "f64":  return 10
        return -1

    def is_signed_int(self, type_name: str) -> bool:
        """Check if type is signed integer (i8, i16, i32, i64).
        
        Args:
            type_name (str): Type name to check
        
        Returns:
            bool: True if signed integer type
        """
        return type_name in ("i8", "i16", "i32", "i64")
    
    def is_unsigned_int(self, type_name: str) -> bool:
        """Check if type is unsigned integer (u8, u16, u32, u64).
        
        Args:
            type_name (str): Type name to check
        
        Returns:
            bool: True if unsigned integer type
        """
        return type_name in ("u8", "u16", "u32", "u64")

    def find_common_numeric_type(self, a: TypeNode, b: TypeNode) -> TypeNode:
        """Find common supertype for implicit type coercion.
        
        Args:
            a (TypeNode): First type
            b (TypeNode): Second type
        
        Returns:
            TypeNode: Type with higher rank (broader type for coercion)
        
        Notes:
            - Same types return as-is
            - Float types take precedence over int types
            - Among same category, higher rank type is returned
            - Rank: i8 < i16 < i32 < i64 < u8 < u16 < u32 < u64 < f32 < f64
        """
        a_name = a.name
        b_name = b.name

        if a_name == b_name:
            return a

        if FLOAT_TYPES and (a_name in FLOAT_TYPES or b_name in FLOAT_TYPES):
            if a_name in FLOAT_TYPES and b_name in FLOAT_TYPES:
                rank_a = self.numeric_type_rank(a_name)
                rank_b = self.numeric_type_rank(b_name)
                return a if rank_a >= rank_b else b
            return TypeNode("f64")

        if self.is_unsigned_int(a_name) and self.is_unsigned_int(b_name):
            rank_a = self.numeric_type_rank(a_name)
            rank_b = self.numeric_type_rank(b_name)
            larger = a_name if rank_a >= rank_b else b_name
            return TypeNode(larger)

        if self.is_signed_int(a_name) and self.is_signed_int(b_name):
            rank_a = self.numeric_type_rank(a_name)
            rank_b = self.numeric_type_rank(b_name)
            larger = a_name if rank_a >= rank_b else b_name
            return TypeNode(larger)

        return None

    # ============================================================
    # ジェネリック関数の型推論（T の制約解決）
    # ============================================================
    def infer_call_subst(self, expr, env):
        """Infer generic type substitution from function call arguments.
        
        Args:
            expr: Function call expression with name and arguments
            env (list): Scope stack for expression evaluation
        
        Processing:
            1. Look up function entry by name
            2. Return None if builtin or non-generic function
            3. If explicit type args provided, return direct substitution
            4. Otherwise, evaluate each argument and infer types:
               - Extract runtime type via runtime_type_of()
               - Match against generic type parameters
               - Resolve to most specific common type
        
        Returns:
            dict: Substitution mapping (type_param_name -> TypeNode) or None
        
        Raises:
            RuntimeError: If argument types conflict and no common type
        
        Notes:
            - Explicit type args override inference
            - Builtin functions don't support generics
            - Numeric type promotion uses find_common_numeric_type()
        """
        if expr.name not in self.functions:
            return None  # Not a registered function (could be lambda or undefined)
        entry = self.functions[expr.name]

        # 組み込み関数はジェネリック推論しない
        if isinstance(entry, tuple) and entry[0] == "builtin":
            return None

        # ジェネリックでない関数
        func = entry
        if not func.type_params:
            return None

        subst = {}

        # 明示的な型引数
        if hasattr(expr, "type_args") and expr.type_args:
            return dict(zip(func.type_params, expr.type_args))

        # 型推論
        for arg_expr, param in zip(expr.args, func.params):
            arg_value = self.eval_expr(arg_expr, env)
            arg_type = self.runtime_type_of(arg_value)

            param_type = param.type_node

            if param_type.name in func.type_params:
                if param_type.name not in subst:
                    subst[param_type.name] = arg_type
                else:
                    # すでに推論済みの型と一致するか、昇格可能か確認
                    existing = subst[param_type.name]
                    if self.types_equal(existing, arg_type):
                        # OK: 同じ型
                        pass
                    elif self.numeric_type_rank(existing.name) >= 0 and self.numeric_type_rank(arg_type.name) >= 0:
                        # Both are numeric types: unify to higher rank
                        common = self.find_common_numeric_type(existing, arg_type)
                        if common:
                            subst[param_type.name] = common
                        else:
                            raise RuntimeError(
                                f"Type inference conflict for {param_type.name}: incompatible types {existing.name} and {arg_type.name}"
                            )
                    else:
                        raise RuntimeError(
                            f"Type inference conflict for {param_type.name}"
                        )

        return subst

    # ============================================================
    # Runtime Type Inference
    # ============================================================
    def runtime_type_of(self, value):
        """Infer runtime type of Python value from Mryl semantics.
        
        Args:
            value: Runtime value (any Python type)
        
        Returns:
            TypeNode: Detected type (name, optional type_args)
        
        Processing:
            Dict with __struct_name__: Struct type
            Dict with __range__: Range type
            List: Array type (element type inferred from first element)
            bool: Boolean type
            int: Numeric type (i32 default)
            float: Float type (f64 default)
            str: String type
        
        Notes:
            - Does not distinguish between i32/i64, all ints -> TypeNode("i32")
            - Array elements assumed homogeneous (array<T>)
            - Domain-specific dicts (__struct_name__, __range__) recognized
        """
        # Check bool first (bool is subclass of int in Python)
        if isinstance(value, bool):
            return TypeNode("bool")
        if isinstance(value, int):
            # Default to i32
            return TypeNode("i32")
        if isinstance(value, float):
            # Default to f64
            return TypeNode("f64")
        if isinstance(value, str):
            return TypeNode("string")
        if isinstance(value, dict):
            return TypeNode(value["__struct_name__"], type_args=value.get("__type_args__", []))
        raise RuntimeError(f"Unknown runtime type: {value}")

    # ============================================================
    # Type Comparison (Needed in Interpreter)
    # ============================================================
    def types_equal(self, a: TypeNode, b: TypeNode):
        """Check if two types are structurally equal.
        
        Args:
            a (TypeNode): First type
            b (TypeNode): Second type
        
        Returns:
            bool: True if types match in all aspects (name, array_size, type_args recursively)
        
        Processing:
            1. Compare base type names
            2. Compare array sizes
            3. Recursively compare all type arguments
        
        Notes:
            - For generic types: T<i32> != T<i64>
            - For arrays: [T; 10] != [T; 20]
            - For nested generics: fully recursive comparison
        """
        if a.name != b.name:
            return False
        if a.array_size != b.array_size:
            return False
        if len(a.type_args) != len(b.type_args):
            return False
        for x, y in zip(a.type_args, b.type_args):
            if not self.types_equal(x, y):
                return False
        return True