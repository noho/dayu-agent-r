"""``dayu-cli session`` helper 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import TracebackType
from typing import cast

import pytest

import dayu.cli.commands.session as session_command
import dayu.cli.main as cli_main
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_NOT_IMPLEMENTED,
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
    Host,
    HostApiError,
    HostApiErrorCode,
    HostStreamCursor,
    ListSessionsResult,
    PurgeSessionRequest,
    PurgeSessionResult,
    SessionListItem,
    SessionSlotRef,
    SessionStatus,
)
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
)


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
    calls: list[str]
    purge_requests: list[tuple[str, PurgeSessionRequest]]
    close_cancel_calls: int

    def __init__(
        self,
        *,
        list_result: ListSessionsResult,
        purge_result: PurgeSessionResult | None = None,
        purge_error: HostApiError | None = None,
    ) -> None:
        """初始化 fake Host。

        :param list_result: ``list_sessions`` 返回值。
        :param purge_result: ``purge_session`` 成功返回值。
        :param purge_error: ``purge_session`` 需要抛出的 Host 错误。
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
        self.calls = []
        self.purge_requests = []
        self.close_cancel_calls = 0

    async def list_sessions(self) -> ListSessionsResult:
        """返回预设 Session 列表并记录调用。

        :returns: 预设 list result。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append("list_sessions")
        return self.list_result

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


def test_session_resume_execution_is_left_not_implemented(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """S4 只冻结 ``session resume`` parser shape，不实现执行。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: resume 执行没有停留在 not implemented 时抛出。
    """

    exit_code = cli_main.main(
        (
            "session",
            "resume",
            "--session-id",
            "session-1",
            "--mode",
            "prompt",
            "hello",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_NOT_IMPLEMENTED
    assert "not implemented" in captured.err


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

    def fake_open_host(_options: str) -> _FakeHostContext:
        """返回 fake Host context manager。

        :param _options: fake runtime options。
        :returns: fake Host async context manager。
        :raises Exception: 不主动抛出异常。
        """

        return _FakeHostContext(host)

    monkeypatch.setattr(
        session_command,
        "prepare_entrypoint_runtime",
        fake_prepare_entrypoint_runtime,
    )
    monkeypatch.setattr(session_command, "open_host", fake_open_host)
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
    assert request.context_slot_values["fins_default_subject"] == "未指定具体公司"
    assert request.context_slot_values["base_user"] == "本地 CLI 用户"
