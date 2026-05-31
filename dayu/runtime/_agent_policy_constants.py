"""层中立 Agent policy 常量。

本模块只保存 runtime 配置、scene manifest 与 assembly 共同使用的闭集
字面量，不导入 Engine / Host / Service，也不构造业务层对象。
"""

from __future__ import annotations

from typing import Final

AGENT_FALLBACK_MODE_FORCE_ANSWER: Final[str] = "force_answer"
"""Agent fallback 时要求模型基于已有信息直接回答。"""

AGENT_FALLBACK_MODE_RAISE_ERROR: Final[str] = "raise_error"
"""Agent fallback 时要求直接返回错误。"""

AGENT_FALLBACK_MODES: Final[frozenset[str]] = frozenset(
    {
        AGENT_FALLBACK_MODE_FORCE_ANSWER,
        AGENT_FALLBACK_MODE_RAISE_ERROR,
    }
)
"""runtime 层中立 Agent fallback mode 闭集。"""
