from __future__ import annotations
from Ast import *
from CodeGenerator._proto import _CodeGeneratorBase

class CodeGeneratorHeaderMixin(_CodeGeneratorBase):
    """C ファイル先頭（#include・組み込み型・組み込み関数・Vec ヘルパー）の出力を担当する Mixin
    _emit_includes / _emit_builtin_types / _collect_vec_elem_types /
    _emit_vec_helpers / _emit_builtin_functions / _emit_header
    """

    def _emit_includes(self):
        """#include ディレクティブを出力する """
        self._emit("#include <stdio.h>")
        self._emit("#include <stdlib.h>")
        self._emit("#include <string.h>")
        self._emit("#include <stdint.h>")
        self._emit("#include <stdarg.h>")
        self._emit("#include <time.h>")
        self._emit("#include <ctype.h>")
        self._emit("#include <regex.h>")
        self._emit("")

    def _emit_builtin_types(self):
        """組み込み型定義 (MrylString) を出力する """
        self._emit("// ============================================================")
        self._emit("// Built-in types and structures")
        self._emit("// ============================================================")
        self._emit("")
        self._emit("typedef struct {")
        self.indent_level += 1
        self._emit("char* data;")
        self._emit("int length;")
        self.indent_level -= 1
        self._emit("} MrylString;")
        self._emit("")

    def _collect_vec_elem_types(self, program) -> set:
        """AST を走査して動的配列 (array_size == -1) の要素型名を収集する。
        Box<T> 要素は "Box_T" 形式（例: Box_i32）で登録する。
        """
        types = set()

        def walk_type(t):
            if t and getattr(t, 'array_size', None) == -1:
                if t.name == "Box" and getattr(t, 'type_args', None):
                    # Box<T>[] → "Box_T" として登録
                    inner_name = t.type_args[0].name if t.type_args else "i32"
                    types.add(f"Box_{inner_name}")
                else:
                    types.add(t.name)

        def walk_stmt(s):
            if s is None:
                return
            cls = s.__class__.__name__
            if cls == 'LetDecl':
                walk_type(s.type_node)
            elif cls == 'Block':
                for st in s.statements:
                    walk_stmt(st)
            elif cls == 'IfStmt':
                walk_stmt(s.then_block)
                if s.else_block:
                    walk_stmt(s.else_block)
            elif cls in ('WhileStmt',):
                walk_stmt(s.body)
            elif cls == 'ForStmt':
                walk_stmt(s.body)

        for func in program.functions:
            for p in func.params:
                walk_type(getattr(p, 'type_node', None))
            if func.body:
                walk_stmt(func.body)
        return types

    def _collect_combinator_types(self, program) -> dict:
        """AST を走査して Task::when_all / when_any の使用型を収集する。
        T は LetDecl の型注釈から取得する（型推論環境が未構築のため _infer_expr_type は使えない）。
        戻り値: { T_name: set_of_combinators }  例: {"i32": {"when_all"}}
        """
        result = {}

        def check_let(s):
            """LetDecl が `let x: T = await Task::when_*(...)` の形か確認し型を登録する。"""
            ie = s.init_expr
            if ie is None or ie.__class__.__name__ != 'AwaitExpr':
                return
            inner = ie.expr
            if inner.__class__.__name__ != 'EnumVariantExpr':
                return
            if inner.enum_name != 'Task' or inner.variant_name not in ('when_all', 'when_any'):
                return
            if not inner.args or not hasattr(inner.args[0], 'elements'):
                return
            # 型注釈から T を取得（when_all: i32[]→"i32"、when_any: i32→"i32"）
            t = s.type_node
            if t is None:
                return
            T_name = t.name  # TypeNode("i32", array_size=-1).name == "i32"
            result.setdefault(T_name, set()).add(inner.variant_name)

        def walk_stmt(s):
            if s is None:
                return
            cls = s.__class__.__name__
            if cls == 'LetDecl':
                check_let(s)
            elif cls == 'Block':
                for st in s.statements:
                    walk_stmt(st)
            elif cls == 'IfStmt':
                walk_stmt(s.then_block)
                if s.else_block:
                    walk_stmt(s.else_block)
            elif cls in ('WhileStmt', 'ForStmt'):
                walk_stmt(s.body)

        for func in program.functions:
            if func.body:
                walk_stmt(func.body)
        return result

    def _emit_vec_helpers(self, elem_types: set):
        """MrylVec_<T> 構造体とヘルパー関数を出力する。
        "Box_T" 形式の要素型は T* ポインタ型として扱う（Vec<Box<T>> サポート）。
        """
        _c_map = {
            "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
            "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t",
            "f32": "float", "f64": "double", "bool": "int",
            "string": "MrylString",
        }
        self._emit("// ============================================================")
        self._emit("// Dynamic array (MrylVec_<T>) types and helpers")
        self._emit("// ============================================================")
        self._emit("")
        for et in sorted(elem_types):
            # Box_T 形式: 要素の C 型は T* （Box<T> = ヒープポインタ）
            if et.startswith("Box_"):
                inner_mryl = et[4:]  # "Box_i32" → "i32"
                ct = _c_map.get(inner_mryl, "int32_t") + "*"
            else:
                ct = _c_map.get(et, et if et not in _c_map else _c_map[et])
            T, C = et, ct
            self._emit(f"typedef struct {{ {C}* data; int32_t len; int32_t cap; }} MrylVec_{T};")
            self._emit(f"static inline MrylVec_{T} mryl_vec_{T}_new(void) {{")
            self._emit(f"    MrylVec_{T} v; v.data = NULL; v.len = 0; v.cap = 0; return v;")
            self._emit(f"}}")
            self._emit(f"static inline MrylVec_{T} mryl_vec_{T}_from({C}* elems, int32_t n) {{")
            self._emit(f"    MrylVec_{T} v; v.len = n; v.cap = n;")
            self._emit(f"    v.data = ({C}*)malloc(sizeof({C}) * n);")
            self._emit(f"    for (int32_t i = 0; i < n; i++) v.data[i] = elems[i];")
            self._emit(f"    return v;")
            self._emit(f"}}")
            self._emit(f"static inline void mryl_vec_{T}_push(MrylVec_{T}* v, {C} val) {{")
            self._emit(f"    if (v->len == v->cap) {{")
            self._emit(f"        v->cap = v->cap ? v->cap * 2 : 4;")
            self._emit(f"        v->data = ({C}*)realloc(v->data, sizeof({C}) * v->cap);")
            self._emit(f"    }}")
            self._emit(f"    v->data[v->len++] = val;")
            self._emit(f"}}")
            self._emit(f"static inline {C} mryl_vec_{T}_pop(MrylVec_{T}* v) {{")
            self._emit(f"    return v->data[--v->len];")
            self._emit(f"}}")
            self._emit(f"static inline {C} mryl_vec_{T}_remove(MrylVec_{T}* v, int32_t idx) {{")
            self._emit(f"    {C} __val = v->data[idx];")
            self._emit(f"    for (int32_t i = idx; i < v->len - 1; i++) v->data[i] = v->data[i+1];")
            self._emit(f"    v->len--;")
            self._emit(f"    return __val;")
            self._emit(f"}}")
            self._emit(f"static inline void mryl_vec_{T}_insert(MrylVec_{T}* v, int32_t idx, {C} val) {{")
            self._emit(f"    if (v->len == v->cap) {{")
            self._emit(f"        v->cap = v->cap ? v->cap * 2 : 4;")
            self._emit(f"        v->data = ({C}*)realloc(v->data, sizeof({C}) * v->cap);")
            self._emit(f"    }}")
            self._emit(f"    for (int32_t i = v->len; i > idx; i--) v->data[i] = v->data[i-1];")
            self._emit(f"    v->data[idx] = val;")
            self._emit(f"    v->len++;")
            self._emit(f"}}")
            # string 要素の場合は各要素の char* も解放するデストラクタを追加する。
            # 通常の free(v.data) では MrylString 構造体の配列しか解放されず、
            # 内部の char* がリークするため専用の free 関数が必要。
            if T == "string":
                self._emit(f"static inline void mryl_vec_string_free(MrylVec_string v) {{")
                self._emit(f"    for (int32_t i = 0; i < v.len; i++) free_mryl_string(v.data[i]);")
                self._emit(f"    free(v.data);")
                self._emit(f"}}")
            self._emit(f"")

    def _emit_builtin_functions(self):
        """組み込み関数 (mryl_panic / print / println / MrylString helpers) を出力する """
        self._emit("// ============================================================")
        self._emit("// Built-in functions")
        self._emit("// ============================================================")
        self._emit("")
        self._emit("static void mryl_panic(")
        self._emit("        const char* error_type, const char* message,")
        self._emit("        const char* func, const char* file, int line) {")
        self.indent_level += 1
        self._emit("time_t __now = time(NULL);")
        self._emit("struct tm* __tm = localtime(&__now);")
        self._emit("char __timebuf[24];")
        self._emit("strftime(__timebuf, sizeof(__timebuf), \"%Y-%m-%d %H:%M:%S\", __tm);")
        self._emit("// Brief one-liner to stdout")
        self._emit("printf(\"[FATAL] %s: %s\\n  See stderr for full error report.\\n\", error_type, message);")
        self._emit("// Detailed report to stderr")
        self._emit("fprintf(stderr, \"[%s] ERROR %s: %s\\n\", __timebuf, error_type, message);")
        self._emit("fprintf(stderr, \"  function: %s\\n\", func);")
        self._emit("fprintf(stderr, \"  file: %s\\n\", file);")
        self._emit("fprintf(stderr, \"  line: %d\\n\", line);")
        self._emit("fprintf(stderr, \"\\nStacktrace:\\n\");")
        self._emit("fprintf(stderr, \"  %s(%s:%d)\\n\", func, file, line);")
        self._emit("exit(1);")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("void print(const char* fmt, ...) {")
        self.indent_level += 1
        self._emit("va_list args;")
        self._emit("va_start(args, fmt);")
        self._emit("vprintf(fmt, args);")
        self._emit("va_end(args);")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("void println(const char* fmt, ...) {")
        self.indent_level += 1
        self._emit("va_list args;")
        self._emit("va_start(args, fmt);")
        self._emit("vprintf(fmt, args);")
        self._emit("va_end(args);")
        self._emit("printf(\"\\n\");")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("// MrylString helper functions")
        self._emit("MrylString make_mryl_string(const char* str) {")
        self.indent_level += 1
        self._emit("MrylString s;")
        self._emit("s.data = (char*)malloc(strlen(str) + 1);")
        self._emit("strcpy(s.data, str);")
        self._emit("s.length = strlen(str);")
        self._emit("return s;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("void free_mryl_string(MrylString s) {")
        self.indent_level += 1
        self._emit("if (s.data != NULL) {")
        self.indent_level += 1
        self._emit("free(s.data);")
        self.indent_level -= 1
        self._emit("}")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("MrylString mryl_string_concat(MrylString a, MrylString b) {")
        self.indent_level += 1
        self._emit("int new_length = a.length + b.length;")
        self._emit("MrylString result;")
        self._emit("result.data = (char*)malloc(new_length + 1);")
        self._emit("strcpy(result.data, a.data);")
        self._emit("strcat(result.data, b.data);")
        self._emit("result.length = new_length;")
        self._emit("return result;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("// string built-in method helpers")
        self._emit("static inline int32_t mryl_str_len(MrylString s) { return (int32_t)s.length; }")
        self._emit("static inline int mryl_str_contains(MrylString s, MrylString sub) { return strstr(s.data, sub.data) != NULL; }")
        self._emit("static inline int mryl_str_starts_with(MrylString s, MrylString pre) { return strncmp(s.data, pre.data, strlen(pre.data)) == 0; }")
        self._emit("static inline int mryl_str_ends_with(MrylString s, MrylString suf) {")
        self.indent_level += 1
        self._emit("size_t sl = strlen(s.data), pl = strlen(suf.data);")
        self._emit("if (pl > sl) return 0;")
        self._emit("return strcmp(s.data + (sl - pl), suf.data) == 0;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("static inline MrylString mryl_str_trim(MrylString s) {")
        self.indent_level += 1
        self._emit("const char *p = s.data;")
        self._emit("while (*p == ' ' || *p == '\\t' || *p == '\\n' || *p == '\\r') p++;")
        self._emit("size_t len = strlen(p);")
        self._emit("while (len > 0 && (p[len-1] == ' ' || p[len-1] == '\\t' || p[len-1] == '\\n' || p[len-1] == '\\r')) len--;")
        self._emit("char *buf = (char*)malloc(len + 1);")
        self._emit("memcpy(buf, p, len);")
        self._emit("buf[len] = '\\0';")
        self._emit("MrylString r;")
        self._emit("r.data = buf;")
        self._emit("r.length = (int)len;")
        self._emit("return r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("static inline MrylString mryl_str_to_upper(MrylString s) {")
        self.indent_level += 1
        self._emit("char *buf = (char*)malloc(s.length + 1);")
        self._emit("strcpy(buf, s.data);")
        self._emit("for (int i = 0; i < s.length; i++) buf[i] = (char)toupper((unsigned char)buf[i]);")
        self._emit("MrylString r;")
        self._emit("r.data = buf;")
        self._emit("r.length = s.length;")
        self._emit("return r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("static inline MrylString mryl_str_to_lower(MrylString s) {")
        self.indent_level += 1
        self._emit("char *buf = (char*)malloc(s.length + 1);")
        self._emit("strcpy(buf, s.data);")
        self._emit("for (int i = 0; i < s.length; i++) buf[i] = (char)tolower((unsigned char)buf[i]);")
        self._emit("MrylString r;")
        self._emit("r.data = buf;")
        self._emit("r.length = s.length;")
        self._emit("return r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("static inline MrylString mryl_str_replace(MrylString s, MrylString from, MrylString to_s) {")
        self.indent_level += 1
        self._emit("if (from.length == 0) return make_mryl_string(s.data);")
        self._emit("int count = 0;")
        self._emit("const char *p = s.data;")
        self._emit("while ((p = strstr(p, from.data)) != NULL) {")
        self.indent_level += 1
        self._emit("count++;")
        self._emit("p += from.length;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("int new_len = s.length + count * (to_s.length - from.length);")
        self._emit("char *buf = (char*)malloc(new_len + 1);")
        self._emit("char *dst = buf;")
        self._emit("p = s.data;")
        self._emit("const char *found;")
        self._emit("while ((found = strstr(p, from.data)) != NULL) {")
        self.indent_level += 1
        self._emit("size_t seg = found - p;")
        self._emit("memcpy(dst, p, seg);")
        self._emit("dst += seg;")
        self._emit("memcpy(dst, to_s.data, to_s.length);")
        self._emit("dst += to_s.length;")
        self._emit("p = found + from.length;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("strcpy(dst, p);")
        self._emit("MrylString r;")
        self._emit("r.data = buf;")
        self._emit("r.length = new_len;")
        self._emit("return r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("static MrylString _mryl_to_string_i32(int32_t n) {")
        self.indent_level += 1
        self._emit("char buf[32];")
        self._emit("snprintf(buf, sizeof(buf), \"%d\", n);")
        self._emit("return make_mryl_string(buf);")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("static MrylString _mryl_to_string_f64(double n) {")
        self.indent_level += 1
        self._emit("char buf[32];")
        self._emit("snprintf(buf, sizeof(buf), \"%g\", n);")
        self._emit("return make_mryl_string(buf);")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("static MrylString _mryl_to_string_bool(int n) {")
        self.indent_level += 1
        self._emit("return make_mryl_string(n ? \"true\" : \"false\");")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("static MrylString _mryl_to_string_string(MrylString s) { return make_mryl_string(s.data); }")
        self._emit("")
        self._emit("#define to_string(x) _Generic((x), double: _mryl_to_string_f64, float: _mryl_to_string_f64, MrylString: _mryl_to_string_string, _Bool: _mryl_to_string_bool, default: _mryl_to_string_i32)(x)")
        self._emit("")
        self._emit("// ---- Input functions ----")
        self._emit("static MrylString read_line(void) {")
        self.indent_level += 1
        self._emit("char buf[4096];")
        self._emit("if (fgets(buf, sizeof(buf), stdin) == NULL) {")
        self.indent_level += 1
        self._emit("buf[0] = '\\0';")
        self.indent_level -= 1
        self._emit("}")
        self._emit("int len = (int)strlen(buf);")
        self._emit("while (len > 0 && (buf[len-1] == '\\n' || buf[len-1] == '\\r')) {")
        self.indent_level += 1
        self._emit("buf[--len] = '\\0';")
        self.indent_level -= 1
        self._emit("}")
        self._emit("return make_mryl_string(buf);")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        # parse_int / parse_f64: return Result<T, string>  (#42)
        self.result_type_registry.add(('int32_t', 'MrylString', 'MrylResult_int32_t_MrylString'))
        self.result_type_registry.add(('double',  'MrylString', 'MrylResult_double_MrylString'))
        self._emit("// parse_int(s) -> MrylResult_int32_t_MrylString")
        self._emit("static MrylResult_int32_t_MrylString parse_int(MrylString s) {")
        self.indent_level += 1
        self._emit("MrylResult_int32_t_MrylString __r;")
        self._emit("char* __end;")
        self._emit("long __v = strtol(s.data, &__end, 10);")
        self._emit("if (__end == s.data || *__end != '\\0') {")
        self.indent_level += 1
        self._emit("__r.is_ok = 0;")
        self._emit("__r.data.err_val = make_mryl_string(\"cannot parse string as i32\");")
        self._emit("return __r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("__r.is_ok = 1;")
        self._emit("__r.data.ok_val = (int32_t)__v;")
        self._emit("return __r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        self._emit("// parse_f64(s) -> MrylResult_double_MrylString")
        self._emit("static MrylResult_double_MrylString parse_f64(MrylString s) {")
        self.indent_level += 1
        self._emit("MrylResult_double_MrylString __r;")
        self._emit("char* __end;")
        self._emit("double __v = strtod(s.data, &__end);")
        self._emit("if (__end == s.data || *__end != '\\0') {")
        self.indent_level += 1
        self._emit("__r.is_ok = 0;")
        self._emit("__r.data.err_val = make_mryl_string(\"cannot parse string as f64\");")
        self._emit("return __r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("__r.is_ok = 1;")
        self._emit("__r.data.ok_val = __v;")
        self._emit("return __r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        # checked_div: safe integer division returning Result<i32, string>
        # Pre-register the typedef so _RESULT_TYPEDEFS_PLACEHOLDER is correctly filled
        self.result_type_registry.add(('int32_t', 'MrylString', 'MrylResult_int32_t_MrylString'))
        self._emit("// checked_div(a, b) -> MrylResult_int32_t_MrylString")
        self._emit("// Returns Ok(a/b) or Err(\"division by zero\")")
        self._emit("static MrylResult_int32_t_MrylString checked_div(int32_t a, int32_t b) {")
        self.indent_level += 1
        self._emit("if (b == 0) {")
        self.indent_level += 1
        self._emit("MrylResult_int32_t_MrylString __r;")
        self._emit("__r.is_ok = 0;")
        self._emit("__r.data.err_val = make_mryl_string(\"division by zero\");")
        self._emit("return __r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("MrylResult_int32_t_MrylString __r;")
        self._emit("__r.is_ok = 1;")
        self._emit("__r.data.ok_val = a / b;")
        self._emit("return __r;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")
        # mryl_safe_div / mryl_safe_mod: panic on zero divisor (Phase 1 trap)
        self._emit("// mryl_safe_div / mryl_safe_mod: panic on zero divisor")
        self._emit("static int32_t mryl_safe_div(int32_t a, int32_t b) {")
        self.indent_level += 1
        self._emit("if (b == 0) {")
        self.indent_level += 1
        self._emit("mryl_panic(\"RuntimeError\", \"division by zero\", __func__, __FILE__, __LINE__);")
        self.indent_level -= 1
        self._emit("}")
        self._emit("return a / b;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("static int32_t mryl_safe_mod(int32_t a, int32_t b) {")
        self.indent_level += 1
        self._emit("if (b == 0) {")
        self.indent_level += 1
        self._emit("mryl_panic(\"RuntimeError\", \"division by zero\", __func__, __FILE__, __LINE__);")
        self.indent_level -= 1
        self._emit("}")
        self._emit("return a % b;")
        self.indent_level -= 1
        self._emit("}")
        self._emit("")

    def _emit_header(self):
        """組み込み型・関数をまとめて出力する (内部利用) """
        self._emit_builtin_types()
        self._emit_builtin_functions()
