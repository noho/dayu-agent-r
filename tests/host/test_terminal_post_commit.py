"""S3 exact terminal post-commit contract、静态闭集与 coordinator 测试。"""

from __future__ import annotations

import ast
import asyncio
from collections import Counter
from pathlib import Path

import pytest

import dayu.host as host_package
from dayu.host.admission import AdmissionWakeupPort, PendingDispatchRecord
from dayu.host.api import HostSessionEventDeliveryPolicy
from dayu.host.open_host import _TerminalPostCommitCoordinator
from dayu.host.terminal_post_commit import TerminalPostCommitNotice
from dayu.host.transient_delta import HostTransientDeltaHub

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

_EXPECTED_TERMINAL_PRODUCERS: dict[str, frozenset[tuple[str, str]]] = {
    "dayu/host/admission.py": frozenset(
        {
            ("_CancelRunOperation._cancel_queued", "cancel_queued_in_transaction"),
            (
                "_CancelRunOperation._cancel_predispatch_starting_or_none",
                "cancel_predispatch_starting_in_transaction",
            ),
            (
                "_CancelRunOperation._cancel_recovering",
                "cancel_recovering_run_in_transaction",
            ),
            (
                "_CancelRunOperation._cancel_waiting",
                "cancel_waiting_run_in_transaction",
            ),
            (
                "_CancelSessionRunsOperation._cancel_queued_target",
                "cancel_queued_in_transaction",
            ),
            (
                "_CancelSessionRunsOperation._cancel_predispatch_target",
                "cancel_predispatch_starting_in_transaction",
            ),
            (
                "_CancelSessionRunsOperation._cancel_waiting_target",
                "cancel_waiting_run_in_transaction",
            ),
            (
                "_CancelSessionRunsOperation._cancel_recovering_target",
                "cancel_recovering_run_in_transaction",
            ),
            (
                "_CloseoutAttemptTerminalOperation.__call__",
                "terminal_closeout_in_transaction",
            ),
        }
    ),
    "dayu/host/waiting.py": frozenset(
        {
            (
                "DefaultHostResolveWaitService._resolve_failed",
                "fail_run_from_waiting_in_transaction",
            ),
            (
                "DefaultHostResolveWaitService._resolve_lost",
                "mark_run_lost_from_waiting_in_transaction",
            ),
            ("_expire_wait_in_transaction", "fail_run_from_waiting_in_transaction"),
        }
    ),
    "dayu/host/engine_ingest.py": frozenset(
        {
            ("EngineEventIngestor._close_terminal", "terminal_closeout_in_transaction"),
            (
                "EngineEventIngestor._close_host_lifecycle_terminal",
                "terminal_closeout_in_transaction",
            ),
            (
                "EngineEventIngestor._close_active_cancel",
                "active_cancel_closeout_in_transaction",
            ),
            (
                "EngineEventIngestor._fail_recovering_run",
                "fail_recovering_run_in_transaction",
            ),
            (
                "_close_reactive_fallback_hard_in_transaction",
                "fail_recovering_run_in_transaction",
            ),
        }
    ),
    "dayu/host/recovery.py": frozenset(
        {
            (
                "SessionAttachmentRecoveryScanner._classify_recovering",
                "lose_recovering_run_in_transaction",
            ),
            (
                "SessionAttachmentRecoveryScanner._close_positive_orphan",
                "close_startup_orphan_attempt_in_transaction",
            ),
            (
                "SessionAttachmentRecoveryScanner._lose_unrecoverable_source",
                "lose_recovering_run_in_transaction",
            ),
        }
    ),
    "dayu/host/dispatch.py": frozenset(
        {
            (
                "HostDispatchScheduler._tick_active_cancel_watchdog._operation",
                "active_cancel_watchdog_closeout_in_transaction",
            ),
            (
                "HostDispatchScheduler._fail_unstarted_in_transaction",
                "fail_unstarted_run_in_transaction",
            ),
            (
                "HostDispatchScheduler._closeout_worker_startup_timeout._operation",
                "terminal_closeout_in_transaction",
            ),
        }
    ),
}

_TERMINAL_TRANSITION_NAMES = frozenset(
    transition
    for producers in _EXPECTED_TERMINAL_PRODUCERS.values()
    for _qualified_name, transition in producers
)

_EXPECTED_QUEUE_PROMOTION_WAKE_CALLS = Counter(
    {
        ("dayu/host/admission.py", "_wake_start_governance_if_needed"): 1,
        (
            "dayu/host/recovery.py",
            "SessionAttachmentRecoveryScanner._wake_after_committed_batch",
        ): 1,
        (
            "dayu/host/open_host.py",
            "_TerminalPostCommitCoordinator._notify_on_owner_loop",
        ): 1,
        (
            "dayu/host/open_host.py",
            "_ThreadsafeSchedulerWakeupPort.wake_queue_promotion",
        ): 2,
    }
)

_TERMINAL_NOTICE_PROJECTION_CONSUMERS = (
    "dayu/host/admission.py",
    "dayu/host/engine_ingest.py",
    "dayu/host/recovery.py",
    "dayu/host/dispatch.py",
    "dayu/host/waiting.py",
)


class _QualifiedCallVisitor(ast.NodeVisitor):
    """收集 call 所属 class/function qualified name。"""

    def __init__(self) -> None:
        """初始化空 scope 与 call 记录。

        :returns: ``None``。
        """

        self._scope: list[str] = []
        self.calls: list[tuple[str, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """进入 class scope。

        :param node: class AST node。
        :returns: ``None``。
        """

        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """进入同步 function scope。

        :param node: function AST node。
        :returns: ``None``。
        """

        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """进入异步 function scope。

        :param node: async function AST node。
        :returns: ``None``。
        """

        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """记录 call 的末级 symbol 与当前 qualified scope。

        :param node: call AST node。
        :returns: ``None``。
        """

        call_name = _call_name(node.func)
        if call_name is not None:
            self.calls.append((".".join(self._scope), call_name))
        self.generic_visit(node)


class _RecordingPromotionPort(AdmissionWakeupPort):
    """记录 coordinator ordinary promotion，并观察调用时 delivery watermark。"""

    def __init__(self, hub: HostTransientDeltaHub) -> None:
        """初始化记录端口。

        :param hub: coordinator 使用的 delivery owner。
        :returns: ``None``。
        """

        self._hub = hub
        self.promotions: list[tuple[str, int]] = []

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """拒绝本测试不应发生的 dispatch wake。

        :param record: pending dispatch record。
        :returns: 不会返回。
        :raises AssertionError: 始终抛出。
        """

        raise AssertionError(f"unexpected dispatch wake: {record.run_id}")

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 promotion 调用时已可见的 delivery watermark。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        """

        self.promotions.append(
            (
                session_id,
                self._hub.committed_terminal_event_sequence_high_watermark(
                    session_id
                ),
            )
        )


def test_notice_strict_validation_and_private_package_boundary() -> None:
    """Notice 严格拒绝 bool/非正数/空 identity，且不进入 public package。"""

    notice = TerminalPostCommitNotice(
        session_id="session-a",
        terminal_event_sequence=1,
        wake_queue_promotion=False,
    )
    assert notice.terminal_event_sequence == 1
    with pytest.raises(TypeError):
        TerminalPostCommitNotice(
            session_id="session-a",
            terminal_event_sequence=True,
            wake_queue_promotion=False,
        )
    with pytest.raises(ValueError):
        TerminalPostCommitNotice(
            session_id="session-a",
            terminal_event_sequence=0,
            wake_queue_promotion=False,
        )
    with pytest.raises(ValueError):
        TerminalPostCommitNotice(
            session_id=" ",
            terminal_event_sequence=1,
            wake_queue_promotion=False,
        )
    with pytest.raises(TypeError):
        TerminalPostCommitNotice(
            session_id="session-a",
            terminal_event_sequence=1,
            wake_queue_promotion=1,  # type: ignore[arg-type]
        )
    assert not hasattr(host_package, "TerminalPostCommitNotice")
    assert not hasattr(host_package, "TerminalPostCommitPort")


def test_terminal_contract_module_has_no_upper_layer_dependency() -> None:
    """local-only contract 只依赖 dataclass/typing，不反向依赖业务层。"""

    tree = ast.parse(
        (_REPOSITORY_ROOT / "dayu/host/terminal_post_commit.py").read_text(
            encoding="utf-8"
        )
    )
    imported_roots = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imported_roots == {"__future__", "dataclasses", "typing"}


def test_static_terminal_producer_manifest_is_exact() -> None:
    """冻结 accepted plan 的 production terminal transition producer 闭集。"""

    actual: dict[str, frozenset[tuple[str, str]]] = {}
    for relative_path in _EXPECTED_TERMINAL_PRODUCERS:
        visitor = _qualified_calls(relative_path)
        actual[relative_path] = frozenset(
            (qualified_name, call_name)
            for qualified_name, call_name in visitor.calls
            if call_name in _TERMINAL_TRANSITION_NAMES
        )
    assert actual == _EXPECTED_TERMINAL_PRODUCERS


def test_queue_promotion_wakeup_allowlist_is_exact() -> None:
    """terminal producers 不得重新引入 ordinary promotion 旁路。"""

    actual: Counter[tuple[str, str]] = Counter()
    for relative_path in (
        "dayu/host/admission.py",
        "dayu/host/waiting.py",
        "dayu/host/recovery.py",
        "dayu/host/engine_ingest.py",
        "dayu/host/dispatch.py",
        "dayu/host/command.py",
        "dayu/host/open_host.py",
    ):
        visitor = _qualified_calls(relative_path)
        for qualified_name, call_name in visitor.calls:
            if call_name == "wake_queue_promotion":
                actual[(relative_path, qualified_name)] += 1
    assert actual == _EXPECTED_QUEUE_PROMOTION_WAKE_CALLS


def test_terminal_notice_projection_has_single_durable_owner() -> None:
    """五个 consumer 直接调用 durable owner，且不保留本地投影或别名。"""

    helper_name = "project_terminal_notice_from_exact_run_event"
    owner_tree = ast.parse(
        (_REPOSITORY_ROOT / "dayu/host/durable/run_transition.py").read_text(
            encoding="utf-8"
        )
    )
    owner_definitions = tuple(
        node
        for node in owner_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == helper_name
    )
    assert len(owner_definitions) == 1
    owner_definition = owner_definitions[0]
    assert tuple(argument.arg for argument in owner_definition.args.args) == (
        "run",
        "exact_run_event",
    )
    assert tuple(
        ast.unparse(annotation)
        for argument in owner_definition.args.args
        if (annotation := argument.annotation) is not None
    ) == ("RunRow | None", "EventLogRow | None")
    assert tuple(
        argument.arg for argument in owner_definition.args.kwonlyargs
    ) == ("wake_queue_promotion",)
    assert tuple(
        ast.unparse(annotation)
        for argument in owner_definition.args.kwonlyargs
        if (annotation := argument.annotation) is not None
    ) == ("bool",)

    for relative_path in _TERMINAL_NOTICE_PROJECTION_CONSUMERS:
        tree = ast.parse(
            (_REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        )
        local_definitions = tuple(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {
                helper_name,
                "terminal_notice_from_transition",
                "_terminal_notice_from_transition",
                "_terminal_notice_from_wait_transition",
            }
        )
        direct_imports = tuple(
            alias
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "dayu.host.durable.run_transition"
            for alias in node.names
            if alias.name == helper_name
        )
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        local_notice_constructions = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "TerminalPostCommitNotice"
        )
        local_helper_aliases = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and isinstance(node.value, ast.Name)
            and node.value.id == helper_name
        )
        assert local_definitions == ()
        assert len(direct_imports) == 1
        assert direct_imports[0].asname is None
        assert helper_name in called_names
        assert local_notice_constructions == ()
        assert local_helper_aliases == ()


def test_source_has_no_run_ref_notice_or_optional_production_port() -> None:
    """禁止 Run-ref notice helper、optional/default terminal port 与 runtime setter。"""

    admission_source = (_REPOSITORY_ROOT / "dayu/host/admission.py").read_text(
        encoding="utf-8"
    )
    dispatch_source = (_REPOSITORY_ROOT / "dayu/host/dispatch.py").read_text(
        encoding="utf-8"
    )
    command_source = (_REPOSITORY_ROOT / "dayu/host/command.py").read_text(
        encoding="utf-8"
    )
    assert "_terminal_notice_from_run_ref" not in admission_source
    assert "terminal_post_commit_port: TerminalPostCommitPort | None" not in (
        admission_source
    )
    assert "set_terminal_post_commit_port" not in dispatch_source
    assert "NoopTerminalPostCommit" not in dispatch_source
    assert "class _NoLocalDeliveryTerminalPostCommitPort" in command_source


@pytest.mark.asyncio
async def test_coordinator_watermark_before_promotion_and_independent_dedupe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """覆盖 owner loop、dedupe、close barrier 与低基数 outcome。"""

    caplog.set_level("INFO", logger="dayu.host.open_host")
    hub = HostTransientDeltaHub(
        policy=HostSessionEventDeliveryPolicy(
            transient_mailbox_max_items=8,
            max_subscriptions_per_session=2,
        )
    )
    promotion = _RecordingPromotionPort(hub)
    coordinator = _TerminalPostCommitCoordinator(
        loop=asyncio.get_running_loop(),
        delivery_hub=hub,
        promotion_port=promotion,
    )
    coordinator.notify_terminal_post_commit(_notice(10, wake=False))
    coordinator.notify_terminal_post_commit(_notice(12, wake=False))
    await asyncio.to_thread(
        coordinator.notify_terminal_post_commit,
        _notice(11, wake=True),
    )
    coordinator.notify_terminal_post_commit(_notice(11, wake=True))
    coordinator.notify_terminal_post_commit(_notice(13, wake=True))

    assert hub.committed_terminal_event_sequence_high_watermark("session-a") == 13
    assert promotion.promotions == [
        ("session-a", 12),
        ("session-a", 13),
    ]
    asyncio.get_running_loop().call_soon(
        coordinator._notify_on_owner_loop,
        _notice(14, wake=True),
    )
    await coordinator.close()
    assert hub.committed_terminal_event_sequence_high_watermark("session-a") == 14
    assert promotion.promotions == [
        ("session-a", 12),
        ("session-a", 13),
        ("session-a", 14),
    ]
    coordinator.notify_terminal_post_commit(_notice(15, wake=True))
    assert hub.committed_terminal_event_sequence_high_watermark("session-a") == 14
    assert promotion.promotions == [
        ("session-a", 12),
        ("session-a", 13),
        ("session-a", 14),
    ]
    messages = {
        record.getMessage()
        for record in caplog.records
        if "event=terminal_notice" in record.getMessage()
    }
    assert messages == {
        "host.session_event_delivery event=terminal_notice outcome=delivery_advanced",
        "host.session_event_delivery event=terminal_notice outcome=duplicate",
        "host.session_event_delivery event=terminal_notice outcome=promotion_woken",
        "host.session_event_delivery event=terminal_notice outcome=closing reason=coordinator_closing",
    }
    assert all("session-a" not in message for message in messages)
    assert all("capacity" not in message for message in messages)
    hub.close()


def _notice(sequence: int, *, wake: bool) -> TerminalPostCommitNotice:
    """构造 coordinator 测试 notice。

    :param sequence: exact terminal sequence。
    :param wake: promotion flag。
    :returns: terminal notice。
    """

    return TerminalPostCommitNotice(
        session_id="session-a",
        terminal_event_sequence=sequence,
        wake_queue_promotion=wake,
    )


def _qualified_calls(relative_path: str) -> _QualifiedCallVisitor:
    """解析 production module 并返回 qualified call visitor。

    :param relative_path: 仓库相对路径。
    :returns: 已完成遍历的 visitor。
    """

    tree = ast.parse(
        (_REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    )
    visitor = _QualifiedCallVisitor()
    visitor.visit(tree)
    return visitor


def _call_name(callable_node: ast.expr) -> str | None:
    """返回 call target 末级 symbol。

    :param callable_node: call.func AST expression。
    :returns: 可识别 Name/Attribute 的末级名称；其它表达式返回 ``None``。
    """

    if isinstance(callable_node, ast.Name):
        return callable_node.id
    if isinstance(callable_node, ast.Attribute):
        return callable_node.attr
    return None
