"""
SMTP发送适配器，每项意图只发送给一个收件人；服务器受理与收件人实际收到分别表达。
"""

import smtplib
import ssl
from email.message import EmailMessage
from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from shared.data.fields import meaning
from shared.data.models import Data
from shared.effects.spec import AdapterReply
from shared.flow.heavy import HeavySteps


# 地址和内容保存为加密意图，不进入运行摘要。
class MailInput(Data):
    sender: str = meaning("发信地址")
    recipient: str = meaning("单个收件地址")
    subject: str = meaning("主题")
    text: str = meaning("纯文本正文")


# 该编号只证明本次消息身份，不代表SMTP供应商支持按编号去重。
class MailReceipt(Data):
    message_id: str = meaning("发送消息编号")


# 连接与凭据只存在于产品配置，不进入ProviderSpec的静态结构。
class SmtpConfig(BaseModel):
    account: str = Field(min_length=1, description="稳定供应商账号标识，不填写密码")
    host: str = Field(min_length=1)
    port: int = Field(default=465, ge=1, le=65535)
    tls: Literal["ssl", "starttls"] = "ssl"
    username: str = ""
    password: SecretStr | None = None
    timeout: float = Field(default=10, gt=0)


# 标准SMTP无法权威查询最终送达，未知状态必须保留，不能用Message-ID假定安全重发。
class SmtpAdapter:
    simulated = False

    # 只保存配置，实际网络连接在事务外发送时建立。
    def __init__(self, config: SmtpConfig) -> None:
        self.config = config
        self.identity = f"{config.account}@{config.host}:{config.port}/{config.username}"
        self.work = HeavySteps(8)

    # 产品组装按ProviderSpec绑定限额，实际线程结束之前不会归还位置。
    def configure_limit(self, concurrency: int) -> None:
        if self.work.running:
            raise ValueError("正在发送时不能改变SMTP线程限额")
        self.work.concurrency = concurrency

    # 同步SMTP在线程执行；取消等待不能停止已发送的邮件，因此上层保留unknown。
    async def send(self, input: Data, key: str) -> AdapterReply:
        return await self.work.run(self.send_once, MailInput.model_validate(input), key)

    # 协议没有查询接口；结果未知不能伪装为未发送。
    async def lookup(self, input: Data, key: str) -> AdapterReply:
        return AdapterReply("unknown")

    # 每次连接在发送函数中释放；取消后仍在发送的线程只能留下未知证据。
    async def close(self) -> None:
        await self.work.close()

    # 明确的SMTP拒绝可以记为refused，其他异常由统一效果服务保留unknown。
    def send_once(self, input: MailInput, key: str) -> AdapterReply:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = (
            input.sender,
            input.recipient,
            input.subject,
        )
        message["Message-ID"] = f"<{key}@fastapi.local>"
        message.set_content(input.text)
        try:
            with self.client() as client:
                if self.config.tls == "starttls":
                    client.starttls(context=ssl.create_default_context())
                if self.config.username:
                    password = (
                        self.config.password.get_secret_value() if self.config.password else ""
                    )
                    client.login(self.config.username, password)
                refused = client.send_message(message, input.sender, [input.recipient])
                if refused:
                    return AdapterReply("refused")
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
            return AdapterReply("refused")
        reference = str(message["Message-ID"])
        return AdapterReply("accepted", MailReceipt(message_id=reference), reference)

    # TLS参数只传给SSL客户端，普通SMTP必须在登录前升级TLS。
    def client(self) -> smtplib.SMTP:
        if self.config.tls == "ssl":
            return smtplib.SMTP_SSL(
                self.config.host,
                self.config.port,
                timeout=self.config.timeout,
                context=ssl.create_default_context(),
            )
        return smtplib.SMTP(self.config.host, self.config.port, timeout=self.config.timeout)
