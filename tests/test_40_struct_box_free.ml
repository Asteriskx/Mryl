// ============================================================
// Test 40: #68 struct フィールド Box free
//          #67 Option<Box<T>> free
//
//   A. struct に Box<i32> フィールド → スコープ終了時 mryl_free_Wrapper 呼び出し
//   B. 複数 struct 変数が同スコープ → 逆順で free される
//   C. 関数から struct を返す → 呼び元で free（返値自身は free しない）
//   D. while ループ内 struct Box → イテレーション末に mryl_free
//   E. Option<Box<i32>> Some → スコープ終了時に内部 Box を free
//   F. Option<Box<i32>> None → free なし（has_value=false なので安全）
//   G. match Option<Box<i32>> Some(b) で参照後 → スコープ終了で ob を free
//
// ※ ネスト struct(OuterNode→InnerNode) の Box ポインタ共有問題は既知制約
//    (issue_struct_destructor_cyclic.md) として v0.7.0 以降で対応予定。
//
// カバレッジ観点:
//   C0  : 各パターンを少なくとも1回実行
//   C1  : Some/None 両パス (E/F)、ループ複数イテレーション (D)
//   MC/DC: struct_has_box_fields true/false（Box 持ち/持たない struct）
// ============================================================

struct Wrapper {
    value: i32;
    data: Box<i32>;
}

fn make_wrapper(v: i32) -> Wrapper {
    return Wrapper { value: v, data: Box::new(v * 10) };
}

fn main() -> i32 {
    // ----------------------------------------------------------
    // A. 基本 struct Box フィールド free
    //    w.data の malloc 領域がスコープ終了時に mryl_free_Wrapper で free される
    // ----------------------------------------------------------
    let w: Wrapper = Wrapper { value: 1, data: Box::new(42) };
    println("{}", *w.data);     // 42

    // ----------------------------------------------------------
    // B. 複数 struct 変数が同スコープ（宣言逆順: w3 → w2 の順で free）
    // ----------------------------------------------------------
    let w2: Wrapper = Wrapper { value: 2, data: Box::new(200) };
    let w3: Wrapper = Wrapper { value: 3, data: Box::new(300) };
    println("{}", *w2.data);    // 200
    println("{}", *w3.data);    // 300

    // ----------------------------------------------------------
    // C. 関数から返された struct → 呼び元でデストラクタ呼び出し
    //    make_wrapper 内の return 変数は free しない（所有権移動）
    // ----------------------------------------------------------
    let wret: Wrapper = make_wrapper(5);
    println("{}", *wret.data);  // 50

    // ----------------------------------------------------------
    // D. while ループ内 struct Box（各イテレーション末に mryl_free）
    //    ループ内で宣言した lw は各反復の末に mryl_free_Wrapper が呼ばれる
    // ----------------------------------------------------------
    let i: i32 = 0;
    while (i < 3) {
        let lw: Wrapper = Wrapper { value: i, data: Box::new(i + 100) };
        println("{}", *lw.data);    // 100, 101, 102
        i = i + 1;
    }

    // ----------------------------------------------------------
    // E. Option<Box<i32>> Some → スコープ終了時に内部 Box を free
    // ----------------------------------------------------------
    let ob: Option<Box<i32>> = Some(Box::new(77));
    let eval: i32 = match ob {
        Some(b) => *b,
        None    => -1,
    };
    println("{}", eval);    // 77

    // ----------------------------------------------------------
    // F. Option<Box<i32>> None → has_value=false なので free なし
    // ----------------------------------------------------------
    let on: Option<Box<i32>> = None;
    let fval: i32 = match on {
        Some(b) => *b,
        None    => 0,
    };
    println("{}", fval);    // 0

    // ----------------------------------------------------------
    // G. match で Some(b) をバインドして参照し、ob2 はスコープ終了時 free
    //    b = ob2.value（ポインタエイリアス）→ ob2 free で内部 Box が解放される
    // ----------------------------------------------------------
    let ob2: Option<Box<i32>> = Some(Box::new(55));
    match ob2 {
        Some(b) => println("{}", *b),   // 55
        None    => println("none"),
    };

    println("=== OK ===");
    return 0;
}
