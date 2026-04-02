# Mryl プログラミング言語(v0.6.0) - 言語リファレンス

<p align="left">
  <img src="assets/icon_banner.svg" width="700" alt="Mryl banner"/>
</p>

**Mryl（ミリルと読みます）** は、静的型付け、型推論、ジェネリック、構造体、配列などを備えた小さな本格的なプログラミング言語です。

- [言語詳細仕様はこちら](doc/design/mryl_specification.md)

## 目次

1. [クイックスタート](#クイックスタート)
2. [セットアップ](#セットアップ)
3. [概要](#概要)
4. [基本型](#基本型)
5. [変数宣言](#変数宣言)
6. [定数宣言](#定数宣言)
7. [演算子](#演算子)
8. [型キャスト](#型キャスト)
9. [制御構文](#制御構文)
10. [条件付きコンパイル](#条件付きコンパイル)
11. [関数](#関数)
12. [ラムダ式](#ラムダ式)
13. [async / await](#async--await)
14. [ジェネリック](#ジェネリック)
15. [構造体](#構造体)
16. [static fn（静的メソッド）](#static-fn静的メソッド)
17. [enum（列挙型）](#enum列挙型)
18. [match 式](#match-式)
19. [Result 型とエラーハンドリング](#result-型とエラーハンドリング)
20. [Option 型](#option-型)
21. [Box 型（ヒープポインタ）](#box-型ヒープポインタ)
22. [配列（固定長）](#配列固定長)
23. [可変長配列（T[]）](#可変長配列t)
24. [組み込み関数](#組み込み関数)
25. [string 組み込みメソッド](#string-組み込みメソッド)
26. [Iter\<T\> / LINQ スタイルコレクション操作](#itert--linq-スタイルコレクション操作)
27. [型推論](#型推論)
28. [型チェック](#型チェック)
29. [まとめ](#まとめ)
30. [テストファイル](#テストファイル)
31. [トラブルシューティング](#トラブルシューティング)

---

## クイックスタート

**5分で Hello World を動かす手順です。**

### 1. ファイルを作る

`hello.ml` というファイルを作成します：

```mryl
fn main() -> i32 {
    println("Hello, Mryl!");

    let name = "world";
    let n    = 42;
    println("name={}, n={}", name, n);

    return 0;
}
```

### 2. 実行する

```powershell
# 仮想環境を有効化している場合
.venv\Scripts\python.exe core\Mryl.py hello.ml
```

### 3. 出力イメージ

```
=== Python Interpreter ===
Hello, Mryl!
name=world, n=42

=== C Compilation ===
OK - Compilation successful: bin\Mryl.exe

=== Native Execution ===
Hello, Mryl!
name=world, n=42
Program returned: 0
```

Python インタプリタと C ネイティブの両方で実行されます。生成ファイルは `bin\Mryl.c` と `bin\Mryl.exe` です。

### もう少し試してみる

```mryl
fn greet(name: string) -> string {
    return "Hello, " + name + "!";
}

struct Point {
    x: i32;
    y: i32;
}

fn main() -> i32 {
    // 関数呼び出し
    println("{}", greet("Mryl"));     // Hello, Mryl!

    // struct
    let p = Point { x: 3, y: 4 };
    println("x={}, y={}", p.x, p.y); // x=3, y=4

    // ループ
    for (let i = 1; i <= 3; i++) {
        println("i={}", i);
    }

    return 0;
}
```

---

## セットアップ

### 開発環境（動作確認済み構成）

| 項目 | 内容 |
|------|------|
| **OS** | Windows 11 25H2（ビルド 26200.7623） |
| **エディタ** | Visual Studio Code 64bit |
| **開発言語** | Python 3.14.x, C |
| **コンパイラ** | GCC 16.0.1（Cygwin 経由） |
| **AI エージェント** | Claude Code - Claude Sonnet 4.6（テスト・デバッグ補助）|

> AI エージェントはテストケースの生成・デバッグ支援に使用しており、言語コア実装には関与していません。

### 対応システム

| 項目 | 内容 |
|------|------|
| **対応 OS** | Windows（Cygwin GCC が必須） |
| **Linux / macOS** | GCC がパスに通っていれば動作可能（未検証） |
| **Python** | 3.9 以上 |
| **GCC** | 任意のバージョン（動作確認: 16.0.1） |

### 必要なソフトウェア

| 項目 | バージョン | 入手先 |
|------|-----------|--------|
| **Python** | 3.9 以上 | https://www.python.org/ |
| **Cygwin** | 任意 | https://www.cygwin.com/ |
| **GCC** | Cygwin パッケージ `gcc-core` | Cygwin インストーラ経由 |

GCC は Cygwin 経由で使用します。  
Cygwin のインストール先: `C:\cygwin64\bin\bash.exe`（`CodeGenerator.py` のデフォルトパス）

### Python ライブラリ

**サードパーティパッケージは不要です。** `pip install` は一切不要で、Python 3.9+ を用意するだけで動作します。

使用している標準ライブラリは以下のとおりです：

| モジュール | 用途 |
|-----------|------|
| `asyncio` | Python インタープリタモードでの async/await 実行 |
| `subprocess` | GCC 呼び出しおよびネイティブバイナリ実行 |
| `os` | パス操作・ファイル存在確認 |
| `sys` | 標準入出力・終了コード制御 |
| `enum` | `TokenKind` 列挙体の定義（Lexer） |
| `datetime` | エラー出力のタイムスタンプ生成 |

### 実行方法

```bash
# 仮想環境を有効化している場合
.venv\Scripts\python.exe core\Mryl.py tests\<ファイル名>.ml
```

出力先: `bin\Mryl.c`（C ソース）、`bin\Mryl.exe`（実行ファイル）

---

## 概要

### 言語名の由来

**Mryl（ミリル）** という名前は、2 つの英単語を組み合わせた造語です。

| 語源 | 意味 |
|------|------|
| **Mist**（ミスト） | 霧・靄。静かに漂うイメージ |
| **Rill**（リル） | 小川のせせらぎ、さざ波の流れ |

「霧のようにふわりと広がり、小川のようにゆったりと流れる」という言葉のイメージから生まれました。

> プログラミング言語の学習・開発を、焦らずゆっくり、まったり楽しんでほしい。  
> そんな願いを込めて **Mryl** と名付けました。

なお、当初は **Mint** という名称でしたが、同名の言語が既に存在していたため、語感を活かしつつ独自性を持たせた **Mryl** に改名しました。

---

### 設計思想と影響を受けた言語

Mryl は **C / C++ / C# / Rust** の 4 言語から影響を受けています。

C と C++ は多くの入門者が最初に触れる言語であり、Mryl の構文の基盤となっています。`for (let i = 0; i < n; i++)` のような C 風ループや `++` / `--` 演算子、ビット演算、ポインタを意識したメモリモデルはその名残です。

その上に、C# や Rust が切り拓いたモダンな設計を取り入れています。

| 機能 | 参考言語 |
|------|---------|
| `async / await`（状態機械 + スケジューラ） | C# |
| `Result<T, E>`・`.try()` によるエラーハンドリング | Rust |
| `enum`（データ付きバリアント）+ `match` 式 | Rust |
| ジェネリック関数・構造体（型パラメータ） | C# / Rust |
| 自動メモリ管理（参照カウント） | Rust |
| `for x in collection` の Rust 風イテレーション | Rust |
| `println("value: {}", x)` フォーマット文字列 | Rust |
| ラムダ式（`(x) => x * 2`） | C# |

> **Mryl のコンセプト**：C/C++ で学ぶ「低レイヤーの感覚」を持ちながら、
> C# や Rust が実現した「安全で読みやすいコード」をひとつの言語で体験できること。

---

### 機能一覧

Mryl は以下の機能を備えています：

- **静的型付け**：コンパイル時に型チェック
- **型推論**：`let x = 10;` で型を自動推論
- **複数の数値型**：符号付/無しの8/16/32/64ビット整数、32/64ビット浮動小数点
- **自動型昇格**：`i8 + i32 = i32` のように自動で型を統一
- **ジェネリック関数・構造体**：複数の型パラメータをサポート
- **構造体**：名前付きフィールドを持つデータ型
- **enum**：データを持てる列挙型（Rust 風）
- **match 式**：パターンマッチングによる分岐
- **Result\<T,E\>**：型安全なエラーハンドリング（`Ok` / `Err` + `.try()`）
- **Option\<T\>**：値なし（`None`）/ 値あり（`Some(v)`）の安全な型、match によるパターンマッチ
- **Box\<T\>**：ヒープポインタ型、`*b` デリファレンス、`.unbox()`、多重ポインタ（`Box<Box<T>>` 等）対応
- **配列**：固定長配列と可変長配列（`T[]`）に対応
- **制御構文**：if/else, while, for（Rust 風・包含 `to`・C 風）、`break` / `continue`
- **インクリメント/デクリメント**：`++`, `--` 演算子対応
- **フォーマット文字列**：Rust 風の `println("i = {}", i)` 表記
- **関数**：戻り値型指定、複数パラメータ、前方宣言による相互再帰
- **ラムダ式**：`(x, y) => x + y` の無名関数（クロージャキャプチャ対応・C コード生成は fat pointer 方式）
- **fn 型パラメータ**：関数をコールバックとして渡せる高階関数
- **fix キーワード**：不変変数・不変引数の宣言
- **async/await**：非同期関数と待機構文（async ラムダ含む）
- **string 操作**：連結（`+`）、比較（`==` / `!=`）、組み込みメソッド（`len` / `contains` / `starts_with` / `ends_with` / `trim` / `to_upper` / `to_lower` / `replace` / `find` / `split`）
- **Iter\<T\> / LINQ コレクション操作**：`filter` / `select` / `take` / `skip` / `to_array` / `aggregate` / `for_each` / `count` / `first` / `any` / `all` / `select_many`（C# LINQ 準拠）
- **ユーザー入力**：`read_line()` / `parse_int()` / `parse_f64()`（`Result<T, string>` 返し）/ `checked_div()`（ゼロ除算安全除算）
- **構造化エラー出力**：タイムスタンプ付きスタックトレース + 行番号

---

## 基本型

### 整数型（符号あり）
```
i8    : 8ビット符号付整数（-128 ～ 127）
i16   : 16ビット符号付整数
i32   : 32ビット符号付整数（デフォルト）
i64   : 64ビット符号付整数
```

### 整数型（符号なし）
```
u8    : 8ビット符号なし整数（0 ～ 255）
u16   : 16ビット符号なし整数
u32   : 32ビット符号なし整数
u64   : 64ビット符号なし整数
```

### 浮動小数点型
```
f32   : 32ビット浮動小数点数
f64   : 64ビット浮動小数点数（デフォルト）
```

### その他
```
string: テキスト
bool  : true / false
```

---

## 変数宣言

### 型付き宣言
```mryl
let x: i32 = 10;
let y: f64 = 3.14(f64);
let s: string = "hello";
let b: bool = true;
```

### 型推論
```mryl
let x = 10;           // i32と推論
let y = 3.14;         // f64と推論
let s = "hello";      // stringと推論
```

### 型キャスト（型サフィックス）
```mryl
let a = 5(u8);        // u8型のリテラル
let b = 100(i16);     // i16型のリテラル
let c = 3.14(f32);    // f32型のリテラル
let d = 1_000(u32);   // アンダースコア区切り対応
```

---

## 定数宣言

### const によるコンパイル時定数

**Mryl** では `const` キーワードで、コンパイル時に評価される定数を宣言できます：

```mryl
const MAX_VALUE = 100;
const PI = 31415;
const DEBUG = 1;
```

**特徴:**
- **コンパイル時評価**: const 式はコンパイル時に評価される
- **型推論**: リテラルから自動推論
- **定数式対応**: 算術演算、比較、論理演算などをサポート
- **コンパイルバリエーション**: 下記の条件付きコンパイルで使用可能

#### const 式の例

```mryl
const DEBUG = 1;
const OPTIMIZATION_LEVEL = 2;
const MAX_ITERATIONS = 100;

// const を使った式
const DOUBLED = MAX_VALUE * 2;
const CALCULATED = PI / 10000;

fn main() -> i32 {
    // const を変数として参照可能
    let x: i32 = MAX_VALUE + 50;
    println(x);
    
    return 0;
}
```

**注**: const は グローバルスコープで定義する必要があります。

---

## 演算子

### 算術演算
```mryl
let a = 10 + 5;       // 加算
let b = 10 - 5;       // 減算
let c = 10 * 5;       // 乗算
let d = 10 / 5;       // 整数除算
let e = 10 % 3;       // 剰余
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
let a = true || false;  // OR (短絡評価)
let b = true && true;   // AND (短絡評価)
let c = !true;          // NOT
```

### ビット演算
```mryl
let x = 5;        // 0101
let y = 3;        // 0011

let and = x & y;  // ビット AND: 1 (0001)
let or = x | y;   // ビット OR: 7 (0111)
let xor = x ^ y;  // ビット XOR: 6 (0110)
let lshift = x << 1;  // 左シフト: 10 (1010)
let rshift = x >> 1;  // 右シフト: 2 (0010)
let not = ~x;     // ビット反転: -6 (2進補数)
```

### インクリメント・デクリメント
```mryl
let i = 5;
++i;              // Pre-increment: i を 6 にしてから 6 を返す
let j = i++;      // Post-increment: 6 を返してから i を 7 にする（j = 6）

i--;              // Post-decrement
--i;              // Pre-decrement
```

### 複合代入演算子
```mryl
let n = 10;
n += 5;   // n = n + 5  → 15
n -= 3;   // n = n - 3  → 12
n *= 2;   // n = n * 2  → 24
n /= 3;   // n = n / 3  → 8
n %= 5;   // n = n % 5  → 3

let b = 8;
b <<= 1;  // b = b << 1 → 16
b >>= 2;  // b = b >> 2 → 4

let c = 12;
c ^= 5;   // c = c ^ 5  → 9
```

### 演算子優先順位
```
優先度（高→低）
 1. [] . () post++ post--    （配列インデックス・メンバアクセス・関数呼び出し・後置 インクリ）
 2. ! ~ ++ --                （前置単項演算子）
 3. * / %
 4. + -
 5. << >>
 6. < <= > >=
 7. == !=
 8. &
 9. ^
10. |
11. && （短絡評価）
12. || （短絡評価）
13. = += -= *= /= %= <<= >>= ^=
```

### 型昇格（自動型統一）
```mryl
let x: i8 = 5(i8);
let y: i32 = 10(i32);
let z = x + y;          // i32 に自動昇格
```

型昇格ルール：
| パターン | 結果 |
|---------|------|
| i8 + i32 | i32 |
| u16 + u64 | u64 |
| i32 + f32 | f64 |
| f32 + f64 | f64 |
| i32 + u32 | エラー（符号混在不可） |

---

## 型キャスト

Mryl では `value(type)` 形式で明示的な型指定ができます：

```mryl
let a = 42(u8);           // u8 として初期化
let b = 3.14159(f32);     // f32 として初期化
let c = 1_000_000(u32);   // 大きな数値は可読性のためアンダースコア区切り
```

---

## 制御構文

### if 文
```mryl
if (x < 10) {
    println(x);
} else if (x < 20) {
    println(10 + x);
} else {
    println(x);
}
```

### while ループ
```mryl
let x = 0;
while (x < 10) {
    println(x);
    x = x + 1;
}
```

### for ループ（Rust 風）
```mryl
// 範囲ループ（0 ～ 9：上限は除外）
for i in 0..10 {
    println(i);
}

// 配列ループ
let arr = [1, 2, 3];
for x in arr {
    println(x);
}

// フォーマット文字列との組み合わせ
for i in 0..3 {
    println("i = {}", i);
}
```

### for ループ（包含レンジ `to`）

`to` キーワードで**上限を含む**範囲ループを記述できます。`0..10` は 10 を含まず、`0 to 10` は 10 を含みます：

```mryl
// 0, 1, 2, ..., 10（10 を含む）
for i in 0 to 10 {
    println(i);
}

// 変数を使った例
let n: i32 = 5;
for i in 1 to n {    // 1, 2, 3, 4, 5
    println(i);
}
```

### for ループ（C 風）
```mryl
// 従来形式の for ループ
for (let i = 0; i < 10; i++) {
    println(i);
}

// 更新式も自由
for (let i = 0; i < 10; i = i + 2) {
    println(i);
}
```

### break / continue

`break` はループを即座に終了し、`continue` は現在のイテレーションをスキップして次のイテレーションへ進みます。  
`while`・Rust 風 `for`・C 風 `for` の全てで使用できます。

```mryl
// break（ループ脱出）
let i = 0;
while (i < 10) {
    if (i == 5) { break; }
    println("{}", i);
    i++;
}
// → 0 1 2 3 4

// continue（次のイテレーションへ）
for j in 0..8 {
    if (j % 2 == 0) { continue; }
    println("{}", j);
}
// → 1 3 5 7

// C 風 for での break / continue
for (let k = 0; k < 10; k++) {
    if (k == 3) { continue; }
    if (k == 7) { break; }
    println("{}", k);
}
// → 0 1 2 4 5 6
```

**注意**：C 風 for の `continue` を実行してもインクリメント式（`k++`）は正しく実行されます。

### インクリメント / デクリメント演算子
```mryl
let i = 5;
i++;              // Post-increment: i を 6 にする
let j = i++;      // j = 6 を取得してから i を 7 にする

i--;              // Post-decrement: i を 6 にする

++i;              // Pre-increment: i を 7 にしてから 7 を返す
let k = ++i;      // i = 8、k = 8
```

---

## 条件付きコンパイル

**Mryl** では、`const` 定義と `#ifdef`, `#ifndef`, `#if` ディレクティブを使って、コンパイル時にコードの一部を条件付きでインクルード/除外できます。

### #ifdef - 定数が定義されている場合

```mryl
const DEBUG = 1;
const OPTIMIZATION_LEVEL = 2;

fn main() -> i32 {
    #ifdef DEBUG
    println(1);  // DEBUG が定義されていればこのコードはインクルード
    #endif
    
    #ifdef PRODUCTION
    println(999); // PRODUCTION が定義されていなければスキップ
    #endif
    
    return 0;
}
```

**動作:**
- DEBUG が定義されているので `println(1)` は実行
- PRODUCTION が定義されていないので `println(999)` はスキップ

### #ifndef - 定数が未定義な場合

```mryl
fn main() -> i32 {
    #ifndef PRODUCTION
    println(1);  // PRODUCTION が未定義ならコードはインクルード
    #endif
    
    return 0;
}
```

### #if - 定数式を評価

```mryl
const OPTIMIZATION_LEVEL = 2;

fn main() -> i32 {
    #if OPTIMIZATION_LEVEL
    println(1);  // ゼロ以外なら実行
    #endif
    
    #if OPTIMIZATION_LEVEL > 1
    println(2);  // const 式を評価
    #endif
    
    return 0;
}
```

### #else ブロック

```mryl
const MODE = 1;

fn main() -> i32 {
    #ifdef DEBUG
    println(10);
    #else
    println(20);  // DEBUG が未定義なら実行
    #endif
    
    return 0;
}
```

**特徴:**
- **コンパイル時評価**: 条件が false の場合、コードは C コードに含まれない
- **ネストサポート**: 複数の #if/#ifdef ブロックをネスト可能
- **const 式対応**: 比較演算、算術演算など全て対応

---

## 関数

### 関数定義
```mryl
fn add(a: i32, b: i32) -> i32 {
    return a + b;
}
```

### 関数呼び出し
```mryl
let result = add(5, 3);  // 8
println(result);
```

### 戻り値型なし
```mryl
fn greeting(name: string) -> void {
    println(name);
}
```

---

## ラムダ式

### ラムダ式の定義

ラムダ式は `(パラメータ) => 式` の形式で無名関数を定義します：

```mryl
let mul2 = (x: i32) => x * 2;
let add  = (x: i32, y: i32) => x + y;
```

`=>` の右辺を `{ }` で囲むことで、複数のステートメントを持つ**ブロックボディ**を記述できます：

```mryl
let process = (x: i32) => {
    let doubled = x * 2;
    let result  = doubled * 2;
    println(result);
};
```

### ラムダ式の呼び出し

通常の関数と同じ構文で呼び出せます：

```mryl
fn main() {
    let mul2 = (x: i32) => x * 2;
    let r1 = mul2(5);              // 10

    let add = (x: i32, y: i32) => x + y;
    let r2 = add(3, 7);            // 10

    let is_positive = (n: i32) => n > 0;
    let r3 = is_positive(5);       // true
}
```

### 特徴

- **型注釈**：パラメータに `: 型` で型を指定
- **単一式ボディ**：`(x: i32) => x * 2` のように `=>` の右辺を単一の式で記述
- **ブロックボディ**：`(x: i32) => { ... }` のように `{ }` で複数ステートメントを記述可能。`return` 文なしは `void`、`return` 文ありはその型を自動推論
- **関数ポインタ型**：C コード生成時は fat pointer 構造体（`MrylFn_*`）に変換。名前付き関数を渡す場合は `void* env` 付き thunk を自動生成
- **クロージャ**：Python インタプリタモードでは宣言時の環境をキャプチャ

### async ラムダ式

`async` キーワードをラムダ式の前に付けることで、**非同期ラムダ**を定義できます：

```mryl
fn main() {
    // 戻り値なし async ラムダ
    let greet = async (name: i32) => {
        println(name);
    };
    await greet(42);

    // await を内包する async ラムダ（async fn の結果を待機）
    let compute = async (x: i32) => {
        let result = await some_async_fn(x);
        println(result);
    };
    await compute(10);
}
```

**構文**：

```
async (パラメータリスト) => { ブロックボディ }
```

**特徴**：

| 項目 | 内容 |
|------|------|
| 戻り値型 | `MrylTask*`（タスクハンドル） |
| 呼び出し | `await 変数名(引数)` で待機・実行 |
| `await` 内包 | ブロック内で `await` を使用して他の async 関数/ラムダ呼び出し可能 |
| C コード生成 | 専用ステートマシン（SM）＋ファクトリ関数として展開 |
| Python モード | `asyncio.create_task()` でコルーチンとして実行 |

> **注意**：async ラムダはブロックボディ `{ }` のみサポートします。単一式ボディ（`async (x) => x * 2`）は使用できません。

---

## async / await

### 非同期関数の定義

`async fn` で非同期関数を定義します：

```mryl
async fn compute_sum(n: i32) -> i32 {
    let result: i32 = n * n;
    return result;
}

async fn print_message() {
    println("Hello from async function!");
}
```

### 非同期関数の呼び出しと await

非同期関数の呼び出しはすぐに `MrylTask*`（タスクハンドル）を返します。  
結果を待つには `await` を使います：

```mryl
fn main() {
    // 非同期タスクを起動（スケジューラへ POST）
    let handle = compute_sum(7);

    // 完了を待機して結果を取得
    let result: i32 = await handle;    // 49
    println("{}", result);

    // 戻り値なし (void) の await
    let h2 = print_message();
    await h2;
}
```

### async fn と Result\<T,E\>

`async fn` の戻り値型に `Result<T,E>` を指定できます。
`Err(...)` を返した場合、タスク状態は `MRYL_TASK_FAULTED` に遷移します。
`await` 側は `COMPLETED` と `FAULTED` の両方を完了として扱い、`Result` 値をそのまま取得できます。

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

> **FAULTED 状態**: `Err(...)` を返す `async fn` は `MRYL_TASK_FAULTED` をセットして終了します。
> `await` の停止条件は `COMPLETED || FAULTED` であるため、エラーも含めて正しく待機・取得できます。

---

### Task コンビネータ（v0.6.0）

複数の `Future<T>` を同時に待機する静的メソッドです。

| API | 説明 |
|-----|------|
| `Task::when_all([t1, t2, ...])` | 全タスクの完了を待機し、結果を配列で返す（`Future<T[]>`） |
| `Task::when_any([t1, t2, ...])` | 最初に完了したタスクの結果を返す（`Future<T>`） |

```mryl
async fn fetch(n: i32) -> i32 { return n; }

fn main() {
    let t1 = fetch(10);
    let t2 = fetch(20);

    // when_all: 全件完了を待機 → 結果配列
    let all: i32[] = await Task::when_all([t1, t2]);
    println("{}", all[0]);   // 10
    println("{}", all[1]);   // 20

    let t3 = fetch(1);
    let t4 = fetch(2);

    // when_any: 最初に完了した値を取得（FIFO スケジューラ → t3 が先）
    let first: i32 = await Task::when_any([t3, t4]);
    println("{}", first);    // 1
}
```

> **制限（v0.6.0）**: 要素型 `T` は `void` および `Result<T,E>` 非対応。全要素が同一型であること。

---

### Task キャンセル（v0.6.0）

`weak(handle)` で弱参照 `WeakTask<T>` を取得し、`cancel(token)` でキャンセルします。

| API | 説明 |
|-----|------|
| `weak(handle: Future<T>)` | 弱参照 `WeakTask<T>` を取得（`__task_weak_retain` に対応） |
| `cancel(token: WeakTask<T>)` | Task をキャンセル（冪等・完了済みなら何もしない） |

```mryl
async fn long_task(n: i32) -> i32 { return n * 2; }

fn main() {
    let handle = long_task(42);
    let token: WeakTask<i32> = weak(handle);  // 弱参照取得

    cancel(token);  // キャンセル（handle は await しない）
}
```

**設計規約**: キャンセルは「Task を捨てる」操作。キャンセル後に `handle` を `await` しない。  
`WeakTask<T>` を `await` しようとすると TypeChecker がエラーを出します。

---

### アーキテクチャ概要

Mryl の async/await は **C# 風の状態機械 + シングルスレッドスケジューラ** で実装されています。
pthreads は使用しません。

```
┌─── Mryl ソースコード ─────────────────────────────────────────┐
│  async fn compute_sum(n: i32) -> i32 { ... }                 │
│  fn main() { let h = compute_sum(7); let r = await h; ... }  │
└──────────────────────────────────────────────────────────────┘
            ↓ CodeGenerator
┌─── 生成 C コード ─────────────────────────────────────────────┐
│  typedef struct { int __state; int32_t n; int32_t result;    │
│                   MrylTask* __task; } __ComputeSum_SM;        │
│  void __compute_sum_move_next(MrylTask* t) { ... }           │
│  MrylTask* compute_sum(int32_t n) { ... factory ... }        │
└──────────────────────────────────────────────────────────────┘
            ↓ main()
┌─── スケジューラループ ────────────────────────────────────────┐
│  __scheduler_init() → __scheduler_post(task) → __scheduler_run() │
└──────────────────────────────────────────────────────────────┘
```

### MrylTask 構造体

```c
typedef struct MrylTask {
    int           strong_count;  // 強参照カウント（共有所有権）
    int           weak_count;    // 弱参照カウント（キャンセルトークン用）
    MrylTaskState state;         // PENDING / RUNNING / COMPLETED / CANCELLED / FAULTED(Err返却時)
    void*         result;        // 戻り値（ヒープ確保）
    void        (*move_next)(struct MrylTask*);  // 状態遷移関数ポインタ
    void        (*on_cancel)(struct MrylTask*);  // キャンセル時コールバック
    void*         sm;            // 状態機械構造体ポインタ
    struct MrylTask* awaiter;    // このタスク完了時に再開するタスク
} MrylTask;
```

### 参照カウント（メモリ管理）

| 操作 | カウント変化 |
|------|-------------|
| `factory` 生成時 | `strong_count = 1` |
| 呼び出し元 `retain` | `strong_count++` (→2) |
| SM 完了時 `release` | `strong_count--` (→1) |
| `await` 後 `release` | `strong_count--` (→0 → `free`) |
| `main()` タスク | `strong_count = 2`、`scheduler_run()` 後に明示 `release` |

弱参照 (`weak_count`) はキャンセルトークンとして使用します：  
`__task_lock()` → 強参照に昇格（キャンセル済みなら `NULL`）。

### スケジューラ

```c
#define __SCHEDULER_CAP 65536
typedef struct { MrylTask* queue[__SCHEDULER_CAP]; int head, tail; } MrylScheduler;

static inline void __scheduler_post(MrylTask* t) { ... } // タスクをキューに追加
static inline void __scheduler_run(void)  { ... } // キューが空になるまで実行
```

- シングルスレッド、ロックフリー、循環バッファ（最大 65536 タスク）
- `move_next` が中断（`return`）するとスケジューラが次のタスクを処理
- await で中断したタスクは被待機タスクの `awaiter` 経由で再 POST される

### 状態機械（goto-dispatch）

各 `async fn` は **SM 構造体** と **`move_next` 関数** にコンパイルされます：

```c
// ── SM 構造体（パラメータ + ローカル変数 + 状態）────────────
typedef struct {
    int __state;          // 現在の状態番号
    int32_t n;            // パラメータ
    int32_t result;       // ローカル変数
    MrylTask* __task;     // 自身のタスクポインタ
} __ComputeSum_SM;

// ── move_next（状態遷移関数）────────────────────────────────
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
        __task_release(__task);
        if (__task->awaiter) __scheduler_post(__task->awaiter);
        return;
    }
}
```

await がある場合、状態番号が増えて中断点を記録します（`main()` の例は仕様書参照）。

### キャンセル

```mryl
let handle = long_task(42);
let token: WeakTask<i32> = weak(handle);  // 弱参照取得
cancel(token);                             // キャンセル（handle は await しない）
```

`__task_cancel()` を呼ぶと `state = MRYL_TASK_CANCELLED` になり、  
awaiter が存在すれば自動的に再スケジュールされます。

### 特徴まとめ

| 項目 | 説明 |
|------|------|
| C コード生成 | 状態機械（goto-dispatch） + MrylTask 参照カウント |
| スケジューラ | シングルスレッド循環バッファ（cap=65536）|
| 戻り値受け渡し | `MrylTask*.result`（`void*`、ヒープ確保）|
| 参照カウント | `strong_count` + `weak_count`（shared/weak_ptr 相当）|
| `Result<T,E>` 返し | `Err(...)` 返却時に `MRYL_TASK_FAULTED`、`await` は COMPLETED/FAULTED 両方で停止 |
| キャンセル | `__task_cancel()` + `on_cancel` コールバック |
| `#include` | `<pthread.h>` 不要、`-lpthread` リンク不要 |
| Python モード | `asyncio.create_task()` + `loop.run_until_complete()` |

---

## ジェネリック

### 単一型パラメータ
```mryl
fn identity<T>(value: T) -> T {
    return value;
}

fn main() {
    let x = identity(42);
    let s = identity("hello");
}
```

### 複数型パラメータ
```mryl
fn pair<T, U>(first: T, second: U) {
    // T と U は異なる型
}

fn main() {
    pair(5, "hello");     // T=i32, U=string
    pair(3.14(f64), true); // T=f64, U=bool
}
```

### ジェネリック構造体
```mryl
struct Box<T> {
    value: T;
}

fn main() {
    let b = Box<i32> { value: 42 };
}
```

### 型推論
```mryl
fn add<T>(a: T, b: T) -> T {
    return a + b;
}

fn main() {
    let result = add(10, 20);  // T = i32 と推論
}
```

---

## 構造体

### 定義
```mryl
struct Point {
    x: i32;
    y: i32;
}

struct Person {
    name: string;
    age: u8;
}
```

### 初期化
```mryl
let p = Point { x: 10, y: 20 };
let person = Person { name: "Alice", age: 30(u8) };
```

### フィールドアクセス
```mryl
let x_coord = p.x;
println(person.name);
```

### フィールド代入
```mryl
p.x = 5;
person.age = 31(u8);
```

### メソッド定義

構造体に対して `impl` ブロックを使用してメソッドを定義できます。メソッドは第1パラメータとして `self` を受け取ります。

```mryl
struct Point {
    x: i32;
    y: i32;
}

impl Point {
    fn display(self) -> i32 {
        println("Point({}, {})", self.x, self.y);
        return 0;
    }

    fn distance(self) -> i32 {
        return self.x + self.y;
    }
}
```

### メソッド呼び出し

```mryl
let p = Point { x: 3, y: 4 };

// メソッド呼び出し（self は自動的に渡される）
p.display();

let dist = p.distance();
println("Distance: {}", dist);
```

### Box フィールドを持つ struct の自動メモリ解放

`Box<T>` 型のフィールドを持つ struct は、コンパイラが自動的に **デストラクタ関数 `mryl_free_StructName()`** を生成します。
この関数は struct 変数のスコープ終了時・`return` 文実行前に自動で呼ばれ、Box フィールドを `free` します。
手動で `free` を呼ぶ必要はありません。

```mryl
struct Node {
    value: i32;
    data: Box<i32>;
}

fn example() {
    let n = Node { value: 1, data: Box::new(42) };
    println("{}", *n.data);
    // スコープ終了時に mryl_free_Node(n) が自動呼び出し → free(n.data)
}
```

ネストした struct（フィールドに別の struct を持つ場合）も再帰的に解放されます。

```mryl
struct Inner {
    x: Box<i32>;
}

struct Outer {
    inner: Inner;
}

fn example() {
    let o = Outer { inner: Inner { x: Box::new(10) } };
    // スコープ終了時: mryl_free_Outer(o) → mryl_free_Inner(o.inner) → free(o.inner.x)
}
```

---

## static fn（静的メソッド）

`impl` ブロック内に `static fn` で宣言する**静的メソッド**です。インスタンスではなく型そのものに属するため、`self` パラメータを持ちません。

### 宣言

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
```

### 呼び出し構文

`TypeName::method(args)` — `::` 演算子で呼び出します。

```mryl
fn main() -> i32 {
    let c = Counter::zero();        // static fn 呼び出し
    c.increment();                  // instance fn 呼び出し
    println("{}", c.value);         // 1
    return 0;
}
```

### static fn 内から同 struct の他 static fn を呼ぶ

```mryl
impl Counter {
    static fn default_max() -> i32 { return 100; }

    static fn bounded() -> Counter {
        let max = Counter::default_max();  // OK
        return Counter { value: max };
    }
}
```

### fn 型変数への代入

括弧なしの `TypeName::method` は `fn` 型変数として扱えます。

```mryl
// fn 型変数への代入
let f: fn() -> Counter = Counter::zero;
let c = f();

// 高階関数への引数として渡す
fn make(factory: fn() -> Counter) -> Counter {
    return factory();
}
let c2 = make(Counter::zero);
```

### 制約

- `static fn` 内で `self` を使用するとコンパイルエラー
- `static let`（静的変数）は Mryl では非対応（`struct` で代替）

### C コード生成

| Mryl | 生成される C コード |
|---|---|
| `static fn zero() -> Counter` | `Counter Counter_zero()` |
| `Counter::zero()` | `Counter_zero()` |
| `Counter::zero`（単純参照） | `Counter_zero`（関数ポインタ） |
| `Counter::zero`（`fn()->Counter` 型引数・変数代入） | thunk + fat pointer `MrylFn_void_ret_Counter` |

> `fn(T)->U` 型パラメータへ渡す場合や `fn` 型変数へ代入する場合は、
> 統一的な fat pointer 規約（`MrylFn_*`）に合わせるため thunk ラッパーが自動生成されます。

---

## enum（列挙型）

Mryl の `enum` は Rust 風のデータ付き列挙型（代数的データ型）です。  
各バリアントに任意の型の値を関連付けられます。

### enum 定義

```mryl
// シンプル（データなし）バリアント
enum Direction {
    North,
    South,
    East,
    West,
}

// データ付きバリアント
enum Shape {
    Circle(f64),        // 半径
    Rect(f64, f64),     // 幅・高さ
    Point,              // データなし
}

// 複数フィールド付き
enum Message {
    Quit,
    Move(i32, i32),
    Write(string),
    ChangeColor(i32, i32, i32),
}
```

### enum 値の生成

```mryl
let d: Direction = Direction::North;
let s: Shape     = Shape::Circle(3.0);
let r: Shape     = Shape::Rect(4.0, 5.0);
let p: Shape     = Shape::Point;
```

### enum の特徴

- `::` 演算子でバリアントを参照（`EnumName::Variant`）
- データなしバリアントも OK
- `match` 式と組み合わせてパターンマッチング

---

## match 式

`match` はパターンマッチングによる分岐構文です。
`if-else` の代わりに enum バリアントや単純な値に対して使えます。

> **設計メモ**: `match` は基本的に**式**として設計されており、評価結果を変数に代入するのが主な用途です。
> ただし、全アームが `println` 等の `void` を返す場合は**文としても使用可能**です（値は破棄されます）。

### enum に対する match

```mryl
enum Shape {
    Circle(f64),
    Rect(f64, f64),
    Point,
}

fn area(s: Shape) -> f64 {
    let result: f64 = match s {
        Shape::Circle(r)  => r * r * 3.14159,
        Shape::Rect(w, h) => w * h,
        Shape::Point      => 0.0,
    };
    return result;
}

fn main() -> i32 {
    let c = Shape::Circle(2.0);
    let r = Shape::Rect(3.0, 4.0);
    println("{}", area(c));    // 12.566...
    println("{}", area(r));    // 12.0
    return 0;
}
```

### match を式として使う

`match` は式として評価でき、変数に代入できます：

```mryl
let s = Shape::Circle(5.0);
let label: string = match s {
    Shape::Circle(r)  => "circle",
    Shape::Rect(w, h) => "rect",
    Shape::Point      => "point",
};
println("{}", label);   // circle
```

### 数値/文字列に対する match

```mryl
let x = 2;
let name: string = match x {
    1 => "one",
    2 => "two",
    3 => "three",
};
println("{}", name);   // two
```

### 部分マッチ（_ ワイルドカード）

全バリアントを網羅しない場合も `_` でキャッチオールアームを記述できます。

```mryl
let x: i32 = 42;
let result: string = match x {
    1 => "one",
    2 => "two",
    _ => "other",
};
println("{}", result);   // other
```

---

## Result 型とエラーハンドリング

Mryl には組み込みの `Result<T,E>` 型があり、型安全なエラーハンドリングを実現します。

### Result 型の基本

```mryl
// Ok(値) または Err(エラー値) を返す関数
fn divide(a: i32, b: i32) -> Result<i32, i32> {
    if (b == 0) {
        return Err(-1);
    }
    return Ok(a / b);
}
```

### Result の利用

```mryl
fn main() -> i32 {
    let r = divide(10, 2);

    // match でパターンマッチング
    let val: i32 = match r {
        Ok(v)  => v,
        Err(e) => {
            println("Error: {}", e);
            0
        },
    };
    println("{}", val);   // 5
    return 0;
}
```

### .try() エラー伝播

`.try()` メソッドを使うと、`Err` の場合に即座に実行時エラー（panic）として報告されます。  
成功の場合は内部の値を取り出します。

```mryl
fn main() -> i32 {
    let result = divide(10, 0).try();   // b==0 なので Err(-1) で panic
    println("{}", result);
    return 0;
}
```

panic 時の出力例：
```
[2024-01-01 12:00:00] MrylRuntimeError: .try() called on Err(-1)
  at main (line 2)
```

### エラー出力の特徴

- **タイムスタンプ付き**：`[YYYY-MM-DD HH:MM:SS]` 形式
- **スタックトレース**：呼び出し元の関数名 + 行番号を表示
- **構造化エラー種別**：型エラー、パース失敗、実行時エラーを区別

---

## Option 型

`Option<T>` は「値がある (`Some`)」か「値がない (`None`)」かを安全に扱う型です。  
null / undefined の代替として使用し、`match` でパターンマッチングにより値を取り出します。

### Option の生成

```mryl
let a: Option<i32> = Some(42);   // 値あり
let b: Option<i32> = None;       // 値なし
```

### match によるパターンマッチング

```mryl
fn describe(opt: Option<i32>) -> i32 {
    return match opt {
        Some(v) => v,
        None    => -1,
    };
}

fn main() -> i32 {
    println("{}", describe(Some(10)));  // 10
    println("{}", describe(None));      // -1
    return 0;
}
```

### 関数の戻り値として

```mryl
fn safe_head(arr: i32[], n: i32) -> Option<i32> {
    if (n == 0) { return None; }
    return Some(arr[0]);
}
```

---

## Box 型（ヒープポインタ）

`Box<T>` は値をヒープに確保し、ポインタとして保持します。  
再帰的データ構造や動的割り当てが必要な場面で使用します。  
ネイティブコンパイル時は `T*`（`malloc` によるヒープ確保）に変換されます。

### Box の生成

```mryl
let b: Box<i32> = Box::new(42);
```

### デリファレンス（`*` 演算子）

```mryl
let val: i32 = *b;          // 42
println("{}", *b);
```

### .unbox() メソッド

```mryl
let val: i32 = b.unbox();   // *b と等価
```

### 多重ポインタ（`Box<Box<T>>`）

ネストした Box は `>>` が `RSHIFT` と衝突するため、内側から順に型引数を解釈します。

```mryl
let bb: Box<Box<i32>> = Box::new(Box::new(99));
let inner: Box<i32>   = *bb;
println("{}", *inner);           // 99
println("{}", (*bb).unbox());    // 99

// 3重・4重も同様
let bbb: Box<Box<Box<i32>>>      = Box::new(Box::new(Box::new(7)));
let bbbb: Box<Box<Box<Box<i32>>>> = Box::new(Box::new(Box::new(Box::new(3))));
```

### 自動メモリ解放（Auto Free）

`Box<T>` 変数は**スコープ終了時・`return` 文実行前**に自動的に `free` されます。
手動で `free` を呼ぶ必要はありません。

```mryl
fn example() {
    let b: Box<i32> = Box::new(10);
    println("{}", *b);
    // スコープ終了時に自動 free(b)
}
```

#### 多重ポインタの free 順序

`Box<Box<T>>` の場合、内側から外側の順に free されます。

```mryl
let bb: Box<Box<i32>> = Box::new(Box::new(5));
let inner: Box<i32>   = *bb;   // inner に内部ポインタを取り出し
// → free(bb) のみ（inner は別途 free される）

let bb2: Box<Box<i32>> = Box::new(Box::new(5));
// inner を取り出さない場合 → free(*bb2); free(bb2) の順
```

#### Vec<Box<T>>

`Box<T>[]`（可変長配列の各要素が Box）は、スコープ終了時に要素ごと free した後、配列本体も free されます。

```mryl
let boxes: Box<i32>[] = ...;
// → for 各要素 { free(element) } → free(boxes.data)
```

#### Option<Box<T>>

`Option<Box<T>>` 変数は、スコープ終了時に値が存在する場合のみ `free` されます。

```mryl
fn example() {
    let ob: Option<Box<i32>> = Some(Box::new(99));
    // スコープ終了時: if(ob.has_value) free(ob.value)
}
```

---

## 配列（固定長）

### 配列型
```mryl
let xs: i32[3];  // 3要素の i32 配列
```

### 配列リテラル
```mryl
let arr = [1, 2, 3, 4, 5];        // 型推論：i32[5]
let floats = [1.0, 2.5, 3.14];    // 型推論：f64[3]
```

### 配列アクセス
```mryl
let first = arr[0];
let second = arr[1];
```

### 配列代入
```mryl
arr[0] = 10;
arr[1] = 20;
```

---

## 可変長配列（T[]）

`T[]` 構文で宣言する動的サイズの配列（Vec）です。  
要素の追加・削除・挿入が実行時に行えます。

### 宣言と初期化

```mryl
// 空の動的配列
let nums: i32[] = [];

// 初期値あり
let floats: f64[] = [1.0, 2.0, 3.0];
```

### push / pop

```mryl
let v: i32[] = [];
v.push(10);
v.push(20);
v.push(30);
// v = [10, 20, 30]

let last = v.pop();     // 30 を取り出して削除
// v = [10, 20]
```

### len / is_empty

```mryl
let v: i32[] = [1, 2, 3];
println("{}", v.len());          // 3
println("{}", v.is_empty());     // false

let empty: i32[] = [];
println("{}", empty.is_empty()); // true
```

### インデックスアクセス

```mryl
let arr: i32[] = [10, 20, 30];
let first = arr[0];              // 10
arr[1] = 99;
println("{}", arr[1]);           // 99
```

### insert / remove

```mryl
let v: i32[] = [1, 2, 3];
v.insert(1, 99);     // インデックス 1 に 99 を挿入
// v = [1, 99, 2, 3]

let removed = v.remove(0);  // インデックス 0 を削除して返す
// removed = 1, v = [99, 2, 3]
```

### for-in によるイテレーション

```mryl
let items: string[] = ["a", "b", "c"];
for item in items {
    println("{}", item);
}
// a
// b
// c
```

### 条件式での is_empty

```mryl
let v: i32[] = [];
if (v.is_empty()) {
    println("empty");
}

v.push(1);
while (!v.is_empty()) {
    let x = v.pop();
    println("{}", x);
}
```

### C コード生成

動的配列は内部的に `MrylVec_<T>` 構造体としてコンパイルされます：

```c
typedef struct {
    int32_t* data;
    size_t   len;
    size_t   cap;
} MrylVec_int32_t;

static inline void mryl_vec_int32_t_push(MrylVec_int32_t* v, int32_t val) { ... }
static inline int32_t mryl_vec_int32_t_pop(MrylVec_int32_t* v) { ... }
// insert / remove も同様に生成
```

### API 一覧

| メソッド | 説明 | 戻り値 |
|----------|------|--------|
| `v.push(x)` | 末尾に追加 | void |
| `v.pop()` | 末尾を取り出して削除 | T |
| `v.len()` | 要素数を返す | i32 |
| `v.is_empty()` | 空なら true | bool |
| `v[i]` | インデックスアクセス | T |
| `v[i] = x` | インデックス代入 | void |
| `v.insert(i, x)` | インデックス i に挿入 | void |
| `v.remove(i)` | インデックス i を削除して返す | T |

---

## 型推論

Mryl は多くの場合で型を自動推論します：

```mryl
let x = 10;                    // i32
let y = 3.14;                  // f64
let s = "hello";               // string
let arr = [1, 2, 3];           // i32[3]
let result = add(5, 3);        // 関数の戻り値型から推論
```

---

## 型チェック

Mryl は静的型チェック言語です。以下の項目は コンパイル時にチェックされます：

### 変数型チェック
```mryl
let x: i32 = 10;
let y = x + 5;    // ✓ OK
let z = x + "5";  // ✗ エラー（型不一致）
```

### 関数引数型チェック
```mryl
fn process(x: i32) {
    println(x);
}

process(42);      // ✓ OK
process("hello"); // ✗ エラー
```

### 構造体フィールド型チェック
```mryl
struct Box {
    value: i32;
}

let b = Box { value: 42 };     // ✓ OK
let c = Box { value: "text" }; // ✗ エラー
```

### ジェネリック型推論
```mryl
fn add<T>(a: T, b: T) -> T {
    return a + b;
}

add(5, 10);        // ✓ OK（T = i32）
add(5, 3.14);      // ✗ エラー（型不一致）
```

---

## 組み込み関数

### print / println（フォーマット文字列対応）
```mryl
// シンプルな出力
print(42);
println("hello");

// フォーマット文字列（Rust 風）
let i = 10;
println("i = {}", i);

// 複数の変数
let x = 5;
let y = 20;
println("x = {}, y = {}", x, y);

// 複数変数の例
let name = "Mryl";
let version = 1;
println("Language: {}, Version: {}", name, version);
```

フォーマット文字列は最初の引数に `{}` を含める形式です。後続の引数が順番に `{}` に代入されます。

### to_string
```mryl
let n = 42;
let s = to_string(n);
println("Converted: {}", s);

// フォーマット文字列付き
let x = 100;
println(to_string("Value is {}", x));
```

### read_line / parse_int / parse_f64
```mryl
// 標準入力から1行読み取る
let line: string = read_line();
println("got={}", line);
```

`parse_int` / `parse_f64` は `Result<T, string>` を返します。`.try()` で値を取り出し、失敗時はパニックします：

```mryl
// .try() で値を取り出す（Err ならパニック）
let n: i32 = parse_int("42").try();    // 42
let f: f64 = parse_f64("3.14").try();  // 3.14

// match で安全に処理する
let r = parse_int("abc");   // Err("cannot parse 'abc' as i32")
let n2: i32 = match r {
    Ok(v)  => v,
    Err(e) => { println("Error: {}", e); -1 },
};
```

### checked_div

`checked_div(a, b)` はゼロ除算を安全に処理し、`Result<i32, string>` を返します。

```mryl
let r1 = checked_div(10, 3);   // Ok(3)
let r2 = checked_div(5, 0);    // Err("division by zero")

let val: i32 = match r1 {
    Ok(v)  => v,
    Err(e) => { println("{}", e); -1 },
};
println("{}", val);  // 3
```

通常の `/` や `%` 演算子でゼロ除算が発生した場合はランタイムパニックになります。安全に処理したい場合は `checked_div` を使ってください。

---

## string 組み込みメソッド

`string` 型の変数に対してドット記法でメソッドを呼び出せます。

```mryl
let s = "  Hello, World!  ";

// 文字列長（i32）
println("len={}", s.len());                        // 18

// 部分文字列を含むか（bool）
println("has={}", s.contains("World"));            // true

// 前方一致 / 後方一致（bool）
println("sw={}", "hello".starts_with("hel"));      // true
println("ew={}", "hello".ends_with("lo"));         // true

// 前後空白除去（string）
println("trim={}", s.trim());                      // Hello, World!

// 大文字 / 小文字変換（string）
println("up={}", "hello".to_upper());              // HELLO
println("lo={}", "WORLD".to_lower());              // world

// 置換（string）
println("rep={}", "foo bar foo".replace("foo", "baz")); // baz bar baz

// 部分文字列の位置（Option<i32>）
let pos = "hello world".find("world");
match pos {
    Some(i) => println("found at {}", i),  // found at 6
    None    => println("not found"),
};

// 区切り文字で分割（string[]）
let parts = "apple,banana,cherry".split(",");
println("{}", parts.len());   // 3
println("{}", parts[0]);      // apple
```

| メソッド | 引数 | 戻り値 | 説明 |
|----------|------|--------|------|
| `len()` | — | `i32` | 文字列の長さ |
| `contains(sub)` | `string` | `bool` | 部分文字列を含むか |
| `starts_with(pre)` | `string` | `bool` | 前方一致 |
| `ends_with(suf)` | `string` | `bool` | 後方一致 |
| `trim()` | — | `string` | 前後の空白・改行を除去 |
| `to_upper()` | — | `string` | 大文字変換 |
| `to_lower()` | — | `string` | 小文字変換 |
| `replace(from, to)` | `string, string` | `string` | 全出現箇所を置換 |
| `find(pat)` | `string` | `Option<i32>` | 最初の出現位置を返す（なければ `None`） |
| `split(sep)` | `string` | `string[]` | 区切り文字で分割した配列を返す |

---

## Iter\<T\> / LINQ スタイルコレクション操作

配列（`T[]`）に対して C# LINQ 準拠のメソッドチェーンでコレクション操作を記述できます。
`.iter()` 不要で、配列から直接チェーンを開始できます。

```mryl
let nums: i32[] = [1, 2, 3, 4, 5];

// filter → select → to_array チェーン
let result = nums
    .filter((x: i32) => x % 2 == 0)
    .select((x: i32) => x * 10)
    .to_array();

println("{}", result.len());   // 2
println("{}", result[0]);      // 20
println("{}", result[1]);      // 40

// aggregate（初期値なし）
let sum_r = nums.aggregate((a: i32, b: i32) => a + b);
match sum_r {
    Ok(s)  => println("sum={}", s),   // sum=15
    Err(e) => println("err={}", e),
};

// count / first / any / all
println("{}", nums.count());                         // 5
println("{}", nums.any((x: i32) => x > 4));          // true
println("{}", nums.all((x: i32) => x > 0));          // true

// for_each（副作用専用・文としてのみ使用可。let/fix/代入/return に使用不可）
nums.take(3).for_each((x: i32) => println("{}", x)); // 1 2 3
```

### API 一覧

#### 中間操作（チェーン可能・`Iter<T>` を返す）

| メソッド | 戻り値 | C# 対応 | 説明 |
|---|---|---|---|
| `select(fn(T)->U)` | `Iter<U>` | `Select` | 各要素を変換 |
| `filter(fn(T)->bool)` | `Iter<T>` | `Where` | 条件を満たす要素だけ残す |
| `take(n: i32)` | `Iter<T>` | `Take` | 先頭 n 件 |
| `skip(n: i32)` | `Iter<T>` | `Skip` | 先頭 n 件をスキップ |
| `select_many(fn(T)->U[])` | `Iter<U>` | `SelectMany` | map + flatten（v0.5.0 #65） |

#### 終端操作（評価・消費）

| メソッド | 戻り値 | C# 対応 | 説明 |
|---|---|---|---|
| `to_array()` | `T[]` | `ToArray` | 配列に変換 |
| `aggregate(fn(T,T)->T)` | `Result<T, string>` | `Aggregate` | 初期値なし畳み込み |
| `aggregate(init, fn(U,T)->U)` | `U` | `Aggregate` | 初期値あり畳み込み |
| `for_each(fn(T)->void)` | `void` | `ForEach` | 副作用専用・文としてのみ使用可（`let`/`fix`/代入/`return` 不可） |
| `count()` | `i32` | `Count` | 要素数 |
| `first()` | `Result<T, string>` | `First` | 先頭要素（空なら `Err`） |
| `any(fn(T)->bool)` | `bool` | `Any` | 条件を満たす要素が存在するか |
| `all(fn(T)->bool)` | `bool` | `All` | 全要素が条件を満たすか |

---

## まとめ

Mryl は以下の特徴を備えた最小限の本格プログラミング言語です：

✓ 静的型付け＋型推論  
✓ 複数の数値型（8種類の整数型 + 2種類の浮動小数点型）  
✓ 自動型昇格（型の互換性を維持）  
✓ **コンパイル時定数（const）**  
✓ **条件付きコンパイル（#ifdef, #ifndef, #if）**  
✓ ジェネリック関数・構造体  
✓ 構造体とフィールドアクセス・メソッド定義（impl）  
✓ **enum**（シンプル / データ付き、Rust 風代数的データ型）  
✓ **match 式**（enum パターンマッチング、値マッチング）  
✓ **Result\<T,E\>**（`Ok` / `Err` + `.try()` エラー伝播）  
✓ **構造化エラー出力**（タイムスタンプ + スタックトレース + 行番号）  
✓ 配列（固定長）と **可変長配列**（`T[]`、push/pop/insert/remove/len/is_empty）  
✓ 制御構文（if/else, while, for Rust風・包含 `to`・C風）  
✓ **break / continue**（while/for 全形式対応）  
✓ インクリメント/デクリメント演算子  
✓ フォーマット文字列（`println("Value: {}", x)` 形式）  
✓ **ラムダ式**（`(x, y) => x + y`）  
✓ **fn 型パラメータ**（高階関数・コールバック）  
✓ **fix キーワード**（不変変数・不変関数パラメータ）  
✓ **前方宣言**（`fn name(...) -> T;` による相互再帰）  
✓ **Option\<T\>**（`Some` / `None` + match パターンマッチ）  
✓ **Box\<T\>**（ヒープポインタ / `*` deref / `.unbox()` / 多重ポインタ / スコープ自動 free / `Vec<Box<T>>` 対応）  
✓ **string 操作**（連結 `+`、比較 `==` / `!=`、組み込みメソッド 11 種）  
✓ **Iter\<T\> / LINQ**（`filter` / `select` / `take` / `skip` / `to_array` / `aggregate` / `for_each` / `count` / `first` / `any` / `all` / `select_many`）  
✓ **ユーザー入力**（`read_line()` / `parse_int()` / `parse_f64()`（`Result<T, string>` 返し）/ `checked_div()`）  
✓ **async / await**（状態機械 + シングルスレッドスケジューラ、`-lpthread` 不要）  
✓ Python インタプリタ + C コードジェネレータの二重実行エンジン  

学習用言語としても、趣味の言語としても十分な完成度を持っています。

## テストファイル

実装済みの全機能は以下のテストファイルで検証可能：

| ファイル | 内容 | 状態 |
|----------|------|------|
| [tests/test_01_types.ml](../tests/test_01_types.ml) | 基本型・変数宣言・型推論・型キャスト・型昇格 | ✅ Python + C + Native |
| [tests/test_02_operators.ml](../tests/test_02_operators.ml) | 算術/比較/論理/ビット/複合代入/インクリメント | ✅ Python + C + Native |
| [tests/test_03_control.ml](../tests/test_03_control.ml) | if-else / while / for Rust風 / for C風 / break / continue | ✅ Python + C + Native |
| [tests/test_04_functions.ml](../tests/test_04_functions.ml) | 基本関数 / 再帰 / ラムダ式 / ジェネリック | ✅ Python + C + Native |
| [tests/test_05_struct.ml](../tests/test_05_struct.ml) | 構造体 / メソッド / ジェネリック構造体 | ✅ Python + C + Native |
| [tests/test_06_enum_match.ml](../tests/test_06_enum_match.ml) | enum / match 式 | ✅ Python + C + Native |
| [tests/test_07_result.ml](../tests/test_07_result.ml) | Result&lt;T,E&gt; / Ok / Err / match / .try() | ✅ Python + C + Native |
| [tests/test_08_array.ml](../tests/test_08_array.ml) | 固定長配列 / 可変長配列（Vec） | ✅ Python + C + Native |
| [tests/test_09_const_compile.ml](../tests/test_09_const_compile.ml) | const / #ifdef / #ifndef / #if / #else | ✅ Python + C + Native |
| [tests/test_10_async_await.ml](../tests/test_10_async_await.ml) | async / await / ネスト待機 | ✅ Python + C + Native |
| [tests/test_11_builtin.ml](../tests/test_11_builtin.ml) | print / println / to_string | ✅ Python + C + Native |
| [tests/test_12_type_check.ml](../tests/test_12_type_check.ml) | 型宣言 / 型推論 / 型チェック / 型昇格 | ✅ Python + C + Native |
| [tests/test_13_boundary_numeric.ml](../tests/test_13_boundary_numeric.ml) | 数値型境界値（C0・境界値分析） | ✅ Python + C + Native |
| [tests/test_14_branch_coverage.ml](../tests/test_14_branch_coverage.ml) | 条件分岐網羅（C0/C1/MC/DC） | ✅ Python + C + Native |
| [tests/test_15_loop_boundary.ml](../tests/test_15_loop_boundary.ml) | ループ境界値（while/for/break/continue）| ✅ Python + C + Native |
| [tests/test_16_async_lambda.ml](../tests/test_16_async_lambda.ml) | async ラムダ式（定義・呼び出し・await 待機・ネスト await） | ✅ Python + C + Native |
| [tests/test_17_higherorder.ml](../tests/test_17_higherorder.ml) | 高階関数・ラムダ応用・前方宣言・相互再帰 | ✅ Python + C + Native |
| [tests/test_18_string_ops.ml](../tests/test_18_string_ops.ml) | string 操作（連結・比較・組み込みメソッド） | ✅ Python + C + Native |
| [tests/test_19_nested_struct.ml](../tests/test_19_nested_struct.ml) | ネスト struct・struct 配列 | ✅ Python + C + Native |
| [tests/test_20_callback.ml](../tests/test_20_callback.ml) | fn 型パラメータ（コールバック） | ✅ Python + C + Native |
| [tests/test_21_fix.ml](../tests/test_21_fix.ml) | `fix` キーワード（不変変数・不変引数） | ✅ Python + C + Native |
| [tests/test_22_input.ml](../tests/test_22_input.ml) | ユーザー入力（`read_line` / `parse_int` / `parse_f64`） | ✅ Python + C + Native |
| [tests/test_23_static.ml](../tests/test_23_static.ml) | `static fn` / `::` 呼び出し / fn 型参照 | ✅ Python + C + Native |
| [tests/test_24_zero_div.ml](../tests/test_24_zero_div.ml) | ゼロ除算安全（`checked_div` / 境界値分析） | ✅ Python + C + Native |
| [tests/test_25_parse_result.ml](../tests/test_25_parse_result.ml) | `parse_int` / `parse_f64` の Result 返し | ✅ Python + C + Native |
| [tests/test_26_option.ml](../tests/test_26_option.ml) | `Option<T>`（`Some` / `None` / match パターン） | ✅ Python + C + Native |
| [tests/test_27_match_wildcard.ml](../tests/test_27_match_wildcard.ml) | match ワイルドカードパターン（`_` 全面対応） | ✅ Python + C + Native |
| [tests/test_28_box.ml](../tests/test_28_box.ml) | `Box<T>`（生成・`*` deref・`.unbox()`・多重ポインタ）| ✅ Python + C + Native |
| [tests/test_29_string_find.ml](../tests/test_29_string_find.ml) | `string.find()`（`Option<i32>` 返し・各種パターン） | ✅ Python + C + Native |
| [tests/test_30_string_split.ml](../tests/test_30_string_split.ml) | `string.split()`（区切り文字・境界値・空文字） | ✅ Python + C + Native |
| [tests/test_31_iter_linq.ml](../tests/test_31_iter_linq.ml) | `Iter<T>` / LINQ 全 12 メソッド（C0/C1/MC/DC） | ✅ Python + C + Native |
| [tests/test_32_iter_chain_free.ml](../tests/test_32_iter_chain_free.ml) | チェーン中間 `MrylVec` のメモリ解放（#62） | ✅ Python + C + Native |
| [tests/test_33_select_many.ml](../tests/test_33_select_many.ml) | `select_many` C コード生成（#65、C0/C1/MC/DC） | ✅ Python + C + Native |
| [tests/test_34_closure_capture.ml](../tests/test_34_closure_capture.ml) | クロージャキャプチャ fat pointer 実装（#44、C0/C1/MC/DC） | ✅ Python + C + Native |
| [tests/test_35_box_free.ml](../tests/test_35_box_free.ml) | `Box<T>` 自動 free（スコープ・return・ループ・多重・`Vec<Box<T>>`、#66） | ✅ Python + C + Native |
| [tests/test_36_for_each_void_stmt.ml](../tests/test_36_for_each_void_stmt.ml) | `for_each` void 文式・キャプチャあり fat pointer ラムダ（#64） | ✅ Python + C + Native |
| [tests/test_37_iter_lambda_typecheck.ml](../tests/test_37_iter_lambda_typecheck.ml) | `Iter<T>` メソッドへのラムダ引数型検査（#63、C0/C1/MC/DC） | ✅ Python + C + Native |
| [tests/test_38_async_result.ml](../tests/test_38_async_result.ml) | `async fn` + `Result<T,E>` FAULTED 状態伝播（#51） | ✅ Python + C + Native |
| [tests/test_42_iter_lambda_param_count.ml](../tests/test_42_iter_lambda_param_count.ml) | `Iter<T>` ラムダ引数数チェック（#69、C0） | ✅ Python + C + Native |
| [tests/test_43_task_when_all_any.ml](../tests/test_43_task_when_all_any.ml) | `Task::when_all` / `Task::when_any` コンビネータ（#61、C0/C1） | ✅ Python + C + Native |
| [tests/test_44_async_cancel.ml](../tests/test_44_async_cancel.ml) | `weak` / `cancel` Task キャンセル機構（#52、C0/C1） | ✅ Python + C + Native |

実行方法は「[セットアップ](#セットアップ)」を参照してください。

---

## トラブルシューティング

### GCC が見つからない

```
FileNotFoundError: [WinError 2] 指定されたファイルが見つかりません: 'C:\cygwin64\bin\bash.exe'
```

**原因**: Cygwin がインストールされていない、またはパスが違う。

**解決策**:

1. [Cygwin](https://www.cygwin.com/) をインストールし、`gcc-core` パッケージを選択する
2. `core/Mryl.py` 内の `CYGWIN_BASH` 定数を実際のインストールパスに変更する

```python
# core/Mryl.py の先頭付近を確認して変更
CYGWIN_BASH = r"C:\cygwin64\bin\bash.exe"  # 実際のパスに変更
```

---

### Python バージョンエラー

```
SyntaxError: ...
```

**原因**: Python 3.9 未満を使用している。

**解決策**: `python --version` でバージョンを確認し、Python 3.9 以上を使用する。

---

### C コンパイルは成功するが実行結果が Python と違う

**原因**: `f64` の `println` フォーマットや `bool` の表示など、バージョン間の挙動差異が残っている可能性。

**解決策**: [Issues](https://github.com/Mryl-Dev/Mryl/issues) に報告するか、`tests/` 下の類似テストファイルで同様の機能を確認する。

---

### `ParseError` が出る

**原因**: `parse_int()` / `parse_f64()` は `Result<T, string>` を返します。`.try()` を呼んだとき、入力が無効な数値だと実行時パニックします。

```mryl
// parse_int は Result<i32, string> を返す
let r = parse_int("abc");   // Err("cannot parse 'abc' as i32")
let n = r.try();            // ← ここで ParseError パニック
```

**解決策**: `.try()` の前に `match` で `Ok` / `Err` を確認する：

```mryl
let r = parse_int(read_line());
let n: i32 = match r {
    Ok(v)  => v,
    Err(e) => { println("Error: {}", e); 0 },
};
```

---

### `TypeError` が発生する

`fix` 変数への再代入・型の不一致などが原因です。エラーメッセージに行番号が表示されるので、その行を確認する。

```
TypeError at line 5: cannot assign to fix variable 'x'
```
