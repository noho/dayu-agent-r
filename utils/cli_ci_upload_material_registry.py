"""upload_material 登记的只读 readiness owner；不运行产品或裁决自然语言。"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import signal
from typing import Literal, Mapping, Sequence, cast

from dayu.contracts.json_value import JsonValue
from utils.cli_ci_run_observation import (
    PublicEvidencePathClassification,
    classify_public_evidence_path,
)

REGISTRATION_TARGET = '22eca6c313005e3c5185340f2d6b535ab2583056'
MEASURED_PARENT = '8009ba4e100081fd1b56f64ddf5bc0c42a06e808'
OLD_TARGET = '79977b3a52f8566672e3b462f786f1004dfd3f89'
OLD_RUN = 'upload-material-cli-20261003-79977b3a-01'
FOCUSED_RUN = 'upload-material-diagnostics-focused04-22eca6c3-01'
OLD_REPORT_SHA = 'f35d33f5ff62b1e45d6f6ecf7ae1bcf7db4139f33c5b2af714e59ea0680ef53c'
OLD_SCAN_SHA = '0d3809860ac41e6140b8bd52e7c1e07e85f8d312082447fc9fb929a442c4ff58'
RECEIPT_PATH = 'docs/gateflow/evidence/upload-material-registry-20261003/retention-receipt.json'
RECEIPT_BYTES = 559
RECEIPT_SHA = '785f683849143b82cb6b07f916a36a3fad27f886f8e392711185040ecde61eb0'
REVIEW_PATH = 'docs/gateflow/evidence/upload-material-converter-diagnostics-20261003/code-review-proof.json'
REVIEW_BYTES = 9735
REVIEW_SHA = 'a736639f30bcb6c0624c6f7a81c2cd3b83c6bc5fc0892e32f632bd424c94f3a9'
AUTHORITY_LIST_PATH = 'workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/oracle-authority-index.json'
AUTHORITY_LIST_SHA = '8610ff1259a04f35a0dd21a474a52f63a3b8113752d35bebb63b2bfccc1b4521'
MATERIAL_ORACLE = 'cli.upload_material.document-publication'
MATERIAL_REF = MATERIAL_ORACLE + '@1'
NEXT_RUN = 'next-upload-material-conformance-run'
SOURCE_IDS = ('cli802', 'diagnostics-focused04')
DIMENSIONS = ('command_parameter_ids', 'precondition_state_ids', 'interactive_branch_option_ids', 'input_class_ids', 'combination_high_risk_ids', 'cross_command_assertion_ids')
PREDICATES = tuple('upload_material.' + name for name in (
    'public-parser','workspace','identity-admission','fiscal-date','company-identity',
    'asset-selection','conversion-publication','typed-content-failure','action-state',
    'amended-overwrite','primary-role','cross-consumption','direct-boundary',
    'operator-logging','sigint','crash-retry-observation','concurrent-publication',
    'converter-diagnostic-channel','evidence-lineage',
))
_PREDICATE_AUTHORITIES: tuple[tuple[str,...],...] = (
    ('UM-O01-O06','UM-O07','UM-O08'),('UM-O01-O06',),
    ('UM-O01-O06','UM-O07','UM-O08','UM-O17','accepted-repair-design'),
    ('UM-O09','UM-O10','UM-O11','accepted-repair-design'),('UM-O12','accepted-repair-design'),
    ('UM-O01-O06','UM-O23','UM-O24','accepted-repair-design'),
    ('UM-O19','UM-O20','UM-O26','UM-O34','accepted-repair-design'),('UM-O21','UM-O22','UM-O34'),
    ('UM-O13','UM-O14','UM-O15','UM-O16','accepted-repair-design'),('UM-O18',),
    ('UM-O24','UM-O25'),('UM-O27','accepted-repair-design'),('UM-O28','project-hard-contract'),
    ('UM-O01-O06','UM-O29'),('UM-O30',),('UM-O31',),('UM-O32','UM-O33','accepted-repair-design'),
    ('UM-CI-N01','diagnostic-design'),('UM-O35','UM-O36','CLI-hard-contract'),
)
MEASURED_PATHS = (
    'dayu/runtime/process_diagnostics.py','dayu/runtime/log.py',
    'dayu/fins/pipelines/docling_process_converter.py',
    'dayu/runtime/interruptible_process.py','dayu/runtime/macos_sandbox.py',
)
PUBLIC_ROOTS = (
    'workspace/evidence/' + OLD_RUN + '/public',
    'output/evidence-backup/' + OLD_RUN + '/public',
    'workspace/evidence/' + FOCUSED_RUN + '/public',
    'output/evidence-backup/' + FOCUSED_RUN + '/public',
)
SUPPLEMENT_PATHS = (
    'workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/oracle-candidates.json',
    'workspace/tmp/upload-material-registry-20261003/goal-confirmation.md',
    'docs/reviews/upload-material-cli-postrepair-root-adjudication-20261003.md',
    'docs/gateflow/upload-material-unified-repair-plan-20261002.md',
    'docs/gateflow/upload-material-converter-diagnostics-plan-20261003.md',
    'AGENTS.md','docs/cli_ci.md',
)
FOCUSED_CASES = ('NATIVE-DEFAULT-04','NATIVE-QUIET-04','NATIVE-LOG-04','NATIVE-ERROR-04','NATIVE-SIGINT-04','XBRL-REAL-NATIVE-04')
FOCUSED_INPUT_CLASSES = {case: 'native-PDF' for case in FOCUSED_CASES[:-1]} | {FOCUSED_CASES[-1]: 'controlled-XBRL-instance'}
FOCUSED_STATE = 'independent-fresh'
FOCUSED_CANCEL_EXIT = 130
AUTHORITY_INDEX_PATH = 'docs/gateflow/evidence/upload-material-registry-20261003/authority-index.json'
USER_ADJUDICATION_ID = 'upload_material.user-decisions.O01-O36+N01'
PATH_KINDS = frozenset(('help','positive','negative','cancel','crash','owner','wiring'))
NO_CREDIT = frozenset(('BATCH-GENERATE','BATCH-SCRIPT-CONSUME','BATCH-PROCESS-MATERIAL','BATCH-PROCESS-FILING','BATCH2-PROCESS-MATERIAL','BATCH2-PROCESS-FILING'))
SHA_PATTERN = re.compile(r'[0-9a-f]{64}')


class RegistryValidationError(ValueError):
    """带文件或 row 定位的登记合同错误。"""


@dataclass(frozen=True, slots=True)
class RegistryValidationReport:
    """唯一 producer 的验证投影；参数为不可变计数、错误、gap和proof值。"""
    counts: tuple[tuple[str, int], ...]
    errors: tuple[str, ...]
    gaps: tuple[str, ...]
    proof: JsonValue

    def to_json(self) -> JsonValue:
        """生成机器报告。参数：无；返回：JSON报告；异常：无主动异常。"""
        return {'validation_result':'pass' if not self.errors and not self.gaps else 'fail',
                'registry_status':'ready' if not self.errors and not self.gaps else 'calibration',
                'counts':dict(self.counts),'errors':list(self.errors),'gaps':list(self.gaps),'proof':self.proof}


def _mapping(value: JsonValue, location: str) -> dict[str, JsonValue]:
    """严格取对象。参数：value、location；返回：映射；异常：合同错误。"""
    if not isinstance(value, dict):
        raise RegistryValidationError(location + ': required JSON object')
    return value


def _array(value: JsonValue, location: str) -> list[JsonValue]:
    """严格取数组。参数：value、location；返回：数组；异常：合同错误。"""
    if not isinstance(value, list):
        raise RegistryValidationError(location + ': required JSON array')
    return value


def _field(value: Mapping[str, JsonValue], key: str, location: str) -> JsonValue:
    """取必填字段。参数：value、key、location；返回：字段；异常：缺字段。"""
    if key not in value:
        raise RegistryValidationError(location + '.' + key + ': missing')
    return value[key]


def _text(value: JsonValue, location: str) -> str:
    """取非空文本。参数：value、location；返回：文本；异常：合同错误。"""
    if not isinstance(value, str) or not value.strip():
        raise RegistryValidationError(location + ': required nonempty string')
    return value


def _integer(value: JsonValue, location: str) -> int:
    """取整数并拒布尔。参数：value、location；返回：整数；异常：合同错误。"""
    if type(value) is not int:
        raise RegistryValidationError(location + ': required integer')
    return cast(int, value)


def _strings(value: JsonValue, location: str) -> tuple[str, ...]:
    """取字符串数组。参数：value、location；返回：tuple；异常：合同错误。"""
    return tuple(_text(v, location) for v in _array(value, location))


def _argv(value: JsonValue, location: str) -> tuple[str, ...]:
    """保留argv显式空值。参数：value、location；返回：字符串tuple；异常：非字符串元素。"""
    values = _array(value, location)
    if any(not isinstance(v, str) for v in values):
        raise RegistryValidationError(location + ': argv elements must be strings')
    return tuple(cast(str, v) for v in values)


def _sha(value: JsonValue, location: str) -> str:
    """取SHA256。参数：value、location；返回：digest；异常：合同错误。"""
    text = _text(value, location)
    if SHA_PATTERN.fullmatch(text) is None:
        raise RegistryValidationError(location + ': required SHA256')
    return text


def _equal(actual: JsonValue, expected: JsonValue, location: str) -> None:
    """断言精确JSON值。参数：actual、expected、location；返回：无；异常：值不符。"""
    if actual != expected or type(actual) is not type(expected):
        raise RegistryValidationError(location + ': value mismatch')


def _required_fields(value: Mapping[str, JsonValue], keys: tuple[str, ...], location: str) -> None:
    """定位当前新记录的必填字段。参数：value、keys、location；返回：无；异常：缺字段。"""
    for key in keys:
        _field(value,key,location)


def _strict_path(root: Path, relative: str, location: str) -> Path:
    """严格相对路径。参数：root、relative、location；返回：regular路径；异常：边界错误。"""
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.as_posix() != relative:
        raise RegistryValidationError(location + ': lexical relative path required')
    candidate = root / path
    for component in (root, *root.parents, candidate, *candidate.parents):
        if component.is_symlink():
            raise RegistryValidationError(location + ': symlink forbidden: ' + str(component))
    if not root.is_dir() or not candidate.is_file():
        raise RegistryValidationError(location + ': regular file missing: ' + relative)
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (ValueError, OSError) as error:
        raise RegistryValidationError(location + ': resolved root containment') from error
    return candidate


def _read_descriptor(value: JsonValue, root: Path, location: str) -> bytes:
    """核精确身份后读列明文件。参数：value、root、location；返回：字节；异常：身份错误。"""
    item = _mapping(value, location)
    relative = _text(_field(item,'relative_path',location), location + '.relative_path')
    path = _strict_path(root, relative, location)
    raw = path.read_bytes()
    size = _integer(_field(item,'bytes',location), location + '.bytes')
    digest = _sha(_field(item,'sha256',location), location + '.sha256')
    if size < 0 or len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise RegistryValidationError(location + ': bytes/SHA mismatch: ' + relative)
    return raw


def _public_descriptor(value: JsonValue, roots: tuple[Path, Path, Path, Path], location: str) -> bytes:
    """按两个固定source读双副本。参数：value、roots、location；返回：原字节；异常：引用错误。"""
    item = _mapping(value, location)
    if set(item)!={'source_id','relative_path','bytes','sha256'}:
        raise RegistryValidationError(location + ': exact public descriptor keys required')
    source = _text(_field(item,'source_id',location), location + '.source_id')
    if source not in SOURCE_IDS:
        raise RegistryValidationError(location + ': unknown source_id ' + source)
    relative = _text(_field(item,'relative_path',location),location)
    if 'private' in Path(relative).parts or classify_public_evidence_path(relative) is not PublicEvidencePathClassification.PUBLISHABLE:
        raise RegistryValidationError(location + ': private/raw database public ref forbidden')
    index = SOURCE_IDS.index(source) * 2
    raw = _read_descriptor(value,roots[index],location)
    backup = _read_descriptor(value,roots[index+1],location + '.backup')
    if raw != backup:
        raise RegistryValidationError(location + ': dual copy mismatch')
    return raw


def load_registry(path: Path) -> JsonValue:
    """严格读JSON文件。参数：path；返回：JsonValue；异常：IO、JSON或regular边界错误。"""
    checked = _strict_path(path.absolute().parent,path.name,str(path))
    return cast(JsonValue,json.loads(checked.read_bytes()))


def canonical_digest(value: JsonValue) -> str:
    """计算全JSON canonical摘要。参数：value；返回：SHA；异常：不可序列化。"""
    raw = json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _basis(registry: JsonValue) -> str:
    """v6只排除顶层投影。参数：registry；返回：basis摘要；异常：对象错误。"""
    value = _mapping(registry,'registry')
    return canonical_digest({k:v for k,v in value.items() if k not in ('registry_status','readiness_proof')})


def _records(registry: JsonValue, kind: str) -> list[dict[str, JsonValue]]:
    """取记录列表。参数：registry、kind；返回：记录；异常：类型错误。"""
    value = _mapping(registry,kind)
    _equal(_field(value,'schema_version',kind),1,kind+'.schema_version')
    return [_mapping(v,kind) for v in _array(_field(value,kind,kind),kind)]


def _identity(record: Mapping[str, JsonValue], kind: str) -> str:
    """取得版本身份。参数：record、kind；返回：id@version；异常：类型错误。"""
    return _text(_field(record,kind+'_id',kind),kind) + '@' + str(_integer(_field(record,'version',kind),kind))


def compare_historical_records(before: JsonValue, current: JsonValue, record_kind: Literal['oracle','scenario']) -> tuple[str, ...]:
    """比较旧记录全值。参数：before、current、record_kind；返回：定位差异；异常：坏shape。"""
    kind = record_kind + 's'
    records = _records(current,kind)
    identities = [_identity(v,record_kind) for v in records]
    if len(set(identities)) != len(identities):
        return (kind + ': duplicate record identity',)
    lookup = dict(zip(identities,records))
    errors = []
    for old in _records(before,kind):
        identity = _identity(old,record_kind)
        if identity not in lookup or canonical_digest(old) != canonical_digest(lookup[identity]):
            errors.append(kind + ': historical canonical value changed: ' + identity)
    if record_kind == 'scenario':
        previous = _mapping(before,kind); present = _mapping(current,kind)
        _equal(_field(present,'readiness_proof_history_20260802',kind),_field(previous,'readiness_proof_history_20260802',kind),kind+'.readiness_proof_history_20260802')
    return tuple(errors)


def _source_guard(focused: dict[str, JsonValue], roots: tuple[Path, Path, Path, Path], source_root: Path) -> None:
    """核focused来源与五live模块。参数：focused、roots、source_root；返回：无；异常：定位合同错误。"""
    location = 'focused-source'
    keys = {'schema_version','source_id','registration_target','measured_parent','measured_source','reviewed_source','source_records','original_source_descriptors','report','scan','measurements','retention_receipt'}
    if set(focused) != keys:
        raise RegistryValidationError(location + ': exact schema keys required')
    for key,expected in (('schema_version',1),('source_id',SOURCE_IDS[1]),('registration_target',REGISTRATION_TARGET),('measured_parent',MEASURED_PARENT)):
        _equal(_field(focused,key,location),expected,location+'.'+key)
    measured = [_mapping(v,location+'.measured_source') for v in _array(focused['measured_source'],location)]
    if tuple(_text(v['relative_path'],location) for v in measured) != MEASURED_PATHS:
        raise RegistryValidationError(location + '.measured_source: exactly five measured product modules required')
    for value in measured:
        _read_descriptor(value,source_root,location+'.measured_source')
    review_raw = _read_descriptor({'relative_path':REVIEW_PATH,'bytes':REVIEW_BYTES,'sha256':REVIEW_SHA},source_root,location+'.reviewed_source.anchor')
    review = _mapping(cast(JsonValue,json.loads(review_raw)),location)
    _equal(focused['reviewed_source'],_field(review,'source11',location),location+'.reviewed_source')
    receipt = _mapping(focused['retention_receipt'],location+'.retention_receipt')
    _equal(receipt,{'relative_path':RECEIPT_PATH,'bytes':RECEIPT_BYTES,'sha256':RECEIPT_SHA},location+'.retention_receipt')
    raw = _read_descriptor(receipt,source_root,location+'.retention_receipt')
    value = _mapping(cast(JsonValue,json.loads(raw)),location+'.retention_receipt')
    if set(value) != {'bytes','sha256','primary','backup','equal','mode','contains'}:
        raise RegistryValidationError(location+'.retention_receipt: seven-key receipt required')
    _integer(value['bytes'],location);_sha(value['sha256'],location)
    for key in ('primary','backup','mode','contains'):
        _text(value[key],location)
    _equal(value['equal'],True,location+'.retention_receipt.equal')
    # 固定原件身份，不沿receipt内部private路径读档。
    originals = _array(focused['original_source_descriptors'],location)
    identities = { _text(_mapping(v,location)['label'],location): _mapping(v,location) for v in originals }
    expected_shas = {'real-matrix-result.json':'3293641330337c0647e731b7666ace52478fc5ead2b12373ce3f8c1d7fc2f6b3','result.json':'a120a1ca46b0f0a5681cdb2fbf89e69a3ca60c203972d6c03e38cb96f40dedcd','source-final.json':'84d19555ea7212c00abffaae718f120867cbeb2611e6646085f705a7d2213784'}
    if set(identities) != set(expected_shas) or len(identities)!=len(originals):
        raise RegistryValidationError(location+'.original_source_descriptors: missing/duplicate original')
    for name,digest in expected_shas.items():
        _equal(identities[name]['sha256'],digest,location+'.original_source_descriptors.'+name)
        _integer(identities[name]['bytes'],location)
    records = _array(focused['source_records'],location)
    if len(records)!=1:
        raise RegistryValidationError(location+'.source_records: single observation projection required')
    source = _mapping(cast(JsonValue,json.loads(_public_descriptor(records[0],roots,location+'.source_records'))),location)
    _equal(source['measured_parent'],MEASURED_PARENT,location+'.source_records.measured_parent')
    _equal(source['reviewed_source'],focused['reviewed_source'],location+'.source_records.reviewed_source')
    _equal(canonical_digest(source['source_final_historical']),'fec7254c808b787e7cb92891f1f9fdd6db6420204493bd6858c5da9248bfa78a',location+'.source_records.historical_fullvalue')
    historical = [_mapping(v,location) for v in _array(source['source_final_historical'],location)]
    # 历史测试曾变化，此差异须保持；不会live读取历史tests/README。
    review_by_path = {_text(_mapping(v,location)['relative_path'],location):_mapping(v,location) for v in _array(focused['reviewed_source'],location)}
    test_path = 'tests/runtime/test_process_diagnostics.py'
    old_test = [v for v in historical if v['relative_path']==test_path]
    if len(old_test)!=1 or old_test[0]['sha256']==review_by_path[test_path]['sha256']:
        raise RegistryValidationError(location+'.source_records: historical source-final test difference erased')
    dirty = [_mapping(v,location) for v in _array(source['dirty_source'],location)]
    for value in measured:
        match = [v for v in dirty if v['path']==str(source_root/_text(value['relative_path'],location))]
        if len(match)!=1 or match[0]['sha256']!=value['sha256']:
            raise RegistryValidationError(location+'.source_records.dirty_source: source conflict')
    measurements = [_mapping(v,location) for v in _array(focused['measurements'],location)]
    for index,value in enumerate(measurements):
        _required_fields(value,('measurement_id','source_scenario_id','required_evidence','actual_wait','actual_exit'),location+'.measurements.'+str(index))
    if tuple(v['measurement_id'] for v in measurements)!=FOCUSED_CASES:
        raise RegistryValidationError(location+'.measurements: six unique actual measurements required')
    for value in measurements:
        case = _text(value['measurement_id'],location)
        _equal(value['source_scenario_id'],'diagnostics-focused04.'+case,location+'.'+case)
        _equal(value['actual_wait'],True,location+'.'+case+'.actual_wait')
        _integer(value['actual_exit'],location+'.'+case)
        refs = _array(value['required_evidence'],location+'.'+case)
        names = {_text(_mapping(v,location)['relative_path'],location) for v in refs}
        names_required=('command.json','stdout.bin','stderr.bin','owner-observation.json','actual-exit.json') if case==FOCUSED_CASES[-1] else ('command.json','stdout.bin','stderr.bin','result.json','public-before.json','public-after.json')
        if case in FOCUSED_CASES[2:4]:
            names_required+=('operator.log',)
        required = {case+'/'+v for v in names_required}
        if not required <= names:
            raise RegistryValidationError(location+'.'+case+': mandatory public refs missing')
        for ref in refs:
            _equal(_mapping(ref,location)['source_id'],SOURCE_IDS[1],location+'.'+case+'.source_id')
            _public_descriptor(ref,roots,location+'.'+case)


def _scan_guard(source: str, scan_ref: JsonValue, roots: tuple[Path, Path, Path, Path]) -> None:
    """只读核唯一scan及tree清单。参数：source、scan_ref、roots；返回：无；异常：卫生或身份错误。"""
    value = _mapping(scan_ref,'scan.'+source)
    _equal(value['source_id'],source,'scan.'+source)
    _equal(value['relative_path'],'secret-scan.json','scan.'+source)
    if source==SOURCE_IDS[0]:
        _equal(value['sha256'],OLD_SCAN_SHA,'scan.cli802.original')
    scan = _mapping(cast(JsonValue,json.loads(_public_descriptor(scan_ref,roots,'scan.'+source))),'scan.'+source)
    _equal(scan['status'],'complete','scan.'+source)
    for key,list_key in (('secret_scan','hits'),('path_hygiene','violations')):
        component = _mapping(scan[key],'scan.'+source+'.'+key)
        _equal(component['status'],'complete','scan.'+source+'.'+key)
        _equal(component[list_key],[],'scan.'+source+'.'+key)
    _equal(scan['validation_errors'],[],'scan.'+source)
    descriptors = [_mapping(v,'scan') for v in _array(scan['files'],'scan')]
    paths = [_text(v['path'],'scan') for v in descriptors]
    if len(set(paths))!=len(paths) or 'secret-scan.json' in paths:
        raise RegistryValidationError('scan.'+source+': duplicate/self descriptor')
    _equal(scan['scanned_file_count'],len(paths),'scan.'+source+'.count')
    _equal(scan['scanned_byte_count'],sum(_integer(v['size_bytes'],'scan') for v in descriptors),'scan.'+source+'.bytes')
    pair_index = SOURCE_IDS.index(source)*2
    for root in roots[pair_index:pair_index+2]:
        present = {p.relative_to(root).as_posix() for p in root.rglob('*') if not p.is_dir() or p.is_symlink()}
        if present != set(paths)|{'secret-scan.json'}:
            raise RegistryValidationError('scan.'+source+': source tree missing/extra file: '+str(root))
        # 旧整树已有独立fullbyte proof，当前不重hash97MB；仍逐descriptor核路径/size，required refs另核双SHA。
        for entry in descriptors:
            path = _strict_path(root,_text(entry['path'],'scan'),'scan.'+source)
            if path.stat().st_size != _integer(entry['size_bytes'],'scan'):
                raise RegistryValidationError('scan.'+source+': file size drift: '+str(path))
            if source==SOURCE_IDS[1]:
                _read_descriptor({'relative_path':entry['path'],'bytes':entry['size_bytes'],'sha256':entry['sha256']},root,'scan.'+source)


def _authority_guard(authority: dict[str, JsonValue], source_root: Path) -> dict[str, tuple[str, ...]]:
    """核批准来源及正文anchors。参数：authority、source_root；返回：predicate到authority；异常：引用错误。"""
    raw = _read_descriptor({'relative_path':AUTHORITY_LIST_PATH,'bytes':4915,'sha256':AUTHORITY_LIST_SHA},source_root,'authority.fixed-index')
    frozen = _mapping(cast(JsonValue,json.loads(raw)),'authority.fixed-index')
    files = _mapping(frozen['files'],'authority.fixed-index.files')
    allowed = set(files)|set(SUPPLEMENT_PATHS)
    sources = [_mapping(v,'authority.sources') for v in _array(authority['sources'],'authority.sources')]
    ids = [_text(v['authority_id'],'authority') for v in sources]
    if len(set(ids))!=len(ids):
        raise RegistryValidationError('authority: duplicate authority_id')
    historic_paths: set[str] = set()
    for value in sources:
        identity = _text(value['authority_id'],'authority')
        path = _text(value['relative_path'],'authority.'+identity)
        if path not in allowed:
            raise RegistryValidationError('authority.'+identity+': source not approved: '+path)
        if value['kind'] not in ('user-decision','current-design','hard-contract'):
            raise RegistryValidationError('authority.'+identity+': reviewer consensus is not authority')
        raw = _read_descriptor(value,source_root,'authority.'+identity)
        if path in files:
            _equal(value['kind'],'user-decision','authority.'+identity+'.kind')
            historic_paths.add(path);_equal(value['sha256'],files[path],'authority.'+identity+'.frozen')
        _text(value['approval_provenance'],'authority.'+identity+'.approval_provenance')
        if identity=='UM-CI-N01':
            candidate_document=_mapping(cast(JsonValue,json.loads(raw)),'authority.UM-CI-N01')
            candidates=[_mapping(v,'authority.UM-CI-N01') for v in _array(candidate_document['candidates'],'authority.UM-CI-N01')]
            matched=[v for v in candidates if v['candidate_id']=='UM-CI-N01']
            if len(matched)!=1:
                raise RegistryValidationError('authority.UM-CI-N01: unique user decision missing')
            _equal(matched[0]['status'],'accepted','authority.UM-CI-N01.status')
            decision=_mapping(_field(matched[0],'user_adjudication','authority.UM-CI-N01'),'authority.UM-CI-N01.user_adjudication')
            _text(_field(decision,'accepted_predicate','authority.UM-CI-N01'),'authority.UM-CI-N01.accepted_predicate')
            _equal(decision['received_at'],'2026-10-03T09:15:58.686979+00:00','authority.UM-CI-N01.received_at')
            anchors_for_decision=_array(value['anchors'],'authority.UM-CI-N01.anchors')
            if len(anchors_for_decision)!=1 or _mapping(anchors_for_decision[0],'authority.UM-CI-N01')['heading']!='UM-CI-N01.user_adjudication':
                raise RegistryValidationError('authority.UM-CI-N01: exact approved user_adjudication anchor required')
        anchors = _array(value['anchors'],'authority.'+identity+'.anchors')
        if not anchors:
            raise RegistryValidationError('authority.'+identity+': no approved body anchor')
        for anchor_value in anchors:
            anchor = _mapping(anchor_value,'authority.'+identity)
            start = _integer(anchor['start_byte'],'authority');end = _integer(anchor['end_byte'],'authority')
            if not 0<=start<end<=len(raw):
                raise RegistryValidationError('authority.'+identity+': body range invalid')
            body = raw[start:end]
            _equal(hashlib.sha256(body).hexdigest(),_sha(anchor['body_sha256'],'authority'),'authority.'+identity+'.body')
            _text(anchor['heading'],'authority.'+identity+'.heading')
    if historic_paths!=set(files):
        raise RegistryValidationError('authority: 31 frozen historical source identities required')
    predicates = [_mapping(v,'authority.predicates') for v in _array(authority['predicates'],'authority')]
    lookup: dict[str, tuple[str,...]] = {}
    for value in predicates:
        predicate = _text(value['predicate_id'],'authority')
        if predicate in lookup:
            raise RegistryValidationError('authority: duplicate predicate '+predicate)
        refs = _strings(value['authority_refs'],'authority.'+predicate)
        if not refs or not set(refs)<=set(ids):
            raise RegistryValidationError('authority.'+predicate+': dangling/missing authority')
        if predicate not in PREDICATES or refs!=_PREDICATE_AUTHORITIES[PREDICATES.index(predicate)]:
            raise RegistryValidationError('authority.'+predicate+': frozen approved predicate authority relation mismatch')
        lookup[predicate]=refs
    if set(lookup)!=set(PREDICATES):
        raise RegistryValidationError('authority: nineteen stable predicates required')
    return lookup


def _oracle_guard(oracles: JsonValue, scenarios: JsonValue, formal_ids: set[str]) -> dict[str, JsonValue]:
    """核stable owner、双向refs与material形状。参数：两registry、formal_ids；返回：material；异常：合同错误。"""
    all_oracles = _records(oracles,'oracles'); all_scenarios = _records(scenarios,'scenarios')
    owners: dict[str,str] = {}
    refs = {_identity(v,'oracle') for v in all_oracles}
    for index,oracle in enumerate(all_oracles):
        oracle_location='oracles.record.'+str(index)
        for predicate_index,value in enumerate(_array(_field(oracle,'predicates',oracle_location),oracle_location+'.predicates')):
            predicate_location=oracle_location+'.predicates.'+str(predicate_index)
            predicate_entry=_mapping(value,predicate_location)
            predicate = _text(_field(predicate_entry,'predicate_id',predicate_location),predicate_location+'.predicate_id')
            if _field(oracle,'status',oracle_location)=='accepted':
                if predicate in owners:
                    raise RegistryValidationError('oracles: duplicate current accepted owner: '+predicate)
                owners[predicate]=_identity(oracle,'oracle')
    material = [v for index,v in enumerate(all_oracles) if _field(v,'oracle_id','oracles.record.'+str(index))==MATERIAL_ORACLE]
    if len(material)!=1:
        raise RegistryValidationError('oracles: one new material oracle required')
    item = material[0]
    oracle_location='oracles.material'
    _required_fields(item,('oracle_id','version','status','category','scope','predicates','allowed_variants','authority_basis','observed_behavior','user_adjudication','applicable_from','supersedes','superseded_by'),oracle_location)
    for key,expected in (('version',1),('status','accepted'),('category','behavioral'),('scope',{'command':'upload_material'}),('supersedes',None),('superseded_by',None)):
        _equal(item[key],expected,'oracles.material.'+key)
    if not _strings(item['allowed_variants'],oracle_location+'.allowed_variants'):
        raise RegistryValidationError(oracle_location+'.allowed_variants: nonempty required')
    basis=[_mapping(value,oracle_location+'.authority_basis') for value in _array(item['authority_basis'],oracle_location+'.authority_basis')]
    if len(basis)!=len(PREDICATES):
        raise RegistryValidationError(oracle_location+'.authority_basis: nineteen predicates required')
    for index,entry in enumerate(basis):
        location=oracle_location+'.authority_basis.'+str(index)
        _required_fields(entry,('predicate_id','authority_refs','index'),location)
        _equal(entry['predicate_id'],PREDICATES[index],location+'.predicate_id')
        _equal(list(_strings(entry['authority_refs'],location+'.authority_refs')),list(_PREDICATE_AUTHORITIES[index]),location+'.authority_refs')
        _equal(entry['index'],AUTHORITY_INDEX_PATH,location+'.index')
    adjudication=_mapping(item['user_adjudication'],oracle_location+'.user_adjudication')
    _required_fields(adjudication,('identity','result','notes'),oracle_location+'.user_adjudication')
    _equal(adjudication['identity'],USER_ADJUDICATION_ID,oracle_location+'.user_adjudication.identity')
    _equal(adjudication['result'],'accepted',oracle_location+'.user_adjudication.result')
    if not _strings(adjudication['notes'],oracle_location+'.user_adjudication.notes'):
        raise RegistryValidationError(oracle_location+'.user_adjudication.notes: nonempty required')
    predicates = [_mapping(v,'oracles.material.predicates.'+str(index)) for index,v in enumerate(_array(item['predicates'],'oracles.material'))]
    if {_text(_field(v,'predicate_id','oracles.material.predicates.'+str(index)),'oracles.material.predicates.'+str(index)+'.predicate_id') for index,v in enumerate(predicates)}!=set(PREDICATES) or len(predicates)!=len(PREDICATES):
        raise RegistryValidationError('oracles.material: missing/duplicate stable predicate')
    for index,predicate in enumerate(predicates):
        predicate_location='oracles.material.predicates.'+str(index)
        for key in ('expected','forbidden'):
            if not _strings(_field(predicate,key,predicate_location),predicate_location+'.'+key):
                raise RegistryValidationError(predicate_location+'.'+key+': empty')
    applicable = _mapping(item['applicable_from'],'oracles.material.applicable_from')
    if set(applicable)!={'date','target'}:
        raise RegistryValidationError('oracles.material.applicable_from: exact date/target required')
    text = _text(applicable['date'],'oracles.material.applicable_from.date')
    try:
        if date.fromisoformat(text).isoformat()!=text:
            raise ValueError('not canonical ISO date')
    except ValueError as error:
        raise RegistryValidationError('oracles.material.applicable_from.date: invalid ISO calendar date') from error
    _equal(applicable['target'],NEXT_RUN,'oracles.material.applicable_from.target')
    observed = _mapping(item['observed_behavior'],'oracles.material.observed_behavior')
    if set(observed)!={'run_ids','report_ids','report_digest_sha256','adjudication_artifacts','report_frozen','scenario_refs'}:
        raise RegistryValidationError('oracles.material.observed_behavior: exact six keys required')
    _equal(observed['run_ids'],[OLD_RUN,FOCUSED_RUN],'oracles.material.observed_behavior.run_ids')
    for key in ('report_ids','report_digest_sha256'):
        if len(_strings(observed[key],'oracles.material.'+key))!=2:
            raise RegistryValidationError('oracles.material.'+key+': two paired values required')
    _equal(observed['report_frozen'],True,'oracles.material.report_frozen')
    if set(_strings(observed['scenario_refs'],'oracles.material'))!=formal_ids:
        raise RegistryValidationError('oracles.material: oracle-to-scenario refs mismatch')
    for index,scenario in enumerate(all_scenarios):
        identity = _text(_field(scenario,'scenario_id','scenarios.record.'+str(index)),'scenarios.record.'+str(index)+'.scenario_id')
        if identity in formal_ids:
            _required_fields(scenario,('scenario_id','source_scenario_id','version','status','command','path_kind','coverage_claims','invocation','precondition','accepted_oracle_refs','oracle_predicate_refs','correctness_surfaces','authorization_requirements','resource_budget','required_evidence','observed_evidence','user_adjudication_identity','applicable_from','supersedes','superseded_by'),'scenarios.'+identity)
        for ref in _strings(_field(scenario,'accepted_oracle_refs','scenarios.'+identity),identity):
            if ref not in refs:
                raise RegistryValidationError(identity+': dangling frozen accepted_oracle_ref '+ref)
        for predicate in _strings(_field(scenario,'oracle_predicate_refs','scenarios.'+identity),identity):
            if predicate not in owners:
                raise RegistryValidationError(identity+': dangling stable predicate '+predicate)
        if identity in formal_ids:
            location='scenarios.'+identity
            _equal(scenario['source_scenario_id'],identity.removeprefix('upload_material.'),location+'.source_scenario_id')
            path_kind=_text(scenario['path_kind'],location+'.path_kind')
            if path_kind not in PATH_KINDS:
                raise RegistryValidationError(location+'.path_kind: unknown enum '+path_kind)
            _equal(scenario['user_adjudication_identity'],USER_ADJUDICATION_ID,location+'.user_adjudication_identity')
            _equal(scenario['supersedes'],None,location+'.supersedes')
            _equal(scenario['superseded_by'],None,location+'.superseded_by')
            if not _strings(scenario['authorization_requirements'],location+'.authorization_requirements'):
                raise RegistryValidationError(location+'.authorization_requirements: nonempty required')
            budget=_mapping(scenario['resource_budget'],location+'.resource_budget')
            _text(_field(budget,'scope',location+'.resource_budget'),location+'.resource_budget.scope')
            precondition=_mapping(scenario['precondition'],location+'.precondition')
            _text(_field(precondition,'state_id',location+'.precondition'),location+'.precondition.state_id')
            if not _strings(_field(precondition,'setup_steps',location+'.precondition'),location+'.precondition.setup_steps'):
                raise RegistryValidationError(location+'.precondition.setup_steps: nonempty required')
            observation=_mapping(scenario['observed_evidence'],location+'.observed_evidence')
            _required_fields(observation,('bundle_id','report_id','report_sha256','relative_ref','execution_outcome','exit_code','evidence_status','gap_kind'),location+'.observed_evidence')
            for key in ('bundle_id','report_id','relative_ref','execution_outcome','evidence_status','gap_kind'):
                _text(observation[key],location+'.observed_evidence.'+key)
            _sha(observation['report_sha256'],location+'.observed_evidence.report_sha256')
            _integer(observation['exit_code'],location+'.observed_evidence.exit_code')
            _equal(scenario['status'],'accepted',identity+'.status')
            _equal(scenario['version'],1,identity+'.version')
            _equal(scenario['applicable_from'],NEXT_RUN,identity+'.applicable_from')
            if MATERIAL_REF not in _strings(scenario['accepted_oracle_refs'],identity):
                raise RegistryValidationError(identity+': missing material frozen ref')
    return item


def _parameter_claims(argv: tuple[str,...], physical_command: str | None, parser: dict[str,JsonValue]) -> list[JsonValue]:
    """从冻结action取exact参数ID。参数：argv、physical_command、parser；返回：canonical IDs；异常：inventory类型错误。"""
    actions=list(_array(parser['root'],'parser.root'))
    if physical_command=='upload_material':
        actions.extend(_array(parser['upload_material'],'parser.upload_material'))
    by_option: dict[str,str]={}
    for value in actions:
        action=_mapping(value,'parser.action');options=_strings(action['options'],'parser.action.options')
        if not options:
            continue
        long_options=[v for v in options if v.startswith('--')]
        canonical=long_options[0] if long_options else options[0]
        for option in options:
            by_option[option]='parameter:'+canonical
    # 未声明的参数、删除项或缩写只保真实输入，不取得永久static parameter信用。
    return [cast(JsonValue,v) for v in sorted({by_option[token.split('=',1)[0]] for token in argv if token.split('=',1)[0] in by_option})]


def _cli_leaf(argv: tuple[str,...], parser: dict[str,JsonValue], location: str) -> str:
    """按冻结root参数arity定位leaf。参数：argv、parser、location；返回：完整command；异常：无法唯一定位。"""
    root_actions=[_mapping(v,location) for v in _array(parser['root'],location)]
    options: dict[str,str]={}
    for action in root_actions:
        for option in _strings(action['options'],location):
            options[option]=_text(action['nargs'],location)
    cursor=1
    while cursor<len(argv) and argv[cursor].startswith('-'):
        token=argv[cursor];option=token.split('=',1)[0]
        if option not in options or options[option] not in ('0','None'):
            raise RegistryValidationError(location+': root parameter cannot identify actual leaf: '+option)
        cursor+=1 if options[option]=='0' or '=' in token else 2
    if cursor>=len(argv):
        raise RegistryValidationError(location+': missing actual leaf')
    leaf=argv[cursor]
    if leaf not in _strings(parser['commands'],location):
        raise RegistryValidationError(location+': unknown actual leaf: '+leaf)
    if leaf in ('tool_trace','session'):
        if cursor+1>=len(argv):
            raise RegistryValidationError(location+': missing command subpath')
        leaf+=' '+argv[cursor+1]
    return leaf


def _focused_terminal(raw: bytes, case: str, location: str) -> tuple[bool, int, str]:
    """从冻结结果取得focused终态。参数：raw、case、location；返回：wait、exit、既有outcome；异常：原件shape或终态不支持。"""
    result=_mapping(cast(JsonValue,json.loads(raw)),location+'.result')
    exit_key='actual_exit' if case==FOCUSED_CASES[-1] else 'exit'
    actual_wait=_field(result,'actual_wait',location+'.result')
    _equal(actual_wait,True,location+'.result.actual_wait')
    actual_exit=_integer(_field(result,exit_key,location+'.result'),location+'.result.'+exit_key)
    if actual_exit==0:
        outcome='success'
    elif case==FOCUSED_CASES[-2] and actual_exit==FOCUSED_CANCEL_EXIT:
        outcome='cancel'
    else:
        raise RegistryValidationError(location+'.result: unsupported focused terminal')
    return True,actual_exit,outcome


def _focused_claims(case: str, argv: tuple[str,...], parser: dict[str,JsonValue], location: str) -> dict[str,JsonValue]:
    """按批准的六测量与原命令派生义务。参数：case、argv、parser、location；返回：六维及原claim；异常：测量输入不符。"""
    input_class=FOCUSED_INPUT_CLASSES[case]
    suffix='.xml' if case==FOCUSED_CASES[-1] else '.pdf'
    file_positions=[index for index,token in enumerate(argv) if token=='--files']
    if len(file_positions)!=1 or file_positions[0]+1>=len(argv) or not argv[file_positions[0]+1].endswith(suffix):
        raise RegistryValidationError(location+': focused measured input class mismatch')
    stable='focused:'+case
    return {
        'command_parameter_ids':['command:upload_material',*_parameter_claims(argv,'upload_material',parser)],
        'precondition_state_ids':['state:'+FOCUSED_STATE],
        'interactive_branch_option_ids':[],
        'input_class_ids':['input:'+input_class],
        'combination_high_risk_ids':[stable],
        'cross_command_assertion_ids':[],
        'raw_stable_claims':[stable],
    }


def _crash_path_kind(process: Mapping[str,JsonValue], path_kind: JsonValue, location: str) -> None:
    """按实际外部强杀终态约束分类。参数：process、path_kind、location；返回：无；异常：分类与原件不符。"""
    killed=process.get('signal')==signal.SIGKILL and process.get('harness_deadline_kill') is False and process.get('actual_wait_returncode')==-signal.SIGKILL
    if killed:
        _equal(path_kind,'crash',location+'.path_kind')
    elif path_kind=='crash':
        raise RegistryValidationError(location+'.path_kind: crash requires SIGKILL facts')


def _assignment_guard(assignment: dict[str, JsonValue], scenarios: JsonValue, authorities: dict[str, tuple[str,...]], roots: tuple[Path, Path, Path, Path], focused: dict[str,JsonValue]) -> tuple[dict[str,int], set[str], JsonValue]:
    """逐row重算coverage与完整来源。参数：assignment、scenarios、authorities、roots、focused；返回：计数、formal IDs、campaign；异常：gap。"""
    rows = [_mapping(v,'assignment.rows.'+str(index)) for index,v in enumerate(_array(_field(assignment,'rows','assignment'),'assignment.rows'))]
    ids = [_text(_field(v,'source_scenario_id','assignment.rows.'+str(index)),'assignment.rows.'+str(index)+'.source_scenario_id') for index,v in enumerate(rows)]
    for index,row in enumerate(rows):
        row_location='assignment.rows.'+str(index)+'.'+ids[index]
        _required_fields(row,('source_id','source_scenario_id','physical_command','campaign_role','registration_class','classification_reason','formal','state','input_class','invocation_argv','command_ref','result_ref','execution_outcome','actual_exit','actual_wait','coverage_claims','required_evidence','surfaces'),row_location)
        if row['campaign_role']=='Service-owner':
            _required_fields(row,('actual_operation_observation',),row_location)
    if len(ids)!=len(set(ids)):
        raise RegistryValidationError('assignment: duplicate source_scenario_id')
    inventory = _mapping(assignment['inventory'],'assignment.inventory')
    matrices = [_mapping(v,'inventory.matrices') for v in _array(inventory['matrices'],'inventory')]
    actual_ids: set[str] = set(); matrix_counts: dict[str,int] = {}; frozen_rows: dict[str,dict[str,JsonValue]]={}
    for key in ('parser','interactive','pairwise'):
        _public_descriptor(inventory[key],roots,'inventory.'+key)
    parser_inventory=_mapping(cast(JsonValue,json.loads(_public_descriptor(inventory['parser'],roots,'inventory.parser'))),'parser')
    pairwise=_mapping(cast(JsonValue,json.loads(_public_descriptor(inventory['pairwise'],roots,'inventory.pairwise'))),'pairwise')
    paircases=[_mapping(v,'pairwise') for v in _array(pairwise['cases'],'pairwise')]
    pairs={_text(v['scenario'],'pairwise'):_strings(v['obligation_ids'],'pairwise') for v in paircases}
    axes=[_strings(v,'pairwise.axes') for v in _array(pairwise['axes'],'pairwise')]
    mandatory_pairs={f'PW-{i}-{a}--{j}-{b}' for i,values in enumerate(axes) for j,others in enumerate(axes) if i<j for a in values for b in others}
    measured_pairs=set().union(*[set(v) for v in pairs.values()])
    if measured_pairs!=mandatory_pairs:
        raise RegistryValidationError('inventory.pairwise: incomplete actual pair projections')
    for entry in matrices:
        matrix = _array(cast(JsonValue,json.loads(_public_descriptor(entry['matrix'],roots,'inventory.matrix'))),'inventory.matrix')
        index = _array(cast(JsonValue,json.loads(_public_descriptor(entry['execution_index'],roots,'inventory.execution_index'))),'inventory.index')
        matrix_ids = {_text(_mapping(v,'matrix')['id'],'matrix') for v in matrix}
        index_ids = {_text(_mapping(v,'index')['scenario_id'],'index') for v in index}
        if matrix_ids!=index_ids or len(matrix_ids)!=len(matrix) or actual_ids & matrix_ids:
            raise RegistryValidationError('inventory: matrix/index identity mismatch or duplicate')
        for value in matrix:
            frozen_value=_mapping(value,'matrix');frozen_rows[_text(frozen_value['id'],'matrix')]=frozen_value
        actual_ids |= matrix_ids
        matrix_counts[_text(entry['name'],'inventory')]=len(matrix)
    old_rows = [v for v in rows if v['source_id']==SOURCE_IDS[0]]
    if set(_text(v['source_scenario_id'],'assignment') for v in old_rows)!=actual_ids:
        raise RegistryValidationError('assignment: incomplete cli802 inventory')
    focused_rows = [v for v in rows if v['source_id']==SOURCE_IDS[1]]
    if set(v['source_scenario_id'] for v in focused_rows)!=set('diagnostics-focused04.'+v for v in FOCUSED_CASES):
        raise RegistryValidationError('assignment: focused identity missing')
    measurements={_text(_field(_mapping(v,'focused.measurements'),'source_scenario_id','focused.measurements'),'focused.measurements'):_mapping(v,'focused.measurements') for v in _array(_field(focused,'measurements','focused'),'focused.measurements')}
    if set(measurements)!=set('diagnostics-focused04.'+v for v in FOCUSED_CASES):
        raise RegistryValidationError('focused.measurements: incomplete source identities')
    source_descriptors={_text(_field(_mapping(v,'assignment.evidence_sources'),'source_id','assignment.evidence_sources'),'assignment.evidence_sources'):_mapping(v,'assignment.evidence_sources') for v in _array(_field(assignment,'evidence_sources','assignment'),'assignment.evidence_sources')}
    formal_ids: set[str] = set(); mandatory_by_dimension: dict[str,set[str]]={v:set() for v in DIMENSIONS}
    covered: dict[str,set[str]]={v:set() for v in DIMENSIONS}; scenario_map = {_text(_field(v,'scenario_id','scenarios.record.'+str(index)),'scenarios.record.'+str(index)+'.scenario_id'):v for index,v in enumerate(_records(scenarios,'scenarios'))}
    roles: Counter[str] = Counter(); service_counts: Counter[str]=Counter(); predicates_covered: set[str]=set()
    for row_index,row in enumerate(rows):
        identity = _text(row['source_scenario_id'],'assignment');location='assignment.'+identity
        source = _text(row['source_id'],location)
        if source not in SOURCE_IDS:
            raise RegistryValidationError(location+': unknown source ID')
        formal = row['formal'];
        expected_formal = identity not in NO_CREDIT and row['physical_command'] is not None
        _equal(formal,expected_formal,location+'.formal-credit-scope')
        if type(formal) is not bool:
            raise RegistryValidationError(location+': formal must be bool')
        reason = _text(row['classification_reason'],location)
        roles[_text(row['registration_class'],location)]+=1
        if identity in NO_CREDIT and formal:
            raise RegistryValidationError(location+': diagnostic batch-v1/v2 cannot get formal credit')
        required = _array(row['required_evidence'],location)
        raw_by_name: dict[str,bytes] = {}
        for ref in required:
            value = _mapping(ref,location)
            _equal(value['source_id'],source,location+'.required_evidence.source_id')
            relative = _text(value['relative_path'],location)
            if relative in raw_by_name:
                raise RegistryValidationError(location+': duplicate required descriptor')
            raw_by_name[relative]=_public_descriptor(ref,roots,location+'.'+relative)
        command_ref = _text(row['command_ref'],location)
        if command_ref not in raw_by_name:
            raise RegistryValidationError(location+': command ref missing')
        command = _mapping(cast(JsonValue,json.loads(raw_by_name[command_ref])),location+'.command')
        _equal(row['invocation_argv'],command['argv'],location+'.argv')
        claims_value=_mapping(row['coverage_claims'],location+'.coverage_claims')
        if source==SOURCE_IDS[0]:
            frozen=frozen_rows[identity]
            for key in ('state','input_class'):
                _equal(row[key],frozen[key],location+'.'+key)
            _equal(command['argv'],frozen['argv'],location+'.matrix.argv')
            _equal(claims_value['raw_stable_claims'],frozen['claims'],location+'.raw_stable_claims')
            physical=row['physical_command']
            actual_argv=_argv(command['argv'],location)
            if row['campaign_role']=='Service-owner':
                _equal(physical,'service.upload_material',location+'.physical_command')
                if len(actual_argv)<4 or Path(actual_argv[1]).name!='failure_owner.py' or actual_argv[2]!='child':
                    raise RegistryValidationError(location+': invalid actual Service operation argv')
                terminal_name=identity+'/public-terminal.json';stdout_name=identity+'/stdout.bin'
                if terminal_name not in raw_by_name or stdout_name not in raw_by_name:
                    raise RegistryValidationError(location+': mandatory Service terminal/raw missing')
                terminal=_mapping(cast(JsonValue,json.loads(raw_by_name[terminal_name])),location+'.public-terminal')
                stdout_rows=[_mapping(cast(JsonValue,json.loads(line)),location+'.stdout') for line in raw_by_name[stdout_name].split(b'\n') if line]
                actual_terminals=[v['terminal'] for v in stdout_rows if 'terminal' in v]
                if len(actual_terminals)!=1:
                    raise RegistryValidationError(location+': unique actual Service terminal missing')
                _equal(actual_terminals[0],terminal,location+'.Service_terminal')
                operation_location='assignment.rows.'+str(row_index)+'.'+identity+'.actual_operation_observation'
                operation=_mapping(row['actual_operation_observation'],operation_location)
                _equal(_field(operation,'terminal_status',operation_location),terminal['status'],location+'.terminal_status')
                _equal(_field(operation,'terminal_exit',operation_location),terminal['exit_code'],location+'.terminal_exit')
                service_counts[_text(terminal['status'],location)]+=1
            elif row['campaign_role']=='batch-shell':
                _equal(physical,'sh',location+'.physical_command')
                _equal(Path(actual_argv[0]).name,'sh',location+'.physical_executable')
            elif row['campaign_role']=='root-parser':
                _equal(physical,None,location+'.physical_command')
            else:
                leaf=_cli_leaf(actual_argv,parser_inventory,location)
                _equal(physical,leaf,location+'.physical_command')
            command_ids: list[JsonValue]=([cast(JsonValue,'command:'+_text(physical,location))] if physical is not None else [])+_parameter_claims(actual_argv,_text(physical,location) if physical is not None else None,parser_inventory)
            combination_ids: list[JsonValue]=[cast(JsonValue,v) for v in (list(dict.fromkeys(_strings(frozen['claims'],location)))+list(pairs[identity] if identity in pairs else ()))]
            expected_claims: dict[str,JsonValue]={
                'command_parameter_ids':command_ids,
                'precondition_state_ids':['state:'+_text(frozen['state'],location)],
                'interactive_branch_option_ids':[],
                'input_class_ids':['input:'+_text(frozen['input_class'],location)],
                'combination_high_risk_ids':combination_ids,
                'cross_command_assertion_ids':['wiring:'+identity] if row['campaign_role'] in ('cross-wiring','batch-shell','Service-owner') else [],
                'raw_stable_claims':frozen['claims'],
            }
            _equal(claims_value,expected_claims,location+'.coverage_dimensions')
        else:
            case=identity.removeprefix('diagnostics-focused04.')
            measurement=measurements[identity]
            _equal(row['required_evidence'],measurement['required_evidence'],location+'.required_evidence')
            if identity!='diagnostics-focused04.XBRL-REAL-NATIVE-04':
                _equal(command['checkpoint_parent'],MEASURED_PARENT,location+'.measured_parent')
            _equal(row['physical_command'],'upload_material',location+'.physical_command')
            actual_argv=_argv(command['argv'],location)
            if len(actual_argv)<4 or actual_argv[1:4]!=('-m','dayu.cli','upload_material'):
                raise RegistryValidationError(location+': focused actual command path mismatch')
            expected_claims=_focused_claims(case,actual_argv,parser_inventory,location)
            _equal(claims_value,expected_claims,location+'.coverage_dimensions')
            _equal(row['state'],FOCUSED_STATE,location+'.state')
            _equal(row['input_class'],FOCUSED_INPUT_CLASSES[case],location+'.input_class')
            result_ref=case+('/actual-exit.json' if case==FOCUSED_CASES[-1] else '/result.json')
            _equal(row['result_ref'],result_ref,location+'.result_ref')
            if result_ref not in raw_by_name:
                raise RegistryValidationError(location+'.result_ref: required descriptor missing')
            actual_wait,actual_exit,outcome=_focused_terminal(raw_by_name[result_ref],case,location)
            _equal(measurement['actual_wait'],actual_wait,location+'.measurement.actual_wait')
            _equal(measurement['actual_exit'],actual_exit,location+'.measurement.actual_exit')
            _equal(row['actual_wait'],actual_wait,location+'.actual_wait')
            _equal(row['actual_exit'],actual_exit,location+'.actual_exit')
            _equal(row['execution_outcome'],outcome,location+'.execution_outcome')

        surfaces = [_mapping(v,location+'.surfaces') for v in _array(row['surfaces'],location)]
        if not surfaces:
            raise RegistryValidationError(location+': mandatory surface missing')
        for surface in surfaces:
            predicate = _text(surface['predicate_id'],location)
            refs = _strings(surface['authority_refs'],location)
            if predicate not in authorities or not refs or not set(refs)<=set(authorities[predicate]):
                raise RegistryValidationError(location+': mandatory surface has no unique applicable approved authority: '+predicate)
            _equal(surface['evidence_status'],'sufficient',location+'.'+predicate+'.evidence_status')
            if not _strings(surface['measurement_refs'],location) or not set(_strings(surface['measurement_refs'],location))<=set(raw_by_name):
                raise RegistryValidationError(location+': mandatory measurement missing: '+predicate)
            if formal:
                predicates_covered.add(predicate)
        claims = _mapping(row['coverage_claims'],location+'.coverage_claims')
        for dimension in DIMENSIONS:
            values = _strings(_field(claims,dimension,location),location+'.'+dimension)
            if dimension=='interactive_branch_option_ids' and values:
                raise RegistryValidationError(location+': direct CLI no interactive branch credit')
            if formal:
                mandatory_by_dimension[dimension].update(_strings(_field(expected_claims,dimension,location),location+'.expected.'+dimension))
                covered[dimension].update(values)
        if formal:
            scenario_id='upload_material.'+identity
            formal_ids.add(scenario_id)
            if scenario_id not in scenario_map:
                raise RegistryValidationError(location+': formal scenario missing')
            scenario=scenario_map[scenario_id]
            _required_fields(scenario,('source_scenario_id','command','path_kind','coverage_claims','invocation','precondition','oracle_predicate_refs','correctness_surfaces','required_evidence','observed_evidence'), 'scenarios.'+scenario_id)
            _equal(scenario['source_scenario_id'],identity,location+'.source_scenario_id')
            for key,row_key in (('command','physical_command'),('coverage_claims','coverage_claims')):
                _equal(scenario[key],row[row_key],location+'.'+key)
            invocation=_mapping(scenario['invocation'],location)
            _required_fields(invocation,('argv','cwd','input_description'),location+'.invocation')
            _equal(invocation['argv'],row['invocation_argv'],location+'.invocation')
            _equal(invocation['cwd'],_field(command,'cwd',location+'.command'),location+'.invocation.cwd')
            _equal(invocation['input_description'],[row['input_class']],location+'.invocation.input_description')
            if 'stdin' in command:
                _equal(_field(invocation,'stdin',location+'.invocation'),command['stdin'],location+'.invocation.stdin')
            elif 'stdin' in invocation:
                raise RegistryValidationError(location+'.invocation.stdin: absent from source command')
            precondition=_mapping(scenario['precondition'],location+'.precondition')
            _equal(_field(precondition,'state_id',location+'.precondition'),row['state'],location+'.precondition.state_id')
            _equal(scenario['oracle_predicate_refs'],[v['predicate_id'] for v in surfaces],location+'.predicate_refs')
            _equal(scenario['correctness_surfaces'],[v['predicate_id'] for v in surfaces],location+'.correctness_surfaces')
            _equal(scenario['required_evidence'],row['required_evidence'],location+'.required_evidence')
            observation=_mapping(scenario['observed_evidence'],location)
            source_record=source_descriptors[source]
            source_report=_mapping(_field(source_record,'report',location+'.source'),location+'.source.report')
            _equal(_field(observation,'bundle_id',location+'.observed_evidence'),source_record['run_id'],location+'.observed_evidence.bundle_id')
            _equal(_field(observation,'report_id',location+'.observed_evidence'),PUBLIC_ROOTS[SOURCE_IDS.index(source)*2]+'/observed-behavior.md',location+'.observed_evidence.report_id')
            _equal(_field(observation,'report_sha256',location+'.observed_evidence'),source_report['sha256'],location+'.observed_evidence.report_sha256')
            _equal(_field(observation,'relative_ref',location+'.observed_evidence'),identity.removeprefix('diagnostics-focused04.'),location+'.observed_evidence.relative_ref')
            _equal(_field(observation,'gap_kind',location+'.observed_evidence'),'none',location+'.observed_evidence.gap_kind')
            _equal(observation['execution_outcome'],row['execution_outcome'],location+'.execution_outcome')
            _equal(observation['exit_code'],row['actual_exit'],location+'.exit_code')
            _equal(observation['evidence_status'],'sufficient',location+'.evidence_status')
            if source==SOURCE_IDS[0]:
                result_ref=_text(row['result_ref'],location)
                if result_ref not in raw_by_name:
                    raise RegistryValidationError(location+'.result_ref: required descriptor missing')
                result=_mapping(cast(JsonValue,json.loads(raw_by_name[result_ref])),location+'.result')
                _equal(row['execution_outcome'],result['execution_outcome'],location+'.raw_execution_outcome')
                process=_mapping(result['process_outcome'],location)
                _equal(row['actual_exit'],process['actual_wait_returncode'],location+'.actual_exit')
                _crash_path_kind(process,scenario['path_kind'],location)
            else:
                _equal(row['actual_wait'],True,location+'.actual_wait')
        else:
            if 'upload_material.'+identity in scenario_map:
                raise RegistryValidationError(location+': no-credit row present in formal registry: '+reason)
    new_ids={_text(v['scenario_id'],'scenarios') for v in _records(scenarios,'scenarios') if _text(v['scenario_id'],'scenarios').startswith('upload_material.')}
    if new_ids!=formal_ids:
        raise RegistryValidationError('assignment: dangling scenario-to-assignment refs')
    if predicates_covered!=set(PREDICATES):
        raise RegistryValidationError('assignment: uncovered mandatory predicates '+str(sorted(set(PREDICATES)-predicates_covered)))
    dimension_proof: dict[str,JsonValue]={}
    for dimension in DIMENSIONS:
        # no-credit rows只能提供诊断，不生成mandatory正向义务；formal每个维度独立闭合。
        mandatory=mandatory_by_dimension[dimension]
        missing=mandatory-covered[dimension]
        extra=covered[dimension]-mandatory
        if missing or extra:
            raise RegistryValidationError('coverage_dimensions.'+dimension+': missing='+str(sorted(missing))+' unexpected='+str(sorted(extra)))
        dimension_value: dict[str,JsonValue]={'mandatory':len(mandatory),'covered':len(covered[dimension]),'gaps':len(missing),'obligation_ids':[cast(JsonValue,v) for v in sorted(mandatory)],'not_applicable':'direct CLI has no interactive branches' if dimension=='interactive_branch_option_ids' else None}
        dimension_proof[dimension]=dimension_value
    counts={'source_cli802':len(old_rows),'source_focused':len(focused_rows),'new_formal_scenarios':len(formal_ids),'new_oracles':1,'new_predicates':len(PREDICATES),'excluded':len(rows)-len(formal_ids)}
    campaign: JsonValue={'registration_target':REGISTRATION_TARGET,'counts':counts,'matrix_counts':matrix_counts,'classes':dict(roles),'actual_Service_terminal_classes':dict(service_counts),'coverage_dimensions':dimension_proof,'pairwise':{'mandatory':len(mandatory_pairs),'covered':len(measured_pairs),'gaps':0,'obligation_ids':[cast(JsonValue,v) for v in sorted(mandatory_pairs)]},'inventory':inventory,'product_finding_refs':['UM-CI-N01-F01 historical violation; independently closed; original observation retained'],'checks':{'historical_records':'unchanged','dangling':0,'duplicate':0,'uncovered':0,'pending':0,'gaps':0}}
    return counts,formal_ids,campaign


def validate_upload_material_registration(oracles: JsonValue, scenarios: JsonValue, assignment: JsonValue, authority_index: JsonValue, evidence_root: Path, backup_root: Path, focused_evidence_root: Path, focused_backup_root: Path, focused_source: JsonValue, source_root: Path, registration_target: str, before_oracles: JsonValue, before_scenarios: JsonValue) -> RegistryValidationReport:
    """唯一readiness producer。参数：两registry、assignment、authority、四publicroot、focused_source、source_root、target及各自before；返回：计数/错误/gap/两proof；异常：底层IO或JSON损坏。"""
    counts: dict[str,int]={}
    try:
        _equal(registration_target,REGISTRATION_TARGET,'registration_target')
        roots=(evidence_root,backup_root,focused_evidence_root,focused_backup_root)
        for root,relative in zip(roots,PUBLIC_ROOTS):
            if root.absolute()!=source_root/relative:
                raise RegistryValidationError('root binding: '+relative)
            if root.is_symlink() or not root.is_dir():
                raise RegistryValidationError('root binding: missing/symlink '+str(root))
        for kind,previous,current in (('oracle',before_oracles,oracles),('scenario',before_scenarios,scenarios)):
            errors=compare_historical_records(previous,current,cast(Literal['oracle','scenario'],kind))
            if errors:
                raise RegistryValidationError('; '.join(errors))
        focused=_mapping(focused_source,'focused-source');authority=_mapping(authority_index,'authority');assign=_mapping(assignment,'assignment')
        _source_guard(focused,roots,source_root)
        authorities=_authority_guard(authority,source_root)
        sources=[_mapping(v,'assignment.evidence_sources.'+str(index)) for index,v in enumerate(_array(_field(assign,'evidence_sources','assignment'),'assignment.evidence_sources'))]
        if tuple(_field(v,'source_id','assignment.evidence_sources.'+str(index)) for index,v in enumerate(sources))!=SOURCE_IDS:
            raise RegistryValidationError('assignment.evidence_sources: exactly two unique source IDs required')
        _equal(_field(sources[0],'run_id','assignment.cli802'),OLD_RUN,'assignment.cli802.run_id')
        _equal(_field(sources[1],'run_id','assignment.focused'),FOCUSED_RUN,'assignment.focused.run_id')
        _equal(_field(sources[0],'target','assignment.cli802'),OLD_TARGET,'assignment.cli802.target')
        _equal(_field(sources[1],'registration_target','assignment.focused'),REGISTRATION_TARGET,'assignment.focused.registration_target')
        _equal(_field(sources[1],'measured_parent','assignment.focused'),MEASURED_PARENT,'assignment.focused.measured_parent')
        _equal(_field(sources[1],'measured_source','assignment.focused'),focused['measured_source'],'assignment.focused.measured_source')
        for index,source in enumerate(sources):
            source_id=SOURCE_IDS[index]
            source_location='assignment.'+('cli802' if index==0 else 'focused')
            report=_mapping(_field(source,'report',source_location),'report.'+source_id)
            _equal(_field(report,'source_id','report.'+source_id),source_id,'report.'+source_id)
            _equal(_field(report,'relative_path','report.'+source_id),'observed-behavior.md','report.'+source_id)
            if index==0:
                _equal(_field(report,'sha256','report.cli802'),OLD_REPORT_SHA,'report.cli802.original')
                # 原报告20MB已有fullSHA双核，不重复读取全文；只核fixeddescriptor与stat。
                _public_descriptor(report,roots,'report.cli802')
            else:
                _equal(_field(source,'report',source_location),focused['report'],'focused-source.report')
                _equal(_field(source,'scan',source_location),focused['scan'],'focused-source.scan')
                _public_descriptor(report,roots,'report.'+source_id)
            _scan_guard(source_id,_field(source,'scan',source_location),roots)
        counts,formal_ids,campaign=_assignment_guard(assign,scenarios,authorities,roots,focused)
        material=_oracle_guard(oracles,scenarios,formal_ids)
        observed=_mapping(material['observed_behavior'],'material.observed_behavior')
        _equal(observed['report_ids'],[PUBLIC_ROOTS[0]+'/observed-behavior.md',PUBLIC_ROOTS[2]+'/observed-behavior.md'],'material.report_ids')
        _equal(observed['report_digest_sha256'],[_mapping(v['report'],'source')['sha256'] for v in sources],'material.report_digests')
        artifacts=_array(observed['adjudication_artifacts'],'material.adjudication_artifacts')
        if not artifacts:
            raise RegistryValidationError('material.adjudication_artifacts: missing')
        for item in artifacts:
            value=_mapping(item,'material.adjudication_artifacts');path=_text(value['path'],'material.adjudication_artifacts')
            if path not in { _text(_mapping(v,'authority')['relative_path'],'authority') for v in _array(authority['sources'],'authority') }:
                raise RegistryValidationError('material.adjudication_artifacts: non-approved source')
            raw=_strict_path(source_root,path,'material.adjudication_artifacts').read_bytes()
            _equal(hashlib.sha256(raw).hexdigest(),value['sha256'],'material.adjudication_artifacts.'+path)
        campaign_value=_mapping(campaign,'campaign');campaign_value['evidence_sources']=[cast(JsonValue,v) for v in sources]
        campaign_value['authority_digest']=canonical_digest(authority_index);campaign_value['assignment_digest']=canonical_digest(assignment);campaign_value['focused_source_digest']=canonical_digest(focused_source)
        common: dict[str,JsonValue]={'proof_version':6,'target_commit':REGISTRATION_TARGET,'registry_digest_basis':{'oracles':_basis(oracles),'scenarios':_basis(scenarios)},'campaigns':{'upload_material':campaign_value},'validation_result':'pass','registry_status':'ready','commands':['init','prompt','interactive','download','upload_filing','upload_material']}
        proofs: dict[str,JsonValue]={}
        for kind,before in (('oracles',before_oracles),('scenarios',before_scenarios)):
            previous=_mapping(before,'before.'+kind)
            proofs[kind]={**common,'historical_ready_proofs':[previous['readiness_proof']]}
        return RegistryValidationReport(tuple(sorted(counts.items())),(),(),proofs)
    except (RegistryValidationError,KeyError) as error:
        return RegistryValidationReport(tuple(sorted(counts.items())),(str(error),),(),None)


def _check_projection(report: RegistryValidationReport, oracles: JsonValue, scenarios: JsonValue) -> tuple[str,...]:
    """strict CLI核既有投影。参数：report、两registry；返回：差异；异常：坏shape。"""
    if report.errors or report.gaps:
        return report.errors+report.gaps
    proofs=_mapping(report.proof,'proof')
    errors=[]
    for kind,value in (('oracles',oracles),('scenarios',scenarios)):
        registry=_mapping(value,kind)
        if 'readiness_proof' not in registry or registry['readiness_proof']!=proofs[kind]:
            errors.append(kind+'.readiness_proof: strict recomputation mismatch')
        if _field(registry,'registry_status',kind)!='ready':
            errors.append(kind+'.registry_status: result projection mismatch')
    return tuple(errors)


class _RegistryArguments(argparse.Namespace):
    """仅拥有显式CLI参数；不承载业务状态或额外payload。"""
    check: bool
    oracle_registry: Path
    scenario_registry: Path
    authority_index: Path
    assignment: Path
    before_oracles: Path
    before_scenarios: Path
    evidence_root: Path
    backup_root: Path
    focused_evidence_root: Path
    focused_backup_root: Path
    focused_source: Path
    source_root: Path
    output: Path
    registration_target: str


def _cli_read_boundary(args: _RegistryArguments) -> None:
    """核列明的治理读取白名单。参数：args；返回：无；异常：越界、symlink或非regular。"""
    root=args.source_root.absolute()
    fixed=(
        (args.oracle_registry,'docs/cli_ci_oracles.json'),
        (args.scenario_registry,'docs/cli_ci_scenarios.json'),
        (args.authority_index,'docs/gateflow/evidence/upload-material-registry-20261003/authority-index.json'),
        (args.assignment,'docs/gateflow/evidence/upload-material-registry-20261003/mandatory-assignment.json'),
        (args.focused_source,'docs/gateflow/evidence/upload-material-registry-20261003/focused-source.json'),
        (args.before_oracles,'workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/cli_ci_oracles.json.before'),
        (args.before_scenarios,'workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/cli_ci_scenarios.json.before'),
    )
    for path,relative in fixed:
        if path.absolute()!=root/relative:
            raise RegistryValidationError('CLI read boundary: '+relative)
        _strict_path(root,relative,'CLI read boundary: '+relative)


def _write_cli_report(path: Path, value: JsonValue) -> None:
    """独占创建机器报告。参数：path、value；返回：无；异常：IO/文件存在。"""
    with path.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main(argv: Sequence[str] | None = None) -> int:
    """唯一显式--check入口。参数：argv或进程参数；返回：0ready、1语义/ref/gap、2误用/格式；异常：argparse以2退出。"""
    parser=argparse.ArgumentParser(description='只读验证 upload_material 登记readiness，不执行产品。',allow_abbrev=False)
    parser.add_argument('--check',action='store_true',required=True)
    for name in ('oracle-registry','scenario-registry','authority-index','assignment','before-oracles','before-scenarios','evidence-root','backup-root','focused-evidence-root','focused-backup-root','focused-source','source-root','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--registration-target',required=True)
    args=_RegistryArguments()
    parser.parse_args(argv,namespace=args)
    try:
        _cli_read_boundary(args)
        oracles=load_registry(args.oracle_registry);scenarios=load_registry(args.scenario_registry)
        report=validate_upload_material_registration(oracles,scenarios,load_registry(args.assignment),load_registry(args.authority_index),args.evidence_root.absolute(),args.backup_root.absolute(),args.focused_evidence_root.absolute(),args.focused_backup_root.absolute(),load_registry(args.focused_source),args.source_root.absolute(),args.registration_target,load_registry(args.before_oracles),load_registry(args.before_scenarios))
        errors=_check_projection(report,oracles,scenarios)
        value=_mapping(report.to_json(),'report')
        if errors:
            value['errors']=list(errors);value['validation_result']='fail';value['registry_status']='calibration'
        _write_cli_report(args.output,value)
        return 1 if errors else 0
    except RegistryValidationError as error:
        report=RegistryValidationReport((),(str(error),),(),None)
        try:
            _write_cli_report(args.output,report.to_json())
        except OSError as write_error:
            parser.exit(2,str(write_error)+'\n')
        return 1
    except (OSError,json.JSONDecodeError) as error:
        parser.exit(2,str(error)+'\n')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
