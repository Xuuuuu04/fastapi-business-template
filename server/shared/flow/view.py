from typing import Any

from pydantic import TypeAdapter, ValidationError

from shared.data.fields import FieldNote, notes_of
from shared.data.models import WorkData
from shared.errors.framework import StepRuleBroken


class FieldTypes:
    def __init__(self, work: type[WorkData]) -> None:
        self.notes: dict[str, FieldNote] = notes_of(work)
        self.adapters: dict[str, TypeAdapter[Any]] = {
            name: TypeAdapter(info.annotation) for name, info in work.model_fields.items()
        }
        self.annotations = {name: info.annotation for name, info in work.model_fields.items()}

    def label(self, name: str) -> str:
        note = self.notes.get(name)
        return f"{name}（{note.meaning}）" if note and note.meaning else name

    def check(self, name: str, value: Any, place: str) -> Any:
        try:
            return self.adapters[name].validate_python(value, strict=True)
        except ValidationError as error:
            expected = getattr(self.annotations[name], "__name__", str(self.annotations[name]))
            first = error.errors()[0]["msg"] if error.errors() else ""
            raise StepRuleBroken(
                f"步骤“{place}”写入字段 {self.label(name)} 的值类型不对：期望 {expected}，"
                f"实际是 {type(value).__name__}（{first}）"
            ) from None


class StepView:
    __slots__ = ("_values", "_reads", "_writes", "_written", "_types", "_place")

    def __init__(
        self,
        values: dict[str, Any],
        reads: tuple[str, ...],
        writes: tuple[str, ...],
        types: FieldTypes,
        place: str,
    ) -> None:
        object.__setattr__(self, "_values", values)
        object.__setattr__(self, "_reads", frozenset(reads))
        object.__setattr__(self, "_writes", frozenset(writes))
        object.__setattr__(self, "_written", set())
        object.__setattr__(self, "_types", types)
        object.__setattr__(self, "_place", place)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._reads and name not in self._written:
            raise StepRuleBroken(
                f"步骤“{self._place}”读取了未声明的字段 {self._types.label(name)}，"
                "请在 reads 中声明"
            )
        if name not in self._values:
            raise StepRuleBroken(
                f"步骤“{self._place}”读取的字段 {self._types.label(name)} 还没有值"
            )
        return self._values[name]

    def __setattr__(self, name: str, value: Any) -> None:
        if name not in self._writes:
            raise StepRuleBroken(
                f"步骤“{self._place}”写入了未声明的字段 {self._types.label(name)}，"
                "请在 writes 中声明"
            )
        self._values[name] = self._types.check(name, value, self._place)
        self._written.add(name)


def missing_writes(view: StepView) -> list[str]:
    written = object.__getattribute__(view, "_written")
    return [name for name in object.__getattribute__(view, "_writes") if name not in written]
