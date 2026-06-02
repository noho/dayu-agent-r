# WU-TOOL-01 Slice 4 Code/Doc Review

- **Gate**: code review
- **Reviewer**: DeepSeek-v4-pro
- **Approved plan**: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- **Implementation artifact**: `docs/reviews/wu-tool-01-implementation-slice4-codex-20260601.md`
- **Review scope**: Slice 4 未提交 diff（tests/host/test_toolruntime_duplicate_governance.py, dayu/host/README.md, tests/README.md, docs/reviews/wu-tool-01-implementation-slice4-codex-20260601.md）
- **Date**: 2026-06-01

## Findings

### Finding 1 — [PASS] cross-Attempt regression 测试真实有效

**文件**: `tests/host/test_toolruntime_duplicate_governance.py:759-801`

`test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs`（原 `test_duplicate_key_includes_attempt_id` 增强后重命名）：

- 两个独立 ToolRuntime handle，相同 `run_id`（`_RUN_ID`），不同 `attempt_id`（`"attempt-duplicate"` vs `"attempt-other"`），相同 tool/args。
- REUSE policy 设定下，两个 Attempt 的首调用均得到 `DuplicateDecisionKind.ALLOW`。
- 断言 `reuse_prior_event_refs == ()`，确认不复用旧 Attempt refs。
- 断言 `duplicate_key` 不同（因 `attempt_id` 已纳入 key hash），确认 scope 隔离。
- 断言 `duplicate_scope.attempt_id` 分别等于各自 Attempt id。
- 两个 `_CountingTool.call_count == 1`，确认均为 fresh execution。

**结论**: 测试真实证明了同 run_id 不同 Attempt 同 tool/args 为 fresh request，不复用旧 Attempt refs。非假阳性。

### Finding 2 — [PASS] fresh ToolRuntime handle / worker restart non-durable 测试真实有效

**文件**: `tests/host/test_toolruntime_duplicate_governance.py:804-838`

`test_fresh_toolruntime_handle_same_attempt_is_in_memory_non_durable_restart_behavior`:

- 两个独立 ToolRuntime handle，相同 `attempt_id`（`_ATTEMPT_ID`），相同 tool/args。
- 第一个 handle 接受 first tool 结果后，第二个 handle（fresh `InMemoryAttemptDuplicateGovernance`）不继承旧内存索引。
- 断言 `duplicate_key` 相等（相同 attempt_id + tool/args），但第二个 handle 无 prior accepted entry。
- `restarted_tool.call_count == 1`，`duplicate_decision == ALLOW`，`reuse_prior_event_refs == ()`。
- 测试名和 docstring 明确标注 "该行为不是 correctness 前提"。

**结论**: 测试真实证明了新 ToolRuntime handle 不继承旧内存 duplicate index，并正确地将此行为标记为 in-memory non-durable 边界，而非 correctness 前提。非假阳性。

### Finding 3 — [PASS] dayu/host/README.md 更新符合 AGENTS.md 职责

**文件**: `dayu/host/README.md:231-233, 239`

变更内容：
- 新增 2 行描述 duplicate governance 为 attempt-local in-memory 治理能力，明确新 Attempt / worker restart / Host restart 不继承旧内存索引。
- 新增 1 行描述 `HostToolingOptions.duplicate_governance_policy` 为 construction-time typed 配置入口。
- 将 "run-scoped duplicate governance registry" 替换为 "attempt-local duplicate governance state"。

审查结论：
- 内容限于 Host 稳定边界和 construction 契约，不写过程状态或未来设计。
- 不包含实现细节。
- 不越界描述 Service/Engine/UI 行为。
- 符合 `CLAUDE.md` 中 dayu/host/README.md 的职责定义。

### Finding 4 — [PASS] tests/README.md 更新符合 AGENTS.md 职责

**文件**: `tests/README.md:55, 130`

变更内容：
- 命令示例中补充了 `test_tool_trace_projection.py`、`test_dispatch_scheduler.py`、`test_tooling_options.py`。
- 将 "Run-scoped duplicate registry 的同 Run 共享 / 跨 Run 隔离 / scheduler 生命周期清理" 替换为 "attempt-scoped duplicate key / in-flight owner-waiter 串行化 / cross-Attempt fresh request / worker restart in-memory non-durable behavior / trace scope projection"。

审查结论：
- 内容限于当前 `tests/` 已存在的测试覆盖事实。
- 不写用户手册、设计文档、未落地测试体系或时间敏感记录。
- 符合 `CLAUDE.md` 中 tests/README.md 的职责定义。

### Finding 5 — [PASS] 旧术语清理完整

`rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host tests/host dayu/host/README.md tests/README.md` 结果中：

| 匹配位置 | 内容 | 判定 |
|---|---|---|
| `dayu/host/README.md` | `run-scoped truncation cursor` | 允许（truncation cursor 语义） |
| `dayu/host/README.md` | `run-local token`（compaction 上下文） | 允许（reactive compaction cancellation token） |
| `dayu/host/tool_runtime.py` | `run-scoped truncation` / `TruncationManager` | 允许（truncation 语义） |
| `dayu/host/api.py` | `run-scoped truncation manager` | 允许（truncation 语义） |
| `tests/README.md` | `run-scoped truncation cursor / scope token` | 允许（truncation 语义） |
| `tests/host/test_local_proxy_engine_ingest.py` | `run_id="run-local"` | 允许（测试数据 id，非 governance 术语） |

**结论**: duplicate governance 相关的 production/test/doc 中无残留 run-scoped registry / run-local duplicate registry / RunScoped / RunLocal / 同 Run 说法。所有匹配均为 truncation cursor / token 或 compaction cancellation token 或测试数据 id，属于 plan 明确允许保留的无关术语。

### Finding 6 — [PASS] HostToolingOptions.duplicate_governance_policy 可配置说明已覆盖

**生产代码验证**:
- `dayu/host/tooling.py:87-88`: `HostToolingOptions.duplicate_governance_policy: DuplicateGovernancePolicy`，typed field with `default_factory=DuplicateGovernancePolicy`。
- `dayu/host/tool_duplicate_governance.py:140-158`: `DuplicateGovernancePolicy` 包含 `default_duplicate_decision`、`decisions_by_tool_name`、`justification_argument_names_by_tool_name`、`messages: DuplicateGovernanceMessages`。
- `dayu/host/tool_duplicate_governance.py:62-137`: `DuplicateGovernanceMessages` 包含 `allow`、`reuse`、`hint`、`require_justification`、`hard_stop`、`attempt_scope_diagnostic`、`prior_accept_missing` 七个 typed field + `message_for(kind)` 方法。
- `dayu/host/dispatch.py:2692-2693`: 生产 dispatch 路径 `tooling_options.duplicate_governance_policy` 传入 `ToolRuntimeBuildRequest`。
- `tests/host/test_tooling_options.py:226-328`: 覆盖 default policy、独立 messages 实例、custom messages、custom justification、validation 错误路径。

**README 覆盖**:
- `dayu/host/README.md:232`: 明确 "默认动作、按工具覆盖动作、模型可见治理文案与 justification 参数名" 均通过 `HostToolingOptions.duplicate_governance_policy` 以 typed `DuplicateGovernancePolicy` 配置。

**结论**: policy / prompt / justification 可配置说明完整，未遗漏。

### Finding 7 — [NON-BLOCKING] 旧 test_duplicate_key_includes_attempt_id 被重命名合并

**文件**: `tests/host/test_toolruntime_duplicate_governance.py:759`

Slice 1 plan 要求添加 `test_duplicate_key_includes_attempt_id`。Slice 4 将其重命名为 `test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs` 并增强了行为断言。

**分析**: 原测试主要断言 duplicate key 因 attempt_id 不同而不同（实现细节）；新测试名称和断言聚焦于 cross-Attempt fresh request 行为（`tool_fact_kind`、`duplicate_decision`、`reuse_prior_event_refs`）。增强后的测试覆盖了原测试的所有断言（duplicate_key 不等、duplicate_scope.attempt_id 匹配）并增加了行为级验证。

**判定**: 非阻塞。重命名和增强是合理的，行为测试优于实现细节测试。但 plan 中"Add test_duplicate_key_includes_attempt_id"的原始意图（验证 key 包含 attempt_id）仍由增强后测试中的 `duplicate_key` 不相等断言覆盖。

### Finding 8 — [NON-BLOCKING] implementation report 对未修改文件的引用不够精确

**文件**: `docs/reviews/wu-tool-01-implementation-slice4-codex-20260601.md:20`

实现报告称 "保留并依赖 `tests/host/test_dispatch_scheduler.py::test_reactive_recovery_uses_fresh_duplicate_governance_attempt`"。经验证，该测试确实存在于 `test_dispatch_scheduler.py:4079`，且未在 Slice 4 diff 中修改（属前序 Slice 产物）。

**判定**: 非阻塞。引用正确，但作为 Slice 4 实现报告，花一句话说明该测试由 Slice 2/3 引入会更好。

## Open Questions

无。所有 review points 均有明确结论。

## Verification

| 验证项 | 命令/方法 | 结果 |
|---|---|---|
| 测试套件 | `pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_dispatch_scheduler.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_tooling_options.py -q` | **123 passed** |
| 类型检查 | `pyright` | **0 errors, 0 warnings, 0 informations** |
| 术语 grep | `rg "run-local\|run-scoped\|RunScoped\|RunLocal\|同 Run" dayu/host tests/host dayu/host/README.md tests/README.md` | 所有匹配均为允许的 truncation/compaction/test-data 上下文 |
| 生产代码未修改 | `git diff HEAD -- dayu/host/tool_runtime.py dayu/host/dispatch.py dayu/host/tooling.py dayu/host/tool_duplicate_governance.py dayu/host/tool_trace.py` | 无输出，Slice 4 未修改生产文件 |
| Any/object/无类型签名 | pyright + 人工审查 diff | 无 |
| 兼容路径 | 人工审查 diff | 无兼容 re-export/wrapper/facade |
| schema/public contract 越界 | 人工审查 diff | 无 |

### 额外验证

对 `dayu/host/tool_duplicate_governance.py` 完整阅读确认：
- `DuplicateGovernanceScope` 包含 `kind: Literal["attempt"]` + `attempt_id: str`（plan §6 要求）。
- `DuplicateGovernancePolicy` 包含 `default_duplicate_decision`、`decisions_by_tool_name`、`justification_argument_names_by_tool_name`、`messages`（plan §6 要求）。
- `DuplicateGovernanceMessages` 七个 typed field 均有 default 值，`__post_init__` 拒绝空/空白字符串（plan §6 要求）。
- `DuplicateDecision` 包含 `scope`、`reason_code`、`durable_missing_reason`（plan §6 要求）。
- `DuplicateGovernancePort` 为 async Protocol（plan §6 要求）。
- `duplicate_governance_key()` 包含 scope（kind + attempt_id）（plan §7.2 要求）。
- `InMemoryAttemptDuplicateGovernance` 实现 owner/waiter 状态机（plan §7.6 要求）。
- `__all__` 导出列表完整，无兼容 re-export。

## Conclusion

Slice 4 的 regression matrix、README sync 和 type check 实现正确、完整、无阻塞问题。

- **cross-Attempt regression**（`test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs`）真实证明同 run_id 不同 Attempt 同 tool/args 按 fresh request 执行，不复用旧 Attempt refs。
- **worker/Host restart non-durable test**（`test_fresh_toolruntime_handle_same_attempt_is_in_memory_non_durable_restart_behavior`）真实证明 fresh ToolRuntime handle 不继承内存 duplicate index，且正确标注为 "不是 correctness 前提"。
- **README 更新**：`dayu/host/README.md` 和 `tests/README.md` 均符合各自 AGENTS.md 职责，不写过程状态或未来设计。
- **术语清理**：duplicate governance 无残留 run-scoped registry / run-local / RunScoped / RunLocal / 同 Run 说法。
- **policy 可配置说明**：`HostToolingOptions.duplicate_governance_policy` 的 typed policy/prompt/justification 配置已在 README 中说明。
- **测试验证**：123 passed，pyright 0 errors，无假阳性，无 Any/object/无类型签名，无兼容路径，无 schema/public contract 越界。

### Remaining blocking findings: 0

两个 non-blocking 发现（Finding 7: 旧测试名被合并，Finding 8: implementation report 引用精度）不影响 correctness、stability 或 maintainability，无需阻塞 Slice 4 验收。
