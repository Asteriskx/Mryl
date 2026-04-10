// ============================================================
// Test 53: Task::when_all / when_any で Result<T,E> タスクを使う (#84)
//   A. when_any — Ok タスクの result を受け取る
//   B. when_any — Err タスク（FAULTED）の result を受け取る
//   C. when_all — 全タスク Ok のケース
//   D. when_all — Ok/Err 混在のケース（全結果を収集できることを確認）
//
// カバレッジ観点:
//   C0: when_all / when_any の各経路を実行
//   C1: Ok/Err の両ケースを含む組み合わせ
// ============================================================

async fn fetch_ok(v: i32) -> Result<i32, string> {
    return Ok(v * 2);
}

async fn fetch_err(msg: string) -> Result<i32, string> {
    return Err(msg);
}

// A. when_any — Ok タスク
fn test_a() {
    let t1 = fetch_ok(7);
    let r: Result<i32, string> = await Task::when_any([t1]);
    match r {
        Ok(v)  => println("A1: Ok {}", v),    // A1: Ok 14
        Err(e) => println("A1: Err {}", e),
    };
}

// B. when_any — Err タスク（FAULTED 状態の result を読む）
fn test_b() {
    let t1 = fetch_err("fail");
    let r: Result<i32, string> = await Task::when_any([t1]);
    match r {
        Ok(v)  => println("B1: Ok {}", v),
        Err(e) => println("B1: Err {}", e),   // B1: Err fail
    };
}

// C. when_all — 全タスク Ok
fn test_c() {
    let t1 = fetch_ok(1);
    let t2 = fetch_ok(2);
    let t3 = fetch_ok(3);
    let results: Result<i32, string>[] = await Task::when_all([t1, t2, t3]);
    println("C1: {}", results.len());          // C1: 3
    let r0: Result<i32, string> = results[0];
    let r1: Result<i32, string> = results[1];
    match r0 {
        Ok(v)  => println("C2: Ok {}", v),    // C2: Ok 2
        Err(e) => println("C2: Err {}", e),
    };
    match r1 {
        Ok(v)  => println("C3: Ok {}", v),    // C3: Ok 4
        Err(e) => println("C3: Err {}", e),
    };
}

// D. when_all — Ok/Err 混在（両結果が収集される）
fn test_d() {
    let t1 = fetch_ok(5);
    let t2 = fetch_err("oops");
    let results: Result<i32, string>[] = await Task::when_all([t1, t2]);
    println("D1: {}", results.len());          // D1: 2
    let r0: Result<i32, string> = results[0];
    let r1: Result<i32, string> = results[1];
    match r0 {
        Ok(v)  => println("D2: Ok {}", v),    // D2: Ok 10
        Err(e) => println("D2: Err {}", e),
    };
    match r1 {
        Ok(v)  => println("D3: Ok {}", v),
        Err(e) => println("D3: Err {}", e),   // D3: Err oops
    };
}

fn main() {
    println("=== 53: Task Result combinator ===");
    println("--- A: when_any Ok ---");
    test_a();
    println("--- B: when_any Err ---");
    test_b();
    println("--- C: when_all Ok ---");
    test_c();
    println("--- D: when_all mixed ---");
    test_d();
    println("=== OK ===");
}
