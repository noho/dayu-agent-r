# UF-FIX06 Slice 3 code re-review

## 元数据

- Reviewer：AgentMiMo
- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：3
- 基线：`affa665b`
- 输入裁决：`docs/reviews/uf-fix06-slice3-code-review-adjudication-20260815.md`
- 输入 fix artifact：`docs/gateflow/uf-fix06-slice3-code-fix-20260815.md`
- 日期：2026-08-15
- 结论：`PASS` — blocking finding 为 0

## 核验范围

逐项核验 accepted A1–A5 的修复证据，并执行新回归、owner drift、scope/stop-condition 检查。

## A1：failure kind 文档遗漏 USAGE

**裁决要求：** `FinsUploadFailureReason.kind` 的属性说明必须列出 usage、content、storage、runtime。

**证据：** `upload_failure.py:80`

```python
kind: usage、content、storage 或 runtime 分类。
```

旧版为 `content、storage 或 runtime 分类`，已补齐 `usage`。

**结论：** ✅ 已修复。属性说明覆盖全部 4 个 closed kind。

## A2：转换 helper 漏报 typed cancellation

**裁决要求：** `_build_pending_assets` 的 Raises 明确列出 `DoclingConversionCancelledError`，并把 material `DoclingConversionError` 透传与取消语义分开说明。

**证据：** `docling_upload_service.py:747-756`

```python
Raises:
    DoclingConversionCancelledError: 转换前或两次转换之间观察到取消时抛出。
    FinsUploadFailureError: filing Docling 转换失败时抛出。
    DoclingConversionError: material Docling 转换失败时原样抛出。
    RuntimeError: 未产生主 Docling 文件时抛出。
    ValueError: preparation 与 ``original_assets`` 不一致时抛出。
```

旧版只列 `FinsUploadFailureError`、`RuntimeError`、`ValueError`。现在 cancellation、filing wrapped failure、material typed failure 和 invariant failure 四类分别列出。

**结论：** ✅ 已修复。Raises 文档完整覆盖所有异常路径。

## A3：新增 loop-top cancel 分支缺直接反例

**裁决要求：** 增加 prepare 阶段 token 翻转测试，至少覆盖 material 两文件在第二个 converter input 前取消；断言 cancelled plan、空 file events、前一转换允许完成但所有 partial assets/events 被丢弃、零 batch、零发布。

**证据：** `test_docling_upload_service.py` — `test_prepare_material_cancellation_before_second_conversion_discards_partial_work`

关键断言：
```python
cancellation = _CancelOnNthCheck(cancel_at=4)
prepared = _prepare_material_for_admission_test(service=context.service, files=files, cancellation=cancellation)

assert isinstance(prepared, UploadOperationResult)
assert prepared.status == "cancelled"
assert prepared.file_events == []          # 空 file events
assert prepared.stored_file_count == 0     # 零存储
assert calls == ["first.pdf"]              # 首项已调用
assert context.batching_repository.begin_calls == 0  # 零 batch
assert published_tree_sha256(tmp_path, "AAPL") == {}  # 零发布
with pytest.raises(FileNotFoundError):     # 零 source meta
    context.source_repository.get_source_meta(...)
```

**取消机制验证：**
- `_CancelOnNthCheck(cancel_at=4)`：第 4 次 `is_cancelled()` 返回 True
- `_build_pending_assets` 中循环：首项完成转换后（含 2 次 cancel check + 1 次在循环顶 + 1 次在转换前），第二项循环顶的 cancel check 触发 `DoclingConversionCancelledError`
- `prepare_upload` 捕获 `DoclingConversionCancelledError` 返回 cancelled result
- 未进入 `_PreparedAssetMutation` 构造，因此 publication batch 不开启

**batch 跟踪验证：** `_BatchIdentityUploadBatchingRepository` 记录 `begin_calls`，断言为 0 证实 prepare 阶段无 batch 操作。

**结论：** ✅ 已修复。cancelled plan、空 events、首项转换完成但 partial 丢弃、零 batch/零发布/零 source meta 全部覆盖。

## A4：material 第 N 个转换失败缺原子性反例

**裁决要求：** 增加 `[ok.pdf, corrupt.docx]` material 反例，断言调用顺序、第二项 typed conversion failure、前序派生资产不发布；至少一条 workflow 级断言既有 catch-all 产生 content failure，且不把未经 owner 证明的文件名错误归给 failure。

### Service 层反例

**证据：** `test_docling_upload_service.py` — `test_prepare_material_nth_conversion_failure_discards_partial_work`

```python
cause = DoclingConversionError(DoclingConversionFailureKind.CONVERTER_EXECUTION, ..., 19)
context.service._docling_converter = _SelectiveFailingDoclingConverter(failing_name="corrupt.docx", ...)

with pytest.raises(DoclingConversionError) as exc_info:
    _prepare_material_for_admission_test(service=context.service, files=files)

assert exc_info.value is cause                  # 异常 identity 保持
assert calls == ["ok.pdf", "corrupt.docx"]      # 两项都调用
assert context.batching_repository.begin_calls == 0  # 零 batch
assert published_tree_sha256(tmp_path, "AAPL") == {}  # 零发布
with pytest.raises(FileNotFoundError):           # 零 source meta
    context.source_repository.get_source_meta(...)
```

Service 保留 `DoclingConversionError` 原样抛出（不 wrapping 为 `FinsUploadFailureError`），这与 `_build_pending_assets` 的 Raises 文档一致。

### Workflow 层反例

**证据：** `test_sec_pipeline_upload_material_stream.py` — `test_upload_material_nth_conversion_failure_is_content_terminal_without_source_publication`

```python
pipeline = SecPipeline(..., docling_converter=_FailingMaterialDoclingConverter(failing_name="corrupt.docx", ...))

events = [event async for event in pipeline.upload_material_stream(...)]

assert calls == ["ok.pdf", "corrupt.docx"]
assert result["status"] == "failed"
assert result["stored_file_count"] == 0
assert result["failure"] == {
    "kind": "content",
    "code": "docling_converter_execution",
    "message": "文件无法解析或已损坏，请检查文件后重试",
    "retry_hint": "请确认文件可正常打开并重新上传",
    "file_label": None,                         # 不伪造文件归属
}
with pytest.raises(FileNotFoundError):           # 零 source 发布
    pipeline._source_repository.get_source_meta(...)
assert not tuple((tmp_path / "portfolio" / "AAPL" / "materials").glob("*"))  # 零 material 目录
```

workflow `except Exception` 捕获 `DoclingConversionError`，经 `fins_upload_failure_from_exception` 投影为 `content` terminal。`file_label=None` 因为 material 转换异常不携带文件归属信息，workflow 不伪造。

**结论：** ✅ 已修复。Service 层保持 typed exception identity，workflow 层投影 content terminal 且不伪造 file attribution，零发布全覆盖。

## A5：closed public failure fact 本身未校验 kind/code

**裁决要求：** `FinsUploadFailureReason.__post_init__` 自身必须校验 enum 具体类型与 `_FAILURE_KIND_BY_CODE` 一致性；code 分组必须显式验证互斥与完整；JSON parser 继续复用同一 mapping。补 direct-construction mismatch/open-type 与 mapping completeness/disjointness contract tests。

### Production 修复

**证据 1 — `__post_init__` 校验：** `upload_failure.py:107-113`

```python
if type(self.kind) is not FinsUploadFailureKind:
    raise TypeError("failure.kind 必须是 FinsUploadFailureKind")
if type(self.code) is not FinsUploadFailureCode:
    raise TypeError("failure.code 必须是 FinsUploadFailureCode")
expected_kind = _FAILURE_KIND_BY_CODE[self.code]
if self.kind is not expected_kind:
    raise ValueError("failure.kind 与 failure.code 不一致")
```

`type(x) is not EnumClass` 精确拒绝 `cast(EnumClass, "string_value")` 等伪装值，比 `isinstance` 更严格。

**证据 2 — 分组互斥/完整 guard：** `upload_failure.py:185-203`

```python
_FAILURE_CODES_BY_KIND: Final[...] = {kind: codes_set, ...}
# 完整性：所有 kind 都有分组
if frozenset(_FAILURE_CODES_BY_KIND) != frozenset(FinsUploadFailureKind):
    raise RuntimeError("upload failure kind 分组必须完整")
# 互斥性：code 不重复出现在多个 kind
_GROUPED_FAILURE_CODE_COUNT = sum(len(codes) for codes in ...)
_ALL_GROUPED_FAILURE_CODES = frozenset(code for codes in ... for code in codes)
if _GROUPED_FAILURE_CODE_COUNT != len(_ALL_GROUPED_FAILURE_CODES):
    raise RuntimeError("upload failure code 分组必须互斥")
# 完整性：所有 code 都被分组
if _ALL_GROUPED_FAILURE_CODES != frozenset(FinsUploadFailureCode):
    raise RuntimeError("upload failure code 分组必须完整")
# 统一 mapping 从分组派生，不复制
_FAILURE_KIND_BY_CODE = {code: kind for kind, codes in _FAILURE_CODES_BY_KIND.items() for code in codes}
```

三重 guard 在 module-load 时执行：kind 完整 → code 互斥 → code 完整 → mapping 从分组单源派生。

**证据 3 — parser 复用同一 mapping：** `upload_failure.py:369`

```python
expected_kind = _FAILURE_KIND_BY_CODE[code]
```

parser 不复制判断逻辑，直接使用同一 `_FAILURE_KIND_BY_CODE`。

### Test 证据

**test_upload_failure.py — direct construction mismatch：**

```python
@pytest.mark.parametrize(("kind", "code"), (
    (FinsUploadFailureKind.CONTENT, FinsUploadFailureCode.UNSUPPORTED_UPLOAD_FORMAT),
    (FinsUploadFailureKind.USAGE, FinsUploadFailureCode.DOCLING_CONVERTER_EXECUTION),
    (FinsUploadFailureKind.RUNTIME, FinsUploadFailureCode.STORAGE_IO),
))
def test_upload_failure_reason_direct_construction_rejects_kind_code_mismatch(kind, code):
    with pytest.raises(ValueError, match="failure.kind 与 failure.code 不一致"):
        FinsUploadFailureReason(kind=kind, code=code, ...)
```

三组跨-kind 错配全部被 `__post_init__` 拒绝。

**test_upload_failure.py — open enum values：**

```python
def test_upload_failure_reason_direct_construction_rejects_open_enum_values():
    with pytest.raises(TypeError, match="failure.kind 必须是 FinsUploadFailureKind"):
        FinsUploadFailureReason(kind=cast(FinsUploadFailureKind, "usage"), ...)
    with pytest.raises(TypeError, match="failure.code 必须是 FinsUploadFailureCode"):
        FinsUploadFailureReason(code=cast(FinsUploadFailureCode, "unsupported_upload_format"), ...)
```

`cast` 伪装的 open 字符串被 `type(x) is not` 精确拒绝。

**test_upload_failure.py — mapping contract：**

```python
def test_upload_failure_kind_code_mapping_is_disjoint_complete_and_single_source():
    groups = upload_failure._FAILURE_CODES_BY_KIND
    grouped_codes = tuple(code for codes in groups.values() for code in codes)
    expected_mapping = {code: kind for kind, codes in groups.items() for code in codes}
    assert frozenset(groups) == frozenset(FinsUploadFailureKind)       # kind 完整
    assert len(grouped_codes) == len(frozenset(grouped_codes))         # code 互斥
    assert frozenset(grouped_codes) == frozenset(FinsUploadFailureCode)  # code 完整
    assert upload_failure._FAILURE_KIND_BY_CODE == expected_mapping    # mapping 同源
```

测试从 `_FAILURE_CODES_BY_KIND` 重新派生 mapping 并与 `_FAILURE_KIND_BY_CODE` 比较，验证单源性。

**结论：** ✅ 已修复。`__post_init__` 校验 enum 具体类型与 kind/code 一致性；分组 guard 验证互斥与完整；parser 复用同一 mapping；direct-construction mismatch、open-type 与 mapping contract 测试全覆盖。

## 新回归检查

### 既有测试未退化

- 新增反例聚焦 suite：84 passed, 3 warnings
- Slice 3 focused matrix（实现文档声明）：1235 passed, 1 skipped, 3 warnings
- 全量 coverage matrix（实现文档声明）：1338 passed, 1 skipped, 3 warnings

### `_FAILURE_CODES_BY_KIND` 重构未引入 mapping 漂移

旧代码使用内联 dict comprehension：
```python
{**{code: USAGE for code in _USAGE_FAILURE_CODES}, **{code: CONTENT for ...}, ...}
```

新代码使用 `_FAILURE_CODES_BY_KIND` 分组 + 派生 mapping：
```python
_FAILURE_CODES_BY_KIND = {kind: codes_set, ...}
_FAILURE_KIND_BY_CODE = {code: kind for kind, codes in _FAILURE_CODES_BY_KIND.items() for code in codes}
```

两者的数学等价性由 module-load guard（互斥 + 完整）和 `test_upload_failure_kind_code_mapping_is_disjoint_complete_and_single_source`（同源比较）双重保证。

### `type(x) is not` 比旧 `isinstance` 更严格

旧 `__post_init__` 无 kind/code 校验。新增 `type(x) is not EnumClass` 精确拒绝 `cast` 伪装值，比 `isinstance` 更严格。所有通过 `fins_upload_failure_from_exception` 正常路径构造的 reason 使用 enum member literal，不受影响。

### A3 cancel_at=4 计数与实际 cancel check 位置匹配

`_CancelOnNthCheck(cancel_at=4)` 的 4 次检查：
1. `prepare_upload` L301：`if _is_cancelled(cancellation)` — 第 1 次
2. `prepare_upload` L323：`if _is_cancelled(cancellation)` — 第 2 次
3. `_build_pending_assets` L768 循环顶：`if _is_cancelled(cancellation)` — 第 3 次（首项进入循环前）
4. 首项转换完成后，第二项循环顶 L768：`if _is_cancelled(cancellation)` — 第 4 次 → True → raise

但 `_FakeDoclingConverter` 无 cancel check，所以首项转换完成后再检查。`cancel_at=4` 确保首项转换完成但第二项未开始。测试断言 `calls == ["first.pdf"]` 验证此计数正确。

## Owner drift 检查

### failure owner 唯一性 ✅

- `FinsUploadFailureReason.__post_init__` 是 kind/code 一致性的唯一校验点
- `_FAILURE_CODES_BY_KIND` 是分组的唯一 source of truth
- `_FAILURE_KIND_BY_CODE` 从 `_FAILURE_CODES_BY_KIND` 单源派生
- `upload_failure_reason_from_json` 复用 `_FAILURE_KIND_BY_CODE`
- `fins_upload_failure_from_exception` 使用 enum member literal 构造，由 `__post_init__` 校验

### Service selection owner 唯一性 ✅

- `upload_format_contract.FinsUploadFilingFiles` / `FinsUploadMaterialFiles` 是 typed selection 唯一 owner
- `_prepare_upload_selection` 是 source_kind/selection 类型收窄的唯一校验点
- Service 只消费 closed typed union，不重建 selection

### primary_document owner 唯一性 ✅

- `_build_pending_assets` 从首次成功转换直接产生 `primary_document`
- `_PreparedAssetMutation` 携带到 `_store_upload_assets`
- `_create_source_document` 写入 source meta
- 不再有 `_pick_primary_docling_file` 扫描 stored entries

## Scope/Stop-condition 检查

### Scope 边界 ✅

- 只修改 Slice 3 allowed production/test files + implementation/code-fix artifacts
- 未修改旧 review artifacts、README、registry、oracle/scenario、design doc、冻结 evidence
- 未运行 UF-PF06/UF-PF12
- 未 commit

### Stop condition ✅

- 无 storage schema 变更
- 无原子 batch 协议变更
- 无显式 primary 或 batch association 变更
- 无 collision stop condition 触发
- material empty、delete+files、collision 保持既有 residual 分类

## Findings

无 blocking findings。

无 non-blocking findings。A1–A5 全部按裁决要求闭环，无新增问题。

## Residual risks（继承自裁决与实现文档）

- material empty 文件：保持 converter-owned 行为，不在本 work unit 扩展 failure code。
- delete + files 历史不一致：用户明确排除的其它 upload work unit。
- collision、显式 primary、batch association：assigned to UF-FIX07/后续 work unit。
- README 旧引用：assigned to Slice 4。
- 真实格式矩阵与 Docling integration：covered by UF-PF06/UF-PF12，本轮按约束未运行。
- 未分类 residual risk：无。

## Verdict

**PASS** — blocking finding 为 0。

Accepted A1–A5 全部按裁决要求闭环：
- A1：failure kind 文档补齐 `usage`
- A2：`_build_pending_assets` Raises 完整覆盖四类异常
- A3：material 两文件第二项前取消反例覆盖 cancelled plan、空 events、零 batch/发布/source
- A4：material 第 N 项转换失败在 Service 保持 typed exception、workflow 投影 content terminal 且不伪造 file attribution、零发布
- A5：reason constructor 校验 enum 具体类型与 kind/code 一致性；分组互斥/完整 guard；parser 复用同一 mapping；direct-construction/open-type/mapping contract 测试全覆盖

无新回归、无 owner drift、无 scope 越界。
