# WU-TOOLS-01-F08 Aggregate Deepreview

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: `3dbc27a8`
- Output file: `docs/reviews/wu-tools-01-f08-aggregate-deepreview-mimo.md`
- Timestamp: 20260611-110706
- Included scope: `git diff 3dbc27a8..HEAD` — F08 从 goal/plan 到 implementation/code-review 的全部已提交变更（21 files, +1400 -28）
- Excluded scope: 无
- Parallel review coverage: 无

## Verdict

pass.

## Findings

未发现实质性问题。

逐项 deepreview focus 验证如下：

### Focus 1: 第一性原理 — 动机与 scope

- **动机成立**：`build_engine_processor_registry()` 位于 `dayu.documents.processors.registry`，注册的是通用 documents processor（Docling、Markdown、BS），被 Doc tools 和 Fins 复用，不属于 Engine。Host 设计真源（`docs/host/design.md` L39-40）明确 Engine 不拥有工具注册、文档存取或 Fins 语义；Engine 设计真源（`docs/engine/design.md` L12）明确 Engine 不拥有工具注册表。迁移完成后继续暴露 `engine` 命名会误导 ownership，弱化 `dayu.documents` 作为共享文档基础能力 owner 的边界。
- **严重性正确评估**：plan 正确识别为 ownership / public naming drift，非运行时行为 bug，严重性适中。
- **scope 未被高估或偏离**：单 slice，只做直接 rename、直接调用方更新、focused behavior tests 和必要稳定文档同步。不引入新 registry abstraction、provider 机制、兼容层、迁移 shim、模块拆分或配置项。

### Focus 2: 分层 — ownership 清晰，无反向依赖或跨层泄漏

- `dayu.documents.processors.registry` 定义 `build_documents_processor_registry()`，注册通用 documents processor。
- `dayu.fins.processors.registry` 调用 `build_documents_processor_registry()` 作为基础，再覆盖注册 Fins 专属 processor。
- `dayu.documents.processors._doc_processor_factory` 使用 documents registry 作为 doc tools 的处理器工厂。
- Engine 不参与文档处理器注册，不 import `dayu.documents.processors`。
- 没有引入反向依赖：documents 不依赖 fins/host/engine，fins 只依赖 documents（正向），host/engine 不依赖 documents.processor_registry（非直接）。

### Focus 3: 兼容性禁令 — 无旧名 alias/re-export/wrapper/facade

- `dayu/documents/processors/__init__.py:12` 仅导出 `build_documents_processor_registry`，`__all__` 中无旧名字符串。
- `dayu/documents/processors/registry.py` 未保留 `build_engine_processor_registry = build_documents_processor_registry` 或等价别名。
- `dayu/documents/processors/_doc_processor_factory.py` 未保留旧名 wrapper。
- `dayu/fins/processors/registry.py` 未保留旧名 import 或 fallback。
- `rg -n "build_engine_processor_registry|_ENGINE_PROCESSOR_REGISTRY|_get_engine_processor_registry" dayu tests dayu/fins/README.md docs/host/issues-implementation-control.md` 返回 exit 1（无匹配）。
- 符合 AGENTS.md "禁止兼容性代码：兼容性 re-export、兼容性常量 re-export、兼容性 wrapper / facade" 约束。

### Focus 4: 行为保持 — registry 行为不变，测试真能证明

- **documents 默认 registry**：`registry.py:38-57` 函数体语义等价——`ProcessorRegistry()` + 三个 `register(overwrite=True)` 调用，priority 均为 `_GENERIC_PROCESSOR_PRIORITY = 10`，顺序为 Docling → Markdown → BS。`test_documents_processor_registry_registers_default_processors` 断言 `list_processors()` 精确等于 `[{"name":"docling_processor","class":"DoclingProcessor","priority":10}, ...]`，锁定名称、类、priority 和同 priority 下顺序。
- **Fins registry overlay**：`fins/processors/registry.py:60` 调用 `build_documents_processor_registry()` 作为基础，随后以 `overwrite=True` 覆盖共享名称（FinsDoclingProcessor/FinsMarkdownProcessor priority 100，FinsBSProcessor priority 80），SEC 处理器 priority 200/190/120 不变。`test_fins_processor_registry_overlays_documents_defaults` 使用 `name → (class, priority)` 映射断言覆盖行为和 priority bucket，未硬编码完整列表顺序；同时断言共享名称不再指向通用类。
- **验证命令**：`pytest tests/documents/test_processors.py tests/fins/test_processor_registry.py -q` → 5 passed, 3 warnings。`pytest tests/documents tests/fins -q` → 263 passed, 1 skipped, 3 warnings。warnings 为 edgartools 依赖的 deprecation warnings，与 rename 无关。

### Focus 5: LLM-facing / 文档语义

- `dayu/fins/README.md` 两处 ownership 表述从 "engine 文档处理器注册表基础上" 改为 "documents 默认处理器注册表基础上"，自解释、无内部治理伪装。
- `docs/host/issues-implementation-control.md` F08 section 使用业务可读语义描述 rename 行为和验证结果。
- 未把系统状态、调度状态或 Host/Engine 内部治理信息伪装成业务事实。

### Focus 6: 测试 / pyright / README

- **pyright**：`python -m pyright dayu/ tests/ utils/` → 0 errors, 0 warnings, 0 informations。
- **README 触发规则**：
  - `dayu/fins/` 修改 → 检查并更新 `dayu/fins/README.md`：已更新，符合 README 内 Agent 更新约束。
  - `tests/` 修改 → 检查 `tests/README.md`：未更新，正确——新测试位于既有 `tests/documents/` 和 `tests/fins/` 分层，未引入新层级或约定。
  - 未触发 `dayu/README.md` 更新：不涉及 UI/Service/Host/Engine 分层关系变化。
- **验证矩阵**：focused registry tests（documents + Fins）覆盖行为不变核心断言；full `tests/documents tests/fins` 覆盖集成路径；pyright 覆盖类型安全。

### Focus 7: Residual risk — WU-TOOLS-01-S1-R2 关闭充分

- `WU-TOOLS-01-S1-R2` 已从 Residual Risk 表移除（原 `docs/host/issues-implementation-control.md` L199）。
- F08 section 明确记录 "已关闭 `WU-TOOLS-01-S1-R2`"，关闭依据为实现验证证据：旧名在全部 stable target 中清除、focused tests 证明行为不变、pyright 0 errors。
- 关闭证据链完整，无需 reopen。

### Focus 8: 总控一致性抽查 — F04-F07 不再出现

- `rg -n "WU-TOOLS-01-F0[4567]" docs/host/issues-implementation-control.md` 返回 exit 1（无匹配）。
- 总控中不存在 WU-TOOLS-01-F04/F05/F06/F07 作为 active work unit 或 residual risk。

## Open Questions

无。

## Residual Risk

| 风险项 | 严重度 | Owner | 说明 |
|---|---|---|---|
| 仓库外部 consumer 断裂 | 低 | PR / release communication | 移除 `build_engine_processor_registry` 公共 export 可能 break 仓库外调用方。按 AGENTS.md 禁止兼容 re-export 的规则，由 PR / release 说明缓解。 |
| 历史 artifact 旧名留痕 | 低 | 无（可接受留痕） | `docs/reviews/` 和 `docs/host/` 下历史 plan / review artifact 继续包含旧名，属计划内留痕，非 cleanup target。 |
| 单文件覆盖率未独立测量 | 低 | 无（未度量项） | 行为风险已被 focused contract tests 和 full `tests/documents tests/fins`（263 passed）覆盖；覆盖率缺口属于未度量项，非已知缺陷。 |

## 验证摘要

| 检查项 | 结果 |
|---|---|
| 旧名清理 `rg`（stable targets） | passed，无匹配 |
| 历史 artifact `rg` | passed，仅历史 review/plan artifact 保留旧名 |
| `pytest tests/documents/test_processors.py tests/fins/test_processor_registry.py -q` | 5 passed, 3 warnings |
| `pytest tests/documents tests/fins -q` | 263 passed, 1 skipped, 3 warnings |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed |
| 兼容性代码检查（alias/re-export/wrapper/facade） | passed，无兼容性代码 |
| 分层边界检查（反向依赖 / 跨层泄漏） | passed，无违规 |
| 总控 F04-F07 一致性抽查 | passed，无残留 |
| WU-TOOLS-01-S1-R2 关闭证据链 | 完整，无需 reopen |
