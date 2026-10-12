
## 规则账本

`dev rules source`登记脱敏来源，原文用`--raw-file`保存在本机`.agents/records/business-raw`，不会写进账本。`propose`先记为推定，`adopt`记录采纳，`confirm`必须提供来源、修订、确认种类和依据，`retire`保留废止历史。修改确认文本会新建修订并恢复为推定；历史代码、文档和合成fixture不会自动成为人类确认。

`doc/rules-ledger.json`是可提交事实；本机SQLite锁只协调读改写，并不是唯一证据。文件摘要用于发现变化，不验证确认人的真实身份。请先脱敏摘要和引用，风险按业务影响声明，不把所有数字统一列为高风险。
