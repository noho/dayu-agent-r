"""Host P4 context compact 边界测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import dayu.host as host


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_engine_does_not_import_host_context_compaction() -> None:
    """Engine 不得反向依赖 Host compact 实现。"""

    engine_files = (_REPO_ROOT / "dayu" / "engine").rglob("*.py")
    for path in engine_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith("dayu.host._context_compaction")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(
                        "dayu.host._context_compaction"
                    )


def test_host_public_api_does_not_export_compact_coordinator() -> None:
    """Host public API 不导出 compact coordinator 实现类。"""

    assert "ContextCompactCoordinator" not in host.__all__
    assert "DefaultRunInputBuilder" not in host.__all__
