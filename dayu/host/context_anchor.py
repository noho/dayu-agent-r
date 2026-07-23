"""Host-private durable context usage anchor resolver。

本模块只在调用方提供的同一个 ``HostTransaction`` snapshot 内扫描
runner-call manifest、accepted iteration link、usage observation、accepted
iteration completion preview 与 compact boundary。它不计算当前预测、阈值或
治理动作，也不持有连接、cache 或模块可变状态。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.host._event_payload import payload_object
from dayu.host._runner_call_manifest import (
    RunnerCallInputManifest,
    RunnerCallSizingStatus,
    parse_runner_call_hot_payload,
    parse_runner_call_manifest,
    require_current_runner_input_serializer_schema_version,
)
from dayu.host.context_budget import (
    MAX_CONTEXT_TOKEN_COUNT,
    USAGE_OBSERVATION_STATUS_OBSERVED,
    ContextEstimatorContract,
    ContextSizingFallbackReason,
    UsageObservation,
    build_usage_observation_diagnostic,
)
from dayu.host.durable.codec import is_sha256_digest, parse_utc_timestamp
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.schema import (
    RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
    TABLE_EVENT_LOG,
)
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.payload_resolution import sqlite_payload_object

_RUNNER_CALL_INPUT_ASSEMBLED = "RUNNER_CALL_INPUT_ASSEMBLED"
_RUNNER_CALL_INPUT_ITERATION_LINKED = "RUNNER_CALL_INPUT_ITERATION_LINKED"
_USAGE_REPORTED = "USAGE_REPORTED"
_ITERATION_COMPLETED = "ITERATION_COMPLETED"
_CONTEXT_COMPACTED = "CONTEXT_COMPACTED"
_SCAN_EVENT_TYPES = (
    _RUNNER_CALL_INPUT_ASSEMBLED,
    _RUNNER_CALL_INPUT_ITERATION_LINKED,
    _USAGE_REPORTED,
    _ITERATION_COMPLETED,
    _CONTEXT_COMPACTED,
)
_SCAN_PAGE_SIZE = 64
_ELIGIBLE_RUNNER_CALL_KINDS = frozenset(
    (
        "initial_user_dispatch",
        "followup_user_dispatch",
        "post_compaction_dispatch",
        "tool_result_continuation",
    )
)
_ELIGIBLE_FINISH_REASONS = frozenset(("stop", "length", "tool_calls"))
_LINK_FIELDS = frozenset(
    (
        "session_id",
        "host_run_id",
        "attempt_id",
        "execution_id",
        "manifest_event_id",
        "manifest_payload_ref",
        "manifest_digest",
        "manifest_schema_version",
        "runner_call_index",
        "runner_call_kind",
        "runner_call_trigger_reason",
        "iteration_id",
        "iteration_index",
        "engine_message_count",
        "engine_role_sequence_digest",
        "runner_input_serializer_schema_version",
        "expected_message_count",
        "expected_role_sequence_digest",
        "validation_status",
        "diagnostic",
    )
)
_USAGE_FIELDS = frozenset(
    (
        "session_id",
        "run_id",
        "attempt_id",
        "execution_id",
        "iteration_id",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "provider_request_id",
        "policy_ref",
        "estimator_digest",
        "estimated_input_tokens",
        "usage_observation_status",
        "usage_observation_digest",
        "prompt_token_delta",
        "context_pressure",
        "runner_call_pairing",
    )
)
_USAGE_PAIRING_FIELDS = frozenset(
    (
        "status",
        "reason",
        "manifest_event_id",
        "manifest_payload_ref",
        "manifest_digest",
        "iteration_link_event_id",
        "input_snapshot_digest",
        "observation_digest",
    )
)
_COMPLETION_FIELDS = frozenset(
    (
        "attempt_id",
        "execution_id",
        "worker_event_index",
        "engine_event_type",
        "iteration_id",
        "finish_reason",
        "provider_request_id",
        "client_correlation_id",
    )
)


@dataclass(frozen=True, slots=True)
class ContextAnchorQuery:
    """当前complete candidate的anchor查询条件。

    :param session_id: 当前Session id。
    :param current_run_id: 调用方从当前complete candidate冻结的Host Run typed identity；
        不与历史anchor Run id做相等比较。
    :param candidate_input_cursor: resolver允许读取的最大EventLog sequence；它不是
        token count。
    :param candidate_input_digest: 调用方从当前complete candidate冻结的input digest
        typed identity；不与历史anchor input digest做相等比较。
    :param provider: frozen provider identity。
    :param model: frozen model identity。
    :param context_window_size: frozen context window。
    :param estimator_contract: 当前stable estimator contract。
    :param request_semantics_digest: 当前request serialization digest。
    """

    session_id: str
    current_run_id: str
    candidate_input_cursor: int
    candidate_input_digest: str
    provider: str
    model: str
    context_window_size: int
    estimator_contract: ContextEstimatorContract
    request_semantics_digest: str

    def __post_init__(self) -> None:
        """校验query typed atoms。

        :returns: ``None``。
        :raises TypeError: cursor/window/contract类型非法时抛出。
        :raises ValueError: identity、digest或范围非法时抛出。
        """

        for field_name, value in (
            ("session_id", self.session_id),
            ("current_run_id", self.current_run_id),
            ("provider", self.provider),
            ("model", self.model),
        ):
            _require_text(value, field_name=f"ContextAnchorQuery.{field_name}")
        _require_non_negative_int(
            self.candidate_input_cursor,
            field_name="ContextAnchorQuery.candidate_input_cursor",
        )
        _require_digest(
            self.candidate_input_digest,
            field_name="ContextAnchorQuery.candidate_input_digest",
        )
        _require_positive_int(
            self.context_window_size,
            field_name="ContextAnchorQuery.context_window_size",
        )
        if self.context_window_size > MAX_CONTEXT_TOKEN_COUNT:
            raise ValueError("context_window_size exceeds supported range")
        if not isinstance(self.estimator_contract, ContextEstimatorContract):
            raise TypeError("estimator_contract must be ContextEstimatorContract")
        _require_digest(
            self.request_semantics_digest,
            field_name="ContextAnchorQuery.request_semantics_digest",
        )


@dataclass(frozen=True, slots=True)
class CompatibleContextAnchor:
    """已证明eligible且compatible的ordinary usage anchor。

    :param manifest_event_id: anchor manifest event id。
    :param manifest_payload_ref: manifest payload ref。
    :param manifest_digest: manifest payload digest。
    :param iteration_link_event_id: unique accepted link id。
    :param usage_event_id: unique valid usage event id。
    :param usage_observation_digest: strict observation digest。
    :param iteration_completed_event_id: unique accepted completion preview id。
    :param usage_anchor_tokens: ``U_anchor``。
    :param conservative_anchor_tokens: ``E_anchor``。
    """

    manifest_event_id: str
    manifest_payload_ref: str
    manifest_digest: str
    iteration_link_event_id: str
    usage_event_id: str
    usage_observation_digest: str
    iteration_completed_event_id: str
    usage_anchor_tokens: int
    conservative_anchor_tokens: int

    def __post_init__(self) -> None:
        """校验anchor refs与数值范围。

        :returns: ``None``。
        :raises TypeError: token不是严格整数时抛出。
        :raises ValueError: ref、digest或token范围非法时抛出。
        """

        for field_name, value in (
            ("manifest_event_id", self.manifest_event_id),
            ("manifest_payload_ref", self.manifest_payload_ref),
            ("iteration_link_event_id", self.iteration_link_event_id),
            ("usage_event_id", self.usage_event_id),
            ("iteration_completed_event_id", self.iteration_completed_event_id),
        ):
            _require_text(
                value,
                field_name=f"CompatibleContextAnchor.{field_name}",
            )
        for field_name, value in (
            ("manifest_digest", self.manifest_digest),
            ("usage_observation_digest", self.usage_observation_digest),
        ):
            _require_digest(
                value,
                field_name=f"CompatibleContextAnchor.{field_name}",
            )
        for field_name, value in (
            ("usage_anchor_tokens", self.usage_anchor_tokens),
            ("conservative_anchor_tokens", self.conservative_anchor_tokens),
        ):
            _require_non_negative_int(
                value,
                field_name=f"CompatibleContextAnchor.{field_name}",
            )
            if value > MAX_CONTEXT_TOKEN_COUNT:
                raise ValueError(f"{field_name} exceeds supported range")


@dataclass(frozen=True, slots=True)
class ContextAnchorResolution:
    """resolver的封闭结果。

    :param anchor: compatible anchor；fallback时为``None``。
    :param fallback_reason: closed fallback reason；anchored时为``None``。
    """

    anchor: CompatibleContextAnchor | None
    fallback_reason: ContextSizingFallbackReason | None

    def __post_init__(self) -> None:
        """校验anchor与fallback reason恰有一个非空。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 两字段同时为空或同时非空时抛出。
        """

        if self.anchor is not None and not isinstance(
            self.anchor,
            CompatibleContextAnchor,
        ):
            raise TypeError("anchor must be CompatibleContextAnchor")
        if self.fallback_reason is not None and not isinstance(
            self.fallback_reason,
            ContextSizingFallbackReason,
        ):
            raise TypeError(
                "fallback_reason must be ContextSizingFallbackReason"
            )
        if (self.anchor is None) == (self.fallback_reason is None):
            raise ValueError(
                "anchor resolution requires exactly one result branch"
            )


@dataclass(frozen=True, slots=True)
class _ManifestEvidence:
    """strict manifest及其EventLog row。"""

    row: EventLogRow
    manifest: RunnerCallInputManifest


@dataclass(frozen=True, slots=True)
class _LinkEvidence:
    """strict accepted iteration link atoms。"""

    row: EventLogRow
    manifest_event_id: str
    manifest_payload_ref: str
    manifest_digest: str
    run_id: str
    attempt_id: str
    execution_id: str
    runner_call_index: int
    runner_call_kind: str
    runner_call_trigger_reason: str
    iteration_id: str
    iteration_index: int
    message_count: int
    role_sequence_digest: str


@dataclass(frozen=True, slots=True)
class _CompletionEvidence:
    """strict accepted iteration completion preview atoms。"""

    row: EventLogRow
    identity: tuple[str, str, str, str]
    finish_reason: str


@dataclass(frozen=True, slots=True)
class _UsageEvidence:
    """strict valid paired usage atoms。"""

    row: EventLogRow
    identity: tuple[str, str, str, str]
    prompt_tokens: int
    observation_digest: str


@dataclass(frozen=True, slots=True)
class _CallEvidence:
    """单次actual runner call的完整lineage结论。"""

    sequence: int
    manifest: _ManifestEvidence
    link: _LinkEvidence
    completion: _CompletionEvidence
    usage: _UsageEvidence | None


@dataclass(frozen=True, slots=True)
class _Barrier:
    """阻止越过查找旧anchor的durable lineage barrier。"""

    sequence: int
    reason: ContextSizingFallbackReason


def resolve_context_anchor(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    query: ContextAnchorQuery,
) -> ContextAnchorResolution:
    """在调用方同一个transaction snapshot内选择compatible anchor。

    扫描使用固定页大小、倒序keyset，并在latest accepted compact boundary停止；
    不设置会截断长Session历史的总条数上限。任何较新的invalid、ambiguous、
    incomplete或compatibility gap都是barrier，resolver不会越过它寻找旧anchor。

    :param transaction: 调用方现有Host transaction。
    :param event_log_store: stateless EventLog primitive。
    :param query: 当前complete candidate compatibility条件。
    :returns: compatible anchor或closed fallback reason。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: query字段非法时由typed boundary抛出。
    """

    if not isinstance(transaction, HostTransaction):
        raise TypeError("transaction must be HostTransaction")
    if not isinstance(event_log_store, EventLogStore):
        raise TypeError("event_log_store must be EventLogStore")
    if not isinstance(query, ContextAnchorQuery):
        raise TypeError("query must be ContextAnchorQuery")
    rows, compact_boundary_found = _read_anchor_rows(
        transaction,
        event_log_store,
        query,
    )
    items = _build_scan_items(
        transaction,
        query=query,
        rows=rows,
    )
    for item in sorted(items, key=lambda value: value.sequence, reverse=True):
        if isinstance(item, _Barrier):
            return _fallback(item.reason)
        mismatch = _compatibility_mismatch(item.manifest.manifest, query)
        if mismatch is not None:
            return _fallback(mismatch)
        if item.usage is None:
            continue
        sizing = item.manifest.manifest.sizing_snapshot
        if (
            item.manifest.row.payload_ref is None
            or item.manifest.row.payload_digest is None
            or sizing.conservative_input_tokens is None
        ):
            return _fallback(ContextSizingFallbackReason.MANIFEST_INCOMPLETE)
        return ContextAnchorResolution(
            anchor=CompatibleContextAnchor(
                manifest_event_id=item.manifest.row.event_id,
                manifest_payload_ref=item.manifest.row.payload_ref,
                manifest_digest=item.manifest.row.payload_digest,
                iteration_link_event_id=item.link.row.event_id,
                usage_event_id=item.usage.row.event_id,
                usage_observation_digest=item.usage.observation_digest,
                iteration_completed_event_id=item.completion.row.event_id,
                usage_anchor_tokens=item.usage.prompt_tokens,
                conservative_anchor_tokens=(
                    sizing.conservative_input_tokens
                ),
            ),
            fallback_reason=None,
        )
    if compact_boundary_found:
        return _fallback(
            ContextSizingFallbackReason.ACCEPTED_COMPACT_INVALIDATED
        )
    return _fallback(ContextSizingFallbackReason.USAGE_MISSING)


def _read_anchor_rows(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    query: ContextAnchorQuery,
) -> tuple[tuple[EventLogRow, ...], bool]:
    """倒序keyset读取anchor相关rows直到compact boundary。

    :param transaction: 调用方transaction。
    :param event_log_store: EventLog primitive。
    :param query: 当前candidate query。
    :returns: boundary之后的rows与是否遇到compact boundary。
    :raises HostDurableError: SQLite row或EventLog row缺失时抛出。
    """

    placeholders = ", ".join("?" for _event_type in _SCAN_EVENT_TYPES)
    before_sequence: int | None = None
    collected: list[EventLogRow] = []
    while True:
        boundary_sql = (
            "event_sequence <= ?"
            if before_sequence is None
            else "event_sequence < ?"
        )
        boundary_value = (
            query.candidate_input_cursor
            if before_sequence is None
            else before_sequence
        )
        page = transaction.fetchall(
            f"""
            SELECT event_id, event_sequence
            FROM {TABLE_EVENT_LOG}
            WHERE session_id = ?
              AND {boundary_sql}
              AND event_type IN ({placeholders})
            ORDER BY event_sequence DESC
            LIMIT ?
            """,
            (
                query.session_id,
                boundary_value,
                *_SCAN_EVENT_TYPES,
                _SCAN_PAGE_SIZE,
            ),
        )
        if not page:
            return (tuple(collected), False)
        for raw in page:
            event_id = raw.get("event_id")
            sequence = raw.get("event_sequence")
            if not isinstance(event_id, str):
                raise HostDurableError("anchor scan event id is invalid")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence < 0
            ):
                raise HostDurableError("anchor scan event sequence is invalid")
            row = event_log_store.read_event_by_id(transaction, event_id)
            if row is None or row.event_sequence != sequence:
                raise HostDurableError("anchor scan EventLog row is missing")
            if row.event_type == _CONTEXT_COMPACTED:
                return (tuple(collected), True)
            collected.append(row)
        before_sequence = _required_page_tail_sequence(page)
        if len(page) < _SCAN_PAGE_SIZE:
            return (tuple(collected), False)


def _build_scan_items(
    transaction: HostTransaction,
    *,
    query: ContextAnchorQuery,
    rows: tuple[EventLogRow, ...],
) -> tuple[_CallEvidence | _Barrier, ...]:
    """把durable rows重建为calls与barriers。

    :param transaction: 当前transaction。
    :param query: 当前candidate query。
    :param rows: compact boundary之后的相关rows。
    :returns: 可按sequence倒序裁决的calls/barriers。
    :raises Exception: 不主动把历史损坏传播为Run失败；统一转barrier。
    """

    manifests: dict[str, _ManifestEvidence] = {}
    compactor_manifest_ids: set[str] = set()
    links: list[_LinkEvidence] = []
    completions: list[_CompletionEvidence] = []
    raw_usage_rows: list[EventLogRow] = []
    items: list[_CallEvidence | _Barrier] = []
    for row in rows:
        if row.event_type == _RUNNER_CALL_INPUT_ASSEMBLED:
            try:
                evidence = _parse_manifest_evidence(
                    transaction,
                    row,
                    query=query,
                )
                manifests[row.event_id] = evidence
                if evidence.manifest.compactor_identity is not None:
                    compactor_manifest_ids.add(row.event_id)
            except (HostDurableError, TypeError, ValueError):
                items.append(
                    _Barrier(
                        sequence=row.event_sequence,
                        reason=ContextSizingFallbackReason.MANIFEST_INCOMPLETE,
                    )
                )
        elif row.event_type == _RUNNER_CALL_INPUT_ITERATION_LINKED:
            try:
                links.append(_parse_link_evidence(row))
            except (HostDurableError, TypeError, ValueError):
                items.append(
                    _Barrier(
                        sequence=row.event_sequence,
                        reason=ContextSizingFallbackReason.ITERATION_LINK_INVALID,
                    )
                )
        elif row.event_type == _ITERATION_COMPLETED:
            try:
                completions.append(_parse_completion_evidence(row))
            except (HostDurableError, TypeError, ValueError):
                items.append(
                    _Barrier(
                        sequence=row.event_sequence,
                        reason=(
                            ContextSizingFallbackReason.ITERATION_INCOMPLETE
                        ),
                    )
                )
        elif row.event_type == _USAGE_REPORTED:
            raw_usage_rows.append(row)
    links_by_manifest: dict[str, list[_LinkEvidence]] = {}
    link_identity_counts: dict[tuple[str, str, str, str], int] = {}
    for link in links:
        links_by_manifest.setdefault(link.manifest_event_id, []).append(link)
        identity = _link_identity(link)
        link_identity_counts[identity] = (
            link_identity_counts.get(identity, 0) + 1
        )
    ambiguous_link_identities = frozenset(
        identity
        for identity, count in link_identity_counts.items()
        if count > 1
    )
    consumed_link_ids: set[str] = set()
    consumed_usage_ids: set[str] = set()
    consumed_completion_ids: set[str] = set()
    for manifest_event_id, manifest_evidence in manifests.items():
        manifest_links = links_by_manifest.get(manifest_event_id, [])
        if manifest_event_id in compactor_manifest_ids:
            for link in manifest_links:
                consumed_link_ids.add(link.row.event_id)
                _consume_identity_events(
                    link,
                    raw_usage_rows=raw_usage_rows,
                    completions=completions,
                    consumed_usage_ids=consumed_usage_ids,
                    consumed_completion_ids=consumed_completion_ids,
                )
            continue
        item = _call_item(
            manifest=manifest_evidence,
            links=manifest_links,
            raw_usage_rows=raw_usage_rows,
            completions=completions,
            consumed_link_ids=consumed_link_ids,
            consumed_usage_ids=consumed_usage_ids,
            consumed_completion_ids=consumed_completion_ids,
            ambiguous_link_identities=ambiguous_link_identities,
        )
        items.append(item)
    for link in links:
        if link.row.event_id not in consumed_link_ids:
            items.append(
                _Barrier(
                    sequence=link.row.event_sequence,
                    reason=ContextSizingFallbackReason.MANIFEST_MISMATCH,
                )
            )
    for usage_row in raw_usage_rows:
        if usage_row.event_id not in consumed_usage_ids:
            items.append(
                _Barrier(
                    sequence=usage_row.event_sequence,
                    reason=ContextSizingFallbackReason.USAGE_INVALID,
                )
            )
    for completion in completions:
        if completion.row.event_id not in consumed_completion_ids:
            items.append(
                _Barrier(
                    sequence=completion.row.event_sequence,
                    reason=ContextSizingFallbackReason.LINEAGE_GAP,
                )
            )
    return tuple(items)


def _call_item(
    *,
    manifest: _ManifestEvidence,
    links: list[_LinkEvidence],
    raw_usage_rows: list[EventLogRow],
    completions: list[_CompletionEvidence],
    consumed_link_ids: set[str],
    consumed_usage_ids: set[str],
    consumed_completion_ids: set[str],
    ambiguous_link_identities: frozenset[tuple[str, str, str, str]],
) -> _CallEvidence | _Barrier:
    """校验单manifest的完整lineage并构造call/barrier。

    :param manifest: strict manifest。
    :param links: 引用该manifest的links。
    :param raw_usage_rows: boundary内usage rows。
    :param completions: boundary内completion rows。
    :param consumed_link_ids: 已归属link ids。
    :param consumed_usage_ids: 已归属usage ids。
    :param consumed_completion_ids: 已归属completion ids。
    :param ambiguous_link_identities: 存在多个accepted link的iteration identities。
    :returns: complete call或closed barrier。
    :raises Exception: 不主动抛出异常。
    """

    if len(links) == 0:
        return _Barrier(
            sequence=manifest.row.event_sequence,
            reason=ContextSizingFallbackReason.ITERATION_LINK_MISSING,
        )
    if len(links) != 1:
        sequence = max(link.row.event_sequence for link in links)
        for duplicate_link in links:
            consumed_link_ids.add(duplicate_link.row.event_id)
            _consume_identity_events(
                duplicate_link,
                raw_usage_rows=raw_usage_rows,
                completions=completions,
                consumed_usage_ids=consumed_usage_ids,
                consumed_completion_ids=consumed_completion_ids,
            )
        return _Barrier(
            sequence=sequence,
            reason=ContextSizingFallbackReason.ITERATION_LINK_INVALID,
        )
    link = links[0]
    consumed_link_ids.add(link.row.event_id)
    if _link_identity(link) in ambiguous_link_identities:
        _consume_identity_events(
            link,
            raw_usage_rows=raw_usage_rows,
            completions=completions,
            consumed_usage_ids=consumed_usage_ids,
            consumed_completion_ids=consumed_completion_ids,
        )
        return _Barrier(
            sequence=link.row.event_sequence,
            reason=ContextSizingFallbackReason.ITERATION_LINK_INVALID,
        )
    if not _link_matches_manifest(link, manifest):
        _consume_identity_events(
            link,
            raw_usage_rows=raw_usage_rows,
            completions=completions,
            consumed_usage_ids=consumed_usage_ids,
            consumed_completion_ids=consumed_completion_ids,
        )
        return _Barrier(
            sequence=link.row.event_sequence,
            reason=ContextSizingFallbackReason.MANIFEST_MISMATCH,
        )
    identity = _link_identity(link)
    matching_completions = [
        completion
        for completion in completions
        if completion.identity == identity
    ]
    matching_usage = [
        row
        for row in raw_usage_rows
        if _row_identity(row) == identity
    ]
    consumed_completion_ids.update(
        completion.row.event_id for completion in matching_completions
    )
    consumed_usage_ids.update(row.event_id for row in matching_usage)
    sequence = max(
        (
            manifest.row.event_sequence,
            link.row.event_sequence,
            *(row.event_sequence for row in matching_usage),
            *(
                completion.row.event_sequence
                for completion in matching_completions
            ),
        )
    )
    if len(matching_completions) == 0:
        return _Barrier(
            sequence=sequence,
            reason=ContextSizingFallbackReason.ITERATION_INCOMPLETE,
        )
    if len(matching_completions) != 1:
        return _Barrier(
            sequence=sequence,
            reason=(
                ContextSizingFallbackReason.ITERATION_COMPLETION_AMBIGUOUS
            ),
        )
    completion = matching_completions[0]
    if completion.finish_reason not in _ELIGIBLE_FINISH_REASONS:
        return _Barrier(
            sequence=sequence,
            reason=(
                ContextSizingFallbackReason.ITERATION_FINISH_REASON_INELIGIBLE
            ),
        )
    if completion.row.event_sequence <= link.row.event_sequence:
        return _Barrier(
            sequence=sequence,
            reason=ContextSizingFallbackReason.ITERATION_INCOMPLETE,
        )
    if len(matching_usage) > 1:
        return _Barrier(
            sequence=sequence,
            reason=ContextSizingFallbackReason.USAGE_AMBIGUOUS,
        )
    usage: _UsageEvidence | None = None
    if matching_usage:
        try:
            usage = _parse_usage_evidence(
                matching_usage[0],
                manifest=manifest,
                link=link,
            )
        except (HostDurableError, TypeError, ValueError):
            return _Barrier(
                sequence=sequence,
                reason=ContextSizingFallbackReason.USAGE_INVALID,
            )
        if (
            usage.row.event_sequence <= link.row.event_sequence
            or completion.row.event_sequence <= usage.row.event_sequence
        ):
            return _Barrier(
                sequence=sequence,
                reason=ContextSizingFallbackReason.LINEAGE_GAP,
            )
    return _CallEvidence(
        sequence=sequence,
        manifest=manifest,
        link=link,
        completion=completion,
        usage=usage,
    )


def _parse_manifest_evidence(
    transaction: HostTransaction,
    row: EventLogRow,
    *,
    query: ContextAnchorQuery,
) -> _ManifestEvidence:
    """strict读取digest-verified manifest。

    :param transaction: 当前transaction。
    :param row: manifest EventLog row。
    :param query: 当前Session query。
    :returns: strict manifest evidence。
    :raises HostDurableError: row/hot/descriptor/manifest任一非法时抛出。
    """

    if (
        row.event_class is not EventClass.CANONICAL_FACT
        or row.session_id != query.session_id
        or row.payload_ref is None
        or row.payload_digest is None
    ):
        raise HostDurableError("runner-call manifest row identity is invalid")
    hot = parse_runner_call_hot_payload(payload_object(row))
    if (
        hot.manifest_payload_ref != row.payload_ref
        or hot.manifest_digest != row.payload_digest
    ):
        raise HostDurableError("runner-call manifest hot descriptor mismatch")
    body = sqlite_payload_object(
        transaction,
        payload_ref=row.payload_ref,
        payload_digest=row.payload_digest,
        payload_label="context anchor runner-call manifest",
    )
    manifest = parse_runner_call_manifest(body, hot_payload=hot)
    if (
        manifest.identity.session_id != row.session_id
        or manifest.identity.host_run_id != row.run_id
        or manifest.identity.attempt_id != row.attempt_id
        or manifest.identity.execution_id != row.execution_id
    ):
        raise HostDurableError("runner-call manifest EventLog scope mismatch")
    return _ManifestEvidence(row=row, manifest=manifest)


def _parse_link_evidence(row: EventLogRow) -> _LinkEvidence:
    """strict parse accepted iteration link。

    :param row: link EventLog row。
    :returns: strict link evidence。
    :raises HostDurableError: shape、identity或complete validation非法时抛出。
    """

    if (
        row.event_class is not EventClass.CANONICAL_FACT
        or row.run_id is None
        or row.attempt_id is None
        or row.execution_id is None
    ):
        raise HostDurableError("iteration link row identity is invalid")
    value = payload_object(row)
    _require_exact_fields(value, _LINK_FIELDS, field_name="iteration link")
    if (
        _required_text(value, "session_id") != row.session_id
        or _required_text(value, "host_run_id") != row.run_id
        or _required_text(value, "attempt_id") != row.attempt_id
        or _required_text(value, "execution_id") != row.execution_id
        or _required_text(value, "validation_status") != "complete"
        or value.get("diagnostic") is not None
        or _required_text(value, "manifest_schema_version")
        != RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION
    ):
        raise HostDurableError("iteration link payload identity is invalid")
    engine_count = _required_non_negative_int(value, "engine_message_count")
    expected_count = _required_non_negative_int(
        value,
        "expected_message_count",
    )
    engine_digest = _required_digest(value, "engine_role_sequence_digest")
    expected_digest = _required_digest(
        value,
        "expected_role_sequence_digest",
    )
    if engine_count != expected_count or engine_digest != expected_digest:
        raise HostDurableError("iteration link validation atoms mismatch")
    require_current_runner_input_serializer_schema_version(
        _required_text(value, "runner_input_serializer_schema_version")
    )
    return _LinkEvidence(
        row=row,
        manifest_event_id=_required_text(value, "manifest_event_id"),
        manifest_payload_ref=_required_text(value, "manifest_payload_ref"),
        manifest_digest=_required_digest(value, "manifest_digest"),
        run_id=row.run_id,
        attempt_id=row.attempt_id,
        execution_id=row.execution_id,
        runner_call_index=_required_non_negative_int(
            value,
            "runner_call_index",
        ),
        runner_call_kind=_required_text(value, "runner_call_kind"),
        runner_call_trigger_reason=_required_text(
            value,
            "runner_call_trigger_reason",
        ),
        iteration_id=_required_text(value, "iteration_id"),
        iteration_index=_required_non_negative_int(value, "iteration_index"),
        message_count=expected_count,
        role_sequence_digest=expected_digest,
    )


def _parse_completion_evidence(row: EventLogRow) -> _CompletionEvidence:
    """strict parse durable accepted iteration completion preview。

    :param row: completion preview row。
    :returns: strict completion evidence。
    :raises HostDurableError: class、shape或identity非法时抛出。
    """

    if (
        row.event_class is not EventClass.PREVIEW
        or row.run_id is None
        or row.attempt_id is None
        or row.execution_id is None
    ):
        raise HostDurableError("iteration completion row identity is invalid")
    value = payload_object(row)
    _require_exact_fields(
        value,
        _COMPLETION_FIELDS,
        field_name="iteration completion",
    )
    if (
        _required_text(value, "attempt_id") != row.attempt_id
        or _required_text(value, "execution_id") != row.execution_id
        or _required_text(value, "engine_event_type")
        != "iteration_completed"
    ):
        raise HostDurableError("iteration completion payload identity mismatch")
    _required_non_negative_int(value, "worker_event_index")
    _optional_text(value, "provider_request_id")
    _optional_text(value, "client_correlation_id")
    iteration_id = _required_text(value, "iteration_id")
    return _CompletionEvidence(
        row=row,
        identity=(
            row.run_id,
            row.attempt_id,
            row.execution_id,
            iteration_id,
        ),
        finish_reason=_required_text(value, "finish_reason"),
    )


def _parse_usage_evidence(
    row: EventLogRow,
    *,
    manifest: _ManifestEvidence,
    link: _LinkEvidence,
) -> _UsageEvidence:
    """strict parse unique valid paired usage observation。

    :param row: usage projection signal。
    :param manifest: exact linked manifest。
    :param link: exact accepted link。
    :returns: strict usage evidence。
    :raises HostDurableError: shape、pairing、digest、identity或range非法时抛出。
    """

    if (
        row.event_class is not EventClass.PROJECTION_SIGNAL
        or row.run_id is None
        or row.attempt_id is None
        or row.execution_id is None
    ):
        raise HostDurableError("usage row identity is invalid")
    value = payload_object(row)
    _require_exact_fields(value, _USAGE_FIELDS, field_name="usage observation")
    identity = _link_identity(link)
    if (
        _required_text(value, "session_id") != row.session_id
        or _required_text(value, "run_id") != row.run_id
        or _required_text(value, "attempt_id") != row.attempt_id
        or _required_text(value, "execution_id") != row.execution_id
        or _required_text(value, "iteration_id") != identity[3]
        or _row_identity(row) != identity
    ):
        raise HostDurableError("usage observation identity mismatch")
    sizing = manifest.manifest.sizing_snapshot
    if (
        sizing.estimator_digest is None
        or sizing.conservative_input_tokens is None
        or sizing.policy_ref is None
        or sizing.input_snapshot_digest is None
    ):
        raise HostDurableError("usage anchor manifest sizing is incomplete")
    prompt_tokens = _required_non_negative_int(value, "prompt_tokens")
    completion_tokens = _required_non_negative_int(
        value,
        "completion_tokens",
    )
    total_tokens = _required_non_negative_int(value, "total_tokens")
    for token_count in (prompt_tokens, completion_tokens, total_tokens):
        if token_count > MAX_CONTEXT_TOKEN_COUNT:
            raise HostDurableError("usage token count exceeds supported range")
    provider_request_id = _optional_text(value, "provider_request_id")
    if (
        _required_text(value, "policy_ref") != sizing.policy_ref
        or _required_text(value, "estimator_digest")
        != sizing.estimator_digest
        or _required_non_negative_int(value, "estimated_input_tokens")
        != sizing.conservative_input_tokens
        or _required_text(value, "usage_observation_status")
        != USAGE_OBSERVATION_STATUS_OBSERVED
        or _required_int(value, "prompt_token_delta")
        != prompt_tokens - sizing.conservative_input_tokens
    ):
        raise HostDurableError("usage observation diagnostic atoms mismatch")
    observation = UsageObservation(
        session_id=row.session_id,
        run_id=row.run_id,
        attempt_id=row.attempt_id,
        execution_id=row.execution_id,
        iteration_id=identity[3],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        provider_request_id=provider_request_id,
        estimator_digest=sizing.estimator_digest,
        policy_ref=sizing.policy_ref,
        observed_at=parse_utc_timestamp(row.occurred_at),
    )
    diagnostic = build_usage_observation_diagnostic(
        observation,
        estimated_input_tokens=sizing.conservative_input_tokens,
        status=USAGE_OBSERVATION_STATUS_OBSERVED,
    )
    observation_digest = _required_digest(
        value,
        "usage_observation_digest",
    )
    if observation_digest != diagnostic.observation_digest:
        raise HostDurableError("usage observation digest mismatch")
    pairing_value = value.get("runner_call_pairing")
    if not isinstance(pairing_value, Mapping):
        raise HostDurableError("runner_call_pairing must be object")
    pairing = _json_mapping(pairing_value)
    _require_exact_fields(
        pairing,
        _USAGE_PAIRING_FIELDS,
        field_name="runner_call_pairing",
    )
    if (
        _required_text(pairing, "status") != "complete"
        or pairing.get("reason") is not None
        or _required_text(pairing, "manifest_event_id")
        != manifest.row.event_id
        or _required_text(pairing, "manifest_payload_ref")
        != link.manifest_payload_ref
        or _required_digest(pairing, "manifest_digest")
        != link.manifest_digest
        or _required_text(pairing, "iteration_link_event_id")
        != link.row.event_id
        or _required_digest(pairing, "input_snapshot_digest")
        != sizing.input_snapshot_digest
        or _required_digest(pairing, "observation_digest")
        != observation_digest
    ):
        raise HostDurableError("usage runner-call pairing mismatch")
    if not isinstance(value.get("context_pressure"), Mapping):
        raise HostDurableError("usage context pressure must be object")
    return _UsageEvidence(
        row=row,
        identity=identity,
        prompt_tokens=prompt_tokens,
        observation_digest=observation_digest,
    )


def _compatibility_mismatch(
    manifest: RunnerCallInputManifest,
    query: ContextAnchorQuery,
) -> ContextSizingFallbackReason | None:
    """比较anchor manifest与当前candidate compatibility atoms。

    :param manifest: strict complete manifest。
    :param query: 当前candidate query。
    :returns: 首个closed mismatch；全部compatible时为``None``。
    :raises Exception: 不主动抛出异常。
    """

    sizing = manifest.sizing_snapshot
    if (
        manifest.validation_status != "complete"
        or manifest.compactor_identity is not None
        or manifest.identity.runner_call_kind
        not in _ELIGIBLE_RUNNER_CALL_KINDS
    ):
        return ContextSizingFallbackReason.RUNNER_CALL_KIND_INELIGIBLE
    if sizing.status is not RunnerCallSizingStatus.COMPLETE:
        return ContextSizingFallbackReason.MANIFEST_INCOMPLETE
    if sizing.provider != query.provider:
        return ContextSizingFallbackReason.PROVIDER_MISMATCH
    if sizing.model != query.model:
        return ContextSizingFallbackReason.MODEL_MISMATCH
    if sizing.context_window_size != query.context_window_size:
        return ContextSizingFallbackReason.CONTEXT_WINDOW_MISMATCH
    if (
        sizing.estimator_id != query.estimator_contract.estimator_id
        or sizing.estimator_version
        != query.estimator_contract.estimator_version
    ):
        return ContextSizingFallbackReason.ESTIMATOR_CONTRACT_MISMATCH
    if sizing.request_semantics_digest != query.request_semantics_digest:
        return ContextSizingFallbackReason.REQUEST_SEMANTICS_MISMATCH
    return None


def _link_matches_manifest(
    link: _LinkEvidence,
    manifest: _ManifestEvidence,
) -> bool:
    """判断link是否唯一精确引用manifest。

    :param link: strict link。
    :param manifest: strict manifest。
    :returns: refs、identity与ordering全部一致时返回``True``。
    :raises Exception: 不主动抛出异常。
    """

    identity = manifest.manifest.identity
    return (
        manifest.row.event_sequence < link.row.event_sequence
        and manifest.row.payload_ref == link.manifest_payload_ref
        and manifest.row.payload_digest == link.manifest_digest
        and identity.host_run_id == link.run_id
        and identity.attempt_id == link.attempt_id
        and identity.execution_id == link.execution_id
        and identity.runner_call_index == link.runner_call_index
        and identity.runner_call_kind == link.runner_call_kind
        and identity.runner_call_trigger_reason
        == link.runner_call_trigger_reason
        and manifest.manifest.message_count == link.message_count
        and manifest.manifest.role_sequence_digest
        == link.role_sequence_digest
        and (
            identity.iteration_id is None
            or identity.iteration_id == link.iteration_id
        )
        and (
            identity.iteration_index is None
            or identity.iteration_index == link.iteration_index
        )
    )


def _consume_identity_events(
    link: _LinkEvidence,
    *,
    raw_usage_rows: list[EventLogRow],
    completions: list[_CompletionEvidence],
    consumed_usage_ids: set[str],
    consumed_completion_ids: set[str],
) -> None:
    """把明确属于excluded compactor identity的events标记为已消费。

    :param link: compactor link。
    :param raw_usage_rows: usage rows。
    :param completions: completion rows。
    :param consumed_usage_ids: consumed usage id集合。
    :param consumed_completion_ids: consumed completion id集合。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    identity = _link_identity(link)
    consumed_usage_ids.update(
        row.event_id for row in raw_usage_rows if _row_identity(row) == identity
    )
    consumed_completion_ids.update(
        completion.row.event_id
        for completion in completions
        if completion.identity == identity
    )


def _link_identity(link: _LinkEvidence) -> tuple[str, str, str, str]:
    """返回link exact iteration identity。

    :param link: strict link。
    :returns: ``(run, attempt, execution, iteration)``。
    :raises Exception: 不主动抛出异常。
    """

    return (
        link.run_id,
        link.attempt_id,
        link.execution_id,
        link.iteration_id,
    )


def _row_identity(row: EventLogRow) -> tuple[str, str, str, str] | None:
    """从usage row读取可比较的iteration identity。

    :param row: EventLog row。
    :returns: identity；row/payload缺失typed字段时为``None``。
    :raises Exception: payload损坏时返回``None``。
    """

    if (
        row.run_id is None
        or row.attempt_id is None
        or row.execution_id is None
    ):
        return None
    try:
        iteration_id = _required_text(payload_object(row), "iteration_id")
    except (HostDurableError, TypeError, ValueError):
        return None
    return (
        row.run_id,
        row.attempt_id,
        row.execution_id,
        iteration_id,
    )


def _required_page_tail_sequence(page: tuple[HostRow, ...]) -> int:
    """读取reverse keyset page尾部sequence。

    :param page: SQLite page rows。
    :returns: 最小sequence，供下一页exclusive cursor使用。
    :raises HostDurableError: row类型非法时抛出。
    """

    value = page[-1].get("event_sequence")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError("anchor scan page tail is invalid")
    return value


def _fallback(reason: ContextSizingFallbackReason) -> ContextAnchorResolution:
    """构造closed fallback resolution。

    :param reason: fallback reason。
    :returns: 无anchor的typed resolution。
    :raises Exception: 不主动抛出异常。
    """

    return ContextAnchorResolution(anchor=None, fallback_reason=reason)


def _require_exact_fields(
    value: Mapping[str, JsonValue],
    expected: frozenset[str],
    *,
    field_name: str,
) -> None:
    """校验JSON object字段集合精确匹配。

    :param value: JSON object。
    :param expected: exact字段集合。
    :param field_name: 错误边界名称。
    :returns: ``None``。
    :raises HostDurableError: 字段缺失或出现unknown字段时抛出。
    """

    if frozenset(value) != expected:
        raise HostDurableError(f"{field_name} fields mismatch")


def _required_text(value: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填非空文本。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises HostDurableError: 字段不是非空文本时抛出。
    """

    result = value.get(field_name)
    if not isinstance(result, str) or result.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")
    return result


def _optional_text(
    value: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取可选非空文本。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 非空文本或``None``。
    :raises HostDurableError: 非空值不是非空文本时抛出。
    """

    result = value.get(field_name)
    if result is None:
        return None
    if not isinstance(result, str) or result.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text or null")
    return result


def _required_digest(value: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填sha256 digest。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: canonical digest。
    :raises HostDurableError: 字段不是sha256 digest时抛出。
    """

    result = _required_text(value, field_name)
    if not is_sha256_digest(result):
        raise HostDurableError(f"{field_name} must be sha256 digest")
    return result


def _required_non_negative_int(
    value: Mapping[str, JsonValue],
    field_name: str,
) -> int:
    """读取严格非负整数。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 非负整数。
    :raises HostDurableError: 字段不是严格非负整数时抛出。
    """

    result = value.get(field_name)
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        raise HostDurableError(f"{field_name} must be non-negative int")
    return result


def _required_int(value: Mapping[str, JsonValue], field_name: str) -> int:
    """读取严格整数。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 整数。
    :raises HostDurableError: 字段不是严格整数时抛出。
    """

    result = value.get(field_name)
    if isinstance(result, bool) or not isinstance(result, int):
        raise HostDurableError(f"{field_name} must be int")
    return result


def _json_mapping(value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    """保留已由runtime证明的JSON mapping窄类型。

    :param value: JSON mapping。
    :returns: 原mapping。
    :raises Exception: 不主动抛出异常。
    """

    return value


def _require_text(value: str, *, field_name: str) -> None:
    """校验非空文本。

    :param value: 待校验值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises ValueError: 值不是非空文本时抛出。
    """

    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty text")


def _require_digest(value: str, *, field_name: str) -> None:
    """校验sha256 digest。

    :param value: 待校验值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises ValueError: 值不是sha256 digest时抛出。
    """

    if not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be sha256 digest")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验严格非负整数。

    :param value: 待校验值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 值不是严格整数时抛出。
    :raises ValueError: 值为负数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_positive_int(value: int, *, field_name: str) -> None:
    """校验严格正整数。

    :param value: 待校验值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 值不是严格整数时抛出。
    :raises ValueError: 值不为正时抛出。
    """

    _require_non_negative_int(value, field_name=field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


__all__ = [
    "CompatibleContextAnchor",
    "ContextAnchorQuery",
    "ContextAnchorResolution",
    "resolve_context_anchor",
]
