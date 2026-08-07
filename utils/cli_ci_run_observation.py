"""CLI CI 对 Host canonical Run terminal facts 的只读投影。

本模块只读取物理只读 Host EventLog window，并把 accepted Run、terminal
类型与 canonical reason 投影为确定性 typed facts。它不读取进程退出状态，
不判定业务答案，也不持久化第二份 Run status。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from dayu.contracts.json_value import JsonValue
from dayu.host.api import CancelMode, RunStatus
from dayu.host.durable.connection import open_host_durable_read_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogReadClassFilter,
    EventLogReadFilter,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import HostSQLiteStoragePolicy
from dayu.host.durable.transaction import HostTransaction
from dayu.host.lifecycle_events import (
    HOST_RUN_TERMINAL_EVENT_TYPES,
    HostRunEventType,
    event_type_values,
    is_public_outbox_terminal_item_event,
    run_status_for_terminal_event,
)

_DEFAULT_PAGE_SIZE: Final[int] = 64
_DEFAULT_PUBLIC_SCAN_MAX_BYTES: Final[int] = 128 * 1024 * 1024
_FINAL_PUBLICATION_SCAN_REPORT_NAME: Final[str] = "secret-scan.json"
_REASON_KEY: Final[str] = "reason"
_RAW_DATABASE_SUFFIXES: Final[frozenset[str]] = frozenset(
    (".sqlite", ".sqlite3", ".db")
)
_RAW_DATABASE_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:^|[\s\"'=:(])[^\s\"'<>]*\.(?:sqlite|sqlite3|db)"
    r"(?:$|[\s\"',;)])"
)
_RUN_EVENT_TYPES: Final[tuple[str, ...]] = (
    HostRunEventType.RUN_ACCEPTED.value,
    *event_type_values(HOST_RUN_TERMINAL_EVENT_TYPES),
)
_RUN_EVENT_FILTER: Final[EventLogReadFilter] = EventLogReadFilter(
    class_filters=(
        EventLogReadClassFilter(
            event_class=EventClass.CANONICAL_FACT,
            event_types=_RUN_EVENT_TYPES,
        ),
    )
)


class RunObservationError(RuntimeError):
    """Run terminal observation 不完整或 canonical facts 非法。"""


@dataclass(frozen=True, slots=True)
class PublicEvidenceSecretProbe:
    """public evidence exact-value secret probe。

    :param name: 只进入scan diagnostics的secret标签。
    :param value: 仅在内存中用于exact match的真实secret值。
    """

    name: str
    value: str

    def __post_init__(self) -> None:
        """校验secret probe非空且类型严格。

        :returns: ``None``。
        :raises TypeError: name/value不是字符串时抛出。
        :raises ValueError: name/value为空或纯空白时抛出。
        """

        if not isinstance(self.name, str) or not isinstance(self.value, str):
            raise TypeError("secret probe name/value must be str")
        if self.name.strip() == "" or self.value.strip() == "":
            raise ValueError("secret probe name/value must be non-empty")


@dataclass(frozen=True, slots=True)
class PublicEvidenceScanResult:
    """secret exact-value scan与路径卫生检查的typed结果。

    :param scanned_file_count: 已读取regular files数量。
    :param scanned_byte_count: 已扫描bytes总数。
    :param file_descriptors: scanned file path/size/digest。
    :param secret_hits: actual secret/canary exact-value命中。
    :param path_hygiene_violations: symlink、raw DB file/path或scope越界。
    :param validation_errors: missing/unreadable/oversized file diagnostics。
    """

    scanned_file_count: int
    scanned_byte_count: int
    file_descriptors: tuple[JsonValue, ...]
    secret_hits: tuple[JsonValue, ...]
    path_hygiene_violations: tuple[JsonValue, ...]
    validation_errors: tuple[JsonValue, ...]

    def to_json(self) -> JsonValue:
        """转换为public secret-scan JSON object。

        :returns: 分离secret scan与path hygiene的确定性JSON。
        :raises Exception: 不主动抛出异常。
        """

        valid = not (
            self.secret_hits
            or self.path_hygiene_violations
            or self.validation_errors
        )
        return {
            "status": "complete" if valid else "invalid",
            "scanned_file_count": self.scanned_file_count,
            "scanned_byte_count": self.scanned_byte_count,
            "files": list(self.file_descriptors),
            "secret_scan": {
                "status": "complete" if not self.secret_hits else "invalid",
                "hits": list(self.secret_hits),
            },
            "path_hygiene": {
                "status": (
                    "complete"
                    if not self.path_hygiene_violations
                    else "invalid"
                ),
                "violations": list(self.path_hygiene_violations),
            },
            "validation_errors": list(self.validation_errors),
        }


class RunObservationRole(StrEnum):
    """Run 在当前 CI action chain 中的显式角色。"""

    REQUIRED = "required"
    DEPENDENT = "dependent"
    INDEPENDENT = "independent"


class HarnessActionRole(StrEnum):
    """PTY harness action 在依赖链中的控制角色。"""

    REQUIRED = "required"
    INDEPENDENT = "independent"
    DEPENDENT = "dependent"
    CLEANUP_EOT = "cleanup_eot"


class RemainingActionDisposition(StrEnum):
    """依赖链安全停止后剩余 action 的确定性处置。"""

    NOT_RUN_DEPENDENT = "not_run_dependent"
    NOT_RUN_PROCESS_STOP = "not_run_process_stop"
    SEND_CLEANUP_EOT = "send_cleanup_eot"


@dataclass(frozen=True, slots=True)
class HarnessActionControl:
    """供 tracked 纯决策使用的最小 PTY action 控制事实。

    :param action_index: action 在原序列中的零基位置。
    :param role: action 的显式控制角色。
    :param required_success_accepted_ordinal: dependent action 的 upstream ordinal。
    """

    action_index: int
    role: HarnessActionRole
    required_success_accepted_ordinal: int | None

    def __post_init__(self) -> None:
        """校验 action control 的角色与 dependency 一致性。

        :returns: ``None``。
        :raises TypeError: index、role 或 ordinal 类型非法时抛出。
        :raises ValueError: index、ordinal 或角色组合非法时抛出。
        """

        if isinstance(self.action_index, bool) or not isinstance(
            self.action_index, int
        ):
            raise TypeError("action_index must be int")
        if self.action_index < 0:
            raise ValueError("action_index must be non-negative")
        if not isinstance(self.role, HarnessActionRole):
            raise TypeError("role must be HarnessActionRole")
        if self.role is HarnessActionRole.DEPENDENT:
            if self.required_success_accepted_ordinal is None:
                raise ValueError("dependent action must declare upstream ordinal")
            _require_positive_int(
                self.required_success_accepted_ordinal,
                field_name="required_success_accepted_ordinal",
            )
        elif self.required_success_accepted_ordinal is not None:
            raise ValueError("non-dependent action must not declare upstream ordinal")


@dataclass(frozen=True, slots=True)
class RemainingActionDecision:
    """依赖链安全停止后一个 remaining action 的处置。

    :param action_index: 原 action index。
    :param disposition: not-run 或唯一 cleanup/EOT 处置。
    :param required_success_accepted_ordinal: dependent action 的 upstream ordinal。
    """

    action_index: int
    disposition: RemainingActionDisposition
    required_success_accepted_ordinal: int | None


class DependencyGateStatus(StrEnum):
    """success-required dependency gate 的确定性状态。"""

    PROCEEDED = "proceeded"
    STOPPED = "stopped"
    PENDING = "pending"
    INVALID = "invalid"


class RunEvidenceStatus(StrEnum):
    """required Run terminal evidence 的完整性状态。"""

    COMPLETE = "complete"
    INSUFFICIENT = "insufficient"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class RunObservationWindow:
    """不可变 EventLog observation window。

    :param start_event_sequence: 排他起点。
    :param end_event_sequence: 冻结后的包含式终点。
    :param session_id: 可选 exact session scope。
    """

    start_event_sequence: int
    end_event_sequence: int
    session_id: str | None

    def __post_init__(self) -> None:
        """校验 window 边界。

        :returns: ``None``。
        :raises TypeError: 边界或 session 类型非法时抛出。
        :raises ValueError: sequence 值或 session 文本非法时抛出。
        """

        if isinstance(self.start_event_sequence, bool) or not isinstance(
            self.start_event_sequence, int
        ):
            raise TypeError("start_event_sequence must be int")
        if isinstance(self.end_event_sequence, bool) or not isinstance(
            self.end_event_sequence, int
        ):
            raise TypeError("end_event_sequence must be int")
        if self.start_event_sequence < 0:
            raise ValueError("start_event_sequence must be non-negative")
        if self.end_event_sequence < self.start_event_sequence:
            raise ValueError("end_event_sequence must not precede start")
        if self.session_id is not None:
            if not isinstance(self.session_id, str):
                raise TypeError("session_id must be str or None")
            if self.session_id.strip() == "":
                raise ValueError("session_id must be non-empty")

    def to_json(self) -> JsonValue:
        """转换为确定性 JSON object。

        :returns: window JSON object。
        """

        return {
            "start_event_sequence": self.start_event_sequence,
            "end_event_sequence": self.end_event_sequence,
            "session_id": self.session_id,
        }


@dataclass(frozen=True, slots=True)
class RunTerminalObservation:
    """一个 accepted Run 的 canonical terminal observation。

    :param accepted_ordinal: 跨 segment 累计的一基 accepted ordinal。
    :param role: 显式 action-chain role。
    :param session_id: canonical session identity。
    :param run_id: canonical Run identity。
    :param accepted_event_id: ``RUN_ACCEPTED`` event id。
    :param accepted_event_sequence: ``RUN_ACCEPTED`` event sequence。
    :param terminal_event_type: shared Host terminal event type。
    :param terminal_event_id: terminal event id。
    :param terminal_event_sequence: terminal event sequence。
    :param terminal_class: lifecycle owner 投影的 durable Run terminal status。
    :param reason: exact ``reason_json`` 中的 canonical reason。
    :param public_outbox_terminal: 是否属于既有 public outbox terminal 集合。
    """

    accepted_ordinal: int
    role: RunObservationRole
    session_id: str
    run_id: str
    accepted_event_id: str
    accepted_event_sequence: int
    terminal_event_type: HostRunEventType
    terminal_event_id: str
    terminal_event_sequence: int
    terminal_class: RunStatus
    reason: str
    public_outbox_terminal: bool

    def to_json(self) -> JsonValue:
        """转换为稳定 JSON object。

        :returns: per-Run terminal JSON object。
        """

        return {
            "accepted_ordinal": self.accepted_ordinal,
            "role": self.role.value,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "accepted_event_id": self.accepted_event_id,
            "accepted_event_sequence": self.accepted_event_sequence,
            "terminal_event_type": self.terminal_event_type.value,
            "terminal_event_id": self.terminal_event_id,
            "terminal_event_sequence": self.terminal_event_sequence,
            "terminal_class": self.terminal_class.value,
            "reason": self.reason,
            "public_outbox_terminal": self.public_outbox_terminal,
        }


@dataclass(frozen=True, slots=True)
class RunTerminalObservationSet:
    """一个 frozen window 的完整 per-Run terminal projection。

    :param window: frozen observation window。
    :param runs: 按 accepted event sequence 排序的 Run facts。
    """

    window: RunObservationWindow
    runs: tuple[RunTerminalObservation, ...]

    def to_json(self) -> JsonValue:
        """转换为 run-terminals.json 可直接写入的 JSON value。

        :returns: window、summary 与 per-Run facts。
        """

        return {
            "window": self.window.to_json(),
            "summary": {
                "accepted": len(self.runs),
                "succeeded": self._count(RunStatus.SUCCEEDED),
                "failed": self._count(RunStatus.FAILED),
                "cancelled": self._count(RunStatus.CANCELLED),
                "lost": self._count(RunStatus.LOST),
                "missing": 0,
                "invalid": 0,
            },
            "runs": [run.to_json() for run in self.runs],
        }

    def by_accepted_ordinal(
        self, accepted_ordinal: int
    ) -> RunTerminalObservation | None:
        """按累计 accepted ordinal 查找 Run fact。

        :param accepted_ordinal: 一基 accepted ordinal。
        :returns: 找到时返回 fact，否则返回 ``None``。
        :raises TypeError: ordinal 类型非法时抛出。
        :raises ValueError: ordinal 非正数时抛出。
        """

        _require_positive_int(accepted_ordinal, field_name="accepted_ordinal")
        for run in self.runs:
            if run.accepted_ordinal == accepted_ordinal:
                return run
        return None

    def _count(self, terminal_class: RunStatus) -> int:
        """统计指定 terminal class。

        :param terminal_class: 目标 terminal class。
        :returns: 精确计数。
        """

        return sum(run.terminal_class is terminal_class for run in self.runs)


@dataclass(frozen=True, slots=True)
class RunDependencyDecision:
    """一个 success-required dependency gate 的 typed 结果。

    :param status: proceeded/stopped/pending/invalid。
    :param required_success_accepted_ordinal: 明确 upstream ordinal。
    :param upstream_run_id: 已观察到时的 upstream Run id。
    :param upstream_terminal: 已观察到时的 terminal class。
    :param upstream_reason: 已观察到时的 canonical reason。
    """

    status: DependencyGateStatus
    required_success_accepted_ordinal: int
    upstream_run_id: str | None
    upstream_terminal: RunStatus | None
    upstream_reason: str | None

    def to_json(self) -> JsonValue:
        """转换为 deterministic dependency gate JSON。

        :returns: dependency decision JSON object。
        """

        return {
            "status": self.status.value,
            "required_success_accepted_ordinal": (
                self.required_success_accepted_ordinal
            ),
            "upstream_run_id": self.upstream_run_id,
            "upstream_terminal": (
                None
                if self.upstream_terminal is None
                else self.upstream_terminal.value
            ),
            "upstream_reason": self.upstream_reason,
        }


def observe_run_terminals(
    *,
    db_path: Path,
    artifact_root: Path,
    window: RunObservationWindow,
    roles_by_accepted_ordinal: Mapping[int, RunObservationRole],
    accepted_ordinal_offset: int = 0,
    page_size: int = _DEFAULT_PAGE_SIZE,
    sqlite_policy: HostSQLiteStoragePolicy | None = None,
) -> RunTerminalObservationSet:
    """从物理只读 Host store 投影 frozen window 的完整 Run terminals。

    :param db_path: 现有 Host SQLite 文件。
    :param artifact_root: Host artifact root。
    :param window: 排他/包含式 frozen EventLog window。
    :param roles_by_accepted_ordinal: 每个累计 ordinal 的显式 chain role。
    :param accepted_ordinal_offset: 当前 segment 前已接受 Run 数。
    :param page_size: filtered keyset 单页大小，仅影响批次。
    :param sqlite_policy: 可选只读 busy-timeout policy。
    :returns: 完整且严格验证的 per-Run terminal facts。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: ordinal offset 或 page size 非法时抛出。
    :raises RunObservationError: window、reason 或 Run 归属不完整时抛出。
    """

    if not isinstance(window, RunObservationWindow):
        raise TypeError("window must be RunObservationWindow")
    if isinstance(accepted_ordinal_offset, bool) or not isinstance(
        accepted_ordinal_offset, int
    ):
        raise TypeError("accepted_ordinal_offset must be int")
    if accepted_ordinal_offset < 0:
        raise ValueError("accepted_ordinal_offset must be non-negative")
    _require_positive_int(page_size, field_name="page_size")
    policy = HostSQLiteStoragePolicy() if sqlite_policy is None else sqlite_policy
    if not isinstance(policy, HostSQLiteStoragePolicy):
        raise TypeError("sqlite_policy must be HostSQLiteStoragePolicy or None")
    event_log = EventLogStore()
    rows: tuple[EventLogRow, ...] = ()
    with open_host_durable_read_store(
        db_path=db_path,
        artifact_root=artifact_root,
        sqlite_policy=policy,
    ) as store:
        rows = store.run_read(
            lambda transaction: _read_filtered_window(
                transaction,
                event_log,
                window=window,
                page_size=page_size,
            )
        )
    return _project_terminal_rows(
        rows,
        window=window,
        roles_by_accepted_ordinal=roles_by_accepted_ordinal,
        accepted_ordinal_offset=accepted_ordinal_offset,
    )


def evaluate_success_dependency(
    observation: RunTerminalObservation | None,
    *,
    required_success_accepted_ordinal: int,
    deadline_reached: bool,
) -> RunDependencyDecision:
    """机械判定一个明确 upstream Run 是否允许 dependent work 继续。

    :param observation: upstream terminal fact；等待期尚无 terminal 时为 ``None``。
    :param required_success_accepted_ordinal: 依赖的累计 accepted ordinal。
    :param deadline_reached: 当前等待 deadline 是否已到。
    :returns: proceeded/stopped/pending/invalid typed decision。
    :raises TypeError: observation 或 deadline 类型非法时抛出。
    :raises ValueError: ordinal 非正数时抛出。
    """

    _require_positive_int(
        required_success_accepted_ordinal,
        field_name="required_success_accepted_ordinal",
    )
    if not isinstance(deadline_reached, bool):
        raise TypeError("deadline_reached must be bool")
    if observation is None:
        return RunDependencyDecision(
            status=(
                DependencyGateStatus.INVALID
                if deadline_reached
                else DependencyGateStatus.PENDING
            ),
            required_success_accepted_ordinal=required_success_accepted_ordinal,
            upstream_run_id=None,
            upstream_terminal=None,
            upstream_reason=None,
        )
    if not isinstance(observation, RunTerminalObservation):
        raise TypeError("observation must be RunTerminalObservation or None")
    if observation.accepted_ordinal != required_success_accepted_ordinal:
        return RunDependencyDecision(
            status=DependencyGateStatus.INVALID,
            required_success_accepted_ordinal=required_success_accepted_ordinal,
            upstream_run_id=observation.run_id,
            upstream_terminal=observation.terminal_class,
            upstream_reason=observation.reason,
        )
    return RunDependencyDecision(
        status=(
            DependencyGateStatus.PROCEEDED
            if observation.terminal_class is RunStatus.SUCCEEDED
            else DependencyGateStatus.STOPPED
        ),
        required_success_accepted_ordinal=required_success_accepted_ordinal,
        upstream_run_id=observation.run_id,
        upstream_terminal=observation.terminal_class,
        upstream_reason=observation.reason,
    )


def dependent_action_accepted_ordinal(
    required_success_accepted_ordinal: int,
) -> int:
    """把直接 upstream ordinal 转为紧随其后的 dependent Run ordinal。

    当前 PTY chain 每个 dependent action 只依赖紧邻的上一个 accepted Run；该
    转换集中在这里，避免 temporary harness 隐式散落 ``+ 1`` 算术。

    :param required_success_accepted_ordinal: 直接 upstream Run 的累计 ordinal。
    :returns: dependent action 被接受后对应的累计 ordinal。
    :raises TypeError: upstream ordinal 类型非法时抛出。
    :raises ValueError: upstream ordinal 非正数时抛出。
    """

    _require_positive_int(
        required_success_accepted_ordinal,
        field_name="required_success_accepted_ordinal",
    )
    return required_success_accepted_ordinal + 1


def run_observation_role_for_harness_action(
    role: HarnessActionRole,
) -> RunObservationRole:
    """把业务 action role 投影为 per-Run observation role。

    :param role: required/dependent/independent/cleanup harness role。
    :returns: 对应的 reusable Run observation role。
    :raises TypeError: role 类型非法时抛出。
    :raises ValueError: cleanup/EOT 不产生 Run，不能投影时抛出。
    """

    if not isinstance(role, HarnessActionRole):
        raise TypeError("role must be HarnessActionRole")
    if role is HarnessActionRole.CLEANUP_EOT:
        raise ValueError("cleanup/EOT does not have Run observation role")
    return RunObservationRole(role.value)


def classify_required_run_evidence(
    terminal_statuses: tuple[RunStatus, ...] | None,
) -> RunEvidenceStatus:
    """区分 canonical observation invalid 与 valid non-succeeded evidence。

    ``None`` 表示 canonical observation shape/identity/读取失败；空 tuple 表示
    required Run acceptance/terminal 缺失。二者均为 invalid。非空且全部
    ``SUCCEEDED`` 才 complete；其余合法 terminal 为 insufficient，而不是 PASS。

    :param terminal_statuses: required/dependent Run terminal statuses；invalid 时为
        ``None``。
    :returns: complete/insufficient/invalid。
    :raises TypeError: tuple 元素不是 terminal RunStatus 时抛出。
    """

    if terminal_statuses is None or len(terminal_statuses) == 0:
        return RunEvidenceStatus.INVALID
    for status in terminal_statuses:
        if status not in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.LOST,
        }:
            raise TypeError("terminal_statuses must contain terminal RunStatus")
    if all(status is RunStatus.SUCCEEDED for status in terminal_statuses):
        return RunEvidenceStatus.COMPLETE
    return RunEvidenceStatus.INSUFFICIENT


def validate_terminal_class_summary(
    *,
    accepted: int,
    succeeded: int,
    failed: int,
    cancelled: int,
    lost: int,
    terminal_statuses: tuple[RunStatus, ...],
) -> None:
    """逐类对账per-Run terminal records与summary。

    :param accepted: summary accepted计数。
    :param succeeded: summary succeeded计数。
    :param failed: summary failed计数。
    :param cancelled: summary cancelled计数。
    :param lost: summary lost计数。
    :param terminal_statuses: per-Run records中的typed terminal类别。
    :returns: ``None``。
    :raises TypeError: 任一计数或terminal tuple类型非法时抛出。
    :raises ValueError: 任一计数为负数时抛出。
    :raises RunObservationError: summary与per-Run records不完全一致时抛出。
    """

    summary = {
        RunStatus.SUCCEEDED: succeeded,
        RunStatus.FAILED: failed,
        RunStatus.CANCELLED: cancelled,
        RunStatus.LOST: lost,
    }
    for field_name, value in (
        ("accepted", accepted),
        ("succeeded", succeeded),
        ("failed", failed),
        ("cancelled", cancelled),
        ("lost", lost),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field_name} must be int")
        if value < 0:
            raise ValueError(f"{field_name} must be non-negative")
    if not isinstance(terminal_statuses, tuple):
        raise TypeError("terminal_statuses must be tuple")
    observed = {status: 0 for status in summary}
    for status in terminal_statuses:
        if status not in observed:
            raise TypeError("terminal_statuses must contain terminal RunStatus")
        observed[status] += 1
    if len(terminal_statuses) != accepted:
        raise RunObservationError(
            "per-Run terminal record count does not match accepted summary"
        )
    if observed != summary:
        raise RunObservationError(
            "per-Run terminal classes do not match summary"
        )


def scan_public_evidence_files(
    *,
    evidence_root: Path,
    files: tuple[Path, ...],
    exact_secret_probes: tuple[PublicEvidenceSecretProbe, ...],
    max_file_bytes: int = _DEFAULT_PUBLIC_SCAN_MAX_BYTES,
) -> PublicEvidenceScanResult:
    """扫描public evidence secrets，并独立执行raw DB/path hygiene检查。

    普通repo/run/corpus路径不是credential，不参与exact secret probes。路径卫生只
    拒绝scope外文件、symlink、raw ``*.sqlite``/``*.sqlite3``/``*.db``文件，
    以及public文本中出现的raw database路径。

    :param evidence_root: public evidence共同root。
    :param files: 拟公开文件tuple。
    :param exact_secret_probes: 实际secret值与有意义canary的内存probe。
    :param max_file_bytes: 单文件最大扫描bytes。
    :returns: secret与path hygiene分离的typed scan result。
    :raises TypeError: 参数或tuple元素类型非法时抛出。
    :raises ValueError: root、limit或重复文件非法时抛出。
    """

    if not isinstance(evidence_root, Path):
        raise TypeError("evidence_root must be Path")
    if not isinstance(files, tuple):
        raise TypeError("files must be tuple")
    if not isinstance(exact_secret_probes, tuple):
        raise TypeError("exact_secret_probes must be tuple")
    _require_positive_int(max_file_bytes, field_name="max_file_bytes")
    for probe in exact_secret_probes:
        if not isinstance(probe, PublicEvidenceSecretProbe):
            raise TypeError("exact_secret_probes item must be PublicEvidenceSecretProbe")
    root = evidence_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("evidence_root must be directory")
    seen_paths: set[Path] = set()
    descriptors: list[JsonValue] = []
    secret_hits: list[JsonValue] = []
    path_violations: list[JsonValue] = []
    validation_errors: list[JsonValue] = []
    scanned_bytes = 0
    for candidate in files:
        if not isinstance(candidate, Path):
            raise TypeError("files item must be Path")
        if candidate in seen_paths:
            raise ValueError("files must not contain duplicates")
        seen_paths.add(candidate)
        absolute_candidate = candidate.absolute()
        try:
            relative = absolute_candidate.relative_to(root)
        except ValueError:
            path_violations.append(
                {"path": str(candidate), "reason": "outside_evidence_root"}
            )
            continue
        relative_text = relative.as_posix()
        path_cursor = root
        has_symlink_component = False
        for part in relative.parts:
            path_cursor = path_cursor / part
            if path_cursor.is_symlink():
                has_symlink_component = True
                break
        if has_symlink_component:
            path_violations.append(
                {"path": relative_text, "reason": "symlink_forbidden"}
            )
            continue
        try:
            absolute_candidate.resolve(strict=False).relative_to(root)
        except ValueError:
            path_violations.append(
                {"path": relative_text, "reason": "outside_evidence_root"}
            )
            continue
        if candidate.suffix.lower() in _RAW_DATABASE_SUFFIXES:
            path_violations.append(
                {"path": relative_text, "reason": "raw_database_file_forbidden"}
            )
            continue
        if not candidate.is_file():
            validation_errors.append(
                {"path": relative_text, "reason": "regular_file_missing"}
            )
            continue
        try:
            size = candidate.stat().st_size
            if size > max_file_bytes:
                validation_errors.append(
                    {"path": relative_text, "reason": "file_size_limit_exceeded"}
                )
                continue
            raw = candidate.read_bytes()
        except OSError as error:
            validation_errors.append(
                {
                    "path": relative_text,
                    "reason": f"{type(error).__name__}: {error}",
                }
            )
            continue
        scanned_bytes += len(raw)
        text = raw.decode("utf-8", errors="replace")
        descriptors.append(
            {
                "path": relative_text,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        for probe in exact_secret_probes:
            if probe.value in text:
                secret_hits.append(
                    {
                        "path": relative_text,
                        "match_kind": "exact_value",
                        "probe": probe.name,
                    }
                )
        if _RAW_DATABASE_PATH_PATTERN.search(text) is not None:
            path_violations.append(
                {"path": relative_text, "reason": "raw_database_path_forbidden"}
            )
    return PublicEvidenceScanResult(
        scanned_file_count=len(descriptors),
        scanned_byte_count=scanned_bytes,
        file_descriptors=tuple(descriptors),
        secret_hits=tuple(secret_hits),
        path_hygiene_violations=tuple(path_violations),
        validation_errors=tuple(validation_errors),
    )


def write_final_publication_scan_report(
    *,
    evidence_root: Path,
    report_path: Path,
    exact_secret_probes: tuple[PublicEvidenceSecretProbe, ...],
    max_file_bytes: int = _DEFAULT_PUBLIC_SCAN_MAX_BYTES,
) -> None:
    """扫描最终public evidence tree并以独占创建方式写唯一scan report。

    调用方必须先落盘全部拟发布 evidence，包括 final completion/index。唯一允许
    不进入扫描 descriptors 的文件是本函数即将创建的 ``secret-scan.json``；该
    report 在调用时必须完全不存在。既有regular file、directory、broken/valid
    symlink都视为stale report并fail closed，禁止覆盖或二次扫描形成双真源。

    :param evidence_root: 已完整落盘的public evidence tree根目录。
    :param report_path: 待独占创建的 ``secret-scan.json`` 路径。
    :param exact_secret_probes: 实际secret值与有意义canary的内存probe。
    :param max_file_bytes: 单文件最大扫描bytes。
    :returns: ``None``；publication verdict只持久化在report中。
    :raises TypeError: 路径、probe tuple或limit类型非法时抛出。
    :raises ValueError: root/report边界、report名称或limit非法时抛出。
    :raises RunObservationError: report已存在、report parent非法或含symlink时抛出。
    :raises OSError: evidence枚举、文件读取或report写入失败时抛出。
    """

    if not isinstance(evidence_root, Path):
        raise TypeError("evidence_root must be Path")
    if not isinstance(report_path, Path):
        raise TypeError("report_path must be Path")
    if report_path.name != _FINAL_PUBLICATION_SCAN_REPORT_NAME:
        raise ValueError("report_path must name secret-scan.json")
    if ".." in report_path.parts:
        raise ValueError("report_path must not contain path traversal")
    if evidence_root.is_symlink():
        raise RunObservationError("evidence_root must not be symlink")
    root = evidence_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("evidence_root must be directory")
    absolute_report = report_path.absolute()
    try:
        relative_report = absolute_report.relative_to(root)
    except ValueError as error:
        raise ValueError("report_path must be inside evidence_root") from error
    resolved_report = report_path.resolve(strict=False)
    try:
        resolved_report.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "resolved report_path must be inside evidence_root"
        ) from error
    report_parent = absolute_report.parent
    path_cursor = root
    for part in relative_report.parts[:-1]:
        path_cursor = path_cursor / part
        if path_cursor.is_symlink():
            raise RunObservationError("report_path ancestor symlink is forbidden")
    if not report_parent.is_dir():
        raise RunObservationError("report_path parent must already exist")
    if absolute_report.exists() or absolute_report.is_symlink():
        raise RunObservationError(
            "final publication scan report must not already exist"
        )

    candidates = tuple(
        candidate
        for candidate in sorted(root.rglob("*"), key=lambda path: path.as_posix())
        if candidate.is_symlink() or not candidate.is_dir()
    )
    if absolute_report.exists() or absolute_report.is_symlink():
        raise RunObservationError(
            "final publication scan report appeared before scan"
        )
    result = scan_public_evidence_files(
        evidence_root=root,
        files=candidates,
        exact_secret_probes=exact_secret_probes,
        max_file_bytes=max_file_bytes,
    )
    serialized = json.dumps(
        result.to_json(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    try:
        with absolute_report.open("x", encoding="utf-8") as report_file:
            report_file.write(serialized)
    except FileExistsError as error:
        raise RunObservationError(
            "final publication scan report appeared before publication"
        ) from error


def classify_remaining_actions_for_safe_stop(
    actions: tuple[HarnessActionControl, ...],
) -> tuple[RemainingActionDecision, ...]:
    """依赖 stop/invalid 后分类所有 remaining actions，并只允许一次 EOT。

    dependent business action 一律 ``not_run``；显式 cleanup/EOT 中仅第一项允许
    发送，其余 action 因 process 即将关闭而记录 ``not_run``。这项纯决策不操作
    PTY，也不把 process exit 推导为 Run success。

    :param actions: 从当前 action 开始的剩余 typed controls。
    :returns: 与输入顺序 exact 对齐的处置 tuple。
    :raises TypeError: actions 或元素类型非法时抛出。
    :raises ValueError: action index 重复/倒序或缺少 cleanup/EOT 时抛出。
    """

    if not isinstance(actions, tuple):
        raise TypeError("actions must be tuple")
    decisions: list[RemainingActionDecision] = []
    previous_index = -1
    cleanup_selected = False
    for action in actions:
        if not isinstance(action, HarnessActionControl):
            raise TypeError("actions item must be HarnessActionControl")
        if action.action_index <= previous_index:
            raise ValueError("action indexes must be strictly increasing")
        previous_index = action.action_index
        if (
            action.role is HarnessActionRole.CLEANUP_EOT
            and not cleanup_selected
        ):
            disposition = RemainingActionDisposition.SEND_CLEANUP_EOT
            cleanup_selected = True
        elif action.role is HarnessActionRole.DEPENDENT:
            disposition = RemainingActionDisposition.NOT_RUN_DEPENDENT
        else:
            disposition = RemainingActionDisposition.NOT_RUN_PROCESS_STOP
        decisions.append(
            RemainingActionDecision(
                action_index=action.action_index,
                disposition=disposition,
                required_success_accepted_ordinal=(
                    action.required_success_accepted_ordinal
                ),
            )
        )
    if not cleanup_selected:
        raise ValueError("remaining actions must include explicit cleanup/EOT")
    return tuple(decisions)


def _read_filtered_window(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    window: RunObservationWindow,
    page_size: int,
) -> tuple[EventLogRow, ...]:
    """在同一 read transaction 内用 filtered keyset 读尽 frozen window。

    :param transaction: Host read transaction。
    :param event_log: Host EventLog reader。
    :param window: frozen window。
    :param page_size: 单页 matching row 上限。
    :returns: 按真实 event sequence 排序的 matching rows。
    :raises RunObservationError: covered cursor 不前进、倒退或越界时抛出。
    """

    cursor = window.start_event_sequence
    rows: list[EventLogRow] = []
    while cursor < window.end_event_sequence:
        page = event_log.read_events_after_matching(
            transaction,
            cursor,
            event_filter=_RUN_EVENT_FILTER,
            limit=page_size,
            max_event_sequence=window.end_event_sequence,
            session_id=window.session_id,
        )
        if page.covered_event_sequence <= cursor:
            raise RunObservationError(
                "filtered EventLog window did not reach frozen end"
            )
        if page.covered_event_sequence > window.end_event_sequence:
            raise RunObservationError("filtered EventLog window exceeded frozen end")
        for row in page.rows:
            if not (cursor < row.event_sequence <= window.end_event_sequence):
                raise RunObservationError("filtered EventLog row escaped keyset page")
            rows.append(row)
        cursor = page.covered_event_sequence
    return tuple(rows)


def _project_terminal_rows(
    rows: tuple[EventLogRow, ...],
    *,
    window: RunObservationWindow,
    roles_by_accepted_ordinal: Mapping[int, RunObservationRole],
    accepted_ordinal_offset: int,
) -> RunTerminalObservationSet:
    """把 filtered rows 投影为 accepted Run 与唯一 terminal facts。

    :param rows: frozen window 内的 matching canonical rows。
    :param window: observation window。
    :param roles_by_accepted_ordinal: 每个累计 ordinal 的显式 role。
    :param accepted_ordinal_offset: segment 前累计 accepted 数。
    :returns: 严格完整的 terminal set。
    :raises RunObservationError: accepted/terminal 归属、数量或 role 非法时抛出。
    """

    accepted_rows: list[EventLogRow] = []
    terminals_by_run: dict[str, list[EventLogRow]] = {}
    accepted_run_ids: set[str] = set()
    for row in rows:
        if row.event_type == HostRunEventType.RUN_ACCEPTED.value:
            run_id = _required_run_id(row)
            if run_id in accepted_run_ids:
                raise RunObservationError("Run has duplicate RUN_ACCEPTED facts")
            accepted_run_ids.add(run_id)
            accepted_rows.append(row)
            continue
        terminal_type = _terminal_event_type(row.event_type)
        if terminal_type is None:
            raise RunObservationError("filtered row is not a configured Run event")
        run_id = _required_run_id(row)
        terminals_by_run.setdefault(run_id, []).append(row)
    if set(terminals_by_run).difference(accepted_run_ids):
        raise RunObservationError("terminal fact has no RUN_ACCEPTED in window")
    observations: list[RunTerminalObservation] = []
    expected_role_ordinals: set[int] = set()
    for local_ordinal, accepted in enumerate(accepted_rows, start=1):
        accepted_ordinal = accepted_ordinal_offset + local_ordinal
        expected_role_ordinals.add(accepted_ordinal)
        role = roles_by_accepted_ordinal.get(accepted_ordinal)
        if not isinstance(role, RunObservationRole):
            raise RunObservationError("accepted Run role is missing or invalid")
        run_id = _required_run_id(accepted)
        terminal_rows = terminals_by_run.get(run_id, [])
        if len(terminal_rows) == 0:
            raise RunObservationError("accepted Run has no terminal in frozen window")
        if len(terminal_rows) > 1:
            raise RunObservationError("accepted Run has duplicate terminal facts")
        terminal = terminal_rows[0]
        if terminal.session_id != accepted.session_id:
            raise RunObservationError(
                "Run terminal session_id does not match RUN_ACCEPTED"
            )
        terminal_type = _terminal_event_type(terminal.event_type)
        if terminal_type is None:
            raise RunObservationError("terminal type is invalid")
        if terminal.event_sequence <= accepted.event_sequence:
            raise RunObservationError("Run terminal does not follow RUN_ACCEPTED")
        observations.append(
            RunTerminalObservation(
                accepted_ordinal=accepted_ordinal,
                role=role,
                session_id=accepted.session_id,
                run_id=run_id,
                accepted_event_id=accepted.event_id,
                accepted_event_sequence=accepted.event_sequence,
                terminal_event_type=terminal_type,
                terminal_event_id=terminal.event_id,
                terminal_event_sequence=terminal.event_sequence,
                terminal_class=_terminal_status(terminal_type),
                reason=_terminal_reason(terminal, terminal_type=terminal_type),
                public_outbox_terminal=is_public_outbox_terminal_item_event(
                    terminal.event_type
                ),
            )
        )
    if set(roles_by_accepted_ordinal) != expected_role_ordinals:
        raise RunObservationError("roles do not exactly match accepted ordinals")
    return RunTerminalObservationSet(window=window, runs=tuple(observations))


def _required_run_id(row: EventLogRow) -> str:
    """读取 canonical Run identity。

    :param row: EventLog row。
    :returns: 非空 run id。
    :raises RunObservationError: run id 缺失或为空时抛出。
    """

    if row.run_id is None or row.run_id.strip() == "":
        raise RunObservationError("Run lifecycle fact is missing run_id")
    return row.run_id


def _terminal_event_type(event_type: str) -> HostRunEventType | None:
    """把 shared Host terminal type 字符串解析为 enum。

    :param event_type: EventLog event type。
    :returns: terminal enum；非 terminal 时返回 ``None``。
    """

    for terminal_type in HOST_RUN_TERMINAL_EVENT_TYPES:
        if event_type == terminal_type.value:
            return terminal_type
    return None


def _terminal_status(terminal_type: HostRunEventType) -> RunStatus:
    """通过 lifecycle owner 投影 shared Host terminal type。

    :param terminal_type: shared Host terminal enum。
    :returns: lifecycle owner 返回的 durable terminal status。
    :raises RunObservationError: 非 terminal enum 时抛出。
    """

    status = run_status_for_terminal_event(terminal_type.value)
    if status is None:
        raise RunObservationError("Host Run event type is not terminal")
    return status


def _terminal_reason(
    row: EventLogRow,
    *,
    terminal_type: HostRunEventType,
) -> str:
    """按 terminal-specific canonical shape 读取 ``reason_json.reason``。

    :param row: terminal EventLog row。
    :param terminal_type: shared Host Run terminal type。
    :returns: canonical reason string，不读取 payload fallback。
    :raises RunObservationError: JSON malformed 或 event-specific shape 非法时抛出。
    """

    if row.reason_json is None:
        raise RunObservationError("terminal reason_json is missing")
    try:
        decoded = cast(JsonValue, json.loads(row.reason_json))
    except json.JSONDecodeError as exc:
        raise RunObservationError("terminal reason_json is malformed") from exc
    if not isinstance(decoded, dict):
        raise RunObservationError("terminal reason_json must be object")
    keys = set(decoded)
    if terminal_type is HostRunEventType.RUN_CANCELLED:
        if keys not in ({_REASON_KEY}, {_REASON_KEY, "mode"}):
            raise RunObservationError(
                "RUN_CANCELLED reason_json has unknown canonical keys"
            )
        if "mode" in decoded:
            mode = decoded["mode"]
            if not isinstance(mode, str) or mode not in {
                item.value for item in CancelMode
            }:
                raise RunObservationError(
                    "RUN_CANCELLED reason_json mode is invalid"
                )
    elif terminal_type is HostRunEventType.RUN_LOST:
        if keys not in ({_REASON_KEY}, {_REASON_KEY, "orphan_proof"}):
            raise RunObservationError(
                "RUN_LOST reason_json has unknown canonical keys"
            )
        if "orphan_proof" in decoded:
            orphan_proof = decoded["orphan_proof"]
            if (
                not isinstance(orphan_proof, str)
                or orphan_proof.strip() == ""
            ):
                raise RunObservationError(
                    "RUN_LOST reason_json orphan_proof is invalid"
                )
    elif keys != {_REASON_KEY}:
        raise RunObservationError(
            "terminal reason_json must contain exact reason key"
        )
    reason = decoded[_REASON_KEY]
    if not isinstance(reason, str) or reason.strip() == "":
        raise RunObservationError("terminal reason must be non-empty string")
    return reason


def _require_positive_int(value: int, *, field_name: str) -> None:
    """校验严格正整数参数。

    :param value: 待校验数值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 数值不是 int 或为 bool 时抛出。
    :raises ValueError: 数值非正时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


__all__ = [
    "DependencyGateStatus",
    "HarnessActionControl",
    "HarnessActionRole",
    "PublicEvidenceScanResult",
    "PublicEvidenceSecretProbe",
    "RemainingActionDecision",
    "RemainingActionDisposition",
    "RunDependencyDecision",
    "RunEvidenceStatus",
    "RunObservationError",
    "RunObservationRole",
    "RunObservationWindow",
    "RunTerminalObservation",
    "RunTerminalObservationSet",
    "classify_remaining_actions_for_safe_stop",
    "classify_required_run_evidence",
    "dependent_action_accepted_ordinal",
    "evaluate_success_dependency",
    "observe_run_terminals",
    "run_observation_role_for_harness_action",
    "scan_public_evidence_files",
    "validate_terminal_class_summary",
    "write_final_publication_scan_report",
]
