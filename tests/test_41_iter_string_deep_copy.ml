// ============================================================
// Test 41: #70 Iter<string> first()/filter()/skip() deep copy
//
//   A. filter().first() → 中間 vec 解放後も ok_val が有効
//   B. filter() 結果を skip().first() にチェーン → 多段 deep copy
//   C. first() が空シーケンス → Err("empty sequence")
//   D. filter() で全要素除外 → first() が Err
//   E. skip(n) で先頭スキップ後 first() → 正しい要素を返す
//
// カバレッジ観点:
//   C0  : 各パターンを少なくとも1回実行
//   C1  : Ok / Err 両パス (A,B vs C,D)
// ============================================================

fn main() -> i32 {
    // A: filter().first() → 中間 vec が解放されても ok_val は deep copy 済みで有効
    let words: string[] = ["hello", "hi", "world", "foo"];
    let ra = words.filter((w: string) => w.len() > 3).first();
    match ra {
        Ok(v) => println("{}", v),
        Err(e) => println("err"),
    };

    // B: filter().skip(1).first() → 多段チェーン deep copy
    let rb = words.filter((w: string) => w.len() >= 3).skip(1).first();
    match rb {
        Ok(v) => println("{}", v),
        Err(e) => println("err"),
    };

    // C: 空シーケンスへの first() → Err
    let empty: string[] = [];
    let rc = empty.first();
    match rc {
        Ok(v) => println("{}", v),
        Err(e) => println("{}", e),
    };

    // D: filter で全除外 → first() が Err
    let rd = words.filter((w: string) => w.len() > 100).first();
    match rd {
        Ok(v) => println("{}", v),
        Err(e) => println("{}", e),
    };

    // E: skip(2).first() → 3番目の要素を返す
    let re = words.skip(2).first();
    match re {
        Ok(v) => println("{}", v),
        Err(e) => println("err"),
    };

    return 0;
}
