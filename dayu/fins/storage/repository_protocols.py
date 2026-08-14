"""财报仓储窄协议定义。

该模块按真实职责簇拆分财报仓储协议，避免单一仓储同时承担：
- 批处理事务
- 公司级元数据
- 源文档 CRUD
- processed 产物 CRUD
- 文件对象读写
- filing 维护治理
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import TracebackType
from typing import BinaryIO, Literal, Optional, Protocol

from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.source import Source
from dayu.fins.domain.company_meta_contract import CompanyMetaCommitIntent
from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    CompanyMetaInventoryEntry,
    DocumentEntry,
    DocumentHandle,
    DocumentMeta,
    DocumentQuery,
    DownloadRejectionRegistry,
    DocumentSummary,
    FileObjectMeta,
    ProcessedCreateRequest,
    ProcessedDeleteRequest,
    ProcessedHandle,
    RejectedFilingArtifact,
    RejectedFilingArtifactUpsertRequest,
    ProcessedUpdateRequest,
    SourceDocumentProvenance,
    SourceDocumentRevision,
    SourceDocumentStateChangeRequest,
    SourceDocumentUpsertRequest,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ticker_normalization import normalize_ticker

from .source_integrity import SourceIntegrityClassification


CompanyTickerIdentityCorruptionKind = Literal[
    "invalid_descriptor",
    "invalid_meta",
    "identity_mismatch",
    "duplicate_owner",
]
"""Published company ticker identity corruption 的 closed kind。"""


class CompanyTickerAliasConflictError(ValueError):
    """本次 lookup ticker 已被另一 canonical corpus 占用。"""

    alias: str
    existing_canonical_ticker: str
    incoming_canonical_ticker: str

    def __init__(
        self,
        *,
        alias: str,
        existing_canonical_ticker: str,
        incoming_canonical_ticker: str,
    ) -> None:
        """构造 incoming identity conflict。

        Args:
            alias: 发生冲突的 normalized lookup ticker。
            existing_canonical_ticker: 当前 published owner。
            incoming_canonical_ticker: 本次提交的 canonical corpus。

        Returns:
            无。

        Raises:
            ValueError: 任一业务 identity 为空时抛出。
        """

        for field_name, ticker in (
            ("alias", alias),
            ("existing_canonical_ticker", existing_canonical_ticker),
            ("incoming_canonical_ticker", incoming_canonical_ticker),
        ):
            if not ticker or normalize_ticker(ticker).canonical != ticker:
                raise ValueError(f"{field_name} 必须是 normalized ticker")
        self.alias = alias
        self.existing_canonical_ticker = existing_canonical_ticker
        self.incoming_canonical_ticker = incoming_canonical_ticker
        super().__init__("股票代码别名已属于其他 canonical corpus")


class CompanyTickerIdentityCorruptionError(ValueError):
    """Published company ticker identity durable state 已损坏。"""

    kind: CompanyTickerIdentityCorruptionKind
    lookup_ticker: str | None

    def __init__(
        self,
        *,
        kind: CompanyTickerIdentityCorruptionKind,
        lookup_ticker: str | None = None,
    ) -> None:
        """构造不携带 filesystem locator 的 durable corruption fact。

        Args:
            kind: closed corruption kind。
            lookup_ticker: 可选 normalized lookup ticker，仅供结构化 owner 处理。

        Returns:
            无。

        Raises:
            ValueError: kind 不属于 closed contract 或 lookup ticker 为空字符串时抛出。
        """

        allowed_kinds: frozenset[str] = frozenset(
            {"invalid_descriptor", "invalid_meta", "identity_mismatch", "duplicate_owner"}
        )
        if kind not in allowed_kinds:
            raise ValueError("未知 company ticker identity corruption kind")
        if lookup_ticker is not None and normalize_ticker(lookup_ticker).canonical != lookup_ticker:
            raise ValueError("lookup_ticker 必须是 normalized ticker")
        self.kind = kind
        self.lookup_ticker = lookup_ticker
        super().__init__("工作区公司代码身份数据损坏")


@dataclass(frozen=True, slots=True)
class FilingUploadPublishedState:
    """filing 上传校验所需的同版 published state。

    Attributes:
        company_meta: 当前已发布公司元数据；不存在时为 ``None``。
        source_meta: 当前已发布 filing source 元数据；不存在时为 ``None``。
    """

    company_meta: CompanyMeta | None
    source_meta: Mapping[str, JsonValue] | None


class FilingUploadStateRepositoryProtocol(Protocol):
    """filing 上传校验使用的最小只读仓储协议。"""

    def read_filing_upload_state(
        self,
        ticker: str,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """读取同一 publication guard 下的公司与 filing source 状态。

        Args:
            ticker: 待校验的公司代码。
            document_id: 待校验的 filing 文档 ID。

        Returns:
            同版 published state；独立缺失的成员分别为 ``None``。

        Raises:
            CompanyTickerIdentityCorruptionError: published target、descriptor、meta
                或 identity durable state 损坏时抛出。
            ValueError: ticker 或 document identity 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published state 读取失败时抛出。
        """

        ...


@dataclass(frozen=True, slots=True)
class SourceSnapshotFileDescriptor:
    """source snapshot 内单个业务文件的无路径描述符。

    Attributes:
        name: source meta 声明的 exact 业务文件名。
        etag: 可选对象标识。
        last_modified: 可选最近修改时间。
        size: 可选声明字节数。
        content_type: 可选媒体类型。
        sha256: 可选文件内容摘要。
    """

    name: str
    etag: Optional[str]
    last_modified: Optional[str]
    size: Optional[int]
    content_type: Optional[str]
    sha256: Optional[str]


class SourceSnapshotConsistencyError(RuntimeError):
    """source publication 持续变化导致无法取得稳定 snapshot。"""

    def __init__(self) -> None:
        """构造不携带 revision 或 filesystem locator 的一致性异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__("源文档发布在读取期间持续变化，无法取得稳定快照")


class SourceSnapshotProtocol(Protocol):
    """storage-owned source snapshot 资源协议。"""

    def __enter__(self) -> SourceSnapshotProtocol:
        """进入 snapshot 资源生命周期。

        Args:
            无。

        Returns:
            当前仍可读的 snapshot 资源。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """退出 snapshot 资源生命周期并释放临时资源。

        Args:
            exc_type: 生命周期内活动异常的类型；正常退出时为 ``None``。
            exc: 生命周期内活动异常；正常退出时为 ``None``。
            traceback: 生命周期内活动异常的 traceback；正常退出时为 ``None``。

        Returns:
            始终返回 ``False``，不压制生命周期内的活动异常。

        Raises:
            OSError: 正常退出且临时资源清理失败时抛出 path-free 文件系统异常。
        """

        ...

    @property
    def ticker(self) -> str:
        """返回 exact external ticker。"""

        ...

    @property
    def document_id(self) -> str:
        """返回 exact external document ID。"""

        ...

    @property
    def source_kind(self) -> SourceKind:
        """返回 snapshot 已解析的 source kind。"""

        ...

    @property
    def source_meta(self) -> Mapping[str, JsonValue]:
        """返回不含 storage 私有字段的独立 source meta 副本。"""

        ...

    @property
    def provenance(self) -> SourceDocumentProvenance:
        """返回与 snapshot 同版的 source provenance。"""

        ...

    @property
    def revision(self) -> SourceDocumentRevision:
        """返回与 snapshot 同版的 opaque published revision。"""

        ...

    @property
    def files(self) -> tuple[SourceSnapshotFileDescriptor, ...]:
        """返回 source meta 顺序下的完整业务文件描述符。"""

        ...

    @property
    def primary_filename(self) -> str:
        """返回精确命中文件描述符的主文件名。"""

        ...

    def get_source(self, filename: str) -> Source:
        """返回 full snapshot 中指定业务文件的临时 Source。

        Args:
            filename: snapshot 描述符中的 exact 业务文件名。

        Returns:
            只引用 snapshot 私有临时树的 Source。

        Raises:
            FileNotFoundError: filename 不属于 snapshot 时抛出。
            RuntimeError: snapshot 未物化文件或已经关闭时抛出。
            OSError: 临时文件不可读时抛出。
        """

        ...

    def get_primary_source(self) -> Source:
        """返回 full snapshot 的主文件临时 Source。

        Args:
            无。

        Returns:
            只引用 snapshot 私有临时树的主文件 Source。

        Raises:
            RuntimeError: snapshot 未物化文件或已经关闭时抛出。
            OSError: 临时主文件不可读时抛出。
        """

        ...

    def close(self) -> None:
        """幂等关闭 snapshot 并释放其临时资源。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 临时资源清理失败时抛出 path-free 文件系统异常。
        """

        ...


class BatchingRepositoryProtocol(Protocol):
    """批处理事务仓储协议。"""

    def begin_batch(self, ticker: str) -> BatchToken:
        """开启 ticker 级批处理事务。

        Args:
            ticker: 要绑定的股票代码。

        Returns:
            当前 storage core 登记的显式 batch capability。

        Raises:
            RuntimeError: 同 ticker 已存在活动 batch 或当前无法取得 owner lock 时抛出。
            ValueError: ticker 不满足单路径组件契约时抛出。
            OSError: staging、journal 或锁文件准备失败时抛出。
        """
        ...

    def commit_batch(self, batch: BatchToken) -> None:
        """提交批处理事务并消费 token。

        Args:
            batch: 当前 storage core 登记的活动 batch capability。

        Returns:
            无；返回即表示 ``COMMITTED`` journal 已成为唯一提交事实。

        Raises:
            ValueError: token 不是当前活动 batch 时抛出。
            OSError: ``COMMITTED`` 前 physical swap、journal 或 restore 失败时抛出；
                capability 仍由本方法终态消费，caller 不得再次 rollback。
            RuntimeFileLockError: 没有更早 operation error 且 publication/writer lock
                获取或释放失败时抛出；``COMMITTED`` 后 publication release failure
                作为 post-commit 主异常抛出且不回滚 durable tree，后续 cleanup/writer
                release failure 只附着为诊断。
        """
        ...

    def rollback_batch(self, batch: BatchToken) -> None:
        """回滚尚未进入 ``commit_batch`` 的活动 batch并消费 token。

        Args:
            batch: 当前 storage core 登记且尚未交给 ``commit_batch`` 的 capability。

        Returns:
            无。

        Raises:
            ValueError: token 已失效或不是当前活动 batch 时抛出。
            OSError: rollback journal 写入失败时抛出；staging 仍会清理且 capability
                仍会终态消费。
            RuntimeFileLockError: 没有更早 rollback error 且 writer lock 释放失败时
                抛出；已有主异常时 release failure 只附着为诊断。
        """
        ...

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """恢复合法 orphan，并 fail-closed 保留 malformed recovery evidence。

        Args:
            dry_run: 是否只返回拟执行 action 而不修改 filesystem。

        Returns:
            按扫描顺序记录的 restore/delete/cleanup/skip/preserve action。

        Raises:
            RuntimeFileLockError: recovery、writer 或 publication lock 操作失败时抛出。
            OSError: evidence 枚举、读取或 physical restore 失败时抛出。
        """
        ...


class CompanyMetaRepositoryProtocol(Protocol):
    """公司级元数据仓储协议。"""

    def scan_company_meta_inventory(self) -> list[CompanyMetaInventoryEntry]:
        """按 ticker publication guard 扫描 published 公司目录。

        Args:
            无。

        Returns:
            按目录名排序的公司元数据盘点结果。

        Raises:
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published tree 访问失败时抛出。
        """
        ...

    def get_company_meta(self, ticker: str) -> CompanyMeta:
        """从 published tree 读取公司级元数据。

        Args:
            ticker: 股票代码。

        Returns:
            对应公司的元数据对象。

        Raises:
            FileNotFoundError: 元数据不存在时抛出。
            ValueError: 元数据内容缺失或格式非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 底层文件系统读取失败时抛出。
        """
        ...

    def stage_company_meta_intent(
        self,
        intent: CompanyMetaCommitIntent,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction state 中记录公司元数据提交意图。

        Args:
            intent: 待在 commit-time 与 authoritative published state 合并的意图。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker、意图不匹配或重复 stage 时抛出。
        """
        ...

    def resolve_company_ticker(self, ticker: str) -> str | None:
        """按唯一 published identity index 解析 canonical corpus ticker。

        Args:
            ticker: 单个 canonical 或 accepted alias 查询值。

        Returns:
            唯一 canonical corpus ticker；输入非法或未命中时返回 ``None``。

        Raises:
            CompanyTickerIdentityCorruptionError: descriptor、meta、identity 或唯一性损坏时抛出。
            RuntimeFileLockError: identity/publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...


class SourceDocumentRepositoryProtocol(Protocol):
    """源文档仓储协议。"""

    def has_source_storage_root(self, ticker: str, source_kind: SourceKind) -> bool:
        """判断 published tree 中某类源文档根目录是否存在。

        Args:
            ticker: 股票代码。
            source_kind: filing 或 material 来源类型。

        Returns:
            published 根目录存在且为目录时返回 ``True``。

        Raises:
            NotADirectoryError: published 根路径存在但不是目录时抛出。
            ValueError: ticker 或 source kind 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def has_filing_xbrl_instance(self, ticker: str, document_id: str) -> bool:
        """判断 published filing 中是否存在 XBRL instance。

        Args:
            ticker: 股票代码。
            document_id: filing 文档 ID。

        Returns:
            published filing 中存在 XBRL instance 时返回 ``True``。

        Raises:
            FileNotFoundError: published filing 目录不存在时抛出。
            NotADirectoryError: published filing 路径不是目录时抛出。
            ValueError: ticker 或 document ID 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def has_staged_filing_xbrl_instance(
        self,
        ticker: str,
        document_id: str,
        *,
        batch: BatchToken,
    ) -> bool:
        """显式读取指定 open transaction staging 中的 filing XBRL instance。

        Args:
            ticker: 股票代码。
            document_id: filing 文档 ID。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            staging filing 中存在 XBRL instance 时返回 ``True``。

        Raises:
            FileNotFoundError: staging filing 目录不存在时抛出。
            NotADirectoryError: staging filing 路径不是目录时抛出。
            ValueError: capability、ticker 或 document ID 非法时抛出。
            OSError: staging I/O 失败时抛出。
        """
        ...

    def create_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """在显式 transaction staging 中创建源文档。

        Args:
            req: 通用源文档创建请求。
            source_kind: filing 或 material 来源类型。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            新建源文档句柄。

        Raises:
            FileExistsError: staging 文档已存在时抛出。
            FileNotFoundError: 请求引用的输入文件不存在时抛出。
            ValueError: capability、source kind 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """
        ...

    def update_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """在显式 transaction staging 中更新源文档。

        Args:
            req: 通用源文档更新请求。
            source_kind: filing 或 material 来源类型。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            更新后的源文档句柄。

        Raises:
            FileNotFoundError: staging 文档或请求引用文件不存在时抛出。
            ValueError: capability、source kind 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """
        ...

    def delete_source_document(
        self,
        req: SourceDocumentStateChangeRequest,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中逻辑删除源文档。

        Args:
            req: 源文档状态变更请求。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            FileNotFoundError: staging 文档不存在时抛出。
            ValueError: capability、source kind 或请求字段非法时抛出。
            OSError: staging meta 或 manifest 写入失败时抛出。
        """
        ...

    def reset_source_document(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> None:
        """重置单个源文档的完整存储。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker、document ID 或 source kind 非法时抛出。
            OSError: 重置底层存储失败时抛出。
        """
        ...

    def restore_source_document(
        self,
        req: SourceDocumentStateChangeRequest,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """在显式 transaction staging 中恢复逻辑删除的源文档。

        Args:
            req: 源文档状态变更请求。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            恢复后的源文档句柄。

        Raises:
            FileNotFoundError: staging 文档不存在时抛出。
            ValueError: capability、source kind 或请求字段非法时抛出。
            OSError: staging meta 或 manifest 写入失败时抛出。
        """
        ...

    def get_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> DocumentMeta:
        """从 published tree 读取源文档 meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            published source meta。

        Raises:
            FileNotFoundError: published source meta 不存在时抛出。
            ValueError: ticker、document ID、source kind 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def classify_source_integrity(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> SourceIntegrityClassification:
        """分类单个 published source 的物理完整性。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: filing 或 material。

        Returns:
            typed published integrity classification。

        Raises:
            ValueError: identity、meta 或文件声明结构非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published 文件系统读取失败时抛出。
        """
        ...

    def classify_staged_source_integrity(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> SourceIntegrityClassification:
        """分类真实 open batch staging 内的 source 完整性。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: filing 或 material。
            batch: 同一 core、ticker 且仍 open 的真实 capability。

        Returns:
            typed staged integrity classification。

        Raises:
            ValueError: capability、identity、meta 或文件声明结构非法时抛出。
            OSError: staging 文件系统读取失败时抛出。
        """
        ...

    def list_source_integrity(
        self,
        ticker: str,
    ) -> tuple[SourceIntegrityClassification, ...]:
        """在一个 publication guard 内列出完整 ticker source integrity。

        Args:
            ticker: exact external ticker。

        Returns:
            排序后的 filing+material typed inventory。

        Raises:
            ValueError: identity、manifest、meta 或文件声明结构非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published 文件系统读取失败时抛出。
        """
        ...

    def get_source_document_locator(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> PurePosixPath:
        """返回 published source 文档目录的 workspace-relative locator。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            storage owner 校验且只用于定位的相对 POSIX locator。

        Raises:
            FileNotFoundError: published source meta 不存在时抛出。
            ValueError: identity、source kind 或 meta 不一致时抛出。
            RuntimeError: publication guard 获取或释放失败时抛出。
            OSError: published tree 读取失败时抛出。
        """

        ...

    def read_source_snapshot(
        self,
        ticker: str,
        document_id: str,
        source_kind: Optional[SourceKind] = None,
        *,
        materialize_files: bool,
    ) -> SourceSnapshotProtocol:
        """读取同一 published revision 的完整 typed source snapshot。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: 可选显式 source kind；缺省时由 storage 在同一 guard 内解析。
            materialize_files: 是否把全部业务文件复制到 snapshot 私有临时树。

        Returns:
            同时拥有 identity、meta、provenance、revision、files 与 primary 的资源。

        Raises:
            FileNotFoundError: source 不存在、已删除或 reset 后抛出。
            ValueError: source kind 歧义、descriptor、meta、primary 或文件声明非法时抛出。
            SourceSnapshotConsistencyError: publication 持续变化且内部稳定读取耗尽时抛出。
            RuntimeError: publication guard 获取或释放失败时抛出。
            OSError: published 或临时文件系统访问失败时抛出。
        """
        ...

    def get_source_document_provenance(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        meta: DocumentMeta | None = None,
    ) -> SourceDocumentProvenance:
        """从 published meta 或显式输入 meta 投影源文档溯源事实。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。
            meta: 可选、由调用方已读取的 published meta；未提供时由 storage 读取。

        Returns:
            storage owner 校验后的源文档溯源事实。

        Raises:
            FileNotFoundError: 未传 meta 且 published source meta 不存在时抛出。
            KeyError: meta 缺少必需溯源字段时抛出。
            ValueError: ticker、document ID、source kind 或溯源字段非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def replace_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        meta: DocumentMeta,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中整体替换源文档 meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。
            meta: 完整替换元数据。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            FileNotFoundError: staging source meta 不存在时抛出。
            ValueError: capability、source kind、ticker 或 document ID 非法时抛出。
            OSError: staging meta 或 manifest 写入失败时抛出。
        """
        ...

    def list_source_document_ids(self, ticker: str, source_kind: SourceKind) -> list[str]:
        """从 published tree 按来源列出源文档 ID。

        Args:
            ticker: 股票代码。
            source_kind: filing 或 material 来源类型。

        Returns:
            published 文档 ID 排序列表。

        Raises:
            ValueError: ticker 或 source kind 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def get_source_handle(self, ticker: str, document_id: str, source_kind: SourceKind) -> SourceHandle:
        """从 published tree 校验并构造源文档句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            published source handle。

        Raises:
            FileNotFoundError: published source meta 不存在时抛出。
            ValueError: ticker、document ID 或 source kind 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """
        ...

    def get_primary_file(self, ticker: str, document_id: str, source_kind: SourceKind) -> FileObjectMeta:
        """从 published tree 读取源文档主文件对象元数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            published 主文件对象元数据。

        Raises:
            FileNotFoundError: published source 或主文件不存在时抛出。
            ValueError: ticker、document ID、source kind 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def get_source(self, ticker: str, document_id: str, source_kind: SourceKind, filename: str) -> Source:
        """从 published tree 构造指定文件的 delayed-open Source。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。
            filename: published source 文件名。

        Returns:
            文件描述符打开阶段重新获取 publication guard 的 Source。

        Raises:
            FileNotFoundError: published 文档、meta 或目标文件不存在时抛出。
            ValueError: ticker、document ID、source kind、filename 或 URI 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 或 Source 构造失败时抛出。
        """
        ...

    def get_primary_source(self, ticker: str, document_id: str, source_kind: SourceKind) -> Source:
        """从 published tree 构造主文件的 delayed-open Source。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: filing 或 material 来源类型。

        Returns:
            文件描述符打开阶段重新获取 publication guard 的 Source。

        Raises:
            FileNotFoundError: published source 或主文件不存在时抛出。
            ValueError: ticker、document ID、source kind、meta 或 URI 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 或 Source 构造失败时抛出。
        """
        ...


class ProcessedDocumentRepositoryProtocol(Protocol):
    """processed 产物仓储协议。"""

    def create_processed(self, req: ProcessedCreateRequest, *, batch: BatchToken) -> DocumentHandle:
        """在显式 transaction staging 中创建 processed 文档。

        Args:
            req: processed 创建请求。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            新建 processed 文档句柄。

        Raises:
            FileExistsError: staging 文档已存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """
        ...

    def update_processed(self, req: ProcessedUpdateRequest, *, batch: BatchToken) -> DocumentHandle:
        """在显式 transaction staging 中更新 processed 文档。

        Args:
            req: processed 更新请求。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            更新后的 processed 文档句柄。

        Raises:
            FileNotFoundError: staging 文档不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """
        ...

    def delete_processed(self, req: ProcessedDeleteRequest, *, batch: BatchToken) -> None:
        """在显式 transaction staging 中删除 processed 文档。

        Args:
            req: processed 删除请求。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            FileNotFoundError: staging 文档不存在时抛出。
            ValueError: capability 或请求字段非法时抛出。
            OSError: staging 删除失败时抛出。
        """
        ...

    def get_processed_handle(self, ticker: str, document_id: str) -> ProcessedHandle:
        """从 published tree 校验并构造 processed 句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            published processed 句柄。

        Raises:
            FileNotFoundError: published processed meta 不存在时抛出。
            ValueError: ticker 或 document ID 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """
        ...

    def get_processed_meta(self, ticker: str, document_id: str) -> DocumentMeta:
        """从 published tree 读取 processed meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            processed 元数据。

        Raises:
            FileNotFoundError: published meta 不存在时抛出。
            ValueError: ticker、document ID 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def list_processed_documents(self, ticker: str, query: DocumentQuery) -> list[DocumentSummary]:
        """从 published tree 按查询条件列出 processed 文档摘要。

        Args:
            ticker: 股票代码。
            query: 文档过滤条件。

        Returns:
            published processed 文档摘要列表。

        Raises:
            ValueError: ticker、query 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def clear_processed_documents(self, ticker: str, *, batch: BatchToken) -> None:
        """在显式 transaction staging 中清空 ticker 的 processed 产物。

        Args:
            ticker: 股票代码。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability 或 ticker 非法时抛出。
            OSError: staging 清理失败时抛出。
        """
        ...

    def mark_processed_reprocess_required(
        self,
        ticker: str,
        document_id: str,
        required: bool,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中标记 processed 是否需要重处理。

        Args:
            ticker: 股票代码。
            document_id: processed 文档 ID。
            required: 是否要求重处理；为 ``False`` 时不写入。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker 或 document ID 非法时抛出。
            OSError: staging meta 读写失败时抛出。
        """
        ...


class DocumentBlobRepositoryProtocol(Protocol):
    """文档文件对象仓储协议。"""

    def list_entries(self, handle: SourceHandle | ProcessedHandle) -> list[DocumentEntry]:
        """从 published tree 列出文档目录直系条目。

        Args:
            handle: source 或 processed 文档句柄。

        Returns:
            直系条目元数据列表。

        Raises:
            FileNotFoundError: published 文档目录不存在时抛出。
            ValueError: handle 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def read_file_bytes(self, handle: SourceHandle | ProcessedHandle, name: str) -> bytes:
        """从 published tree 读取文件字节内容。

        Args:
            handle: source 或 processed 文档句柄。
            name: 文档目录下的直系文件名。

        Returns:
            文件字节内容。

        Raises:
            FileNotFoundError: published 文件不存在时抛出。
            IsADirectoryError: 目标是目录时抛出。
            ValueError: handle 或文件名非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def delete_entry(
        self,
        handle: SourceHandle | ProcessedHandle,
        name: str,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中删除文档直系条目。

        Args:
            handle: source 或 processed 文档句柄。
            name: 待删除的直系条目名。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            FileNotFoundError: staging 条目不存在时抛出。
            ValueError: capability、handle 或条目名非法时抛出。
            OSError: staging 删除失败时抛出。
        """
        ...

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """在显式 transaction staging 中写入文件对象。

        Args:
            handle: source 或 processed 文档句柄。
            filename: 文件名。
            data: 二进制输入流。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。
            content_type: 可选内容类型。
            metadata: 可选字符串元数据。

        Returns:
            已写入文件的对象元数据。

        Raises:
            FileNotFoundError: processed handle 对应 staging meta 不存在时抛出。
            ValueError: capability、handle、文件名或 staging containment 非法时抛出。
            OSError: staging 写入失败时抛出。
        """
        ...

    def list_files(self, handle: SourceHandle | ProcessedHandle) -> list[FileObjectMeta]:
        """从 published tree 列出目录中的文件对象元数据。

        Args:
            handle: source 或 processed 文档句柄。

        Returns:
            文件对象元数据列表。

        Raises:
            FileNotFoundError: published 文档 meta 不存在时抛出。
            ValueError: handle 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...


class FilingMaintenanceRepositoryProtocol(Protocol):
    """filing 维护治理仓储协议。"""

    def clear_filing_documents(self, ticker: str, *, batch: BatchToken) -> None:
        """在显式 transaction staging 中清空 ticker 的 filing 文档。

        Args:
            ticker: 股票代码。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability 或 ticker 非法时抛出。
            OSError: staging 清理失败时抛出。
        """
        ...

    def load_download_rejection_registry(self, ticker: str) -> DownloadRejectionRegistry:
        """从 published tree 读取下载拒绝注册表。

        Args:
            ticker: 股票代码。

        Returns:
            document ID 到拒绝事实的注册表。

        Raises:
            ValueError: ticker 或 registry 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def save_download_rejection_registry(
        self,
        ticker: str,
        registry: DownloadRejectionRegistry,
        *,
        batch: BatchToken,
    ) -> None:
        """在显式 transaction staging 中保存下载拒绝注册表。

        Args:
            ticker: 股票代码。
            registry: document ID 到拒绝事实的注册表。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker 或 registry 内容非法时抛出。
            OSError: staging 写入失败时抛出。
        """
        ...

    def store_rejected_filing_file(
        self,
        ticker: str,
        document_id: str,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """在显式 transaction staging 中写入 rejected filing 文件。

        Args:
            ticker: 股票代码。
            document_id: rejected filing 文档 ID。
            filename: 文件名。
            data: 二进制输入流。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。
            content_type: 可选内容类型。
            metadata: 可选字符串元数据。

        Returns:
            文件对象元数据。

        Raises:
            ValueError: capability、ticker、document ID 或 filename 非法时抛出。
            OSError: staging 写入失败时抛出。
        """
        ...

    def upsert_rejected_filing_artifact(
        self,
        req: RejectedFilingArtifactUpsertRequest,
        *,
        batch: BatchToken,
    ) -> RejectedFilingArtifact:
        """在显式 transaction staging 中写入 rejected filing artifact。

        Args:
            req: artifact 写入请求。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。

        Returns:
            storage owner 规范化后的 artifact。

        Raises:
            ValueError: capability 或请求字段非法时抛出。
            OSError: staging 写入失败时抛出。
        """
        ...

    def get_rejected_filing_artifact(
        self,
        ticker: str,
        document_id: str,
    ) -> RejectedFilingArtifact:
        """从 published tree 读取 rejected filing artifact。

        Args:
            ticker: 股票代码。
            document_id: rejected filing 文档 ID。

        Returns:
            rejected filing artifact。

        Raises:
            FileNotFoundError: published artifact 不存在时抛出。
            ValueError: ticker、document ID 或 meta 内容非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def list_rejected_filing_artifacts(
        self,
        ticker: str,
    ) -> list[RejectedFilingArtifact]:
        """从 published tree 列出 ticker 的 rejected filing artifacts。

        Args:
            ticker: 股票代码。

        Returns:
            按文档 ID 排序的 rejected filing artifacts。

        Raises:
            ValueError: ticker 或任一 artifact meta 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def read_rejected_filing_file_bytes(
        self,
        ticker: str,
        document_id: str,
        filename: str,
    ) -> bytes:
        """从 published tree 读取 rejected filing 文件内容。

        Args:
            ticker: 股票代码。
            document_id: rejected filing 文档 ID。
            filename: 文件名。

        Returns:
            文件字节内容。

        Raises:
            FileNotFoundError: published 文件不存在时抛出。
            IsADirectoryError: 目标是目录时抛出。
            ValueError: ticker、document ID 或 filename 非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published I/O 失败时抛出。
        """
        ...

    def cleanup_stale_filing_documents(
        self,
        ticker: str,
        *,
        batch: BatchToken,
        active_form_types: set[str],
        valid_document_ids: set[str],
    ) -> int:
        """在显式 transaction staging 中清理不再有效的 filing 文档。

        Args:
            ticker: 股票代码。
            batch: 同一 storage core、ticker 且仍为 open 的显式 capability。
            active_form_types: 本次窗口覆盖的 form type 集合。
            valid_document_ids: 本次窗口仍应保留的文档 ID 集合。

        Returns:
            实际清理的文档数量。

        Raises:
            ValueError: capability、ticker、meta 或 manifest 内容非法时抛出。
            OSError: staging 清理或 manifest 写入失败时抛出。
        """
        ...


__all__ = [
    "BatchingRepositoryProtocol",
    "CompanyMetaRepositoryProtocol",
    "FilingUploadPublishedState",
    "FilingUploadStateRepositoryProtocol",
    "SourceSnapshotConsistencyError",
    "SourceSnapshotFileDescriptor",
    "SourceSnapshotProtocol",
    "SourceDocumentRepositoryProtocol",
    "ProcessedDocumentRepositoryProtocol",
    "DocumentBlobRepositoryProtocol",
    "FilingMaintenanceRepositoryProtocol",
]
