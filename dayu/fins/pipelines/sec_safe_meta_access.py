"""SecPipeline 元数据安全读取与版本计算真源模块。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

from collections.abc import Callable
from typing import Optional

from dayu.fins.domain.document_models import CompanyMeta
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import (
    CompanyMetaRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)


def safe_get_company_meta(
    repository: CompanyMetaRepositoryProtocol,
    *,
    ticker: str,
) -> Optional[CompanyMeta]:
    """安全读取公司元数据。

    Args:
        repository: 公司元数据仓储。
        ticker: 股票代码。

    Returns:
        公司元数据；不存在时返回 `None`。

    Raises:
        ValueError: 元数据格式非法时抛出。
    """

    try:
        return repository.get_company_meta(ticker=ticker)
    except FileNotFoundError:
        return None


def safe_get_document_meta(
    repository: SourceDocumentRepositoryProtocol,
    *,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
) -> Optional[dict[str, JsonValue]]:
    """安全读取源文档 meta。

    Args:
        repository: source 仓储。
        ticker: 股票代码。
        document_id: 文档 ID。
        source_kind: 源文档类型。

    Returns:
        文档 meta；不存在时返回 `None`。

    Raises:
        ValueError: 元数据格式非法时抛出。
    """

    try:
        return repository.get_source_meta(
            ticker=ticker,
            document_id=document_id,
            source_kind=source_kind,
        )
    except FileNotFoundError:
        return None


def safe_get_filing_source_meta(
    repository: SourceDocumentRepositoryProtocol,
    *,
    ticker: str,
    document_id: str,
) -> Optional[dict[str, JsonValue]]:
    """安全读取 filing source meta。

    该函数固定读取 `SourceKind.FILING`，并把不存在或底层 staging 读取失败
    统一收口为 `None`，避免下载流程因为缺失 meta 中断。

    Args:
        repository: source 仓储。
        ticker: 股票代码。
        document_id: 文档 ID。

    Returns:
        filing meta；文件不存在或读取失败时返回 `None`。

    Raises:
        无。
    """

    try:
        return repository.get_source_meta(
            ticker=ticker,
            document_id=document_id,
            source_kind=SourceKind.FILING,
        )
    except (FileNotFoundError, ValueError, OSError):
        return None


def safe_get_processed_meta(
    repository: ProcessedDocumentRepositoryProtocol,
    *,
    ticker: str,
    document_id: str,
) -> Optional[dict[str, JsonValue]]:
    """安全读取 processed meta。

    Args:
        repository: processed 仓储。
        ticker: 股票代码。
        document_id: 文档 ID。

    Returns:
        processed meta；不存在时返回 `None`。

    Raises:
        ValueError: 元数据格式非法时抛出。
    """

    try:
        return repository.get_processed_meta(ticker=ticker, document_id=document_id)
    except FileNotFoundError:
        return None


def resolve_document_version(
    previous_meta: Optional[dict[str, JsonValue]],
    source_fingerprint: str,
    *,
    increment_document_version: Callable[[str], str],
) -> str:
    """计算文档版本号。

    Args:
        previous_meta: 旧 meta。
        source_fingerprint: 新指纹。
        increment_document_version: 版本号递增函数。

    Returns:
        文档版本号。

    Raises:
        无。
    """

    if previous_meta is None:
        return "v1"
    previous_version = str(previous_meta.get("document_version", "v1"))
    previous_fingerprint = str(previous_meta.get("source_fingerprint", "")).strip()
    if previous_fingerprint and previous_fingerprint != source_fingerprint:
        return increment_document_version(previous_version)
    return previous_version