"""文件系统仓储 — 公司元数据操作 mixin。"""

from __future__ import annotations

from typing import Optional

from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    CompanyMetaInventoryEntry,
    now_iso8601,
)

from ._fs_storage_infra import _ActiveBatchState, _FsStorageInfra
from ._fs_storage_utils import (
    _SOURCE_META_FILENAME,
    _normalize_company_ticker_aliases,
    _normalize_ticker,
    _read_json_object,
    _write_json,
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
            ValueError: 元数据字段缺失或格式错误时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published meta 读取失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        guard_token = self._acquire_publication_guard(normalized_ticker)
        try:
            return self._get_company_meta_unguarded(normalized_ticker)
        finally:
            self._release_lock_token(guard_token)

    def _get_company_meta_unguarded(self, normalized_ticker: str) -> CompanyMeta:
        """在 caller 已持 publication guard 时读取公司元数据。

        Args:
            normalized_ticker: 已规范化的股票代码。

        Returns:
            公司级元数据对象。

        Raises:
            FileNotFoundError: 元数据文件不存在时抛出。
            ValueError: 元数据字段缺失或格式错误时抛出。
        """

        company_meta_path = self._company_meta_path_for_read(normalized_ticker)
        if not company_meta_path.exists():
            raise FileNotFoundError(f"公司元数据不存在: {company_meta_path}")
        data = _read_json_object(company_meta_path)
        return CompanyMeta.from_dict(data)

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
                    directory_name=self.dayu_root.name,
                    status="hidden_directory",
                    detail="Dayu 工作目录不参与公司元数据批处理",
                )
            )
        if not self.portfolio_root.exists():
            return inventory

        for directory_name in self._published_ticker_directory_names():
            if not directory_name:
                continue
            if directory_name.startswith("."):
                inventory.append(
                    CompanyMetaInventoryEntry(
                        directory_name=directory_name,
                        status="hidden_directory",
                        detail="隐藏目录不参与公司元数据批处理",
                    )
                )
                continue
            normalized_ticker = _normalize_ticker(directory_name)
            guard_token = self._acquire_publication_guard(normalized_ticker)
            try:
                ticker_dir = self._target_ticker_dir(normalized_ticker)
                if not ticker_dir.is_dir():
                    continue
                meta_path = ticker_dir / _SOURCE_META_FILENAME
                if not meta_path.exists():
                    inventory.append(
                        CompanyMetaInventoryEntry(
                            directory_name=directory_name,
                            status="missing_meta",
                            detail="缺少 meta.json",
                        )
                    )
                    continue
                try:
                    company_meta = CompanyMeta.from_dict(_read_json_object(meta_path))
                except (KeyError, TypeError, ValueError) as exc:
                    inventory.append(
                        CompanyMetaInventoryEntry(
                            directory_name=directory_name,
                            status="invalid_meta",
                            detail=str(exc),
                        )
                    )
                    continue
                inventory.append(
                    CompanyMetaInventoryEntry(
                        directory_name=directory_name,
                        status="available",
                        company_meta=company_meta,
                    )
                )
            finally:
                self._release_lock_token(guard_token)
        return inventory

    def upsert_company_meta(self, meta: CompanyMeta, *, batch: BatchToken) -> None:
        """写入公司级元数据。

        Args:
            meta: 公司级元数据对象。
            batch: 显式 transaction capability。

        Returns:
            无。

        Raises:
            ValueError: capability、ticker 或元数据路径字段非法时抛出。
            OSError: 写入失败时抛出。
        """

        state = self._resolve_active_batch(batch, meta.ticker)
        self._upsert_company_meta_impl(meta, state)

    def _upsert_company_meta_impl(self, meta: CompanyMeta, state: _ActiveBatchState) -> None:
        """执行公司元数据写入（内部实现）。

        Args:
            meta: 公司级元数据对象。
            state: 已解析的内部 transaction state。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        ticker = _normalize_ticker(meta.ticker)
        ticker_dir = self._ticker_dir_for_write(ticker, state)
        self._ensure_ticker_structure(ticker_dir)
        normalized_meta = CompanyMeta(
            company_id=meta.company_id,
            company_name=meta.company_name,
            ticker=ticker,
            market=meta.market,
            resolver_version=meta.resolver_version,
            updated_at=meta.updated_at or now_iso8601(),
            ticker_aliases=_normalize_company_ticker_aliases(
                canonical_ticker=ticker,
                ticker_aliases=meta.ticker_aliases,
            ),
        )
        _write_json(ticker_dir / _SOURCE_META_FILENAME, normalized_meta.to_dict())

    def resolve_existing_ticker(self, candidates: list[str]) -> Optional[str]:
        """按候选顺序从 published 公司目录解析已存在的 ticker。

        Args:
            candidates: 候选 ticker 列表，顺序即优先级。

        Returns:
            首个命中的仓储 ticker；若均不存在则返回 `None`。

        Raises:
            OSError: 文件系统访问失败时抛出。
            ValueError: 同一 alias 命中多个公司目录时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """

        for candidate in candidates:
            normalized_ticker = _normalize_ticker(candidate)
            guard_token = self._acquire_publication_guard(normalized_ticker)
            try:
                if self._target_ticker_dir(normalized_ticker).exists():
                    return normalized_ticker
            finally:
                self._release_lock_token(guard_token)
        return self._resolve_existing_ticker_by_company_alias(candidates)

    # ---------- 内部实现 ----------

    def _resolve_existing_ticker_by_company_alias(self, candidates: list[str]) -> Optional[str]:
        """通过公司级 `meta.json` 的 alias 解析已存在 ticker。

        Args:
            candidates: 候选 ticker 列表，顺序即优先级。

        Returns:
            首个命中的规范 ticker；若均不存在则返回 `None`。

        Raises:
            OSError: 文件系统访问失败时抛出。
            ValueError: 同一 alias 命中多个公司目录时抛出。
        """

        normalized_candidates = [_normalize_ticker(candidate) for candidate in candidates]
        if not normalized_candidates:
            return None
        alias_to_tickers = self._build_company_alias_index()
        for candidate in normalized_candidates:
            matched_tickers = alias_to_tickers.get(candidate, [])
            if len(matched_tickers) > 1:
                raise ValueError(
                    f"ticker alias={candidate} 命中多个公司目录: {matched_tickers}"
                )
            if len(matched_tickers) == 1:
                return matched_tickers[0]
        return None

    def _build_company_alias_index(self) -> dict[str, list[str]]:
        """扫描公司级 `meta.json` 并构建 alias 索引。

        Args:
            无。

        Returns:
            `alias -> [ticker]` 映射。

        Raises:
            OSError: 文件系统访问失败时抛出。
            ValueError: 公司级元数据格式非法时抛出。
        """

        company_meta_by_ticker = self._scan_company_meta_by_ticker()
        alias_index = self._build_company_alias_index_from_meta(company_meta_by_ticker)
        return {
            alias: tickers.copy()
            for alias, tickers in alias_index.items()
        }

    def _scan_company_meta_by_ticker(self) -> dict[str, CompanyMeta]:
        """扫描 published 可读视图中的公司级元数据。

        当前可读视图只包含已提交到 `portfolio/*` 的公司目录。

        Args:
            无。

        Returns:
            `ticker -> CompanyMeta` 映射。

        Raises:
            OSError: 文件系统访问失败时抛出。
            ValueError: 公司级元数据格式非法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """

        company_meta_by_ticker: dict[str, CompanyMeta] = {}
        for ticker in self._published_ticker_directory_names():
            if ticker.startswith("."):
                continue
            normalized_ticker = _normalize_ticker(ticker)
            guard_token = self._acquire_publication_guard(normalized_ticker)
            try:
                ticker_dir = self._target_ticker_dir(normalized_ticker)
                meta_path = ticker_dir / _SOURCE_META_FILENAME
                if not meta_path.exists():
                    continue
                company_meta = CompanyMeta.from_dict(_read_json_object(meta_path))
                company_meta_by_ticker[normalized_ticker] = company_meta
            finally:
                self._release_lock_token(guard_token)
        return company_meta_by_ticker

    def _build_company_alias_index_from_meta(
        self,
        company_meta_by_ticker: dict[str, CompanyMeta],
    ) -> dict[str, list[str]]:
        """根据公司级元数据构建 alias 索引。

        Args:
            company_meta_by_ticker: `ticker -> CompanyMeta` 映射。

        Returns:
            `alias -> [ticker]` 映射。

        Raises:
            ValueError: 公司级元数据中的 ticker 非法时抛出。
        """

        alias_index: dict[str, list[str]] = {}
        for normalized_ticker in sorted(company_meta_by_ticker):
            company_meta = company_meta_by_ticker[normalized_ticker]
            normalized_aliases = _normalize_company_ticker_aliases(
                canonical_ticker=normalized_ticker,
                ticker_aliases=company_meta.ticker_aliases,
            )
            for alias in normalized_aliases:
                alias_index.setdefault(alias, [])
                if normalized_ticker not in alias_index[alias]:
                    alias_index[alias].append(normalized_ticker)
        return alias_index

    def _published_ticker_directory_names(self) -> list[str]:
        """收集 published ticker 与正在 swap 的 publication lock 名称。

        Args:
            无。

        Returns:
            排序且去重的 ticker 目录名称。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        ticker_names: set[str] = set()
        if self.portfolio_root.exists():
            for ticker_dir in sorted(self.portfolio_root.iterdir(), key=lambda item: item.name):
                if ticker_dir.is_dir():
                    ticker_names.add(ticker_dir.name.strip())
        if self._batch_lock_root.exists():
            suffix = ".publication.lock"
            for lock_path in self._batch_lock_root.glob(f"*{suffix}"):
                ticker_names.add(lock_path.name[: -len(suffix)])
        return sorted(name for name in ticker_names if name)
