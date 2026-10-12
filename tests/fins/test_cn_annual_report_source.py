"""年度原件 owner：真实 Fs snapshot、声明投影、同版读取与取消资源边界。"""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import SourceDocumentRevision
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_annual_report_source import project_cn_annual_report_original, read_cn_annual_report_pdf, CnAnnualReportSourceError
from dayu.fins.pipelines.cn_download_models import CnAnnualReportPublication, CnDownloadCancelledError
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol
from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.storage.source_integrity import SourceIntegrityClassification, SourceIntegrityRevisionConflictError, SourceIntegrityRepairRequiredError, SourceIntegrityPreflightError, SourceIntegrityStatus, SourceIntegrityReason
from tests.fins.test_cn_download_workflow import _build_pipeline, _FakeDiscoveryClient, _FakeConverter, _candidate, _collect_events


def _seed(root: Path) -> CnPipeline:
    """创建真实 Fs 完整原件。参数：root。返回：真实 pipeline。异常：owner 原错误。"""
    pipeline=_build_pipeline(tmp_path=root,discovery=_FakeDiscoveryClient(root,(_candidate(),)),converter=_FakeConverter())
    _collect_events(pipeline,start_is_explicit=True)
    return pipeline


def test_real_exact_original(tmp_path: Path) -> None:
    """参数：真实根。返回：无。异常：原件名、版本或 locator 偏差断言失败。"""
    pipeline=_seed(tmp_path);entry=pipeline.source_repository.read_source_meta_integrity_view('600519',SourceKind.FILING,batch=None)[0]
    assert entry.integrity.revision is not None
    publication=CnAnnualReportPublication('cninfo','A1',entry.document_id,entry.integrity.revision)
    calls:list[int]=[]
    pdf=read_cn_annual_report_pdf('600519',entry.document_id,publication,entry.source_meta,pipeline.source_repository,lambda: calls.append(1))
    assert len(calls)==5 and pdf.publication==publication and pdf.source_url==_candidate().source_url
    with pipeline.source_repository.read_source_snapshot('600519',entry.document_id,SourceKind.FILING,materialize_files=True) as snapshot:
        descriptor=project_cn_annual_report_original(snapshot)
        assert descriptor.name==entry.document_id+'.pdf'
        with snapshot.get_source(descriptor.name).open() as stream:assert stream.read()==pdf.pdf_bytes


@pytest.mark.parametrize('mode',('no_files','empty','no_role','two','non_pdf','bad_name','size','sha','missing_descriptor'))
def test_projection_declared_role_only(tmp_path: Path,monkeypatch: pytest.MonkeyPatch,mode: str) -> None:
    """参数：根、声明反例。返回：无。异常：角色猜测或错配未拒断言失败。"""
    pipeline=_seed(tmp_path);docid=pipeline.source_repository.list_source_document_ids('600519',SourceKind.FILING)[0]
    with pipeline.source_repository.read_source_snapshot('600519',docid,SourceKind.FILING,materialize_files=True) as snapshot:
        meta=dict(snapshot.source_meta);entries=meta['files'];assert isinstance(entries,list)
        original=next(dict(e) for e in entries if isinstance(e,Mapping) and e.get('source')=='original')
        if mode=='no_files':meta.pop('files')
        elif mode=='empty':meta['files']=[]
        elif mode=='no_role':original.pop('source');meta['files']=[original]
        elif mode=='two':meta['files']=[original,original]
        else:
            field,value={'non_pdf':('content_type','text/plain'),'bad_name':('name',''), 'size':('size',1),'sha':('sha256','bad'),'missing_descriptor':('name','other.pdf')}[mode]
            original[field]=value;meta['files']=[original]
        def altered(self: SourceSnapshotProtocol) -> Mapping[str,JsonValue]:
            """参数：真实 snapshot。返回：测试声明。异常：无。"""
            return meta
        monkeypatch.setattr(type(snapshot),'source_meta',property(altered))
        with pytest.raises(CnAnnualReportSourceError):project_cn_annual_report_original(snapshot)


@pytest.mark.parametrize('locator',('',None,42,' ','opaque locator'))
def test_actual_locator_exact_predicate(tmp_path: Path,monkeypatch: pytest.MonkeyPatch,locator: JsonValue) -> None:
    """参数：根及实际 locator。返回：无。异常：predicate 或原样保留漂移断言失败。"""
    pipeline=_seed(tmp_path);entry=pipeline.source_repository.read_source_meta_integrity_view('600519',SourceKind.FILING,batch=None)[0]
    assert entry.integrity.revision is not None
    publication=CnAnnualReportPublication('cninfo','A1',entry.document_id,entry.integrity.revision)
    snapshot=pipeline.source_repository.read_source_snapshot('600519',entry.document_id,SourceKind.FILING,materialize_files=True)
    meta={**snapshot.source_meta,'source_url':locator}
    def altered(self: SourceSnapshotProtocol) -> Mapping[str,JsonValue]:
        """参数：真实 snapshot。返回：原件 locator 测试声明。异常：无。"""
        return meta
    def acquire(ticker: str,document_id: str,source_kind: SourceKind,*,materialize_files: bool) -> SourceSnapshotProtocol:
        """参数：仓储 read 输入。返回：实际已取 snapshot。异常：无。"""
        return snapshot
    monkeypatch.setattr(type(snapshot),'source_meta',property(altered));monkeypatch.setattr(pipeline.source_repository,'read_source_snapshot',acquire)
    if type(locator) is str and locator!='':assert read_cn_annual_report_pdf('600519',entry.document_id,publication,entry.source_meta,pipeline.source_repository,None).source_url==locator
    else:
        with pytest.raises(CnAnnualReportSourceError):read_cn_annual_report_pdf('600519',entry.document_id,publication,entry.source_meta,pipeline.source_repository,None)
    with pytest.raises(RuntimeError):snapshot.get_source(entry.document_id+'.pdf').open()


@pytest.mark.parametrize('field,value',(('covered_fiscal_periods',['FY','H1']),('covered_fiscal_periods',[]),('fiscal_year',2023),('is_deleted',True),('source_id','other')))
def test_raw_meta_same_revision_mismatch(tmp_path: Path,field: str,value: JsonValue) -> None:
    """参数：根及 raw JSON 差异。返回：无。异常：静默规范化或旧值被信任断言失败。"""
    pipeline=_seed(tmp_path);entry=pipeline.source_repository.read_source_meta_integrity_view('600519',SourceKind.FILING,batch=None)[0]
    assert entry.integrity.revision is not None
    witness=CnAnnualReportPublication('cninfo','A1',entry.document_id,entry.integrity.revision)
    with pytest.raises(SourceIntegrityRevisionConflictError):read_cn_annual_report_pdf('600519',entry.document_id,witness,{**entry.source_meta,field:value},pipeline.source_repository,None)


@pytest.mark.parametrize('at',range(1,6))
def test_cancel_every_read_checkpoint(tmp_path: Path,monkeypatch: pytest.MonkeyPatch,at: int) -> None:
    """参数：根与 checkpoint 序号。返回：无。异常：取消对象改变或快照未释放断言失败。"""
    pipeline=_seed(tmp_path);entry=pipeline.source_repository.read_source_meta_integrity_view('600519',SourceKind.FILING,batch=None)[0]
    assert entry.integrity.revision is not None
    witness=CnAnnualReportPublication('cninfo','A1',entry.document_id,entry.integrity.revision)
    expected=CnDownloadCancelledError('source cancelled');calls:list[int]=[];snapshots:list[SourceSnapshotProtocol]=[];real=pipeline.source_repository.read_source_snapshot
    def acquire(ticker: str,document_id: str,source_kind: SourceKind,*,materialize_files: bool) -> SourceSnapshotProtocol:
        """参数：真实仓储输入。返回：真实 snapshot。异常：原仓储错误。"""
        snapshot=real(ticker,document_id,source_kind,materialize_files=materialize_files);snapshots.append(snapshot);return snapshot
    def checkpoint() -> None:
        """参数：无。返回：无。异常：指定点原取消对象。"""
        calls.append(1)
        if len(calls)==at:raise expected
    monkeypatch.setattr(pipeline.source_repository,'read_source_snapshot',acquire)
    with pytest.raises(CnDownloadCancelledError) as raised:read_cn_annual_report_pdf('600519',entry.document_id,witness,entry.source_meta,pipeline.source_repository,checkpoint)
    assert raised.value is expected
    for snapshot in snapshots:
        with pytest.raises(RuntimeError):snapshot.get_source(entry.document_id+'.pdf').open()


@pytest.mark.parametrize('kind',('value','missing','os','repair','unsafe','revision'))
def test_acquire_error_mapping(tmp_path: Path,monkeypatch: pytest.MonkeyPatch,kind: str) -> None:
    """参数：根及真实 acquire 故障类型。返回：无。异常：错映射或重复 acquire 断言失败。"""
    pipeline=_seed(tmp_path);entry=pipeline.source_repository.read_source_meta_integrity_view('600519',SourceKind.FILING,batch=None)[0]
    assert entry.integrity.revision is not None
    witness=CnAnnualReportPublication('cninfo','A1',entry.document_id,entry.integrity.revision)
    expected=FileNotFoundError() if kind=='missing' else OSError('storage') if kind=='os' else ValueError('storage')
    def acquire(ticker: str,document_id: str,source_kind: SourceKind,*,materialize_files: bool) -> SourceSnapshotProtocol:
        """参数：仓储输入。返回：不返回。异常：测试原错误。"""
        raise expected
    classification=entry.integrity
    if kind=='repair':classification=replace(classification,status=SourceIntegrityStatus.REPAIR_REQUIRED,reasons=(SourceIntegrityReason.SIZE_MISMATCH,))
    elif kind=='unsafe':classification=replace(classification,status=SourceIntegrityStatus.UNSAFE,revision=None,reasons=(SourceIntegrityReason.META_UNTRUSTED,))
    elif kind=='revision':classification=replace(classification,revision=SourceDocumentRevision('different'))
    def classify(ticker: str,document_id: str,source_kind: SourceKind) -> SourceIntegrityClassification:
        """参数：目标。返回：所观察分类。异常：无。"""
        return classification
    monkeypatch.setattr(pipeline.source_repository,'read_source_snapshot',acquire);monkeypatch.setattr(pipeline.source_repository,'classify_source_integrity',classify)
    error_type={'repair':SourceIntegrityRepairRequiredError,'unsafe':SourceIntegrityPreflightError,'revision':SourceIntegrityRevisionConflictError,'missing':SourceIntegrityRevisionConflictError}.get(kind,type(expected))
    with pytest.raises(error_type) as raised:read_cn_annual_report_pdf('600519',entry.document_id,witness,entry.source_meta,pipeline.source_repository,None)
    if kind in ('value','os'):assert raised.value is expected
    else:assert raised.value.__cause__ is expected
