// ============================================================
// Test 46: 配列リテラル / split() の MrylVec.data free（#78）
//   A. ArrayLiteral で初期化した動的配列がスコープ終了時に free される     [C0]
//   B. 同一スコープに複数の ArrayLiteral 動的配列                         [C0]
//   C. ループ内で ArrayLiteral 動的配列を繰り返し宣言                     [C1]
//   D. split() 結果 Vec がスコープ終了時に free される                    [C0]
//   E. 関数内で ArrayLiteral Vec を宣言して返す（返値は free しない）      [C0]
//
// カバレッジ観点:
//   C0: 各ケースを少なくとも 1 回実行
//   C1: C でループが複数回回ることで繰り返し free を確認
//
// ※ メモリリーク（free 漏れ）の確認は valgrind 等の外部ツールを要するが、
//    ここでは C コンパイル・実行が正常完了することで回帰確認とする。
// ============================================================

fn make_vec() -> i32[] {
    // E. 関数内で ArrayLiteral Vec を宣言して返す
    //    返値となる変数は free されず、呼び出し元へ所有権が移る
    let v: i32[] = [10, 20, 30];
    return v;
}

fn main() -> i32 {
    println("=== 46: array literal free ===");

    // ----------------------------------------------------------
    // A. ArrayLiteral 動的配列 / C0
    // ----------------------------------------------------------
    println("--- A: ArrayLiteral free ---");
    let nums: i32[] = [1, 2, 3, 4, 5];
    println("len={}", nums.len());   // 5
    println("v[0]={}", nums[0]);     // 1
    println("v[4]={}", nums[4]);     // 5
    // スコープ内で変更しても正常動作するか確認
    nums.push(6);
    println("after push len={}", nums.len());  // 6

    // ----------------------------------------------------------
    // B. 同一スコープに複数の ArrayLiteral Vec / C0
    // ----------------------------------------------------------
    println("--- B: multiple ArrayLiteral ---");
    let a: i32[] = [10, 20];
    let b: i32[] = [30, 40, 50];
    println("a.len={}", a.len());   // 2
    println("b.len={}", b.len());   // 3
    println("a[0]={}", a[0]);       // 10
    println("b[2]={}", b[2]);       // 50

    // ----------------------------------------------------------
    // C. ループ内で ArrayLiteral Vec を繰り返し宣言 [C1]
    // ----------------------------------------------------------
    println("--- C: loop ArrayLiteral ---");
    let i: i32 = 0;
    while (i < 3) {
        let tmp: i32[] = [100, 200, 300];
        println("i={} tmp.len={}", i, tmp.len());  // 3 (各イテレーション)
        // tmp.data はイテレーション末に free される
        i = i + 1;
    }

    // ----------------------------------------------------------
    // D. split() 結果 Vec / C0
    // ----------------------------------------------------------
    println("--- D: split free ---");
    let csv: string = "alpha,beta,gamma";
    let parts: string[] = csv.split(",");
    println("parts.len={}", parts.len());  // 3
    println("parts[0]={}", parts[0]);      // alpha
    println("parts[2]={}", parts[2]);      // gamma
    // parts.data はスコープ終了時に free される

    // ----------------------------------------------------------
    // E. 関数から返す ArrayLiteral Vec（返値は free されない）
    // ----------------------------------------------------------
    println("--- E: return ArrayLiteral ---");
    let ret: i32[] = make_vec();
    println("ret.len={}", ret.len());   // 3
    println("ret[1]={}", ret[1]);       // 20

    println("=== OK ===");
    return 0;
}
