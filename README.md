# polynomial_commitment_based_secrete_sharing
2025年海南大学本科毕业设计《基于多项式承诺的可验证秘密分享》 :yum:

多项式承诺方案由《Efficient polynomial commitment schemes for multiple points and polynomials》[^1]
改进而来，信息使用utf_8编码，保留原方案基于多个评估点和多项式的批量验证优势，结合FRI折叠技术和秘密分片，构建一个安全高效的可验证秘密共享系统。 :v:   

The polynomial commitment scheme is improved from "Efficient polynomial commitment schemes for multiple points and polynomials". The information is encoded using utf_8, retaining the advantages of the original scheme based on batch verification of multiple evaluation points and polynomials, and combining FRI folding technology and secret sharding to build a secure and efficient verifiable secret sharing system  :fire:

## 创新点
1. 对于生成的多项式，采用FRI折叠来使多项式的次数保证在一个期望的区间内，确保承诺和证明的时间复杂度在同样在一个期望的区间内。
   For the generated polynomial, FRI folding is used to ensure that the degree of the polynomial is within an expected interval, ensuring that the time complexity of commitment and proof is also within an expected interval. :dog: :service_dog:	
3. 为了增强秘密分享过程中的安全性，将需要分享的秘密分片到多个多项式进行分享。批量验证过程由Dan Boneh等人构建的多项式承诺方案高效进行。
   In order to enhance the security of secret sharing, the secret to be shared is sharded into multiple polynomials for sharing. The batch verification process is efficiently carried out by the polynomial commitment scheme constructed by Dan Boneh et al. :heart_on_fire: :yellow_heart: :blue_heart:  

[^1]: (https://eprint.iacr.org/2020/081)

## 运行示例
:bento:创建了两个带有ui交互界面的程序分别用来多项式承诺和秘密分享  
Created two programs with UI interactive interfaces for polynomial commitment and secret sharing respectively

:framed_picture:承诺过程的ui和验证结果  
![commitment ui](https://github.com/user-attachments/assets/f24fd1a5-7914-4c17-8add-90a693a6427d)
![verification](https://github.com/user-attachments/assets/baeed7db-2b87-4892-8a7d-6bb0114a3d92)  
:framed_picture:恢复的ui和结果  
![recovery ui](https://github.com/user-attachments/assets/35dd2ed6-f76c-4dcd-b96e-3b79b9ae8090)

## end
大学该画上句号了，四年来在性格上成长了很多，感谢海南大学和遇到的每一个人，在新的人生阶段中要像歌词一样啊

:musical_note: _夢が迎えに来てくれるまで  
震えて待ってるだけだった昨日  
明日僕は龍の足元へ  
崖を登り  
呼ぶよ「さあ、行こうぜ」  
銀の龍の背に乗って  
届けに行こう 命の砂漠へ  
銀の龍の背に乗って  
運んで行こう 雨雲の渦を_:musical_note:

出发吧！不管去到哪里！保持温柔缓慢而坚定地前进 :muscle: :muscle:

01:52 2025年3月30日（星期日） (GMT+8)






