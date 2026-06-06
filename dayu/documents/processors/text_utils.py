"""处理器层通用文本处理工具。

本模块提供所有处理器共享的低层级文本处理函数，
避免在各处理器中重复定义相同的文本标准化逻辑。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional


def normalize_whitespace(text: str) -> str:
    """规范化空白字符：将连续空白压缩为单空格，去除首尾空白。

    使用 ``str.split()`` + ``" ".join()`` 实现，
    等价于 ``re.sub(r"\\s+", " ", text).strip()`` 但性能更优。

    对 ``None`` 和其它非字符串值，先转为 ``str`` 再处理。

    Args:
        text: 原始文本。

    Returns:
        规范化后的文本。
    """
    return " ".join(str(text or "").split())


def infer_suffix_from_uri(uri: str) -> str:
    """从 URI 推断文件后缀。

    剥离 scheme（如 ``https://``）后取路径后缀。

    Args:
        uri: 资源 URI 或文件路径。

    Returns:
        小写后缀（如 ``".html"``）；无法识别返回空字符串。
    """
    raw = str(uri or "").strip()
    if not raw:
        return ""
    # 剥离 scheme 部分（若无 scheme，split 返回原串）
    path_part = raw.split("://", 1)[-1]
    return Path(path_part).suffix.lower()


__all__ = [
    "PAGE_HEADER_NOISE_PATTERN",
    "PREVIEW_MAX_CHARS",
    "SECTION_REF_PATTERN",
    "TABLE_PLACEHOLDER_PATTERN",
    "TABLE_REF_PATTERN",
    "append_missing_table_placeholders",
    "clean_page_header_noise",
    "extract_table_refs_from_text",
    "extract_tail_sentence",
    "format_section_ref",
    "format_table_placeholder",
    "format_table_ref",
    "infer_caption_from_context",
    "infer_suffix_from_uri",
    "normalize_optional_string",
    "normalize_whitespace",
]

# ---------------------------------------------------------------------------
# 通用截断常量
# ---------------------------------------------------------------------------
# 章节预览/上下文截断的默认最大字符数
PREVIEW_MAX_CHARS: int = 200


def normalize_optional_string(value: Any) -> Optional[str]:
    """将任意值标准化为可选字符串。

    对 ``None``、空字符串等无意义值统一返回 ``None``，
    其他值经空白归一化后返回。

    注意：不处理 ``float('nan')`` 或 ``pandas.NaT`` 等特殊浮点值，
    如需处理请在调用前单独检测。

    Args:
        value: 任意输入值。

    Returns:
        标准化字符串；空值返回 ``None``。
    """
    if value is None:
        return None
    normalized = normalize_whitespace(str(value))
    return normalized or None


# ---------------------------------------------------------------------------
# 页眉噪声清除与 caption 推断
# ---------------------------------------------------------------------------

# 自适应页脚噪声模式：页码 + "Table of Contents" + 可选全大写公司名
PAGE_HEADER_NOISE_PATTERN = re.compile(
    r"\d+\s+Table\s+of\s+Contents"
    r"(?:\s+[A-Z][A-Z\s,.\-&]+?(?:INC|CORP|LLC|LTD|CO|LP)\.?(?=\s|$))?",
    re.IGNORECASE,
)

# 句子边界：句号/分号后跟空格，或换行符
_TAIL_SENTENCE_BOUNDARY = re.compile(r"[.;]\s+|\n")


def extract_tail_sentence(text: str) -> Optional[str]:
    """提取文本末尾的最后一个完整句子或短语。

    使用句号/分号/换行作为分隔符，取尾部片段。
    若文本以冒号结尾，保留完整的冒号前短语。

    Args:
        text: 已清洗的前文文本。

    Returns:
        尾部句子/短语；若开头即为起点则返回整段文本。
    """
    if not text:
        return None

    # 不拆冒号，因为 "xxx as follows:" 整句是有意义的 caption
    parts = _TAIL_SENTENCE_BOUNDARY.split(text)

    # 取最后一个非空部分
    for candidate in reversed(parts):
        candidate = candidate.strip()
        if candidate:
            return candidate

    return None


def clean_page_header_noise(text: str) -> str:
    """自适应清除文本中的页眉页脚噪声。

    清除常见的多页 HTML 文档页眉模式：

    - ``"36 Table of Contents"``
    - ``"36 Table of Contents AMAZON.COM, INC."``

    所有模式均为自适应检测（正则匹配），不依赖特定公司名。

    Args:
        text: 待清理文本（通常为 ``context_before``）。

    Returns:
        清理后的文本；空或无噪声时原样返回。
    """
    if not text:
        return text
    cleaned = PAGE_HEADER_NOISE_PATTERN.sub("", text)
    # 多次替换后可能产生多余空格
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


# caption 推断的长度上限：超过此值视为正文段落而非标题
_CAPTION_MAX_LEN = 200
# caption 推断的长度下限：过短无意义
_CAPTION_MIN_LEN = 5


def infer_caption_from_context(context_before: str) -> Optional[str]:
    """从表格前文推断简短 caption。

    当 HTML ``<caption>`` 标签不存在时，尝试从 ``context_before`` 的
    末尾提取一个简短、有意义的描述性短语作为自动 caption。

    自适应策略（无业务域硬编码规则）：

    1. 去除页脚噪声（页码 + "Table of Contents" 等自适应模式）。
    2. 提取最后一个句子/短语（句号/分号/换行分隔）。
    3. 若该短语过长则不采用（>200 字视为段落正文而非标题）。

    Args:
        context_before: 表格前文文本（通常最长 200 字）。

    Returns:
        推断的 caption，若无法推断则返回 ``None``。
    """
    if not context_before or not context_before.strip():
        return None

    text = context_before.strip()

    # ── 自适应去除页脚/页眉噪声 ──
    text = PAGE_HEADER_NOISE_PATTERN.sub("", text).strip()

    if not text:
        return None

    # ── 提取末尾句子/短语 ──
    tail = extract_tail_sentence(text)
    if not tail:
        return None

    # 过长说明是正文段落而非标题
    if len(tail) > _CAPTION_MAX_LEN:
        return None

    # 过短无意义（单个词或符号）
    if len(tail) < _CAPTION_MIN_LEN:
        return None

    return tail


# ---------------------------------------------------------------------------
# ref 格式化
# ---------------------------------------------------------------------------

SECTION_REF_PATTERN = re.compile(r"^s_\d{4}$")
"""章节引用匹配模式。"""

TABLE_REF_PATTERN = re.compile(r"^t_\d{4}$")
"""表格引用匹配模式。"""

TABLE_PLACEHOLDER_PATTERN = re.compile(r"\[\[(t_\d{4})\]\]")
"""表格占位符匹配模式。"""


def format_section_ref(index: int) -> str:
    """生成 ``s_NNNN`` 格式的章节引用。

    Args:
        index: 章节序号（≥ 1）。

    Returns:
        格式化后的引用字符串。

    Raises:
        ValueError: ``index`` < 1 时抛出。
    """
    if index < 1:
        raise ValueError(f"section index 必须为正数，当前值: {index}")
    return f"s_{index:04d}"


def format_table_ref(index: int) -> str:
    """生成 ``t_NNNN`` 格式的表格引用。

    Args:
        index: 表格序号（≥ 1）。

    Returns:
        格式化后的引用字符串。

    Raises:
        ValueError: ``index`` < 1 时抛出。
    """
    if index < 1:
        raise ValueError(f"table index 必须为正数，当前值: {index}")
    return f"t_{index:04d}"


def format_table_placeholder(table_ref: str) -> str:
    """生成表格占位符文本。

    Args:
        table_ref: 表格引用。

    Returns:
        ``[[t_NNNN]]`` 形式的占位符。

    Raises:
        ValueError: `table_ref` 为空时抛出。
    """

    normalized_ref = normalize_optional_string(table_ref)
    if normalized_ref is None:
        raise ValueError("table_ref 不能为空")
    return f"[[{normalized_ref}]]"


def extract_table_refs_from_text(content: str) -> list[str]:
    """从文本中提取表格引用。

    Args:
        content: 待扫描文本。

    Returns:
        按出现顺序去重后的表格引用列表。

    Raises:
        无。
    """

    refs: list[str] = []
    for match in TABLE_PLACEHOLDER_PATTERN.finditer(str(content or "")):
        ref = match.group(1)
        if ref not in refs:
            refs.append(ref)
    return refs


def append_missing_table_placeholders(content: str, missing_refs: list[str]) -> str:
    """在文本尾部补齐缺失的表格占位符。

    Args:
        content: 原始文本。
        missing_refs: 缺失的表格引用列表。

    Returns:
        追加占位符后的文本。

    Raises:
        无。
    """

    normalized_content = str(content or "")
    placeholders = [
        format_table_placeholder(ref)
        for ref in missing_refs
        if format_table_placeholder(ref) not in normalized_content
    ]
    if not placeholders:
        return normalized_content
    suffix = "\n".join(placeholders)
    if normalized_content:
        return f"{normalized_content}\n{suffix}".strip()
    return suffix
