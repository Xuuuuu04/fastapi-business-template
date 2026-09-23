"""
对本机查询接口施加有界并发负载。
只读取笔记，输出响应耗时和失败率，不用于生产容量承诺。
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


# 请求本机接口并返回耗时与成功标记。
def request(port: int) -> tuple[float, bool]:
    start = perf_counter()
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/v1/notes?limit=1", timeout=5) as reply:
            reply.read()
            success = reply.status == 200
    except (HTTPError, URLError, TimeoutError):
        success = False
    return (perf_counter() - start) * 1000, success


# 按显式指定的并发和请求数执行本机负载检查。
def main() -> None:
    parser = argparse.ArgumentParser(description="本机只读负载检查")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.count <= 10000 or not 1 <= args.workers <= 32:
        parser.error("请求数须为 1 至 10000，并发数须为 1 至 32")
    if not 1 <= args.port <= 65535:
        parser.error("端口须为 1 至 65535")
    start = perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(request, [args.port] * args.count))
    elapsed = perf_counter() - start
    times = sorted(duration for duration, success in results)
    failed = sum(not success for duration, success in results)
    print(
        json.dumps(
            {
                "requests": args.count,
                "workers": args.workers,
                "failed": failed,
                "failure_rate": failed / args.count,
                "requests_per_second": args.count / elapsed,
                "p50_ms": median(times),
                "p95_ms": times[max(0, (len(times) * 95 + 99) // 100 - 1)],
                "max_ms": max(times),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
