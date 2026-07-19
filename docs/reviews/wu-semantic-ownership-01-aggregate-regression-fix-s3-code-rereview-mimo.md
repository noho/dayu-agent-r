# WU-SEMANTIC-OWNERSHIP-01 Slice 3 Final Code Re-Review — AgentMiMo（第一路）

## Verdict

`PASS / NO_NEW_MATERIAL_FINDING / INITIAL_FINDINGS_CONFIRMED_ZERO / READY_FOR_CONTROLLER_ADJUDICATION`。

## 1. Review identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 3。
- Review type：第一路完整 final re-review；覆盖 Controller 锁定的全部 9-path target，不限于 zero-change artifact。
- Accepted base：`9ad5711e20dd35d5a0cdc0cf79067333ff3b3daf`。
- 证据链：
  - Initial MiMo review：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-mimo.md`
  - DS review：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-ds.md`
  - Controller adjudication：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-controller-adjudication.md`
  - Codex zero-change artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-fix-codex.md`
  - Controller zero-change validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-fix-controller-validation.md`
  - Implementation Controller validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-implementation-controller-validation.md`
  - Accepted plan commit Controller validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-accepted-plan-commit-controller-validation.md`

## 2. Review lock 独立复核

```text
tracked binary diff SHA-256 = de39190c66121255ddd69fdb3418b9ad8bca74e455a98ff94f3fe2e9e08fb206  ✓ MATCH
9-path content-manifest SHA-256 = 83cddc11fc114531972ad43db8f55080c0f53803d3eed76ddeb93afacf3f8b28  ✓ MATCH
9-path status-manifest SHA-256 = 2c7b84432af3b37521b1618a4058bee851f02300adf11df75be1634cf7d21573  ✓ MATCH
```

三个 locks 与 implementation Controller validation、initial code review、Codex zero-change artifact 与 Controller zero-change validation 完全一致。

## 3. 9-path per-file content hash 独立复核

| Path | Expected SHA-256（Codex artifact） | Actual SHA-256 | Status |
|---|---|---|---|
| `dayu/documents/processors/docling_processor.py` | `e2ab00fd...fd649` | `e2ab00fd...fd649` | MATCH |
| `dayu/fins/README.md` | `adcfd166...2525` | `adcfd166...2525` | MATCH |
| `dayu/fins/processors/sec_form_section_common.py` | `9f66893b...45a2` | `9f66893b...45a2` | MATCH |
| `tests/documents/test_processors.py` | `4dedb3ac...c65f` | `4dedb3ac...c65f` | MATCH |
| `tests/fins/test_sec_pipeline_download.py` | `840feae7...eae6` | `840feae7...eae6` | MATCH |
| `tests/fins/test_processor_read_consistency.py` | `0ee788c2...40c1` | `0ee788c2...40c1` | MATCH |
| `tests/fins/test_fins_ingestion_tools.py` | `6ece9288...f747` | `6ece9288...f747` | MATCH |
| `tests/host/test_effective_execution_config.py` | `e3a85cad...6acf` | `e3a85cad...6acf` | MATCH |
| `tests/runtime/test_argparse_exit.py` | `3aa60784...3f3d` | `3aa60784...3f3d` | MATCH |

逐文件 hash 与 Codex zero-change artifact §4.1 完全一致。S3-STOP-F01、S3-STOP-F02 实现、全部测试与 README 均未被 fix gate 改写。

## 4. Protected zero-diff paths 独立复核

```text
dayu/documents/processors/base.py           : zero diff ✓
dayu/fins/processors/sec_processor.py       : zero diff ✓
dayu/fins/processors/ten_k_processor.py     : zero diff ✓
dayu/fins/processors/ten_q_processor.py     : zero diff ✓
dayu/fins/processors/bs_ten_k_processor.py  : zero diff ✓
dayu/fins/processors/bs_ten_q_processor.py  : zero diff ✓
```

marker producer contract、`SecProcessor` unsupported-marker contract、10-K/10-Q/BS subclass 行为均未修改。

## 5. S3-STOP-F01 Docling Caption Resolver 逐行复核

### 5.1 Caption 解析路径

审查 `dayu/documents/processors/docling_processor.py:_extract_table_caption` (L1174-1207)：

| Plan 要求 | 代码证据 | 判定 |
|---|---|---|
| 使用 typed `RefItem.cref`，不读 JSON `$ref` | L1194: `caption_ref.cref` | ✓ |
| root ref `#` 在 resolve 前以命名常量跳过 | L51: `_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"`；L1194: `caption_ref.cref == _DOCLING_DOCUMENT_ROOT_REF` | ✓ |
| 只在 resolve 周围捕获 `AttributeError`/`IndexError` | L1197-1198: `except (AttributeError, IndexError):` | ✓ |
| resolve 到非 TextItem 时跳过 | L1200: `isinstance(resolved, TextItem)` | ✓ |
| 规范化空白、精确大小写去重、保留首次出现 | L1202: `_normalize_whitespace(resolved.text)`；L1203: `caption in seen`；L1205: `seen.add(caption)` | ✓ |
| 多 caption 单空格连接，无剩余返回 None | L1207: `" ".join(captions) or None` | ✓ |
| `_build_tables` 传入同源 `DoclingDocument` | L630: `caption = _extract_table_caption(table_item, document)` — `document` 即 `_build_tables` 接收的同一 `DoclingDocument`（L601, L630） | ✓ |
| 三个 public consumers 共享 `_TableBlock.caption` | `list_tables()` L279: `caption=table.caption`；`read_table()` L361: `caption=table.caption`；`_build_page_tables()` L1501: `caption=table.caption` | ✓ |

**新增代码禁止模式扫描**：

```text
hasattr/getattr (in _extract_table_caption)  : zero match ✓
except Exception (in _extract_table_caption) : zero match ✓
warning/logger (in _extract_table_caption)   : zero match ✓
```

`_DOCLING_DOCUMENT_ROOT_REF` 为模块级 `Final[str]` 常量。`TextItem` 在模块级从 `docling_core.types.doc.document` 导入，非 lazy import、非 `TYPE_CHECKING`。

### 5.2 Docling caption tests 8-node matrix

| Test | 覆盖语义 | 判定 |
|---|---|---|
| `test_docling_json_processor_projects_referenced_table_caption` | 单 caption 引用传播 | ✓ |
| `test_docling_json_processor_preserves_normalized_unique_caption_order` | 顺序/去重/规范化/大小写敏感 | ✓ |
| `test_docling_json_processor_returns_none_for_empty_or_blank_captions` | 空列表、全空白 | ✓ |
| `test_docling_json_processor_skips_dangling_caption_references` | 未知 collection、越界 index | ✓ |
| `test_docling_json_processor_skips_document_root_caption_reference` | root ref `#` 跳过 | ✓ |
| `test_docling_json_processor_rejects_model_invalid_caption_reference` | 非法 `$ref` loader 边界 | ✓ |
| `test_docling_json_processor_skips_non_text_caption_references` | 非 TextItem 跳过 | ✓ |
| `test_docling_json_processor_propagates_caption_to_public_table_views` | 三个 public consumer 一致性 | ✓ |

全部经真实 `DoclingDocument` 构造、`save_as_json()` 序列化、`DoclingProcessor` load 后断言 public 结果。测试使用 `_ref_item("#/texts/N")` 构造 `RefItem`——通过 `RefItem.model_validate({"$ref": ref})` 走 Pydantic deserialization，正确映射 `$ref`（JSON alias）到 Python `cref` 字段。

### 5.3 Adversarial failure pass

| 反例 | 预期行为 | 判定 |
|---|---|---|
| captions 为空列表 | 循环不执行，返回 None | ✓ |
| 所有 refs 为 root ref `#` | 全部 continue，返回 None | ✓ |
| 所有 refs 为 dangling | 全部 continue，返回 None | ✓ |
| 混合 valid + root + dangling + non-text | 只有 valid TextItem 保留 | ✓ |
| resolve 抛出 `RuntimeError` | 异常向上传播（不捕获） | ✓ |
| TextItem.text 经规范化后为空 | 跳过该 ref | ✓ |
| 大小写不同的相同词 | 分别保留（case-sensitive） | ✓ |

**S3-STOP-F01 verdict**：全部 plan 约束已验证通过。Caption resolver 是 `_TableBlock.caption` 的唯一 producer；三个 public consumer 均直接消费同一字段，无重算或下游补偿。

## 6. S3-STOP-F02 Virtual Section Publication State Machine 逐行复核

### 6.1 State 定义与 transition owner

审查 `dayu/fins/processors/sec_form_section_common.py`：

**状态枚举**（L254-259）：`_VirtualSectionPublicationMode` 为 owner-private enum，不暴露到 public contract。

**唯一 transition owner**：`_refresh_virtual_section_state()`（L453-508）是唯一可提交 terminal transition 的方法。

**Transition 规则验证**：

| Transition | 代码证据 | 判定 |
|---|---|---|
| BUILDING → VIRTUAL_PUBLISHED | L504-508：所有验证通过后调用 `_publish_virtual_section_state()` | ✓ |
| BUILDING → BASE_FALLBACK_PUBLISHED | L499-500：missing_refs 非空时 `_publish_base_fallback_state()`；L470-471：空 virtual_sections 时 `_publish_base_fallback_state()` | ✓ |
| VIRTUAL_PUBLISHED → VIRTUAL_PUBLISHED | L462-467：identity multiset 校验后重建映射 | ✓ |
| BASE_FALLBACK_PUBLISHED → BASE_FALLBACK_PUBLISHED | L456-457：直接 return（幂等 no-op） | ✓ |

### 6.2 Contradiction-first 验证顺序

`_refresh_virtual_section_state()` 的验证顺序（L469-508）：

1. **Base table ref 校验**（L474）：`_validate_base_table_refs()` — 缺失/空/重复 → `ValueError`
2. **Raw marker ref 校验**（L477-478）：`_validate_raw_marker_refs()` — dangling/重复 → `ValueError`
3. **Virtual section tree 校验**（L480）：`_validate_virtual_section_tree()` — ref 重复/父子悬挂/双向矛盾 → `ValueError`
4. **Candidate mapping 构建**（L481-483）：`_assign_tables_to_virtual_sections()` — 同一 marker 多归属 → `ValueError`
5. **Section table refs 投影**（L485-489）：`_build_candidate_section_table_refs()` — 悬挂 section_ref → `ValueError`
6. **双向一致性校验**（L490-495）：`_validate_candidate_table_mapping()` — 悬挂/重复/双向不一致 → `ValueError`
7. **Incomplete proof 判定**（L497-501）：`missing_refs = base_table_ref_set - set(candidate_mapping)` 非空 → whole-base fallback

步骤 1-6 任一失败即 `ValueError` fail-closed；步骤 7 仅在无矛盾时触发 fallback。**incomplete + dangling 同时存在时，dangling 在步骤 2 优先 fail-closed**。

### 6.3 Atomic publication

- `_publish_base_fallback_state()`（L510-526）：清空 `_virtual_sections`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`，设 `BASE_FALLBACK_PUBLISHED`。✓
- `_publish_virtual_section_state()`（L528-553）：一次性更新 `section.table_refs`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`，设 `VIRTUAL_PUBLISHED`。✓
- 验证期间不提前修改 published state。✓

### 6.4 Five public consumers with typed mode guard

| Consumer | 代码位置 | Guard | Base 委托 |
|---|---|---|---|
| `list_sections()` | L987 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().list_sections()` |
| `list_tables()` | L958 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().list_tables()` |
| `get_section_title()` | L1014 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().get_section_title(ref)` |
| `read_section()` | L1033 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().read_section(ref)` |
| `search()` | L1079 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().search(...)` |

精确五个 consumer，统一使用 `mode is not VIRTUAL_PUBLISHED` guard。无单独反推状态、按可用性静默过滤或位置猜测。

### 6.5 `_assign_tables_to_virtual_sections` 返回候选映射

- 只返回 `candidate_mapping`，不修改 published state。✓
- 标题或范围不能唯一证明归属时保留未映射事实，由 refresh owner 统一决定 fallback。✓
- `_record_candidate_table_mapping` 同一 marker 多归属 → `ValueError`。✓

### 6.6 `_remap_tables_to_deepest_virtual_sections`

- 只操作同一个 owner-local `candidate_mapping`（参数 `table_ref_to_virtual_ref`）。✓
- `list(table_ref_to_virtual_ref.items())` 创建迭代副本，循环中直接修改原 dict 的 value——正确，只修改已有 key 的 value。✓
- 最深子章节查找：`_find_deepest_virtual_section_ref()` 同层多命中 → `ValueError`。✓
- 最终双向校验：`_validate_candidate_table_mapping()` 在 remap 之后执行。✓

### 6.7 Deleted forbidden patterns

```text
_filter_table_refs_by_availability       : zero match ✓
_assign_unmapped_tables_by_position      : zero match ✓
fallback_ref / last_known_ref            : zero match ✓
_collect_available_table_refs_from_base  : zero match ✓
```

`SecProcessor` import 已移除（L48 删除行）；剩余 `SecProcessor` 引用仅在 docstring（L808-809, L1893），非代码引用。

### 6.8 禁止模式扫描（S3-STOP-F02 新增核心逻辑）

```text
hasattr/getattr (in new functions)        : zero match ✓
except Exception (in new functions)       : zero match ✓
warning/logger (in new functions)         : zero match ✓
```

既有代码中的 8 处 `except Exception`（L621, L635, L676, L691, L695, L826, L870, L1218）全部位于 S3-STOP-F02 之前的既有基础设施代码，不在新增 hunk 中。

### 6.9 零表格文档

`base_table_refs = ()` → `base_table_ref_set = set()` → `_validate_raw_marker_refs` 无 dangling → `_validate_candidate_table_mapping` 检查空集 → `missing_refs = set() - set() = ∅` → `_publish_virtual_section_state()` 发布 `VIRTUAL_PUBLISHED`。✓

### 6.10 首次/二次 refresh 幂等

- `_postprocess_virtual_sections()` 默认空操作。✓
- `expand_ten_k_virtual_sections_content()` / `expand_ten_q_virtual_sections_content()` 以 `if not full_text or not virtual_sections: return` 开头；fallback 清空 `_virtual_sections` 后二次调用自然 no-op。✓
- `BASE_FALLBACK_PUBLISHED` → direct return。✓
- `VIRTUAL_PUBLISHED` → identity multiset check → maintain。✓

**S3-STOP-F02 verdict**：全部 plan 约束已验证通过。

## 7. Tests 完整性复核

### 7.1 S3-STOP-F02 六类反例矩阵

| Plan 要求的反例类别 | 覆盖测试 | 判定 |
|---|---|---|
| 1. Public 10-K + unsupported marker + base table | `test_ten_k_public_processor_assigns_tables_without_marker_capability` — 真实 `TenKFormProcessor`，合法 HTML，`_assert_processor_matches_base_public_contract` 逐值验证 | ✓ |
| 2. Complete mapping + deepest remap | `test_virtual_section_complete_mapping_publishes_deepest_bidirectional_candidate` — 两表一子章节，remap 到最深，二次 refresh 幂等 | ✓ |
| 3. Incomplete proof（两子类） | `test_virtual_section_incomplete_proof_publishes_whole_base_fallback` — (a) partial: base 两表 marker 只证一表；(b) ambiguous: range/title 不能唯一证明归属 | ✓ |
| 4. Duplicate/dangling/contradictory + mixed priority | `test_virtual_section_contradictions_fail_before_incomplete_fallback` — 五种子类，incomplete+dangling 优先 fail-closed；`test_virtual_section_refresh_fails_closed_for_duplicate_or_dangling_refs` | ✓ |
| 5. Zero-table document | `test_virtual_section_zero_table_document_publishes_virtual_projection` — base_table_refs=()，发布 virtual，空 tables | ✓ |
| 6. 10-K/10-Q second postprocess idempotence | `test_ten_q_public_processor_keeps_base_fallback_through_second_postprocess`；`test_report_form_second_postprocess_keeps_base_fallback_terminal`（parametrize 四 processor）；`test_both_ten_q_paths_preserve_object_ref_multiset_and_refresh`；`test_both_ten_k_paths_migrate_to_shared_refresh_without_behavior_drift`；`test_ten_q_path_rejects_expansion_that_creates_section` | ✓ |

### 7.2 公共 processor 测试 oracle pattern

`_assert_processor_matches_base_public_contract`（L1810-1843）逐字段比较 `SecProcessor.list_sections(processor)`（unbound call，绕过 mixin override）与 `processor.list_sections()`（走 mixin guard），并在 section/table/title/read/search 五个维度逐值比较。正确验证 "fallback 是同源 base publication"。

`_assert_virtual_harness_matches_base_contract`（L1031-1059）对 owner harness 做同样验证。

### 7.3 Protected test files

| Test file | Entry hash | Current hash | Status |
|---|---|---|---|
| `tests/fins/test_fins_ingestion_tools.py` | `6ece9288...f747` | `6ece9288...f747` | MATCH |
| `tests/host/test_effective_execution_config.py` | `e3a85cad...6acf` | `e3a85cad...6acf` | MATCH |
| `tests/runtime/test_argparse_exit.py` | `3aa60784...3f3d` | `3aa60784...3f3d` | MATCH |

## 8. README 复核

`dayu/fins/README.md` 新增两行准确描述：
- atomic validation / publication ✓
- whole-base fallback ✓
- contradiction fail-closed ✓
- terminal idempotence ✓
- 五个 public consumers 统一 mode ✓
- no silent filtering, no position guessing ✓

根 `README.md`、`dayu/README.md`、`tests/README.md` 无 diff（`NO_UPDATE`）。判断正确。

## 9. Controller adjudication observations 确认

全部 observations 按 Controller no-code disposition 未被实施：

| ID | Controller disposition | Re-review 确认 |
|---|---|---|
| MiMo F-01 | `REJECTED_AS_FINDING / NON_BLOCKING PERFORMANCE_OBSERVATION` | 未实施缓存/复用。✓ |
| MiMo F-02 | `REJECTED_AS_FINDING / OWNER-LOCAL_IDENTITY_REQUIRED` | 未实施深拷贝。publication dict 浅拷贝保持同一 section identity。✓ |
| DS O01 | `REJECTED_AS_FINDING / PLAN-AUTHORIZED_OWNER_HARNESS` | `_VirtualHarness` 仍 import 私有类型，断言走 public consumer。✓ |
| DS O02 | `REJECTED_AS_CURRENT_FINDING / EVIDENCE-INSUFFICIENT / PROTECTED EXISTING_SAFE-DEGRADE` | 既有 marker producer 宽异常未修改。✓ |
| DS O03 | `NOT_A_FINDING` | unbound base oracle 模式未修改。✓ |

## 10. Gemini / provider / deferred 状态确认

- Gemini/provider：search_web=0，按测试账号低 budget 边界裁决 `EXPECTED_TEST_ACCOUNT_QUOTA / PROVIDER_ADHERENCE_RESIDUAL / NO_CODE_ACTION / NON_BLOCKING`。不建议重试或改 config/model/key/retry/quota/budget。✓
- AR-F05：保持 closed。✓
- AR-F06：`RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。✓
- AR-F07：`PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE`。保持 remote Windows release blocker。✓
- 无新增 secret infrastructure、统一 authorization framework、兼容 shim 或 deferred Issue 能力。✓

## 11. Findings summary

### Material findings

**0**。全部 plan 约束已验证通过。无 blocking finding。

### Initial review findings 状态

| # | Initial severity | Initial description | Re-review 状态 |
|---|---|---|---|
| F-01 | Non-blocking | `_build_markers(marked_text)` 重复计算 | Controller REJECTED；未实施。确认 non-blocking。✓ |
| F-02 | Non-blocking | publication dict 浅拷贝 | Controller REJECTED；identity required。确认 non-blocking。✓ |

**无新 material finding。Initial findings 全部确认为 non-blocking 且未被实施。**

## 12. Adversarial checklist

| Check | Result |
|---|---|
| Docling captions 仍满足 S3-STOP-F01 且无猜测/内部 ref 泄露 | ✓ PASS |
| Fins BUILDING/VIRTUAL_PUBLISHED/BASE_FALLBACK_PUBLISHED 真正原子 | ✓ PASS |
| contradiction-first 与 incomplete fallback 顺序正确 | ✓ PASS |
| `_remap_tables_to_deepest_virtual_sections` 只消费同一 candidate mapping | ✓ PASS |
| 首次/二次 refresh 同 terminal 且五 public consumers 只消费 typed mode | ✓ PASS |
| 测试在 public/owner contract 而非私有实现/coverage padding | ✓ PASS |
| README 准确 | ✓ PASS |
| 没有兼容 shim、deferred Issue、统一 authorization、安全机制删除 | ✓ PASS |
| Protected hashes 全部 MATCH | ✓ PASS |
| Protected zero-diff paths 全部 exit 0 | ✓ PASS |
| Controller observations 按 no-code disposition 未被实施 | ✓ PASS |
| Gemini/provider residual 不建议重试/改配置 | ✓ PASS |
| AR-F07 保持 remote Windows release blocker | ✓ PASS |
| 不审查范围外的变更 | ✓ PASS |

## 13. Artifact SHA

```text
Review artifact path: docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-rereview-mimo.md
```

Controller 应在读取后独立计算本 artifact 的 SHA-256 并记录。
