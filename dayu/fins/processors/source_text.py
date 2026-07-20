"""Fins processor 源文本严格解码能力。

本模块独占 source bytes/path 到 UTF-8 文本的转换规则。调用方不得用
``ignore`` 或 ``replace`` 把损坏字节伪装成可读取正文。
"""

from __future__ import annotations

from pathlib import Path

from dayu.documents.processors.source import Source

_UTF8_TEXT_SUFFIXES = frozenset({".htm", ".html", ".json", ".md", ".markdown", ".txt", ".xhtml", ".xml"})
"""Fins processor 必须按 UTF-8 解释的文本文件后缀。"""


class FinsSourceDecodeError(Exception):
    """源文档无法被可靠读取或解码。

    Args:
        message: 不包含路径和原始字节的稳定错误说明。

    Returns:
        无。

    Raises:
        无。
    """


def decode_source_bytes(payload: bytes) -> str:
    """按 UTF-8 规则严格解码源文档字节。

    UTF-8 BOM 会被规范化移除；普通 ASCII/UTF-8 保持内容不变。

    Args:
        payload: 待解码的源文档字节。

    Returns:
        严格解码后的文本。

    Raises:
        FinsSourceDecodeError: 字节不是合法 UTF-8 时抛出，并保留
            ``UnicodeDecodeError`` 作为 cause。
    """

    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FinsSourceDecodeError("源文档不是有效的 UTF-8 文本。") from exc


def read_source_path_text(source_path: Path) -> str:
    """读取本地 source path 并严格解码为 UTF-8 文本。

    Args:
        source_path: 已物化的源文档路径。

    Returns:
        严格解码后的文本。

    Raises:
        FinsSourceDecodeError: 路径读取失败或内容不是合法 UTF-8 时抛出。
    """

    try:
        payload = source_path.read_bytes()
    except OSError as exc:
        raise FinsSourceDecodeError("源文档文本读取失败。") from exc
    return decode_source_bytes(payload)


def materialize_source_text(source: Source, *, suffix: str | None = None) -> str:
    """物化 Source 后严格读取 UTF-8 文本。

    Args:
        source: 文档来源抽象。
        suffix: 物化时使用的可选文件后缀。

    Returns:
        严格解码后的文本。

    Raises:
        FinsSourceDecodeError: 物化、读取或 UTF-8 解码失败时抛出。
    """

    try:
        source_path = source.materialize(suffix=suffix)
    except Exception as exc:
        raise FinsSourceDecodeError("源文档文本物化失败。") from exc
    return read_source_path_text(Path(source_path))


def validate_source_utf8_text(source: Source) -> None:
    """在 processor registry 选择前校验文本 source 的 UTF-8 完整性。

    二进制文档不进入该校验；HTML/XML/Markdown/JSON/纯文本 source 必须
    在任一候选 processor 构建前通过同一严格 decoder，避免候选内部的
    宽松解析把损坏字节伪装成成功。

    Args:
        source: 文档来源抽象。

    Returns:
        无。

    Raises:
        FinsSourceDecodeError: 文本 source 物化、读取或解码失败时抛出。
    """

    media_type = (source.media_type or "").strip().lower()
    uri_suffix = Path(source.uri.split("?", 1)[0]).suffix.lower()
    is_text_media_type = (
        media_type.startswith("text/")
        or "html" in media_type
        or "xml" in media_type
        or "json" in media_type
    )
    if not is_text_media_type and uri_suffix not in _UTF8_TEXT_SUFFIXES:
        return
    try:
        with source.open() as stream:
            payload = stream.read()
    except Exception as exc:
        raise FinsSourceDecodeError("源文档文本读取失败。") from exc
    decode_source_bytes(payload)


__all__ = [
    "FinsSourceDecodeError",
    "decode_source_bytes",
    "materialize_source_text",
    "read_source_path_text",
    "validate_source_utf8_text",
]
