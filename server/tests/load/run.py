"""
对本机已启动的服务施加有界的并发压力，输出响应耗时和失败率。
只用于比较改动前后的变化，结果不能当作生产容量承诺。
用法：uv run python -m tests.load.run --port 8000 --key 服务密钥 --count 500 --workers 20
"""

import argparse
import asyncio
import json
import time
from statistics import median

import httpx2


# 发送一个请求，返回耗时（毫秒）和是否成功。
async def hit(
    client: httpx2.AsyncClient, path: str, limit: asyncio.Semaphore
) -> tuple[float, bool]:
    async with limit:
        started = time.perf_counter()
        try:
            reply = await client.get(path)
            passed = reply.status_code == 200
        except httpx2.HTTPError:
            passed = False
        return (time.perf_counter() - started) * 1000, passed


# 按指定并发发送请求并汇总结果。
async def measure(port: int, key: str, path: str, count: int, workers: int) -> dict[str, float]:
    headers = {"X-API-Key": key} if key else {}
    limit = asyncio.Semaphore(workers)
    async with httpx2.AsyncClient(
        base_url=f"http://127.0.0.1:{port}", headers=headers, timeout=10
    ) as client:
        started = time.perf_counter()
        results = await asyncio.gather(*(hit(client, path, limit) for _ in range(count)))
        elapsed = time.perf_counter() - started
    times = sorted(duration for duration, _ in results)
    failed = sum(not passed for _, passed in results)
    return {
        "requests": count,
        "workers": workers,
        "failed": failed,
        "requests_per_second": round(count / elapsed, 1),
        "p50_ms": round(median(times), 1),
        "p95_ms": round(times[max(0, int(len(times) * 0.95) - 1)], 1),
        "max_ms": round(times[-1], 1),
    }


# 解析参数并输出结果；有失败时返回非零。
def main() -> None:
    parser = argparse.ArgumentParser(description="本机压力检查")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--key", default="", help="服务密钥；只测 /health/live 时可以不填")
    parser.add_argument("--path", default="/api/v1/products?limit=20")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    if not (1 <= args.count <= 20000 and 1 <= args.workers <= 200):
        parser.error("请求数须在 1 到 20000 之间，并发数须在 1 到 200 之间")
    result = asyncio.run(measure(args.port, args.key, args.path, args.count, args.workers))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["failed"] else 0)


if __name__ == "__main__":
    main()
