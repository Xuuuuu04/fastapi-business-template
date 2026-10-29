import string
from dataclasses import dataclass
from pathlib import Path

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken


@dataclass(frozen=True, eq=False)
class Prompt:
    name: str
    title: str
    version: str
    file: Path
    output: type[Data] | None = None
    max_tokens: int = 800
    temperature: float = 0.2


@dataclass(frozen=True)
class PromptText:
    system: str
    user: str
    names: frozenset[str]


def prompt(
    name: str,
    title: str,
    *,
    file: Path,
    version: str,
    output: type[Data] | None = None,
    max_tokens: int = 800,
    temperature: float = 0.2,
) -> Prompt:
    return Prompt(name, title, version, file, output, max_tokens, temperature)


def load_prompt(item: Prompt) -> PromptText:
    text = item.file.read_text(encoding="utf-8")
    parts: dict[str, list[str]] = {"system": [], "user": []}
    current = ""
    for line in text.splitlines():
        heading = line.strip().lower()
        if heading in ("## system", "## user"):
            current = heading[3:]
            continue
        if current:
            parts[current].append(line)
    system, user = "\n".join(parts["system"]).strip(), "\n".join(parts["user"]).strip()
    if not user:
        raise ValueError(f"提示词文件 {item.file.name} 缺少“## user”段落")
    names = {field for _, field, _, _ in string.Formatter().parse(system + user) if field}
    return PromptText(system, user, frozenset(names))


def fill_prompt(item: Prompt, text: PromptText, values: dict[str, object]) -> tuple[str, str]:
    missing = text.names - values.keys()
    extra = values.keys() - text.names
    if missing or extra:
        raise StepRuleBroken(
            f"提示词“{item.title}”的变量不一致：缺少 {sorted(missing)}，多出 {sorted(extra)}"
        )
    return text.system.format(**values), text.user.format(**values)
