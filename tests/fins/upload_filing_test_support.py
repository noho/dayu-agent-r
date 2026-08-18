"""Filing upload workflow 原子性 owner 测试支持。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from dayu.fins.domain.company_meta_contract import (
    CompanyMetaCommitIntent,
    CompanyMetaCommitOutcome,
)
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    SourceDocumentStateChangeRequest,
    SourceDocumentUpsertRequest,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet


class TrackingBatchingRepository(FsBatchingRepository):
    """记录 batch 生命周期并可注入 rollback failure 的真实 FS 仓储。"""

    def __init__(self, workspace_root: Path, *, repository_set: _FsRepositorySet) -> None:
        """初始化 tracking batch 仓储。

        Args:
            workspace_root: 工作区根目录。
            repository_set: 所有 staging writer 共用的 storage core。

        Returns:
            无。

        Raises:
            OSError: 仓储初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self.begin_tokens: list[BatchToken] = []
        self.commit_tokens: list[BatchToken] = []
        self.rollback_tokens: list[BatchToken] = []
        self.fail_rollback = False

    def begin_batch(self, ticker: str) -> BatchToken:
        """开始 batch 并记录 capability identity。

        Args:
            ticker: canonical ticker。

        Returns:
            真实 FS batch capability。

        Raises:
            OSError: batch 初始化失败时抛出。
            ValueError: ticker 非法时抛出。
            RuntimeError: 已存在 active writer 时抛出。
        """

        token = super().begin_batch(ticker)
        self.begin_tokens.append(token)
        return token

    def commit_batch(self, batch: BatchToken) -> CompanyMetaCommitOutcome | None:
        """记录并提交 batch。

        Args:
            batch: caller 转交的 batch capability。

        Returns:
            batch 含 company-meta intent 时返回真实 publication-final outcome；
            否则返回 ``None``。

        Raises:
            OSError: commit 失败时抛出。
            ValueError: capability 非法时抛出。
        """

        self.commit_tokens.append(batch)
        return super().commit_batch(batch)

    def rollback_batch(self, batch: BatchToken) -> None:
        """记录并回滚 batch，或在调用真实 rollback 前注入失败。

        Args:
            batch: caller 持有的 batch capability。

        Returns:
            无。

        Raises:
            OSError: 启用 failure injection 或真实 rollback 失败时抛出。
            ValueError: capability 非法时抛出。
        """

        self.rollback_tokens.append(batch)
        if self.fail_rollback:
            raise OSError("injected rollback evidence failure")
        super().rollback_batch(batch)


class TrackingCompanyMetaRepository(FsCompanyMetaRepository):
    """记录 company stage token 并可在真实 stage 后注入主异常。"""

    def __init__(self, workspace_root: Path, *, repository_set: _FsRepositorySet) -> None:
        """初始化 tracking company 仓储。

        Args:
            workspace_root: 工作区根目录。
            repository_set: 与 batch/source 共用的 storage core。

        Returns:
            无。

        Raises:
            OSError: 仓储初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self.stage_tokens: list[BatchToken] = []
        self.fail_after_stage = False

    def stage_company_meta_intent(
        self,
        intent: CompanyMetaCommitIntent,
        *,
        batch: BatchToken,
    ) -> None:
        """记录 token、执行真实 stage，并按需注入主异常。

        Args:
            intent: authoritative merge 使用的 company meta intent。
            batch: caller-owned batch capability。

        Returns:
            无。

        Raises:
            RuntimeError: 启用 stage failure injection 时抛出。
            OSError: 真实 stage 失败时抛出。
            ValueError: capability 或 meta 非法时抛出。
        """

        self.stage_tokens.append(batch)
        super().stage_company_meta_intent(intent, batch=batch)
        if self.fail_after_stage:
            raise RuntimeError("injected company stage primary failure")


class TrackingSourceDocumentRepository(FsSourceDocumentRepository):
    """记录 filing source stage 使用的 batch capability。"""

    def __init__(self, workspace_root: Path, *, repository_set: _FsRepositorySet) -> None:
        """初始化 tracking source 仓储。

        Args:
            workspace_root: 工作区根目录。
            repository_set: 与 batch/company 共用的 storage core。

        Returns:
            无。

        Raises:
            OSError: 仓储初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self.stage_tokens: list[BatchToken] = []
        self.fail_after_stage = False

    def create_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """记录 create source 的 capability 后执行真实 stage。

        Args:
            req: source create request。
            source_kind: filing 或 material。
            batch: caller-owned batch capability。

        Returns:
            staged source handle。

        Raises:
            OSError: stage 失败时抛出。
            ValueError: capability 或请求非法时抛出。
        """

        self.stage_tokens.append(batch)
        handle = super().create_source_document(req, source_kind, batch=batch)
        if self.fail_after_stage:
            raise RuntimeError("injected source stage primary failure")
        return handle

    def update_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """记录 update source 的 capability 后执行真实 stage。

        Args:
            req: source update request。
            source_kind: filing 或 material。
            batch: caller-owned batch capability。

        Returns:
            staged source handle。

        Raises:
            OSError: stage 失败时抛出。
            ValueError: capability 或请求非法时抛出。
        """

        self.stage_tokens.append(batch)
        handle = super().update_source_document(req, source_kind, batch=batch)
        if self.fail_after_stage:
            raise RuntimeError("injected source stage primary failure")
        return handle

    def delete_source_document(
        self,
        req: SourceDocumentStateChangeRequest,
        *,
        batch: BatchToken,
    ) -> None:
        """记录 delete source 的 capability 后执行真实 stage。

        Args:
            req: source state change request。
            batch: caller-owned batch capability。

        Returns:
            无。

        Raises:
            OSError: stage 失败时抛出。
            ValueError: capability 或请求非法时抛出。
        """

        self.stage_tokens.append(batch)
        super().delete_source_document(req, batch=batch)


def published_tree_sha256(workspace_root: Path, ticker: str) -> dict[str, str]:
    """返回 ticker published tree 的逐文件 SHA-256 snapshot。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: canonical ticker。

    Returns:
        相对 workspace 的文件路径到 SHA-256 的稳定映射；tree absent 时为空。

    Raises:
        OSError: tree 枚举或文件读取失败时抛出。
    """

    ticker_root = workspace_root / "portfolio" / ticker
    if not ticker_root.exists():
        return {}
    return {
        path.relative_to(workspace_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(ticker_root.rglob("*"))
        if path.is_file()
    }
