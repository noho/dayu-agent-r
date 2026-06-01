# WU-CTX-02 + WU-CTX-03 Slice C Code Review

## Reviewer

AgentMiMo

## Gate / Scope

- 当前 gate：WU-CTX-02 + WU-CTX-03 implementation Slice C。
- Approved plan：`docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`。
- 已有前置 accepted commits：Slice A `2f2f22c`，Slice B `e6156de`。
- Implementation artifact：`docs/reviews/wu-ctx-02-03-implementation-sliceC-codex-20260601.md`。

## 审查范围

本次审查覆盖以下未提交 diff（git diff HEAD）：

| 文件 | 变更类型 | 行数变化 |
|------|---------|---------|
| `dayu/host/context_fallback.py` | 新增 | +745 |
| `dayu/host/run_input.py` | 扩展 | +159 |
| `dayu/host/dispatch.py` | 扩展 | +331 / -74 |
| `tests/host/test_run_input_builder.py` | 扩展 | +292 |
| `tests/host/test_dispatch_scheduler.py` | 扩展 | +101 |
| `dayu/host/README.md` | 更新 | +2 |
| `tests/README.md` | 更新 | +2 / -1 |

## 验证命令及结果

```
$ source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q
97 passed in 1.15s

$ source .venv/bin/activate && python -m pyright dayu/host/context_fallback.py dayu/host/run_input.py dayu/host/dispatch.py
0 errors, 0 warnings, 0 informations
```

## Findings

### F-01: `EventLogContextFallbackProvider` 中冗余 SQL 子串拼接

- **Severity**: observation（不阻塞）
- **文件**: `dayu/host/context_fallback.py:289-299`
- **描述**: `_load_context_fallback_tx` 使用 f-string 拼接 `TABLE_EVENT_LOG` 常量构造 SQL。该模式与本项目既有 EventLog 查询风格一致（如 `dispatch.py` 中同类用法），不是新引入的风险。`TABLE_EVENT_LOG` 是模块级常量，不来自用户输入。
- **处理**: 无需修改，保持与既有代码风格一致。

### F-02: `_required_block_ids` 包含 `already_represented` blocks 的语义正确性

- **Severity**: observation（不阻塞）
- **文件**: `dayu/host/context_fallback.py:538-557`
- **描述**: `_required_block_ids` 将 `STABLE_INPUT` section 和 `already_represented=True` 的 blocks 都加入必保留集合。这覆盖了"stable / compact represented context"语义：`already_represented` 标记已被 compact summary 或 stable fact 充分代表的 blocks，包含 `COMPACT_INPUT` section 的 blocks。逻辑正确，但依赖 `already_represented` 标记的正确设置（由上游 `compact_material.py` 保证）。
- **处理**: 无需修改，上游 material 构造已有覆盖。

### F-03: `build_selection_failure_budget_payload` 使用 `RecentWindowFallbackAction.FAIL_CLOSED` 作为 decision 值

- **Severity**: observation（不阻塞）
- **文件**: `dayu/host/context_fallback.py:498`
- **描述**: `build_selection_failure_budget_payload` 的 `decision` 字段使用 `RecentWindowFallbackAction.FAIL_CLOSED.value`（即 `"fail_closed"`），而正常路径的 `RecentWindowFallbackBudgetResult.decision` 使用 `ContextBudgetDecision` 枚举值（如 `"within_budget"` / `"block_hard_threshold"`）。两者类型不一致，但 selection failure 本身就是异常路径，使用 `"fail_closed"` 作为诊断语义是合理的。`build_context_compaction_failed_payload` 的 `fallback_budget_result` 字段是 `object | null`，不要求内部 decision 必须是 `ContextBudgetDecision`。
- **处理**: 无需修改，语义清晰。

### F-04: `_fallback_context_messages` 中当前 input anchor 被排除后再由 `RunInputBuilder.build` 追加

- **Severity**: observation（不阻塞）
- **文件**: `dayu/host/run_input.py:1668-1675`（build 方法末尾追加 `UserMessage`）与 `run_input.py` `_fallback_context_messages` 函数
- **描述**: `_fallback_context_messages` 排除 `CURRENT_INPUT_ANCHOR` block（因为它由 `build` 方法在末尾作为 `UserMessage` 追加）。这确保了当前用户消息不重复。流程：fallback 路径过滤掉 current anchor → 渲染为 bounded context messages → `build` 末尾追加 `UserMessage(role=USER, content=current_facts.user_prompt)`。逻辑正确。
- **处理**: 无需修改。

### F-05: 测试中 `_hard_threshold_prompt` 使用 `"x" * 240` 硬编码长度

- **Severity**: observation（不阻塞）
- **文件**: `tests/host/test_dispatch_scheduler.py:4143-4152`
- **描述**: `_HARD_THRESHOLD_PROMPT_CHAR_COUNT = 240` 和 `_hard_threshold_prompt()` 是测试辅助常量和函数，与既有的 `_SOFT_THRESHOLD_PROMPT_CHAR_COUNT = 120` / `_soft_threshold_prompt()` 模式一致。测试常量是允许的字面量（AGENTS.md 约束"禁止魔法数字"豁免测试常量）。
- **处理**: 无需修改。

### F-06: fallback dispatch 路径的 `_start_governed_in_transaction` 是否写 `RUN_STARTED`

- **Severity**: observation（不阻塞）
- **文件**: `dayu/host/dispatch.py` `_append_compaction_failed_with_proactive_fallback` 方法
- **描述**: fallback budget 通过时调用 `self._start_governed_in_transaction(transaction, run)` 创建 pending dispatch。这是既有方法，负责写 `RUN_STARTED` 并返回 `PendingDispatchRecord`。随后由 `drain_once` 处理 dispatch。`RUN_STARTED` 在 `CONTEXT_COMPACTION_FAILED` 之后写入，符合 plan 要求的状态机：`CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED -> ATTEMPT_STARTED -> dispatch`。
- **处理**: 无需修改。

## 设计合规性检查

| 检查项 | 结论 |
|-------|------|
| deterministic recent-window fallback selection：固定 current input anchor、stable/compact represented context、floor，reverse chronological 追加 | ✅ 符合 |
| 无 public N 配置、无 arbitrary max-N 魔法常量 | ✅ 符合 |
| fallback digest 与 payload 稳定、无 raw prompt/provider payload 泄漏 | ✅ 符合 |
| failed payload 字段与 Slice B validator 兼容 | ✅ 符合（新增字段均为 optional，`fallback_action` 默认 `"not_applicable"`） |
| fallback_action 语义正确 | ✅ 符合 |
| budget re-estimate 复用现有 conservative estimator 和 `BudgetEstimateInput.message_fragments` | ✅ 符合 |
| 未引入 provider tokenizer 或 public `ContextBudgetPolicy` 字段 | ✅ 符合 |
| RunInputBuilder fallback provider 默认 no-op | ✅ 符合 |
| active fallback 只过滤同源 ordinary material blocks | ✅ 符合 |
| 当前 input 只由正常 user message anchor 追加，不重复或丢失 | ✅ 符合 |
| proactive dispatch 不进入 `RECOVERING` | ✅ 符合 |
| 不写 `CONTEXT_COMPACTED` | ✅ 符合 |
| 不写 compact artifact | ✅ 符合 |
| 不物化 memory stable facts | ✅ 符合 |
| 预算通过创建 Attempt，over-budget 或 selection failure fail closed | ✅ 符合 |
| tests 覆盖核心分支，未堆兼容逻辑 | ✅ 符合 |
| README 更新符合职责 | ✅ 符合 |

## AGENTS.md 合规性检查

| 检查项 | 结论 |
|-------|------|
| 中文 docstring 完整（参数、返回值、异常） | ✅ |
| 签名无 `Any` / `object` / 无类型参数 | ✅ |
| 无魔法数字/字符串（测试常量除外） | ✅ |
| 无 God object / God function | ✅ |
| 无兼容性代码 | ✅ |
| 分层架构 `UI -> Service -> Host -> Engine` | ✅ Host 内部 helper，不越界 |
| `dayu.runtime` 无反向依赖 | ✅ 未触碰 |
| 数据处理 / 存储 / 工具调用职责分离 | ✅ |
| 测试跟着实现边界迁移 | ✅ 新增测试覆盖 fallback 路径 |

## 最终结论

**Accepted。No blocking findings。**

Slice C 实现完整覆盖了 approved plan 中 proactive deterministic recent-window fallback 的全部要求。fallback selection 算法正确实现了 budget-driven、deterministic、无 public config 的 recent window 选择。payload 稳定无泄漏。状态机符合设计：fallback dispatch 不进入 `RECOVERING`，不写 `CONTEXT_COMPACTED`，不写 compact artifact。RunInputBuilder fallback provider 正确过滤并渲染 selected blocks。测试覆盖了核心分支（selection determinism、budget normal/empty/over-budget、RunInputBuilder rendering、proactive compactor missing + fallback pass、fallback budget fail closed、proposal failure + fallback dispatch）。pyright 和测试均通过。

residual risks（由 implementation artifact 已声明）：
- Slice C 只覆盖 proactive fallback；reactive fallback 由 Slice D 覆盖。
- proactive material source 仍沿用当前已实现的 view。
- fallback dispatch 后真实 provider 仍可能再次 overflow，由既有 reactive governance 和后续 slice 覆盖。
