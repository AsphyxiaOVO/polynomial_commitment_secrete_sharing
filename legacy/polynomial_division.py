def polynomial_to_string(coefficients):
    terms = []
    degree = len(coefficients) - 1
    for i, coeff in enumerate(coefficients):
        if coeff != 0:
            if i == degree:
                terms.append(f"{coeff}")
            elif i == degree - 1:
                terms.append(f"{coeff}x")
            else:
                terms.append(f"{coeff}x^{degree - i}")
    return " + ".join(terms)

def polynomial_division(dividend, divisor, field):    #输入从高次到低次
    # 获取多项式的次数
    m = len(dividend) - 1
    n = len(divisor) - 1

    # 初始化商和余数
    quotient = [0] * (m - n + 1)
    remainder = dividend[:]

    # 多项式除法
    for k in range(m - n + 1):
        quotient[k] = (remainder[k] * pow(divisor[0], -1, field)) % field
        for j in range(n + 1):
            remainder[k + j] = (remainder[k + j] - quotient[k] * divisor[j]) % field

    # 移除余数中的前导零
    while remainder and remainder[0] == 0:
        remainder.pop(0)

    return quotient, remainder                 #输出从高次到低次

def evaluate_polynomial(coefficients, x, field):
    result = 0
    degree = len(coefficients) - 1
    for i, c in enumerate(coefficients):
        result += c * (x ** (degree - i))
    return result % field

# 示例使用
if __name__ == "__main__":
    field = 13  # 有限域 F13
    dividend = [1, 2, 0, 10]  # 被除多项式，从高次到低次
    divisor = [1, -3, 2]  # 除数多项式，从高次到低次

    # 计算多项式的商和余数
    quotient, remainder = polynomial_division(dividend, divisor, field)

    # 打印被除多项式、除数多项式、商和余数
    print("被除多项式: ", polynomial_to_string(dividend))
    print("除数多项式: ", polynomial_to_string(divisor))
    print("商: ", polynomial_to_string(quotient))
    print("余数: ", polynomial_to_string(remainder))
