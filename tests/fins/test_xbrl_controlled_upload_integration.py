"""受控 XBRL owner 失败合同及外部许可真实 CLI/Fs 集成。

真实输入由本轮管理员资源显式提供，不把许可原件纳为仓库 fixture。
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from io import BytesIO
from typing import cast
import pytest
from docling.datamodel.base_models import ConversionStatus, DocumentStream, InputFormat
from docling.datamodel.document import ConversionResult, _DocumentConversionInput, get_input_rejection_cause
from docling.exceptions import DocumentLoadError
from dayu.documents import docling_runtime
from dayu.runtime.interruptible_process import InterruptibleProcessCompleted
from tests.fins.test_docling_process_converter import _forbidden_xbrl_pdf_dispatch, _observe_synthetic_policy
from dayu.contracts.json_value import JsonValue
from dayu.documents.xbrl_config import PreparedXbrlInput, XbrlConfigurationError
from dayu.fins.pipelines import docling_process_converter as process
from dayu.fins.pipelines.docling_upload_service import build_material_ids
from dayu.fins.storage import FsMaterialUploadStateRepository, FsSourceDocumentRepository
from dayu.fins.domain.enums import SourceKind
from dayu.runtime.macos_sandbox import MacosSandboxError
from tests.documents.test_xbrl_config import _deployment, _loaded

@pytest.mark.asyncio
@pytest.mark.parametrize('name',['report.xml','report.xbrl','report.XML'])
async def test_unconfigured_xbrl_no_generic_fallback(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：候选名/替身；返回：无；异常：非 construction 或通用分支调用时断言失败。"""
    def forbidden(*args: bytes, **kwargs: str) -> None:
        """参数：不得发生的通用转换；返回：无；异常：任何调用均失败。"""
        raise AssertionError('uncontrolled generic conversion forbidden')
    monkeypatch.setattr(process,'convert_pdf_bytes_with_docling',forbidden)
    with pytest.raises(process.DoclingConversionError) as error:
        await process.ProcessDoclingConverter(xbrl_config=None).convert_to_json_bytes(b'<synthetic/>',name,config=process.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,cancellation=None)
    assert error.value.kind is process.DoclingConversionFailureKind.CONVERTER_CONSTRUCTION
    assert isinstance(error.value.__cause__,XbrlConfigurationError)

def test_worker_policy_and_snapshot_failure_are_construction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：合成快照/属性工具；返回：无；异常：worker 先于复验解析或错误分类漂移时断言失败。"""
    config,_,_=_deployment(tmp_path); loaded=_loaded(config,tmp_path/'workspace')
    prepared=process.prepare_xbrl_input(loaded,snapshot_root=tmp_path/'snapshot',writable_root=tmp_path/'work',stream_name='report.xml')
    input_path=tmp_path/'input.xml'; input_path.write_bytes(b'<synthetic/>')
    target=process._DoclingProcessTarget(str(input_path),str(prepared.writable_root/'out.json'),'report.xml',process.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,prepared,'synthetic-profile')
    def failure(profile: str) -> None:
        """参数：策略；返回：无；异常：明确模拟内核应用失败。"""
        raise MacosSandboxError('synthetic sandbox application failure')
    monkeypatch.setattr(process,'apply_macos_sandbox',failure)
    original=Path.cwd()
    for key in ('TMPDIR','XDG_CONFIG_HOME','XDG_CACHE_HOME'): monkeypatch.setenv(key,os.environ.get(key,'synthetic-before'))
    monkeypatch.setattr(process.tempfile,'tempdir',process.tempfile.tempdir)
    try:
        descriptor=target(); assert isinstance(descriptor,dict)
        assert descriptor['failure_kind']=='converter_construction'
        def applied(profile: str) -> None:
            """参数：合成策略；返回：无；异常：无，仅验证复验首序。"""
        monkeypatch.setattr(process,'apply_macos_sandbox',applied)
        path=prepared.taxonomy_snapshot_root/'issuer.xsd'; path.chmod(0o600); path.write_bytes(b'tamper')
        descriptor=target(); assert isinstance(descriptor,dict); assert descriptor['failure_kind']=='converter_construction'
    finally:
        os.chdir(original)

def test_real_external_instance_cli_manifest_and_repository_readback(tmp_path: Path) -> None:
    """参数：全新仓储和显式外部资源；返回：无；异常：真实 CLI/提交/hash/主源失败时断言失败。"""
    resource=os.environ.get('DAYU_S3_XBRL_RESOURCE')
    if resource is None:
        pytest.skip('真实混合许可材料需显式外部管理员资源；本轮验收必须配置此项')
    info=cast(dict[str,JsonValue],json.loads(Path(resource).read_text()))
    instance=Path(cast(str,info['instance'])); config=cast(str,info['config'])
    assert hashlib.sha256(instance.read_bytes()).hexdigest()=='04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1'
    base=tmp_path/'store'; material='S3 real controlled external instance'
    argv=[sys.executable,'-m','dayu.cli','upload_material','--base',str(base),'--ticker','MLAC','--action','auto','--forms','MATERIAL_OTHER','--material-name',material,'--company-name','Mountain Lake Acquisition Corp.','--files',str(instance)]
    environment=os.environ.copy(); environment['DAYU_XBRL_CONFIG']=config
    (tmp_path/'command.json').write_text(json.dumps({'argv':argv,'cwd':str(Path.cwd()),'DAYU_XBRL_CONFIG':config},indent=2)+'\n')
    completed=subprocess.run(argv,env=environment,cwd=Path.cwd(),stdin=subprocess.DEVNULL,capture_output=True,timeout=90,check=False)
    (tmp_path/'stdout').write_bytes(completed.stdout); (tmp_path/'stderr').write_bytes(completed.stderr)
    (tmp_path/'actual-exit.json').write_text(json.dumps({'actual_exit':completed.returncode,'actual_wait':True})+'\n')
    assert completed.returncode==0,completed.stderr.decode()
    identity=build_material_ids(form_type='MATERIAL_OTHER',material_name=material,fiscal_year=None,fiscal_period=None,document_id=None)
    state=FsMaterialUploadStateRepository(base).read_material_upload_state('MLAC',identity.document_id)
    assert state.source_integrity.status.value=='complete' and state.publication_identity is not None
    assert state.publication_identity.primary_document==instance.name+'_docling.json'
    assert state.publication_identity.document_version=='v1' and state.publication_identity.amended is False
    source=FsSourceDocumentRepository(base)
    with source.read_source_snapshot('MLAC',identity.document_id,SourceKind.MATERIAL,materialize_files=True) as snapshot:
        with snapshot.get_source(instance.name).open() as stream:
            assert hashlib.sha256(stream.read()).hexdigest()=='04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1'
        with snapshot.get_primary_source().open() as stream:
            document=cast(JsonValue,json.load(stream)); assert isinstance(document,dict)
            assert document['schema_name']=='DoclingDocument'
            assert isinstance(document['key_value_items'],list) and document['key_value_items']


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix,content',[('.xml',b'<ordinary>synthetic plain XML</ordinary>'),('.xbrl',b'<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase"/>'),('.xml',b'<broken'),('.json',b'{"synthetic":"not a Docling document"}')])
async def test_real_invalid_content_no_success(suffix: str, content: bytes) -> None:
    """参数：明确合成无效内容；返回：无；异常：真实转换假成功或错误类型漂移时断言失败。"""
    resource=os.environ.get('DAYU_S3_XBRL_RESOURCE')
    if resource is None: pytest.skip('真实受控运行需显式管理员资源，本轮必配')
    from dayu.documents.xbrl_config import load_xbrl_conversion_config
    info=cast(dict[str,JsonValue],json.loads(Path(resource).read_text()))
    config=load_xbrl_conversion_config(Path(cast(str,info['config'])),Path.cwd())
    with pytest.raises(process.DoclingConversionError) as error:
        await process.ProcessDoclingConverter(xbrl_config=config).convert_to_json_bytes(content,'negative'+suffix,config=process.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,cancellation=None)
    assert error.value.kind is process.DoclingConversionFailureKind.CONVERTER_EXECUTION


_SYNTHETIC_XBRL_LOAD_FAILURE = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<html xmlns="http://www.xbrl.org/2003/instance"><body><xbrl/></body></html>'
)


class _RealRejectedResultRelease:
    """观察真实 Docling 拒绝结果的释放调用，不伪造 backend 或成功转换。"""

    def __init__(self) -> None:
        """参数：无；返回：无；异常：无，初始化计数。"""
        self.calls = 0

    def release(self, conversion: ConversionResult) -> None:
        """参数：worker 持有的真实结果；返回：无；异常：形状/owner 回归时失败。"""
        self.calls += 1
        assert conversion.status is ConversionStatus.FAILURE
        assert conversion.input.format is InputFormat.XML_XBRL
        assert conversion.input.valid is False
        assert isinstance(get_input_rejection_cause(conversion.input), DocumentLoadError)
        # 直接断言本次真实第三方对象尚未绑定属性，不固化 None fixture。
        with pytest.raises(AttributeError):
            _ = conversion.input._backend
        docling_runtime.unload_xbrl_conversion(conversion)


def test_real_xbrl_load_rejection_retains_worker_and_parent_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """参数：独占根/观察工具；返回：无；异常：真实坏内容路由、结果或父投影漂移时失败。

    内核应用在此控制流测试中显式替换；真实 CLI 隔离票据必须另行采集。
    """
    config, _, _ = _deployment(tmp_path)
    prepared = process.prepare_xbrl_input(
        _loaded(config, tmp_path / 'workspace'), snapshot_root=tmp_path / 'snapshot',
        writable_root=tmp_path / 'work', stream_name='routed-bad.xml',
    )
    guessed = _DocumentConversionInput(path_or_stream_iterator=[])._guess_format(
        DocumentStream(name='routed-bad.xml', stream=BytesIO(_SYNTHETIC_XBRL_LOAD_FAILURE)),
    )
    assert guessed is InputFormat.XML_XBRL
    input_path = tmp_path / 'input.xml'
    output_path = prepared.writable_root / 'output.json'
    input_path.write_bytes(_SYNTHETIC_XBRL_LOAD_FAILURE)
    observer = _RealRejectedResultRelease()
    monkeypatch.setattr(process, 'unload_xbrl_conversion', observer.release)
    monkeypatch.setattr(process, 'convert_pdf_bytes_with_docling', _forbidden_xbrl_pdf_dispatch)
    monkeypatch.setattr(process, 'apply_macos_sandbox', _observe_synthetic_policy)
    monkeypatch.chdir(Path.cwd())
    for key in ('TMPDIR', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
        monkeypatch.setenv(key, os.environ.get(key, 'synthetic-before'))
    monkeypatch.setattr(process.tempfile, 'tempdir', process.tempfile.tempdir)
    target = process._DoclingProcessTarget(
        str(input_path), str(output_path), 'routed-bad.xml',
        process.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG, prepared, 'synthetic-profile',
    )
    descriptor = target()
    assert observer.calls == 1
    assert descriptor == process._failure_descriptor(process.DoclingConversionFailureKind.CONVERTER_EXECUTION)
    assert not output_path.exists()
    with pytest.raises(process.DoclingConversionError) as error:
        process._read_terminal_result(
            output_path=output_path, wait_result=InterruptibleProcessCompleted(value=descriptor, exitcode=0),
        )
    assert error.value.kind is process.DoclingConversionFailureKind.CONVERTER_EXECUTION
    assert error.value.exit_code == 0
