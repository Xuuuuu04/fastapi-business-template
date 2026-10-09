"""
十万行原件回放端到端：真实定时入口、批量解析/汇算/CSV、阶段耗时SQL内存与无人工完成。
"""

import csv
import hashlib
import json
import os
from pathlib import Path

import pytest

from app.setup.drill import execute
from shared.drills.isolation import isolated
from tests.framework.drill_sample import module

pytestmark = pytest.mark.anyio


# 原件不通过模型重新生成结果；清单固定内容摘要，框架实际消费原始JSON字节。
def original(folder: Path, count: int = 100000) -> dict:
    content = json.dumps(
        {"rows": [{"id": i, "value": i * 2} for i in range(1, count + 1)]}
    ).encode()
    (folder / "original.json").write_bytes(content)
    return dict(
        pipeline="drill_sample.daily",
        scale=count,
        timeout_seconds=60,
        replay={
            "recorded_upstream": [
                dict(
                    method="GET",
                    path="/original",
                    params={"count": str(count)},
                    file="original.json",
                    sha256=hashlib.sha256(content).hexdigest(),
                    headers={"content-type": "application/json"},
                )
            ]
        },
    )


# 每数据库真正跑完整定时链，无真实网络，CSV实际下载产物按内容验收。
async def test_100000_rows_original_replay(tmp_path: Path) -> None:
    config = original(tmp_path)
    postgres = os.environ.get("APP_TEST_DATABASE_URL", "")
    async with isolated(tmp_path, postgres if postgres.startswith("postgresql") else "") as url:
        result = await execute([module], config, url, tmp_path, tmp_path, tmp_path / "output")
    assert result["state"] == "succeeded" and result["needs_manual"] is False
    assert result["external_network"] is False and result["isolated"] is True
    assert [stage["state"] for stage in result["stages"]] == ["succeeded"] * 5
    parsed = next(stage for stage in result["stages"] if stage["name"] == "parse")
    assert parsed["rows"] == 100000 and parsed["row_evidence"] == "已提交段"
    assert parsed["slow_sql"] and all(call["elapsed_ms"] > 0 for call in parsed["slow_sql"])
    assert result["memory_peak_bytes"] > 0 and result["coverage"]["replay_stages"] == ["collect"]
    assert result["coverage"]["uncovered_stages"] == []
    assert set(result["coverage"]["no_replay_stages"]) == {"wait", "parse", "sum", "publish"}
    file = tmp_path / "output/artifacts/drill_sample/report.csv"
    with file.open() as source:
        rows = list(csv.DictReader(source))
    assert rows == [{"rows": "100000", "total": "10000100000"}]


# 原件摘要不符明确失败，不能访问真实上游补数据，也不能声称覆盖完成。
async def test_replay_missing_or_changed_is_not_success(tmp_path: Path) -> None:
    config = original(tmp_path)
    config["replay"]["recorded_upstream"][0]["sha256"] = "invalid"
    async with isolated(tmp_path) as url:
        result = await execute([module], config, url, tmp_path, tmp_path, tmp_path / "output")
    assert result["state"] == "failed" and result["needs_manual"] is True
    assert "collect" in result["coverage"]["uncovered_stages"]
    assert result["coverage"]["originals"] == []
