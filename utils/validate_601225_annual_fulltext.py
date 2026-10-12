"""独立验收：真实摘要 seed、全部源/Docling 核验、repeat 比较与逐文件覆盖率。"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from dataclasses import replace
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import cast

from docling.utils.utils import create_file_hash
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.common.origin import DocumentOrigin

from observe_601225_cli_http import summarize_http
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.downloaders.cninfo_downloader import _parse_raw_announcement, JsonValue as ProviderJsonValue
from dayu.fins.pipelines.cn_annual_report_facts import resolve_cn_annual_report_facts
from dayu.fins.pipelines.cn_annual_report_source import project_cn_annual_report_original
from dayu.fins.pipelines.cn_download_models import CnCompanyProfile, CnReportCandidate, CnReportPeriodProjection
from dayu.fins.pipelines.cn_download_source_upsert import build_cn_file_entry, build_content_fingerprint, build_remote_fingerprint, commit_cn_filing_source_document
from dayu.fins.pipelines.cn_form_utils import build_cn_filing_ids
from dayu.fins.pipelines.docling_converter_factory import create_docling_converter
from dayu.fins.pipelines.docling_process_converter import DEFAULT_FINS_DOCLING_CONVERSION_CONFIG
from dayu.fins.storage import FsSourceDocumentRepository, FsBatchingRepository, FsDocumentBlobRepository, FsProcessedDocumentRepository
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage.source_integrity import SourceIntegrityStatus

_REPO = Path(__file__).resolve().parents[1]
_TARGETS = {'1213161683':2021,'1219815158':2023,'1223301988':2024}
_SEEDS = ('1213161682','1223301999')
_REPEAT_GETS = {'clean-repeat':{'1204545056','1209875597','1213161682','1223301999'},'seeded-repeat':{'1204545056','1209875597'}}
_PRODUCTION = (
 'dayu/fins/pipelines/cn_annual_report_facts.py','dayu/fins/pipelines/cn_annual_report_source.py',
 'dayu/fins/storage/source_integrity.py','dayu/fins/downloaders/cninfo_downloader.py','dayu/fins/downloaders/hkexnews_downloader.py',
 'dayu/fins/pipelines/cn_download_models.py','dayu/fins/pipelines/cn_download_protocols.py','dayu/fins/pipelines/cn_report_selection.py',
 'dayu/fins/pipelines/cn_download_identity.py','dayu/fins/pipelines/cn_download_workflow.py',
 'dayu/fins/pipelines/cn_download_filing_workflow.py','dayu/fins/pipelines/cn_download_source_upsert.py')


def _json(path: Path) -> JsonValue:
    """读辅助 JSON。参数：path。返回：实际 JSON。异常：I/O/JSON 原错误。"""
    return cast(JsonValue,json.loads(path.read_bytes()))


def _mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    """校验辅助 object。参数：value。返回：mapping。异常：ValueError 为非法结构。"""
    if not isinstance(value,Mapping):raise ValueError('expected JSON object')
    return value


def _text(value: JsonValue) -> str:
    """校验字符串。参数：value。返回：原值。异常：ValueError 为非法结构。"""
    if type(value) is not str:raise ValueError('expected string')
    return value


def _evidence(evidence_root: Path) -> dict[str, Mapping[str, JsonValue]]:
    """读取冻结官方 PDF hash。参数：evidence_root。返回：source→原记录。异常：非法证据拒绝。"""
    rows=_json(evidence_root/'official-pdf-evidence.json')
    if not isinstance(rows,list):raise ValueError('official evidence not list')
    return {_text(_mapping(row)['source_id']):_mapping(row) for row in rows}


def source_records(base: Path, evidence_root: Path) -> dict[str, JsonValue]:
    """经仓储读取全部源并核原件、primary、hash、model 与 origin。

    参数：base 为独立根；evidence_root 为冻结官方原件。返回：完整 source→资产/metadata/revision。
    异常：声明/事实/产物不一致拒绝，仓储原错误透传。
    """
    source=FsSourceDocumentRepository(base,create_directories=False)
    records:dict[str,JsonValue]={};official=_evidence(evidence_root)
    ids=source.list_source_document_ids('601225',SourceKind.FILING)
    for document_id in ids:
        integrity=source.classify_source_integrity('601225',document_id,SourceKind.FILING)
        if integrity.status is not SourceIntegrityStatus.COMPLETE:raise ValueError('held source not COMPLETE')
        with source.read_source_snapshot('601225',document_id,SourceKind.FILING,materialize_files=True) as snapshot:
            meta=snapshot.source_meta;sid=_text(meta['source_id'])
            if sid in records:raise ValueError('duplicate held source key')
            original=project_cn_annual_report_original(snapshot)
            primary=tuple(d for d in snapshot.files if d.name==snapshot.primary_filename)
            declarations=meta['files'];assert isinstance(declarations,list)
            docling=tuple(_mapping(e) for e in declarations if _mapping(e).get('source')=='docling' and _mapping(e).get('name')==snapshot.primary_filename and _mapping(e).get('content_type')=='application/json')
            if len(primary)!=1 or len(docling)!=1 or meta.get('primary_document')!=snapshot.primary_filename:raise ValueError('primary declaration mismatch')
            with snapshot.get_source(original.name).open() as stream:pdf=stream.read()
            with snapshot.get_source(primary[0].name).open() as stream:json_bytes=stream.read()
            pdf_sha=hashlib.sha256(pdf).hexdigest();json_sha=hashlib.sha256(json_bytes).hexdigest()
            for descriptor,payload in ((original,pdf),(primary[0],json_bytes)):
                if descriptor.size!=len(payload) or descriptor.sha256!=hashlib.sha256(payload).hexdigest():raise ValueError('descriptor SHA/size missing or mismatch')
                declared=next(_mapping(e) for e in declarations if _mapping(e).get('name')==descriptor.name)
                if declared.get('size')!=len(payload) or declared.get('sha256')!=descriptor.sha256:raise ValueError('declared SHA/size missing or mismatch')
            if meta.get('pdf_sha256')!=pdf_sha:raise ValueError('source PDF SHA mismatch')
            fingerprint=build_content_fingerprint(pdf_bytes=pdf,docling_json_bytes=json_bytes)
            if meta.get('source_fingerprint')!=fingerprint:raise ValueError('content fingerprint mismatch')
            model=DoclingDocument.model_validate_json(json_bytes)
            expected=DocumentOrigin.model_validate({'mimetype':'application/pdf','filename':original.name,'binary_hash':create_file_hash(BytesIO(pdf))})
            if model.origin is None or not model.pages or model.origin!=expected:raise ValueError('actual model/origin/pages mismatch')
            body_count=len(model.body.children);text_count=sum(bool(item.text.strip()) for item in model.texts)
            facts:dict[str,JsonValue]={}
            if meta.get('fiscal_period')=='FY':
                annual=resolve_cn_annual_report_facts(pdf)
                facts={'fiscal_year':annual.fiscal_year,'kind':annual.kind}
                if sid in _TARGETS:
                    if annual.kind!='full' or annual.fiscal_year!=_TARGETS[sid] or meta.get('fiscal_year')!=annual.fiscal_year or meta.get('fiscal_year_source')!='source_document':raise ValueError('target year/full/provenance mismatch')
                    if meta.get('is_deleted') is not False or meta.get('ingest_complete') is not True or not body_count or not text_count:raise ValueError('target active/model content sanity failed')
                    if official[sid]['sha256']!=pdf_sha:raise ValueError('target official PDF SHA mismatch')
                if sid in _SEEDS and (annual.kind!='summary' or official[sid]['sha256']!=pdf_sha):raise ValueError('seed summary facts/SHA mismatch')
            records[sid]={'document_id':document_id,'provider':meta.get('source_provider'),'revision':snapshot.revision.token,
                          'meta':dict(meta),'status':integrity.status.value,'original_name':original.name,'primary_name':primary[0].name,
                          'pdf_sha256':pdf_sha,'pdf_size':len(pdf),'json_sha256':json_sha,'json_size':len(json_bytes),
                          'fingerprint_expected':fingerprint,'facts':facts,'model_valid':True,
                          'origin_expected':cast(JsonValue,json.loads(expected.model_dump_json())),
                          'origin_actual':cast(JsonValue,json.loads(model.origin.model_dump_json())),
                          'body_children':body_count,'nonempty_text_items':text_count}
    return records


async def seed(base: Path, evidence_root: Path) -> dict[str, JsonValue]:
    """只在空独立 base 经生产 Docling 和仓储 seed 两份实际官方摘要。

    参数：base/evidence_root。返回：成功后的完整资产核验。异常：原转换/commit/事实错误，不发布半成品。
    """
    base.resolve().relative_to(_REPO/'workspace/tmp')
    if base.exists() and any(base.iterdir()):raise ValueError('seed base must be empty')
    repositories=build_fs_repository_set(workspace_root=base)
    batching=FsBatchingRepository(base,repository_set=repositories);source=FsSourceDocumentRepository(base,repository_set=repositories)
    blob=FsDocumentBlobRepository(base,repository_set=repositories);processed=FsProcessedDocumentRepository(base,repository_set=repositories)
    converter=create_docling_converter(base);evidence=_evidence(evidence_root)
    raw=_mapping(_json(evidence_root/'current-002.response.bin'))['announcements'];assert isinstance(raw,list)
    by_id={item.announcement_id:item for row in raw if (item:=_parse_raw_announcement(cast(ProviderJsonValue,row))) is not None}
    for sid in _SEEDS:
        pdf=(evidence_root/f'{sid}.pdf').read_bytes();sha=hashlib.sha256(pdf).hexdigest();facts=resolve_cn_annual_report_facts(pdf)
        if facts.kind!='summary' or sha!=evidence[sid]['sha256']:raise ValueError('seed original mismatch')
        item=by_id[sid]
        candidate=CnReportCandidate(provider='cninfo',source_id=sid,source_url=item.source_url,title=item.title,language='zh',
            filing_date=item.announcement_date,fiscal_year=facts.fiscal_year,fiscal_year_source='source_document',
            period_projection=CnReportPeriodProjection('FY',('FY',)),amended=False,content_length=len(pdf),etag=None,last_modified=None)
        docid,internal=build_cn_filing_ids(ticker='601225',form_type='FY',fiscal_year=facts.fiscal_year,fiscal_period='FY',amended=False)
        pdf_name=f'{docid}.pdf';json_name=f'{docid}_docling.json'
        print(f'seed conversion_started source_id={sid}',flush=True)
        conversion=await converter.convert_to_json_bytes(pdf,pdf_name,config=DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,cancellation=None)
        docling=conversion.json_bytes
        print(f'seed conversion_completed source_id={sid}',flush=True)
        batch=batching.begin_batch('601225');commit_started=False
        try:
            handle=SourceHandle('601225',docid,SourceKind.FILING.value)
            pdf_meta=blob.store_file(handle,pdf_name,BytesIO(pdf),content_type='application/pdf',batch=batch)
            json_meta=blob.store_file(handle,json_name,BytesIO(docling),content_type='application/json',batch=batch)
            commit_cn_filing_source_document(source_repository=source,processed_repository=processed,ticker='601225',document_id=docid,
                internal_document_id=internal,primary_document=json_name,
                file_entries=[build_cn_file_entry(filename=pdf_name,file_meta=pdf_meta,source_label='original'),build_cn_file_entry(filename=json_name,file_meta=json_meta,source_label='docling')],
                candidate=candidate,profile=CnCompanyProfile('cninfo','CNINFO:9900023204','陕西煤业','601225'),pdf_sha256=sha,
                remote_fingerprint=build_remote_fingerprint(candidate),source_fingerprint=build_content_fingerprint(pdf_bytes=pdf,docling_json_bytes=docling),
                previous_completed_meta=None,source_meta_exists=False,batch=batch)
            commit_started=True;batching.commit_batch(batch)
        finally:
            if not commit_started:batching.rollback_batch(batch)
    return {'validation_status':'passed','scenario':'seed','sources':source_records(base,evidence_root)}


def _progress_record(line: str) -> Mapping[str, JsonValue]:
    """逐项 JSON decode 公开进度值，支持含空格消息。参数：line 为前缀后内容。返回：字段。异常：非法格式拒绝。"""
    decoder=json.JSONDecoder();fields:dict[str,JsonValue]={};remaining=line
    while remaining:
        match=re.match(r'([a-z_]+)=',remaining)
        if match is None:raise ValueError('progress key malformed')
        value,end=decoder.raw_decode(remaining[match.end():]);fields[match[1]]=cast(JsonValue,value)
        remaining=remaining[match.end()+end:].lstrip()
    return fields


def verify(base: Path, evidence_root: Path, run_dir: Path) -> dict[str, JsonValue]:
    """核验 actual CLI、全部源及网络/转换全集。参数：三个证据根。返回：辅助结果。异常：任一不一致拒绝。"""
    run=_mapping(_json(run_dir/'run.json'));http=_mapping(_json(run_dir/'http-summary.json'))
    if run.get('status')!='exited' or run.get('exit_code')!=0 or http.get('validation_status')!='passed':raise ValueError('actual CLI/observer failed or incomplete')
    pid=run.get('pid')
    if not isinstance(pid,int):raise ValueError('CLI PID missing')
    observed=summarize_http(run_dir,pid)
    if observed['validation_status']!='passed':raise ValueError('strict actual HTTP reconciliation failed:'+str(observed['errors']))
    for field in ('pdf_get_attempt_counts','pdf_get_wire_counts','annual_raw_count'):
        if observed[field]!=http.get(field):raise ValueError('observer saved/recomputed mismatch')
    http=observed
    sources=source_records(base,evidence_root)
    if not set(_TARGETS)<=set(sources):raise ValueError('target full source missing')
    by_name={_text(_mapping(row)['primary_name']):sid for sid,row in sources.items()}
    conversions:dict[str,JsonValue]={sid:{'started':0,'completed':0} for sid in sources}
    diagnostics:list[Mapping[str,JsonValue]]=[]
    for filename in ('stdout.txt','stderr.txt'):
        for line in (run_dir/filename).read_text().splitlines():
            if line.startswith('Fins progress: '):
                fields=_progress_record(line.removeprefix('Fins progress: '));stage=fields.get('stage')
                if fields.get('operation')!='download':raise ValueError('unexpected operation')
                if stage in ('download.conversion_started','download.conversion_completed'):
                    name=_text(fields['document'])
                    if name not in by_name:raise ValueError('unknown conversion document')
                    counts=_mapping(conversions[by_name[name]]);key='started' if stage=='download.conversion_started' else 'completed';count=counts[key];assert isinstance(count,int)
                    conversions[by_name[name]]={**counts,key:count+1}
            if line.startswith('Fins download diagnostics: '):diagnostics.append(_mapping(cast(JsonValue,json.loads(line.removeprefix('Fins download diagnostics: ')))))
    if len(diagnostics)!=1:raise ValueError('diagnostics missing/duplicate')
    diagnostic=diagnostics[0];summary=_mapping(diagnostic['summary']);counts=_mapping(summary['counts'])
    if (diagnostic.get('status')!='success' or diagnostic.get('exit_code')!=0 or diagnostic.get('failure') is not None or diagnostic.get('failed_documents')!=[]
        or summary.get('terminal_disposition')!='succeeded' or any(counts.get(k)!=0 for k in ('failed','rejected','uncertain'))
        or summary.get('uncertain_reports')!=[] or summary.get('omitted_uncertain_count')!=0):raise ValueError('public terminal diagnostics failed')
    for sid,raw_counts in conversions.items():
        c=_mapping(raw_counts)
        if c['started']!=c['completed'] or c['started'] not in (0,1):raise ValueError('conversion event count not closed')
    first=run_dir.name.endswith('01')
    if first and any(_mapping(conversions[sid])['started']!=1 for sid in _TARGETS):raise ValueError('target actual conversion absent')
    if not first and any(_mapping(c)['started']!=0 for c in conversions.values()):raise ValueError('repeat converted held source')
    return {'validation_status':'passed','sources':sources,'source_count':len(sources),'run':dict(run),'http':dict(http),'conversion_counts':conversions,'diagnostics':dict(diagnostic)}


def compare(scenario: str, before: Mapping[str, JsonValue], after: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """比较全部持有资产与精确 GET 集合。参数：scenario、两次 verify。返回：差异列表。异常：不一致拒绝。"""
    previous=_mapping(before['sources']);current=_mapping(after['sources']);diffs:list[JsonValue]=[]
    for sid,row in previous.items():
        if current.get(sid)!=row:diffs.append('source_changed:'+sid)
    if scenario=='seeded-first':
        if set(previous)!=set(_SEEDS):diffs.append('seed_set_mismatch')
        for sid in _TARGETS:
            full=_mapping(current[sid])
            if any(full['document_id']==_mapping(previous[s])['document_id'] for s in _SEEDS):diffs.append('summary_full_identity_collision')
    else:
        if set(previous)!=set(current):diffs.append('held_set_changed')
        http=_mapping(after['http'])
        for field in ('pdf_get_attempt_counts','pdf_get_wire_counts'):
            actual=_mapping(http[field])
            if set(actual)!=_REPEAT_GETS[scenario] or any(v!=1 for v in actual.values()):diffs.append('repeat_exact_GET_mismatch:'+field)
            if set(actual)&set(previous):diffs.append('held_source_GET:'+field)
    return {'validation_status':'failed' if diffs else 'passed','scenario':scenario,'differences':diffs}


def coverage(path: Path) -> dict[str, JsonValue]:
    """逐实际修改生产/测试文件核 >=80%。参数：coverage JSON。返回：逐文件结果。异常：缺文件/低覆盖拒绝。"""
    files=_mapping(_mapping(_json(path))['files'])
    changed=subprocess.check_output(['git','diff','--name-only'],cwd=_REPO,text=True).splitlines()
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard','tests/fins'],cwd=_REPO,text=True).splitlines()
    targets=set(_PRODUCTION)|{n for n in changed+untracked if n.startswith('tests/') and n.endswith('.py')}
    normalized={str(Path(name).resolve().relative_to(_REPO)):entry for name,entry in files.items()}
    reports:list[JsonValue]=[];failed=False
    for name in sorted(targets):
        if name not in normalized:failed=True;reports.append({'path':name,'error':'missing entry'});continue
        summary=_mapping(_mapping(normalized[name])['summary']);percent=summary['percent_covered'];statements=summary['num_statements']
        if not isinstance(percent,(int,float)) or not isinstance(statements,int):raise ValueError('invalid coverage report')
        passed=statements==0 or percent>=80;failed=failed or not passed
        reports.append({'path':name,'num_statements':statements,'percent_covered':percent,'passed':passed})
    return {'validation_status':'failed' if failed else 'passed','files':reports,'frozen_changed_test_files':[n for n in sorted(targets) if n.startswith('tests/')]}


def main() -> int:
    """执行验收子命令，失败也保存实际原因。参数：argv。返回：0/2。异常：写输出失败透传。"""
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='operation',required=True)
    for operation in ('seed','verify'):
        p=sub.add_parser(operation);p.add_argument('--base',type=Path,required=True);p.add_argument('--evidence-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
        if operation=='verify':p.add_argument('--run-dir',type=Path,required=True)
    p=sub.add_parser('compare');p.add_argument('--scenario',choices=('clean-repeat','seeded-first','seeded-repeat'),required=True);p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('coverage');p.add_argument('--coverage',type=Path,required=True);p.add_argument('--output',type=Path,default=_REPO/'workspace/tmp/601225-validation/coverage-check.json')
    args=parser.parse_args()
    try:
        if args.operation=='seed':result=asyncio.run(seed(args.base,args.evidence_root))
        elif args.operation=='verify':result=verify(args.base,args.evidence_root,args.run_dir)
        elif args.operation=='compare':result=compare(args.scenario,_mapping(_json(args.before)),_mapping(_json(args.after)))
        else:result=coverage(args.coverage)
    except Exception as exc:result={'validation_status':'failed','error_type':type(exc).__name__,'error':str(exc)}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'validation_status':result['validation_status'],'output':str(args.output)},ensure_ascii=False))
    return 0 if result['validation_status']=='passed' else 2


if __name__=='__main__':sys.exit(main())
