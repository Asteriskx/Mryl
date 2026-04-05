// ============================================================
// Test 45: Observable<T> / Subject<T> リアクティブストリーム (fix #45)
//   Subject の emit / subscribe / オペレータの基本動作を確認。
//
//   A. emit → subscribe の基本動作
//   B. filter でスキップ確認
//   C. map で値変換
//   D. take で件数制限（C1: n=0 / n>0）
//   E. skip で先頭スキップ
//   F. complete / error ハンドラ
//   G. unsubscribe 後は on_next が来ない
//   H. filter + map チェーン
//   I. merge（2 ソース合流）
//   J. 複数 subscribe
//
// カバレッジ観点:
//   C0: 全メソッドを 1 回以上実行
//   C1: take(n=0) / take(n>0) の両ケース
// ============================================================

// ── A: emit → subscribe の基本動作 ──────────────────────────
fn test_a() {
    let s: Subject<i32> = Subject<i32>::new();
    let sub: Subscription = s.subscribe((x: i32) => {
        println("A: {}", x);
    });
    s.emit(1);   // A: 1
    s.emit(2);   // A: 2
    s.emit(3);   // A: 3
    sub.unsubscribe();
}

// ── B: filter でスキップ確認 ─────────────────────────────────
fn test_b() {
    let s: Subject<i32> = Subject<i32>::new();
    let obs: Observable<i32> = s.filter((x: i32) => { return x > 0; });
    let sub: Subscription = obs.subscribe((x: i32) => {
        println("B: {}", x);
    });
    s.emit(-1);  // スキップ
    s.emit(5);   // B: 5
    s.emit(-3);  // スキップ
    s.emit(10);  // B: 10
    sub.unsubscribe();
}

// ── C: map で値変換 ──────────────────────────────────────────
fn test_c() {
    let s: Subject<i32> = Subject<i32>::new();
    let obs: Observable<i32> = s.map((x: i32) => { return x * 2; });
    let sub: Subscription = obs.subscribe((x: i32) => {
        println("C: {}", x);
    });
    s.emit(3);   // C: 6
    s.emit(7);   // C: 14
    sub.unsubscribe();
}

// ── D: take で件数制限 ───────────────────────────────────────
fn test_d() {
    // D1: take(2) — 先頭 2 件のみ
    let s1: Subject<i32> = Subject<i32>::new();
    let obs1: Observable<i32> = s1.take(2);
    let sub1: Subscription = obs1.subscribe((x: i32) => {
        println("D1: {}", x);
    });
    s1.emit(10);   // D1: 10
    s1.emit(20);   // D1: 20
    s1.emit(30);   // スキップ（take 済み）
    sub1.unsubscribe();

    // D2: take(0) — 何も受け取らない
    let s2: Subject<i32> = Subject<i32>::new();
    let obs2: Observable<i32> = s2.take(0);
    let sub2: Subscription = obs2.subscribe((x: i32) => {
        println("D2: FAIL");  // 来ないはず
    });
    s2.emit(99);
    sub2.unsubscribe();
    println("D2: ok");
}

// ── E: skip で先頭スキップ ───────────────────────────────────
fn test_e() {
    let s: Subject<i32> = Subject<i32>::new();
    let obs: Observable<i32> = s.skip(2);
    let sub: Subscription = obs.subscribe((x: i32) => {
        println("E: {}", x);
    });
    s.emit(1);  // スキップ
    s.emit(2);  // スキップ
    s.emit(3);  // E: 3
    s.emit(4);  // E: 4
    sub.unsubscribe();
}

// ── F: complete / error ハンドラ ─────────────────────────────
fn test_f() {
    let s1: Subject<i32> = Subject<i32>::new();
    let sub1: Subscription = s1.subscribe(
        (x: i32) => { println("F1_next: {}", x); },
        (e: string) => { println("F1_err: {}", e); },
        () => { println("F1_complete"); }
    );
    s1.emit(1);       // F1_next: 1
    s1.complete();    // F1_complete
    s1.emit(2);       // スキップ（complete 済み）
    sub1.unsubscribe();

    let s2: Subject<i32> = Subject<i32>::new();
    let sub2: Subscription = s2.subscribe(
        (x: i32) => { println("F2_next: {}", x); },
        (e: string) => { println("F2_err: {}", e); },
        () => { println("F2_complete"); }
    );
    s2.emit(9);           // F2_next: 9
    s2.error("oops");     // F2_err: oops
    s2.emit(99);          // スキップ（error 済み）
    sub2.unsubscribe();
}

// ── G: unsubscribe 後は on_next が来ない ────────────────────
fn test_g() {
    let s: Subject<i32> = Subject<i32>::new();
    let sub: Subscription = s.subscribe((x: i32) => {
        println("G: {}", x);
    });
    s.emit(1);      // G: 1
    sub.unsubscribe();
    s.emit(2);      // スキップ（unsubscribe 済み）
    println("G: done");
}

// ── H: filter + map チェーン ─────────────────────────────────
fn test_h() {
    let s: Subject<i32> = Subject<i32>::new();
    let obs: Observable<i32> = s
        .filter((x: i32) => { return x > 0; })
        .map((x: i32) => { return x * 10; });
    let sub: Subscription = obs.subscribe((x: i32) => {
        println("H: {}", x);
    });
    s.emit(-1);  // スキップ
    s.emit(2);   // H: 20
    s.emit(-3);  // スキップ
    s.emit(4);   // H: 40
    sub.unsubscribe();
}

// ── I: merge（2 ソース合流）──────────────────────────────────
fn test_i() {
    let s1: Subject<i32> = Subject<i32>::new();
    let s2: Subject<i32> = Subject<i32>::new();
    let merged: Observable<i32> = s1.merge(s2);
    let sub: Subscription = merged.subscribe((x: i32) => {
        println("I: {}", x);
    });
    s1.emit(1);  // I: 1
    s2.emit(2);  // I: 2
    s1.emit(3);  // I: 3
    sub.unsubscribe();
}

// ── J: 複数 subscribe ────────────────────────────────────────
fn test_j() {
    let s: Subject<i32> = Subject<i32>::new();
    let sub1: Subscription = s.subscribe((x: i32) => {
        println("J1: {}", x);
    });
    let sub2: Subscription = s.subscribe((x: i32) => {
        println("J2: {}", x);
    });
    s.emit(42);  // J1: 42 / J2: 42
    sub1.unsubscribe();
    sub2.unsubscribe();
}

// ── K: Subject<string> — string 型の Subject 動作確認 ─────────
fn test_k() {
    let s: Subject<string> = Subject<string>::new();

    // K1: emit → subscribe
    let sub1: Subscription = s.subscribe((x: string) => {
        println("K1: {}", x);
    });
    s.emit("hello");   // K1: hello
    s.emit("world");   // K1: world
    sub1.unsubscribe();

    // K2: filter で長さチェック
    let obs: Observable<string> = s.filter((x: string) => { return x.len() > 3; });
    let sub2: Subscription = obs.subscribe((x: string) => {
        println("K2: {}", x);
    });
    s.emit("hi");     // スキップ（len=2）
    s.emit("mryl");   // K2: mryl（len=4）
    s.emit("ok");     // スキップ（len=2）
    s.emit("hello");  // K2: hello（len=5）
    sub2.unsubscribe();
    println("K: done");
}

// ── L: Subject<Point> — struct 型の Subject 動作確認 ────────────
struct Point {
    x: i32;
    y: i32;
}

fn test_l() {
    let s: Subject<Point> = Subject<Point>::new();

    // L1: emit → subscribe（struct 値を受け取る）
    let sub1: Subscription = s.subscribe((p: Point) => {
        println("L1: {},{}", p.x, p.y);
    });
    let p1: Point = Point { x: 1, y: 2 };
    let p2: Point = Point { x: 3, y: 4 };
    s.emit(p1);   // L1: 1,2
    s.emit(p2);   // L1: 3,4
    sub1.unsubscribe();

    // L2: filter で x > 0 のみ通過
    let obs: Observable<Point> = s.filter((p: Point) => { return p.x > 0; });
    let sub2: Subscription = obs.subscribe((p: Point) => {
        println("L2: {},{}", p.x, p.y);
    });
    let p3: Point = Point { x: -1, y: 5 };
    let p4: Point = Point { x: 2, y: 7 };
    s.emit(p3);   // スキップ（x=-1）
    s.emit(p4);   // L2: 2,7
    sub2.unsubscribe();
    println("L: done");
}

fn main() {
    test_a();
    test_b();
    test_c();
    test_d();
    test_e();
    test_f();
    test_g();
    test_h();
    test_i();
    test_j();
    test_k();
    test_l();
    println("=== OK ===");
}
