"""
定义框架自己会抛出的错误。
业务模块在自己的 data.py 中定义业务错误，写法与这里相同。
"""

from shared.errors.kinds import BusinessError, Kind


class NotSignedIn(BusinessError):
    code = "not_signed_in"
    kind = Kind.NOT_SIGNED_IN
    message = "需要提供有效的服务密钥或登录身份"


class NotAllowed(BusinessError):
    code = "not_allowed"
    kind = Kind.FORBIDDEN
    message = "没有执行此操作的权限"


class TooBusy(BusinessError):
    code = "too_busy"
    kind = Kind.TOO_MANY
    message = "服务繁忙，请稍后再试"


class QueueFull(BusinessError):
    code = "queue_full"
    kind = Kind.TOO_MANY
    message = "这类任务排队已满，请稍后再试"


class DuplicateRequest(BusinessError):
    code = "duplicate_request"
    kind = Kind.CONFLICT
    message = "同一个请求编号已经用于内容不同的请求"


class RunTimeout(BusinessError):
    code = "run_timeout"
    kind = Kind.TIMEOUT
    message = "处理超时"


class ResultUnknown(BusinessError):
    code = "result_unknown"
    kind = Kind.UNKNOWN_RESULT
    message = "保存结果尚不能确认，请用运行编号核对"


class DatabaseUnavailable(BusinessError):
    code = "database_unavailable"
    kind = Kind.TEMPORARY
    message = "数据库暂时不可用"


class ModelUnavailable(BusinessError):
    code = "model_unavailable"
    kind = Kind.TEMPORARY
    message = "大模型服务暂时不可用"


class ModelOutputInvalid(BusinessError):
    code = "model_output_invalid"
    kind = Kind.TEMPORARY
    message = "大模型返回的内容不符合约定格式"


class ModelRejected(BusinessError):
    code = "model_rejected"
    kind = Kind.BROKEN
    message = "大模型服务拒绝了请求，请检查模型配置和提示词"


class RemoteUnavailable(BusinessError):
    code = "remote_unavailable"
    kind = Kind.TEMPORARY
    message = "外部系统暂时不可用"


class RemoteResultUnknown(BusinessError):
    code = "remote_result_unknown"
    kind = Kind.UNKNOWN_RESULT
    message = "写入外部系统时没有得到结果，对方可能已经处理，请核对后再决定是否重试"


class RemoteRejected(BusinessError):
    code = "remote_rejected"
    kind = Kind.INVALID
    message = "外部系统拒绝了请求"


class RemoteNotFound(BusinessError):
    code = "remote_not_found"
    kind = Kind.NOT_FOUND
    message = "外部系统中没有找到请求的数据"


class RemoteAuthFailed(BusinessError):
    code = "remote_auth_failed"
    kind = Kind.BROKEN
    message = "外部系统拒绝访问，请检查密钥配置"


class RemoteNotConfigured(BusinessError):
    code = "remote_not_configured"
    kind = Kind.BROKEN
    message = "外部系统没有配置"


class TooManyRequests(BusinessError):
    code = "too_many_requests"
    kind = Kind.TOO_MANY
    message = "请求过于频繁，请稍后再试"


class FileTooLarge(BusinessError):
    code = "file_too_large"
    kind = Kind.INVALID
    message = "文件超过大小限制"


class FileTypeNotAllowed(BusinessError):
    code = "file_type_not_allowed"
    kind = Kind.INVALID
    message = "文件类型不允许或文件已过期"


class StepRuleBroken(BusinessError):
    code = "step_rule_broken"
    kind = Kind.BROKEN
    message = "步骤的实际行为与声明不一致"


class StaleAttempt(BusinessError):
    code = "stale_attempt"
    kind = Kind.CONFLICT
    message = "这次任务尝试已经过期，结果不会保存"


class DeclarationError(Exception):
    # 汇总启动检查发现的全部问题，一次性列出。
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"模块声明有 {len(problems)} 处问题：\n{lines}")


class ConfigError(Exception):
    # 汇总配置检查发现的问题，服务拒绝启动。
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"运行配置有 {len(problems)} 处问题：\n{lines}")
