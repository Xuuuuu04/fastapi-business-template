# 框架用法

业务包只从 `shared.public` 导入框架；测试工具（`try_step`、`capture`、`simulate`、`FakeClock` 等）从 `shared.flow.testing` 导入；产品组装用的 `ApplicationSpec` 和适配器在 `app/product.py` 里从各自的模块导入。只导入别的包的 `public.py` 和 `library.工具包.public`；不导入 fastapi、httpx 等 HTTP 库，SQLAlchemy 只在 `store/` 里用。违反时启动和检查都会报错。模板没有预置业务包，每节末尾列出的 `server/tests/framework/` 下的文件就是完整可运行的例子。

路由文件在 `app/api/v1/包名.py`，接口多时拆成 `包名_主题.py`，拆出来的 router 要加进 `app/api/routers.py` 的 `MODULE_ROUTERS`。删除类接口写 `@router.delete(..., status_code=204)`，函数返回 `None`。路由只做参数转换并 `await run(操作, 输入)`，可以用 `app.api.runner` 的 `RunDep`、`FailureLimit` 和 `app.api.replies` 的 `responses_for`。

## 声明

`Data` 用于输入、输出和包之间传递的数据，创建后不能修改，不接受多余字段。`WorkData` 是一次流程用到和产生的全部字段，由步骤按声明读写。分页结果用 `Page[条目]` 或 `CursorPage[条目]`，空结果用 `Nothing`。

```python
class QuoteInput(Data):
    sku: str = meaning("商品编号", min_length=1, max_length=40)
    amount: Decimal = meaning("下单金额", unit="元", gt=0)
    note: str | None = meaning("备注", empty="调用方没有填写", default=None)
```

- 每个字段写 `meaning()`；类型允许 None 的字段必须写 `empty=`。启动时逐个字段检查。
- 金额用 `Decimal`，步骤写入浮点数会被拒绝。运行记录默认只记数量和长度，`log_value=True` 才记取值，`secret=True` 从不记录。
- 不用没有元素类型的 `dict`、`list`、`Any`。确实要收原始结构时，把那个 Data 列进 `Module(boundary_data=(...))`。

操作写在 public.py：

```python
create_quote = contract(
    "quote.create_quote",
    "生成报价",
    input=QuoteInput,
    output=QuoteView,
    access="quote.write",
    effect="command",
    errors=(QuoteInvalid,),
)
```

- 名称是 `包名.动作`；`access` 只能是 `public`、`signed_in` 或以本包名开头的权限。
- `effect` 必须写。`"query"` 操作的步骤不能保存、不能登记任务、不能调写入类上游接口，也不能调用 command 操作。
- 可选：`entry=False`（内部操作，只给本包或别的操作调用，不需要 HTTP 或后台入口）、`timeout`（秒，默认 30）、`audit=True`（写操作记录）、`stream=True`、`query_budget`、`aliases`（业务别名和旧路径，供 `dev locate` 检索）。

步骤和流程写在 steps/ 和 flow.py：

```python
@step("保存报价", reads=["sku", "total"], writes=["result"], saves=True)
async def save_quote(data: QuoteWork, store: QuoteStore, clock: Clock) -> None:
    data.result = await store.add(data.sku, data.total, clock.now())


quote_flow = Flow("生成报价", work=QuoteWork, result="result", steps=[count_total, save_quote])
```

步骤靠参数名拿到工具：

| 参数名 | 拿到什么 | 需要的声明 |
| --- | --- | --- |
| `data` | 流程数据，只能读写 reads/writes 里的字段 | 都有 |
| `store` | 本包存储实现 | 写库加 `saves=True` |
| `call` | `await call(操作, 输入)` 同步调用别的操作 | `uses=[操作]` |
| `later` | 登记后台任务，返回任务编号 | `later=[操作]`、`saves=True` |
| `model`、`remote`、`effects` | 大模型、外部接口、持久外部效果 | `prompts`、`remotes` 与 `endpoints`、`providers` |
| `caller`、`cache`、`clock`、`note`、`emit`、`checkpoint`、`pipeline` | 调用者、缓存、时钟、写说明、流式输出、分段提交点、多阶段流程 | 见各节 |

- `store`、`call`、`model`、`remote`、`effects` 一个步骤里最多出现一个。
- 没有 `saves=True` 的步骤拿到只读连接。第一个保存步骤开始写事务，整个操作成功才提交，任何一步失败都回滚。写事务开始后不能再调大模型或外部接口，所以顺序是先读、再调外部、最后保存。
- 一个流程最多 12 步。操作输入的每个字段要在 WorkData 里同名同类型出现，`result` 字段类型必须是操作的输出。
- 条件用 `@condition("是会员", reads=["vip"])` 写一个返回 bool 的函数，步骤用 `when=条件` 引用。
- 步骤不 return，结果写到 `data` 上。要等待的写 `async def`；耗时的同步纯计算加 `heavy=True`，只能有 `data` 参数，必须自己有限结束。
- 生成器的样例步骤带 `placeholder=True`；`simulated=True` 的模拟骨架只能在测试里配合 `simulate()` 跑。两者都过不了 `dev check --delivery`。

模块写在 module.py：

```python
module = Module(
    name="quote",
    title="报价",
    version="1",
    kind="capability",
    provides={public.create_quote: flow.quote_flow},
    store=SqlQuoteStore,
    tables=(quotes,),
    read_dependencies=("price",),
)
```

- 流程包（workflow）不能有表。能力包跨包只能调对方的 query 操作，并在 `read_dependencies` 写明对方包名；跨包写入放到流程包。
- 按需登记 `remotes`、`endpoints`、`prompts`、`jobs`、`schedules`、`pipelines`、`providers`、`aliases`。步骤用到而模块没登记的，启动时报错。
- 改规则或数据格式时升级 `version`；已排队的旧版本任务会停下，处理方法见 fastapi-operations。

单独测一个步骤用 `shared.flow.testing` 的 `try_step(步骤, Work类, 字段=值)`，异步步骤用 `try_step_async`。例子：`sample_modules.py`、`test_step_rules.py`、`test_injection.py`、`test_package_policy.py`。

## 存储

SQL 只写在 `store/`：`contract.py` 用 Protocol 声明方法和返回的 Data，`sql.py` 实现，`tables.py` 用 `metadata` 定义表。表名以包名开头，时间列用 `UtcTime()`，金额列用 `ExactNumber(18, 2)`，按组织隔离的表加 `org_column()`，按负责人隔离加 `owner_column(see_all="权限名")`。存储构造参数只能用这些名字：`db`、`legacy`（旧系统只读库）、`remote`、`files`、`cache`、`caller`、`vault`。存储要抛的业务错误（比如下面的 `QuoteExists`）定义在 `store/contract.py`，因为 store 不能导入本包的 `data.py`。

```python
class SqlQuoteStore:
    def __init__(self, db: Db, caller: Caller) -> None:
        self.db, self.caller = db, caller

    async def add(self, sku: str, total: Decimal, now: float) -> QuoteView:
        values = {
            "org_id": self.caller.org_id,
            "sku": sku,
            "total": total,
            "created_at": datetime.fromtimestamp(now, UTC),
        }
        return view_of(
            await self.db.one(
                insert(quotes).values(**values).returning(quotes), conflict=QuoteExists()
            )
        )
```

| `Db` 方法 | 用途 |
| --- | --- |
| `all`、`first`、`one`、`scalar` | 读多行、首行、正好一行、单个值 |
| `change(语句, conflict=错误())` | 写入并返回行数；`one` 也接受 `conflict`，只把唯一约束冲突换成这个业务错误 |
| `change_or_fail(语句, 错误())` | 带条件修改，一行都没改到就抛这个错误 |
| `first_for_update`、`all_for_update` | 在保存步骤里加锁读取 |
| `insert_many(表, 行列表)` | 一条 SQL 批量插入，最多 100 行，各行字段相同 |
| `page_after(查询, 唯一可排序列, after, limit)` | 按位置续读，返回 `(行, 下一页 after)`，由存储包成 `CursorPage` |
| `update_tracked(表, 条件, 值)` | 修改并写变更历史，查询用 `/api/system/changes`（目前没有测试样例） |

- 用 SQLAlchemy Core，不用 ORM，不能执行原始 SQL 文本。
- 带 `org_column()` 的表，每一层查询（子查询、别名、更新关联的表）都要写 `表.c.org_id == caller.org_id`。只认 `列 == 值`，`in_`、`or_` 里缺条件或无法判断的语句会被拒绝。`owner_column` 同理，没有 see_all 权限的调用者每层写 `owner_id == caller.id`。
- 按读到的值决定写入（扣库存、状态流转）时，在保存步骤里 `first_for_update`，或用 `change_or_fail(update(...).where(表.c.状态 == 读到的状态), 错误())`。不要在只读步骤读、再在保存步骤无条件写。
- 查询额度：contract 写 `query_budget=QueryBudget(queries=20, rows=5000, bytes=64000, repeated=20)`。没写的用默认值（1000 次、100000 行、64000000 字节、同一函数 100 次）。测试环境超额就失败并回滚，其他环境只记录。
- 新增表的迁移步骤见 SKILL.md“生成命令”。只保留不修改的外部表登记在 `Module(external_tables=...)`，产品维护但已不在代码里的历史表登记在 `owned_tables`。旧系统的表定义放 `server/legacy/`，用 `legacy.schema` 的 `legacy_metadata`，不进迁移；存储构造参数写 `legacy` 拿到 `APP_LEGACY_DATABASE_URL` 的只读入口。

例子：`test_conditional_change.py`、`test_bulk_insert.py`、`test_owner_scope.py`、`test_common_services.py`、`query_budget_sample.py`、`test_legacy_database.py`。

## 错误

```python
class QuoteInvalid(BusinessError):
    code = "quote_invalid"
    kind = Kind.INVALID
    message = "金额必须大于零"
```

种类和状态码：`INVALID` 422，`NOT_FOUND` 404，`CONFLICT` 409，`NOT_SIGNED_IN` 401，`FORBIDDEN` 403，`TOO_MANY` 429，`TEMPORARY` 503，`TIMEOUT` 504，`UNKNOWN_RESULT` 502，`BROKEN` 500。后台任务只对 `TEMPORARY` 和 `TIMEOUT` 按 Retry 重试。

- 抛出时可带说明和字段：`raise QuoteInvalid(f"商品 {sku} 金额为 0", fields={"amount": "必须大于零"})`。
- 程序按 `code` 判断，不按说明文字判断。contract 的 `errors` 列出会抛的业务错误，接口文档据此生成。
- 意外异常只记录类型和出错位置，不记录消息。各类问题怎么处理见 SKILL.md 的“出错怎么办”。

## 后台任务

登记任务：步骤里声明 `later=[操作]` 和 `saves=True`，`await later(操作, 输入, key=幂等键)`，任务和业务写入同一事务提交；路由里 `return await run.later(操作, 输入, key=幂等键)`，返回带 `status_url` 的受理结果。同一个 key 只受理一次。被当作任务执行的操作都要在 module.py 的 `jobs` 里有 JobPlan：

| JobPlan 参数 | 含义 |
| --- | --- |
| `retry=Retry(3, (10, 60, 300))` | 暂时故障和超时的重试次数与每次等待秒数；不写就不重试 |
| `repeat_safe=True` | 期限过期后自动重排；必须来自真实的幂等规则，不因为任务短就写 |
| `max_queued`、`lease_seconds` | 排队上限（1000）、租约秒数（60） |
| `serial=SerialKey("conversation", "session_id")` | 同组织同业务键的任务跨 worker 串行 |
| `resources=(ResourceLimit("model", concurrency=4, cooldown=10),)` | 跨 worker 的并发位置和执行间隔 |
| `queue_timeout`、`attempt_timeout`、`valid_until_field` | 排队预算、单次尝试预算、输入里的有效期字段 |
| `revalidate=查询操作` | 执行前用同一输入调这个 query 操作（输出 `Validity`）核对身份或状态 |

定时：`Schedule("daily", "每日汇总", public.summarize, SummaryInput(), daily_at=time(2, 0))`，或 `every=timedelta(...)`。时区默认 `Asia/Shanghai`，用 `zone=` 改。`org_ids=("alpha",)` 限定组织，`org_ids=()` 是只跑一次的全局任务，不写就用 `APP_SCHEDULE_ORG_IDS`；`slot_input_field="字段路径"` 把实际时段写进输入。

分段提交用于固定范围的大批数据，每批独立提交。JobPlan 写 `segmented=True, repeat_safe=True, cursor=游标Data`，读取步骤从 `checkpoint.cursor.get("after", 0)` 取起点，最后一个步骤声明提交点：

```python
@step("声明本批提交点", reads=["start", "end", "total"])
def commit_batch(data: BatchWork, checkpoint: Checkpoint) -> None:
    if data.end == data.total:
        checkpoint.finish(rows=data.end - data.start, cursor={"after": data.end})
    else:
        checkpoint.advance({"after": data.end}, rows=data.end - data.start)
```

- 游标是不超过 16 KiB 的 JSON 字典，只放位置。每批只能声明一次提交点，并且必须推进。输入范围固定，游标格式变了要升级模块版本。
- 单批耗时的上限见 fastapi-operations 的运行参考“compose 部署”。
- 分段任务里的外部写入回滚不掉，发送后失败会停在“结果待确认”，处理方法见 fastapi-operations。固定来源导入加 `import_plan=ImportPlan(...)`，最后一批提交前自动对账。
- 上游明确要求等待（如 429）时抛 `RetryLater(60, resource="model")`，不消耗重试次数。用户登记的任务沿用登记时的身份，要求撤权立即生效的，执行步骤要重新读用户状态。SQLite 只能跑一个 worker。

例子：`test_jobs.py`、`segment_sample.py`、`test_segmented_jobs.py`、`import_sample.py`、`test_job_limits.py`、`test_job_defer.py`、`test_job_revalidation.py`、`test_schedule_organizations.py`。

## 多阶段流程

采集、等待、汇算、发布需要各自的事务和恢复点时用 Pipeline。每个阶段引用一个已登记的公开操作，并有自己的 JobPlan；定时只登记首入口 `pipeline.start`，它的权限默认是 `包名.run`，用 `Pipeline(..., access=...)` 改。

```python
daily = Pipeline(
    "report.daily",
    "经营日报",
    Begin,
    (
        Stage("collect", public.collect),
        Wait("wait", public.check_ready, every=30, timeout=3600),
        Stage("publish", public.publish),
    ),
)
start = Schedule(
    "daily",
    "日报入口",
    daily.start,
    daily.start.input(request=StartRequest[Begin](data=Begin())),
    every=timedelta(days=1),
    slot_input_field="request.period",
)
```

- module.py 登记 `pipelines=(daily,)`、`schedules=(start,)` 和三个阶段的 JobPlan。阶段输入默认来自上一阶段，可写 `input_from="input"` 或已完成的阶段名；阶段数据不超过 16 KiB，大结果只传引用。
- Wait 的操作输出要有布尔字段 `ready`，每次只检查一次，等待由框架推进；它的 JobPlan 必须 `repeat_safe=True`。不要在步骤里循环 sleep。
- `overlap="skip"`（默认）跳过重叠周期，`"queue"` 依次排队。`complete_by=DailyTime(time(9, 30))` 设截止，`on_overdue="pause"` 逾期后停在下一阶段前。
- 扇出：`FanOut("名称", 规划操作, stages=(...), join=All() 或 Ratio(0.9), max_parallel=8)`。规划步骤 `pipeline.add_members([Member(key=稳定键, input=Data)])`，汇算步骤 `pipeline.results(...)` 分页读取，固定来源用 `freeze_sources=True` 和 `pipeline.source(Data)`。
- `runtime.submit(pipeline.start, ...)` 返回流程编号，不是任务编号。

例子：`pipeline_sample.py`、`test_pipelines.py`、`fanout_sample.py`、`test_fanout.py`、`test_pipeline_overdue.py`。

## 外部调用

| 要做的事 | 只用这一种写法 |
| --- | --- |
| 调 HTTP 接口，读或写 | `remote.call` 加已声明的 `Endpoint` |
| 发邮件、调第三方 SDK | `effects` 加 `ProviderSpec` |

```python
supplier = remote("supplier", "供应商接口")
query_price = Endpoint(
    "supplier.query_price", "POST", "/prices/query", input=Query, output=Receipt, effect="read"
)


@step("查询价格", reads=["sku"], writes=["receipt"], remotes=[supplier], endpoints=[query_price])
async def read_price(data: Work, remote: RemoteClient) -> None:
    data.receipt = (await remote.call(supplier, query_price, Query(sku=data.sku))).data
```

- 模块登记 `remotes=(supplier,)`、`endpoints=(query_price,)`。地址和凭据只写在 `APP_REMOTES`，生产环境声明了却没配置会拒绝启动。
- 读写安全看 `effect`（`"read"` 或 `"write"`），不看 HTTP 方法。写入遇到 5xx、408、499、超时报"结果待确认"，不自动重发；对方真支持去重时才传 `key=`。`accepted_statuses=(409,)` 让确定的 4xx 拒绝回执按 output 校验后返回，`unknown_on=(202,)` 把额外状态当作待确认。
- 输入默认 GET/HEAD 放查询参数、其他方法放 JSON 正文。路径里有参数时写 `path_fields`，要显式分配时用 `query_fields`、`body_fields`，上传文件用 `file_fields` 并在调用时传 `files=(FilePart(...),)`。
- 重试和熔断（连续 5 次暂时失败后暂停 30 秒）由框架做，业务不要再包重试。响应默认限制 2,000,000 字节。
- 写事务开始后不能再调外部接口。要在保存之后通知对方，就在保存步骤里用 `later` 登记一个后台任务，由任务里的步骤去调。

发邮件和调 SDK 用 `ProviderSpec`（`transport="smtp"` 或 `"sdk"`），框架会持久记录每次发送的意图，可以事后查询原请求：产品在 `app/product.py` 的 `ApplicationSpec(providers=..., adapters=...)` 组装，适配器用 `shared.effects` 里的 `SmtpAdapter`、`SdkAdapter`；模块登记 `providers=(spec,)`，步骤声明 `providers=[spec]` 并用 `effects` 参数。`await effects.call(spec, 输入, key=业务键)` 在事务外立即发送；`await effects.enqueue(...)` 在保存步骤里登记，随业务提交后由 worker 发送；`await effects.perform(意图编号, lookup=True)` 只查询原请求。`repeat_safe=True` 只在供应商保证重复执行安全时写。

例子：`endpoint_sample.py`、`test_endpoint_contracts.py`、`test_remote_write_safety.py`、`test_effect_tasks.py`、`test_provider_effects.py`、`test_effect_recovery.py`。

## 文件

存储构造参数写 `files: ModuleFiles`，键限定在本包前缀里，不能含 `..`。上传接口由产品写在 `app/api/v1/`，路径要列进 `APP_UPLOAD_PATHS`；路由用 `services.uploads.receive(...)` 得到 `temp_id`，再作为操作输入。

- 临时上传：`read_upload(temp_id, max_bytes)` 有界读取，`adopt(temp_id, key)` 转为正式文件，`discard_upload` 丢弃。
- 本包文件：`save_bytes`、`read`、`open`、`exists`、`delete`。
- 不可变原件：`freeze(temp_id)` 返回 `ArtifactRef`（含大小和 SHA-256）；分批用 `read_window(ref, offset, length, max_bytes=...)`，游标只存 offset 和引用；`open_artifact(ref)` 完整流式读取并在末尾核对摘要。

例子：`test_artifact_refs.py`、`test_recovered_files_remote.py`、`tests/contracts/test_cache_and_files.py`。

## 大模型

```python
describe = prompt(
    "describe_mark", "说明文字", file=Path(__file__).parent / "prompts" / "describe.md", version="3"
)


@step("请大模型说明", reads=["mark"], writes=["result"], prompts=[describe])
async def ask_text(data: TextWork, model: Model) -> None:
    data.result = await model.ask(describe, mark=data.mark)
```

- 提示词文件放包的 `prompts/`，变量写 `{name}`，缺少或多出都报错；改内容就改 `version`。模块登记 `prompts=(describe,)`。
- 结构化结果用 `await model.ask_data(提示词, 输出Data, 变量=值)`。重试、并发、熔断由框架的模型调用服务处理；保存步骤之后不能再调大模型。
- 本地和测试没配模型时用模拟回复；生产声明了提示词却没配模型会拒绝启动。例子：`sample_modules.py` 的 `ask_text`、`test_model_calls.py`。

## 权限与身份

- 操作级权限写在 contract 的 `access`，入口、内部同步调用、Runtime.submit/Later 等业务提交入口和后台执行都检查目标操作权限：匿名 401，缺权限 403。`uses` 只声明依赖，不授予权限，组合流程的调用者须拥有各目标操作的权限；队列内部推进只保存原身份，权限在目标操作执行时检查。`access` 写 `public`、`signed_in` 或 `包名.动作`；调用者持有的权限还可以是 `*`（全部）和 `包名.*`（本包全部）。
- 资源级权限在步骤里查：参数写 `caller: Caller`，`caller.can("quote.approve")` 不满足就 `raise NotAllowed()`。数据隔离用存储一节的 `org_column`、`owner_column`。身份只来自已验证的凭据，不用请求正文里自报的身份。
- 字段加密：存储构造参数写 `vault: Vault`，写库前 `vault.encrypt(文字)`，读出后 `vault.decrypt(...)`，密钥在 `APP_DATA_KEYS`。例子：`test_vault.py`。
- 旧系统用自定义请求头传会话时，写 `Module(identity=解析操作, identity_header="X-Legacy-Token", identity_token="opaque")`。例子：`identity_sample.py`、`test_identity_declaration.py`。账号登录见 `frontend-interface.md`。

## 缓存、表格、时钟和其他

缓存：步骤参数或存储构造参数写 `cache: ModuleCache`，键自动加包前缀。只缓存能重新算出来的内容，必须给有效期（秒）；缓存故障按未命中处理；多实例要配 `APP_CACHE_URL`。例子：`tests/contracts/test_cache_and_files.py`。

```python
found = await self.cache.get_data(f"price:{sku}", Price)
if found is None:
    found = await self.read_price(sku)
    await self.cache.set_data(f"price:{sku}", found, 300)
```

表格导入导出只在路由层做，`from shared.exchange.sheets import MEDIA, read_sheet, write_sheet`。`read_sheet(内容, 文件名, {表头: 字段}, {必需字段: 表头})` 返回 `[(文件行号, {字段: 文字})]`，值全是文字，由业务步骤按规则转换并按行号报错。`write_sheet(行, {字段: 表头}, "csv" 或 "xlsx")` 返回文件内容，内容类型取 `MEDIA[格式]`。一次最多 5000 行，空文件、缺必需列、非 UTF-8 的 CSV 直接报错，更大的文件用分段任务。例子：`test_sheets.py`。

时钟：步骤参数写 `clock: Clock`，`clock.now()` 返回 UTC 时间戳（秒）。calc 不读时钟，由步骤传入。测试用 `ApplicationSpec(clock=FakeClock(起点))` 组装，`clock.advance(秒)` 推进；生产组装拒绝 FakeClock。例子：`test_time_runtime.py`、`tests/unit/test_clocks.py`。

流式输出：contract 写 `stream=True`，异步步骤用 `emit: Emitter`，`await emit(文字)` 每段不超过 64 KiB；客户端调用 `POST /api/v1/stream/{操作名}`，断开会取消并回滚。例子：`test_streaming.py`。

观察样例：要在测试里核对中间字段时，步骤写 `observes=["字段"]`（须在本步骤读写范围内），测试用 `with capture(journal):` 包住真实运行，再 `journal.compare([ExpectedObservation(ObservationPoint(操作名, 步骤名, 字段), 预期值)])` 找最早的不一致。中间值对上了，仍要另外断言数据库状态和外部发送次数。例子：`test_observation_points.py`。
