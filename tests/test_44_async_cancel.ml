// ============================================================
// Test 44: weak / cancel — Task キャンセル機構 (fix #52)
//   async Task への弱参照取得とキャンセルの基本動作を確認。
//
//   A. cancel 前に Task が完了 → cancel は何もしない（冪等）
//   B. weak() で WeakTask<T> を取得 → 型チェックが通ること
//   C. when_any + cancel パターン（タイムアウト的な使い方）
//   D. 複数 Task の一部をキャンセル
//
// カバレッジ観点:
//   C0: weak / cancel を各 1 回以上実行
//   C1: 完了済み Task への cancel（冪等確認）/ 未完了 Task への cancel
// ============================================================

async fn ret_val(v: i32) -> i32 { return v; }
async fn ret_str(s: string) -> string { return s; }

// ── A: 完了済み Task に cancel しても問題ない（冪等）────────
fn test_a() {
    let handle = ret_val(42);
    let result: i32 = await handle;
    // 完了後に弱参照を取得して cancel → 何もしない
    let t2 = ret_val(99);
    let token: WeakTask<i32> = weak(t2);
    let r2: i32 = await t2;
    cancel(token);  // 完了済みへの cancel は冪等
    println("A1: {}", result);  // 42
    println("A2: {}", r2);      // 99
}

// ── B: weak() で WeakTask<T> を取得できること ───────────────
fn test_b() {
    let handle = ret_val(10);
    let token: WeakTask<i32> = weak(handle);
    cancel(token);
    // cancel 後は handle を await しない（設計規約）
    println("B1: ok");
}

// ── C: when_any + cancel（タイムアウトパターン）────────────
fn test_c() {
    let t1 = ret_val(1);
    let t2 = ret_val(2);
    let tok2: WeakTask<i32> = weak(t2);
    // when_any で最初に完了した Task の結果を取得
    let first: i32 = await Task::when_any([t1, t2]);
    // 負けた方をキャンセル（FIFO スケジューラなので t1 が先に完了）
    cancel(tok2);
    println("C1: {}", first);   // 1
}

// ── D: 複数 Task の一部をキャンセル ─────────────────────────
fn test_d() {
    let ta = ret_val(100);
    let tb = ret_val(200);
    let tc = ret_val(300);
    let tok_b: WeakTask<i32> = weak(tb);
    let tok_c: WeakTask<i32> = weak(tc);
    cancel(tok_b);
    cancel(tok_c);
    // ta だけ await する
    let ra: i32 = await ta;
    println("D1: {}", ra);      // 100
}

fn main() {
    test_a();
    test_b();
    test_c();
    test_d();
    println("=== OK ===");
}
