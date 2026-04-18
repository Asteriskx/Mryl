# Mryl プログラミング言語 - 言語詳細仕様書

**バージョン**: 0.7.0
**最終更新**: 2026年4月18日

---

## 目次

1. [概要](#概要)
2. [プロジェクト構成](#プロジェクト構成)
3. [実装機能](#実装機能)
4. [演算子](#演算子)
5. [Const 定数とコンパイル時評価](#const-定数とコンパイル時評価)
6. [条件付きコンパイル](#条件付きコンパイル)
7. [型システム](#型システム)
8. [ジェネリック](#ジェネリック)
9. [構造体とメソッド](#構造体とメソッド)
10. [static fn（静的メソッド）](#static-fn静的メソッド)
11. [ラムダ式](#ラムダ式)
12. [async / await](#async--await)
13. [制御フロー](#制御フロー)
14. [メモリ管理](#メモリ管理)
15. [入力関数](#入力関数)
16. [コンパイルパイプライン](#コンパイルパイプライン)
17. [AST構造](#ast構造)
18. [拡張ガイド](#拡張ガイド)

---

## 概要

**Mryl** は小規模な静的型付けプログラミング言語で、以下の特徴を持っています：

- **静的型付け**: コンパイル時に型チェック
- **ネイティブコンパイル**: C コード生成を経由して、Windows/Linux で実行可能なバイナリへコンパイル
- **ジェネリック関数**: 複数の型パラメータをサポート
- **構造体とメソッド**: オブジェクト指向プログラミングのサポート
- **メモリ安全性**: 自動メモリ管理（malloc/free の自動化）
- **完全な演算子セット**: 論理、ビット、複合代入演算子を完全サポート
- **ラムダ式**: `(x, y) => x + y` の無名関数（async ラムダ含む）、外部変数のクロージャキャプチャ対応（C コード生成は fat pointer 方式）
- **fn 型パラメータ**: 関数をコールバックとして渡せる高階関数
- **fix キーワード**: 不変変数・不変関数パラメータの宣言
- **前方宣言**: `fn name(...) -> T;` 構文による相互再帰サポート
- **string 操作**: 連結（`+`）・比較（`==` / `!=`）・組み込みメソッド（`len` / `contains` / `starts_with` / `ends_with` / `trim` / `to_upper` / `to_lower` / `replace` / `find` / `split`）
- **Option\<T\>**: 値なし（`None`）/ 値あり（`Some(v)`）の安全な型、match によるパターンマッチ
- **Box\<T\>**: ヒープポインタ型（C では `T*` に変換）、`*b` デリファレンス、`.unbox()`、多重ポインタ対応
- **Iter\<T\> / LINQ**: 配列に対する C# LINQ 準拠のメソッドチェーン（`filter` / `select` / `take` / `skip` / `to_array` / `aggregate` / `for_each` / `count` / `first` / `any` / `all` / `select_many`）
- **ユーザー入力**: `read_line()` / `parse_int()` / `parse_f64()`（`Result<T, string>` 返し）/ `checked_div()`（ゼロ除算安全除算）
- **async / await**: 状態機械 + シングルスレッドスケジューラによる非同期処理

### コンパイルパイプライン

```
Mryl ソースコード (.ml)
  ↓
[Lexer] トークン化
  ↓
[Parser] AST 構築（演算子優先順位を正確に処理）
  ↓
[TypeChecker] 型チェック
  ↓
[Interpreter] Python インタプリタ (検証用)
  ↓
[CodeGenerator] C コード生成
  ↓
[GCC (Cygwin)] C コンパイル
  ↓
実行可能バイナリ (.exe)
```

---

## プロジェクト構成

```
Mryl/
├── core/
│   ├── Lexer.py              # トークン化（FAT_ARROW, ASYNC, AWAIT 対応）
│   ├── Parser.py             # AST 構築（ラムダ, async fn, await）
│   ├── Ast.py                # AST ノード定義（Lambda, AwaitExpr, is_async）
│   ├── TypeChecker/          # 型チェックパッケージ（Mixin 分割）
│   │   ├── __init__.py       #   TypeChecker メインクラス（4 Mixin 多重継承）
│   │   ├── _stmt.py          #   文の型チェック
│   │   ├── _expr.py          #   式の型チェック
│   │   ├── _call.py          #   関数呼び出しの型チェック
│   │   └── _util.py          #   型比較・型昇格ユーティリティ
│   ├── Interpreter.py        # Python インタプリタ（クロージャ, asyncio）
│   ├── CodeGenerator/        # C コード生成パッケージ（Mixin 分割）
│   │   ├── __init__.py       #   CodeGenerator メインクラス（10 Mixin 多重継承）
│   │   ├── _proto.py         #   Protocol 基底クラス（全属性・メソッドスタブ）
│   │   ├── _util.py          #   共通ユーティリティ・エスケープ処理
│   │   ├── _type.py          #   C 型変換・フォーマット指定子
│   │   ├── _const.py         #   定数生成・定数式評価
│   │   ├── _struct.py        #   struct/enum 生成
│   │   ├── _header.py        #   インクルード・組み込み型・ヘルパー生成
│   │   ├── _stmt.py          #   文生成
│   │   ├── _expr.py          #   式生成・match 式・メソッド呼び出し
│   │   ├── _lambda.py        #   ラムダ・クロージャ生成
│   │   ├── _async.py         #   async/await ステートマシン生成
│   │   └── _generic.py       #   ジェネリック関数インスタンス化
│   ├── MrylError.py          # エラー定義
│   └── Mryl.py               # エントリポイント
├── tests/
│   ├── test_01_types.ml         # 基本型・変数宣言・型推論・型キャスト・型昇格
│   ├── test_02_operators.ml     # 算術/比較/論理/ビット/複合代入/インクリメント
│   ├── test_03_control.ml       # if-else / while / for / break / continue
│   ├── test_04_functions.ml     # 基本関数 / 再帰 / ラムダ式 / ジェネリック
│   ├── test_05_struct.ml        # 構造体 / メソッド / ジェネリック構造体
│   ├── test_06_enum_match.ml    # enum / match 式
│   ├── test_07_result.ml        # Result<T,E> / Ok / Err / .try()
│   ├── test_08_array.ml         # 固定長配列 / 可変長配列
│   ├── test_09_const_compile.ml # const / #ifdef / #ifndef / #if / #else
│   ├── test_10_async_await.ml   # async / await / ネスト待機
│   ├── test_11_builtin.ml       # print / println / to_string
│   ├── test_12_type_check.ml    # 型宣言 / 型推論 / 型チェック / 型昇格
│   ├── test_13_boundary_numeric.ml  # 数値型境界値（C0・境界値分析）
│   ├── test_14_branch_coverage.ml   # 条件分岐網羅（C0/C1/MC/DC）
│   ├── test_15_loop_boundary.ml     # ループ境界値（while/for/break/continue）
│   ├── test_16_async_lambda.ml      # async ラムダ式（定義・呼び出し・await 待機・ネスト await）
│   ├── test_17_higherorder.ml       # 高階関数
│   ├── test_18_string_ops.ml        # 文字列操作（連結・比較・組み込みメソッド）
│   ├── test_19_nested_struct.ml     # ネスト構造体
│   ├── test_20_callback.ml          # コールバック
│   ├── test_21_fix.ml               # fix キーワード
│   ├── test_22_input.ml             # read_line / parse_int / parse_f64（Result<T, string> 返し）
│   ├── test_23_static.ml            # static fn / :: 呼び出し / StaticMethodRef
│   ├── test_24_zero_div.ml          # ゼロ除算安全（checked_div・境界値分析）
│   ├── test_25_parse_result.ml      # parse_int / parse_f64 の Result 返し
│   ├── test_26_option.ml            # Option<T>（Some / None / match パターン）
│   ├── test_27_match_wildcard.ml    # match ワイルドカードパターン（_ 全面対応）
│   ├── test_28_box.ml               # Box<T>（生成・* deref・.unbox()・多重ポインタ）
│   ├── test_29_string_find.ml       # string.find()（Option<i32> 返し・各種パターン）
│   ├── test_30_string_split.ml      # string.split()（区切り文字・境界値・空文字）
│   ├── test_31_iter_linq.ml         # Iter<T> / LINQ 全 12 メソッド（C0/C1/MC/DC）
│   ├── test_32_iter_chain_free.ml   # チェーン中間 MrylVec のメモリ解放（#62）
│   ├── test_33_select_many.ml       # select_many C コード生成（#65、C0/C1/MC/DC）
│   ├── test_34_closure_capture.ml   # クロージャキャプチャ fat pointer（#44、C0/C1/MC/DC）
│   ├── test_35_box_free.ml          # Box<T> 自動 free（スコープ・return・ループ・多重・Vec<Box<T>>、#66）
│   ├── test_36_for_each_void_stmt.ml    # for_each void 文式・キャプチャあり fat pointer ラムダ（#64）
│   ├── test_37_iter_lambda_typecheck.ml # Iter<T> メソッドへのラムダ引数型検査（#63、C0/C1/MC/DC）
│   ├── test_38_async_result.ml          # async fn + Result<T,E> FAULTED 状態伝播（#51）
│   ├── test_39_toarray_free.ml          # to_array() 結果 MrylVec の自動 free（#71、C0/C1）
│   ├── test_40_struct_box_free.ml       # struct フィールド Box<T> free / Option<Box<T>> free（#67/#68）
│   ├── test_41_iter_string_deep_copy.ml # Iter<string> first()/filter()/skip() deep copy（#70）
│   ├── test_42_iter_lambda_param_count.ml # Iter<T> ラムダ引数数チェック（#69、C0）
│   ├── test_43_task_when_all_any.ml     # Task::when_all / Task::when_any コンビネータ（#61、C0/C1）
│   ├── test_44_async_cancel.ml          # weak / cancel Task キャンセル機構（#52、C0/C1）
│   ├── test_45_observable.ml            # Observable<T> / Subject<T> リアクティブストリーム（#45、C0/C1）
│   ├── test_46_array_literal_free.ml    # string[]/ArrayLiteral Vec 追跡・mryl_str_split 挿入位置修正（#78、C0/C1）
│   ├── test_47_aggregate_string.ml      # aggregate() string deep copy・ラムダ戻り値型推論（#81、C0）
│   ├── test_48_match_box_return.ml      # match Some(b) バインド変数の二重 free 修正（#79、C0）
│   ├── test_49_if_block_scope.ml        # if/else ブロック内リソーススコープ管理（#94、C0/C1）
│   ├── test_50_struct_destructor_order.ml # 相互参照 struct デストラクタ前方宣言（#80、C0）
│   ├── test_51_for_each_mutable_capture.ml # for_each ラムダ内ミュータブルキャプチャ（#83、C0/C1）
│   ├── test_52_string_vec_free.ml       # string[] 要素 char* 解放・iter 系 Vec 二重 free 修正（#96/#97、C0/C1）
│   ├── test_53_task_result_combinator.ml # Task::when_all/any の Result<T,E> タスク対応（#84、C0/C1）
│   └── test_54_multidim_array.ml        # 多次元配列 i32[][]・f64[][]・bool[][]・string[][]・i32[][][]（#82、C0/C1）
├── my/                               # 動作確認用 Mryl コード置き場
├── bin/
│   ├── Mryl.c                # 生成された C ソースコード
│   └── Mryl.exe              # コンパイル済みバイナリ
└── doc/
    ├── readme.md             # 言語リファレンス（ユーザー向け）
    ├── mryl_specification.md # この開発者仕様書
    ├── UNIT_TEST_SPEC.md     # 単体テスト仕様書（C0/C1/MC/DC）
    └── ASYNC_REDESIGN.md     # async/await 設計資料
```

---

## 実装機能

### 3.1 基本型

| 型 | 説明 | C 対応 |
|---|---|---|
| `i8, i16, i32, i64` | 符号付き整数 | `int8_t`, `int16_t`, `int32_t`, `int64_t` |
| `u8, u16, u32, u64` | 符号なし整数 | `uint8_t`, `uint16_t`, `uint32_t`, `uint64_t` |
| `f32, f64` | 浮動小数点数 | `float`, `double` |
| `string` | 文字列 | `MrylString` (struct) |
| `bool` | ブール値 | `int` (1/0) |
| `T[]` | 1次元動的配列 | `MrylVec_T` struct |
| `T[][]` / `T[][][]` | 多次元動的配列（N次元対応） | `MrylVec_MrylVec_T` 等（入れ子 struct） |

### 3.2 const 定数

| 機能 | 説明 |
|------|------|
| `const NAME = expr` | コンパイル時定数の宣言 |
| const 式評価 | 算術・論理・ビット演算対応 |
| const 参照 | 関数内で const を変数として参照可能 |
| C コード生成 | `#define NAME value` で生成 |

### 3.3 fix キーワード（不変変数・不変引数）

| 機能 | 説明 |
|------|------|
| `fix x: T = expr` | 不変変数の宣言 |
| `fix x = expr` | 不変変数（型推論） |
| `fn f(fix a: T, b: T)` | `a` は不変、`b` は可変の混在引数 |
| `(fix x: T) => expr` | ラムダの不変パラメータ |
| 変量への再代入 | 型チェッカー時に `TypeError` |

### 3.4 ラムダ式

| 機能 | 説明 |
|------|------|
| `(パラメータ) => 式` | 単一式ボディのラムダ式 |
| `(パラメータ) => { 文; ... }` | 複数ステートメントを持つブロックボディのラムダ式 |
| `async (パラメータ) => { 文; ... }` | async ラムダ式（`MrylTask*` を返す） |
| 型注釈対応 | パラメータに `: T` で型を指定可能 |
| `fn` 型 | 演算が展開する内部型 (`fn(i32)->i32` 等) |
| ブロックボディの戻り値型 | `return` 文なし → `void`、あり → 式の型を自動推論 |
| C コード生成（同期） | `static 型 __lambda_N(パラメータ)` + 型付き関数ポインタ |
| C コード生成（async） | SM 構造体 + `move_next` 関数 + ファクトリ関数として展開 |

### 3.5 async / await

| 機能 | 説明 |
|------|------|
| `async fn name(パラメータ) -> T` | 非同期関数の定義 |
| `let h = asyncFn(args)` | 即時起動、`Future<T>` 型のハンドルを返す |
| `let v: T = await h` | 完了待機 + 戻り値取得 |
| `await h` | void 非同期の完了待機 |
| `Future<T>` | 非同期タスクの型。C コードでは `MrylTask*` |
| `WeakTask<T>` | Task への弱参照型。C コードでは `MrylTask*`（weak_count で管理）|
| `weak(handle)` | `Future<T>` から `WeakTask<T>` を取得する組み込み式 |
| `cancel(token)` | `WeakTask<T>` 経由で Task をキャンセルする組み込み関数 |
| C コード生成 | SM 構造体 + `move_next` 関数 + ファクトリ関数 + スケジューラ |

#### Task コンビネータ（v0.6.0、Result 対応: v0.7.0）

複数の `Future<T>` を同時に待機する静的メソッド群。

| API | シグネチャ | 説明 |
|-----|-----------|------|
| `Task::when_all` | `([t1, t2, ...]: Future<T>[]) -> Future<T[]>` | 全タスク完了後に結果配列を返す（C# `Task.WhenAll` 相当） |
| `Task::when_any` | `([t1, t2, ...]: Future<T>[]) -> Future<T>` | 最初に完了したタスクの結果を返す（C# `Task.WhenAny` 相当） |

**使用例（primitive 型）:**
```mryl
let t1 = fetch(1);
let t2 = fetch(2);
let results: i32[] = await Task::when_all([t1, t2]);  // [result1, result2]
let first: i32     = await Task::when_any([t1, t2]);  // 最初に完了した値
```

**使用例（Result<T,E> 型、v0.7.0）:**
```mryl
async fn fetch_ok(v: i32) -> Result<i32, string> { return Ok(v * 2); }
async fn fetch_err(msg: string) -> Result<i32, string> { return Err(msg); }

fn main() {
    // when_all: Ok/Err 混在でも全結果を収集（Result がエラーをラップ）
    let results: Result<i32, string>[] = await Task::when_all([fetch_ok(5), fetch_err("oops")]);
    println("{}", results.len());   // 2
    match results[1] {
        Ok(v)  => println("ok: {}", v),
        Err(e) => println("err: {}", e),   // err: oops
    };

    // when_any: 最初に完了したタスクの Result を取得（Err タスクも値として受け取れる）
    let r: Result<i32, string> = await Task::when_any([fetch_err("fail")]);
    match r {
        Ok(v)  => println("ok: {}", v),
        Err(e) => println("err: {}", e),   // err: fail
    };
}
```

**制限:**
- 要素型 `T` は `void` 不可（`void` Task のコンビネータ非対応）
- 全要素が同一型 `T` であること（混在型不可）
- `Result<T,E>[]` 配列リテラルの直接記述は未対応（issue #99）

#### Task キャンセル（v0.6.0）

`weak(handle)` で `Future<T>` への弱参照 `WeakTask<T>` を取得し、`cancel(token)` でキャンセルする。

```mryl
async fn long_task(n: i32) -> i32 { return n * 2; }

fn main() {
    let handle = long_task(42);
    let token: WeakTask<i32> = weak(handle);  // 弱参照取得

    cancel(token);  // Task をキャンセル（handle は await しない）
}
```

**設計規約:**
- キャンセルは「Task を捨てる」操作。キャンセル後は `handle` を `await` しない
- `cancel()` は冪等（完了済み・キャンセル済みの Task に対して何もしない）
- `WeakTask<T>` は `await` 不可（TypeChecker でエラー）

**タイムアウトパターン（`when_any` との組み合わせ）:**
```mryl
let handle = long_process();
let timer  = delay(5000);
let tok_h: WeakTask<i32> = weak(handle);

let _: i32 = await Task::when_any([handle, timer]);
cancel(tok_h);  // タイムアウトした場合に handle をキャンセル
```

**C コード生成:**
| Mryl 構文 | 生成 C コード |
|-----------|-------------|
| `weak(handle)` | `__task_weak_retain(handle)` |
| `cancel(token)` | `__task_cancel(token)` |
| `WeakTask<T>` 型 | `MrylTask*` |

### 3.6 Observable\<T\> / Subject\<T\>（リアクティブストリーム、v0.6.0）

C# Rx.NET と同じパイプライン設計のリアクティブストリーム。

| 型 / 概念 | 説明 |
|-----------|------|
| `Subject<T>` | イベントの発信源。subscribe の登録先 |
| `Observable<T>` | パイプライン（filter/map 等の変換後のストリーム） |
| `Subscription` | 購読を管理するハンドル。`unsubscribe()` で解除 |

**Subject<T> API:**

| 式 / 文 | 説明 |
|---------|------|
| `Subject<T>::new()` | 新しい Subject を作成（C: `mryl_subject_T_new()`） |
| `s.emit(val)` | 購読者全員に値を送信 |
| `s.complete()` | 完了通知（以降の emit 無視） |
| `s.error(msg)` | エラー通知（以降の emit 無視） |
| `s.subscribe(on_next)` | 購読登録（`Subscription` 返し） |
| `s.subscribe(on_next, on_error, on_complete)` | 3 ハンドラ版 |
| `s.filter(pred)` | 述語を満たす値のみ通過する `Observable<T>` |
| `s.map(mapper)` | 値を変換した `Observable<T>` |
| `s.take(n)` | 先頭 n 件のみ通過する `Observable<T>` |
| `s.skip(n)` | 先頭 n 件をスキップする `Observable<T>` |
| `s.merge(other)` | 2 ソースを合流する `Observable<T>` |
| `sub.unsubscribe()` | 購読解除（C: `mryl_subscription_unsubscribe(sub)`） |

**型パラメータ T:** 数値型・`string`・ユーザー定義 `struct` に対応。

**C コード生成:** モノモーフ化方式。`Subject<i32>` → `MrylSubject_i32*` として型ごとに展開。  
オペレータは新しい Subject を生成して上流に subscribe 登録するパイプライン方式。

```mryl
let s: Subject<i32> = Subject<i32>::new();
let obs: Observable<i32> = s
    .filter((x: i32) => { return x > 0; })
    .map((x: i32)    => { return x * 10; });
let sub: Subscription = obs.subscribe((x: i32) => { println("{}", x); });
s.emit(-1);  // スキップ
s.emit(3);   // 30
sub.unsubscribe();
```

**制限（v0.6.0）:**
- `debounce()` / `next_async()` オペレータは v0.7.0 候補（issue 化済み）
- Subject のバックプレッシャー制御なし

### 3.8 条件付きコンパイル

| ディレクティブ | 説明 | 例 |
|----------|------|-----|
| `#ifdef NAME` | const が定義されている場合 | `#ifdef DEBUG` |
| `#ifndef NAME` | const が未定義の場合 | `#ifndef PRODUCTION` |
| `#if EXPR` | const 式を評価 | `#if OPTIMIZATION_LEVEL > 1` |
| `#endif` | ブロック終了 | - |
| `#else` | else 分岐 | - |

**処理フロー:**
- Lexer でディレクティブトークン認識
- Parser で ConditionalBlock AST 構築
- CodeGenerator で条件評価 → 該当ブロックのみコンパイル

### 3.9 数値型型昇格システム

二項演算で型が異なる場合、自動的に上位の型に昇格：

```
昇格ルール:
- 符号付き: i8 < i16 < i32 < i64
- 符号なし: u8 < u16 < u32 < u64
- 浮動小数点: f32 < f64
- 整数 + 浮動小数点 → 浮動小数点 (f64)
- 例: i32 + f32 → f64, u16 + u64 → u64
```

### 3.10 fn 型パラメータ（高階関数・コールバック）

| 機能 | 説明 |
|------|------|
| `fn f(cb: fn(i32) -> i32, x: i32) -> i32` | 関数型パラメータの定義 |
| `fn f(cb: fn(i32, i32) -> i32, ...)` | 複数パラメータの関数型 |
| `fn f(cb: fn(i32) -> void, ...)` | void 戻り値の関数型 |
| ラムダ変数を渡す | `apply(double, 5)` — ラムダをコールバックとして渡す |
| 名前付き関数を渡す | `apply(my_func, 5)` — 定義済み関数を渡す |
| C コード生成 | `MrylFn_*` fat pointer 構造体（`{fn_ptr, env}`）。名前付き関数を渡す場合は `void* __e` 付き thunk を自動生成して fat pointer でラップ |

### 3.11 static fn（静的メソッド）

| 機能 | 説明 |
|------|------|
| `static fn name(params) -> T` | impl ブロック内に宣言する静的メソッド |
| `TypeName::method(args)` | 静的メソッド呼び出し（`::` 演算子） |
| `TypeName::method` | fn 型変数への参照（括弧なし） |
| `self` 禁止 | static fn 内で `self` を使用するとコンパイルエラー |
| 同 struct の他 static fn 呼び出し | `Counter::other()` のように内部から呼び出し可能 |
| C コード生成 | `StructName_method(params)`（self なし通常関数） |
| fn 型変数への代入 | `Counter::zero` → C では `Counter_zero`（関数ポインタ） |

### 3.10 前方宣言

| 機能 | 説明 |
|------|------|
| `fn name(params) -> T;` | 関数の前方宣言（ボディなし） |
| 相互再帰 | `is_even` / `is_odd` のように互いを呼び合う関数の記述 |
| C コード生成 | 関数定義の前にプロトタイプ宣言を出力 |

### 3.11 string 操作

#### エスケープシーケンス

文字列リテラル内で以下のエスケープシーケンスが使用できます。

| シーケンス | 意味 |
|---|---|
| `\n` | 改行（LF） |
| `\t` | タブ |
| `\r` | キャリッジリターン |
| `\"` | ダブルクォート |
| `\\` | バックスラッシュ |

### 3.12 Option\<T\>（安全な省略可能値）

| 機能 | 説明 |
|------|------|
| `Some(v)` | 値 `v` を持つ Option 値の生成 |
| `None` | 値なし Option 値の生成 |
| `match opt { Some(v) => ..., None => ... }` | パターンマッチによる値の取り出し |
| 関数引数・戻り値 | `Option<T>` 型の受け渡し・返却 |
| TypeChecker | `Some` → `Option<推論型>`、`None` → `Option<_>`（文脈から解決） |
| CodeGenerator | 組み込み union 型 `Mryl_Option_T` に展開 |

### 3.13 Box\<T\>（ヒープポインタ）

| 機能 | 説明 |
|------|------|
| `Box::new(v)` | 値 `v` をヒープに確保し `Box<T>` を返す |
| `*b` | デリファレンス（`UnaryOp("deref")`） |
| `b.unbox()` | `.unbox()` メソッド — `*b` と等価 |
| `Box<Box<T>>` | 多重ポインタ（2〜4 重以上） |
| 自動 free（スコープ終了） | スコープ末尾で `local_box_vars` を逆順に `free` |
| 自動 free（return） | `return` 前に `local_box_vars` / `local_box_vec_vars` を逆順に `free` |
| 自動 free（ループ） | while / for の各イテレーション末に `_emit_loop_iteration_cleanup` で free |
| `Box<Box<T>>` inner_moved | `let X: Box<T> = *Y` パターンで `Y` を `box_inner_moved` にマーク → `free(Y)` のみ（二重 free 防止） |
| `Box<T>[]`（`Vec<Box<T>>`） | 要素ごと free 後に `.data` を free（`_emit_box_vec_free`） |
| struct Box フィールド自動デストラクタ | Box フィールドを持つ struct に `mryl_free_StructName()` を自動生成。ネスト struct は再帰呼び出し。`_struct_has_box_fields()` で循環参照防止付き判定 |
| struct Box フィールド自動 free | struct 変数をスコープ終了・return・ループイテレーション末に `mryl_free_StructName()` で解放（`local_struct_box_vars` で追跡）。VarRef フィールドは所有権移動とみなし double free 防止 |
| `Option<Box<T>>` 自動 free | `Option<Box<T>>` 変数を `local_option_box_vars` で追跡。スコープ終了・return 時に `if(has_value) free(value)` を emit |
| TypeChecker | `Box<T>` → `TypeNode("Box", type_args=[inner])` |
| CodeGenerator | `Box<T>` → `T*`、`Box::new(v)` → `({ T* p = malloc(sizeof(T)); *p = v; p; })` |
| ユーザー定義構造体との共存 | `generate()` 開始時に `has_user_box` をキャッシュ。`struct Box` が存在する場合は組み込み Box を無効化 |

#### 演算子

| 機能 | 説明 |
|------|------|
| `a + b` | string 連結（`mryl_string_concat` で展開） |
| `a == b` | string 比較（`strcmp` で展開） |
| `a != b` | string 非等比較 |
| 関数引数・戻り値 | `string` 型の受け渡し・返却 |

#### 組み込みメソッド（v0.3.0 #11 / v0.4.0 #54 #55）

| メソッド | 引数 | 戻り値 | C 展開先 |
|----------|------|--------|----------|
| `s.len()` | — | `i32` | `mryl_str_len(s)` |
| `s.contains(sub)` | `string` | `bool` | `mryl_str_contains(s, sub)` |
| `s.starts_with(pre)` | `string` | `bool` | `mryl_str_starts_with(s, pre)` |
| `s.ends_with(suf)` | `string` | `bool` | `mryl_str_ends_with(s, suf)` |
| `s.trim()` | — | `string` | `mryl_str_trim(s)` |
| `s.to_upper()` | — | `string` | `mryl_str_to_upper(s)` |
| `s.to_lower()` | — | `string` | `mryl_str_to_lower(s)` |
| `s.replace(from, to)` | `string, string` | `string` | `mryl_str_replace(s, from, to)` |
| `s.find(pat)` | `string` | `Option<i32>` | `mryl_str_find(s, pat)` |
| `s.split(sep)` | `string` | `string[]` | `mryl_str_split(s, sep)` → `MrylVec_MrylString` |

すべてのメソッドは `_header.py` が生成するインライン C ヘルパー関数へ展開されます。

### 3.14 Iter\<T\>（LINQ スタイルコレクション操作）（v0.4.0 #43 / v0.5.0 #65 #62）

配列（`T[]`）に対して C# LINQ 準拠のメソッドチェーンでコレクション操作を記述できる型。
内部的には `TypeNode("Iter", type_args=[T])` として表現し、`array_size=-1` で既存の動的配列ブランチと統一。

#### 中間操作（Iter\<T\> を返す）

| メソッド | 引数型 | 戻り値型 | C# 対応 |
|---|---|---|---|
| `select(fn)` | `fn(T) -> U` | `Iter<U>` | `Select` |
| `filter(fn)` | `fn(T) -> bool` | `Iter<T>` | `Where` |
| `take(n)` | `i32` | `Iter<T>` | `Take` |
| `skip(n)` | `i32` | `Iter<T>` | `Skip` |
| `select_many(fn)` | `fn(T) -> U[]` | `Iter<U>` | `SelectMany`（v0.5.0 #65） |

#### 終端操作

| メソッド | 引数型 | 戻り値型 | C# 対応 |
|---|---|---|---|
| `to_array()` | — | `T[]` | `ToArray` |
| `aggregate(fn)` | `fn(T,T) -> T` | `Result<T, string>` | `Aggregate`（初期値なし）|
| `aggregate(init, fn)` | `U, fn(U,T) -> U` | `U` | `Aggregate`（初期値あり）|
| `for_each(fn)` | `fn(T) -> void` | `void` | `ForEach`（副作用専用・文としてのみ使用可） |
| `count()` | — | `i32` | `Count` |
| `first()` | — | `Result<T, string>` | `First` |
| `any(fn)` | `fn(T) -> bool` | `bool` | `Any` |
| `all(fn)` | `fn(T) -> bool` | `bool` | `All` |

#### 実装詳細

| 層 | 実装方針 |
|---|---|
| Interpreter | Python list comprehension / スライスで中間値を表現 |
| TypeChecker | `_check_iter_method` で型規則を管理（`core/TypeChecker/_call.py`） |
| CodeGenerator（`for_each` 以外） | GCC statement expression `({ ... })` でインライン生成（`_expr.py`） |
| CodeGenerator（`for_each`） | 通常ブロック `{ ... }` として生成（GCC 拡張不使用）（`_expr.py`） |
| CodeGenerator（型推論） | `vec_` prefix で iter メソッド戻り値型を推論（`_generic.py`） |

#### `for_each` の制約

`for_each` は戻り値が `void` の副作用専用操作であり、**文としてのみ使用可能**。
TypeChecker が以下をコンパイルエラーとして検出する：

```mryl
let x = arr.for_each(...);    // NG: void を let に代入
fix x = arr.for_each(...);    // NG: void を fix に代入
x = arr.for_each(...);        // NG: void を代入
return arr.for_each(...);     // NG: void を return
arr.for_each(...);            // OK: 文として使用
```

#### 既知の制限

| 制限 | issue | 状態 |
|---|---|---|
| `select_many` C コード生成未実装（`NotImplementedError`） | `issue_iter_select_many_codegen.md` | ✅ v0.5.0 #65 解決 |
| 中間 `MrylVec` のメモリリーク | `issue_iter_intermediate_memleak.md` | ✅ v0.5.0 #62 解決 |
| `for_each` void statement expression の GCC 拡張依存 | `issue_iter_for_each_void_stmtexpr.md` | ✅ v0.5.0 #64 解決 |
| ラムダ引数型検査が浅い | `issue_iter_lambda_typecheck_shallow.md` | ⚠️ #63 未対応 |
| ラムダ引数数チェック未実装 | `issue_iter_lambda_param_count.md` | ✅ v0.6.0 #69 解決 |
| `for_each` ラムダ内ミュータブルキャプチャ非対応 | `issue_for_each_mutable_capture.md` | ✅ v0.7.0 #83 解決 |
| iter 系 `MrylVec` 二重 free | `issue_iter_vec_double_free.md` | ✅ v0.7.0 #96 解決 |
| `string[]` 要素 `char*` のメモリリーク | `issue_vec_string_elem_not_freed.md` | ✅ v0.7.0 #97 解決 |
| `Task::when_all/any` で `Result<T,E>` タスク非対応 | — | ✅ v0.7.0 #84 解決 |
| 多次元配列（`i32[][]` 以上）未対応 | `issue_2d_array_unsupported.md` | ✅ v0.7.0 #82 解決 |
| 多次元配列の固定長形式（`T[3][4]` 等）未対応 | — | ⚠️ 将来対応 |
| 多次元配列の型チェックが次元数のみ検証（要素型の厳密チェックなし） | — | ⚠️ 将来対応 |
| `Result<T,E>[]` 配列リテラル未対応 | `issue_result_array_literal.md` | ⚠️ #99 将来対応 |
| 型パラメータキーエンコーディング一般化 | `issue_type_key_generalization.md` | ⚠️ 将来対応 |
| `select_many` VarRef ラムダ時の所有権 | — | ⚠️ 将来の所有権機能で対応予定 |

---

## 演算子

### 演算子優先順位（高→低）

```
優先度  演算子                        結合性   説明
───────────────────────────────────────────────────────────────────────
 1     [] . () post++ post--   左    配列インデックス、メンバアクセス、関数呼び出し、後置インクリ
 2     ! ~ ++ -- (prefix)      右    単項 NOT、ビット反転、前置インクリメント
 3     * / %                   左    乗算、除算、剰余
 4     + -                     左    加算、減算
 5     << >>                   左    ビットシフト
 6     < <= > >=               左    比較演算
 7     == !=                   左    等価演算
 8     &                       左    ビット AND
 9     ^                       左    ビット XOR
10     |                       左    ビット OR
11     &&                      左    論理 AND (短絡評価)
12     ||                      左    論理 OR (短絡評価)
13     = += -= *= /= %= <<= >>= ^=  右    代入（複合代入含む）
```

### 算術演算

```mryl
let a = 10 + 5;       // 加算 → 15
let b = 10 - 5;       // 減算 → 5
let c = 10 * 5;       // 乗算 → 50
let d = 10 / 5;       // 整数除算 → 2
let e = 10 % 3;       // 剰余 → 1
```

### 比較演算

```mryl
let a = 5 < 10;       // true
let b = 5 <= 5;       // true
let c = 10 > 5;       // true
let d = 10 >= 10;     // true
let e = 5 == 5;       // true
let f = 5 != 10;      // true
```

### 論理演算

```mryl
let a = true || false;    // OR → true
let b = true && true;     // AND → true
let c = !true;            // NOT → false

// ショートサーキット評価
let short_and = false && expensive_function();  // 右は評価されない
let short_or = true || expensive_function();    // 右は評価されない
```

**注**: &&と||は短絡評価される（右側が必要な場合のみ評価）

### ビット演算

```mryl
let x = 5;        // 0101
let y = 3;        // 0011

let and = x & y;  // 0001 → 1
let or = x | y;   // 0111 → 7
let xor = x ^ y;  // 0110 → 6
let lshift = x << 1;  // 1010 → 10
let rshift = x >> 1;  // 0010 → 2
let not = ~x;     // 反転 → -6 (2進補数)
```

### インクリメント・デクリメント

```mryl
let i = 5;
++i;              // Pre-increment: i を 6 にしてから 6 を返す
let j = i++;      // Post-increment: 6 を返してから i を 7 に
i--;              // Post-decrement: 7 を返してから i を 6 に
--i;              // Pre-decrement: i を 5 にしてから 5 を返す
```

### 複合代入演算子

```mryl
let n = 10;
n += 5;   // n = n + 5 → 15
n -= 3;   // n = n - 3 → 12
n *= 2;   // n = n * 2 → 24
n /= 3;   // n = n / 3 → 8
n %= 5;   // n = n % 5 → 3

let b = 8;
b <<= 1;  // b = b << 1 → 16
b >>= 2;  // b = b >> 2 → 4

let c = 12;
c ^= 5;   // c = c ^ 5 → 9
```

**内部処理**: 複合代入は Parser で自動的に二項演算に変換される
- `n += 5` → `n = (n + 5)`

---

## Const 定数とコンパイル時評価

### const 宣言

`const` キーワードでコンパイル時に評価される定数を宣言：

```mryl
const MAX_VALUE = 100;
const PI = 31415;
const OPTIMIZATION_LEVEL = 2;
const DEFAULT_SIZE = 256;
```

**特徴:**
- **グローバルスコープのみ**: const はプログラムの最上位で宣言
- **コンパイル時評価**: const 式はコンパイル時に完全に評価される
- **型推論**: リテラルから自動推論（i32 がデフォルト）
- **定数式**: 以下の式をサポート：
  - 数値リテラル、文字列リテラル、ブール値
  - 二項演算（+, -, *, /, %）
  - 比較演算（==, !=, <, >, <=, >=）
  - 論理演算（&&, ||, !）
  - ビット演算（&, |, ^, <<, >>）
  - 他の const への参照

### const 式の評価例

```mryl
const MAX = 100;
const DOUBLED = MAX * 2;        // 200（コンパイル時計算）
const RESULT = (100 + 50) / 3;  // 50（コンパイル時計算）

fn main() -> i32 {
    // const を変数として参照可能
    let x = MAX;                // x = 100
    let y = DOUBLED - 40;       // y = 160
    println(x);
    println(y);
    return 0;
}
```

### Interpreter と CodeGenerator での処理

```
Parser: const 宣言 → const_table に値をキャッシュ
TypeChecker: const 型検証 → const_table で型情報を保持
Interpreter: const の値を参照可能
CodeGenerator: const → #define ディレクティブで C コード生成
```

---

## 条件付きコンパイル

条件付きコンパイルディレクティブで、コンパイル時にコードをインクルード/除外：

### #ifdef - 定数定義チェック

```mryl
const DEBUG = 1;

#ifdef DEBUG
println(1);  // DEBUG が定義されていればコンパイルに含める
#endif
```

**動作:** DEBUG が const で定義されていれば then_block をコンパイル。定義されていなければスキップ。

### #ifndef - 定数未定義チェック

```mryl
#ifndef PRODUCTION
println(1);  // PRODUCTION が定義されていなければコンパイルに含める
#endif
```

**動作:** PRODUCTION が const で定義されていなければ then_block をコンパイル。定義されていればスキップ。

### #if - 定数式評価

```mryl
const OPTIMIZATION_LEVEL = 2;

#if OPTIMIZATION_LEVEL
println(1);  // ゼロ以外なら実行（OPTIMIZATION_LEVEL = 2）
#endif

#if OPTIMIZATION_LEVEL > 1
println(2);  // 式を評価（true）
#endif
```

**動作:** const 式をコンパイル時に評価。真なら then_block、偽なら else_block をコンパイル。

### #else による分岐

```mryl
const MODE = 1;

#ifdef DEBUG
println(10);  // DEBUG が定義されていれば
#else
println(20);  // DEBUG が未定義なら
#endif
```

### 条件付きコンパイルの実装詳細

```
Lexer: #ifdef, #ifndef, #if, #endif, #else トークン認識
Parser: ConditionalBlock AST ノード作成
TypeChecker: 両ブロックの型チェック
Interpreter: 条件評価 → 対応するブロック実行
CodeGenerator: 条件評価 → 対応するブロックのみ C コード生成
```

**例: C コード生成でのフィルタリング**

```mryl
const DEBUG = 1;

#ifdef DEBUG
printf("Debug\n");    // 含まれる
#endif

#ifdef PRODUCTION
printf("Production\n"); // 除外される
#endif
```

↓ 生成される C コード

```c
#define DEBUG 1
// ... 
printf("Debug\n");    // このコードのみ含まれる
```

---

## 型システム

### 型宣言

```mryl
let x: i32 = 10;
let y: f64 = 3.14;
let s: string = "hello";
let b: bool = true;
let arr: i32[5] = [1, 2, 3, 4, 5];
```

### 型推論

```mryl
let x = 10;           // i32と推論
let y = 3.14;         // f64と推論
let s = "hello";      // stringと推論
```

### 型キャスト

```mryl
let a = 5(u8);        // u8型のリテラル
let b = 100(i16);     // i16型のリテラル
let c = 3.14(f32);    // f32型のリテラル
```

---

## ジェネリック

### ジェネリック関数

```mryl
fn add<T>(a: T, b: T) -> T {
    return a + b;
}

// 使用例
let sum1 = add(5, 10);        // → add_i32 に単相化
let sum2 = add(3.14, 2.86);   // → add_f64 に単相化
let concat = add("a", "b");   // → add_string に単相化
```

### 複数の型パラメータ

```mryl
fn pair<T, U>(a: T, b: U) -> string {
    return to_string(a) + to_string(b);
}

let result = pair(5, "hello");  // → pair_i32_string に単相化
```

**実装詳細**:
- Parser で型パラメータを `<T, U>` の形式でパース
- TypeChecker でジェネリック関数の型チェック（制約緩い）
- CodeGenerator で単相化: 各型引数の組み合わせで別関数生成
  - `add_i32(int32_t a, int32_t b) → int32_t`
  - `add_f64(double a, double b) → double`
  - `add_string(MrylString a, MrylString b) → MrylString`

---

## 構造体とメソッド

### 構造体定義

```mryl
struct Point {
    x: i32,
    y: i32
}

struct Pair<T> {
    first: T,
    second: T
}
```

### メソッド定義

```mryl
impl Point {
    fn distance() -> i32 {
        return x + y;
    }
}

impl Pair<T> {
    fn get_first() -> T {
        return first;
    }
}
```

### 使用例

```mryl
let p = Point { x: 3, y: 4 };
let d = p.distance();  // → Point_distance(p) に変換 → 7

let pair = Pair { first: 10, second: 20 };
let x = pair.get_first();  // → Pair_T_get_first(pair)
```

### Box フィールドを持つ struct の自動デストラクタ

`Box<T>` 型フィールドを持つ struct に対し、コンパイラは `mryl_free_StructName()` を自動生成する。
struct 変数はスコープ終了・`return` 前・ループイテレーション末に自動解放される。

| 項目 | 内容 |
|------|------|
| デストラクタ生成条件 | `_struct_has_box_fields()` で Box フィールドの有無を再帰判定（循環参照防止付き） |
| Box フィールド | `free(s.field)` を emit |
| ネスト struct フィールド | `mryl_free_Inner(s.field)` を再帰的に emit |
| 追跡変数 | `local_struct_box_vars` で struct 変数を管理 |
| double free 防止 | `StructInit` での `VarRef` フィールドは所有権移動とみなし追跡対象から除外 |

```c
// 生成例
void mryl_free_Node(Node s) {
    free(s.data);
}
```

---

## static fn（静的メソッド）

`impl` ブロック内に `static fn` で宣言するメソッド。インスタンスではなく型そのものに属するため、`self` パラメータを持たない。

### 宣言と呼び出し

```mryl
struct Counter {
    value: i32;
}

impl Counter {
    static fn zero() -> Counter {
        return Counter { value: 0 };
    }

    static fn with_value(n: i32) -> Counter {
        return Counter { value: n };
    }

    fn increment(self) {
        self.value = self.value + 1;
    }
}

fn main() -> i32 {
    let c = Counter::zero();     // static fn 呼び出し
    c.increment();               // instance fn 呼び出し
    println("{}", c.value);      // 1
    return 0;
}
```

### fn 型変数への参照

```mryl
let f: fn() -> Counter = Counter::zero;   // 括弧なし = 参照
let c = f();

fn make(factory: fn() -> Counter) -> Counter {
    return factory();
}
let c2 = make(Counter::zero);             // コールバックとして渡す
```

### C コード変換

| Mryl | 生成 C コード |
|---|---|
| `static fn zero() -> Counter` 宣言 | `Counter Counter_zero()` |
| `Counter::zero()` | `Counter_zero()` |
| `Counter::zero`（単純参照） | `Counter_zero`（関数ポインタ） |
| `Counter::zero`（`fn()->Counter` 型引数・変数代入） | thunk + fat pointer `MrylFn_void_ret_Counter` |

> `fn(T)->U` 型パラメータへ渡す場合や `fn` 型変数へ代入する場合は、
> 統一的な fat pointer 規約（`MrylFn_*`）に合わせるため thunk ラッパーが自動生成されます。

---

## ラムダ式

### 基本構文

```mryl
// 単一式ボディ
let f = (パラメータ: 型) => 式;

// ブロックボディ（複数ステートメント）
let g = (パラメータ: 型) => {
    文;
    文;
};
```

### 使用例

```mryl
fn main() {
    // 単一パラメータ（単一式ボディ）
    let mul2 = (x: i32) => x * 2;
    let r1 = mul2(5);              // 10

    // 複数パラメータ（単一式ボディ）
    let add = (x: i32, y: i32) => x + y;
    let r2 = add(3, 7);            // 10

    // 比較式
    let is_positive = (n: i32) => n > 0;
    let r3 = is_positive(5);       // true (1)

    // ブロックボディ（複数ステートメント、戻り値 void）
    let process = (x: i32) => {
        let doubled = x * 2;
        let result  = doubled * 2;
        println(result);
    };
    process(3);                    // 12
    process(5);                    // 20

    // ブロックボディ（return 文あり、戻り値型を自動推論）
    let compute = (x: i32) => {
        let doubled = x * 2;
        let result  = doubled + 10;
        return result;
    };
    let r1 = compute(3);           // 16
    let r2 = compute(5);           // 20
}
```

### 型システム

- ラムダ変数の型は内部的に `fn` 型として扱われる
- TypeChecker が引数・戻り値の型を推論し `fn(i32, i32) -> i32` 形式で保持
- ブロックボディの場合、`return` 文をスキャンして戻り値型を自動推論する（`return` なしは `void`）

### C コード生成

**単一式ボディ**

```c
// ラムダ → static 関数 + 型付き関数ポインタ
static int32_t __lambda_0(int32_t x) {
    return (x * 2);
}

int main(void) {
    int32_t (*mul2)(int32_t) = __lambda_0;
    int32_t r1 = mul2(5);   // 10
}
```

**ブロックボディ — void（`return` なし）**

```c
static void __lambda_0(int32_t x) {
    int32_t doubled = (x * 2);
    int32_t result = (doubled * 2);
    printf("%d\n", result);
}

int main(void) {
    void (*process)(int32_t) = __lambda_0;
    process(3);   // 12
    process(5);   // 20
}
```

**ブロックボディ — 戻り値あり（`return` 文から型を自動推論）**

```c
static int32_t __lambda_1(int32_t x) {
    int32_t doubled = (x * 2);
    int32_t result = (doubled + 10);
    return result;
}

int main(void) {
    int32_t (*compute)(int32_t) = __lambda_1;
    int32_t r1 = compute(3);   // 16
    int32_t r2 = compute(5);   // 20
}
```

**static 関数の挿入位置**: 最初の関数定義の直前

**クロージャキャプチャ（fat pointer 方式）**

外部変数を参照するラムダは、キャプチャ変数を保持する環境構造体と関数ポインタをペアにした fat pointer として生成されます。

```mryl
fn make_adder(n: i32) -> fn(i32) -> i32 {
    return (x: i32) => x + n;  // n をキャプチャ
}
```

```c
// キャプチャ変数を保持する環境構造体
typedef struct { int32_t n; } __lambda_0_env_t;

// 第1引数に env_ptr を受け取るラムダ本体
static int32_t __lambda_0(void* env_ptr, int32_t x) {
    __lambda_0_env_t* __env = (__lambda_0_env_t*)env_ptr;
    return (x + __env->n);
}

// fat pointer 型（関数ポインタ + 環境ポインタのペア）
typedef struct { int32_t (*fn)(void*, int32_t); void* env; } MrylClosure_i32_i32;

int32_t make_adder_result_call(MrylClosure_i32_i32 c, int32_t x) {
    return c.fn(c.env, x);
}
```

- キャプチャ変数がない通常ラムダは fat pointer を使わず、従来の関数ポインタのみで生成されます。

### Python インタプリタでの動作

クロージャとして実装 — 宣言時点の環境をキャプチャした辞書 `{'__lambda__': True, 'params', 'body', 'captured_env'}` として保存。

### async ラムダ式

`async` キーワードを付けて宣言する非同期ラムダ式です。

**構文**：

```mryl
let 変数名 = async (パラメータ: 型) => {
    // 非同期ボディ（await を内包可能）
};
await 変数名(引数);
```

**使用例**（ボディ内 await なし）：

```mryl
fn main() {
    let greet = async (x: i32) => {
        println(x);
    };
    await greet(42);       // 42
}
```

**使用例**（ボディ内 await あり）：

```mryl
async fn double(n: i32) -> i32 {
    return n * 2;
}

fn main() {
    let compute = async (x: i32) => {
        let result = await double(x);
        println(result);
    };
    await compute(5);      // 10
}
```

**C コード生成**：

async ラムダは `async fn` と同様にステートマシン（SM）として展開されます：

```c
// ===== Async Lambda state machines =====
typedef struct { int state; int32_t x; } __lambda_0_sm_t;
static int __lambda_0_move_next(__lambda_0_sm_t* sm, MrylTask* task) { ... }
static MrylTask* __lambda_0_factory(int32_t x) { ... }

int main(void) {
    MrylTask* (*greet)(int32_t) = __lambda_0_factory;
    MrylTask* __h0 = greet(42);
    mryl_scheduler_run();
}
```

**特徴**：

| 項目 | 内容 |
|------|------|
| 戻り値型 | `MrylTask*` |
| 呼び出し方法 | `await 変数(引数)` で待機・実行 |
| ボディ内 await | `await` を使用して他の async 関数/ラムダを待機可能 |
| 制限 | ブロックボディ `{ }` のみサポート（単一式ボディ不可） |
| Python モード | `asyncio.create_task()` でコルーチンとして実行 |

---

## async / await

### 非同期関数の定義

```mryl
async fn compute_sum(n: i32) -> i32 {
    let result: i32 = n * n;
    return result;
}

async fn print_message() {
    println("Hello from async function!");
}
```

### 呼び出しと await

```mryl
fn main() {
    // 非同期タスクを起動 → スケジューラへ POST、MrylTask* を返す
    let handle = compute_sum(7);

    // 完了待機 + 戻り値取得
    let result: i32 = await handle;    // 49
    println("{}", result);

    // void 非同期の await
    let h2 = print_message();
    await h2;
}
```

### async fn と Result\<T,E\>

`async fn` の戻り値に `Result<T,E>` を指定できます。

| 返値 | タスク状態 |
|------|-----------|
| `Ok(v)` | `MRYL_TASK_COMPLETED` |
| `Err(e)` | `MRYL_TASK_FAULTED` |

`await` の停止条件は `state == COMPLETED || state == FAULTED` です。
どちらの場合も `MrylTask*.result` に `Result` 値がヒープ確保され、呼び出し元で `match` により取得できます。

```mryl
async fn fetch(url: string) -> Result<string, string> {
    if (url == "") {
        return Err("empty url");
    }
    return Ok("data received");
}

fn main() {
    let r: Result<string, string> = await fetch("");
    match r {
        Ok(v)  => println("ok: {}", v),
        Err(e) => println("err: {}", e),   // "err: empty url"
    };
}
```

### アーキテクチャ

Mryl の async/await は **C# 風の状態機械 + シングルスレッドスケジューラ** で実装されます。
pthreads、OS スレッド、外部ライブラリは不要です。

```
async fn  →  SM 構造体 + move_next 関数 + ファクトリ関数
fn main() →  SM 構造体 + move_next 関数 + main エントリポイント
await     →  awaiter 設定 + 中断点記録 + 再 POST で再開
```

### MrylTask 構造体と状態

```c
typedef enum {
    MRYL_TASK_PENDING,    // 未開始
    MRYL_TASK_RUNNING,    // 実行中
    MRYL_TASK_COMPLETED,  // 正常完了（Ok 含む）
    MRYL_TASK_CANCELLED,  // キャンセル済み
    MRYL_TASK_FAULTED     // エラー完了（async fn が Err を返した場合）
} MrylTaskState;

typedef struct MrylTask {
    int           strong_count;  // 強参照カウント（所有権）
    int           weak_count;    // 弱参照カウント（キャンセルトークン）
    MrylTaskState state;         // PENDING / RUNNING / COMPLETED / CANCELLED / FAULTED(Err返却時)
    void*         result;        // 戻り値（ヒープ確保 void*）
    void        (*move_next)(struct MrylTask*);
    void        (*on_cancel)(struct MrylTask*);
    void*         sm;            // SM 構造体ポインタ
    struct MrylTask* awaiter;    // 完了時に再開するタスク
} MrylTask;
```

### スケジューラ

```c
#define __SCHEDULER_CAP 65536
typedef struct {
    MrylTask* queue[__SCHEDULER_CAP];
    int head, tail;
} MrylScheduler;

static MrylScheduler __scheduler;

static inline void __scheduler_init(void) { __scheduler.head = __scheduler.tail = 0; }
static inline void __scheduler_post(MrylTask* t) {
    __scheduler.queue[__scheduler.tail++ % __SCHEDULER_CAP] = t;
}
static inline void __scheduler_run(void) {
    while (__scheduler.head != __scheduler.tail) {
        MrylTask* t = __scheduler.queue[__scheduler.head++ % __SCHEDULER_CAP];
        if (t->state != MRYL_TASK_CANCELLED) t->move_next(t);
    }
}
```

- **シングルスレッド**、ロックフリー、静的循環バッファ（最大 65536 タスク）
- `move_next()` が `return` すると制御がスケジューラに返り次のタスクを処理
- `await` で中断したタスクは、被待機タスクの完了時に `awaiter` 経由で再 POST

### 参照カウント（メモリ管理）

| イベント | `strong_count` 変化 |
|---------|--------------------|
| ファクトリ生成 | `= 1` |
| 呼び出し元 `__task_retain()` | `+1 → 2` |
| SM 完了時 `__task_release()` | `-1 → 1` |
| `await` 後 `__task_release()` | `-1 → 0 → free` |
| `main()` タスク生成時 | `= 2`（SM 完了で 1、`scheduler_run` 後の明示 release で 0）|

弱参照は `__task_weak_retain()` / `__task_weak_release()` で管理。  
`__task_lock()` で弱参照から強参照に昇格（CANCELLED/COMPLETED なら `NULL`）。

### C コード生成の詳細（`test_async.ml` より）

#### SM 構造体とファクトリ（`compute_sum`）

```c
// SM 構造体：パラメータ + ローカル変数 + __state + __task
typedef struct {
    int __state;
    int32_t n;          // パラメータ
    int32_t result;     // ローカル変数
    MrylTask* __task;
} __ComputeSum_SM;

// move_next 関数（goto-dispatch）
void __compute_sum_move_next(MrylTask* __task) {
    __ComputeSum_SM* __sm = (__ComputeSum_SM*)__task->sm;
    if (__task->state == MRYL_TASK_CANCELLED) return;
    switch (__sm->__state) {
        case 0: goto __state_0;
        default: return;
    }
    __state_0: {
        __sm->result = (__sm->n * __sm->n);
        int32_t* __res = (int32_t*)malloc(sizeof(int32_t));
        *__res = __sm->result;
        __task->result = (void*)__res;
        __task->state = MRYL_TASK_COMPLETED;
        __task_release(__task);               // strong 2→1
        if (__task->awaiter) __scheduler_post(__task->awaiter); // main を再開
        return;
    }
}

// ファクトリ関数
MrylTask* compute_sum(int32_t n) {
    MrylTask* __task = (MrylTask*)malloc(sizeof(MrylTask));
    __ComputeSum_SM* __sm = (__ComputeSum_SM*)malloc(sizeof(__ComputeSum_SM));
    memset(__sm, 0, sizeof(__ComputeSum_SM));
    __sm->n = n;
    __sm->__task      = __task;
    __task->strong_count = 1;   // ファクトリ所有分
    __task->state        = MRYL_TASK_PENDING;
    __task->move_next    = __compute_sum_move_next;
    __task->sm           = __sm;
    __scheduler_post(__task);
    return __task;
}
```

#### main() の状態機械（2 つの await = 3 状態）

```c
typedef struct {
    int __state;
    MrylTask* handle;   // compute_sum(7) の結果
    int32_t result;     // await handle の結果
    MrylTask* h2;       // print_message() の結果
    MrylTask* __task;
} __Main_SM;

void __main_move_next(MrylTask* __task) {
    __Main_SM* __sm = (__Main_SM*)__task->sm;
    if (__task->state == MRYL_TASK_CANCELLED) return;
    switch (__sm->__state) {
        case 0: goto __state_0;
        case 1: goto __state_1;
        case 2: goto __state_2;
        default: return;
    }
    __state_0: {  // 初期: compute_sum 起動 + await 設定
        __sm->handle = compute_sum(7);
        __task_retain(__sm->handle);               // strong 1→2
        __sm->handle->awaiter = __task;            // 完了時 main を再開
        if (__sm->handle->state != MRYL_TASK_COMPLETED) {
            __sm->__state = 1; return;             // 中断:
        }
        goto __state_1;
    }
    __state_1: {  // compute_sum 完了後: 結果取得 + print_message 起動
        if (__sm->handle->state == MRYL_TASK_CANCELLED) {
            __sm->result = 0;
        } else {
            __sm->result = *(int32_t*)__sm->handle->result;
        }
        __task_release(__sm->handle);              // strong 2→1→0→free
        println("%d", __sm->result);
        __sm->h2 = print_message();
        __task_retain(__sm->h2);
        __sm->h2->awaiter = __task;
        if (__sm->h2->state != MRYL_TASK_COMPLETED) {
            __sm->__state = 2; return;
        }
        goto __state_2;
    }
    __state_2: {  // print_message 完了後: main 終了
        __task_release(__sm->h2);
        __task->state = MRYL_TASK_COMPLETED;
        __task_release(__task);                    // strong 2→1
        if (__task->awaiter) __scheduler_post(__task->awaiter);
        return;
    }
}

int main(void) {
    __scheduler_init();
    MrylTask* __main_task = (MrylTask*)malloc(sizeof(MrylTask));
    __Main_SM* __main_sm  = (__Main_SM*)malloc(sizeof(__Main_SM));
    memset(__main_sm, 0, sizeof(__Main_SM));
    __main_sm->__task        = __main_task;
    __main_task->strong_count = 2;           // main が 2 持つ
    __main_task->move_next    = __main_move_next;
    __main_task->sm           = __main_sm;
    __scheduler_post(__main_task);
    __scheduler_run();                       // 全タスクが完了するまでポンプ
    __task_release(__main_task);             // strong 1→0→free
    return 0;
}
```

### キャンセル

Mryl 構文の `weak(handle)` / `cancel(token)` が以下の C コードに対応します。

```mryl
let token: WeakTask<i32> = weak(handle);  // → __task_weak_retain(handle)
cancel(token);                             // → __task_cancel(token)
```

```c
static inline MrylTask* __task_weak_retain(MrylTask* t) {
    if (t) t->weak_count++;
    return t;
}

static inline void __task_cancel(MrylTask* t) {
    if (!t) return;
    if (t->state == MRYL_TASK_PENDING || t->state == MRYL_TASK_RUNNING) {
        t->state = MRYL_TASK_CANCELLED;
        if (t->on_cancel) t->on_cancel(t);       // カスタムコールバック
        if (t->awaiter)  __scheduler_post(t->awaiter); // awaiter も再開
    }
}
```

awaiter は `MRYL_TASK_CANCELLED` を確認して結果をデフォルト値（`0` / `NULL`）とします。  
設計規約として、キャンセルした Task は `await` しません。

### 実装詳細

| レイヤー | 実装 |
|---------|------|
| Lexer | `ASYNC`, `AWAIT` トークン |
| Parser | `parse_async_function_decl()`, `parse_unary()` で `await` 処理 |
| Ast | `FunctionDecl.is_async=True`, `AwaitExpr(expr)` |
| TypeChecker | 非同期呼び出し → `Future<T>` 型。`await` → `T` 型に unwrap |
| Interpreter | `asyncio.create_task()` + `loop.run_until_complete()` |
| CodeGenerator | SM 構造体 + goto-dispatch + MrylTask + スケジューラ |

gcc コマンドに `-lpthread` は**不要**です。

---

## 制御フロー

### if-else-if-else チェーン

```mryl
if (x > 10) {
    println("big");
} else if (x > 5) {
    println("medium");
} else {
    println("small");
}
```

### while ループ

```mryl
let i = 0;
while (i < 10) {
    println(i);
    i += 1;
}
```

### for ループ (Rust 風)

```mryl
for i in 0..10 {
    println(i);
}

let arr = [1, 2, 3];
for x in arr {
    println(x);
}
```

### for ループ（包含レンジ `to`）

`0 to 10` は 0〜10 を**含む**（10 を含む）レンジ。`0..10` は 10 を含まない排他レンジ。

```mryl
for i in 0 to 10 {   // 0, 1, 2, ..., 10
    println(i);
}

let n: i32 = 5;
for i in 1 to n {    // 1, 2, 3, 4, 5
    println(i);
}
```

### for ループ (C 風)

```mryl
for (let i = 0; i < 10; i++) {
    println(i);
}

for (let i = 0; i < 10; i += 2) {
    println(i);
}
```

### return

```mryl
fn fact(n: i32) -> i32 {
    if (n <= 1) {
        return 1;
    }
    return n * fact(n - 1);
}
```

---

## メモリ管理

### MrylString 構造体

```c
typedef struct {
    char* data;   // 文字列本体
    int length;   // 文字列長
} MrylString;
```

### 自動メモリクリーンアップ

Mryl の文字列は自動的にメモリが解放されます：

```mryl
fn test() {
    let s1 = "Hello";
    let s2 = "World";
    let result = s1 + s2;  // 自動的に MrylString_concat が呼ばれる
    println(result);       // 関数終了時に自動で free_mryl_string が呼ばれる
}
```

**実装フロー** (CodeGenerator):
1. `_generate_let()` で StringLiteral を検出
2. 一時変数 `__temp_str_0, __temp_str_1, ...` を生成
3. `local_string_vars` に追加して追跡
4. 関数終了時に `free_mryl_string()` を自動生成

---

## 入力関数

### read_line

標準入力から 1 行読み取り、末尾の改行を除去して `string` として返します。

```mryl
let line: string = read_line();
println("got={}", line);
```

### parse_int

`string` を解析して `Result<i32, string>` を返します。成功時は `Ok(value)`、失敗時は `Err(message)` です。

```mryl
// .try() で値を取り出す（Err ならパニック）
let n: i32 = parse_int("42").try();       // 42

// match で安全に処理
let r = parse_int("abc");   // Err("cannot parse 'abc' as i32")
let n2: i32 = match r {
    Ok(v)  => v,
    Err(e) => { println("Error: {}", e); -1 },
};
```

### parse_f64

`string` を解析して `Result<f64, string>` を返します。成功時は `Ok(value)`、失敗時は `Err(message)` です。

```mryl
// .try() で値を取り出す（Err ならパニック）
let f: f64 = parse_f64("3.14").try();     // 3.14

// match で安全に処理
let r = parse_f64("abc");   // Err("cannot parse 'abc' as f64")
let v: f64 = match r {
    Ok(x)  => x,
    Err(e) => { println("Error: {}", e); 0.0 },
};
```

### checked_div

`a / b` をゼロ除算安全に計算し、`Result<i32, string>` を返します。

```mryl
let r1 = checked_div(10, 3);   // Ok(3)
let r2 = checked_div(5, 0);    // Err("division by zero")

let val: i32 = match r1 {
    Ok(v)  => v,
    Err(e) => { println("{}", e); -1 },
};
println("{}", val);  // 3
```

通常の `/` / `%` 演算子でゼロ除算が発生した場合はランタイムパニックになります。  
安全に処理したい場合は `checked_div` を使ってください。

---

## コンパイルパイプライン

### Lexer (トークン化)

**役割**: ソースコードを Token 列に変換

```python
tokens = [
  Token(TokenKind.LET, "let", 1, 1),
  Token(TokenKind.IDENT, "x", 1, 5),
  Token(TokenKind.EQ, "=", 1, 7),
  Token(TokenKind.NUMBER, "5", 1, 9),
  Token(TokenKind.SEMICOLON, ";", 1, 10),
  ...
]
```

**演算子対応**: 新演算子用の TokenKind を定義
- 論理: `TokenKind.AND`, `TokenKind.OR`, `TokenKind.NOT`
- ビット: `TokenKind.AMPERSAND`, `TokenKind.PIPE`, `TokenKind.CARET`, `TokenKind.TILDE`, `TokenKind.LSHIFT`, `TokenKind.RSHIFT`
- 複合代入: `TokenKind.PLUS_EQ`, 等

### Parser (AST 構築)

**役割**: Token 列を AST に変換

**演算子優先順位実装**:
```
parse_expr() → parse_logical_or()
parse_logical_or() → parse_logical_and()
parse_logical_and() → parse_bitwise_or()
parse_bitwise_or() → parse_bitwise_xor()
parse_bitwise_xor() → parse_bitwise_and()
parse_bitwise_and() → parse_equality()
parse_equality() → parse_comparison()
parse_comparison() → parse_shift()
parse_shift() → parse_range()
parse_range() → parse_term()
parse_term() → parse_factor()
parse_factor() → parse_unary()
parse_unary() → parse_postfix()
parse_postfix() → parse_primary()
```

**複合代入の処理**:
```python
# Parser で複合代入を検出して自動的に二項演算に変換
if self.current.kind == TokenKind.PLUS_EQ:
    self.advance()
    value = self.parse_expr()
    # n += 5 → n = (n + 5)
    return Assignment(target, BinaryOp("+", target, value))
```

### TypeChecker (型チェック)

**役割**: AST の全体の型安全性を確認

**演算子型チェック**:
```python
def check_binary(self, expr: BinaryOp):
    left = self.check_expr(expr.left)
    right = self.check_expr(expr.right)
    
    # 論理演算: bool または numeric
    if expr.op in ("&&", "||"):
        if (is_numeric(left) or left == "bool") and \
           (is_numeric(right) or right == "bool"):
            return TypeNode("bool")
    
    # ビット演算: numeric のみ
    if expr.op in ("&", "|", "^", "<<", ">>"):
        if is_numeric(left) and is_numeric(right):
            return find_common_numeric_type(left, right)
```

### Interpreter (Python インタプリタ)

**役割**: Python で AST を実行（検証用）

**dispatch table による分岐**（`type(node)` キーの辞書で isinstance チェーンを排除）:
```python
def _build_dispatch_tables(self):
    self._stmt_dispatch = {
        LetDecl: self._exec_let_decl,
        IfStmt:  self._exec_if_stmt,
        # ... 12 エントリ（LetDecl 〜 ConditionalBlock）
    }
    self._expr_dispatch = {
        BinaryOp: self._eval_binary_op,  # 短絡評価を内包
        VarRef:   self._eval_varref,
        # ... 19 エントリ（NumberLiteral 〜 BlockExpr）
    }

def exec_stmt(self, stmt, env):
    handler = self._stmt_dispatch.get(type(stmt))
    if handler is None:
        raise RuntimeError(f"Unknown statement: {stmt}")
    handler(stmt, env)

def eval_expr(self, expr, env):
    handler = self._expr_dispatch.get(type(expr))
    if handler is None:
        raise RuntimeError(f"Unknown expression: {expr}")
    return handler(expr, env)
```

**`&&` / `||` のショートサーキット評価** は `_eval_binary_op` ハンドラ内に収容：
```python
def _eval_binary_op(self, expr, env):
    if expr.op == "&&":
        left = self.eval_expr(expr.left, env)
        if not self.is_truthy(left):
            return False  # 右は評価されない
        return self.is_truthy(self.eval_expr(expr.right, env))
    if expr.op == "||":
        left = self.eval_expr(expr.left, env)
        if self.is_truthy(left):
            return True   # 右は評価されない
        return self.is_truthy(self.eval_expr(expr.right, env))
    # ... 他の演算子
```

### CodeGenerator (C コード生成)

**役割**: AST を C コードに変換

**演算子マッピング**:
```
Mryl              C
────────────────────
&&       →        &&
||       →        ||
!        →        !
&        →        &
|        →        |
^        →        ^
~        →        ~
<<       →        <<
>>       →        >>
```

**生成順序** (重要):
```
1. #include
2. #define （const 定数）
3. ビルトイン型定義（MrylString 等）
4. ユーザー定義構造体
5. ビルトイン関数（print, println 等）
6. 非同期関数の args 構造体 + スレッドラッパー
7. ラムダ static 関数 (__lambda_N)
8. Forward declarations ← CRITICAL
9. ユーザー定義関数（main() 含む）
10. 単相化されたジェネリック関数
```

---

## AST構造

主要な AST ノード ([core/Ast.py](core/Ast.py)):

```python
class Program:
    structs: list[StructDecl]
    functions: list[FunctionDecl]
    consts: list[ConstDecl]        # const 宣言（コンパイル時定数）
    enums: list[EnumDecl]          # enum 宣言

class FunctionDecl:
    name: str
    type_params: list[str]     # ['T', 'U'] など
    params: list[Param]
    return_type: TypeNode
    body: Block
    is_async: bool             # async fn の場合 True

class LetDecl(Statement):
    name: str
    type_node: Optional[TypeNode]
    init_expr: Expression

class Assignment(Statement):
    target: Expression           # VarRef, ArrayAccess, StructAccess
    expr: Expression

class IfStmt(Statement):
    condition: Expression
    then_block: Block
    else_block: Optional[Union[IfStmt, Block]]

class ForStmt(Statement):
    variable: str
    iterable: Expression
    condition: Optional[Expression]     # C-style のみ
    update: Optional[Expression]        # C-style のみ
    body: Block
    is_c_style: bool

class BinaryOp(Expression):
    op: str          # '+', '-', '&&', '||', '&', '|', '^', '<<', '>>' など
    left: Expression
    right: Expression

class UnaryOp(Expression):
    op: str          # '-', '!', '~', '++', '--', 'post++', 'post--' など
    operand: Expression

class Lambda(Expression):
    params: list[Param]        # 型注釈なしも可
    body: Expression | Block   # 単一式またはブロック

class AwaitExpr(Expression):
    expr: Expression           # await 対象（Future<T> 型の式）
```

---

## 拡張ガイド

### 新しい演算子を追加する場合

#### 1. Lexer.py に追加

```python
class TokenKind(Enum):
    NEW_OP = auto()  # 新演算子

# read_token() メソッドに認識ロジックを追加
if ch == '@' and self.peek() == '@':
    self.advance(); self.advance()
    return Token(TokenKind.NEW_OP, "@@", line, col)
```

#### 2. Parser.py に追加

```python
# 優先順位に応じて適切なメソッドに追加
def parse_new_precedence_level(self):
    node = self.parse_higher_precedence()
    while self.current.kind == TokenKind.NEW_OP:
        op = self.current.value
        self.advance()
        right = self.parse_higher_precedence()
        node = BinaryOp(op, node, right)
    return node
```

#### 3. TypeChecker.py に追加

```python
def check_binary(self, expr: BinaryOp):
    # ... 既存コード ...
    if expr.op == "@@":
        # 型チェックロジック
        if some_condition:
            return TypeNode("bool")
```

#### 4. Interpreter.py に追加

```python
def eval_binary(self, op, left, right):
    # ... 既存コード ...
    if op == "@@":
        return left @@ right  # Python の演算に対応
```

#### 5. CodeGenerator.py に追加

```python
def _generate_expr(self, expr):
    if isinstance(expr, BinaryOp):
        # ... 既存コード ...
        # C言語の対応演算子を指定
        c_op_map = {
            "@@": "some_c_function"  # 必要に応じて関数呼び出し
        }
```

---

## よくあるエラーと対処法

### エラー: "Forward declaration missing"
**原因**: CodeGenerator が main() の後に forward declaration を生成
**対処**: `generate()` メソッドで順序確認（ステップ5がステップ6の前）

### エラー: 演算子が認識されない
**原因**: Lexer で TokenKind が定義されていない
**対処**: TokenKind enum に新演算子を追加

### エラー: 型チェック失敗
**原因**: TypeChecker で演算子の型ルールが定義されていない
**対処**: check_binary() または check_unary() に型チェック追加

### エラー: C コンパイルエラー
**原因**: CodeGenerator で生成された C コードが無効
**対処**: `_generate_expr()` で正しい C 演算子にマップ

---

## 実行方法

### 実行コマンド

```bash
cd c:\Repository\Mryl
.venv\Scripts\python.exe core\Mryl.py tests\<ファイル名>.ml
```

### 依存関係

**Python サードパーティパッケージは不要。** Python 3.9+ と GCC (Cygwin) だけが実行に必要です。

| 標準モジュール | 用途 |
|-----------|------|
| `asyncio` | Python インタープリタモードでの async/await 実行 |
| `subprocess` | GCC 呼び出しおよびネイティブバイナリ実行 |
| `os` | パス操作・ファイル存在確認 |
| `sys` | 標準入出力・終了コード制御 |
| `enum` | `TokenKind` 列挙体の定義（Lexer） |
| `datetime` | エラー出力のタイムスタンプ生成 |

### 出力ファイル

- `bin\Mryl.c` — 生成された C コード
- `bin\Mryl.exe` — コンパイル済みバイナリ

---

## 環境要件

| 項目 | バージョン | 用途 |
|------|-----------|------|
| **Python** | 3.9 以上 | インタープリタ実行・C コード生成 |
| **GCC** (Cygwin) | 任意 | C ソースのコンパイルとネイティブ実行 |
| **OS** | Windows | Cygwin GCC 経由でネイティブバイナリを生成 |

Python 標準ライブラリのみを使用しているため、`pip install` は不要です。  
詳細は「[実行方法](#実行方法)」セクションを参照してください。

---

## まとめ

Mryl は以下の特徴を持つ、完全に機能するプログラミング言語です：

- ✅ 静的型付けと型推論
- ✅ 完全な演算子セット（16 + 元々の8 = 24個）
- ✅ ジェネリック関数と構造体
- ✅ C コード生成によるネイティブ実行
- ✅ ショートサーキット評価
- ✅ 自動メモリ管理
- ✅ メソッド定義とメソッド呼び出し
- ✅ **ラムダ式** (`(x, y) => x + y` 型付き関数ポインタに変換)
- ✅ **async / await** (状態機械 + スケジューラ、MrylTask 参照カウント)
- ✅ **Option\<T\>**（`Some` / `None` + match パターンマッチ）
- ✅ **Box\<T\>**（ヒープポインタ / `*` deref / `.unbox()` / 多重ポインタ / スコープ自動 free / `Vec<Box<T>>` 対応）
- ✅ **string 組み込みメソッド 11 種**（`find` / `split` 含む）
- ✅ **Iter\<T\> / LINQ コレクション操作 12 メソッド**（C# LINQ 準拠）  

---
