# WU-TOOLS-CANCEL-01 Residual Hardening S1 Code Review - AgentDS

## Scope

- Mode: current changes (S1 implementation only)
- Branch: `phase/wu-tools-cancel-01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-code-review-ds.md`
- Included scope: S1 implementation per plan slice — process-backed envelope contract, Host parser switching, ProcessCapsuleInterruptPolicy, config loader/service assembly mapping, runtime grace validation, related README/tests/artifact.
- Excluded scope: S2A (process group cleanup), S2B (Playwright cleanup smoke), S3 (tool migration + AAPL XBRL fixture), S4 (docs/control state final validation), and any S2/S3 tool-level changes to Doc/Fins/Web tools.
- Parallel review coverage: 无（单 reviewer 逐文件走读）。

## Review Method Summary

从五个真源文档出发，沿以下链路逐行走读：

1. **Contract ownership**：`dayu/contracts/tool_execution.py` → `dayu/contracts/__init__.py` 导出白名单。
2. **Parser behavior**：`parse_process_tool_envelope` → `_tool_outcome_from_process_envelope` → `_malformed_process_envelope_outcome` / `_unsupported_process_envelope_outcome`。
3. **Parameter effectiveness**：`host_runtime.json` → `ProcessCapsuleInterruptPolicyConfig` → `HostRuntimeProfileConfig` → `_tooling_options_from_discovery` → `_process_capsule_interrupt_policy_from_config` → `HostToolingOptions.process_capsule_interrupt_policy` → `ToolRuntimeBuildRequest` → `DefaultToolRuntimeFactory.create_tool_runtime` → `DeclaredToolExecutionCapsuleFactory` → `_declared_capsule_for_execution` → `ProcessBackedToolExecutionCapsule(interrupt_policy=...)` → `self._handle.terminate(grace_seconds=...)` / `self._handle.kill(grace_seconds=...)`。
4. **Config behavior**：`_load_layered_config_file` workspace overlay → `_parse_host_runtime_profile` → `_optional_process_capsule_interrupt_policy` → `_require_non_negative_finite_float_field`。
5. **Runtime grace validation**：`InterruptibleProcessHandle.terminate/kill` → `_validate_grace_seconds`。
6. **Architecture**：runtime import 检查、Host concrete tool import 检查、LLM-facing schema 排除 execution capability。
7. **Tests**：envelope 状态覆盖、policy invalid input 覆盖、config loader 缺省/合法/非法覆盖、package exports 白名单覆盖、旧常量移除断言。

每个关键分支均沿真实代码路径走读，不基于猜测或间接迹象。

## Findings

### 01-未修复-低-`InterruptibleProcessHandle.close()` 使用硬编码 `grace_seconds=0.2` 而非 Host policy 值

- **入口/函数**: `ProcessBackedToolExecutionCapsule.close()` → `InterruptibleProcessHandle.close()`
- **文件(行号)**: `dayu/runtime/interruptible_process.py:252`（`await self.kill(grace_seconds=0.2)`）
- **输入场景**: 任何 process-backed capsule 的 close 路径（成功、失败、取消、timeout 后均会触发）。
- **实际分支**: `InterruptibleProcessHandle.close()` 在进程仍存活时执行 `self.kill(grace_seconds=0.2)`。
- **预期行为**: S1 已将 governed terminate/kill cleanup grace 提升为 `ProcessCapsuleInterruptPolicy` 的 typed 默认值（`0.2`/`0.2`），Host 层面的 capsule.terminate() 和 capsule.kill() 均使用 policy 值。close() 作为 best-effort 清理，可使用合理默认值，但值应与 policy 默认值保持语义一致，避免形成两个独立真源。
- **实际行为**: `close()` 路径的 kill grace 是 runtime 层硬编码 `0.2`，与 Host 层的 `ProcessCapsuleInterruptPolicy.kill_grace_seconds` 默认值无引用关系。若将来 policy 默认值调整为 `0.5`，close() 路径仍使用 `0.2`。
- **直接证据**: 
  - `dayu/runtime/interruptible_process.py:249-256`：close() 直接 hardcode `grace_seconds=0.2`。
  - `dayu/host/tool_runtime.py:1870-1876`：`ProcessBackedToolExecutionCapsule.close()` 仅委托 `self._handle.close()`，不使用 `self._interrupt_policy.kill_grace_seconds`。
  - `dayu/host/tooling.py:28-29`：`_DEFAULT_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` 和 `_DEFAULT_PROCESS_CAPSULE_KILL_GRACE_SECONDS` 是 Host 层默认常量。
- **影响**: close() 是 best-effort 清理（docstring 明确说明"调用方不应把这个结果解释为业务事实"），实际影响极低。但两处独立默认值增加了维护负担——修改 Host policy 默认值时需同步修改 runtime close()，否则形成语义漂移。
- **建议改法和验证点**: 
  - 方案 A（推荐）：在 `ProcessBackedToolExecutionCapsule.close()` 中覆盖行为，显式调用 `self._handle.kill(grace_seconds=self._interrupt_policy.kill_grace_seconds)` 后再执行 handle.close() 的其他清理（关闭 result_queue 等），使 close() 路径的 kill grace 与 policy 一致。
  - 方案 B：保持现状但添加注释说明 runtime close() 的 `0.2` 是独立于 Host policy 的 best-effort 默认值，并记录在 S4 README 中。
  - 验证点：确认 `ProcessBackedToolExecutionCapsule.close()` 的 kill grace 值来自 policy 或明确文档说明独立原因。
- **修复风险（低）**: 方案 A 仅影响 capsule.close() 的 kill grace 等待时间，不改变 governed terminate/kill 路径（已正确使用 policy 值），不引入新状态或并发问题。
- **严重程度（低）**: close() 是 best-effort 清理，且当前两个值恰好相同（均为 `0.2`），行为无实际差异。

## Open Questions

无。

## Residual Risk

- 按计划 S2A/S2B 未实现：process group / nested child cleanup 尚未落地，Playwright 清理 smoke 缺失——当前 `InterruptibleProcessHandle` 仅能清理直接子进程，不保证清理嵌套子进程。
- 按计划 S3 未实现：Doc/Fins/Web 具体工具尚未迁移到 contracts envelope helper，仍使用各自私有的 `_DOC_PROCESS_*` / `_FINS_PROCESS_*` / `_WEB_PROCESS_*` 常量。Host parser 已正确支持 hint，但工具侧尚未产生 hint。
- S1 未覆盖的测试面：
  - `InterruptibleProcessHandle.close()` 中 hardcoded `0.2` 未在测试中显式断言（当前测试不区分 close() 路径和 governed kill 路径的 grace 值）。
  - `process_tool_completed_envelope` / `process_tool_failed_envelope` 构造 helper 的单元测试缺失（当前通过集成测试间接覆盖）。
  - `_require_non_negative_finite_number` 与 `_validate_grace_seconds` 虽然校验逻辑相同，但无测试证明两者拒绝相同的非法值集合（当前各有独立测试覆盖）。

## Conclusion

**PASS**

S1 实现正确地完成了 plan 中定义的所有目标：envelope contract 落在 `dayu.contracts`、Host parser 通过 contracts parser 消费并正确映射 hint、ProcessCapsuleInterruptPolicy 沿完整链路到达 capsule terminate/kill、config loader 正确处理缺失/合法/非法 policy block、runtime grace validation 与 Host policy validation 约束一致、架构约束满足（runtime 无 Host/Engine import，Host 无 concrete tool import）、LLM-facing schema 不透出 execution capability。旧 ToolRuntime grace 常量已从 active 路径移除并有无常量残留的 grep 级测试保护。

唯一 finding（01）为低严重度维护性建议，不阻塞 merge。
