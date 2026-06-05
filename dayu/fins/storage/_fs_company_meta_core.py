"""文件系统仓储 — 公司元数据操作 mixin。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.fins.domain.document_models import CompanyMeta, CompanyMetaInventoryEntry, now_iso8601

from ._fs_storage_infra import _FsStorageInfra
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
        """读取公司级元数据。

        Args:
            ticker: 股票代码。

        Returns:
            公司级元数据对象。

        Raises:
            FileNotFoundError: 元数据文件不存在时抛出。
            ValueError: 元数据字段缺失或格式错误时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        if normalized_ticker not in self._active_batches:
            cached_company_meta = self._get_cached_company_meta(normalized_ticker)
            if cached_company_meta is not None:
                return cached_company_meta
        company_meta_path = self._company_meta_path_for_read(normalized_ticker)
        if not company_meta_path.exists():
            raise FileNotFoundError(f"公司元数据不存在: {company_meta_path}")
        data = _read_json_object(company_meta_path)
        company_meta = CompanyMeta.from_dict(data)
        if normalized_ticker not in self._active_batches:
            self._cache_company_meta(company_meta)
        return company_meta

    def scan_company_meta_inventory(self) -> list[CompanyMetaInventoryEntry]:
        """扫描公司目录并返回元数据盘点结果。

        该接口用于需要批量枚举公司目录的上层调用方，统一通过 storage
        层识别隐藏目录、缺失 `meta.json` 与非法元数据，避免上层自行拼接
        `portfolio/` 路径后盲扫。

        Args:
            无。

        Returns:
            按目录名字典序排列的扫描结果列表。

        Raises:
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

        for ticker_dir in sorted(self.portfolio_root.iterdir(), key=lambda item: item.name):
            if not ticker_dir.is_dir():
                continue
            directory_name = ticker_dir.name.strip()
            if not directory_name:
                continue
            if ticker_dir.name.startswith("."):
                inventory.append(
                    CompanyMetaInventoryEntry(
                        directory_name=directory_name,
                        status="hidden_directory",
                        detail="隐藏目录不参与公司元数据批处理",
                    )
                )
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
        return inventory

    def upsert_company_meta(self, meta: CompanyMeta) -> None:
        """写入公司级元数据。

        Args:
            meta: 公司级元数据对象。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        self._execute_with_auto_batch(meta.ticker, self._upsert_company_meta_impl, meta)

    def _upsert_company_meta_impl(self, meta: CompanyMeta) -> None:
        """执行公司元数据写入（内部实现）。

        Args:
            meta: 公司级元数据对象。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        ticker = _normalize_ticker(meta.ticker)
        ticker_dir = self._ticker_dir_for_write(ticker)
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
        self._invalidate_company_meta_caches()

    def resolve_existing_ticker(self, candidates: list[str]) -> Optional[str]:
        """按候选顺序解析仓储中已存在的 ticker。

        Args:
            candidates: 候选 ticker 列表，顺序即优先级。

        Returns:
            首个命中的仓储 ticker；若均不存在则返回 `None`。

        Raises:
            OSError: 文件系统访问失败时抛出。
            ValueError: 同一 alias 命中多个公司目录时抛出。
        """

        for candidate in candidates:
            normalized_ticker = _normalize_ticker(candidate)
            if self._target_ticker_dir(normalized_ticker).exists():
                return normalized_ticker
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

        if self._alias_index is not None and not self._active_batches:
            return {
                alias: tickers.copy()
                for alias, tickers in self._alias_index.items()
            }
        company_meta_by_ticker = self._scan_company_meta_by_ticker()
        alias_index = self._build_company_alias_index_from_meta(company_meta_by_ticker)
        if not self._active_batches:
            self._company_meta_by_ticker = company_meta_by_ticker
            self._alias_index = alias_index
        return {
            alias: tickers.copy()
            for alias, tickers in alias_index.items()
        }

    def _get_cached_company_meta(self, ticker: str) -> Optional[CompanyMeta]:
        """从缓存读取公司级元数据。

        Args:
            ticker: 规范 ticker。

        Returns:
            缓存命中的公司级元数据；未命中时返回 `None`。

        Raises:
            无。
        """

        if self._company_meta_by_ticker is None:
            return None
        return self._company_meta_by_ticker.get(ticker)

    def _cache_company_meta(self, meta: CompanyMeta) -> None:
        """把单个公司级元数据写入缓存。

        Args:
            meta: 公司级元数据。

        Returns:
            无。

        Raises:
            无。
        """

        if self._company_meta_by_ticker is None:
            self._company_meta_by_ticker = {}
        self._company_meta_by_ticker[_normalize_ticker(meta.ticker)] = meta

    def _scan_company_meta_by_ticker(self) -> dict[str, CompanyMeta]:
        """扫描当前可读视图中的公司级元数据。

        当前可读视图包含：
        - 已提交到 `portfolio/*` 的公司目录。
        - 同实例内活动 batch 的 staging 目录（覆盖正式目录）。

        Args:
            无。

        Returns:
            `ticker -> CompanyMeta` 映射。

        Raises:
            OSError: 文件系统访问失败时抛出。
            ValueError: 公司级元数据格式非法时抛出。
        """

        company_meta_by_ticker: dict[str, CompanyMeta] = {}
        ticker_dirs = self._collect_readable_ticker_dirs()
        for ticker, ticker_dir in ticker_dirs.items():
            meta_path = ticker_dir / _SOURCE_META_FILENAME
            if not meta_path.exists():
                continue
            company_meta = CompanyMeta.from_dict(_read_json_object(meta_path))
            company_meta_by_ticker[_normalize_ticker(ticker)] = company_meta
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

    def _collect_readable_ticker_dirs(self) -> dict[str, Path]:
        """收集当前实例可读视图中的 ticker 目录。

        活动 batch 的 staging 目录会覆盖同名正式目录，确保 alias 解析与
        `get_company_meta()` 在同一 read view 上工作。

        Args:
            无。

        Returns:
            `ticker -> 目录路径` 映射。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        ticker_dirs: dict[str, Path] = {}
        if self.portfolio_root.exists():
            for ticker_dir in sorted(self.portfolio_root.iterdir(), key=lambda item: item.name):
                if not ticker_dir.is_dir():
                    continue
                ticker_dirs[_normalize_ticker(ticker_dir.name)] = ticker_dir
        for ticker, token in self._active_batches.items():
            ticker_dirs[_normalize_ticker(ticker)] = token.staging_ticker_dir
        return ticker_dirs
