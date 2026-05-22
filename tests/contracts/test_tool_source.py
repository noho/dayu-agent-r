"""工具来源引用契约测试。"""

from __future__ import annotations

from typing import cast

import pytest

from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef


def test_tool_bundle_source_ref_requires_enum_source_kind() -> None:
    """source_kind 必须是 ToolBundleSourceKind 枚举成员。"""

    with pytest.raises(TypeError, match="source_kind"):
        ToolBundleSourceRef(
            source_kind=cast(ToolBundleSourceKind, "config_binding"),
            source_id="binding-1",
        )

