"""F5 稳定根、可信年度和财政日历 owner；真实 Fs 与冻结官方 Raw 正例。"""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.document_models import SourceDocumentStateChangeRequest
from dayu.fins.downloaders import hkexnews_downloader as hk
from dayu.fins.pipelines.cn_download_models import CnReportPeriodProjection, CnReportHeadMeta, HkexnewsRawAnnouncement
from dayu.fins.pipelines.cn_report_selection import (
    hk_annual_end_date, local_hk_annual_ends, resolve_hk_report_period, select_hkexnews_report_candidates,
)
from dayu.fins.pipelines.hk_fiscal_calendar import relevant_annual_end_dates
from dayu.fins.storage import (
    CompanyTickerIdentityCorruptionError, FsBatchingRepository, FsDocumentBlobRepository,
    FsSourceDocumentRepository, SourceIntegrityPreflightError, SourceIntegrityPreflightReason,
    SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from tests.fins.test_cn_report_selection import _hk_query, _hk_raw, _head_meta
from tests.fins.test_fins_storage_atomicity import (
    _stage_meta_view_pair, _MetaViewRenameBarrier, _PublicationBarrier, _active_batch_paths,
    _create_complete_source, _identity_descriptor_file,
)

_CAPTURE = Path(__file__).resolve().parent / "fixtures/hk_f5_official_raw"
_TickerCorruption = Literal["missing", "malformed", "symlink", "wrong_canonical"]
_PUBLISHED_TICKER_CORRUPTIONS: tuple[_TickerCorruption, ...] = (
    "missing", "malformed", "symlink", "wrong_canonical",
)
_OFFICIAL_ASSET_HASHES: tuple[tuple[str, str], ...] = (
    ("annual-results.body", "62582cfbfa1aaeb588971f339bbbb33767420528718b916877d0e05d0c6cb94a"),
    ("annual-results.json", "f9e81c7005ec04e34c66779f45cd14fa3d3c17f961994f018471befb20c21fcf"),
    ("quarter-results.body", "0d6bbb3ba351b9a8cdd1966dea75234efb9dbfdb686fba89a289cd5924b59f32"),
    ("quarter-results.json", "c00ebf3a542048da96e335e7ab5f790a7cbfbdf6de06c14a6695fa64ee6331dc"),
    ("owner-validation.json", "bb1ef2ffc5211ffbcdd87d28a119aa59b1b07e6c6b89b5ac4813f1d497160660"),
    ("result.json", "27a633a3bde1c1c26bd01d62d52e03b405e4d8e286fbdc7d628e5ddd94004f56"),
)


def _damage_published_ticker_descriptor(ticker_dir: Path, corruption: _TickerCorruption) -> None:
    """仅损坏已发布 ticker descriptor，保留来源文档和 manifest 原字节。

    参数：ticker_dir 为真实发布公司目录；corruption 为损坏形态。
    返回：无。
    异常：descriptor 不唯一时断言失败；文件操作异常原样传播。
    """
    descriptor = _identity_descriptor_file(ticker_dir)
    if corruption == "missing":
        descriptor.unlink()
    elif corruption == "malformed":
        descriptor.write_text("{}", encoding="utf-8")
    elif corruption == "symlink":
        outside = ticker_dir.parent.parent / "outside-descriptor.json"
        outside.write_bytes(descriptor.read_bytes())
        descriptor.unlink()
        descriptor.symlink_to(outside)
    else:
        payload: JsonValue = json.loads(descriptor.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        payload["external_identity"] = "MSFT"
        descriptor.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize("corruption", _PUBLISHED_TICKER_CORRUPTIONS)
@pytest.mark.parametrize("kind", (SourceKind.FILING, SourceKind.MATERIAL))
@pytest.mark.parametrize("reader", ("get", "view", "list", "list_all"))
def test_published_source_reads_reject_ticker_descriptor_corruption(
    tmp_path: Path, corruption: _TickerCorruption, kind: SourceKind, reader: str,
) -> None:
    """正式发布完整来源后，三个读入口均由 ticker 身份 owner 拒绝损坏。

    参数：tmp_path 为真实仓储根；corruption 为 ticker 损坏；kind 为来源类型；reader 为入口。
    返回：无。
    异常：错误类别漂移、损坏被当正常读取或 guard 未释放时断言失败。
    """
    repo = build_fs_repository_set(workspace_root=tmp_path)
    batching = FsBatchingRepository(tmp_path, repository_set=repo)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repo)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repo)
    batch = batching.begin_batch("AAPL")
    _create_complete_source(source, blob, batch=batch, document_id="A", source_kind=kind)
    batching.commit_batch(batch)
    ticker_dir = tmp_path / "portfolio" / "AAPL"
    descriptor = _identity_descriptor_file(ticker_dir)
    original_descriptor = descriptor.read_bytes()
    original_meta = source.get_source_meta("AAPL", "A", kind)
    assert source.classify_source_integrity("AAPL", "A", kind).status is SourceIntegrityStatus.COMPLETE
    _damage_published_ticker_descriptor(ticker_dir, corruption)
    with pytest.raises(CompanyTickerIdentityCorruptionError) as raised:
        if reader == "get":
            source.get_source_meta("AAPL", "A", kind)
        elif reader == "view":
            source.read_source_meta_view("AAPL", kind)
        elif reader == "list":
            source.list_source_document_ids("AAPL", kind)
        else:
            repo.core.list_document_ids("AAPL")
    assert raised.value.kind == "invalid_descriptor"
    # 修复同一 ticker descriptor 后使用独立 core 写者，证明异常路径释放 publication guard。
    if descriptor.is_symlink():
        descriptor.unlink()
    descriptor.write_bytes(original_descriptor)
    fresh_batching = FsBatchingRepository(tmp_path)
    next_batch = fresh_batching.begin_batch("AAPL")
    fresh_batching.rollback_batch(next_batch)
    assert source.get_source_meta("AAPL", "A", kind) == original_meta


@pytest.mark.parametrize("corruption", _PUBLISHED_TICKER_CORRUPTIONS)
@pytest.mark.parametrize("kind", (SourceKind.FILING, SourceKind.MATERIAL))
def test_ticker_corruption_preserves_locator_integrity_and_staging_contracts(
    tmp_path: Path, corruption: _TickerCorruption, kind: SourceKind,
) -> None:
    """published 身份、whole-kind 和真实 staging 各保留原错误/能力边界。

    参数：tmp_path 为真实根；corruption 为 ticker 损坏；kind 为来源类型。
    返回：无。
    异常：locator typed kind、whole-kind unsafe 或 staging 独立性漂移时断言失败。
    """
    repo = build_fs_repository_set(workspace_root=tmp_path)
    batching = FsBatchingRepository(tmp_path, repository_set=repo)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repo)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repo)
    batch = batching.begin_batch("AAPL")
    _create_complete_source(source, blob, batch=batch, document_id="A", source_kind=kind)
    batching.commit_batch(batch)
    staging_batch = batching.begin_batch("AAPL")
    _create_complete_source(source, blob, batch=staging_batch, document_id="B", source_kind=kind)
    try:
        _damage_published_ticker_descriptor(tmp_path / "portfolio" / "AAPL", corruption)
        with pytest.raises(CompanyTickerIdentityCorruptionError) as locator_error:
            source.get_source_document_locator("AAPL", "A", kind)
        assert locator_error.value.kind == "invalid_descriptor"
        with pytest.raises(SourceIntegrityPreflightError) as integrity_error:
            source.read_source_meta_integrity_view("AAPL", kind, batch=None)
        assert integrity_error.value.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
        staged = source.read_source_meta_integrity_view("AAPL", kind, batch=staging_batch)
        assert [entry.document_id for entry in staged] == ["A", "B"]
        assert all(entry.integrity.status is SourceIntegrityStatus.COMPLETE for entry in staged)
    finally:
        batching.rollback_batch(staging_batch)
    with pytest.raises(ValueError):
        source.read_source_meta_integrity_view("AAPL", kind, batch=staging_batch)


@pytest.mark.parametrize("kind", (SourceKind.FILING, SourceKind.MATERIAL))
def test_published_source_normal_missing_complete_and_deleted_controls(tmp_path: Path, kind: SourceKind) -> None:
    """正常不存在、完整来源及逻辑删除保持 raw 读取与完整性分类原契约。

    参数：tmp_path 为真实根；kind 为来源类型。
    返回：无。
    异常：正常缺席误报 ticker corruption 或原分类/完整元数据漂移时断言失败。
    """
    repo = build_fs_repository_set(workspace_root=tmp_path)
    batching = FsBatchingRepository(tmp_path, repository_set=repo)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repo)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repo)
    assert source.list_source_document_ids("AAPL", kind) == []
    assert repo.core.list_document_ids("AAPL") == []
    assert source.read_source_meta_view("AAPL", kind).entries == ()
    assert source.read_source_meta_integrity_view("AAPL", kind, batch=None) == ()
    with pytest.raises(FileNotFoundError):
        source.get_source_meta("AAPL", "absent", kind)
    batch = batching.begin_batch("AAPL")
    _create_complete_source(source, blob, batch=batch, document_id="A", source_kind=kind)
    batching.commit_batch(batch)
    meta = source.get_source_meta("AAPL", "A", kind)
    assert source.read_source_meta_view("AAPL", kind).entries[0].source_meta == meta
    complete = source.read_source_meta_integrity_view("AAPL", kind, batch=None)
    assert complete[0].source_meta == meta
    assert complete[0].integrity.status is SourceIntegrityStatus.COMPLETE
    assert source.classify_source_integrity("AAPL", "absent", kind).status is SourceIntegrityStatus.MISSING
    with pytest.raises(FileNotFoundError):
        source.get_source_meta("AAPL", "absent", kind)
    batch = batching.begin_batch("AAPL")
    source.delete_source_document(SourceDocumentStateChangeRequest(ticker="AAPL", document_id="A", source_kind=kind.value), batch=batch)
    batching.commit_batch(batch)
    deleted = source.get_source_meta("AAPL", "A", kind)
    assert deleted["is_deleted"] is True
    assert source.list_source_document_ids("AAPL", kind) == ["A"]
    assert source.read_source_meta_view("AAPL", kind).entries[0].source_meta == deleted
    deleted_entry = source.read_source_meta_integrity_view("AAPL", kind, batch=None)[0]
    assert deleted_entry.source_meta == deleted
    # 物理完整性与逻辑删除是独立事实；删除不等于物理缺席。
    assert deleted_entry.integrity.status is SourceIntegrityStatus.COMPLETE
    assert source.classify_source_integrity("AAPL", "A", kind).status is SourceIntegrityStatus.COMPLETE


@pytest.mark.parametrize("distance", (365, 366, 367))
def test_single_calendar_owner_has_exact_neighbor_boundary(distance: int) -> None:
    """参数为间隔天数；返回无；366 天边界漂移时断言失败。"""
    end = date(2025, 9, 30)
    anchors = (end - timedelta(days=distance), end + timedelta(days=distance))
    expected = tuple(sorted(set(anchors))) if distance <= 366 else ()
    assert relevant_annual_end_dates(end, anchors + anchors) == expected
    assert resolve_hk_report_period(title="截至2025年9月30日止第三季度業績", category_text="季度業績", annual_ends=(date(2020, 6, 30),)) == (2025, _head_projection())


def _head_projection() -> CnReportPeriodProjection:
    """参数无；返回 Q3 owner 投影；构造异常原样传播。"""
    return CnReportPeriodProjection(identity_period="Q3", covered_periods=("Q3",))


def test_same_evidence_local_remote_english_and_conflict() -> None:
    """参数无；返回无；同证据窄宽不一致、英文被排证或未知触发 HEAD 时断言失败。"""
    quarter = _hk_raw(document_id="B", title="截至2025年9月30日止三個月業績", category_text="季度業績", filing_date="2025-11-13")
    annual = replace(_hk_raw(document_id="annual", title="ANNUAL RESULTS FOR YEAR ENDED 31 DECEMBER 2024", category_text="Annual Results"), language="en")
    ends = (date(2024, 12, 31),)
    assert hk_annual_end_date(title=annual.title, category_text=annual.category_text) == ends[0]
    narrow = select_hkexnews_report_candidates(query=_hk_query(("Q3",)), announcements=(quarter,), local_annual_ends=ends, read_head_meta=_head_meta)
    broad = select_hkexnews_report_candidates(query=_hk_query(("Q3",)), announcements=(annual, quarter), local_annual_ends=(), read_head_meta=_head_meta)
    assert narrow == broad
    assert len(narrow.candidates) == 1 and not narrow.uncertain_reports
    unknown = select_hkexnews_report_candidates(query=_hk_query(("Q3",)), announcements=(quarter,), local_annual_ends=(), read_head_meta=_no_head)
    conflict = select_hkexnews_report_candidates(query=_hk_query(("Q3",)), announcements=(quarter,), local_annual_ends=ends + (date(2025, 6, 30),), read_head_meta=_no_head)
    assert len(unknown.uncertain_reports) == len(conflict.uncertain_reports) == 1
    assert not unknown.candidates and not conflict.candidates
    assert unknown.uncertain_reports[0].existing_document_id is None
    assert unknown.uncertain_reports[0].report_date == "2025-09-30"
    assert resolve_hk_report_period(title=quarter.title, category_text=quarter.category_text, annual_ends=ends) == (2025, _head_projection())


def _no_head(url: str) -> CnReportHeadMeta:
    """参数为被禁止调用的 URL；返回不发生；HEAD 被调用时抛 AssertionError。"""
    raise AssertionError(url)


@pytest.mark.parametrize("english", (False, True))
def test_remote_annual_and_candidates_use_same_query_window(english: bool) -> None:
    """验证远端年度与主候选消费同一窗口，全部公告为合成反例。

    参数：english 控制年度证据为中文或英文；英文仅供证据。
    返回：无。
    异常：外窗年度改变未知、未知调用 HEAD 或宽窗未确定时断言失败。
    """
    quarter = _hk_raw(document_id="B", title="截至2025年9月30日止三個月業績", category_text="季度業績", filing_date="2025-11-13")
    annual = replace(
        _hk_raw(document_id="annual", title="截至2024年12月31日止全年業績", category_text="末期業績", filing_date="2025-03-19"),
        title="ANNUAL RESULTS FOR YEAR ENDED 31 DECEMBER 2024" if english else "截至2024年12月31日止全年業績",
        language="en" if english else "zh",
    )
    narrow = replace(_hk_query(("Q3",)), start_date=quarter.filing_date, end_date=quarter.filing_date)
    alone = select_hkexnews_report_candidates(query=narrow, announcements=(quarter,), local_annual_ends=(), read_head_meta=_no_head)
    outside = select_hkexnews_report_candidates(query=narrow, announcements=(annual, quarter), local_annual_ends=(), read_head_meta=_no_head)
    assert alone == outside
    assert not outside.candidates and len(outside.uncertain_reports) == 1
    assert outside.uncertain_reports[0].source_id == "B"
    broad = replace(narrow, start_date=annual.filing_date)
    known = select_hkexnews_report_candidates(query=broad, announcements=(annual, quarter, annual), local_annual_ends=(), read_head_meta=_head_meta)
    local = select_hkexnews_report_candidates(query=narrow, announcements=(annual, quarter), local_annual_ends=(date(2024, 12, 31),), read_head_meta=_head_meta)
    assert known == local
    assert len(known.candidates) == 1 and not known.uncertain_reports
    assert known.candidates[0].source_id == "B"
    # 全响应同 ID 冲突仍是协议错误，不能以其中一行在窗外而忽略冲突。
    with pytest.raises(ValueError, match="核心事实冲突"):
        select_hkexnews_report_candidates(query=narrow, announcements=(annual, replace(annual, title="2025年全年業績"), quarter), local_annual_ends=(), read_head_meta=_no_head)
    assert select_hkexnews_report_candidates(query=narrow, announcements=(annual,), local_annual_ends=(), read_head_meta=_no_head).candidates == ()


@pytest.mark.parametrize("barrier", ("target_to_backup", "staging_to_target"))
def test_integrity_view_waits_through_real_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, barrier: _PublicationBarrier) -> None:
    """参数为真实根与 publication 点；返回无；同窗混 A/B 或缺 COMPLETE 时断言失败。"""
    repo = build_fs_repository_set(workspace_root=tmp_path)
    batching = FsBatchingRepository(tmp_path, repository_set=repo)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repo)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repo)
    a = batching.begin_batch("AAPL")
    _stage_meta_view_pair(source, blob, a, "A", replace_existing=False)
    batching.commit_batch(a)
    b = batching.begin_batch("AAPL")
    _stage_meta_view_pair(source, blob, b, "B", replace_existing=True)
    staged = source.read_source_meta_integrity_view("AAPL", SourceKind.FILING, batch=b)
    published = source.read_source_meta_integrity_view("AAPL", SourceKind.FILING, batch=None)
    assert [v.source_meta["version"] for v in staged] == ["B", "B"]
    assert [v.source_meta["version"] for v in published] == ["A", "A"]
    pause = _MetaViewRenameBarrier(repo.core, _active_batch_paths(repo.core), barrier)
    monkeypatch.setattr(repo.core, "_replace_directory", pause)
    reader = FsSourceDocumentRepository(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        commit = pool.submit(batching.commit_batch, b)
        assert pause.entered.wait(5)
        observed = pool.submit(reader.read_source_meta_integrity_view, "AAPL", SourceKind.FILING, batch=None)
        try:
            assert not observed.done()
            pause.resume.set()
            commit.result(timeout=5)
            after = observed.result(timeout=5)
        finally:
            pause.resume.set()
    assert [v.source_meta["version"] for v in after] == ["B", "B"]
    assert all(v.integrity.status is SourceIntegrityStatus.COMPLETE for v in after)
    assert [v.source_meta["version"] for v in published] == ["A", "A"]
    with pytest.raises(ValueError):
        source.read_source_meta_integrity_view("AAPL", SourceKind.FILING, batch=b)


class _ReadFailure:
    """稳定根 getter 指定原异常注入，不影响其他仓储方法。"""
    def __init__(self, error: ValueError | OSError) -> None:
        """参数为原异常对象；返回无；异常无。"""
        self.error = error
    def __call__(self, ticker: str, document_id: str, kind: SourceKind, ticker_dir: Path) -> dict[str, JsonValue]:
        """参数为 getter 原输入；返回不发生；抛出同一原始异常。"""
        del ticker, document_id, kind, ticker_dir
        raise self.error


@pytest.mark.parametrize("error", (ValueError("原 raw JSON 错误"), OSError("原 raw 读取错误")))
def test_strict_raw_exception_identity_and_guard_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: ValueError | OSError) -> None:
    """参数为真实根与原异常；返回无；读取错误变分类/前缀或 guard 未释放时断言失败。"""
    repo = build_fs_repository_set(workspace_root=tmp_path)
    batching = FsBatchingRepository(tmp_path, repository_set=repo)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repo)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repo)
    token = batching.begin_batch("AAPL")
    _stage_meta_view_pair(source, blob, token, "A", replace_existing=False)
    batching.commit_batch(token)
    with monkeypatch.context() as patch:
        patch.setattr(repo.core, "_get_source_meta_at_root", _ReadFailure(error))
        with pytest.raises(type(error)) as raised:
            source.read_source_meta_integrity_view("AAPL", SourceKind.FILING, batch=None)
        assert raised.value is error
    next_batch = batching.begin_batch("AAPL")
    batching.rollback_batch(next_batch)
    assert len(source.read_source_meta_integrity_view("AAPL", SourceKind.FILING, batch=None)) == 2


def test_official_frozen_raw_preserves_hash_scope_and_explicit_q3() -> None:
    """参数无；返回无；官方字节/hash/stock 或 Q3 正例变化时断言失败，不冒称官方未知反例。"""
    for filename, digest in _OFFICIAL_ASSET_HASHES:
        assert hashlib.sha256((_CAPTURE / filename).read_bytes()).hexdigest() == digest
    assert (_CAPTURE / "annual-results.body").stat().st_size == 1446
    assert (_CAPTURE / "quarter-results.body").stat().st_size == 658
    raw: list[HkexnewsRawAnnouncement] = []
    for name, digest in (("annual-results", "62582cfbfa1aaeb588971f339bbbb33767420528718b916877d0e05d0c6cb94a"), ("quarter-results", "0d6bbb3ba351b9a8cdd1966dea75234efb9dbfdb686fba89a289cd5924b59f32")):
        body = (_CAPTURE / (name + ".body")).read_bytes()
        envelope: JsonValue = json.loads((_CAPTURE / (name + ".json")).read_text())
        assert isinstance(envelope, dict)
        assert hashlib.sha256(body).hexdigest() == envelope["raw_response_body_sha256"] == digest
        assert body.decode() == envelope["raw_response_body"]
        payload: hk.JsonValue = json.loads(body)
        snapshot = hk._parse_title_search_snapshot(payload, requested_row_range=100, stock_code="00700", category_spec=hk._PERIOD_TO_CATEGORY_SPEC["Q3"], language="zh")
        for row in snapshot.rows:
            stock = row["STOCK_CODE"]
            assert isinstance(stock, str) and hk._announcement_matches_stock(stock, "00700")
            parsed = hk._parse_announcement(row, language="zh")
            assert parsed is not None
            raw.append(parsed)
    assert len(raw) == 3
    annuals = tuple(d for r in raw if (d := hk_annual_end_date(title=r.title, category_text=r.category_text)) is not None)
    assert annuals == (date(2024, 12, 31),)
    quarter = next(r for r in raw if r.document_id == "11914784")
    assert resolve_hk_report_period(title=quarter.title, category_text=quarter.category_text, annual_ends=()) == (2025, _head_projection())
    assert resolve_hk_report_period(title=quarter.title, category_text=quarter.category_text, annual_ends=annuals) == (2025, _head_projection())
