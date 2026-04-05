# Observable<T> / Subject<T> 詳細設計書 (v0.6.0)

## 概要

issue #45 として実装するリアクティブストリーム機能。
`Subject<T>` が値を push し、`Observable<T>` がパイプラインを構成、`subscribe()` で購読する。

---

## v0.6.0 スコープ確定

| 機能 | v0.6.0 | 理由 |
|------|--------|------|
| `Subject<T>::new()` / `emit()` / `complete()` / `error()` | ✅ | 核心機能 |
| `filter()` / `map()` / `take()` / `skip()` | ✅ | 基本オペレータ |
| `merge()` | ✅ | 複数ソース合流（async 不要） |
| `subscribe()` / `Subscription` / `unsubscribe()` | ✅ | 購読管理 |
| `debounce()` | ❌ v0.7.0 | タイマー未実装 |
| `next_async()` | ❌ v0.7.0 | async↔Observable 橋渡しが複雑 |

---

## 型設計

### `Subject<T>` と `Observable<T>` の分離

```
Subject<T>     = 値を emit する発信源（cold → hot への変換点）
Observable<T>  = Subject<T> にオペレータを繋げたパイプライン
```

C# Rx.NET と同じ論法で分離する。
`Subject<T>` は `Observable<T>` のサブタイプとして扱い、
オペレータは `Subject<T>` / `Observable<T>` どちらに対しても適用可能。

### `Subscription`

`IDisposable` 相当の独立型。`WeakTask<T>` とは無関係。

```mryl
let sub: Subscription = subject.subscribe((x: i32) => { println("{}", x); });
sub.unsubscribe();
```

### 型一覧

| Mryl 型 | C 表現 | 説明 |
|---------|--------|------|
| `Subject<T>` | `MrylSubject_T*` | 発信源構造体ポインタ |
| `Observable<T>` | `MrylObservable_T*` | パイプライン構造体ポインタ |
| `Subscription` | `MrylSubscription*` | 購読ハンドル構造体ポインタ |

---

## 構文・API 仕様

### Subject の生成と操作

```mryl
let subject: Subject<i32> = Subject<i32>::new();

subject.emit(42);          // 購読者に値をプッシュ
subject.complete();        // ストリーム正常終了
subject.error("oops");     // エラーをプッシュ（購読者の onError を呼ぶ）
```

### 中間オペレータ（`Observable<T>` を返す）

```mryl
let obs: Observable<i32> = subject
    .filter((x: i32) -> bool { return x > 0; })
    .map((x: i32) -> i32 { return x * 2; })
    .take(5)
    .skip(1);
```

| メソッド | シグネチャ | 説明 |
|----------|-----------|------|
| `filter` | `fn(fn(T) -> bool) -> Observable<T>` | 条件フィルタ |
| `map` | `fn(fn(T) -> U) -> Observable<U>` | 型変換 |
| `take` | `fn(i32) -> Observable<T>` | 先頭 n 件で complete |
| `skip` | `fn(i32) -> Observable<T>` | 先頭 n 件をスキップ |
| `merge` | `fn(Observable<T>) -> Observable<T>` | 2 ストリームを合流 |

### 終端操作（`Subscription` を返す）

```mryl
// 値のみ購読
let sub: Subscription = subject.subscribe((x: i32) => { println("{}", x); });

// 値 / エラー / 完了ハンドラを指定
let sub2: Subscription = subject.subscribe(
    (x: i32) => { println("next: {}", x); },
    (e: string) => { println("error: {}", e); },
    () => { println("complete"); }
);

sub.unsubscribe();  // 購読解除
```

---

## C コード生成設計

### 構造体定義（`_header.py` に追加）

型ごとにモノモーフ（Iter<T> / Vec<T> と同様の方式）。

```c
/* Subject<i32> の例 */
typedef void (*MrylSubject_i32_OnNext)(int32_t, void*);
typedef void (*MrylSubject_i32_OnError)(const char*, void*);
typedef void (*MrylSubject_i32_OnComplete)(void*);

typedef struct MrylSubscription_i32 {
    MrylSubject_i32_OnNext     on_next;
    MrylSubject_i32_OnError    on_error;
    MrylSubject_i32_OnComplete on_complete;
    void*                      ctx;       // クロージャ環境（fat pointer の env）
    int                        active;    // 1=購読中, 0=解除済み
    struct MrylSubscription_i32* next;    // 連結リスト（複数購読者）
} MrylSubscription_i32;

typedef struct MrylSubject_i32 {
    MrylSubscription_i32* subscribers; // 購読者連結リスト先頭
    int                   completed;   // 1=complete 済み
    int                   errored;     // 1=error 済み
} MrylSubject_i32;
```

### Observable パイプライン

オペレータは「ラップされた Subject」として実装する。
`filter` / `map` は新しい Subject を生成し、上流の subscribe 時に変換ロジックを挟む。

```c
/* filter の概念的な実装 */
// filter(pred) → 新しい MrylSubject_i32 を生成
// 上流.subscribe(x => { if (pred(x)) downstream.emit(x); })
```

C 生成の具体的な命名規則：
- Subject 構造体：`MrylSubject_{T}`
- Subscription 構造体：`MrylSubscription_{T}`
- emit 関数：`mryl_subject_{T}_emit(s, val)`
- subscribe 関数：`mryl_subject_{T}_subscribe(s, on_next, on_error, on_complete, ctx)`
- unsubscribe 関数：`mryl_subscription_{T}_unsubscribe(sub)`

### emit の C 生成

```c
static inline void mryl_subject_i32_emit(MrylSubject_i32* s, int32_t val) {
    if (s->completed || s->errored) return;
    MrylSubscription_i32* cur = s->subscribers;
    while (cur) {
        if (cur->active && cur->on_next) cur->on_next(val, cur->ctx);
        cur = cur->next;
    }
}
```

---

## Python インタプリタ側設計

`Subject<T>` を購読者リストを持つ dict として表現する。

```python
# Subject<T> の内部表現
{
    '__subject__': True,
    'elem_type': 'i32',
    'subscribers': [],   # list of {'on_next': fn, 'on_error': fn, 'on_complete': fn, 'active': True}
    'completed': False,
    'errored': False,
}

# Subscription の内部表現
{
    '__subscription__': True,
    'subject': <subject_dict>,
    'handler': <handler_dict>,
}
```

### MethodCall の評価ルール

| メソッド | 対象型 | 動作 |
|---------|--------|------|
| `emit(v)` | Subject | 全 active 購読者の on_next を呼ぶ |
| `complete()` | Subject | completed=True、全購読者の on_complete を呼ぶ |
| `error(msg)` | Subject | errored=True、全購読者の on_error を呼ぶ |
| `filter(fn)` | Subject/Observable | 新 Observable を生成（上流に subscribe 登録）|
| `map(fn)` | Subject/Observable | 新 Observable を生成（変換あり）|
| `take(n)` | Subject/Observable | n 件後に自動 unsubscribe |
| `skip(n)` | Subject/Observable | 先頭 n 件を無視 |
| `merge(obs)` | Observable | 2 つのソースを合流 |
| `subscribe(fn)` | Subject/Observable | Subscription を返す |
| `unsubscribe()` | Subscription | active=False に設定 |

---

## TypeChecker 設計

### 型登録

- `Subject<T>` → `TypeNode("Subject", type_args=[T])`
- `Observable<T>` → `TypeNode("Observable", type_args=[T])`
- `Subscription` → `TypeNode("Subscription")`

### 型規則

| 式 | 型 |
|----|-----|
| `Subject<i32>::new()` | `Subject<i32>` |
| `subject.emit(v: T)` | `void` |
| `subject.complete()` | `void` |
| `subject.error(msg: string)` | `void` |
| `obs.filter(fn: fn(T)->bool)` | `Observable<T>` |
| `obs.map(fn: fn(T)->U)` | `Observable<U>` |
| `obs.take(n: i32)` | `Observable<T>` |
| `obs.skip(n: i32)` | `Observable<T>` |
| `obs.merge(other: Observable<T>)` | `Observable<T>` |
| `obs.subscribe(fn: fn(T)->void)` | `Subscription` |
| `sub.unsubscribe()` | `void` |

### Subject<T> は Observable<T> として扱う

TypeChecker の `check_method_call` において、`Subject<T>` に対してオペレータを適用した場合も `Observable<T>` を返すように処理する。

---

## Lexer / Parser / Ast への影響

### 新規キーワード

なし。`Subject` / `Observable` / `Subscription` は識別子として扱い、
`Subject<i32>::new()` は既存の `EnumVariantExpr`（`Task::when_all` と同方式）でパース可能。

### Ast への追加

なし。既存の `MethodCall` / `EnumVariantExpr` で表現できる。

---

## イレギュラー点検

| 懸念 | 内容 | 対応 |
|------|------|------|
| complete/error 後の emit | `completed` / `errored` フラグで即 return | C・Python 両方で実装 |
| unsubscribe 後の on_next 呼び出し | `active` フラグチェックで skip | 連結リスト走査中でも安全 |
| map で型変換（T → U）の Subject 生成 | 型ごとにモノモーフの Subject が必要 | 使用型を scan して生成 |
| 複数 subscribe の順序保証 | 連結リストを追加順に走査 | FIFO 保証 |
| filter チェーン中の subscribe 解除 | 中間 Observable の subscription も解除が必要 | unsubscribe は上流まで伝播させる |
| merge で両ソースが complete した場合 | 両方 complete 後にダウンストリームに complete | カウンタで管理 |
| `Subject<T>` に `await` / `weak` を使う | TypeChecker でエラー（Future<T> 以外は拒否） | 既存の型チェックで弾かれる |

---

## テスト設計

**ファイル**: `tests/test_45_observable.ml`

| ケース | 観点 |
|--------|------|
| A: emit → subscribe の基本動作 | C0 |
| B: filter でスキップ確認 | C1 |
| C: map で型変換 | C0 |
| D: take で件数制限 | C1（n=0 / n>0）|
| E: skip で先頭スキップ | C1 |
| F: complete / error ハンドラ | C1 |
| G: unsubscribe 後は on_next が来ない | C1 |
| H: filter + map チェーン | C0 |
| I: merge（2 ソース合流）| C0 |
| J: 複数 subscribe | C0 |

---

## 実装タスク一覧

- [ ] `TypeChecker/_expr.py` — `Subject<T>::new()` 型チェック追加
- [ ] `TypeChecker/_call.py` — `subscribe()` / `unsubscribe()` / `emit()` 型チェック追加
- [ ] `TypeChecker/_expr.py` — `filter` / `map` / `take` / `skip` / `merge` 型チェック追加
- [ ] `Interpreter.py` — `Subject<T>` / `Observable<T>` / `Subscription` 評価追加
- [ ] `CodeGenerator/_header.py` — `MrylSubject_T` / `MrylSubscription_T` 構造体 + 関数 emit 追加
- [ ] `CodeGenerator/_type.py` — `Subject<T>` / `Observable<T>` / `Subscription` → C 型変換追加
- [ ] `CodeGenerator/_stmt.py` — let 文での Subject / Observable / Subscription 変数生成
- [ ] `CodeGenerator/_expr.py` — `Subject<T>::new()` / オペレータ / subscribe コード生成
- [ ] `tests/test_45_observable.ml` — テストファイル作成

---

## 関連

- `issue_observable_rx.md`（#45）
- `issue_observable_debounce_v0.7.0.md`（v0.7.0 課題）
- `issue_observable_next_async_v0.7.0.md`（v0.7.0 課題）
- `doc/discussion/discussion_null_async_design_2026-04-02_190651.md`
