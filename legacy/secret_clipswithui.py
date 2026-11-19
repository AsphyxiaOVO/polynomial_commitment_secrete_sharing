import tkinter as tk
from tkinter import messagebox
from message_coding import merge_polynomials_to_integer, decode_constant_to_message

# 生成多项式
def generate_polynomial(coefficients):
    return coefficients[::-1]

# 计算多项式在指定点的数值
def evaluate_polynomial(coefficients, x, field):
    result = 0
    for i, c in enumerate(coefficients):
        result += c * (x ** i)
    return result % field

# 在模下求逆
def mod_inverse(a, p):
    if a == 0:
        return 0
    lm, hm = 1, 0
    low, high = a % p, p
    while low > 1:
        r = high // low
        nm, new = hm - lm * r, high - low * r
        lm, low, hm, high = nm, new, lm, low
    return lm % p

# 拉格朗日插值法
def lagrange(array, p):
    k = len(array)
    l = 0
    for i in range(k):
        xi, yi = array[i]
        li = yi
        for j in range(k):
            if i != j:
                xj = array[j][0]
                li *= (0 - xj) * mod_inverse(xi - xj, p)
                li %= p
        l += li
        l %= p
    return l

# 从输入的秘密中恢复消息
def secret_recovery_frominput(k, num, field, shares):
    recovered_secrets = []
    for poly_index in range(num):
        points = [(share['x'], share['y'][poly_index]) for share in shares]
        secret = lagrange(points, field)
        recovered_secrets.append(secret)
    return recovered_secrets

class SecretRecoveryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Secret Recovery")

        # 参数输入
        self.num_label = tk.Label(root, text="多项式的数量:")
        self.num_label.grid(row=0, column=0)
        self.num_entry = tk.Entry(root)
        self.num_entry.grid(row=0, column=1)

        self.field_label = tk.Label(root, text="有限域的值:")
        self.field_label.grid(row=1, column=0)
        self.field_entry = tk.Entry(root)
        self.field_entry.grid(row=1, column=1)

        self.k_label = tk.Label(root, text="门限 (k):")
        self.k_label.grid(row=2, column=0)
        self.k_entry = tk.Entry(root)
        self.k_entry.grid(row=2, column=1)

        self.padding_label = tk.Label(root, text="填充的0数目:")
        self.padding_label.grid(row=3, column=0)
        self.padding_entry = tk.Entry(root)
        self.padding_entry.grid(row=3, column=1)

        self.generate_button = tk.Button(root, text="初始化输入", command=self.generate_share_inputs)
        self.generate_button.grid(row=4, column=0, columnspan=2)

        # 用于动态共享输入的帧
        self.share_frame = tk.Frame(root)
        self.share_frame.grid(row=5, column=0, columnspan=2)

        # 计算恢复的秘密的按钮
        self.compute_button = tk.Button(root, text="恢复秘密", command=self.compute_recovered_secrets)
        self.compute_button.grid(row=6, column=0, columnspan=2)

        # 输出文本区
        self.output_text = tk.Text(root, height=10, width=50)
        self.output_text.grid(row=7, column=0, columnspan=2)

        # 解码按钮
        self.decode_button = tk.Button(root, text="Decode Message", command=self.decode_message)
        self.decode_button.grid(row=8, column=0, columnspan=2)

        self.shares = []  # 存储共享值
        self.recovered_secrets = []  # 存储计算的秘密

    # 在模下的输入
    def generate_share_inputs(self):
        try:
            num = int(self.num_entry.get())
            k = int(self.k_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "请输入多项式数和份额的有效整数。")
            return

        # 清除之前的输入
        for widget in self.share_frame.winfo_children():
            widget.destroy()

        self.shares = []
        for i in range(k):
            share_label = tk.Label(self.share_frame, text=f"Share {i+1}:")
            share_label.grid(row=i, column=0)

            x_label = tk.Label(self.share_frame, text="x:")
            x_label.grid(row=i, column=1)
            x_entry = tk.Entry(self.share_frame)
            x_entry.grid(row=i, column=2)

            y_entries = []
            for j in range(num):
                y_label = tk.Label(self.share_frame, text=f"y{j+1}:")
                y_label.grid(row=i, column=3 + j*2)
                y_entry = tk.Entry(self.share_frame)
                y_entry.grid(row=i, column=4 + j*2)
                y_entries.append(y_entry)

            self.shares.append({'x': x_entry, 'y': y_entries})

    # 计算和显示秘密
    def compute_recovered_secrets(self):
        try:
            num = int(self.num_entry.get())
            field = int(self.field_entry.get())
            k = int(self.k_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "请输入多项式数、模和份额的有效数")
            return

        shares_data = []
        for share in self.shares:
            x = int(share['x'].get())
            y_values = [int(y_entry.get()) for y_entry in share['y']]
            shares_data.append({'x': x, 'y': y_values})

        self.recovered_secrets = secret_recovery_frominput(k, num, field, shares_data)
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, f"Recovered secrets: {self.recovered_secrets}\n")

    # 解码和显示秘密
    def decode_message(self):
        try:
            padding_zeros = int(self.padding_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "请输入填充零的有数")
            return

        if not self.recovered_secrets:
            messagebox.showerror("Error", "没有要解码的秘密.")
            return

        encoded = merge_polynomials_to_integer(self.recovered_secrets, padding_zeros)
        decoded = decode_constant_to_message(encoded)
        self.output_text.insert(tk.END, f"解码的消息: {decoded}\n")

if __name__ == "__main__":
    root = tk.Tk()
    app = SecretRecoveryApp(root)
    root.mainloop()