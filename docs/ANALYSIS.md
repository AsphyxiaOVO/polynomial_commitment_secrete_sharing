# 原始实现分析与重构说明

本文记录重构前对原始代码（现位于 `legacy/`）的分析、发现的问题、对应的修复，以及刻意保留或未解决的限制。
`legacy/` 中的文件保持原样，未做任何修改。

## 1. 原始数据流

```
main_withui_finally.py (Tkinter)
  └─ 输入: 多项式数量 m, 有限域 field, 点集 T, 每行 "S_i;系数(高→低, 不含常数)", 消息
  └─ Prover.initialize_parameters
       1. reduce_high_degree_polynomials   → FRI.reduce_power (次数 > 5 时折叠)
       2. message_coding: UTF-8 → 大整数 → 十进制字符串均分为 m 段 (末尾补 '0')
       3. 每段整数替换 f_i 的常数项
       4. r_i = rxi.fit_polynomial(f_i 在 S_i 上的取值)   (NumPy Vandermonde + SymPy inv_mod)
  └─ 添加验证者 (x, y)
       cm_i = f_i(x)                         ← 同时也是参与者 x 的份额
       W    = Σ y^i · ((f_i − r_i) / Z_{S_i})(x)
  └─ 验证: W·Z_T(x) == Σ (cm_i − r_i(x)) · y^i · Z_{T\S_i}(x)

secret_clipswithui.py (Tkinter)
  └─ 输入: 多项式数量, 有限域, 门限 k, 补零个数, k 个份额 (x, y_1..y_m)
  └─ 对每个多项式做拉格朗日插值求 f_i(0) → 合并十进制字符串 → 解码 UTF-8
```

**GUI 与算法的耦合**：`Prover` / `Verifier` 定义在 GUI 文件中；参数解析、线程、`print` 调试输出、算法调用交织在
`MainWindow` 的回调里；恢复界面的模数、补零个数、门限全部由用户手工输入，与生成时的参数没有任何绑定。

**多项式系数顺序**：三处约定不一致——

| 位置 | 顺序 |
| --- | --- |
| `main_withui_finally.py`、`polynomial_division.py`、`rxi.py` (np.vander) | 高 → 低 |
| `FRI.py` | 低 → 高（调用前后用 `[::-1]` 翻转） |
| `secret_clipswithui.evaluate_polynomial` | 低 → 高 |

重构后 `pcss` 内部统一为**低 → 高**（`coeffs[i]` 是 `X^i` 的系数），边界处用
`polynomial.from_high_to_low / to_high_to_low` 转换。

## 2. 发现的问题（均有回归测试 `tests/test_legacy_regressions.py` 复现）

| # | 问题 | 后果 | 修复 |
| --- | --- | --- | --- |
| 1 | `rxi.fit_polynomial` 最终 `astype(int)` 转成 int64 | p = 2^255−19 时 `OverflowError` | `polynomial.interpolate` 纯 Python 整数拉格朗日插值 |
| 2 | `mod_inverse(0)` 返回 0 | 份额 x 重复时静默给出错误秘密 | `field.inv` 抛 `NonInvertibleError`；插值前检测重复点 `DuplicatePointError` |
| 3 | 恢复时未使用门限 `k`，仅按输入份额个数插值 | 多项式次数 ≥ 份额数时恢复出错误值且无提示 | 生成时把 `threshold` 写入 `SharingMetadata`，恢复时份额数 < k 抛 `InsufficientSharesError` |
| 4 | 多项式次数由用户输入的系数个数决定，与 k 无关 | 门限语义不成立 | 系统固定 `d = k − 1`，首项系数非零 |
| 5 | 十进制字符串分片 | 前导 `\x00` 丢失；分片可能 ≥ 模数而被取模破坏 | 31 字节定长分片（2^248 < p），记录 `original_length` |
| 6 | `reduce_high_degree_polynomials` 对高→低列表从末尾找"前导零" | 实际扫描的是常数项（GUI 总是补 0），6 次多项式被误判为 5 次而不折叠 | `polynomial.degree` 基于规范化的低→高表示 |
| 7 | `FRI.py` 停止条件是 `len > 5`，而主程序触发条件是 `degree > 5` | 两处判定不一致 | `fri.reduce_degree(max_degree=…)` 统一用次数判定 |
| 8 | `T \ S_i` 为空（S_i = T）时 `polynomials[0]` → `IndexError` | 合法输入崩溃 | 空积定义为 1 |
| 9 | 验证点 x ∈ T 时 Z_T(x) = 0 且右侧每项为 0 | **任意 W 都能通过验证** | `validate_challenge` 拒绝 x ∈ T |
| 10 | 挑战 y = 0 | 除第一个多项式外权重全为 0，不参与验证 | 要求 1 ≤ y < p（p 为素数，故 y^i ≠ 0） |
| 11 | 未检查 S_i ⊆ T、空集、重复点 | 等式不成立或插值矩阵奇异 | `validate_point_sets` |
| 12 | 多项式除法余数被忽略；除数为零多项式时行为未定义 | 静默错误 | `divmod_poly` 校验；余数非零抛 `ProtocolError` |
| 13 | `evaluate_polynomial` 先算 `x**i` 再取模 | 大 x 时中间值巨大、慢 | Horner 法逐步取模 |
| 14 | 模数由用户输入 | 非素数时模逆不存在 | 固定 `FIELD_MODULUS = 2**255 - 19`，不对外开放修改 |
| 15 | `except Exception` 包住全部输入解析 | 掩盖程序错误 | GUI 只捕获 `PCSSError`（输入/参数错误） |

## 3. FRI 降幂与门限的冲突（任务 A.3）

一次折叠：`f(X) = f_e(X²) + X·f_o(X²)` → `g(Y) = f_e(Y) + α·f_o(Y)`。

对门限多项式 `f`（次数 k−1）：

* `deg g = ⌊(k−1)/2⌋ < k−1` → 少于 k 个份额就能确定 g，门限被破坏；
* `g(0) = f_0 + α·f_1 ≠ f_0` → 常数项（秘密）改变。

原实现之所以"看起来能用"，是因为常数项在折叠**之后**才被替换、且门限与次数本来就没有绑定。
因此重构后：

* `legacy/FRI.py` 原样保留；
* `pcss/fri.py` 是在 GF(p) 上的同一算法（默认 α = 6、`max_degree = 5`），作为**独立研究原型**；
* 秘密分享多项式**不做** FRI 折叠（`tests/test_fri.py::test_fri_breaks_shamir_threshold` 演示冲突）。

## 4. 承诺 / 验证的性质（任务 D.3）

保留的代数关系：

```
W·Z_T(x) = Σ_i (cm_i − r_i(x))·y^i·Z_{T\S_i}(x)
```

测试证明了：

* 合法输入下等式成立（随机 255-bit 多项式、多组 x, y）；
* 错误见证、篡改任一 cm_i（配合诚实 W）、用其他 (x, y) 的见证都会被拒绝；
* x ∈ T、y = 0、S_i ⊄ T 等退化/非法输入被拒绝。

同时必须如实说明的限制：

1. `cm_i = f_i(x)` 只是多项式求值，**不具备**标准承诺方案的隐藏性或绑定性，不能称为生产级 Polynomial Commitment。
2. 知道 `r_i` 的人可以对**任意** `cm'` 解出 `W' = RHS / Z_T(x)` 并通过验证
   （`test_forged_consistent_pair_is_accepted_documented_limitation`）。因此该验证**不能检测任意的份额篡改**，
   只能检测"份额与该次给出的见证不一致"。
3. 原 GUI 规则要求 `0 ∈ S_i`，于是 `r_i(0) = f_i(0)` 就是秘密分片本身——拿到 `r_i` 的验证者即知道秘密。
   重构保留此规则（默认 `require_zero_in_point_sets=True`）以忠实于原研究流程，但 `r_i` 只能交给可信验证方。
4. 若 `|S_i| ≥ k`，则 `r_i = f_i`，见证恒为 0，验证者获得完整多项式。
5. 恢复阶段：份额数 > k 时会用冗余份额做一致性检查（`InconsistentSharesError`）；恰好 k 个份额时，
   篡改无法由恢复过程本身发现（多数情况下解码会因填充/UTF-8 校验失败而报错，但不保证）。

## 5. 资源限制（任务 B.3，`pcss/config.py`）

| 参数 | 上限 |
| --- | --- |
| 门限 k | 2 ≤ k ≤ 32 |
| 份额数 n | k ≤ n ≤ 100 |
| 消息长度 | 2048 UTF-8 字节（≤ 67 个分片） |
| \|S_i\| | ≤ 6（与原 GUI 一致） |
| \|T\| | ≤ 64 |
| 通用多项式 / FRI 输入 | ≤ 1024 个系数（折叠轮数 ≤ 10，必然终止） |

所有坐标、份额值、挑战值都必须是 `[0, p)` 内的整数（拒绝 `bool`、浮点数、负数和 ≥ p 的值）。
