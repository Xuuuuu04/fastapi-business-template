from pathlib import Path

from fastapi.testclient import TestClient

from app.api.errors import field_problems
from app.setup.build import build
from app.setup.web import create_app
from shared.public import Data, Nothing, meaning
from tests.testing_app import make_settings


class Batch(Data):
    amounts: list[int] = meaning("合成整数列表")


def test_bulk_validation_response_is_bounded(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    app = create_app(settings, build(settings, modules=[]))

    @app.post("/test/bulk")
    async def receive(body: Batch) -> Nothing:
        return Nothing()

    with TestClient(app) as client:
        reply = client.post("/test/bulk", json={"amounts": ["synthetic-private-input"] * 2000})
    assert reply.status_code == 422
    assert len(reply.json()["fields"]) == 50
    assert len(reply.content) < 64 * 1024
    assert "synthetic-private-input" not in reply.text
    assert reply.json()["fields"][0]["field"] == "amounts.0"
    assert reply.json()["fields"][-1]["field"] == "amounts.49"


def test_field_problem_paths_and_text_are_bounded() -> None:
    fields = field_problems(
        [
            ("x" * 201, "路径太长"),
            ("\ud800", "非法字符"),
            ("lines.0.amount", "请修改金额" * 500),
        ]
    )
    assert len(fields) == 1 and fields[0].field == "lines.0.amount"
    assert len(fields[0].problem.encode("utf-8")) <= 300
    assert len(field_problems([(f"x.{i}", "中文错误") for i in range(2000)])) == 50
