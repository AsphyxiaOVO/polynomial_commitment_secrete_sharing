# legacy/ — 原始实现（未修改）

这里是重构前的原始代码，内容与 `master` 分支根目录下的同名文件完全一致，仅移动了位置，用于对照和回归测试
（`tests/test_legacy_regressions.py`）。新代码请使用仓库根目录的 `pcss/` 与 `gui/`。

运行原界面（需要 numpy、sympy、tkinter）：

```bash
cd legacy
python main_withui_finally.py
python secret_clipswithui.py
```

原实现存在的问题及修复见 [`../docs/ANALYSIS.md`](../docs/ANALYSIS.md)。

原界面截图：[承诺界面](../docs/images/commitment_ui.png) ·
[验证结果](../docs/images/verification.png) · [恢复界面](../docs/images/recovery_ui.png)
