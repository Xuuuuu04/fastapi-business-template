# $title（$name）

## 用途

最小账号登录：按组织代码、账号和口令登录，换取访问令牌；有管理权限的调用者可以新建账号。角色、停用、改口令、刷新令牌和两步验证都不在这里，产品需要时自己加。

## 公开操作

| 操作 | 用途 | 权限 |
| --- | --- | --- |
| $name.login | 核对组织代码、账号和口令，返回登录账号 | public |
| $name.create_account | 新建账号，授予不超出自己的权限 | $name.manage |

## 依赖

不调用其他模块。访问令牌由接口层用 `shared/access/tokens.py` 的 `issue_token` 签发，权限写法与 `Caller` 一致。

## 内部组织

- `module.json`：生成器提供的标准结构说明，不能自行扩展允许的文件范围。
- `data.py`：公开数据、流程数据、业务错误。
- `flow.py`：每个操作的步骤顺序。
- `steps/`：`sign_in.py` 登录，`accounts.py` 新建账号，`passwords.py` 口令计算。
- `store/`：`contract.py` 声明需要的读写，`sql.py` 是数据库实现，`tables.py` 定义账号表。
- 接口在 `app/api/v1/$name.py`，路径固定为 `/api/v1/access`，登录失败限流也在那里。

## 测试

- `tests/modules/$name/`：口令计算和授权范围的步骤测试。
- `tests/integration/$name/`：从 HTTP 接口新建账号、登录、限流和权限检查。
