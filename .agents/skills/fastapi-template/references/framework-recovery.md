# 外部回收证明与升级接入

模板只提供通用判断，不内置任何产品摘要。产品在自己的升级任务目录保存已审查证明：

```json
{
  "schema_version": 1,
  "files": {
    "server/shared/example.py": {
      "base": "<旧模板文件SHA256>",
      "products": ["<已审查产品补丁SHA256>"],
      "replacement": "<新实现SHA256>",
      "manual_review": ["server/.env"]
    }
  }
}
```

摘要须为64位小写十六进制；文件路径必须规范、相对且位于框架管理范围内。
证明最多1 MiB。只有三份文件同时匹配才标recovered，未知或变化的内容继续报冲突。
证明中的人工接入项仍列入manual_review；预览零冲突不代表业务已经升级。

```bash
uv run dev upgrade \
  --base /旧模板 --source /新模板 --target /产品 \
  --recovery-proof /产品升级任务/recovery-proof.json
```

没有此参数时仅普通三份比较。apply之前重新读取证明与文件；证明或内容变化导致方案不同，
拒绝保存。不要把产品证明放入模板，也不要从模板复制别的产品证明。

## 身份解析

产品在module.py声明公开会话解析操作：

```python
Module(..., identity=public.resolve_identity, identity_token="opaque", identity_header="X-Session")
```

identity_token明确选择标准Authorization的处理方式：默认jwt保持原校验；opaque走产品解析。
兼容头始终走产品解析，只在标准Authorization不存在时使用。输入token可为str或SecretStr，
输出username/name/org_id为str、permissions为list[str]，账号状态与会话有效期由产品操作核对。
成功解析不保存完整运行记录，失败正常保存。没有令牌缓存，每次请求都核验会话；
账号停用或撤销由下一次数据库解析直接生效，不引入30秒缓存延迟。

## 组织与类型

部署可配置APP_SCHEDULE_ORG_IDS，旧APP_SCHEDULE_ORG_ID兼容；Schedule可指定组织范围。
PostgreSQL产品RLS通过APP_DATABASE_ORG_SETTING选择迁移中已有的组织设置名，值来自可信身份。
业务域名、JSON大小限制、小数精度和比率范围由产品store与迁移维护，不进入通用模板。
API和worker应同步发布；长汇算按实际停止预算选批大小，追加新框架表仍沿用产品迁移链。
