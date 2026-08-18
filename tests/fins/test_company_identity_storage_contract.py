"""Workspace company ticker identity storage owner 与并发契约测试。"""

from __future__ import annotations

import errno
import json
import multiprocessing
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from threading import Barrier, Event
from typing import NoReturn, Protocol

import pytest

import dayu.fins.storage._fs_storage_infra as storage_infra_module
from dayu.fins.domain.company_meta_contract import (
    CompanyMetaConcurrentUpdateError,
    CompanyNameIgnoredChange,
    build_company_meta_commit_intent,
)
from dayu.fins.domain.document_models import BatchToken, CompanyMeta
from dayu.fins.pipelines.upload_company_meta import RESOLVER_VERSION, stage_company_meta_for_upload
from dayu.fins.storage import (
    CompanyTickerAliasConflictError,
    CompanyTickerIdentityCorruptionError,
    FsBatchingRepository,
    FsCompanyMetaRepository,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage._fs_storage_core import FsStorageCore
from dayu.fins.ticker_normalization import build_company_ticker_identity
from dayu.fins.upload_failure import (
    FinsUploadFailureCode,
    FinsUploadFailureKind,
    fins_upload_failure_from_exception,
    upload_failure_reason_from_json,
)
from dayu.runtime.filelock import RuntimeFileLockError, RuntimeFileLockToken
from tests.fins.company_meta_test_support import stage_company_meta_fixture


class _LockAcquirer(Protocol):
    """测试记录器所包装的 lock acquisition 协议。"""

    def __call__(self, lock_path: Path, *, blocking: bool) -> RuntimeFileLockToken:
        """获取 runtime lock token。

        Args:
            lock_path: lock path。
            blocking: 是否阻塞。

        Returns:
            runtime lock token。

        Raises:
            RuntimeError: 非阻塞锁已占用时抛出。
            OSError: lock filesystem 操作失败时抛出。
        """

        ...


class _LockAcquisitionRecorder:
    """记录 core 私有 lock path 的测试 callable。"""

    def __init__(
        self,
        wrapped: _LockAcquirer,
    ) -> None:
        """初始化记录器。

        Args:
            wrapped: 原始 lock acquisition callable。

        Returns:
            无。

        Raises:
            无。
        """

        self._wrapped = wrapped
        self.names: list[str] = []

    def __call__(self, lock_path: Path, *, blocking: bool) -> RuntimeFileLockToken:
        """记录 basename 后调用真实 lock owner。

        Args:
            lock_path: 待获取的 lock path。
            blocking: 是否阻塞。

        Returns:
            真实 runtime lock token。

        Raises:
            RuntimeError: 非阻塞锁已被占用时透出。
            OSError: lock filesystem 操作失败时透出。
        """

        self.names.append(lock_path.name)
        return self._wrapped(lock_path, blocking=blocking)


class _LstatDeny:
    """仅对一个 exact path 注入 PermissionError 的 lstat callable。"""

    def __init__(self, denied_path: Path, wrapped: _LstatCallable) -> None:
        """初始化 lstat failure injector。

        Args:
            denied_path: 唯一拒绝访问的路径。
            wrapped: 原始 lstat callable。

        Returns:
            无。

        Raises:
            无。
        """

        self._denied_path = denied_path
        self._wrapped = wrapped

    def __call__(
        self,
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
    ) -> os.stat_result:
        """拒绝目标路径并透传其它 lstat。

        Args:
            path: lstat target。
            dir_fd: 可选目录文件描述符。

        Returns:
            非目标路径的真实 stat。

        Raises:
            PermissionError: 目标路径始终拒绝访问。
            OSError: 其它路径的真实 lstat 失败时透出。
        """

        if Path(path) == self._denied_path:
            raise PermissionError(errno.EACCES, "permission denied", str(path))
        return self._wrapped(path, dir_fd=dir_fd)


class _OneShotLstatFailure:
    """对一个 exact path 的第一次 lstat 注入指定 I/O 失败。"""

    def __init__(
        self,
        failed_path: Path,
        error_number: int,
        wrapped: _LstatCallable,
    ) -> None:
        """初始化一次性 lstat failure injector。

        Args:
            failed_path: 第一次访问时失败的 exact path。
            error_number: 注入的 errno。
            wrapped: 原始 lstat callable。

        Returns:
            无。

        Raises:
            无。
        """

        self._failed_path = failed_path
        self._error_number = error_number
        self._wrapped = wrapped
        self._triggered = False

    def __call__(
        self,
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
    ) -> os.stat_result:
        """首次访问目标时失败，之后透传真实 lstat。

        Args:
            path: lstat target。
            dir_fd: 可选目录文件描述符。

        Returns:
            非注入分支的真实 stat。

        Raises:
            OSError: 首次访问 exact target 时抛出指定 I/O 失败。
        """

        if Path(path) == self._failed_path and not self._triggered:
            self._triggered = True
            raise OSError(self._error_number, "injected lstat failure", str(path))
        return self._wrapped(path, dir_fd=dir_fd)


class _LstatCallable(Protocol):
    """测试 failure injector 包装的 lstat 协议。"""

    def __call__(
        self,
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
    ) -> os.stat_result:
        """读取 path 的 link stat。

        Args:
            path: lstat target。
            dir_fd: 可选目录文件描述符。

        Returns:
            stat result。

        Raises:
            OSError: lstat 失败时抛出。
        """

        ...


class _PublicationGuardAcquirer(Protocol):
    """测试 failure injector 包装的 publication guard acquisition 协议。"""

    def __call__(self, ticker: str, /) -> RuntimeFileLockToken:
        """获取 ticker publication guard。

        Args:
            ticker: canonical ticker。

        Returns:
            runtime lock token。

        Raises:
            RuntimeFileLockError: guard 获取失败时抛出。
        """

        ...


class _LockReleaser(Protocol):
    """测试 release failure injector 包装的 lock release 协议。"""

    def __call__(self, token: RuntimeFileLockToken) -> None:
        """释放 runtime lock token。

        Args:
            token: 已持锁 token。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: release 失败时抛出。
        """

        ...


class _DirectoryReplacer(Protocol):
    """测试 barrier 包装的 directory replace 协议。"""

    def __call__(self, source: Path, target: Path) -> None:
        """原子替换目录。

        Args:
            source: replace source。
            target: replace target。

        Returns:
            无。

        Raises:
            OSError: replace 失败时抛出。
        """

        ...


class _ZeroArgumentLockAcquirer(Protocol):
    """无参数 lock acquisition 协议。"""

    def __call__(self) -> RuntimeFileLockToken:
        """取得 lock token。

        Args:
            无。

        Returns:
            runtime lock token。

        Raises:
            RuntimeFileLockError: acquire 失败时抛出。
        """

        ...


class _NthPublicationAcquireFailure:
    """在第 N 次 target publication guard acquisition 注入失败。"""

    def __init__(self, wrapped: _PublicationGuardAcquirer, fail_at: int) -> None:
        """初始化 acquire failure injector。

        Args:
            wrapped: 原始 publication guard acquisition。
            fail_at: 从一开始计数的失败位置。

        Returns:
            无。

        Raises:
            ValueError: fail_at 非正数时抛出。
        """

        if fail_at < 1:
            raise ValueError("fail_at 必须为正数")
        self._wrapped = wrapped
        self._fail_at = fail_at
        self._count = 0

    def __call__(self, ticker: str) -> RuntimeFileLockToken:
        """在指定调用位置失败，其它调用透传。

        Args:
            ticker: canonical ticker。

        Returns:
            非失败位置的真实 lock token。

        Raises:
            RuntimeFileLockError: 到达注入位置时抛出。
        """

        self._count += 1
        if self._count == self._fail_at:
            raise RuntimeFileLockError("injected publication acquire failure")
        return self._wrapped(ticker)


class _ReleaseFailureAfterRelease:
    """真实释放指定 lock 后注入一次 release failure。"""

    def __init__(self, wrapped: _LockReleaser, target_name: str) -> None:
        """初始化 release failure injector。

        Args:
            wrapped: 原始 release callable。
            target_name: 要注入失败的 exact lock basename。

        Returns:
            无。

        Raises:
            无。
        """

        self._wrapped = wrapped
        self._target_name = target_name
        self._triggered = False

    def __call__(self, token: RuntimeFileLockToken) -> None:
        """先真实释放，再对目标 lock 抛出一次 typed failure。

        Args:
            token: 待释放 lock token。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: 首次释放目标 lock 后抛出。
        """

        self._wrapped(token)
        if token.lock_path.name == self._target_name and not self._triggered:
            self._triggered = True
            raise RuntimeFileLockError("injected release failure")


class _ReplaceDirectoryForbidden:
    """记录并禁止任何 physical directory replace。"""

    def __init__(self) -> None:
        """初始化空调用记录。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.calls: list[tuple[Path, Path]] = []

    def __call__(self, source: Path, target: Path) -> NoReturn:
        """记录错误调用并立即失败。

        Args:
            source: replace source。
            target: replace target。

        Returns:
            不返回。

        Raises:
            AssertionError: 每次调用均抛出。
        """

        self.calls.append((source, target))
        raise AssertionError("lock acquire failure 后禁止 physical replace")


class _BlockingFirstReplace:
    """在第一次 replace 前建立可控 recovery barrier。"""

    def __init__(self, wrapped: _DirectoryReplacer) -> None:
        """初始化 recovery replace barrier。

        Args:
            wrapped: 原始 directory replace callable。

        Returns:
            无。

        Raises:
            无。
        """

        self._wrapped = wrapped
        self.entered = Event()
        self.allow = Event()
        self._blocked = False

    def __call__(self, source: Path, target: Path) -> None:
        """首次调用阻塞到测试显式放行，再执行真实 replace。

        Args:
            source: replace source。
            target: replace target。

        Returns:
            无。

        Raises:
            OSError: 真实 replace 失败时透出。
            AssertionError: barrier 未在时限内放行时抛出。
        """

        if not self._blocked:
            self._blocked = True
            self.entered.set()
            assert self.allow.wait(timeout=5)
        self._wrapped(source, target)


class _IdentityAcquireSignal:
    """记录 read path 开始尝试取得 identity guard。"""

    def __init__(self, wrapped: _ZeroArgumentLockAcquirer) -> None:
        """初始化 acquisition signal。

        Args:
            wrapped: 原始 identity acquisition callable。

        Returns:
            无。

        Raises:
            无。
        """

        self._wrapped = wrapped
        self.entered = Event()

    def __call__(self) -> RuntimeFileLockToken:
        """发出尝试信号后取得真实 identity guard。

        Args:
            无。

        Returns:
            真实 lock token。

        Raises:
            RuntimeFileLockError: acquire 失败时透出。
        """

        self.entered.set()
        return self._wrapped()


def test_first_meta_less_publication_uses_global_identity_lock_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次 descriptor publication 即使无 meta 也必须进入全局身份验证锁序。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 首次发布绕过 recovery/identity 或锁序错误时抛出。
    """

    batching, company, core = _build_repositories(tmp_path / "workspace")
    batch = batching.begin_batch("DELTA")
    recorder = _LockAcquisitionRecorder(core._acquire_lock_token)
    monkeypatch.setattr(core, "_acquire_lock_token", recorder)

    batching.commit_batch(batch)

    assert recorder.names[:2] == ["batch_recovery.lock", "company_identity.lock"]
    assert recorder.names[-1].endswith(".publication.lock")
    assert company.resolve_company_ticker("delta.us") == "DELTA"
    assert company.resolve_company_ticker("MSFT") is None


def test_meta_less_corpus_can_be_supplemented_and_routes_aliases(
    tmp_path: Path,
) -> None:
    """合法 meta-less corpus 应 canonical-only，后续可原子补齐 aliases。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: meta-less 被视为损坏或补 meta 后路由不同 corpus 时抛出。
    """

    batching, company, _ = _build_repositories(tmp_path / "workspace")
    empty_batch = batching.begin_batch("V-BA")
    batching.commit_batch(empty_batch)

    assert company.resolve_company_ticker("V.BA") == "V-BA"
    assert company.resolve_company_ticker("VISA") is None

    meta_batch = batching.begin_batch("V-BA")
    stage_company_meta_fixture(
        company,
        _meta("V-BA", aliases=("VISA",)),
        batch=meta_batch,
    )
    batching.commit_batch(meta_batch)

    assert company.resolve_company_ticker("V.BA.US") == "V-BA"
    assert company.resolve_company_ticker("visa") == "V-BA"


def test_unique_index_supports_cross_market_and_canonical_equivalent_queries(
    tmp_path: Path,
) -> None:
    """唯一 index 应统一处理跨市场 canonical 与合法语法变体。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: route 依赖下游 upper/fallback 或跨市场 identity 丢失时抛出。
    """

    batching, company, _ = _build_repositories(tmp_path / "workspace")
    for ticker, aliases in (
        ("0700", ("TCEHY",)),
        ("600519", ("KWEICHOW",)),
    ):
        batch = batching.begin_batch(ticker)
        stage_company_meta_fixture(company, _meta(ticker, aliases=aliases), batch=batch)
        batching.commit_batch(batch)

    assert company.resolve_company_ticker("0700-hk") == "0700"
    assert company.resolve_company_ticker("tcehy.us") == "0700"
    assert company.resolve_company_ticker("600519.sh") == "600519"
    assert company.resolve_company_ticker("kweichow") == "600519"


def test_conflicting_identity_is_rejected_before_published_side_effect(
    tmp_path: Path,
) -> None:
    """incoming alias/canonical 冲突应 typed 拒绝且不发布目标 corpus。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 冲突类型、字段或 durable side effect 不符合契约时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, _ = _build_repositories(workspace_root)
    existing_batch = batching.begin_batch("MSFT")
    stage_company_meta_fixture(company, _meta("MSFT", aliases=()), batch=existing_batch)
    batching.commit_batch(existing_batch)
    incoming_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(
        company,
        _meta("DELTA", aliases=("MSFT",)),
        batch=incoming_batch,
    )

    with pytest.raises(CompanyTickerAliasConflictError) as exc_info:
        batching.commit_batch(incoming_batch)

    assert exc_info.value.alias == "MSFT"
    assert exc_info.value.existing_canonical_ticker == "MSFT"
    assert exc_info.value.incoming_canonical_ticker == "DELTA"
    assert not (workspace_root / "portfolio" / "DELTA").exists()
    assert company.resolve_company_ticker("MSFT") == "MSFT"


def test_alias_conflict_and_corruption_have_distinct_bounded_upload_projection() -> None:
    """failure owner 应区分 incoming conflict 与 published corruption。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: closed kind/code、文案或文件归属不符合契约时抛出。
    """

    conflict = fins_upload_failure_from_exception(
        CompanyTickerAliasConflictError(
            alias="MSFT",
            existing_canonical_ticker="MSFT",
            incoming_canonical_ticker="DELTA",
        ),
        file_label="private.pdf",
    )
    corruption = fins_upload_failure_from_exception(
        CompanyTickerIdentityCorruptionError(kind="invalid_descriptor"),
        file_label="private.pdf",
    )

    assert conflict.kind is FinsUploadFailureKind.STORAGE
    assert conflict.code is FinsUploadFailureCode.TICKER_ALIAS_CONFLICT
    assert conflict.file_label is None
    assert conflict.message == "股票代码别名已属于当前工作区中的其他公司，请移除冲突别名后重试"
    assert upload_failure_reason_from_json(conflict.to_json()) == conflict
    assert corruption.kind is FinsUploadFailureKind.STORAGE
    assert corruption.code is FinsUploadFailureCode.STORAGE_IO
    assert corruption.file_label is None
    assert corruption.message == "工作区公司代码身份数据损坏，无法安全提交"


def test_concurrent_first_publications_with_same_alias_have_one_winner(
    tmp_path: Path,
) -> None:
    """两个独立 repository core 并发首发同 alias 时必须恰有一个成功。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 全局锁未串行化或冲突未原子拒绝时抛出。
    """

    workspace_root = tmp_path / "workspace"
    first_batching, first_company, _ = _build_repositories(workspace_root)
    second_batching, second_company, _ = _build_repositories(workspace_root)
    first_batch = first_batching.begin_batch("DELTA")
    second_batch = second_batching.begin_batch("MSFT")
    stage_company_meta_fixture(
        first_company,
        _meta("DELTA", aliases=("SHARED",)),
        batch=first_batch,
    )
    stage_company_meta_fixture(
        second_company,
        _meta("MSFT", aliases=("SHARED",)),
        batch=second_batch,
    )
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(_commit_after_barrier, first_batching, first_batch, barrier),
            executor.submit(_commit_after_barrier, second_batching, second_batch, barrier),
        )
        outcomes = tuple(future.result(timeout=10) for future in futures)

    successes = tuple(outcome for outcome in outcomes if outcome is None)
    failures = tuple(outcome for outcome in outcomes if outcome is not None)
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], CompanyTickerAliasConflictError)
    assert first_company.resolve_company_ticker("shared") in {"DELTA", "MSFT"}
    published = tuple(ticker for ticker in ("DELTA", "MSFT") if (workspace_root / "portfolio" / ticker).is_dir())
    assert len(published) == 1


def test_commit_authoritative_reload_preserves_same_version_concurrent_update(
    tmp_path: Path,
) -> None:
    """旧 snapshot 构造的 intent 应在 commit 重读后合并较新的同版本事实。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: storage 用 prevalidation snapshot 覆盖 authoritative state 时抛出。
    """

    batching, company, _ = _build_repositories(tmp_path / "workspace")
    initial_batch = batching.begin_batch("DELTA")
    initial = _meta("DELTA", aliases=("OLD",))
    stage_company_meta_fixture(company, initial, batch=initial_batch)
    batching.commit_batch(initial_batch)
    observed = company.get_company_meta("DELTA")
    delayed_intent = build_company_meta_commit_intent(
        proposed_identity=build_company_ticker_identity("DELTA", ("DELAYED",)),
        merge_mode="refresh_if_stale",
        observed_meta=observed,
        proposed_company_id="delayed-id",
        proposed_company_name="Delayed Name",
        resolver_version="resolver-v2",
        requested_company_name="Delayed Name",
    )
    concurrent_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(
        company,
        CompanyMeta(
            company_id="authoritative-id",
            company_name="Authoritative Name",
            ticker_identity=build_company_ticker_identity("DELTA", ("NEWER",)),
            resolver_version="resolver-v2",
            updated_at="producer-time",
        ),
        batch=concurrent_batch,
    )
    batching.commit_batch(concurrent_batch)

    delayed_batch = batching.begin_batch("DELTA")
    company.stage_company_meta_intent(delayed_intent, batch=delayed_batch)
    outcome = batching.commit_batch(delayed_batch)
    final_meta = company.get_company_meta("DELTA")

    assert outcome is not None
    assert outcome.company_meta == final_meta
    assert outcome.ignored_company_name == CompanyNameIgnoredChange(
        requested_company_name="Delayed Name",
        published_company_name="Authoritative Name",
    )
    assert final_meta.company_id == "authoritative-id"
    assert final_meta.company_name == "Authoritative Name"
    assert final_meta.ticker_identity.accepted_aliases == ("OLD", "NEWER", "DELAYED")


def test_cross_process_same_canonical_stale_intent_preserves_alias_union(
    tmp_path: Path,
) -> None:
    """跨进程 same-canonical 更新后，旧 intent 应保留 authoritative alias union。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: stale commit 覆盖另一进程 alias 或非身份事实时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, _ = _build_repositories(workspace_root)
    initial_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(company, _meta("DELTA", aliases=("OLD",)), batch=initial_batch)
    batching.commit_batch(initial_batch)
    observed = company.get_company_meta("DELTA")
    delayed_intent = build_company_meta_commit_intent(
        proposed_identity=build_company_ticker_identity("DELTA", ("PARENT",)),
        merge_mode="refresh_if_stale",
        observed_meta=observed,
        proposed_company_id="parent-id",
        proposed_company_name="Parent Name",
        resolver_version="resolver-v2",
    )

    _run_meta_commit_process(
        workspace_root,
        aliases=("CHILD",),
        resolver_version="resolver-v2",
        company_id="child-id",
        company_name="Child Name",
    )
    delayed_batch = batching.begin_batch("DELTA")
    company.stage_company_meta_intent(delayed_intent, batch=delayed_batch)
    batching.commit_batch(delayed_batch)

    final_meta = company.get_company_meta("DELTA")
    assert final_meta.company_id == "child-id"
    assert final_meta.company_name == "Child Name"
    assert final_meta.ticker_identity.accepted_aliases == ("OLD", "CHILD", "PARENT")


def test_cross_process_same_canonical_changed_but_still_stale_is_rejected(
    tmp_path: Path,
) -> None:
    """跨进程 current 已改变且仍非本 resolver 版本时必须 typed 拒绝旧 refresh。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 不安全 stale refresh 被接受或 authoritative tree 改变时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, _ = _build_repositories(workspace_root)
    initial_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(company, _meta("DELTA", aliases=("OLD",)), batch=initial_batch)
    batching.commit_batch(initial_batch)
    observed = company.get_company_meta("DELTA")
    delayed_intent = build_company_meta_commit_intent(
        proposed_identity=build_company_ticker_identity("DELTA", ("PARENT",)),
        merge_mode="refresh_if_stale",
        observed_meta=observed,
        proposed_company_id="parent-id",
        proposed_company_name="Parent Name",
        resolver_version="resolver-v3",
    )

    _run_meta_commit_process(
        workspace_root,
        aliases=("CHILD",),
        resolver_version="resolver-v2",
        company_id="child-id",
        company_name="Child Name",
    )
    target_dir = workspace_root / "portfolio" / "DELTA"
    tree_before = _tree_bytes(target_dir)
    delayed_batch = batching.begin_batch("DELTA")
    company.stage_company_meta_intent(delayed_intent, batch=delayed_batch)

    with pytest.raises(CompanyMetaConcurrentUpdateError):
        batching.commit_batch(delayed_batch)

    assert _tree_bytes(target_dir) == tree_before
    assert company.resolve_company_ticker("CHILD") == "DELTA"
    assert company.resolve_company_ticker("PARENT") is None


def test_two_material_processes_on_same_canonical_union_aliases(
    tmp_path: Path,
) -> None:
    """两个真实 upload-meta producer 进程写同 canonical 时必须稳定 union aliases。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 跨进程 writer/authoritative merge 丢失任一 material alias 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, _ = _build_repositories(workspace_root)
    initial_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(
        company,
        CompanyMeta(
            company_id="delta-id",
            company_name="Delta Inc.",
            ticker_identity=build_company_ticker_identity("DELTA", ("OLD",)),
            resolver_version=RESOLVER_VERSION,
            updated_at="initial",
        ),
        batch=initial_batch,
    )
    batching.commit_batch(initial_batch)
    context = multiprocessing.get_context("spawn")
    first_parent, first_child = context.Pipe()
    second_parent, second_child = context.Pipe()
    first_process = context.Process(
        target=_commit_upload_alias_in_process,
        args=(workspace_root, "MAT-A", first_child),
    )
    second_process = context.Process(
        target=_commit_upload_alias_in_process,
        args=(workspace_root, "MAT-B", second_child),
    )
    first_process.start()
    second_process.start()
    first_child.close()
    second_child.close()
    first_parent.send("go")
    second_parent.send("go")
    first_result = first_parent.recv()
    second_result = second_parent.recv()
    first_parent.close()
    second_parent.close()
    _join_successful_process(first_process)
    _join_successful_process(second_process)

    assert first_result == "ok"
    assert second_result == "ok"
    aliases = company.get_company_meta("DELTA").ticker_identity.accepted_aliases
    assert aliases[0] == "OLD"
    assert frozenset(aliases) == frozenset({"OLD", "MAT-A", "MAT-B"})


def test_commit_rejects_meta_disappearance_before_swap(
    tmp_path: Path,
) -> None:
    """prevalidation 后 meta 消失应并发拒绝，且不得执行 target backup/swap。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: meta disappearance 被当作 create、corruption 或发生发布副作用时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, _ = _build_repositories(workspace_root)
    initial_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(
        company,
        _meta("DELTA", aliases=("OLD",)),
        batch=initial_batch,
    )
    batching.commit_batch(initial_batch)
    update_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(
        company,
        CompanyMeta(
            company_id="new-id",
            company_name="New Name",
            ticker_identity=build_company_ticker_identity("DELTA", ("NEW",)),
            resolver_version="resolver-v2",
            updated_at="producer-time",
        ),
        batch=update_batch,
    )
    target_dir = workspace_root / "portfolio" / "DELTA"
    (target_dir / "meta.json").unlink()
    tree_before_commit = _tree_bytes(target_dir)

    with pytest.raises(CompanyMetaConcurrentUpdateError):
        batching.commit_batch(update_batch)

    assert _tree_bytes(target_dir) == tree_before_commit
    assert company.resolve_company_ticker("DELTA") == "DELTA"
    assert company.resolve_company_ticker("OLD") is None


@pytest.mark.parametrize(
    ("corruption", "expected_kind"),
    (
        ("missing_descriptor", "invalid_descriptor"),
        ("malformed_descriptor", "invalid_descriptor"),
        ("descriptor_symlink", "invalid_descriptor"),
        ("malformed_meta", "invalid_meta"),
        ("meta_symlink", "invalid_meta"),
        ("meta_directory", "invalid_meta"),
        ("identity_mismatch", "identity_mismatch"),
    ),
)
def test_published_descriptor_and_meta_corruption_are_typed(
    tmp_path: Path,
    corruption: str,
    expected_kind: str,
) -> None:
    """published descriptor/meta 损坏必须由 closed typed corruption owner 分类。

    Args:
        tmp_path: pytest 临时目录。
        corruption: 待注入的 durable corruption。
        expected_kind: 预期 closed kind。

    Returns:
        无。

    Raises:
        AssertionError: corruption 被当作缺失、冲突或普通 I/O 时抛出。
        OSError: 测试环境无法创建 symlink 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, _ = _build_repositories(workspace_root)
    batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(company, _meta("DELTA", aliases=("DLTA",)), batch=batch)
    batching.commit_batch(batch)
    corpus_dir = workspace_root / "portfolio" / "DELTA"
    descriptor_path = _identity_descriptor_file(corpus_dir)
    meta_path = corpus_dir / "meta.json"
    if corruption == "missing_descriptor":
        descriptor_path.unlink()
    elif corruption == "malformed_descriptor":
        descriptor_path.write_text("{}", encoding="utf-8")
    elif corruption == "descriptor_symlink":
        payload = descriptor_path.read_bytes()
        outside = tmp_path / "outside-descriptor.json"
        outside.write_bytes(payload)
        descriptor_path.unlink()
        descriptor_path.symlink_to(outside)
    elif corruption == "malformed_meta":
        meta_path.write_text("{}", encoding="utf-8")
    elif corruption == "meta_symlink":
        outside_meta = tmp_path / "outside-meta.json"
        outside_meta.write_bytes(meta_path.read_bytes())
        meta_path.unlink()
        meta_path.symlink_to(outside_meta)
    elif corruption == "meta_directory":
        meta_path.unlink()
        meta_path.mkdir()
    else:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        payload["ticker"] = "MSFT"
        meta_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CompanyTickerIdentityCorruptionError) as read_exc_info:
        company.get_company_meta("DELTA")
    assert read_exc_info.value.kind == expected_kind

    with pytest.raises(CompanyTickerIdentityCorruptionError) as exc_info:
        company.resolve_company_ticker("DELTA")

    assert exc_info.value.kind == expected_kind


def test_duplicate_published_alias_is_typed_corruption_not_incoming_conflict(
    tmp_path: Path,
) -> None:
    """已持久化的多 owner lookup key 应分类为 duplicate_owner corruption。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: durable duplicate 被误投影为 incoming conflict 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, _ = _build_repositories(workspace_root)
    for ticker, alias in (("DELTA", "DLTA"), ("MSFT", "MSF")):
        batch = batching.begin_batch(ticker)
        stage_company_meta_fixture(company, _meta(ticker, aliases=(alias,)), batch=batch)
        batching.commit_batch(batch)
    msft_meta_path = workspace_root / "portfolio" / "MSFT" / "meta.json"
    payload = json.loads(msft_meta_path.read_text(encoding="utf-8"))
    payload["ticker_aliases"] = ["DLTA"]
    msft_meta_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CompanyTickerIdentityCorruptionError) as exc_info:
        company.resolve_company_ticker("DLTA")

    assert exc_info.value.kind == "duplicate_owner"
    assert exc_info.value.lookup_ticker == "DLTA"


@pytest.mark.parametrize("protected_target", ("descriptor", "directory"))
def test_descriptor_scan_preserves_permission_io_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    protected_target: str,
) -> None:
    """descriptor file 或 ticker directory stat 失败不得被抹平成 corruption。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        protected_target: 注入失败的 filesystem target 类别。

    Returns:
        无。

    Raises:
        AssertionError: PermissionError 被 Path predicate 抹平或误分型时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, _ = _build_repositories(workspace_root)
    batch = batching.begin_batch("DELTA")
    batching.commit_batch(batch)
    corpus_dir = workspace_root / "portfolio" / "DELTA"
    descriptor_path = _identity_descriptor_file(corpus_dir)
    denied_path = descriptor_path if protected_target == "descriptor" else corpus_dir
    monkeypatch.setattr(
        storage_infra_module.os,
        "lstat",
        _LstatDeny(denied_path, storage_infra_module.os.lstat),
    )

    with pytest.raises(PermissionError):
        company.resolve_company_ticker("DELTA")


@pytest.mark.parametrize("error_number", (errno.EACCES, errno.EIO))
def test_begin_batch_lstat_failure_never_reclassifies_existing_corpus_as_new(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    """begin-time EACCES/EIO 必须 fail closed 且保持 existing corpus byte-for-byte。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        error_number: 注入的 permission 或普通 I/O errno。

    Returns:
        无。

    Raises:
        AssertionError: I/O 被误判为 missing 或 published tree 被替换时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    initial_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(
        company,
        _meta("DELTA", aliases=("DLTA",)),
        batch=initial_batch,
    )
    batching.commit_batch(initial_batch)
    target_dir = workspace_root / "portfolio" / "DELTA"
    tree_before = _tree_bytes(target_dir)
    injected_lstat = _OneShotLstatFailure(
        target_dir,
        error_number,
        storage_infra_module.os.lstat,
    )
    monkeypatch.setattr(storage_infra_module.os, "lstat", injected_lstat)

    with pytest.raises(OSError) as exc_info:
        batching.begin_batch("DELTA")

    assert exc_info.value.errno == error_number
    assert str(target_dir) not in str(exc_info.value)
    assert _tree_bytes(target_dir) == tree_before
    retry_batch = batching.begin_batch("DELTA")
    batching.rollback_batch(retry_batch)
    assert core._active_batches == {}


@pytest.mark.parametrize("locator_kind", ("symlink", "regular_file"))
def test_begin_batch_rejects_non_directory_locator_and_releases_writer(
    tmp_path: Path,
    locator_kind: str,
) -> None:
    """begin-time symlink/regular file 必须 fail closed 且释放 reservation/writer。

    Args:
        tmp_path: pytest 临时目录。
        locator_kind: symlink 或 regular-file target fixture。

    Returns:
        无。

    Raises:
        AssertionError: locator 被改变、内部 reservation 泄漏或 retry 无法取得 writer 时抛出。
        OSError: 测试环境无法创建 locator fixture 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, _, core = _build_repositories(workspace_root)
    target_dir = workspace_root / "portfolio" / "DELTA"
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    regular_payload = b"foreign ticker locator"
    symlink_target = tmp_path / "outside-company"
    if locator_kind == "symlink":
        symlink_target.mkdir()
        target_dir.symlink_to(symlink_target, target_is_directory=True)
        expected_link = os.readlink(target_dir)
    else:
        target_dir.write_bytes(regular_payload)
        expected_link = None

    with pytest.raises(CompanyTickerIdentityCorruptionError) as exc_info:
        batching.begin_batch("DELTA")
    assert exc_info.value.kind == "invalid_descriptor"

    target_stat = os.lstat(target_dir)
    if locator_kind == "symlink":
        assert stat.S_ISLNK(target_stat.st_mode)
        assert os.readlink(target_dir) == expected_link
    else:
        assert stat.S_ISREG(target_stat.st_mode)
        assert target_dir.read_bytes() == regular_payload
    assert core._active_batches == {}
    assert core._active_transaction_by_ticker == {}
    assert core._reserved_batch_tickers == set()
    assert tuple(core.batch_root.iterdir()) == ()

    target_dir.unlink()
    retry_batch = batching.begin_batch("DELTA")
    batching.rollback_batch(retry_batch)
    assert core._active_batches == {}
    assert core._active_transaction_by_ticker == {}
    assert core._reserved_batch_tickers == set()


@pytest.mark.parametrize("error_number", (errno.EACCES, errno.EIO))
def test_commit_backup_lstat_io_failure_precedes_replace_and_preserves_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    """commit-time backup lstat I/O failure 必须在 replace 前 fail closed。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        error_number: 注入的 permission 或普通 I/O errno。

    Returns:
        无。

    Raises:
        AssertionError: I/O 被误判为 missing、发生 replace 或 published/evidence 改变时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    initial_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(company, _meta("DELTA", aliases=("DLTA",)), batch=initial_batch)
    batching.commit_batch(initial_batch)
    target_dir = workspace_root / "portfolio" / "DELTA"
    tree_before = _tree_bytes(target_dir)
    backup_evidence_before = _tree_bytes(core.backup_root)
    update_batch = batching.begin_batch("DELTA")
    update_state = core._active_batches[update_batch.transaction_id]
    replace_forbidden = _ReplaceDirectoryForbidden()
    monkeypatch.setattr(core, "_replace_directory", replace_forbidden)
    monkeypatch.setattr(
        storage_infra_module.os,
        "lstat",
        _OneShotLstatFailure(
            target_dir,
            error_number,
            storage_infra_module.os.lstat,
        ),
    )

    with pytest.raises(OSError) as exc_info:
        batching.commit_batch(update_batch)

    assert exc_info.value.errno == error_number
    assert str(target_dir) not in str(exc_info.value)
    assert replace_forbidden.calls == []
    assert _tree_bytes(target_dir) == tree_before
    assert _tree_bytes(core.backup_root) == backup_evidence_before
    assert not update_state.backup_dir.exists()
    assert not update_state.staging_root_dir.exists()
    assert core._active_batches == {}


def test_commit_backup_rejects_non_directory_before_replace_and_preserves_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit-time regular-file target 必须在 replace 前拒绝并保持 locator/evidence。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: non-directory 被当作 missing、发生 replace 或 evidence 改变时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    initial_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(company, _meta("DELTA", aliases=("DLTA",)), batch=initial_batch)
    batching.commit_batch(initial_batch)
    target_dir = workspace_root / "portfolio" / "DELTA"
    update_batch = batching.begin_batch("DELTA")
    update_state = core._active_batches[update_batch.transaction_id]
    parked_tree = workspace_root / "parked-delta"
    target_dir.rename(parked_tree)
    foreign_payload = b"foreign commit-time locator"
    target_dir.write_bytes(foreign_payload)
    parked_tree_before = _tree_bytes(parked_tree)
    backup_evidence_before = _tree_bytes(core.backup_root)
    replace_forbidden = _ReplaceDirectoryForbidden()
    monkeypatch.setattr(core, "_replace_directory", replace_forbidden)

    with pytest.raises(CompanyTickerIdentityCorruptionError) as exc_info:
        batching.commit_batch(update_batch)
    assert exc_info.value.kind == "invalid_descriptor"

    assert replace_forbidden.calls == []
    assert stat.S_ISREG(os.lstat(target_dir).st_mode)
    assert target_dir.read_bytes() == foreign_payload
    assert _tree_bytes(parked_tree) == parked_tree_before
    assert _tree_bytes(core.backup_root) == backup_evidence_before
    assert not update_state.backup_dir.exists()
    assert not update_state.staging_root_dir.exists()
    assert core._active_batches == {}


def test_existing_corpus_document_only_commit_does_not_take_global_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既有 corpus 的 document-only commit 不得取得 recovery/identity guards。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: document-only path 误取全局 guard 时抛出。
    """

    batching, _, core = _build_repositories(tmp_path / "workspace")
    first_batch = batching.begin_batch("DELTA")
    batching.commit_batch(first_batch)
    monkeypatch.setattr(core, "_acquire_recovery_lock", _raise_lock_acquire_failure)
    monkeypatch.setattr(core, "_acquire_company_identity_guard", _raise_lock_acquire_failure)

    document_batch = batching.begin_batch("DELTA")
    batching.commit_batch(document_batch)


def test_alias_resolution_lock_order_is_identity_then_sorted_publications(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """alias read 必须按 identity -> sorted publication 的固定方向取锁。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: read lock 顺序反向或 publication 未排序时抛出。
    """

    batching, company, core = _build_repositories(tmp_path / "workspace")
    for ticker, alias in (("MSFT", "MSF"), ("DELTA", "DLTA")):
        batch = batching.begin_batch(ticker)
        stage_company_meta_fixture(company, _meta(ticker, aliases=(alias,)), batch=batch)
        batching.commit_batch(batch)
    recorder = _LockAcquisitionRecorder(core._acquire_lock_token)
    monkeypatch.setattr(core, "_acquire_lock_token", recorder)

    assert company.resolve_company_ticker("msf") == "MSFT"

    assert recorder.names[0] == "company_identity.lock"
    publication_names = recorder.names[1:]
    assert publication_names
    assert publication_names == sorted(publication_names)
    assert all(name.endswith(".publication.lock") for name in publication_names)
    assert "batch_recovery.lock" not in recorder.names


@pytest.mark.parametrize(
    "failure_point",
    ("recovery", "identity", "scan_publication", "target_publication"),
)
def test_identity_commit_acquire_failures_happen_before_first_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    """四层 identity commit guard acquire failure 均须在首次 replace 前失败。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        failure_point: recovery、identity、scan 或 target publication 注入点。

    Returns:
        无。

    Raises:
        AssertionError: acquire failure 后发生 physical replace 或 tree 改变时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    initial_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(company, _meta("DELTA", aliases=("OLD",)), batch=initial_batch)
    batching.commit_batch(initial_batch)
    target_dir = workspace_root / "portfolio" / "DELTA"
    tree_before = _tree_bytes(target_dir)
    update_batch = batching.begin_batch("DELTA")
    stage_company_meta_fixture(
        company,
        CompanyMeta(
            company_id="company-delta-v2",
            company_name="Delta v2",
            ticker_identity=build_company_ticker_identity("DELTA", ("NEW",)),
            resolver_version="test-v2",
            updated_at="observed-v2",
        ),
        batch=update_batch,
    )
    replace_forbidden = _ReplaceDirectoryForbidden()
    monkeypatch.setattr(core, "_replace_directory", replace_forbidden)
    if failure_point == "recovery":
        monkeypatch.setattr(core, "_acquire_recovery_lock", _raise_lock_acquire_failure)
    elif failure_point == "identity":
        monkeypatch.setattr(core, "_acquire_company_identity_guard", _raise_lock_acquire_failure)
    elif failure_point == "scan_publication":
        monkeypatch.setattr(
            core,
            "_acquire_publication_guard_for_key",
            _NthPublicationAcquireFailure(core._acquire_publication_guard_for_key, 1),
        )
    else:
        monkeypatch.setattr(
            core,
            "_acquire_publication_guard",
            _NthPublicationAcquireFailure(core._acquire_publication_guard, 2),
        )

    with pytest.raises(RuntimeFileLockError):
        batching.commit_batch(update_batch)

    assert replace_forbidden.calls == []
    assert _tree_bytes(target_dir) == tree_before


def test_alias_conflict_survives_identity_release_failure_with_bounded_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """alias conflict 必须压过后续 identity release failure 并保留有界诊断。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: release failure 覆盖冲突主异常或诊断泄漏路径时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    existing = batching.begin_batch("MSFT")
    batching.commit_batch(existing)
    incoming = batching.begin_batch("DELTA")
    stage_company_meta_fixture(company, _meta("DELTA", aliases=("MSFT",)), batch=incoming)
    tree_before = _tree_bytes(workspace_root / "portfolio" / "MSFT")
    monkeypatch.setattr(
        core,
        "_release_lock_token",
        _ReleaseFailureAfterRelease(core._release_lock_token, "company_identity.lock"),
    )

    with pytest.raises(CompanyTickerAliasConflictError) as exc_info:
        batching.commit_batch(incoming)

    notes = tuple(exc_info.value.__notes__)
    assert notes == ("company identity guard release failed: error_type=RuntimeFileLockError",)
    assert str(workspace_root) not in notes[0]
    assert _tree_bytes(workspace_root / "portfolio" / "MSFT") == tree_before
    assert not (workspace_root / "portfolio" / "DELTA").exists()


def test_alias_conflict_survives_publication_release_failure_with_bounded_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """publication guarded scan 的 conflict 必须压过同 guard release failure。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: publication release failure 覆盖 typed primary 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    existing = batching.begin_batch("MSFT")
    batching.commit_batch(existing)
    incoming = batching.begin_batch("DELTA")
    stage_company_meta_fixture(company, _meta("DELTA", aliases=("MSFT",)), batch=incoming)
    publication_lock_name = core._publication_lock_path("MSFT").name
    monkeypatch.setattr(core, "_read_published_company_identity", _raise_published_alias_conflict)
    monkeypatch.setattr(
        core,
        "_release_lock_token",
        _ReleaseFailureAfterRelease(core._release_lock_token, publication_lock_name),
    )

    with pytest.raises(CompanyTickerAliasConflictError) as exc_info:
        batching.commit_batch(incoming)

    notes = tuple(exc_info.value.__notes__)
    assert notes == ("published corpus publication guard release失败：injected release failure",)
    assert str(workspace_root) not in notes[0]
    assert not (workspace_root / "portfolio" / "DELTA").exists()


@pytest.mark.parametrize("healthy_first", (True, False))
def test_meta_less_canonical_and_healthy_alias_conflict_in_both_directions(
    tmp_path: Path,
    healthy_first: bool,
) -> None:
    """meta-less canonical 与 healthy alias 的冲突必须与提交方向无关。

    Args:
        tmp_path: pytest 临时目录。
        healthy_first: 是否先发布带 alias 的 healthy corpus。

    Returns:
        无。

    Raises:
        AssertionError: 任一方向未冲突或已发布 winner 被改变时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, _ = _build_repositories(workspace_root)
    if healthy_first:
        winner_batch = batching.begin_batch("DELTA")
        stage_company_meta_fixture(company, _meta("DELTA", aliases=("MATERIAL",)), batch=winner_batch)
        batching.commit_batch(winner_batch)
        incoming_batch = batching.begin_batch("MATERIAL")
        winner = "DELTA"
        absent = "MATERIAL"
    else:
        winner_batch = batching.begin_batch("MATERIAL")
        batching.commit_batch(winner_batch)
        incoming_batch = batching.begin_batch("DELTA")
        stage_company_meta_fixture(company, _meta("DELTA", aliases=("MATERIAL",)), batch=incoming_batch)
        winner = "MATERIAL"
        absent = "DELTA"
    winner_dir = workspace_root / "portfolio" / winner
    tree_before = _tree_bytes(winner_dir)

    with pytest.raises(CompanyTickerAliasConflictError):
        batching.commit_batch(incoming_batch)

    assert company.resolve_company_ticker("MATERIAL") == winner
    assert _tree_bytes(winner_dir) == tree_before
    assert not (workspace_root / "portfolio" / absent).exists()


def test_swapped_orphan_is_recovered_before_interleaving_conflict_validation(
    tmp_path: Path,
) -> None:
    """B commit 必须先恢复 A 的 pre-COMMITTED swap，再按 restored identity 冲突。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: B 看到 A 未提交 alias 或 recovery 晚于 validation 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    initial = batching.begin_batch("ALPHA")
    stage_company_meta_fixture(company, _meta("ALPHA", aliases=("OLD",)), batch=initial)
    batching.commit_batch(initial)
    original_tree = _tree_bytes(workspace_root / "portfolio" / "ALPHA")
    orphan_batch = batching.begin_batch("ALPHA")
    _replace_staged_aliases(core, orphan_batch, aliases=("NEW",))
    interleaving_batch = batching.begin_batch("BETA")
    stage_company_meta_fixture(company, _meta("BETA", aliases=("OLD",)), batch=interleaving_batch)
    _leave_batch_swapped_before_committed(core, orphan_batch)

    with pytest.raises(CompanyTickerAliasConflictError) as exc_info:
        batching.commit_batch(interleaving_batch)

    assert exc_info.value.alias == "OLD"
    assert exc_info.value.existing_canonical_ticker == "ALPHA"
    assert _tree_bytes(workspace_root / "portfolio" / "ALPHA") == original_tree
    assert company.resolve_company_ticker("OLD") == "ALPHA"
    assert company.resolve_company_ticker("NEW") is None
    assert not (workspace_root / "portfolio" / "BETA").exists()


def test_recovery_holds_identity_barrier_across_physical_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """read 必须等待 orphan restore 完成，不能观察 swap/restore 中间 identity。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: read 在 recovery identity barrier 内提前完成时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    recovery_set = build_fs_repository_set(workspace_root=workspace_root)
    recovery_core = recovery_set.core
    read_set = build_fs_repository_set(workspace_root=workspace_root)
    read_company = FsCompanyMetaRepository(workspace_root, repository_set=read_set)
    initial = batching.begin_batch("ALPHA")
    stage_company_meta_fixture(company, _meta("ALPHA", aliases=("OLD",)), batch=initial)
    batching.commit_batch(initial)
    orphan_batch = batching.begin_batch("ALPHA")
    _replace_staged_aliases(core, orphan_batch, aliases=("NEW",))
    _leave_batch_swapped_before_committed(core, orphan_batch)
    blocker = _BlockingFirstReplace(recovery_core._replace_directory)
    read_signal = _IdentityAcquireSignal(read_set.core._acquire_company_identity_guard)
    monkeypatch.setattr(recovery_core, "_replace_directory", blocker)
    monkeypatch.setattr(read_set.core, "_acquire_company_identity_guard", read_signal)

    with ThreadPoolExecutor(max_workers=2) as executor:
        recovery_future = executor.submit(recovery_core.recover_orphan_batches)
        assert blocker.entered.wait(timeout=5)
        read_future = executor.submit(read_company.resolve_company_ticker, "OLD")
        assert read_signal.entered.wait(timeout=5)
        assert not read_future.done()
        blocker.allow.set()
        recovery_actions = recovery_future.result(timeout=5)
        resolved = read_future.result(timeout=5)

    assert any("restore backup ticker=ALPHA" in action for action in recovery_actions)
    assert resolved == "ALPHA"
    assert read_company.resolve_company_ticker("NEW") is None


def test_orphan_identity_acquire_failure_preserves_recovery_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """orphan recovery identity acquire failure 必须发生在 restore 前并保留 evidence。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: acquire failure 后 replace 或 evidence 改变时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    recovery_core = build_fs_repository_set(workspace_root=workspace_root).core
    initial = batching.begin_batch("ALPHA")
    stage_company_meta_fixture(company, _meta("ALPHA", aliases=("OLD",)), batch=initial)
    batching.commit_batch(initial)
    orphan_batch = batching.begin_batch("ALPHA")
    _replace_staged_aliases(core, orphan_batch, aliases=("NEW",))
    token_dir, backup_dir = _leave_batch_swapped_before_committed(core, orphan_batch)
    tree_before = _tree_bytes(workspace_root)
    replace_forbidden = _ReplaceDirectoryForbidden()
    monkeypatch.setattr(recovery_core, "_acquire_company_identity_guard", _raise_lock_acquire_failure)
    monkeypatch.setattr(recovery_core, "_replace_directory", replace_forbidden)

    with pytest.raises(RuntimeFileLockError):
        recovery_core.recover_orphan_batches()

    assert replace_forbidden.calls == []
    assert _tree_bytes(workspace_root) == tree_before
    assert token_dir.is_dir()
    assert backup_dir.is_dir()


def test_orphan_identity_release_failure_preserves_primary_and_completed_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """orphan restore 成功后的 identity release failure 应抛出且不撤销已完成恢复。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: release failure 隐藏、恢复未完成或 evidence 清理错误时抛出。
    """

    workspace_root = tmp_path / "workspace"
    batching, company, core = _build_repositories(workspace_root)
    recovery_set = build_fs_repository_set(workspace_root=workspace_root)
    recovery_core = recovery_set.core
    initial = batching.begin_batch("ALPHA")
    stage_company_meta_fixture(company, _meta("ALPHA", aliases=("OLD",)), batch=initial)
    batching.commit_batch(initial)
    original_tree = _tree_bytes(workspace_root / "portfolio" / "ALPHA")
    orphan_batch = batching.begin_batch("ALPHA")
    _replace_staged_aliases(core, orphan_batch, aliases=("NEW",))
    token_dir, backup_dir = _leave_batch_swapped_before_committed(core, orphan_batch)
    monkeypatch.setattr(
        recovery_core,
        "_release_lock_token",
        _ReleaseFailureAfterRelease(recovery_core._release_lock_token, "company_identity.lock"),
    )

    with pytest.raises(RuntimeFileLockError, match="injected release failure"):
        recovery_core.recover_orphan_batches()

    recovered_company = FsCompanyMetaRepository(workspace_root, repository_set=recovery_set)
    assert _tree_bytes(workspace_root / "portfolio" / "ALPHA") == original_tree
    assert recovered_company.resolve_company_ticker("OLD") == "ALPHA"
    assert recovered_company.resolve_company_ticker("NEW") is None
    assert not token_dir.exists()
    assert not backup_dir.exists()


def _build_repositories(
    workspace_root: Path,
) -> tuple[FsBatchingRepository, FsCompanyMetaRepository, FsStorageCore]:
    """构造共享同一 core 的 batching/company repositories。

    Args:
        workspace_root: Fins workspace root。

    Returns:
        batching repository、company repository 与真实 core。

    Raises:
        OSError: repository 初始化失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    return (
        FsBatchingRepository(workspace_root, repository_set=repository_set),
        FsCompanyMetaRepository(workspace_root, repository_set=repository_set),
        repository_set.core,
    )


def _commit_meta_in_process(
    workspace_root: Path,
    aliases: tuple[str, ...],
    resolver_version: str,
    company_id: str,
    company_name: str,
    connection: Connection,
) -> None:
    """子进程等待 barrier 后提交一份 same-canonical CompanyMeta。

    Args:
        workspace_root: Fins workspace root。
        aliases: 子进程拟议 aliases。
        resolver_version: 子进程 producer resolver version。
        company_id: 子进程拟议 company id。
        company_name: 子进程拟议 company name。
        connection: 父子进程同步与结果通道。

    Returns:
        无。

    Raises:
        无；异常类型通过 connection 返回父进程。
    """

    try:
        if connection.recv() != "go":
            connection.send("invalid-command")
            return
        batching, company, _ = _build_repositories(workspace_root)
        batch = batching.begin_batch("DELTA")
        stage_company_meta_fixture(
            company,
            CompanyMeta(
                company_id=company_id,
                company_name=company_name,
                ticker_identity=build_company_ticker_identity("DELTA", aliases),
                resolver_version=resolver_version,
                updated_at="child-observed",
            ),
            batch=batch,
        )
        batching.commit_batch(batch)
        connection.send("ok")
    except Exception as exc:
        connection.send(f"error:{exc.__class__.__name__}")
    finally:
        connection.close()


def _commit_upload_alias_in_process(
    workspace_root: Path,
    alias: str,
    connection: Connection,
) -> None:
    """子进程执行真实 upload company-meta producer 并提交 alias。

    Args:
        workspace_root: Fins workspace root。
        alias: 本进程 material alias。
        connection: 父子进程同步与结果通道。

    Returns:
        无。

    Raises:
        无；异常类型通过 connection 返回父进程。
    """

    try:
        if connection.recv() != "go":
            connection.send("invalid-command")
            return
        batching, company, _ = _build_repositories(workspace_root)
        batch = batching.begin_batch("DELTA")
        stage_company_meta_for_upload(
            repository=company,
            ticker="DELTA",
            action="update",
            company_name="Delta Inc.",
            ticker_aliases=(alias,),
            batch=batch,
        )
        batching.commit_batch(batch)
        connection.send("ok")
    except Exception as exc:
        connection.send(f"error:{exc.__class__.__name__}")
    finally:
        connection.close()


def _run_meta_commit_process(
    workspace_root: Path,
    *,
    aliases: tuple[str, ...],
    resolver_version: str,
    company_id: str,
    company_name: str,
) -> None:
    """spawn 单个 metadata writer 并要求成功退出。

    Args:
        workspace_root: Fins workspace root。
        aliases: 子进程拟议 aliases。
        resolver_version: 子进程 resolver version。
        company_id: 子进程 company id。
        company_name: 子进程 company name。

    Returns:
        无。

    Raises:
        AssertionError: 子进程提交或退出失败时抛出。
    """

    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe()
    process = context.Process(
        target=_commit_meta_in_process,
        args=(
            workspace_root,
            aliases,
            resolver_version,
            company_id,
            company_name,
            child_connection,
        ),
    )
    process.start()
    child_connection.close()
    parent_connection.send("go")
    result = parent_connection.recv()
    parent_connection.close()
    _join_successful_process(process)
    assert result == "ok"


def _join_successful_process(process: BaseProcess) -> None:
    """有界等待 spawn process 并要求零退出码。

    Args:
        process: 已启动的子进程。

    Returns:
        无。

    Raises:
        AssertionError: 子进程超时或非零退出时抛出。
    """

    process.join(timeout=10)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        raise AssertionError("spawn writer process 超时")
    assert process.exitcode == 0


def _raise_lock_acquire_failure() -> NoReturn:
    """注入无路径 lock acquisition failure。

    Args:
        无。

    Returns:
        不返回。

    Raises:
        RuntimeFileLockError: 每次调用均抛出。
    """

    raise RuntimeFileLockError("injected lock acquire failure")


def _raise_published_alias_conflict(
    directory: Path,
    *,
    expected_storage_key: str,
    known_directory_stat: os.stat_result,
) -> NoReturn:
    """在 publication guarded durable read seam 注入 typed alias conflict。

    Args:
        directory: 被扫描的 published directory。
        expected_storage_key: descriptor expected key。
        known_directory_stat: 已显式 lstat 的目录状态。

    Returns:
        不返回。

    Raises:
        CompanyTickerAliasConflictError: 每次调用均抛出。
    """

    del directory, expected_storage_key, known_directory_stat
    raise CompanyTickerAliasConflictError(
        alias="MSFT",
        existing_canonical_ticker="MSFT",
        incoming_canonical_ticker="DELTA",
    )


def _replace_staged_aliases(
    core: FsStorageCore,
    batch: BatchToken,
    *,
    aliases: tuple[str, ...],
) -> None:
    """在 crash fixture 中把 staging CompanyMeta 改成指定 aliases。

    Args:
        core: 持有 active batch 的 storage core。
        batch: active batch capability。
        aliases: crash 前尚未 committed 的 aliases。

    Returns:
        无。

    Raises:
        KeyError: batch 或 meta payload 缺失时抛出。
        OSError: fixture 读写失败时抛出。
    """

    state = core._active_batches[batch.transaction_id]
    meta_path = state.staging_ticker_dir / "meta.json"
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("staging meta fixture 必须为 JSON object")
    payload["ticker_aliases"] = list(aliases)
    meta_path.write_text(json.dumps(payload), encoding="utf-8")


def _leave_batch_swapped_before_committed(
    core: FsStorageCore,
    batch: BatchToken,
) -> tuple[Path, Path]:
    """构造 target 已 swap、journal 未到 COMMITTED 的真实 orphan evidence。

    Args:
        core: 持有 active batch 的 storage core。
        batch: 要模拟进程崩溃的 batch capability。

    Returns:
        transaction token directory 与 backup directory。

    Raises:
        KeyError: batch 不活动时抛出。
        OSError: physical swap 或 journal 写入失败时抛出。
    """

    state = core._active_batches[batch.transaction_id]
    if state.target_ticker_dir.exists():
        core._replace_directory(state.target_ticker_dir, state.backup_dir)
    core._write_batch_journal(state, storage_infra_module._PHASE_BACKED_UP_TARGET)
    core._replace_directory(state.staging_ticker_dir, state.target_ticker_dir)
    core._write_batch_journal(state, storage_infra_module._PHASE_SWAPPED_TARGET)
    token_dir = state.staging_root_dir
    backup_dir = state.backup_dir
    core._close_active_batch(state)
    return token_dir, backup_dir


def _meta(ticker: str, *, aliases: tuple[str, ...]) -> CompanyMeta:
    """构造 storage contract 测试 CompanyMeta。

    Args:
        ticker: canonical ticker。
        aliases: accepted aliases。

    Returns:
        严格 CompanyMeta。

    Raises:
        ValueError: ticker identity 非法时抛出。
    """

    return CompanyMeta(
        company_id=f"company-{ticker}",
        company_name=f"{ticker} Inc.",
        ticker_identity=build_company_ticker_identity(ticker, aliases),
        resolver_version="test-v1",
        updated_at="observed",
    )


def _commit_after_barrier(
    repository: FsBatchingRepository,
    batch: BatchToken,
    barrier: Barrier,
) -> Exception | None:
    """让两个独立 core 同时进入 commit 并捕获 typed 结果。

    Args:
        repository: batch capability owner。
        batch: 待提交 batch。
        barrier: 两方同步屏障。

    Returns:
        成功返回 ``None``；失败返回原始异常。

    Raises:
        无。
    """

    barrier.wait(timeout=5)
    try:
        repository.commit_batch(batch)
    except Exception as exc:
        return exc
    return None


def _identity_descriptor_file(identity_directory: Path) -> Path:
    """枚举 storage owner 写入的唯一 ticker descriptor。

    Args:
        identity_directory: published ticker directory。

    Returns:
        唯一隐藏 JSON descriptor。

    Raises:
        AssertionError: descriptor 候选不唯一时抛出。
    """

    candidates = tuple(
        path for path in identity_directory.iterdir() if path.name.startswith(".") and path.suffix == ".json"
    )
    assert len(candidates) == 1
    return candidates[0]


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """读取目录树中全部 regular files 的相对路径与内容。

    Args:
        root: 待快照目录。

    Returns:
        相对 POSIX path 到 exact bytes 的映射。

    Raises:
        OSError: 枚举或读取失败时抛出。
    """

    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}
