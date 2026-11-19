import numpy as np
from sympy import Matrix


def fit_polynomial(points, field):
    # 提取点的 x 和 y 坐标
    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]

    # 多项式的次数为点的数量减一
    degree = len(points) - 1

    # 创建范德蒙德矩阵并对有限域取模
    matrix = np.vander(x_coords, degree + 1) % field

    # 转换为 SymPy 矩阵以进行有限域操作
    A = Matrix(matrix)
    b = Matrix(y_coords)

    # 计算 A 的逆矩阵取模 field 并求解系数
    A_inv = A.inv_mod(field)
    coefficients = (A_inv * b).applyfunc(lambda x: x % field)

    # 转换为 NumPy 数组并返回普通的 Python 列表
    return np.array(coefficients).astype(int).flatten().tolist()


# # 使用示例
# points = [(1, 10), (2, 8),(3,11)]  # 示例点集 (x1, y1), (x2, y2)
# field = 13
# coefficients = fit_polynomial(points, field)
# print(coefficients)
