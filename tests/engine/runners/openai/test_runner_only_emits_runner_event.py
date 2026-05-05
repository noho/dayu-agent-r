"""Runner 子树**只**产出 :class:`RunnerEvent` 的 AST 守卫测试。

按 ``docs/code_review.md`` §6 与 ``docs/engine/phase1-plan.md`` §2 / §6.4：
Runner 不得越界实现 Agent 多轮 loop，不得把取消 / 失败 / 最终回答提升
为 Host 可见终态。具体表现为 Runner 子树**不**产出 :class:`EngineEvent`、
不引用 ``FinalAnswerData`` / ``RunCancelledData`` / ``RunFailedData`` /
``RunSuspendedData`` / ``IterationStartedData`` / ``EngineRunOutcome*``
等 Engine / Agent 状态机概念。

本测试通过 AST 扫描 ``dayu/engine/runners/`` 子树的 import 与名字使用，
锁住该边界。
"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.engine.runners as runners_pkg

# 禁止 import 的模块
FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "dayu.engine.contracts.engine_events",
    "dayu.engine.contracts.agent_run",
    "dayu.engine.contracts.agent_policy",
)

# 禁止以名字方式引用的 Engine / Agent 状态机概念
FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {
        "EngineEvent",
        "EngineEventData",
        "EngineEventType",
        "EngineRunOutcomeFinalAnswer",
        "EngineRunOutcomeCancelled",
        "EngineRunOutcomeFailed",
        "EngineRunOutcomeSuspended",
        "FinalAnswerData",
        "RunCancelledData",
        "RunFailedData",
        "RunSuspendedData",
        "IterationStartedData",
        "AgentRunRequest",
        "AgentRunResult",
        "AgentPolicy",
        "ContentCompleteData",
        "ContentDeltaData",
        "ReasoningDeltaData",
        "ToolCallRequestedData",
        "ToolResultAcceptedData",
        "RunResumeHint",
    }
)


def _runners_root() -> Path:
    """返回 ``dayu/engine/runners/`` 的源码根目录路径。"""

    pkg_file = runners_pkg.__file__
    assert pkg_file is not None
    return Path(pkg_file).resolve().parent


def _iter_python_files() -> list[Path]:
    """递归收集 runners 子树下所有 ``.py`` 文件。"""

    root = _runners_root()
    return sorted(
        p for p in root.rglob("*.py") if "__pycache__" not in p.parts
    )


def _violations_in_file(path: Path) -> list[str]:
    """收集单文件违规列表。

    :param path: ``.py`` 文件路径。
    :returns: 违规说明列表。
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in FORBIDDEN_IMPORT_PREFIXES:
                if module == prefix or module.startswith(prefix + "."):
                    violations.append(
                        f"{path}:{node.lineno} import from {module!r}"
                    )
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    violations.append(
                        f"{path}:{node.lineno} import name {alias.name!r}"
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                for prefix in FORBIDDEN_IMPORT_PREFIXES:
                    if module == prefix or module.startswith(prefix + "."):
                        violations.append(
                            f"{path}:{node.lineno} import {module!r}"
                        )
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                violations.append(
                    f"{path}:{node.lineno} reference to {node.id!r}"
                )
        elif isinstance(node, ast.Attribute):
            # ``something.EngineEvent`` 形式
            if node.attr in FORBIDDEN_NAMES:
                violations.append(
                    f"{path}:{node.lineno} attribute access .{node.attr}"
                )
    return violations


def test_runner_subtree_does_not_reference_engine_events() -> None:
    """Runner 子树不得 import / 引用 :class:`EngineEvent` 与 Agent 状态机类型。"""

    all_violations: list[str] = []
    for path in _iter_python_files():
        all_violations.extend(_violations_in_file(path))
    assert not all_violations, (
        "Runner subtree must only emit RunnerEvent; found references to "
        "Engine/Agent state-machine types:\n" + "\n".join(all_violations)
    )
