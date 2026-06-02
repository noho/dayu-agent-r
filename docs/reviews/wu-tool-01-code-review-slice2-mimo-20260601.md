# WU-TOOL-01 Slice 2 Code Review

- Gate: code review
- Reviewer: MiMo
- Branch: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Implementation artifact: `docs/reviews/wu-tool-01-implementation-slice2-codex-20260601.md`
- Review scope: Slice 2 未提交改动

## Findings

### F1 — [OK] HostToolingOptions typed duplicate_governance_policy 暴露正确

- 文件: `dayu/host/tooling.py:17,87-89,101-107`
- `DuplicateGovernancePolicy` 从 `dayu.host.tool_duplicate_governance` 直接导入，不经过 `tool_runtime`，不使用 lazy import。
- `default_factory=DuplicateGovernancePolicy` 保证零配置可用。
- `__post_init__` 使用 `isinstance` 校验类型，拒绝非法对象。
- frozen dataclass + slots，符合 Host construction 输入边界契约。
- 结论: 通过，无 finding。

### F2 — [OK] dispatch 正确传入 per-Attempt policy

- 文件: `dayu/host/dispatch.py:2692-2694`
- `_run_input_builder_for_attempt` 将 `tooling_options.duplicate_governance_policy` 传入 `ToolRuntimeBuildRequest`。
- dispatch.py 无 `InMemoryRunScopedDuplicateGovernanceRegistry`、`_duplicate_governance_registry`、`clear_run`、`clear_all` 残留。
- 仅有一处 `duplicate` 引用，即 policy 传入。
- 结论: 通过，无 finding。

### F3 — [OK] reactive recovery 测试真实证明 attempt-scoped 行为

- 文件: `tests/host/test_dispatch_scheduler.py:4078-4175`
- 测试使用 `DuplicateGovernancePolicy(default_duplicate_decision=DuplicateDecisionKind.REUSE)` 配置。
- 第一个 Attempt 内：同 tool/args 执行两次，`tool.call_count == 1`，证明 duplicate reuse 生效。
- `first_event_gate` 控制 reactive recovery 时机，确保第一个 Attempt 的 duplicate 治理状态在 recovery 前已建立。
- 第二个 Attempt：`accepted_snapshots[1].attempt_id != seeded.attempt_id`，同 tool/args 执行后 `tool.call_count == 2`，证明新 Attempt 不继承旧 Attempt duplicate index。
- 测试通过 `factory.accepted_requests[0]` 和 `factory.accepted_requests[1]` 获取独立的 executor 实例，每个 executor 绑定各自的 attempt scope。
- 结论: 通过，无 finding。

### F4 — [OK] custom message / justification / validation 测试覆盖充分

- 文件: `tests/host/test_tooling_options.py:235-328`
- `test_duplicate_governance_policy_zero_config_uses_default_messages`: 零配置断言所有 7 个消息字段非空，且 `first.messages is not second.messages` 证明 `default_factory` 每次创建新实例。
- `test_host_tooling_options_accepts_custom_duplicate_messages`: 自定义 7 个消息字段后透传验证。
- `test_host_tooling_options_accepts_custom_duplicate_justification_name`: `REQUIRE_JUSTIFICATION` + 自定义参数名透传。
- `test_duplicate_governance_policy_rejects_empty_messages_and_argument_names`: 空 `reuse` 消息、空 argument name、空 tool name 均被 `ValueError` 拒绝。
- `test_host_tooling_options_rejects_invalid_duplicate_policy_type`: `cast(DuplicateGovernancePolicy, "invalid-policy")` 被 `isinstance` 拒绝。
- 签名无 `Any`/`object`/无类型参数/无类型返回值。`cast` 仅用于测试中构造非法输入，不逃避类型检查。
- 结论: 通过，无 finding。

### F5 — [OK] 无 duplicate governance run-scoped / run-local 残留

- `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host/tooling.py dayu/host/dispatch.py tests/host/test_tooling_options.py tests/host/test_dispatch_scheduler.py` — 无命中。
- `rg "_duplicate_governance_registry|clear_run|clear_all|active_run_count" dayu/host/dispatch.py tests/host/test_dispatch_scheduler.py` — 无命中。
- `rg "InMemoryRunScoped|RunScopedDuplicate|run_scoped_duplicate" dayu/host/dispatch.py tests/host/test_dispatch_scheduler.py` — 无命中。
- close lifecycle matrix (`test_dispatch_scheduler.py:241`) 已移除 "duplicate registry cleared" 文案。
- 结论: 通过，无 finding。

### F6 — [OK] 未违反 AGENTS.md

- **docstring**: `tooling.py` 中 `HostToolingOptions` 类和 `__post_init__` 均有完整中文 docstring，含参数、返回值、异常。新增 `duplicate_governance_policy` 字段在类 docstring 中有说明。
- **分层**: `tooling.py` 属于 Host construction 输入边界，`dispatch.py` 属于 Host scheduler，均在 Host 层内，无反向依赖。
- **禁止兼容 wrapper/re-export**: 无兼容 re-export；`DuplicateGovernancePolicy` 直接从 `dayu.host.tool_duplicate_governance` 导入。
- **README 决策**: implementation artifact 声明 README 同步放在 Slice 4，本 slice 不更新。符合 approved plan Slice 2 scope。
- **测试**: 70 passed，覆盖 default policy、custom message、custom justification、empty validation、invalid type、reactive recovery attempt-scoped 行为。
- **pyright**: 0 errors, 0 warnings, 0 informations。
- 结论: 通过，无 finding。

## Open Questions

无。

## Verification

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_tooling_options.py tests/host/test_dispatch_scheduler.py` | 70 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| 术语 grep (run-local/run-scoped/RunScoped/RunLocal/同 Run) | 无命中 |
| 残留 registry 引用 grep | 无命中 |
| import 来源验证 | 全部从 `dayu.host.tool_duplicate_governance` 导入 |

## Conclusion

Slice 2 实现与 approved plan 完全一致。所有 6 个审查重点均通过：

1. `HostToolingOptions` 通过 typed `duplicate_governance_policy` 暴露配置入口，从 `dayu.host.tool_duplicate_governance` 直接导入。
2. dispatch 把 `tooling_options.duplicate_governance_policy` 传入每个 per-Attempt `ToolRuntimeBuildRequest`。
3. reactive recovery 测试通过 `REUSE` policy + `tool.call_count` + `first_event_gate` 时序控制，真实证明新 Attempt 不继承旧 Attempt duplicate index。
4. custom message / justification / empty validation / invalid type 测试覆盖充分，无 `Any`/`object`/无类型签名/不合规 cast。
5. 无 duplicate governance run-scoped/run-local 兼容行为或旧术语残留。
6. 未违反 AGENTS.md。

**Remaining blocking findings: 0**
