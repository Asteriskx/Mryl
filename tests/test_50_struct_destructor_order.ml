// ============================================================
// Test 50: 循環参照・相互参照 struct のデストラクタ前方宣言（#80）
//   A. Box フィールドを持つ struct 1つ（既存動作の回帰確認）              [C0]
//   B. 相互参照 struct: NodeB が NodeA を値フィールドで持つ               [C0]
//      → mryl_free_NodeB は mryl_free_NodeA を呼ぶため前方宣言が必要
//   C. 3段ネスト struct (NodeC → NodeB → NodeA の順で定義)             [C0]
//
// カバレッジ観点:
//   C0: 各 struct パターンのコンパイル・実行が正常終了すること
// ============================================================

struct NodeA {
    val: i32;
    data: Box<i32>;
}

// NodeB は NodeA を値フィールドで持つ
// → mryl_free_NodeB 内で mryl_free_NodeA を呼ぶ
// → NodeA より後に定義でも前方宣言があれば OK
struct NodeB {
    inner: NodeA;
    extra: i32;
}

struct NodeC {
    child: NodeB;
    name_val: i32;
}

fn main() -> i32 {
    println("=== 50: struct destructor order ===");

    // ----------------------------------------------------------
    // A. 単独 Box フィールド struct（回帰）
    // ----------------------------------------------------------
    println("--- A: single struct ---");
    let a: NodeA = NodeA { val: 10, data: Box::new(42) };
    println("A1: val={}", a.val);    // A1: val=10
    println("A2: data={}", *a.data); // A2: data=42

    // ----------------------------------------------------------
    // B. 相互参照 struct（NodeB は NodeA を含む）
    // ----------------------------------------------------------
    println("--- B: nested struct ---");
    let b: NodeB = NodeB {
        inner: NodeA { val: 20, data: Box::new(99) },
        extra: 7
    };
    println("B1: inner.val={}", b.inner.val);    // B1: inner.val=20
    println("B2: inner.data={}", *b.inner.data); // B2: inner.data=99
    println("B3: extra={}", b.extra);            // B3: extra=7

    // ----------------------------------------------------------
    // C. 3段ネスト struct
    // ----------------------------------------------------------
    println("--- C: deep nested ---");
    let c: NodeC = NodeC {
        child: NodeB {
            inner: NodeA { val: 30, data: Box::new(77) },
            extra: 5
        },
        name_val: 100
    };
    println("C1: child.inner.val={}", c.child.inner.val);    // C1: 30
    println("C2: child.inner.data={}", *c.child.inner.data); // C2: 77
    println("C3: name_val={}", c.name_val);                  // C3: 100

    println("=== OK ===");
    return 0;
}
