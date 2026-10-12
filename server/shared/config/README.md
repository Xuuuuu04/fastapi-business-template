# config：运行配置

[settings.py](settings.py) 读取以 `APP_` 开头的环境变量，示例见 `server/.env.example`。导入时不读环境，测试可以直接传入 `Settings(...)`。

`check_production()` 列出生产环境不允许的配置：必须用 PostgreSQL、不能开启开发者身份、运行记录必须保存到数据库、至少要有一把服务密钥、必须写入代码版本并设置独立的 JWT 密钥。不满足时服务拒绝启动。生产环境默认关闭 `/system/console`。
