"""dayu-cli init 的交互式 workspace 初始化 orchestrator。

本模块只拥有请求路径、RESET 确认、fresh-root bootstrap、init lock、交互
选择、环境持久化编排与用户输出。Managed-root transaction 由
dayu.cli.init_workspace 唯一拥有；配置 schema 与 Fins provider classification
分别留在 ConfigLoader 与 Service owner。
"""

from __future__ import annotations

import getpass
import importlib
import os
import platform
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dayu.cli.arg_parsing import ParsedCliArgs
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.cli.init_catalog import (
    INIT_MODEL_CHOICES,
    CustomOpenAIModelSettings,
    InitCatalogError,
    InitModelChoice,
    InitModelChoiceKind,
    InitModelSelection,
    OllamaModelSettings,
    find_init_model_choice,
    ollama_template_defaults,
    validate_init_catalog,
)
from dayu.cli.init_environment import (
    OPTIONAL_ENVIRONMENT_NAMES,
    EnvironmentPersistenceEntry,
    EnvironmentPersistenceError,
    EnvironmentPersistenceInterrupted,
    EnvironmentPersistencePlan,
    EnvironmentPersistenceResult,
    PosixEnvironmentPersistencePlan,
    WindowsEnvironmentPersistencePlan,
    has_non_empty_environment_value,
    persist_environment,
    plan_environment_persistence,
)
from dayu.cli.init_workspace import (
    InitMode,
    InitWorkspaceError,
    PreparedWorkspaceTransaction,
    WorkspaceSnapshot,
    WorkspaceTransactionRequest,
    abort_prepared_workspace_transaction,
    determine_init_mode,
    prepare_workspace_transaction,
    publish_workspace_transaction,
    snapshot_managed_roots,
)
from dayu.runtime.filelock import RuntimeFileLockError, file_lock

_BASE_OPTION: Final[str] = "--base"
_PACKAGE_CONFIG_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "config"
_PACKAGE_MANIFEST_ROOT: Final[Path] = _PACKAGE_CONFIG_ROOT / "prompts" / "manifests"
_INIT_LOCK_NAME: Final[str] = ".dayu-init.lock"
_DEFAULT_CONFIRM: Final[str] = "n"
_AFFIRMATIVE_ANSWERS: Final[frozenset[str]] = frozenset({"y", "yes"})
_NEGATIVE_ANSWERS: Final[frozenset[str]] = frozenset({"", "n", "no"})
_DEFAULT_OLLAMA_MODEL_NAME: Final[str] = "qwen3:8b"
_DEFAULT_CUSTOM_ENDPOINT: Final[str] = "https://api.example.com/v1/chat/completions"
_DEFAULT_CONTEXT_WINDOW: Final[int] = 131072
_PREWARM_IMPORT_ROOTS: Final[tuple[str, ...]] = (
    "dayu.cli.commands.interactive",
    "dayu.cli.commands.prompt",
)
_PREWARM_FAILURE_SUMMARY: Final[str] = (
    "entry-module import did not complete; normal command import remains available"
)


class CliInitUsageError(ValueError):
    """Init 命令的请求路径或显式输入不合法。"""


class CliInitOperationError(RuntimeError):
    """Init 命令在 owner contract 内无法完成。"""


@dataclass(frozen=True, slots=True)
class _WorkspaceRootIdentity:
    """Orchestrator 记录的 workspace root identity。

    :param canonical_path: resolved absolute path。
    :param device: st_dev。
    :param inode: st_ino。
    :param mode: st_mode。
    """

    canonical_path: Path
    device: int
    inode: int
    mode: int


def run_init_command(args: ParsedCliArgs) -> int:
    """执行 dayu-cli init。

    :param args: argparse 已解析的 init 参数。
    :returns: CLI 退出码。
    :raises OSError: stdout/stderr 写入失败时由 print 透传。
    """

    try:
        requested_workspace = _resolve_workspace_root(args.workspace_root)
        _validate_requested_workspace_path(requested_workspace)
        platform_system = platform.system()
        unlocked_snapshot = snapshot_managed_roots(
            requested_workspace,
            platform_system=platform_system,
        )
        requested_mode = determine_init_mode(
            unlocked_snapshot,
            reset=args.reset,
            overwrite=args.overwrite,
        )
        if requested_mode is InitMode.RESET and not _confirm_reset(unlocked_snapshot):
            print("dayu-cli init: reset cancelled; workspace unchanged")
            return EXIT_SUCCESS
        workspace_identity = _bootstrap_workspace_root(requested_workspace)
        lock_path = workspace_identity.canonical_path / _INIT_LOCK_NAME
        _validate_lock_path(lock_path, allow_absent=True)
        print(
            f"dayu-cli init: 正在等待此 workspace lock: workspace={workspace_identity.canonical_path} lock={lock_path}"
        )
        with file_lock(
            lock_path,
            timeout_seconds=None,
            create_parent_dirs=False,
        ):
            _require_workspace_identity(workspace_identity)
            _validate_lock_path(lock_path, allow_absent=False)
            locked_snapshot = snapshot_managed_roots(
                workspace_identity.canonical_path,
                platform_system=platform_system,
            )
            locked_mode = determine_init_mode(
                locked_snapshot,
                reset=args.reset,
                overwrite=args.overwrite,
            )
            _require_confirmed_snapshot(
                unlocked_snapshot=unlocked_snapshot,
                locked_snapshot=locked_snapshot,
                requested_mode=requested_mode,
                locked_mode=locked_mode,
            )
            selection = _select_model()
            persistence_plan = _collect_environment_persistence_plan(selection)
            prepared = prepare_workspace_transaction(
                WorkspaceTransactionRequest(
                    workspace_root=workspace_identity.canonical_path,
                    package_config_root=_PACKAGE_CONFIG_ROOT,
                    mode=locked_mode,
                    selection=selection,
                    expected_snapshot=locked_snapshot,
                    platform_system=platform_system,
                )
            )
            try:
                persistence_result = _persist_environment_if_needed(persistence_plan)
            except EnvironmentPersistenceInterrupted as exc:
                abort_error = _try_abort_prepared_transaction(prepared)
                _report_persisted_environment_names(exc.result)
                _report_retained_environment_paths(exc.result.retained_paths)
                _report_abort_failure(abort_error)
                raise
            except KeyboardInterrupt:
                abort_error = _try_abort_prepared_transaction(prepared)
                _report_abort_failure(abort_error)
                raise
            except EnvironmentPersistenceError as exc:
                abort_error = _try_abort_prepared_transaction(prepared)
                _report_retained_environment_paths(exc.retained_paths)
                _report_abort_failure(abort_error)
                raise
            except OSError:
                abort_error = _try_abort_prepared_transaction(prepared)
                _report_abort_failure(abort_error)
                raise
            if persistence_result is not None and not persistence_result.succeeded:
                abort_error = _try_abort_prepared_transaction(prepared)
                _report_persisted_environment_names(persistence_result)
                _report_retained_environment_paths(persistence_result.retained_paths)
                _report_abort_failure(abort_error)
                raise CliInitOperationError(_environment_failure_message(persistence_result))
            try:
                result = publish_workspace_transaction(prepared)
            except (InitWorkspaceError, KeyboardInterrupt):
                _report_persisted_environment_names(persistence_result)
                raise
        if result.mode is InitMode.FIRST or result.mode is InitMode.RESET:
            _run_init_prewarm()
        print(f"dayu-cli init: initialized workspace config mode={result.mode.value} at {result.config_root}")
        for warning in result.warnings:
            print(
                "dayu-cli init: cleanup warning "
                f"stage={warning.stage} path={warning.path} "
                f"path_exists={warning.path_exists} "
                f"partial_deletion={warning.partial_deletion} "
                "deletion_durability_unconfirmed="
                f"{warning.deletion_durability_unconfirmed} "
                f"error_type={warning.error_type}",
                file=sys.stderr,
            )
        return EXIT_SUCCESS
    except CliInitUsageError as exc:
        print(f"dayu-cli init: workspace path is invalid: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except (
        CliInitOperationError,
        InitCatalogError,
        EnvironmentPersistenceError,
        InitWorkspaceError,
        RuntimeFileLockError,
    ) as exc:
        print(_format_operation_error(exc), file=sys.stderr)
        return EXIT_FAILURE
    except OSError as exc:
        print(
            f"dayu-cli init: filesystem operation failed: {exc.__class__.__name__}",
            file=sys.stderr,
        )
        return EXIT_FAILURE


def _resolve_workspace_root(raw_value: str) -> Path:
    """解析 workspace 请求路径但不创建它。

    :param raw_value: --base/--workspace 原始值。
    :returns: expanded absolute non-strict resolved path。
    :raises CliInitUsageError: 输入为空时抛出。
    """

    stripped = raw_value.strip()
    if not stripped:
        raise CliInitUsageError(f"{_BASE_OPTION} must not be empty")
    expanded = Path(stripped).expanduser()
    return Path(os.path.abspath(expanded))


def _validate_requested_workspace_path(workspace_root: Path) -> None:
    """在 read-only snapshot 前分类用户请求路径。

    :param workspace_root: non-strict resolved request path。
    :returns: None。
    :raises CliInitUsageError: 已存在路径为 symlink 或非普通目录时抛出。
    :raises OSError: no-follow stat 失败时透传。
    """

    if workspace_root.is_symlink():
        raise CliInitUsageError("workspace root must not be a symlink")
    if not workspace_root.exists():
        return
    path_stat = os.stat(workspace_root, follow_symlinks=False)
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISDIR(path_stat.st_mode):
        raise CliInitUsageError("workspace root must be an ordinary directory")


def _bootstrap_workspace_root(workspace_root: Path) -> _WorkspaceRootIdentity:
    """显式创建 fresh workspace root 并立即锁定 identity。

    :param workspace_root: 请求的 canonical absolute path。
    :returns: 创建/复核后的 identity。
    :raises CliInitUsageError: symlink、非目录、创建失败或类型竞争时抛出。
    """

    if workspace_root.is_symlink():
        raise CliInitUsageError("workspace root must not be a symlink")
    try:
        workspace_root.mkdir(parents=True, exist_ok=True)
        path_stat = os.stat(workspace_root, follow_symlinks=False)
    except OSError as exc:
        raise CliInitUsageError(exc.__class__.__name__) from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISDIR(path_stat.st_mode):
        raise CliInitUsageError("workspace root must be an ordinary directory")
    canonical = workspace_root.resolve(strict=True)
    return _WorkspaceRootIdentity(
        canonical_path=canonical,
        device=path_stat.st_dev,
        inode=path_stat.st_ino,
        mode=path_stat.st_mode,
    )


def _require_workspace_identity(identity: _WorkspaceRootIdentity) -> None:
    """获锁后复核 workspace root identity 未漂移。

    :param identity: bootstrap 后记录的 identity。
    :returns: None。
    :raises CliInitUsageError: root identity/type/resolved path 漂移时抛出。
    """

    path_stat = os.stat(identity.canonical_path, follow_symlinks=False)
    current = _WorkspaceRootIdentity(
        canonical_path=identity.canonical_path.resolve(strict=True),
        device=path_stat.st_dev,
        inode=path_stat.st_ino,
        mode=path_stat.st_mode,
    )
    if current != identity or not stat.S_ISDIR(current.mode):
        raise CliInitUsageError("workspace root identity changed while waiting")


def _validate_lock_path(lock_path: Path, *, allow_absent: bool) -> None:
    """校验 init lock path 为 workspace 内普通非 symlink 文件。

    :param lock_path: 固定 workspace-local lock path。
    :param allow_absent: acquire 前是否允许路径不存在。
    :returns: None。
    :raises CliInitUsageError: lock 是 symlink、目录、special file 或缺失时抛出。
    """

    if not lock_path.exists():
        if lock_path.is_symlink():
            raise CliInitUsageError("init lock must not be a dangling symlink")
        if allow_absent:
            return
        raise CliInitUsageError("init lock file was not created")
    path_stat = os.stat(lock_path, follow_symlinks=False)
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise CliInitUsageError("init lock must be an ordinary file")


def _confirm_reset(snapshot: WorkspaceSnapshot) -> bool:
    """显示 active-process 警告和实际 targets 后默认 No 确认 RESET。

    :param snapshot: unlocked managed-root snapshot。
    :returns: 只有用户显式回答 Yes 时返回 True。
    :raises CliInitUsageError: 输入不是明确 yes/no 时抛出。
    :raises KeyboardInterrupt: 用户中断时透传。
    """

    existing_targets = tuple(root.path for root in snapshot.roots if root.exists)
    print(
        "dayu-cli init: RESET 警告：.dayu-init.lock 只串行 init；"
        "请先停止此 workspace 的 active Dayu CLI/Web/WeChat/Host 进程。"
    )
    if existing_targets:
        print("dayu-cli init: RESET targets:")
        for target in existing_targets:
            print(f"  - {target}")
    else:
        print("dayu-cli init: RESET targets: none")
    return _confirm("确认 RESET? [y/N]: ")


def _require_confirmed_snapshot(
    *,
    unlocked_snapshot: WorkspaceSnapshot,
    locked_snapshot: WorkspaceSnapshot,
    requested_mode: InitMode,
    locked_mode: InitMode,
) -> None:
    """锁内拒绝确认后发生的 managed-root TOCTOU 漂移。

    :param unlocked_snapshot: bootstrap/lock 前展示依据。
    :param locked_snapshot: 获锁后重新读取的 snapshot。
    :param requested_mode: 解锁阶段模式。
    :param locked_mode: 锁内模式。
    :returns: None。
    :raises CliInitOperationError: RESET snapshot 或任一模式发生漂移时抛出。
    """

    if requested_mode is not locked_mode:
        raise CliInitOperationError("init mode changed while acquiring lock; rerun")
    if requested_mode is InitMode.RESET and unlocked_snapshot.roots != locked_snapshot.roots:
        raise CliInitOperationError("RESET target snapshot changed after confirmation; rerun")


def _select_model() -> InitModelSelection:
    """校验 package catalog 并收集一个明确 model pair。

    :returns: 类型化模型选择。
    :raises CliInitOperationError: 用户取消或选择输入非法时抛出。
    :raises InitCatalogError: package catalog/dynamic 输入漂移时抛出。
    """

    models = validate_init_catalog(
        _PACKAGE_CONFIG_ROOT,
        _PACKAGE_MANIFEST_ROOT,
    )
    print("dayu-cli init: 请选择普通/思考模型组合：")
    for index, choice in enumerate(INIT_MODEL_CHOICES, start=1):
        print(f"  {index}. {choice.display_name}")
    raw_choice = _read_input("模型组合编号或 choice id: ").strip()
    choice = _parse_model_choice(raw_choice)
    if choice.kind is InitModelChoiceKind.OLLAMA:
        defaults = ollama_template_defaults(models)
        model_name = _read_non_empty_input(
            f"Ollama model [{_DEFAULT_OLLAMA_MODEL_NAME}]: ",
            default=_DEFAULT_OLLAMA_MODEL_NAME,
        )
        endpoint = _read_non_empty_input(
            f"Ollama endpoint [{defaults.endpoint}]: ",
            default=defaults.endpoint,
        )
        context_window = _read_positive_integer(
            f"Ollama context window [{defaults.context_window_tokens}]: ",
            default=defaults.context_window_tokens,
        )
        return InitModelSelection(
            choice=choice,
            dynamic_settings=OllamaModelSettings(
                model_name=model_name,
                endpoint=endpoint,
                context_window_tokens=context_window,
            ),
        )
    if choice.kind is InitModelChoiceKind.CUSTOM_OPENAI:
        model_name = _read_non_empty_input("Custom model name: ", default=None)
        endpoint = _read_non_empty_input(
            f"Custom endpoint [{_DEFAULT_CUSTOM_ENDPOINT}]: ",
            default=_DEFAULT_CUSTOM_ENDPOINT,
        )
        context_window = _read_positive_integer(
            f"Custom context window [{_DEFAULT_CONTEXT_WINDOW}]: ",
            default=_DEFAULT_CONTEXT_WINDOW,
        )
        return InitModelSelection(
            choice=choice,
            dynamic_settings=CustomOpenAIModelSettings(
                model_name=model_name,
                endpoint=endpoint,
                context_window_tokens=context_window,
            ),
        )
    return InitModelSelection(choice=choice)


def _parse_model_choice(raw_choice: str) -> InitModelChoice:
    """把明确编号或 stable id 映射到 catalog entry。

    :param raw_choice: 用户输入。
    :returns: catalog 中唯一 entry。
    :raises CliInitOperationError: 输入为空、越界或未知时抛出。
    """

    if not raw_choice:
        raise CliInitOperationError("model choice is required")
    if raw_choice.isdecimal():
        index = int(raw_choice)
        if 1 <= index <= len(INIT_MODEL_CHOICES):
            return INIT_MODEL_CHOICES[index - 1]
        raise CliInitOperationError("model choice number is out of range")
    try:
        return find_init_model_choice(raw_choice)
    except InitCatalogError as exc:
        raise CliInitOperationError(str(exc)) from exc


def _collect_environment_persistence_plan(
    selection: InitModelSelection,
) -> EnvironmentPersistencePlan | None:
    """收集缺失 required secret 与固定 optional integrations。

    :param selection: 已完成的 model selection。
    :returns: 无新值时为 None；否则为用户最终确认的 typed plan。
    :raises CliInitOperationError: required 值缺失或用户拒绝批次时抛出。
    :raises EnvironmentPersistenceError: 值或平台/shell contract 非法时抛出。
    """

    entries: list[EnvironmentPersistenceEntry] = []
    required_name = selection.choice.required_secret_env_name
    if required_name is not None and not has_non_empty_environment_value(required_name, os.environ):
        required_value = getpass.getpass(f"{required_name}（输入隐藏，不写日志）: ")
        if not required_value:
            raise CliInitOperationError(f"required environment value was not provided: {required_name}")
        entries.append(
            EnvironmentPersistenceEntry(
                name=required_name,
                value=required_value,
            )
        )
    for optional_name in OPTIONAL_ENVIRONMENT_NAMES:
        if has_non_empty_environment_value(optional_name, os.environ):
            continue
        optional_value = getpass.getpass(f"可选 {optional_name}（留空跳过，输入隐藏）: ")
        if optional_value:
            entries.append(
                EnvironmentPersistenceEntry(
                    name=optional_name,
                    value=optional_value,
                )
            )
    if not entries:
        return None
    unconfirmed_plan = _build_environment_plan(
        entries=tuple(entries),
        confirmed=False,
    )
    names = ", ".join(entry.name for entry in entries)
    print(
        "dayu-cli init: 将持久化以下环境变量名（不显示值）: "
        f"target={_persistence_target(unconfirmed_plan)} names={names}"
    )
    if not _confirm("确认持久化这一批环境变量? [y/N]: "):
        raise CliInitOperationError("environment persistence was not confirmed; workspace unchanged")
    return _build_environment_plan(entries=tuple(entries), confirmed=True)


def _build_environment_plan(
    *,
    entries: tuple[EnvironmentPersistenceEntry, ...],
    confirmed: bool,
) -> EnvironmentPersistencePlan:
    """从当前 OS 明确输入构造 S1 owner 的 typed persistence plan。

    :param entries: 新环境值批次。
    :param confirmed: 用户是否最终确认。
    :returns: POSIX 单 profile 或 Windows setx plan。
    :raises EnvironmentPersistenceError: 平台/shell/home 不受支持时抛出。
    """

    return plan_environment_persistence(
        entries=entries,
        platform_system=platform.system(),
        home_directory=Path.home(),
        shell_path=os.environ.get("SHELL", ""),
        confirmed=confirmed,
    )


def _persistence_target(plan: EnvironmentPersistencePlan) -> str:
    """从 typed plan 投影安全 target，不重建平台规则。

    :param plan: S1 owner 已校验的 plan。
    :returns: POSIX profile path 或 Windows setx。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(plan, PosixEnvironmentPersistencePlan):
        return str(plan.profile_path)
    if isinstance(plan, WindowsEnvironmentPersistencePlan):
        return "setx"
    raise AssertionError("unreachable environment persistence plan")


def _persist_environment_if_needed(
    plan: EnvironmentPersistencePlan | None,
) -> EnvironmentPersistenceResult | None:
    """在 staging validation 成功后执行已确认 persistence。

    :param plan: 可空 typed plan。
    :returns: 无计划为 None；否则返回脱敏结果。
    :raises EnvironmentPersistenceError: POSIX/plan owner 失败时透传。
    """

    if plan is None:
        return None
    return persist_environment(plan)


def _environment_failure_message(result: EnvironmentPersistenceResult) -> str:
    """把 Windows partial failure 投影为仅含 names 的安全错误。

    :param result: S1 owner 的脱敏失败结果。
    :returns: 不含 values/captured output 的错误文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        "environment persistence failed; "
        f"written_names={','.join(result.written_names)} "
        f"unwritten_names={','.join(result.unwritten_names)}"
    )


def _report_persisted_environment_names(
    result: EnvironmentPersistenceResult | None,
) -> None:
    """Workspace publication 失败时如实报告已写 OS store 的变量名。

    :param result: 可空 persistence result。
    :returns: None。
    :raises Exception: diagnostic I/O 失败由 owner-local best-effort 边界吸收。
    """

    if result is None or not result.written_names:
        return
    _report_diagnostic_best_effort(
        "dayu-cli init: workspace 未发布；环境变量已持久化且不能自动回滚: "
        f"written_names={','.join(result.written_names)}"
    )


def _report_retained_environment_paths(retained_paths: tuple[Path, ...]) -> None:
    """Best-effort 投影环境 owner 的 retained-path 真值。

    :param retained_paths: 仍存在或无法确认已清理的私有临时路径。
    :returns: ``None``。
    :raises Exception: diagnostic I/O 失败由 owner-local best-effort 边界吸收。
    """

    if not retained_paths:
        return
    _report_diagnostic_best_effort(
        "dayu-cli init: 环境持久化临时路径仍存在或无法确认清理: "
        f"retained={','.join(str(path) for path in retained_paths)}"
    )


def _try_abort_prepared_transaction(
    prepared: PreparedWorkspaceTransaction,
) -> InitWorkspaceError | None:
    """在任何 diagnostic I/O 前尝试 identity-safe abort prepared transaction。

    :param prepared: persistence 前已完成真实 staging/validation 的 transaction。
    :returns: abort 成功为 ``None``；失败返回既有 typed retained truth。
    :raises Exception: 只吸收 ``InitWorkspaceError``，其它实现错误仍传播。
    """

    try:
        abort_prepared_workspace_transaction(prepared)
    except InitWorkspaceError as exc:
        return exc
    return None


def _report_abort_failure(abort_error: InitWorkspaceError | None) -> None:
    """Best-effort 投影 abort 失败的 retained/public truth。

    :param abort_error: 可空 typed workspace abort error。
    :returns: ``None``。
    :raises Exception: diagnostic I/O 失败由 owner-local best-effort 边界吸收。
    """

    if abort_error is None:
        return
    _report_diagnostic_best_effort(_format_operation_error(abort_error))


def _report_diagnostic_best_effort(message: str) -> None:
    """输出不得覆盖已确定的 transaction/interrupt 控制流。

    :param message: 已由 owner 格式化且不含 secret value 的诊断。
    :returns: ``None``。
    :raises Exception: 所有普通 diagnostic I/O 错误均被吸收。
    """

    try:
        print(message, file=sys.stderr)
    except Exception:
        return


def _run_init_prewarm() -> None:
    """按固定顺序仅导入两个真实 CLI 用户入口。

    :returns: ``None``。
    :raises Exception: 普通导入失败会转成脱敏 warning；控制流异常仍透传。
    """

    try:
        for module_name in _PREWARM_IMPORT_ROOTS:
            importlib.import_module(module_name)
    except Exception as exc:
        _report_diagnostic_best_effort(
            "dayu-cli init: prewarm warning "
            f"error_type={exc.__class__.__name__} "
            f"summary={_PREWARM_FAILURE_SUMMARY}"
        )


def _confirm(prompt: str) -> bool:
    """读取默认 No 的明确 yes/no。

    :param prompt: 用户可见提示。
    :returns: 显式 yes 为 True；No/空/EOF 为 False。
    :raises CliInitUsageError: 其它输入无法解释时抛出。
    :raises KeyboardInterrupt: 用户中断时透传。
    """

    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        answer = _DEFAULT_CONFIRM
    if answer in _AFFIRMATIVE_ANSWERS:
        return True
    if answer in _NEGATIVE_ANSWERS:
        return False
    raise CliInitUsageError("confirmation must be yes or no")


def _read_input(prompt: str) -> str:
    """读取必需交互输入并把 EOF 收敛为取消。

    :param prompt: 用户可见提示。
    :returns: 原始输入。
    :raises CliInitOperationError: EOF 时抛出。
    :raises KeyboardInterrupt: 用户中断时透传。
    """

    try:
        return input(prompt)
    except EOFError as exc:
        raise CliInitOperationError("interactive input ended before selection") from exc


def _read_non_empty_input(prompt: str, *, default: str | None) -> str:
    """读取非空文本，可显式采用给定 default。

    :param prompt: 用户可见提示。
    :param default: 空输入采用的默认值；None 表示空输入非法。
    :returns: 非空文本。
    :raises CliInitOperationError: 输入为空且无默认值时抛出。
    """

    value = _read_input(prompt).strip()
    if value:
        return value
    if default is not None:
        return default
    raise CliInitOperationError("a non-empty value is required")


def _read_positive_integer(prompt: str, *, default: int) -> int:
    """读取严格正整数，可采用显式 default。

    :param prompt: 用户可见提示。
    :param default: 空输入采用的正整数。
    :returns: 正整数。
    :raises CliInitOperationError: 输入不是正整数时抛出。
    """

    raw_value = _read_input(prompt).strip()
    if not raw_value:
        return default
    if not raw_value.isdecimal() or int(raw_value) <= 0:
        raise CliInitOperationError("context window must be a positive integer")
    return int(raw_value)


def _format_operation_error(exc: Exception) -> str:
    """格式化不含 secret 的 init operation diagnostic。

    :param exc: 已知 owner exception。
    :returns: 用户可见安全文本。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(exc, InitWorkspaceError):
        retained = ",".join(str(path) for path in exc.retained_paths) or "none"
        public_truth = ",".join(exc.public_root_states) or "not-recorded"
        return (
            "dayu-cli init: workspace transaction failed "
            f"stage={exc.stage} error={exc} retained={retained} "
            f"public={public_truth} partial_deletion={exc.partial_deletion} "
            "deletion_durability_unconfirmed="
            f"{exc.deletion_durability_unconfirmed}"
        )
    return f"dayu-cli init: {exc}"


__all__: tuple[str, ...] = ("run_init_command",)
