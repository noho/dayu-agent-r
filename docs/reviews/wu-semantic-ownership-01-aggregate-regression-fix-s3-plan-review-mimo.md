# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Corrected Plan — Adversarial Plan Review（AgentMiMo）

## 1. Review identity

- 日期：`2026-07-19`。
- Review target：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，SHA-256 `ef4a0832f1885e4013d673294b944a56280619baab1f97d438896af5c8cbedcf`。
- Review scope：完整 corrected plan，不只新增 hunks；包括 S3 correction authority、S3 plan-correction codex artifact、S3 production-defect adjudication、S3 implementation codex artifact、S3 implementation controller authorization、S2 accepted-commit validation。
- 独立 review：不复用前一路结论，不启动 subagent，不假设 Controller 预先裁决。
- Review posture：constructively adversarial，默认假设 plan 至少有一个重要问题直到证据证明其可靠。

## 2. Assumptions tested

1. S3-STOP-F01 root cause 唯一且 owner 边界正确。
2. `TextItem` 模块级 import 与项目 required dependency / import boundary 一致。
3. `_build_tables()` 已持有的 `DoclingDocument` 可以直接传给 caption resolver。
4. 多 caption 连接规则（ref 顺序、whitespace 规范化、大小写敏感精确去重、单空格连接）是业务正确的。
5. dangling ref 精确捕获 `AttributeError` / `IndexError` 不会吞编程错误。
6. model-invalid public loader test 不引入 production raw JSON 解析。
7. non-text boundary 用 `isinstance(item, TextItem)` 判定完整。
8. 三个 public views / provenance fixture 可以构造真实 Docling provenance。
9. allowlist / protected hashes 精确且不漂移。
10. README `NO_UPDATE` 裁决正确。
11. 最终 canonical/219/219/pyright/Ruff/build/scans/smokes/security 门禁完整。
12. trusted internal secret 裁决一致。
13. Gemini quota 分类不变。
14. AR-F06/07 与 deferred/no-code 边界不漂移。

## 3. Findings

### 001-未修复-中-TextItem 模块级 import 缺少显式 TYPE_CHECKING 保护

- **位置**: §4.3 correction implementation order / exact owner change, item 3
- **问题类型**: 架构边界 / 最佳实践偏离
- **当前写法**: "为 runtime type narrowing 在模块级从 Docling public types 导入 `TextItem`；`docling-core>=2.74.0,<3.0.0` 是项目必需依赖，因此不增加 lazy import"
- **反例/失败场景**: 当前 `docling_processor.py` 已有 `if TYPE_CHECKING: from docling_core.types.doc.document import DoclingDocument, NodeItem, TableItem`。`TextItem` 当前仅在 TYPE_CHECKING 分支中可用。若在模块级无条件导入 `TextItem`，而 `DoclingDocument`、`NodeItem`、`TableItem` 仍保留在 TYPE_CHECKING 分支，会产生不一致的 import 策略：同一包的四个类型有两种不同的 import 机制。这不是功能错误，但违反了代码内聚性原则。
- **为什么有问题**: `docling-core` 确实是 required dependency，但当前模块已选择 TYPE_CHECKING 模式处理 Docling 类型。在模块级无条件导入 `TextItem` 而保留其他三个类型在 TYPE_CHECKING 中，会导致 import 策略不一致。更重要的是，当前 `_extract_table_caption` 的签名使用 `TableItem` 作为 TYPE_CHECKING-only 类型注解；如果 caption resolver 需要模块级 `TextItem`，则说明该函数的 import 需求与同模块其他函数不同，这是设计信号。
- **直接证据**: `docling_processor.py:18-19` 使用 `if TYPE_CHECKING` 保护 `DoclingDocument, NodeItem, TableItem`；plan §4.3 item 3 要求模块级导入 `TextItem`。
- **影响**: 代码风格不一致；若未来 `docling-core` 改变 import 成本或引入可选依赖模式，不一致的 import 策略可能导致问题。
- **建议改法和验证点**: 两种方案均可接受，但必须一致：(a) 把 `TextItem` 也放入 TYPE_CHECKING 分支，在 `_extract_table_caption` 内部用 `TYPE_CHECKING` 块内的类型做 isinstance 检查（需要运行时 import），或 (b) 把所有四个 Docling 类型都从 TYPE_CHECKING 移到模块级无条件导入。方案 (b) 更简单，因为 `docling-core` 是 required dependency。验证点：import 策略在模块内一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-中-多 caption 单空格连接可能丢失业务分隔语义

- **位置**: §4.3 item 4; §6 plan-correction-codex item 6
- **问题类型**: 契约缺失 / 最佳实践偏离
- **当前写法**: "最后用单个 ASCII 空格连接所有剩余文本，形成唯一 `str` caption"
- **反例/失败场景**: 假设一个 Docling 文档有两个 caption refs：第一个解析为 `"Table 1"`，第二个解析为 `"Revenue by Segment"`。当前规则产生 `"Table 1 Revenue by Segment"`。如果原始文档意图是 `"Table 1: Revenue by Segment"` 或 `"Table 1 — Revenue by Segment"`，单空格连接丢失了原始分隔符。更极端的情况：第一个 caption 以句号结尾 `"Summary."`，第二个以大写字母开头 `"Revenue"`，连接后为 `"Summary. Revenue"`——这恰好正确，但如果第一个 caption 以冒号或分号结尾，连接后的标点语义可能改变。
- **为什么有问题**: Docling 的 `TableItem.captions` 是一个 `list[RefItem]`，每个 ref 指向一个独立的 `TextItem`。这些 TextItem 的 `text` 是文档作者编写的原始文本。当多个 caption 被合并时，原始文本之间的分隔符信息（可能是冒号、破折号、换行或其它标点）在 Docling 数据模型中不存在——它只存储 refs 列表，不存储 ref 之间的分隔符。因此，plan 选择单空格连接是合理的默认行为，但缺少一个关键文档：**这个连接规则是 Docling 数据模型的限制，不是业务选择**。如果未来 Docling 版本在 refs 之间添加分隔符信息，当前实现需要更新。
- **直接证据**: `docling-core==2.74.0` 的 `TableItem.captions: list[RefItem]` 不包含 ref 间分隔符字段。Plan §4.3 item 4 固定了单空格连接但未说明这是数据模型限制。
- **影响**: 低。当前 Docling 版本不提供分隔符信息，单空格是唯一合理默认。但 plan 应明确记录这一限制，避免 implementation agent 误以为这是业务偏好而尝试更复杂的连接策略。
- **建议改法和验证点**: 在 plan 中补充一句："单空格连接是因为 `TableItem.captions` 的 `list[RefItem]` 不包含 ref 间分隔符元数据；若未来 Docling 版本提供分隔符，resolver 应优先使用。" 验证点：plan 文档完整性。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-高-dangling ref 捕获 `AttributeError` / `IndexError` 可能掩盖 Docling 内部 bug

- **位置**: §4.3 item 5; §6 plan-correction-codex item 6 fail-safe 边界
- **问题类型**: 状态机漏洞 / 最佳实践偏离
- **当前写法**: "符合 Docling JSON-pointer shape 但指向未知 document collection 时由 public `resolve()` 产生的 `AttributeError`，以及指向已知 collection 越界 index 时产生的 `IndexError`，只在单次 `caption_ref.resolve(document)` 调用周围精确捕获并跳过该 ref"
- **反例/失败场景**: `RefItem.resolve(document)` 的内部实现可能在某些边界条件下抛出 `AttributeError` 或 `IndexError`，但原因不是 dangling ref，而是 Docling 内部 bug、document 结构异常或版本不兼容。例如：
  - Docling 升级后 `resolve()` 的实现改变，`AttributeError` 来源从"未知 collection"变为"内部属性名变更"。
  - `IndexError` 可能来自 `resolve()` 内部的列表操作 bug，而非真正的越界 ref。
  - 当前 plan 假设 `AttributeError` = unknown collection, `IndexError` = out-of-range，但这两个异常类型在 Python 中非常通用，`resolve()` 内部的任何属性访问或索引操作失败都会产生相同异常。
- **为什么有问题**: Plan 的 fail-safe 设计意图正确——dangling ref 是可选 caption metadata 的已知数据完整性问题，应该优雅降级。但精确区分"dangling ref 导致的异常"和"Docling 内部 bug 导致的异常"在 `except` 层面不可能。`except (AttributeError, IndexError)` 会捕获 `resolve()` 内部任意位置的同类型异常，不仅是 JSON-pointer 解析失败。
- **直接证据**: `RefItem.resolve(document)` 是第三方公共方法，其实现细节不在本项目控制范围内。`except (AttributeError, IndexError)` 是宽泛的异常类型，无法区分异常来源。
- **影响**: 中。如果 Docling 升级引入 `resolve()` 内部 bug，该 bug 会被 caption resolver 静默吞掉，表现为 caption=None，而实际应该暴露错误。这会导致难以调试的"caption 消失"问题。
- **建议改法和验证点**: 两种改进方向：
  1. **保守方案**：只捕获 `IndexError`（越界是 dangling ref 的明确信号），对 `AttributeError` 不捕获（unknown collection 会表现为 AttributeError，但与 Docling 内部 bug 无法区分）。如果 `AttributeError` 确实来自 unknown collection，它会在 `resolve()` 的第一行失败，可以通过检查异常 traceback 的 depth 来区分——但这过于复杂。
  2. **推荐方案**：保持当前 `except (AttributeError, IndexError)`，但添加一个 **warning log**（不是 debug/ignore），记录被跳过的 ref 和异常详情，便于 operator 发现 Docling 升级引入的 regression。同时在 plan 中明确：这个 catch 是 **数据完整性降级**，不是错误处理；如果 caption 在已知有效文档中全部消失（所有 ref 都被跳过），应视为异常信号而非正常 None。
  验证点：测试中验证"全部 ref 都是 dangling"时返回 None，但同时验证"一个有效 ref + 一个 dangling ref"时保留有效 caption。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 004-未修复-低-model-invalid ref test 的 Docling load 边界不够明确

- **位置**: §4.3 item 6; §7 test oracle item 4
- **问题类型**: 测试缺口
- **当前写法**: "语法非法、不能被 Docling `RefItem` 模型接受的 ref 不是 caption resolver 的 fail-safe 输入：它必须在真实 `DoclingDocument.load_from_json()` 边界失败，并按现有 Docling JSON parsing error 对外暴露"
- **反例/失败场景**: Plan 要求测试"先由真实 `DoclingDocument.save_as_json()` 生成其余完整 payload，只把 serialized `captions[*].$ref` 替换为 model-invalid 值，再从 public processor 构造入口断言现有 Docling JSON parsing error"。这里有一个微妙问题：替换 `$ref` 字段后，JSON 是否仍然能被 `DoclingDocument.load_from_json()` 成功解析取决于 `RefItem` 的 Pydantic validator 行为。如果 `RefItem` 对非法 `$ref` 做宽松解析（例如接受任意字符串但 resolve 时失败），则 load 不会抛出 parsing error，而是 resolve 时失败——这会落入 caption resolver 的 `except` 分支，而不是 plan 期望的 load-time error。
- **为什么有问题**: Plan 假设 model-invalid ref 在 load 时失败，但 Docling 的 `RefItem` 可能采用"宽松解析 + resolve 时验证"模式。如果实际行为是 resolve-time failure 而非 load-time failure，测试断言会错误。
- **直接证据**: 需要验证 `RefItem` 的 Pydantic validator 是否在 load 时拒绝非法 `$ref`，还是只在 `resolve()` 时失败。当前未做此验证。
- **影响**: 低。测试设计意图正确，但断言可能需要调整为"load 失败或 resolve 时失败"。
- **建议改法和验证点**: Implementation agent 应先验证 `RefItem` 对非法 `$ref` 的实际行为（load-time vs resolve-time），然后调整测试断言。Plan 应补充这个验证步骤。验证点：测试在当前 `docling-core==2.74.0` 下通过。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 005-已接受候选-中-caption ref 解析到非 TextItem 子类时的类型判定完整性

- **位置**: §4.3 item 3; §7 test oracle item 5
- **问题类型**: 契约缺失
- **当前写法**: "resolved item 只有 `isinstance(item, TextItem)` 时才读取其 typed `text`；`SectionHeaderItem`、`TitleItem` 等 TextItem 子类自然符合，TableItem/PictureItem 等非文本 item 不符合"
- **反例/失败场景**: 当前 `docling-core==2.74.0` 中 `TextItem` 的子类包括 `SectionHeaderItem`、`TitleItem`、`ListItem`、`CodeItem`、`FormulaItem`。Plan 只明确提到 `SectionHeaderItem` 和 `TitleItem`。如果 caption ref 解析到 `ListItem` 或 `CodeItem`，它们也是 `TextItem` 子类，会被接受并读取其 `text`。这是正确行为（它们确实有文本内容），但 plan 没有明确列出这些子类。
- **为什么有问题**: 不是功能错误，但 plan 的类型判定说明不够完整。如果 implementation agent 只看 plan 文本，可能误以为只有 `SectionHeaderItem` 和 `TitleItem` 是合法的。
- **直接证据**: `docling-core==2.74.0` 中 `TextItem.__subclasses__()` 包含 `ListItem`、`CodeItem`、`FormulaItem`。
- **影响**: 低。`isinstance(item, TextItem)` 正确覆盖所有文本子类，plan 只是文档不完整。
- **建议改法和验证点**: Plan 应补充："`TextItem` 的所有子类（包括 `ListItem`、`CodeItem`、`FormulaItem`）自然符合 isinstance 检查。" 验证点：测试覆盖至少一个非 `SectionHeaderItem`/`TitleItem` 的 `TextItem` 子类作为 caption ref 目标。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 006-未修复-高-三个 public views 的 provenance fixture 依赖 Docling 内部结构

- **位置**: §7 test oracle item 1, item 6
- **问题类型**: 测试缺口 / 过度耦合
- **当前写法**: "fixture 带真实 page provenance 时同时断言 `get_page_content(page_no)["tables"][0]["caption"]` 相同"
- **反例/失败场景**: `get_page_content()` 需要 `page_no` 来定位表格。在 Docling 文档中，page provenance 来自 `TableItem.prov` 字段（`list[ItemProv]`，每个有 `page_no`）。构造一个带真实 page provenance 的 `DoclingDocument` 需要设置 `TableItem.prov = [ItemProv(page_no=1, ...)]`。但 `ItemProv` 的完整构造可能需要 `bbox` 等字段，而 plan 没有说明如何构造这些字段。
- **为什么有问题**: 如果 `ItemProv` 构造不完整（例如缺少 `bbox`），`get_page_content()` 的 page 查找逻辑可能无法匹配表格，导致 page view 测试失败——不是因为 caption 修复有问题，而是因为 provenance fixture 不完整。
- **直接证据**: `get_page_content()` 的 page 查找逻辑依赖 `table.page_no`，该值来自 `_extract_page_no(table_item)`，后者从 `table_item.prov` 提取。Plan 没有说明 `ItemProv` 的构造要求。
- **影响**: 中。测试可能因 fixture 构造不当而失败，implementation agent 需要自行研究 `ItemProv` 的完整构造。
- **建议改法和验证点**: Plan 应明确："page provenance fixture 必须构造完整的 `ItemProv(page_no=N, bbox=...)` 对象，其中 `bbox` 可以是零值但必须存在。" 或者："如果 `get_page_content()` 对缺少 `prov` 的表格已有 graceful fallback，page view 测试可以使用该 fallback 路径。" 验证点：测试在当前代码下通过。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 007-无操作-低-219 changed production 集合不变性假设

- **位置**: §4.3; §3.1; §6.2
- **问题类型**: 无操作
- **当前写法**: "该 path 已经属于 aggregate parent 到当前树的 219 changed-production 集合，因此修改内容不改变集合成员，final 仍必须精确 219"
- **分析**: Plan 正确识别了 `dayu/documents/processors/docling_processor.py` 已经在 219 集合中。Slice 3 只修改该文件内容，不增加或删除集合成员。这是正确的。
- **结论**: 无需修改。

### 008-无操作-低-allowlist 精确性

- **位置**: §3.1, §3.2
- **问题类型**: 无操作
- **分析**: Production allowlist 只有 `M dayu/documents/processors/docling_processor.py`。Test allowlist 有六个路径。Protected zero-diff paths 完整列出。与 §0 的 entry hash 保护一致。
- **结论**: 无需修改。

### 009-未修复-中-caption 规范化使用 `_normalize_whitespace()` 的行为边界未明确

- **位置**: §4.3 item 4
- **问题类型**: 契约缺失
- **当前写法**: "每个 resolved text 用现有 `_normalize_whitespace()` 做 strip 并把连续空白规范为单空格"
- **反例/失败场景**: `_normalize_whitespace()` 的具体行为未在 plan 中定义。如果它把 `\n`、`\t`、`\r` 都规范为单空格，则 `"Revenue\nby\nSegment"` 变成 `"Revenue by Segment"`。这通常是正确的。但如果 caption 包含有意的换行格式（例如多行标题），规范化后会丢失格式。此外，如果 `_normalize_whitespace()` 还做了 Unicode 规范化（例如全角空格→半角空格），这可能影响大小写敏感去重的比较结果。
- **为什么有问题**: Plan 引用了现有 helper 但没有说明其完整行为。Implementation agent 需要知道 `_normalize_whitespace()` 是否只处理 ASCII 空白还是也处理 Unicode 空白，是否做 strip，是否保留原始字符。
- **直接证据**: `_normalize_whitespace` 在 `text_utils.py` 中定义，plan 没有引用其具体实现。
- **影响**: 低。大多数情况下行为正确，但 edge case 可能导致意外。
- **建议改法和验证点**: Plan 应补充 `_normalize_whitespace()` 的行为摘要："strip 首尾空白，连续 ASCII 空白规范为单空格，不做 Unicode 规范化。" 或者 implementation agent 应先读取该 helper 的 docstring。验证点：测试覆盖含 `\n`、`\t` 的 caption 文本。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 010-无操作-低-README NO_UPDATE 裁决

- **位置**: §3.4; §6 plan-correction-codex §8
- **问题类型**: 无操作
- **分析**: Caption 修复不改变最终用户安装/CLI/Web/WeChat 工作区/排障流程，不改变跨包分层或 `dayu.documents` 层中立职责，也不新增测试层级、运行方式或维护规则。`tests/README.md` 的现有 documents processor 说明已覆盖 Docling 表格输出。裁决正确。
- **结论**: 无需修改。

### 011-无操作-低-trusted internal secret 裁决一致性

- **位置**: §2.2.1; §4.3 "Unchanged trust / quota / deferred boundaries"
- **问题类型**: 无操作
- **分析**: Config 与 Host internal SQLite/EventLog 仍是 `ACCEPTED_TRUSTED_INTERNAL`。Docling caption 修复不涉及 secret/credential/token。Tool Trace、audit、public、LLM-facing、logs、outputs、diff/reviews 继续 `ZERO_REQUIRED`。裁决一致。
- **结论**: 无需修改。

### 012-无操作-低-Gemini quota 分类

- **位置**: §4.3 "Unchanged trust / quota / deferred boundaries"
- **问题类型**: 无操作
- **分析**: Gemini 仍为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。Slice 3 不追加真实 provider 调用。正确。
- **结论**: 无需修改。

### 013-无操作-低-AR-F06/07 与 deferred/no-code 边界

- **位置**: §4.3; §9
- **问题类型**: 无操作
- **分析**: AR-F06 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。AR-F07 保持 `PENDING_RELEASE_BLOCKER`。Issues 142/151/175/177/178、Topic 8/9 不变。正确。
- **结论**: 无需修改。

### 014-未修复-中-caption 去重规则的业务正确性未被挑战

- **位置**: §4.3 item 4
- **问题类型**: 最佳实践偏离
- **当前写法**: "按规范化后的完整字符串精确相等、大小写敏感去重，保留第一次出现；不同大小写或不同正文不擅自合并"
- **反例/失败场景**: 假设两个 caption refs 指向不同的 TextItem，但文本分别为 `"Revenue"` 和 `"revenue"`（大小写不同）。当前规则保留两者，产生 `"Revenue revenue"`。从业务角度看，这可能是同一概念的重复引用（例如文档编辑时的格式不一致），合并为 `"Revenue"` 可能更合理。但 plan 选择保留两者，理由是"不擅自合并"。
- **为什么有问题**: 这是一个设计选择，不是 bug。但 plan 没有解释为什么大小写敏感去重比大小写不敏感去重更正确。在财报文档中，表格标题的大小写通常是一致的（由文档作者控制），大小写不同更可能是不同语义（例如 "Revenue" vs "revenue" 可能分别指收入行和收入表）。Plan 应明确记录这个选择的理由。
- **直接证据**: 无直接证据表明哪种去重策略更正确，因为这是业务语义选择。
- **影响**: 低。当前选择是保守的（保留更多信息），不会导致数据丢失。
- **建议改法和验证点**: Plan 应补充："大小写敏感去重的理由是：财报表格标题的大小写差异通常表示不同语义，不应合并。" 验证点：测试覆盖大小写不同的 caption case。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 015-无操作-低-final canonical/219/219/pyright/Ruff/build/scans/smokes/security 门禁完整性

- **位置**: §6
- **问题类型**: 无操作
- **分析**: Plan §6 完整列出了所有门禁：canonical non-coverage full suite、exact single-node exclusion coverage、full pyright、full Ruff、diff/allowlist/staged、build、six canonical scans、README/security/deferred/no-code ledger、per-slice real-smoke completeness。与原 accepted plan 一致，没有弱化。
- **结论**: 无需修改。

## 4. Open questions

1. **`RefItem` 对非法 `$ref` 的行为**：需要验证 `docling-core==2.74.0` 的 `RefItem` 是在 Pydantic validation 阶段拒绝非法 `$ref`，还是在 `resolve()` 时才失败。这影响 model-invalid test 的断言设计。（关联 finding 004）

2. **`ItemProv` 构造复杂度**：需要验证构造带 page provenance 的 `DoclingDocument` 是否需要完整的 `ItemProv(bbox=...)` 对象，还是 `page_no` 就足够。（关联 finding 006）

3. **`_normalize_whitespace()` 完整行为**：需要确认该 helper 是否只处理 ASCII 空白，是否做 Unicode 规范化。（关联 finding 009）

## 5. Residual risks

1. **Docling 版本升级风险**：`docling-core>=2.74.0,<3.0.0` 的范围上限是 `<3.0.0`。如果 2.x 版本改变 `RefItem.resolve()` 的行为或 `TextItem` 的子类层次，caption resolver 可能需要调整。当前 plan 的 fail-safe 设计（精确捕获 `AttributeError`/`IndexError`）提供了一定保护，但如 finding 003 所述，可能掩盖内部 bug。
   - **跟踪目的地**: 本 WU 的 aggregate regression gate，以及未来 `docling-core` 版本升级时的 CI。

2. **多 caption 连接的 LLM 可读性**：单空格连接的 caption 对 LLM 来说是否足够可读，取决于实际 Docling 文档中多 caption 的频率和内容。当前没有证据表明这是一个问题，但值得关注。
   - **跟踪目的地**: 本 WU 的 aggregate deepreview。

3. **S3-STOP-F01 修复后 coverage 路径**：Docling owner 的 line coverage 从 63.46% 提升到 80%+ 需要大量 test cases。Plan 的 caption matrix（7 个 test nodes）加上其余 payload sniff/section/table/page/search cases 是否足够达到 80%，需要 implementation 时验证。如果不够，可能需要更多 cases，但不能为了 coverage 而降低测试质量。
   - **跟踪目的地**: Slice 3 implementation gate。

## 6. Final plan review conclusion

**pass-with-risks**

Corrected plan 在 S3-STOP-F01 的 root cause 判定、owner 边界、caption public contract、fail-safe 设计和 test oracle 方面总体正确且足够 code-generation-ready。没有发现 true blocker。

主要 findings：
- **003（中）**：`except (AttributeError, IndexError)` 可能掩盖 Docling 内部 bug，建议添加 warning log 并在 plan 中明确这是数据完整性降级。
- **006（中）**：page provenance fixture 的 `ItemProv` 构造要求未明确，可能导致 implementation agent 阻塞。
- **001（低）**：TextItem import 策略与模块内其他 Docling 类型不一致。
- **002/004/005/009/014（低）**：plan 文档完整性可以改进，但不影响功能正确性。

建议 Controller 在裁决时：
1. 接受 003 为 accepted-candidate，要求 implementation 添加 warning log。
2. 接受 006 为 accepted-candidate，要求 plan 补充 `ItemProv` 构造说明或 implementation agent 先验证。
3. 其余 findings 可作为 no-action 或 deferred。

Controller adjudication 入口：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-mimo.md`。

Artifact SHA-256：`485946385306e080804804031c347063057b7db0538a1f6ac12d39cff78519df`。
