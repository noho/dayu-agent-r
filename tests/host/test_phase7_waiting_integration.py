"""Phase 7 waiting integration smoke tests。"""

from __future__ import annotations

from dayu.host import resolve_wait


def test_phase7_resolve_wait_public_entry_is_importable() -> None:
    """P7-S3 integration 测试集包含 public resolve_wait 入口。"""

    assert resolve_wait.__name__ == "resolve_wait"
