# polynomial_commitment_secrete_sharing

> 基于多项式承诺思路的可验证秘密分享 —— 毕业设计原型（重构版）
> English: A teaching / research prototype of verifiable secret sharing inspired by polynomial commitments

**⚠️ 这是教学与研究原型，不是生产级密码系统。** 使用素数 p = 2^255 − 19 并不意味着整个协议具备生产级安全性；
其中的"承诺值"是普通多项式求值，不具备 KZG 等标准承诺方案的隐藏性 / 绑定性。详见 [已知限制](#已知限制)。

## 项目简介

本项目对应 2025 年海南大学本科毕业设计《基于多项式承诺的可验证秘密分享》，以
Boneh et al., *Efficient polynomial commitment schemes for multiple points and polynomials*
([ePrint 2020/081](https://eprint.iacr.org/2020/081)) 的多点、多多项式批量验证思路为基础，结合：

- UTF-8 消息分片与 Shamir 门限秘密分享；
- 多项式求值、见证生成与代数一致性验证；
- FRI 风格降幂（独立研究原型）。

本分支（`refactor/core-validation-tests`）在**不改变研究思路**的前提下，把算法从 Tkinter GUI 中拆分为可测试的
`pcss` 包，修复了原实现中的正确性问题，并补充了输入校验与单元测试。原始代码完整保留在 [`legacy/`](legacy/)。
原实现的分析与问题清单见 [`docs/ANALYSIS.md`](docs/ANALYSIS.md)。

## 流程

1. **编码**：消息 → UTF-8 字节 → 每 31 字节一个分片（末片右侧补 `\x00`）→ `int.from_bytes(…, "big")`。
   因为 2^248 < p，每个分片都是合法的域元素。
2. **秘密分享**：每个分片 `s_j` 作为多项式 `f_j` 的常数项；系统按门限 k 固定 `deg f_j = k − 1`，其余系数随机生成
   （`secrets.randbelow`）。参与者 x 的份额为 `(x, [f_1(x), …, f_m(x)])`。
3. **证明者初始化**：对每个 `f_i` 和点集 `S_i ⊆ T` 求插值多项式 `r_i`。
4. **分发与见证**：验证者给出 `(x, y)`，证明者返回 `cm_i = f_i(x)`（即份额值）与见证
   `W = Σ y^i · ((f_i − r_i)/Z_{S_i})(x)`。
5. **验证**：检查 `W·Z_T(x) == Σ (cm_i − r_i(x))·y^i·Z_{T\S_i}(x)`。
6. **恢复**：≥ k 个份额 → 拉格朗日插值求 `f_j(0)` → 按 `original_length` 去除填充 → UTF-8 解码。

三个参数互相独立，不可混淆：**`chunk_count`**（分片数 = 多项式个数，由消息字节长度决定）、
**`share_count` n**（参与者 / 份额数）、**`threshold` k**（恢复门限）。

## 目录结构

```
pcss/                 核心算法（无 GUI 依赖，仅标准库）
  config.py           FIELD_MODULUS = 2**255 - 19, CHUNK_SIZE = 31, 资源上限
  errors.py           异常层级（输入错误均为 ValueError 子类）
  field.py            GF(p) 运算、模逆
  polynomial.py       多项式运算（系数统一为低→高）、除法、插值
  encoding.py         消息 ↔ 31 字节分片
  sharing.py          门限分享 (d = k − 1) 与恢复
  commitment.py       Prover / Verifier（论文中的批量验证等式）
  fri.py              FRI 风格降幂研究原型（不作用于分享多项式）
  vss.py              端到端流程 DealerSession
gui/                  Tkinter 薄界面（只做输入/显示）
  dealer_app.py       证明者初始化、分发份额与见证、验证
  recovery_app.py     载入 JSON 份额并恢复秘密
  parsing.py          界面文本解析（可单测）
tests/                pytest 单元测试（含与 legacy 实现的对照 / 回归测试）
examples/demo.py      命令行演示
legacy/               原始实现（未修改）
docs/                 分析文档、原界面截图
```

## 快速开始

需要 Python 3.9+。核心包只依赖标准库。

```bash
pip install -r requirements-dev.txt   # pytest；numpy/sympy 仅用于 legacy 对照测试
python -m pytest                       # 运行全部测试
python examples/demo.py                # 命令行演示
python -m gui.dealer_app               # 证明者 / 验证者界面
python -m gui.recovery_app             # 秘密恢复界面
```

代码中使用：

```python
from pcss import DealerSession, Verifier, recover_message

session = DealerSession.create("你好 🌸", threshold=3, share_count=5, point_sets=[[0, 7, 9]])
verifier = Verifier(session.public_parameters())

share, opening = session.open_share(x=1, y=12345)   # y 为验证者的挑战值
assert verifier.verify_opening(opening).valid

print(recover_message(session.shares[:3], session.metadata))   # -> "你好 🌸"
```

## 主要改动

| 任务 | 内容 |
| --- | --- |
| A 门限 | 系统根据 k 固定 `d = k − 1`；校验 `k ≥ 2`、`n ≥ k`、`n < p`、份额数 ≥ k、x 互不相同且非 0、值属于 GF(p)、每份额值个数 = `chunk_count`；门限写入元数据，恢复时不从点数推断次数 |
| B 有限域 | 统一 `FIELD_MODULUS = 2**255 - 19`；纯 Python 整数实现取模、模逆、Horner 求值、多项式除法和拉格朗日插值（替换 NumPy/SymPy 实现）；设置资源上限 |
| C 编码 | 31 字节定长分片 + 元数据 `original_length / chunk_size / chunk_count / threshold`；空消息编码为 1 个全零分片、`original_length = 0` |
| D 验证 | 保留原证明者 / 验证者算法；修复空点集、除法非法输入、重复点、不可逆元素、系数顺序、次数判断；拒绝 `S_i ⊄ T`、`x ∈ T`、`y = 0` |
| 解耦 | 算法移入 `pcss`；GUI 改为薄界面，只捕获 `PCSSError`，不再使用宽泛的 `except Exception` |
| FRI | 与门限冲突（降低次数、改变常数项），保留为独立研究原型，不应用于秘密分享多项式 |

## 已知限制

- **不是标准密码学承诺**：`cm_i = f_i(x)` 不隐藏也不绑定。知道 `r_i` 的人可以为任意 `cm'` 构造通过验证的 `W'`
  （见 `tests/test_commitment.py::test_forged_consistent_pair_is_accepted_documented_limitation`）。
  因此当前方案**不能检测任意份额篡改**；已测试能识别的是：错误见证、配合诚实见证的篡改份额值、退化的验证点。
- **`r_i` 会泄露秘密**：原设计要求 `0 ∈ S_i`，于是 `r_i(0) = f_i(0)` 即秘密分片。`r_i` 只能交给可信验证方；
  可用 `require_zero_in_point_sets=False` 关闭此规则，但这偏离了原论文实现。
- **恢复时的篡改检测有限**：份额多于 k 时用冗余份额做一致性检查；恰好 k 个时无法保证发现篡改。
- **FRI** 仅是研究原型，不是完整的 FRI 低次测试协议，也不参与秘密分享。
- 未提供安全性证明；随机数来自 `secrets`，但未做常数时间实现等工程防护。

## 参考文献

- D. Boneh, J. Drake, B. Fisch, A. Gabizon. *Efficient polynomial commitment schemes for multiple points and polynomials.*
  [ePrint 2020/081](https://eprint.iacr.org/2020/081)

---

## English Overview

A refactored teaching/research prototype of verifiable secret sharing:

- **`pcss` package** (standard library only): GF(p) arithmetic with p = 2^255 − 19, polynomial utilities
  (low-to-high coefficients), 31-byte message chunking, Shamir sharing with degree fixed to k − 1,
  the thesis' batched evaluation check `W·Z_T(x) = Σ (cm_i − r_i(x))·y^i·Z_{T\S_i}(x)`, and an FRI-style folding prototype.
- **Validation**: threshold/share-count bounds, distinct non-zero x-coordinates, field-range checks,
  `S_i ⊆ T`, `x ∉ T`, `y ≠ 0`, resource limits; explicit exception hierarchy.
- **Tests**: ~200 pytest cases (≈98 % line coverage of `pcss`), including regression tests that reproduce bugs of the
  original code in `legacy/` and equivalence tests showing the refactored algebra matches it.
- **Limitations**: the "commitments" are plain evaluations (neither hiding nor binding); forged consistent
  (cm', W') pairs pass; r_i reveals the secret when 0 ∈ S_i. Not production cryptography.

Run `python -m pytest`, `python examples/demo.py`, `python -m gui.dealer_app`, `python -m gui.recovery_app`.
