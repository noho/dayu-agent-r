"""材料身份、静态首错、一次路径解析及公开入口的 owner 契约测试。"""
from __future__ import annotations

from datetime import datetime
from dayu.contracts.json_value import JsonValue
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.upload_batch import UploadBatchPlanRequest, generate_upload_batch_plan
from dayu.cli.commands.fins import _upload_batch_command_argv, _prevalidate_upload_material_request
from dayu.cli.arg_parsing import parse_cli_args

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from dayu.fins.ingestion_runtime import FinsUploadMaterialRequest, admit_fins_upload_material_request
from dayu.fins.pipelines.docling_upload_service import build_material_ids
from dayu.fins.upload_usage_contract import FinsUploadUsageCode, FinsUploadUsageError, FinsUploadUsageCategory
from dayu.fins import upload_asset_plan
from dayu.fins.tools.upload_tools import _upload_request_from_arguments


@pytest.mark.parametrize("action", ("auto", "create", "update", "delete"))
@pytest.mark.parametrize("missing", (None, "", "  "))
@pytest.mark.parametrize("field,code", (("form_type", FinsUploadUsageCode.MISSING_FORM_TYPE), ("material_name", FinsUploadUsageCode.MISSING_MATERIAL_NAME)))
def test_required_identity_before_seed(action: str, missing: str | None, field: str, code: FinsUploadUsageCode, tmp_path: Path) -> None:
    """参数：动作、缺失值、字段及原因/隔离根；返回：无；异常：断言失败；非法身份不能计算 seed 或读取目标。"""
    raw = FinsUploadMaterialRequest(ticker="AAPL", action=action, files=() if action == "delete" else (tmp_path / "a.txt",), form_type=" other ", material_name="Deck")
    raw = replace(raw, form_type=missing) if field == "form_type" else replace(raw, material_name=missing)
    with patch("dayu.fins.pipelines.docling_upload_service.hashlib.sha1", side_effect=AssertionError("非法输入计算 seed")):
        with pytest.raises(FinsUploadUsageError) as raised:
            admit_fins_upload_material_request(raw)
    assert raised.value.failure.code is code
    assert raised.value.failure.category is FinsUploadUsageCategory.REQUEST
    assert raised.value.failure.hint


@pytest.mark.parametrize("unit", ("x", "😀", "e\u0301"))
@pytest.mark.parametrize("length", (239, 240, 241))
def test_name_code_points(unit: str, length: int) -> None:
    """参数：字符组成及码点长度；返回：无；异常：断言失败；不截断或 Unicode 归一化。"""
    name = (unit * length)[:length]
    if length > 240:
        with pytest.raises(FinsUploadUsageError) as raised:
            build_material_ids(form_type=" other ", material_name=" " + name + " ", fiscal_year=None, fiscal_period=None, document_id=None)
        assert raised.value.failure.code is FinsUploadUsageCode.MATERIAL_NAME_TOO_LONG
    else:
        identity = build_material_ids(form_type=" other ", material_name=" " + name + " ", fiscal_year=None, fiscal_period=None, document_id=None)
        assert identity.material_name == name
        assert identity.form_type == "OTHER"
        with pytest.raises(ValueError):
            replace(identity, form_type=" other ")


@pytest.mark.parametrize("year", (None, 1799, 1800, 2100, 2101, -1, 0, 10000, True, False))
@pytest.mark.parametrize("period", (None, "", "  ", "FY", " h1 ", "q1", "Q2", "Q3", "Q4", "bad", "x" * 241))
def test_optional_fiscal_domain(year: int | None, period: str | None) -> None:
    """参数：独立可省略的财年/财期；返回：无；异常：断言失败；非法年先于财期。"""
    valid_year = year is None or type(year) is int and 1800 <= year <= 2100
    valid_period = period is None or period.strip().upper() in ("", "FY", "H1", "Q1", "Q2", "Q3", "Q4")
    if not valid_year or not valid_period:
        with pytest.raises(FinsUploadUsageError) as raised:
            build_material_ids(form_type="OTHER", material_name="Deck", fiscal_year=year, fiscal_period=period, document_id=None)
        expected = FinsUploadUsageCode.INVALID_MATERIAL_FISCAL_YEAR if not valid_year else FinsUploadUsageCode.UNSUPPORTED_FISCAL_PERIOD
        assert raised.value.failure.code is expected
    else:
        identity = build_material_ids(form_type="OTHER", material_name="Deck", fiscal_year=year, fiscal_period=period, document_id=None)
        assert identity.fiscal_year == year
        assert identity.fiscal_period == (period.strip().upper() or None if period is not None else None)


def test_document_assertion_and_internal_input() -> None:
    """参数：无；返回：无；异常：断言失败；ID 仅一致断言，旧内部输入空/非空都拒绝。"""
    identity = build_material_ids(form_type="OTHER", material_name="Deck", fiscal_year=None, fiscal_period=None, document_id=None)
    assert build_material_ids(form_type="OTHER", material_name="Deck", fiscal_year=None, fiscal_period=None, document_id=identity.document_id) == identity
    for value, code in (("", FinsUploadUsageCode.EMPTY_DOCUMENT_ID), ("  ", FinsUploadUsageCode.EMPTY_DOCUMENT_ID), ("wrong", FinsUploadUsageCode.DOCUMENT_ID_MISMATCH)):
        with pytest.raises(FinsUploadUsageError) as raised:
            build_material_ids(form_type="OTHER", material_name="Deck", fiscal_year=None, fiscal_period=None, document_id=value)
        assert raised.value.failure.code is code
    for value in ("", "old"):
        with pytest.raises(ValueError, match="unknown upload parameter"):
            _upload_request_from_arguments({"ticker": "AAPL", "upload_kind": "material", "internal_document_id": value})


def test_once_normalization_and_pure_replace(tmp_path: Path) -> None:
    """参数：隔离文件根；返回：无；异常：断言失败；每 occurrence 一次解析，构造与 replace 不再 I/O。"""
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a"); b.write_text("b")
    link = tmp_path / "selected.txt"
    link.symlink_to(b)
    raw = FinsUploadMaterialRequest(ticker="AAPL", files=(a, b), primary_selectors=(link,), form_type=" other ", material_name=" Deck ")
    with patch.object(upload_asset_plan, "normalize_upload_asset_path", wraps=upload_asset_plan.normalize_upload_asset_path) as normalize:
        valid = admit_fins_upload_material_request(raw)
        assert normalize.call_count == 3
        valid.validate()
        assert replace(valid) == valid
        assert normalize.call_count == 3
    assert valid.request.primary_selectors == (b,)
    assert valid.asset_plan.primary_original_name == "b.txt"
    with pytest.raises(ValueError):
        replace(valid, request=replace(valid.request, primary_selectors=(a,)))
    with pytest.raises(ValueError):
        replace(valid, identity=replace(valid.identity, material_name="Other"))


@pytest.mark.parametrize("files,selectors,code", ((0, 0, "missing_files"), (2, 0, "missing_multi_file_primary"), (2, 2, "multiple_primary_selectors"), (1, 1, "primary_not_in_files")))
def test_selection_and_first_error(files: int, selectors: int, code: str, tmp_path: Path) -> None:
    """参数：文件数/选择数/原因与隔离根；返回：无；异常：断言失败；纯选择封闭分类及 exact 成员要求。"""
    paths = tuple(tmp_path / f"{i}.txt" for i in range(files))
    selected = tuple(tmp_path / "outside.txt" for _ in range(selectors))
    raw = FinsUploadMaterialRequest(ticker="AAPL", files=paths, primary_selectors=selected, form_type="OTHER", material_name="Deck")
    with pytest.raises(FinsUploadUsageError) as raised:
        admit_fins_upload_material_request(raw)
    assert raised.value.failure.code.value == code
    assert raised.value.failure.category is FinsUploadUsageCategory.REQUEST
    if code == "missing_multi_file_primary":
        assert raised.value.failure.message == "多文件材料必须明确指定唯一主文件"
    bad = replace(raw, files=tuple(tmp_path / f"{i}.txt" for i in range(101)))
    with pytest.raises(FinsUploadUsageError) as raised:
        admit_fins_upload_material_request(bad)
    assert raised.value.failure.code is FinsUploadUsageCode.TOO_MANY_FILES
    assert raised.value.failure.category is FinsUploadUsageCategory.ASSET_PLAN


def test_delete_rejects_paths_without_io(tmp_path: Path) -> None:
    """参数：不存在的目标路径根；返回：无；异常：断言失败；删除组合错误不触 filesystem。"""
    raw = FinsUploadMaterialRequest(ticker="AAPL", action="delete", files=(tmp_path / "missing.txt",), form_type="OTHER", material_name="Deck")
    with patch.object(upload_asset_plan, "normalize_upload_asset_path", side_effect=AssertionError("删除组合解析路径")):
        with pytest.raises(FinsUploadUsageError) as raised:
            admit_fins_upload_material_request(raw)
        assert raised.value.failure.code is FinsUploadUsageCode.FILES_NOT_ALLOWED_FOR_DELETE
        with pytest.raises(FinsUploadUsageError) as raised:
            admit_fins_upload_material_request(replace(raw, files=(), primary_selectors=(tmp_path / "missing.txt",)))
        assert raised.value.failure.code is FinsUploadUsageCode.PRIMARY_NOT_ALLOWED_FOR_DELETE


@pytest.mark.parametrize("action", ("auto", "create", "update", "delete"))
@pytest.mark.parametrize("field,code", (
    ("form", FinsUploadUsageCode.MISSING_FORM_TYPE),
    ("name", FinsUploadUsageCode.MISSING_MATERIAL_NAME),
    ("year", FinsUploadUsageCode.INVALID_MATERIAL_FISCAL_YEAR),
    ("period", FinsUploadUsageCode.UNSUPPORTED_FISCAL_PERIOD),
    ("empty_id", FinsUploadUsageCode.EMPTY_DOCUMENT_ID),
    ("wrong_id", FinsUploadUsageCode.DOCUMENT_ID_MISMATCH),
))
def test_real_runtime_static_identity_has_no_lifecycle_side_effect(
    tmp_path: Path, action: str, field: str, code: FinsUploadUsageCode,
) -> None:
    """参数：隔离根、全动作、非法字段/原因；返回：无；异常：断言失败；真实 runtime 在读取字节、batch、job/observation 前拒绝。"""
    default = DefaultFinsRuntime.create(workspace_root=tmp_path)
    runtime = default.get_ingestion_runtime()
    raw = FinsUploadMaterialRequest(ticker="AAPL", action=action,
        files=() if action == "delete" else (tmp_path / "never-read.txt",), form_type="OTHER", material_name="Deck")
    if field == "form": raw = replace(raw, form_type="  ")
    elif field == "name": raw = replace(raw, material_name=None)
    elif field == "year": raw = replace(raw, fiscal_year=True)
    elif field == "period": raw = replace(raw, fiscal_period="unsupported")
    elif field == "empty_id": raw = replace(raw, document_id="")
    else: raw = replace(raw, document_id="wrong")
    with patch.object(type(runtime.job_store), "create_job", side_effect=AssertionError("不得创建 job")), \
         patch.object(default.batching_repository, "begin_batch", side_effect=AssertionError("不得开始 batch")), \
         patch.object(default.source_repository, "get_source_meta", side_effect=AssertionError("不得读目标")), \
         patch.object(upload_asset_plan, "normalize_upload_asset_path", side_effect=AssertionError("身份错误先于路径")), \
         patch.object(Path, "read_bytes", side_effect=AssertionError("不得读字节")):
        for start in (runtime.start_upload,):
            with pytest.raises(FinsUploadUsageError) as raised:
                start(raw)
            assert raised.value.failure.code is code
        with pytest.raises(FinsUploadUsageError) as observed:
            runtime.prepare_observed_upload(raw, _IdentityOpenToken())
        assert observed.value.failure.code is code
    assert runtime._observations == {}
    assert not tuple((tmp_path / ".dayu" / "fins_ingestion" / "jobs").glob("*.json"))
    assert not (tmp_path / "portfolio" / "AAPL").exists()
    default.close()


class _IdentityOpenToken:
    """仅提供未取消事实，不替换 workflow 或仓储。"""

    def is_cancelled(self) -> bool:
        """参数：无；返回：False；异常：无。"""
        return False

    def cancel_reason(self) -> str | None:
        """参数：无；返回：None；异常：无。"""
        return None

    def requested_at(self) -> datetime | None:
        """参数：无；返回：None；异常：无。"""
        return None


def test_batch_material_entry_to_real_parser_and_handoff(tmp_path: Path) -> None:
    """参数：真实源文件/根；返回：无；异常：断言失败；typed batch 实际 argv 经 parser 与共享准入取得规范事实。"""
    source_dir = tmp_path / "inputs"
    source_dir.mkdir()
    (source_dir / "2024 Earnings Presentation.pdf").write_bytes(b"batch content")
    plan = generate_upload_batch_plan(UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir,
        material_form=" earnings_presentation ", company_name="Apple Inc."))
    assert len(plan.material_entries) == 1
    entry = plan.material_entries[0]
    argv = _upload_batch_command_argv(entry, workspace_root=tmp_path / "workspace")
    parsed = parse_cli_args(argv[3:])
    validated = _prevalidate_upload_material_request(parsed)
    assert validated is not None
    assert validated.identity.form_type == entry.form_type
    assert validated.identity.material_name == entry.material_name
    assert validated.request.form_type == validated.identity.form_type
    assert validated.request.files == (entry.file,)
    assert validated.asset_plan.primary_original_name == entry.file.name
    assert validated.request.document_id is None


@pytest.mark.parametrize("selector_case", ("same_basename_outside", "repeat_same_selector"))
def test_material_selector_is_exact_and_keeps_occurrences(tmp_path: Path, selector_case: str) -> None:
    """参数：真实根与反例；返回：无；异常：断言失败；同basename不能命中，重复同一selector不能去重。"""
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    selectors = (tmp_path / "outside" / "a.txt",) if selector_case == "same_basename_outside" else (a, a)
    request = FinsUploadMaterialRequest(ticker="AAPL", files=(a, b), primary_selectors=selectors,
                                       form_type="OTHER", material_name="Deck")
    with pytest.raises(FinsUploadUsageError) as error:
        admit_fins_upload_material_request(request)
    assert error.value.failure.category is FinsUploadUsageCategory.REQUEST
    expected = (FinsUploadUsageCode.PRIMARY_NOT_IN_FILES if selector_case == "same_basename_outside"
                else FinsUploadUsageCode.MULTIPLE_PRIMARY_SELECTORS)
    assert error.value.failure.code is expected
    assert error.value.failure.hint and error.value.failure.file_label is None


@pytest.mark.parametrize("action", ("auto", "create", "update", "delete"))
@pytest.mark.parametrize("ticker", (None, "", "bad,ticker"))
def test_identity_tool_combination_precedes_ticker(action: str, ticker: str | None, tmp_path: Path) -> None:
    """参数：动作、非法代码与隔离根；返回：无；异常：断言失败；共享组合 leaf 先于 ticker/date/identity 且不解析路径。"""
    arguments: dict[str, JsonValue] = {"upload_kind": "material", "action": action,
        "files": [str(tmp_path / "never.txt")] if action == "delete" else [],
        "form_type": "", "material_name": "", "filing_date": "bad"}
    if ticker is not None:
        arguments["ticker"] = ticker
    with patch.object(upload_asset_plan, "normalize_upload_asset_path", side_effect=AssertionError("组合 leaf 不得解析路径")):
        with pytest.raises(FinsUploadUsageError) as raised:
            _upload_request_from_arguments(arguments)
    assert raised.value.failure.code is (FinsUploadUsageCode.FILES_NOT_ALLOWED_FOR_DELETE
        if action == "delete" else FinsUploadUsageCode.MISSING_FILES)
    assert raised.value.failure.category is FinsUploadUsageCategory.REQUEST
    assert raised.value.failure.message and raised.value.failure.hint


def test_identity_tool_path_projection_preserves_raw_text(tmp_path: Path) -> None:
    """参数：真实文件根；返回：无；异常：断言失败；files 与 primary 原文不被通用文本 trim 改写。"""
    original = tmp_path / "a.txt"
    original.write_bytes(b"contents")
    arguments: dict[str, JsonValue] = {"ticker": "AAPL", "upload_kind": "material",
        "files": [str(original) + " "], "primary": str(original) + " ",
        "form_type": "OTHER", "material_name": "Deck"}
    raw = _upload_request_from_arguments(arguments)
    assert isinstance(raw, FinsUploadMaterialRequest)
    assert raw.files == raw.primary_selectors == (Path(str(original) + " "),)
    # exact 选择不能把原文中不存在的路径裁剪成另一个真实成员。
    arguments["files"] = [str(original)]
    raw = _upload_request_from_arguments(arguments)
    assert isinstance(raw, FinsUploadMaterialRequest)
    with pytest.raises(FinsUploadUsageError) as raised:
        admit_fins_upload_material_request(raw)
    assert raised.value.failure.code is FinsUploadUsageCode.PRIMARY_NOT_IN_FILES


@pytest.mark.parametrize("files", ("a.txt", [False], [""], ["   "]))
def test_identity_tool_files_lexical_boundary(files: JsonValue) -> None:
    """参数：词法非法 JSON 文件列表；返回：无；异常：断言失败；保留既有数组/非空字符串约束。"""
    with pytest.raises(ValueError, match="files must"):
        _upload_request_from_arguments({"upload_kind": "material", "files": files})
