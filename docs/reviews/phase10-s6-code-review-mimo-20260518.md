# Phase 10 Slice 6 Code Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-18
Scope: Phase 10 Slice 6 — Production Composition Wiring, Multi-turn Integration, Docs Sync

## Verdict

**PASS**

## Summary

Slice 6 在 `HostCommandHandleOptions` 增加 `context_window_size` / `reserved_output_tokens` / 可选 hard threshold / minimum protection tokens 四个 typed 字段，`__post_init__` 期校验可组成合法 `ContextBudgetPolicy`；新增 `compose_host_local_execution_options(...)` 从 command options 归一化 `ContextBudgetPolicy` 并注入 compact artifact root，保持 memory projection policy 独立。测试验证 budget 字段不在 per-run request / metadata 中，composition helper 正确 wiring，非法值被拒绝。全部 259 个测试通过，pyright 零错误。

## Verification

| 检查项 | 结果 |
| --- | --- |
| `pytest tests/host/test_public_contracts.py -q` | 39 passed, 0 failed |
| `pytest tests/host/ (all P10 validation suite) -q` | 259 passed, 0 failed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed |

## Adversarial Check Matrix

### 1. `compose_host_local_execution_options` 是 production wiring 还是孤立 helper？

| 维度 | 证据 | 结论 |
| --- | --- | --- |
| 函数签名正确 | 接收 `HostCommandHandleOptions`，返回 `HostLocalExecutionOptions \| None` | **PASS** |
| 数据流正确 | `context_window_size` + `reserved_output_tokens` → `default_context_budget_policy(...)` → `ContextBudgetPolicy` → 覆盖 `local_execution.context_budget_policy` | **PASS** |
| artifact root wiring | `options.artifact_root` → `compact_artifact_root`，`options.create_parent_dirs` → `compact_artifact_create_parent_dirs` | **PASS** |
| memory policy 隔离 | `replace(...)` 只覆盖 context policy / artifact root，`memory_projection_policy` 保持原值 | **PASS** |
| 未被 `create_host_command_handle` 调用 | `create_host_command_handle` 仍拒绝 `local_execution` 非空；composition helper 是独立 public function | **设计正确** |
| 为什么设计正确 | `create_host_command_handle` 是同步 factory，不隐藏 async scheduler lifecycle。composition root 需先调用 `compose_host_local_execution_options` 拿到 typed options，再显式 `await HostDispatchScheduler.open(...)` 装配。这保持了 async lifecycle 的显式边界。 | **PASS** |
| 测试覆盖 | `test_compose_host_local_execution_options_wires_context_policy` 验证字段 wiring；`test_compose_host_local_execution_options_without_local_execution_is_none` 验证 None 分支 | **PASS** |

**结论：** `compose_host_local_execution_options` 是 production composition wiring 的正确形态。它不被 `create_host_command_handle` 内部调用是设计意图：同步 command handle 与 async scheduler 分离。composition root 必须显式编排两者。

### 2. 默认值是否削弱"显式输入"语义？

| 维度 | 证据 | 结论 |
| --- | --- | --- |
| 默认值定义 | `HOST_CONTEXT_WINDOW_SIZE_DEFAULT = 8192`, `HOST_RESERVED_OUTPUT_TOKENS_DEFAULT = 1024` | — |
| `__post_init__` 校验 | `_validate_command_context_budget_fields(self)` 用默认值构造 policy，验证通过 | **PASS** |
| 一致性 | 其他选项字段也有默认值：`sqlite_busy_timeout_seconds`、`payload_inline_threshold_bytes` 等。pattern 一致。 | **PASS** |
| 隐患评估 | composition root 使用默认值时，policy 合法但可能与实际 context window 不匹配。但这与 `sqlite_busy_timeout_seconds` 默认 5.0 可能与生产不匹配是同类风险，属于 options 配置职责。 | **低风险** |
| `HOST_*_DEFAULT` 是否在 `__all__` | 不在。这与其他 `HOST_EVENT_STREAM_*` 常量（在 `__all__` 中）不一致，但不影响功能。 | **Info** |

**结论：** 默认值是可接受的 options pattern，不削弱"显式输入"语义。composition root 若需定制，显式传入即可。`__post_init__` 校验确保默认值始终合法。

### 3. `context_compactor` 是否缺失？

| 维度 | 证据 | 结论 |
| --- | --- | --- |
| Plan 要求 | "context_compactor: ContextCompactor"、"compact artifact store root via existing durable artifact root" | — |
| 当前实现 | `compose_host_local_execution_options` 使用 `replace(options.local_execution, ...)`，保留 caller 提供的 `context_compactor` | **正确** |
| 不默认注入 | composition helper 不注入 `FakeContextCompactor` 或默认 compactor | **正确** |
| 无 compactor 时行为 | S4/S5 已处理：`_compact_reactive_recovery` 检查 `compactor is None` → fail closed | **PASS** |
| `compact_artifact_root` | 从 `options.artifact_root` 注入 | **PASS** |
| `context_budget_policy` | 从 command options 构造注入 | **PASS** |

**结论：** 这是正确的显式注入边界。composition helper 负责 policy 和 artifact root（这些必须从 command options 派生），compactor 由 caller 在 `local_execution` 中显式提供。不注入 fake compactor 符合"production path 不隐式使用 fake"的设计约束。这不是 plan gap，而是 plan 中"context budget provider ... otherwise prefer passing the typed ContextBudgetPolicy value"的正确解读。

### 4. 是否必须补 aggregate E2E test？

| 维度 | 证据 | 结论 |
| --- | --- | --- |
| Plan 要求 | "End-to-end local fake worker scenario: Run 1 creates raw turns...Later Run over soft threshold triggers proactive compact...Subsequent Run messages contain pinned state..." | — |
| 现有覆盖 | `test_dispatch_scheduler.py`: proactive soft threshold compact + reactive recovery (S4/S5) | **PASS** |
| | `test_memory_projection.py`: CONTEXT_COMPACTED → memory projection → pinned state / episode summary (S3) | **PASS** |
| | `test_run_input_builder.py`: compacted projection → RunInputBuilder messages (S3) | **PASS** |
| | `test_phase5_local_execution_integration.py`: full scheduler + worker + Run lifecycle (S4/S5) | **PASS** |
| | `test_public_contracts.py`: composition wiring + per-run budget isolation (S6) | **PASS** |
| 单一 aggregate test | 不存在。分层 tests 组合覆盖了 plan 描述的全部路径。 | — |
| Phase 10 exit condition | "多轮会话主体路径应当具备 memory + proactive compaction + reactive recovery 的可验证闭环" | — |

**结论：** 分层测试组合已覆盖 Phase 10 exit condition 的全部可验证点。单一 aggregate test 的价值在于发现跨模块集成缺陷，但当前分层边界清晰（typed policy / event payload / projection / RunInputBuilder / scheduler），跨模块耦合风险低。不阻塞当前 slice，但建议 Phase 10 aggregate validation owner 在 public scheduler harness 上追加一个单一 multi-turn scenario 以增强回归信心。

### 5. Budget 字段是否被错误放入 per-run request / metadata？

| 维度 | 证据 | 结论 |
| --- | --- | --- |
| `StartRunRequest` 字段 | `test_context_budget_inputs_are_not_per_run_fields` 断言 `forbidden.isdisjoint(start_fields)` | **PASS** |
| `SubmitFollowupRequest` 字段 | 同上断言 `forbidden.isdisjoint(followup_fields)` | **PASS** |
| `HostMetadataEntry` 字段 | 同上断言 `forbidden.isdisjoint(metadata_fields)` | **PASS** |
| `HostLocalExecutionOptions` | `context_budget_policy` 作为 typed policy 存在，不是 per-run bag | **PASS** |
| Engine budget_state | S5 已验证不作为 Host budget truth | **PASS** |

**结论：** budget 参数只存在于 `HostCommandHandleOptions`（composition-level）和 `HostLocalExecutionOptions`（scheduler-level typed policy），不在 per-run request / metadata 中。设计正确。

### 6. 类型、docstring、README 同步

| 检查项 | 证据 | 结论 |
| --- | --- | --- |
| 新增字段类型 | `context_window_size: int`, `reserved_output_tokens: int`, `context_budget_hard_threshold_tokens: int | None`, `context_budget_minimum_protection_tokens: int | None` | **PASS** |
| `__post_init__` 校验 | `_validate_command_context_budget_fields` 调用 `default_context_budget_policy` 验证字段组合 | **PASS** |
| Docstring | `HostCommandHandleOptions` docstring 已列出四个新字段及语义 | **PASS** |
| `compose_host_local_execution_options` docstring | 描述 composition root typed wiring 边界，明确不读取 Engine/metadata/payload | **PASS** |
| `dayu/host/README.md` | 新增 context budget fields 描述、`compose_host_local_execution_options` data flow、budget/memory policy 分离 | **PASS** |
| `tests/README.md` | 新增 `test_context_compact_events.py` 运行入口，标注 `test_context_budget.py` 等覆盖类别 | **PASS** |
| `dayu/README.md` | 未更新。implementation artifact 说明未改变 UI/Service/Host/Engine 分层边界。可接受。 | **PASS** |
| pyright | 0 errors | **PASS** |
| `__all__` | `HOST_CONTEXT_WINDOW_SIZE_DEFAULT` / `HOST_RESERVED_OUTPUT_TOKENS_DEFAULT` 不在 `__all__`。与 `HOST_EVENT_STREAM_*` 常量的导出 pattern 不一致。不影响功能但影响 API 可发现性。 | **Info** |

## Findings

**无 blocking / high / medium defect。**

### Info

**I1. `HOST_CONTEXT_WINDOW_SIZE_DEFAULT` / `HOST_RESERVED_OUTPUT_TOKENS_DEFAULT` 未在 `api.py.__all__` 中导出**

- 文件: `dayu/host/api.py:49-50`, `dayu/host/api.py:2076-2141`
- 状态: 两个常量是 `HostCommandHandleOptions` 新增字段的默认值，但不在 `__all__` 中。`HOST_EVENT_STREAM_DEFAULT_LIMIT` / `HOST_EVENT_STREAM_MAX_LIMIT` 等同类常量在 `__all__` 中。
- 影响: 不影响功能。composition root 若需参考默认值，可通过 `HostCommandHandleOptions` 构造时的默认行为获取。但 API 一致性略差。
- 优先级极低，不阻塞。

## Plan Compliance

| 计划要求 | 状态 | 证据 |
| --- | --- | --- |
| `HostCommandHandleOptions.context_window_size: int` | PASS | `api.py:1173` default `HOST_CONTEXT_WINDOW_SIZE_DEFAULT` |
| `HostCommandHandleOptions.reserved_output_tokens: int` | PASS | `api.py:1174` default `HOST_RESERVED_OUTPUT_TOKENS_DEFAULT` |
| `HostCommandHandleOptions.context_budget_hard_threshold_tokens: int | None` | PASS | `api.py:1175` default `None` |
| `HostCommandHandleOptions.context_budget_minimum_protection_tokens: int | None` | PASS | `api.py:1176` default `None` |
| `HostLocalExecutionOptions.context_budget_policy: ContextBudgetPolicy` | PASS | `api.py:740` (pre-existing from S4) |
| Command handle wiring constructs ContextBudgetPolicy | PASS | `command.py:compose_host_local_execution_options` |
| Service supplies positive integers to options | PASS | `__post_init__` → `_validate_command_context_budget_fields` |
| No per-run metadata override | PASS | `test_context_budget_inputs_are_not_per_run_fields` |
| Memory projection policy separate from context policy | PASS | `compose_host_local_execution_options` 只覆盖 context policy |
| FakeContextCompactor only for tests/local dev | PASS | composition helper 不注入 fake compactor |
| `dayu/host/README.md` 更新 | PASS | context budget fields、composition data flow、policy 分离 |
| `tests/README.md` 更新 | PASS | `test_context_compact_events.py` 入口、覆盖类别标注 |
| `dayu/README.md` 仅在分层边界变化时更新 | PASS | 未改变分层边界，未更新 |
| Root `README.md` 仅在 CLI 暴露时更新 | PASS | 未暴露 CLI options，未更新 |
| Public contract tests | PASS | context budget validation、composition wiring、per-run isolation |
| End-to-end local fake worker scenario | PARTIAL | 分层 tests 组合覆盖全部路径；无单一 aggregate test（见 Finding 4 分析） |
| Reactive fake worker recovery | PASS | S5 `test_dispatch_scheduler.py` 已覆盖 |
| pyright | PASS | 0 errors |

## Residual Risks

1. **无单一 aggregate multi-turn E2E test**：plan 要求的 end-to-end scenario（Run 1 raw turns → follow-up under budget → later Run over threshold → proactive compact → subsequent Run with pinned state / summaries）由分层 tests 组合证明，但无单一 test case 串联。建议 Phase 10 aggregate validation owner 追加。
2. **`HOST_CONTEXT_WINDOW_SIZE_DEFAULT` / `HOST_RESERVED_OUTPUT_TOKENS_DEFAULT` 不在 `__all__`**：API 一致性问题，不影响功能。可在后续 API cleanup 中对齐。
3. **Production compactor adapter 未实现**：composition helper 不注入默认 compactor，未配置 compactor 时 compact 触发 fail closed。真实 production compactor adapter 归后续 composition owner。
4. **Provider-specific tokenizer / retrieval 不在范围内**：沿用 S4/S5 residual。
