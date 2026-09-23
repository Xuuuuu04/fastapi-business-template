# 请求路由

路由按 service 的业务分组对应组织，例如 operations/reports/routes.py。仅在路由增多时继续拆成更深目录，不机械复制全部 service 子目录。

routes.py 使用 APIRouter；forms.py 定义 HTTP 请求和响应模型。路由完成输入校验与身份解析后调用业务入口，转换返回结果和业务异常。

请求参数合法不代表业务操作被允许；对象范围和状态限制仍由业务服务检查。健康检查等系统接口可以独立于角色目录。
