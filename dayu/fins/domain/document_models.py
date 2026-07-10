"""财报领域模型定义。

该模块集中定义仓储层与管线层通用的数据对象，包含：
- 批处理事务 token
- 公司级元数据
- 文档 CRUD 请求对象
- 文档查询对象与摘要对象
- manifest item 对象

说明：
- 这些模型用于财报仓储窄协议与具体文件系统仓储实现的方法签名。
- 所有对象均采用 dataclass，便于类型检查、测试和序列化。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.filing_semantics import (
    normalize_document_quality,
    normalize_fiscal_period,
    parse_sec_form_type,
)


DocumentMeta = dict[str, Any]
"""文档元数据字典类型别名。"""


class FinsIngestMethod(str, Enum):
    """财报源文档进入仓储的业务方式。"""

    DOWNLOAD = "download"
    UPLOAD = "upload"

    @classmethod
    def from_storage_value(cls, value: str, *, field_name: str = "ingest_method") -> "FinsIngestMethod":
        """从 storage meta 字符串解析 ingest method。

        Args:
            value: storage meta 中的业务可读字符串值。
            field_name: 报错使用的字段名。

        Returns:
            已校验的 ingest method 枚举值。

        Raises:
            ValueError: 字符串为空或不是合法 ingest method 时抛出。
        """

        normalized = value.strip().lower()
        if not normalized:
            raise ValueError(f"{field_name} 不能为空")
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"{field_name} 非法: {value}") from exc

    def to_storage_value(self) -> str:
        """转换为 storage JSON 使用的业务可读字符串。

        Args:
            无。

        Returns:
            storage meta 中持久化的字符串值。

        Raises:
            无。
        """

        return self.value


class FinsSourceProvider(str, Enum):
    """财报源文档提供方的仓储值。

    该枚举表达 source meta 中持久化的 provider 真源，不直接作为
    LLM-facing 展示值使用。
    """

    SEC_EDGAR = "sec_edgar"
    CNINFO = "cninfo"
    HKEXNEWS = "hkexnews"
    USER_UPLOAD = "user_upload"

    @classmethod
    def from_storage_value(cls, value: str, *, field_name: str = "source_provider") -> "FinsSourceProvider":
        """从 storage meta 字符串解析 source provider。

        Args:
            value: storage meta 中的 provider 字符串。
            field_name: 报错使用的字段名。

        Returns:
            已校验的 provider 枚举值。

        Raises:
            ValueError: 字符串为空或不是合法 provider 时抛出。
        """

        normalized = value.strip().lower()
        if not normalized:
            raise ValueError(f"{field_name} 不能为空")
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"{field_name} 非法: {value}") from exc

    def to_storage_value(self) -> str:
        """转换为 source meta 使用的仓储字符串。

        Args:
            无。

        Returns:
            storage meta 中持久化的字符串值。

        Raises:
            无。
        """

        return self.value


@dataclass(frozen=True)
class SourceDocumentProvenance:
    """源文档溯源事实投影。

    Attributes:
        source_kind: 源文档类型。
        ingest_method: 文档进入仓储的业务方式。
        source_provider: 文档来源提供方。
        ingest_complete: source meta 是否为完成态。
    """

    source_kind: SourceKind
    ingest_method: FinsIngestMethod
    source_provider: FinsSourceProvider
    ingest_complete: bool

    @classmethod
    def from_meta(
        cls,
        meta: Mapping[str, JsonValue],
        source_kind: SourceKind,
    ) -> "SourceDocumentProvenance":
        """从 source meta 解析溯源事实。

        Args:
            meta: source repository 读取到的 meta 内容。
            source_kind: 仓储路由已经确认的源文档类型。

        Returns:
            已校验的源文档溯源事实。

        Raises:
            KeyError: meta 缺少必需溯源字段时抛出。
            ValueError: 字段类型或枚举值非法时抛出。
        """

        raw_ingest_method = meta["ingest_method"]
        if not isinstance(raw_ingest_method, str):
            raise ValueError("ingest_method 必须为字符串")
        raw_provider = meta["source_provider"]
        if not isinstance(raw_provider, str):
            raise ValueError("source_provider 必须为字符串")
        raw_ingest_complete = meta["ingest_complete"]
        if not isinstance(raw_ingest_complete, bool):
            raise ValueError("ingest_complete 必须为布尔值")
        return cls(
            source_kind=source_kind,
            ingest_method=FinsIngestMethod.from_storage_value(raw_ingest_method),
            source_provider=FinsSourceProvider.from_storage_value(raw_provider),
            ingest_complete=raw_ingest_complete,
        )


@dataclass(frozen=True)
class DownloadRejectionEntry:
    """SEC 下载拒绝注册表条目。

    该模型是下载拒绝事实的 typed contract，避免仓储与 pipeline 之间通过
    松散嵌套字典重复解释同一业务语义。
    """

    document_id: str
    reason: str
    category: str
    form_type: str
    filing_date: str
    download_version: str

    def __post_init__(self) -> None:
        """校验直接构造的下载拒绝条目字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 必填字段为空或 form 类型非法时抛出。
        """

        for field_name, value in (
            ("document_id", self.document_id),
            ("reason", self.reason),
            ("category", self.category),
            ("form_type", self.form_type),
            ("filing_date", self.filing_date),
            ("download_version", self.download_version),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} 不能为空")
        canonical_form_type = parse_sec_form_type(self.form_type, field_name="form_type")
        if canonical_form_type != self.form_type:
            raise ValueError("form_type 必须使用 canonical SEC form")

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, JsonValue],
        *,
        expected_document_id: Optional[str] = None,
    ) -> "DownloadRejectionEntry":
        """从 JSON 对象解析下载拒绝条目。

        Args:
            data: registry JSON 中的单条拒绝记录。
            expected_document_id: registry key 表达的预期 document id；提供时必须与条目字段一致。

        Returns:
            已校验的下载拒绝条目。

        Raises:
            KeyError: 缺少必需字段时抛出。
            ValueError: 字段类型、空值、form 类型或 document id 不匹配时抛出。
        """

        document_id = _required_json_string(data, "document_id")
        if expected_document_id is not None and document_id != expected_document_id:
            raise ValueError("download rejection document_id 与 registry key 不一致")
        form_type = parse_sec_form_type(_required_json_string(data, "form_type"), field_name="form_type")
        return cls(
            document_id=document_id,
            reason=_required_json_string(data, "reason"),
            category=_required_json_string(data, "category"),
            form_type=form_type,
            filing_date=_required_json_string(data, "filing_date"),
            download_version=_required_json_string(data, "download_version"),
        )

    def to_dict(self) -> dict[str, str]:
        """转换为 registry JSON 持久化字典。

        Args:
            无。

        Returns:
            JSON 可序列化的字符串字典。

        Raises:
            无。
        """

        return {
            "document_id": self.document_id,
            "reason": self.reason,
            "category": self.category,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "download_version": self.download_version,
        }


DownloadRejectionRegistry: TypeAlias = dict[str, DownloadRejectionEntry]
"""SEC 下载拒绝注册表 typed 映射。"""


@dataclass(frozen=True)
class FileObjectMeta:
    """文件对象元数据。"""

    uri: str
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    size: Optional[int] = None
    content_type: Optional[str] = None
    sha256: Optional[str] = None


@dataclass(frozen=True)
class SourceFileEntry:
    """源文档文件条目。

    该模型对应 `filings/*/meta.json` 中的 `files[]` 条目，用于在不依赖
    宽泛字典的前提下表达文件级元数据。
    """

    name: str
    uri: str
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    size: Optional[int] = None
    content_type: Optional[str] = None
    sha256: Optional[str] = None
    source_url: Optional[str] = None
    http_etag: Optional[str] = None
    http_last_modified: Optional[str] = None
    ingested_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """将条目转换为可序列化字典。

        Args:
            无。

        Returns:
            JSON 可序列化字典。

        Raises:
            无。
        """

        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceFileEntry":
        """从字典构建源文档文件条目。

        Args:
            data: 原始字典。

        Returns:
            `SourceFileEntry` 实例。

        Raises:
            KeyError: 缺少必填字段时抛出。
            ValueError: 必填字段为空时抛出。
        """

        name = str(data["name"]).strip()
        uri = str(data["uri"]).strip()
        if not name:
            raise ValueError("SourceFileEntry.name 不能为空")
        if not uri:
            raise ValueError("SourceFileEntry.uri 不能为空")
        raw_size = data.get("size")
        size = int(raw_size) if isinstance(raw_size, int) else None
        return cls(
            name=name,
            uri=uri,
            etag=_optional_str(data.get("etag")),
            last_modified=_optional_str(data.get("last_modified")),
            size=size,
            content_type=_optional_str(data.get("content_type")),
            sha256=_optional_str(data.get("sha256")),
            source_url=_optional_str(data.get("source_url")),
            http_etag=_optional_str(data.get("http_etag")),
            http_last_modified=_optional_str(data.get("http_last_modified")),
            ingested_at=_optional_str(data.get("ingested_at")),
        )


@dataclass(frozen=True)
class DocumentEntry:
    """文档目录直系条目。"""

    name: str
    is_file: bool


@dataclass(frozen=True)
class BatchToken:
    """批处理事务 token。

    Attributes:
        token_id: 批处理唯一标识。
        ticker: 对应股票代码。
        target_ticker_dir: 正式 `portfolio/{ticker}` 目录。
        staging_root_dir: 批处理暂存根目录。
        staging_ticker_dir: 批处理暂存目录。
        backup_dir: 提交阶段的备份目录。
        journal_path: 事务 journal 路径。
        ticker_lock_path: ticker 事务锁路径。
        created_at: token 创建时间（ISO8601）。
    """

    token_id: str
    ticker: str
    target_ticker_dir: Path
    staging_root_dir: Path
    staging_ticker_dir: Path
    backup_dir: Path
    journal_path: Path
    ticker_lock_path: Path
    created_at: str


@dataclass(frozen=True)
class CompanyMeta:
    """公司级元数据模型。"""

    company_id: str
    company_name: str
    ticker: str
    market: str
    resolver_version: str
    updated_at: str
    ticker_aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """将对象转换为字典。

        Args:
            无。

        Returns:
            可序列化字典。

        Raises:
            无。
        """

        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompanyMeta":
        """从字典构建 `CompanyMeta`。

        Args:
            data: 原始字典数据。

        Returns:
            `CompanyMeta` 实例。

        Raises:
            KeyError: 缺少必填字段时抛出。
        """

        raw_ticker_aliases = data.get("ticker_aliases")
        ticker_aliases = raw_ticker_aliases if isinstance(raw_ticker_aliases, list) else []
        return cls(
            company_id=str(data["company_id"]),
            company_name=str(data["company_name"]),
            ticker=str(data["ticker"]),
            ticker_aliases=[
                str(item).strip()
                for item in ticker_aliases
                if str(item).strip()
            ],
            market=str(data["market"]),
            resolver_version=str(data["resolver_version"]),
            updated_at=str(data["updated_at"]),
        )


CompanyMetaInventoryStatus = Literal[
    "available",
    "hidden_directory",
    "missing_meta",
    "invalid_meta",
]
"""公司目录扫描状态。"""


@dataclass(frozen=True)
class CompanyMetaInventoryEntry:
    """公司目录扫描结果。

    Attributes:
        directory_name: 公司目录名。
        status: 扫描状态。
        company_meta: 当状态为 ``available`` 时的公司元数据。
        detail: 附加说明或错误信息。
    """

    directory_name: str
    status: CompanyMetaInventoryStatus
    company_meta: Optional[CompanyMeta] = None
    detail: str = ""


@dataclass(frozen=True)
class DocumentHandle:
    """文档句柄。"""

    ticker: str
    document_id: str
    form_type: Optional[str] = None
    primary_file_uri: Optional[str] = None
    file_uris: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceHandle:
    """源文档句柄。"""

    ticker: str
    document_id: str
    source_kind: str


@dataclass(frozen=True)
class ProcessedHandle:
    """解析产物句柄。"""

    ticker: str
    document_id: str


@dataclass(frozen=True)
class SourceDocumentUpsertRequest:
    """源文档（filings/materials）写入请求基类。"""

    ticker: str
    document_id: str
    internal_document_id: str
    form_type: Optional[str] = None
    primary_document: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)
    files: list[FileObjectMeta] = field(default_factory=list)
    file_entries: Optional[list[dict[str, Any]]] = None


@dataclass(frozen=True)
class SourceDocumentStateChangeRequest:
    """源文档状态变更请求。

    用于统一 filings / materials 的逻辑删除与恢复操作，避免 public
    仓储协议继续暴露成对重复的 filing/material 方法。
    """

    ticker: str
    document_id: str
    source_kind: str


@dataclass(frozen=True)
class MaterialCreateRequest(SourceDocumentUpsertRequest):
    """材料创建请求。"""


@dataclass(frozen=True)
class MaterialUpdateRequest(SourceDocumentUpsertRequest):
    """材料更新请求。"""


@dataclass(frozen=True)
class MaterialDeleteRequest:
    """材料删除请求。"""

    ticker: str
    document_id: str


@dataclass(frozen=True)
class MaterialRestoreRequest:
    """材料恢复请求。"""

    ticker: str
    document_id: str


@dataclass(frozen=True)
class FilingCreateRequest(SourceDocumentUpsertRequest):
    """财报创建请求。"""


@dataclass(frozen=True)
class FilingUpdateRequest(SourceDocumentUpsertRequest):
    """财报更新请求。"""


@dataclass(frozen=True)
class RejectedFilingArtifactUpsertRequest:
    """rejected filing artifact 写入请求。

    该请求用于将 policy reject 的 filing 以完整 source artifact 形态保存到
    `.rejections/`，但不进入 active filings manifest。
    """

    ticker: str
    document_id: str
    internal_document_id: str
    accession_number: str
    company_id: str
    form_type: str
    filing_date: str
    report_date: Optional[str]
    primary_document: str
    selected_primary_document: str
    rejection_reason: str
    rejection_category: str
    classification_version: str
    source_fingerprint: str
    files: list[SourceFileEntry] = field(default_factory=list)
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    report_kind: Optional[str] = None
    amended: bool = False
    has_xbrl: Optional[bool] = None
    ingest_method: FinsIngestMethod = FinsIngestMethod.DOWNLOAD


@dataclass(frozen=True)
class RejectedFilingArtifact:
    """rejected filing artifact 读取结果。"""

    ticker: str
    document_id: str
    internal_document_id: str
    accession_number: str
    company_id: str
    form_type: str
    filing_date: str
    report_date: Optional[str]
    primary_document: str
    selected_primary_document: str
    rejection_reason: str
    rejection_category: str
    classification_version: str
    source_fingerprint: str
    files: list[SourceFileEntry] = field(default_factory=list)
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    report_kind: Optional[str] = None
    amended: bool = False
    has_xbrl: Optional[bool] = None
    ingest_method: FinsIngestMethod = FinsIngestMethod.DOWNLOAD
    rejected_at: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_meta_dict(cls, data: dict[str, Any]) -> "RejectedFilingArtifact":
        """从 rejected artifact meta 构建对象。

        Args:
            data: meta.json 字典。

        Returns:
            `RejectedFilingArtifact` 实例。

        Raises:
            KeyError: 缺少必填字段时抛出。
            ValueError: 必填字段非法时抛出。
        """

        return cls(
            ticker=str(data["ticker"]).strip(),
            document_id=str(data["document_id"]).strip(),
            internal_document_id=str(data["internal_document_id"]).strip(),
            accession_number=str(data["accession_number"]).strip(),
            company_id=str(data["company_id"]).strip(),
            form_type=parse_sec_form_type(str(data["form_type"])),
            filing_date=str(data["filing_date"]).strip(),
            report_date=_optional_str(data.get("report_date")),
            primary_document=str(data["primary_document"]).strip(),
            selected_primary_document=str(data["selected_primary_document"]).strip(),
            rejection_reason=str(data["rejection_reason"]).strip(),
            rejection_category=str(data["rejection_category"]).strip(),
            classification_version=str(data["classification_version"]).strip(),
            source_fingerprint=str(data.get("source_fingerprint", "")).strip(),
            files=[
                SourceFileEntry.from_dict(item)
                for item in data.get("files", [])
                if isinstance(item, dict)
            ],
            fiscal_year=int(data["fiscal_year"]) if isinstance(data.get("fiscal_year"), int) else None,
            fiscal_period=normalize_fiscal_period(_optional_str(data.get("fiscal_period"))),
            report_kind=_optional_str(data.get("report_kind")),
            amended=bool(data.get("amended", False)),
            has_xbrl=data.get("has_xbrl") if isinstance(data.get("has_xbrl"), bool) else None,
            ingest_method=FinsIngestMethod.from_storage_value(str(data["ingest_method"])),
            rejected_at=str(data.get("rejected_at", "")).strip(),
            created_at=str(data.get("created_at", "")).strip(),
            updated_at=str(data.get("updated_at", "")).strip(),
        )

    def to_meta_dict(self) -> dict[str, Any]:
        """将对象转换为 rejected artifact meta 字典。

        Args:
            无。

        Returns:
            meta.json 字典。

        Raises:
            无。
        """

        return {
            "ticker": self.ticker,
            "document_id": self.document_id,
            "internal_document_id": self.internal_document_id,
            "accession_number": self.accession_number,
            "company_id": self.company_id,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "report_date": self.report_date,
            "primary_document": self.primary_document,
            "selected_primary_document": self.selected_primary_document,
            "rejection_reason": self.rejection_reason,
            "rejection_category": self.rejection_category,
            "classification_version": self.classification_version,
            "source_fingerprint": self.source_fingerprint,
            "files": [item.to_dict() for item in self.files],
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "report_kind": self.report_kind,
            "amended": self.amended,
            "has_xbrl": self.has_xbrl,
            "ingest_method": self.ingest_method.to_storage_value(),
            "rejected_at": self.rejected_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class FilingDeleteRequest:
    """财报删除请求。"""

    ticker: str
    document_id: str


@dataclass(frozen=True)
class FilingRestoreRequest:
    """财报恢复请求。"""

    ticker: str
    document_id: str


@dataclass(frozen=True)
class ProcessedUpsertRequest:
    """解析产物写入请求基类。"""

    ticker: str
    document_id: str
    internal_document_id: str
    source_kind: str
    form_type: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)
    sections: Optional[list[dict[str, Any]]] = None
    tables: Optional[list[dict[str, Any]]] = None
    financials: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class ProcessedCreateRequest(ProcessedUpsertRequest):
    """解析产物创建请求。"""


@dataclass(frozen=True)
class ProcessedUpdateRequest(ProcessedUpsertRequest):
    """解析产物更新请求。"""


@dataclass(frozen=True)
class ProcessedDeleteRequest:
    """解析产物删除请求。"""

    ticker: str
    document_id: str


@dataclass(frozen=True)
class DocumentQuery:
    """文档查询条件。"""

    form_type: Optional[str] = None
    fiscal_years: Optional[list[int]] = None
    fiscal_periods: Optional[list[str]] = None
    source_kind: Optional[str] = None
    include_deleted: bool = False


@dataclass(frozen=True)
class DocumentSummary:
    """文档摘要对象。"""

    document_id: str
    internal_document_id: str
    source_kind: str
    form_type: Optional[str] = None
    material_name: Optional[str] = None
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    report_date: Optional[str] = None
    filing_date: Optional[str] = None
    amended: bool = False
    is_deleted: bool = False
    document_version: str = "v1"
    quality: str = "full"
    has_financials: bool = False
    section_count: int = 0
    table_count: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentSummary":
        """从字典创建 `DocumentSummary`。

        Args:
            data: 摘要字典。

        Returns:
            文档摘要对象。

        Raises:
            KeyError: 缺失必要字段时抛出。
        """

        return cls(
            document_id=str(data["document_id"]),
            internal_document_id=str(data.get("internal_document_id", "")),
            source_kind=str(data.get("source_kind", "filing")),
            form_type=_optional_str(data.get("form_type")),
            material_name=data.get("material_name"),
            fiscal_year=data.get("fiscal_year"),
            fiscal_period=normalize_fiscal_period(_optional_str(data.get("fiscal_period"))),
            report_date=data.get("report_date"),
            filing_date=data.get("filing_date"),
            amended=bool(data.get("amended", False)),
            is_deleted=bool(data.get("is_deleted", False)),
            document_version=str(data.get("document_version", "v1")),
            quality=normalize_document_quality(_optional_str(data.get("quality"))),
            has_financials=bool(data.get("has_financials", False)),
            section_count=int(data.get("section_count", 0)),
            table_count=int(data.get("table_count", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        """将对象转换为字典。

        Args:
            无。

        Returns:
            可序列化字典。

        Raises:
            无。
        """

        return asdict(self)


@dataclass(frozen=True)
class FilingSummary:
    """财报源文件摘要。

    用于向上层调用方暴露已下载财报文件的基本信息，包含文档标识、表单类型、
    申报/报告日期、财年财期、主文件路径等展示所需字段。
    """

    document_id: str
    form_type: Optional[str] = None
    filing_date: Optional[str] = None
    report_date: Optional[str] = None
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    is_deleted: bool = False
    primary_file_name: Optional[str] = None
    primary_file_path: Optional[str] = None


@dataclass(frozen=True)
class FilingManifestItem:
    """`filings/filing_manifest.json` 项目。"""

    document_id: str
    internal_document_id: str
    form_type: Optional[str] = None
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    report_date: Optional[str] = None
    filing_date: Optional[str] = None
    amended: bool = False
    ingest_method: FinsIngestMethod = FinsIngestMethod.DOWNLOAD
    ingest_complete: bool = True
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    document_version: str = "v1"
    source_fingerprint: str = ""
    has_xbrl: Optional[bool] = None

    def to_dict(self) -> dict[str, Any]:
        """将对象转换为 manifest 字典。

        Args:
            无。

        Returns:
            项目字典。

        Raises:
            无。
        """

        payload = asdict(self)
        payload["ingest_method"] = self.ingest_method.to_storage_value()
        return payload


@dataclass(frozen=True)
class MaterialManifestItem:
    """`materials/material_manifest.json` 项目。"""

    document_id: str
    internal_document_id: str
    form_type: Optional[str] = None
    material_name: Optional[str] = None
    filing_date: Optional[str] = None
    report_date: Optional[str] = None
    ingest_complete: bool = True
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    document_version: str = "v1"
    source_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        """将对象转换为 manifest 字典。

        Args:
            无。

        Returns:
            项目字典。

        Raises:
            无。
        """

        return asdict(self)


@dataclass(frozen=True)
class ProcessedManifestItem:
    """`processed/manifest.json` 项目。"""

    document_id: str
    internal_document_id: str
    source_kind: str
    form_type: Optional[str] = None
    material_name: Optional[str] = None
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    report_date: Optional[str] = None
    filing_date: Optional[str] = None
    amended: bool = False
    is_deleted: bool = False
    document_version: str = "v1"
    quality: str = "full"
    has_financials: bool = False
    section_count: int = 0
    table_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """将对象转换为 manifest 字典。

        Args:
            无。

        Returns:
            项目字典。

        Raises:
            无。
        """

        return asdict(self)


def now_iso8601() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串。

    Args:
        无。

    Returns:
        ISO8601 时间字符串。

    Raises:
        无。
    """

    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _required_json_string(data: Mapping[str, JsonValue], field_name: str) -> str:
    """从 JSON 对象读取必填非空字符串。

    Args:
        data: JSON 对象。
        field_name: 字段名。

    Returns:
        去除首尾空白后的字符串。

    Raises:
        KeyError: 字段缺失时抛出。
        ValueError: 字段不是字符串或字符串为空时抛出。
    """

    value = data[field_name]
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须为字符串")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} 不能为空")
    return normalized


def _optional_str(value: Any) -> Optional[str]:
    """将任意值标准化为可选字符串。

    Args:
        value: 原始值。

    Returns:
        去空白后的字符串；若为空则返回 `None`。

    Raises:
        无。
    """

    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
