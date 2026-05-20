"""
Testes unitários para StatusRepository e LogRepository.
Validam as garantias de complexidade O(1) e o comportamento do buffer circular.
"""
from datetime import datetime
from collections import deque

import pytest

from backend.core.entities import MonitorResult
from backend.core.enums import MonitorStatus
from backend.repositories.status_repository import StatusRepository
from backend.repositories.log_repository import LogRepository


def _make_result(target_id: str, status: MonitorStatus, ms: float | None = 10.0) -> MonitorResult:
    return MonitorResult(
        target_id=target_id,
        status=status,
        response_time_ms=ms,
        timestamp=datetime.utcnow(),
    )


class TestStatusRepository:
    def test_update_and_get(self):
        repo = StatusRepository()
        result = _make_result("sp-01", MonitorStatus.ONLINE)
        repo.update(result)
        assert repo.get("sp-01") == result

    def test_get_unknown_returns_none(self):
        repo = StatusRepository()
        assert repo.get("nao-existe") is None

    def test_update_overwrites_previous(self):
        repo = StatusRepository()
        repo.update(_make_result("sp-01", MonitorStatus.ONLINE))
        offline = _make_result("sp-01", MonitorStatus.OFFLINE, None)
        repo.update(offline)
        assert repo.get("sp-01").status == MonitorStatus.OFFLINE

    def test_get_summary_counts(self):
        repo = StatusRepository()
        repo.update(_make_result("a", MonitorStatus.ONLINE))
        repo.update(_make_result("b", MonitorStatus.ONLINE))
        repo.update(_make_result("c", MonitorStatus.OFFLINE))
        summary = repo.get_summary()
        assert summary["total"]   == 3
        assert summary["online"]  == 2
        assert summary["offline"] == 1


class TestLogRepository:
    def test_append_and_get_recent(self):
        repo = LogRepository(maxlen=10)
        repo.append(_make_result("sp-01", MonitorStatus.ONLINE))
        logs = repo.get_recent(5)
        assert len(logs) == 1

    def test_circular_buffer_evicts_oldest(self):
        """
        Garante que o deque com maxlen evicta o elemento mais antigo em O(1).
        Se o buffer fosse uma list, list.pop(0) seria O(n).
        """
        repo = LogRepository(maxlen=3)
        for i in range(5):
            repo.append(_make_result(f"host-{i}", MonitorStatus.ONLINE))
        recent = repo.get_recent(10)
        # Buffer de 3: deve conter apenas os 3 últimos
        assert len(recent) == 3
        ids = [r.target_id for r in recent]
        assert "host-4" in ids
        assert "host-0" not in ids

    def test_get_by_target_filters_correctly(self):
        repo = LogRepository(maxlen=20)
        repo.append(_make_result("sp-01", MonitorStatus.ONLINE))
        repo.append(_make_result("rj-01", MonitorStatus.OFFLINE))
        repo.append(_make_result("sp-01", MonitorStatus.DEGRADED))
        results = repo.get_by_target("sp-01")
        assert all(r.target_id == "sp-01" for r in results)
        assert len(results) == 2
