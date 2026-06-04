"""runtime 层中立 digest helper 测试。"""

from __future__ import annotations

import hashlib

from dayu.runtime._digest import text_digest


def test_text_digest_matches_existing_sha256_prefix_shape() -> None:
    """文本 digest 必须保持 ``sha256:<hex>`` 输出形态。"""

    text = "Dayu scene fragment\n"

    assert text_digest(text) == "sha256:" + hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()
