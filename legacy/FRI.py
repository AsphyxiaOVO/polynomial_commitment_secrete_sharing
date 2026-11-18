def split_polynomial(coefficients):
    """
    将多项式分解为偶次幂之和和奇次幂之和
    参数:
        coefficients: 多项式系数列表，从低次幂到高次幂
    返回:
        even_terms: 偶次幂项的系数
        odd_terms: 奇次幂项的系数
    """
    even_terms = []
    for i in range(0, len(coefficients)):
        if i % 2 == 0:
            even_terms.append(coefficients[i])

    odd_terms = []
    for i in range(1, len(coefficients)):
        if i % 2 != 0:
            odd_terms.append(coefficients[i])

    # 补齐系数列表长度
    if len(odd_terms) < len(even_terms):
        odd_terms.append(0)

    print(f"[多项式分解] 原始多项式系数: {coefficients}")
    print(f"[多项式分解] 偶次幂系数: {even_terms}")
    print(f"[多项式分解] 奇次幂系数: {odd_terms}")

    return even_terms, odd_terms

def transform_to_y_polynomial(even_terms, odd_terms, a):
    """
    将分解后的多项式转换为以y(y=x^2)为底的形式
    参数:
        even_terms: 偶次幂项的系数
        odd_terms: 奇次幂项的系数
        a: 随机系数
    返回:
        y_polynomial: 以y为底的多项式系数
    """
    # 确保a为整数
    a = int(a)
    
    # 对于偶次幂项：x^(2n) = y^n
    y_from_even = [int(even_terms[i]) for i in range(len(even_terms))]
    
    # 对于奇次幂项：x^(2n+1) = x * y^n = a * y^n
    y_from_odd = [int(a * odd_terms[i]) for i in range(len(odd_terms))]
    
    # 合并同类项
    max_power = max(len(even_terms), len(odd_terms))
    y_polynomial = [0] * max_power
    for i in range(max_power):
        if i < len(even_terms):
            y_polynomial[i] += y_from_even[i]
        if i < len(odd_terms):
            y_polynomial[i] += y_from_odd[i]
    
    print(f"[转换结果] a = {a}")
    print(f"[转换结果] 以y为底的多项式系数: {y_polynomial[::-1]}")
    
    # 检查是否需要继续降幂
    if max_power > 5:
        print(f"\n[降幂检测] 当前最高次幂为 {max_power}，大于5，继续降幂处理")
        return reduce_power(y_polynomial)
    
    return y_polynomial

def reduce_power(polynomial):
    """
    对多项式进行降幂处理
    参数:
        polynomial: 多项式系数列表
    返回:
        reduced_polynomial: 降幂后的多项式系数列表
    """
    # 分解多项式
    even_terms, odd_terms = split_polynomial(polynomial)
    
    # 转换为y多项式（使用默认a=6）
    return transform_to_y_polynomial(even_terms, odd_terms, 6)

if __name__ == "__main__":
    import random
    
    # 获取用户输入的多项式系数
    print("\n=== 多项式系数输入 ===")
    print("请输入多项式的系数（从低次幂到高次幂，用空格分隔）")

    coefficients = [int(x) for x in input("请输入系数: ").strip().split()]
    # 多项式分解测试
    print("\n=== 多项式分解测试 ===")
    even_terms, odd_terms = split_polynomial(coefficients)
    
    # 从高到低打印原多项式
    print("原多项式: " + " + ".join([f"{coefficients[i]}x^{i}" for i in range(len(coefficients)-1, -1, -1)]))
    
    # 从高到低打印分解形式
    even_terms_str = " + ".join([f"{even_terms[i]}x^{2*i}" for i in range(len(even_terms)-1, -1, -1)])
    odd_terms_str = " + ".join([f"{odd_terms[i]}x^{2*i}" for i in range(len(odd_terms)-1, -1, -1)])
    print(f"分解形式: ({even_terms_str}) + ")
    print(f"          x({odd_terms_str})")
    
    # 转换为以y为底的多项式
    print("\n=== 转换为y多项式 ===")
    a = int(input("请输入系数a的值: "))

    y_polynomial = transform_to_y_polynomial(even_terms, odd_terms, a)
    
    # 从高到低打印最终多项式
    print(f"最终多项式: {' + '.join([f'{y_polynomial[i]}y^{i}' for i in range(len(y_polynomial)-1, -1, -1)])}")