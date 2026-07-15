"""R03 real public-run smoke 的纯 assembly 与 stdout security guard 测试。"""

from __future__ import annotations

import inspect
import pathlib
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host.accepted_tool_outcome import accepted_tool_outcome_json
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
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
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    accepted_evidence_envelope_to_json_value,
    derive_accepted_evidence_id,
)
from dayu.host.payload_resolution import ToolCallRequestAtoms
from dayu.host.tool_call_request import (
    AcceptedToolCallRequestAtomInput,
    ToolCallRequestEventOrigin,
    build_tool_call_requested_event_request,
)
from utils.smoke_host_public_r03_semantic_ownership import (
    AwaitingRequestIdentity,
    FinsAwaitingTool,
    SmokeArgs,
    _OPAQUE_SENTINELS,
    _accepted_projection,
    _canonical_fact_rows,
    _expected_required_tool_calls,
    _forbidden_awaiting_duplicate_fields,
    _round_specs,
    _safe_summary_text,
    _strict_accepted_request_atoms,
    _validate_required_request_atoms,
    _validate_tool_awaiting_payload_contract,
    _workspace_retention_summary,
    parse_args,
    prepare_runtime_assembly,
    run_smoke,
)

_PROVIDER_ENV = {
    "DEEPSEEK_API_KEY": "test-deepseek-provider-key",
    "MIMO_PLAN_API_KEY": "test-mimo-provider-key",
}


def test_cli_parses_all_explicit_smoke_inputs(tmp_path: pathlib.Path) -> None:
    """CLI 把 public smoke 输入解析为直接 typed fields。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 显式参数被丢失、藏入 extra 或 choice 失效时抛出。
    """

    doc_file = tmp_path / "report.txt"
    args = parse_args(
        (
            "--workspace-root",
            str(tmp_path / "workspace"),
            "--scene-id",
            "interactive",
            "--doc-file",
            str(doc_file),
            "--web-query",
            "OpenAI official documentation",
            "--fins-ticker",
            "MSFT",
            "--fins-document-id",
            "MSFT-10K-2025",
            "--fins-awaiting-tool",
            "start_fins_preprocess",
            "--keep-workspace",
        )
    )

    assert args.workspace_root == (tmp_path / "workspace").resolve()
    assert args.doc_file == doc_file.resolve()
    assert args.scene_id == "interactive"
    assert args.web_query == "OpenAI official documentation"
    assert args.fins_ticker == "MSFT"
    assert args.fins_document_id == "MSFT-10K-2025"
    assert args.fins_awaiting_tool is FinsAwaitingTool.PREPROCESS
    assert args.keep_workspace is True


def test_runtime_assembly_uses_real_configured_tools_and_production_poller(
    tmp_path: pathlib.Path,
) -> None:
    """assembly 使用真实 Doc/Web/Fins definitions、provider 与 wait poller。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: assembly 注入 fake/scripted runner/tool 或未启用 poller 时抛出。
    """

    args = _args(tmp_path)
    args.doc_file.parent.mkdir(parents=True)
    args.doc_file.write_text("R03 semantic ownership fixture", encoding="utf-8")

    assembly = prepare_runtime_assembly(args, env=_PROVIDER_ENV)

    tool_names = frozenset(
        definition.name
        for definition in assembly.discovered_tools.tool_bundle.definitions
    )
    assert {
        "read_file",
        "search_web",
        "list_documents",
        "get_document_sections",
        "start_fins_preprocess",
        "start_fins_download",
        "start_fins_upload",
    }.issubset(tool_names)
    assert assembly.options.wait_poller_policy is not None
    assert type(assembly.options.worker_factory).__name__ == (
        "DefaultLocalEngineWorkerFactory"
    )
    assert "fake" not in type(assembly.options.worker_factory).__name__.lower()
    assert "scripted" not in type(assembly.options.worker_factory).__name__.lower()
    assert assembly.scene_inputs.system_prompt.strip() != ""
    assert assembly.options.ordinary_run_baseline.runner_spec.headers[
        "Authorization"
    ] in {
        "Bearer test-deepseek-provider-key",
        "Bearer test-mimo-provider-key",
    }


def test_round_specs_use_only_public_submit_inputs_and_exact_tool_sets(
    tmp_path: pathlib.Path,
) -> None:
    """round specs 只携带 user prompt 与 exact tool names，不写 wait result。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 工具轮次、显式参数或 no-tool observation 不符合 contract 时抛出。
    """

    args = _args(tmp_path)
    specs = _round_specs(args)

    assert tuple(label for label, _prompt, _tools in specs) == (
        "doc",
        "web",
        "fins-awaiting",
        "fins-list",
        "fins-read",
        "observation",
    )
    assert tuple(tools for _label, _prompt, tools in specs) == (
        frozenset({"read_file"}),
        frozenset({"search_web"}),
        frozenset({"start_fins_preprocess"}),
        frozenset({"list_documents"}),
        frozenset({"get_document_sections"}),
        frozenset(),
    )
    prompt_text = "\n".join(prompt for _label, prompt, _tools in specs)
    assert str(args.doc_file) in prompt_text
    assert args.web_query in prompt_text
    assert args.fins_ticker in prompt_text
    assert args.fins_document_id in prompt_text
    fins_list_prompt = specs[3][1]
    fins_read_prompt = specs[4][1]
    assert "documents[].document_id" in fins_list_prompt
    assert "上一轮 list_documents 已用于验证" in fins_read_prompt
    assert "只有当上一轮同 ticker" in fins_read_prompt
    assert "本轮必须停止且不得调用工具" in fins_read_prompt
    assert "禁止猜测" in fins_read_prompt
    assert "extra" not in prompt_text
    assert "手工写" not in prompt_text


@pytest.mark.parametrize("awaiting_tool", tuple(FinsAwaitingTool))
def test_expected_exact_arguments_cover_every_awaiting_variant(
    tmp_path: pathlib.Path,
    awaiting_tool: FinsAwaitingTool,
) -> None:
    """typed expected calls 覆盖三个 awaiting variant 与 Fins grounding/read。

    :param tmp_path: pytest 临时目录。
    :param awaiting_tool: 当前验证的 selected Fins awaiting tool。
    :returns: ``None``。
    :raises AssertionError: expected arguments 与 prompt/schema contract 漂移时抛出。
    """

    args = replace(_args(tmp_path), fins_awaiting_tool=awaiting_tool)
    expected_calls = {
        call.tool_name: dict(call.arguments)
        for call in _expected_required_tool_calls(args)
    }

    assert len(expected_calls) == 5
    assert expected_calls["read_file"] == {"file_path": str(args.doc_file)}
    assert expected_calls["search_web"] == {"query": args.web_query}
    assert expected_calls["list_documents"] == {"ticker": args.fins_ticker}
    assert expected_calls["get_document_sections"] == {
        "ticker": args.fins_ticker,
        "document_id": args.fins_document_id,
    }
    if awaiting_tool is FinsAwaitingTool.PREPROCESS:
        assert expected_calls[awaiting_tool.value] == {
            "ticker": args.fins_ticker,
            "document_ids": [args.fins_document_id],
            "rebuild_processed": False,
        }
    elif awaiting_tool is FinsAwaitingTool.DOWNLOAD:
        assert expected_calls[awaiting_tool.value] == {
            "ticker": args.fins_ticker,
            "source": "auto",
            "overwrite_existing": False,
            "rebuild_processed": False,
        }
    else:
        assert expected_calls[awaiting_tool.value] == {
            "ticker": args.fins_ticker,
            "upload_kind": "material",
            "action": "auto",
            "files": [str(args.doc_file)],
            "form_type": "R03_SMOKE",
            "material_name": "R03 semantic ownership smoke",
            "document_id": args.fins_document_id,
        }
    assert _round_specs(args)[2][2] == frozenset({awaiting_tool.value})
    strict_atoms: list[ToolCallRequestAtoms] = []
    for index, expected_call in enumerate(
        _expected_required_tool_calls(args),
        start=1,
    ):
        arguments_json: dict[str, JsonValue] = {
            "arguments": dict(expected_call.arguments)
        }
        arguments_digest = sha256_digest_json(arguments_json)
        strict_atoms.append(
            ToolCallRequestAtoms(
                tool_call_id=f"tool-call-{index}",
                tool_name=expected_call.tool_name,
                arguments_json=arguments_json,
                normalized_arguments_digest=arguments_digest,
                arguments_payload_digest=arguments_digest,
                semantic_input_digest=sha256_digest_json(
                    {"semantic": expected_call.tool_name}
                ),
                semantic_query_text=None,
                semantic_query_digest=None,
            )
        )
    _validate_required_request_atoms(args, strict_atoms)


def test_strict_diagnostic_collection_ignores_engine_previews(
    tmp_path: pathlib.Path,
) -> None:
    """同名 Engine preview 不进入 strict request/result semantic 集。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: preview 被 strict parser/projection 消费，或 canonical
        request/result 未按 exact owner contract 校验时抛出。
    """

    event_log = EventLogStore()
    accepted_arguments: dict[str, JsonValue] = {
        "file_path": str(tmp_path / "report.txt")
    }
    arguments_json: dict[str, JsonValue] = {
        "arguments": accepted_arguments,
    }
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_input_digest = sha256_digest_json({"semantic": "read report"})
    raw_tool_outcome = accepted_tool_outcome_json(
        ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"summary": "diagnostic projection result"},
                meta=None,
            )
        )
    )
    with open_host_durable_store(_diagnostic_options(tmp_path)) as store:
        def seed(
            transaction: HostTransaction,
        ) -> tuple[
            EventLogRow,
            EventLogRow,
            EventLogRow,
            EventLogRow,
            EventLogRow,
            EventLogRow,
        ]:
            """写入 request/awaiting/result 的 preview 与 canonical rows。

            :param transaction: Host write transaction。
            :returns: 三组 preview/canonical rows。
            :raises HostDurableError: EventLog、request atom 或 evidence 写入失败时
                抛出。
            """

            preview_request = event_log.append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-engine-request-preview",
                    event_class=EventClass.PREVIEW,
                    session_id="session-smoke-diagnostic",
                    run_id="run-smoke-diagnostic",
                    attempt_id="attempt-smoke-diagnostic",
                    execution_id="execution-smoke-diagnostic",
                    event_type="TOOL_CALL_REQUESTED",
                    occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
                    actor="host.engine_ingest",
                    source="host.engine_ingest",
                    client_request_id=None,
                    idempotency_key="preview-request",
                    policy_decision=None,
                    reason=None,
                    payload_json={
                        "tool_call_id": "tool-call-smoke-diagnostic",
                        "tool_name": "read_file",
                        "argument_key_count": 1,
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
            canonical_request = event_log.append_event(
                transaction,
                build_tool_call_requested_event_request(
                    transaction,
                    atom=AcceptedToolCallRequestAtomInput(
                        session_id="session-smoke-diagnostic",
                        run_id="run-smoke-diagnostic",
                        attempt_id="attempt-smoke-diagnostic",
                        execution_id="execution-smoke-diagnostic",
                        iteration_id="iteration-smoke-diagnostic",
                        tool_call_id="tool-call-smoke-diagnostic",
                        tool_name="read_file",
                        tool_schema_digest=sha256_digest_json(
                            {"schema": "read_file"}
                        ),
                        tool_identity_digest=sha256_digest_json(
                            {"identity": "read_file"}
                        ),
                        accepted_arguments=accepted_arguments,
                        normalized_arguments_digest=arguments_digest,
                        tool_fact_kind="completed",
                        accept_idempotency_key="accepted-request",
                        semantic_input_digest=semantic_input_digest,
                        semantic_query_text="Read the selected report",
                    ),
                    event_id="event-canonical-request",
                    occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
                    origin=ToolCallRequestEventOrigin.ORDINARY_ACCEPT,
                ),
            ).row
            canonical_awaiting = event_log.append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-canonical-awaiting",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id="session-smoke-diagnostic",
                    run_id="run-smoke-diagnostic",
                    attempt_id="attempt-smoke-diagnostic",
                    execution_id="execution-smoke-diagnostic",
                    event_type="TOOL_AWAITING",
                    occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
                    actor="host.tool_runtime",
                    source="host.tool_runtime.awaiting_accept",
                    client_request_id=None,
                    idempotency_key="canonical-awaiting",
                    policy_decision=None,
                    reason=None,
                    payload_json={
                        "tool_call_id": "tool-call-smoke-diagnostic",
                        "tool_name": "read_file",
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
            preview_awaiting = event_log.append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-engine-awaiting-preview",
                    event_class=EventClass.PREVIEW,
                    session_id="session-smoke-diagnostic",
                    run_id="run-smoke-diagnostic",
                    attempt_id="attempt-smoke-diagnostic",
                    execution_id="execution-smoke-diagnostic",
                    event_type="TOOL_AWAITING",
                    occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
                    actor="host.engine_ingest",
                    source="host.engine_ingest",
                    client_request_id=None,
                    idempotency_key="preview-awaiting",
                    policy_decision=None,
                    reason=None,
                    payload_json={
                        "tool_call_id": "tool-call-smoke-diagnostic",
                        "tool_name": "read_file",
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
            result_event_id = "event-canonical-result"
            envelope = AcceptedEvidenceEnvelope(
                evidence_id=derive_accepted_evidence_id(result_event_id),
                producer_event_ref=result_event_id,
                tool_name="read_file",
                tool_call_id="tool-call-smoke-diagnostic",
                tool_query=AcceptedEvidenceToolQuery(
                    tool_call_requested_event_ref=canonical_request.event_id,
                    normalized_arguments_digest=arguments_digest,
                    semantic_input_digest=semantic_input_digest,
                ),
                result_ref=AcceptedEvidenceResultRef(
                    payload_ref=None,
                    payload_digest=None,
                    outcome_digest=sha256_digest_json(raw_tool_outcome),
                    truncation_applied=False,
                ),
                source_refs=(),
                locator_refs=(),
            )
            canonical_result = event_log.append_event(
                transaction,
                EventLogAppendRequest(
                    event_id=result_event_id,
                    event_class=EventClass.CANONICAL_FACT,
                    session_id="session-smoke-diagnostic",
                    run_id="run-smoke-diagnostic",
                    attempt_id="attempt-smoke-diagnostic",
                    execution_id="execution-smoke-diagnostic",
                    event_type="TOOL_RESULT_ACCEPTED",
                    occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
                    actor="host.tool_runtime",
                    source="host.tool_runtime.accept",
                    client_request_id=None,
                    idempotency_key="canonical-result",
                    policy_decision=None,
                    reason=None,
                    payload_json={
                        "tool_call_id": "tool-call-smoke-diagnostic",
                        "tool_name": "read_file",
                        "normalized_arguments_digest": arguments_digest,
                        "tool_fact_kind": "completed",
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(envelope)
                        ),
                        "raw_tool_outcome": raw_tool_outcome,
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
            preview_result = event_log.append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-engine-result-preview",
                    event_class=EventClass.PREVIEW,
                    session_id="session-smoke-diagnostic",
                    run_id="run-smoke-diagnostic",
                    attempt_id="attempt-smoke-diagnostic",
                    execution_id="execution-smoke-diagnostic",
                    event_type="TOOL_RESULT_ACCEPTED",
                    occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
                    actor="host.engine_ingest",
                    source="host.engine_ingest",
                    client_request_id=None,
                    idempotency_key="preview-result",
                    policy_decision=None,
                    reason=None,
                    payload_json={
                        "tool_call_id": "tool-call-smoke-diagnostic",
                        "tool_name": "read_file",
                        "has_result": True,
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
            return (
                preview_request,
                canonical_request,
                preview_awaiting,
                canonical_awaiting,
                preview_result,
                canonical_result,
            )

        (
            preview_request,
            canonical_request,
            preview_awaiting,
            canonical_awaiting,
            preview_result,
            canonical_result,
        ) = store.transaction_runner.run_write(seed)
        strict_rows = store.transaction_runner.run_read(
            lambda transaction: _strict_accepted_request_atoms(
                transaction,
                (preview_request, canonical_request),
            )
        )
        awaiting_rows = _canonical_fact_rows(
            (preview_awaiting, canonical_awaiting),
            event_type="TOOL_AWAITING",
        )
        result_rows = _canonical_fact_rows(
            (preview_result, canonical_result),
            event_type="TOOL_RESULT_ACCEPTED",
        )
        result_projections = store.transaction_runner.run_read(
            lambda transaction: tuple(
                _accepted_projection(transaction, row) for row in result_rows
            )
        )

        assert len(strict_rows) == 1
        parsed_row, atoms = strict_rows[0]
        assert parsed_row.event_id == canonical_request.event_id
        assert parsed_row.event_class is EventClass.CANONICAL_FACT
        assert atoms.arguments_json == arguments_json
        assert atoms.normalized_arguments_digest == arguments_digest
        assert atoms.arguments_payload_digest == arguments_digest
        assert tuple(row.event_id for row in awaiting_rows) == (
            canonical_awaiting.event_id,
        )
        assert tuple(row.event_id for row in result_rows) == (
            canonical_result.event_id,
        )
        assert len(result_projections) == 1
        projection = result_projections[0]
        assert projection.llm_material is not None
        assert projection.llm_material.result_text == canonical_json_dumps(
            raw_tool_outcome
        )


@pytest.mark.parametrize("awaiting_tool", tuple(FinsAwaitingTool))
def test_tool_awaiting_contract_accepts_only_request_link_for_all_variants(
    awaiting_tool: FinsAwaitingTool,
) -> None:
    """三个 awaiting variant 的治理 payload 只通过 strict request link 取参数。

    :param awaiting_tool: 当前验证的 selected Fins awaiting tool。
    :returns: ``None``。
    :raises AssertionError: 合法治理 payload 被拒绝或含 arguments 副本时抛出。
    """

    identity = _awaiting_identity(awaiting_tool)
    payload = _valid_awaiting_payload(identity)

    assert _forbidden_awaiting_duplicate_fields(payload) == ()
    _validate_tool_awaiting_payload_contract(
        payload,
        expected_request=identity,
    )


@pytest.mark.parametrize(
    "forbidden_field",
    (
        "accepted_arguments",
        "accepted_arguments_source_digest",
        "normalized_arguments_digest",
        "arguments_payload_digest",
    ),
)
def test_tool_awaiting_contract_rejects_every_argument_duplicate_field(
    forbidden_field: str,
) -> None:
    """TOOL_AWAITING forbidden arguments/digest 副本全部 fail closed。

    :param forbidden_field: 注入的 request arguments/digest 副本字段。
    :returns: ``None``。
    :raises AssertionError: forbidden 字段未被 helper 拒绝时抛出。
    """

    identity = _awaiting_identity(FinsAwaitingTool.PREPROCESS)
    payload = _valid_awaiting_payload(identity)
    payload[forbidden_field] = "forbidden-copy"

    assert forbidden_field in _forbidden_awaiting_duplicate_fields(payload)
    with pytest.raises(RuntimeError, match="duplicated request arguments/digest"):
        _validate_tool_awaiting_payload_contract(
            payload,
            expected_request=identity,
        )


def test_tool_awaiting_contract_rejects_wrong_request_link() -> None:
    """TOOL_AWAITING link 必须指向 selected awaiting request。

    :returns: ``None``。
    :raises AssertionError: wrong request link 未 fail closed 时抛出。
    """

    identity = _awaiting_identity(FinsAwaitingTool.PREPROCESS)
    payload = _valid_awaiting_payload(identity)
    payload["tool_call_requested_event_ref"] = {
        "event_id": "event-request-other",
        "event_sequence": identity.event_sequence,
    }

    with pytest.raises(RuntimeError, match="event_id link mismatch"):
        _validate_tool_awaiting_payload_contract(
            payload,
            expected_request=identity,
        )


def test_stdout_failure_summary_redacts_secrets_and_bounds_text() -> None:
    """stdout failure summary 不输出 secret、header 或无界异常正文。

    :returns: ``None``。
    :raises AssertionError: secret marker 未脱敏或摘要未截断时抛出。
    """

    for secret_text in (
        "Authorization: Bearer provider-secret",
        "api_key=provider-secret",
        "Cookie: session=provider-secret",
        "access token provider-secret",
    ):
        assert _safe_summary_text(secret_text) == "<redacted>"
    bounded = _safe_summary_text("x" * 1_000)
    assert bounded.endswith("...")
    assert len(bounded) < 300


def test_workspace_retention_summary_always_matches_non_destructive_behavior() -> None:
    """workspace 无论 CLI marker 是否显式提供都如实声明 kept=true。

    :returns: ``None``。
    :raises AssertionError: 输出声称删除 artifacts 或 kept=false 时抛出。
    """

    assert _workspace_retention_summary(False) == (
        "R03 SMOKE WORKSPACE_KEPT true caller_requested=false cleanup=never"
    )
    assert _workspace_retention_summary(True) == (
        "R03 SMOKE WORKSPACE_KEPT true caller_requested=true cleanup=never"
    )


def test_public_chain_source_and_output_guard_are_explicit() -> None:
    """源码固定 public execution chain 与 internal diagnostic read/output 边界。

    :returns: ``None``。
    :raises AssertionError: 脚本绕过 public Host、打印敏感输入或伪造 wait result 时抛出。
    """

    source = inspect.getsource(run_smoke)
    assert "open_host(assembly.options)" in source
    assert "host.ensure_session" in source
    assert "_run_round" in source
    assert "_read_internal_projection_observation" in source
    assert "resolve_wait" not in source
    assert "raw_tool_outcome" not in source
    assert "headers" not in source
    assert "system_prompt" not in source
    for sentinel in _OPAQUE_SENTINELS:
        assert sentinel not in source


def _awaiting_identity(awaiting_tool: FinsAwaitingTool) -> AwaitingRequestIdentity:
    """构造 assembly guard 使用的 selected awaiting request identity。

    :param awaiting_tool: selected Fins awaiting tool。
    :returns: typed request identity。
    :raises Exception: 不主动抛出异常。
    """

    return AwaitingRequestIdentity(
        event_id="event-request-awaiting",
        event_sequence=42,
        tool_call_id="tool-call-awaiting",
        tool_name=awaiting_tool.value,
    )


def _valid_awaiting_payload(
    identity: AwaitingRequestIdentity,
) -> dict[str, JsonValue]:
    """构造只含治理字段与 canonical request link 的测试 payload。

    :param identity: selected awaiting request identity。
    :returns: 合规 TOOL_AWAITING payload。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "tool_name": identity.tool_name,
        "tool_call_id": identity.tool_call_id,
        "tool_call_requested_event_ref": {
            "event_id": identity.event_id,
            "event_sequence": identity.event_sequence,
        },
        "semantic_input_digest": "sha256:" + "a" * 64,
    }


def _diagnostic_options(tmp_path: pathlib.Path) -> HostDurableStoreOptions:
    """构造 smoke diagnostic 测试使用的 durable store 配置。

    :param tmp_path: pytest 提供的临时目录。
    :returns: 指向临时 SQLite 与 artifact 目录的 durable store 配置。
    :raises ValueError: 当底层配置拒绝无效存储参数时抛出。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "diagnostic.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _args(tmp_path: pathlib.Path) -> SmokeArgs:
    """构造纯 assembly 测试参数。

    :param tmp_path: pytest 临时目录。
    :returns: typed SmokeArgs。
    :raises Exception: 不主动抛出异常。
    """

    return SmokeArgs(
        workspace_root=(tmp_path / "workspace").resolve(),
        scene_id="interactive",
        doc_file=(tmp_path / "inputs" / "report.txt").resolve(),
        web_query="OpenAI official documentation",
        fins_ticker="MSFT",
        fins_document_id="MSFT-10K-2025",
        fins_awaiting_tool=FinsAwaitingTool.PREPROCESS,
        keep_workspace=True,
    )
