# 统一错误

handlers.py 将业务错误、参数校验、未知路由和内部错误转换为 code、message、request_id、details。状态码保留真实含义，不将失败返回为 200。

校验错误不回传原始输入；内部日志记录异常类别和请求编号，不记录密钥或原始 SQL。
