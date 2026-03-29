// ============================================================
// Test 42: Iter<T> ラムダ引数数チェック (fix #69)
//   TypeChecker が各 iter メソッドの期待引数数を検査することを確認。
//
//   A. filter: 1引数ラムダ → PASS
//   B. select: 1引数ラムダ → PASS
//   C. for_each: 1引数ラムダ → PASS
//   D. any: 1引数ラムダ → PASS
//   E. all: 1引数ラムダ → PASS
//   F. aggregate 初期値なし: 2引数ラムダ → PASS
//   G. aggregate 初期値あり: 2引数ラムダ → PASS
//   H. select_many: 1引数ラムダ → PASS
//
// ※ 不正引数数（0引数・多引数）は TypeChecker が検出し
//    コンパイルエラーとなるため、本ファイルには含めない。
//
// カバレッジ観点:
//   C0: 各 iter メソッドを 1 回以上実行
// ============================================================

fn main() -> i32 {

    // ----------------------------------------------------------
    // A. filter: 1引数ラムダ
    // ----------------------------------------------------------
    let nums: i32[] = [1, 2, 3, 4, 5];
    let evens: i32[] = nums.filter((x: i32) => x % 2 == 0).to_array();
    if (evens.len() != 2) { return 1; }
    println("A: {}", evens.len());

    // ----------------------------------------------------------
    // B. select: 1引数ラムダ
    // ----------------------------------------------------------
    let doubled: i32[] = nums.select((x: i32) => x * 2).to_array();
    if (doubled.len() != 5) { return 1; }
    if (doubled[0] != 2) { return 1; }
    println("B: {}", doubled[0]);

    // ----------------------------------------------------------
    // C. for_each: 1引数ラムダ（副作用として println）
    // ----------------------------------------------------------
    let c_count: i32 = nums.count();
    nums.for_each((x: i32) => println("C: {}", x));
    if (c_count != 5) { return 1; }

    // ----------------------------------------------------------
    // D. any: 1引数ラムダ
    // ----------------------------------------------------------
    let has_even: bool = nums.any((x: i32) => x % 2 == 0);
    if (has_even != true) { return 1; }
    println("D: {}", has_even);

    // ----------------------------------------------------------
    // E. all: 1引数ラムダ
    // ----------------------------------------------------------
    let all_positive: bool = nums.all((x: i32) => x > 0);
    if (all_positive != true) { return 1; }
    println("E: {}", all_positive);

    // ----------------------------------------------------------
    // F. aggregate 初期値なし: 2引数ラムダ (T,T)->T
    // ----------------------------------------------------------
    let agg_result = nums.aggregate((acc: i32, x: i32) => acc + x);
    match agg_result {
        Ok(v) => {
            if (v != 15) { return 1; }
            println("F: {}", v);
        }
        Err(_) => { return 1; }
    };

    // ----------------------------------------------------------
    // G. aggregate 初期値あり: 2引数ラムダ (U,T)->U
    // ----------------------------------------------------------
    let product: i32 = nums.aggregate(1, (acc: i32, x: i32) => acc * x);
    if (product != 120) { return 1; }
    println("G: {}", product);

    // ----------------------------------------------------------
    // H. select_many: 1引数ラムダ（各要素を [x, x*10] に展開）
    // ----------------------------------------------------------
    let seeds: i32[] = [1, 2];
    let flat: i32[] = seeds.select_many((x: i32) => [x, x * 10]).to_array();
    if (flat.len() != 4) { return 1; }
    if (flat[0] != 1) { return 1; }
    if (flat[1] != 10) { return 1; }
    println("H: {}", flat.len());

    println("test_42 passed");
    return 0;
}
