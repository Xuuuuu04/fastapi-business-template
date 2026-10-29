from dataclasses import replace
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT, ROOT
from fastapi_project.development.runtime import recent_runs
from fastapi_template.template.initialization import initialize

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.records.stores import RunFilter, SqlRunStore
from shared.records.version import source_version
from tests.framework.sample_modules import CalcInput, calc


@pytest.mark.anyio
async def test_current_success_samples_require_matching_source(sample: Services) -> None:
    await sample.runtime.run(calc, CalcInput(amount=5), caller=DEVELOPER)
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    assert run.source_version == source_version(ROOT)
    store = SqlRunStore(sample.database)
    await store.save(
        [
            replace(
                run, id="old", root_id="old", contract="old_package.calculate", source_version="old"
            ),
            replace(
                run,
                id="lost",
                root_id="lost",
                contract="lost_package.calculate",
                gaps=["部分记录缺失"],
            ),
            run,
        ]
    )
    settings = sample.settings.model_copy(update={"run_records": "database"})
    status = await recent_runs(settings, 10)
    assert status["current_successful"] == ["sample_calc.calc"]
    assert "old_package.calculate" in status["successful"]
    assert "lost_package.calculate" not in status["successful"]
    assert all("graph" in item and item["steps"][0]["source"] for item in status["runs"])
    assert "caller" not in str(status) and "version-test" not in str(status)


def test_source_version_tracks_code_not_history(tmp_path: Path) -> None:
    target = tmp_path / "product"
    initialize(PROJECT, target, "版本样例")
    root = target / "server"
    before = source_version(root)
    (target / "doc/tasks.md").write_text("# 新工作\n", encoding="utf-8")
    (root / "var").mkdir()
    (root / "var/check.json").write_text("{}", encoding="utf-8")
    assert source_version(root) == before
    source = root / "app/setup/catalog.py"
    source.write_text(source.read_text() + "\n# 代码变化样例\n", encoding="utf-8")
    assert source_version(root) != before
