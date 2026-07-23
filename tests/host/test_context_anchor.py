"""Host-private durable context anchor resolver owner tests。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.engine_events import (
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    runner_role_sequence_digest,
)
from dayu.host._runner_call_manifest import (
    RunnerCallHotAtoms,
    complete_runner_call_hot_diagnostic,
    runner_call_hot_payload,
)
from dayu.host.context_anchor import (
    ContextAnchorQuery,
    ContextAnchorResolution,
    resolve_context_anchor,
)
from dayu.host.context_budget import (
    CONTEXT_ESTIMATOR_CONTRACT,
    MAX_CONTEXT_TOKEN_COUNT,
    USAGE_OBSERVATION_STATUS_OBSERVED,
    ContextSizingFallbackReason,
    UsageObservation,
    build_usage_observation_diagnostic,
)
from dayu.host.durable.codec import sha256_digest_json
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
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.schema import (
    RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
)
from dayu.host.durable.transaction import HostTransaction

_NOW = datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC)
_SESSION_ID = "session-anchor"
_PROVIDER = "openai"
_MODEL = "model-anchor"
_WINDOW = 10_000
_REQUEST_DIGEST = sha256_digest_json({"supports_stream_usage": False})


@dataclass(frozen=True, slots=True)
class _CallRows:
    """测试runner call的durable evidence引用。"""

    manifest: EventLogRow
    link: EventLogRow
    usage: EventLogRow | None
    completion: EventLogRow | None


def test_query_event_cursor_is_independent_from_token_ceiling() -> None:
    """EventLog sequence不复用token/window上限。

    :returns: ``None``。
    :raises AssertionError: cursor与window没有遵守各自owner边界时抛出。
    """

    cursor = MAX_CONTEXT_TOKEN_COUNT + 1
    query = ContextAnchorQuery(
        session_id=_SESSION_ID,
        current_run_id="run-current",
        candidate_input_cursor=cursor,
        candidate_input_digest=sha256_digest_json({"current": cursor}),
        provider=_PROVIDER,
        model=_MODEL,
        context_window_size=_WINDOW,
        estimator_contract=CONTEXT_ESTIMATOR_CONTRACT,
        request_semantics_digest=_REQUEST_DIGEST,
    )
    assert query.candidate_input_cursor == cursor

    with pytest.raises(
        ValueError,
        match="context_window_size exceeds supported range",
    ):
        ContextAnchorQuery(
            session_id=_SESSION_ID,
            current_run_id="run-current",
            candidate_input_cursor=cursor,
            candidate_input_digest=sha256_digest_json({"current": cursor}),
            provider=_PROVIDER,
            model=_MODEL,
            context_window_size=MAX_CONTEXT_TOKEN_COUNT + 1,
            estimator_contract=CONTEXT_ESTIMATOR_CONTRACT,
            request_semantics_digest=_REQUEST_DIGEST,
        )


@pytest.mark.parametrize(
    ("candidate_input_cursor", "expected_exception"),
    (
        (True, TypeError),
        (-1, ValueError),
    ),
)
def test_query_event_cursor_fails_closed_at_typed_boundary(
    candidate_input_cursor: int,
    expected_exception: type[TypeError] | type[ValueError],
) -> None:
    """bool与负EventLog sequence在query owner边界失败。

    :param candidate_input_cursor: 待校验EventLog sequence。
    :param expected_exception: 对应typed boundary异常。
    :returns: ``None``。
    :raises AssertionError: 非法cursor未按契约失败时抛出。
    """

    with pytest.raises(
        expected_exception,
        match="ContextAnchorQuery.candidate_input_cursor",
    ):
        ContextAnchorQuery(
            session_id=_SESSION_ID,
            current_run_id="run-current",
            candidate_input_cursor=candidate_input_cursor,
            candidate_input_digest=sha256_digest_json(
                {"current": candidate_input_cursor}
            ),
            provider=_PROVIDER,
            model=_MODEL,
            context_window_size=_WINDOW,
            estimator_contract=CONTEXT_ESTIMATOR_CONTRACT,
            request_semantics_digest=_REQUEST_DIGEST,
        )


def test_resolver_selects_strict_compatible_anchor_in_same_transaction(
    tmp_path: Path,
) -> None:
    """完整conjunction存在时返回唯一compatible anchor。

    :param tmp_path: pytest临时目录。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        rows, resolution = store.transaction_runner.run_write(
            lambda transaction: _append_and_resolve(
                transaction,
                call_index=0,
                conservative_tokens=6_000,
                prompt_tokens=6_200,
            )
        )
        assert resolution.fallback_reason is None
        assert resolution.anchor is not None
        assert rows.usage is not None
        assert rows.completion is not None
        assert resolution.anchor.manifest_event_id == rows.manifest.event_id
        assert resolution.anchor.iteration_link_event_id == rows.link.event_id
        assert resolution.anchor.usage_event_id == rows.usage.event_id
        assert resolution.anchor.iteration_completed_event_id == (
            rows.completion.event_id
        )
        assert resolution.anchor.usage_anchor_tokens == 6_200
        assert resolution.anchor.conservative_anchor_tokens == 6_000


def test_resolver_crosses_completed_calls_without_usage_and_keyset_pages(
    tmp_path: Path,
) -> None:
    """较新的完整missing-usage calls可跨页寻找旧anchor。

    :param tmp_path: pytest临时目录。
    """

    def operation(transaction: HostTransaction) -> ContextAnchorResolution:
        """写入超过一页的lineage并解析。

        :param transaction: 当前write transaction。
        :returns: resolver结果。
        """

        _append_call(
            transaction,
            call_index=0,
            conservative_tokens=5_900,
            prompt_tokens=6_100,
        )
        for call_index in range(1, 24):
            _append_call(
                transaction,
                call_index=call_index,
                conservative_tokens=6_000 + call_index,
                prompt_tokens=None,
            )
        return _resolve(transaction)

    with open_host_durable_store(_options(tmp_path)) as store:
        resolution = store.transaction_runner.run_write(operation)
        assert resolution.anchor is not None
        assert resolution.anchor.usage_anchor_tokens == 6_100


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("missing_link", ContextSizingFallbackReason.ITERATION_LINK_MISSING),
        ("missing_completion", ContextSizingFallbackReason.ITERATION_INCOMPLETE),
        (
            "duplicate_completion",
            ContextSizingFallbackReason.ITERATION_COMPLETION_AMBIGUOUS,
        ),
        ("duplicate_link", ContextSizingFallbackReason.ITERATION_LINK_INVALID),
        ("link_mismatch", ContextSizingFallbackReason.MANIFEST_MISMATCH),
        ("duplicate_usage", ContextSizingFallbackReason.USAGE_AMBIGUOUS),
        ("invalid_usage", ContextSizingFallbackReason.USAGE_INVALID),
        ("ineligible_finish", ContextSizingFallbackReason.ITERATION_FINISH_REASON_INELIGIBLE),
    ),
)
def test_newer_lineage_barrier_never_falls_through_to_old_anchor(
    tmp_path: Path,
    mutation: str,
    expected_reason: ContextSizingFallbackReason,
) -> None:
    """任何较新invalid/incomplete/ambiguous lineage均阻断旧anchor。

    :param tmp_path: pytest临时目录。
    :param mutation: 较新call的损坏类型。
    :param expected_reason: 预期closed fallback reason。
    """

    def operation(transaction: HostTransaction) -> ContextAnchorResolution:
        """写入旧anchor与较新barrier。

        :param transaction: 当前write transaction。
        :returns: resolver结果。
        """

        _append_call(
            transaction,
            call_index=0,
            conservative_tokens=6_000,
            prompt_tokens=6_200,
        )
        _append_call(
            transaction,
            call_index=1,
            conservative_tokens=6_100,
            prompt_tokens=6_300,
            append_link=mutation != "missing_link",
            append_completion=mutation != "missing_completion",
            finish_reason=(
                "error" if mutation == "ineligible_finish" else "stop"
            ),
            duplicate_usage=mutation == "duplicate_usage",
            invalid_usage=mutation == "invalid_usage",
            duplicate_link=mutation == "duplicate_link",
            link_mismatch=mutation == "link_mismatch",
            duplicate_completion=mutation == "duplicate_completion",
        )
        return _resolve(transaction)

    with open_host_durable_store(_options(tmp_path)) as store:
        resolution = store.transaction_runner.run_write(operation)
        assert resolution.anchor is None
        assert resolution.fallback_reason is expected_reason


@pytest.mark.parametrize(
    ("provider", "model", "window", "estimator_version", "request_digest", "reason"),
    (
        (
            "other-provider",
            _MODEL,
            _WINDOW,
            "1",
            _REQUEST_DIGEST,
            ContextSizingFallbackReason.PROVIDER_MISMATCH,
        ),
        (
            _PROVIDER,
            "other-model",
            _WINDOW,
            "1",
            _REQUEST_DIGEST,
            ContextSizingFallbackReason.MODEL_MISMATCH,
        ),
        (
            _PROVIDER,
            _MODEL,
            20_000,
            "1",
            _REQUEST_DIGEST,
            ContextSizingFallbackReason.CONTEXT_WINDOW_MISMATCH,
        ),
        (
            _PROVIDER,
            _MODEL,
            _WINDOW,
            "2",
            _REQUEST_DIGEST,
            ContextSizingFallbackReason.ESTIMATOR_CONTRACT_MISMATCH,
        ),
        (
            _PROVIDER,
            _MODEL,
            _WINDOW,
            "1",
            sha256_digest_json({"supports_stream_usage": True}),
            ContextSizingFallbackReason.REQUEST_SEMANTICS_MISMATCH,
        ),
    ),
)
def test_resolver_rejects_each_compatibility_dimension(
    tmp_path: Path,
    provider: str,
    model: str,
    window: int,
    estimator_version: str,
    request_digest: str,
    reason: ContextSizingFallbackReason,
) -> None:
    """每个compatibility维度不匹配都在最新call处fallback。

    :param tmp_path: pytest临时目录。
    :param provider: anchor provider。
    :param model: anchor model。
    :param window: anchor context window。
    :param estimator_version: anchor estimator version。
    :param request_digest: anchor request semantics digest。
    :param reason: 预期fallback reason。
    """

    def operation(transaction: HostTransaction) -> ContextAnchorResolution:
        """写入指定compatibility反例。

        :param transaction: 当前write transaction。
        :returns: resolver结果。
        """

        _append_call(
            transaction,
            call_index=0,
            conservative_tokens=6_000,
            prompt_tokens=6_200,
            provider=provider,
            model=model,
            window=window,
            estimator_version=estimator_version,
            request_digest=request_digest,
        )
        return _resolve(transaction)

    with open_host_durable_store(_options(tmp_path)) as store:
        resolution = store.transaction_runner.run_write(operation)
        assert resolution.anchor is None
        assert resolution.fallback_reason is reason


def test_latest_accepted_compact_invalidates_old_anchor_until_refresh(
    tmp_path: Path,
) -> None:
    """accepted compact boundary截断旧anchor，新成功call可刷新。

    :param tmp_path: pytest临时目录。
    """

    def operation(
        transaction: HostTransaction,
    ) -> tuple[ContextAnchorResolution, ContextAnchorResolution]:
        """在同一snapshot验证compact前后选择。

        :param transaction: 当前write transaction。
        :returns: compact后fallback与刷新后anchor。
        """

        _append_call(
            transaction,
            call_index=0,
            conservative_tokens=6_000,
            prompt_tokens=6_200,
        )
        _append_event(
            transaction,
            event_id="event-compact",
            event_class=EventClass.CANONICAL_FACT,
            event_type="CONTEXT_COMPACTED",
            run_id="run-compact",
            attempt_id=None,
            execution_id=None,
            payload={"accepted": True},
        )
        invalidated = _resolve(transaction)
        _append_call(
            transaction,
            call_index=1,
            conservative_tokens=5_000,
            prompt_tokens=5_100,
        )
        return invalidated, _resolve(transaction)

    with open_host_durable_store(_options(tmp_path)) as store:
        invalidated, refreshed = store.transaction_runner.run_write(operation)
        assert invalidated.anchor is None
        assert invalidated.fallback_reason is (
            ContextSizingFallbackReason.ACCEPTED_COMPACT_INVALIDATED
        )
        assert refreshed.anchor is not None
        assert refreshed.anchor.usage_anchor_tokens == 5_100


def test_actual_usage_presence_does_not_depend_on_supports_flag(
    tmp_path: Path,
) -> None:
    """supports=false但实际usage完整时仍可anchor。

    :param tmp_path: pytest临时目录。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        _rows, resolution = store.transaction_runner.run_write(
            lambda transaction: _append_and_resolve(
                transaction,
                call_index=0,
                conservative_tokens=6_000,
                prompt_tokens=6_200,
                request_digest=sha256_digest_json(
                    {"supports_stream_usage": False}
                ),
            )
        )
        assert resolution.anchor is not None


def test_supports_flag_does_not_invent_missing_usage(
    tmp_path: Path,
) -> None:
    """supports=true但无usage时仍严格fallback。

    :param tmp_path: pytest临时目录。
    """

    request_digest = sha256_digest_json(
        {"supports_stream_usage": True}
    )

    def operation(transaction: HostTransaction) -> ContextAnchorResolution:
        """写入完整无usage call并解析。

        :param transaction: 当前transaction。
        :returns: missing-usage resolution。
        """

        _append_call(
            transaction,
            call_index=0,
            conservative_tokens=6_000,
            prompt_tokens=None,
            request_digest=request_digest,
        )
        return _resolve(transaction, request_digest=request_digest)

    with open_host_durable_store(_options(tmp_path)) as store:
        resolution = store.transaction_runner.run_write(operation)
        assert resolution.anchor is None
        assert resolution.fallback_reason is (
            ContextSizingFallbackReason.USAGE_MISSING
        )


def _append_and_resolve(
    transaction: HostTransaction,
    *,
    call_index: int,
    conservative_tokens: int,
    prompt_tokens: int,
    request_digest: str = _REQUEST_DIGEST,
) -> tuple[_CallRows, ContextAnchorResolution]:
    """追加单个成功call并在同一transaction解析。

    :param transaction: 当前write transaction。
    :param call_index: call index。
    :param conservative_tokens: ``E_anchor``。
    :param prompt_tokens: ``U_anchor``。
    :param request_digest: request semantics digest。
    :returns: durable rows与resolver结果。
    """

    rows = _append_call(
        transaction,
        call_index=call_index,
        conservative_tokens=conservative_tokens,
        prompt_tokens=prompt_tokens,
        request_digest=request_digest,
    )
    return rows, _resolve(transaction, request_digest=request_digest)


def _resolve(
    transaction: HostTransaction,
    *,
    request_digest: str = _REQUEST_DIGEST,
) -> ContextAnchorResolution:
    """在当前transaction snapshot解析anchor。

    :param transaction: 当前transaction。
    :param request_digest: 当前candidate request semantics digest。
    :returns: typed resolver结果。
    """

    cursor_row = transaction.fetchone(
        "SELECT MAX(event_sequence) AS cursor FROM event_log"
    )
    cursor = cursor_row.get("cursor") if cursor_row is not None else None
    assert isinstance(cursor, int)
    return resolve_context_anchor(
        transaction,
        EventLogStore(),
        ContextAnchorQuery(
            session_id=_SESSION_ID,
            current_run_id="run-current",
            candidate_input_cursor=cursor,
            candidate_input_digest=sha256_digest_json({"current": cursor}),
            provider=_PROVIDER,
            model=_MODEL,
            context_window_size=_WINDOW,
            estimator_contract=CONTEXT_ESTIMATOR_CONTRACT,
            request_semantics_digest=request_digest,
        ),
    )


def _append_call(
    transaction: HostTransaction,
    *,
    call_index: int,
    conservative_tokens: int,
    prompt_tokens: int | None,
    provider: str = _PROVIDER,
    model: str = _MODEL,
    window: int = _WINDOW,
    estimator_version: str = "1",
    request_digest: str = _REQUEST_DIGEST,
    append_link: bool = True,
    append_completion: bool = True,
    finish_reason: str = "stop",
    duplicate_usage: bool = False,
    invalid_usage: bool = False,
    duplicate_link: bool = False,
    link_mismatch: bool = False,
    duplicate_completion: bool = False,
) -> _CallRows:
    """追加一个可定向损坏的runner-call lineage。

    :param transaction: 当前write transaction。
    :param call_index: runner call index。
    :param conservative_tokens: manifest conservative tokens。
    :param prompt_tokens: provider usage；``None``表示合法缺失。
    :param provider: manifest provider。
    :param model: manifest model。
    :param window: manifest context window。
    :param estimator_version: manifest estimator version。
    :param request_digest: manifest request semantics digest。
    :param append_link: 是否追加link。
    :param append_completion: 是否追加completion。
    :param finish_reason: completion finish reason。
    :param duplicate_usage: 是否追加第二条usage。
    :param invalid_usage: 是否篡改usage pairing。
    :param duplicate_link: 是否追加同identity第二条accepted link。
    :param link_mismatch: 是否篡改link的runner-call identity。
    :param duplicate_completion: 是否追加同identity第二条completion。
    :returns: 已追加的evidence rows。
    """

    run_id = f"run-{call_index}"
    attempt_id = f"attempt-{call_index}"
    execution_id = f"execution-{call_index}"
    iteration_id = f"iteration-{call_index}"
    role_digest = runner_role_sequence_digest(("user",))
    estimator_digest = sha256_digest_json({"estimate": call_index})
    input_digest = sha256_digest_json({"input": call_index})
    projection_digest = sha256_digest_json({"projection": call_index})
    manifest_ref = f"payload-runner-manifest:{call_index}"
    manifest = _manifest_payload(
        call_index=call_index,
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        role_digest=role_digest,
        estimator_digest=estimator_digest,
        conservative_tokens=conservative_tokens,
        provider=provider,
        model=model,
        window=window,
        estimator_version=estimator_version,
        request_digest=request_digest,
        input_digest=input_digest,
        projection_digest=projection_digest,
    )
    manifest_digest = sha256_digest_json(manifest)
    descriptor = PayloadStore().write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=manifest_ref,
            payload_id=f"sqlite-runner-manifest:{call_index}",
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=manifest,
            media_type="application/json",
            metadata={},
            expected_digest=manifest_digest,
        ),
    )
    hot = runner_call_hot_payload(
        RunnerCallHotAtoms(
            session_id=_SESSION_ID,
            host_run_id=run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            runner_call_index=call_index,
            runner_call_kind=(
                "initial_user_dispatch"
                if call_index == 0
                else "tool_result_continuation"
            ),
            runner_call_trigger_reason=(
                "initial_user_input"
                if call_index == 0
                else "tool_results_available"
            ),
            iteration_id=None if call_index == 0 else iteration_id,
            iteration_index=None if call_index == 0 else call_index,
            manifest_payload_ref=descriptor.payload_ref,
            manifest_digest=descriptor.payload_digest,
            manifest_schema_version=RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
            validation_status="complete",
            message_count=1,
            role_sequence_digest=role_digest,
            input_projection_digest=projection_digest,
            runner_call_projection_artifact_ref=f"payload-projection:{call_index}",
            runner_call_projection_artifact_digest=projection_digest,
            runner_call_projection_artifact_size_bytes=128,
            diagnostic=complete_runner_call_hot_diagnostic(
                status="complete",
                message_count=1,
                role_sequence_digest=role_digest,
                consumer_boundary="test.context_anchor",
            ),
        ),
        manifest=manifest,
    )
    manifest_row = _append_event(
        transaction,
        event_id=f"event-manifest-{call_index}",
        event_class=EventClass.CANONICAL_FACT,
        event_type="RUNNER_CALL_INPUT_ASSEMBLED",
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        payload=hot,
        payload_ref=descriptor.payload_ref,
        payload_digest=descriptor.payload_digest,
    )
    if not append_link:
        return _CallRows(manifest_row, manifest_row, None, None)
    link_payload = _link_payload(
        call_index=call_index,
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        iteration_id=iteration_id,
        manifest_row=manifest_row,
        role_digest=role_digest,
    )
    if link_mismatch:
        link_payload = {
            **link_payload,
            "runner_call_kind": "followup_user_dispatch",
            "runner_call_trigger_reason": "followup_user_input",
        }
    link_row = _append_event(
        transaction,
        event_id=f"event-link-{call_index}",
        event_class=EventClass.CANONICAL_FACT,
        event_type="RUNNER_CALL_INPUT_ITERATION_LINKED",
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        payload=link_payload,
    )
    if duplicate_link:
        _append_event(
            transaction,
            event_id=f"event-link-{call_index}-duplicate",
            event_class=EventClass.CANONICAL_FACT,
            event_type="RUNNER_CALL_INPUT_ITERATION_LINKED",
            run_id=run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            payload=link_payload,
        )
    usage_row: EventLogRow | None = None
    if prompt_tokens is not None:
        usage_row = _append_usage(
            transaction,
            suffix=str(call_index),
            run_id=run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            iteration_id=iteration_id,
            prompt_tokens=prompt_tokens,
            conservative_tokens=conservative_tokens,
            estimator_digest=estimator_digest,
            input_digest=input_digest,
            manifest_row=manifest_row,
            link_row=link_row,
            invalid_usage=invalid_usage,
        )
        if duplicate_usage:
            _append_usage(
                transaction,
                suffix=f"{call_index}-duplicate",
                run_id=run_id,
                attempt_id=attempt_id,
                execution_id=execution_id,
                iteration_id=iteration_id,
                prompt_tokens=prompt_tokens,
                conservative_tokens=conservative_tokens,
                estimator_digest=estimator_digest,
                input_digest=input_digest,
                manifest_row=manifest_row,
                link_row=link_row,
                invalid_usage=False,
            )
    completion_row = (
        _append_event(
            transaction,
            event_id=f"event-completion-{call_index}",
            event_class=EventClass.PREVIEW,
            event_type="ITERATION_COMPLETED",
            run_id=run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            payload={
                "attempt_id": attempt_id,
                "execution_id": execution_id,
                "worker_event_index": call_index,
                "engine_event_type": "iteration_completed",
                "iteration_id": iteration_id,
                "finish_reason": finish_reason,
                "provider_request_id": None,
                "client_correlation_id": None,
            },
        )
        if append_completion
        else None
    )
    if duplicate_completion:
        _append_event(
            transaction,
            event_id=f"event-completion-{call_index}-duplicate",
            event_class=EventClass.PREVIEW,
            event_type="ITERATION_COMPLETED",
            run_id=run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            payload={
                "attempt_id": attempt_id,
                "execution_id": execution_id,
                "worker_event_index": call_index + 100,
                "engine_event_type": "iteration_completed",
                "iteration_id": iteration_id,
                "finish_reason": finish_reason,
                "provider_request_id": None,
                "client_correlation_id": None,
            },
        )
    return _CallRows(manifest_row, link_row, usage_row, completion_row)


def _manifest_payload(
    *,
    call_index: int,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    role_digest: str,
    estimator_digest: str,
    conservative_tokens: int,
    provider: str,
    model: str,
    window: int,
    estimator_version: str,
    request_digest: str,
    input_digest: str,
    projection_digest: str,
) -> Mapping[str, JsonValue]:
    """构造strict complete manifest body。

    :returns: canonical manifest JSON。
    :raises Exception: 不主动抛出异常。
    """

    runner_call_kind = (
        "initial_user_dispatch"
        if call_index == 0
        else "tool_result_continuation"
    )
    trigger = (
        "initial_user_input"
        if call_index == 0
        else "tool_results_available"
    )
    metadata_id = f"projector:{call_index}:user"
    projector_id = "user_input_message"
    projector_schema = "run_input_projector.v1"
    purpose = "ordinary_run_input"
    source_refs: list[JsonValue] = [f"event:input:{call_index}"]
    projector_digest = sha256_digest_json(
        {
            "projector_id": projector_id,
            "projector_schema_version": projector_schema,
            "purpose": purpose,
            "source_contract_refs": source_refs,
        }
    )
    return {
        "schema_version": RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
        "manifest_id": f"runner-call-manifest:{call_index}",
        "session_id": _SESSION_ID,
        "host_run_id": run_id,
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "runner_call_index": call_index,
        "runner_call_kind": runner_call_kind,
        "runner_call_trigger_reason": trigger,
        "iteration_id": None if call_index == 0 else f"iteration-{call_index}",
        "iteration_index": None if call_index == 0 else call_index,
        "message_count": 1,
        "role_sequence_digest": role_digest,
        "runner_input_serializer_schema_version": (
            RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
        ),
        "input_projection_digest": projection_digest,
        "runner_call_projection_artifact_ref": f"payload-projection:{call_index}",
        "runner_call_projection_artifact_digest": projection_digest,
        "runner_call_projection_artifact_size_bytes": 128,
        "message_entries": [
            {
                "index": 0,
                "role": "user",
                "content_digest": sha256_digest_json({"message": call_index}),
                "content_size_bytes": 8,
                "source_refs": source_refs,
                "projection_artifact_ref": f"payload-projection:{call_index}",
                "projection_artifact_digest": projection_digest,
                "projector_metadata_id": metadata_id,
                "provider_tool_calls_digest": None,
                "reasoning_content_digest": None,
            }
        ],
        "source_cursor_refs": source_refs,
        "tool_schema_snapshot_refs": [],
        "memory_snapshot_cursor_ref": None,
        "compact_artifact_refs": [],
        "context_fallback_decision_ref": None,
        "projector_metadata": [
            {
                "projector_metadata_id": metadata_id,
                "projector_id": projector_id,
                "projector_schema_version": projector_schema,
                "projector_digest": projector_digest,
                "purpose": purpose,
                "source_contract_refs": source_refs,
            }
        ],
        "compactor_identity": None,
        "sizing_snapshot": {
            "status": "complete",
            "reason": None,
            "sizing_stage": (
                "ordinary" if call_index == 0 else "continuation"
            ),
            "estimator_id": CONTEXT_ESTIMATOR_CONTRACT.estimator_id,
            "estimator_version": estimator_version,
            "estimator_digest": estimator_digest,
            "conservative_input_tokens": conservative_tokens,
            "context_window_size": window,
            "provider": provider,
            "model": model,
            "request_semantics_digest": request_digest,
            "input_snapshot_digest": input_digest,
            "policy_ref": "policy-anchor",
            "policy_snapshot_digest": sha256_digest_json(
                {"policy": "anchor"}
            ),
        },
        "diagnostic": None,
    }


def _link_payload(
    *,
    call_index: int,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    iteration_id: str,
    manifest_row: EventLogRow,
    role_digest: str,
) -> Mapping[str, JsonValue]:
    """构造strict accepted iteration link。

    :returns: canonical link payload。
    :raises AssertionError: manifest descriptor缺失时抛出。
    """

    assert manifest_row.payload_ref is not None
    assert manifest_row.payload_digest is not None
    return {
        "session_id": _SESSION_ID,
        "host_run_id": run_id,
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "manifest_event_id": manifest_row.event_id,
        "manifest_payload_ref": manifest_row.payload_ref,
        "manifest_digest": manifest_row.payload_digest,
        "manifest_schema_version": RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
        "runner_call_index": call_index,
        "runner_call_kind": (
            "initial_user_dispatch"
            if call_index == 0
            else "tool_result_continuation"
        ),
        "runner_call_trigger_reason": (
            "initial_user_input"
            if call_index == 0
            else "tool_results_available"
        ),
        "iteration_id": iteration_id,
        "iteration_index": call_index,
        "engine_message_count": 1,
        "engine_role_sequence_digest": role_digest,
        "runner_input_serializer_schema_version": (
            RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
        ),
        "expected_message_count": 1,
        "expected_role_sequence_digest": role_digest,
        "validation_status": "complete",
        "diagnostic": None,
    }


def _append_usage(
    transaction: HostTransaction,
    *,
    suffix: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    iteration_id: str,
    prompt_tokens: int,
    conservative_tokens: int,
    estimator_digest: str,
    input_digest: str,
    manifest_row: EventLogRow,
    link_row: EventLogRow,
    invalid_usage: bool,
) -> EventLogRow:
    """追加strict paired usage或定向篡改pairing。

    :returns: usage EventLog row。
    :raises AssertionError: manifest descriptor缺失时抛出。
    """

    observation = UsageObservation(
        session_id=_SESSION_ID,
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        iteration_id=iteration_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=100,
        total_tokens=prompt_tokens + 100,
        provider_request_id=None,
        estimator_digest=estimator_digest,
        policy_ref="policy-anchor",
        observed_at=_NOW,
    )
    diagnostic = build_usage_observation_diagnostic(
        observation,
        estimated_input_tokens=conservative_tokens,
        status=USAGE_OBSERVATION_STATUS_OBSERVED,
    )
    assert manifest_row.payload_ref is not None
    assert manifest_row.payload_digest is not None
    pairing_manifest_id = (
        "event-invalid" if invalid_usage else manifest_row.event_id
    )
    return _append_event(
        transaction,
        event_id=f"event-usage-{suffix}",
        event_class=EventClass.PROJECTION_SIGNAL,
        event_type="USAGE_REPORTED",
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        payload={
            "session_id": _SESSION_ID,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "execution_id": execution_id,
            "iteration_id": iteration_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": 100,
            "total_tokens": prompt_tokens + 100,
            "provider_request_id": None,
            "policy_ref": "policy-anchor",
            "estimator_digest": estimator_digest,
            "estimated_input_tokens": conservative_tokens,
            "usage_observation_status": USAGE_OBSERVATION_STATUS_OBSERVED,
            "usage_observation_digest": diagnostic.observation_digest,
            "prompt_token_delta": prompt_tokens - conservative_tokens,
            "context_pressure": {"status": "observed"},
            "runner_call_pairing": {
                "status": "complete",
                "reason": None,
                "manifest_event_id": pairing_manifest_id,
                "manifest_payload_ref": manifest_row.payload_ref,
                "manifest_digest": manifest_row.payload_digest,
                "iteration_link_event_id": link_row.event_id,
                "input_snapshot_digest": input_digest,
                "observation_digest": diagnostic.observation_digest,
            },
        },
    )


def _append_event(
    transaction: HostTransaction,
    *,
    event_id: str,
    event_class: EventClass,
    event_type: str,
    run_id: str,
    attempt_id: str | None,
    execution_id: str | None,
    payload: Mapping[str, JsonValue],
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> EventLogRow:
    """追加测试EventLog row。

    :returns: committed-in-transaction row。
    :raises Exception: EventLog contract非法时透传。
    """

    return EventLogStore().append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=event_class,
            session_id=_SESSION_ID,
            run_id=run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            event_type=event_type,
            occurred_at=_NOW,
            actor="tester",
            source="pytest",
            client_request_id=None,
            idempotency_key=None,
            policy_decision=None,
            reason=None,
            payload_json=payload,
            payload_ref=payload_ref,
            payload_digest=payload_digest,
        ),
    ).row


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试durable store options。

    :param tmp_path: pytest临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts"
        ),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )
