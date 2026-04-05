// ============================================================
// Test 43: Task::when_all / Task::when_any コンビネータ (fix #61)
//   複数 Task を同時待機するコンビネータの基本動作を確認。
//
//   A. when_all i32×3     → 3要素の結果配列が返る
//   B. when_all i32×1     → 1要素の結果配列が返る
//   C. when_any i32×2     → 最初に完了した値が返る (FIFO → t1)
//   D. when_any i32×1     → 1要素の when_any
//   E. when_all f64×2     → 2要素の結果配列が返る (型汎用性確認)
//
// カバレッジ観点:
//   C0: when_all / when_any を各 1 回以上実行
//   C1: 要素数 1 / 複数のケースを両方カバー
// ============================================================

// ── helper async fn ──────────────────────────────────────────
async fn ret_i32(v: i32) -> i32 { return v; }
async fn ret_f64(v: f64) -> f64 { return v; }

// ── A: when_all (i32×3) ─────────────────────────────────────
fn test_a() {
    let t1 = ret_i32(10);
    let t2 = ret_i32(20);
    let t3 = ret_i32(30);
    let results: i32[] = await Task::when_all([t1, t2, t3]);
    println("A1: {}", results.len());   // 3
    println("A2: {}", results[0]);      // 10
    println("A3: {}", results[1]);      // 20
    println("A4: {}", results[2]);      // 30
}

// ── B: when_all (要素数 1) ───────────────────────────────────
fn test_b() {
    let t1 = ret_i32(99);
    let results: i32[] = await Task::when_all([t1]);
    println("B1: {}", results.len());   // 1
    println("B2: {}", results[0]);      // 99
}

// ── C: when_any (i32×2) — 最初に完了した値を取得 ───────────
fn test_c() {
    let t1 = ret_i32(1);
    let t2 = ret_i32(2);
    let first: i32 = await Task::when_any([t1, t2]);
    // スケジューラは FIFO なので t1 が先に完了する
    println("C1: {}", first);           // 1
}

// ── D: when_any (要素数 1) ───────────────────────────────────
fn test_d() {
    let t1 = ret_i32(42);
    let v: i32 = await Task::when_any([t1]);
    println("D1: {}", v);               // 42
}

// ── E: when_all (f64×2) ─────────────────────────────────────
fn test_e() {
    let t1 = ret_f64(1.5);
    let t2 = ret_f64(2.5);
    let results: f64[] = await Task::when_all([t1, t2]);
    println("E1: {}", results.len());   // 2
}

fn main() {
    test_a();
    test_b();
    test_c();
    test_d();
    test_e();
    println("=== OK ===");
}
