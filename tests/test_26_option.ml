// ============================================================
// Test 26: Option<T> / Some / None / match
//   A. Some(v) の生成match (Some アーム実行)
//   B. None の生成match (None アーム実行)
//   C. 関数戻り値 Option - Some パス
//   D. 関数戻り値 Option - None パス
//   E. ゼロ除算を Option で安全に捌く (MC/DC)
//   F. Option<StructType>: struct型を内部型に持つ Option (#76 関連)
//
// カバレッジ観点:
//   C0  : Some/None 式生成関数戻値match 全アームを少なくとも1回実行
//   C1  :
//     A/B: match の Some アーム / None アーム 両方を実行
//     E  : safe_divide() の if(b==0) true(None)/false(Some) 両ブランチを実行
//     F  : Option<Point> の Some/None 両アームを実行
//   MC/DC:
//     safe_divide() 内 (b == 0):
//       {b==0=F}  Some  (単一条件なので C1 = MC/DC)
//       {b==0=T}  None
// ============================================================

// ----------------------------------------------------------
// F. Option<StructType>
// ----------------------------------------------------------
struct Point {
    x: i32;
    y: i32;
}

fn find_point(flag: bool) -> Option<Point> {
    if (flag) {
        return Some(Point { x: 3, y: 4 });
    }
    return None;
}

// ----------------------------------------------------------
// C/D. Option を返す場合分け関数
// ----------------------------------------------------------
fn maybe_value(flag: bool) -> Option<i32> {
    if (flag) {
        return Some(42);
    }
    return None;
}

// ----------------------------------------------------------
// E. MC/DC: b == 0 のみで分岐
// ----------------------------------------------------------
fn safe_divide(a: i32, b: i32) -> Option<i32> {
    if (b == 0) {
        return None;
    }
    return Some(a / b);
}

// ----------------------------------------------------------
// main
// ----------------------------------------------------------
fn main() -> i32 {
    println("=== 26: Option<T> ===");

    // ----------------------------------------------------------
    // A. Some 生成match -- Some アーム実行
    // ----------------------------------------------------------
    println("--- A: Some path ---");
    let a: Option<i32> = Some(10);
    let r1: i32 = match a {
        Some(v) => v,
        None    => -1,
    };
    println("some(10)={}", r1);

    // ----------------------------------------------------------
    // B. None 生成match -- None アーム実行
    // ----------------------------------------------------------
    println("--- B: None path ---");
    let b: Option<i32> = None;
    let r2: i32 = match b {
        Some(v) => v,
        None    => 0,
    };
    println("none={}", r2);

    // ----------------------------------------------------------
    // C. 関数戻り値 -- Some パス
    // ----------------------------------------------------------
    println("--- C: fn returns Some ---");
    let c = maybe_value(true);
    let r3: i32 = match c {
        Some(v) => v,
        None    => -1,
    };
    println("maybe(T)={}", r3);

    // ----------------------------------------------------------
    // D. 関数戻り値 -- None パス
    // ----------------------------------------------------------
    println("--- D: fn returns None ---");
    let d = maybe_value(false);
    let r4: i32 = match d {
        Some(v) => v,
        None    => 99,
    };
    println("maybe(F)={}", r4);

    // ----------------------------------------------------------
    // E. MC/DC: safe_divide
    //   T26-01: b=2   b==0=F  Some(5)
    //   T26-02: b=0   b==0=T  None
    // ----------------------------------------------------------
    println("--- E: safe_divide MC/DC ---");
    let e1 = safe_divide(10, 2);
    let r5: i32 = match e1 {
        Some(v) => v,
        None    => -1,
    };
    println("10/2={}", r5);

    let e2 = safe_divide(10, 0);
    let r6: i32 = match e2 {
        Some(v) => v,
        None    => -2,
    };
    println("10/0={}", r6);

    // ----------------------------------------------------------
    // F. Option<StructType> [C1]
    //   T26-F1: Some(Point) → x/y を取り出す
    //   T26-F2: None → デフォルト値
    // ----------------------------------------------------------
    println("--- F: Option<StructType> ---");
    let f1 = find_point(true);
    let fx: i32 = match f1 {
        Some(p) => p.x,
        None    => -1,
    };
    let fy: i32 = match find_point(true) {
        Some(p) => p.y,
        None    => -1,
    };
    println("point.x={}", fx);     // 3
    println("point.y={}", fy);     // 4

    let f2 = find_point(false);
    let fn_val: i32 = match f2 {
        Some(p) => p.x,
        None    => 0,
    };
    println("none.x={}", fn_val);  // 0

    println("=== OK ===");
    return 0;
}
