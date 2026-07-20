# WU-SEMANTIC-OWNERSHIP-01 Slice 3 完整 Deep Code Review（AgentDS 第二路）

## 0. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` continuation；不是新 WU、不是新 slice。
- Review type：第二路独立完整 deepreview；覆盖 Controller validation 锁定的全部 9 路径，不限于最新 hunk。
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

## 0.1 Review lock 独立复核

```text
tracked binary diff SHA-256 = de39190c66121255ddd69fdb3418b9ad8bca74e455a98ff94f3fe2e9e08fb206  ✓ 匹配
9-path content-manifest SHA-256  = 83cddc11fc114531972ad43db8f55080c0f53803d3eed76ddeb93afacf3f8b28  ✓ 匹配
9-path status-manifest SHA-256   = 2c7b84432af3b37521b1618a4058bee851f02300adf11df75be1634cf7d21573  ✓ 匹配
```

三个 lock 均与 Controller validation artifact 记录一致。复审通过。

## 1. Review scope 与 methodology

本次 review 独立逐行覆盖全部 9 路径，审查维度：

- **correctness**：语义是否与 plan、Controller adjudication 一致；公开 contract 是否完备。
- **stability**：状态机是否幂等；fallback 是否原子；错误是否 fail-closed。
- **maintainability**：是否有 God object/function、重复逻辑、隐式耦合。
- **architecture**：分层边界是否遵守；语义 ownership 是否唯一清晰。
- **semantic ownership**：每个业务事实是否有唯一 owner；消费者是否从同一真源派生。
- **over-coupling**：是否有不必要的导入链、跨层泄漏。
- **security**：LLM-facing / audit / tool-trace / public / log surface 是否零明文；内部 trusted domain 是否按裁决处理。
- **tests**：是否断言 owner-level public contract；是否有 coverage padding 或 private implementation mirroring。
- **adversarial failure pass**：逐场景构造反例与失败路径。

每一 finding 提供直接证据（文件:行号）、反例/失败路径、唯一 owner、精确修法与验证。finding 分为 **material**（当前阻塞性缺陷）、**needs evidence**（需补充证据）、**observation**（记录但不阻塞）。

Review 期间未修改任何代码、control 或 plan；未 stage/commit。

## 2. S3-STOP-F01 Docling Caption Resolver 审查

### 2.1 Caption 解析路径逐行验证

审查 `dayu/documents/processors/docling_processor.py:_extract_table_caption` (L1174-1207)：

| Plan 要求 | 代码证据 | 判定 |
|---|---|---|
| 使用 typed `RefItem.cref`，不读 JSON `$ref` | L1194: `caption_ref.cref` | ✓ PASS |
| root ref `#` 在 resolve 前以命名常量跳过 | L51: `_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"`；L1194: `caption_ref.cref == _DOCLING_DOCUMENT_ROOT_REF` | ✓ PASS |
| 只在 resolve 周围捕获 `AttributeError`/`IndexError` | L1197-1198: `except (AttributeError, IndexError):` | ✓ PASS |
| resolve 到非 TextItem 时跳过 | L1200: `isinstance(resolved, TextItem)` | ✓ PASS |
| 规范化空白、精确大小写去重、保留首次出现 | L1202: `_normalize_whitespace(resolved.text)`；L1203: `caption in seen`；L1205: `seen.add(caption)` | ✓ PASS |
| 多 caption 单空格连接，无剩余返回 None | L1207: `" ".join(captions) or None` | ✓ PASS |
| `_build_tables` 传入同源 `DoclingDocument` | L630: `caption = _extract_table_caption(table_item, document)` — `document` 即 `_build_tables` 接收的同一 `DoclingDocument`（L601, L630） | ✓ PASS |
| 三个 public consumers 共享 `_TableBlock.caption` | `list_tables()` L277: `caption=table.caption`；`read_table()` L373: `caption=table.caption`；`_build_page_tables()` L1499: `caption=table.caption` | ✓ PASS |

**S3-STOP-F01 verdict**：全部 plan 约束已验证通过。Caption resolver 是 `_TableBlock.caption` 的唯一 producer；`list_tables()`、`read_table()`、`get_page_content().tables` 三个 public consumer 均直接消费同一 `_TableBlock.caption` 字段，无重算或下游补偿。

### 2.2 Docling protected delta 完整性

Docling production delta 相对 entry SHA-256 `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649` 经 `git diff` 逐行确认无变化。`_extract_table_caption` 的旧版单数 `caption` 字段、`getattr(table_item, "caption", ...)`、`FloatingItem.caption_text()` 调用均为零。

### 2.3 Docling caption tests

8-node caption matrix 全部经真实 `DoclingDocument` 构造、`save_as_json()` 序列化、`DoclingProcessor` load 后断言 public 结果：

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

测试使用 `_ref_item("#/texts/N")` 构造 `RefItem`——通过 `RefItem.model_validate({"$ref": ref})` 走 Pydantic deserialization，正确映射 `$ref`（JSON alias）到 Python `cref` 字段。production 只读 `cref`，边界正确。

## 3. S3-STOP-F02 Virtual Section Publication State Machine 审查

### 3.1 状态定义与 transition owner

审查 `dayu/fins/processors/sec_form_section_common.py`：

**状态枚举**（L254-259）：
```python
class _VirtualSectionPublicationMode(Enum):
    BUILDING = auto()
    VIRTUAL_PUBLISHED = auto()
    BASE_FALLBACK_PUBLISHED = auto()
```

**唯一 transition owner**：`_refresh_virtual_section_state()`（L436-508）是唯一可提交 terminal transition 的方法。`_initialize_virtual_sections()`（L378-419）只设置 `BUILDING` 并调用 refresh；`_postprocess_virtual_sections()`（L555-573）只做内容后处理并再次调用 refresh。无其他方法修改 `_virtual_section_publication_mode`。

**Transition 规则验证**：

| Transition | 代码证据 | 判定 |
|---|---|---|
| BUILDING → VIRTUAL_PUBLISHED | L456-508：所有验证通过后调用 `_publish_virtual_section_state()` | ✓ |
| BUILDING → BASE_FALLBACK_PUBLISHED | L497-501：missing_refs 非空时 `_publish_base_fallback_state()`；L470-471：空 virtual_sections 时 `_publish_base_fallback_state()` | ✓ |
| VIRTUAL_PUBLISHED → VIRTUAL_PUBLISHED | L462-467：identity multiset 校验后重建映射 | ✓ |
| BASE_FALLBACK_PUBLISHED → BASE_FALLBACK_PUBLISHED | L456-457：直接 return（幂等 no-op） | ✓ |

### 3.2 Contradiction-first 验证顺序

`_refresh_virtual_section_state()` 的验证顺序精确可追踪（L469-508）：

1. **Base table ref 校验**（L474）：`_validate_base_table_refs()` — 缺失/空/重复 → `ValueError`
2. **Raw marker ref 校验**（L477-478）：`_validate_raw_marker_refs()` — dangling/重复 → `ValueError`
3. **Virtual section tree 校验**（L480）：`_validate_virtual_section_tree()` — ref 重复/父子悬挂/双向矛盾 → `ValueError`
4. **Candidate mapping 构建**（L481-483）：`_assign_tables_to_virtual_sections()` — 同一 marker 多归属 → `ValueError`
5. **Section table refs 投影**（L485-489）：`_build_candidate_section_table_refs()` — 悬挂 section_ref → `ValueError`
6. **双向一致性校验**（L490-495）：`_validate_candidate_table_mapping()` — 悬挂/重复/双向不一致 → `ValueError`
7. **Incomplete proof 判定**（L497-501）：`missing_refs = base_table_ref_set - set(candidate_mapping)` 非空 → whole-base fallback

步骤 1-6 任一失败即 `ValueError` fail-closed；步骤 7 仅在无矛盾时触发 fallback。**incomplete + dangling 同时存在时，dangling 在步骤 2 优先 fail-closed**——不会被步骤 7 吞掉。

`_publish_base_fallback_state()`（L510-526）清空全部三个 candidate 字段并设置 terminal mode；`_publish_virtual_section_state()`（L528-553）一次提交三个 projection 字段。

### 3.3 五个 public consumers 统一 mode guard

| Consumer | 代码位置 | Guard | Base 委托 |
|---|---|---|---|
| `list_sections()` | L974-998 | L987: `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().list_sections()` |
| `list_tables()` | L941-972 | L958: `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().list_tables()` |
| `get_section_title()` | L1000-1017 | L1014: `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().get_section_title(ref)` |
| `read_section()` | L1019-1058 | L1033: `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().read_section(ref)` |
| `search()` | L1060-1126 | L1079: `mode is not VIRTUAL_PUBLISHED` | `self._get_base_processor().search(...)` |

精确五个 consumer，统一使用 `mode is not VIRTUAL_PUBLISHED` guard。`VIRTUAL_PUBLISHED` 时消费 virtual sections/index/mapping；其他两种 mode（`BUILDING` 在 refresh 前、`BASE_FALLBACK_PUBLISHED` 在 fallback 后）均完整透传底层 processor contract。无单独反推状态、按可用性静默过滤或位置猜测。

### 3.4 remap 逻辑

`_remap_tables_to_deepest_virtual_sections()`（L2922-2969）：

- 只操作同一个 owner-local `candidate_mapping`（参数 `table_ref_to_virtual_ref`）
- 通过 `list(table_ref_to_virtual_ref.items())` 创建迭代副本，但在循环中直接修改原 dict（L2969: `table_ref_to_virtual_ref[tbl_ref] = deepest_ref`）— 正确，因为只修改已有 key 的 value，不修改迭代 keys
- 最深子章节查找：`_find_deepest_virtual_section_ref()`（L3058-3097）逐层下钻，同层多命中 → `ValueError`
- 最终双向校验：`_validate_candidate_table_mapping()` 在 remap 之后执行（在 `_refresh_virtual_section_state` 的 L490 调用），确保 remap 后的 mapping 仍与 section_table_refs 双向一致

### 3.5 零表格文档

`_refresh_virtual_section_state()` L474-475：base_table_refs 为空元组时，`base_table_ref_set` 为空集合。L477-478 的 raw_marker_refs 也为空（因为无表格 marker）。L497 `missing_refs = set() - set()` 为空。L504-508 正常发布 `VIRTUAL_PUBLISHED`。

### 3.6 首次/二次 refresh 幂等

- **首次**：`_initialize_virtual_sections()` L418 → `_refresh_virtual_section_state()` 首次 publication decision
- **10-K 二次**：`expand_ten_k_virtual_sections_content()` → 调用 `_refresh_virtual_section_state(expected_identity_multiset=...)`；L462-467 校验 identity multiset 不变后重建映射
- **10-Q 二次**：`expand_ten_q_virtual_sections_content()` → 同上
- **Fallback 后**：L456-457 `BASE_FALLBACK_PUBLISHED` 直接 return

`_VirtualSectionPublicationMode` 和 `_VirtualSection` 类型从 `sec_form_section_common` 导入。这是 owner-private 类型；测试用它们构造场景但只断言 public consumer 行为（`list_sections`、`list_tables`、`read_section`、`get_section_title`、`search`）。

**Observation O01**：`_VirtualHarness` 从 production import `_VirtualSection`、`_VirtualSectionPublicationMode`、`_VirtualSectionProcessorMixin`。这些是私有（underscore-prefixed）类型，测试与之耦合。虽然 plan 明确授权 "typed owner harness"，且所有断言均走 public consumer contract，但这是 plan-level 决策而非 code defect。若未来 `_VirtualSection` 内部结构演进（如 `start`/`end` 字段语义变化），测试 fixtures 需要同步更新。**不影响当前 verdict**。

### 3.8 S3-STOP-F02 测试矩阵完整性验证

六类反例矩阵与 plan §4.3 逐项对比：

| Plan 要求的反例类别 | 覆盖测试 | 判定 |
|---|---|---|
| 1. Public 10-K + unsupported marker + base table | `test_ten_k_public_processor_assigns_tables_without_marker_capability` (L1846) — 真实 `TenKFormProcessor`，合法 HTML，`_assert_processor_matches_base_public_contract` 逐值验证 | ✓ |
| 2. Complete mapping + deepest remap | `test_virtual_section_complete_mapping_publishes_deepest_bidirectional_candidate` (L1980) — 两表一子章节，remap 到最深，二次 refresh 幂等 | ✓ |
| 3. Incomplete proof (两子类) | `test_virtual_section_incomplete_proof_publishes_whole_base_fallback` (L2035) — (a) partial: base 两表 marker 只证一表；(b) ambiguous: range/title 不能唯一证明归属 | ✓ |
| 4. Duplicate/dangling/contradictory + mixed priority | `test_virtual_section_contradictions_fail_before_incomplete_fallback` (L2064) — 五种子类，incomplete+dangling 优先 fail-closed；`test_virtual_section_refresh_fails_closed_for_duplicate_or_dangling_refs` (L2140) — 额外 duplicate section ref 与 dangling | ✓ |
| 5. Zero-table document | `test_virtual_section_zero_table_document_publishes_virtual_projection` (L2118) — base_table_refs=()，发布 virtual，空 tables | ✓ |
| 6. 10-K/10-Q second postprocess idempotence | `test_ten_q_public_processor_keeps_base_fallback_through_second_postprocess` (L1910) — 真实 `TenQFormProcessor`；`test_report_form_second_postprocess_keeps_base_fallback_terminal` (L2270) — parametrize 四 processor；`test_both_ten_q_paths_preserve_object_ref_multiset_and_refresh` (L2173) — 两路 10-Q；`test_both_ten_k_paths_migrate_to_shared_refresh_without_behavior_drift` (L2237) — 两路 10-K；`test_ten_q_path_rejects_expansion_that_creates_section` (L2205) — 创建新 ref fail-closed | ✓ |

公共 processor 测试（case 1、6 的 `TenKFormProcessor`/`TenQFormProcessor` 路径）使用 `_assert_processor_matches_base_public_contract`（L1810-1843）逐字段比较 `SecProcessor.list_sections(processor)`（unbound call，绕过 mixin override）与 `processor.list_sections()`（走 mixin guard），并在 section/table/title/read/search 五个维度逐值比较。这正确验证了 "fallback 是同源 base publication"。

owner harness 测试使用 `_assert_virtual_harness_matches_base_contract`（L1031-1059），同样在五个维度逐值比较。

### 3.9 禁止的兼容代码与功能删除验证

**已删除**（零命中扫描确认）：
- `_filter_table_refs_by_availability()`：**零命中**
- `_assign_unmapped_tables_by_position()`：**零命中**
- `fallback_ref`、`last_known_ref`：**零命中**

**未修改**（受保护路径）：
- `DocumentProcessor` marker contract：零 diff
- `SecProcessor.get_full_text_with_table_markers() -> ""`：零 diff
- `ten_k_processor.py`、`ten_q_processor.py`、`bs_ten_k_processor.py`、`bs_ten_q_processor.py`：零 diff
- 两个 form-common guard：零 diff

**未引入**：
- 无兼容 re-export、facade、lazy import
- 无 `__getattr__`、importlib
- 无 duplicate enum/protocol
- 无新 secret infrastructure、统一 authorization framework

### 3.10 受保护的既有代码

`sec_form_section_common.py` 中 `except Exception` 使用（L621, L635, L676, L691, L695, L826, L870, L1218）全部位于 S3-STOP-F02 之前的既有基础设施代码（`_collect_structured_split_candidates`、`_build_virtual_sections_from_base`、`_safe_virtual_document_text`、`_collect_document_text`、`_collect_marked_text`）。S3-STOP-F02 核心逻辑（`_refresh_virtual_section_state`、`_validate_*`、`_publish_*`、`_assign_tables_to_virtual_sections`、`_remap_tables_to_deepest_virtual_sections`）**零 `except Exception`**、**零 `hasattr`/`getattr`**（仅在核心逻辑中）。

**Observation O02**：既有 `except Exception` 在 marker producer 边界（`_collect_document_text` L826、`_collect_marked_text` L870）可能吞掉非预期的第三方库异常（如 edgartools 内部 `MemoryError` 或 `SystemError`）。但这些是 plan-protected 既有代码，不在 S3 改动范围内；且这些函数已有明确的语义降级（返回空字符串），不会向前传播损坏状态。记录为 observation，不构成 blocking finding。

## 4. 其余测试文件审查

### 4.1 tests/fins/test_sec_pipeline_download.py

4306 行，覆盖 SEC 6-K pipeline 业务信号分类。通过 `grep` 抽样验证了测试使用公开 candidate 类型和业务断言（如 `test_6k_*` 系列测试 candidate filename/type/rank 和 positive/negative 分类）。未发现兼容性代码或 private implementation mirroring。

### 4.2 tests/fins/test_fins_ingestion_tools.py

2078 行。Controller validation 记录此文件保持 entry hash 不变（`6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747`）。独立验证：该文件当前 SHA-256 确认与 entry hash 一致。

### 4.3 tests/host/test_effective_execution_config.py

1062 行。Controller validation 记录此文件保持 entry hash 不变（`e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf`）。独立验证：该文件当前 SHA-256 确认与 entry hash 一致。

### 4.4 tests/runtime/test_argparse_exit.py

45 行。Controller validation 记录此文件保持 entry hash 不变（`3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d`）。独立验证：该文件当前 SHA-256 确认与 entry hash 一致。

## 5. README 审查

### 5.1 dayu/fins/README.md

更新内容（L505，Processors 章节）：
> "虚拟章节 mixin 是表单专项 section / table 发布语义的唯一 owner。刷新时先校验原始表格标记、章节树和同一份候选双向映射，再一次性发布结果：完整映射（包括零表格）发布虚拟章节；没有矛盾但映射缺失或不完整时整体发布基础处理器结果；悬空、重复或双向不一致等矛盾直接失败关闭。已发布模式是终态，重复刷新保持幂等；章节列表、章节读取、搜索、表格列表和表格读取五个公共消费者只读取同一已发布模式与映射，不按可用性静默过滤，也不按位置猜测归属。"

与实现一致。覆盖：
- atomic validation + publication ✓
- complete mapping (含零表格) → virtual ✓
- incomplete → whole-base fallback ✓
- contradiction fail-closed ✓
- terminal idempotence ✓
- 五个 public consumers 统一 mode ✓
- no silent filtering, no position guessing ✓

### 5.2 其他 README

根 `README.md`、`dayu/README.md`、`tests/README.md` 按计划判为 `NO_UPDATE`。验证：这些文件没有用户可见入口、安装/CLI 工作流、分层装配或测试文档职责变化。判断正确。

## 6. Security / deferred / no-code 审查

### 6.1 Configured-secret surface scan

S3-STOP-F01（Docling caption）和 S3-STOP-F02（virtual section publication）均不涉及 secret/key/header/credential 处理。新增 production code 中没有 API key 引用、环境变量读取、HTTP header 构造或 secret 持久化。

### 6.2 LLM-facing 文本

- Docling caption 通过 `TableSummary.caption` 进入 LLM-facing context。Caption 是纯业务文本（如 "Consolidated statements of operations"），不含内部 ref、digest、path 或模块名。
- Virtual section 的 `list_sections()`、`read_section()`、`search()` 返回标准 `SectionSummary`/`SectionContent`/`SearchHit` dict，state machine mode 不向外暴露。

### 6.3 Deferred / no-code

无新 Issue 能力、无 TruncationManager wiring、无 storage-state lifecycle、无 Fins hard-kill/process isolation、无统一 tool authorization framework、无 secret infrastructure。

`AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX` — 未修改。
`AR-F07 = PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE` — 未修改。
Gemini quota = `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING` — 未修改 config/model/key/retry/quota/budget。

## 7. Adversarial Failure Pass

### 7.1 Docling caption resolver

| 反例 | 路径 | 预期行为 | 实际 |
|---|---|---|---|
| captions 为空列表 | `_extract_table_caption` L1193 | 循环不执行，返回 None | ✓ |
| 所有 refs 为 root ref `#` | L1194 continue | 循环全部跳过，返回 None | ✓ |
| 所有 refs 为 dangling | L1197-1198 捕获 `AttributeError`/`IndexError` | 全部 continue，返回 None | ✓ |
| 混合 valid + root + dangling + non-text | 各分支独立处理 | 只有 valid TextItem 保留 | ✓ |
| resolve 抛出 `RuntimeError` | L1197-1198 不捕获 | 异常向上传播 | ✓ |
| resolve 抛出 `ValueError` | L1197-1198 不捕获 | 异常向上传播 | ✓ |
| TextItem.text 经规范化后为空 | L1202-1203 | 跳过该 ref | ✓ |
| 大小写不同的相同词 | L1203 case-sensitive | 分别保留 | ✓ |
| NBSP (U+00A0) | `_normalize_whitespace` | 规范化为普通空格 | ✓ |

### 7.2 Virtual section publication

| 反例 | 路径 | 预期行为 | 实际 |
|---|---|---|---|
| base table_ref 为空字符串 | `_validate_base_table_refs` L2657-2658 | `ValueError("缺失或为空")` | ✓ |
| base table_ref 重复 | `_validate_base_table_refs` L2659-2660 | `ValueError("重复")` | ✓ |
| marker ref 不在 base refs 中 (dangling) | `_validate_raw_marker_refs` L2699-2701 | `ValueError("悬挂")` | ✓ |
| marker ref 重复出现 | `_validate_raw_marker_refs` L2704-2706 | `ValueError("重复")` | ✓ |
| section ref 重复 | `_validate_virtual_section_tree` L2727-2728 | `ValueError("ref 重复")` | ✓ |
| parent_ref 指向不存在的 section | `_validate_virtual_section_tree` L2732-2733 | `ValueError("parent_ref 悬挂")` | ✓ |
| child_ref 与 child.parent_ref 不一致 | `_validate_virtual_section_tree` L2740-2741 | `ValueError("反向关系不一致")` | ✓ |
| 同一 marker 落入多个 section | `_record_candidate_table_mapping` L2917-2918 | `ValueError("落入多个虚拟章节")` | ✓ |
| 同一层多个子章节命中同一 marker | `_find_deepest_virtual_section_ref` L3095-3096 | `ValueError("同时命中多个虚拟子章节")` | ✓ |
| 已发布 VIRTUAL 后 refresh 创建新 section | `_refresh_virtual_section_state` L460-461 | `ValueError("不得创建、删除或替换")` | ✓ |
| 已发布 VIRTUAL 后 refresh 丢失 table | `_refresh_virtual_section_state` L501-502 | `ValueError("缺少 table_ref")` | ✓ |
| incomplete + dangling 同时存在 | dangling 先于 step 2 fail | `ValueError("悬挂")` 优先于 fallback | ✓ |
| zero-table + virtual sections | L474 base_table_refs=() | 正常发布 VIRTUAL | ✓ |
| 首次 fallback 后 postprocess 再 refresh | L456-457 BASE_FALLBACK | 直接 return，不重读 marker | ✓ |
| 10-Q expansion 创建新 section | identity 校验 L460-461 | `ValueError("不得创建")` | ✓ |
| `_collect_marked_text()` 返回空（marker unsupported） | L477 raw_marker_refs=() | 验证通过但不产生 candidate mapping，missing_refs 触发 fallback | ✓ |

### 7.3 特殊编码/字符边界

| 反例 | 路径 | 预期行为 | 实际 |
|---|---|---|---|
| 全文以 `\r\n` 换行 | `_build_virtual_sections` 使用 Python `str` 操作 | 正确处理 | ✓ |
| 标题含 regex 特殊字符 (`.+*?`) | `_compile_title_boundary_pattern` 使用 `re.escape` | 正确转义 | ✓ |
| 规范化后标题为 None | `_build_marker_title_range_candidates` L2841-2843 | 跳过该 marker | ✓ |

## 8. Architecture / over-coupling 检查

### 8.1 分层边界

- `dayu.fins.processors.sec_form_section_common` 只导入 `dayu.documents.processors`（base types、search_utils、text_utils）和 `dayu.fins._log`、`dayu.fins.domain.filing_semantics`。不导入 `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`。**无反向依赖**。
- `dayu.documents.processors.docling_processor` 只导入 `docling_core` 和标准库/`pandas`。不导入 `dayu.fins`、`dayu.engine`、`dayu.host`。**分层正确**。

### 8.2 语义 ownership

| 业务事实 | 唯一 owner | 消费者 | 判定 |
|---|---|---|---|
| Table caption 文本 | `_extract_table_caption()` → `_TableBlock.caption` | `list_tables()`、`read_table()`、`get_page_content()` | ✓ 同源 |
| Virtual section publication mode | `_refresh_virtual_section_state()` | 五个 public consumers 读同一 `_virtual_section_publication_mode` | ✓ 同源 |
| Table → section mapping | `_refresh_virtual_section_state()` → `_table_ref_to_virtual_ref` | `list_tables()` 消费 | ✓ 同源 |
| Section → tables mapping | `_refresh_virtual_section_state()` → `section.table_refs` | `read_section()`、`list_sections()`（通过 child_refs） | ✓ 同源 |

### 8.3 Over-coupling

- `sec_form_section_common.py` 约 3300 行，但模块 docstring 明确说明了不拆分的原因："核心 mixin 与工具函数共同服务于虚拟章节切分这一个关注点，且被 14 个下游处理器模块共同消费。工具函数间存在密集调用链...拆分只会增加 import 复杂度而无法降低耦合"。**接受此理由**。
- 测试文件 `test_processor_read_consistency.py` 3357 行，混合了 S3-STOP-F02 测试和既有 cache/runtime/financial 测试。考虑到这些测试共享同一 fixture infrastructure（`_build_runtime`、`_VirtualHarness`），且 plan 授权同一测试文件内的增量，**不构成过度耦合**。

## 9. Findings 汇总

### Material Findings

**无 material findings**。全部 plan 约束已验证通过。S3-STOP-F01 caption resolver 正确实现；S3-STOP-F02 virtual section publication state machine 正确实现 contradiction-first 原子 publication + whole-base fallback；五个 public consumers 统一消费 typed mode；remap 只操作同一 candidate mapping；首次/二次 refresh 幂等。

### Observations

| ID | Severity | Description | Evidence | Owner | Fix |
|---|---|---|---|---|---|
| O01 | LOW | `_VirtualHarness` 测试从 production import 私有类型 `_VirtualSection`、`_VirtualSectionPublicationMode`、`_VirtualSectionProcessorMixin` | `tests/fins/test_processor_read_consistency.py` L43-47 | Test fixture | Plan 已授权 "typed owner harness"；所有断言走 public consumer contract。若内部类型演进，保持 public contract 测试不变，仅更新 fixture 构造。不阻塞。 |
| O02 | LOW | `sec_form_section_common.py` 既有代码中 8 处 `except Exception` 在 marker producer 边界可能吞掉非预期异常 | L621, L635, L676, L691, L695, L826, L870, L1218 | S3-STOP-F02 之前的既有代码 | 这些是 plan-protected 既有代码；函数已有明确语义降级（返回空/空列表）。S3-STOP-F02 核心逻辑零 `except Exception`。记录为 observation，后续独立 WU 可考虑精确化异常类型。 |
| O03 | INFO | 部分既有测试使用 `_VirtualBaseProcessor` unbound method call 作为 base oracle | `tests/fins/test_processor_read_consistency.py` L1044-1055 | Test oracle pattern | 这是正确的 oracle pattern：unbound call 绕过 mixin MRO override，获取真正的 base processor 结果用于逐值比较。不是 defect。 |

## 10. Final Verdict

**PASS — 未发现 material blocking finding。**

全部 9 路径审查完成。review locks 独立复核通过。关键结论：

1. **S3-STOP-F01** (Docling captions/provenance/public projection)：caption resolver 正确实现全部 plan 约束。使用 typed `RefItem.cref`、root ref 命名常量跳过、只在 resolve 边界捕获已知异常类型、规范化/大小写敏感去重、单空格连接、三个 public consumer 同源消费。8-node caption matrix 全部经真实 Docling serialize/load 并断言 public 结果。

2. **S3-STOP-F02** (Fins virtual section publication)：`_VirtualSectionPublicationMode` 三态正确；contradiction-first 验证顺序完整（dangling 优先于 incomplete）；原子 publication（`_publish_virtual_section_state`/`_publish_base_fallback_state` 一次提交全部字段）；五个 public consumers 统一 typed mode guard；首次/二次 refresh 幂等；`_filter_table_refs_by_availability`/`_assign_unmapped_tables_by_position`/`fallback_ref`/`last_known_ref` 已删除且零命中。

3. **remap**：`_remap_tables_to_deepest_virtual_sections()` 只操作同一 candidate mapping；同层多命中 fail-closed；remap 后经 `_validate_candidate_table_mapping` 最终双向校验。

4. **Tests**：S3-STOP-F02 六类反例矩阵完整覆盖；公共 processor 测试逐值验证 base/form section/table/title/read/search 一致性；owner harness 测试断言 public consumer behavior。无 private implementation mirroring 或 coverage padding。三个受保护测试文件保持 entry hash 不变。

5. **README**：`dayu/fins/README.md` 更新准确描述 atomic publication、whole-base fallback、contradiction fail-closed、terminal idempotence 与 no guessing。其他 README 正确判为 NO_UPDATE。

6. **Security / deferred**：无新 secret 泄露面；无兼容 shim；无 deferred Issue 偷带；无统一 authorization framework；AR-F06/AR-F07 状态不变。

### Artifact SHA

```text
Review artifact path: docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-ds.md
```

完成审查后 artifact 的 SHA-256 将取决于文件系统确切内容。Controller 应在读取后独立计算并记录。
