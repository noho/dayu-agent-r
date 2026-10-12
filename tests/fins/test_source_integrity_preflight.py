"""inventory 纯拒绝检查与 selected repair 权限分离的 owner contract。"""

import pytest
from dayu.fins.domain.document_models import SourceDocumentRevision
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage.source_integrity import (
 SourceIntegrityClassification,SourceIntegrityStatus,SourceIntegrityReason,SourceIntegrityPreflightError,
 SourceIntegrityPreflightReason,validate_source_integrity_inventory,classify_source_integrity_preflight,
 SelectedSourceRepairRequired,NoSourceRepairRequired,
)


def _item(document_id: str,status: SourceIntegrityStatus,kind: SourceKind=SourceKind.FILING) -> SourceIntegrityClassification:
    """参数：身份/状态/类别。返回：合法分类。异常：构造错误原样。"""
    return SourceIntegrityClassification('600519',kind,document_id,None if status in (SourceIntegrityStatus.UNSAFE,SourceIntegrityStatus.MISSING) else SourceDocumentRevision('r'),status,
        (SourceIntegrityReason.META_UNTRUSTED,) if status is SourceIntegrityStatus.UNSAFE else (SourceIntegrityReason.SIZE_MISMATCH,) if status is SourceIntegrityStatus.REPAIR_REQUIRED else ())


@pytest.mark.parametrize('status',(SourceIntegrityStatus.COMPLETE,SourceIntegrityStatus.MISSING,SourceIntegrityStatus.REPAIR_REQUIRED))
def test_inventory_has_no_repair_authorization(status: SourceIntegrityStatus) -> None:
    """参数：clean/唯一 repair 状态。返回：无。异常：早期check错误授予修复断言失败。"""
    inventory=(_item('A',status),)
    assert validate_source_integrity_inventory(inventory) is None
    if status is SourceIntegrityStatus.REPAIR_REQUIRED:
        with pytest.raises(SourceIntegrityPreflightError) as raised:classify_source_integrity_preflight(inventory,accepted_filing_ids=frozenset(),rejected_filing_ids=frozenset())
        assert raised.value.reason is SourceIntegrityPreflightReason.UNSELECTED_REPAIR_REQUIRED
        assert isinstance(classify_source_integrity_preflight(inventory,accepted_filing_ids=frozenset({'A'}),rejected_filing_ids=frozenset()),SelectedSourceRepairRequired)
        with pytest.raises(SourceIntegrityPreflightError) as raised:classify_source_integrity_preflight(inventory,accepted_filing_ids=frozenset(),rejected_filing_ids=frozenset({'A'}))
        assert raised.value.reason is SourceIntegrityPreflightReason.SELECTED_REJECTED_REPAIR_REQUIRED
    else:assert isinstance(classify_source_integrity_preflight(inventory,accepted_filing_ids=frozenset(),rejected_filing_ids=frozenset()),NoSourceRepairRequired)


def test_unsafe_priority_and_material_repair() -> None:
    """参数：无。返回：无。异常：优先序或 material 写权限漂移断言失败。"""
    repairs=(_item('A',SourceIntegrityStatus.REPAIR_REQUIRED),_item('B',SourceIntegrityStatus.REPAIR_REQUIRED))
    with pytest.raises(SourceIntegrityPreflightError) as raised:validate_source_integrity_inventory(repairs)
    assert raised.value.reason is SourceIntegrityPreflightReason.MULTIPLE_REPAIR_REQUIRED
    with pytest.raises(SourceIntegrityPreflightError) as raised:validate_source_integrity_inventory((*repairs,_item('C',SourceIntegrityStatus.UNSAFE)))
    assert raised.value.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    material=(_item('M',SourceIntegrityStatus.REPAIR_REQUIRED,SourceKind.MATERIAL),)
    assert validate_source_integrity_inventory(material) is None
    with pytest.raises(SourceIntegrityPreflightError):classify_source_integrity_preflight(material,accepted_filing_ids=frozenset({'M'}),rejected_filing_ids=frozenset())
