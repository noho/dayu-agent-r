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
from dataclasses import dataclass
from typing import cast
import pytest
from docling.datamodel.base_models import ConversionStatus, DocumentStream, InputFormat
from docling.datamodel.document import ConversionResult, _DocumentConversionInput, get_input_rejection_cause
from docling.exceptions import DocumentLoadError
from dayu.documents import docling_runtime
from dayu.runtime.interruptible_process import InterruptibleProcessCompleted
from tests.fins.test_docling_process_converter import _forbidden_xbrl_pdf_dispatch, _observe_synthetic_policy, _run_xbrl_spawn
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


def test_worker_policy_and_snapshot_failure_are_construction(tmp_path: Path) -> None:
    """参数：独占快照；返回：无；异常：真实 spawn 先序或 construction 分类漂移失败。"""
    for mode in ('policy', 'tamper'):
        root = tmp_path / mode; root.mkdir()
        config, _, _ = _deployment(root)
        prepared = process.prepare_xbrl_input(_loaded(config, root / 'workspace'), snapshot_root=root / 'snapshot', writable_root=root / 'work', stream_name='report.xml')
        input_path = root / 'input.xml'; input_path.write_bytes(b'<synthetic/>')
        diagnostics = prepared.writable_root / 'diagnostics'; diagnostics.mkdir(mode=0o700)
        target = process._DoclingProcessTarget(str(input_path), str(prepared.writable_root / 'out.json'), 'report.xml', process.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG, prepared, 'synthetic-profile', str(diagnostics))
        descriptor = _run_xbrl_spawn(_IntegrationSpawnProbe(target, mode, str(root / 'observed.json')))
        assert isinstance(descriptor, dict) and descriptor['failure_kind'] == 'converter_construction'


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
    diagnostics = prepared.writable_root / 'diagnostics'; diagnostics.mkdir(mode=0o700)
    target = process._DoclingProcessTarget(str(input_path), str(output_path), 'routed-bad.xml', process.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG, prepared, 'synthetic-profile', str(diagnostics))
    observation = tmp_path / 'observed.json'
    descriptor = _run_xbrl_spawn(_IntegrationSpawnProbe(target, 'realreject', str(observation)))
    assert json.loads(observation.read_text()) == {'release': 1}
    assert descriptor == process._failure_descriptor(process.DoclingConversionFailureKind.CONVERTER_EXECUTION)
    assert not output_path.exists()
    with pytest.raises(process.DoclingConversionError) as error:
        process._read_terminal_result(
            output_path=output_path, wait_result=InterruptibleProcessCompleted(value=descriptor, exitcode=0),
        )
    assert error.value.kind is process.DoclingConversionFailureKind.CONVERTER_EXECUTION
    assert error.value.exit_code == 0


@dataclass(frozen=True, slots=True)
class _IntegrationSpawnProbe:
    """在独立真实 worker 观察受控失败路径；合成策略不作为内核票据。"""
    target: process._DoclingProcessTarget
    mode: str
    observation: str

    def __call__(self) -> JsonValue:
        """参数：无；返回：原 descriptor；异常：owner 断言或未闭合错误传播。"""
        patch = pytest.MonkeyPatch()
        observer = _RealRejectedResultRelease()
        patch.setattr(process, 'apply_macos_sandbox', _policy_failure if self.mode == 'policy' else _observe_synthetic_policy)
        patch.setattr(process, 'convert_pdf_bytes_with_docling', _forbidden_xbrl_pdf_dispatch)
        if self.mode == 'realreject':
            patch.setattr(process, 'unload_xbrl_conversion', observer.release)
            patch.setattr(process, 'convert_xbrl_bytes_with_docling', _observe_real_rejection_convert)
        if self.mode == 'tamper':
            assert self.target.xbrl_input is not None
            path = self.target.xbrl_input.taxonomy_snapshot_root / 'issuer.xsd'; path.chmod(0o600); path.write_bytes(b'tamper')
        try:
            descriptor = self.target()
            Path(self.observation).write_text(json.dumps({'release': observer.calls}))
            return descriptor
        finally: patch.undo()


def _policy_failure(profile: str) -> None:
    """参数：策略；返回：永不返回；异常：合成内核应用错误。"""
    raise MacosSandboxError('synthetic sandbox application failure')



def _observe_real_rejection_convert(input_bytes: bytes, *, stream_name: str, xbrl_input: PreparedXbrlInput) -> ConversionResult:
    """参数：真实坏输入/快照；返回：真实结果；异常：写独占观察后仍传播真实异常。"""
    import traceback
    try:
        return docling_runtime.convert_xbrl_bytes_with_docling(input_bytes, stream_name=stream_name, xbrl_input=xbrl_input)
    except Exception:
        (xbrl_input.writable_root / 'real-rejection-error.txt').write_text(traceback.format_exc())
        raise


@dataclass(frozen=True, slots=True)
class _KernelDiagnosticsProbe:
    """在真实 target 的内核策略下检查原许可边界，不扩策略或 descriptor。"""
    target: process._DoclingProcessTarget
    outside_workspace: str
    private_file: str
    parent_log: str
    admin_manifest: str

    def __call__(self) -> JsonValue:
        """参数：无；返回：测试 envelope 内原 descriptor 和内核事实；异常：权限或真实转换违例传播。"""
        import errno
        import logging
        import socket
        from dayu.runtime.process_diagnostics import ProcessLogDiagnostic, ProcessRawDiagnostic, read_process_diagnostics
        patch = pytest.MonkeyPatch(); facts: dict[str, JsonValue] = {}
        original = process.convert_xbrl_bytes_with_docling
        original_apply = process.apply_macos_sandbox
        def observe_apply(profile: str) -> None:
            """参数：原策略；返回：实际应用；异常：保留直接内核错误后原样传播。"""
            try: original_apply(profile)
            except Exception as exc:
                facts['sandbox_application_error'] = {'type': type(exc).__name__, 'message': str(exc)}
                raise
        patch.setattr(process, 'apply_macos_sandbox', observe_apply)
        assert self.target.xbrl_input is not None
        prepared = self.target.xbrl_input
        def observed(input_bytes: bytes, *, stream_name: str, xbrl_input: PreparedXbrlInput) -> ConversionResult:
            """参数：真实输入/快照；返回：真实转换结果；异常：内核拒绝与转换错误原样传播。"""
            checks = [('workspace_read', self.outside_workspace, os.O_RDONLY),
                      ('private_read', self.private_file, os.O_RDONLY),
                      ('parent_log_write', self.parent_log, os.O_WRONLY),
                      ('admin_write', self.admin_manifest, os.O_WRONLY),
                      ('runtime_write', str(Path(sys.executable).resolve()), os.O_WRONLY),
                      ('taxonomy_write', str(xbrl_input.taxonomy_snapshot_root / xbrl_input.manifest.files[0].relative_path), os.O_WRONLY)]
            for label, path, flags in checks:
                try:
                    fd = os.open(path, flags)
                except OSError as exc:
                    assert exc.errno in (errno.EPERM, errno.EACCES), (label, exc.errno)
                    facts[label] = {'denied': True, 'errno': exc.errno, 'path': path}
                else:
                    os.close(fd); raise AssertionError(label + ' unexpectedly allowed')
            with socket.socket() as network:
                try: network.connect(('127.0.0.1', 9))
                except OSError as exc:
                    assert exc.errno in (errno.EPERM, errno.EACCES), exc.errno
                    facts['network'] = {'denied': True, 'errno': exc.errno}
                else: raise AssertionError('network allowed')
            logging.getLogger('kernel.diagnostics').warning('real kernel structured warning')
            os.write(1, b'real kernel raw stdout\n'); os.write(2, b'real kernel raw stderr\n')
            # 新开 sidecar 路径也必须只在原 work 内可写。
            extra = xbrl_input.writable_root / 'diagnostics' / 'kernel-write.txt'
            extra.write_text('within original work')
            facts['diagnostics_directory'] = str(extra.parent)
            return original(input_bytes, stream_name=stream_name, xbrl_input=xbrl_input)
        patch.setattr(process, 'convert_xbrl_bytes_with_docling', observed)
        try:
            descriptor = self.target()
            facts['records'] = [v.message for v in read_process_diagnostics(Path(self.target.diagnostics_directory), require_complete=True) if isinstance(v, ProcessLogDiagnostic)]
            facts['raw'] = [v.data.decode('utf-8', errors='backslashreplace') for v in read_process_diagnostics(Path(self.target.diagnostics_directory), require_complete=True) if isinstance(v, ProcessRawDiagnostic)]
            facts['work_root'] = str(prepared.writable_root)
            return {'descriptor': descriptor, 'kernel_facts': facts}
        finally:
            patch.undo()


def test_real_kernel_diagnostics_respects_original_xbrl_permissions(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：独占外部数据目录/公开双流；返回：无；异常：真实内核许可、诊断隔离或转换失败时断言失败。"""
    from dayu.documents.xbrl_config import load_xbrl_conversion_config
    resource = os.environ.get('DAYU_S3_XBRL_RESOURCE')
    if resource is None: pytest.skip('真实内核验收需显式管理员资源；常规 coverage 跳过不计正例')
    assert not any(os.environ.get(k) for k in ('COVERAGE_PROCESS_START', 'COVERAGE_PROCESS_CONFIG', 'COVERAGE_FILE', 'COVERAGE_RCFILE'))
    info = cast(dict[str, JsonValue], json.loads(Path(resource).read_text()))
    instance = Path(cast(str, info['instance'])); config_path = Path(cast(str, info['config']))
    config = load_xbrl_conversion_config(config_path, tmp_path / 'workspace')
    assert config is not None
    prepared = process.prepare_xbrl_input(config, snapshot_root=tmp_path / 'taxonomy', writable_root=tmp_path / 'work', stream_name=instance.name)
    input_root = tmp_path / 'input'; input_root.mkdir(); input_path = input_root / 'input.xml'
    input_path.write_bytes(instance.read_bytes()); input_path.chmod(0o400)
    diagnostic_root = prepared.writable_root / 'diagnostics'; diagnostic_root.mkdir(mode=0o700)
    workspace_file = tmp_path / 'workspace' / 'canary.txt'; workspace_file.parent.mkdir(); workspace_file.write_text('workspace private fixture')
    private_file = tmp_path / 'private' / 'canary.txt'; private_file.parent.mkdir(); private_file.write_text('private fixture')
    log = tmp_path / 'parent.log'; log.write_text('parent only')
    profile = process._build_xbrl_sandbox_profile(input_root=input_root, prepared=prepared)
    target = process._DoclingProcessTarget(str(input_path), str(prepared.writable_root / 'output.json'), instance.name,
                                          process.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG, prepared, profile, str(diagnostic_root))
    envelope = _run_xbrl_spawn(_KernelDiagnosticsProbe(target, str(workspace_file), str(private_file), str(log), str(config_path.parent / 'manifest.json')))
    (tmp_path / 'kernel-profile.sb').write_text(profile)
    (tmp_path / 'kernel-result.json').write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + '\n')
    assert isinstance(envelope, dict)
    descriptor = envelope['descriptor']; facts = envelope['kernel_facts']; assert isinstance(facts, dict)
    assert isinstance(descriptor, dict) and descriptor['status'] == 'success', envelope
    for key in ('workspace_read', 'private_read', 'parent_log_write', 'admin_write', 'runtime_write', 'taxonomy_write', 'network'):
        fact = facts[key]; assert isinstance(fact, dict) and fact['denied'] is True
    assert facts['diagnostics_directory'] == str(diagnostic_root)
    assert isinstance(facts['records'], list) and 'real kernel structured warning' in facts['records']
    assert isinstance(facts['raw'], list) and 'real kernel raw stdout\n' in facts['raw'] and 'real kernel raw stderr\n' in facts['raw']
    assert log.read_text() == 'parent only'
    (tmp_path / 'kernel-profile.sb').write_text(profile)
    (tmp_path / 'kernel-result.json').write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + '\n')
    public = capfd.readouterr(); assert public.out == public.err == ''
