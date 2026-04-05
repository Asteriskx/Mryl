// ============================================================
// Test 39: to_array() 結果 MrylVec の .data free（#71）
//   A. filter().to_array() の結果を変数に代入 → スコープ終了時に free  [C0]
//   B. 複数の to_array() 変数が同スコープに存在する                      [C0]
//   C. ループ内で to_array() を繰り返す → 各イテレーション末に free      [C1]
//
// カバレッジ観点:
//   C0: 各ケースを少なくとも1回実行
//   C1: C ループが複数回回ることで繰り返し free を確認
// ============================================================

fn main() -> i32 {
    println("=== 39: to_array free ===");

    let src: i32[] = [1, 2, 3, 4, 5];

    // ----------------------------------------------------------
    // A. filter().to_array() → スコープ終了時に .data が free される
    // ----------------------------------------------------------
    println("--- A: filter.to_array ---");
    let filtered: i32[] = src.filter((x: i32) => x > 2).to_array();
    println("len={}", filtered.len());  // 3

    // ----------------------------------------------------------
    // B. 複数 to_array() 変数が同スコープに存在
    // ----------------------------------------------------------
    println("--- B: multiple to_array ---");
    let a: i32[] = src.filter((x: i32) => x % 2 == 0).to_array();
    let b: i32[] = src.filter((x: i32) => x % 2 != 0).to_array();
    println("even.len={}", a.len());    // 2
    println("odd.len={}", b.len());     // 3

    // ----------------------------------------------------------
    // C. ループ内で to_array() を繰り返す [C1]
    // ----------------------------------------------------------
    println("--- C: loop to_array ---");
    let i: i32 = 0;
    while (i < 3) {
        let tmp: i32[] = src.filter((x: i32) => x > i).to_array();
        println("i={} len={}", i, tmp.len());
        // tmp.data はイテレーション末に free される
        i = i + 1;
    }

    println("=== OK ===");
    return 0;
}
