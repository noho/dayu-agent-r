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
from dayu.cli.agent_entrypoint import CliSigintMonitor
from dayu.cli.arg_parsing import ParsedCliArgs
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.cli.output import render_session_list, render_session_purge_result
from dayu.cli.session_identity import (
    CliSessionDisplayKind,
    CliSessionLabelKind,
    display_identity_from_slot,
    slot_ref_for_cli_label,
)
from dayu.host.api import (
    FollowupBehavior,
    FollowupSnapshot,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostStreamCursor,
    ListSessionsResult,
    PurgeSessionRequest,
    PurgeSessionResult,
    SessionSnapshot,
    SessionListItem,
    SessionSlotRef,
    SessionStatus,
    SubmitFollowupRequest,
    RunStatus,
)
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeError,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
)
from dayu.service.host_assembly import ServiceRunOverrides


@dataclass(frozen=True, slots=True)
class _FakeHostAssembly:
    """测试用 Host assembly。"""

    options: str


@dataclass(frozen=True, slots=True)
class _FakeRuntime:
    """测试用 entrypoint runtime result。"""

    host_assembly: _FakeHostAssembly


@dataclass(slots=True)
class _FakeRuntimeCapture:
    """测试用 runtime request capture。"""

    requests: list[EntrypointRuntimeRequest]


@dataclass(slots=True)
class _FakeResumeCapture:
    """测试用 resume helper 调用记录。"""

    prompt_prepare_calls: list[str]
    interactive_prepare_calls: list[str]
    prompt_execute_sessions: list[str]
    interactive_execute_sessions: list[str]


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


def test_cli_label_kind_maps_to_host_slot_ref() -> None:
    """CLI label kind 必须映射到对应 Host slot namespace。

    :returns: ``None``。
    :raises AssertionError: slot ref 映射不符合 CLI label namespace 时抛出。
    """

    prompt_slot = slot_ref_for_cli_label(CliSessionLabelKind.PROMPT, " proj.v1 ")
    interactive_slot = slot_ref_for_cli_label(
        CliSessionLabelKind.INTERACTIVE,
        "earnings",
    )

    assert prompt_slot == SessionSlotRef(
        scope="cli.prompt",
        slot_key="cli.prompt.proj.v1",
    )
    assert interactive_slot == SessionSlotRef(
        scope="cli.interactive",
        slot_key="cli.interactive.earnings",
    )


def test_display_identity_from_slot_covers_cli_and_other_slots() -> None:
    """Session list slot 反解必须覆盖 anonymous、prompt、interactive、other。

    :returns: ``None``。
    :raises AssertionError: 任一 slot 展示身份反解不符合固定规则时抛出。
    """

    anonymous = display_identity_from_slot(None)
    prompt = display_identity_from_slot(
        SessionSlotRef(scope="cli.prompt", slot_key="cli.prompt.proj.v1")
    )
    interactive = display_identity_from_slot(
        SessionSlotRef(
            scope="cli.interactive",
            slot_key="cli.interactive.earnings",
        )
    )
    other_scope = display_identity_from_slot(
        SessionSlotRef(scope="service.workflow", slot_key="workflow.alpha")
    )
    prompt_bad_prefix = display_identity_from_slot(
        SessionSlotRef(scope="cli.prompt", slot_key="not-cli.prompt.alpha")
    )
    prompt_empty_suffix = display_identity_from_slot(
        SessionSlotRef(scope="cli.prompt", slot_key="cli.prompt.")
    )

    assert anonymous.kind is CliSessionDisplayKind.ANONYMOUS
    assert anonymous.label == "-"
    assert prompt.kind is CliSessionDisplayKind.PROMPT
    assert prompt.label == "proj.v1"
    assert interactive.kind is CliSessionDisplayKind.INTERACTIVE
    assert interactive.label == "earnings"
    assert other_scope.kind is CliSessionDisplayKind.OTHER
    assert other_scope.label == "workflow.alpha"
    assert prompt_bad_prefix.kind is CliSessionDisplayKind.OTHER
    assert prompt_bad_prefix.label == "not-cli.prompt.alpha"
    assert prompt_empty_suffix.kind is CliSessionDisplayKind.OTHER
    assert prompt_empty_suffix.label == "cli.prompt."


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
                        scope="cli.prompt",
                        slot_key="cli.prompt.proj.v1",
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
    assert "session-prompt\topen\tprompt\tproj.v1\t-\t0\t2026-06-16T01:02:03Z\t-" in rendered
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
                        scope="cli.prompt",
                        slot_key="cli.prompt.proj.v1",
                    ),
                    active_run_id="run-active",
                ),
                _session_list_item(
                    session_id="session-closed",
                    slot=SessionSlotRef(
                        scope="cli.interactive",
                        slot_key="cli.interactive.ops",
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
    _assert_session_runtime_uses_prompt_carrier(runtime_capture)
    assert host.calls == ["list_sessions"]
    assert "session-anonymous\topen\tanonymous\t-" in captured.out
    assert "session-prompt\topen\tprompt\tproj.v1\trun-active\t0" in captured.out
    assert "session-closed\tclosed\tinteractive\tops\t-\t0" in captured.out
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
    _assert_session_runtime_uses_prompt_carrier(runtime_capture)
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
                        scope="cli.prompt",
                        slot_key="cli.prompt.proj.v1",
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
            "--kind",
            "prompt",
            "--yes",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    _assert_session_runtime_uses_prompt_carrier(runtime_capture)
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
    _assert_session_runtime_uses_prompt_carrier(runtime_capture)
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
                        scope="cli.prompt",
                        slot_key="cli.prompt.proj.v1",
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
            "--kind",
            "prompt",
            "--yes",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    _assert_session_runtime_uses_prompt_carrier(runtime_capture)
    assert "--label proj.v1 --kind prompt" in captured.err
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
                        scope="cli.interactive",
                        slot_key="cli.interactive.proj.v1",
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
            "--kind",
            "interactive",
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
            "--kind",
            "prompt",
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
                        scope="cli.prompt",
                        slot_key="cli.prompt.proj.v1",
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
            "--kind",
            "prompt",
            "--mode",
            "prompt",
            "--base",
            str(tmp_path),
            "hello",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "--label proj.v1 --kind prompt" in captured.err
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
                        scope="cli.interactive",
                        slot_key="cli.interactive.proj.v1",
                    ),
                ),
            )
        )
    )
    _install_fake_open_host(monkeypatch, host)
    _install_fake_resume_execution(monkeypatch)

    async def fake_execute_interactive_on_existing_session(
        *,
        host: Host,
        prepared: interactive_command._PreparedInteractiveExistingSessionExecution,
        session_id: str,
    ) -> int:
        """模拟 interactive startup barrier 失败。

        :param host: fake Host。
        :param prepared: fake interactive prepared execution。
        :param session_id: 目标 Session id。
        :returns: 不返回；始终抛出。
        :raises EntrypointRuntimeError: 始终抛出 startup 失败。
        """

        raise EntrypointRuntimeError("queued run did not become active")

    monkeypatch.setattr(
        session_command,
        "_execute_interactive_on_existing_session",
        fake_execute_interactive_on_existing_session,
    )

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--label",
            "proj.v1",
            "--kind",
            "interactive",
            "--mode",
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "interactive startup failed" in captured.err
    assert "--label proj.v1 --kind interactive" in captured.err
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

    monkeypatch.setattr(session_command, "open_host", fake_open_host)


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
    )

    async def fake_prepare_prompt_existing_session_execution(
        args: ParsedCliArgs,
        *,
        command_name: str,
        scenario: str,
        user_prompt: str,
    ) -> prompt_command._PreparedPromptExistingSessionExecution:
        """返回 fake prompt existing-session 准备结果。

        :param args: session resume 参数。
        :param command_name: 当前 CLI command 名称。
        :param scenario: prompt scene id。
        :param user_prompt: 本轮用户 prompt。
        :returns: fake prompt prepared execution。
        :raises Exception: 不主动抛出异常。
        """

        capture.prompt_prepare_calls.append(user_prompt)
        return prompt_command._PreparedPromptExistingSessionExecution(
            runtime=cast(
                EntrypointRuntimeResult,
                _FakeRuntime(host_assembly=_FakeHostAssembly(options="fake-options")),
            ),
            workspace_root=Path(args.workspace_root or "."),
            invocation=session_command.new_cli_invocation(
                command_name=command_name,
                scenario=scenario,
                display_user="本地 CLI 用户",
                ticker=args.ticker,
            ),
            user_prompt=user_prompt,
            run_overrides=ServiceRunOverrides(),
        )

    async def fake_execute_prompt_on_existing_session(
        *,
        host: Host,
        prepared: prompt_command._PreparedPromptExistingSessionExecution,
        session_id: str,
        sigint_monitor: CliSigintMonitor,
    ) -> int:
        """在 fake Host 上提交一轮 prompt。

        :param host: fake Host。
        :param prepared: fake prompt prepared execution。
        :param session_id: 目标 Session id。
        :param sigint_monitor: prompt SIGINT monitor。
        :returns: CLI 成功退出码。
        :raises HostApiError: fake Host 配置 submit 失败时抛出。
        """

        sigint_monitor.close()
        capture.prompt_execute_sessions.append(session_id)
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

    async def fake_prepare_interactive_existing_session_execution(
        args: ParsedCliArgs,
        *,
        command_name: str,
        scenario: str,
    ) -> interactive_command._PreparedInteractiveExistingSessionExecution:
        """返回 fake interactive existing-session 准备结果。

        :param args: session resume 参数。
        :param command_name: 当前 CLI command 名称。
        :param scenario: interactive scene id。
        :returns: fake interactive prepared execution。
        :raises Exception: 不主动抛出异常。
        """

        capture.interactive_prepare_calls.append(args.mode or "")
        return interactive_command._PreparedInteractiveExistingSessionExecution(
            runtime=cast(
                EntrypointRuntimeResult,
                _FakeRuntime(host_assembly=_FakeHostAssembly(options="fake-options")),
            ),
            workspace_root=Path(args.workspace_root or "."),
            invocation=session_command.new_cli_invocation(
                command_name=command_name,
                scenario=scenario,
                display_user="本地 CLI 用户",
                ticker=args.ticker,
            ),
            run_overrides=ServiceRunOverrides(),
        )

    async def fake_execute_interactive_on_existing_session(
        *,
        host: Host,
        prepared: interactive_command._PreparedInteractiveExistingSessionExecution,
        session_id: str,
        input_reader: Callable[[str], str] | None = None,
        sigint_monitor_factory: Callable[[], CliSigintMonitor] | None = None,
    ) -> int:
        """在 fake Host 上提交两轮 interactive 输入。

        :param host: fake Host。
        :param prepared: fake interactive prepared execution。
        :param session_id: 目标 Session id。
        :param input_reader: 未使用的输入读取器。
        :param sigint_monitor_factory: 未使用的 SIGINT monitor 工厂。
        :returns: CLI 成功退出码。
        :raises HostApiError: fake Host 配置 submit 失败时抛出。
        """

        capture.interactive_execute_sessions.append(session_id)
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
        "_prepare_prompt_existing_session_execution",
        fake_prepare_prompt_existing_session_execution,
    )
    monkeypatch.setattr(
        session_command,
        "_execute_prompt_on_existing_session",
        fake_execute_prompt_on_existing_session,
    )
    monkeypatch.setattr(
        session_command,
        "_prepare_interactive_existing_session_execution",
        fake_prepare_interactive_existing_session_execution,
    )
    monkeypatch.setattr(
        session_command,
        "_execute_interactive_on_existing_session",
        fake_execute_interactive_on_existing_session,
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

    async def fake_prepare_entrypoint_runtime(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """返回最小 fake runtime。

        :param request: runtime 准备请求。
        :returns: 经测试边界 cast 的 fake runtime result。
        :raises Exception: 不主动抛出异常。
        """

        capture.requests.append(request)
        return cast(
            EntrypointRuntimeResult,
            _FakeRuntime(host_assembly=_FakeHostAssembly(options="fake-options")),
        )

    monkeypatch.setattr(
        session_command,
        "prepare_entrypoint_runtime",
        fake_prepare_entrypoint_runtime,
    )
    _install_fake_open_host(monkeypatch, host)
    return capture


def _assert_session_runtime_uses_prompt_carrier(
    capture: _FakeRuntimeCapture,
) -> None:
    """断言 session 命令 runtime assembly 使用已存在 prompt scene carrier。

    :param capture: fake runtime 捕获到的请求。
    :returns: ``None``。
    :raises AssertionError: runtime scene 或 required slots 不符合真实 manifest 时抛出。
    """

    assert len(capture.requests) == 1
    request = capture.requests[0]
    assert request.scene_id == "prompt"
    assert request.context_slot_values["fins_default_subject"] == ""
    assert "Asia/Shanghai" in str(request.context_slot_values["current_time"])
