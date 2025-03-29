# polynomial_commitment_based_secrete_sharing
2025年海南大学本科毕业设计《基于多项式承诺的可验证秘密分享》 :yum:

多项式承诺方案由《Efficient polynomial commitment schemes for multiple points and polynomials》[^1]
改进而来，信息使用utf_8编码，保留原方案基于多个评估点和多项式的批量验证优势，结合FRI折叠技术和秘密分片，构建一个安全高效的可验证秘密共享系统。 

## 创新点
1. 对于生成的多项式，采用FRI折叠来使多项式的次数保证在一个期望的区间内，确保承诺和证明的时间复杂度在同样在一个期望的区间内。
2. 为了增强秘密分享过程中的安全性，将需要分享的秘密分片到多个多项式进行分享。批量验证过程由Dan Boneh等人构建的多项式承诺方案高效进行。

[^1]: (https://eprint.iacr.org/2020/081)

### 运行示例
创建了两个带有ui交互界面的程序分别用来多项式承诺和秘密分享



