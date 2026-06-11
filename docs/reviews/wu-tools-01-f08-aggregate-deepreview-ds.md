# WU-TOOLS-01-F08 Aggregate Deepreview

## Meta

- Work unit: `WU-TOOLS-01-F08`
- Gate: aggregate deepreview
- Date: 2026-06-11
- Reviewer: AgentDS
- Scope: `git diff 3dbc27a8..HEAD` — F08 从 goal/plan 到 implementation/code-review 的全部已提交变更
- Design sources: `AGENTS.md`, `docs/host/design.md`, `docs/engine/design.md`, `docs/host/issues-implementation-control.md`
- Reviewed artifacts:
  - `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`
  - `docs/reviews/wu-tools-01-f08-goal-confirmation-controller.md`
  - `docs/reviews/wu-tools-01-f08-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f08-plan-review-ds.md`
  - `docs/reviews/wu-tools-01-f08-plan-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f08-plan-fix-codex.md`
  - `docs/reviews/wu-tools-01-f08-plan-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f08-plan-rereview-ds.md`
  - `docs/reviews/wu-tools-01-f08-plan-rereview-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f08-implementation-codex.md`
  - `docs/reviews/wu-tools-01-f08-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f08-code-review-ds.md`
  - `docs/reviews/wu-tools-01-f08-code-review-controller-adjudication.md`

## Verdict

**Pass.** No blocking findings. The work unit was correctly motivated, strictly scoped, faithfully implemented per the accepted plan, and independently verified.

## Findings

Findings: none.

## Review Evidence

### 1. 第一性原理：动机与 scope

F08 动机成立且 scope 正确。直接证据：

- `dayu/documents/processors/registry.py:17` 定义的函数 `build_engine_processor_registry()` 位于 `dayu.documents` 包，注册的是通用 documents processor（Docling/Markdown/BS），不依赖 `dayu.engine`。
- `docs/engine/design.md:26-27` 明确规定 "Engine 不保存跨 run 状态，不拥有工具注册表，不读取配置文件，不理解财报业务语义，也不直接访问财报文档存储。"
- 旧名暗示 Engine ownership，属于迁移后遗留的 ownership/public naming drift。rename 修复了这个问题，scope 严格限定在直接命名替换、调用方更新、focused tests 和稳定文档同步，无 scope creep。

没有 scope 高估或偏离。所有 8 个 changed production/doc files 都在 accepted plan 的精确允许范围内。

### 2. 分层：documents/Fins/Host/Engine ownership

分层清洁，无反向依赖，无跨层泄漏：

- `dayu.documents.processors.registry` — 构建共享 documents 默认 processor registry。这是 documents 层的能力，不依赖 Host/Engine/Fins。
- `dayu.documents.processors._doc_processor_factory` — Doc tools 消费这个 registry，是 documents 层的消费者。
- `dayu.fins.processors.registry` — Fins 层从 documents 层导入，在默认 registry 基础上 overlay Fins/SEC processor。方向正确：`dayu.fins` -> `dayu.documents`。
- 无 Host/Engine 反向依赖。无 documents 层导入 `dayu.engine` 或 `dayu.host`。

新增 import `from .processor_registry import ProcessorRegistry`（`_doc_processor_factory.py:17`）在 `from __future__ import annotations` 下服务于类型注解，pyright 0 errors 确认没有引入运行时循环依赖。

### 3. 兼容性禁令

无旧名 alias/re-export/wrapper/facade。独立验证：

- `rg "build_engine_processor_registry|_ENGINE_PROCESSOR_REGISTRY|_get_engine_processor_registry" dayu tests dayu/fins/README.md docs/host/issues-implementation-control.md` — 无匹配（exit 1）。
- `dayu/documents/processors/__init__.py:23` 的 `__all__` 仅包含 `"build_documents_processor_registry"`，不包含旧名。
- git diff 全文搜索 `= build_documents_processor_registry` 没有发现 alias 赋值。
- 无旧名 wrapper、facade 或条件别名。

历史 review artifacts（`docs/reviews/`）和 `docs/host/` 下非 control doc 的历史 plan artifacts 保留旧引用，属于 accepted plan 明确允许的留痕。这些文件的旧名出现在 plan evidence / review 代码快照 / 历史裁决中，不是稳定 public API。

### 4. 行为保持：documents registry 与 Fins overlay registry

Documents 默认 registry 行为不变（`registry.py:38-57`）：
- 注册 `DoclingProcessor` → `docling_processor`，priority 10
- 注册 `MarkdownProcessor` → `markdown_processor`，priority 10
- 注册 `BSProcessor` → `bs_processor`，priority 10
- `_GENERIC_PROCESSOR_PRIORITY = 10` 未修改

Fins registry overlay 行为不变（`fins/processors/registry.py:60-170`）：
- 先调用 `build_documents_processor_registry()` 作为基础
- 以 `overwrite=True` 覆盖注册 Fins 增强处理器
- SEC 专项处理器 priority 200/190/120 层级不变
- 所有常量 `_SPECIAL_FORM_PRIORITY`、`_REPORT_FORM_FALLBACK_PRIORITY`、`_SEC_PROCESSOR_PRIORITY`、`_FINS_DOC_MARKDOWN_PRIORITY`、`_FINS_BS_PRIORITY` 未修改

**Focused tests 证明行为不变：**

`tests/documents/test_processors.py:46-55`（`test_documents_processor_registry_registers_default_processors`）：
- 从新名 import：`from dayu.documents.processors import build_documents_processor_registry`
- 断言 `list_processors()` 精确等于 3 个默认 processor 注册记录，锁定 name/class/priority

`tests/fins/test_processor_registry.py:8-71`（`test_fins_processor_registry_overlays_documents_defaults`）：
- 使用 `name → (class, priority)` mapping 断言覆盖行为
- 断言共享名称指向 Fins 类而非通用类
- 使用 priority bucket 集合断言 SEC 处理器 200/190 层级
- 未硬编码完整列表顺序

### 5. LLM-facing/文档语义：README/control doc 自解释

`dayu/fins/README.md` 两处 ownership 表述更新：
- L382: "在 engine 文档处理器注册表基础上" → "在 documents 默认处理器注册表基础上"
- L596: "在通用文档处理器基础上" → "在 documents 默认处理器注册表基础上"

更新符合 `dayu/fins/README.md` 的 Agent 更新约束：只涉及当前已实现架构的 ownership 表述修正。

`docs/host/issues-implementation-control.md` 更新：
- F08 section（行 225）：记录新名 `build_documents_processor_registry(...)` 和实现状态
- F08 section（行 1065）：记录 `WU-TOOLS-01-S1-R2` 关闭
- Residual Risk 表：`WU-TOOLS-01-S1-R2` 行已移除（原行 199）

总控文档状态表正确反映当前 gate（`review`），next entry point（`aggregate deepreview gate`），以及 blocking open questions（`none`）。

无内部治理伪装成业务事实的情况。Registry registry builder 名称现在直接表达 documents ownership，不需要读者依赖隐式上下文猜测 "engine" 的含义。

### 6. 测试/pyright/README 验证矩阵

| 验证项 | 命令 | 结果 | 独立复验 |
|---|---|---|---|
| 旧名清理 | `rg ... dayu tests dayu/fins/README.md docs/host/issues-implementation-control.md` | exit 1（无匹配） | ✓ 已复验 |
| Focused tests | `pytest tests/documents/test_processors.py tests/fins/test_processor_registry.py -q` | 5 passed, 3 warnings | ✓ 已复验 |
| 全量相关 tests | `pytest tests/documents tests/fins -q` | 263 passed, 1 skipped, 3 warnings | 未复验（controller 已验证） |
| Pyright | `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations | ✓ 已复验 |
| Whitespace | `git diff --check` | passed | ✓ 已复验 |

3 个 pytest warnings 为 edgartools 依赖的 deprecation warnings，与本次 rename 无关。

README 触发判断：`dayu/fins/` 修改 → `dayu/fins/README.md` 已更新；`tests/` 修改 → `tests/README.md` 检查后无需更新（新测试位于既有分层）；`dayu/README.md` 无需更新（无分层关系/装配方式变化）。

### 7. WU-TOOLS-01-S1-R2 关闭充分性

关闭证据链完整：

1. `rg` 确认旧名在全部 stable target（生产代码、测试、Fins README、总控文档）中已清除
2. Focused tests 证明 behavior registry 行为不变
3. Pyright 0 errors
4. `WU-TOOLS-01-S1-R2` 已从 active Residual Risk 表移除
5. F08 section 明确记录关闭依据

无需将 S1-R2 转移到其他 work unit。无需 reopen。

### 8. F04-F07 总控一致性

独立验证 `rg "WU-TOOLS-01-F0[4-7]" docs/host/issues-implementation-control.md` — 无匹配（exit 1）。

总控文档中无 `WU-TOOLS-01-F04`/`F05`/`F06`/`F07` 引用。这些 work unit 已在更早的 phase 被 merge 到 F01-03/F09 或作为 completed 子任务。总控当前只会显示 active/current work units；F04-F07 作为 completed 子任务可能出现在各 work unit 的 detail section 叙述中（例如 `WU-CM-01-F04` 是另一个 work unit 系列的编号），但这是预期内的历史事实，不是错误引用。

总控一致性抽查通过。

## Open Questions

无。

## Residual Risks

1. **仓库外部 consumer 断裂**：移除 `build_engine_processor_registry` 公共 export 可能 break 仓库外调用方。Project rules (AGENTS.md) 和 accepted plan 均明确禁止兼容 alias/re-export/wrapper。缓解方式：PR/release 说明中注明 breaking change。Owner: release note / PR description。

2. **`docs/reviews/` 历史 artifact 旧名留痕**：历史 review artifact 保留 22+ 处 `build_engine_processor_registry` 引用。属于 accepted plan 明确允许的留痕。低优先级困惑风险：未来开发者检索旧名时可能困惑。

3. **单文件测试覆盖率未独立测量**：implementation 未提供 `_doc_processor_factory.py`、`registry.py` 等单个文件的覆盖率数据。行为风险已被 focused contract tests 和 full `tests/documents tests/fins`（263 passed）覆盖。覆盖率缺口属于未度量项，非已知缺陷。

## 验证与只读检查摘要

| Pre-gate artifact | Verdict | 关键证据 |
|---|---|---|
| Goal confirmation (controller) | pass | 第一性原理核实，动机成立且 scope 正确 |
| Plan review (MiMo + DS) | pass-with-findings → 4 accepted | accepted findings 均已被 plan fix 覆盖 |
| Plan fix (Codex) | 全部修复 | 5 findings 按要求修复 |
| Plan re-review (MiMo + DS) | pass ×2 | 0 blocking findings |
| Plan re-review adjudication (controller) | pass | 接受 plan，进入 implementation |
| Implementation (Codex) | passed | 8 files changed, 所有验证通过 |
| Code review (MiMo + DS) | pass ×2 | 无实质问题 |
| Code review adjudication (controller) | pass | 0 accepted fix findings |
| **Aggregate deepreview (DS)** | **pass** | **无实质问题** |

独立复验完整通过：旧名清理 `rg` exit 1、focused tests 5 passed、pyright 0 errors。

Gate flow 完整：goal confirmation → plan → plan review → plan fix → plan re-review → plan re-review adjudication → implementation → code review → code review adjudication → aggregate deepreview。每个 gate 都有完整 artifact chain。
