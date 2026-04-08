// ============================================================
// Test 52: string[] 要素 (char*) の解放確認 (fix #97)
//   A. ArrayLiteral string[] → mryl_vec_string_free で要素解放
//   B. filter().to_array() → 各 MrylString.data も解放
//   C. skip().to_array()   → 各 MrylString.data も解放
//   D. split()             → 各 MrylString.data も解放
//   E. ループ内 string[]   → イテレーション毎に要素解放
//   F. bool[] / f64[]      → 数値型は要素解放不要、回帰確認
//
// カバレッジ観点:
//   C0: 各初期化パターンを少なくとも 1 回実行
//   C1: 空 filter 結果 (len=0) と非空の両ケース
// ============================================================

fn main() -> i32 {
    println("=== 52: string[] vec free ===");

    // ----------------------------------------------------------
    // A. ArrayLiteral string[]
    // ----------------------------------------------------------
    println("--- A: ArrayLiteral ---");
    let words: string[] = ["hello", "world", "foo"];
    println("A1: {}", words.len());    // A1: 3
    println("A2: {}", words[0]);       // A2: hello

    // ----------------------------------------------------------
    // B. filter().to_array() — 結果の各要素の char* も解放対象
    // ----------------------------------------------------------
    println("--- B: filter.to_array ---");
    let long_words: string[] = words.filter((w: string) => w.len() > 3).to_array();
    println("B1: {}", long_words.len());   // B1: 2
    println("B2: {}", long_words[0]);      // B2: hello

    // C1: 全要素除外 (len=0)
    let none_words: string[] = words.filter((w: string) => w.len() > 10).to_array();
    println("B3: {}", none_words.len());   // B3: 0

    // ----------------------------------------------------------
    // C. skip().to_array() — 新規確保 Vec の各要素も解放対象
    // ----------------------------------------------------------
    println("--- C: skip.to_array ---");
    let skipped: string[] = words.skip(1).to_array();
    println("C1: {}", skipped.len());   // C1: 2
    println("C2: {}", skipped[0]);      // C2: world

    // ----------------------------------------------------------
    // D. split() — 各要素の char* も解放対象
    // ----------------------------------------------------------
    println("--- D: split ---");
    let csv: string = "alpha,beta,gamma";
    let parts: string[] = csv.split(",");
    println("D1: {}", parts.len());    // D1: 3
    println("D2: {}", parts[1]);       // D2: beta

    // ----------------------------------------------------------
    // E. ループ内 string[] — イテレーション毎に要素解放
    // ----------------------------------------------------------
    println("--- E: loop string[] ---");
    let i: i32 = 0;
    while (i < 3) {
        let tmp: string[] = ["a", "b", "c"];
        println("E: {}", tmp.len());   // E: 3 (3回)
        i = i + 1;
    }

    // ----------------------------------------------------------
    // F. bool[] / f64[] — 回帰確認（数値型は要素解放不要）
    // ----------------------------------------------------------
    println("--- F: numeric types ---");
    let flags: bool[] = [true, false, true];
    let f1: bool[] = flags.filter((x: bool) => x).to_array();
    println("F1: {}", f1.len());   // F1: 2

    let vals: f64[] = [1.1, 2.2, 3.3, 4.4];
    let f2: f64[] = vals.skip(2).to_array();
    println("F2: {}", f2.len());   // F2: 2

    println("=== OK ===");
    return 0;
}
