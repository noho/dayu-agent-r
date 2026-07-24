"""Tool Trace Analyzer trusted input snapshot 与完整性边界测试。"""

from __future__ import annotations

import json
import io
import os
import shutil
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, NoReturn

import pytest

import dayu.host as host_public
import dayu.host.tool_trace_analysis_input as input_module
from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    append_event,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_HOST_TOOL_TRACE_HOT
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.tool_trace import (
    ToolTraceSinkOptions,
    _tool_trace_cold_lock_path,
    catch_up_tool_trace_projection,
)
from dayu.host.tool_trace_analysis_contracts import (
    ToolTraceAnalysisPolicy,
    ToolTraceAnalysisSource,
    ToolTraceInputMode,
)
from dayu.host.tool_trace_analysis_input import (
    ToolTraceAnalysisDataset,
    ToolTraceAnalysisInputError,
    ToolTraceAnalysisInputFailureReason,
    ToolTraceInputDiagnosticCode,
    load_tool_trace_analysis_input,
)
from dayu.runtime.filelock import (
    RuntimeFileLockError,
    RuntimeFileLockTimeoutError,
)

_FIXED_NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)


class _FailingCloseReader(io.BufferedReader):
    """用于证明 cold handle close failure fatal 的 binary reader。"""

    def close(self) -> None:
        """模拟 close 失败。

        :returns: 永不返回。
        :raises OSError: 始终抛出。
        """

        raise OSError("close failed")

    def force_close(self) -> None:
        """绕过模拟 override 关闭底层 reader。

        :returns: ``None``。
        :raises OSError: 真实 close 失败时抛出。
        """

        super().close()


def _workspace_paths(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path]:
    """返回测试 workspace、DB、artifact 与 cold 路径。

    :param tmp_path: pytest 临时目录。
    :returns: ``(workspace, db, artifact_root, cold_jsonl)``。
    :raises: 无。
    """

    workspace = (tmp_path / "workspace").absolute()
    artifact_root = workspace / ".dayu" / "artifacts"
    db_path = workspace / ".dayu" / "host" / "dayu_host.sqlite3"
    cold_path = artifact_root / "tool-trace" / "tool-trace-cold.jsonl"
    return workspace, db_path, artifact_root, cold_path


def _store_options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造与 workspace 输入布局一致的 durable options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    :raises ValueError: typed options 校验失败时抛出。
    """

    _, db_path, artifact_root, _ = _workspace_paths(tmp_path)
    return HostDurableStoreOptions(
        db_path=db_path,
        payload_policy=PayloadStoragePolicy(artifact_root=artifact_root),
        sqlite_policy=HostSQLiteStoragePolicy(),
    )


def _workspace_source(tmp_path: Path) -> ToolTraceAnalysisSource:
    """构造已存在 workspace 的五字段 Source。

    :param tmp_path: pytest 临时目录。
    :returns: workspace-directory Source。
    :raises ValueError: 测试布局尚未建立时抛出。
    """

    workspace, db_path, artifact_root, cold_path = _workspace_paths(tmp_path)
    return ToolTraceAnalysisSource(
        requested_path=workspace,
        mode=ToolTraceInputMode.WORKSPACE_DIRECTORY,
        cold_jsonl_path=cold_path,
        hot_db_path=db_path,
        artifact_root=artifact_root,
    )


def _append_trace_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
) -> None:
    """追加可由 production Tool Trace projection 消费的 lifecycle event。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: 测试 event id。
    :returns: ``None``。
    :raises Exception: durable append 失败时透传。
    """

    request = EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-analysis",
        run_id="run-analysis",
        attempt_id="attempt-analysis",
        execution_id="execution-analysis",
        event_type="RUN_SUCCEEDED",
        occurred_at=_FIXED_NOW,
        actor="host",
        source="analysis-input-test",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={"final_answer": f"answer:{event_id}"},
        payload_ref=None,
        payload_digest=None,
    )
    transaction_runner.run_write(lambda transaction: append_event(transaction, request))


def _catch_up_trace(
    transaction_runner: HostTransactionRunner,
    cold_path: Path,
) -> None:
    """使用 production projection 生成 hot/cold baseline。

    :param transaction_runner: Host durable transaction runner。
    :param cold_path: cold JSONL 路径。
    :returns: ``None``。
    :raises Exception: projection 失败时透传。
    """

    result = catch_up_tool_trace_projection(
        transaction_runner,
        options=ToolTraceSinkOptions(
            cold_jsonl_path=cold_path,
            lock_path=_tool_trace_cold_lock_path(cold_path),
        ),
    )
    assert result.failures == 0


def _build_workspace_baseline(
    tmp_path: Path,
    *,
    event_ids: tuple[str, ...] = ("event-1",),
) -> HostDurableStoreOptions:
    """通过 production projection 建立合法 Analyzer baseline。

    :param tmp_path: pytest 临时目录。
    :param event_ids: 依序追加的 event ids。
    :returns: durable options。
    :raises Exception: durable/projection 失败时透传。
    """

    options = _store_options(tmp_path)
    _, _, _, cold_path = _workspace_paths(tmp_path)
    with open_host_durable_store(options) as store:
        for event_id in event_ids:
            _append_trace_event(store.transaction_runner, event_id=event_id)
        _catch_up_trace(store.transaction_runner, cold_path)
    return options


def _load(source: ToolTraceAnalysisSource) -> ToolTraceAnalysisDataset:
    """使用默认 typed policies 读取 dataset。

    :param source: 显式输入来源。
    :returns: normalized dataset。
    :raises ToolTraceAnalysisInputError: 输入 fatal failure 时抛出。
    """

    return load_tool_trace_analysis_input(
        source,
        ToolTraceAnalysisPolicy(),
        HostSQLiteStoragePolicy(),
    )


def _read_cold_objects(cold_path: Path) -> list[dict[str, JsonValue]]:
    """读取 cold JSONL objects 的可变副本。

    :param cold_path: cold JSONL 路径。
    :returns: JSON object list。
    :raises OSError: 文件读取失败时抛出。
    :raises ValueError: 行不是 JSON object 时抛出。
    """

    objects: list[dict[str, JsonValue]] = []
    for line in cold_path.read_text(encoding="utf-8").splitlines():
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError("cold fixture line must be object")
        objects.append(parsed)
    return objects


def _write_cold_objects(
    cold_path: Path,
    objects: list[dict[str, JsonValue]],
) -> None:
    """写回 Analyzer 输入副本。

    :param cold_path: cold JSONL 路径。
    :param objects: JSON object list。
    :returns: ``None``。
    :raises OSError: 文件写入失败时抛出。
    """

    cold_path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(canonical_json_dumps(item) + "\n" for item in objects)
    cold_path.write_text(text, encoding="utf-8")


def _refresh_cold_integrity(
    item: dict[str, JsonValue],
    *,
    keep_ref: bool = False,
) -> None:
    """按 production preimage 重新计算 cold digest/ref。

    :param item: 待更新 cold object。
    :param keep_ref: 是否保留原 cold ref，用于 source conflict fixture。
    :returns: ``None``。
    :raises ValueError: event_id 不是文本时抛出。
    """

    event_id = item["event_id"]
    if not isinstance(event_id, str):
        raise ValueError("event_id must be text")
    preimage = {
        key: value
        for key, value in item.items()
        if key
        not in (
            "line_digest",
            "cold_trace_ref",
            "cold_trace_digest",
        )
    }
    digest = sha256_digest_json(preimage)
    item["line_digest"] = digest
    item["cold_trace_digest"] = digest
    if not keep_ref:
        item["cold_trace_ref"] = f"tool-trace-cold:{event_id}"


def _diagnostic_codes(
    dataset: ToolTraceAnalysisDataset,
) -> tuple[ToolTraceInputDiagnosticCode, ...]:
    """返回 dataset diagnostic codes。

    :param dataset: normalized dataset。
    :returns: 按产生顺序排列的 codes。
    :raises: 无。
    """

    return tuple(item.code for item in dataset.input_diagnostics)


def test_source_public_contract_has_exactly_five_fields_and_no_lock_export(
    tmp_path: Path,
) -> None:
    """public Source 只能有五个字段，Host root 不导出内部 lock helper。"""

    _build_workspace_baseline(tmp_path)
    source = _workspace_source(tmp_path)

    assert tuple(source.__dataclass_fields__) == (
        "requested_path",
        "mode",
        "cold_jsonl_path",
        "hot_db_path",
        "artifact_root",
    )
    assert "_tool_trace_cold_lock_path" not in host_public.__all__


def test_source_accepts_all_four_explicit_modes(tmp_path: Path) -> None:
    """四种模式必须使用各自唯一完整路径布局。"""

    _build_workspace_baseline(tmp_path)
    workspace, db_path, artifact_root, cold_path = _workspace_paths(tmp_path)
    dayu_source = ToolTraceAnalysisSource(
        requested_path=workspace / ".dayu",
        mode=ToolTraceInputMode.DAYU_DIRECTORY,
        cold_jsonl_path=cold_path,
        hot_db_path=db_path,
        artifact_root=artifact_root,
    )
    cold_source = ToolTraceAnalysisSource(
        requested_path=cold_path,
        mode=ToolTraceInputMode.COLD_FILE,
        cold_jsonl_path=cold_path,
        hot_db_path=None,
        artifact_root=None,
    )
    trace_directory = (tmp_path / "trace-only").absolute()
    trace_cold = trace_directory / "tool-trace-cold.jsonl"
    trace_directory.mkdir()
    shutil.copyfile(cold_path, trace_cold)
    trace_source = ToolTraceAnalysisSource(
        requested_path=trace_directory,
        mode=ToolTraceInputMode.TRACE_DIRECTORY,
        cold_jsonl_path=trace_cold,
        hot_db_path=None,
        artifact_root=None,
    )

    assert _workspace_source(tmp_path).mode is ToolTraceInputMode.WORKSPACE_DIRECTORY
    assert dayu_source.mode is ToolTraceInputMode.DAYU_DIRECTORY
    assert cold_source.mode is ToolTraceInputMode.COLD_FILE
    assert trace_source.mode is ToolTraceInputMode.TRACE_DIRECTORY


@pytest.mark.parametrize(
    ("mode", "hot_present", "artifact_present"),
    (
        (ToolTraceInputMode.COLD_FILE, True, False),
        (ToolTraceInputMode.TRACE_DIRECTORY, False, True),
    ),
)
def test_source_rejects_cold_only_capability_double_truth(
    tmp_path: Path,
    mode: ToolTraceInputMode,
    hot_present: bool,
    artifact_present: bool,
) -> None:
    """cold-only mode 不得通过 nullable 组合夹带 hot/artifact capability。"""

    requested = (tmp_path / "trace.jsonl").absolute()
    if mode is ToolTraceInputMode.TRACE_DIRECTORY:
        requested = (tmp_path / "trace-directory").absolute()
        requested.mkdir()
        cold_path = requested / "tool-trace-cold.jsonl"
    else:
        cold_path = requested
    cold_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        ToolTraceAnalysisSource(
            requested_path=requested,
            mode=mode,
            cold_jsonl_path=cold_path,
            hot_db_path=(tmp_path / "hot.sqlite3").absolute() if hot_present else None,
            artifact_root=(tmp_path / "artifacts").absolute() if artifact_present else None,
        )


def test_source_rejects_relative_wrong_layout_and_wrong_type(
    tmp_path: Path,
) -> None:
    """Source boundary 必须拒绝相对路径、错误 layout 与现存错误类型。"""

    _build_workspace_baseline(tmp_path)
    workspace, db_path, artifact_root, cold_path = _workspace_paths(tmp_path)
    with pytest.raises(ValueError, match="absolute"):
        ToolTraceAnalysisSource(
            requested_path=Path("workspace"),
            mode=ToolTraceInputMode.WORKSPACE_DIRECTORY,
            cold_jsonl_path=cold_path,
            hot_db_path=db_path,
            artifact_root=artifact_root,
        )
    with pytest.raises(ValueError, match="layout"):
        ToolTraceAnalysisSource(
            requested_path=workspace,
            mode=ToolTraceInputMode.WORKSPACE_DIRECTORY,
            cold_jsonl_path=(workspace / "wrong.jsonl"),
            hot_db_path=db_path,
            artifact_root=artifact_root,
        )
    cold_path.unlink()
    cold_path.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        _workspace_source(tmp_path)


def test_policy_rejects_bool_nonpositive_and_nonfinite_values() -> None:
    """Analyzer policy 必须严格拒绝 bool、非正数与非有限 multiplier。"""

    with pytest.raises(TypeError):
        ToolTraceAnalysisPolicy(large_payload_threshold_bytes=True)
    with pytest.raises(ValueError):
        ToolTraceAnalysisPolicy(payload_ranking_limit=0)
    with pytest.raises(ValueError):
        ToolTraceAnalysisPolicy(latency_outlier_multiplier=float("inf"))
    with pytest.raises(ValueError):
        ToolTraceAnalysisPolicy(latency_outlier_multiplier=1.0)


def test_valid_workspace_projection_joins_and_resolves_source_payload(
    tmp_path: Path,
) -> None:
    """production baseline 必须完成 hot/cold join 与 source payload resolution。"""

    _build_workspace_baseline(tmp_path)
    dataset = _load(_workspace_source(tmp_path))

    assert dataset.hot_store_available is True
    assert dataset.hot_event_sequence_watermark == 1
    assert len(dataset.hot_rows) == 1
    assert len(dataset.cold_records) == 1
    assert len(dataset.joined_records) == 1
    assert dataset.joined_records[0].resolved_payloads is not None
    assert dataset.input_diagnostics == ()
    assert dataset.limitations == ()
    assert dataset.cold_snapshot is not None
    assert dataset.cold_snapshot.cold_lock_path == _tool_trace_cold_lock_path(dataset.source.cold_jsonl_path)


@pytest.mark.parametrize(
    ("raw_line", "expected_code"),
    (
        ("not-json\n", ToolTraceInputDiagnosticCode.INVALID_JSON_LINE),
        ("[]\n", ToolTraceInputDiagnosticCode.NON_OBJECT_JSON_LINE),
        (
            '{"schema_version":2}\n',
            ToolTraceInputDiagnosticCode.UNSUPPORTED_SCHEMA_VERSION,
        ),
        (
            '{"schema_version":1,"event_sequence":"bad"}\n',
            ToolTraceInputDiagnosticCode.INVALID_RECORD_FIELD,
        ),
    ),
)
def test_parser_syntax_and_type_units_are_strict_current_schema(
    tmp_path: Path,
    raw_line: str,
    expected_code: ToolTraceInputDiagnosticCode,
) -> None:
    """parser unit fixture 只覆盖 current schema syntax/type，不伪造业务语义。"""

    cold_path = (tmp_path / "cold.jsonl").absolute()
    cold_path.write_text(raw_line, encoding="utf-8")
    source = ToolTraceAnalysisSource(
        requested_path=cold_path,
        mode=ToolTraceInputMode.COLD_FILE,
        cold_jsonl_path=cold_path,
        hot_db_path=None,
        artifact_root=None,
    )

    dataset = _load(source)

    assert expected_code in _diagnostic_codes(dataset)
    assert dataset.cold_records == ()
    assert {item.reason_code for item in dataset.limitations} == {
        "hot_store_unavailable",
        "payload_resolution_unavailable",
    }


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("line_digest", ToolTraceInputDiagnosticCode.LINE_DIGEST_MISMATCH),
        ("cold_digest", ToolTraceInputDiagnosticCode.COLD_DIGEST_MISMATCH),
        ("cold_ref", ToolTraceInputDiagnosticCode.COLD_REF_MISMATCH),
    ),
)
def test_projection_baseline_targeted_integrity_corruption(
    tmp_path: Path,
    mutation: str,
    expected_code: ToolTraceInputDiagnosticCode,
) -> None:
    """digest/ref integration 必须先以 production baseline 成立，再单点破坏副本。"""

    _build_workspace_baseline(tmp_path)
    source = _workspace_source(tmp_path)
    baseline = _load(source)
    assert baseline.input_diagnostics == ()
    _, _, _, cold_path = _workspace_paths(tmp_path)
    objects = _read_cold_objects(cold_path)
    if mutation == "line_digest":
        objects[0]["event_type"] = "RUN_FAILED"
    elif mutation == "cold_digest":
        objects[0]["cold_trace_digest"] = "sha256:" + "0" * 64
    else:
        objects[0]["cold_trace_ref"] = "tool-trace-cold:wrong-event"
    _write_cold_objects(cold_path, objects)

    dataset = _load(source)

    assert expected_code in _diagnostic_codes(dataset)
    assert dataset.cold_records == ()


def test_duplicate_exact_and_conflicting_source_keys_are_distinct(
    tmp_path: Path,
) -> None:
    """exact duplicate 与同 source key 冲突必须使用不同 owner 诊断。"""

    _build_workspace_baseline(tmp_path)
    _, _, _, cold_path = _workspace_paths(tmp_path)
    objects = _read_cold_objects(cold_path)
    duplicate = dict(objects[0])
    conflict = dict(objects[0])
    conflict["event_type"] = "RUN_FAILED"
    _refresh_cold_integrity(conflict, keep_ref=True)
    _write_cold_objects(cold_path, [objects[0], duplicate, conflict])

    dataset = _load(_workspace_source(tmp_path))

    codes = _diagnostic_codes(dataset)
    assert ToolTraceInputDiagnosticCode.DUPLICATE_COLD_LINE in codes
    assert ToolTraceInputDiagnosticCode.COLD_SOURCE_CONFLICT in codes
    assert len(dataset.cold_records) == 1
    assert len(dataset.joined_records) == 1


def test_hot_only_and_cold_only_have_owner_specific_results(
    tmp_path: Path,
) -> None:
    """hot-only 产生 confirmed missing-cold，cold-only 只产生 capability limitation。"""

    _build_workspace_baseline(tmp_path)
    _, db_path, _, cold_path = _workspace_paths(tmp_path)
    cold_copy = (tmp_path / "cold-copy.jsonl").absolute()
    shutil.copyfile(cold_path, cold_copy)
    cold_path.unlink()
    lock_path = _tool_trace_cold_lock_path(cold_path)
    lock_path.unlink()
    hot_only = _load(_workspace_source(tmp_path))
    assert ToolTraceInputDiagnosticCode.MISSING_COLD_TRACE in _diagnostic_codes(hot_only)
    assert not lock_path.exists()

    cold_source = ToolTraceAnalysisSource(
        requested_path=cold_copy,
        mode=ToolTraceInputMode.COLD_FILE,
        cold_jsonl_path=cold_copy,
        hot_db_path=None,
        artifact_root=None,
    )
    cold_only = _load(cold_source)
    assert cold_only.hot_store_available is False
    assert cold_only.input_diagnostics == ()
    assert "hot_store_unavailable" in {item.reason_code for item in cold_only.limitations}
    assert db_path.exists()


def test_hot_cold_identity_mismatch_is_not_loose_joined(
    tmp_path: Path,
) -> None:
    """secondary identity 不一致必须诊断并排除 join。"""

    _build_workspace_baseline(tmp_path)
    _, _, _, cold_path = _workspace_paths(tmp_path)
    objects = _read_cold_objects(cold_path)
    objects[0]["event_sequence"] = 2
    _refresh_cold_integrity(objects[0])
    _write_cold_objects(cold_path, objects)

    dataset = _load(_workspace_source(tmp_path))

    assert ToolTraceInputDiagnosticCode.HOT_COLD_SOURCE_MISMATCH in _diagnostic_codes(dataset)
    assert dataset.joined_records == ()


def test_hot_empty_cold_empty_is_normal_and_cold_late_is_all_limited(
    tmp_path: Path,
) -> None:
    """hot-empty 两分支必须固定 watermark=0 且不产生 missing-hot 误报。"""

    empty_root = tmp_path / "empty"
    options = _store_options(empty_root)
    _, _, _, empty_cold = _workspace_paths(empty_root)
    with open_host_durable_store(options):
        empty_cold.parent.mkdir(parents=True, exist_ok=True)
        empty_cold.write_bytes(b"")
    empty_dataset = _load(_workspace_source(empty_root))
    assert empty_dataset.hot_event_sequence_watermark == 0
    assert empty_dataset.input_diagnostics == ()
    assert empty_dataset.limitations == ()

    source_root = tmp_path / "source"
    _build_workspace_baseline(source_root)
    _, _, _, source_cold = _workspace_paths(source_root)
    shutil.copyfile(source_cold, empty_cold)
    late_dataset = _load(_workspace_source(empty_root))

    assert late_dataset.hot_event_sequence_watermark == 0
    assert late_dataset.input_diagnostics == ()
    assert [item.reason_code for item in late_dataset.limitations] == ["input_changed_during_analysis"]
    assert late_dataset.limitations[0].hot_event_sequence_watermark == 0


def test_cold_row_not_above_watermark_without_hot_is_confirmed_missing(
    tmp_path: Path,
) -> None:
    """cold row 不高于 watermark 时缺 hot 必须是 confirmed diagnostic。"""

    options = _build_workspace_baseline(
        tmp_path,
        event_ids=("event-1", "event-2"),
    )
    with open_host_durable_store(options) as store:
        store.transaction_runner.run_write(
            lambda transaction: transaction.execute(
                f"DELETE FROM {TABLE_HOST_TOOL_TRACE_HOT} WHERE event_id = ?",
                ("event-1",),
            )
        )

    dataset = _load(_workspace_source(tmp_path))

    assert ToolTraceInputDiagnosticCode.MISSING_HOT_TRACE in _diagnostic_codes(dataset)
    assert all(item.reason_code != "input_changed_during_analysis" for item in dataset.limitations)


def test_existing_non_dayu_hot_store_is_fatal_not_cold_only(
    tmp_path: Path,
) -> None:
    """已存在但 schema 非 Dayu 的 DB 必须 fatal，不能改写为 hot unavailable。"""

    source_root = tmp_path / "source"
    _build_workspace_baseline(source_root)
    _, _, _, source_cold = _workspace_paths(source_root)
    workspace, db_path, artifact_root, cold_path = _workspace_paths(tmp_path)
    cold_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_cold, cold_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.close()
    source = ToolTraceAnalysisSource(
        requested_path=workspace,
        mode=ToolTraceInputMode.WORKSPACE_DIRECTORY,
        cold_jsonl_path=cold_path,
        hot_db_path=db_path,
        artifact_root=artifact_root,
    )

    with pytest.raises(ToolTraceAnalysisInputError) as captured:
        _load(source)

    assert captured.value.reason is ToolTraceAnalysisInputFailureReason.HOT_STORE_READ_FAILED


def test_file_only_does_not_open_descriptor_ref(tmp_path: Path) -> None:
    """file-only 必须把 ref 当定位标签，不直接打开 ref string。"""

    _build_workspace_baseline(tmp_path)
    _, _, _, cold_path = _workspace_paths(tmp_path)
    objects = _read_cold_objects(cold_path)
    objects[0]["payload_ref"] = "artifact:missing/private.json"
    objects[0]["payload_digest"] = "sha256:" + "1" * 64
    _refresh_cold_integrity(objects[0])
    cold_copy = (tmp_path / "file-only.jsonl").absolute()
    _write_cold_objects(cold_copy, objects)
    source = ToolTraceAnalysisSource(
        requested_path=cold_copy,
        mode=ToolTraceInputMode.COLD_FILE,
        cold_jsonl_path=cold_copy,
        hot_db_path=None,
        artifact_root=None,
    )

    dataset = _load(source)

    assert len(dataset.cold_records) == 1
    assert dataset.input_diagnostics == ()
    assert "payload_resolution_unavailable" in {item.reason_code for item in dataset.limitations}


def test_prefix_snapshot_releases_lock_before_real_producer_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """barrier 必须证明 slow prefix read 不占 producer 的既有 lock timeout。"""

    options = _build_workspace_baseline(tmp_path)
    source = _workspace_source(tmp_path)
    original_read = input_module._read_exact_prefix
    barrier = threading.Barrier(2)
    reader_results: list[ToolTraceAnalysisDataset] = []
    reader_errors: list[BaseException] = []

    def blocked_read(handle: BinaryIO, length: int) -> bytes:
        """在锁已释放后用 barrier 阻塞精确 prefix read。

        :param handle: 锁内已打开的同一 handle。
        :param length: captured prefix 长度。
        :returns: 原实现读取的精确 prefix。
        :raises BaseException: barrier 或原读取失败时透传。
        """

        barrier.wait(timeout=5.0)
        barrier.wait(timeout=5.0)
        return original_read(handle, length)

    def run_reader() -> None:
        """在线程中运行 Analyzer reader 并记录结果。

        :returns: ``None``。
        :raises: 无；异常记录到 ``reader_errors``。
        """

        try:
            reader_results.append(_load(source))
        except BaseException as exc:
            reader_errors.append(exc)

    monkeypatch.setattr(input_module, "_read_exact_prefix", blocked_read)
    reader = threading.Thread(target=run_reader)
    reader.start()
    barrier.wait(timeout=5.0)
    _, _, _, cold_path = _workspace_paths(tmp_path)
    with open_host_durable_store(options) as store:
        _append_trace_event(store.transaction_runner, event_id="event-2")
        _catch_up_trace(store.transaction_runner, cold_path)
    barrier.wait(timeout=5.0)
    reader.join(timeout=5.0)
    assert not reader.is_alive()
    assert reader_errors == []
    assert len(reader_results) == 1
    assert [record.event_id for record in reader_results[0].cold_records] == ["event-1"]

    monkeypatch.setattr(input_module, "_read_exact_prefix", original_read)
    next_dataset = _load(source)
    assert [record.event_id for record in next_dataset.cold_records] == [
        "event-1",
        "event-2",
    ]


def test_snapshot_keeps_open_handle_when_path_is_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """path 替换后本次读取必须保持旧 handle，不能重开新 path。"""

    _build_workspace_baseline(tmp_path)
    source = _workspace_source(tmp_path)
    cold_path = source.cold_jsonl_path
    original_bytes = cold_path.read_bytes()
    original_read = input_module._read_exact_prefix

    def replace_then_read(
        handle: BinaryIO,
        length: int,
    ) -> bytes:
        """替换 path 后从原 handle 读取。

        :param handle: 已打开旧 inode handle。
        :param length: captured prefix 长度。
        :returns: 原 handle prefix。
        :raises OSError: rename/write/read 失败时抛出。
        """

        replaced = cold_path.with_suffix(".replaced")
        cold_path.replace(replaced)
        cold_path.write_bytes(b"not-json\n")
        return original_read(handle, length)

    monkeypatch.setattr(input_module, "_read_exact_prefix", replace_then_read)
    dataset = _load(source)

    assert len(dataset.cold_records) == 1
    assert dataset.cold_records[0].event_id == "event-1"
    assert cold_path.read_bytes() != original_bytes


def test_truncate_or_short_read_is_fatal_not_partial_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同 inode truncate 导致 short read 时必须 fatal。"""

    _build_workspace_baseline(tmp_path)
    source = _workspace_source(tmp_path)
    original_read = input_module._read_exact_prefix

    def truncate_then_read(
        handle: BinaryIO,
        length: int,
    ) -> bytes:
        """截断已打开 handle 后执行原 exact read。

        :param handle: 已打开 handle。
        :param length: captured prefix 长度。
        :returns: 永不正常返回。
        :raises OSError: 原 exact read 观察到 short read 时抛出。
        """

        os.ftruncate(handle.fileno(), 0)
        return original_read(handle, length)

    monkeypatch.setattr(input_module, "_read_exact_prefix", truncate_then_read)
    with pytest.raises(ToolTraceAnalysisInputError) as captured:
        _load(source)

    assert captured.value.reason is ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_READ_FAILED


def test_cold_handle_close_failure_is_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """精确 prefix 已读完但 handle close 失败时仍不得返回 dataset。"""

    _build_workspace_baseline(tmp_path)
    readers: list[_FailingCloseReader] = []

    def open_failing_close(path: Path) -> BinaryIO:
        """打开 close 会失败的真实 binary reader。

        :param path: cold JSONL 路径。
        :returns: failing-close buffered reader。
        :raises OSError: raw file 无法打开时抛出。
        """

        raw = path.open("rb", buffering=0)
        reader = _FailingCloseReader(raw)
        readers.append(reader)
        return reader

    monkeypatch.setattr(
        input_module,
        "_open_cold_binary_file",
        open_failing_close,
    )
    try:
        with pytest.raises(ToolTraceAnalysisInputError) as captured:
            _load(_workspace_source(tmp_path))
        assert captured.value.reason is ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_READ_FAILED
    finally:
        for reader in readers:
            reader.force_close()


@pytest.mark.parametrize(
    ("error", "expected_reason"),
    (
        (
            RuntimeFileLockTimeoutError("timeout"),
            ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_LOCK_TIMEOUT,
        ),
        (
            RuntimeFileLockError("failed"),
            ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_LOCK_FAILED,
        ),
    ),
)
def test_lock_failures_are_fatal_without_unlocked_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: RuntimeFileLockError,
    expected_reason: ToolTraceAnalysisInputFailureReason,
) -> None:
    """lock timeout/acquire/release failure 必须映射稳定 fatal reason。"""

    _build_workspace_baseline(tmp_path)

    def fail_lock(
        lock_path: str | Path,
        *,
        timeout_seconds: float | None = None,
        create_parent_dirs: bool = True,
    ) -> NoReturn:
        """模拟 runtime lock construction/acquire failure。

        :param lock_path: lock 路径。
        :param timeout_seconds: timeout。
        :param create_parent_dirs: 是否创建 parent。
        :returns: 永不返回。
        :raises RuntimeFileLockError: 参数化失败。
        """

        del lock_path, timeout_seconds, create_parent_dirs
        raise error

    monkeypatch.setattr(input_module, "file_lock", fail_lock)
    with pytest.raises(ToolTraceAnalysisInputError) as captured:
        _load(_workspace_source(tmp_path))

    assert captured.value.reason is expected_reason
