from __future__ import annotations
from CodeGenerator._proto import _CodeGeneratorBase
from Ast import TypeNode


class CodeGeneratorTypeMixin(_CodeGeneratorBase):
    """型変換を担当する Mixin
    _type_to_c / _type_to_c_base / _type_to_fmt_spec / _emit_result_typedefs / _emit_option_typedefs
    """

    def _type_to_c(self, type_node) -> str:
        """Mryl TypeNode を C 型文字列に変換する。
        副作用: Result<T,E> / Option<T> の初回変換時に各 registry へ登録する。
        """
        if not type_node:
            return "void"

        type_map = {
            "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
            "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t",
            "f32": "float", "f64": "double",
            "string": "MrylString", "bool": "int", "int": "int32_t", "void": "void",
        }

        type_name = type_node.name or ""
        base_type = type_map.get(type_name, type_name)

        # 動的配列は最初にチェックする（Result<T,E>[] 等の struct 型も MrylVec_<key> を返す）
        # 後続の "Result" / "Box" 等のチェックより前に判定しないと struct C 型が返ってしまう
        if getattr(type_node, 'array_size', None) == -1:
            if type_node.name == "Array" and getattr(type_node, 'type_args', None):
                # 多次元配列ラッパー: 要素の C 型を再帰的に解決してキーにする
                # 例: Array<i32[]> → elem_c="MrylVec_i32" → MrylVec_MrylVec_i32
                elem_c = self._type_to_c(type_node.type_args[0])
                T_key = elem_c.replace("*", "Ptr").replace(" ", "_")
            elif getattr(type_node, 'type_args', None):
                # 型引数がある複合型（Result<i32,string>[] など）は _type_key でキーを生成する
                # Box<T>[] も "Box_T" 形式のキーで MrylVec_Box_T が生成される
                T_key = self._type_key(TypeNode(type_node.name, type_args=list(type_node.type_args)))
            else:
                T_key = type_name
            return f"MrylVec_{T_key}"

        if type_node.name == "Future":
            return "MrylTask*"

        # WeakTask<T> は C 表現上 Future<T> と同一（MrylTask* のまま）
        if type_node.name == "WeakTask":
            return "MrylTask*"

        # Subject<T> / Observable<T> → MrylSubject_T*
        if type_node.name in ("Subject", "Observable"):
            if type_node.type_args:
                arg = type_node.type_args[0]
                T = arg.name if hasattr(arg, 'name') else str(arg)
            else:
                T = "i32"
            return f"MrylSubject_{T}*"

        # Subscription → MrylSubscription_T*（型引数なし、void* で汎用的に扱う）
        if type_node.name == "Subscription":
            return "void*"

        if type_node.name == "Box":
            # ユーザー定義 struct Box がある場合は通常の base_type として処理する
            if not self.has_user_box:
                if type_node.type_args:
                    arg = type_node.type_args[0]
                    inner_c = self._type_to_c(arg if hasattr(arg, 'name') else TypeNode(arg))
                    return f"{inner_c}*"
                return "void*"

        if type_node.name == "Result":
            if type_node.type_args and len(type_node.type_args) == 2:
                ok_c  = self._type_to_c(type_node.type_args[0])
                err_c = self._type_to_c(type_node.type_args[1])
                struct_name = (
                    f"MrylResult_{ok_c}_{err_c}"
                    .replace("*", "Ptr")
                    .replace(" ", "_")
                )
                self.result_type_registry.add((ok_c, err_c, struct_name))
                return struct_name
            return "MrylResult_i32_i32"

        if type_node.name == "Option":
            if type_node.type_args:
                inner_c = self._type_to_c(type_node.type_args[0])
                struct_name = (
                    f"MrylOption_{inner_c}"
                    .replace("*", "Ptr")
                    .replace(" ", "_")
                )
                self.option_type_registry.add((inner_c, struct_name))
                return struct_name
            return "MrylOption_int32_t"

        if type_node.name == "fn":
            # fn(T...)->U を fat pointer struct に変換: MrylFn_{arg_part}_ret_{ret_part}
            if getattr(type_node, 'type_args', None):
                ret_c    = self._type_to_c(type_node.type_args[-1])
                arg_cs   = tuple(self._type_to_c(t) for t in type_node.type_args[:-1])
                arg_part = "_".join(c.replace("*", "Ptr").replace(" ", "_") for c in arg_cs) if arg_cs else "void"
                ret_part = ret_c.replace("*", "Ptr").replace(" ", "_")
                struct_name = f"MrylFn_{arg_part}_ret_{ret_part}"
                self.fn_type_registry.add((arg_cs, ret_c, struct_name))
                return struct_name
            return "void*"

        # 静的配列 (array_size > 0) → C の配列型 base_type[N] として扱う
        if type_node.array_size:
            return f"{base_type}[{type_node.array_size}]"

        return base_type

    def _type_to_c_base(self, type_name: str) -> str:
        """TypeNode なしで型名文字列を C 型文字列に変換する """
        type_map = {
            "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
            "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t",
            "f32": "float", "f64": "double",
            "string": "MrylString", "bool": "int", "int": "int32_t", "void": "void",
        }
        return type_map.get(type_name, type_name)

    def _type_to_fmt_spec(self, arg_expr) -> str:
        """printf 書式指定子を式の型から推定する。"""
        t = self._infer_expr_type(arg_expr)
        if t in ("string", "str"):
            return "%s"
        if t in ("f32", "f64", "float"):
            return "%g"
        if t in ("i64",):
            return "%lld"
        if t in ("u64",):
            return "%llu"
        if t in ("u32", "u16", "u8"):
            return "%u"
        if t in ("bool",):
            return "%s"
        return "%d"

    def _emit_result_typedefs(self):
        """result_type_registry に登録済みの Result<T,E> 型を typedef として出力する """
        if not self.result_type_registry:
            return
        self._emit("// ===== Result<T,E> type structs =====")
        for (ok_c, err_c, struct_name) in sorted(self.result_type_registry):
            self._emit(f"typedef struct {{")
            self._emit(f"    int is_ok;")
            self._emit(f"    union {{ {ok_c} ok_val; {err_c} err_val; }} data;")
            self._emit(f"}} {struct_name};")
        self._emit("")

    def _emit_option_typedefs(self):
        """option_type_registry に登録済みの Option<T> 型を typedef として出力する"""
        if not self.option_type_registry:
            return
        self._emit("// ===== Option<T> type structs =====")
        for (inner_c, struct_name) in sorted(self.option_type_registry):
            self._emit(f"typedef struct {{")
            self._emit(f"    {inner_c} value;")
            self._emit(f"    int has_value;")
            self._emit(f"}} {struct_name};")
        self._emit("")
