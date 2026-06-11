# WU-TOOLS-01-F08 Plan Review — AgentDS

## 元信息

- Work unit: `WU-TOOLS-01-F08`
- Gate: plan review
- Date: 2026-06-11
- Reviewer: AgentDS
- Reviewed artifact: `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`
- Goal confirmation: `docs/reviews/wu-tools-01-f08-goal-confirmation-controller.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/issues-implementation-control.md`

## Review Scope

按 `/planreview` 指定范围：只 review F08 plan，不实现代码、不修改文件。重点审查动机、命名决策、affected files 完整性、测试计划行为不变证明、validation commands 合理性、README 触发判断、hidden coupling / scope 漏洞 / 过度设计 / stop condition 缺口。

## 已核对的直接证据

### 代码事实

- `dayu/documents/processors/registry.py:17` — `build_engine_processor_registry()` 注册 DoclingProcessor (`docling_processor`, priority 10)、MarkdownProcessor (`markdown_processor`, priority 10)、BSProcessor (`bs_processor`, priority 10)。函数位于 `dayu.documents` 包，不依赖 `dayu.engine`。
- `dayu/documents/processors/__init__.py:12,23` — 导入并导出 `build_engine_processor_registry` 到公共 `__all__`。
- `dayu/documents/processors/_doc_processor_factory.py:17,20,33,45-48,87` — 导入旧 builder，模块级单例 `_ENGINE_PROCESSOR_REGISTRY`，通过 `_get_engine_processor_registry()` 返回并用于 `create_doc_file_processor()`。
- `dayu/fins/processors/registry.py:3,11,41,60` — 模块 docstring "在 engine 核心处理器注册表基础上"、导入旧 builder、函数 docstring "先加载 engine 核心处理器"、调用 `build_engine_processor_registry()` 作为 Fins registry 基础。
- `dayu/fins/README.md:382` — "`build_fins_processor_registry()` 在 engine 文档处理器注册表基础上覆盖注册..."
- `docs/host/issues-implementation-control.md` — 多处引用旧函数名（当前状态表 F08 行、F08 section、residual risk 表 `WU-TOOLS-01-S1-R2`）。
- `rg` 确认：生产代码仅 4 个文件引用旧名，测试代码零直接引用，`docs/reviews/` 下多处历史 artifact 引用旧名（均为历史留痕）。

### 设计真源对齐

- `docs/host/design.md` — Host 不拥有工具注册、文档存取或 Fins 语义。
- `docs/engine/design.md:26-27` — "Engine 不保存跨 run 状态，不拥有工具注册表，不读取配置文件，不理解财报业务语义，也不直接访问财报文档存储。"
- 当前 `build_engine_processor_registry()` 位于 `dayu.documents.processors.registry`，注册通用 documents processor，由 Doc tools 和 Fins 复用。函数名暗示 Engine ownership，与设计真源冲突。

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | 旧名仅存在于 plan 声称的 4 个生产文件中 | 成立。`rg` 确认无其他生产文件引用。 |
| A2 | 重命名不改变 ProcessorRegistry 行为 | 成立。函数体重命名不改变注册逻辑。 |
| A3 | `build_documents_processor_registry` 是最优新名 | 成立。优于 `build_default_processor_registry`（跨包语义弱）。 |
| A4 | Fins README 仅 line 382 有旧 ownership 表述 | 成立。其他引用 `build_fins_processor_registry()` 的行不涉及 "engine" 所有权措辞。 |
| A5 | 现有测试不直接导入旧 builder，rename 不会 break 测试 | 成立。测试只通过 `build_fins_processor_registry()` 间接消费。 |
| A6 | 单 slice 足够覆盖所有改动 | 成立。4 个文件的行为面集中在同一 builder 的直接调用链。 |

## Findings

### F1-未修复-低-other-docs/host-plan-artifacts-旧名残留未纳入清理范围说明

- **位置**: plan "成功信号" 与 "验证命令" 章节
- **问题类型**: 范围漂移 / open question 未收敛
- **当前写法**: 
  - 成功信号: "`build_engine_processor_registry` 在生产代码、测试、稳定 README 和 `docs/host/issues-implementation-control.md` 中无残留"
  - 验证命令: `rg ... dayu tests dayu/fins/README.md docs/host/issues-implementation-control.md`
  - 明确排除 `docs/reviews/` 历史 artifact
- **反例/失败场景**: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md:21` 包含 `build_engine_processor_registry(...)` 引用（作为非目标声明）。这不是 review artifact，而是另一个已完成 work unit 的 plan artifact。plan 未讨论这类 `docs/host/` 下非 control doc 的历史 plan artifact 是否需要更新。
- **为什么有问题**: plan 的 success signal 与 `rg` 验证范围存在微小不一致——success signal 说 "生产代码、测试、稳定 README 和 control doc 中无残留"，`rg` 的搜索目标也精确匹配这四类。但 `docs/host/` 下的其他 plan artifact 不在 success signal 也不在 `rg` target 中，plan 没有解释为什么这些文件不需要更新。
- **直接证据**: 
  - `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md:21` 引用了 `build_engine_processor_registry(...)`
  - plan 的 success signal 和 `rg` 命令均不覆盖此文件
- **影响**: 低——该文件是已完成 work unit 的 plan，其旧名引用出现在非目标声明中，不影响当前实现。但若 implementation agent 对 "哪些 docs/host/ 文件需要更新" 产生歧义，可能浪费时间检查。
- **建议改法和验证点**: 在 plan 的 "成功信号" 或 "非目标" 中增加一句：`docs/host/` 下非 control doc 的历史 plan artifact 可保留旧引用（类似 `docs/reviews/` 的留痕规则），或单独列出需检查的文件清单。最简方案是修改 `rg` 验证命令中的目标为 `docs/host/issues-implementation-control.md`（与 success signal 一致），并在 plan 正文中说明理由。
- **修复风险（低）**: 加一句话澄清即可。
- **严重程度（低）**: 不影响实现正确性，仅 clarity 问题。

### F2-未修复-低-Fins-focused-test-断言与已有-pipeline-tests-存在语义重叠但未说明互补关系

- **位置**: plan "测试" 章节 > Fins test 断言
- **问题类型**: 切片过粗 / 最佳实践偏离
- **当前写法**: plan 要求新增 focused Fins test，断言 `build_fins_processor_registry().list_processors()` 的完整 name→class→priority 映射。同时已有 30+ 处 `test_sec_pipeline_*.py` 测试通过 `build_fins_processor_registry()` 构造 `processor_registry` 参数进行 pipeline 集成测试。
- **反例/失败场景**: focused test 重复断言 pipeline tests 早已通过 indirect coverage 证明的同一组注册事实。如果 focused test 的断言值与 pipeline tests 隐式依赖的 registry 行为产生冲突（例如 priority 常量重构后 focused test 更新但 pipeline test 未更新），会出现同一行为有两种不同断言真源。
- **为什么有问题**: plan 没有解释 focused test 与已有 pipeline tests 的关系——是互补（focused test 作为 contract test，pipeline test 作为 integration test）还是替代（focused test 使 pipeline tests 中的 registry 断言变得多余）。这不是 blocking 问题，但可能在 review gate 引发关于测试职责的讨论。
- **直接证据**: 
  - `tests/fins/test_sec_pipeline_download.py` 等大量测试已使用 `build_fins_processor_registry()` 作为 registry 输入
  - plan 建议新增的 `tests/fins/test_processor_registry.py` 会再次断言同一 registry 的 composition
- **影响**: 低——如果 implementation 清楚区分 contract test vs integration test 的职责，不会造成问题。最多在 code review gate 被问到 "为什么需要两个地方断言同一件事"。
- **建议改法和验证点**: 在测试章节加一句说明：focused test 是 registry contract test（直接断言注册名称/类/priority），pipeline tests 是 consumer integration test（通过真实 pipeline 行为间接证明 registry 可用）。两者互补，不替代。
- **修复风险（低）**: 加一句话说明。
- **严重程度（低）**: 不影响正确性，属 test strategy clarity。

### F3-未修复-低-pytest-tests/documents-tests/fins-全量回归可能引入不必要噪声

- **位置**: plan "验证命令" 章节 > "相关包测试"
- **问题类型**: 最佳实践偏离
- **当前写法**: `pytest tests/documents tests/fins -q` 作为相关包测试。plan 已包含 focused test 命令优先运行。
- **反例/失败场景**: `tests/fins/` 包含 18 个测试文件，其中 pipeline download/upload stream tests 涉及 SEC 下载器、巨潮下载器、披露易下载器等外部依赖或 heavy fixtures。如果这些测试因网络、fixture 过期或环境问题失败（而非本次 rename 导致），implementation agent 或 reviewer 可能难以快速判断 rename 是否引入回归。
- **为什么有问题**: plan 将 focused tests 与全量包测试都列为验证命令，但没有说明全量包测试失败时如何区分 rename 回归 vs 预存环境/fixture 问题。这不是 plan 的缺陷，但 implementation closeout 需要明确这一点。
- **直接证据**: `tests/fins/` 目录包含 `test_sec_pipeline_download.py`（~2200 行）、`test_sec_pipeline_upload_filing_stream.py` 等重型测试。
- **影响**: 低——rename 不改变 registry 行为，因此全量 Fins 测试失败几乎一定不是 rename 导致。implementation agent 在 closeout 中只需确认 focused tests 通过即可证明 rename 正确性。
- **建议改法和验证点**: 无需修改 plan。implementation closeout 中如全量 tests/fins 有非 rename 相关失败，应记录为预存问题而非 rename 回归。
- **修复风险（低）**: 无需修 plan，属于 closeout 注意事项。
- **严重程度（低）**: 不影响 plan 可执行性。

## Open Questions

无。plan 已覆盖所有关键决策点，无 blocking open question。

## Residual Risk

1. **仓库外部 consumer 影响**: 移除 `build_engine_processor_registry` 公共 export 可能 break 仓库外调用方。plan 已识别此风险并裁决按项目规则禁止 alias/wrapper，由 PR/release 说明缓解。Risk owner: release note / PR description。

2. **`_doc_processor_factory.py` 覆盖率**: 当前该文件 0% 单测覆盖（仅通过 integration path 间接覆盖）。本次 rename 不改变其行为，但也不新增其 focused test。若后续修改该文件行为，需先补测试。Risk owner: 后续 work unit / 常规测试维护。

3. **历史 plan artifact 旧名引用**: `docs/host/` 下非 control doc 的历史 plan artifact 会继续包含旧名。这是可接受留痕（与 `docs/reviews/` 规则一致），但若未来有人检索 `build_engine_processor_registry` 可能找到这些文件并困惑。Risk owner: 低优先级，可在实现 closeout 中简要说明。

## Plan Review Conclusion

**Verdict: pass-with-risks**

Plan 动机成立，代码事实准确，命名决策 `build_documents_processor_registry(...)` 优于备选方案，affected files 完整，测试计划能证明行为不变，validation commands 合理，README 触发判断符合约束，无 hidden coupling、scope 漏洞、过度设计或 stop condition 缺口。

3 条 findings 均为低严重度，不影响 plan 进入 implementation gate：
- F1: `docs/host/` 历史 plan artifact 边界澄清（可一句话修复）
- F2: focused test 与 pipeline test 互补关系说明（可在 code review 中自然澄清）
- F3: 全量 `tests/fins` 回归可能引入噪声（closeout 注意事项，无需修 plan）

Controller 可按需裁决 findings 为 accepted（修改 plan）或 deferred（在 implementation/closeout 处理）。

## Finding Summary

| Finding | 严重程度 | 建议裁决 |
|---------|---------|---------|
| F1: 历史 docs/host/ plan artifact 旧名残留范围说明 | 低 | accepted 或 deferred |
| F2: focused test 与 pipeline test 互补关系 | 低 | deferred |
| F3: 全量 tests/fins 回归噪声 | 低 | deferred（closeout 注意即可） |
