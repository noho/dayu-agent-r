"""``dayu-cli session`` helper 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import TracebackType
from collections.abc import Callable
from typing import cast

import pytest

import dayu.cli.commands.session as session_command
import dayu.cli.commands.prompt as prompt_command
import dayu.cli.commands.interactive as interactive_command
import dayu.cli.main as cli_main
import dayu.cli.session_execution as session_execution
from dayu.cli.host_api_errors import (
    CliHostApiErrorTarget,
    exit_code_for_host_api_error,
    format_host_api_error,
)
from dayu.cli.agent_entrypoint import CliSigintMonitor, package_config_root
from dayu.cli.arg_parsing import ParsedCliArgs
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.cli.output import render_session_list, render_session_purge_result
from dayu.cli.session_identity import (
    CliSessionDisplayKind,
    display_identity_from_slot,
    slot_ref_for_cli_label,
)
from dayu.contracts import JsonValue
from dayu.host.api import (
    CloseSessionRequest,
    CreateSessionRequest,
    FollowupBehavior,
    FollowupSnapshot,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostCommandHandleOptions,
    HostSessionAccessMode,
    HostSessionAttachment,
    HostStreamCursor,
    ListSessionsResult,
    OperationContext,
    PurgeSessionRequest,
    PurgeSessionResult,
    SessionSnapshot,
    SessionListItem,
    SessionSlotRef,
    SessionStatus,
    SubmitFollowupRequest,
    RunStatus,
)
from dayu.host.command import (
    close_session as command_close_session,
    create_host_command_handle,
    create_session as command_create_session,
)
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeError,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
)
from dayu.service.host_assembly import ServiceRunOverrides
from dayu.service.host_admin import ServiceHostAdminRequest, prepare_host_admin

_MODEL_ID = "deepseek-v4-flash"


def test_host_api_error_policy_maps_explicit_selector_not_found_to_usage() -> None:
    """显式 session id selector 的 NOT_FOUND 必须映射为 usage error。"""

    error = HostApiError(
        code=HostApiErrorCode.NOT_FOUND,
        message="session not found",
        retryable=False,
    )

    exit_code = exit_code_for_host_api_error(
        error,
        target=CliHostApiErrorTarget(
            selector="--session-id missing",
            session_id="missing",
            explicit_session_id_selector=True,
            resolved_from_label=False,
        ),
    )

    assert exit_code == EXIT_USAGE_ERROR


def test_host_api_error_policy_maps_label_toctou_not_found_to_failure() -> None:
    """label 已解析后的 NOT_FOUND TOCTOU 必须映射为 failure。"""

    error = HostApiError(
        code=HostApiErrorCode.NOT_FOUND,
        message="session vanished",
        retryable=False,
    )

    exit_code = exit_code_for_host_api_error(
        error,
        target=CliHostApiErrorTarget(
            selector="--label alpha",
            session_id="session-A",
            explicit_session_id_selector=False,
            resolved_from_label=True,
        ),
    )

    assert exit_code == EXIT_FAILURE


def test_host_api_error_policy_maps_prompt_interactive_not_found_to_failure() -> None:
    """prompt/interactive 无显式 session selector 时 NOT_FOUND 必须是 failure。"""

    error = HostApiError(
        code=HostApiErrorCode.NOT_FOUND,
        message="slot missing",
        retryable=False,
    )

    assert exit_code_for_host_api_error(error) == EXIT_FAILURE


def test_host_api_error_formatter_keeps_core_code_and_message() -> None:
    """HostApiError formatter 必须保留统一 host_code / host_message 核心。"""

    error = HostApiError(
        code=HostApiErrorCode.CONFLICT,
        message="write conflict",
        retryable=True,
    )

    rendered = format_host_api_error("prompt", error)

    assert "dayu-cli prompt" in rendered
    assert "host_code=conflict" in rendered
    assert "host_message=write conflict" in rendered
    assert exit_code_for_host_api_error(error) == EXIT_FAILURE


@dataclass(frozen=True, slots=True)
class _FakeHostAssembly:
    """测试用 Host assembly。"""

    options: str


@dataclass(frozen=True, slots=True)
class _FakeAdminAssembly:
    """测试用 HostAdmin assembly。"""

    options: str


@dataclass(frozen=True, slots=True)
class _FakeRuntime:
    """测试用 entrypoint runtime result。"""

    host_assembly: _FakeHostAssembly


@dataclass(slots=True)
class _FakeRuntimeCapture:
    """测试用 admin assembly request capture。"""

    requests: list[ParsedCliArgs]


@dataclass(slots=True)
class _FakeResumeCapture:
    """测试用 resume helper 调用记录。"""

    prompt_prepare_calls: list[str]
    interactive_prepare_calls: list[str]
    prompt_execute_sessions: list[str]
    interactive_execute_sessions: list[str]
    prompt_display_flags: list[tuple[bool, bool]]
    interactive_display_flags: list[tuple[bool, bool]]


class _FakeHostContext:
    """测试用 Host async context manager。"""

    _host: "_FakeSessionHost"

    def __init__(self, host: "_FakeSessionHost") -> None:
        """初始化 fake context manager。

        :param host: 待返回的 fake Host。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._host = host

    async def __aenter__(self) -> Host:
        """进入 async context 并返回 fake Host。

        :returns: fake Host，经测试边界 cast 为 Host protocol。
        :raises Exception: 不主动抛出异常。
        """

        return cast(Host, self._host)

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """退出 async context。

        :param _exc_type: 异常类型；未发生异常时为 ``None``。
        :param _exc: 异常实例；未发生异常时为 ``None``。
        :param _traceback: traceback；未发生异常时为 ``None``。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """


class _FakeSessionAttachment:
    """CLI session resume fake Host 返回的显式 RW attachment。"""

    def __init__(self, session_id: str) -> None:
        """初始化测试 attachment。

        :param session_id: attachment 绑定的 Session id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.session_id = session_id
        self.access_mode = HostSessionAccessMode.READ_WRITE
        self.close_count = 0

    async def aclose(self) -> None:
        """记录 attachment lexical close。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1


class _FakeSessionHost:
    """测试用 Session Host public API fake。"""

    list_result: ListSessionsResult
    purge_result: PurgeSessionResult
    purge_error: HostApiError | None
    get_session_status: SessionStatus
    submit_error: HostApiError | None
    calls: list[str]
    purge_requests: list[tuple[str, PurgeSessionRequest]]
    submit_requests: list[tuple[str, SubmitFollowupRequest]]
    close_cancel_calls: int
    attach_session_ids: list[str]
    attachments: list[_FakeSessionAttachment]

    def __init__(
        self,
        *,
        list_result: ListSessionsResult,
        purge_result: PurgeSessionResult | None = None,
        purge_error: HostApiError | None = None,
        get_session_status: SessionStatus = SessionStatus.OPEN,
        submit_error: HostApiError | None = None,
    ) -> None:
        """初始化 fake Host。

        :param list_result: ``list_sessions`` 返回值。
        :param purge_result: ``purge_session`` 成功返回值。
        :param purge_error: ``purge_session`` 需要抛出的 Host 错误。
        :param get_session_status: ``get_session`` 返回的 Session status。
        :param submit_error: ``submit_followup`` 需要抛出的 Host 错误。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.list_result = list_result
        self.purge_result = purge_result or PurgeSessionResult(
            session_id="session-purged",
            purged=True,
            purge_tombstone_ref="tombstone-ref-abcdef",
            deleted_counts_digest="sha256:hidden",
        )
        self.purge_error = purge_error
        self.get_session_status = get_session_status
        self.submit_error = submit_error
        self.calls = []
        self.purge_requests = []
        self.submit_requests = []
        self.close_cancel_calls = 0
        self.attach_session_ids = []
        self.attachments = []

    async def attach_session(self, session_id: str) -> HostSessionAttachment:
        """记录显式 Session attachment 并返回可关闭对象。

        :param session_id: 目标 Session id。
        :returns: 测试用 RW attachment。
        :raises Exception: 不主动抛出异常。
        """

        attachment = _FakeSessionAttachment(session_id)
        self.attach_session_ids.append(session_id)
        self.attachments.append(attachment)
        return attachment

    async def list_sessions(self) -> ListSessionsResult:
        """返回预设 Session 列表并记录调用。

        :returns: 预设 list result。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append("list_sessions")
        return self.list_result

    async def get_session(self, session_id: str) -> SessionSnapshot:
        """返回预设状态的 Session snapshot 并记录调用。

        :param session_id: 目标 Session id。
        :returns: Session snapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"get_session:{session_id}")
        return _session_snapshot(session_id=session_id, status=self.get_session_status)

    async def submit_followup(
        self,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """记录 submit_followup 请求并返回或抛出预设结果。

        :param session_id: 目标 Session id。
        :param request: SubmitFollowupRequest。
        :returns: FollowupSnapshot。
        :raises HostApiError: 测试配置要求模拟 Host 失败时抛出。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append((session_id, request))
        if self.submit_error is not None:
            raise self.submit_error
        return FollowupSnapshot(
            accepted_input_ref="input-ref",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id=f"run-{len(self.submit_requests)}",
            accepted_run_status=RunStatus.RUNNING,
            command_watermark=HostStreamCursor(event_sequence=456),
            queued_run_id=None,
            target_run_id=None,
        )

    async def purge_session(
        self,
        session_id: str,
        request: PurgeSessionRequest,
    ) -> PurgeSessionResult:
        """记录 purge 请求并返回或抛出预设结果。

        :param session_id: 待清理 Session id。
        :param request: Host purge request。
        :returns: 预设 purge result。
        :raises HostApiError: 测试配置要求模拟 Host 失败时抛出。
        """

        self.calls.append(f"purge:{session_id}")
        self.purge_requests.append((session_id, request))
        if self.purge_error is not None:
            raise self.purge_error
        return self.purge_result

    async def close_session(self) -> None:
        """记录禁止路径调用。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_cancel_calls += 1

    async def ensure_session(self) -> None:
        """记录禁止路径调用。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_cancel_calls += 1

    async def create_session(self) -> None:
        """记录禁止路径调用。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_cancel_calls += 1

    async def cancel_session_runs(self) -> None:
        """记录禁止路径调用。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_cancel_calls += 1


def test_cli_label_maps_once_to_shared_host_slot_ref() -> None:
    """CLI label 必须经唯一 owner 映射到共享 Agent slot。

    :returns: ``None``。
    :raises AssertionError: slot ref 映射不符合共享 namespace 时抛出。
    """

    shared_slot = slot_ref_for_cli_label(" 财报.项目一 ")

    assert shared_slot == SessionSlotRef(
        scope="cli.agent",
        slot_key="cli.agent.财报.项目一",
    )
    with pytest.raises(ValueError, match="label must not be empty"):
        slot_ref_for_cli_label(" \t ")


def test_display_identity_from_slot_covers_shared_legacy_and_other_slots() -> None:
    """Session list 必须识别共享 alias，并把旧 namespace 视为 other。

    :returns: ``None``。
    :raises AssertionError: 任一 slot 展示身份反解不符合固定规则时抛出。
    """

    anonymous = display_identity_from_slot(None)
    labeled = display_identity_from_slot(
        SessionSlotRef(scope="cli.agent", slot_key="cli.agent.proj.v1")
    )
    legacy_prompt = display_identity_from_slot(
        SessionSlotRef(scope="cli.prompt", slot_key="cli.prompt.proj.v1")
    )
    legacy_interactive = display_identity_from_slot(
        SessionSlotRef(
            scope="cli.interactive",
            slot_key="cli.interactive.earnings",
        )
    )
    other_scope = display_identity_from_slot(
        SessionSlotRef(scope="service.workflow", slot_key="workflow.alpha")
    )
    labeled_bad_prefix = display_identity_from_slot(
        SessionSlotRef(scope="cli.agent", slot_key="not-cli.agent.alpha")
    )
    labeled_empty_suffix = display_identity_from_slot(
        SessionSlotRef(scope="cli.agent", slot_key="cli.agent.")
    )

    assert anonymous.kind is CliSessionDisplayKind.ANONYMOUS
    assert anonymous.label == "-"
    assert labeled.kind is CliSessionDisplayKind.LABELED
    assert labeled.label == "proj.v1"
    assert legacy_prompt.kind is CliSessionDisplayKind.OTHER
    assert legacy_prompt.label == "cli.prompt.proj.v1"
    assert legacy_interactive.kind is CliSessionDisplayKind.OTHER
    assert legacy_interactive.label == "cli.interactive.earnings"
    assert other_scope.kind is CliSessionDisplayKind.OTHER
    assert other_scope.label == "workflow.alpha"
    assert labeled_bad_prefix.kind is CliSessionDisplayKind.OTHER
    assert labeled_bad_prefix.label == "not-cli.agent.alpha"
    assert labeled_empty_suffix.kind is CliSessionDisplayKind.OTHER
    assert labeled_empty_suffix.label == "cli.agent."


def test_render_session_list_uses_public_summary_without_internal_fields() -> None:
    """Session list 输出只展示 public summary，不泄漏内部治理字段。

    :returns: ``None``。
    :raises AssertionError: 输出格式或内部字段隐藏行为不符合预期时抛出。
    """

    output = StringIO()
    render_session_list(
        ListSessionsResult(
            sessions=(
                _session_list_item(
                    session_id="session-anonymous",
                    slot=None,
                    queued_run_ids=(
                        "attempt-hidden",
                        "execution-hidden",
                        "payload-ref-hidden",
                        "digest-hidden",
                    ),
                ),
                _session_list_item(
                    session_id="session-prompt",
                    slot=SessionSlotRef(
                        scope="cli.agent",
                        slot_key="cli.agent.proj.v1",
                    ),
                ),
                _session_list_item(
                    session_id="session-other",
                    slot=SessionSlotRef(
                        scope="service.workflow",
                        slot_key="workflow.alpha",
                    ),
                ),
            )
        ),
        stdout=output,
    )

    rendered = output.getvalue()

    assert "SESSION_ID\tSTATUS\tKIND\tLABEL\tACTIVE_RUN\tQUEUED\tCREATED_AT\tCLOSED_AT" in rendered
    assert "session-anonymous\topen\tanonymous\t-\t-\t4\t2026-06-16T01:02:03Z\t-" in rendered
    assert "session-prompt\topen\tlabeled\tproj.v1\t-\t0\t2026-06-16T01:02:03Z\t-" in rendered
    assert "session-other\topen\tother\tworkflow.alpha\t-\t0\t2026-06-16T01:02:03Z\t-" in rendered
    assert "attempt-hidden" not in rendered
    assert "execution-hidden" not in rendered
    assert "payload-ref-hidden" not in rendered
    assert "digest-hidden" not in rendered
    assert "HostStreamCursor" not in rendered


def test_render_session_list_empty_result() -> None:
    """空 Session 列表输出稳定可读空状态。

    :returns: ``None``。
    :raises AssertionError: 空列表输出不符合预期时抛出。
    """

    output = StringIO()

    render_session_list(ListSessionsResult(sessions=()), stdout=output)

    assert output.getvalue() == "No sessions.\n"


def test_render_session_purge_result_hides_digest() -> None:
    """purge 输出只展示 tombstone 前缀，不展示删除计数 digest。

    :returns: ``None``。
    :raises AssertionError: purge 输出格式或 digest 隐藏行为不符合预期时抛出。
    """

    output = StringIO()
    render_session_purge_result(
        PurgeSessionResult(
            session_id="session-purged",
            purged=True,
            purge_tombstone_ref="tombstone-ref-abcdef",
            deleted_counts_digest="sha256:digest-hidden",
        ),
        stdout=output,
    )

    rendered = output.getvalue()

    assert rendered == "Purged session session-purged (tombstone: tombstone-re...)\n"
    assert "sha256" not in rendered
    assert "digest-hidden" not in rendered
    assert "payload" not in rendered
    assert "attempt" not in rendered
    assert "execution" not in rendered


def test_session_list_calls_host_public_api_and_renders_sessions(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``session list`` 必须只通过 Host public list 输出 Session 摘要。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: 调用路径或输出不符合 S4 契约时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(
            sessions=(
                _session_list_item(session_id="session-anonymous", slot=None),
                _session_list_item(
                    session_id="session-prompt",
                    slot=SessionSlotRef(
                        scope="cli.agent",
                        slot_key="cli.agent.proj.v1",
                    ),
                    active_run_id="run-active",
                ),
                _session_list_item(
                    session_id="session-closed",
                    slot=SessionSlotRef(
                        scope="cli.agent",
                        slot_key="cli.agent.ops",
                    ),
                    status=SessionStatus.CLOSED,
                    closed_at=datetime(2026, 6, 16, 2, 3, 4, tzinfo=UTC),
                ),
            )
        )
    )
    runtime_capture = _install_fake_session_runtime(monkeypatch, host)

    exit_code = cli_main.main(("session", "list", "--base", str(tmp_path)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    _assert_session_uses_admin_assembly(runtime_capture)
    assert host.calls == ["list_sessions"]
    assert "session-anonymous\topen\tanonymous\t-" in captured.out
    assert "session-prompt\topen\tlabeled\tproj.v1\trun-active\t0" in captured.out
    assert "session-closed\tclosed\tlabeled\tops\t-\t0" in captured.out
    assert captured.err == ""


def test_real_session_list_succeeds_without_model_api_keys(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """真实 CLI list 只走 admin assembly，全部 model secret 缺失仍成功。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: CLI 错误打开 execution runtime 时抛出。
    """

    for env_name in (
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "MIMO_API_KEY",
        "MIMO_PLAN_API_KEY",
        "MIMO_PLAN_SG_API_KEY",
        "OPENAI_API_KEY",
        "QWEN_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)

    exit_code = cli_main.main(("session", "list", "--base", str(tmp_path)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.err == ""


def test_real_session_purge_succeeds_without_model_api_keys(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """真实 CLI purge 只走 admin opener，全部 model secret 缺失仍成功。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: CLI 错误装配 execution capability 时抛出。
    """

    for env_name in (
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "MIMO_API_KEY",
        "MIMO_PLAN_API_KEY",
        "MIMO_PLAN_SG_API_KEY",
        "OPENAI_API_KEY",
        "QWEN_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)
    admin_assembly = prepare_host_admin(
        ServiceHostAdminRequest(
            workspace_root=tmp_path,
            package_config_root=package_config_root(),
            config_overlay_dir=None,
        )
    )
    admin_options = admin_assembly.options
    command_handle = create_host_command_handle(
        HostCommandHandleOptions(
            host_handle_id="cli-real-purge-seed",
            db_path=admin_options.db_path,
            artifact_root=admin_options.artifact_root,
            create_parent_dirs=admin_options.create_parent_dirs,
            sqlite_busy_timeout_seconds=(
                admin_options.sqlite_busy_timeout_seconds
            ),
            sqlite_write_busy_retry_count=(
                admin_options.sqlite_write_busy_retry_count
            ),
            sqlite_write_retry_initial_delay_seconds=(
                admin_options.sqlite_write_retry_initial_delay_seconds
            ),
            sqlite_write_retry_backoff_multiplier=(
                admin_options.sqlite_write_retry_backoff_multiplier
            ),
            sqlite_write_retry_max_delay_seconds=(
                admin_options.sqlite_write_retry_max_delay_seconds
            ),
            payload_inline_threshold_bytes=(
                admin_options.payload_inline_threshold_bytes
            ),
            context_window_size=8192,
            reserved_output_tokens=1024,
        )
    )
    try:
        context = _real_admin_seed_context("create")
        session = command_create_session(
            command_handle,
            CreateSessionRequest(
                context=context,
                client_request_id="cli-real-purge-create",
                bind_slot=False,
                scope=None,
                slot_key=None,
                metadata=(),
            ),
        )
        command_close_session(
            command_handle,
            session.session_id,
            CloseSessionRequest(
                context=_real_admin_seed_context("close"),
                client_request_id="cli-real-purge-close",
                reason="cli_real_purge_seed",
            ),
        )
    finally:
        command_handle.close()

    exit_code = cli_main.main(
        (
            "session",
            "purge",
            "--session-id",
            session.session_id,
            "--yes",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert session.session_id in captured.out
    assert captured.err == ""


def test_session_purge_missing_yes_returns_usage_error() -> None:
    """``session purge`` 缺少 ``--yes`` 时由 parser 返回用法错误。

    :returns: ``None``。
    :raises AssertionError: 缺确认参数未被拒绝时抛出。
    """

    assert cli_main.main(("session", "purge", "--session-id", "session-1")) == (
        EXIT_USAGE_ERROR
    )


def test_session_purge_by_session_id_calls_host_purge(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``session purge --session-id`` 必须直接调用 Host purge_session。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: purge 调用或输出不符合 S4 契约时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(sessions=()),
        purge_result=PurgeSessionResult(
            session_id="session-1",
            purged=True,
            purge_tombstone_ref="tombstone-1234567890",
            deleted_counts_digest="sha256:hidden",
        ),
    )
    runtime_capture = _install_fake_session_runtime(monkeypatch, host)

    exit_code = cli_main.main(
        (
            "session",
            "purge",
            "--session-id",
            "session-1",
            "--yes",
            "--reason",
            "cleanup",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    _assert_session_uses_admin_assembly(runtime_capture)
    assert host.calls == ["purge:session-1"]
    assert len(host.purge_requests) == 1
    session_id, request = host.purge_requests[0]
    assert session_id == "session-1"
    assert request.reason == "cleanup"
    assert request.client_request_id.startswith("dayu-cli:session:")
    assert request.client_request_id.endswith(":session:purge")
    assert captured.out == "Purged session session-1 (tombstone: tombstone-12...)\n"
    assert captured.err == ""


def test_session_purge_by_label_resolves_slot_then_purges(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``session purge --label`` 必须先用 list_sessions 解析 slot 再 purge。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: label selector 解析或 purge 调用不符合契约时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(
            sessions=(
                _session_list_item(
                    session_id="session-A",
                    slot=SessionSlotRef(
                        scope="cli.agent",
                        slot_key="cli.agent.proj.v1",
                    ),
                ),
            )
        ),
        purge_result=PurgeSessionResult(
            session_id="session-A",
            purged=True,
            purge_tombstone_ref="tombstone-ref-abcdef",
            deleted_counts_digest="sha256:hidden",
        ),
    )
    runtime_capture = _install_fake_session_runtime(monkeypatch, host)

    exit_code = cli_main.main(
        (
            "session",
            "purge",
            "--label",
            "proj.v1",
            "--yes",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    _assert_session_uses_admin_assembly(runtime_capture)
    assert host.calls == ["list_sessions", "purge:session-A"]
    assert captured.out == "Purged session session-A (tombstone: tombstone-re...)\n"
    assert captured.err == ""


def test_session_purge_invalid_state_explains_closed_terminal_precondition(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Host INVALID_STATE 必须说明 purge 前置条件且不自动 close/cancel。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: 错误映射或禁止调用路径不符合契约时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(sessions=()),
        purge_error=HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="purge_session requires a closed Session with terminal Runs",
            retryable=False,
        ),
    )
    runtime_capture = _install_fake_session_runtime(monkeypatch, host)

    exit_code = cli_main.main(
        (
            "session",
            "purge",
            "--session-id",
            "session-1",
            "--yes",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    _assert_session_uses_admin_assembly(runtime_capture)
    assert "closed Session" in captured.err
    assert "terminal Runs" in captured.err
    assert "no close/cancel" in captured.err
    assert "invalid_state" in captured.err
    assert host.calls == ["purge:session-1"]
    assert host.close_cancel_calls == 0


def test_session_purge_by_label_toctou_error_includes_selector_and_host_context(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """label purge 的 TOCTOU Host 错误必须包含 selector 与 Host 上下文。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: TOCTOU 错误上下文不完整时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(
            sessions=(
                _session_list_item(
                    session_id="session-A",
                    slot=SessionSlotRef(
                        scope="cli.agent",
                        slot_key="cli.agent.proj.v1",
                    ),
                ),
            )
        ),
        purge_error=HostApiError(
            code=HostApiErrorCode.CONFLICT,
            message="slot changed before purge",
            retryable=False,
        ),
    )
    runtime_capture = _install_fake_session_runtime(monkeypatch, host)

    exit_code = cli_main.main(
        (
            "session",
            "purge",
            "--label",
            "proj.v1",
            "--yes",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    _assert_session_uses_admin_assembly(runtime_capture)
    assert "--label proj.v1" in captured.err
    assert "session-A" in captured.err
    assert "conflict" in captured.err
    assert "slot changed before purge" in captured.err
    assert host.calls == ["list_sessions", "purge:session-A"]


def test_session_resume_prompt_by_session_id_resolves_and_submits_without_create(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """prompt resume by session id 必须 get_session 后在同一 Session submit。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: resume selector 或 submit 路径不符合契约时抛出。
    """

    host = _FakeSessionHost(list_result=ListSessionsResult(sessions=()))
    _install_fake_open_host(monkeypatch, host)
    resume_capture = _install_fake_resume_execution(monkeypatch)

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--session-id",
            "session-1",
            "--mode",
            "prompt",
            "--base",
            str(tmp_path),
            "hello",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.err == ""
    assert host.calls == ["get_session:session-1", "submit:session-1"]
    assert host.close_cancel_calls == 0
    assert host.submit_requests[0][1].user_prompt == "hello"
    assert resume_capture.prompt_prepare_calls == ["hello"]
    assert resume_capture.prompt_execute_sessions == ["session-1"]
    assert resume_capture.prompt_display_flags == [(True, True)]


def test_session_resume_model_maps_to_service_assembly_override(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """session resume 的 ``--model`` 必须进入共享 Service assembly override。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: CLI model 没有精确映射到 ``model_id`` 时抛出。
    """

    host = _FakeSessionHost(list_result=ListSessionsResult(sessions=()))
    _install_fake_open_host(monkeypatch, host)
    captured_requests: list[EntrypointRuntimeRequest] = []

    async def capture_prepare(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """捕获 session resume 传给 Service helper 的 runtime request。

        :param request: CLI 构造的 runtime request。
        :returns: 不启动真实 runtime 的 typed fake。
        :raises Exception: 不主动抛出异常。
        """

        captured_requests.append(request)
        return cast(
            EntrypointRuntimeResult,
            _FakeRuntime(host_assembly=_FakeHostAssembly(options="fake-options")),
        )

    async def execute_prompt(
        *,
        host: Host,
        prepared: session_execution.PreparedPromptSessionExecution,
        session_id: str,
        sigint_monitor: CliSigintMonitor,
        detail: bool = True,
        thinking: bool = True,
    ) -> int:
        """短路 Host submit，只验证 resume runtime conversion。

        :param host: 当前 fake Host。
        :param prepared: 已准备的 prompt execution。
        :param session_id: 已解析的目标 Session id。
        :param sigint_monitor: 本轮 SIGINT monitor。
        :param detail: 是否显示 activity。
        :param thinking: 是否显示 thinking。
        :returns: CLI 成功退出码。
        :raises Exception: monitor 关闭失败时透传。
        """

        del host, prepared, session_id, detail, thinking
        sigint_monitor.close()
        return EXIT_SUCCESS

    monkeypatch.setattr(
        session_execution,
        "prepare_entrypoint_runtime",
        capture_prepare,
    )
    monkeypatch.setattr(
        session_command,
        "execute_prompt_on_session",
        execute_prompt,
    )

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--session-id",
            "session-1",
            "--mode",
            "prompt",
            "--model",
            _MODEL_ID,
            "--base",
            str(tmp_path),
            "hello",
        )
    )

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().err == ""
    assert captured_requests[0].assembly_overrides.model_id == _MODEL_ID


def test_session_resume_interactive_by_label_resolves_and_reuses_session(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """interactive resume by label 必须 list resolve 后多轮复用同一 Session。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: label 解析或 interactive 路由不符合契约时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(
            sessions=(
                _session_list_item(
                    session_id="session-A",
                    slot=SessionSlotRef(
                        scope="cli.agent",
                        slot_key="cli.agent.proj.v1",
                    ),
                ),
            )
        )
    )
    _install_fake_open_host(monkeypatch, host)
    resume_capture = _install_fake_resume_execution(monkeypatch)

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--label",
            "proj.v1",
            "--mode",
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.err == ""
    assert host.calls == [
        "list_sessions",
        "submit:session-A",
        "submit:session-A",
    ]
    assert [session_id for session_id, _request in host.submit_requests] == [
        "session-A",
        "session-A",
    ]
    assert host.close_cancel_calls == 0
    assert resume_capture.interactive_prepare_calls == ["interactive"]
    assert resume_capture.interactive_execute_sessions == ["session-A"]
    assert resume_capture.interactive_display_flags == [(True, True)]


def test_session_resume_prompt_passes_display_flags_to_existing_session_executor(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """prompt resume 必须把 detail/thinking 展示参数传给 existing-session 入口。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: 展示参数未传递时抛出。
    """

    host = _FakeSessionHost(list_result=ListSessionsResult(sessions=()))
    _install_fake_open_host(monkeypatch, host)
    resume_capture = _install_fake_resume_execution(monkeypatch)

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--session-id",
            "session-1",
            "--mode",
            "prompt",
            "--no-detail",
            "--no-thinking",
            "--base",
            str(tmp_path),
            "hello",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.err == ""
    assert resume_capture.prompt_execute_sessions == ["session-1"]
    assert resume_capture.prompt_display_flags == [(False, False)]


def test_session_resume_interactive_passes_display_flags_to_existing_session_executor(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """interactive resume 必须把 detail/thinking 展示参数传给 existing-session 入口。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: 展示参数未传递时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(
            sessions=(
                _session_list_item(
                    session_id="session-A",
                    slot=SessionSlotRef(
                        scope="cli.agent",
                        slot_key="cli.agent.proj.v1",
                    ),
                ),
            )
        )
    )
    _install_fake_open_host(monkeypatch, host)
    resume_capture = _install_fake_resume_execution(monkeypatch)

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--label",
            "proj.v1",
            "--mode",
            "interactive",
            "--no-detail",
            "--no-thinking",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.err == ""
    assert resume_capture.interactive_execute_sessions == ["session-A"]
    assert resume_capture.interactive_display_flags == [(False, False)]


def test_session_resume_interactive_rejects_ticker_before_runtime_prepare(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """interactive resume 必须在 runtime prepare 前拒绝 prompt 专属 ticker。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: ticker 未返回用法错误或泄漏 traceback 时抛出。
    """

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--session-id",
            "session-A",
            "--mode",
            "interactive",
            "--ticker",
            "AAPL",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "does not accept --ticker" in captured.err
    assert "Traceback" not in captured.err


def test_session_resume_closed_session_returns_usage_error_without_submit(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """resume 解析到 CLOSED Session 时必须返回用户错误且不 submit。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: CLOSED Session 没有 fail fast 时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(sessions=()),
        get_session_status=SessionStatus.CLOSED,
    )
    _install_fake_open_host(monkeypatch, host)
    _install_fake_resume_execution(monkeypatch)

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--session-id",
            "session-closed",
            "--mode",
            "prompt",
            "--base",
            str(tmp_path),
            "hello",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "closed" in captured.err
    assert host.calls == ["get_session:session-closed"]
    assert host.submit_requests == []


def test_session_resume_missing_label_returns_usage_error_without_create(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """resume by missing label 必须返回用户错误且不 create / ensure。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: missing label 触发创建或提交时抛出。
    """

    host = _FakeSessionHost(list_result=ListSessionsResult(sessions=()))
    _install_fake_open_host(monkeypatch, host)
    _install_fake_resume_execution(monkeypatch)

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--label",
            "missing",
            "--mode",
            "prompt",
            "--base",
            str(tmp_path),
            "hello",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "no session found" in captured.err
    assert host.calls == ["list_sessions"]
    assert host.submit_requests == []
    assert host.close_cancel_calls == 0


def test_session_resume_by_label_toctou_error_includes_selector_and_host_context(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """resume by label submit TOCTOU 错误必须包含 selector、session id 和 Host 错误。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: TOCTOU 错误上下文不完整时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(
            sessions=(
                _session_list_item(
                    session_id="session-A",
                    slot=SessionSlotRef(
                        scope="cli.agent",
                        slot_key="cli.agent.proj.v1",
                    ),
                ),
            )
        ),
        submit_error=HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="session closed before submit",
            retryable=False,
        ),
    )
    _install_fake_open_host(monkeypatch, host)
    _install_fake_resume_execution(monkeypatch)

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--label",
            "proj.v1",
            "--mode",
            "prompt",
            "--base",
            str(tmp_path),
            "hello",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "--label proj.v1" in captured.err
    assert "session-A" in captured.err
    assert "invalid_state" in captured.err
    assert "session closed before submit" in captured.err
    assert host.calls == ["list_sessions", "submit:session-A"]


def test_session_resume_interactive_startup_error_includes_selector_and_session(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """interactive startup barrier 失败时必须输出 selector 与 Session 上下文。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param tmp_path: 测试 workspace 根目录。
    :returns: ``None``。
    :raises AssertionError: 错误没有结构化展示时抛出。
    """

    host = _FakeSessionHost(
        list_result=ListSessionsResult(
            sessions=(
                _session_list_item(
                    session_id="session-A",
                    slot=SessionSlotRef(
                        scope="cli.agent",
                        slot_key="cli.agent.proj.v1",
                    ),
                ),
            )
        )
    )
    _install_fake_open_host(monkeypatch, host)
    _install_fake_resume_execution(monkeypatch)

    async def fake_execute_interactive_on_session(
        *,
        host: Host,
        prepared: session_execution.PreparedInteractiveSessionExecution,
        session_id: str,
        detail: bool = True,
        thinking: bool = True,
    ) -> int:
        """模拟 interactive startup barrier 失败。

        :param host: fake Host。
        :param prepared: fake interactive prepared execution。
        :param session_id: 目标 Session id。
        :param detail: 是否显示运行态 activity stream。
        :param thinking: 是否显示运行态 thinking 增量。
        :returns: 不返回；始终抛出。
        :raises EntrypointRuntimeError: 始终抛出 startup 失败。
        """

        raise EntrypointRuntimeError("queued run did not become active")

    monkeypatch.setattr(
        session_command,
        "execute_interactive_on_session",
        fake_execute_interactive_on_session,
    )

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--label",
            "proj.v1",
            "--mode",
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "interactive startup failed" in captured.err
    assert "--label proj.v1" in captured.err
    assert "session-A" in captured.err
    assert "queued run did not become active" in captured.err
    assert host.calls == ["list_sessions"]
    assert host.submit_requests == []


def _session_list_item(
    *,
    session_id: str,
    slot: SessionSlotRef | None,
    queued_run_ids: tuple[str, ...] = (),
    active_run_id: str | None = None,
    status: SessionStatus = SessionStatus.OPEN,
    closed_at: datetime | None = None,
) -> SessionListItem:
    """构造测试用 Session list item。

    :param session_id: Session id。
    :param slot: Host public slot ref。
    :param queued_run_ids: queued Run id 元组。
    :param active_run_id: active Run id。
    :param status: Session status。
    :param closed_at: Session closed_at。
    :returns: Session list item。
    :raises ValueError: 构造出的 public DTO 字段非法时抛出。
    :raises TypeError: 构造出的 public DTO 类型非法时抛出。
    """

    return SessionListItem(
        session_id=session_id,
        status=status,
        slot=slot,
        active_run_id=active_run_id,
        queued_run_ids=queued_run_ids,
        timeline_cursor=HostStreamCursor(event_sequence=123),
        created_at=datetime(2026, 6, 16, 1, 2, 3, tzinfo=UTC),
        closed_at=closed_at,
    )


def _real_admin_seed_context(operation: str) -> HostCallContext:
    """构造真实 CLI admin seed 使用的 Host context。

    :param operation: seed operation 名称。
    :returns: Host call context。
    :raises Exception: typed contract 校验失败时透传。
    """

    return HostCallContext(
        actor="test",
        source="test_session_command",
        request_id=f"cli-real-purge-{operation}",
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name=f"cli_real_purge_{operation}",
            operation_kind="test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="cli_session_admin",
            correlation_id=f"cli-real-purge-{operation}",
        ),
    )


def _session_snapshot(
    *,
    session_id: str,
    status: SessionStatus,
) -> SessionSnapshot:
    """构造测试用 Session snapshot。

    :param session_id: Session id。
    :param status: Session status。
    :returns: Session snapshot。
    :raises ValueError: 构造出的 public DTO 字段非法时抛出。
    """

    return SessionSnapshot(
        session_id=session_id,
        status=status,
        slot=None,
        active_run_id=None,
        queued_run_ids=(),
        timeline_cursor=HostStreamCursor(event_sequence=321),
    )


def _submit_request(
    *,
    context: HostCallContext,
    session_id: str,
    user_prompt: str,
) -> SubmitFollowupRequest:
    """构造 fake resume execution 使用的 submit request。

    :param context: Host call context。
    :param session_id: 目标 Session id。
    :param user_prompt: 本轮用户 prompt。
    :returns: SubmitFollowupRequest。
    :raises ValueError: request 字段非法时抛出。
    """

    return SubmitFollowupRequest(
        context=context,
        session_id=session_id,
        client_request_id=f"test-submit-{len(user_prompt)}",
        system_prompt=None,
        user_prompt=user_prompt,
        tool_names=frozenset(),
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _install_fake_open_host(
    monkeypatch: pytest.MonkeyPatch,
    host: _FakeSessionHost,
) -> None:
    """安装 session command 测试用 Host opener fake。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param host: fake Host。
    :returns: ``None``。
    :raises Exception: monkeypatch 设置失败时透传。
    """

    def fake_open_host(_options: str) -> _FakeHostContext:
        """返回 fake Host context manager。

        :param _options: fake runtime options。
        :returns: fake Host async context manager。
        :raises Exception: 不主动抛出异常。
        """

        return _FakeHostContext(host)

    def fake_prepare_session_admin(_args: ParsedCliArgs) -> _FakeAdminAssembly:
        """返回不读取真实配置的 fake admin assembly。

        :param _args: argparse 已解析参数。
        :returns: fake admin assembly。
        :raises Exception: 不主动抛出异常。
        """

        return _FakeAdminAssembly(options="fake-admin-options")

    monkeypatch.setattr(session_command, "open_host", fake_open_host)
    monkeypatch.setattr(session_command, "open_host_admin", fake_open_host)
    monkeypatch.setattr(
        session_command,
        "_prepare_session_admin",
        fake_prepare_session_admin,
    )


def _install_fake_resume_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> _FakeResumeCapture:
    """安装 session resume 测试用 prompt / interactive existing-session fake。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: resume helper 调用记录。
    :raises Exception: monkeypatch 设置失败时透传。
    """

    capture = _FakeResumeCapture(
        prompt_prepare_calls=[],
        interactive_prepare_calls=[],
        prompt_execute_sessions=[],
        interactive_execute_sessions=[],
        prompt_display_flags=[],
        interactive_display_flags=[],
    )

    async def fake_prepare_prompt_session_execution(
        args: ParsedCliArgs,
        *,
        command_name: str,
        scenario: str,
        user_prompt: str,
        ticker: str | None,
        context_slot_values: dict[str, JsonValue],
        usage_error_factory: Callable[[str], ValueError],
    ) -> session_execution.PreparedPromptSessionExecution:
        """返回 fake prompt existing-session 准备结果。

        :param args: session resume 参数。
        :param command_name: 当前 CLI command 名称。
        :param scenario: prompt scene id。
        :param user_prompt: 本轮用户 prompt。
        :returns: fake prompt prepared execution。
        :raises Exception: 不主动抛出异常。
        """

        del context_slot_values, usage_error_factory
        capture.prompt_prepare_calls.append(user_prompt)
        return session_execution.PreparedPromptSessionExecution(
            runtime=cast(
                EntrypointRuntimeResult,
                _FakeRuntime(host_assembly=_FakeHostAssembly(options="fake-options")),
            ),
            workspace_root=Path(args.workspace_root or "."),
            invocation=session_command.new_cli_invocation(
                command_name=command_name,
                scenario=scenario,
                display_user="本地 CLI 用户",
                ticker=ticker,
            ),
            user_prompt=user_prompt,
            run_overrides=ServiceRunOverrides(),
        )

    async def fake_execute_prompt_on_session(
        *,
        host: Host,
        prepared: session_execution.PreparedPromptSessionExecution,
        session_id: str,
        sigint_monitor: CliSigintMonitor,
        detail: bool = True,
        thinking: bool = True,
    ) -> int:
        """在 fake Host 上提交一轮 prompt。

        :param host: fake Host。
        :param prepared: fake prompt prepared execution。
        :param session_id: 目标 Session id。
        :param sigint_monitor: prompt SIGINT monitor。
        :param detail: 是否显示运行态 activity stream。
        :param thinking: 是否显示运行态 thinking 增量。
        :returns: CLI 成功退出码。
        :raises HostApiError: fake Host 配置 submit 失败时抛出。
        """

        sigint_monitor.close()
        capture.prompt_execute_sessions.append(session_id)
        capture.prompt_display_flags.append((detail, thinking))
        await host.submit_followup(
            session_id,
            _submit_request(
                context=prompt_command.build_prompt_host_context(
                    prepared.invocation,
                    operation="submit_followup",
                ),
                session_id=session_id,
                user_prompt=prepared.user_prompt,
            ),
        )
        return EXIT_SUCCESS

    async def fake_prepare_interactive_session_execution(
        args: ParsedCliArgs,
        *,
        command_name: str,
        scenario: str,
        context_slot_values: dict[str, JsonValue],
        usage_error_factory: Callable[[str], ValueError],
    ) -> session_execution.PreparedInteractiveSessionExecution:
        """返回 fake interactive existing-session 准备结果。

        :param args: session resume 参数。
        :param command_name: 当前 CLI command 名称。
        :param scenario: interactive scene id。
        :param context_slot_values: interactive scene context slots。
        :param usage_error_factory: 当前命令用法错误构造器。
        :returns: fake interactive prepared execution。
        :raises Exception: 不主动抛出异常。
        """

        del context_slot_values, usage_error_factory
        capture.interactive_prepare_calls.append(args.mode or "")
        return session_execution.PreparedInteractiveSessionExecution(
            runtime=cast(
                EntrypointRuntimeResult,
                _FakeRuntime(host_assembly=_FakeHostAssembly(options="fake-options")),
            ),
            workspace_root=Path(args.workspace_root or "."),
            invocation=session_command.new_cli_invocation(
                command_name=command_name,
                scenario=scenario,
                display_user="本地 CLI 用户",
                ticker=None,
            ),
            run_overrides=ServiceRunOverrides(),
        )

    async def fake_execute_interactive_on_session(
        *,
        host: Host,
        prepared: session_execution.PreparedInteractiveSessionExecution,
        session_id: str,
        input_reader: Callable[[str], str] | None = None,
        sigint_monitor_factory: Callable[[], CliSigintMonitor] | None = None,
        detail: bool = True,
        thinking: bool = True,
    ) -> int:
        """在 fake Host 上提交两轮 interactive 输入。

        :param host: fake Host。
        :param prepared: fake interactive prepared execution。
        :param session_id: 目标 Session id。
        :param input_reader: 未使用的输入读取器。
        :param sigint_monitor_factory: 未使用的 SIGINT monitor 工厂。
        :param detail: 是否显示运行态 activity stream。
        :param thinking: 是否显示运行态 thinking 增量。
        :returns: CLI 成功退出码。
        :raises HostApiError: fake Host 配置 submit 失败时抛出。
        """

        capture.interactive_execute_sessions.append(session_id)
        capture.interactive_display_flags.append((detail, thinking))
        for user_prompt in ("first interactive turn", "second interactive turn"):
            await host.submit_followup(
                session_id,
                _submit_request(
                    context=interactive_command.build_interactive_host_context(
                        prepared.invocation,
                        operation="submit_followup",
                    ),
                    session_id=session_id,
                    user_prompt=user_prompt,
                ),
            )
        return EXIT_SUCCESS

    monkeypatch.setattr(
        session_command,
        "prepare_prompt_session_execution",
        fake_prepare_prompt_session_execution,
    )
    monkeypatch.setattr(
        session_command,
        "execute_prompt_on_session",
        fake_execute_prompt_on_session,
    )
    monkeypatch.setattr(
        session_command,
        "prepare_interactive_session_execution",
        fake_prepare_interactive_session_execution,
    )
    monkeypatch.setattr(
        session_command,
        "execute_interactive_on_session",
        fake_execute_interactive_on_session,
    )
    return capture


def _install_fake_session_runtime(
    monkeypatch: pytest.MonkeyPatch,
    host: _FakeSessionHost,
) -> _FakeRuntimeCapture:
    """安装 session command 测试用 runtime 与 Host opener fake。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param host: fake Host。
    :returns: runtime request capture。
    :raises Exception: monkeypatch 设置失败时透传。
    """

    capture = _FakeRuntimeCapture(requests=[])

    def fake_prepare_session_admin(
        args: ParsedCliArgs,
    ) -> _FakeAdminAssembly:
        """返回最小 fake admin assembly。

        :param args: argparse 已解析参数。
        :returns: fake admin assembly。
        :raises Exception: 不主动抛出异常。
        """

        capture.requests.append(args)
        return _FakeAdminAssembly(options="fake-admin-options")

    _install_fake_open_host(monkeypatch, host)
    monkeypatch.setattr(
        session_command,
        "_prepare_session_admin",
        fake_prepare_session_admin,
    )
    return capture


def _assert_session_uses_admin_assembly(
    capture: _FakeRuntimeCapture,
) -> None:
    """断言 list/purge 只准备一次 admin assembly，不准备 execution scene。

    :param capture: fake runtime 捕获到的请求。
    :returns: ``None``。
    :raises AssertionError: admin routing 次数或 action 不符合预期时抛出。
    """

    assert len(capture.requests) == 1
    request = capture.requests[0]
    assert request.session_action in {"list", "purge"}
    assert not hasattr(session_command, "prepare_entrypoint_runtime")
