// ============================================================
// Test 54: 多次元配列 i32[][] / f64[][] / bool[][] / string[][] / *[][][] (#82)
//   A. i32[][] 宣言・インデックスアクセス・書き込み
//   B. i32[][] 関数引数渡し (matrix_sum)
//   C. i32[][] for ループ
//   D. f64[][] 宣言・インデックスアクセス・書き込み・for ループ（関数引数渡し）
//   E. bool[][] 宣言・インデックスアクセス・書き込み・関数引数渡し (bool_matrix_any)
//   F. string[][] 宣言・インデックスアクセス・書き込み・for ループ（関数引数渡し）
//   G. i32[][][] 3次元配列
//   H. f64[][][] 3次元配列
//   I. bool[][][] 3次元配列
//   J. string[][][] 3次元配列
//
// カバレッジ観点:
//   C0: 各型（i32/f64/bool/string）の 2D・3D 宣言と要素参照を各 1 パス
//   C1: 書き込み後参照・関数引数渡し・for ループによるネスト走査（全型、2D/3D）
// ============================================================

fn sum_row(row: i32[]) -> i32 {
    let s: i32 = 0;
    for v in row {
        s = s + v;
    }
    return s;
}

fn matrix_sum(mat: i32[][]) -> i32 {
    let total: i32 = 0;
    for row in mat {
        total = total + sum_row(row);
    }
    return total;
}

fn f64_matrix_get(mat: f64[][], r: i32, c: i32) -> f64 {
    return mat[r][c];
}

fn f64_matrix_sum(mat: f64[][]) -> f64 {
    let total: f64 = 0.0;
    for row in mat {
        for v in row {
            total = total + v;
        }
    }
    return total;
}

fn bool_matrix_any(mat: bool[][]) -> bool {
    for row in mat {
        for v in row {
            if (v) {
                return true;
            }
        }
    }
    return false;
}

fn string_matrix_concat(mat: string[][]) -> string {
    let result: string = "";
    for row in mat {
        for v in row {
            result = result + v;
        }
    }
    return result;
}

fn main() -> i32 {
    println("=== 54: Multi-dim array ===");

    // ----------------------------------------------------------
    println("--- A: i32[][] ---");
    // ----------------------------------------------------------

    let matrix: i32[][] = [[1, 2, 3], [4, 5, 6], [7, 8, 9]];
    println("A1: {}", matrix[0][0]);   // 1
    println("A2: {}", matrix[0][2]);   // 3
    println("A3: {}", matrix[1][1]);   // 5
    println("A4: {}", matrix[2][2]);   // 9

    // 書き込み後の参照
    matrix[1][0] = 40;
    println("A5: {}", matrix[1][0]);   // 40

    // ----------------------------------------------------------
    println("--- B: function arg ---");
    // ----------------------------------------------------------

    let total: i32 = matrix_sum(matrix);
    println("B1: {}", total);          // 1+2+3+40+5+6+7+8+9 = 81

    // ----------------------------------------------------------
    println("--- C: for loop ---");
    // ----------------------------------------------------------

    let rowsum: i32 = 0;
    for row in matrix {
        rowsum = rowsum + sum_row(row);
    }
    println("C1: {}", rowsum);         // 81

    // ----------------------------------------------------------
    println("--- D: f64[][] ---");
    // ----------------------------------------------------------

    let fmat: f64[][] = [[1.0, 2.5], [3.0, 4.5]];
    println("D1: {}", f64_matrix_get(fmat, 0, 1));   // 2.5
    println("D2: {}", f64_matrix_get(fmat, 1, 0));   // 3

    // 書き込み後の参照
    fmat[0][0] = 9.9;
    println("D3: {}", f64_matrix_get(fmat, 0, 0));   // 9.9

    // for ループ + 関数引数渡し（9.9+2.5+3.0+4.5 = 19.9）
    let fsum: f64 = f64_matrix_sum(fmat);
    println("D4: {}", fsum);           // 19.9

    // ----------------------------------------------------------
    println("--- E: bool[][] ---");
    // ----------------------------------------------------------

    let bmat_false: bool[][] = [[false, false], [false, false]];
    let bmat_true:  bool[][] = [[false, true],  [false, false]];
    println("E1: {}", bool_matrix_any(bmat_false));   // false
    println("E2: {}", bool_matrix_any(bmat_true));    // true

    // 書き込み後に bool_matrix_any で再検査
    bmat_false[1][1] = true;
    println("E3: {}", bool_matrix_any(bmat_false));   // true

    // ----------------------------------------------------------
    println("--- F: string[][] ---");
    // ----------------------------------------------------------

    let smat: string[][] = [["hello", "world"], ["foo", "bar"]];
    println("F1: {}", smat[0][0]);    // hello
    println("F2: {}", smat[1][1]);    // bar

    // 書き込み後の参照
    smat[0][1] = "WORLD";
    println("F3: {}", smat[0][1]);    // WORLD

    // for ループ + 関数引数渡し
    let cat: string = string_matrix_concat(smat);
    println("F4: {}", cat);           // helloWORLDfoobar

    // ----------------------------------------------------------
    println("--- G: i32[][][] ---");
    // ----------------------------------------------------------

    let cube: i32[][][] = [[[1, 2], [3, 4]], [[5, 6], [7, 8]]];
    println("G1: {}", cube[0][0][0]);   // 1
    println("G2: {}", cube[0][1][1]);   // 4
    println("G3: {}", cube[1][0][1]);   // 6
    println("G4: {}", cube[1][1][1]);   // 8

    // ----------------------------------------------------------
    println("--- H: f64[][][] ---");
    // ----------------------------------------------------------

    let fcube: f64[][][] = [[[1.0, 2.0], [3.0, 4.0]], [[5.0, 6.0], [7.0, 8.0]]];
    println("H1: {}", fcube[0][0][0]);   // 1
    println("H2: {}", fcube[0][1][1]);   // 4
    println("H3: {}", fcube[1][0][1]);   // 6
    println("H4: {}", fcube[1][1][1]);   // 8

    // ----------------------------------------------------------
    println("--- I: bool[][][] ---");
    // ----------------------------------------------------------

    let bcube: bool[][][] = [[[true, false], [false, true]], [[false, false], [true, true]]];
    println("I1: {}", bcube[0][0][0]);   // true
    println("I2: {}", bcube[0][1][0]);   // false
    println("I3: {}", bcube[1][1][0]);   // true

    // ----------------------------------------------------------
    println("--- J: string[][][] ---");
    // ----------------------------------------------------------

    let scube: string[][][] = [[["a", "b"], ["c", "d"]], [["e", "f"], ["g", "h"]]];
    println("J1: {}", scube[0][0][0]);   // a
    println("J2: {}", scube[0][1][1]);   // d
    println("J3: {}", scube[1][0][1]);   // f
    println("J4: {}", scube[1][1][1]);   // h

    println("=== OK ===");
    return 0;
}
