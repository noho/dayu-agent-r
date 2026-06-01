"""WU-STRESS-01 Host production stress suite 哨兵测试。"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from dayu.host import HostEventKind, HostTerminalStatus
from tests.host.stress_support import (
    HostStressSummary,
    StressTerminalObservation,
    assert_summary_ok,
    summary_to_json,
    terminal_dedupe_ok,
    terminal_duplicate_count,
)

pytestmark = pytest.mark.stress

_SUMMARY_JSON_PROPERTY = "host_stress_summary"
_SCENARIO_NAME = "slice1-sentinel"
_SUMMARY_JSON_FIELDS: tuple[str, ...] = (
    "crash_count",
    "failure_boundary",
    "liveness_stale_detected",
    "recovery_count",
    "run_count",
    "scenario_name",
    "scheduler_drained",
    "session_count",
    "terminal_dedupe_ok",
    "terminal_duplicate_count",
    "watch_lag_max",
    "watch_lag_samples",
)


@pytest.mark.timeout(5)
def test_stress_marker_summary_contract(
    record_property: Callable[[str, str], None],
) -> None:
    """验证 stress summary JSON 字段和 terminal 去重 helper 基础契约。

    :param record_property: pytest 属性记录 fixture。
    :returns: ``None``。
    :raises AssertionError: summary 字段缺失或 terminal helper 行为不符时抛出。
    """

    duplicate_observations = (
        StressTerminalObservation(
            run_id="run-1",
            event_id="event-1",
            event_sequence=1,
            terminal_kind=HostEventKind.SUCCEEDED,
            terminal_status=HostTerminalStatus.SUCCEEDED,
        ),
        StressTerminalObservation(
            run_id="run-1",
            event_id="event-2",
            event_sequence=2,
            terminal_kind=HostEventKind.SUCCEEDED,
            terminal_status=HostTerminalStatus.SUCCEEDED,
        ),
    )
    assert terminal_duplicate_count(duplicate_observations) == 1
    assert not terminal_dedupe_ok(duplicate_observations)

    summary = HostStressSummary(
        scenario_name=_SCENARIO_NAME,
        session_count=1,
        run_count=1,
        crash_count=0,
        recovery_count=0,
        watch_lag_max=0,
        watch_lag_samples=(0,),
        scheduler_drained=True,
        liveness_stale_detected=False,
        terminal_duplicate_count=0,
        terminal_dedupe_ok=True,
        failure_boundary=None,
    )
    summary_json = summary_to_json(summary)
    record_property(_SUMMARY_JSON_PROPERTY, summary_json)

    for field_name in _SUMMARY_JSON_FIELDS:
        assert f'"{field_name}"' in summary_json
    assert f'"scenario_name": "{_SCENARIO_NAME}"' in summary_json
    assert_summary_ok(summary)
