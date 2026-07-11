# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round2 Batch E1

## Scope

- **Mode**: current changes
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `HEAD`（未提交 workspace diff）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-round2-batch-e1-code-review-ds.md`
- **Included scope**: 9 modified files + 1 untracked test file（见下方文件列表）
- **Excluded scope**: `dayu/fins/README.md`（README 变更，非代码逻辑）；仅格式化/换行的 diff hunk（不影响语义）
- **Parallel review coverage**: 无（单 reviewer 逐链路走读）

### 变更文件

| 文件 | 性质 |
|------|------|
| `dayu/fins/tools/read_runtime.py` | 核心：read runtime capability Protocol、source meta typed projection、source meta LRU、result construction 收窄 |
| `dayu/fins/tools/read_runtime_helpers.py` | 辅助：`XbrlTaxonomyProcessor` Protocol、`_normalize_json_scalar_text`、`_resolve_processor_taxonomy` 收窄 |
| `dayu/fins/tools/result_types.py` | 公共契约：result TypedDict 字段收窄（`list[dict[str, Any]]` → 具体类型） |
| `dayu/fins/storage/_fs_storage_utils.py` | `_coerce_optional_int` 参数从 `object` → `JsonValue` |
| `dayu/fins/processors/sec_section_build.py` | `_TableTextLike` Protocol、`_normalize_table_objects`/`_extract_section_table_fingerprints` 收窄 |
| `dayu/fins/processors/sec_report_form_common.py` | `_EdgarSectionLike`/`_EdgarDocumentWithSections` Protocol、`_rebuild_virtual_sections_from_edgartools` 收窄 |
| `dayu/fins/processors/sec_form_section_common.py` | `_VirtualDocumentTextLike`/`_VirtualDocumentOwner` Protocol、`_safe_virtual_document_text`/`_build_structured_split_anchor` 收窄 |
| `dayu/documents/processors/docling_processor.py` | `_DoclingLabelValue` Protocol、`_normalize_label` 收窄 |
| `tests/fins/test_read_runtime_semantic_ownership_guards.py` | 新增守护测试（untracked） |

---

## Findings

### 1 — `_parse_source_document_meta` 对 bool 字段的非 bool 输入静默转为 `False`，改变了旧代码 `bool()` 强转行为

- **入口/函数**: `_parse_source_document_meta` → 被 `_get_source_meta_cached_by_kind` / `_get_document_meta_cached` 调用
- **文件(行号)**: `dayu/fins/tools/read_runtime.py:370-376`
- **输入场景**: 仓储 raw meta JSON 中 `amended`、`is_deleted`、`ingest_complete` 字段为整数 `0`/`1`（JSON 中常见的 truthy/falsy 表达）
- **实际分支**:
  ```python
  "amended": bool(amended_value) if isinstance(amended_value, bool) else False,
  ```
  当 `amended_value` 是 `int` 类型时，`isinstance(amended_value, bool)` 为 `False`（`bool` 是 `int` 的子类，但 `int` 不是 `bool`），走入 `else False`。
- **预期行为**: 旧代码 `bool(meta.get("amended", False))` 对 `int` 值 `1` 返回 `True`，对 `0` 返回 `False`，使用 Python 标准 truthiness。
- **实际行为**: 新代码对任何非 `bool` 值（包括 `int` 1）静默返回 `False`。如果历史数据或非标准 ingestion 路径写入 `"amended": 1`，则该文档不再被标记为 amended。
- **直接证据**:
  - 旧代码（`read_runtime.py` 原 line 1833）: `"amended": bool(meta.get("amended", False))` — 用 `bool()` 强转
  - 新代码（line 370）: `bool(amended_value) if isinstance(amended_value, bool) else False` — 用 isinstance guard + 静默 `else False`
  - `_SourceDocumentMeta` TypedDict 声明 `amended: bool`（line 185），是收窄后的契约，但 `_parse_source_document_meta` 是收窄函数本身，负责把 raw JSON 转为 typed projection。它应该在发现非 bool 值时至少 log warning，而不是静默丢弃。
- **影响**: 如果 raw meta 中 bool 字段以整数形式存储，会导致 `is_deleted` 始终为 `False`（漏展示已删除文档）、`amended` 始终为 `False`（漏标修订文档）、`ingest_complete` 对缺失字段默认为 `True`（可能展示入库不完整的文档）。影响面取决于实际数据质量——如果 ingestion 始终写 `bool`，则不会触发；但收窄函数不应假设上游永远正确。
- **建议改法和验证点**:
  1. 对 `amended`/`is_deleted`/`ingest_complete` 采用 `bool(value) if isinstance(value, (bool, int)) and not isinstance(value, bool) else ...` 的兼容收窄（对 int 仍走 `bool()` 但排除 `bool` 子类），或者显式 log warning 并在 docstring 中声明"不接受 int 0/1 作为 bool 表达"。
  2. 在 `_parse_source_document_meta` 的 docstring 中明确列出每个字段的收窄规则。
  3. 补测试：传入 `{"amended": 1, "is_deleted": 0, "ingest_complete": 1}` 验证行为是否符合预期。
- **修复风险**: 低。只需调整 bool 收窄逻辑，不影响 typed projection 契约。
- **严重程度**: 中

---

### 2 — `_normalize_json_scalar_text` 在 `read_runtime.py` 和 `read_runtime_helpers.py` 中重复定义，形成双 owner

- **入口/函数**: `_normalize_json_scalar_text`
- **文件(行号)**:
  - `dayu/fins/tools/read_runtime.py:380-399`
  - `dayu/fins/tools/read_runtime_helpers.py:2031-2046`（diff 中新增）
- **输入场景**: 任何对 JSON 标量字段做文本标准化时
- **实际分支**: 两个模块各自定义了自己的 `_normalize_json_scalar_text`，实现相同但返回类型注解不同（`str | None` vs `Optional[str]`）。
- **预期行为**: 按项目语义所有权规则，"多个消费者需要同一语义时，必须复用同一个 source of truth"。`read_runtime.py` 已经大量从 `read_runtime_helpers.py` import 私有 helper（如 `_collect_parent_titles`、`_normalize_form_type_for_matching` 等），应当也从同一处 import `_normalize_json_scalar_text`。
- **实际行为**: `read_runtime.py` 定义了独立副本（line 380），`read_runtime_helpers.py` 也定义了独立副本（line 2031）。两者语义完全相同，但分属不同模块。
- **直接证据**:
  - `read_runtime.py:94-95` 的 import 列表中不包含 `_normalize_json_scalar_text`
  - `read_runtime.py:380` 定义了 `def _normalize_json_scalar_text(value: JsonValue | None) -> str | None:`
  - `read_runtime_helpers.py:2031` 定义了 `def _normalize_json_scalar_text(value: JsonValue | None) -> Optional[str]:`
  - 两个函数体完全相同：`if isinstance(value, list) or isinstance(value, Mapping): return None` + `return normalize_optional_text(value)`
- **影响**: 未来若修改标准化逻辑（如新增对 `float` 的特殊处理），可能只更新一个副本，导致两个调用路径行为不一致。当前无运行时 bug，但违反语义所有权规则。
- **建议改法和验证点**:
  1. 将 `_normalize_json_scalar_text` 的唯一定义放在 `read_runtime_helpers.py`
  2. `read_runtime.py` 从 `read_runtime_helpers` import 它
  3. 删除 `read_runtime.py` 中的重复定义
  4. 验证所有调用方行为不变（函数体相同，无行为变更）
- **修复风险**: 低。纯代码重组，语义无变化。
- **严重程度**: 中

---

### 3 — `test_fins_read_runtime_weak_typing_guards_lock_owner_boundaries` 使用 brittle source scanning 做断言

- **入口/函数**: `test_fins_read_runtime_weak_typing_guards_lock_owner_boundaries`
- **文件(行号)**: `tests/fins/test_read_runtime_semantic_ownership_guards.py:135-185`
- **输入场景**: 任何对 `read_runtime.py` / `read_runtime_helpers.py` 或其他 targeted 文件的代码变更
- **实际分支**: 测试通过字符串匹配检查源码中不存在特定反模式。例如：
  ```python
  assert "_meta_cache: dict[tuple[str, str], Optional[dict[str, Any]]]" not in read_runtime_source
  assert ") -> list[dict[str, Any]]" not in _function_source(read_runtime_source, "_collect_source_documents")
  ```
- **预期行为**: 测试应断言 contract/行为级别（如"source meta cache 是有界 LRU 而非无界 dict"），而非对特定源码字符串做存在性检查。
- **实际行为**: 以下场景会误杀（false positive）或漏杀（false negative）：
  - **False positive**: 如果有人注释中写了 `_meta_cache: dict[tuple[str, str], Optional[dict[str, Any]]]`，测试失败但代码正确
  - **False positive**: 如果函数签名被 reformat 成多行但语义相同，`") -> list[dict[str, Any]]"` 检测失效
  - **False negative**: 如果有人在其他函数中重新引入 `getattr(processor` 但不在 `read_runtime_source` 中，测试不会捕获
  - **False positive**: 变量重命名、空格变化、类型注解从 `dict[str, Any]` 变为 `dict[str, JsonValue]`（仍在 `read_runtime_helpers.py` 中）— 这些是合法的渐进式改进，但字符串匹配无法区分
- **直接证据**:
  - Line 148: `read_runtime_source = Path("dayu/fins/tools/read_runtime.py").read_text(encoding="utf-8")` — 全文读取源码做字符串搜索
  - Line 168: `assert "getattr(processor" not in read_runtime_source` — 字符串级断言
  - Line 170-175: 对函数源码片段的字符串模式匹配
  - Line 176-185: 对多个文件的 `forbidden_object_signatures` 精确字符串匹配
- **影响**: 测试脆弱，不随代码自然演进。格式化工具（如 ruff/black）的批量重排或类型注解的渐进收窄都可能打破测试。这种测试会让后续贡献者对修改目标文件产生不必要的恐惧。
- **建议改法和验证点**:
  1. 保留字符串扫描测试作为**信息性检查**（warning），但将核心断言改为**行为级**：验证 `FinsReadRuntime` 的 `_meta_cache` 是 `ProcessorLRUCache` 实例（而非 dict）、验证特定 public 方法的返回类型不含 `dict[str, Any]`（通过 `typing.get_type_hints` 或 runtime isinstance 检查）。
  2. `forbidden_object_signatures` 部分可以用 AST 而非字符串匹配：解析每个目标文件的 AST，检查函数签名的参数注解是否为 `object` / `Any`。这样对格式化不敏感。
  3. 如果保留字符串扫描作为 regression guard，在测试 docstring 中明确说明"本测试对格式敏感，仅用于防止特定已知反模式回归；格式化变更可能需要更新本测试"。
- **修复风险**: 中。将测试从字符串扫描迁移到 AST/行为级断言需要理解现有代码结构。
- **严重程度**: 低

---

### 4 — `test_read_runtime_source_meta_cache_is_bounded` 对私有字段 `_meta_cache` 做断言，依赖内部实现细节

- **入口/函数**: `test_read_runtime_source_meta_cache_is_bounded`
- **文件(行号)**: `tests/fins/test_read_runtime_semantic_ownership_guards.py:112-132`
- **输入场景**: `FinsReadRuntime` 内部缓存实现变更
- **实际分支**:
  ```python
  assert runtime._meta_cache.size() == 2
  assert [key.document_id for key in runtime._meta_cache.keys_snapshot()] == ["doc-2", "doc-3"]
  ```
- **预期行为**: 测试应断言 **contract 级别** 行为——缓存是有界的（不会无限增长），而非断言内部 `_meta_cache` 的具体方法和 LRU 逐出顺序。
- **实际行为**: 直接访问 `runtime._meta_cache`（私有属性），并调用 `size()` 和 `keys_snapshot()` 方法，然后断言 LRU 顺序是 `["doc-2", "doc-3"]`。如果 `ProcessorLRUCache` 的内部实现改变（如 `keys_snapshot` 排序方向改变），测试会失败，但运行时行为可能不受影响。
- **直接证据**:
  - Line 131: `assert runtime._meta_cache.size() == 2` — 访问私有字段
  - Line 132: `assert [key.document_id for key in runtime._meta_cache.keys_snapshot()] == ["doc-2", "doc-3"]` — 断言内部 LRU 顺序
- **影响**: 如果 `ProcessorLRUCache` 的实现细节变更（如 snapshot 顺序从"从旧到新"变为"从新到旧"），测试会失败，但 cache 有界性的 contract 并未改变。这违反了"测试必须断言 owner 级 contract 行为；禁止让测试固化偶然行为"的项目约束。
- **建议改法和验证点**:
  1. 建议在 `FinsReadRuntime` 上暴露一个 public 或 test-facing 方法（如 `meta_cache_size() -> int`）返回缓存条目数，避免测试直接访问 `_meta_cache`。
  2. LRU 顺序断言应改为：验证插入 doc-1/doc-2/doc-3 后 doc-1 不再能被 `_get_document_meta_cached` 命中（因为被逐出），而非断言内部 snapshot 顺序。这才是真正的 contract 行为——"超出容量后最旧的条目被逐出"。
  3. 或者，将 `keys_snapshot` 的排序约定放入 `ProcessorLRUCache` 的 docstring 并作为 stable API 承诺，然后测试可以安全依赖它。
- **修复风险**: 低。只需调整断言方式。
- **严重程度**: 低

---

### 5 — `_iter_sections` 仍使用 `document: Any` 和 `getattr` 动态访问，Protocol 收窄未传播到调用链末梢

- **入口/函数**: `_iter_sections` → 被 `_rebuild_virtual_sections_from_edgartools` 调用
- **文件(行号)**: `dayu/fins/processors/sec_section_build.py:716-732`
- **输入场景**: `_rebuild_virtual_sections_from_edgartools` 接收 `_EdgarDocumentWithSections`（已收窄），但内部立即调用 `_iter_sections(document)`，而 `_iter_sections` 签名仍是 `document: Any`
- **实际分支**:
  ```python
  # _iter_sections (sec_section_build.py:729)
  sections_obj = getattr(document, "sections", None)
  if not isinstance(sections_obj, dict):
      return []
  ```
- **预期行为**: 既然 `_rebuild_virtual_sections_from_edgartools` 已把参数收窄为 `_EdgarDocumentWithSections`（要求 `sections: dict[str, _EdgarSectionLike]`），下游 `_iter_sections` 应接收同样的窄类型或至少 `_EdgarDocumentWithSections`，消除 `getattr` 动态访问。
- **实际行为**: `_iter_sections` 仍用 `getattr(document, "sections", None)` 做动态访问，类型信息在调用链末梢丢失。`_rebuild_virtual_sections_from_edgartools` 的 Protocol 收窄只在类型检查层面生效，运行时 `_iter_sections` 仍用 duck typing。
- **直接证据**:
  - `_rebuild_virtual_sections_from_edgartools`（`sec_report_form_common.py:519`）参数类型为 `_EdgarDocumentWithSections`
  - `_iter_sections`（`sec_section_build.py:716`）参数类型为 `Any`，line 729 使用 `getattr(document, "sections", None)`
  - `_iter_sections` 未被本批次修改（不在 diff 中）
- **影响**: Protocol 收窄的效果被削弱——`_rebuild_virtual_sections_from_edgartools` 的调用者得到类型安全，但内部链路仍依赖运行时 duck typing。这不是功能 bug（运行时行为正确），但违反了"收窄应从 owner boundary 一致传播"的语义所有权原则。`_iter_sections` 是 `_EdgarDocumentWithSections` 的下游消费者，应受益于上游的类型收窄。
- **建议改法和验证点**:
  1. 将 `_iter_sections` 的参数类型从 `Any` 改为 `_EdgarDocumentWithSections`（或从 `sec_report_form_common` import，或把 Protocol 移到共享位置）
  2. 将函数体内的 `getattr(document, "sections", None)` 改为 `document.sections`（直接属性访问）
  3. 检查 `_iter_sections` 是否有其他调用方（当前只有 `_rebuild_virtual_sections_from_edgartools` 一处），如有则一并更新
- **修复风险**: 低。行为不变，仅类型收窄。
- **严重程度**: 低

---

### 6 — `get_financial_statement` result construction 中 `rows` 不再做 `isinstance(rows, list)` 校验

- **入口/函数**: `FinsReadRuntime.get_financial_statement`
- **文件(行号)**: `dayu/fins/tools/read_runtime.py:1627-1633`
- **输入场景**: processor 的 `get_financial_statement` 返回了非 list 类型的 `rows`（如 dict、str、或自定义对象）
- **实际分支**:
  ```python
  rows = statement_payload.get("rows")
  if rows is None:
      raise ValueError("processor get_financial_statement result missing rows")
  for _row in rows:
      _raise_if_fins_cancelled(cancellation_token)
  ```
- **预期行为**: 旧代码有 `if isinstance(rows, list):` 守护（原 line 1603），当 `rows` 不是 list 时跳过迭代，返回结果不含 rows 遍历的取消检查。新代码只检查了 `rows is None`。
- **实际行为**: 若 processor 返回 `"rows": {"key": "value"}`（非 None 非 list），`for _row in rows:` 会遍历 dict keys，不会抛异常但语义错误。若返回 `"rows": 42`（非 None 非 iterable），`for _row in rows:` 抛出 `TypeError`，未被 catch。
- **直接证据**:
  - 旧代码（原 read_runtime.py diff line 1602-1604）: `rows = result.get("rows")` → `if isinstance(rows, list): for _row in rows: ...`
  - 新代码（line 1627-1633）: `rows = statement_payload.get("rows")` → `if rows is None: raise ValueError(...)` → `for _row in rows: ...` 无条件迭代
- **影响**: processor contract violation 时（rows 非 list），错误从静默吞下变为 `TypeError` 或静默语义错误。`TypeError` 传播比静默吞下更好（fail loud），但 `for _row in rows:` 对 dict 不会报错（遍历 keys），这种场景仍然静默。建议统一加 `isinstance(rows, list)` 校验，与 XBRL 路径的 `isinstance(normalized_facts, list)` 风格一致。
- **建议改法和验证点**:
  1. 在 `rows = statement_payload.get("rows")` 之后增加 `if not isinstance(rows, list): raise ValueError(...)`
  2. 参照 XBRL 路径 line 1807-1808 的 `if not isinstance(normalized_facts, list): raise ValueError(...)` 模式保持一致性
- **修复风险**: 低。仅增加校验，正常路径不受影响。
- **严重程度**: 低

---

## Open Questions

1. **`_parse_source_document_meta` 对 `material_name` 不做收窄**：`material_name` 字段直接透传 `raw_meta.get("material_name")`（`JsonValue | None`），而其他字符串字段都通过 `_normalize_json_scalar_text` 收窄。是否有意为之（因为 `material_name` 可以是嵌套 JSON 对象），还是遗漏？从 `_SourceDocumentMeta` TypedDict 的声明 `material_name: JsonValue | None` 来看是有意保留的，但建议在 docstring 中明确说明。

2. **`sc13_processor.py` 中 `_safe_virtual_document_text(self)` 的类型兼容性**：`Sc13FormProcessor` 继承自 `_BaseSecReportFormProcessor` → `_VirtualSectionProcessorMixin` → `SecProcessor`。`SecProcessor.__init__` 中 `self._document = _parse_document(...)` 且 `_parse_document` 返回 `Any`。`_VirtualDocumentOwner` Protocol 要求 `_document: _VirtualDocumentTextLike`（有 `.text()` 方法）。虽然 edgartools 文档对象在运行时确实有 `.text()`，但类型层面 `_document` 是 `Any`，pyright 可能无法验证 `_VirtualDocumentOwner` 的 structural match。需确认 pyright 对此路径的实际检查结果。

3. **`_build_citation` 中 `_get_source_meta_cached_by_kind` 与 `_resolve_source_kind` 的双重 IO**：`_build_citation`（line 2168-2169）先调 `_resolve_source_kind`（在 FILING/MATERIAL 中尝试 `get_source_handle`），再调 `_get_source_meta_cached_by_kind`（调 `get_source_meta`）。这是两次独立 IO。旧代码也是同样模式，但这是一个可优化的 N+1 模式（非本次引入）。

---

## Residual Risk

1. **`_get_document_meta_cached` 对不存在的文档永久缓存 None**：一旦某 document_id 被确认不存在，`None` 被写入 LRU 缓存，后续即使该文档被异步 ingestion 写入，缓存中的 `None` 仍会阻止读取。这是**旧代码的既有行为**（旧无界 dict 也有同样问题），不是本批次回归。但引入 LRU 后，缓存驱逐可以部分缓解（长时间运行后 None 会被自然逐出）。建议未来增加 TTL 或显式 invalidate 机制。

2. **测试覆盖范围**：`source .venv/bin/activate && pytest -q tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py -k "citation or xbrl or read_runtime"`（总计 18 passed）。覆盖了：
   - taxonomy Protocol 识别/失败传播
   - source meta cache 有界性
   - weak typing guards（字符串扫描）
   - import boundary
   - 既有的 read runtime / citation 测试

   **未覆盖**：
   - `_parse_source_document_meta` 对非标准 bool/int 输入的单元测试
   - `_normalize_json_scalar_text` 对非标量输入（list/dict）的单元测试
   - `get_financial_statement` 结果构造中 `statement_locator` 为 None 时的默认构造路径
   - SEC/Docling Protocol 收窄的端到端集成测试（依赖真实 edgartools/docling 对象）

3. **`read_runtime_helpers.py` 中的 `_build_recommended_documents` 与 `read_runtime.py` 中的 `_build_recommended_documents_for_list_result` 功能重叠**：两者做相同的推荐槽位填充，但前者操作 `Mapping[str, JsonValue]`（泛型），后者操作 `_ListedDocumentSummary`（TypedDict）。这是刻意设计的 dual path（helpers 版本供旧调用方，read_runtime 版本供 typed path），但两套实现需要保持同步。本批次已将 `list_documents` 主路径迁移到 typed 版本。

4. **pyright 覆盖范围**：实现说明声明 `python -m pyright dayu/ tests/ utils/` 0 errors 0 warnings。这覆盖了全部生产代码和测试代码，范围充分。

---

## 总评

本批次 E1 diff 在 read runtime capability Protocol 化、source meta typed projection、source meta LRU 有界缓存、object signature 收窄四个方向上都达成了设计目标。未发现 blocking correctness 或 data corruption 风险。

主要发现集中在：
- `_parse_source_document_meta` 中 bool 收窄的 int0/1 行为变更（Finding 1，中危）
- `_normalize_json_scalar_text` 双 owner 问题（Finding 2，中危）
- 测试的 brittle source scanning 和 private-field assertion（Findings 3/4，低危）
- Protocol 收窄未传播到 `_iter_sections`（Finding 5，低危）
- `get_financial_statement` rows 缺少 `isinstance` 校验（Finding 6，低危）

上述 finding 均不阻止 merge，但建议在后续 batch 中处理 Finding 1 和 Finding 2。
