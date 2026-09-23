# load：压力测试

需要先启动服务。只用于比较改动前后的变化，结果不能当作生产容量承诺；正式评估要在目标机器、真实数据量和 PostgreSQL 上进行。

```bash
uv run python -m tests.load.run --port 8000 --key 服务密钥 --count 500 --workers 20
uv run python -m tests.load.run --port 8000 --path /health/live --count 1000 --workers 50
```

输出请求数、失败数、每秒请求数、p50、p95 和最大耗时。有失败时返回非零。
