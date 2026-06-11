# WU-TOOLS-01-F08 Plan Review — AgentMiMo

## 元信息

- Review target：`docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`
- Gate：plan review
- 日期：2026-06-11
- Reviewer：AgentMiMo
- 控制 / 设计来源：`docs/host/issues-implementation-control.md`、`docs/host/design.md`、`docs/engine/design.md`、`docs/reviews/wu-tools-01-f08-goal-confirmation-controller.md`

## Review Scope

只 review F08 plan，不实现代码、不修改文件。

## 假设检验

Plan 声称的关键假设与直接证据核对：

1. **旧名只有四个生产文件引用** — `rg` 确认：`registry.py`、`__init__.py`、`_doc_processor_factory.py`、`fins/processors/registry.py`。与 plan 一致。
2. **Fins README 存在旧 ownership 表述** — 代码确认 `fins/processors/registry.py` line 2 docstring 含 "engine 核心处理器注册表"；`dayu/fins/README.md` line 382 含 "engine 文档处理器注册表"。与 plan 一致。
3. **`list_processors()` 方法存在** — `processor_registry.py:100` 确认存在，返回 `list[dict[str, object]]`。与 plan 测试方案一致。
4. **Documents 默认 registry priority 为 10** — `registry.py:14` 确认 `_GENERIC_PROCESSOR_PRIORITY = 10`。与 plan 一致。
5. **Fins priority 层级 200/190/120/100/80** — `fins/processors/registry.py:31-35` 确认。与 plan 一致。
6. **Fins registry 先调用旧 builder 再覆盖** — `fins/processors/registry.py:60` 确认 `registry = build_engine_processor_registry()`。与 plan 一致。
7. **`_get_engine_processor_registry()` 无返回类型注解** — `_doc_processor_factory.py:33` 确认。Plan 正确识别需补充。

## Findings

### 01-未修复-中-Fins 测试文件在 allowed files 中标记为"可选"但测试计划和行为不变证明均要求 Fins 测试

- **位置**: Implementation Slice → allowed files；Tests 章节；行为不变证明 → Fins registry 章节
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**: Implementation Slice allowed files 将 `tests/fins/test_processor_registry.py` 标记为"可选"。但 Tests 章节明确要求 Fins test 断言（共享名称最终对应 Fins classes、Fins 仍先加载 documents 默认 registry 再覆盖）。行为不变证明章节要求"测试断言 registry records，不只断言 import 成功"。
- **反例/失败场景**: Implementation agent 看到"可选"后跳过创建 Fins 测试文件。此时 Fins registry 的覆盖行为（documents 默认 → Fins 增强 → SEC 专项）只能通过代码阅读验证，无法通过测试执行证明。行为不变证明章节的 Fins 断言全部落空。
- **为什么有问题**: 测试计划和行为不变证明是 plan 的 success signal 来源。若 Fins 测试"可选"，则 implementation agent 无法确定是否必须创建该文件来满足验收信号。Plan 内部存在"必须证明"与"可选文件"的矛盾。
- **直接证据**:
  - allowed files: "可选：`tests/fins/test_processor_registry.py`"
  - Tests 章节: "Fins test 断言：...断言共享名称 `docling_processor`、`markdown_processor`、`bs_processor` 最终对应 Fins classes...断言最终 Fins registry 中这些共享名称不再指向通用 `DoclingProcessor`、`MarkdownProcessor`、`BSProcessor`"
  - 行为不变证明: "`build_fins_processor_registry()` 必须先调用 `build_documents_processor_registry()`"
- **影响**: Implementation agent 可能跳过 Fins 测试，导致 plan 的 Fins 行为不变证明无法通过测试执行验证。
- **建议改法和验证点**: 将 `tests/fins/test_processor_registry.py` 从 allowed files 的"可选"改为必选，与 `tests/documents/test_processors.py` 同等对待。或者明确说明：若不创建 Fins focused test，则必须通过 `pytest tests/fins` 全包回归来证明 Fins 行为不变，并在验证命令中明确该替代路径。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 02-未修复-低-Fins 测试断言顺序依赖可能过脆

- **位置**: Tests 章节 → Fins test 断言
- **问题类型**: 测试缺口
- **当前写法**: Plan 列出 Fins registry 的完整 priority 层级断言（SEC 表单 BS 主路径 200、SEC 表单 edgartools 回退 190、`sec_processor` 120、`docling_processor`/`FinsDoclingProcessor` 100、`markdown_processor`/`FinsMarkdownProcessor` 100、`bs_processor`/`FinsBSProcessor` 80）。Plan 同时建议"若完整顺序断言过脆，可在测试中用 helper 从 `list_processors()` 生成 `name -> (class, priority)` 映射，再单独断言关键顺序 / priority bucket"。
- **反例/失败场景**: `list_processors()` 返回的列表按 priority 降序排列，但同 priority 内的顺序取决于 `register()` 调用顺序。Fins registry 注册了 18 个处理器（含 fallback），完整顺序断言会因任何新增/重排注册而失败。Implementation agent 若按 plan 的完整列表写硬编码断言，测试会过脆。
- **为什么有问题**: Plan 自己也承认"完整顺序断言过脆"并给了替代方案，但没有明确推荐哪种。Implementation agent 可能选择硬编码完整列表。
- **直接证据**: Plan Tests 章节列出完整 priority 层级列表后说"若完整顺序断言过脆，可在测试中用 helper 从 `list_processors()` 生成 `name -> (class, priority)` 映射，再单独断言关键顺序 / priority bucket"。
- **影响**: 测试可能因同 priority 内注册顺序微调而失败，增加维护成本。
- **建议改法和验证点**: 明确推荐使用 `name -> (class, priority)` 映射方式，只断言关键 priority bucket 和覆盖行为（共享名称最终指向 Fins classes），不要求完整顺序。将"若完整顺序断言过脆"改为"使用 helper 映射方式，避免硬编码完整顺序"。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risks

1. **外部调用方影响**：移除旧 public export 可能影响仓库外调用方。Plan 在 Residual Risk 章节已识别并通过 PR / release 说明缓解，符合项目约束（禁止兼容 re-export）。风险低，无需在 plan 内额外处理。

2. **`_GENERIC_PROCESSOR_PRIORITY` 常量命名**：该常量不含 `engine` 语义，不需要重命名。Plan 正确保留。无风险。

## 结论

**pass-with-risks**

Plan 整体质量高：动机成立且严重性评估准确，命名决策有直接证据支撑，affected files 完整且与 `rg` 扫描结果一致，禁止兼容 alias / re-export / wrapper 的约束明确，README 触发判断符合更新约束，无过度设计，无 hidden coupling。

1 条 accepted-candidate finding（Fins 测试文件"可选"与测试计划矛盾），1 条 low-severity finding（测试断言过脆建议）。无 blocking open questions。Plan 可在修复 finding 01 后交给 implementation agent。
