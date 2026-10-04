"""材料状态受理、公司独立阶段与实际 final 的 owner 级真实 Fs 验证。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    ValidatedFinsUploadMaterialRequest,
    FinsUploadMaterialRequest,
    FinsUploadPipelineResult,
    admit_fins_upload_material_request,
)
from dayu.fins.pipelines.docling_process_converter import DoclingConversionConfig, DoclingConversionResult
from dayu.fins.pipelines.docling_upload_service import DoclingUploadService, PreparedDoclingUpload, describe_prepared_material_publication, UploadOperationResult, _PreparedDeleteMutation
from dayu.fins.pipelines.material_upload_publication import (
    MaterialUploadPublicationDecision,
    MaterialUploadPublicationDisposition,
    arbitrate_material_upload_publication,
    execute_material_upload_company_stage,
    execute_prepared_material_publication,
)
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.storage import FsMaterialUploadStateRepository
from dayu.fins.storage.source_integrity import SourceIntegrityStatus
from dayu.fins.pipelines.upload_company_meta import (
    resolve_upload_company_meta_decision,
    stage_upload_company_meta_decision,
)
from dayu.fins.domain.document_models import CompanyMeta, BatchToken
from dayu.fins.storage import MaterialUploadPublishedState
from dayu.fins.storage._fs_storage_infra import _PHASE_COMMITTED
from tests.fins.test_material_upload_state_repository import _PostCommitReleaseFault
from dayu.fins.tools.read_runtime import _parse_source_document_meta
from dayu.fins.upload_failure import FinsUploadFailureError, FinsUploadPrevalidationError
from dayu.fins.upload_repair_contract import NoExistingSourceRepair
from dayu.fins.upload_usage_contract import FinsUploadUsageError


class _CountingConverter:
    """确定性矩阵只注入转换次数；所有状态、提交和资产存储均为真实 Fs。"""

    def __init__(self) -> None:
        """参数：无；返回：无；异常：无。"""
        self.calls: list[str] = []

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """参数：实际原件及配置/取消；返回：确定性派生物；异常：无。"""
        del config, cancellation
        self.calls.append(stream_name)
        data = b'{"probe": "' + hashlib.sha256(input_bytes).hexdigest().encode() + b'"}'
        return DoclingConversionResult(data, len(data), hashlib.sha256(data).hexdigest())


def _pipeline(root: Path) -> tuple[DefaultFinsRuntime, SecPipeline, _CountingConverter]:
    """参数：独占根；返回：同组仓储、pipeline 与计数器；异常：装配或 I/O。"""
    runtime = DefaultFinsRuntime.create(workspace_root=root)
    converter = _CountingConverter()
    pipeline = SecPipeline(
        workspace_root=root,
        processor_registry=build_fins_processor_registry(),
        material_upload_state_repository=runtime.material_upload_state_repository,
        batching_repository=runtime.batching_repository,
        company_repository=runtime.company_repository,
        source_repository=runtime.source_repository,
        blob_repository=runtime.blob_repository,
        processed_repository=runtime.processed_repository,
        filing_maintenance_repository=runtime.filing_maintenance_repository,
        filing_upload_state_repository=runtime.filing_upload_state_repository,
        docling_converter=converter,
    )
    return runtime, pipeline, converter


def _request(
    root: Path, *, action: str = "auto", amended: bool = False, overwrite: bool = False
) -> FinsUploadMaterialRequest:
    """参数：独占原件与动作/标记；返回：完整请求；异常：无。"""
    return FinsUploadMaterialRequest(
        ticker="AAPL",
        action=action,
        files=() if action == "delete" else (root / "probe.txt",),
        form_type="MATERIAL_OTHER",
        material_name="Owner Probe",
        company_name="Apple Inc.",
        amended=amended,
        overwrite=overwrite,
    )


def _bytes(root: Path) -> dict[str, bytes]:
    """参数：业务仓储根；返回：exact 文件字节；异常：I/O；不以 inode/mtime 判 no-op。"""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".lock" not in path.name and "logs" not in path.parts
    }


@pytest.mark.parametrize("same_bytes", [True, False])
@pytest.mark.parametrize("same_flag", [True, False])
@pytest.mark.parametrize("overwrite", [True, False])
def test_eight_amended_cells(tmp_path: Path, same_bytes: bool, same_flag: bool, overwrite: bool) -> None:
    """参数：八格输入与根；返回：无；异常：断言失败；真实 Fs status/version/次数/metadata 保全。"""
    runtime, pipeline, converter = _pipeline(tmp_path)
    file = tmp_path / "probe.txt"
    file.write_text("first content")
    first = pipeline.upload_material(_request(tmp_path))
    assert first["status"] == "ok" and first["published_amended"] is False
    identifier = first["document_id"]
    assert isinstance(identifier, str)
    before = runtime.material_upload_state_repository.read_material_upload_state("AAPL", identifier)
    assert before.source_meta is not None
    converter.calls.clear()
    if not same_bytes:
        file.write_text("second content")
    result = pipeline.upload_material(_request(tmp_path, amended=not same_flag, overwrite=overwrite))
    expected = (
        "skipped"
        if same_bytes and same_flag and not overwrite
        else "metadata_updated" if same_bytes and not same_flag and not overwrite else "ok"
    )
    assert result["status"] == expected and result["published_amended"] is (not same_flag)
    assert len(converter.calls) == (0 if expected in {"skipped", "metadata_updated"} else 1)
    after = runtime.material_upload_state_repository.read_material_upload_state("AAPL", identifier)
    assert (
        after.publication_identity is not None
        and before.publication_identity is not None
        and after.source_meta is not None
    )
    assert after.publication_identity.document_version == ("v1" if same_bytes else "v2")
    assert after.source_meta["first_ingested_at"] == before.source_meta["first_ingested_at"]
    if expected == "metadata_updated":
        ignored = {"amended", "updated_at"}
        assert {k: v for k, v in before.source_meta.items() if k not in ignored} == {
            k: v for k, v in after.source_meta.items() if k not in ignored
        }
    if expected == "skipped":
        assert after == before
    runtime.close()


@pytest.mark.parametrize(
    "action,overwrite,code",
    [
        ("update", False, "update_target_missing"),
        ("update", True, "update_target_missing"),
        ("delete", False, "delete_target_missing"),
    ],
)
def test_missing_target_precedes_company_and_writes(tmp_path: Path, action: str, overwrite: bool, code: str) -> None:
    """参数：缺目标的动作/覆盖；返回：无；异常：断言失败；目标错误先于公司名称且零业务写。"""
    state = FsMaterialUploadStateRepository(tmp_path)
    raw = replace(_request(tmp_path, action=action, overwrite=overwrite), company_name=None)
    before = _bytes(tmp_path)
    with pytest.raises(FinsUploadUsageError) as raised:
        admit_fins_upload_material_request(raw, state_repository=state)
    assert raised.value.failure.code.value == code and _bytes(tmp_path) == before


@pytest.mark.parametrize("changed", [False, True])
def test_active_create_rejects_before_company(tmp_path: Path, changed: bool) -> None:
    """参数：同/异字节；返回：无；异常：断言失败；activecreate 无覆盖均前置拒。"""
    runtime, pipeline, _ = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    assert pipeline.upload_material(_request(tmp_path))["status"] == "ok"
    if changed:
        (tmp_path / "probe.txt").write_text("second")
    before = _bytes(tmp_path)
    with pytest.raises(FinsUploadUsageError) as raised:
        admit_fins_upload_material_request(
            replace(_request(tmp_path, action="create"), company_name=None),
            state_repository=runtime.material_upload_state_repository,
        )
    assert raised.value.failure.code.value == "create_target_exists" and _bytes(tmp_path) == before
    runtime.close()


def test_delete_actual_flag_noop_and_restore(tmp_path: Path) -> None:
    """参数：独占根；返回：无；异常：断言失败；删标记来自 final，重删零差异，恢复保首次时间/同指纹版本。"""
    runtime, pipeline, converter = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    first = pipeline.upload_material(_request(tmp_path, amended=True))
    identifier = first["document_id"]
    assert isinstance(identifier, str)
    initial = runtime.material_upload_state_repository.read_material_upload_state("AAPL", identifier)
    deleted = pipeline.upload_material(_request(tmp_path, action="delete"))
    assert deleted["status"] == "deleted" and deleted["published_amended"] is True
    snapshot = runtime.material_upload_state_repository.read_material_upload_state("AAPL", identifier)
    before = _bytes(tmp_path)
    assert pipeline.upload_material(_request(tmp_path, action="delete"))["published_amended"] is True
    assert (
        _bytes(tmp_path) == before
        and runtime.material_upload_state_repository.read_material_upload_state("AAPL", identifier) == snapshot
    )
    converter.calls.clear()
    restored = pipeline.upload_material(_request(tmp_path, action="update", amended=True))
    assert restored["status"] == "ok" and converter.calls == ["probe.txt"]
    after = runtime.material_upload_state_repository.read_material_upload_state("AAPL", identifier)
    assert initial.source_meta is not None and after.source_meta is not None
    assert (
        after.source_meta["first_ingested_at"] == initial.source_meta["first_ingested_at"]
        and after.source_meta["document_version"] == initial.source_meta["document_version"]
    )
    runtime.close()


def test_old_admission_winner_actual_final_then_identical_skip(tmp_path: Path) -> None:
    """参数：独占根；返回：无；异常：断言失败；两 old MISSING，正常公司 no-op 和同次 final，无 postcommitreadback。"""
    runtime, pipeline, converter = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    raw = _request(tmp_path)
    a = admit_fins_upload_material_request(raw, state_repository=runtime.material_upload_state_repository)
    b = admit_fins_upload_material_request(raw, state_repository=runtime.material_upload_state_repository)
    assert a.state_admission.observed_state.source_integrity.status is SourceIntegrityStatus.MISSING
    winner = pipeline.upload_material_validated(a)
    assert winner["status"] == "ok"
    before = _bytes(tmp_path)
    loser = pipeline.upload_material_validated(b)
    assert loser["status"] == "skipped" and _bytes(tmp_path) == before
    final = runtime.material_upload_state_repository.read_material_upload_state("AAPL", a.identity.document_id)
    assert final.publication_identity is not None
    decision = arbitrate_material_upload_publication(
        request=b, fresh_state=final, candidate=final.publication_identity, expected_company_meta=final.company_meta
    )
    assert decision.disposition is MaterialUploadPublicationDisposition.IDENTICAL_SKIP
    for changed in (
        replace(final.publication_identity, amended=True),
        replace(final.publication_identity, primary_document="different_docling.json"),
    ):
        assert (
            arbitrate_material_upload_publication(
                request=b, fresh_state=final, candidate=changed, expected_company_meta=final.company_meta
            ).disposition
            is MaterialUploadPublicationDisposition.CONFLICT
        )
    assert (
        arbitrate_material_upload_publication(
            request=replace(b, request=replace(raw, overwrite=True)),
            fresh_state=final,
            candidate=final.publication_identity,
            expected_company_meta=final.company_meta,
        ).disposition
        is MaterialUploadPublicationDisposition.CONFLICT
    )
    with pytest.raises(ValueError):
        MaterialUploadPublicationDecision(MaterialUploadPublicationDisposition.CONFLICT, None)
    runtime.close()


@pytest.mark.asyncio
async def test_company_survives_prepare_failure_and_actual_final_identity(tmp_path: Path) -> None:
    """参数：独占根；返回：无；异常：断言失败；公司独立 final 保留，材料 result/outcome 引用同次状态。"""
    runtime, _, converter = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    request = admit_fins_upload_material_request(
        _request(tmp_path), state_repository=runtime.material_upload_state_repository
    )
    company = execute_material_upload_company_stage(
        request=request,
        state_repository=runtime.material_upload_state_repository,
        company_repository=runtime.company_repository,
        batching_repository=runtime.batching_repository,
        cancellation=None,
    )
    service = DoclingUploadService(
        source_repository=runtime.source_repository,
        blob_repository=runtime.blob_repository,
        docling_converter=converter,
    )
    identity = request.identity
    prepared = await service.prepare_upload(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id=identity.document_id,
        internal_document_id=identity.internal_document_id,
        form_type=identity.form_type,
        selection=request.asset_plan,
        overwrite=False,
        previous_meta=None,
        meta={
            "ingest_method": "upload",
            "material_name": identity.material_name,
            "amended": False,
            "fiscal_year": None,
            "fiscal_period": None,
        },
        repair_disposition=NoExistingSourceRepair(),
        cancellation=None,
    )
    outcome = execute_prepared_material_publication(
        request=request,
        prepared=prepared,
        expected_company_meta=company,
        state_repository=runtime.material_upload_state_repository,
        batching_repository=runtime.batching_repository,
        upload_service=service,
        cancellation=None,
    )
    assert (
        outcome.published_state is outcome.result.material_published_state and outcome.result.published_amended is False
    )
    assert outcome.published_state is not None and outcome.published_state.company_meta == company
    old = outcome.published_state
    assert old.publication_identity is not None
    assert runtime.material_upload_state_repository.read_material_upload_state("AAPL", identity.document_id) == old
    runtime.close()


@pytest.mark.parametrize("status", ["ok", "skipped", "deleted", "metadata_updated"])
def test_material_pipeline_result_requires_actual_bool(status: str) -> None:
    """参数：材料正常状态；返回：无；异常：断言失败；严格 bool 与 filing 状态隔离。"""
    count = 1 if status == "ok" else 0
    with pytest.raises(ValueError):
        FinsUploadPipelineResult(
            source_kind=SourceKind.MATERIAL, published_amended=None, status=status, stored_file_count=count
        )
    assert (
        FinsUploadPipelineResult(
            source_kind=SourceKind.MATERIAL, published_amended=True, status=status, stored_file_count=count
        ).published_amended
        is True
    )
    if status == "metadata_updated":
        with pytest.raises(ValueError):
            FinsUploadPipelineResult(
                source_kind=SourceKind.FILING, published_amended=None, status=status, stored_file_count=0
            )


def seed_material_upload_target(request: FinsUploadMaterialRequest, workspace_root: Path) -> FinsUploadMaterialRequest:
    """参数：旧测试要消费的删除请求与独占根；返回：原请求；异常：真实 owner 发布失败；显式构造完整 existing target，不伪造 state。"""
    if request.action != "delete":
        return request
    runtime, pipeline, converter = _pipeline(workspace_root)
    if normalize_ticker(request.ticker).market != "US":
        pipeline = CnPipeline(
            workspace_root=workspace_root,
            docling_converter=converter,
            material_upload_state_repository=runtime.material_upload_state_repository,
            batching_repository=runtime.batching_repository,
            company_repository=runtime.company_repository,
            source_repository=runtime.source_repository,
            blob_repository=runtime.blob_repository,
            processed_repository=runtime.processed_repository,
            filing_maintenance_repository=runtime.filing_maintenance_repository,
            filing_upload_state_repository=runtime.filing_upload_state_repository,
        )
    workspace_root.mkdir(parents=True, exist_ok=True)
    sample = workspace_root / "seed-target.txt"
    sample.write_text("Existing target fixture")
    create = replace(request, action="auto", files=(sample,), primary_selectors=(), company_name="Apple Inc.")
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(pipeline.upload_material, create).result(timeout=10)["status"] == "ok"
    runtime.close()
    return request


async def _prepare_admitted(
    runtime: DefaultFinsRuntime, request: ValidatedFinsUploadMaterialRequest, converter: _CountingConverter
) -> tuple[DoclingUploadService, PreparedDoclingUpload, CompanyMeta | None]:
    """参数：真实受理与同组运行时；返回：独立公司 final、准备和服务；异常：owner 真实失败。"""
    company = execute_material_upload_company_stage(
        request=request,
        state_repository=runtime.material_upload_state_repository,
        company_repository=runtime.company_repository,
        batching_repository=runtime.batching_repository,
        cancellation=None,
    )
    service = DoclingUploadService(
        source_repository=runtime.source_repository,
        blob_repository=runtime.blob_repository,
        docling_converter=converter,
    )
    identity = request.identity
    prepared = await service.prepare_upload(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action=request.state_admission.resolved_action,
        document_id=identity.document_id,
        internal_document_id=identity.internal_document_id,
        form_type=identity.form_type,
        selection=request.asset_plan,
        overwrite=request.request.overwrite,
        previous_meta=request.state_admission.observed_state.source_meta,
        meta={
            "ingest_method": "upload",
            "material_name": identity.material_name,
            "amended": request.request.amended,
            "fiscal_year": identity.fiscal_year,
            "fiscal_period": identity.fiscal_period,
        },
        repair_disposition=NoExistingSourceRepair(),
        cancellation=None,
    )
    return service, prepared, company


@pytest.mark.parametrize("candidate_kind", ["content", "metadata", "skip"])
@pytest.mark.asyncio
async def test_unordered_multifile_real_candidate_and_input_events(tmp_path: Path, candidate_kind: str) -> None:
    """参数：独占根与三种真实 D 候选；返回：无；异常：断言失败；规范身份与输入事件顺序分离。"""
    runtime, pipeline, converter = _pipeline(tmp_path)
    b, a = tmp_path / "b.txt", tmp_path / "a.txt"
    b.write_text("companion content")
    a.write_text("primary content")
    raw = replace(_request(tmp_path), files=(b, a), primary_selectors=(a,))
    if candidate_kind != "content":
        with ThreadPoolExecutor(max_workers=1) as executor:
            assert executor.submit(pipeline.upload_material, raw).result(timeout=10)["status"] == "ok"
    desired = replace(raw, amended=candidate_kind == "metadata")
    winner_request = admit_fins_upload_material_request(desired, state_repository=runtime.material_upload_state_repository)
    loser_request = admit_fins_upload_material_request(desired, state_repository=runtime.material_upload_state_repository)
    assert winner_request.state_admission.observed_state == loser_request.state_admission.observed_state
    assert winner_request.request.files == (b, a) and winner_request.asset_plan.primary_original_name == "a.txt"
    if candidate_kind == "content":
        assert winner_request.state_admission.observed_state.source_integrity.status is SourceIntegrityStatus.MISSING
    service, prepared, company = await _prepare_admitted(runtime, loser_request, converter)
    assert not isinstance(prepared, (UploadOperationResult, _PreparedDeleteMutation))
    candidate = describe_prepared_material_publication(prepared)
    assert [item.name for item in candidate.originals] == ["a.txt", "b.txt"]
    assert candidate.primary_document == "a.txt_docling.json"
    with ThreadPoolExecutor(max_workers=1) as executor:
        winner = executor.submit(pipeline.upload_material_validated, winner_request).result(timeout=10)
    assert winner["status"] == {"content": "ok", "metadata": "metadata_updated", "skip": "skipped"}[candidate_kind]
    final = runtime.material_upload_state_repository.read_material_upload_state("AAPL", loser_request.identity.document_id)
    assert final.publication_identity == candidate and final.company_meta == company
    before = _bytes(tmp_path)
    outcome = execute_prepared_material_publication(
        request=loser_request, prepared=prepared, expected_company_meta=company,
        state_repository=runtime.material_upload_state_repository,
        batching_repository=runtime.batching_repository, upload_service=service, cancellation=None,
    )
    assert outcome.result.status == "skipped"
    assert [event.name for event in outcome.result.file_events] == ["b.txt", "a.txt"]
    assert _bytes(tmp_path) == before and outcome.published_state == final
    assert runtime.material_upload_state_repository.read_material_upload_state("AAPL", loser_request.identity.document_id) == final
    # 普通请求仍按原输入发出文件事件，不消费身份 tuple 的规范顺序。
    events = [event async for event in pipeline.upload_material_stream(desired)]
    assert [event.payload["name"] for event in events if event.event_type == "file_skipped"] == ["b.txt", "a.txt"]
    assert _bytes(tmp_path) == before
    runtime.close()


@pytest.mark.parametrize("difference", ["primary", "content", "amended"])
@pytest.mark.asyncio
async def test_multifile_different_real_candidate_remains_conflict(tmp_path: Path, difference: str) -> None:
    """参数：真实输入差异；返回：无；异常：断言失败；不同主源/角色指纹、内容或标记不可 skip。"""
    runtime, pipeline, converter = _pipeline(tmp_path)
    b, a = tmp_path / "b.txt", tmp_path / "a.txt"
    b.write_text("companion")
    a.write_text("primary")
    raw = replace(_request(tmp_path), files=(b, a), primary_selectors=(a,))
    loser = admit_fins_upload_material_request(raw, state_repository=runtime.material_upload_state_repository)
    altered = replace(raw, primary_selectors=(b,)) if difference == "primary" else replace(raw, amended=True) if difference == "amended" else raw
    if difference == "content":
        b.write_text("different companion")
    altered_request = admit_fins_upload_material_request(altered, state_repository=runtime.material_upload_state_repository)
    service, prepared, company = await _prepare_admitted(runtime, altered_request, converter)
    if difference == "content":
        b.write_text("companion")
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(pipeline.upload_material_validated, loser).result(timeout=10)["status"] == "ok"
    before = _bytes(tmp_path)
    with pytest.raises(FinsUploadFailureError) as raised:
        execute_prepared_material_publication(
            request=altered_request, prepared=prepared, expected_company_meta=company,
            state_repository=runtime.material_upload_state_repository,
            batching_repository=runtime.batching_repository, upload_service=service, cancellation=None,
        )
    assert raised.value.failure.code.value == "source_publication_conflict" and _bytes(tmp_path) == before
    runtime.close()


@pytest.mark.asyncio
async def test_create_on_tombstone_keeps_storage_rejection(tmp_path: Path) -> None:
    """参数：真实根；返回：无；异常：断言失败；非覆盖 create 保现仓储拒绝且不自动恢复。"""
    runtime, pipeline, converter = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(pipeline.upload_material, _request(tmp_path)).result(timeout=10)["status"] == "ok"
        assert executor.submit(pipeline.upload_material, _request(tmp_path, action="delete")).result(timeout=10)["status"] == "deleted"
    before = _bytes(tmp_path)
    admitted = admit_fins_upload_material_request(_request(tmp_path, action="create"), state_repository=runtime.material_upload_state_repository)
    assert admitted.state_admission.observed_state.publication_identity is not None
    assert admitted.state_admission.observed_state.publication_identity.is_deleted
    service, prepared, company = await _prepare_admitted(runtime, admitted, converter)
    with pytest.raises(FileExistsError):
        execute_prepared_material_publication(
            request=admitted, prepared=prepared, expected_company_meta=company,
            state_repository=runtime.material_upload_state_repository,
            batching_repository=runtime.batching_repository, upload_service=service, cancellation=None,
        )
    assert _bytes(tmp_path) == before
    runtime.close()


@pytest.mark.parametrize("candidate_kind", ["delete", "content", "metadata", "skip"])
@pytest.mark.parametrize("drift", ["source", "company"])
@pytest.mark.asyncio
async def test_writer_rejects_after_prepare_competing_commit(tmp_path: Path, candidate_kind: str, drift: str) -> None:
    """参数：四种候选和两种漂移；返回：无；异常：断言失败；B 在 A begin 前提交，不持 A writer 等 B。"""
    runtime, pipeline, converter = _pipeline(tmp_path)
    original = tmp_path / "probe.txt"
    original.write_text("first")
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(pipeline.upload_material, _request(tmp_path)).result(timeout=10)["status"] == "ok"
    if candidate_kind == "content":
        original.write_text("second")
    raw = _request(
        tmp_path,
        action="delete" if candidate_kind == "delete" else "auto" if candidate_kind == "skip" else "update",
        amended=candidate_kind == "metadata",
    )
    admitted = admit_fins_upload_material_request(raw, state_repository=runtime.material_upload_state_repository)
    service, prepared, company = await _prepare_admitted(runtime, admitted, converter)
    if drift == "source":
        original.write_text("competing third")
        with ThreadPoolExecutor(max_workers=1) as executor:
            assert (
                executor.submit(pipeline.upload_material, _request(tmp_path, action="update", amended=True)).result(
                    timeout=10
                )["status"]
                == "ok"
            )
    else:
        decision = resolve_upload_company_meta_decision(
            existing_meta=company, ticker="AAPL", action="update", company_name=None, ticker_aliases=("MSFT",)
        )
        batch = runtime.batching_repository.begin_batch("AAPL")
        stage_upload_company_meta_decision(repository=runtime.company_repository, decision=decision, batch=batch)
        assert (
            runtime.material_upload_state_repository.commit_material_upload_company_batch(batch).company_meta != company
        )
    before = _bytes(tmp_path)
    with pytest.raises(FinsUploadFailureError) as raised:
        execute_prepared_material_publication(
            request=admitted,
            prepared=prepared,
            expected_company_meta=company,
            state_repository=runtime.material_upload_state_repository,
            batching_repository=runtime.batching_repository,
            upload_service=service,
            cancellation=None,
        )
    assert raised.value.failure.code.value == "source_publication_conflict"
    assert _bytes(tmp_path) == before
    runtime.close()


@pytest.mark.parametrize("phase", ["begin", "read", "commit"])
@pytest.mark.asyncio
async def test_operational_executor_failure_is_never_reinterpreted(tmp_path: Path, phase: str) -> None:
    """参数：真实生命周期故障位置；返回：无；异常：断言失败；原 I/O 原样传播，零成功/跳过及零材料发布。"""
    runtime, _, converter = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    admitted = admit_fins_upload_material_request(
        _request(tmp_path), state_repository=runtime.material_upload_state_repository
    )
    service, prepared, company = await _prepare_admitted(runtime, admitted, converter)
    before = _bytes(tmp_path)
    target = runtime.batching_repository if phase == "begin" else runtime.material_upload_state_repository
    method = (
        "begin_batch"
        if phase == "begin"
        else "read_material_upload_state_in_batch" if phase == "read" else "commit_material_upload_batch"
    )
    error = OSError("actual injected I/O")
    if phase == "commit":
        # commit owner 必须完成关闭：在其真实 swap 位置注入，而非伪造未关闭的 commit 返回。
        from dayu.fins.storage._fs_storage_core import FsStorageCore

        with patch.object(FsStorageCore, "_replace_directory", side_effect=error):
            with pytest.raises(OSError) as raised:
                execute_prepared_material_publication(
                    request=admitted,
                    prepared=prepared,
                    expected_company_meta=company,
                    state_repository=runtime.material_upload_state_repository,
                    batching_repository=runtime.batching_repository,
                    upload_service=service,
                    cancellation=None,
                )
    else:
        with patch.object(target, method, side_effect=error):
            with pytest.raises(OSError) as raised:
                execute_prepared_material_publication(
                    request=admitted,
                    prepared=prepared,
                    expected_company_meta=company,
                    state_repository=runtime.material_upload_state_repository,
                    batching_repository=runtime.batching_repository,
                    upload_service=service,
                    cancellation=None,
                )
    assert raised.value is error and _bytes(tmp_path) == before
    runtime.close()


def test_list_marker_and_recommendations_share_actual_metadata(tmp_path: Path) -> None:
    """参数：真实仓储根；返回：无；异常：断言失败；true/false 不过滤，metadata-only 同 ID 的公开标记与推荐引用一致。"""
    runtime, pipeline, _ = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    a = pipeline.upload_material(_request(tmp_path, amended=True))
    b = pipeline.upload_material(replace(_request(tmp_path), material_name="Second identity"))
    assert a["status"] == b["status"] == "ok"
    listed = runtime.get_read_runtime().list_documents(ticker="AAPL")
    documents = {row["document_id"]: row for row in listed["documents"]}
    assert (
        documents[a["document_id"]]["published_amended"] is True
        and documents[b["document_id"]]["published_amended"] is False
    )
    assert all("amended" not in row for row in documents.values())
    assert all(value is None or value in documents for value in listed["recommended_documents"].values())
    changed = pipeline.upload_material(_request(tmp_path, amended=False))
    assert changed["status"] == "metadata_updated" and changed["document_id"] == a["document_id"]
    refreshed = runtime.get_read_runtime().list_documents(ticker="AAPL")
    assert (
        next(row for row in refreshed["documents"] if row["document_id"] == a["document_id"])["published_amended"]
        is False
    )
    assert all(value is None or value in documents for value in refreshed["recommended_documents"].values())
    runtime.close()


@pytest.mark.parametrize("damage", ["original_missing", "docling_missing", "manifest_missing", "digest_same_length"])
@pytest.mark.asyncio
async def test_old_missing_admission_cannot_skip_damaged_winner(tmp_path: Path, damage: str) -> None:
    """参数：真实 winner 的四类损坏；返回：无；异常：断言失败；损坏 state 不获得 verifiedskip，无材料补写。"""
    runtime, pipeline, converter = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    admitted = admit_fins_upload_material_request(
        _request(tmp_path), state_repository=runtime.material_upload_state_repository
    )
    service, prepared, company = await _prepare_admitted(runtime, admitted, converter)
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(pipeline.upload_material, _request(tmp_path)).result(timeout=10)["status"] == "ok"
    name = (
        "probe.txt"
        if damage in {"original_missing", "digest_same_length"}
        else "probe.txt_docling.json" if damage == "docling_missing" else "material_manifest.json"
    )
    path = next((tmp_path / "portfolio").rglob(name))
    if damage == "digest_same_length":
        data = path.read_bytes()
        path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    else:
        path.unlink()
    before = _bytes(tmp_path)
    with pytest.raises(FinsUploadFailureError) as raised:
        execute_prepared_material_publication(
            request=admitted,
            prepared=prepared,
            expected_company_meta=company,
            state_repository=runtime.material_upload_state_repository,
            batching_repository=runtime.batching_repository,
            upload_service=service,
            cancellation=None,
        )
    assert raised.value.failure.code.value == "source_publication_conflict" and _bytes(tmp_path) == before
    runtime.close()


def test_arbiter_strict_same_business_and_company_snapshot(tmp_path: Path) -> None:
    """参数：真实双方 old MISSING 与 final；返回：无；异常：断言失败；各业务差异和已观察公司时间不可当同材料，版本不用于反推相同。"""
    runtime, pipeline, _ = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    admitted = admit_fins_upload_material_request(
        _request(tmp_path), state_repository=runtime.material_upload_state_repository
    )
    assert pipeline.upload_material(_request(tmp_path))["status"] == "ok"
    final = runtime.material_upload_state_repository.read_material_upload_state("AAPL", admitted.identity.document_id)
    candidate = final.publication_identity
    assert candidate is not None and final.company_meta is not None
    variants = [
        replace(candidate, source_fingerprint="a" * 64),
        replace(candidate, material_name="Different"),
        replace(candidate, form_type="OTHER"),
        replace(candidate, amended=True),
        replace(candidate, is_deleted=True),
        replace(candidate, originals=(replace(candidate.originals[0], name="different.txt"),)),
        replace(candidate, primary_document="different.json"),
    ]
    for variant in variants:
        assert (
            arbitrate_material_upload_publication(
                request=admitted, fresh_state=final, candidate=variant, expected_company_meta=final.company_meta
            ).disposition
            is MaterialUploadPublicationDisposition.CONFLICT
        )
    assert (
        arbitrate_material_upload_publication(
            request=admitted,
            fresh_state=final,
            candidate=replace(candidate, document_version="v7"),
            expected_company_meta=final.company_meta,
        ).disposition
        is MaterialUploadPublicationDisposition.IDENTICAL_SKIP
    )
    assert (
        arbitrate_material_upload_publication(
            request=admitted,
            fresh_state=replace(final, company_meta=replace(final.company_meta, updated_at="2000-01-01T00:00:00Z")),
            candidate=candidate,
            expected_company_meta=final.company_meta,
        ).disposition
        is MaterialUploadPublicationDisposition.CONFLICT
    )
    runtime.close()


@pytest.mark.parametrize("marker", [None, "false", 0, 1])
def test_material_read_marker_is_required_exact_bool(tmp_path: Path, marker: str | int | None) -> None:
    """参数：缺失或非 bool 字段；返回：无；异常：断言失败；只用严格材料 owner，filing 原 amended 保留。"""
    runtime, pipeline, _ = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    result = pipeline.upload_material(_request(tmp_path))
    identifier = result["document_id"]
    assert isinstance(identifier, str)
    state = runtime.material_upload_state_repository.read_material_upload_state("AAPL", identifier)
    assert state.source_meta is not None
    raw = dict(state.source_meta)
    if marker is None:
        del raw["amended"]
    else:
        raw["amended"] = marker
    with pytest.raises(KeyError if marker is None else ValueError):
        _parse_source_document_meta(raw, source_kind=SourceKind.MATERIAL)
    runtime.close()


class _CancelledMaterialToken:
    """只提供已取消事实的公共 token。"""

    def is_cancelled(self) -> bool:
        """参数：无；返回：True；异常：无。"""
        return True

    def cancel_reason(self) -> str | None:
        """参数：无；返回：测试取消原因；异常：无。"""
        return "owner test cancel"

    def requested_at(self) -> datetime | None:
        """参数：无；返回：固定取消时间；异常：无。"""
        return datetime(2026, 10, 3, tzinfo=timezone.utc)


class _MaterialExecutorReleaseFault:
    """在实际提交的真实 COMMITTED 锁释放位置注入故障，记录唯一提交次数。"""

    def __init__(self, repository: FsMaterialUploadStateRepository) -> None:
        """参数：实际 Fs owner；返回：无；异常：无。"""
        self.repository = repository
        self.original = repository.commit_material_upload_batch
        self.calls = 0
        self.fault: _PostCommitReleaseFault | None = None

    def __call__(self, batch: BatchToken) -> MaterialUploadPublishedState:
        """参数：实际 capability；返回：真实 final；异常：实际释放故障传播。"""
        self.calls += 1
        core = self.repository._repository_set.core
        state = core._resolve_active_batch(batch, batch.ticker)
        self.fault = _PostCommitReleaseFault(core, state)
        with patch.object(core, "_release_lock_token", self.fault):
            return self.original(batch)


@pytest.mark.asyncio
async def test_executor_release_failure_keeps_durable_and_never_retries(tmp_path: Path) -> None:
    """参数：真实 Fs 与提交后释放故障；返回：无；异常：断言失败；一次 commit、无 postcommit read、无 rollback/retry/skip。"""
    runtime, _, converter = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    request = admit_fins_upload_material_request(
        _request(tmp_path, amended=True), state_repository=runtime.material_upload_state_repository
    )
    service, prepared, company = await _prepare_admitted(runtime, request, converter)
    repository = runtime.material_upload_state_repository
    assert isinstance(repository, FsMaterialUploadStateRepository)
    fault = _MaterialExecutorReleaseFault(repository)
    with (
        patch.object(repository, "commit_material_upload_batch", fault),
        patch.object(repository, "read_material_upload_state", side_effect=AssertionError("禁止 postcommit read")),
    ):
        with pytest.raises(OSError, match="post-COMMITTED"):
            execute_prepared_material_publication(
                request=request,
                prepared=prepared,
                expected_company_meta=company,
                state_repository=repository,
                batching_repository=runtime.batching_repository,
                upload_service=service,
                cancellation=None,
            )
    assert fault.calls == 1 and fault.fault is not None and fault.fault.fired
    assert fault.fault.state.phase == _PHASE_COMMITTED
    with pytest.raises(ValueError):
        runtime.batching_repository.rollback_batch(fault.fault.state.token)
    final = repository.read_material_upload_state("AAPL", request.identity.document_id)
    assert final is not None and final.source_integrity.status is SourceIntegrityStatus.COMPLETE
    assert final.publication_identity is not None and final.publication_identity.amended is True
    assert final == fault.fault.state.material_final
    runtime.close()


@pytest.mark.asyncio
async def test_executor_precommit_cancel_has_no_material_final(tmp_path: Path) -> None:
    """参数：真实准备后的取消 token；返回：无；异常：断言失败；D rollback 零材料写，独立公司仍保留。"""
    runtime, _, converter = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    request = admit_fins_upload_material_request(
        _request(tmp_path, amended=True), state_repository=runtime.material_upload_state_repository
    )
    service, prepared, company = await _prepare_admitted(runtime, request, converter)
    before = _bytes(tmp_path)
    outcome = execute_prepared_material_publication(
        request=request,
        prepared=prepared,
        expected_company_meta=company,
        state_repository=runtime.material_upload_state_repository,
        batching_repository=runtime.batching_repository,
        upload_service=service,
        cancellation=_CancelledMaterialToken(),
    )
    assert (
        outcome.result.status == "cancelled"
        and outcome.result.published_amended is None
        and outcome.published_state is None
    )
    assert _bytes(tmp_path) == before and runtime.company_repository.get_company_meta("AAPL") == company
    runtime.close()


def test_initial_none_company_race_is_decided_by_company_commit_owner(tmp_path: Path) -> None:
    """参数：两份真实旧受理及在 A begin 前的 B 公司提交；返回：无；异常：断言失败；None→同意图由公司 owner 严格 no-op，不被分离的只读检查误拒。"""
    runtime, _, _ = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    a = admit_fins_upload_material_request(
        _request(tmp_path), state_repository=runtime.material_upload_state_repository
    )
    b = admit_fins_upload_material_request(
        _request(tmp_path), state_repository=runtime.material_upload_state_repository
    )
    competing_final = execute_material_upload_company_stage(
        request=b, state_repository=runtime.material_upload_state_repository,
        company_repository=runtime.company_repository, batching_repository=runtime.batching_repository,
        cancellation=None,
    )
    after_b = _bytes(tmp_path)
    with patch.object(runtime.material_upload_state_repository, "read_material_upload_state", side_effect=AssertionError("公司阶段不得独立 fresh read")):
        final = execute_material_upload_company_stage(
            request=a,
            state_repository=runtime.material_upload_state_repository,
            company_repository=runtime.company_repository,
            batching_repository=runtime.batching_repository,
            cancellation=None,
        )
    assert competing_final is not None and final == competing_final
    assert _bytes(tmp_path) == after_b
    runtime.close()


class _PublishBeforeCompanyValidate:
    """在 A 取得公司 guard 前完成 B 的真实发布，不在 A writer 内等待。"""

    def __init__(self, runtime: DefaultFinsRuntime, pipeline: SecPipeline, competing: ValidatedFinsUploadMaterialRequest) -> None:
        """参数：真实仓储、市场及 B 旧受理；返回：无；异常：无。"""
        self.runtime = runtime
        self.pipeline = pipeline
        self.competing = competing
        self.original = runtime.material_upload_state_repository.validate_material_upload_state
        self.fired = False
        self.expected: MaterialUploadPublishedState | None = None
        self.after_b: dict[str, bytes] | None = None

    def __call__(self, *, ticker: str, document_id: str, expected_source_state: MaterialUploadPublishedState | None, expected_company_meta: CompanyMeta | None) -> MaterialUploadPublishedState:
        """参数：真实 guard 输入；返回：原 owner 真值；异常：真实 B 发布或 A guard 失败原样透传。"""
        if not self.fired:
            self.fired = True
            self.expected = expected_source_state
            with ThreadPoolExecutor(max_workers=1) as executor:
                assert executor.submit(self.pipeline.upload_material_validated, self.competing).result(timeout=10)["status"] == "ok"
            self.after_b = _bytes(self.runtime.workspace_root)
        return self.original(ticker=ticker, document_id=document_id, expected_source_state=expected_source_state, expected_company_meta=expected_company_meta)


@pytest.mark.parametrize("action,overwrite", [("auto", False), ("create", False), ("auto", True)])
@pytest.mark.asyncio
async def test_existing_company_old_missing_interleave_keeps_source_owner(tmp_path: Path, action: str, overwrite: bool) -> None:
    """参数：已有公司与动作；返回：无；异常：断言失败；auto 留 writer 裁 skip，其余严格拒绝源漂移。"""
    runtime, pipeline, converter = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(pipeline.upload_material, replace(_request(tmp_path), material_name="Other Material")).result(timeout=10)["status"] == "ok"
    a = admit_fins_upload_material_request(_request(tmp_path, action=action, overwrite=overwrite), state_repository=runtime.material_upload_state_repository)
    b = admit_fins_upload_material_request(_request(tmp_path), state_repository=runtime.material_upload_state_repository)
    assert a.state_admission.observed_state == b.state_admission.observed_state
    assert a.state_admission.observed_state.source_integrity.status is SourceIntegrityStatus.MISSING
    assert a.state_admission.observed_state.company_meta is not None
    interleave = _PublishBeforeCompanyValidate(runtime, pipeline, b)
    with patch.object(runtime.material_upload_state_repository, "validate_material_upload_state", interleave):
        if action != "auto" or overwrite:
            with pytest.raises(FinsUploadFailureError) as raised:
                await _prepare_admitted(runtime, a, converter)
            assert raised.value.failure.code.value == "source_publication_conflict"
            assert interleave.expected is a.state_admission.observed_state
        else:
            service, prepared, company = await _prepare_admitted(runtime, a, converter)
            assert interleave.expected is None
            outcome = execute_prepared_material_publication(
                request=a, prepared=prepared, expected_company_meta=company,
                state_repository=runtime.material_upload_state_repository,
                batching_repository=runtime.batching_repository, upload_service=service, cancellation=None,
            )
            assert outcome.result.status == "skipped" and outcome.published_state is not None
    assert interleave.fired and interleave.after_b == _bytes(tmp_path)
    runtime.close()


@pytest.mark.parametrize("damage", ["bad_meta", "missing_original", "missing_docling", "missing_manifest"])
def test_real_unsafe_or_repair_material_rejected_before_lifecycle(tmp_path: Path, damage: str) -> None:
    """参数：真实材料损坏与三个运行时入口；返回：无；异常：断言失败；拒绝先于观察/job/runner，所有业务字节保持。"""
    runtime, pipeline, _ = _pipeline(tmp_path)
    (tmp_path / "probe.txt").write_text("first")
    first = pipeline.upload_material(_request(tmp_path))
    identifier = first["document_id"]
    assert isinstance(identifier, str)
    source = runtime.source_repository.get_source_meta("AAPL", identifier, SourceKind.MATERIAL)
    if damage == "bad_meta":
        paths = tuple((tmp_path / "portfolio" / "AAPL" / "materials").rglob("meta.json"))
        assert len(paths) == 1
        path = paths[0]
        path.write_text("{}")
    else:
        name = (
            "probe.txt"
            if damage == "missing_original"
            else "probe.txt_docling.json" if damage == "missing_docling" else "material_manifest.json"
        )
        next((tmp_path / "portfolio").rglob(name)).unlink()
    state = runtime.material_upload_state_repository.read_material_upload_state("AAPL", identifier)
    assert state.source_integrity.status in {SourceIntegrityStatus.UNSAFE, SourceIntegrityStatus.REPAIR_REQUIRED}
    ingestion = runtime.get_ingestion_runtime()
    before = _bytes(tmp_path)
    for entrance in ("direct", "observation", "job"):
        with pytest.raises(FinsUploadPrevalidationError) as raised:
            if entrance == "direct":
                ingestion.upload(_request(tmp_path))
            elif entrance == "observation":
                ingestion.prepare_observed_upload(_request(tmp_path), _UncancelledMaterialToken())
            else:
                ingestion.start_upload(_request(tmp_path))
        assert raised.value.failure.code.value == "source_integrity_unsafe"
        assert "材料" in raised.value.failure.message and "filing" not in raised.value.failure.message
    assert ingestion._observations == {} and not tuple(runtime.ingestion_job_store.root_dir.glob("*.json"))
    assert _bytes(tmp_path) == before
    assert source is not None
    runtime.close()


class _UncancelledMaterialToken:
    """生命周期前置校验用公共未取消 token。"""

    def is_cancelled(self) -> bool:
        """参数：无；返回：False；异常：无。"""
        return False

    def cancel_reason(self) -> str | None:
        """参数：无；返回：None；异常：无。"""
        return None

    def requested_at(self) -> datetime | None:
        """参数：无；返回：None；异常：无。"""
        return None
