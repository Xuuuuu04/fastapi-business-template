import hashlib
import json
from pathlib import Path

import pytest
from fastapi_template.template import recovery
from fastapi_template.template.merge import compare_file


def test_recovery_requires_all_three_fingerprints(tmp_path: Path) -> None:
    old, product, new = b"old", b"old with patch", b"generic reviewed implementation"
    name = "server/shared/example.py"
    proof = {
        "base": hashlib.sha256(old).hexdigest(),
        "products": [hashlib.sha256(product).hexdigest()],
        "replacement": hashlib.sha256(new).hexdigest(),
        "manual_review": ["server/.env"],
    }
    path = tmp_path / "proof.json"
    path.write_text(json.dumps({"schema_version": 1, "files": {name: proof}}))
    proofs = recovery.load_proof(path)
    assert recovery.recovered_patch(proofs, name, old, product, new) == ("server/.env",)
    for before, local, after in (
        (b"other", product, new),
        (old, b"unknown patch", new),
        (old, product, b"unreviewed replacement"),
    ):
        assert recovery.recovered_patch(proofs, name, before, local, after) is None
        assert compare_file(name, before, local, after).state == "conflict"
    assert recovery.recovered_patch(proofs, name, old, None, new) is None
    assert recovery.recovered_patch(proofs, "other.py", old, product, new) is None


def test_no_embedded_product_proof() -> None:
    assert recovery.load_proof(None) == {}
    assert not hasattr(recovery, "RECOVERED")


@pytest.mark.parametrize(
    "document",
    [
        {"schema_version": 2, "files": {}},
        {"schema_version": 1, "files": {"../outside": {}}},
        {"schema_version": 1, "files": {"x": {"base": "bad"}}},
    ],
)
def test_invalid_external_proof_is_rejected(tmp_path: Path, document) -> None:
    path = tmp_path / "proof.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        recovery.load_proof(path)


def test_external_proof_changes_are_rechecked_before_apply(tmp_path: Path) -> None:
    from fastapi_template.template.merge import apply_plan, update_plan

    base, source, target = (tmp_path / name for name in ("base", "source", "target"))
    name = "server/shared/example.py"
    old, product, new = b"old", b"custom patch", b"reviewed replacement"
    for root, body in ((base, old), (source, new), (target, product)):
        path = root / name
        path.parent.mkdir(parents=True)
        path.write_bytes(body)
    proof = tmp_path / "proof.json"
    proof.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": {
                    name: {
                        "base": hashlib.sha256(old).hexdigest(),
                        "products": [hashlib.sha256(product).hexdigest()],
                        "replacement": hashlib.sha256(new).hexdigest(),
                        "manual_review": [],
                    }
                },
            }
        )
    )
    changes, _ = update_plan(target, base, source, recovery_proof=proof)
    assert changes[0].state == "recovered"
    proof.write_text(json.dumps({"schema_version": 1, "files": {}}))
    with pytest.raises(ValueError, match="发生变化"):
        apply_plan(target, base, source, changes, recovery_proof=proof)
    assert (target / name).read_bytes() == product
