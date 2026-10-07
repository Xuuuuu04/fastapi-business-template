"""
worker 正常循环、失败与停止的健康信号；不依赖实际容器。
"""

import asyncio
import time
from pathlib import Path

import pytest

from app.setup.build import Services
from shared.config.settings import Settings
from shared.jobs.health import WorkerHealth, worker_healthy
from tests.framework.test_jobs import make_worker

pytestmark = pytest.mark.anyio


# 健康有效期为正常轮询与容器检查留出余量。
def test_worker_poll_cannot_outlast_health_signal() -> None:
    with pytest.raises(ValueError, match="大 30 秒"):
        Settings(_env_file=None, job_health_file="/tmp/test-health", job_poll_seconds=120)
    settings = Settings(
        _env_file=None,
        job_health_file="/tmp/test-health",
        job_poll_seconds=120,
        job_health_seconds=180,
    )
    assert settings.job_health_seconds == 180


# 缺少、过期和损坏的信号失败，正常信号可读且可以清除。
def test_worker_signal_missing_stale_and_clear(tmp_path: Path) -> None:
    path = tmp_path / "worker.health"
    signal = WorkerHealth(str(path))
    assert not worker_healthy(str(path), 60)
    signal.touch()
    assert worker_healthy(str(path), 60)
    path.write_text(str(time.time() - 61))
    assert not worker_healthy(str(path), 60)
    path.write_text("nan")
    assert not worker_healthy(str(path), 60)
    signal.clear()
    assert not path.exists()


# 正常空队列也健康，领取失败不报告成功循环。
@pytest.mark.parametrize("failed", [False, True])
async def test_worker_only_signals_after_successful_loop(
    sample: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed: bool
) -> None:
    worker = make_worker(sample)
    path = tmp_path / "worker.health"
    worker.health = WorkerHealth(str(path))
    stop = asyncio.Event()

    # 让一轮循环结束，按参数模拟正常空队列或数据库失败。
    async def claim(now: float) -> None:
        stop.set()
        if failed:
            raise ConnectionError("合成数据库暂时不可用")

    monkeypatch.setattr(worker.queue, "claim", claim)
    await worker.loop(stop)
    assert worker_healthy(str(path), 60) is not failed


# 停止时移除旧信号，不能把已退出的进程当作近期健康。
async def test_worker_stop_removes_previous_health(sample: Services, tmp_path: Path) -> None:
    worker = make_worker(sample)
    path = tmp_path / "worker.health"
    worker.health = WorkerHealth(str(path))
    worker.health.touch()
    stop = asyncio.Event()
    stop.set()
    await worker.run(stop)
    assert not path.exists()
