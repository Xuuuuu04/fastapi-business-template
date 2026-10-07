"""
有限地读取外部响应。上限按实际解压后的字节计算，不相信 Content-Length。
超限时停止迭代，由调用方的响应上下文关闭连接。
"""

from collections.abc import AsyncIterator


# 外部响应超过声明上限，调用方按读取或写入场景整理失败。
class ResponseTooLarge(Exception):
    pass


# 累计读取分块数据，每块在进入缓冲前检查总量。
async def limited_bytes(chunks: AsyncIterator[bytes], maximum: int) -> bytes:
    parts = []
    size = 0
    async for chunk in chunks:
        size += len(chunk)
        if size > maximum:
            raise ResponseTooLarge()
        parts.append(chunk)
    return b"".join(parts)
