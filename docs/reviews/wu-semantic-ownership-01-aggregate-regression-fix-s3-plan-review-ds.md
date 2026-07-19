# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Plan Review (AgentDS Second Independent Adversarial)

## 0. Gate Identity

- **日期**: `2026-07-19T15:51:58+08:00`。
- **Umbrella**: `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- **Gate**: Slice 3 corrected plan 第二路独立 adversarial plan review；非 AgentMiMo 结论复用。
- **Review target**: Corrected plan SHA-256 `ef4a0832f1885e4013d673294b944a56280619baab1f97d438896af5c8cbedcf`（`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`）及 plan correction artifact SHA-256 `c5b788b03ab54638841a7bd58cb8d5978ef92de8ea120ff3a3408aedbaac2072`（`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-codex.md`）。
- **Immutable slice base**: `9e7a4e9d4796b9c382d44494bb10efa64787b199`。
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-controller-validation.md`，verdict `PASS / PLAN_CORRECTION_SCOPE_VALID / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW`。

## 0a. Review Scope And Non-Goals

### Scope

- 审查完整 corrected plan（含 §0–§10 全部内容）及 S3 plan correction artifact 的全部 claim，挑战：
  - 根因 / 唯一 owner 是否正确。
  - `TextItem` import / boundary 是否与项目依赖契约一致。
  - 同 document 真源传递是否正确。
  - multi-caption 业务组合规则（ref 顺序、规范化、去重、大小写、分隔符、连接）是否正确完备。
  - dangling ref 精确异常边界（`AttributeError` / `IndexError`）是否精确。
  - model-invalid loader oracle 的失败边界是否正确。
  - non-text refs skip 规则是否正确。
  - list/read/page 三 public view 与真实 provenance 一致性。
  - scope / protected locks 是否健全。
  - README / canonical / 219 coverage / pyright / Ruff / build / scans / smokes / security 是否无漂移。
  - trusted internal secret 分类、Gemini quota、AR-F06/07、deferred/no-code 边界是否维持。
  - 反例、测试不可达 / 错误假设、异常分类遗漏、overdesign/underdesign、门禁漂移。

- 使用直接代码证据、当前 `docling-core==2.74.0` public API、Docling 真实 `save_as_json()` / `load_from_json()` 行为、现有 test delta 和保护状态进行证伪。

### Non-Goals

- 不修改 plan、code、tests、control 或任何其它 artifact。
- 不 stage、commit、push、PR 或 closeout。
- 不进入 implementation gate。
- 不复用 AgentMiMo 结论；本 review 是完全独立的第二路。

## 1. Key Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | `TableItem.captions` 是 `list[RefItem]`，默认空列表 | ✅ confirmed — `docling-core==2.74.0` `TableItem.model_fields["captions"].annotation` 为 `list[RefItem]` |
| A2 | `RefItem.resolve(doc)` 是 Docling public reference resolution method | ✅ confirmed — `inspect.getsource(RefItem.resolve)` 确认为 public method |
| A3 | `TextItem` 子类（`SectionHeaderItem` 等）满足 `isinstance(x, TextItem)` | ✅ confirmed — `SectionHeaderItem`, `TitleItem`, `ListItem`, `CodeItem`, `FormulaItem` 均 `issubclass(..., TextItem)` |
| A4 | `PictureItem` / `TableItem` 不是 `TextItem` | ✅ confirmed — `issubclass(PictureItem, TextItem)` = `False`，`issubclass(TableItem, TextItem)` = `False` |
| A5 | `_build_tables()` 已持有 `DoclingDocument` 但未传给 caption resolver | ✅ confirmed — line 628 `caption = _extract_table_caption(table_item)` 只传 `table_item`，丢弃同 scope 的 `document` |
| A6 | 旧 `_extract_table_caption` 读不存在的单数 `caption` 属性 | ✅ confirmed — line 1185 `getattr(table_item, "caption", None)` 在 `docling-core==2.74.0` 的 `TableItem` 上不存在 |
| A7 | 三 public view（`list_tables` / `read_table` / `get_page_content`）统一消费 `_TableBlock.caption` | ✅ confirmed — line 277, 359/372, 1483 均直接使用 `table.caption` |
| A8 | model-invalid ref 在 `DoclingDocument.load_from_json()` 边界失败 | ❌ **REFUTED** — 见 Finding 1 |
| A9 | `AttributeError` 与 `IndexError` 精确区分 dangling ref 数据边界 | ⚠️ **PARTIALLY CORRECT** — 见 Finding 2 |
| A10 | `docling-core>=2.74.0,<3.0.0` 是项目必需依赖，`TextItem` 模块级 import 安全 | ✅ confirmed — `docling-core` 已在 `docling_processor.py:19` 由 `TYPE_CHECKING` 块导入同包 |

## 2. Findings

### S3-PR-DS-F01 — 严重 — model-invalid ref 不在 `load_from_json()` 边界失败，plan 的 fail-safe 分类有 blind spot

- **位置**: Corrected plan §4.3 item 6（"语法非法...必须在真实 DoclingDocument.load_from_json() 边界失败"）；plan correction artifact §6（"语法非法、不能构成 Docling RefItem 的 payload 在真实 DoclingDocument.load_from_json() 边界失败"）；test oracle §4.3 item 4（"语法非法 ref case...从 public processor 构造入口断言现有 Docling JSON parsing error"）。

- **问题类型**: 异常分类遗漏 / 不可直接实施。

- **当前写法**: Plan 声称 model-invalid ref 在 `DoclingDocument.load_from_json()` 边界失败，不是 caption resolver 的 fail-safe 输入。Resolve 必须 "禁止 `except Exception`"，`RuntimeError` 属于必须传播的异常。

- **反例 / 失败场景**: 直接实验证据：
  ```text
  # 合法 Docling JSON: captions = [{"$ref": "#/texts/0"}]
  # 修改为 model-invalid cref: captions = [{"$ref": "not-a-valid-cref"}]
  ```
  结果：
  1. `DoclingDocument.load_from_json(corrupted_file)` **成功** —— `RefItem.cref` 是 `str` 类型，无 regex 校验，`"not-a-valid-cref"` 是合法 Pydantic string value。返回的 `DoclingDocument` 包含 `RefItem(cref='not-a-valid-cref')`。
  2. 随后 `RefItem.resolve(doc)` 抛出 `RuntimeError("Unsupported number of path components: 1")`。
  3. Plan §4.3 item 5-6 将 `RuntimeError` 分类为"必须继续暴露"，不做 fail-safe 捕获。

  **影响**: 一个真实 Docling JSON 文件如果 caption ref 的 `$ref` 是合法字符串但不符合 `#/collection/index` 格式（1 组件、4+ 组件），会绕过 `load_from_json()` 校验，随后在 `resolve()` 中抛出 `RuntimeError`，导致整个 Docling 文档处理崩溃，而不是优雅跳过坏 caption。

  **补充反例**: `RefItem(cref='#/texts/0/extra')` → 4 组件 → `RuntimeError("Unsupported number of path components: 4")`，同样不被捕获。

  **只有一种情况在 `load_from_json()` 失败**: 将 `captions` entry 整体替换为非对象（如 `"not-a-refitem"`）→ Pydantic `ValidationError`。但这与 plan 描述的"替换 `$ref` 值"是不同的测试场景。Plan 描述的测试 oracle 无法按所述方式产生 `load_from_json()` 失败。

- **为什么有问题**: Plan 的错误分类假设（"model-invalid ref → load boundary fails → no need for resolver fail-safe"）被直接实验证据推翻。`RefItem` 的 `cref: str` 字段没有 Pydantic validator/regex constraint。导致 plan 分类为"必须传播"的 `RuntimeError` 实际上可以来自真实 Docling JSON 中的格式错误 ref，而不只是编程错误。

- **直接证据**:
  - `docling_core/types/doc/document.py` `RefItem` 定义：`cref: str`（无 validator）。
  - `RefItem.resolve()` source code（inspect）：1 component → `RuntimeError("Unsupported number of path components: 1")`；4+ components → `RuntimeError("Unsupported number of path components: N")`。
  - 实验验证：`DoclingDocument.load_from_json()` 对 `{"$ref": "not-a-valid-cref"}` 返回合法的 `DoclingDocument`，随后 `resolve()` 抛出 `RuntimeError`。

- **影响**: 实施 Agent 按 plan 写代码后会得到一个对真实 Docling 畸变数据脆弱的 caption resolver——格式异常的 `$ref` 值会导致整个文档处理崩溃，而不是跳过坏 caption 继续处理有效表格。这违反了 plan 自身的 fail-safe 设计意图（"可选 caption metadata fail-safe"）。

- **建议改法和验证点**:
  1. **方案 A（推荐）**: 将 `RuntimeError` 也纳入 caption fail-safe 边界，但窄化捕获范围——只捕获来自 `RefItem.resolve()` 的 `RuntimeError`，不捕获 production 代码自身的 `RuntimeError`。实现方式：在 `RefItem.resolve()` 调用周围用 `try/except RuntimeError` 精确包裹，或检查 `cref.split("/")` 的组件数是否为 3，非 3 直接跳过（不调用 `resolve()`）。
  2. **方案 B**: Plan 明确承认 model-invalid cref 的 `RuntimeError` 会崩溃处理器，将其记录为 known limitation。但需修正 test oracle——不是"断言 Docling JSON parsing error"，而是"断言 processor 在 resolve 时以 RuntimeError 崩溃，或直接跳过（取决于方案选择）"。
  3. 修正 plan 中关于 `load_from_json()` 边界的错误声称。`load_from_json()` 只拒绝结构性不合法的 JSON（非 dict → ValidationError），不校验 `cref` 值语义。
  4. 测试必须覆盖至少 1 组件、4 组件两种 syntactically invalid cref 情况。

- **修复风险（方案 A）**: 低——只在 existing `_extract_table_caption` 中增加一个精确的 `try/except RuntimeError` 或 `cref.split("/")` 组件数预检，不改变 public contract 或其它 owner。

- **修复风险（方案 B）**: 中——需用户接受 processor crash 作为 known limitation，且需更新 stop condition 声明。

- **严重程度**: **严重** — Plan 要求实现时做决策的核心事实（失败边界位置）是错误的，导致实现 agent 要么写出崩溃代码（跟随 plan verbatim），要么必须在 implementation 时重新设计异常分类（违反 plan 的"不得重新设计"约束）。

- **Owner**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` §4.3 item 5–6（error classification boundary）+ test oracle §4.3 item 4（model-invalid test oracle）。

---

### S3-PR-DS-F02 — 中 — `RefItem.resolve()` 异常分类基于间接推断而非 `resolve()` 源码直接证据

- **位置**: Corrected plan §4.3 item 5；plan correction artifact §6。

- **问题类型**: 契约缺失 / root cause 间接推断。

- **当前写法**: Plan 将 `AttributeError` 分类为"未知 document collection"、`IndexError` 分类为"越界 index"。Plan correction artifact §6 写 "public resolve() 因未知 collection 抛出的 AttributeError 或因越界抛出的 IndexError"。

- **反例 / 失败场景**: `RefItem.resolve()` 源码为：
  ```python
  def resolve(self, doc):
      path_components = self.cref.split("/")
      if (num_comps := len(path_components)) == 3:
          _, path, index_str = path_components
          index = int(index_str)
          obj = doc.__getattribute__(path)[index]
      elif num_comps == 2:
          _, path = path_components
          obj = doc.__getattribute__(path)
      else:
          raise RuntimeError(...)
      return obj
  ```
  Plan 的分类在实践上成立（`doc.__getattribute__(path)` 对不存在 collection 抛 `AttributeError`，`[index]` 对越界抛 `IndexError`），但 plan 没有明确：
  1. `doc.__getattribute__(path)[index]` 中的 `IndexError` 也可以来自 3 组件 cref 中 path_components 的下标访问（理论上不可能，因为 `len==3` 已保证 `path_components[1]` 和 `[2]` 存在）。
  2. `int(index_str)` 对非数字 index 抛 `ValueError`——但这不在 plan 的分类表中。
  3. 2 组件 cref（如 `#/texts`）返回整个 `list[TextItem]`，不是 `TextItem` 实例，`isinstance(resolved, TextItem)` 会正确地将其过滤掉——但 plan 未提及 2 组件情况。

  `#/texts/NaN` → `int("NaN")` → `ValueError`。Plan 将 `ValueError` 列入"必须传播"类别。但 `#/texts/NaN` 格式的 cref 在真实 Docling JSON 中是可能的畸变数据。

- **为什么有问题**: Plan 的异常分类虽然没有错误（`AttributeError`/`IndexError` 确实是 resolve 的主要 dangling-ref 异常），但它没有穷举 `resolve()` 可能抛出的异常类型，导致 implementation agent 可能漏掉 `ValueError`（非数字 index）从 docling data 路径抛出的情况。`ValueError` 被 plan 分类为"必须传播"而非 fail-safe，与 `RuntimeError` 有相同的问题。

- **直接证据**: `RefItem.resolve()` 源码 `int(index_str)` 行——如果 `index_str` 不是合法整数，抛 `ValueError`。

- **影响**: 实施 Agent 按 plan 逐字实施后，`#/texts/NaN` 格式的 caption ref 会导致 processor 以 `ValueError` 崩溃而非跳过。

- **建议改法和验证点**: 将 `int(index_str)` 产生的 `ValueError` 也纳入 caption fail-safe 边界。做法：在 resolve 调用周围只捕获 `(AttributeError, IndexError, ValueError, RuntimeError)`——四类均为 Docling ref resolution 可能因为数据畸变而抛出的异常。Plan 不需要额外的精确区分逻辑，因为这四类异常在 caption fail-safe 上下文中都具有相同的语义：该 ref 无法解析为有效 TextItem，跳过即可。测试新增 `#/texts/NaN` case。

- **修复风险**: 低——三行 `try/except` 范围变化。

- **严重程度**: **中** — 与 S3-PR-DS-F01 属于同一类"异常分类基于间接推断"问题，但 `ValueError` 场景比 `RuntimeError` 更边缘（要求 Docling serializer 产出非数字 index）。F01 覆盖了最高概率的失败模式。

- **Owner**: Corrected plan §4.3 item 5–6。

---

### S3-PR-DS-F03 — 中 — JSON 序列化 `$ref` 与 Python 模型 `cref` 术语不一致，plan correction artifact 的 test oracle 描述可能误导 implementation agent

- **位置**: Plan correction artifact §6（"符合 JSON-pointer shape 但 dangling 的 ref"）；corrected plan §4.3 test oracle item 4（"captions[*].$ref 替换为 model-invalid 值"）。

- **问题类型**: 不可直接实施。

- **当前写法**: Plan 交替使用 `$ref`（指 JSON serialization key）和 `RefItem` / `cref`（指 Python model field）。Plan correction artifact 写 "符合 JSON-pointer shape"。Test oracle 写 "只把 serialized captions[*].$ref 替换为 model-invalid 值"。

- **反例 / 失败场景**: 直接实验：`RefItem.model_dump(mode='json')` 产出 `{"cref": "#/texts/0"}`，但 `DoclingDocument.save_as_json()` 产出 `[{"$ref": "#/texts/0"}]`。两者使用不同的序列化键名。实施 agent 如果只读 plan 的 "JSON-pointer shape" 描述而不知道 Docling 在 JSON 序列化路径使用 `$ref` alias、在 Python 路径使用 `cref`，可能在测试或 production 代码中写错字段名。

  现有测试 helper `_ref_item(ref)` 使用 `RefItem.model_validate({"$ref": ref})`——这表明 `$ref` 是 Pydantic validation alias。Plan 的 test oracle 使用 `$ref` 是正确的（操作 JSON serialization），但需要 implementation agent 理解 `$ref`（JSON）→ `cref`（Python）的映射关系。

- **为什么有问题**: Plan 没有明确说明 Docling 的 `RefItem` JSON alias 是 `$ref`、Python field 是 `cref`。implementation agent 可能在 production 代码中尝试访问 `ref.$ref` 或在测试中错误构造 ref。

- **直接证据**:
  - `RefItem.model_fields` → `{'cref': FieldInfo(...)}`（Python field 是 `cref`）
  - `doc.save_as_json()` → `captions: [{"$ref": "#/texts/0"}]`（JSON key 是 `$ref`）
  - 测试 helper: `RefItem.model_validate({"$ref": ref})`（JSON alias 在 validation 时可用）

- **影响**: 实施 Agent 误解后可能写出错误的代码或测试 fixture。若 implementation agent 已读过现有 `_ref_item` helper 和 Docling 源码则不会受影响，但 plan 不应依赖 implementation agent 的额外研究。

- **建议改法和验证点**: 在 plan §4.3 或 correction artifact 中增加一句："Docling RefItem 的 Python field 是 `cref`，JSON serialization key 是 `$ref`；resolver 只使用 Python API `table_item.captions` → `RefItem.resolve(doc)`；tests 操作 serialized JSON 时使用 `$ref` key。" 这是纯文档修正，不改变任何实现语义。

- **修复风险**: 极低——plan-only 文字补充。

- **严重程度**: **中** — 不影响 plan 的正确性（所有实现语义都是正确的），但增加了 implementation agent 犯错的风险。若 implementation agent 已经熟悉 Docling API，影响降为低。

- **Owner**: Plan correction artifact §6。

---

### S3-PR-DS-F04 — 中 — multi-caption 空白规范化的去重规则未考虑 non-breaking space 等 Unicode 空白字符

- **位置**: Corrected plan §4.3 item 4（"规范化为空的文本忽略；按规范化后的完整字符串精确相等、大小写敏感去重"）。

- **问题类型**: 契约缺失 / 反例。

- **当前写法**: Plan 使用 `_normalize_whitespace()` 做空白规范化，然后大小写敏感精确字符串比较去重。`_normalize_whitespace()` 的实现是 `" ".join(str(text or "").split())`。

- **反例 / 失败场景**: Python `str.split()` 默认按 ASCII whitespace（空格、`\t`、`\n`、`\r`、`\v`、`\f`）分割，但不分割 Unicode non-breaking space（`\xa0`）、thin space（` `）等。因此：
  - `"Consolidated\xa0Statements"` 规范化后 = `"Consolidated\xa0Statements"`（NBSP 保留）
  - `"Consolidated Statements"` 规范化后 = `"Consolidated Statements"`
  - 两者不会被去重，caption 会变成 `"Consolidated\xa0Statements Consolidated Statements"` 的重复连接结果

  财报 PDF 转换（尤其 Docling 处理的 HTML/PDF）可能引入 NBSP。这在真实 Docling 表格标题中是可复现场景。

- **为什么有问题**: Plan 的"精确去重"语义正确，但底层 `_normalize_whitespace` 不处理 NBSP，导致两个语义相同的 caption（仅 NBSP vs 普通空格）不会被去重，产生重复 caption 文本。

- **直接证据**:
  - `dayu/documents/processors/text_utils.py:28`: `return " ".join(str(text or "").split())`
  - `str.split()` 文档："If sep is not specified or is None... runs of consecutive whitespace are regarded as a single separator" —— Python 默认 whitespace 不含 NBSP。

- **影响**: 多 caption 连接后可能出现重复语义。

- **建议改法和验证点**:
  1. **方案 A**: 在接受本次 plan 前确认这是一个"low-probability、留到未来改进"的 known limitation，当前 `_normalize_whitespace` 保持不变。在 residual risk 中记录。
  2. **方案 B**: 在 `_normalize_whitespace` 调用前对 caption text 做 `text.replace('\xa0', ' ')` 预处理。但这会触及 text_utils 的通用语义，可能超出 S3 scope。
  3. 测试至少记录 NBSP 行为的现状（不要求修复），防止未来不知道这个 gap。

- **修复风险**: 方案 A 零风险；方案 B 低风险但需评估 `text_utils` 变更的 blast radius。

- **严重程度**: **中** — 严格来说这是一个 pre-existing `_normalize_whitespace` 行为特性，不是 S3 plan 引入的新缺陷。但 plan 将 `_normalize_whitespace` 作为 multi-caption 规范化的唯一手段，应至少记录此限制。

- **Owner**: Corrected plan §4.3 item 4 或 residual risk section。

---

### S3-PR-DS-F05 — 低 — `infer_caption_from_context` 存在现有 fallback 路径，plan 未明确其与新 caption resolver 的关系

- **位置**: Corrected plan §4.3（整体 caption 语义设计）。

- **问题类型**: 契约缺失。

- **当前写法**: Plan 只描述 `_extract_table_caption` → `_TableBlock.caption` 的新路径，未提及 `text_utils.infer_caption_from_context` 的现有 fallback。

- **反例 / 失败场景**: `dayu/documents/processors/text_utils.py` 提供 `infer_caption_from_context(context_before: str) -> Optional[str]`，从表格前文推断 caption。但检查 production code 后发现，该函数未被 `docling_processor.py` 调用——`_TableBlock.caption` 完全由 `_extract_table_caption` 填充，`context_before` 是独立字段。因此不存在"从 context_before 推断 caption 作为 fallback"的现有耦合。

- **为什么有问题**: 最初怀疑存在隐式耦合，但直接代码检查证伪了该怀疑。提升为记录性 finding 以防止 future 实施 agent 误加 fallback。

- **直接证据**: Grep `docling_processor.py` 全文——`infer_caption_from_context` 在该文件中零引用。

- **影响**: 无当前影响。但 plan 应明确声明"禁止在 caption resolver 返回 `None` 时 fallback 到 `context_before` 或 `infer_caption_from_context`"，与现有 `AGENTS.md` 语义所有权约束一致。

- **建议改法和验证点**: 在 plan §4.3 增加一句："caption=`None` 时不得 fallback 到 context_before、infer_caption_from_context、table headers 或任何其它字段。"

- **修复风险**: 极低——文字补充。

- **严重程度**: **低** — 无现有缺陷，纯预防性。

---

### S3-PR-DS-F06 — 低 — `_normalize_whitespace` 接受 `Any` 类型参数，但 plan 的 `isinstance(TextItem)` gate 已防止类型错误传播

- **位置**: Corrected plan §4.3 item 3（"resolved item 只有 isinstance(item, TextItem) 时才读取其 typed text"）结合 `_normalize_whitespace` 实现。

- **问题类型**: 契约确认（非新 defect）。

- **当前写法**: Plan 规定只对 `TextItem` 实例调用 `_normalize_whitespace(text_item.text)`。

- **反例 / 失败场景**: `_normalize_whitespace` 签名是 `(text: str) -> str`，但实现是 `" ".join(str(text or "").split())`，会静默将任何非 str 值转成字符串。如果 implementation agent 错误地将非 TextItem 的 `text` 属性传给 normalizer，可能得到意外的字符串结果。但 plan 的 `isinstance(TextItem)` gate 已经防止这种情况。

- **为什么有问题**: 这不是 plan 的缺陷。记录为"已验证安全"以防止 reviewer 将其标记为风险。

- **直接证据**: `text_utils.py:28` `normalize_whitespace(text: str)` 签名正确；plan §4.3 item 3 明确 gating。

- **影响**: 无。

- **建议改法和验证点**: 无需修改。

- **修复风险**: N/A。

- **严重程度**: **低** — 确认性 finding，不影响 plan 正确性。

---

### S3-PR-DS-F07 — 中 — canonical suite coverage exclusion 依赖 `--deselect` 的精确 node path，但 plan 未校验该 node path 在当前 HEAD 下是否稳定

- **位置**: Corrected plan §6.2（coverage exclusion node）。

- **问题类型**: 测试不可达 / 假设漂移。

- **当前写法**: Plan 硬编码 deselect node path 为 `tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task`。

- **反例 / 失败场景**: 如果从 aggregate parent `3410d742` 到当前 immutable slice base `9e7a4e9d` 期间，该 test node 被 rename、move 或 delete，则 `--deselect` 会静默失效（pytest 对不存在的 deselect 只 warning 不 error）。此外，如果 AR-F06 的根因在后续 commit 中被意外修复，desired behavior 是重新启用（取消 deselect），而非继续 deselect。

- **为什么有问题**: Plan 假设这个精确 node path 始终存在且始终是需要排除的同一 node。当前 code evidence（plan 记录 AR-F06 的 protected zero-diff paths 包括 `tests/host/test_dispatch_scheduler.py`）确认该文件是 protected——所以内容不会变。但 plan 应显式验证该 node 在 `SLICE_BASE` 中存在且名称为该精确值。

- **直接证据**: Plan §3.5 item 1 将 `tests/host/test_dispatch_scheduler.py` 列入 protected zero-diff paths。

- **影响**: 低概率——仅当 base commit 中该 node 名称与 plan 记录的不同时才会失效。

- **建议改法和验证点**: 在 plan §6.2 增加验证步骤："在运行 aggregate coverage 前先 `pytest --collect-only` 确认 target node 存在且 full nodeid 与 deselect 精确匹配；若不存在则 STOP。"

- **修复风险**: 极低——增加一行验证命令。

- **严重程度**: **中** — AR-F06 是 release blocker（`UNFIXED / UNWAIVED`），coverage exclusion 的静默失效会掩盖 scheduler bug 获得虚假的 coverage PASS。

- **Owner**: Corrected plan §6.2。

---

### S3-PR-DS-F08 — 低 — plan 未明确 `_build_tables()` 的 `document` 参数是否已通过 `_iter_document_tables()` 消费的同一实例

- **位置**: Corrected plan §4.3 item 1（"同一 DoclingDocument"）。

- **问题类型**: 契约确认。

- **当前写法**: Plan 要求 `_build_tables()` 传递其已持有的同一 `DoclingDocument` 实例给 caption resolver。

- **反例 / 失败场景**: 当前 `_build_tables(document, linear_items)` 在第 617 行调用 `_iter_document_tables(document)` 获取 `table_items`，然后用这些 table_item 调 `_extract_table_caption(table_item)`（line 628）。`document` 确实是同一实例，`table_item` 也是从该 document 中迭代出的。实施 agent 只需将 `document` 参数加到 `_extract_table_caption` 签名并传递给 `RefItem.resolve(document)`。这是直接的。

- **为什么有问题**: 确认性——验证 plan 的 claim 准确。

- **直接证据**: `docling_processor.py:598-651`——`document` 是函数参数，`_iter_document_tables(document)` 消费同一实例，`_extract_table_caption(table_item)` 当前丢失了 document 引用。

- **影响**: 无。

- **建议改法和验证点**: 无需修改。

- **修复风险**: N/A。

- **严重程度**: **低** — 确认性。

---

## 3. Architecture Boundary Review

### 3.1 分层边界

- ✅ `dayu/documents/processors/docling_processor.py` 是 Docling JSON 处理器，属于 documents 处理层。Caption 解析是表格投影的自然职责，ownership 正确。
- ✅ `TextItem` 从 `docling_core.types.doc.document` 导入，该包已通过 `TYPE_CHECKING` 块在模块中导入（line 19）。作为项目必需依赖（`docling-core>=2.74.0,<3.0.0`），不引入新的架构耦合。
- ✅ 三 public consumers（`list_tables` / `read_table` / `get_page_content`）通过 `_TableBlock.caption` 统一消费，符合"同一真源"原则。
- ✅ Plan 不引入新模块、新 schema、新类型、新 resolver service 或新状态机。变化仅限于一个 private helper 的签名和实现。

### 3.2 依赖方向

- ✅ `RefItem.resolve(DoclingDocument)` → 标准 Docling public API。
- ✅ `_build_tables` → `_extract_table_caption` → `_TableBlock.caption` → public views。单向数据流，无反向依赖。

### 3.3 Public contract

- ✅ `TableSummary.caption` 和 `TableContent.caption` 的 `str | None` 类型不变。无 schema migration。
- ✅ `_TableBlock.caption` 仍是唯一缓存投影。

## 4. Overengineering Review

- ✅ Plan 明确拒绝新 schema、新类型、新 resolver service、新状态机、兼容层。
- ✅ 修复范围精确到一个 private helper 的签名变化和实现替换。
- ✅ 多 caption 语义（顺序、规范化、去重、连接）用现有工具（`_normalize_whitespace`）实现，不引入新的规范化框架。

## 5. Overcoupling Review

- ✅ Caption resolver 不依赖任何下游 consumer。consumer 只读 `_TableBlock.caption`。
- ✅ `_extract_table_caption` 不引入对 `list_tables` / `read_table` / `get_page_content` 的反向依赖。
- ✅ 无跨层穿透。

## 6. Best Practice Review

- ✅ Root cause 由直接类型/代码/实验证据锁定（`docling-core==2.74.0` `TableItem.captions`）。
- ✅ 修复在语义 owner boundary 进行。
- ✅ 测试通过 public processor API 断言，不直接调用 private helper。
- ✅ 异常边界按类型精确分类（尽管 Finding 1/2 指出分类覆盖不完整）。
- ✅ 禁止 `except Exception`、兼容 fallback、下游补偿。

## 7. Protected State Audit

| Protected item | Plan claim | Verified |
|---|---|---|
| Six Slice 3 test path entry hashes | §0 逐项列出 | ⚠️ 未逐项验证（需 runtime hash），但 plan correction artifact §3.1 列出且 plan 声称保护 |
| Controller-owned dirty artifact hashes | §0 逐项列出 | ⚠️ 同上 |
| Production allowlist non-Docling owners zero diff | §3.1 / §4.3 | ✅ plan 明确规定 |
| `test_argparse_exit.py` untracked | §3.2 | ✅ plan 保留在 allowlist |
| Two zero-diff authorized test paths | §4.3 | ✅ plan 明确 |
| README NO_UPDATE | §3.4 | ✅ plan 裁定根/`dayu`/`tests` 三 README `NO_UPDATE` |
| AR-F06/AR-F07/AR-F05 状态 | §1 endorsement | ✅ AR-F06=`RETAINED/UNFIXED`，AR-F07=`PENDING_RELEASE_BLOCKER`，AR-F05=`BLOCKED_BY_S3-STOP-F01` |
| Gemini / secret / deferred | §4.3 | ✅ 维持 |
| Issues 142/151/175/177/178 | §4.3 | ✅ 不扩域 |

## 8. Controller Observation Response

Controller validation 提出六项 adversarial review focus areas：

| # | Controller observation | DS 判定 |
|---|----------------------|---------|
| 1 | `TextItem` 模块级依赖是否与项目一致 | ✅ 一致——`docling_core.types.doc.document` 已在 module TYPE_CHECKING 块导入，`docling-core>=2.74.0` 是必需依赖 |
| 2 | 多 caption 连接规则是否丢失业务分隔 | ✅ 单空格连接是合理默认；多行 caption 的 `\n` 被 `_normalize_whitespace` 转为单空格是预期行为 |
| 3 | dangling ref 只捕获 AttributeError/IndexError 是否精确 | ❌ 不精确——见 S3-PR-DS-F01/F02 |
| 4 | model-invalid serialized payload test 是否经 public loader | ⚠️ plan 声称 `load_from_json()` 失败但实验证据显示不失败——见 S3-PR-DS-F01 |
| 5 | page view fixture 是否具备真实 provenance | ✅ plan §4.3 test oracle item 1 要求"fixture 带真实 page provenance" |
| 6 | 109/22 行 correction 是否无历史误改 | ✅ plan correction artifact §11 报告 `109 insertions / 22 deletions`，`git diff --check` 通过，仅修改 plan 文件 |

## 9. Open Questions

1. **Q1 (from S3-PR-DS-F01)**: 修正后的 exception boundary 应该是什么？方案 A（窄化捕获 RuntimeError + ValueError）还是方案 B（接受崩溃作为 known limitation）？当前 plan 的划分被实验证据推翻，需要 Controller 裁决。

2. **Q2 (from S3-PR-DS-F04)**: NBSP 和其他 Unicode 空白字符的去重 gap 是接受为 known limitation 还是在本 slice 修复？

3. **Q3 (from S3-PR-DS-F07)**: AR-F06 scheduler deselect node path 是否需要在 plan 中增加显式存在性验证步骤？

## 10. Residual Risks

| Risk | Severity | Suggested tracking |
|------|----------|-------------------|
| `RuntimeError` / `ValueError` 从 Docling ref resolution 抛出导致 processor 崩溃 | 严重 | S3-PR-DS-F01/F02 必须在 plan fix gate 解决 |
| NBSP 导致 multi-caption 去重不完整 | 中 | 记录为 S3 known limitation 或 plan fix |
| Scheduler deselect 静默失效 | 中 | S3-PR-DS-F07——增加验证命令 |
| `$ref`/`cref` 术语混淆 | 中 | S3-PR-DS-F03——plan 文本补充 |
| Caption fallback to context_before 缺乏明确禁止声明 | 低 | S3-PR-DS-F05——plan 文本补充 |

## 11. Final Plan Review Conclusion

**Verdict: `PASS-WITH-RISKS`**

### 通过项
- Root cause 锁定正确且基于直接代码/类型/实验证据。
- 语义 owner（Docling table projection boundary）判定正确。
- 同 document 真源传递路径明确且可验证。
- Multi-caption 业务规则（顺序、规范化、去重、连接）定义完整。
- 三 public view 一致性已确认。
- Scope / protected locks / README / deferred/no-code 边界无漂移。
- 无 overdesign/undercoupling 问题。
- 109/22 行 plan correction 精确且无历史误改。

### 必须修复项
- **S3-PR-DS-F01（严重）**: Model-invalid ref 不在 `load_from_json()` 边界失败；`RuntimeError` 从 `resolve()` 抛出的分类需要修正。Plan 的错误分类声称必须纠正，否则 implementation agent 无法在"跟随 plan"和"写出健壮代码"之间做出正确选择。

### 建议修复项
- **S3-PR-DS-F02（中）**: `ValueError`（`int(index_str)` 对非数字 index）也应纳入 caption fail-safe。
- **S3-PR-DS-F03（中）**: `$ref` / `cref` 术语应补充说明。
- **S3-PR-DS-F04（中）**: NBSP 去重 gap 应至少记录为 known limitation。
- **S3-PR-DS-F07（中）**: Scheduler deselect node path 应增加存在性验证。

### Blocking 判定
- S3-PR-DS-F01 是 **blocker**。在修正前，plan 不是 code-generation-ready：implementation agent 必须重新设计异常捕获语义（违反 plan "不得重新设计" 约束），或写出对真实畸变数据脆弱的代码（违反 fail-safe 设计意图）。

---

## 12. Controller Adjudication Entry

**Artifact SHA-256**: 本文件写入后由 Controller 从文件系统读取新鲜 hash。

**Controller Adjudication Entry Point**:
- 逐条裁决 §2 的 8 个 findings（尤其 S3-PR-DS-F01/F02/F03/F04/F05/F07）。
- 决定修正方案（方案 A/B）并授权 AgentCodex plan-only fix。
- 接受修正后进入双路完整 re-review。

**下一 Gate**: `PLAN_FIX_REQUIRED` → AgentCodex 在 plan 和 plan correction artifact 内修复 accepted findings → AgentMiMo/AgentDS 双路完整 re-review → Controller 接受 → 新的 S3 implementation authorization。
