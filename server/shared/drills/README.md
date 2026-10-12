# 端到端演练

`operations drill 配置.json --output 结果目录` 在新的 SQLite 文件或新的 PostgreSQL schema 里，按实际的 Schedule 首入口运行整条 Pipeline。普通产品的运行不受影响；测试样例在 tests/framework，不登记预置业务。

配置包含 pipeline、org_id、scale、timeout_seconds 和 replay。replay 按远程系统列出 method/path/params/file/status/headers；file 是清单目录里的原件，可以填 sha256 固定来源。回放没有覆盖到的请求会失败；所有已声明的远程系统都用本地回放，没有真实网络。大数据可以用 seed 的 table/file JSONL，按每 5000 行导入已登记的业务表。

输出的 report.json 包含：各阶段的状态、总历时、运行号、已确认的行数（或未知）；最慢的五条 SQL 的形状、表和位置；采样的内存峰值（RSS）；是否需要人工操作。文件产物保留在 artifacts 里。回放覆盖情况来自实际调用，没有执行的阶段会明确标注未覆盖；scale 只是请求的规模，不能据此声称处理了那么多行。

PostgreSQL 的连接只为本次任务创建随机 schema，搜索路径不含 public，退出时只删除这个 schema。SQLite 总是临时的新文件。演练不继承 .env、真实密钥、旧库或真实模型配置。

配置示例（pipeline必须已经在module.py声明，scale不会覆盖正式Schedule的输入，真实规模由Schedule输入或seed决定）：

```json
{
  "pipeline": "report.daily",
  "org_id": "drill",
  "scale": 100000,
  "timeout_seconds": 300,
  "seed": [{"table": "report_sources", "file": "sources.jsonl"}],
  "replay": {
    "upstream": [{
      "method": "GET", "path": "/orders", "params": {"day": "2026-10-08"},
      "file": "orders-original.json", "sha256": "原件的SHA256摘要",
      "status": 200, "headers": {"content-type": "application/json"}
    }]
  }
}
```

也可用 `{"endpoint": "upstream.query", "file": "original.json"}` 按Endpoint名回放；
可选method/path/params仍会核对，使用记录包含接口名。旧清单的精确匹配行为不变。

seed 可以省略。演练里写外部系统也只能回放已确认的响应，不能证明真实发布成功。涉及业务数据和产物的目录不要提交 Git。

内部实现：isolation 负责隔离，replay 负责原件传输，app/setup/drill 是入口和协调，metrics 收集实际证据。模拟的模型结果和 create_all 建表不能证明真实模型、真实迁移或恢复能力；这些需要另行验证。

每阶段query_budgets列各次运行额度、实际SQL次数/行数/返回大小、未知数量及存储函数重复提示。显式额度测试默认失败；旧操作默认仅警告。可在演练环境设置APP_QUERY_BUDGET_MODE=warn或APP_QUERY_BUDGET_EXPLAIN=true，生产不会附计划。大小含义与迁移见[数据库](../db/README.md)。
