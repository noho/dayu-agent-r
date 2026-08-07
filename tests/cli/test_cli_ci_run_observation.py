"""CLI CI Host Run terminal observation helper 的 owner contract 测试。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.api import RunStatus
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.lifecycle_events import HostRunEventType
from utils.cli_ci_run_observation import (
    DependencyGateStatus,
    HarnessActionControl,
    HarnessActionRole,
    PublicEvidenceSecretProbe,
    RemainingActionDisposition,
    RunObservationError,
    RunEvidenceStatus,
    RunObservationRole,
    RunObservationWindow,
    classify_remaining_actions_for_safe_stop,
    classify_required_run_evidence,
    dependent_action_accepted_ordinal,
    evaluate_success_dependency,
    observe_run_terminals,
    run_observation_role_for_harness_action,
    scan_public_evidence_files,
    validate_terminal_class_summary,
    write_final_publication_scan_report,
)

_SESSION_ID = "session-cli-ci-observation"


def test_terminal_projection_keeps_each_canonical_terminal_and_reason(
    tmp_path: Path,
) -> None:
    """helper 必须分页投影四类 terminal，并保持 lost 独立。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: terminal/reason/顺序投影错误时抛出。
    """

    options = _options(tmp_path)
    end_sequence = 0
    terminals = (
        HostRunEventType.RUN_SUCCEEDED,
        HostRunEventType.RUN_FAILED,
        HostRunEventType.RUN_CANCELLED,
        HostRunEventType.RUN_LOST,
    )
    with open_host_durable_store(options) as store:

        def seed(transaction: HostTransaction) -> int:
            """写入四个完整 Run 与不相关 lifecycle rows。

            :param transaction: Host write transaction。
            :returns: frozen end sequence。
            """

            event_log = EventLogStore()
            latest = 0
            for ordinal, terminal_type in enumerate(terminals, start=1):
                run_id = f"run-{ordinal}"
                _append(
                    transaction,
                    event_log,
                    event_id=f"accepted-{ordinal}",
                    run_id=run_id,
                    event_type=HostRunEventType.RUN_ACCEPTED.value,
                    reason=None,
                )
                _append(
                    transaction,
                    event_log,
                    event_id=f"started-{ordinal}",
                    run_id=run_id,
                    event_type=HostRunEventType.RUN_STARTED.value,
                    reason=None,
                )
                terminal = _append(
                    transaction,
                    event_log,
                    event_id=f"terminal-{ordinal}",
                    run_id=run_id,
                    event_type=terminal_type.value,
                    reason=(
                        {
                            "reason": f"reason-{ordinal}",
                            "mode": "graceful",
                        }
                        if terminal_type is HostRunEventType.RUN_CANCELLED
                        else (
                            {
                                "reason": f"reason-{ordinal}",
                                "orphan_proof": "owner_pid_missing",
                            }
                            if terminal_type is HostRunEventType.RUN_LOST
                            else {"reason": f"reason-{ordinal}"}
                        )
                    ),
                )
                latest = terminal.event_sequence
            return latest

        end_sequence = store.transaction_runner.run_write(seed)

    observed = observe_run_terminals(
        db_path=options.db_path,
        artifact_root=options.payload_policy.artifact_root,
        window=RunObservationWindow(
            start_event_sequence=0,
            end_event_sequence=end_sequence,
            session_id=_SESSION_ID,
        ),
        roles_by_accepted_ordinal={
            1: RunObservationRole.REQUIRED,
            2: RunObservationRole.DEPENDENT,
            3: RunObservationRole.INDEPENDENT,
            4: RunObservationRole.REQUIRED,
        },
        page_size=1,
    )

    assert tuple(run.terminal_event_type for run in observed.runs) == terminals
    assert tuple(run.terminal_class for run in observed.runs) == (
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.LOST,
    )
    assert tuple(run.public_outbox_terminal for run in observed.runs) == (
        True,
        True,
        True,
        False,
    )
    assert tuple(run.reason for run in observed.runs) == (
        "reason-1",
        "reason-2",
        "reason-3",
        "reason-4",
    )
    assert observed.runs[-1].terminal_class is RunStatus.LOST
    assert observed.runs[-1].public_outbox_terminal is False
    observed_json = observed.to_json()
    assert isinstance(observed_json, dict)
    assert observed_json["summary"] == {
        "accepted": 4,
        "succeeded": 1,
        "failed": 1,
        "cancelled": 1,
        "lost": 1,
        "missing": 0,
        "invalid": 0,
    }


@pytest.mark.parametrize(
    ("reason", "payload", "expected"),
    (
        (None, {"reason": "payload-fallback-forbidden"}, "missing"),
        ({"why": "wrong-key"}, {}, "exact reason key"),
        ({"reason": "ok", "extra": "forbidden"}, {}, "exact reason key"),
        ({"reason": "   "}, {}, "non-empty string"),
        ({"reason": 3}, {}, "non-empty string"),
        (["reason", "wrong-shape"], {}, "must be object"),
    ),
)
def test_terminal_reason_rejects_missing_extra_blank_or_wrong_typed_object(
    tmp_path: Path,
    reason: JsonValue,
    payload: JsonValue,
    expected: str,
) -> None:
    """terminal reason 只接受 exact object，且绝不回退 payload。

    :param tmp_path: pytest 临时目录。
    :param reason: terminal reason JSON value。
    :param payload: terminal payload JSON value。
    :param expected: 期望错误片段。
    :returns: ``None``。
    :raises AssertionError: helper 未 fail closed 时抛出。
    """

    options = _options(tmp_path)
    end_sequence = 0
    with open_host_durable_store(options) as store:

        def seed(transaction: HostTransaction) -> int:
            """写入一个 reason shape 非法的 terminal。

            :param transaction: Host write transaction。
            :returns: frozen end sequence。
            """

            event_log = EventLogStore()
            _append(
                transaction,
                event_log,
                event_id="accepted-invalid-reason",
                run_id="run-invalid-reason",
                event_type=HostRunEventType.RUN_ACCEPTED.value,
                reason=None,
            )
            terminal = _append(
                transaction,
                event_log,
                event_id="terminal-invalid-reason",
                run_id="run-invalid-reason",
                event_type=HostRunEventType.RUN_FAILED.value,
                reason=reason,
                payload=payload,
            )
            return terminal.event_sequence

        end_sequence = store.transaction_runner.run_write(seed)

    with pytest.raises(RunObservationError, match=expected):
        observe_run_terminals(
            db_path=options.db_path,
            artifact_root=options.payload_policy.artifact_root,
            window=RunObservationWindow(0, end_sequence, _SESSION_ID),
            roles_by_accepted_ordinal={1: RunObservationRole.REQUIRED},
        )


def test_second_same_or_different_run_terminal_is_invalid(
    tmp_path: Path,
) -> None:
    """同一 Run 的第二条 terminal canonical fact 必须 observation-invalid。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: duplicate terminal 被接受时抛出。
    """

    options = _options(tmp_path)
    end_sequence = 0
    with open_host_durable_store(options) as store:

        def seed(transaction: HostTransaction) -> int:
            """写入同 Run 的两条 terminal facts。

            :param transaction: Host write transaction。
            :returns: frozen end sequence。
            """

            event_log = EventLogStore()
            _append(
                transaction,
                event_log,
                event_id="accepted-duplicate-terminal",
                run_id="run-duplicate-terminal",
                event_type=HostRunEventType.RUN_ACCEPTED.value,
                reason=None,
            )
            _append(
                transaction,
                event_log,
                event_id="terminal-duplicate-failed",
                run_id="run-duplicate-terminal",
                event_type=HostRunEventType.RUN_FAILED.value,
                reason={"reason": "first"},
            )
            second = _append(
                transaction,
                event_log,
                event_id="terminal-duplicate-lost",
                run_id="run-duplicate-terminal",
                event_type=HostRunEventType.RUN_LOST.value,
                reason={"reason": "second"},
            )
            return second.event_sequence

        end_sequence = store.transaction_runner.run_write(seed)

    with pytest.raises(RunObservationError, match="duplicate terminal"):
        observe_run_terminals(
            db_path=options.db_path,
            artifact_root=options.payload_policy.artifact_root,
            window=RunObservationWindow(0, end_sequence, _SESSION_ID),
            roles_by_accepted_ordinal={1: RunObservationRole.REQUIRED},
        )


def test_terminal_reason_rejects_malformed_json(tmp_path: Path) -> None:
    """物理损坏的 terminal reason JSON 必须 observation-invalid。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: malformed JSON 被接受时抛出。
    """

    options = _options(tmp_path)
    end_sequence = 0
    with open_host_durable_store(options) as store:

        def seed(transaction: HostTransaction) -> int:
            """写入 terminal 后模拟持久化 reason_json 损坏。

            :param transaction: Host write transaction。
            :returns: frozen end sequence。
            """

            event_log = EventLogStore()
            _append(
                transaction,
                event_log,
                event_id="accepted-malformed-reason",
                run_id="run-malformed-reason",
                event_type=HostRunEventType.RUN_ACCEPTED.value,
                reason=None,
            )
            terminal = _append(
                transaction,
                event_log,
                event_id="terminal-malformed-reason",
                run_id="run-malformed-reason",
                event_type=HostRunEventType.RUN_FAILED.value,
                reason={"reason": "before-corruption"},
            )
            transaction.execute(
                "UPDATE event_log SET reason_json = ? WHERE event_id = ?",
                ("{malformed", terminal.event_id),
            )
            return terminal.event_sequence

        end_sequence = store.transaction_runner.run_write(seed)

    with pytest.raises(RunObservationError, match="malformed"):
        observe_run_terminals(
            db_path=options.db_path,
            artifact_root=options.payload_policy.artifact_root,
            window=RunObservationWindow(0, end_sequence, _SESSION_ID),
            roles_by_accepted_ordinal={1: RunObservationRole.REQUIRED},
        )


@pytest.mark.parametrize(
    ("terminal_type", "reason", "expected"),
    (
        (
            HostRunEventType.RUN_CANCELLED,
            {"reason": "cancelled", "mode": "force"},
            "mode is invalid",
        ),
        (
            HostRunEventType.RUN_CANCELLED,
            {"reason": "cancelled", "unknown": "value"},
            "unknown canonical keys",
        ),
        (
            HostRunEventType.RUN_LOST,
            {"reason": "lost", "orphan_proof": "   "},
            "orphan_proof is invalid",
        ),
        (
            HostRunEventType.RUN_LOST,
            {"reason": "lost", "unknown": "value"},
            "unknown canonical keys",
        ),
    ),
)
def test_cancel_and_lost_reason_shapes_reject_unknown_or_invalid_extras(
    tmp_path: Path,
    terminal_type: HostRunEventType,
    reason: JsonValue,
    expected: str,
) -> None:
    """cancel/lost 只接受各自已知治理字段，不接受任意 extra。

    :param tmp_path: pytest 临时目录。
    :param terminal_type: 被测 Run terminal type。
    :param reason: 被测 canonical reason JSON value。
    :param expected: 期望错误片段。
    :returns: ``None``。
    :raises AssertionError: 非法 event-specific shape 被接受时抛出。
    """

    options = _options(tmp_path)
    end_sequence = 0
    with open_host_durable_store(options) as store:

        def seed(transaction: HostTransaction) -> int:
            """写入一个 governance extra 非法的 terminal。

            :param transaction: Host write transaction。
            :returns: frozen end sequence。
            """

            event_log = EventLogStore()
            _append(
                transaction,
                event_log,
                event_id="accepted-invalid-extra",
                run_id="run-invalid-extra",
                event_type=HostRunEventType.RUN_ACCEPTED.value,
                reason=None,
            )
            terminal = _append(
                transaction,
                event_log,
                event_id="terminal-invalid-extra",
                run_id="run-invalid-extra",
                event_type=terminal_type.value,
                reason=reason,
            )
            return terminal.event_sequence

        end_sequence = store.transaction_runner.run_write(seed)

    with pytest.raises(RunObservationError, match=expected):
        observe_run_terminals(
            db_path=options.db_path,
            artifact_root=options.payload_policy.artifact_root,
            window=RunObservationWindow(0, end_sequence, _SESSION_ID),
            roles_by_accepted_ordinal={1: RunObservationRole.REQUIRED},
        )


def test_process_exit_zero_does_not_satisfy_failed_run_dependency(
    tmp_path: Path,
) -> None:
    """process exit 0 不参与 dependency gate；failed Run 必须停止依赖链。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: failed Run 被 process outcome 覆盖时抛出。
    """

    options = _options(tmp_path)
    end_sequence = 0
    with open_host_durable_store(options) as store:

        def seed(transaction: HostTransaction) -> int:
            """写入一个 failed Run。

            :param transaction: Host write transaction。
            :returns: frozen end sequence。
            """

            event_log = EventLogStore()
            _append(
                transaction,
                event_log,
                event_id="accepted-failed-dependency",
                run_id="run-failed-dependency",
                event_type=HostRunEventType.RUN_ACCEPTED.value,
                reason=None,
            )
            terminal = _append(
                transaction,
                event_log,
                event_id="terminal-failed-dependency",
                run_id="run-failed-dependency",
                event_type=HostRunEventType.RUN_FAILED.value,
                reason={"reason": "runner_candidate_invalid"},
            )
            return terminal.event_sequence

        end_sequence = store.transaction_runner.run_write(seed)

    process_exit_code = 0
    observed = observe_run_terminals(
        db_path=options.db_path,
        artifact_root=options.payload_policy.artifact_root,
        window=RunObservationWindow(0, end_sequence, _SESSION_ID),
        roles_by_accepted_ordinal={1: RunObservationRole.REQUIRED},
    )
    decision = evaluate_success_dependency(
        observed.runs[0],
        required_success_accepted_ordinal=1,
        deadline_reached=True,
    )

    assert process_exit_code == 0
    assert decision.status is DependencyGateStatus.STOPPED
    assert decision.upstream_terminal is RunStatus.FAILED
    assert decision.upstream_reason == "runner_candidate_invalid"


def test_missing_terminal_is_pending_before_deadline_and_invalid_afterward() -> None:
    """未观察到 terminal 时，等待期为 pending，deadline 后为 invalid。"""

    pending = evaluate_success_dependency(
        None,
        required_success_accepted_ordinal=7,
        deadline_reached=False,
    )
    invalid = evaluate_success_dependency(
        None,
        required_success_accepted_ordinal=7,
        deadline_reached=True,
    )

    assert pending.status is DependencyGateStatus.PENDING
    assert invalid.status is DependencyGateStatus.INVALID


def test_terminal_session_must_match_accepted_session(tmp_path: Path) -> None:
    """terminal 必须与 RUN_ACCEPTED 属于同一 canonical session。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 跨 session terminal 被错误配对时抛出。
    """

    options = _options(tmp_path)
    end_sequence = 0
    with open_host_durable_store(options) as store:

        def seed(transaction: HostTransaction) -> int:
            """写入 run_id 相同但 session 不同的 accepted/terminal。

            :param transaction: Host write transaction。
            :returns: frozen end sequence。
            """

            event_log = EventLogStore()
            _append(
                transaction,
                event_log,
                event_id="accepted-session-owner",
                run_id="run-session-mismatch",
                event_type=HostRunEventType.RUN_ACCEPTED.value,
                reason=None,
            )
            terminal = _append(
                transaction,
                event_log,
                event_id="terminal-other-session",
                run_id="run-session-mismatch",
                event_type=HostRunEventType.RUN_FAILED.value,
                reason={"reason": "wrong-session"},
                session_id="session-other",
            )
            return terminal.event_sequence

        end_sequence = store.transaction_runner.run_write(seed)

    with pytest.raises(RunObservationError, match="session_id"):
        observe_run_terminals(
            db_path=options.db_path,
            artifact_root=options.payload_policy.artifact_root,
            window=RunObservationWindow(0, end_sequence, None),
            roles_by_accepted_ordinal={1: RunObservationRole.REQUIRED},
        )


def test_safe_stop_classifies_dependents_and_sends_one_cleanup_eot() -> None:
    """stop/invalid 后必须记录所有 dependent not-run，且只发送一次 EOT。

    :returns: ``None``。
    :raises AssertionError: remaining action 分类或 EOT 唯一性错误时抛出。
    """

    decisions = classify_remaining_actions_for_safe_stop(
        (
            HarnessActionControl(2, HarnessActionRole.DEPENDENT, 2),
            HarnessActionControl(3, HarnessActionRole.DEPENDENT, 3),
            HarnessActionControl(4, HarnessActionRole.CLEANUP_EOT, None),
            HarnessActionControl(5, HarnessActionRole.CLEANUP_EOT, None),
        )
    )

    assert tuple(item.disposition for item in decisions) == (
        RemainingActionDisposition.NOT_RUN_DEPENDENT,
        RemainingActionDisposition.NOT_RUN_DEPENDENT,
        RemainingActionDisposition.SEND_CLEANUP_EOT,
        RemainingActionDisposition.NOT_RUN_PROCESS_STOP,
    )


def test_upstream_to_dependent_ordinal_and_independent_role_are_explicit() -> None:
    """ordinal 转换必须由 pure helper owner，independent role 保持可用。

    :returns: ``None``。
    :raises AssertionError: ordinal 或 reusable independent role 漂移时抛出。
    """

    assert dependent_action_accepted_ordinal(7) == 8
    control = HarnessActionControl(0, HarnessActionRole.INDEPENDENT, None)
    assert run_observation_role_for_harness_action(control.role) is (
        RunObservationRole.INDEPENDENT
    )


@pytest.mark.parametrize(
    ("terminal_statuses", "expected"),
    (
        ((RunStatus.SUCCEEDED,), RunEvidenceStatus.COMPLETE),
        ((RunStatus.FAILED,), RunEvidenceStatus.INSUFFICIENT),
        ((RunStatus.CANCELLED, RunStatus.SUCCEEDED), RunEvidenceStatus.INSUFFICIENT),
        (None, RunEvidenceStatus.INVALID),
        ((), RunEvidenceStatus.INVALID),
    ),
)
def test_required_run_evidence_distinguishes_complete_insufficient_and_invalid(
    terminal_statuses: tuple[RunStatus, ...] | None,
    expected: RunEvidenceStatus,
) -> None:
    """valid non-success 必须 insufficient，只有完整成功才 complete。

    :param terminal_statuses: required/dependent terminal statuses 或 invalid marker。
    :param expected: 期望 evidence integrity status。
    :returns: ``None``。
    :raises AssertionError: evidence status 分类漂移时抛出。
    """

    assert classify_required_run_evidence(terminal_statuses) is expected


def test_public_scan_does_not_treat_ordinary_local_paths_as_secrets(
    tmp_path: Path,
) -> None:
    """repo/run/corpus路径属于普通evidence内容，不得伪装成credential泄漏。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 普通本机路径造成secret/path误报时抛出。
    """

    evidence_root = tmp_path / "run"
    evidence_root.mkdir()
    command_record = evidence_root / "command.json"
    command_record.write_text(
        '{"cwd":"/Users/leo/workspace/dayu-agent-r",'
        '"corpus":"/Users/leo/workspace/.dayu-cli-ci/corpus"}',
        encoding="utf-8",
    )

    result = scan_public_evidence_files(
        evidence_root=evidence_root,
        files=(command_record,),
        exact_secret_probes=(
            PublicEvidenceSecretProbe("provider_api_key", "fixture-secret-value"),
        ),
    )

    assert result.to_json() == {
        "status": "complete",
        "scanned_file_count": 1,
        "scanned_byte_count": command_record.stat().st_size,
        "files": list(result.file_descriptors),
        "secret_scan": {"status": "complete", "hits": []},
        "path_hygiene": {"status": "complete", "violations": []},
        "validation_errors": [],
    }


def test_public_scan_detects_injected_exact_secret(tmp_path: Path) -> None:
    """实际secret值进入public evidence时必须由exact probe判invalid。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 注入secret未命中或scan未invalid时抛出。
    """

    evidence_root = tmp_path / "run"
    evidence_root.mkdir()
    public_record = evidence_root / "public.json"
    public_record.write_text(
        '{"accidental":"fixture-secret-value"}',
        encoding="utf-8",
    )

    result = scan_public_evidence_files(
        evidence_root=evidence_root,
        files=(public_record,),
        exact_secret_probes=(
            PublicEvidenceSecretProbe("provider_api_key", "fixture-secret-value"),
        ),
    )
    payload = result.to_json()

    assert isinstance(payload, dict)
    assert payload["status"] == "invalid"
    assert payload["secret_scan"] == {
        "status": "invalid",
        "hits": [
            {
                "path": "public.json",
                "match_kind": "exact_value",
                "probe": "provider_api_key",
            }
        ],
    }


def test_public_path_hygiene_detects_raw_database_and_symlink(
    tmp_path: Path,
) -> None:
    """public evidence中的raw DB文件、路径与symlink必须由扫描事实判invalid。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 任一raw DB/path/symlink未被path hygiene拒绝时抛出。
    """

    evidence_root = tmp_path / "run"
    evidence_root.mkdir()
    raw_database = evidence_root / "host.sqlite3"
    raw_database.write_bytes(b"sqlite fixture")
    path_record = evidence_root / "manifest.json"
    path_record.write_text(
        '{"raw_store":"/private/tmp/dayu/host.db"}',
        encoding="utf-8",
    )
    symlink_record = evidence_root / "linked.json"
    symlink_record.symlink_to(path_record)
    actual_directory = evidence_root / "actual-directory"
    actual_directory.mkdir()
    nested_record = actual_directory / "nested.json"
    nested_record.write_text('{"status":"complete"}', encoding="utf-8")
    symlink_directory = evidence_root / "linked-directory"
    symlink_directory.symlink_to(actual_directory, target_is_directory=True)

    result = scan_public_evidence_files(
        evidence_root=evidence_root,
        files=(
            raw_database,
            path_record,
            symlink_record,
            symlink_directory / "nested.json",
        ),
        exact_secret_probes=(),
    )
    reasons: set[str] = set()
    for violation in result.path_hygiene_violations:
        if not isinstance(violation, dict):
            continue
        reason = violation.get("reason")
        if isinstance(reason, str):
            reasons.add(reason)
    payload = result.to_json()

    assert isinstance(payload, dict)
    assert payload["status"] == "invalid"
    assert reasons == {
        "raw_database_file_forbidden",
        "raw_database_path_forbidden",
        "symlink_forbidden",
    }
    symlink_paths: set[str] = set()
    for violation in result.path_hygiene_violations:
        if not isinstance(violation, dict):
            continue
        path = violation.get("path")
        if (
            violation.get("reason") == "symlink_forbidden"
            and isinstance(path, str)
        ):
            symlink_paths.add(path)
    assert symlink_paths == {"linked.json", "linked-directory/nested.json"}


def test_final_publication_scan_covers_final_metadata_and_only_excludes_report(
    tmp_path: Path,
) -> None:
    """final completion/index必须进入descriptors，唯独absent report可自排除。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: final tree枚举遗漏或额外排除文件时抛出。
    """

    evidence_root = tmp_path / "evidence"
    public_root = evidence_root / "public"
    scenario_root = evidence_root / "scenario-001"
    public_root.mkdir(parents=True)
    scenario_root.mkdir()
    completion = evidence_root / "run-completion.json"
    execution_index = evidence_root / "execution-index-f15-f16.json"
    stdout_record = scenario_root / "stdout.txt"
    completion.write_text(
        '{"secret_scan":{"record_path":"evidence/public/secret-scan.json"}}',
        encoding="utf-8",
    )
    execution_index.write_text(
        '{"secret_scan":{"record_path":"evidence/public/secret-scan.json"}}',
        encoding="utf-8",
    )
    stdout_record.write_text("redacted output", encoding="utf-8")
    report_path = public_root / "secret-scan.json"

    write_final_publication_scan_report(
        evidence_root=evidence_root,
        report_path=report_path,
        exact_secret_probes=(),
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    descriptors = payload.get("files")
    assert isinstance(descriptors, list)
    descriptor_paths = {
        descriptor.get("path")
        for descriptor in descriptors
        if isinstance(descriptor, dict)
    }
    assert descriptor_paths == {
        "execution-index-f15-f16.json",
        "run-completion.json",
        "scenario-001/stdout.txt",
    }
    assert payload["scanned_file_count"] == 3
    assert "public/secret-scan.json" not in descriptor_paths


def test_final_publication_scan_rejects_existing_stale_report(
    tmp_path: Path,
) -> None:
    """既有或stale scan report必须fail closed且不得被覆盖。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: stale report被复用、覆盖或未拒绝时抛出。
    """

    evidence_root = tmp_path / "evidence"
    public_root = evidence_root / "public"
    public_root.mkdir(parents=True)
    report_path = public_root / "secret-scan.json"
    stale_report = '{"status":"stale"}\n'
    report_path.write_text(stale_report, encoding="utf-8")

    with pytest.raises(
        RunObservationError,
        match="must not already exist",
    ):
        write_final_publication_scan_report(
            evidence_root=evidence_root,
            report_path=report_path,
            exact_secret_probes=(),
        )

    assert report_path.read_text(encoding="utf-8") == stale_report


def test_final_publication_scan_rejects_traversal_and_outside_report(
    tmp_path: Path,
) -> None:
    """report target的lexical traversal与resolved root逃逸必须fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: traversal或outside target未在owner boundary拒绝时抛出。
    """

    evidence_root = tmp_path / "evidence"
    (evidence_root / "public").mkdir(parents=True)
    traversal_report = (
        evidence_root / "public" / ".." / ".." / "secret-scan.json"
    )
    outside_report = tmp_path / "outside" / "secret-scan.json"
    actual_report_directory = evidence_root / "actual-report-directory"
    actual_report_directory.mkdir()
    symlink_report_directory = evidence_root / "linked-report-directory"
    symlink_report_directory.symlink_to(
        actual_report_directory,
        target_is_directory=True,
    )
    symlink_ancestor_report = symlink_report_directory / "secret-scan.json"

    with pytest.raises(ValueError, match="path traversal"):
        write_final_publication_scan_report(
            evidence_root=evidence_root,
            report_path=traversal_report,
            exact_secret_probes=(),
        )
    with pytest.raises(ValueError, match="inside evidence_root"):
        write_final_publication_scan_report(
            evidence_root=evidence_root,
            report_path=outside_report,
            exact_secret_probes=(),
        )
    with pytest.raises(RunObservationError, match="ancestor symlink"):
        write_final_publication_scan_report(
            evidence_root=evidence_root,
            report_path=symlink_ancestor_report,
            exact_secret_probes=(),
        )

    assert not (tmp_path / "secret-scan.json").exists()
    assert not outside_report.exists()
    assert not (actual_report_directory / "secret-scan.json").exists()


def test_final_publication_scan_enumerates_secret_database_and_symlink_candidates(
    tmp_path: Path,
) -> None:
    """final-tree orchestration不得遗漏secret、raw DB或symlink候选。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 任一既有scanner行为未进入final report时抛出。
    """

    evidence_root = tmp_path / "evidence"
    public_root = evidence_root / "public"
    public_root.mkdir(parents=True)
    secret_record = evidence_root / "secret.txt"
    secret_record.write_text("fixture-secret-value", encoding="utf-8")
    raw_database = evidence_root / "host.sqlite3"
    raw_database.write_bytes(b"sqlite fixture")
    path_record = evidence_root / "manifest.json"
    path_record.write_text(
        '{"raw_store":"/private/tmp/dayu/host.db"}',
        encoding="utf-8",
    )
    symlink_record = evidence_root / "linked.json"
    symlink_record.symlink_to(path_record)
    report_path = public_root / "secret-scan.json"

    write_final_publication_scan_report(
        evidence_root=evidence_root,
        report_path=report_path,
        exact_secret_probes=(
            PublicEvidenceSecretProbe(
                "provider_api_key",
                "fixture-secret-value",
            ),
        ),
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["status"] == "invalid"
    secret_scan = payload.get("secret_scan")
    path_hygiene = payload.get("path_hygiene")
    assert isinstance(secret_scan, dict)
    assert isinstance(path_hygiene, dict)
    assert secret_scan["hits"] == [
        {
            "match_kind": "exact_value",
            "path": "secret.txt",
            "probe": "provider_api_key",
        }
    ]
    reasons: set[str] = set()
    violations = path_hygiene.get("violations")
    assert isinstance(violations, list)
    for violation in violations:
        if not isinstance(violation, dict):
            continue
        reason = violation.get("reason")
        if isinstance(reason, str):
            reasons.add(reason)
    assert reasons == {
        "raw_database_file_forbidden",
        "raw_database_path_forbidden",
        "symlink_forbidden",
    }


def test_terminal_class_summary_requires_exact_per_run_distribution() -> None:
    """summary总数相等但逐类分布矛盾时也必须observation-invalid。

    :returns: ``None``。
    :raises AssertionError: failed/lost错配未被exact对账拒绝时抛出。
    """

    validate_terminal_class_summary(
        accepted=4,
        succeeded=1,
        failed=1,
        cancelled=1,
        lost=1,
        terminal_statuses=(
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.LOST,
        ),
    )
    with pytest.raises(RunObservationError, match="classes do not match"):
        validate_terminal_class_summary(
            accepted=4,
            succeeded=1,
            failed=1,
            cancelled=1,
            lost=1,
            terminal_statuses=(
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.CANCELLED,
            ),
        )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 observation helper 测试用 Host durable options。

    :param tmp_path: pytest 临时目录。
    :returns: fresh durable options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(),
    )


def _append(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    run_id: str,
    event_type: str,
    reason: JsonValue,
    payload: JsonValue | None = None,
    session_id: str = _SESSION_ID,
) -> EventLogRow:
    """追加 CLI observation 测试用 canonical fact。

    :param transaction: Host write transaction。
    :param event_log: EventLog store。
    :param event_id: event identity。
    :param run_id: Run identity。
    :param event_type: lifecycle event type。
    :param reason: reason JSON value；``None`` 表示未写 reason。
    :param payload: 可选 payload JSON value。
    :param session_id: canonical session identity。
    :returns: appended row。
    """

    return event_log.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=session_id,
            run_id=run_id,
            attempt_id=None,
            execution_id=None,
            event_type=event_type,
            occurred_at=datetime(2026, 8, 7, tzinfo=UTC),
            actor="host",
            source="test",
            client_request_id=None,
            idempotency_key=f"idempotency:{event_id}",
            policy_decision=None,
            reason=reason,
            payload_json={} if payload is None else payload,
            payload_ref=None,
            payload_digest=None,
        ),
    ).row
