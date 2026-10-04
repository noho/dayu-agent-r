"""登记owner的机械合同回归；合成字段只验证引用/shape，不宣产品实测通过。"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import cast
import hashlib
import json

import pytest

from dayu.contracts.json_value import JsonValue
from utils import cli_ci_upload_material_registry as registry


def _map(value: JsonValue) -> dict[str, JsonValue]:
    """取测试对象。参数：value；返回：映射；异常：非法fixture断言。"""
    assert isinstance(value, dict)
    return value


def _list(value: JsonValue) -> list[JsonValue]:
    """取测试列表。参数：value；返回：列表；异常：非法fixture断言。"""
    assert isinstance(value, list)
    return value


def _write(path: Path, value: JsonValue) -> None:
    """写隔离fixture。参数：path、value；返回：无；异常：IO。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n')


def _descriptor(path: Path, root: Path, source: str = 'cli802') -> JsonValue:
    """取得fixture身份。参数：path、root、source；返回：ref；异常：IO。"""
    raw = path.read_bytes()
    return {'source_id':source,'relative_path':path.relative_to(root).as_posix(),
            'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def _material() -> dict[str, JsonValue]:
    """构造最小shape，文本不代表新业务规则。参数：无；返回：oracle；异常：无。"""
    return {'oracle_id':registry.MATERIAL_ORACLE,'version':1,'status':'accepted',
            'category':'behavioral','scope':{'command':'upload_material'},
            'predicates':[{'predicate_id':p,'expected':['contract text fixture'],
                           'forbidden':['contract text fixture']} for p in registry.PREDICATES],
            'authority_basis':[{'predicate_id':p,'authority_refs':list(registry._PREDICATE_AUTHORITIES[index]),
                'index':registry.AUTHORITY_INDEX_PATH} for index,p in enumerate(registry.PREDICATES)],
            'allowed_variants':['wording variation'],
            'user_adjudication':{'identity':registry.USER_ADJUDICATION_ID,'result':'accepted','notes':['approved fixture']},
            'applicable_from':{'date':'2026-10-04','target':registry.NEXT_RUN},
            'supersedes':None,'superseded_by':None,
            'observed_behavior':{'run_ids':[registry.OLD_RUN,registry.FOCUSED_RUN],
                'report_ids':['old/observed-behavior.md','focused/observed-behavior.md'],
                'report_digest_sha256':['a'*64,'b'*64],'adjudication_artifacts':[{'path':'reference'}],
                'report_frozen':True,'scenario_refs':['upload_material.fixture']}}


def _scenario() -> dict[str, JsonValue]:
    """最小引用fixture。参数：无；返回：scenario；异常：无。"""
    return {'scenario_id':'upload_material.fixture','source_scenario_id':'fixture','version':1,'status':'accepted',
            'command':'upload_material','path_kind':'positive','coverage_claims':{},
            'invocation':{'argv':['cli'],'cwd':'fixture','input_description':['fixture']},
            'precondition':{'state_id':'fixture','setup_steps':['fixture']},
            'accepted_oracle_refs':[registry.MATERIAL_REF],
            'oracle_predicate_refs':[registry.PREDICATES[0]],'correctness_surfaces':[registry.PREDICATES[0]],
            'authorization_requirements':['fixture'], 'resource_budget':{'scope':'fixture'},
            'required_evidence':[],
            'observed_evidence':{'bundle_id':'fixture','report_id':'fixture','report_sha256':'a'*64,
                'relative_ref':'fixture','execution_outcome':'success','exit_code':0,'evidence_status':'sufficient','gap_kind':'none'},
            'user_adjudication_identity':registry.USER_ADJUDICATION_ID,
            'applicable_from':registry.NEXT_RUN,'supersedes':None,'superseded_by':None}


def _oracle_inputs() -> tuple[JsonValue, JsonValue]:
    """最小oracle owner输入。参数：无；返回：两registry；异常：无。"""
    return {'schema_version':1,'oracles':[_material()]}, {'schema_version':1,'scenarios':[_scenario()]}


def test_canonical_basis_only_excludes_top_projection() -> None:
    """合同：嵌套业务字段保留。参数：无；返回：无；异常：断言失败。"""
    first: JsonValue = {'schema_version':1,'record':{'registry_status':'business'},
                        'registry_status':'ready','readiness_proof':{'opaque':42}}
    second: JsonValue = {'readiness_proof':{},'registry_status':'calibration',
                         'record':{'registry_status':'business'},'schema_version':1}
    assert registry._basis(first) == registry._basis(second)
    _map(second)['record'] = {'registry_status':'changed business'}
    assert registry._basis(first) != registry._basis(second)
    assert registry.canonical_digest({'b':2,'a':'中文'}) == registry.canonical_digest({'a':'中文','b':2})


def test_historical_records_and_proof_history_are_full_values() -> None:
    """合同：不迁移旧ref或历史proof。参数：无；返回：无；异常：断言失败。"""
    old: JsonValue = {'schema_version':1,'scenarios':[{'scenario_id':'old','version':1,
        'accepted_oracle_refs':['superseded@1']}],'readiness_proof_history_20260802':{'raw':7}}
    current = deepcopy(old)
    assert registry.compare_historical_records(old,current,'scenario') == ()
    _map(_list(_map(current)['scenarios'])[0])['accepted_oracle_refs']=['current@2']
    assert 'old@1' in registry.compare_historical_records(old,current,'scenario')[0]
    current=deepcopy(old)
    _map(current)['readiness_proof_history_20260802']={'raw':8}
    with pytest.raises(registry.RegistryValidationError,match='readiness_proof_history_20260802'):
        registry.compare_historical_records(old,current,'scenario')


def test_duplicate_record_and_missing_old_oracle_rejected() -> None:
    """合同：identity精确唯一。参数：无；返回：无；异常：断言失败。"""
    before: JsonValue={'schema_version':1,'oracles':[{'oracle_id':'old','version':1,'value':'frozen'}]}
    current=deepcopy(before)
    _list(_map(current)['oracles']).append(deepcopy(_list(_map(current)['oracles'])[0]))
    assert 'duplicate' in registry.compare_historical_records(before,current,'oracle')[0]
    assert 'old@1' in registry.compare_historical_records(before,{'schema_version':1,'oracles':[]},'oracle')[0]


def test_current_stable_owner_and_superseded_frozen_reference() -> None:
    """合同：stable用current、冻结ref仍可指superseded。参数：无；返回：无；异常：断言失败。"""
    oracles,scenarios=_oracle_inputs()
    previous=deepcopy(_material());previous['oracle_id']='previous';previous['status']='superseded'
    _list(_map(oracles)['oracles']).append(previous)
    _map(_list(_map(scenarios)['scenarios'])[0])['accepted_oracle_refs']=[registry.MATERIAL_REF,'previous@1']
    assert registry._oracle_guard(oracles,scenarios,{'upload_material.fixture'})['oracle_id']==registry.MATERIAL_ORACLE
    previous['status']='accepted'
    with pytest.raises(registry.RegistryValidationError,match='duplicate current accepted owner'):
        registry._oracle_guard(oracles,scenarios,{'upload_material.fixture'})


@pytest.mark.parametrize('key,value,location',[
    ('report_frozen',False,'report_frozen'),('run_ids',['wrong','source'],'run_ids'),
    ('scenario_refs',['dangling'],'oracle-to-scenario'),('report_ids',['only-one'],'report_ids'),
])
def test_observed_behavior_contract(key: str,value: JsonValue,location: str) -> None:
    """合同：六内键配对与反向refs。参数：key/value/location；返回：无；异常：断言失败。"""
    oracles,scenarios=_oracle_inputs()
    item=_map(_list(_map(oracles)['oracles'])[0]);_map(item['observed_behavior'])[key]=value
    with pytest.raises(registry.RegistryValidationError,match=location):
        registry._oracle_guard(oracles,scenarios,{'upload_material.fixture'})


def test_missing_predicate_observed_extra_key_and_applicable_date_rejected() -> None:
    """合同：predicate集合、自足形状与日历。参数：无；返回：无；异常：断言失败。"""
    for mode in ('predicate','extra','date','scenario-date','frozen-ref','stable-ref'):
        oracles,scenarios=_oracle_inputs();item=_map(_list(_map(oracles)['oracles'])[0]);scenario=_map(_list(_map(scenarios)['scenarios'])[0])
        if mode=='predicate':_list(item['predicates']).pop()
        elif mode=='extra':_map(item['observed_behavior'])['frozen']=True
        elif mode=='date':_map(item['applicable_from'])['date']='2026-02-30'
        elif mode=='scenario-date':scenario['applicable_from']='799'
        elif mode=='frozen-ref':scenario['accepted_oracle_refs']=['missing@1']
        else:scenario['oracle_predicate_refs']=['missing.predicate']
        with pytest.raises(registry.RegistryValidationError):
            registry._oracle_guard(oracles,scenarios,{'upload_material.fixture'})


@pytest.mark.parametrize('relative',['../escape','/absolute','private/data.json','snapshot.sqlite-wal'])
def test_public_refs_reject_lexical_private_and_database(tmp_path: Path,relative: str) -> None:
    """合同：公开ref不能借路径扩权限。参数：tmp_path/relative；返回：无；异常：断言失败。"""
    roots=(tmp_path/'a',tmp_path/'b',tmp_path/'c',tmp_path/'d')
    ref: JsonValue={'source_id':'cli802','relative_path':relative,'bytes':0,'sha256':'a'*64}
    with pytest.raises(registry.RegistryValidationError):
        registry._public_descriptor(ref,roots,'row-x')


@pytest.mark.parametrize('mode',['unknown-source','missing-sha','wrong-sha','wrong-size','one-copy','wrong-root','leaf-symlink','ancestor-symlink','directory'])
def test_public_ref_identity_and_doublecopy(tmp_path: Path,mode: str) -> None:
    """合同：严格source、双副本、无symlink、regular。参数：tmp_path/mode；返回：无；异常：断言失败。"""
    roots=(tmp_path/'a',tmp_path/'b',tmp_path/'c',tmp_path/'d')
    for root in roots:root.mkdir()
    (roots[2]/'proof.json').write_text('actual fixture bytes')
    (roots[3]/'proof.json').write_text('actual fixture bytes')
    ref=_map(_descriptor(roots[2]/'proof.json',roots[2],'diagnostics-focused04'))
    assert registry._public_descriptor(ref,roots,'row-x')==b'actual fixture bytes'
    if mode=='unknown-source':ref['source_id']='unknown'
    elif mode=='missing-sha':del ref['sha256']
    elif mode=='wrong-sha':ref['sha256']='0'*64
    elif mode=='wrong-size':ref['bytes']=True
    elif mode=='one-copy':(roots[3]/'proof.json').unlink()
    elif mode=='wrong-root':ref['source_id']='cli802'
    elif mode=='leaf-symlink':
        (roots[2]/'proof.json').unlink();(roots[2]/'proof.json').symlink_to(roots[3]/'proof.json')
    elif mode=='ancestor-symlink':
        (roots[2]/'parent').symlink_to(roots[3],target_is_directory=True);ref['relative_path']='parent/proof.json'
    else:
        (roots[2]/'proof.json').unlink();(roots[2]/'proof.json').mkdir()
    with pytest.raises(registry.RegistryValidationError,match='row-x'):
        registry._public_descriptor(ref,roots,'row-x')


def _source_fixture(tmp_path: Path) -> tuple[dict[str,JsonValue],tuple[Path,Path,Path,Path]]:
    """复制精确治理anchor，仅供source guard机械测试。参数：tmp_path；返回：descriptor和roots；异常：IO。"""
    repo=Path(__file__).resolve().parents[2]
    review_path=repo/registry.REVIEW_PATH
    review=_map(registry.load_registry(review_path))
    (tmp_path/registry.REVIEW_PATH).parent.mkdir(parents=True)
    (tmp_path/registry.REVIEW_PATH).write_bytes(review_path.read_bytes())
    receipt_path=repo/registry.RECEIPT_PATH
    (tmp_path/registry.RECEIPT_PATH).parent.mkdir(parents=True,exist_ok=True)
    (tmp_path/registry.RECEIPT_PATH).write_bytes(receipt_path.read_bytes())
    measured: list[JsonValue]=[]
    for relative in registry.MEASURED_PATHS:
        source=repo/relative;dest=tmp_path/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes())
        ref=_map(_descriptor(dest,tmp_path));del ref['source_id'];measured.append(ref)
    roots=(tmp_path/'a',tmp_path/'b',tmp_path/'c',tmp_path/'d')
    for root in roots:root.mkdir()
    focused: dict[str,JsonValue]={'schema_version':1,'source_id':'diagnostics-focused04',
        'registration_target':registry.REGISTRATION_TARGET,'measured_parent':registry.MEASURED_PARENT,
        'measured_source':measured,'reviewed_source':review['source11'],
        'source_records':[],'original_source_descriptors':[], 'report':{},'scan':{},'measurements':[],
        'retention_receipt':{'relative_path':registry.RECEIPT_PATH,'bytes':registry.RECEIPT_BYTES,'sha256':registry.RECEIPT_SHA}}
    return focused,roots


@pytest.mark.parametrize('mode,location',[
    ('parent','measured_parent'),('module','measured_source'),('review','reviewed_source'),
    ('receipt-missing','retention_receipt'),('receipt-shape','retention_receipt'),
    ('receipt-size','retention_receipt'),('receipt-sha','retention_receipt'),
    ('receipt-symlink','retention_receipt'),('receipt-directory','retention_receipt'),
    ('source-schema','exact schema'),
])
def test_source_guard_separates_live_product_and_frozen_review(tmp_path: Path,mode: str,location: str) -> None:
    """合同：五live模块和11历史metadata不同职责。参数：tmp_path/mode/location；返回：无；异常：断言失败。"""
    focused,roots=_source_fixture(tmp_path)
    receipt=tmp_path/registry.RECEIPT_PATH
    if mode=='parent':focused['measured_parent']=registry.REGISTRATION_TARGET
    elif mode=='module':(tmp_path/registry.MEASURED_PATHS[0]).write_text('drift')
    elif mode=='review':_map(_list(focused['reviewed_source'])[0])['sha256']='f'*64
    elif mode=='receipt-missing':receipt.unlink()
    elif mode=='receipt-shape':receipt.write_text('{}')
    elif mode=='receipt-size':_map(focused['retention_receipt'])['bytes']=True
    elif mode=='receipt-sha':_map(focused['retention_receipt'])['sha256']='f'*64
    elif mode=='receipt-symlink':
        raw=receipt.read_bytes();receipt.unlink();other=tmp_path/'other';other.write_bytes(raw);receipt.symlink_to(other)
    elif mode=='receipt-directory':receipt.unlink();receipt.mkdir()
    else:focused['extra']=False
    with pytest.raises(registry.RegistryValidationError,match=location):
        registry._source_guard(focused,roots,tmp_path)


def test_authorized_readme_does_not_become_product_live_guard(tmp_path: Path) -> None:
    """合同：README新条目不改变冻结review事实。参数：tmp_path；返回：无；异常：断言失败。"""
    focused,roots=_source_fixture(tmp_path)
    (tmp_path/'tests').mkdir(exist_ok=True);(tmp_path/'tests/README.md').write_text('authorized new entry')
    # 最小fixture缺original descriptors，必须走过五模块/review/receipt才定位此处。
    with pytest.raises(registry.RegistryValidationError,match='original_source_descriptors'):
        registry._source_guard(focused,roots,tmp_path)


def test_strict_projection_preserves_single_own_history_and_failure_is_separate() -> None:
    """合同：两proof各存自身opaque原值；产品finding不阻registryready。参数：无；返回：无；异常：断言失败。"""
    old_o: JsonValue={'target_commit':'historical-o','arbitrary':[True,None,{'raw':3}]}
    old_s: JsonValue={'target_commit':'historical-s','arbitrary':[False]}
    proof_o: JsonValue={'proof_version':6,'historical_ready_proofs':[old_o],'product_finding':'historical product fail'}
    proof_s: JsonValue={'proof_version':6,'historical_ready_proofs':[old_s],'product_finding':'historical product fail'}
    report=registry.RegistryValidationReport((),(),(),{'oracles':proof_o,'scenarios':proof_s})
    oracles: JsonValue={'registry_status':'ready','readiness_proof':proof_o}
    scenarios: JsonValue={'registry_status':'ready','readiness_proof':proof_s}
    assert registry._check_projection(report,oracles,scenarios)==()
    _map(oracles)['registry_status']='calibration'
    assert 'registry_status' in registry._check_projection(report,oracles,scenarios)[0]
    _map(oracles)['registry_status']='ready';_map(oracles)['readiness_proof']={'historical_ready_proofs':[old_o,old_s]}
    assert 'readiness_proof' in registry._check_projection(report,oracles,scenarios)[0]


@pytest.mark.parametrize('argv',[[],['--check'],['--check','--unknown','anything']])
def test_cli_requires_explicit_check_and_all_known_parameters(argv: list[str]) -> None:
    """合同：误用exit2且无bootstrap。参数：argv；返回：无；异常：断言失败。"""
    with pytest.raises(SystemExit) as error:
        registry.main(argv)
    assert error.value.code==2


def test_argv_retains_empty_text_but_identity_disallows_it() -> None:
    """合同：实际空argv与stable ID不同。参数：无；返回：无；异常：断言失败。"""
    assert registry._argv(['--document-id',''],'argv')==('--document-id','')
    with pytest.raises(registry.RegistryValidationError,match='identity'):
        registry._strings([''],'identity')
    with pytest.raises(registry.RegistryValidationError,match='argv'):
        registry._argv([True],'argv')


def test_existing_scan_is_read_only_and_complete_tree(tmp_path: Path) -> None:
    """合同：只读验sole scan，不产第二真源。参数：tmp_path；返回：无；异常：断言失败。"""
    roots=(tmp_path/'a',tmp_path/'b',tmp_path/'c',tmp_path/'d')
    for root in roots:root.mkdir()
    for root in roots[2:]:
        (root/'observation.json').write_text('observation')
    item=_map(_descriptor(roots[2]/'observation.json',roots[2],'diagnostics-focused04'))
    scan: JsonValue={'status':'complete','files':[{'path':'observation.json','size_bytes':item['bytes'],'sha256':item['sha256']}],
        'scanned_file_count':1,'scanned_byte_count':item['bytes'],'secret_scan':{'status':'complete','hits':[]},
        'path_hygiene':{'status':'complete','violations':[]},'validation_errors':[]}
    for root in roots[2:]:_write(root/'secret-scan.json',scan)
    ref=_descriptor(roots[2]/'secret-scan.json',roots[2],'diagnostics-focused04')
    original=(roots[2]/'secret-scan.json').read_bytes()
    registry._scan_guard('diagnostics-focused04',ref,roots)
    assert (roots[2]/'secret-scan.json').read_bytes()==original
    (roots[3]/'extra.json').write_text('extra')
    with pytest.raises(registry.RegistryValidationError,match='source tree'):
        registry._scan_guard('diagnostics-focused04',ref,roots)


def _assignment_fixture(tmp_path: Path) -> tuple[dict[str,JsonValue],JsonValue,dict[str,tuple[str,...]],tuple[Path,Path,Path,Path],dict[str,JsonValue]]:
    """按原始两种结果shape建立隔离引用图。参数：tmp_path；返回：assignment/scenarios/authority/roots/focused；异常：IO。"""
    roots=(tmp_path/'a',tmp_path/'b',tmp_path/'c',tmp_path/'d')
    for root in roots:root.mkdir()
    parser: JsonValue={'root':[{'options':['--log-level'],'nargs':'None'}],
        'upload_material':[{'options':['--files'],'nargs':'None'}],'commands':['upload_material']}
    for root in roots[:2]:
        _write(root/'parser.json',parser);_write(root/'interactive.json',{'branches':[]})
        _write(root/'pairwise.json',{'axes':[],'cases':[]})
        _write(root/'matrix.json',[{'id':'fixture','argv':['dayu-cli','upload_material'],'state':'fresh','input_class':'empty','claims':['fixture-obligation']}])
        _write(root/'index.json',[{'scenario_id':'fixture'}])
    matrix: JsonValue={'name':'minimal','matrix':_descriptor(roots[0]/'matrix.json',roots[0]),'execution_index':_descriptor(roots[0]/'index.json',roots[0])}
    inventory: JsonValue={'parser':_descriptor(roots[0]/'parser.json',roots[0]),'interactive':_descriptor(roots[0]/'interactive.json',roots[0]),'pairwise':_descriptor(roots[0]/'pairwise.json',roots[0]),'matrices':[matrix]}
    rows: list[JsonValue]=[];scenarios: list[JsonValue]=[];measurements: list[JsonValue]=[]
    for index,identity in enumerate(('fixture',*('diagnostics-focused04.'+c for c in registry.FOCUSED_CASES))):
        source='cli802' if index==0 else 'diagnostics-focused04';pair=roots[:2] if index==0 else roots[2:]
        case='fixture' if index==0 else identity.split('.',1)[1]
        input_class='empty' if index==0 else ('controlled-XBRL-instance' if case==registry.FOCUSED_CASES[-1] else 'native-PDF')
        argv: list[JsonValue]=['dayu-cli','upload_material'] if index==0 else ['python','-m','dayu.cli','upload_material','--files','fixture.xml' if case==registry.FOCUSED_CASES[-1] else 'fixture.pdf']
        command: JsonValue={'argv':argv,'cwd':'/fixture','checkpoint_parent':registry.MEASURED_PARENT}
        if case!=registry.FOCUSED_CASES[-1]:_map(command)['stdin']='EOF'
        actual_exit=2 if index==0 else (130 if case==registry.FOCUSED_CASES[-2] else 0)
        outcome='error' if index==0 else ('cancel' if actual_exit==130 else 'success')
        result: JsonValue={'execution_outcome':'error','process_outcome':{'actual_wait_returncode':2}} if index==0 else (
            {'actual_wait':True,'actual_exit':0} if case==registry.FOCUSED_CASES[-1] else {'actual_wait':True,'exit':actual_exit})
        result_name='actual-exit.json' if case==registry.FOCUSED_CASES[-1] else 'result.json'
        for root in pair:
            _write(root/case/'command.json',command);_write(root/case/result_name,result)
        required: list[JsonValue]=[_descriptor(pair[0]/case/name,pair[0],source) for name in ('command.json',result_name)]
        stable='fixture-obligation' if index==0 else 'focused:'+case
        claims: JsonValue={'command_parameter_ids':['command:upload_material'] if index==0 else ['command:upload_material','parameter:--files'],
            'precondition_state_ids':['state:fresh' if index==0 else 'state:independent-fresh'],'interactive_branch_option_ids':[],
            'input_class_ids':['input:'+input_class],'combination_high_risk_ids':[stable],
            'cross_command_assertion_ids':[],'raw_stable_claims':[stable]}
        surfaces: list[JsonValue]=[{'predicate_id':p,'authority_refs':['approved:'+p],'evidence_status':'sufficient',
            'measurement_refs':[case+'/command.json',case+'/'+result_name]} for p in registry.PREDICATES]
        row: JsonValue={'source_id':source,'source_scenario_id':identity,'physical_command':'upload_material','formal':True,'classification_reason':'mechanical fixture only',
            'registration_class':'fixture','campaign_role':'primary','state':'fresh' if index==0 else 'independent-fresh','input_class':input_class,
            'invocation_argv':argv,'command_ref':case+'/command.json','result_ref':case+'/'+result_name,
            'execution_outcome':outcome,'actual_exit':actual_exit,'actual_wait':True,'coverage_claims':claims,'required_evidence':required,'surfaces':surfaces}
        rows.append(row)
        invocation: dict[str,JsonValue]={'argv':argv,'cwd':'/fixture','input_description':[input_class]}
        if case!=registry.FOCUSED_CASES[-1]:invocation['stdin']='EOF'
        scenarios.append({'scenario_id':'upload_material.'+identity,'source_scenario_id':identity,'command':'upload_material','path_kind':'positive',
            'coverage_claims':claims,'invocation':invocation,'precondition':{'state_id':row['state'],'setup_steps':['fixture']},
            'oracle_predicate_refs':list(registry.PREDICATES),'correctness_surfaces':list(registry.PREDICATES),'required_evidence':required,
            'observed_evidence':{'bundle_id':'old-run' if index==0 else 'focused-run',
                'report_id':registry.PUBLIC_ROOTS[0 if index==0 else 2]+'/observed-behavior.md',
                'report_sha256':'a'*64 if index==0 else 'b'*64,'relative_ref':case,
                'execution_outcome':outcome,'exit_code':actual_exit,'evidence_status':'sufficient','gap_kind':'none'}})
        if index>0:measurements.append({'measurement_id':case,'source_scenario_id':identity,
            'required_evidence':required,'actual_exit':actual_exit,'actual_wait':True})
    sources: JsonValue=[{'source_id':'cli802','run_id':'old-run','report':{'sha256':'a'*64}},
        {'source_id':'diagnostics-focused04','run_id':'focused-run','report':{'sha256':'b'*64}}]
    return ({'rows':rows,'inventory':inventory,'evidence_sources':sources},
        {'schema_version':1,'scenarios':scenarios},{p:('approved:'+p,) for p in registry.PREDICATES},roots,{'measurements':measurements})


def test_assignment_counts_derive_from_rows_and_dimensions(tmp_path: Path) -> None:
    """合同：error不能当gap或业务pass，计数与各维来自真实输入图。参数：tmp_path；返回：无；异常：断言失败。"""
    assignment,scenarios,authority,roots,focused=_assignment_fixture(tmp_path)
    counts,ids,campaign=registry._assignment_guard(assignment,scenarios,authority,roots,focused)
    assert counts['source_cli802']==1 and counts['source_focused']==6
    assert counts['new_formal_scenarios']==len(ids)==7
    dimensions=_map(_map(campaign)['coverage_dimensions'])
    assert _map(dimensions['precondition_state_ids'])['mandatory']==2
    assert _map(dimensions['interactive_branch_option_ids'])['mandatory']==0


@pytest.mark.parametrize('mode,location',[
    ('authority','mandatory surface'),('evidence','measurement missing'),('gap','evidence_status'),
    ('dimension','coverage_dimensions'),('raw-claims','raw_stable_claims'),('argv','argv'),
    ('fake-service','physical_command'),('fake-shell','physical_command'),
    ('missing-row','incomplete cli802'),('duplicate-row','duplicate source_scenario_id'),
    ('unknown-source','incomplete cli802'),('no-credit','formal-credit-scope'),
    ('scenario-ref','formal scenario missing'),('reverse-ref','dangling scenario-to-assignment'),
    ('interactive-credit','coverage_dimensions'),
])
def test_assignment_owner_negatives(tmp_path: Path,mode: str,location: str) -> None:
    """合同：单项破坏必须定位row/维度，不借其它维度抵扣。参数：tmp_path/mode/location；返回：无；异常：断言失败。"""
    assignment,scenarios,authority,roots,focused=_assignment_fixture(tmp_path)
    rows=_list(assignment['rows']);row=_map(rows[0]);surface=_map(_list(row['surfaces'])[0]);claims=_map(row['coverage_claims'])
    if mode=='authority':surface['authority_refs']=[]
    elif mode=='evidence':surface['measurement_refs']=['not-read.json']
    elif mode=='gap':surface['evidence_status']='missing'
    elif mode=='dimension':claims['input_class_ids']=[]
    elif mode=='raw-claims':claims['raw_stable_claims']=['invented']
    elif mode=='argv':row['invocation_argv']=['invented']
    elif mode=='fake-service':row['physical_command']='service.upload_material'
    elif mode=='fake-shell':row['physical_command']='sh'
    elif mode=='missing-row':rows.pop(0)
    elif mode=='duplicate-row':rows.append(deepcopy(rows[0]))
    elif mode=='unknown-source':row['source_id']='not-a-source'
    elif mode=='no-credit':row['formal']=False
    elif mode=='scenario-ref':_list(_map(scenarios)['scenarios']).pop(0)
    elif mode=='reverse-ref':
        extra=deepcopy(_list(_map(scenarios)['scenarios'])[0]);_map(extra)['scenario_id']='upload_material.extra';_list(_map(scenarios)['scenarios']).append(extra)
    else:claims['interactive_branch_option_ids']=['invented-branch']
    with pytest.raises(registry.RegistryValidationError,match=location):
        registry._assignment_guard(assignment,scenarios,authority,roots,focused)


@pytest.mark.parametrize('case,field,value,location',[
    ('XBRL-REAL-NATIVE-04','actual_exit',999,'actual_exit'),
    ('NATIVE-DEFAULT-04','actual_wait',False,'actual_wait'),
    ('NATIVE-SIGINT-04','execution_outcome','success','execution_outcome'),
    ('XBRL-REAL-NATIVE-04','result_ref','XBRL-REAL-NATIVE-04/command.json','result_ref'),
    ('NATIVE-DEFAULT-04','measurement_exit',999,'measurement.actual_exit'),
    ('NATIVE-DEFAULT-04','measurement_wait',False,'measurement.actual_wait'),
    ('XBRL-REAL-NATIVE-04','scenario_exit',999,'exit_code'),
])
def test_focused_terminal_is_bound_to_original_result(tmp_path: Path,case: str,field: str,value: JsonValue,location: str) -> None:
    """合同：PDF和XBRL终态均须与原result一致。参数：tmp_path/case/field/value/location；返回：无；异常：断言失败。"""
    assignment,scenarios,authority,roots,focused=_assignment_fixture(tmp_path)
    row=next(_map(v) for v in _list(assignment['rows']) if _map(v)['source_scenario_id']=='diagnostics-focused04.'+case)
    scenario=next(_map(v) for v in _list(_map(scenarios)['scenarios']) if _map(v)['source_scenario_id']=='diagnostics-focused04.'+case)
    if field=='measurement_exit':
        measurement=next(_map(v) for v in _list(focused['measurements']) if _map(v)['measurement_id']==case)
        measurement['actual_exit']=value
    elif field=='measurement_wait':
        measurement=next(_map(v) for v in _list(focused['measurements']) if _map(v)['measurement_id']==case)
        measurement['actual_wait']=value
    elif field=='scenario_exit':
        _map(scenario['observed_evidence'])['exit_code']=value
    else:
        row[field]=value
        if field=='actual_exit':_map(scenario['observed_evidence'])['exit_code']=value
        if field=='execution_outcome':_map(scenario['observed_evidence'])['execution_outcome']=value
    with pytest.raises(registry.RegistryValidationError,match=location):
        registry._assignment_guard(assignment,scenarios,authority,roots,focused)


def test_coverage_cannot_trade_missing_state_for_extra_command(tmp_path: Path) -> None:
    """合同：跨维增加command不能抵消state缺口。参数：tmp_path；返回：无；异常：断言失败。"""
    assignment,scenarios,authority,roots,focused=_assignment_fixture(tmp_path)
    claims=_map(_map(_list(assignment['rows'])[1])['coverage_claims'])
    claims['precondition_state_ids']=[]
    claims['command_parameter_ids']=['command:upload_material','parameter:--files','state:independent-fresh']
    with pytest.raises(registry.RegistryValidationError,match='coverage_dimensions'):
        registry._assignment_guard(assignment,scenarios,authority,roots,focused)


@pytest.mark.parametrize('key',('source_id','result_ref','coverage_claims'))
def test_missing_assignment_field_keeps_row_locator(tmp_path: Path,key: str) -> None:
    """合同：缺字段错误带assignment行与字段名。参数：tmp_path/key；返回：无；异常：断言失败。"""
    assignment,scenarios,authority,roots,focused=_assignment_fixture(tmp_path)
    del _map(_list(assignment['rows'])[1])[key]
    with pytest.raises(registry.RegistryValidationError,match='assignment.rows.1.diagnostics-focused04.NATIVE-DEFAULT-04.'+key):
        registry._assignment_guard(assignment,scenarios,authority,roots,focused)


@pytest.mark.parametrize('dimension,value',[
    ('command_parameter_ids',['command:upload_material','parameter:--files','parameter:--fabricated-flag']),
    ('precondition_state_ids',[]),('input_class_ids',['input:unmeasured']),
    ('combination_high_risk_ids',[]),('cross_command_assertion_ids',['wiring:invented']),
    ('interactive_branch_option_ids',['branch:invented']),
])
def test_focused_six_dimensions_reject_fabricated_or_missing_credit(tmp_path: Path,dimension: str,value: JsonValue) -> None:
    """合同：六维各自按冻结测量派生，不跨维抵扣。参数：tmp_path/dimension/value；返回：无；异常：断言失败。"""
    assignment,scenarios,authority,roots,focused=_assignment_fixture(tmp_path)
    row=_map(_list(assignment['rows'])[1]);_map(row['coverage_claims'])[dimension]=value
    scenario=_map(_list(_map(scenarios)['scenarios'])[1]);_map(scenario['coverage_claims'])[dimension]=value
    with pytest.raises(registry.RegistryValidationError,match='coverage_dimensions'):
        registry._assignment_guard(assignment,scenarios,authority,roots,focused)


@pytest.mark.parametrize('key',('authority_basis','allowed_variants','user_adjudication'))
def test_material_oracle_rejects_each_missing_contract_field(key: str) -> None:
    """合同：三项已批准oracle必填字段各自阻断。参数：key；返回：无；异常：断言失败。"""
    oracles,scenarios=_oracle_inputs();del _map(_list(_map(oracles)['oracles'])[0])[key]
    with pytest.raises(registry.RegistryValidationError,match='oracles.material.'+key):
        registry._oracle_guard(oracles,scenarios,{'upload_material.fixture'})


@pytest.mark.parametrize('key',('predicate_id','expected','forbidden'))
def test_material_predicate_missing_field_keeps_record_and_index(key: str) -> None:
    """合同：谓词首次消费即报告record、predicate索引和字段。参数：key；返回：无；异常：合同错误。"""
    oracles,scenarios=_oracle_inputs()
    predicate=_map(_list(_map(_list(_map(oracles)['oracles'])[0])['predicates'])[0])
    del predicate[key]
    with pytest.raises(registry.RegistryValidationError) as error:
        registry._oracle_guard(oracles,scenarios,{'upload_material.fixture'})
    assert 'predicates.0.'+key in str(error.value)
    if key=='predicate_id':
        assert 'oracles.record.0.' in str(error.value)
    else:
        assert 'oracles.material.' in str(error.value)


@pytest.mark.parametrize('key',('bundle_id','report_id','report_sha256','relative_ref','execution_outcome','exit_code','evidence_status','gap_kind'))
def test_new_scenario_rejects_each_missing_observed_field(key: str) -> None:
    """合同：报告与终态八项逐项必填。参数：key；返回：无；异常：断言失败。"""
    oracles,scenarios=_oracle_inputs();scenario=_map(_list(_map(scenarios)['scenarios'])[0])
    del _map(scenario['observed_evidence'])[key]
    with pytest.raises(registry.RegistryValidationError,match='observed_evidence.'+key):
        registry._oracle_guard(oracles,scenarios,{'upload_material.fixture'})


def test_new_oracle_rejects_wrong_authority_and_adjudication_shape() -> None:
    """合同：批准血缘及裁决内容不能空壳或改引用。参数：无；返回：无；异常：断言失败。"""
    for key in ('authority','variant','adjudication'):
        oracles,scenarios=_oracle_inputs();oracle=_map(_list(_map(oracles)['oracles'])[0])
        if key=='authority':_map(_list(oracle['authority_basis'])[0])['authority_refs']=['invented']
        elif key=='variant':oracle['allowed_variants']=[]
        else:del _map(oracle['user_adjudication'])['result']
        with pytest.raises(registry.RegistryValidationError,match='authority_basis|allowed_variants|user_adjudication'):
            registry._oracle_guard(oracles,scenarios,{'upload_material.fixture'})


@pytest.mark.parametrize('key,value',[
    ('source_scenario_id',None),('path_kind','invented'),('precondition',None),
    ('authorization_requirements',None),('resource_budget',None),
    ('user_adjudication_identity',None),('supersedes','unexpected'),('superseded_by','unexpected'),
    ('observed_evidence',None),
])
def test_new_scenario_required_shape_and_enums(key: str,value: JsonValue) -> None:
    """合同：新增记录缺血缘、非法枚举及错误类型定位。参数：key/value；返回：无；异常：断言失败。"""
    oracles,scenarios=_oracle_inputs();scenario=_map(_list(_map(scenarios)['scenarios'])[0])
    if value is None:del scenario[key]
    else:scenario[key]=value
    with pytest.raises(registry.RegistryValidationError,match=key):
        registry._oracle_guard(oracles,scenarios,{'upload_material.fixture'})


@pytest.mark.parametrize('key',('bundle_id','report_id','report_sha256','relative_ref','gap_kind'))
def test_scenario_report_identity_is_bound_to_its_source(tmp_path: Path,key: str) -> None:
    """合同：报告源五项不得由scenario自行声明。参数：tmp_path/key；返回：无；异常：断言失败。"""
    assignment,scenarios,authority,roots,focused=_assignment_fixture(tmp_path)
    scenario=_map(_list(_map(scenarios)['scenarios'])[1]);_map(scenario['observed_evidence'])[key]='0'*64 if key=='report_sha256' else 'invented'
    with pytest.raises(registry.RegistryValidationError,match='observed_evidence.'+key):
        registry._assignment_guard(assignment,scenarios,authority,roots,focused)


@pytest.mark.parametrize('key,value',[
    ('cwd','/unmeasured'),('input_description',['other']),('stdin','other'),
])
def test_scenario_invocation_tracks_original_command(tmp_path: Path,key: str,value: JsonValue) -> None:
    """合同：cwd、输入分类和已存在stdin对账原command。参数：tmp_path/key/value；返回：无；异常：断言失败。"""
    assignment,scenarios,authority,roots,focused=_assignment_fixture(tmp_path)
    scenario=_map(_list(_map(scenarios)['scenarios'])[1]);_map(scenario['invocation'])[key]=value
    with pytest.raises(registry.RegistryValidationError,match='invocation.'+key):
        registry._assignment_guard(assignment,scenarios,authority,roots,focused)


def test_real_sigkill_result_requires_crash_class_without_rewriting_outcome() -> None:
    """合同：两原signal9/wait-9且非deadline观测归crash，error原值保持。参数：无；返回：无；异常：断言失败。"""
    repo=Path(__file__).resolve().parents[2]
    root=repo/registry.PUBLIC_ROOTS[0]
    for case in ('CRASH-GROUP','TREE-SIGKILL'):
        result=_map(registry.load_registry(root/case/'result.json'))
        assert result['execution_outcome']=='error'
        process=_map(result['process_outcome'])
        registry._crash_path_kind(process,'crash',case)
        with pytest.raises(registry.RegistryValidationError,match=case+'.path_kind'):
            registry._crash_path_kind(process,'negative',case)


def test_non_sigkill_result_rejects_false_crash_label() -> None:
    """合同：无强杀事实不得登记crash，原execution outcome不变。参数：无；返回：无；异常：合同错误。"""
    repo=Path(__file__).resolve().parents[2]
    result=_map(registry.load_registry(repo/registry.PUBLIC_ROOTS[0]/'LOG-CONFLICT-00-00'/'result.json'))
    assert result['execution_outcome']=='error'
    process=_map(result['process_outcome'])
    assert process['signal'] is None and process['actual_wait_returncode']==2 and process['harness_deadline_kill'] is False
    registry._crash_path_kind(process,'negative','LOG-CONFLICT-00-00')
    with pytest.raises(registry.RegistryValidationError,match='LOG-CONFLICT-00-00.path_kind: crash requires SIGKILL facts'):
        registry._crash_path_kind(process,'crash','LOG-CONFLICT-00-00')


@pytest.mark.parametrize('key',('actual_operation_observation','terminal_status','terminal_exit'))
def test_service_observation_missing_field_keeps_row_locator(key: str) -> None:
    """合同：Service终态三处缺字段定位原row。参数：key；返回：无；异常：合同错误。"""
    repo=Path(__file__).resolve().parents[2]
    evidence=repo/'docs/gateflow/evidence/upload-material-registry-20261003'
    assignment=_map(registry.load_registry(evidence/'mandatory-assignment.json'))
    rows=_list(assignment['rows'])
    index=next(i for i,value in enumerate(rows) if _map(value)['campaign_role']=='Service-owner')
    row=_map(rows[index]);identity=str(row['source_scenario_id'])
    if key=='actual_operation_observation':
        del row[key]
    else:
        del _map(row['actual_operation_observation'])[key]
    scenarios=registry.load_registry(repo/'docs/cli_ci_scenarios.json')
    authority=registry._authority_guard(_map(registry.load_registry(evidence/'authority-index.json')),repo)
    focused=_map(registry.load_registry(evidence/'focused-source.json'))
    roots=(repo/registry.PUBLIC_ROOTS[0],repo/registry.PUBLIC_ROOTS[1],
           repo/registry.PUBLIC_ROOTS[2],repo/registry.PUBLIC_ROOTS[3])
    with pytest.raises(registry.RegistryValidationError) as error:
        registry._assignment_guard(assignment,scenarios,authority,roots,focused)
    expected='assignment.rows.'+str(index)+'.'+identity
    if key!='actual_operation_observation':
        expected+='.actual_operation_observation'
    assert expected+'.'+key in str(error.value)


@pytest.mark.parametrize('source_index,key,location',[
    (0,'target','assignment.cli802.target'),
    (0,'report','assignment.cli802.report'),
    (0,'scan','assignment.cli802.scan'),
    (1,'registration_target','assignment.focused.registration_target'),
    (1,'measured_parent','assignment.focused.measured_parent'),
    (1,'report','assignment.focused.report'),
    (1,'scan','assignment.focused.scan'),
])
def test_evidence_source_missing_consumed_field_has_locator(source_index: int,key: str,location: str) -> None:
    """合同：两类source原有必填缺失定位来源和字段。参数：source_index、key、location；返回：无；异常：报告错误。"""
    repo=Path(__file__).resolve().parents[2]
    evidence=repo/'docs/gateflow/evidence/upload-material-registry-20261003'
    before=repo/'workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation'
    assignment=_map(registry.load_registry(evidence/'mandatory-assignment.json'))
    del _map(_list(assignment['evidence_sources'])[source_index])[key]
    roots=(repo/registry.PUBLIC_ROOTS[0],repo/registry.PUBLIC_ROOTS[1],
           repo/registry.PUBLIC_ROOTS[2],repo/registry.PUBLIC_ROOTS[3])
    report=registry.validate_upload_material_registration(
        registry.load_registry(repo/'docs/cli_ci_oracles.json'),registry.load_registry(repo/'docs/cli_ci_scenarios.json'),
        assignment,registry.load_registry(evidence/'authority-index.json'),*roots,
        registry.load_registry(evidence/'focused-source.json'),repo,registry.REGISTRATION_TARGET,
        registry.load_registry(before/'cli_ci_oracles.json.before'),registry.load_registry(before/'cli_ci_scenarios.json.before'))
    assert report.errors and location+': missing' in report.errors[0]


def test_current_frozen_sources_pass_owner_contract_without_product_rerun() -> None:
    """合同：当前PDF/XBRL原始shape及旧全值在唯一producer通过。参数：无；返回：无；异常：断言失败。"""
    repo=Path(__file__).resolve().parents[2]
    evidence=repo/'docs/gateflow/evidence/upload-material-registry-20261003'
    before=repo/'workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation'
    report=registry.validate_upload_material_registration(
        registry.load_registry(repo/'docs/cli_ci_oracles.json'),registry.load_registry(repo/'docs/cli_ci_scenarios.json'),
        registry.load_registry(evidence/'mandatory-assignment.json'),registry.load_registry(evidence/'authority-index.json'),
        repo/registry.PUBLIC_ROOTS[0],repo/registry.PUBLIC_ROOTS[1],repo/registry.PUBLIC_ROOTS[2],repo/registry.PUBLIC_ROOTS[3],
        registry.load_registry(evidence/'focused-source.json'),repo,registry.REGISTRATION_TARGET,
        registry.load_registry(before/'cli_ci_oracles.json.before'),registry.load_registry(before/'cli_ci_scenarios.json.before'))
    assert report.errors==() and report.gaps==()
    assert dict(report.counts)=={'excluded':9,'new_formal_scenarios':799,'new_oracles':1,
        'new_predicates':19,'source_cli802':802,'source_focused':6}


@pytest.mark.parametrize('case',registry.FOCUSED_CASES)
def test_focused_formal_crash_requires_actual_sigkill_facts(case: str) -> None:
    """合同：六个真实focused终态均不能凭scenario标签获得crash信用。参数：case；返回：无；异常：断言失败。"""
    repo=Path(__file__).resolve().parents[2]
    evidence=repo/'docs/gateflow/evidence/upload-material-registry-20261003'
    before=repo/'workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation'
    scenarios=registry.load_registry(repo/'docs/cli_ci_scenarios.json')
    scenario_id='upload_material.diagnostics-focused04.'+case
    matching=[_map(value) for value in _list(_map(scenarios)['scenarios'])
              if _map(value)['scenario_id']==scenario_id]
    assert len(matching)==1 and matching[0]['path_kind']!='crash'
    matching[0]['path_kind']='crash'
    report=registry.validate_upload_material_registration(
        registry.load_registry(repo/'docs/cli_ci_oracles.json'),scenarios,
        registry.load_registry(evidence/'mandatory-assignment.json'),registry.load_registry(evidence/'authority-index.json'),
        repo/registry.PUBLIC_ROOTS[0],repo/registry.PUBLIC_ROOTS[1],repo/registry.PUBLIC_ROOTS[2],repo/registry.PUBLIC_ROOTS[3],
        registry.load_registry(evidence/'focused-source.json'),repo,registry.REGISTRATION_TARGET,
        registry.load_registry(before/'cli_ci_oracles.json.before'),registry.load_registry(before/'cli_ci_scenarios.json.before'))
    assert report.errors==('assignment.diagnostics-focused04.'+case+'.path_kind: crash requires SIGKILL facts',)
    assert report.proof is None


def test_source_bundle_identity_cannot_be_relabelled_with_scenarios() -> None:
    """合同：即使六scenario同步伪造bundle，source运行身份仍锁原件。参数：无；返回：无；异常：断言失败。"""
    repo=Path(__file__).resolve().parents[2]
    evidence=repo/'docs/gateflow/evidence/upload-material-registry-20261003'
    before=repo/'workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation'
    assignment=registry.load_registry(evidence/'mandatory-assignment.json')
    scenarios=registry.load_registry(repo/'docs/cli_ci_scenarios.json')
    _map(_list(_map(assignment)['evidence_sources'])[1])['run_id']='forged-run'
    for value in _list(_map(scenarios)['scenarios']):
        scenario=_map(value)
        if str(scenario['scenario_id']).startswith('upload_material.diagnostics-focused04.'):
            _map(scenario['observed_evidence'])['bundle_id']='forged-run'
    report=registry.validate_upload_material_registration(
        registry.load_registry(repo/'docs/cli_ci_oracles.json'),scenarios,assignment,
        registry.load_registry(evidence/'authority-index.json'),
        repo/registry.PUBLIC_ROOTS[0],repo/registry.PUBLIC_ROOTS[1],repo/registry.PUBLIC_ROOTS[2],repo/registry.PUBLIC_ROOTS[3],
        registry.load_registry(evidence/'focused-source.json'),repo,registry.REGISTRATION_TARGET,
        registry.load_registry(before/'cli_ci_oracles.json.before'),registry.load_registry(before/'cli_ci_scenarios.json.before'))
    assert report.errors and 'assignment.focused.run_id' in report.errors[0]


def test_root_argv_uses_frozen_parameter_arity() -> None:
    """合同：root参数值即使命名像command也不猜leaf。参数：无；返回：无；异常：断言失败。"""
    parser: dict[str,JsonValue]={'root':[{'options':['--base'],'nargs':'None'},{'options':['--quiet'],'nargs':'0'}],
        'commands':['upload_material','tool_trace']}
    assert registry._cli_leaf(('cli','--base','tool_trace','--quiet','upload_material'),parser,'row')=='upload_material'
    assert registry._cli_leaf(('cli','--base=upload_material','tool_trace','analyze'),parser,'row')=='tool_trace analyze'
    with pytest.raises(registry.RegistryValidationError,match='row'):
        registry._cli_leaf(('cli','--unknown','upload_material'),parser,'row')


def test_public_descriptor_extra_key_rejected(tmp_path: Path) -> None:
    """合同：extra字段不能形成隐含读入口。参数：tmp_path；返回：无；异常：断言失败。"""
    ref: JsonValue={'source_id':'cli802','relative_path':'proof','bytes':0,'sha256':'a'*64,'private_path':'other'}
    with pytest.raises(registry.RegistryValidationError,match='exact public descriptor'):
        registry._public_descriptor(ref,(tmp_path,tmp_path,tmp_path,tmp_path),'row-x')


@pytest.mark.parametrize('mode',['review-consensus','missing-user-adjudication'])
def test_authority_never_promotes_reviewer_consensus(tmp_path: Path,monkeypatch: pytest.MonkeyPatch,mode: str) -> None:
    """合同：冻结来源标签不代替明确用户正文。参数：tmp_path/monkeypatch/mode；返回：无；异常：断言失败。"""
    # 只替换fixture自身的索引byte身份，未替换判据或生产权威；不声称产品通过。
    frozen: JsonValue={'files':{}}
    raw=json.dumps(frozen).encode()+b' '*(4915-len(json.dumps(frozen).encode()))
    index=tmp_path/registry.AUTHORITY_LIST_PATH;index.parent.mkdir(parents=True);index.write_bytes(raw)
    monkeypatch.setattr(registry,'AUTHORITY_LIST_SHA',hashlib.sha256(raw).hexdigest())
    source=tmp_path/registry.SUPPLEMENT_PATHS[0]
    _write(source,{'candidates':[{'candidate_id':'UM-CI-N01','status':'accepted','reviewers':['agree']}]})
    content=source.read_bytes()
    sources: list[JsonValue]=[{'authority_id':'UM-CI-N01','relative_path':registry.SUPPLEMENT_PATHS[0],
        'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),
        'kind':'reviewer-consensus' if mode=='review-consensus' else 'user-decision',
        'approval_provenance':'fixture','anchors':[]}]
    with pytest.raises(registry.RegistryValidationError,match='reviewer consensus|user_adjudication'):
        registry._authority_guard({'sources':sources,'predicates':[]},tmp_path)


def test_old_scan_identity_cannot_be_replaced_by_focused_scan(tmp_path: Path) -> None:
    """合同：旧sole scan身份固定。参数：tmp_path；返回：无；异常：断言失败。"""
    ref: JsonValue={'source_id':'cli802','relative_path':'secret-scan.json','bytes':0,'sha256':'f'*64}
    with pytest.raises(registry.RegistryValidationError,match='scan.cli802.original'):
        registry._scan_guard('cli802',ref,(tmp_path,tmp_path,tmp_path,tmp_path))


def test_validation_rejects_wrong_root_without_product_calls(tmp_path: Path) -> None:
    """合同：四root位置参数不得混用。参数：tmp_path；返回：无；异常：断言失败。"""
    report=registry.validate_upload_material_registration({}, {}, {}, {}, tmp_path,tmp_path,tmp_path,tmp_path,{},tmp_path,registry.REGISTRATION_TARGET,{}, {})
    assert report.errors and 'root binding' in report.errors[0]
    assert _map(report.to_json())['registry_status']=='calibration'


def test_parameter_ids_come_from_frozen_action_not_unsupported_argv() -> None:
    """合同：别名规范ID同源，删除项/缩写仅保观察。参数：无；返回：无；异常：断言失败。"""
    inventory: dict[str,JsonValue]={'root':[{'options':['--base','-b','--workspace']}],
        'upload_material':[{'options':['--files']} ]}
    claims=registry._parameter_claims(('cli','upload_material','--workspace','where','--files','x','--file','x','--removed','x'),'upload_material',inventory)
    assert claims==['parameter:--base','parameter:--files']
    assert registry._parameter_claims(('python','--files','x'),'service.upload_material',inventory)==[]
