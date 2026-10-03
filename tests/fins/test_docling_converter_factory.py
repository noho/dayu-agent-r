"""默认装配 owner 显式管理员输入及唯一失败映射合同。"""
from __future__ import annotations
from pathlib import Path
import pytest
from dayu.documents.xbrl_config import XbrlConfigurationError
from dayu.fins.pipelines.docling_converter_factory import create_docling_converter
from dayu.fins.pipelines.docling_process_converter import DoclingConversionError, DoclingConversionFailureKind
from tests.documents.test_xbrl_config import _corrupt_archive, _deployment, _ZIP_INPUT_FAILURES

def test_unset_factory_does_not_discover_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：工作区和环境；返回：无；异常：缺配置装配失败时断言失败。"""
    monkeypatch.delenv('DAYU_XBRL_CONFIG',raising=False)
    assert create_docling_converter(tmp_path) is not None

@pytest.mark.parametrize('value',['','relative.json','/private/tmp/missing-dayu-xbrl-config.json'])
def test_bad_config_is_typed_construction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """参数：非法部署路径；返回：无；异常：错误分类漂移时断言失败。"""
    monkeypatch.setenv('DAYU_XBRL_CONFIG',value)
    with pytest.raises(DoclingConversionError) as error: create_docling_converter(tmp_path)
    assert error.value.kind is DoclingConversionFailureKind.CONVERTER_CONSTRUCTION
    assert isinstance(error.value.__cause__,XbrlConfigurationError)

def test_factory_uses_explicit_validated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：合成部署和环境；返回：无；异常：显式合法输入拒绝时断言失败。"""
    config,_,_=_deployment(tmp_path); monkeypatch.setenv('DAYU_XBRL_CONFIG',str(config))
    assert create_docling_converter(tmp_path/'workspace') is not None


@pytest.mark.parametrize(('mutation', 'cause_type'), _ZIP_INPUT_FAILURES)
def test_real_zip_input_error_is_typed_construction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str, cause_type: type[Exception]) -> None:
    """参数：完整摘要吻合的真实坏 ZIP；返回：无；异常：公开初始化分类或原因链丢失则失败。"""
    config,taxonomy,manifest=_deployment(tmp_path)
    _corrupt_archive(config,taxonomy,manifest,mutation=mutation)
    monkeypatch.setenv('DAYU_XBRL_CONFIG',str(config))
    with pytest.raises(DoclingConversionError) as error:create_docling_converter(tmp_path/'workspace')
    assert error.value.kind is DoclingConversionFailureKind.CONVERTER_CONSTRUCTION
    cause=error.value.__cause__
    assert isinstance(cause,XbrlConfigurationError) and type(cause.__cause__) is cause_type
    assert str(cause.__cause__)
