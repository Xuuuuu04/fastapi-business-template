"""
已审查补丁只在三份摘要精确匹配时回收；任一内容变化仍进入原冲突处理。
"""

import hashlib

from fastapi_template.template import recovery
from fastapi_template.template.merge import compare_file


# 摘要证明不能扩大到尚未审查的新产品修改或后续模板修改。
def test_recovery_requires_all_three_fingerprints(monkeypatch) -> None:
    old, product, new = b"old", b"old with patch", b"generic reviewed implementation"
    name = "server/shared/example.py"
    proof = {
        "base": hashlib.sha256(old).hexdigest(),
        "products": [hashlib.sha256(product).hexdigest()],
        "replacement": hashlib.sha256(new).hexdigest(),
        "manual_review": ["server/.env"],
    }
    monkeypatch.setattr(recovery, "RECOVERED", {name: proof})
    assert recovery.recovered_patch(name, old, product, new) == ("server/.env",)
    for before, local, after in (
        (b"other", product, new),
        (old, b"unknown patch", new),
        (old, product, b"unreviewed replacement"),
    ):
        assert recovery.recovered_patch(name, before, local, after) is None
        assert compare_file(name, before, local, after).state == "conflict"
    assert recovery.recovered_patch(name, old, None, new) is None
    assert recovery.recovered_patch("other.py", old, product, new) is None
