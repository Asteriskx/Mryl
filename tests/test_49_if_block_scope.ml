// ============================================================
// Test 49: if/else ブロック内で宣言されたリソースのスコープ管理（#94）
//   A. if ブロック内で Box<i32> を宣言 → ブランチ終端で free             [C0]
//   B. else ブロック内で Box<i32> を宣言 → else 終端で free             [C0]
//   C. while + if/else で Box を繰り返し宣言 → 各ブランチ末に free      [C1]
//   D. if ブロック内で Option<Box<i32>> を宣言 → ブランチ終端で free     [C0]
//   E. if ブロック内で string[] (split結果) を宣言 → ブランチ終端で free [C0]
//
// カバレッジ観点:
//   C0: 各パターンを少なくとも 1 回実行
//   C1: C でループが複数回回り if/else 両パスを通ること
// ============================================================

fn main() -> i32 {
    println("=== 49: if block scope ===");

    // ----------------------------------------------------------
    // A. if ブロック内 Box
    // ----------------------------------------------------------
    println("--- A: if Box ---");
    let x: i32 = 5;
    if (x > 3) {
        let b: Box<i32> = Box::new(100);
        println("A1: {}", *b);   // A1: 100
    }
    println("A2: ok");   // A2: ok  (b はブランチ終端で free 済み)

    // ----------------------------------------------------------
    // B. else ブロック内 Box
    // ----------------------------------------------------------
    println("--- B: else Box ---");
    if (x < 3) {
        println("B: then");
    } else {
        let b2: Box<i32> = Box::new(200);
        println("B1: {}", *b2);   // B1: 200
    }
    println("B2: ok");

    // ----------------------------------------------------------
    // C. while + if/else 内 Box [C1]
    // ----------------------------------------------------------
    println("--- C: loop if/else Box ---");
    let i: i32 = 0;
    while (i < 4) {
        if (i % 2 == 0) {
            let bc: Box<i32> = Box::new(i * 10);
            println("C: even={}", *bc);
        } else {
            let bd: Box<i32> = Box::new(i * 100);
            println("C: odd={}", *bd);
        }
        i = i + 1;
    }
    // C: even=0, odd=100, even=20, odd=300

    // ----------------------------------------------------------
    // D. if ブロック内 Option<Box<i32>>
    // ----------------------------------------------------------
    println("--- D: if Option<Box> ---");
    if (x > 3) {
        let ob: Option<Box<i32>> = Some(Box::new(77));
        let rv: i32 = match ob {
            Some(b) => *b,
            None    => -1,
        };
        println("D1: {}", rv);   // D1: 77
    }
    println("D2: ok");

    // ----------------------------------------------------------
    // E. if ブロック内 string[] (split 結果)
    // ----------------------------------------------------------
    println("--- E: if split ---");
    if (x > 3) {
        let parts: string[] = "a,b,c".split(",");
        println("E1: {}", parts.len());   // E1: 3
        println("E2: {}", parts[0]);      // E2: a
    }
    println("E3: ok");

    println("=== OK ===");
    return 0;
}
