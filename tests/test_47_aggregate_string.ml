// ============================================================
// Test 47: aggregate() での string 型要素の deep copy 対応（#81）
//   A. string[] の aggregate() 初期値なし（結合）→ Ok           [C0 / Ok パス]
//   B. 空 string[] の aggregate() → Err("empty sequence")      [C0 / Err パス]
//   C. filter().aggregate() チェーン → 中間 vec 解放後も有効   [C1]
//   D. aggregate() 初期値あり（string アキュムレータ）          [C0]
//   E. 単一要素 string[] の aggregate() → ラムダ未呼び出しでも成功 [C0]
//
// カバレッジ観点:
//   C0: 各パターンを少なくとも 1 回実行
//   C1: C でチェーン chain が通ることを確認（filter + aggregate の多段）
// ============================================================

fn main() -> i32 {
    println("=== 47: aggregate string ===");

    // ----------------------------------------------------------
    // A. string[] の aggregate() 初期値なし（文字列結合）
    // ----------------------------------------------------------
    println("--- A: aggregate concat ---");
    let words: string[] = ["hello", "world", "foo"];
    let ra = words.aggregate((a: string, b: string) => a + b);
    match ra {
        Ok(v) => println("A1: {}", v),   // A1: helloworldfoo
        Err(e) => println("A1: err"),
    };

    // ----------------------------------------------------------
    // B. 空配列 → Err("empty sequence")
    // ----------------------------------------------------------
    println("--- B: empty aggregate ---");
    let empty: string[] = [];
    let rb = empty.aggregate((a: string, b: string) => a + b);
    match rb {
        Ok(v) => println("B1: {}", v),
        Err(e) => println("B1: {}", e),   // B1: empty sequence
    };

    // ----------------------------------------------------------
    // C. filter().aggregate() チェーン [C1]
    //    中間 Vec が解放された後もアキュムレータが有効であること
    // ----------------------------------------------------------
    println("--- C: filter+aggregate ---");
    let tags: string[] = ["rust", "go", "mryl", "c"];
    let rc = tags.filter((w: string) => w.len() > 2).aggregate((a: string, b: string) => a + "+" + b);
    match rc {
        Ok(v) => println("C1: {}", v),   // C1: rust+mryl
        Err(e) => println("C1: err"),
    };

    // ----------------------------------------------------------
    // D. 初期値あり aggregate（string アキュムレータ）
    // ----------------------------------------------------------
    println("--- D: aggregate with init ---");
    let ds: string[] = ["a", "b", "c"];
    let rd = ds.aggregate("[", (acc: string, x: string) => acc + x);
    println("D1: {}", rd);   // D1: [abc

    // ----------------------------------------------------------
    // E. 単一要素（ループ 0 回）aggregate() → ラムダ未実行でも Ok
    // ----------------------------------------------------------
    println("--- E: single element ---");
    let single: string[] = ["only"];
    let re = single.aggregate((a: string, b: string) => a + b);
    match re {
        Ok(v) => println("E1: {}", v),   // E1: only
        Err(e) => println("E1: err"),
    };

    println("=== OK ===");
    return 0;
}
