# 业务服务层

[notes](notes/README.md) 是已经实现的笔记示例，展示数据定义、业务规则、存储约定与 SQLite 实现。

operations 和 data 保留原有结构说明，尚无业务代码。业务不依赖 HTTP；SQL 集中在具体功能的 store，事务范围由 service.py 决定。
