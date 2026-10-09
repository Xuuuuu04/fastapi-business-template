# 端到端演练

`operations drill 配置.json --output 结果目录` 在新SQLite文件或新PostgreSQL schema里按实际Schedule首入口运行整条Pipeline。普通产品运行不变化；测试样例在tests/framework，不登记预置业务。

配置包含pipeline、org_id、scale、timeout_seconds和replay。replay按远程系统列method/path/params/file/status/headers，file是清单目录内的原件，可填sha256固定来源。未覆盖请求失败，所有已声明远程系统都使用本地回放，没有真实网络。大数据可用seed的table/file JSONL按5000行导入已登记业务表。

输出report.json含各阶段状态/总历时/运行号/已确认行数或未知、SQL形状/表/位置的最慢五条、RSS采样峰值、是否需要人工操作。保留文件产物到artifacts。回放覆盖来自实际调用，未执行阶段明确未覆盖；scale只是请求规模，不能据此声称处理了这么多行。

PostgreSQL连接只创建本任务随机schema，搜索路径不含public，退出仅删除该schema。SQLite总是临时新文件。演练不继承.env、真实密钥、旧库或真实模型配置。

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

seed可省略；写外部系统也只能回放已确认响应，不能证明真实发布成功。涉及业务数据和产物的目录不要提交Git。

内部：isolation隔离，replay原件传输，app/setup/drill入口和协调，metrics实际证据。模拟模型结果与create_all建表不证明真实模型、迁移或恢复；这些需要另行验证。

每阶段query_budgets列各次运行额度、实际SQL次数/行数/返回大小、未知数量及存储函数重复提示。显式额度测试默认失败；旧操作默认仅警告。可在演练环境设置APP_QUERY_BUDGET_MODE=warn或APP_QUERY_BUDGET_EXPLAIN=true，生产不会附计划。大小含义与迁移见[数据库](../db/README.md)。
