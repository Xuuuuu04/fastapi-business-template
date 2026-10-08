# 2.2 框架补丁回收与产品接入

本批按实际差异回收能力，零售只作只读参考，没有预置零售模块。

| 参考提交 | 判断 | 处理 |
| --- | --- | --- |
| 259e3184 | 捕获已声明的拒绝响应是通用能力，受理含义属于业务 | 新增accepted_statuses，仅捕获可确定的4xx；超时、5xx和较早未知写入仍保留未知 |
| d5c25726 | 临时原件受限读取和重复上传清理是通用能力 | 有界读取上限加一字节，不先读完整文件；保留原件信息与上传生命周期 |
| 10e71ba4 | 保存生成文件与检查存在是通用能力 | save_bytes在线程中写临时文件；SavedFile通过shared.public公开，模块前缀不变 |
| a9b5ca42 | Mermaid样式invoke是通用修复 | 模板已经具备，保留现有回归测试，不重复改代码 |
| f16316b6 | 定时任务组织身份是通用能力 | 支持配置多组织和Schedule声明范围，周期键包含组织；旧单组织时段复用，不重复 |
| 24444ed9 | JSON域驱动双重编码修复属于业务域适配 | retail域不加入模板，在业务store内定义域适配；JSON直接bind_processor避免双编码 |
| 0400e4bf | RLS组织绑定是通用机制；retail域名、精度和限制是业务约定 | 配置数据库组织设置名；业务迁移仍创建策略和域，不内置retail_*类型 |

另两个实际更新问题一并明确：实际定时窗口使用slot_input_field；产品登录不得由框架导入
user_access业务包，改为模块声明identity解析操作。框架保留原JWT校验和无效凭据限流。
这两项为当前升级适配所需，不扩展新的业务功能。

## 零售专用类型替代

在拥有数据表的业务包`store/domain_types.py`中保留产品自己的SQLAlchemy TypeDecorator。
JSON域使用`DOMAIN("retail_object", JSONB(), create_type=False)`，其`bind_processor`把字典
序列化一次，`result_processor`接受驱动已解析的字典或JSON字符串。小数域用产品现有的
`Numeric(24,8)`与`Numeric(16,8)`，只接受Decimal；域的对象大小与比率边界继续由原迁移保证。
各表从本包store导入适配。需要跨包共享业务类型时从明确所有者的public导出；不引用另一个包内部。
此次模板没有创建、删除、重命名任何业务域，也没有修改零售源码或数据库。

## 接入条件

1. 先用原template-source.json对应的旧模板做预览，保留产品的依赖、业务登记和迁移历史。
2. 零售设置`APP_DATABASE_ORG_SETTING=retail.org_id`。多组织填APP_SCHEDULE_ORG_IDS，旧单组织仍可用。
3. 在零售user_access/module.py声明：`identity=public.resolve_session, identity_header="X-Bearer"`。
   输入token可以是str或SecretStr；输出username/name/org_id为str，permissions为list[str]。
   解析操作必须为本模块提供、entry=True、access=public；账号/会话有效期由业务操作核对。
4. 数据库按产品迁移链追加PR1的两张框架表和权限，长汇算再按批大小预算适配。
5. 审查模板工具列出的manual_review后才能应用。预览无框架冲突不代表业务已升级或生产验收。

## 已回收补丁证明

产品以前把业务与框架扩展直接写在受保护文件内，普通文本三份比较会把已审查回收的部分也报冲突。
更新工具仅对本批登记的精确旧模板摘要、产品补丁摘要、新实现摘要同时匹配的项标`recovered`。
这些是经过本批审查和框架测试确认的替代，不是盲目选新版；必要业务声明和配置仍列入manual_review。
任一份原文变化、未知产品补丁或后续模板内容改变，都回到原冲突处理。证明跟随Skill和framework.lock。
