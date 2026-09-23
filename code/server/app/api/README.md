# HTTP 接口

已实现笔记 routes、文档 docs、错误 errors、分页 replies、写入检查 access、请求日志 checks、运行检查 health。limits 仍为按需设计。

接口响应由类型定义，文档从同一应用生成；业务错误统一映射，意外异常只返回简短说明。实现入口见各目录中的 Python 文件。
