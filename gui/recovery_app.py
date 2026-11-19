"""Tkinter front-end: secret recovery from >= k shares.

Run from the repository root::

    python -m gui.recovery_app

Input is the JSON exported by ``gui.dealer_app`` (metadata + shares).  The
threshold k, chunk_count and original_length come from the metadata stored
at sharing time; the user no longer types the field modulus or a padding count.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox

from pcss.errors import PCSSError, ValidationError
from pcss.encoding import decode_message
from pcss.sharing import recover_constants

from .parsing import bundle_from_json, parse_int_list


class RecoveryApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PCSS – 秘密恢复")
        self.geometry("800x600")

        top = tk.Frame(self)
        top.pack(fill="x", padx=8, pady=4)
        tk.Button(top, text="载入份额 JSON…", command=self.on_load).pack(side="left")
        tk.Label(top, text="  使用的份额 x (逗号分隔, 留空 = 全部):").pack(side="left")
        self.subset_entry = tk.Entry(top, width=30)
        self.subset_entry.pack(side="left")
        tk.Button(top, text="恢复秘密", command=self.on_recover).pack(side="left", padx=6)

        self.json_text = tk.Text(self, height=18)
        self.json_text.pack(fill="both", expand=True, padx=8, pady=4)
        self.output = tk.Text(self, height=8, wrap="word")
        self.output.pack(fill="both", padx=8, pady=4)

    def on_load(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return
        with open(path, encoding="utf-8") as fh:
            self.json_text.delete("1.0", tk.END)
            self.json_text.insert("1.0", fh.read())

    def on_recover(self) -> None:
        try:
            metadata, shares = bundle_from_json(self.json_text.get("1.0", "end-1c"))
            subset_text = self.subset_entry.get().strip()
            if subset_text:
                wanted = parse_int_list(subset_text, "x")
                by_x = {s.x: s for s in shares}
                missing = [x for x in wanted if x not in by_x]
                if missing:
                    raise ValidationError(f"JSON 中没有这些 x 的份额: {missing}")
                shares = [by_x[x] for x in wanted]
            constants = recover_constants(shares, metadata)
            message = decode_message(constants, metadata.original_length,
                                     metadata.chunk_size, metadata.chunk_count)
        except PCSSError as exc:
            messagebox.showerror("恢复失败", str(exc))
            return
        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, f"门限 k = {metadata.threshold}, 使用份额数 = {len(shares)}\n")
        self.output.insert(tk.END, f"恢复的常数项: {constants}\n")
        self.output.insert(tk.END, f"解码的消息: {message}\n")


def main() -> None:
    RecoveryApp().mainloop()


if __name__ == "__main__":
    main()
