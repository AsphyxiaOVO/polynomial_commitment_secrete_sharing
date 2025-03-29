def encode_message_to_constant(message: str) -> int:
    return int.from_bytes(message.encode('utf-8'), byteorder='big')

def decode_constant_to_message(constant: int) -> str:
    byte_length = (constant.bit_length() + 7) // 8
    return constant.to_bytes(byte_length, byteorder='big').decode('utf-8')


def split_integer_to_polynomials(number: int, num_polynomials: int) -> tuple[list[int], int]:
    # 计算整数的位数
    num_digits = len(str(number))

    # 计算每个多项式分配的位数
    digits_per_polynomial = num_digits // num_polynomials
    remainder = num_digits % num_polynomials  # 剩余的位数

    # 如果余数不为0，补0直至整除
    if remainder != 0:
        padding_zeros = num_polynomials - remainder     #计算需要补多少个0
        number_str = str(number) + '0' * padding_zeros
    else:
        number_str = str(number)
        padding_zeros= 0

    # 更新位数
    num_digits = len(number_str)
    digits_per_polynomial = num_digits // num_polynomials

    # 初始化结果数组
    result = []
    start = 0

    # 分配位数
    for i in range(num_polynomials):
        # 截取对应的位数
        end = start + digits_per_polynomial
        substring = number_str[start:end]
        result.append(int(substring))

        # 更新起始位置
        start = end

    return result, padding_zeros


def merge_polynomials_to_integer(polynomials: list[int],padding_zeros) -> int:
    # 找到数组中最长的位数
    max_digits = max(len(str(poly)) for poly in polynomials)

    # 将每个多项式补0到最长的位数
    padded_polynomials = [str(poly).zfill(max_digits) for poly in polynomials]

    # 拼接所有多项式
    number_str = ''.join(padded_polynomials)

    # 去掉末尾的0（如果有补0）
    if padding_zeros > 0 :
        number_str = number_str[:-padding_zeros]
    else :
        number_str=number_str

    # 如果去掉末尾的0后字符串为空，说明原始数是0
    if not number_str:
        return 0

    # 将字符串转换为整数
    return int(number_str)


# # 使用示例
# encoded = encode_message_to_constant("Hello世界0")
# print("编码后的常数:", encoded)  # 输出：254907620303045258386675
#
# decoded = decode_constant_to_message(encoded)
# print("解码后的消息:", decoded)  # 输出：Hello世界
#
# # 示例 1
# number = 140052000
# num_polynomials = 2
# result = split_integer_to_polynomials(number, num_polynomials)
# print(result)  # 输出：[14, 52]
#
# # 示例 2
# number = 123456
# num_polynomials = 4
# result = split_integer_to_polynomials(number, num_polynomials)
# print(result)  # 输出：[12, 34, 56, 00]
#
# # 示例 3
# number = 987654321
# num_polynomials = 3
# result = split_integer_to_polynomials(number, num_polynomials)
# print(result)  # 输出：[98, 76, 54, 32, 10]
#
# polynomials=[14005,20000]
# merged_number = merge_polynomials_to_integer(polynomials,1)
# print("合并后的整数:", merged_number)  # 输出：110203