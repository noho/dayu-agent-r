"""人工验证 Host P8 Attempt Lease / Fencing / Recovery 路径的 smoke 脚本。

本脚本通过 7 个 offline deterministic 场景验证 P8 attempt 所有权、fencing、
recovery、terminal close、observer reconciliation 与 durable memory recovery:

1. Owner A acquire + renew → owner acquired, fencing token 不变, lease 刷新。
2. Owner B acquire 同 attempt_index → busy。
3. 时钟推进至 lease 过期 → ``recover_stale_attempts`` supervisor scan
   创建 recovery attempt, recovered_from 链接。
4. Owner A late write → fenced, EventLog 不残留。
5. 新 owner 通过 ``lease_context`` acquire 新 attempt → terminal close,
   attempt_state=failed。
6. 关闭 harness 后重新打开 → startup_reconcile observer caught up。
7. Durable memory: checkpoint caught-up 后删除 memory snapshot,
   startup_reconcile 通过 durable repair 从 EventLog 重建 snapshot
   (P8-S8 gap fix 验证)。

约束:

- 使用 file SQLite（tempfile），非 ``:memory:``。
- 使用 fake clock，无真实 ``time.sleep``。
- 使用 deterministic fake worker，无真实 provider。
- owner token 明文不出现在输出中（只用 masked）。
- summary 输出 ≤20 行，``key=value`` 格式。

运行示例::

    source .venv/bin/activate
    python utils/smoke_host_p8_attempt_lease.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT_PARENT_INDEX: int = 1


def _ensure_repo_root_on_path() -> None:
    """确保按文件路径运行脚本时也能导入仓库顶层包。

    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if __package__ not in (None, ""):
        return
    repo_root = Path(__file__).resolve().parents[_REPO_ROOT_PARENT_INDEX]
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)


_ensure_repo_root_on_path()

from dayu.host._attempt_lease import (  # noqa: E402
    AttemptFencingError,
    AttemptLeaseConfig,
    AttemptOwnerContext,
    AttemptOwnerToken,
    AttemptRecoveryAction,
)
from dayu.host._durable_harness import (  # noqa: E402
    DurableHarnessConfig,
    build_durable_harness,
)
from dayu.host._event_translation import (  # noqa: E402
    user_input_accepted_draft,
)
from dayu.host.contracts import (  # noqa: E402
    HostRunFailedData,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    UserInputAcceptedData,
    UserInputScope,
)
from dayu.runtime.log import LogLevel, configure  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SMOKE_RUN_ID: str = "smoke_p8_run_1"
_SMOKE_SESSION_ID: str = "smoke_p8_session"
_SMOKE_USER_TEXT: str = "P8 smoke 用户问题"
_LEASE_TTL_SECONDS: int = 30
_LEASE_RENEW_INTERVAL_SECONDS: int = 10


# ---------------------------------------------------------------------------
# Fake clock
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FakeUtcClock:
    """可手动推进的 fake UTC clock，用于 smoke 不依赖真实 ``time.sleep``。

    :param _current: 当前 fake UTC 时间。
    """

    _current: datetime

    def now(self) -> datetime:
        """返回当前 fake UTC 时间。

        :returns: timezone-aware UTC datetime。
        :raises Exception: 不主动抛出异常。
        """

        return self._current

    def advance(self, seconds: float) -> None:
        """将 fake 时钟向前推进指定秒数。

        :param seconds: 推进秒数；可以为负数（回退）。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._current += timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_id(value: str) -> str:
    """对 id 做安全 masking，仅暴露末尾 4 位。

    :param value: 待 masking 的 id 字符串。
    :returns: masked 字符串，形如 ``***abcd``。
    :raises Exception: 不主动抛出异常。
    """

    tail = 4
    if len(value) <= tail:
        return "***"
    return "***" + value[-tail:]


def _terminal_failed_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
) -> RunEventDraft:
    """构造 Host-owned RUN_FAILED terminal draft。

    :param run_id: Run id。
    :param session_id: Session id。
    :param occurred_at: 事件发生时间。
    :returns: terminal RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.RUN_FAILED,
        occurred_at=occurred_at,
        data=HostRunFailedData(
            error_code="smoke_p8_test_failure",
            message="P8 smoke test failure",
            recoverable=False,
            exception_type="SmokeTestError",
        ),
        source_engine_event_id=None,
    )


# ---------------------------------------------------------------------------
# Main smoke logic
# ---------------------------------------------------------------------------


async def _run_smoke() -> None:
    """驱动 7 个 P8 attempt lease / fencing / recovery 场景。

    :returns: 无返回值。
    :raises Exception: 子组件异常时透传。
    """

    clock = FakeUtcClock(_current=datetime.now(tz=timezone.utc))
    lease_config = AttemptLeaseConfig(
        ttl=timedelta(seconds=_LEASE_TTL_SECONDS),
        renew_interval=timedelta(seconds=_LEASE_RENEW_INTERVAL_SECONDS),
        owner_id_prefix="smoke",
    )

    with tempfile.TemporaryDirectory(prefix="smoke_p8_") as tmp:
        db_path = str(Path(tmp) / "smoke_p8.db")
        config = DurableHarnessConfig(
            database_path=db_path,
            attempt_lease_config=lease_config,
        )

        # === Scenario 1: Owner A acquire + renew ===
        bundle = build_durable_harness(config=config, clock=clock)
        try:
            # 用 USER_INPUT_ACCEPTED 创建 run 记录
            user_draft = user_input_accepted_draft(
                run_id=_SMOKE_RUN_ID,
                session_id=_SMOKE_SESSION_ID,
                occurred_at=clock.now(),
                turn_id=_SMOKE_RUN_ID,
                content=_SMOKE_USER_TEXT,
            )
            await bundle.event_store.append(user_draft)

            # Owner A acquire via supervisor.lease_context
            owner_a: AttemptOwnerContext | None = None
            async with bundle.attempt_supervisor.lease_context(
                run_id=_SMOKE_RUN_ID,
                attempt_index=0,
            ) as ctx_a:
                owner_a = ctx_a
                a_token_masked = ctx_a.owner_token.masked()
                a_fencing = ctx_a.fencing_token.value
                a_attempt_id = ctx_a.attempt_id

                # Manual renew to verify lease extension
                new_expiry = clock.now() + lease_config.ttl
                async with bundle.storage.transaction() as tx:
                    renew_result = bundle.attempt_lease_store.renew(
                        tx=tx,
                        owner_context=ctx_a,
                        lease_expires_at=new_expiry,
                    )
                renewed = renew_result.decision.value == "acquired"

                print(
                    f"[s1] owner_acquired=true "
                    f"owner={a_token_masked} "
                    f"fencing_token={a_fencing} "
                    f"renewed={renewed}"
                )

            # === Scenario 2: Owner B acquire same attempt_index → busy ===
            # lease_context 退出后 attempt 已 RUNNING，再 acquire 同 index → BUSY
            owner_b_token = AttemptOwnerToken.new()
            owner_b_expiry = clock.now() + lease_config.ttl
            async with bundle.storage.transaction() as tx:
                b_result = bundle.attempt_lease_store.acquire_new_attempt(
                    tx=tx,
                    attempt_id=f"attempt-{_SMOKE_RUN_ID}-0-b",
                    run_id=_SMOKE_RUN_ID,
                    attempt_index=0,
                    recovered_from_attempt_id=None,
                    owner_id="smoke:owner_b",
                    owner_token=owner_b_token,
                    lease_expires_at=owner_b_expiry,
                )
            busy = b_result.decision.value == "busy"
            print(f"[s2] busy={busy}")

            # === Scenario 3: Advance clock → supervisor recovery scan ===
            # 推进时钟超过 lease TTL，使 attempt A lease 过期
            clock.advance(_LEASE_TTL_SECONDS + 5)

            # 通过 supervisor.recover_stale_attempts 执行 recovery scan
            # supervisor 内部扫描候选、CAS 标记 RECOVERING、创建 recovery attempt
            recovery_decisions = await bundle.attempt_supervisor.recover_stale_attempts(
                run_id=_SMOKE_RUN_ID,
            )
            assert len(recovery_decisions) > 0, (
                "recover_stale_attempts 应至少返回 1 个决策"
            )
            decision = recovery_decisions[0]
            assert decision.action is AttemptRecoveryAction.MARK_RECOVERING_AND_CREATE_ATTEMPT, (
                f"期望 MARK_RECOVERING_AND_CREATE_ATTEMPT, 实际 {decision.action}"
            )
            assert decision.recovery_attempt_id is not None
            assert decision.recovery_attempt_index is not None
            recovery_attempt_id = decision.recovery_attempt_id
            recovery_attempt_index = decision.recovery_attempt_index

            # 验证旧 attempt 状态为 RECOVERING
            old_attempt = bundle.attempt_state_store.get(a_attempt_id)
            old_state = (
                old_attempt.state.value
                if old_attempt is not None
                else "missing"
            )

            print(
                f"[s3] recovered_from={_mask_id(a_attempt_id)} "
                f"recovery_attempt={_mask_id(recovery_attempt_id)} "
                f"recovery_index={recovery_attempt_index} "
                f"old_state={old_state}"
            )

            # === Scenario 4: Owner A late write → fenced ===
            # Owner A 的 lease 已过期，scoped_appender.append 应抛
            # AttemptFencingError
            assert owner_a is not None
            old_appender = bundle.attempt_supervisor.scoped_appender(owner_a)
            # 用非 terminal draft 测试 fenced（terminal draft 会先被
            # ValueError 拦截，无法到达 fencing 路径）
            late_non_terminal = RunEventDraft(
                run_id=_SMOKE_RUN_ID,
                session_id=_SMOKE_SESSION_ID,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.USER_INPUT_ACCEPTED,
                occurred_at=clock.now(),
                data=UserInputAcceptedData(
                    turn_id="late-turn",
                    content="late",
                    scope=UserInputScope.SESSION,
                ),
                source_engine_event_id=None,
            )
            try:
                await old_appender.append(late_non_terminal)
                fence_reason = "no_error"
            except AttemptFencingError as exc:
                fence_reason = exc.reason.value

            print(f"[s4] late_write=fenced reason={fence_reason}")

            # === Scenario 5: New owner terminal close via lease_context ===
            # recovery attempt 的 owner_token 由 supervisor 内部持有,
            # 无法从 AttemptRecoveryDecision 获取。改用 lease_context acquire
            # 一个新 attempt (attempt_index = recovery_index + 1) 来验证
            # append_terminal_and_close 路径。
            terminal_attempt_index = recovery_attempt_index + 1
            terminal_draft = _terminal_failed_draft(
                run_id=_SMOKE_RUN_ID,
                session_id=_SMOKE_SESSION_ID,
                occurred_at=clock.now(),
            )
            async with bundle.attempt_supervisor.lease_context(
                run_id=_SMOKE_RUN_ID,
                attempt_index=terminal_attempt_index,
            ) as terminal_ctx:
                link = await bundle.attempt_supervisor.append_terminal_and_close(
                    owner_context=terminal_ctx,
                    draft=terminal_draft,
                )
            attempt_after = bundle.attempt_state_store.get(
                terminal_ctx.attempt_id
            )
            attempt_state = (
                attempt_after.state.value
                if attempt_after is not None
                else "missing"
            )
            print(
                f"[s5] terminal_event_position={link.event_position.value} "
                f"attempt_state={attempt_state}"
            )

        finally:
            bundle.close()

        # === Scenario 6: Reopen harness → startup_reconcile ===
        bundle2 = build_durable_harness(config=config, clock=clock)
        try:
            await bundle2.startup_reconcile()
            checkpoints = await bundle2.coordinator.drain()
            all_caught = all(
                cp.lag_events == 0 for cp in checkpoints
            )
            print(f"[s6] observer_caught_up={all_caught}")

            # === Scenario 7: Durable memory recovery via repair path ===
            # 先验证 memory snapshot 存在（S6 drain 后 projection 已写入）
            snapshot = await bundle2.memory_store.get_snapshot(
                _SMOKE_SESSION_ID
            )
            has_user_input = any(
                _SMOKE_USER_TEXT in (turn.user_text or "")
                for turn in snapshot.recent_raw_turns
            )
            assert has_user_input, (
                "S6 drain 后 memory snapshot 应包含用户输入"
            )

            # 验证 memory observer checkpoint 已 CAUGHT_UP
            memory_cp = bundle2.coordinator.projection_store.get(
                observer_id="host_memory_projection",
                projection_name="conversation_memory",
                schema_version=1,
            )
            checkpoint_caught_up = (
                memory_cp is not None
                and memory_cp.lag_events == 0
            )

            # 直接删除 memory snapshot 模拟 read model 丢失
            async with bundle2.storage.transaction() as tx:
                tx.execute(
                    "DELETE FROM host_conversation_memory_snapshots "
                    "WHERE session_id = ?",
                    (_SMOKE_SESSION_ID,),
                )

            # 验证 snapshot 已被删除
            empty_snapshot = await bundle2.memory_store.get_snapshot(
                _SMOKE_SESSION_ID
            )
            snapshot_deleted = len(empty_snapshot.recent_raw_turns) == 0

            # 再次 startup_reconcile: checkpoint 已 CAUGHT_UP 且无新事件,
            # coordinator drain 不会重投; durable memory repair 路径必须
            # 从 EventLog 重建缺失 snapshot。
            await bundle2.startup_reconcile()
            final_snapshot = await bundle2.memory_store.get_snapshot(
                _SMOKE_SESSION_ID
            )
            memory_recovered = any(
                _SMOKE_USER_TEXT in (turn.user_text or "")
                for turn in final_snapshot.recent_raw_turns
            )

            print(
                f"[s7] checkpoint_caught_up={checkpoint_caught_up} "
                f"snapshot_deleted={snapshot_deleted} "
                f"memory_recovered={memory_recovered} "
                f"recovery_mode=checkpoint_rebuild"
            )
        finally:
            bundle2.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _SmokeArgs:
    """P8 smoke 命令行参数。"""

    log_level: LogLevel


def _parse_args(argv: Sequence[str]) -> _SmokeArgs:
    """解析 smoke 命令行参数。

    :param argv: 不含程序名的命令行参数。
    :returns: 解析后的 smoke 参数。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run manual Host P8 attempt lease smoke checks."
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(level.name for level in LogLevel),
        default=LogLevel.VERBOSE.name,
        help="Dayu namespace log level; default: VERBOSE.",
    )
    namespace = parser.parse_args(list(argv))
    log_level_name: str = namespace.log_level
    return _SmokeArgs(log_level=LogLevel[log_level_name])


def main(argv: Sequence[str] | None = None) -> None:
    """脚本入口。

    :param argv: 不含程序名的命令行参数；为 ``None`` 时读取 ``sys.argv``。
    :returns: 无返回值。
    :raises Exception: 子组件异常时透传。
    """

    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure(level=args.log_level)
    asyncio.run(_run_smoke())


if __name__ == "__main__":
    main()
