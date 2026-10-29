from collections.abc import AsyncIterator


class ResponseTooLarge(Exception):
    pass


async def limited_bytes(chunks: AsyncIterator[bytes], maximum: int) -> bytes:
    parts = []
    size = 0
    async for chunk in chunks:
        size += len(chunk)
        if size > maximum:
            raise ResponseTooLarge()
        parts.append(chunk)
    return b"".join(parts)
