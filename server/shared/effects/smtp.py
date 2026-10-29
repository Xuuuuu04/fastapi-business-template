import smtplib
import ssl
from email.message import EmailMessage
from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from shared.data.fields import meaning
from shared.data.models import Data
from shared.effects.spec import AdapterReply
from shared.flow.heavy import HeavySteps


class MailInput(Data):
    sender: str = meaning("发信地址")
    recipient: str = meaning("单个收件地址")
    subject: str = meaning("主题")
    text: str = meaning("纯文本正文")


class MailReceipt(Data):
    message_id: str = meaning("发送消息编号")


class SmtpConfig(BaseModel):
    account: str = Field(min_length=1, description="稳定供应商账号标识，不填写密码")
    host: str = Field(min_length=1)
    port: int = Field(default=465, ge=1, le=65535)
    tls: Literal["ssl", "starttls"] = "ssl"
    username: str = ""
    password: SecretStr | None = None
    timeout: float = Field(default=10, gt=0)


class SmtpAdapter:
    simulated = False

    def __init__(self, config: SmtpConfig) -> None:
        self.config = config
        self.identity = f"{config.account}@{config.host}:{config.port}/{config.username}"
        self.work = HeavySteps(8)

    def configure_limit(self, concurrency: int) -> None:
        if self.work.running:
            raise ValueError("正在发送时不能改变SMTP线程限额")
        self.work.concurrency = concurrency

    async def send(self, input: Data, key: str) -> AdapterReply:
        return await self.work.run(self.send_once, MailInput.model_validate(input), key)

    async def lookup(self, input: Data, key: str) -> AdapterReply:
        return AdapterReply("unknown")

    async def close(self) -> None:
        await self.work.close()

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

    def client(self) -> smtplib.SMTP:
        if self.config.tls == "ssl":
            return smtplib.SMTP_SSL(
                self.config.host,
                self.config.port,
                timeout=self.config.timeout,
                context=ssl.create_default_context(),
            )
        return smtplib.SMTP(self.config.host, self.config.port, timeout=self.config.timeout)
