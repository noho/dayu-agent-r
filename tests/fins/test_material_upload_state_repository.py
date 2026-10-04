"""真实 Fs 材料状态、条件提交及独立公司严格事实测试。"""
from __future__ import annotations

import hashlib
import json
from io import BytesIO
from dataclasses import replace
from pathlib import Path
from collections.abc import Mapping
from typing import cast

import pytest
from docling_core.types.doc.document import DoclingDocument

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.company_meta_contract import CompanyMetaConcurrentUpdateError
from dayu.fins.domain.document_models import BatchToken, CompanyMeta, SourceDocumentUpsertRequest, SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.docling_upload_service import build_material_ids, _PendingFileAsset, _build_upload_source_fingerprint, _resolve_document_version
from dayu.fins.pipelines.upload_company_meta import resolve_upload_company_meta_decision, stage_upload_company_meta_decision
from dayu.fins.storage import FsBatchingRepository, FsCompanyMetaRepository, FsDocumentBlobRepository, FsMaterialUploadStateRepository, FsSourceDocumentRepository, MaterialUploadPublishedState, SourceIntegrityStatus, SourceIntegrityRevisionConflictError, CompanyTickerAliasConflictError
from dayu.fins.storage._fs_storage_core import FsStorageCore
from dayu.fins.storage._fs_storage_infra import _ActiveBatchState, _PHASE_COMMITTED
from dayu.runtime.filelock import RuntimeFileLockToken
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage.source_manifest_contract import project_material_manifest_item


_IDENTITY = build_material_ids(form_type='MATERIAL_OTHER', material_name='Deck', fiscal_year=None, fiscal_period=None, document_id=None)

def _publish(root: Path, *, amended: bool = False) -> tuple[_FsRepositorySet, MaterialUploadPublishedState]:
    """参数：独占根/真实标记；返回：共享仓储与实际 final；异常：真实仓储失败。"""
    repositories = build_fs_repository_set(workspace_root=root)
    batching = FsBatchingRepository(root, repository_set=repositories)
    state_repo = FsMaterialUploadStateRepository(root, repository_set=repositories)
    blob = FsDocumentBlobRepository(root, repository_set=repositories)
    source = FsSourceDocumentRepository(root, repository_set=repositories)
    old = state_repo.read_material_upload_state('AAPL', _IDENTITY.document_id)
    batch = batching.begin_batch('AAPL')
    state_repo.register_material_upload_preconditions(batch=batch, expected_source_state=old, expected_company_meta=None)
    handle = SourceHandle(ticker='AAPL', document_id=_IDENTITY.document_id, source_kind='material')
    originals = b'original content'
    converted = DoclingDocument(name=_IDENTITY.document_id).model_dump_json().encode()
    entries: list[dict[str, JsonValue]] = []
    for name, data, role in (('original.txt', originals, 'original'), ('original.txt_docling.json', converted, 'docling')):
        asset = blob.store_file(handle, name, BytesIO(data), batch=batch, content_type='application/json' if role == 'docling' else 'text/plain')
        entries.append({'name': name, 'uri': asset.uri, 'size': asset.size, 'sha256': asset.sha256, 'content_type': asset.content_type, 'source': role})
    sha = entries[0]['sha256']
    size = entries[0]['size']
    assert isinstance(sha, str) and type(size) is int
    fingerprint = _build_upload_source_fingerprint(
        [_PendingFileAsset('original.txt', None, None, originals, 'text/plain', sha, size, 'original')],
        source_kind=SourceKind.MATERIAL, primary_original_name='original.txt',
    )
    source.create_source_document(SourceDocumentUpsertRequest(ticker='AAPL', document_id=_IDENTITY.document_id, internal_document_id=_IDENTITY.document_id, form_type='MATERIAL_OTHER', primary_document='original.txt_docling.json', meta={'ingest_method': 'upload', 'source_provider': 'user_upload', 'material_name': 'Deck', 'fiscal_year': None, 'fiscal_period': None, 'amended': amended, 'source_fingerprint': fingerprint.value, 'document_version': _resolve_document_version(None, fingerprint)}, file_entries=entries), SourceKind.MATERIAL, batch=batch)
    return repositories, state_repo.commit_material_upload_batch(batch)


def _bytes(root: Path) -> dict[str, str]:
    """参数：公开测试根；返回：portfolio 完整业务文件摘要；异常：真实读取失败。"""
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (root / 'portfolio').rglob('*') if path.is_file()}


def test_missing_read_is_nonmutating(tmp_path: Path) -> None:
    """参数：不存在仓储根；返回：无；异常：断言失败；只读不创建公司或 source。"""
    root = tmp_path / 'not-created'
    state = FsMaterialUploadStateRepository(root).read_material_upload_state('AAPL', 'm1')
    assert state.source_integrity.status is SourceIntegrityStatus.MISSING
    assert state.source_integrity.revision is None and state.company_meta is None
    assert state.source_meta is None and state.publication_identity is None
    assert not root.exists()


def test_actual_final_and_deep_immutable_meta(tmp_path: Path) -> None:
    """参数：真实根；返回：无；异常：断言失败；actual final 与 inspector 同源且数组/字典不可变。"""
    repositories, final = _publish(tmp_path, amended=True)
    read = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories).read_material_upload_state('AAPL', _IDENTITY.document_id)
    assert final == read and final.source_integrity.status is SourceIntegrityStatus.COMPLETE
    assert final.publication_identity is not None and final.publication_identity.amended is True
    assert final.source_meta is not None and project_material_manifest_item(final.source_meta).amended is True
    files = final.source_meta['files']
    assert isinstance(files, list)
    with pytest.raises(TypeError):
        files.append(None)
    with pytest.raises(TypeError):
        files.clear()
    with pytest.raises(TypeError):
        files.sort(key=str)
    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], files[0])['size'] = 1


def test_metadata_only_preserves_content_and_business_fields(tmp_path: Path) -> None:
    """参数：真实根；返回：无；异常：断言失败；只标记/维护字段变化、内容版及资产保持。"""
    repositories, old = _publish(tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    batch = batching.begin_batch('AAPL')
    state_repo.register_material_upload_preconditions(batch=batch, expected_source_state=old, expected_company_meta=None)
    source.update_material_amended(batch=batch, document_id=_IDENTITY.document_id, amended=True)
    final = state_repo.commit_material_upload_batch(batch)
    assert old.source_meta is not None and final.source_meta is not None
    excluded = {'amended', 'updated_at'}
    assert {key: value for key, value in old.source_meta.items() if key not in excluded} == {key: value for key, value in final.source_meta.items() if key not in excluded}
    assert final.source_integrity.revision != old.source_integrity.revision
    assert final.publication_identity is not None and final.publication_identity.document_version == 'v1'
    assert final.publication_identity.amended is True


def test_registration_and_final_guard_are_owner_checks(tmp_path: Path) -> None:
    """参数：真实根；返回：无；异常：断言失败；源漂移注册拒，commit 前最终 guard 再拒。"""
    repositories, old = _publish(tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    stale = replace(old, publication_identity=replace(old.publication_identity, amended=True) if old.publication_identity is not None else None)
    batch = batching.begin_batch('AAPL')
    with pytest.raises(SourceIntegrityRevisionConflictError):
        state_repo.register_material_upload_preconditions(batch=batch, expected_source_state=stale, expected_company_meta=None)
    batching.rollback_batch(batch)
    before = _bytes(tmp_path)
    batch = batching.begin_batch('AAPL')
    state_repo.register_material_upload_preconditions(batch=batch, expected_source_state=old, expected_company_meta=None)
    # 在 owner 的已登记条件上制造错误期望，只验证真实 final guard，不替换 commit/仓储结果。
    state = repositories.core._resolve_active_batch(batch, 'AAPL')
    state.material_preconditions = (stale, None)
    with pytest.raises(SourceIntegrityRevisionConflictError):
        state_repo.commit_material_upload_batch(batch)
    assert _bytes(tmp_path) == before
    with pytest.raises(ValueError):
        batching.rollback_batch(batch)


def test_company_initial_none_equivalent_noop_and_observed_drift(tmp_path: Path) -> None:
    """参数：真实根；返回：无；异常：断言失败；C01 两分支与业务字节 no-op。"""
    repositories = build_fs_repository_set(workspace_root=tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    company_repo = FsCompanyMetaRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    decision = resolve_upload_company_meta_decision(existing_meta=None, ticker='AAPL', action='create', company_name='Apple Inc.', ticker_aliases=())
    batch = batching.begin_batch('AAPL')
    stage_upload_company_meta_decision(repository=company_repo, decision=decision, batch=batch)
    first = state_repo.commit_material_upload_company_batch(batch).company_meta
    before = _bytes(tmp_path)
    batch = batching.begin_batch('AAPL')
    stage_upload_company_meta_decision(repository=company_repo, decision=decision, batch=batch)
    second = state_repo.commit_material_upload_company_batch(batch).company_meta
    assert first == second and _bytes(tmp_path) == before
    observed = resolve_upload_company_meta_decision(existing_meta=first, ticker='AAPL', action='update', company_name='Different Name', ticker_aliases=())
    assert observed.company_meta_intent is not None
    batch = batching.begin_batch('AAPL')
    stale = replace(observed.company_meta_intent, expected_non_identity=replace(observed.company_meta_intent.expected_non_identity, updated_at='2000-01-01T00:00:00Z') if observed.company_meta_intent.expected_non_identity is not None else None)
    company_repo.stage_company_meta_intent(stale, batch=batch)
    with pytest.raises(CompanyMetaConcurrentUpdateError):
        state_repo.commit_material_upload_company_batch(batch)
    assert _bytes(tmp_path) == before


@pytest.mark.parametrize('field,value', [('company_name', 'Different'), ('resolver_version', 'different')])
def test_initial_none_extra_fields_refused(tmp_path: Path, field: str, value: str) -> None:
    """参数：真实根/字段；返回：无；异常：断言失败；未观察初始历史不用时间猜，当前不等严格拒。"""
    repositories = build_fs_repository_set(workspace_root=tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    company_repo = FsCompanyMetaRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    decision = resolve_upload_company_meta_decision(existing_meta=None, ticker='AAPL', action='create', company_name='Apple Inc.', ticker_aliases=())
    assert decision.company_meta_intent is not None
    altered = replace(decision.company_meta_intent, proposed_company_name=value) if field == 'company_name' else replace(decision.company_meta_intent, resolver_version=value)
    batch = batching.begin_batch('AAPL'); company_repo.stage_company_meta_intent(altered, batch=batch); state_repo.commit_material_upload_company_batch(batch)
    before = _bytes(tmp_path)
    batch = batching.begin_batch('AAPL'); stage_upload_company_meta_decision(repository=company_repo, decision=decision, batch=batch)
    with pytest.raises(CompanyMetaConcurrentUpdateError):
        state_repo.commit_material_upload_company_batch(batch)
    assert _bytes(tmp_path) == before


def test_validate_shared_snapshot_and_required_registration(tmp_path: Path) -> None:
    """参数：真实根；返回：无；异常：断言失败；validator 同版、重复/缺条件与 stage 前类型拒。"""
    repositories, old = _publish(tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repositories)
    assert state_repo.validate_material_upload_state(ticker='AAPL', document_id=_IDENTITY.document_id, expected_source_state=old, expected_company_meta=None) == old
    batch = batching.begin_batch('AAPL')
    assert state_repo.read_material_upload_state_in_batch(batch, _IDENTITY.document_id) == old
    with pytest.raises(ValueError):
        state_repo.commit_material_upload_batch(batch)
    with pytest.raises(ValueError):
        state_repo.commit_material_upload_company_batch(batch)
    with pytest.raises(ValueError):
        source.update_material_amended(batch=batch, document_id=_IDENTITY.document_id, amended=True)
    state_repo.register_material_upload_preconditions(batch=batch, expected_source_state=old, expected_company_meta=None)
    with pytest.raises(ValueError):
        state_repo.register_material_upload_preconditions(batch=batch, expected_source_state=old, expected_company_meta=None)
    with pytest.raises(ValueError):
        source.update_material_amended(batch=batch, document_id='other', amended=True)
    with pytest.raises(ValueError):
        source.update_material_amended(batch=batch, document_id=_IDENTITY.document_id, amended=cast(bool, 1))
    batching.rollback_batch(batch)


@pytest.mark.parametrize('invalid_state', [None, '非法材料状态'])
def test_explicit_none_validates_company_without_missing_source_claim(tmp_path: Path, invalid_state: str | None) -> None:
    """参数：独占根及非法登记值；返回：无；异常：断言失败；只读 None 合法，登记拒非法类型且业务字节不变。"""
    missing = FsMaterialUploadStateRepository(tmp_path).read_material_upload_state('AAPL', _IDENTITY.document_id)
    repositories, complete = _publish(tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    assert state_repo.validate_material_upload_state(ticker='AAPL', document_id=_IDENTITY.document_id, expected_source_state=None, expected_company_meta=None) == complete
    with pytest.raises(SourceIntegrityRevisionConflictError):
        state_repo.validate_material_upload_state(ticker='AAPL', document_id=_IDENTITY.document_id, expected_source_state=missing, expected_company_meta=None)
    before = _bytes(tmp_path)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    batch = batching.begin_batch('AAPL')
    try:
        # 仅故意突破静态类型，验证直接输入 owner 拒绝任何非完整状态类型。
        with pytest.raises(TypeError, match='expected_source_state 必须是 MaterialUploadPublishedState 类型的完整材料状态'):
            state_repo.register_material_upload_preconditions(batch=batch, expected_source_state=cast(MaterialUploadPublishedState, invalid_state), expected_company_meta=None)
        with pytest.raises(ValueError, match='材料提交必须已登记条件且不混入公司 intent'):
            state_repo.commit_material_upload_batch(batch)
    finally:
        batching.rollback_batch(batch)
    assert _bytes(tmp_path) == before


@pytest.mark.parametrize('changed', ['company_name', 'updated_at', 'resolver_version', 'aliases', 'missing'])
def test_company_only_guard_keeps_exact_observed_snapshot(tmp_path: Path, changed: str) -> None:
    """参数：真实根与快照差异；返回：无；异常：断言失败；None 源条件不放宽公司全快照。"""
    repositories, _ = _publish(tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    company_repo = FsCompanyMetaRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    decision = resolve_upload_company_meta_decision(existing_meta=None, ticker='AAPL', action='create', company_name='Apple Inc.', ticker_aliases=())
    batch = batching.begin_batch('AAPL')
    stage_upload_company_meta_decision(repository=company_repo, decision=decision, batch=batch)
    company = state_repo.commit_material_upload_company_batch(batch).company_meta
    assert company is not None
    expected: CompanyMeta | None = company
    if changed == 'missing':
        expected = None
    elif changed == 'company_name':
        expected = replace(company, company_name='Other')
    elif changed == 'updated_at':
        expected = replace(company, updated_at='2000-01-01T00:00:00Z')
    elif changed == 'resolver_version':
        expected = replace(company, resolver_version='Other')
    else:
        expected = replace(company, ticker_identity=replace(company.ticker_identity, accepted_aliases=('FREE',)))
    before = _bytes(tmp_path)
    with pytest.raises(CompanyMetaConcurrentUpdateError):
        state_repo.validate_material_upload_state(ticker='AAPL', document_id=_IDENTITY.document_id, expected_source_state=None, expected_company_meta=expected)
    assert _bytes(tmp_path) == before


def test_company_only_guard_alias_owner_precedes_snapshot(tmp_path: Path) -> None:
    """参数：真实根；返回：无；异常：断言失败；公司 only 条件仍由真实 alias owner 优先拒绝。"""
    repositories, _ = _publish(tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    company_repo = FsCompanyMetaRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    companies: list[CompanyMeta] = []
    for ticker, aliases in [('AAPL', ()), ('GOOG', ('TAKEN',))]:
        decision = resolve_upload_company_meta_decision(existing_meta=None, ticker=ticker, action='create', company_name=ticker, ticker_aliases=aliases)
        batch = batching.begin_batch(ticker)
        stage_upload_company_meta_decision(repository=company_repo, decision=decision, batch=batch)
        company = state_repo.commit_material_upload_company_batch(batch).company_meta
        assert company is not None
        companies.append(company)
    expected = replace(companies[0], ticker_identity=replace(companies[0].ticker_identity, accepted_aliases=('TAKEN',)))
    with pytest.raises(CompanyTickerAliasConflictError):
        state_repo.validate_material_upload_state(ticker='AAPL', document_id=_IDENTITY.document_id, expected_source_state=None, expected_company_meta=expected)


def test_no_staged_document_cannot_become_committed(tmp_path: Path) -> None:
    """参数：真实 fresh 根；返回：无；异常：断言失败；staged 目录不是材料成功事实。"""
    repositories = build_fs_repository_set(workspace_root=tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    old = state_repo.read_material_upload_state('AAPL', 'empty')
    before = _bytes(tmp_path)
    batch = batching.begin_batch('AAPL')
    state_repo.register_material_upload_preconditions(batch=batch, expected_source_state=old, expected_company_meta=None)
    with pytest.raises(RuntimeError, match='未完成目标'):
        state_repo.commit_material_upload_batch(batch)
    assert _bytes(tmp_path) == before
    assert state_repo.read_material_upload_state('AAPL', 'empty') == old


@pytest.mark.parametrize('damage', ['amended_missing', 'amended_nonbool', 'original_missing', 'manifest_missing'])
def test_strict_actual_damage_never_becomes_missing(tmp_path: Path, damage: str) -> None:
    """参数：真实根/单项损坏；返回：无；异常：断言失败；实际损坏分类与 opaque revision，不能 raw None 猜 missing。"""
    repositories, old = _publish(tmp_path)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repositories)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    locator = source.get_source_document_locator('AAPL', _IDENTITY.document_id, SourceKind.MATERIAL)
    directory = tmp_path / locator
    if damage.startswith('amended'):
        meta = json.loads((directory / 'meta.json').read_text())
        if damage == 'amended_missing':
            del meta['amended']
        else:
            meta['amended'] = 'false'
        (directory / 'meta.json').write_text(json.dumps(meta))
    elif damage == 'original_missing':
        (directory / 'original.txt').unlink()
    else:
        (directory.parent / 'material_manifest.json').unlink()
    fresh = state_repo.read_material_upload_state('AAPL', _IDENTITY.document_id)
    expected = SourceIntegrityStatus.UNSAFE if damage.startswith('amended') else SourceIntegrityStatus.REPAIR_REQUIRED
    assert fresh.source_integrity.status is expected
    assert fresh.publication_identity is None
    assert fresh.source_integrity.revision == (None if expected is SourceIntegrityStatus.UNSAFE else old.source_integrity.revision)
    with pytest.raises(SourceIntegrityRevisionConflictError):
        state_repo.validate_material_upload_state(ticker='AAPL', document_id=_IDENTITY.document_id, expected_source_state=old, expected_company_meta=None)


class _PostCommitReleaseFault:
    """仅在本测试真实 COMMITTED 后原锁释放成功处注入 operational 失败。"""

    def __init__(self, core: FsStorageCore, state: _ActiveBatchState) -> None:
        """参数：真实 core/活动 batch；返回：无；异常：无。"""
        self.original = core._release_lock_token
        self.state = state
        self.fired = False

    def __call__(self, token: RuntimeFileLockToken) -> None:
        """参数：真实锁；返回：原释放结果；异常：一次真实 COMMITTED 后注入释放错误。"""
        self.original(token)
        if self.state.phase == _PHASE_COMMITTED and not self.fired:
            self.fired = True
            raise OSError('injected post-COMMITTED release error')


def test_typed_commit_release_failure_keeps_durable_fact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：真实根/故障注入；返回：无；异常：断言失败；release failed 不 rollback/retry/readback-skip。"""
    repositories, old = _publish(tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    batch = batching.begin_batch('AAPL')
    state_repo.register_material_upload_preconditions(batch=batch, expected_source_state=old, expected_company_meta=None)
    source.update_material_amended(batch=batch, document_id=_IDENTITY.document_id, amended=True)
    state = repositories.core._resolve_active_batch(batch, 'AAPL')
    fault = _PostCommitReleaseFault(repositories.core, state)
    monkeypatch.setattr(repositories.core, '_release_lock_token', fault)
    with pytest.raises(OSError, match='post-COMMITTED'):
        state_repo.commit_material_upload_batch(batch)
    assert fault.fired and state.phase == _PHASE_COMMITTED
    with pytest.raises(ValueError):
        batching.rollback_batch(batch)
    final = state_repo.read_material_upload_state('AAPL', _IDENTITY.document_id)
    assert final.publication_identity is not None and final.publication_identity.amended is True
    assert final == state.material_final



def test_company_alias_conflict_precedes_observed_snapshot_conflict(tmp_path: Path) -> None:
    """参数：真实根；返回：无；异常：断言失败；原 alias owner 在材料公司 merge 前裁冲突，filing 规则不改。"""
    repositories = build_fs_repository_set(workspace_root=tmp_path)
    state_repo = FsMaterialUploadStateRepository(tmp_path, repository_set=repositories)
    company_repo = FsCompanyMetaRepository(tmp_path, repository_set=repositories)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    initial = resolve_upload_company_meta_decision(existing_meta=None, ticker='AAPL', action='create', company_name='Apple Inc.', ticker_aliases=())
    batch = batching.begin_batch('AAPL'); stage_upload_company_meta_decision(repository=company_repo, decision=initial, batch=batch)
    first = state_repo.commit_material_upload_company_batch(batch).company_meta
    accepted = resolve_upload_company_meta_decision(existing_meta=first, ticker='AAPL', action='update', company_name=None, ticker_aliases=('CONFLICT',))
    assert accepted.company_meta_intent is not None and accepted.company_meta_intent.expected_non_identity is not None
    competing = resolve_upload_company_meta_decision(existing_meta=None, ticker='GOOG', action='create', company_name='Google Inc.', ticker_aliases=('CONFLICT',))
    batch = batching.begin_batch('GOOG'); stage_upload_company_meta_decision(repository=company_repo, decision=competing, batch=batch); state_repo.commit_material_upload_company_batch(batch)
    before = _bytes(tmp_path)
    batch = batching.begin_batch('AAPL')
    stale = replace(accepted.company_meta_intent, expected_non_identity=replace(accepted.company_meta_intent.expected_non_identity, updated_at='2000-01-01T00:00:00Z'))
    company_repo.stage_company_meta_intent(stale, batch=batch)
    with pytest.raises(CompanyTickerAliasConflictError):
        state_repo.commit_material_upload_company_batch(batch)
    assert _bytes(tmp_path) == before
