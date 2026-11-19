"""Tkinter front-end: dealer (prover) initialisation, share distribution and verification.

Run from the repository root::

    python -m gui.dealer_app

This window only collects input, calls ``pcss`` and displays the result.  All
algorithms live in the ``pcss`` package (the legacy ``main_withui_finally.py``
mixed both).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from typing import Optional

from pcss.commitment import Verifier
from pcss.errors import PCSSError
from pcss.vss import DealerSession

from .parsing import (bundle_to_json, parse_int, parse_int_list, parse_optional_int,
                      parse_point_sets)


class DealerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PCSS – 证明者 / 验证者 (p = 2^255 - 19)")
        self.geometry("900x720")
        self.session: Optional[DealerSession] = None
        self.verifier: Optional[Verifier] = None
        self._build_dealer_frame()
        self._build_verifier_frame()
        self.log = scrolledtext.ScrolledText(self, height=14, wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=4)

    # ------------------------------------------------------------------ UI --
    def _build_dealer_frame(self) -> None:
        f = tk.LabelFrame(self, text="1. 初始化证明者 (Dealer)", padx=6, pady=4)
        f.pack(fill="x", padx=8, pady=4)

        tk.Label(f, text="秘密消息:").grid(row=0, column=0, sticky="nw")
        self.message_text = tk.Text(f, height=3, width=80)
        self.message_text.grid(row=0, column=1, columnspan=5, sticky="we")

        tk.Label(f, text="门限 k:").grid(row=1, column=0, sticky="w")
        self.k_entry = tk.Entry(f, width=8)
        self.k_entry.insert(0, "3")
        self.k_entry.grid(row=1, column=1, sticky="w")
        tk.Label(f, text="份额数 n:").grid(row=1, column=2, sticky="w")
        self.n_entry = tk.Entry(f, width=8)
        self.n_entry.insert(0, "5")
        self.n_entry.grid(row=1, column=3, sticky="w")
        tk.Label(f, text="(多项式次数由系统设为 k-1)").grid(row=1, column=4, sticky="w")

        tk.Label(f, text="点集 S_i\n(每行一个,\n单行=所有分片共用,\n须包含 0):").grid(
            row=2, column=0, sticky="nw")
        self.sets_text = tk.Text(f, height=4, width=40)
        self.sets_text.insert("1.0", "0,7,9")
        self.sets_text.grid(row=2, column=1, columnspan=3, sticky="we")

        tk.Label(f, text="点集 T (留空 = ∪S_i):").grid(row=3, column=0, sticky="w")
        self.t_entry = tk.Entry(f, width=40)
        self.t_entry.grid(row=3, column=1, columnspan=3, sticky="we")

        tk.Button(f, text="初始化证明者", command=self.on_initialise).grid(row=4, column=1, pady=4)
        tk.Button(f, text="导出份额 JSON…", command=self.on_export).grid(row=4, column=2, pady=4)

    def _build_verifier_frame(self) -> None:
        f = tk.LabelFrame(self, text="2. 验证者", padx=6, pady=4)
        f.pack(fill="x", padx=8, pady=4)
        tk.Label(f, text="份额 x:").grid(row=0, column=0, sticky="w")
        self.x_entry = tk.Entry(f, width=12)
        self.x_entry.grid(row=0, column=1, sticky="w")
        tk.Label(f, text="挑战 y (留空=随机, 1 ≤ y < p):").grid(row=0, column=2, sticky="w")
        self.y_entry = tk.Entry(f, width=30)
        self.y_entry.grid(row=0, column=3, sticky="w")
        tk.Button(f, text="分发份额与见证", command=self.on_open).grid(row=0, column=4, padx=4)

        tk.Label(f, text="承诺值 cm_i (逗号分隔):").grid(row=1, column=0, sticky="w")
        self.cm_entry = tk.Entry(f, width=100)
        self.cm_entry.grid(row=1, column=1, columnspan=4, sticky="we")
        tk.Label(f, text="见证 W:").grid(row=2, column=0, sticky="w")
        self.w_entry = tk.Entry(f, width=100)
        self.w_entry.grid(row=2, column=1, columnspan=4, sticky="we")
        tk.Button(f, text="验证", command=self.on_verify).grid(row=3, column=1, pady=4, sticky="w")

    # ------------------------------------------------------------- actions --
    def _write(self, text: str) -> None:
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def _error(self, exc: Exception) -> None:
        messagebox.showerror("输入错误", str(exc))

    def on_initialise(self) -> None:
        try:
            message = self.message_text.get("1.0", "end-1c")
            k = parse_int(self.k_entry.get(), "k")
            n = parse_int(self.n_entry.get(), "n")
            sets = parse_point_sets(self.sets_text.get("1.0", "end-1c"))
            t_text = self.t_entry.get().strip()
            t = parse_int_list(t_text, "T") if t_text else None
            self.session = DealerSession.create(message, k, n, sets, t)
            self.verifier = Verifier(self.session.public_parameters())
        except PCSSError as exc:
            self._error(exc)
            return
        meta = self.session.metadata
        params = self.session.public_parameters()
        self._write(f"[初始化完成] {meta.to_dict()}")
        self._write(f"  T = {list(params.evaluation_set)}")
        self._write(f"  份额 x 坐标 = {[s.x for s in self.session.shares]}")
        self.x_entry.delete(0, tk.END)
        self.x_entry.insert(0, str(self.session.shares[0].x))

    def on_export(self) -> None:
        if self.session is None:
            messagebox.showwarning("提示", "证明者尚未初始化")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(bundle_to_json(self.session.metadata, self.session.shares))
        self._write(f"[导出] {path}")

    def on_open(self) -> None:
        if self.session is None:
            messagebox.showwarning("提示", "证明者尚未初始化")
            return
        try:
            x = parse_int(self.x_entry.get(), "x")
            y = parse_optional_int(self.y_entry.get(), "y")
            _share, opening = self.session.open_share(x, y)
        except PCSSError as exc:
            self._error(exc)
            return
        self.y_entry.delete(0, tk.END)
        self.y_entry.insert(0, str(opening.y))
        self.cm_entry.delete(0, tk.END)
        self.cm_entry.insert(0, ",".join(map(str, opening.commitments)))
        self.w_entry.delete(0, tk.END)
        self.w_entry.insert(0, str(opening.witness))
        self._write(f"[分发] x={x}, y={opening.y}\n  cm={list(opening.commitments)}\n  W={opening.witness}")

    def on_verify(self) -> None:
        if self.verifier is None:
            messagebox.showwarning("提示", "证明者尚未初始化")
            return
        try:
            x = parse_int(self.x_entry.get(), "x")
            y = parse_int(self.y_entry.get(), "y")
            cms = parse_int_list(self.cm_entry.get(), "cm")
            w = parse_int(self.w_entry.get(), "W")
            result = self.verifier.verify(x, y, cms, w)
        except PCSSError as exc:
            self._error(exc)
            return
        self._write(f"[验证] x={x}, y={y}\n  F_left  = {result.left}\n  F_right = {result.right}\n"
                    f"  结果: {'验证通过' if result.valid else '验证失败'}")


def main() -> None:
    DealerApp().mainloop()


if __name__ == "__main__":
    main()
