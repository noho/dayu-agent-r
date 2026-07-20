# WU-SEMANTIC-OWNERSHIP-01 Slice 3 Code Review — AgentMiMo

## Verdict

`PASS / NO_BLOCKING_FINDING / READY_FOR_CONTROLLER_ADJUDICATION`。

## 1. Review identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 3。
- Accepted base：`9ad5711e20dd35d5a0cdc0cf79067333ff3b3daf`。
- Controller validation artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-implementation-controller-validation.md`。
- Review scope：9 paths，不含仅审第二缺陷 hunk。

## 2. Lock verification

### 2.1 9-path content manifest

Controller validation 记录 SHA-256 = `83cddc11fc114531972ad43db8f55080c0f53803d3eed76ddeb93afacf3f8b28`。

独立复核结果：

```text
83cddc11fc114531972ad43db8f55080c0f53803d3eed76ddeb93afacf3f8b28  -
```

**MATCH**。

### 2.2 Protected implementation entry hashes

| Path | Expected SHA-256 | Actual SHA-256 | Status |
|---|---|---|---|
| `dayu/documents/processors/docling_processor.py` | `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649` | `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649` | MATCH |
| `tests/fins/test_fins_ingestion_tools.py` | `6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747` | `6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747` | MATCH |
| `tests/host/test_effective_execution_config.py` | `e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf` | `e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf` | MATCH |
| `tests/runtime/test_argparse_exit.py` | `3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d` | `3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d` | MATCH |

### 2.3 Protected zero-diff paths

```text
dayu/documents/processors/base.py           : zero diff ✓
dayu/fins/processors/sec_processor.py       : zero diff ✓
dayu/fins/processors/ten_k_processor.py     : zero diff ✓
dayu/fins/processors/ten_q_processor.py     : zero diff ✓
dayu/fins/processors/bs_ten_k_processor.py  : zero diff ✓
dayu/fins/processors/bs_ten_q_processor.py  : zero diff ✓
```

## 3. Path-by-path review

### 3.1 `dayu/documents/processors/docling_processor.py` — S3-STOP-F01 protected delta

**Verdict**: PASS。

Docling caption 8-node matrix 实现复核：

1. `_extract_table_caption(table_item, document)` 签名正确接收同源 `DoclingDocument`。
2. `table_item.captions`（复数 `list[RefItem]`）遍历，`caption_ref.cref`（Python typed field）精确等于 `_DOCLING_DOCUMENT_ROOT_REF = "#"` 时静默跳过，**不调用** `resolve()`。✓
3. 非 root ref 各调用一次 `caption_ref.resolve(document)`；只捕获 `AttributeError`（未知 collection）和 `IndexError`（越界），单次调用边界精确。✓
4. `isinstance(resolved, TextItem)` 做类型收窄；`SectionHeaderItem`、`TitleItem` 等 TextItem 子类自然通过；`TableItem`、`PictureItem` 不通过。✓
5. `_normalize_whitespace(resolved.text)` 后空文本跳过；按规范化后完整字符串、大小写敏感去重（`seen` set），保留首次出现。✓
6. 多 caption 用 `" ".join(captions)` 单空格连接；`captions=[]` 或全部被跳过时返回 `None`。✓
7. `_DOCLING_DOCUMENT_ROOT_REF` 为模块级 `Final[str]` 常量。✓
8. `TextItem` 在模块级从 `docling_core.types.doc.document` 导入，非 lazy import、非 `TYPE_CHECKING`。✓
9. `getattr` / `hasattr` 为零。`except Exception` / `RuntimeError` 捕获为零。无 warning/log 副作用。✓
10. `_TableBlock.caption` 唯一缓存投影；`list_tables()`、`read_table()`、`get_page_content().tables` 三个 consumer 共享同一值。✓

受保护 8-node caption matrix 未被改写。

### 3.2 `dayu/fins/README.md`

**Verdict**: PASS。

新增两行准确描述 atomic validation / publication、whole-base fallback、contradiction fail-closed、terminal idempotence 与 no guessing。属于 `Processors` 职责，不写 WU/test list/未来计划。根 README、`dayu/README.md`、`tests/README.md` 无 diff（`NO_UPDATE`）。

### 3.3 `dayu/fins/processors/sec_form_section_common.py` — S3-STOP-F02 implementation

**Verdict**: PASS。

#### 3.3.1 State machine

- `_VirtualSectionPublicationMode` 枚举：`BUILDING`、`VIRTUAL_PUBLISHED`、`BASE_FALLBACK_PUBLISHED`。owner-private，不暴露给 public consumers。✓
- `_initialize_virtual_sections()` 设 `BUILDING` 并初始化空 `_virtual_sections`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`。✓
- `_refresh_virtual_section_state()` 是唯一 terminal transition owner：
  - `BASE_FALLBACK_PUBLISHED` → early return（幂等 no-op）。✓
  - `BUILDING` + 空 `_virtual_sections` → `_publish_base_fallback_state()`。✓
  - `BUILDING` + incomplete mapping → `_publish_base_fallback_state()`。✓
  - `BUILDING` + complete mapping → `_publish_virtual_section_state()`。✓
  - `VIRTUAL_PUBLISHED` + identity check → 保持 `VIRTUAL_PUBLISHED`。✓

#### 3.3.2 Contradiction-first validation order

1. `_validate_base_table_refs()`：缺失/重复 base `table_ref` → `ValueError` fail-closed。✓
2. `_validate_raw_marker_refs()`：dangling（不在 base 中）→ `ValueError`；重复 marker ref → `ValueError`。✓
3. `_validate_virtual_section_tree()`：ref 重复、parent_ref 悬挂、child_ref 悬挂/反向不一致 → `ValueError`。✓
4. `_validate_candidate_table_mapping()`：投影悬挂、重复分配、双向不一致 → `ValueError`。✓
5. 上述全部通过后才检查 `base_refs - mapped_refs`：非空 → whole-base fallback（`BUILDING`）或 `ValueError`（`VIRTUAL_PUBLISHED`）。✓

#### 3.3.3 Atomic publication

- `_publish_base_fallback_state()`：清空 `_virtual_sections`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`，设 `BASE_FALLBACK_PUBLISHED`。✓
- `_publish_virtual_section_state()`：一次性更新 `section.table_refs`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`，设 `VIRTUAL_PUBLISHED`。✓
- 验证期间不提前修改 published state。✓

#### 3.3.4 Five public consumers with typed mode guard

| Consumer | Guard | Base delegation |
|---|---|---|
| `list_sections()` | `mode != VIRTUAL_PUBLISHED → base` | ✓ |
| `list_tables()` | `mode != VIRTUAL_PUBLISHED → base` | ✓ |
| `get_section_title()` | `mode != VIRTUAL_PUBLISHED → base` | ✓ |
| `read_section()` | `mode != VIRTUAL_PUBLISHED → base` | ✓ |
| `search()` | `mode != VIRTUAL_PUBLISHED → base` | ✓ |

#### 3.3.5 `_remap_tables_to_deepest_virtual_sections`

- 只消费同一 `candidate_mapping`（从 `_assign_tables_to_virtual_sections` 返回，通过参数传入）。✓
- 受 `_validate_candidate_table_mapping` 最终双向校验。✓

#### 3.3.6 Deleted forbidden patterns

- `_filter_table_refs_by_availability()`：已删除。✓
- `_assign_unmapped_tables_by_position()`：已删除。✓
- `fallback_ref`、`last_known_ref`：已删除。✓
- `_collect_available_table_refs_from_base()`：已删除。✓

#### 3.3.7 Zero-table document

`base_table_refs = ()` → `base_table_ref_set = set()` → `_validate_raw_marker_refs` 无 dangling → `_validate_candidate_table_mapping` 检查空集 → `missing_refs = set() - set() = ∅` → `_publish_virtual_section_state()` 发布 `VIRTUAL_PUBLISHED`。✓

#### 3.3.8 10-K/10-Q second postprocess idempotence

`_postprocess_virtual_sections()` 默认空操作。`expand_ten_k_virtual_sections_content()` / `expand_ten_q_virtual_sections_content()` 以 `if not full_text or not virtual_sections: return` 开头；fallback 清空 `_virtual_sections` 后二次调用自然 no-op。✓

#### 3.3.9 Forbidden pattern scan on added hunks

```text
hasattr/getattr                   : zero match ✓
except Exception (in added hunks) : zero match ✓
warning/logger (in added hunks)   : zero match ✓
fallback_ref/last_known_ref       : zero match (only in removed lines) ✓
_filter_table_refs_by_availability: zero match (only in removed lines) ✓
_assign_unmapped_tables_by_position: zero match (only in removed lines) ✓
```

### 3.4 `tests/documents/test_processors.py`

**Verdict**: PASS。

Docling caption 8-node matrix 保持不变；新增 payload sniff/support、section/table/page/search/full-text、records/markdown fallback、header/context、malformed/missing metadata 边界。全部断言 public processor 结果，不调用 `_extract_table_caption()` private helper。

### 3.5 `tests/fins/test_sec_pipeline_download.py`

**Verdict**: PASS。

6-K business signal classification 参数矩阵与 candidate type/filename/rank/positive selection owner contract。断言业务结果。

### 3.6 `tests/fins/test_processor_read_consistency.py`

**Verdict**: PASS。

S3-STOP-F02 六类 owner/public counterexample matrix：

1. Public 10-K + unsupported marker + base table → base fallback，逐值比较 section refs、table refs、table `section_ref`、title/read/search。✓
2. Marker supported + complete mapping → virtual publication。✓
3. Marker supported + incomplete proof（两种子场景）→ whole-base fallback。✓
4. Duplicate/dangling/contradictory fail-closed → `ValueError`。✓
5. Zero-table document → virtual publication with empty mapping。✓
6. 10-K/10-Q second postprocess idempotence → base fallback 后二次调用幂等。✓

新增 `_VirtualHarness` 测试类正确初始化 `_base_sections`、`_base_section_contents`、`base_list_tables_call_count`。

### 3.7 `tests/fins/test_fins_ingestion_tools.py`

**Verdict**: PASS（受保护，hash 未变）。

### 3.8 `tests/host/test_effective_execution_config.py`

**Verdict**: PASS（受保护，hash 未变）。

### 3.9 `tests/runtime/test_argparse_exit.py`

**Verdict**: PASS（受保护，hash 未变）。

## 4. Cross-cutting review

### 4.1 Correctness

- State machine 转换完整：`BUILDING → VIRTUAL_PUBLISHED | BASE_FALLBACK_PUBLISHED`；`VIRTUAL_PUBLISHED → VIRTUAL_PUBLISHED`（受 identity 约束）；`BASE_FALLBACK_PUBLISHED → no-op`。✓
- Contradiction-first 顺序不可交换：base duplicate → marker dangling/duplicate → tree/bidirectional contradiction → incomplete fallback。✓
- Atomic publication：验证期间不修改 published state。✓

### 4.2 Stability

- 10-K/10-Q 二次 postprocess 幂等：fallback 后 `_virtual_sections` 为空，`if not full_text or not virtual_sections: return` 短路。✓
- `VIRTUAL_PUBLISHED` 刷新检查 published identity multiset，防止 expansion 创建/删除 section。✓

### 4.3 Maintainability

- `_VirtualSectionPublicationMode` 是 owner-private enum，不暴露到 public contract。✓
- 验证逻辑抽取为独立模块级函数（`_validate_base_table_refs`、`_validate_raw_marker_refs`、`_validate_virtual_section_tree`、`_validate_candidate_table_mapping`），可独立测试。✓
- 删除 4 个不再需要的方法/函数，减少 code surface。✓

### 4.4 Architecture boundary

- `DocumentProcessor` marker contract 零 diff。✓
- `SecProcessor` 零 diff。✓
- 10-K/10-Q/BS 同族 processor 零 diff。✓
- 没有新增 production path。✓
- 没有新增公共 schema、兼容分支或 deferred Issue 能力。✓

### 4.5 Semantic ownership

- Virtual section publication mode 是 `sec_form_section_common.py` 唯一 owner。✓
- `_refresh_virtual_section_state()` 是唯一 terminal transition owner。✓
- 五个 public consumers 只读取同一 typed mode，不反推状态。✓

### 4.6 Over-coupling

- `_assign_tables_to_virtual_sections()` 只返回 candidate mapping，不修改 published state。✓
- `_remap_tables_to_deepest_virtual_sections()` 只操作同一 candidate mapping。✓

### 4.7 Security

- Config/Host internal SQLite/EventLog = `ACCEPTED_TRUSTED_INTERNAL`。本次实现不触及。✓
- Tool Trace/audit/public/LLM/log/output/diff/review = `ZERO_REQUIRED`。本次实现不产生新投影。✓
- 没有新增 secret infrastructure、统一 authorization framework。✓

### 4.8 Tests / Coverage

- 测试断言 public contract 行为，不镜像 private implementation。✓
- 六类 counterexample matrix 完整覆盖。✓
- Fresh aggregate coverage 219/219 >=80%。✓

## 5. Findings summary

| # | Severity | Classification | Description |
|---|---|---|---|
| F-01 | Non-blocking | accepted-candidate | `_assign_tables_to_virtual_sections` 重新调用 `_build_markers(marked_text)` 做 marker 检测；若 `_initialize_virtual_sections` 已有 markers 可考虑复用以减少重复计算。当前行为正确，不影响正确性。 |
| F-02 | Non-blocking | accepted-candidate | `_publish_virtual_section_state` 用 `dict(section_by_ref)` 浅拷贝；若 `_VirtualSection` 对象在发布后被外部修改，published state 会受影响。当前所有 consumers 只读不写，无实际风险。 |

**无 blocking finding。**

## 6. Adversarial checklist

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
| 不审查范围外的变更 | ✓ PASS |
