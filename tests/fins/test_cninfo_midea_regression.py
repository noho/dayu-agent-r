"""美的官方首页派生件的 owner、真实发现和隔离 Fs 入口回归；不代表真实 CLI 验收。"""

import asyncio
from dataclasses import dataclass, field
import hashlib
from io import BytesIO
import json
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs

import httpx
import pytest
from pypdf import PdfReader

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import SourceDocumentUpsertRequest, SourceDocumentRevision
from dayu.fins.domain.enums import SourceKind
from dayu.fins.download_contract import FinsDownloadProviderError, FinsDownloadTransportCategory
from dayu.fins.downloaders.cninfo_downloader import CNINFO_QUERY_URL, CNINFO_STOCK_JSON_URL, CninfoDiscoveryClient
from dayu.fins.pipelines import cn_annual_report_facts
from dayu.fins.pipelines.cn_annual_report_diagnostics import log_cn_annual_report_rejection
from dayu.fins.pipelines.cn_annual_report_facts import CnAnnualReportFactsError, CnAnnualReportFactsReason, resolve_cn_annual_report_facts
from dayu.fins.pipelines.cn_annual_report_source import CnAnnualReportSourceReason
from dayu.fins.pipelines.cn_download_filing_workflow import CnDownloadAnnualPublicationError, run_cn_download_single_filing_stream
from dayu.fins.pipelines.cn_download_models import CnAnnualReportPublication, CnAnnualReportPdf, CnReportCandidate, CnReportQuery, DownloadedReportAsset
from dayu.fins.pipelines.cn_download_pdf_gate import NoopCnDownloadPdfGate
from dayu.fins.pipelines.cn_download_workflow import _read_local_cn_annual_pdfs
from dayu.fins.pipelines.cn_form_utils import PeriodDownloadWindow
from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.pipelines.download_events import DownloadEvent
from dayu.fins.storage import SourceIntegrityStatus
from tests.fins.test_cn_download_workflow import _build_pipeline, _FakeConverter, _seed_annual_owner
from tests.fins.test_cninfo_downloader import _build_client

FIXTURE = Path(__file__).parent / 'fixtures' / 'cninfo_midea_20261018'
QUERY = CnReportQuery('CN', '000333', '2025-01-01', '2026-10-18', ('FY', 'H1', 'Q1', 'Q3'))
ANNUAL_IDS = ('1225065145', '1222951181')
EXPECTED = {
    '1225531404': (2026, 'H1'), '1225259066': (2026, 'Q1'), '1225065145': (2025, 'FY'),
    '1224626720': (2025, 'H1'), '1223412432': (2025, 'Q1'), '1224767336': (2025, 'Q3'), '1222951181': (2024, 'FY'),
}
_CATEGORIES = {'category_ndbg_szsh;': 'FY', 'category_bndbg_szsh;': 'H1', 'category_yjdbg_szsh;': 'Q1', 'category_sjdbg_szsh;': 'Q3'}


def _pdf(source_id: str) -> bytes:
    """读取明确首页派生件。参数：来源 ID。返回：派生字节。异常：文件错误原样传播。"""
    return (FIXTURE / f'{source_id}.page-001.pdf').read_bytes()


@dataclass
class _OfficialHttp:
    """仅替换 HTTP，facts 与 selection 使用生产 owner。"""

    bad_source: str | None = None
    gets: list[str] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """返回冻结响应。参数：生产请求。返回：原 raw 或首页派生件。异常：非预期请求拒绝。"""
        if str(request.url) == CNINFO_STOCK_JSON_URL:
            return httpx.Response(200, content=(FIXTURE / 'stock.response.json').read_bytes())
        if str(request.url) == CNINFO_QUERY_URL:
            form = parse_qs(request.content.decode())
            assert form['stock'] == ['000333,9900005965']
            assert form['seDate'] == ['2025-01-01~2026-10-18']
            period = _CATEGORIES[form['category'][0]]
            return httpx.Response(200, content=(FIXTURE / f'{period}.response.json').read_bytes())
        if request.method == 'HEAD':
            return httpx.Response(200)
        raw = cast(dict[str, JsonValue], json.loads((FIXTURE / 'FY.response.json').read_bytes()))
        rows = raw['announcements']; assert isinstance(rows, list)
        urls = {f"/" + str(row['adjunctUrl']): str(row['announcementId']) for row in rows if isinstance(row, dict)}
        assert request.method == 'GET'
        source_id = urls[request.url.path]
        assert source_id in ANNUAL_IDS, '明确标题摘要不得 GET'
        self.gets.append(source_id)
        payload = b'%PDF-' + b'0' * 2048 if source_id == self.bad_source else _pdf(source_id)
        return httpx.Response(200, content=payload)


def _discover(client: CninfoDiscoveryClient, local: tuple[CnAnnualReportPdf, ...] = ()) -> tuple[CnReportCandidate, ...]:
    """通过真实生产发现返回候选。参数：HTTP client/本地原件。返回：候选。异常：原发现错误。"""
    return client.list_report_candidates(QUERY, client.resolve_company(QUERY), local_annual_ends=(),
        local_cn_annual_pdfs=local, pdf_download_gate=NoopCnDownloadPdfGate()).candidates


@pytest.mark.parametrize('source_id,year', (('1225065145', 2025), ('1222951181', 2024)))
def test_official_midea_facts(source_id: str, year: int) -> None:
    """官方首页直接自证财年/全文。参数：来源/年。返回：无。异常：事实或原文漂移断言失败。"""
    facts = resolve_cn_annual_report_facts(_pdf(source_id))
    assert (facts.fiscal_year, facts.kind) == (year, 'full')
    assert PdfReader(BytesIO(_pdf(source_id))).pages[0].extract_text() == (FIXTURE / f'{source_id}.page-001.txt').read_text()


def test_frozen_provenance_hashes() -> None:
    """长期 fixture 自足保存来源和两类 hash。参数：无。返回：无。异常：资产漂移断言失败。"""
    provenance = cast(dict[str, JsonValue], json.loads((FIXTURE / 'provenance.json').read_bytes()))
    pages = provenance['pdf_first_pages']; responses = provenance['raw_responses']
    assert isinstance(pages, list) and isinstance(responses, list)
    for row in pages:
        assert isinstance(row, dict)
        sid = str(row['source_id'])
        assert row['derived_sha256'] == hashlib.sha256(_pdf(sid)).hexdigest()
        assert row['text_sha256'] == hashlib.sha256((FIXTURE / f'{sid}.page-001.txt').read_bytes()).hexdigest()
        assert row['page_index'] == 0 and cast(int, row['original_pages']) > 1
        assert row['original_sha256'] != row['derived_sha256'] and row['captured_at_utc']
        assert str(row['official_url']).startswith('http://static.cninfo.com.cn/')
    for row in responses:
        assert isinstance(row, dict)
        assert hashlib.sha256((FIXTURE / str(row['file'])).read_bytes()).hexdigest() == row['sha256']


@pytest.mark.parametrize('source_id', ('1225058109', '1222951198'))
def test_official_complex_summary_is_not_inferred_full(source_id: str) -> None:
    """摘要正文不能被忽略后推定全文。参数：来源。返回：无。异常：宽松接受断言失败。"""
    with pytest.raises(CnAnnualReportFactsError) as raised:
        resolve_cn_annual_report_facts(_pdf(source_id))
    assert raised.value.reason is CnAnnualReportFactsReason.MISSING_OR_CONFLICTING_FACTS


def test_official_bare_discovery_prepared_assets() -> None:
    """四个原分类得到七个候选且 prepared 同源。参数：无。返回：无。异常：身份/摘要过滤/资产漂移断言失败。"""
    http = _OfficialHttp(); client = _build_client(http)
    result = client.list_report_candidates(QUERY, client.resolve_company(QUERY), local_annual_ends=(),
        local_cn_annual_pdfs=(), pdf_download_gate=NoopCnDownloadPdfGate())
    assert {c.source_id: (c.fiscal_year, c.period_projection.identity_period) for c in result.candidates} == EXPECTED
    assert http.gets == list(ANNUAL_IDS) and not result.uncertain_reports
    assert {a.candidate.source_id for a in result.prepared_assets} == set(ANNUAL_IDS)
    for asset in result.prepared_assets:
        assert asset.candidate.fiscal_year_source == 'source_document'
        assert asset.pdf_bytes == _pdf(asset.candidate.source_id)
        assert asset.sha256 == hashlib.sha256(asset.pdf_bytes).hexdigest()


def _state(pipeline: CnPipeline) -> dict[str, tuple[str, dict[str, JsonValue], tuple[tuple[str, bytes], ...]]]:
    """经仓储保存完整发布态。参数：隔离 pipeline。返回：revision/meta/全部资产。异常：仓储错误原样。"""
    result: dict[str, tuple[str, dict[str, JsonValue], tuple[tuple[str, bytes], ...]]] = {}
    for docid in pipeline.source_repository.list_source_document_ids('000333', SourceKind.FILING):
        with pipeline.source_repository.read_source_snapshot('000333', docid, SourceKind.FILING, materialize_files=True) as snapshot:
            assets: list[tuple[str, bytes]] = []
            for descriptor in snapshot.files:
                with snapshot.get_source(descriptor.name).open() as stream:
                    assets.append((descriptor.name, stream.read()))
            result[docid] = (snapshot.revision.token, dict(snapshot.source_meta), tuple(assets))
    return result


def test_official_fy_pipeline_then_witness_repeat(tmp_path: Path) -> None:
    """真实发现→prepared→Fs→本地发现/witness，repeat 无 GET/转换/改写。参数：隔离根。返回：无。异常：断言失败。"""
    http = _OfficialHttp(); client = _build_client(http); converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=client, converter=converter)
    first = pipeline.download(ticker='SZ:000333', form_type='FY', start_date=QUERY.start_date,
        end_date=QUERY.end_date, start_is_explicit=True)
    before = _state(pipeline)
    assert len(before) == 2 and converter.calls == 2 and http.gets == list(ANNUAL_IDS)
    for docid, (_, meta, assets) in before.items():
        sid = str(meta['source_id']); assert sid in ANNUAL_IDS
        assert meta['source_provider'] == 'cninfo' and meta['fiscal_year_source'] == 'source_document'
        assert meta['fiscal_year'] == EXPECTED[sid][0] and meta['covered_fiscal_periods'] == ['FY']
        assert dict(assets)[docid + '.pdf'] == _pdf(sid)
        assert pipeline.source_repository.classify_source_integrity('000333', docid, SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE
    http.gets.clear()
    second = pipeline.download(ticker='SZ:000333', form_type='FY', start_date=QUERY.start_date,
        end_date=QUERY.end_date, start_is_explicit=True)
    assert first['status'] == second['status'] == 'ok'
    summary = second['summary']; assert isinstance(summary, dict)
    assert summary['downloaded'] == summary['converted'] == summary['failed'] == 0 and summary['skipped'] == 2
    assert _state(pipeline) == before and http.gets == [] and converter.calls == 2


async def _single(pipeline: CnPipeline, candidate: CnReportCandidate, prepared: DownloadedReportAsset | None) -> list[DownloadEvent]:
    """运行真实单 filing 边界。参数：宿主/候选/prepared。返回：事件。异常：原阶段机异常。"""
    return [event async for event in run_cn_download_single_filing_stream(
        batching_repository=pipeline.batching_repository, source_repository=pipeline.source_repository,
        blob_repository=pipeline.blob_repository, processed_repository=pipeline.processed_repository,
        discovery_client=pipeline.cn_discovery_client, pdf_download_gate=pipeline.pdf_download_gate,
        docling_conversion_runner=pipeline.docling_conversion_runner, ticker='000333',
        profile=pipeline.cn_discovery_client.resolve_company(QUERY), candidate=candidate,
        prepared_asset=prepared, local_annual_publication=None, overwrite=False, cancel_checker=None, module='TEST')]


@pytest.mark.parametrize('path', ('prepared', 'direct', 'complete'))
def test_official_actual_filing_entry_paths(tmp_path: Path, path: str) -> None:
    """合法全文通过三条实际复核入口。参数：隔离根/路径。返回：无。异常：事实漂移或重复处理断言失败。"""
    http = _OfficialHttp(); client = _build_client(http)
    candidate = next(c for c in _discover(client) if c.source_id == '1225065145')
    converter = _FakeConverter(); pipeline = _build_pipeline(tmp_path=tmp_path, discovery=client, converter=converter)
    payload = _pdf(candidate.source_id)
    prepared = DownloadedReportAsset(candidate, payload, hashlib.sha256(payload).hexdigest(), len(payload), '2026-10-18T06:00:00+00:00') if path == 'prepared' else None
    if path == 'complete':
        _seed_annual_owner(pipeline, candidate, payload, ticker='000333')
    before = _state(pipeline); http.gets.clear()
    events = asyncio.run(_single(pipeline, candidate, prepared))
    assert events[-1].payload['status'] == ('skipped' if path == 'complete' else 'downloaded')
    assert http.gets == ([candidate.source_id] if path == 'direct' else [])
    assert converter.calls == (0 if path == 'complete' else 1)
    if path == 'complete':
        assert _state(pipeline) == before


@pytest.mark.parametrize('local', (False, True))
def test_discovery_rejection_logs_exact_stage(tmp_path: Path, caplog: pytest.LogCaptureFixture, local: bool) -> None:
    """落选年度坏件仍整体失败；本地与远端有独立阶段。参数：隔离根/日志/路径。返回：无。异常：scope 漂移断言失败。"""
    http = _OfficialHttp(bad_source='1222951181'); client = _build_client(http)
    cached: tuple[CnAnnualReportPdf, ...] = ()
    if local:
        cached = (CnAnnualReportPdf(CnAnnualReportPublication('cninfo', '1222951181', 'existing-doc', SourceDocumentRevision('r')),
            'opaque locator', b'%PDF-' + b'0' * 2048),)
    converter = _FakeConverter(); pipeline = _build_pipeline(tmp_path=tmp_path, discovery=client, converter=converter)
    with pytest.raises(FinsDownloadProviderError) as raised:
        _discover(client, cached)
    assert raised.value.transport_category is FinsDownloadTransportCategory.PROTOCOL and raised.value.retryable is False
    assert raised.value.safe_message == '巨潮年度报告原文无法确认财年或全文性质'
    assert _state(pipeline) == {} and converter.calls == 0
    log = caplog.text
    assert 'source_id="1222951181"' in log and f"stage={'local_discovery' if local else 'remote_discovery'}" in log
    assert CnAnnualReportFactsReason.EXTRACTION_FAILED.value in log
    assert ('document_id=' in log) is local


def _raise_sensitive_read(stream: BytesIO) -> PdfReader:
    """模拟底层解析异常。参数：输入流。返回：不返回。异常：含私密材料的底层 ValueError。"""
    del stream
    raise ValueError('http://private.invalid/?token=secret /private/source.pdf 财报正文\n\x1b[31m')


def test_cause_and_unsafe_identity_never_leak(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """真实包装拒绝只消费封闭原因。参数：patch/日志。返回：无。异常：安全边界漂移断言失败。"""
    monkeypatch.setattr(cn_annual_report_facts, 'PdfReader', _raise_sensitive_read)
    with pytest.raises(FinsDownloadProviderError) as raised:
        _discover(_build_client(_OfficialHttp()))
    assert isinstance(raised.value.__cause__, CnAnnualReportFactsError)
    assert raised.value.__cause__.__cause__ is not None
    for value in ('http://private.invalid', '/private/source.pdf', '财报正文', '\x1b', 'token=secret'):
        assert value not in caplog.text and value not in str(raised.value)
    caplog.clear()
    unsafe = 'http://private.invalid/?token=secret\n\x1b' + 'X' * 300
    log_cn_annual_report_rejection(source_id=unsafe, stage='local_declaration_read',
        reason=CnAnnualReportSourceReason.ORIGINAL_UNCONFIRMED, document_id=unsafe)
    assert unsafe not in caplog.text and '<不可展示;sha256=' in caplog.text
    assert hashlib.sha256(unsafe.encode()).hexdigest() in caplog.text
    assert len(caplog.records) == 1 and '\x1b' not in caplog.text


@pytest.mark.parametrize('stage', ('download', 'complete'))
@pytest.mark.parametrize('bad', ('wrong_year', 'broken'))
def test_filing_rejection_stage_and_scope(tmp_path: Path, caplog: pytest.LogCaptureFixture, stage: str, bad: str) -> None:
    """实际复核拒绝保持现有原因/范围。参数：根/日志/阶段/反例。返回：无。异常：scope 或分类漂移断言失败。"""
    client = _build_client(_OfficialHttp()); candidate = next(c for c in _discover(client) if c.source_id == '1225065145')
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=client, converter=_FakeConverter())
    payload = _pdf('1222951181') if bad == 'wrong_year' else b'%PDF-' + b'0' * 2048
    if stage == 'complete':
        _seed_annual_owner(pipeline, candidate, payload, ticker='000333')
        before = _state(pipeline)
        with pytest.raises(CnDownloadAnnualPublicationError) as raised:
            asyncio.run(_single(pipeline, candidate, None))
        assert raised.value.reason == 'source_document_facts_mismatch' and _state(pipeline) == before
    else:
        asset = DownloadedReportAsset(candidate, payload, hashlib.sha256(payload).hexdigest(), len(payload), '2026-10-18T06:00:00+00:00')
        events = asyncio.run(_single(pipeline, candidate, asset))
        assert events[-1].payload['reason_code'] == ('provider_protocol' if bad == 'broken' else 'source_document_facts_mismatch')
        assert _state(pipeline) == {}
    assert f"stage={'download_review' if stage == 'download' else 'complete_original_review'}" in caplog.text
    assert 'source_id="1225065145"' in caplog.text and 'document_id=' in caplog.text


@pytest.mark.parametrize('stage', ('local_declaration_read', 'complete_original_review'))
def test_local_declaration_rejection_is_not_parser_reason(tmp_path: Path, caplog: pytest.LogCaptureFixture, stage: str) -> None:
    """真实 Fs 声明拒绝保留自身原因。参数：根/日志。返回：无。异常：owner 归因漂移断言失败。"""
    client = _build_client(_OfficialHttp()); candidate = next(c for c in _discover(client) if c.source_id == '1225065145')
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=client, converter=_FakeConverter())
    docid = _seed_annual_owner(pipeline, candidate, _pdf(candidate.source_id), ticker='000333')
    meta = dict(pipeline.source_repository.get_source_meta('000333', docid, SourceKind.FILING))
    meta['source_url'] = ''
    batch = pipeline.batching_repository.begin_batch('000333')
    pipeline.source_repository.update_source_document(SourceDocumentUpsertRequest(
        ticker='000333', document_id=docid, internal_document_id=str(meta['internal_document_id']),
        form_type='FY', primary_document=str(meta['primary_document']), meta=meta), SourceKind.FILING, batch=batch)
    pipeline.batching_repository.commit_batch(batch)
    before = _state(pipeline)
    if stage == 'local_declaration_read':
        with pytest.raises(FinsDownloadProviderError):
            _read_local_cn_annual_pdfs('000333', (PeriodDownloadWindow('FY', QUERY.start_date, QUERY.end_date),), pipeline.source_repository, None)
    else:
        with pytest.raises(CnDownloadAnnualPublicationError) as raised:
            asyncio.run(_single(pipeline, candidate, None))
        assert raised.value.reason == 'source_document_facts_mismatch'
    assert f'stage={stage}' in caplog.text
    assert CnAnnualReportSourceReason.ORIGINAL_UNCONFIRMED.value in caplog.text
    assert CnAnnualReportFactsReason.UNSUPPORTED_SUFFIX.value not in caplog.text
    assert _state(pipeline) == before
