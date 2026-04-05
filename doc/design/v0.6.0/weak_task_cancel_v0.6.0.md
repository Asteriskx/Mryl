# weak Task / cancel 詳細設計書 (v0.6.0)

## 概要

issue #52 として実装する `weak(handle)` / `cancel(token)` 機能。
Task への弱参照（`WeakTask<T>`）を取得し、外部からキャンセルする機構を追加する。

**方針決定（2026-04-02）**
- `await` の戻り値型は **変更しない**（`T` のまま）
- キャンセルは「Task を捨てる」操作として設計規約化
- キャンセル済み Task は `await` しない（した場合は panic）
- `?` 系演算子（`?.` `??`）の設計は将来課題として分離（issue 化済み）

```mryl
async fn long_task(n: i32) -> i32 {
    return n * 2;
}

fn main() {
    let handle = long_task(42);
    let token: WeakTask<i32> = weak(handle);  // 弱参照取得

    cancel(token);  // Task をキャンセル（handle は捨てる）
    // await handle は行わない（設計規約）
}
```

---

## C ランタイム側の現状

以下はすでに `CodeGenerator/_async.py` の `_emit_task_runtime()` で生成済み：

| 関数/フィールド | 内容 |
|--------------|------|
| `MrylTask.weak_count` | 弱参照カウント |
| `MrylTask.on_cancel` | キャンセル時フック（NULL 初期化済み）|
| `MRYL_TASK_CANCELLED` | キャンセル状態の enum 値 |
| `__task_weak_retain(t)` | weak_count++ して pointer を返す |
| `__task_weak_release(t)` | weak_count--、0 なら free |
| `__task_cancel(t)` | state を CANCELLED に変更、awaiter を再スケジュール |
| `__task_lock(t)` | CANCELLED/COMPLETED でなければ strong_count++ |

**Mryl 構文側（Lexer/Parser/TypeChecker/Interpreter/CodeGenerator）が未実装。**

---

## 型設計

### `WeakTask<T>`

```
TypeNode("WeakTask", type_args=[T])
```

C コード上の表現は `Future<T>`（`MrylTask*`）と同一。
ただし型チェッカーが `cancel()` 引数としてのみ使用を許可し、`await` には使用不可とする。

### 型規則

| 式 | 引数型 | 戻り値型 |
|----|--------|---------|
| `weak(handle)` | `Future<T>` | `WeakTask<T>` |
| `cancel(token)` | `WeakTask<T>` | `void` |
| `await handle` | `Future<T>` | `T`（変更なし）|

---

## 実装箇所

### 1. Lexer.py — `weak` キーワード追加

`KEYWORDS` に追加：
```python
"weak": TokenKind.WEAK,
```

`TokenKind` に `WEAK = auto()` を追加。

`cancel` はキーワードにしない。既存の識別子として Parser/TypeChecker 側で組み込み関数として処理する。

### 2. Parser.py — `weak(expr)` パース

`parse_unary()` 内に追加：

```python
if self.current().kind == TokenKind.WEAK:
    tok = self.advance()
    self.expect(TokenKind.LPAREN)
    expr = self.parse_expr()
    self.expect(TokenKind.RPAREN)
    return WeakExpr(expr, tok.line, tok.column)
```

`cancel(expr)` は既存の関数呼び出し `CallExpr` として処理（識別子扱い）。

### 3. Ast.py — `WeakExpr` ノード追加

```python
class WeakExpr:
    def __init__(self, expr, line, column):
        self.expr   = expr   # Future<T> を返す式
        self.line   = line
        self.column = column
```

### 4. TypeChecker/_expr.py — 型規則追加

**`WeakExpr` の型チェック：**
```python
if isinstance(expr, WeakExpr):
    inner = self.check_expr(expr.expr)
    if inner.name != "Future" or not inner.type_args:
        raise TypeError_("weak() requires Future<T>", expr)
    return TypeNode("WeakTask", type_args=[inner.type_args[0]])
```

**`cancel()` 組み込み関数の型チェック（_call.py）：**
```python
if func_name == "cancel" and len(args) == 1:
    arg_type = self.check_expr(args[0])
    if arg_type.name != "WeakTask":
        raise TypeError_("cancel() requires WeakTask<T>", ...)
    return TypeNode("void")
```

**`await` に `WeakTask<T>` を渡した場合のエラー：**
```python
# check_await 内
if handle_type.name == "WeakTask":
    raise TypeError_("cannot await WeakTask<T>; await Future<T> only", expr)
```

### 5. Interpreter.py — weak / cancel 評価

**`WeakExpr` の評価：**
```python
if isinstance(expr, WeakExpr):
    task = self.eval_expr(expr.expr)
    # Python 側では asyncio.Task の wrap として弱参照を表現
    return {'__weak_task__': True, 'task': task.get('task')}
```

**`cancel()` 組み込み関数の評価：**
```python
if func_name == "cancel" and len(args) == 1:
    token = self.eval_expr(args[0])
    if token.get('__weak_task__') and token.get('task'):
        token['task'].cancel()
    return None
```

### 6. CodeGenerator/_expr.py — C コード生成

**`WeakExpr`：**
```python
if isinstance(expr, WeakExpr):
    inner = self._gen_expr(expr.expr)
    return f"__task_weak_retain({inner})"
```

**`cancel()` 組み込み関数呼び出し：**
```python
# _gen_call() 内
if func_name == "cancel" and len(args) == 1:
    arg = self._gen_expr(args[0])
    return f"__task_cancel({arg})"
```

### 7. CodeGenerator/_type.py — `WeakTask<T>` の C 型変換

```python
if node.name == "WeakTask":
    return "MrylTask*"  # Future<T> と同一表現
```

---

## イレギュラー点検

| 懸念 | 内容 | 対応 |
|------|------|------|
| キャンセル済み Task の await | `await` した場合 C ランタイムは `MRYL_TASK_CANCELLED` チェックで処理を止めるが、結果は返らない。現状ではブロックのまま | TypeChecker で `WeakTask` を `await` させない制約を追加 |
| `weak(handle)` 後に `handle` も使えてしまう | 所有権概念なし（Mryl の現設計では許容） | 設計規約として文書化。将来の所有権機能で対応 |
| `cancel()` を複数回呼ぶ | `__task_cancel()` は `PENDING/RUNNING` のときのみ遷移するため冪等 | 問題なし |
| `weak(weak(handle))` | `WeakTask<T>` に `weak()` は型エラー（`Future<T>` 以外は拒否） | TypeChecker で弾く |
| `when_all` / `when_any` と cancel の組み合わせ | キャンセルされた Task が `when_all` に含まれる場合 `CANCELLED` 状態で完了扱いになる | 既存 `when_any` は `CANCELLED` を終了条件に含めている（実装済み）|

---

## テスト設計

**ファイル**: `tests/test_44_async_cancel.ml`

| ケース | 観点 |
|--------|------|
| A: `weak()` + `cancel()` の基本動作 | C0 |
| B: キャンセル前に Task が完了している場合（cancel は何もしない）| C1 |
| C: `when_any` + cancel（タイムアウトパターン）| 実用パターン |
| D: 複数 Task の一部をキャンセル | C1 |

---

## 実装タスク一覧

- [ ] `Lexer.py` — `TokenKind.WEAK` + `KEYWORDS["weak"]` 追加
- [ ] `Ast.py` — `WeakExpr` ノード追加
- [ ] `Parser.py` — `weak(expr)` パース追加
- [ ] `TypeChecker/_expr.py` — `WeakExpr` 型チェック追加
- [ ] `TypeChecker/_call.py` — `cancel()` 型チェック追加
- [ ] `TypeChecker/_expr.py` — `await WeakTask<T>` エラー追加
- [ ] `TypeChecker/_type.py` — `WeakTask<T>` 型登録（必要に応じて）
- [ ] `Interpreter.py` — `WeakExpr` / `cancel()` 評価追加
- [ ] `CodeGenerator/_expr.py` — `WeakExpr` / `cancel()` コード生成追加
- [ ] `CodeGenerator/_type.py` — `WeakTask<T>` → `MrylTask*` 変換追加
- [ ] `tests/test_44_async_cancel.ml` — テストファイル作成

---

## 関連

- `issue_weak_task_cancel.md`（#52）
- `issue_question_mark_operator.md`（将来課題）
- `issue_null_operators.md`（将来課題）
