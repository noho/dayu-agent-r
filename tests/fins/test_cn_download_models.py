"""CN/HK 下载 pipeline 终态 owner 的封闭词表契约测试。"""

from typing import get_args, Literal

from dayu.fins.pipelines import cn_download_models
from dayu.fins.pipelines.cn_download_models import (
    CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES,
    CN_DOWNLOAD_TERMINAL_CANCELLED,
    CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED,
    CN_DOWNLOAD_TERMINAL_OK,
    CnDownloadTerminalStatus,
)


def test_cn_download_terminal_owner_has_exact_native_string_values() -> None:
    """类型与值必须精确承诺已有三值，不能以同一常量自比代替协议预期。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 词表、原生字符串类型或普通入口子集漂移时抛出。
    """

    assert get_args(CnDownloadTerminalStatus) == ("ok", "cancelled", "integrity_failed")
    assert CN_DOWNLOAD_TERMINAL_OK == "ok"
    assert CN_DOWNLOAD_TERMINAL_CANCELLED == "cancelled"
    assert CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED == "integrity_failed"
    assert all(type(value) is str for value in (
        CN_DOWNLOAD_TERMINAL_OK,
        CN_DOWNLOAD_TERMINAL_CANCELLED,
        CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED,
    ))
    assert type(CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES) is tuple
    assert CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES == ("ok", "cancelled")
    assert CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES == (
        CN_DOWNLOAD_TERMINAL_OK, CN_DOWNLOAD_TERMINAL_CANCELLED,
    )
    assert set(CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES) < set(get_args(CnDownloadTerminalStatus))
    assert CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED not in CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES


def test_cn_download_terminal_owner_exports_all_contract_symbols() -> None:
    """共享模型必须显式导出全部终态契约符号。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 公共契约符号未声明导出时抛出。
    """

    assert {
        "CnDownloadTerminalStatus",
        "CN_DOWNLOAD_TERMINAL_OK",
        "CN_DOWNLOAD_TERMINAL_CANCELLED",
        "CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED",
        "CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES",
    } <= set(cn_download_models.__all__)


from dataclasses import replace
import hashlib
import pytest
from dayu.fins.domain.document_models import SourceDocumentRevision
from dayu.fins.pipelines.cn_download_models import CnAnnualReportFacts,CnAnnualReportPublication,CnAnnualReportPdf,CnReportDiscoveryResult,DownloadedReportAsset,require_matching_cn_annual_asset
from tests.fins.test_cn_download_workflow import _candidate
from tests.fins.test_cn_annual_report_facts import build_synthetic_annual_pdf


@pytest.mark.parametrize('year,kind,error',((True,'full',TypeError),(999,'full',ValueError),(10000,'full',ValueError),(2024,'unknown',ValueError)))
def test_annual_facts_closed(year: int,kind: Literal["full", "summary"],error: type[Exception]) -> None:
    """参数：非法年度事实。返回：无。异常：未拒绝时断言失败。"""
    with pytest.raises(error):CnAnnualReportFacts.__init__(CnAnnualReportFacts(2024,'full'),year,kind)


def _asset() -> DownloadedReportAsset:
    """参数：无。返回：明确合成合法年度资产。异常：无。"""
    pdf=build_synthetic_annual_pdf()
    return DownloadedReportAsset(_candidate(),pdf,hashlib.sha256(pdf).hexdigest(),len(pdf),'2026-10-12T00:00:00+00:00')


@pytest.mark.parametrize('field',('candidate','sha','length','empty','time','nonFY','provenance'))
def test_asset_contract_mismatch(field: str) -> None:
    """参数：资产错配维度。返回：无。异常：错配未拒绝断言失败。"""
    asset=_asset();candidate=asset.candidate
    if field=='candidate':asset=replace(asset,candidate=replace(candidate,source_url='different'))
    elif field=='sha':asset=replace(asset,sha256='wrong')
    elif field=='length':asset=replace(asset,content_length=1)
    elif field=='empty':asset=replace(asset,pdf_bytes=b'')
    elif field=='time':asset=replace(asset,downloaded_at='')
    elif field=='nonFY':candidate=_candidate(fiscal_period='H1')
    else:candidate=replace(candidate,fiscal_year_source='title_or_category_inferred')
    with pytest.raises(ValueError):require_matching_cn_annual_asset(candidate,asset)


@pytest.mark.parametrize('case',('duplicate_candidate','duplicate_asset','unselected_asset','duplicate_witness','both','nonFY'))
def test_discovery_handoff_unique(case: str) -> None:
    """参数：重复/错配结果。返回：无。异常：结果契约未拒绝断言失败。"""
    asset=_asset();candidate=asset.candidate;witness=CnAnnualReportPublication('cninfo',candidate.source_id,'doc',SourceDocumentRevision('r'))
    candidates=(candidate,);assets:tuple[DownloadedReportAsset,...]=();witnesses:tuple[CnAnnualReportPublication,...]=()
    if case=='duplicate_candidate':candidates=(candidate,candidate)
    elif case=='duplicate_asset':assets=(asset,asset)
    elif case=='unselected_asset':candidates=();assets=(asset,)
    elif case=='duplicate_witness':witnesses=(witness,witness)
    elif case=='both':assets=(asset,);witnesses=(witness,)
    else:candidates=(_candidate(fiscal_period='H1'),);witnesses=(witness,)
    with pytest.raises(ValueError):CnReportDiscoveryResult(candidates,(),assets,witnesses)


def test_valid_handoff_and_pdf_input() -> None:
    """参数：无。返回：无。异常：合法资产被拒断言失败。"""
    asset=_asset();witness=CnAnnualReportPublication('cninfo','A1','doc',SourceDocumentRevision('r'))
    require_matching_cn_annual_asset(asset.candidate,asset)
    assert CnReportDiscoveryResult((asset.candidate,),(),(asset,),()).prepared_assets==(asset,)
    assert CnReportDiscoveryResult((asset.candidate,),(),(),(witness,)).local_annual_publications==(witness,)
    assert CnAnnualReportPdf(witness,' ',asset.pdf_bytes).source_url==' '
    with pytest.raises(ValueError):CnAnnualReportPdf(witness,'',asset.pdf_bytes)
    with pytest.raises(ValueError):CnAnnualReportPdf(witness,'locator',b'')
    with pytest.raises(ValueError):CnAnnualReportPublication('cninfo','','doc',SourceDocumentRevision('r'))
