# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二路独立完整 Final Code Re-Review（AgentDS）

## 0. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 3。
- Review type：第二路独立完整 final code re-review；覆盖 Controller validation 锁定的全部 9 路径。
- Accepted base：`9ad5711e20dd35d5a0cdc0cf79067333ff3b3daf`。
- 固定 review target（9 paths）：

```text
dayu/documents/processors/docling_processor.py
dayu/fins/README.md
dayu/fins/processors/sec_form_section_common.py
tests/documents/test_processors.py
tests/fins/test_sec_pipeline_download.py
tests/fins/test_processor_read_consistency.py
tests/fins/test_fins_ingestion_tools.py
tests/host/test_effective_execution_config.py
tests/runtime/test_argparse_exit.py
```

## 0.1 Review locks 独立复核

三个 locks 独立复算：

```text
tracked binary diff SHA-256 = de39190c66121255ddd69fdb3418b9ad8bca74e455a98ff94f3fe2e9e08fb206  ✓ 匹配
9-path content-manifest SHA-256  = 83cddc11fc114531972ad43db8f55080c0f53803d3eed76ddeb93afacf3f8b28  ✓ 匹配
9-path status-manifest SHA-256   = 2c7b84432af3b37521b1618a4058bee851f02300adf11df75be1634cf7d21573  ✓ 匹配
```

复算口径：accepted base 到完整 9-path target 的 `git diff --binary | shasum -a 256`；固定顺序逐文件 `shasum -a 256` 的二次 manifest；固定 9-path 的 `git status --short | shasum -a 256`。三个 lock 均与 Controller adjudication、codex zero-change record、MiMo/DS initial reviews 锁定的值逐字节一致。

## 0.2 逐文件内容 hash 独立复核

| Path | SHA-256 | 与 codex record 对比 |
|---|---|---|
| `dayu/documents/processors/docling_processor.py` | `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649` | MATCH |
| `dayu/fins/README.md` | `adcfd166ec7f9ab1c519cf3e8c161092a4a83a2317af7602bbb0c48f37242525` | MATCH |
| `dayu/fins/processors/sec_form_section_common.py` | `9f66893b6c3c2af2427f02967c16ba1557fb1c5070c58978c9c8de70902c45a2` | MATCH |
| `tests/documents/test_processors.py` | `4dedb3aceb2886d51427ca58a9a2c07a136072119e14679f5f612aa05e34c65f` | MATCH |
| `tests/fins/test_sec_pipeline_download.py` | `840feae7b448049c2dd8f53a6b0cd831b883ff9fee26556b9b427a3df060eae6` | MATCH |
| `tests/fins/test_processor_read_consistency.py` | `0ee788c2139e729f370f5533158519ca6b1968485376c7bb06781456918740c1` | MATCH |
| `tests/fins/test_fins_ingestion_tools.py` | `6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747` | MATCH |
| `tests/host/test_effective_execution_config.py` | `e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf` | MATCH |
| `tests/runtime/test_argparse_exit.py` | `3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d` | MATCH |

全部 9 路径逐文件 hash 与 codex zero-change record 一致。

## 0.3 Protected zero-diff owners 独立复核

```text
dayu/documents/processors/base.py           : zero diff ✓
dayu/fins/processors/sec_processor.py       : zero diff ✓
dayu/fins/processors/ten_k_processor.py     : zero diff ✓
dayu/fins/processors/ten_q_processor.py     : zero diff ✓
dayu/fins/processors/bs_ten_k_processor.py  : zero diff ✓
dayu/fins/processors/bs_ten_q_processor.py  : zero diff ✓
```

`git diff --exit-code 9ad5711e...` 全部通过。marker producer contract、`SecProcessor` unsupported-marker contract、10-K/10-Q/BS subclass 行为均未修改。

## 1. Review methodology

本次 re-review 独立逐行覆盖全部 9 路径。审查维度：

- **lock integrity**：三个 review locks 独立复算是否与 Controller 锁定值一致。
- **protected delta**：S3-STOP-F01 Docling caption 路径是否无回归。
- **state machine correctness**：S3-STOP-F02 三态 transition、contradiction-first 顺序、原子 publication 是否正确。
- **public consumers**：五个 public consumers 是否统一 typed mode guard、同一真源。
- **remap**：`_remap_tables_to_deepest_virtual_sections` 是否只操作同一 candidate mapping、双向校验是否正确。
- **deleted patterns**：`_filter_table_refs_by_availability`、`_assign_unmapped_tables_by_position`、`fallback_ref`、`last_known_ref` 是否零命中。
- **forbidden patterns**：新增 hunk 中 `hasattr`/`getattr`/`except Exception` 是否为零；既有 `except Exception` 是否仅在受保护的既有基础设施代码中。
- **test authenticity**：测试是否断言 owner-level public contract；是否滥用 private implementation mirroring 或 coverage padding。
- **semantic ownership**：每个业务事实是否有唯一 owner；消费者是否从同一真源派生。
- **security / deferred**：无新 secret 泄露面、兼容 shim、deferred Issue 偷带；AR-F06/AR-F07 状态不变；Gemini 保持 NO_CODE_ACTION。
- **pyright**：关键文件 zero errors/warnings。
- **tests**：全部 affected tests 通过。

Review 期间未修改任何代码、tests、README、control、plan 或既有 artifacts；未 stage/commit。

## 2. S3-STOP-F01 Docling Caption Resolver 复核

### 2.1 Caption 解析路径

`_extract_table_caption(table_item, document)`（L1174-1207）：

| Plan 约束 | 代码证据 | 判定 |
|---|---|---|
| 使用 typed `RefItem.cref`，不读 JSON `$ref` | L1194: `caption_ref.cref` | ✓ |
| root ref `#` 以命名常量跳过 | L51: `_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"`；L1194: `caption_ref.cref == _DOCLING_DOCUMENT_ROOT_REF` | ✓ |
| 只在 resolve 边界捕获 `AttributeError`/`IndexError` | L1197-1198: `except (AttributeError, IndexError):` | ✓ |
| resolve 到非 TextItem 跳过 | L1200: `isinstance(resolved, TextItem)` | ✓ |
| 规范化空白、精确大小写去重、保留首次出现 | L1202: `_normalize_whitespace(resolved.text)`；L1203: `caption in seen`；L1205: `seen.add(caption)` | ✓ |
| 多 caption 单空格连接，无剩余返回 None | L1207: `" ".join(captions) or None` | ✓ |
| `_build_tables` 传入同源 `DoclingDocument` | L630: `caption = _extract_table_caption(table_item, document)` — `document` 是 L601 的同一 `DoclingDocument` | ✓ |
| 三个 public consumers 共享 `_TableBlock.caption` | L279: `caption=table.caption`（`list_tables()`）；L374: `caption=table.caption`（`read_table()`）；L1501: `caption=table.caption`（`get_page_content().tables`） | ✓ |

**S3-STOP-F01 verdict**：无回归。Caption resolver 是 `_TableBlock.caption` 的唯一 producer；三个 public consumer 直接消费同一字段，无重算或下游补偿。

### 2.2 Docling protected delta

Docling production delta 相对 entry SHA-256 `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649` 逐行确认无变化。`_extract_table_caption` 的旧版单数 `caption` 字段、`getattr(table_item, "caption", ...)`、`FloatingItem.caption_text()` 调用均为零。

### 2.3 `hasattr`/`getattr` 审计

`docling_processor.py` 中存在 17 处 `getattr` 使用（L583, L878, L908, L948, L965, L970, L993, L999, L1004, L1009, L1045, L1049, L1091, L1119-1121, L1586），全部位于 Docling 既有基础设施代码中（`_normalize_label`、`_export_table_to_markdown`、`_export_table_data`、`_normalize_cell_value`、`_linearize_document`、`_resolve_text_item_ref` 等），用于兼容 docling_core 库的可选属性。Caption resolver `_extract_table_caption`（L1174-1207）零 `getattr`/`hasattr`。**S3-STOP-F01 核心路径零禁止模式。**

## 3. S3-STOP-F02 Virtual Section Publication State Machine 复核

### 3.1 状态枚举

`_VirtualSectionPublicationMode`（L254-259）：

```python
class _VirtualSectionPublicationMode(Enum):
    BUILDING = auto()
    VIRTUAL_PUBLISHED = auto()
    BASE_FALLBACK_PUBLISHED = auto()
```

Owner-private；不暴露给 public consumers。✓

### 3.2 唯一 transition owner

`_refresh_virtual_section_state()`（L436-508）是唯一可提交 terminal transition 的方法：

- `_initialize_virtual_sections()`（L378-419）只设 `BUILDING`（L397），初始化空 mapping（L398-400），调用 refresh（L418）
- `_postprocess_virtual_sections()`（L555-573）只做内容后处理并再次调用 refresh
- 无其他方法修改 `_virtual_section_publication_mode`

### 3.3 Transition 规则逐项验证

| Transition | 代码证据 | 判定 |
|---|---|---|
| BUILDING → VIRTUAL_PUBLISHED | L504-508：全部验证通过后 `_publish_virtual_section_state()` | ✓ |
| BUILDING → BASE_FALLBACK_PUBLISHED | L499-501：missing_refs 非空时 `_publish_base_fallback_state()`；L470-471：`_virtual_sections` 为空时 `_publish_base_fallback_state()` | ✓ |
| VIRTUAL_PUBLISHED → VIRTUAL_PUBLISHED | L462-467：identity multiset 校验后重建映射 | ✓ |
| BASE_FALLBACK_PUBLISHED → BASE_FALLBACK_PUBLISHED | L456-457：直接 return（幂等 no-op） | ✓ |

### 3.4 Contradiction-first 验证顺序

`_refresh_virtual_section_state()` 的验证顺序（L469-508）：

1. **Base table ref 校验**（L474）：`_validate_base_table_refs()` — 缺失/空/重复 → `ValueError`
2. **Raw marker ref 校验**（L477-478）：`_extract_raw_table_refs()` + `_validate_raw_marker_refs()` — dangling/重复 → `ValueError`
3. **Virtual section tree 校验**（L480）：`_validate_virtual_section_tree()` — ref 重复/父子悬挂/双向矛盾 → `ValueError`
4. **Candidate mapping 构建**（L481-483）：`_assign_tables_to_virtual_sections()` — 同一 marker 多归属 → `ValueError`
5. **Section table refs 投影**（L485-489）：`_build_candidate_section_table_refs()` — 悬挂 section_ref → `ValueError`
6. **双向一致性校验**（L490-495）：`_validate_candidate_table_mapping()` — 悬挂/重复/双向不一致 → `ValueError`
7. **Incomplete proof 判定**（L497-501）：`missing_refs = base_table_ref_set - set(candidate_mapping)` 非空 → whole-base fallback（BUILDING）或 `ValueError`（VIRTUAL_PUBLISHED）

步骤 1-6 任一失败即 `ValueError` fail-closed；步骤 7 仅在无矛盾时触发 fallback。**incomplete + dangling 同时存在时，dangling 在步骤 2 优先 fail-closed**——不会被步骤 7 吞掉。✓

### 3.5 Atomic publication

- `_publish_base_fallback_state()`（L510-526）：清空 `_virtual_sections`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`，设 `BASE_FALLBACK_PUBLISHED`。一次提交三个字段，不提前修改。✓
- `_publish_virtual_section_state()`（L528-553）：一次性更新 `section.table_refs`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`，设 `VIRTUAL_PUBLISHED`。验证期间不修改 published state。✓

### 3.6 五个 public consumers 统一 typed mode guard

| Consumer | 代码位置 | Guard | Base 委托 |
|---|---|---|---|
| `list_tables()` | L958 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().list_tables()` |
| `list_sections()` | L987 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().list_sections()` |
| `get_section_title()` | L1014 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().get_section_title(ref)` |
| `read_section()` | L1033 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().read_section(ref)` |
| `search()` | L1079 | `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().search(...)` |

精确五个 consumer，统一使用 `mode is not VIRTUAL_PUBLISHED` guard。`VIRTUAL_PUBLISHED` 时消费 virtual sections/index/mapping；其他两种 mode 均完整透传底层 processor contract。无单独反推状态、按可用性静默过滤或位置猜测。✓

### 3.7 remap 逻辑

`_remap_tables_to_deepest_virtual_sections()`（L2922-2969）：

- 只操作同一 owner-local `candidate_mapping`（参数 `table_ref_to_virtual_ref`）
- 通过 `list(table_ref_to_virtual_ref.items())` 创建迭代副本（L2957），在循环中直接修改原 dict（L2969）——正确，只修改已有 key 的 value，不修改迭代 keys
- `_find_deepest_virtual_section_ref()`（L3058-3097）逐层下钻，同层多命中 → `ValueError`（L3095-3096）
- 最终双向校验：`_validate_candidate_table_mapping()`（L2777-2819）在 remap 之后执行（`_refresh_virtual_section_state` L490 调用），独立验证正向 `section_table_refs` 与反向 `table_ref_to_virtual_ref` 双向一致，并确保所有 table_ref 都在 `base_table_refs` 中（L2807-2808, L2815-2816）

### 3.8 零表格文档

L474-475：`base_table_refs` 为空元组时 `base_table_ref_set` 为空集合。L477-478 的 `raw_marker_refs` 也为空（无表格 marker）。L497 `missing_refs = set() - set()` 为空。L504-508 正常发布 `VIRTUAL_PUBLISHED`。✓

### 3.9 首次/二次 refresh 幂等

- **首次**：`_initialize_virtual_sections()` L418 → `_refresh_virtual_section_state()` 首次 publication decision
- **10-K 二次**：`expand_ten_k_virtual_sections_content()` → `_refresh_virtual_section_state(expected_identity_multiset=...)`；L462-467 校验 identity multiset 不变后重建映射
- **10-Q 二次**：`expand_ten_q_virtual_sections_content()` → 同上
- **Fallback 后**：L456-457 `BASE_FALLBACK_PUBLISHED` 直接 return

### 3.10 核心状态机禁止模式扫描

`sec_form_section_common.py` L436-553（`_refresh_virtual_section_state` + `_publish_base_fallback_state` + `_publish_virtual_section_state`）：

- `hasattr`/`getattr`：**零** ✓
- `except Exception`：**零** ✓
- `except RuntimeError`/`warning`/`logger`：**零** ✓

### 3.11 既有基础设施代码审计

`sec_form_section_common.py` 中 8 处 `except Exception`（L621, L635, L676, L691, L695, L826, L870, L1218）全部位于 S3-STOP-F02 之前的既有基础设施代码（`_collect_structured_split_candidates`、`_build_virtual_sections_from_base`、`_safe_virtual_document_text`、`_collect_document_text`、`_collect_marked_text`）。这些函数已有明确的语义降级（返回空字符串/空列表），不会向前传播损坏状态。本次 review 确认：DS initial review O02 的观察仍成立，但未在本次 slice 实施。✓

### 3.12 已删除禁止模式

全项目扫描确认以下 pattern 零命中：

- `_filter_table_refs_by_availability`：零命中 ✓
- `_assign_unmapped_tables_by_position`：零命中 ✓
- `fallback_ref`（Host 的 `outbox.py`/`read_model.py` 中使用的是不同语义的 `fallback_ref` 参数，与 Fins virtual section 无关）：Fins 中零命中 ✓
- `last_known_ref`：零命中 ✓
- `_collect_available_table_refs_from_base`：零命中 ✓

## 4. Tests 复核

### 4.1 Docling caption 测试

8-node caption matrix（`tests/documents/test_processors.py`）：

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

全部经真实 `DoclingDocument` 构造、`save_as_json()` 序列化、`DoclingProcessor` load 后断言 public 结果。`_ref_item(ref)` 通过 `RefItem.model_validate({"$ref": ref})` 走 Pydantic deserialization，正确映射 `$ref`（JSON alias）到 Python `cref` 字段。Production 只读 `cref`，边界正确。✓

26 passed, 0 failed.

### 4.2 S3-STOP-F02 六类反例矩阵

| Plan 要求的反例类别 | 覆盖测试 | 判定 |
|---|---|---|
| 1. Public 10-K + unsupported marker + base table | `test_ten_k_public_processor_assigns_tables_without_marker_capability`（L1846）— 真实 `TenKFormProcessor`，合法 HTML，`_assert_processor_matches_base_public_contract` 逐值验证 | ✓ |
| 2. Complete mapping + deepest remap | `test_virtual_section_complete_mapping_publishes_deepest_bidirectional_candidate`（L1980）— 两表一子章节，remap 到最深，二次 refresh 幂等 | ✓ |
| 3. Incomplete proof (两子类) | `test_virtual_section_incomplete_proof_publishes_whole_base_fallback`（L2035）— (a) partial: base 两表 marker 只证一表；(b) ambiguous: range/title 不能唯一证明归属 | ✓ |
| 4. Duplicate/dangling/contradictory + mixed priority | `test_virtual_section_contradictions_fail_before_incomplete_fallback`（L2064）— 五种子类，incomplete+dangling 优先 fail-closed；`test_virtual_section_refresh_fails_closed_for_duplicate_or_dangling_refs`（L2140）— 额外 duplicate section ref 与 dangling | ✓ |
| 5. Zero-table document | `test_virtual_section_zero_table_document_publishes_virtual_projection`（L2118）— base_table_refs=()，发布 virtual，空 tables | ✓ |
| 6. 10-K/10-Q second postprocess idempotence | `test_ten_q_public_processor_keeps_base_fallback_through_second_postprocess`（L1910）— 真实 `TenQFormProcessor`；`test_report_form_second_postprocess_keeps_base_fallback_terminal`（L2270）— parametrize 四 processor；`test_both_ten_q_paths_preserve_object_ref_multiset_and_refresh`（L2173）— 两路 10-Q；`test_both_ten_k_paths_migrate_to_shared_refresh_without_behavior_drift`（L2237）— 两路 10-K；`test_ten_q_path_rejects_expansion_that_creates_section`（L2205）— 创建新 ref fail-closed | ✓ |

51 passed, 0 failed.

### 4.3 测试真实性验证

- **公共 processor 测试**：`_assert_processor_matches_base_public_contract`（L1810-1843）使用 `SecProcessor.list_sections(processor)`（unbound call，绕过 mixin override）获取 base truth，与 `processor.list_sections()`（走 mixin guard）逐值比较。同时在 section/table/title/read/search 五个维度逐值验证。**unbound call 是正确 oracle pattern**，不构成 defect。✓
- **Owner harness 测试**：`_assert_virtual_harness_matches_base_contract`（L1031-1059）同样使用 `_VirtualBaseProcessor.list_sections(harness)` unbound call 作为 base truth。✓
- **`_VirtualHarness`**（L894-1028）：从 production import `_VirtualSection`、`_VirtualSectionPublicationMode`、`_VirtualSectionProcessorMixin`。这是 plan 授权的 "typed owner harness"；fixture 只构造 owner 状态，所有断言走 public consumer contract 或 unbound base truth。不迫使 production 保留兼容分支。✓
- **零 `hasattr`/`getattr`**：`tests/fins/test_processor_read_consistency.py` 和 `tests/documents/test_processors.py` 均零 `hasattr`/`getattr`。✓
- **无 private implementation mirroring**：测试不调用 `_extract_table_caption`、`_remap_tables_to_deepest_virtual_sections` 等 private helpers 验证返回值。全部通过 public consumers 断言。✓

### 4.4 其他测试文件

- `tests/fins/test_sec_pipeline_download.py`：175 passed；内容 hash `840feae7...` 与 entry 一致 ✓
- `tests/fins/test_fins_ingestion_tools.py`：175 passed；内容 hash `6ece9288...` 与 entry 一致 ✓
- `tests/host/test_effective_execution_config.py`：175 passed；内容 hash `e3a85cad...` 与 entry 一致 ✓
- `tests/runtime/test_argparse_exit.py`：175 passed；内容 hash `3aa60784...` 与 entry 一致 ✓

合计 26 + 51 + 175 = 252 passed，与 implementation Controller validation 报告一致。

## 5. README 复核

### 5.1 `dayu/fins/README.md`

L505 更新内容：

> "虚拟章节 mixin 是表单专项 section / table 发布语义的唯一 owner。刷新时先校验原始表格标记、章节树和同一份候选双向映射，再一次性发布结果：完整映射（包括零表格）发布虚拟章节；没有矛盾但映射缺失或不完整时整体发布基础处理器结果；悬空、重复或双向不一致等矛盾直接失败关闭。已发布模式是终态，重复刷新保持幂等；章节列表、章节读取、搜索、表格列表和表格读取五个公共消费者只读取同一已发布模式与映射，不按可用性静默过滤，也不按位置猜测归属。"

覆盖验证：
- atomic validation + publication ✓
- complete mapping（含零表格）→ virtual ✓
- incomplete → whole-base fallback ✓
- contradiction fail-closed ✓
- terminal idempotence ✓
- 五个 public consumers 统一 mode ✓
- no silent filtering, no position guessing ✓

### 5.2 其他 README

根 `README.md`、`dayu/README.md`、`tests/README.md` 按计划判为 `NO_UPDATE`。验证：这些文件无 diff，判断正确。

## 6. pyright 独立验证

```text
dayu/documents/processors/docling_processor.py   : 0 errors, 0 warnings
dayu/fins/processors/sec_form_section_common.py  : 0 errors, 0 warnings
tests/documents/test_processors.py               : 0 errors, 0 warnings
tests/fins/test_processor_read_consistency.py    : 0 errors, 0 warnings
```

## 7. Structured integrity checks

- `git diff --check 9ad5711e... -- . ':(exclude)docs/'`：PASS，无输出 ✓
- `git diff --cached --name-only`：EMPTY ✓
- `git log 9ad5711e...HEAD -- <9-path target>`：无输出（base 到 HEAD 之间无 commit 触碰 9 路径） ✓

## 8. Security / deferred / no-code 边界复核

### 8.1 Secret surface

S3-STOP-F01 和 S3-STOP-F02 的生产代码中零出现 `secret`、`api_key`、`API_KEY`、`Authorization`、`Bearer`、`password` 等凭证模式。Docling processor 中零 secret 引用。无新 secret infrastructure。✓

### 8.2 LLM-facing 文本

- Docling caption 通过 `TableSummary.caption` 进入 LLM-facing context。Caption 是纯业务文本（如 "Consolidated statements of operations"），不含内部 ref、digest、path 或模块名。
- Virtual section 的 `list_sections()`、`read_section()`、`search()` 返回标准 `SectionSummary`/`SectionContent`/`SearchHit` dict；state machine mode 不向外暴露。

### 8.3 Deferred / no-code

- 无新 Issue 能力、无 TruncationManager wiring、无 storage-state lifecycle、无 Fins hard-kill/process isolation、无统一 tool authorization framework、无 secret infrastructure。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX` — 未修改。✓
- `AR-F07 = PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE` — 未修改。✓
- Gemini quota = `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING` — 未修改 config/model/key/retry/quota/budget。✓

## 9. MiMo/DS initial review observations 状态复核

| 来源 / ID | Observation | Controller disposition | 当前状态 |
|---|---|---|---|
| MiMo F-01 | `_build_markers(marked_text)` 重复计算 | REJECTED_AS_FINDING / NON_BLOCKING | 未实施缓存/接口扩展 ✓ |
| MiMo F-02 | publication dict 浅拷贝 | REJECTED_AS_FINDING / OWNER-LOCAL_IDENTITY_REQUIRED | 未实施深拷贝 ✓ |
| DS O01 | `_VirtualHarness` import private types | REJECTED_AS_FINDING / PLAN-AUTHORIZED | harness 未修改 ✓ |
| DS O02 | 既有宽异常捕获 | REJECTED_AS_CURRENT_FINDING / EVIDENCE-INSUFFICIENT | 既有 producer 未修改 ✓ |
| DS O03 | unbound base oracle | NOT_A_FINDING | oracle pattern 保留 ✓ |

全部 observation 保持 Controller adjudication 的 zero-code disposition，未在任何 production/test/README 中实施。✓

## 10. Adversarial failure pass 独立复核

### 10.1 Docling caption resolver

| 反例 | 预期行为 | 实际路径 | 判定 |
|---|---|---|---|
| captions 为空列表 | 返回 None | L1193 循环不执行 → L1207 `or None` | ✓ |
| 所有 refs 为 root ref `#` | 返回 None | L1194 continue → 循环全部跳过 | ✓ |
| 所有 refs 为 dangling | 返回 None | L1197-1198 捕获 → 全部 continue | ✓ |
| 混合 valid + root + dangling + non-text | 只有 valid TextItem 保留 | 各分支独立处理 | ✓ |
| resolve 抛出 `RuntimeError` | 向上传播 | L1197-1198 不捕获 | ✓ |
| resolve 抛出 `ValueError` | 向上传播 | L1197-1198 不捕获 | ✓ |
| TextItem.text 经规范化后为空 | 跳过该 ref | L1202-1203 | ✓ |
| 大小写不同的相同词 | 分别保留 | L1203 case-sensitive `in seen` | ✓ |

### 10.2 Virtual section publication

| 反例 | 预期行为 | 实际路径 | 判定 |
|---|---|---|---|
| base table_ref 为空字符串 | `ValueError("缺失或为空")` | `_validate_base_table_refs` L2657-2658 | ✓ |
| base table_ref 重复 | `ValueError("重复")` | `_validate_base_table_refs` L2659-2660 | ✓ |
| marker ref dangling | `ValueError("悬挂")` | `_validate_raw_marker_refs` L2699-2701 | ✓ |
| marker ref 重复 | `ValueError("重复")` | `_validate_raw_marker_refs` L2704-2706 | ✓ |
| section ref 重复 | `ValueError("ref 重复")` | `_validate_virtual_section_tree` L2727-2728 | ✓ |
| parent_ref 悬挂 | `ValueError("parent_ref 悬挂")` | `_validate_virtual_section_tree` L2732-2733 | ✓ |
| child_ref 反向关系不一致 | `ValueError("反向关系不一致")` | `_validate_virtual_section_tree` L2740-2741 | ✓ |
| 同一 marker 落入多个 section | `ValueError("落入多个虚拟章节")` | `_record_candidate_table_mapping` L2917-2918 | ✓ |
| 同层多个子章节命中同一 marker | `ValueError("同时命中多个虚拟子章节")` | `_find_deepest_virtual_section_ref` L3095-3096 | ✓ |
| VIRTUAL 后 refresh 创建新 section | `ValueError("不得创建")` | L460-461 | ✓ |
| VIRTUAL 后 refresh 丢失 table | `ValueError("缺少 table_ref")` | L501-502 | ✓ |
| incomplete + dangling 同时存在 | dangling 优先 fail-closed | 步骤 2 先于步骤 7 | ✓ |
| zero-table + virtual sections | 正常发布 VIRTUAL | L474 base_table_refs=() | ✓ |
| 首次 fallback 后二次 postprocess | 直接 return，不重读 marker | L456-457 | ✓ |
| `_collect_marked_text()` 返回空 | missing_refs 触发 fallback | L477 raw_marker_refs=() → missing_refs 全量 | ✓ |

## 11. Architecture / semantic ownership 复核

### 11.1 分层边界

- `dayu.fins.processors.sec_form_section_common` 只导入 `dayu.documents.processors` 和 `dayu.fins._log`、`dayu.fins.domain.filing_semantics`。不导入 `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`。无反向依赖。✓
- `dayu.documents.processors.docling_processor` 只导入 `docling_core` 和标准库/`pandas`。不导入 `dayu.fins`、`dayu.engine`、`dayu.host`。分层正确。✓

### 11.2 语义 ownership

| 业务事实 | 唯一 owner | 消费者 | 判定 |
|---|---|---|---|
| Table caption 文本 | `_extract_table_caption()` → `_TableBlock.caption` | `list_tables()`、`read_table()`、`get_page_content()` | ✓ 同源 |
| Virtual section publication mode | `_refresh_virtual_section_state()` | 五个 public consumers 读同一 `_virtual_section_publication_mode` | ✓ 同源 |
| Table → section mapping | `_refresh_virtual_section_state()` → `_table_ref_to_virtual_ref` | `list_tables()` 消费 | ✓ 同源 |
| Section → tables mapping | `_refresh_virtual_section_state()` → `section.table_refs` | `read_section()`、`list_sections()` | ✓ 同源 |

### 11.3 无兼容代码

- 无兼容 re-export、facade、lazy import
- 无 `__getattr__`、importlib
- 无 duplicate enum/protocol
- 无新 secret infrastructure、统一 authorization framework

## 12. Findings

### Material Findings

**无 material findings。** 全部 plan 约束已验证通过。S3-STOP-F01 caption resolver 无回归；S3-STOP-F02 virtual section publication state machine 正确实现 contradiction-first 原子 publication + whole-base fallback；五个 public consumers 统一 typed mode guard；remap 只操作同一 candidate mapping 且经最终双向校验；首次/二次 refresh 幂等；deleted patterns 零命中；test authenticity 通过；三个 review locks 独立匹配；9 路径内容逐文件 hash 独立匹配；pyright zero errors；252 tests passed；staged empty；protected owners 零 diff。

### New Findings

| # | Severity | Classification | Description |
|---|---|---|---|
| — | — | — | **无新增 finding**。本次独立 re-review 未发现 DS/MiMo initial reviews 和 Controller adjudication 已覆盖之外的任何 material defect、needs-evidence 或 blocking question。 |

## 13. Final Verdict

**PASS — MATERIAL_FINDING=0 — ZERO_NEW_FINDING**

独立复核结论：

1. **三个 review locks** 独立复算与 Controller 锁定值逐字节一致。逐文件 content hash 与 codex zero-change record 一致。Protected zero-diff owners 全部通过。

2. **S3-STOP-F01**（Docling captions）：caption resolver 无回归。typed `RefItem.cref`、root ref 常量跳过、`(AttributeError, IndexError)` 边界捕获、规范化/大小写敏感去重、三个 public consumer 同源消费——全部 plan 约束持续满足。8-node caption matrix 全部通过（26 passed）。

3. **S3-STOP-F02**（Fins virtual section publication）：`_VirtualSectionPublicationMode` 三态正确；contradiction-first 验证顺序完整（dangling 优先于 incomplete）；原子 publication（一次提交全部字段）；五个 public consumers 统一 typed mode guard；首次/二次 refresh 幂等；deleted patterns 零命中。六类反例矩阵完整覆盖（51 passed）。

4. **MiMo F-01/F-02 和 DS O01/O02/O03**：均保持 Controller adjudication 的 no-code disposition，未在任何 production/test/README 中实施。

5. **Tests**：全部 252 passed；测试断言 owner-level public contract；无 private implementation mirroring；无 coverage padding。pyright zero errors。

6. **Security / deferred**：无新 secret 泄露面；无兼容 shim；无 deferred Issue 偷带。AR-F06/AR-F07 状态不变。Gemini 保持 NO_CODE_ACTION / NON_BLOCKING。

7. **README**：`dayu/fins/README.md` 更新准确。其他 README 正确判为 NO_UPDATE。

### Artifact SHA

本 artifact 完成后的 SHA-256 应由 Controller 在读取后独立计算并记录。写入时内容如下。

---

本 re-review 未修改任何代码、tests、README、control、plan 或既有 artifacts；未 stage/commit/aggregate。
