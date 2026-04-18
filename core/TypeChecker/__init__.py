from Ast import *
from MrylError import *

from TypeChecker._stmt import TypeCheckerStmtMixin
from TypeChecker._expr import TypeCheckerExprMixin
from TypeChecker._call import TypeCheckerCallMixin
from TypeChecker._util import (
    INTEGER_TYPES, FLOAT_TYPES, NUMERIC_TYPES,
    numeric_type_rank as _numeric_type_rank,
    is_signed_int as _is_signed_int,
    is_unsigned_int as _is_unsigned_int,
    find_common_numeric_type as _find_common_numeric_type,
)

class TypeChecker(TypeCheckerStmtMixin, TypeCheckerExprMixin, TypeCheckerCallMixin):
    """Mryl の型チェッカ

    ファイル構成:
        __init__.py  ─ 本体: 初期化 / 型ユーティリティ / check_program・function・method
        _stmt.py     ─ 文チェック (check_block / check_let / check_if ...)
        _expr.py     ─ 式チェック (check_expr / check_binary / check_lambda ...)
        _call.py     ─ 呼び出し・ジェネリクス解決 (check_call / check_struct_init ...)
        _util.py     ─ 定数・純粋関数 (INTEGER_TYPES / FLOAT_TYPES / find_common_numeric_type ...)

    MRO（メソッド解決順）:
        TypeChecker → StmtMixin → ExprMixin → CallMixin → object
    """

    def __init__(self):
        self.structs     = {}  # name -> StructDecl
        self.functions   = {}  # name -> FunctionDecl
        self.enums       = {}  # name -> EnumDecl
        self.env         = []  # スコープスタック（辞書のリスト）
        self.const_table = {}  # name -> {type, expr}
        self.fix_vars    = set()  # fix 宣言された不変変数名のセット

        # ---- 組み込み関数 ----
        self.functions["print"] = FunctionDecl(
            name="print",
            params=[Param("x", TypeNode("any"))],
            return_type=TypeNode("int"),
            body=None,
            type_params=[]
        )
        self.functions["println"] = FunctionDecl(
            name="println",
            params=[Param("x", TypeNode("any"))],
            return_type=TypeNode("int"),
            body=None,
            type_params=[]
        )
        self.functions["to_string"] = FunctionDecl(
            name="to_string",
            params=[Param("x", TypeNode("int"))],
            return_type=TypeNode("string"),
            body=None,
            type_params=[]
        )
        self.functions["read_line"] = FunctionDecl(
            name="read_line",
            params=[],
            return_type=TypeNode("string"),
            body=None,
            type_params=[]
        )
        self.functions["parse_int"] = FunctionDecl(
            name="parse_int",
            params=[Param("s", TypeNode("string"))],
            return_type=TypeNode("Result", type_args=[TypeNode("i32"), TypeNode("string")]),
            body=None,
            type_params=[]
        )
        self.functions["parse_f64"] = FunctionDecl(
            name="parse_f64",
            params=[Param("s", TypeNode("string"))],
            return_type=TypeNode("Result", type_args=[TypeNode("f64"), TypeNode("string")]),
            body=None,
            type_params=[]
        )
        self.functions["checked_div"] = FunctionDecl(
            name="checked_div",
            params=[Param("a", TypeNode("i32")), Param("b", TypeNode("i32"))],
            return_type=TypeNode("Result", type_args=[TypeNode("i32"), TypeNode("string")]),
            body=None,
            type_params=[]
        )

    # ============================================
    # 型比較（ジェネリクス対応）
    # ============================================
    def types_equal(self, a: TypeNode, b: TypeNode) -> bool:
        # any は何とでも一致する
        if a.name == "any" or b.name == "any":
            return True

        # Result / Option: 片方でも type_args がない場合（型推論未解決）は名前だけで一致とする。
        # 両方に type_args がある場合のみ後段の通常比較（型引数を再帰チェック）に委ねる。
        # ※ 両方 type_args ありで早期 True を返すと Result<i32,E> と Result<f64,E> が
        #    同一型と判定されてしまうため、両方 type_args ありの場合はフォールスルーする。
        if a.name == "Result" and b.name == "Result":
            if not a.type_args or not b.type_args:
                return True
        if a.name == "Option" and b.name == "Option":
            if not a.type_args or not b.type_args:
                return True

        # 配列型の比較: 一方のみ配列型はスカラーと配列の不一致 → False
        if a.array_size is not None or b.array_size is not None:
            if a.array_size is None or b.array_size is None:
                return False
            a_dyn = (a.array_size == -1)
            b_dyn = (b.array_size == -1)
            if a.name != b.name:
                return False
            if a_dyn or b_dyn:
                return True  # T[] は T[N] と一致（動的配列の互換性）
            return a.array_size == b.array_size

        # 通常の型比較
        if a.name != b.name:
            return False
        if len(a.type_args) != len(b.type_args):
            return False
        for x, y in zip(a.type_args, b.type_args):
            if not self.types_equal(x, y):
                return False
        return True

    # ============================================
    # 型置換（T → int など）
    # ============================================
    def substitute_type(self, t: TypeNode, subst: dict):
        if t.name in subst:
            return subst[t.name]

        if t.array_size is not None:
            return TypeNode(t.name, array_size=t.array_size)

        if t.type_args:
            new_args = [self.substitute_type(a, subst) for a in t.type_args]
            return TypeNode(t.name, type_args=new_args)

        return TypeNode(t.name)

    # ============================================
    # 数値型ランク・昇格ルール
    # ============================================
    def numeric_type_rank(self, type_name: str) -> int:
        """数値型のランクを返す。大きいほど「大きい型」。"""
        return _numeric_type_rank(type_name)

    def is_signed_int(self, type_name: str) -> bool:
        return _is_signed_int(type_name)

    def is_unsigned_int(self, type_name: str) -> bool:
        return _is_unsigned_int(type_name)

    def find_common_numeric_type(self, a: TypeNode, b: TypeNode) -> TypeNode:
        """2 つの数値型の共通上位型を返す。(_util.find_common_numeric_type へ委譲)"""
        return _find_common_numeric_type(a, b)

    # ============================================
    # エントリポイント
    # ============================================
    def check_program(self, program: Program):
        # const を最初に処理
        for const_decl in program.consts:
            self.check_const_decl(const_decl)

        # 構造体・enum・関数を登録
        for s in program.structs:
            self.structs[s.name] = s
        for e in program.enums:
            self.enums[e.name] = e
        for f in program.functions:
            self.functions[f.name] = f

        if "main" not in self.functions:
            raise TypeError_("main() function not found", program)

        # 構造体メソッドをチェック
        for s in program.structs:
            for method in s.methods:
                self.check_method(s, method)

        # 各関数をチェック
        for f in program.functions:
            self.check_function(f)

    # ============================================
    # メソッド
    # ============================================
    def check_method(self, struct: StructDecl, method: MethodDecl):
        # 前方宣言 (body=None) はスキップ
        if method.body is None:
            return
        self.env = [{}]
        saved_fix_vars = self.fix_vars
        self.fix_vars = set()

        if getattr(method, 'is_static', False):
            # static fn: self パラメータなし。self を使ったら TypeError
            for p in method.params:
                if p.name == 'self':
                    from MrylError import TypeError_
                    raise TypeError_("static fn cannot have 'self' parameter", p)
                self.env[-1][p.name] = p.type_node
        else:
            method.params[0].type_node = TypeNode(struct.name)  # self パラメータの型を解決
            for p in method.params:
                self.env[-1][p.name] = p.type_node
                if getattr(p, 'is_fix', False):
                    self.fix_vars.add(p.name)
        try:
            self.check_block(method.body, method.return_type)
        finally:
            self.fix_vars = saved_fix_vars

    # ============================================
    # 関数
    # ============================================
    def check_function(self, func: FunctionDecl):
        # ジェネリック関数は呼び出し時に実体化するためスキップ
        if func.type_params:
            return
        # 前方宣言 (body=None) はスキップ
        if func.body is None:
            return

        self.env = [{}]
        saved_fix_vars = self.fix_vars
        self.fix_vars = set()
        for p in func.params:
            self.env[-1][p.name] = p.type_node
            if getattr(p, 'is_fix', False):
                self.fix_vars.add(p.name)
        try:
            self.check_block(func.body, func.return_type)
        finally:
            self.fix_vars = saved_fix_vars
