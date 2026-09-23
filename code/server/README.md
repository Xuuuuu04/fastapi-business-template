# FastAPI 单体后端模板

## 1. 初版已实现

这是一个单进程即可运行的单体后端。已删除外部调用层，示例业务使用本地 SQLite，不需要额外启动数据库。

已实现：笔记增删改查、分页、事务、统一错误、写入密钥检查、请求日志、跨域配置、健康检查、在线 API 文档、离线 JSON 与中文文档导出、接口版本比较。

账号角色、后台任务、通知、文件存储和正式部署仍是设计位置，尚未实现。读取笔记是公开的；写入密钥只用于本地体验，不是完整用户系统。

## 2. 启动

在 code/server 目录执行：

```bash
uv sync --locked
cp .env.example .env
uv run python -m shared.db.migrate
uv run uvicorn app.setup.app:create_app --factory --host 127.0.0.1 --port 8000 --reload --no-access-log
```

.env 中的 APP_WRITE_KEY 是本地示例值，使用前修改。数据库默认保存到 var/app.db。启动不会自动修改表结构，迁移命令可重复执行且不会清空笔记。

打开 http://127.0.0.1:8000/docs。先调用查询接口，再点击 Authorize 填入 .env 中的密钥，尝试创建、修改和删除。标题去除首尾空白后不能重复，正文允许为空。

## 3. 目录与阅读顺序

```text
server/
├── app/               接口与应用组装
│   ├── api/           路由、文档、错误、权限、响应与健康检查
│   └── setup/         创建应用、请求级服务组装、生命周期
├── service/           业务服务
│   ├── notes/         已实现的笔记示例
│   ├── operations/    保留的运营报表设计，尚未实现
│   └── data/          跨业务数据定义的设计位置
├── shared/            配置、数据库、日志、登录等公共能力
├── deploy/            当前提供本地运行说明，生产脚本待设计
├── tests/             接口、事务、文档和代码规范检查
└── docs/              架构、实现范围和审查说明
```

建议按以下顺序读一条完整业务：

1. [接口](app/api/routes/notes/routes.py)：接收什么、返回什么。
2. [业务](service/notes/service.py)：检查规则、安排事务。
3. [操作约定](service/notes/needs.py)：业务需要存储提供什么。
4. [存储](service/notes/store/sqlite.py)：查询和保存怎样实现。
5. [组装](app/setup/build.py)：每个请求怎样取得独立服务与连接。

## 4. API 文档

```bash
uv run python -m app.api.docs.export
uv run python -m app.api.docs.compare --before out/old/openapi.json --after out/api/openapi.json
```

第一条命令生成 [中文接口清单](out/api/index.md) 和 [OpenAPI JSON](out/api/openapi.json)，不启动服务、不连接数据库。第二条需要自行提供旧版本文档。比较只提示声明与模型变化，不保证识别全部不兼容行为。

在线入口：/docs、/redoc、/openapi.json。设置 APP_DOCS=false 可关闭在线文档，离线导出仍可用。

## 5. 开发检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

测试使用临时数据库，覆盖正常操作、无权写入、重复标题、非法参数、回滚、重启读取、未初始化状态和文档导出。

本次实际检查结果见[初版验证记录](docs/初版验证记录.md)。启动命令关闭 Uvicorn 默认访问日志，由应用记录路由模板，避免默认日志带出查询参数。

## 6. 代码风格

目录和模块使用小写英文，多词用下划线。Python 类使用大驼峰命名，变量使用简短完整单词，避免无含义的单字母。

每个 Python 文件以多行中文说明开头；每个函数在定义或装饰器前有单行中文说明。相似操作放在同一段，格式由 Ruff 统一。README.md 等标准文件名保留。

当前 SQLite 迁移只支持初始版本，未验证生产并发、正式账号权限或生产部署。下一轮请重点检查业务分包、函数长度、注释和实际接口体验。
