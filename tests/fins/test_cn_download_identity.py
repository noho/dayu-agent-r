"""下载身份 owner 的纯索引及真实仓储读取窗口契约测试。"""

import hashlib
from collections.abc import Mapping
from dataclasses import fields, FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_identity import (
    build_cn_download_identity_index, read_cn_download_identity_index, resolve_cn_download_ids,
)
from dayu.fins.pipelines.cn_download_models import (
    CnReportCandidate, CnReportPeriodProjection, CnSourceProvider,
)
from dayu.fins.pipelines.cn_form_utils import build_cn_filing_ids
from dayu.fins.storage import (
    FsSourceDocumentRepository, FsBatchingRepository, FsDocumentBlobRepository, SourceMetaReadEntry, SourceMetaReadView,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from tests.fins.test_fins_storage_atomicity import _create_complete_source, _read_integrity_json, _write_integrity_json


def _identity_candidate(provider: CnSourceProvider = "hkexnews", source_id: str = "X") -> CnReportCandidate:
    """构造身份查询候选。

    参数：provider 为真实来源类别；source_id 为来源引用。
    返回：固定年度报告候选。异常：无。
    """
    return CnReportCandidate(fiscal_year_source="source_document" if provider == "cninfo" else "title_or_category_inferred",
        provider=provider, source_id=source_id, source_url="https://example.test/report.pdf",
        title="年度报告", language="zh", filing_date="2025-04-01", fiscal_year=2024,
        period_projection=CnReportPeriodProjection(identity_period="FY", covered_periods=("FY",)),
        amended=False, content_length=None, etag=None, last_modified=None,
    )


def _view(
    metas: tuple[tuple[str, Mapping[str, JsonValue]], ...],
    error: ValueError | OSError | None = None,
) -> SourceMetaReadView:
    """构造纯索引测试输入；不模拟仓储或完整性结论。

    参数：metas 为有序成功事实；error 为首个原异常。
    返回：FILING 观察。异常：无。
    """
    return SourceMetaReadView(
        "0700", SourceKind.FILING,
        tuple(SourceMetaReadEntry(document_id, MappingProxyType(dict(meta))) for document_id, meta in metas),
        error,
    )


def test_identity_types_are_closed_frozen_slots() -> None:
    """观察只有身份/元数据/读取错误，索引不能被重新赋值。

    参数：无。返回：无。异常：AssertionError 表示类型契约漂移。
    """
    assert tuple(f.name for f in fields(SourceMetaReadEntry)) == ("document_id", "source_meta")
    assert tuple(f.name for f in fields(SourceMetaReadView)) == ("ticker", "source_kind", "entries", "read_error")
    view = _view(())
    with pytest.raises(FrozenInstanceError):
        view.__setattr__("ticker", "other")
    assert "__dict__" not in SourceMetaReadView.__slots__
    index = build_cn_download_identity_index(view)
    assert isinstance(index.source_matches, MappingProxyType)
    assert isinstance(index.allocated_periods, MappingProxyType)
    assert index.allocated_internal_ids == frozenset()
    with pytest.raises(FrozenInstanceError):
        index.__setattr__("ticker", "other")


def _forbidden_identity_read(ticker: str, source_kind: SourceKind) -> SourceMetaReadView:
    """禁止非 HK 读取。参数：ticker/source_kind 为读取范围。返回：无。异常：AssertionError。"""
    raise AssertionError("非 HK 不应读仓储")


@pytest.mark.parametrize("candidates", [(), (replace(_identity_candidate("cninfo"), period_projection=CnReportPeriodProjection("H1", ("H1",))),)])
def test_non_hk_and_empty_do_not_touch_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidates: tuple[CnReportCandidate, ...],
) -> None:
    """非 HK/空候选零仓储；真实 Fs 的观察方法若被误调立即失败。

    参数：tmp_path 为隔离仓储；monkeypatch 为调用监视；candidates 为候选集合。
    返回：无。异常：AssertionError 表示发生仓储读取。
    """
    source = FsSourceDocumentRepository(tmp_path)
    monkeypatch.setattr(source, "read_source_meta_view", _forbidden_identity_read)
    index = read_cn_download_identity_index("0700", candidates, source)
    for candidate in candidates:
        assert resolve_cn_download_ids("0700", candidate, index) == build_cn_filing_ids(
            ticker="0700", form_type=candidate.period_projection.identity_period, fiscal_year=2024, fiscal_period=candidate.period_projection.identity_period, amended=False,
        )
    assert not index.source_matches and not index.allocated_periods and not index.allocated_internal_ids


def test_identity_kind_and_ticker_misuse_are_development_errors() -> None:
    """错误观察范围仅为开发契约拒绝，不扩展生产业务拒绝。

    参数：无。返回：无。异常：AssertionError 表示范围校验失效。
    """
    with pytest.raises(ValueError, match="filing"):
        build_cn_download_identity_index(SourceMetaReadView("0700", SourceKind.MATERIAL, (), None))
    with pytest.raises(ValueError, match="ticker"):
        resolve_cn_download_ids("00005", _identity_candidate(), build_cn_download_identity_index(_view(())))


@pytest.mark.parametrize("internal", [None, "", 42, False, [], {}])
def test_missing_internal_precedes_later_read_error(internal: JsonValue) -> None:
    """匹配前缀缺内部身份先于后项原读取错，build 不提前抛错。

    参数：internal 为坏身份值。返回：无。异常：AssertionError 表示错误优先序漂移。
    """
    expected = ValueError("later malformed JSON")
    index = build_cn_download_identity_index(_view((("A", {
        "source_provider": "hkexnews", "source_id": "X", "internal_document_id": internal,
    }),), expected))
    with pytest.raises(ValueError, match="^既有下载来源缺少内部文档身份$"):
        resolve_cn_download_ids("0700", _identity_candidate(), index)
    with pytest.raises(ValueError) as raised:
        resolve_cn_download_ids("0700", _identity_candidate(source_id="Y"), index)
    assert raised.value is expected


@pytest.mark.parametrize("count", [0, 1, 2])
@pytest.mark.parametrize("expected", [ValueError("malformed"), FileNotFoundError("missing"), OSError("read")])
def test_read_error_precedes_duplicate_unique_and_allocation(count: int, expected: ValueError | OSError) -> None:
    """原 get 错先于完整扫描后 duplicate、唯一返回和新分配。

    参数：count 为有效匹配数；expected 为原异常对象。返回：无。异常：AssertionError。
    """
    metas = tuple((str(i), {"source_provider": "hkexnews", "source_id": "X", "internal_document_id": f"i{i}"}) for i in range(count))
    index = build_cn_download_identity_index(_view(metas, expected))
    assert index.read_error is expected
    with pytest.raises(type(expected)) as raised:
        resolve_cn_download_ids("0700", _identity_candidate(), index)
    assert raised.value is expected


def test_unique_duplicate_and_non_string_source_values() -> None:
    """合法唯一匹配返回原身份；有效重复拒绝，非字符串来源不被字符串化。

    参数：无。返回：无。异常：AssertionError 表示索引匹配漂移。
    """
    meta: dict[str, JsonValue] = {"source_provider": "hkexnews", "source_id": "X", "internal_document_id": "original"}
    index = build_cn_download_identity_index(_view((("A", meta), ("B", {"source_provider": 1, "source_id": "X"}), ("C", {"source_provider": "hkexnews", "source_id": []}))))
    assert resolve_cn_download_ids("0700", _identity_candidate(), index) == ("A", "original")
    duplicate = build_cn_download_identity_index(_view((("A", meta), ("B", meta))))
    with pytest.raises(ValueError, match="^同一下载来源对应多个文档，无法唯一绑定$"):
        resolve_cn_download_ids("0700", _identity_candidate(), duplicate)
    empty = build_cn_download_identity_index(_view((("A", {"source_provider": "hkexnews", "source_id": "", "internal_document_id": "empty"}),)))
    assert resolve_cn_download_ids("0700", _identity_candidate(source_id=""), empty) == ("A", "empty")


@pytest.mark.parametrize("meta,changed", [
    (None, False), ({"fiscal_period": "FY", "fiscal_year": 2024}, False),
    ({"fiscal_period": "Q3", "fiscal_year": 2024}, True),
    ({"fiscal_period": "FY", "fiscal_year": "2024"}, True),
    ({}, True), ({"fiscal_period": None, "fiscal_year": None}, True),
    ({"fiscal_period": "FY"}, True), ({"fiscal_year": 2024}, True),
    ({"fiscal_period": ["FY"], "fiscal_year": 2024}, True),
])
def test_allocated_absence_same_changed_and_real_none(
    meta: dict[str, JsonValue] | None, changed: bool,
) -> None:
    """缺席不等于在场 None；在场财期以原 JSON 值直接比较。

    参数：meta 为在场原元数据或缺席；changed 为原比较结果。
    返回：无。异常：AssertionError 表示缺席或财期直接比较被篡改。
    """
    candidate = _identity_candidate()
    allocated = build_cn_filing_ids(ticker="0700", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False)
    index = build_cn_download_identity_index(_view(()) if meta is None else _view(((allocated[0], meta),)))
    digest = hashlib.sha1(b"0700|hkexnews|X").hexdigest()
    expected = (f"fil_cn_{digest}", f"cn_{digest}") if changed else allocated
    assert resolve_cn_download_ids("0700", candidate, index) == expected


@pytest.mark.parametrize("first_internal,duplicates", [(None, False), ("i-A", False), ("i-A", True)])
def test_real_fs_prefix_query_preserves_missing_internal_and_original_get_error(
    tmp_path: Path, first_internal: str | None, duplicates: bool,
) -> None:
    """真实 Fs 成功前缀按候选查询复刻原优先序，后项错不让有效重复或唯一返回提前完成。

    参数：tmp_path 为隔离根；first_internal 为首匹配身份；duplicates 为双匹配。
    返回：无。异常：AssertionError 或原仓储异常。
    """
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    batching = FsBatchingRepository(tmp_path, repository_set=repository_set)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    batch = batching.begin_batch("0700")
    ids = ("A", "B", "Z", "ZZ-after-error") if duplicates else ("A", "Z", "ZZ-after-error")
    for document_id in ids:
        _create_complete_source(source, blob, batch=batch, document_id=document_id, ticker="0700")
    batching.commit_batch(batch)
    for document_id in ids:
        path = repository_set.core._source_meta_path_for_read("0700", document_id, SourceKind.FILING)
        meta = _read_integrity_json(path)
        meta["source_provider"] = "hkexnews"
        meta["source_id"] = "late" if document_id == "ZZ-after-error" else "X"
        meta["internal_document_id"] = first_internal if document_id == "A" else f"i-{document_id}"
        _write_integrity_json(path, meta)
    broken = repository_set.core._source_meta_path_for_read("0700", "Z", SourceKind.FILING)
    broken.write_bytes(b"{")
    index = read_cn_download_identity_index("0700", (_identity_candidate(),), source)
    assert isinstance(index.read_error, ValueError)
    assert tuple(index.allocated_periods) == (("A", "B") if duplicates else ("A",))
    with pytest.raises(ValueError) as raised:
        resolve_cn_download_ids("0700", _identity_candidate(), index)
    if first_internal is None:
        assert str(raised.value) == "既有下载来源缺少内部文档身份"
        assert raised.value is not index.read_error
    else:
        assert raised.value is index.read_error
    for source_id in ("Y", "late"):
        with pytest.raises(ValueError) as read_error:
            resolve_cn_download_ids("0700", _identity_candidate(source_id=source_id), index)
        assert read_error.value is index.read_error
    # UNSAFE raw meta 仍是身份读取输入，未将 prefix/读取失败解释成完整性事实。
    assert source.get_source_meta("0700", "A", SourceKind.FILING)["internal_document_id"] == first_internal


class _IdentityViewReadCounter:
    """计数真实 Fs 观察调用，不提供替代仓储事实。"""

    def __init__(self, source: FsSourceDocumentRepository) -> None:
        """初始化。参数：source 为真实仓储。返回：无。异常：无。"""
        self.read = source.read_source_meta_view
        self.calls: list[tuple[str, SourceKind]] = []

    def __call__(self, ticker: str, source_kind: SourceKind) -> SourceMetaReadView:
        """读取原事实。参数：ticker/source_kind 为范围。返回：真实观察。异常：原读取异常。"""
        self.calls.append((ticker, source_kind))
        return self.read(ticker, source_kind)


def test_identity_read_helper_multiple_candidates_builds_one_filing_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多个 HK/非 HK 消费只读取一次 FILING，并且每次 helper 新观察。

    参数：tmp_path 为隔离根；monkeypatch 为真实调用计数。返回：无。异常：AssertionError。
    """
    source = FsSourceDocumentRepository(tmp_path)
    counter = _IdentityViewReadCounter(source)
    monkeypatch.setattr(source, "read_source_meta_view", counter)
    candidates = (_identity_candidate(), _identity_candidate(source_id="Y"), _identity_candidate("cninfo"))
    first = read_cn_download_identity_index("0700", candidates, source)
    for candidate in candidates:
        resolve_cn_download_ids("0700", candidate, first)
    assert counter.calls == [("0700", SourceKind.FILING)]
    second = read_cn_download_identity_index("0700", candidates, source)
    assert second is not first and counter.calls == [("0700", SourceKind.FILING)] * 2


@pytest.mark.parametrize('mode',('empty','same','occupied','fallback_occupied','duplicate','missing_internal','read_error'))
def test_cn_annual_source_key_and_slot_collision(mode: str) -> None:
    """参数：CN年度身份状态。返回：无。异常：来源混同、locator绑定或覆盖碰撞断言失败。"""
    candidate=_identity_candidate('cninfo','full')
    allocated=build_cn_filing_ids(ticker='0700',form_type='FY',fiscal_year=2024,fiscal_period='FY',amended=False)
    digest=hashlib.sha1(b'0700|cninfo|full').hexdigest();fallback=('fil_cn_'+digest,'cn_'+digest)
    same={'source_provider':'cninfo','source_id':'full','internal_document_id':'internal','source_url':'old opaque locator','fiscal_year':2024,'fiscal_period':'FY'}
    occupied={'source_provider':'cninfo','source_id':'summary','internal_document_id':'seed_internal','fiscal_year':2024,'fiscal_period':'FY'}
    rows:tuple[tuple[str,Mapping[str,JsonValue]],...]=()
    error:ValueError | OSError | None=None
    if mode=='same':rows=(('held',same),)
    elif mode=='occupied':rows=((allocated[0],occupied),)
    elif mode=='fallback_occupied':rows=((allocated[0],occupied),(fallback[0],occupied))
    elif mode=='duplicate':rows=(('a',same),('b',same))
    elif mode=='missing_internal':rows=(('held',{**same,'internal_document_id':None}),)
    elif mode=='read_error':error=OSError('original read')
    index=build_cn_download_identity_index(_view(rows,error))
    if mode in ('fallback_occupied','duplicate','missing_internal','read_error'):
        with pytest.raises(OSError if mode=='read_error' else ValueError):resolve_cn_download_ids('0700',candidate,index)
    else:assert resolve_cn_download_ids('0700',candidate,index)==(fallback if mode=='occupied' else ('held','internal') if mode=='same' else allocated)


@pytest.mark.parametrize("seed_slot", ("external", "internal"))
@pytest.mark.parametrize("fallback_slot", (None, "external", "internal"))
@pytest.mark.parametrize("known_source", (False, True))
def test_cn_annual_allocation_checks_both_explicit_id_namespaces(
    seed_slot: str, fallback_slot: str | None, known_source: bool,
) -> None:
    """任一 seed 占用转 fallback，任一 fallback 占用拒绝，未知来源仍占用可信内部 ID。

    参数：seed_slot/fallback_slot 为占用命名空间；known_source 为是否具有可信来源 key。
    返回：无。异常：AssertionError 表示碰撞被忽略或索引被修改。
    """
    candidate = _identity_candidate("cninfo", "full")
    seed = build_cn_filing_ids(ticker="0700", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False)
    digest = hashlib.sha1(b"0700|cninfo|full").hexdigest()
    fallback = (f"fil_cn_{digest}", f"cn_{digest}")
    key: dict[str, JsonValue] = {"source_provider": "cninfo", "source_id": "other"} if known_source else {}
    rows: list[tuple[str, Mapping[str, JsonValue]]] = [
        (seed[0] if seed_slot == "external" else "unrelated-seed-owner",
         {**key, "internal_document_id": seed[1] if seed_slot == "internal" else "seed-owner"}),
    ]
    if fallback_slot is not None:
        rows.append((fallback[0] if fallback_slot == "external" else "unrelated-fallback-owner",
                     {**key, "internal_document_id": fallback[1] if fallback_slot == "internal" else "fallback-owner"}))
    view = _view(tuple(rows))
    index = build_cn_download_identity_index(view)
    before = (dict(index.source_matches), dict(index.allocated_periods), index.allocated_internal_ids)
    if fallback_slot is None:
        assert resolve_cn_download_ids("0700", candidate, index) == fallback
    else:
        with pytest.raises(ValueError, match="^年度来源身份已被其它源占用$"):
            resolve_cn_download_ids("0700", candidate, index)
    assert (dict(index.source_matches), dict(index.allocated_periods), index.allocated_internal_ids) == before
    assert index.allocated_internal_ids == frozenset(row[1]["internal_document_id"] for row in rows)


@pytest.mark.parametrize("internal", (None, "", 42, False, [], {}, "trusted"))
def test_internal_occupancy_uses_only_explicit_nonempty_strings(internal: JsonValue) -> None:
    """内部占用只取非空字符串，不从 external 名字猜内部身份。

    参数：internal 为 owner 声明值。返回：无。异常：AssertionError 表示推测或宽松转换。
    """
    candidate = _identity_candidate("cninfo", "full")
    seed = build_cn_filing_ids(ticker="0700", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False)
    index = build_cn_download_identity_index(_view(((seed[1], {"internal_document_id": internal}),)))
    assert index.allocated_internal_ids == (frozenset({"trusted"}) if internal == "trusted" else frozenset())
    assert resolve_cn_download_ids("0700", candidate, index) == seed


@pytest.mark.parametrize("mode", ("same", "missing", "duplicate", "read_error"))
def test_cn_reuse_and_original_errors_precede_colliding_allocation(mode: str) -> None:
    """同 key 复用及旧错误优先序均先于新分配碰撞检查。

    参数：mode 为复用或原错误场景。返回：无。异常：AssertionError 表示优先序改变。
    """
    candidate = _identity_candidate("cninfo", "full")
    seed = build_cn_filing_ids(ticker="0700", form_type="FY", fiscal_year=2024, fiscal_period="FY", amended=False)
    digest = hashlib.sha1(b"0700|cninfo|full").hexdigest()
    meta: dict[str, JsonValue] = {"source_provider": "cninfo", "source_id": "full", "internal_document_id": "held-internal"}
    rows: list[tuple[str, Mapping[str, JsonValue]]] = [
        (seed[0], {"internal_document_id": seed[1]}),
        (f"fil_cn_{digest}", {"internal_document_id": f"cn_{digest}"}),
        ("held", {**meta, "internal_document_id": None} if mode == "missing" else meta),
    ]
    if mode in {"duplicate", "read_error"}:
        rows.append(("duplicate", meta))
    error = OSError("original read") if mode in {"missing", "read_error"} else None
    index = build_cn_download_identity_index(_view(tuple(rows), error))
    if mode == "same":
        assert resolve_cn_download_ids("0700", candidate, index) == ("held", "held-internal")
    elif mode == "read_error":
        with pytest.raises(OSError) as raised:
            resolve_cn_download_ids("0700", candidate, index)
        assert raised.value is error
    else:
        message = "既有下载来源缺少内部文档身份" if mode == "missing" else "同一下载来源对应多个文档，无法唯一绑定"
        with pytest.raises(ValueError, match=f"^{message}$"):
            resolve_cn_download_ids("0700", candidate, index)
