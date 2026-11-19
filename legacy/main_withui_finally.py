import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
from polynomial_division import polynomial_division
from rxi import fit_polynomial
from FRI import reduce_power
from message_coding import encode_message_to_constant, split_integer_to_polynomials


def polynomial_add(poly1, poly2, field):
    max_len = max(len(poly1), len(poly2))
    poly1 = [0] * (max_len - len(poly1)) + poly1
    poly2 = [0] * (max_len - len(poly2)) + poly2
    result = [(a + b) % field for a, b in zip(poly1, poly2)]
    return result

def polynomial_subtraction(poly1, poly2, field):
    max_len = max(len(poly1), len(poly2))
    poly1 = [0] * (max_len - len(poly1)) + poly1
    poly2 = [0] * (max_len - len(poly2)) + poly2
    result = [(a - b) % field for a, b in zip(poly1, poly2)]
    return result


class Prover:
    def __init__(self):
        self.coefficients = []
        self.field = 0
        self.S = []
        self.points = []
        self.T = []
        self.rx = []
        self.Zs = []
        self.initialized = False

    def initialize_parameters(self, num_polys, field, S, T, coefficients, message):
        self.field = field
        self.S = S
        self.points = S
        self.T = T
        self.coefficients = coefficients

        self.reduce_high_degree_polynomials()

        encoded_message = encode_message_to_constant(message)
        constants, padding_zeros = split_integer_to_polynomials(encoded_message, num_polys)
        print(f"分割后的常数项: {constants}, 填充的0数量: {padding_zeros}")
        for i in range(num_polys):
            reduced_coeffs = self.coefficients[i]
            current_constant = self.evaluate_polynomial(reduced_coeffs, 0, self.field)
            adjusted_coeffs = polynomial_subtraction(reduced_coeffs, [current_constant], self.field)
            adjusted_coeffs = polynomial_add(adjusted_coeffs, [constants[i]], self.field)
            self.coefficients[i] = adjusted_coeffs

        self.rx = []
        for i in range(len(self.coefficients)):
            result = self.evaluate_polynomial_at_points(self.coefficients[i], self.points[i], self.field)
            self.rx.append(fit_polynomial(result, self.field))

        self.initialized = True

    def reduce_high_degree_polynomials(self, max_degree=5):
        for i in range(len(self.coefficients)):
            coeffs = self.coefficients[i]
            degree = len(coeffs) - 1
            while degree >= 0 and coeffs[degree] == 0:
                degree -= 1
            if degree > max_degree:
                coeffs_low_to_high = coeffs[::-1]
                reduced_coeffs_low_to_high = reduce_power(coeffs_low_to_high)
                self.coefficients[i] = reduced_coeffs_low_to_high[::-1]

    @staticmethod
    def evaluate_polynomial(coefficients, x, field):
        result = 0
        for i, c in enumerate(reversed(coefficients)):
            result += c * (x ** i)
        return result % field

    def evaluate_polynomial_at_points(self, coefficients, points, field):
        return [(x, self.evaluate_polynomial(coefficients, x, field)) for x in points]

    @staticmethod
    def polynomial_multiply_mod(p1, p2, field):
        result = [0] * (len(p1) + len(p2) - 1)
        for i in range(len(p1)):
            for j in range(len(p2)):
                result[i + j] = (result[i + j] + p1[i] * p2[j]) % field
        return result

    def compute_commitments(self, x):
        com = [self.evaluate_polynomial(coeffs, x, self.field) for coeffs in self.coefficients]
        return com

    def compute_proof_w(self, y, x):
        self.Zs = []
        for i in range(len(self.coefficients)):
            polynomials = [[1, -s] for s in self.S[i]]
            result = polynomials[0]
            for poly in polynomials[1:]:
                result = self.polynomial_multiply_mod(result, poly, self.field)
            self.Zs.append(result)

        hx = [0]
        for i in range(len(self.coefficients)):
            subtraction = polynomial_subtraction(self.coefficients[i], self.rx[i], self.field)
            portion = polynomial_division(subtraction, self.Zs[i], self.field)
            portion_weight = self.polynomial_multiply_mod(portion[0], [y ** i], self.field)
            hx = polynomial_add(hx, portion_weight, self.field)

        W = self.evaluate_polynomial(hx, x, self.field)
        return W


class Verifier:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.Ztx = 1

    def compute_zi(self, T, S, field):
        Zt_minus_s_points = [[x for x in T if x not in Si] for Si in S]
        Zi = []
        for points in Zt_minus_s_points:
            polynomials = [[1, -p] for p in points]
            result = polynomials[0]
            for poly in polynomials[1:]:
                result = Prover.polynomial_multiply_mod(result, poly, field)
            Zi.append(Prover.evaluate_polynomial(result, self.x, field))
        return Zi

    def compute_f_right(self, num, y, cm, ri, zi, field):
        result = 0
        for i in range(num):
            result += (cm[i] - ri[i]) * (y ** i) * zi[i]
        return result % field

    def compute_f_left(self, W, field):
        return (W * self.Ztx) % field

    def verify_equality(self, T, field):
        self.Ztx = 1  # 将Ztx重置为1后再计算乘积
        for t in T:
            self.Ztx *= (self.x - t)
            self.Ztx %= field

# 验证过程
class ProverThread(threading.Thread):
    def __init__(self, prover, params, app):
        threading.Thread.__init__(self)
        self.prover = prover
        self.params = params
        self.app = app

    def run(self):
        self.prover.initialize_parameters(
            self.params['num_polys'],
            self.params['field'],
            self.params['S'],
            self.params['T'],
            self.params['coefficients'],
            self.params['message']
        )
        self.app.after(0, self.app.prover_finished)

# UI窗口
class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Prover and Verifier UI")
        self.geometry("600x400")

        self.prover = Prover()
        self.verifiers = []

        # UI elements
        self.start_prover_button = tk.Button(self, text="初始化证明者", command=self.start_prover)
        self.start_prover_button.pack(pady=5)

        self.add_verifier_button = tk.Button(self, text="添加验证者", command=self.add_verifier, state=tk.DISABLED)
        self.add_verifier_button.pack(pady=5)

        self.prover_status = tk.Label(self, text="证明者未初始化")
        self.prover_status.pack(pady=5)

        # Frame to hold verifier widgets
        self.verifier_frame = tk.Frame(self)
        self.verifier_frame.pack(fill="both", expand=True)

    def start_prover(self):
        params = self.get_prover_params()
        if params:
            self.prover_status.config(text="证明者初始化中...")
            self.start_prover_button.config(state=tk.DISABLED)
            self.prover_thread = ProverThread(self.prover, params, self)
            self.prover_thread.start()

    def prover_finished(self):
        self.prover_status.config(text="证明者已初始化")
        self.add_verifier_button.config(state=tk.NORMAL)
        self.start_prover_button.config(state=tk.NORMAL)
        print("证明者参数:")
        print(f"多项式数目: {len(self.prover.coefficients)}")
        print(f"有限域: {self.prover.field}")
        print(f"S: {self.prover.S}")
        print(f"T: {self.prover.T}")
        print(f"多项式系数: {self.prover.coefficients}")
        print(f"rx: {self.prover.rx}")

    def get_prover_params(self):
        dialog = tk.Toplevel(self)
        dialog.title("证明者参数")
        dialog.geometry("1000x500")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="多项式数量:").pack()
        num_polys_entry = tk.Entry(dialog)
        num_polys_entry.pack()

        tk.Label(dialog, text="有限域:").pack()
        field_entry = tk.Entry(dialog)
        field_entry.pack()

        tk.Label(dialog, text="点集T:").pack()
        T_entry = tk.Entry(dialog)
        T_entry.pack()

        tk.Label(dialog, text="对于每个多项式，在一行上输入S（,分隔）和系数（,分隔，从高到低，不包括常数），用“；”分隔：").pack()
        polys_text = tk.Text(dialog, height=10)
        polys_text.pack()

        tk.Label(dialog, text="要编码的信息:").pack()
        message_entry = tk.Entry(dialog)
        message_entry.pack()

        params = {}

        def on_submit():
            try:
                num_polys = int(num_polys_entry.get())
                field = int(field_entry.get())
                T = list(map(int, T_entry.get().split(',')))
                polys_lines = polys_text.get("1.0", tk.END).strip().split('\n')
                if len(polys_lines) != num_polys:
                    raise ValueError("多项式的数目不匹配")
                S = []
                coefficients = []
                for line in polys_lines:
                    parts = line.split(';')
                    if len(parts) != 2:
                        raise ValueError("每行必须包含S和系数，用';'分隔")
                    S.append(list(map(int, parts[0].split(','))))
                    if 0 not in S[-1] or len(S[-1]) > 6:
                        raise ValueError("每个S必须包含0，长度<=6")
                    coeffs = list(map(int, parts[1].split(',')))
                    coefficients.append(coeffs + [0])
                message = message_entry.get()
                params['num_polys'] = num_polys
                params['field'] = field
                params['S'] = S
                params['T'] = T
                params['coefficients'] = coefficients
                params['message'] = message
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Input Error", str(e))

        tk.Button(dialog, text="Submit", command=on_submit).pack(pady=5)
        self.wait_window(dialog)
        return params if params else None

    def add_verifier(self):
        params = self.get_verifier_params()
        if params:
            verifier = Verifier(params['x'], params['y'])
            self.verifiers.append(verifier)
            self.create_verifier_ui(verifier)
            self.Distribute_share(verifier)

    def get_verifier_params(self):
        dialog = tk.Toplevel(self)
        dialog.title("验证者参数")
        dialog.geometry("200x150")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="x的值:").pack()
        x_entry = tk.Entry(dialog)
        x_entry.pack()

        tk.Label(dialog, text="y的值:").pack()
        y_entry = tk.Entry(dialog)
        y_entry.pack()

        params = {}

        def on_submit():
            try:
                params['x'] = int(x_entry.get())
                params['y'] = int(y_entry.get())
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Input Error", "X和y必须是整数")

        tk.Button(dialog, text="Submit", command=on_submit).pack(pady=5)
        self.wait_window(dialog)
        return params if params else None

    def create_verifier_ui(self, verifier):
        """为验证器创建UI"""
        frame = tk.LabelFrame(self.verifier_frame, text=f"Verifier (x={verifier.x}, y={verifier.y})", padx=5, pady=5)
        frame.pack(fill="x", pady=5)

        tk.Button(frame, text="Distribute Share", command=lambda: self.Distribute_share(verifier)).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Run Verification", command=lambda: self.run_verification(verifier)).pack(side=tk.LEFT, padx=5)

        # Result display area
        result_text = scrolledtext.ScrolledText(frame, height=5, width=50)
        result_text.pack(side=tk.LEFT, padx=5)
        verifier.result_text = result_text  # 之后重复使用

    def Distribute_share(self, verifier):
        if not self.prover.initialized:
            messagebox.showwarning("Warning", "证明者尚未初始化")
            return
        x = verifier.x
        y = verifier.y
        proof_w = self.prover.compute_proof_w(y, x)
        commitments = self.prover.compute_commitments(x)
        verifier.verify_equality(self.prover.T, self.prover.field)
        messagebox.showinfo("分发结果", f"用户选择的x={x}下的多项式的承诺值分别为：{commitments},见证为：{proof_w}")

    def run_verification(self, verifier):
        if not self.prover.initialized:
            messagebox.showwarning("Warning", "证明者尚未初始化")
            return
        inputs = self.get_verification_inputs(verifier)
        if not inputs:
            return

        x = verifier.x
        y = verifier.y
        proof_w_input = inputs['proof_w']
        commitments_input = inputs['commitments']

        Zi = verifier.compute_zi(self.prover.T, self.prover.S, self.prover.field)
        ri = [self.prover.evaluate_polynomial(rx, x, self.prover.field) for rx in self.prover.rx]
        f_right = verifier.compute_f_right(len(commitments_input), y, commitments_input, ri, Zi, self.prover.field)
        f_left = verifier.compute_f_left(proof_w_input, self.prover.field)

        result = (
            f"Verification for x={x}, y={y}\n"
            f"Input Commitments: {commitments_input}\n"
            f"Input Proof W: {proof_w_input}\n"
            f"F_left: {f_left}\n"
            f"F_right: {f_right}\n"
            f"Result: {'Verification successful!' if f_right == f_left else 'Verification failed!'}"
        )
        verifier.result_text.delete("1.0", tk.END)
        verifier.result_text.insert(tk.END, result)

    def get_verification_inputs(self, verifier):
        """获取证明和承诺."""
        dialog = tk.Toplevel(self)
        dialog.title(f"Verification Inputs for x={verifier.x}, y={verifier.y}")
        dialog.geometry("300x200")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="见证W的值:").pack()
        proof_w_entry = tk.Entry(dialog)
        proof_w_entry.pack()

        tk.Label(dialog, text=f"承诺值（以逗号分隔，共 {len(self.prover.coefficients)} 个值）：").pack()
        commitments_entry = tk.Entry(dialog)
        commitments_entry.pack()

        params = {}

        def on_submit():
            try:
                proof_w = int(proof_w_entry.get())
                commitments = list(map(int, commitments_entry.get().split(',')))
                if len(commitments) != len(self.prover.coefficients):
                    raise ValueError(f"Expected {len(self.prover.coefficients)} commitments, got {len(commitments)}")
                params['proof_w'] = proof_w
                params['commitments'] = commitments
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Input Error", str(e))

        tk.Button(dialog, text="Submit", command=on_submit).pack(pady=5)
        self.wait_window(dialog)
        return params if params else None

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()