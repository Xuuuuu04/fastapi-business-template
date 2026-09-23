"""
设置模板自身的日志格式。
不修改第三方日志，不记录请求正文和密钥。
"""

import logging


# 为服务日志设置一个独立输出处理器。
def configure() -> None:
    log = logging.getLogger("server")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
