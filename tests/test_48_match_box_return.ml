// ============================================================
// Test 48: match Some(b) での Option<Box<T>> 二重 free 防止（#79）
//   A. Some(b) アームで *b を読む（値コピー後、ob のスコープ終了で free） [C0]
//   B. None アーム（ob は has_value=false なので free 安全）              [C0]
//   C. Some(b) で *b を使った計算                                        [C0]
//   D. 連続して Some/None を match する [C1]
//
// カバレッジ観点:
//   C0: 各パターンを少なくとも 1 回実行
//   C1: D で Some/None 両パスを連続確認
//
// ※ 二重 free の検出は Valgrind 等が必要。
//    ここでは C コンパイル・実行が正常終了することで回帰確認とする。
// ============================================================

fn main() -> i32 {
    println("=== 48: match box return ===");

    // ----------------------------------------------------------
    // A. Some(b) で *b の値を読む
    // ----------------------------------------------------------
    println("--- A: Some path ---");
    let ob1: Option<Box<i32>> = Some(Box::new(42));
    let r1: i32 = match ob1 {
        Some(b) => *b,
        None    => -1,
    };
    println("A1: {}", r1);   // A1: 42

    // ----------------------------------------------------------
    // B. None パス
    // ----------------------------------------------------------
    println("--- B: None path ---");
    let ob2: Option<Box<i32>> = None;
    let r2: i32 = match ob2 {
        Some(b) => *b,
        None    => -1,
    };
    println("B1: {}", r2);   // B1: -1

    // ----------------------------------------------------------
    // C. Some(b) で計算して使う
    // ----------------------------------------------------------
    println("--- C: use computed ---");
    let ob3: Option<Box<i32>> = Some(Box::new(10));
    let r3: i32 = match ob3 {
        Some(b) => *b * 2,
        None    => 0,
    };
    println("C1: {}", r3);   // C1: 20

    // ----------------------------------------------------------
    // D. Some/None を連続 match [C1]
    // ----------------------------------------------------------
    println("--- D: sequential match ---");
    let od1: Option<Box<i32>> = Some(Box::new(100));
    let rd1: i32 = match od1 {
        Some(b) => *b,
        None    => -1,
    };
    println("D1: {}", rd1);   // D1: 100

    let od2: Option<Box<i32>> = None;
    let rd2: i32 = match od2 {
        Some(b) => *b,
        None    => -1,
    };
    println("D2: {}", rd2);   // D2: -1

    let od3: Option<Box<i32>> = Some(Box::new(200));
    let rd3: i32 = match od3 {
        Some(b) => *b + 1,
        None    => 0,
    };
    println("D3: {}", rd3);   // D3: 201

    println("=== OK ===");
    return 0;
}
