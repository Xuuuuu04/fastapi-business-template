import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

MAX_PROOF_BYTES = 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RecoveryEntry:
    base: str
    products: tuple[str, ...]
    replacement: str
    manual_review: tuple[str, ...]


def load_proof(path: Path | None) -> dict[str, RecoveryEntry]:
    if path is None:
        return {}
    with path.open("rb") as source:
        body = source.read(MAX_PROOF_BYTES + 1)
    if len(body) > MAX_PROOF_BYTES:
        raise ValueError("回收证明超过1 MiB")
    try:
        document = json.loads(body)
    except (ValueError, UnicodeError):
        raise ValueError("回收证明不是有效JSON") from None
    if not isinstance(document, dict) or set(document) != {"schema_version", "files"}:
        raise ValueError("回收证明需要schema_version与files")
    if document["schema_version"] != 1 or not isinstance(document["files"], dict):
        raise ValueError("回收证明版本或files格式不正确")
    return {safe_name(name): entry_of(raw) for name, raw in document["files"].items()}


def entry_of(raw: Any) -> RecoveryEntry:
    if not isinstance(raw, dict) or set(raw) != {
        "base",
        "products",
        "replacement",
        "manual_review",
    }:
        raise ValueError("回收证明项字段不正确")
    hashes = raw["products"]
    manual = raw["manual_review"]
    if not isinstance(hashes, list) or not hashes or not isinstance(manual, list):
        raise ValueError("products必须为非空摘要列表，manual_review必须为路径列表")
    values = [raw["base"], raw["replacement"], *hashes]
    if any(not isinstance(value, str) or not SHA256.fullmatch(value) for value in values):
        raise ValueError("回收证明摘要必须为64位小写SHA256")
    return RecoveryEntry(
        raw["base"], tuple(hashes), raw["replacement"], tuple(map(safe_name, manual))
    )


def safe_name(name: Any) -> str:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("回收证明路径不正确")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
        raise ValueError("回收证明路径必须是规范的产品内相对路径")
    return name


def recovered_patch(
    proofs: dict[str, RecoveryEntry],
    name: str,
    old: bytes | None,
    local: bytes | None,
    new: bytes | None,
) -> tuple[str, ...] | None:
    proof = proofs.get(name)
    if proof is None or old is None or local is None or new is None:
        return None
    if (
        hashlib.sha256(old).hexdigest() != proof.base
        or hashlib.sha256(local).hexdigest() not in proof.products
        or hashlib.sha256(new).hexdigest() != proof.replacement
    ):
        return None
    return proof.manual_review
