"""文件系统仓储 — 公司元数据操作 mixin。"""

from __future__ import annotations

from dayu.fins.ticker_normalization import try_normalize_ticker

from dayu.fins.domain.company_meta_contract import CompanyMetaCommitIntent

from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    CompanyMetaInventoryEntry,
)

from ._fs_storage_infra import (
    _RECOVERY_LOCK_FILENAME,
    _FsStorageInfra,
    _parse_backup_directory_name,
)
from ._fs_identity import _require_external_identity
from .repository_protocols import CompanyTickerIdentityCorruptionError
from ._fs_storage_utils import (
    _SOURCE_META_FILENAME,
    _list_directory,
    _read_json_object,
)


class _FsCompanyMetaMixin(_FsStorageInfra):
    """公司元数据操作 mixin。"""

    # ---------- 公开接口 ----------

    def get_company_meta(self, ticker: str) -> CompanyMeta:
        """从 published tree 读取公司级元数据。

        Args:
            ticker: 股票代码。

        Returns:
            公司级元数据对象。

        Raises:
            FileNotFoundError: 元数据文件不存在时抛出。
            CompanyTickerIdentityCorruptionError: descriptor、meta 或 identity
                durable state 损坏时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        guard_token = self._acquire_publication_guard(external_ticker)
        try:
            return self._get_company_meta_unguarded(external_ticker)
        finally:
            self._release_lock_token(guard_token)

    def _get_company_meta_unguarded(self, external_ticker: str) -> CompanyMeta:
        """在 caller 已持 publication guard 时读取公司元数据。

        Args:
            external_ticker: exact external ticker。

        Returns:
            公司级元数据对象。

        Raises:
            FileNotFoundError: 元数据文件不存在时抛出。
            CompanyTickerIdentityCorruptionError: descriptor、meta 或 identity
                durable state 损坏时抛出。
            OSError: descriptor 或元数据读取失败时抛出。
        """

        ticker_dir = self._target_ticker_dir(external_ticker)
        directory_stat = self._lstat_optional_storage_path(
            ticker_dir,
            action="检查 published CompanyMeta ticker directory",
        )
        if directory_stat is None:
            raise FileNotFoundError(f"公司元数据不存在: ticker={external_ticker}")
        identity = self._read_published_company_identity(
            ticker_dir,
            expected_storage_key=ticker_dir.name,
            known_directory_stat=directory_stat,
        )
        if identity.canonical_ticker != external_ticker:
            raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
        if identity.company_meta is None:
            raise FileNotFoundError(f"公司元数据不存在: ticker={external_ticker}")
        return identity.company_meta

    def scan_company_meta_inventory(self) -> list[CompanyMetaInventoryEntry]:
        """按 ticker publication guard 扫描 published 公司目录并返回盘点结果。

        该接口用于需要批量枚举公司目录的上层调用方，统一通过 storage
        层识别隐藏目录、缺失 `meta.json` 与非法元数据，避免上层自行拼接
        `portfolio/` 路径后盲扫。

        Args:
            无。

        Returns:
            按目录名字典序排列的扫描结果列表。

        Raises:
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: 文件系统访问失败时抛出。
        """

        inventory: list[CompanyMetaInventoryEntry] = []
        if self.dayu_root.exists():
            inventory.append(
                CompanyMetaInventoryEntry(
                    ticker=None,
                    status="hidden_directory",
                    detail="Dayu 工作目录不参与公司元数据批处理",
                )
            )
        if not self.portfolio_root.exists():
            return inventory

        for ticker_key in self._published_ticker_candidate_keys():
            if not ticker_key:
                continue
            if ticker_key.startswith("."):
                inventory.append(
                    CompanyMetaInventoryEntry(
                        ticker=None,
                        status="hidden_directory",
                        detail="隐藏目录不参与公司元数据批处理",
                    )
                )
                continue
            guard_token = self._acquire_publication_guard_for_key(ticker_key)
            try:
                try:
                    external_ticker = self._ticker_identity_from_candidate_key(ticker_key)
                except (FileNotFoundError, ValueError, OSError):
                    inventory.append(
                        CompanyMetaInventoryEntry(
                            ticker=None,
                            status="invalid_meta",
                            detail="缺少可验证且一致的 ticker identity descriptor",
                        )
                    )
                    continue
                ticker_dir = self._target_ticker_dir(external_ticker)
                if not ticker_dir.is_dir():
                    inventory.append(
                        CompanyMetaInventoryEntry(
                            ticker=external_ticker,
                            status="missing_meta",
                            detail="published ticker target 不存在",
                        )
                    )
                    continue
                meta_path = ticker_dir / _SOURCE_META_FILENAME
                if not meta_path.exists():
                    inventory.append(
                        CompanyMetaInventoryEntry(
                            ticker=external_ticker,
                            status="missing_meta",
                            detail="缺少 meta.json",
                        )
                    )
                    continue
                try:
                    company_meta = CompanyMeta.from_dict(_read_json_object(meta_path))
                    if company_meta.ticker_identity.canonical_ticker != external_ticker:
                        raise ValueError("公司元数据 ticker 与 identity descriptor 不一致")
                except (KeyError, TypeError, ValueError) as exc:
                    inventory.append(
                        CompanyMetaInventoryEntry(
                            ticker=external_ticker,
                            status="invalid_meta",
                            detail=str(exc),
                        )
                    )
                    continue
                inventory.append(
                    CompanyMetaInventoryEntry(
                        ticker=external_ticker,
                        status="available",
                        company_meta=company_meta,
                    )
                )
            finally:
                self._release_lock_token(guard_token)
        return sorted(
            inventory,
            key=lambda entry: (
                entry.ticker is None,
                entry.ticker or "",
                entry.status,
            ),
        )

    def stage_company_meta_intent(
        self,
        intent: CompanyMetaCommitIntent,
        *,
        batch: BatchToken,
    ) -> None:
        """在 transaction state 中记录唯一 CompanyMeta 提交意图。

        Args:
            intent: commit-time authoritative merge 使用的提交意图。
            batch: 显式 transaction capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker、intent 不匹配或重复 stage 时抛出。
        """

        state = self._resolve_active_batch(
            batch,
            intent.proposed_identity.canonical_ticker,
        )
        if state.company_meta_intent is not None:
            raise ValueError("同一 batch 只能 stage 一次 CompanyMeta intent")
        state.company_meta_intent = intent

    def resolve_company_ticker(self, ticker: str) -> str | None:
        """按唯一 published identity index 解析 canonical corpus ticker。

        Args:
            ticker: 单个 canonical 或 accepted alias 查询值。

        Returns:
            命中时返回 descriptor-owned canonical；非法或未命中时返回 ``None``。

        Raises:
            CompanyTickerIdentityCorruptionError: published identity durable state 损坏时抛出。
            RuntimeFileLockError: identity/publication guard 获取或释放失败时抛出。
            OSError: workspace 扫描失败时抛出。
        """

        normalized = try_normalize_ticker(ticker)
        if normalized is None:
            return None
        identity_token = self._acquire_company_identity_guard()
        primary_error: Exception | None = None
        try:
            identities = self._scan_actual_published_company_identities()
            index = self._build_unique_company_identity_index(identities)
            return index.get(normalized.canonical)
        except Exception as exc:
            primary_error = exc
            raise
        finally:
            self._release_lock_after_operation(
                identity_token,
                primary_error=primary_error,
                action="company identity guard release",
            )

    # ---------- 内部实现 ----------

    def _published_ticker_candidate_keys(self) -> list[str]:
        """收集 published、backup 与 lock locator 的 ticker candidates。

        Args:
            无。

        Returns:
            排序且去重的 locator candidate keys；descriptor 校验前不得投影为业务 ticker。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        ticker_keys: set[str] = set()
        if self.portfolio_root.exists():
            for ticker_dir in sorted(
                _list_directory(
                    self.portfolio_root,
                    action="枚举 published ticker root",
                ),
                key=lambda item: item.name,
            ):
                if ticker_dir.is_dir() or ticker_dir.is_symlink():
                    ticker_keys.add(ticker_dir.name)
        if self.backup_root.exists():
            for backup_dir in _list_directory(
                self.backup_root,
                action="枚举 ticker backup root",
            ):
                parsed = _parse_backup_directory_name(backup_dir.name)
                if parsed is not None:
                    ticker_keys.add(parsed[0])
        if self._batch_lock_root.exists():
            publication_suffix = ".publication.lock"
            writer_suffix = ".lock"
            for lock_path in _list_directory(
                self._batch_lock_root,
                action="枚举 batch lock root",
            ):
                if lock_path.name == _RECOVERY_LOCK_FILENAME:
                    continue
                if lock_path.name.endswith(publication_suffix):
                    ticker_keys.add(lock_path.name[: -len(publication_suffix)])
                elif lock_path.name.endswith(writer_suffix):
                    ticker_keys.add(lock_path.name[: -len(writer_suffix)])
        return sorted(key for key in ticker_keys if key)
