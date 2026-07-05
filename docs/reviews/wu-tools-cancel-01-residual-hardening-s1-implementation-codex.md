# WU-TOOLS-CANCEL-01 Residual Hardening S1 Implementation - AgentCodex

## Gate / Scope

- Work unit: `WU-TOOLS-CANCEL-01 residual hardening reopen`
- Gate: implementation
- Slice: S1 `Process Envelope Contract And Cleanup Policy`
- Agent: AgentCodex
- Artifact path: `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-implementation-codex.md`
- Scope boundary: 只实现 S1；未做 S2A / S2B / S3 / S4，未 review，未 commit，未 push，未 mark PR ready。

## 改动摘要

- 在 `dayu.contracts.tool_execution` 新增 process-backed 工具子进程 envelope 常量、构造 helper、parser 与解析结果封闭联合；Host 不再维护 envelope 字段名与 status 私有副本。
- Host process envelope parser 改为消费 contracts parser，并将 failed envelope 的可选结构化 `hint` 映射到 `ToolResultFailure.hint`；缺省 hint 仍合法，不支持旧字段 alias。
- 新增 `ProcessCapsuleInterruptPolicy`，作为 process-backed capsule terminate / kill cleanup grace 的唯一 typed 默认真源，并通过 `HostToolingOptions -> ToolRuntimeBuildRequest -> DefaultToolRuntimeFactory -> DeclaredToolExecutionCapsuleFactory -> _declared_capsule_for_execution -> ProcessBackedToolExecutionCapsule` 传递。
- Implementation-fix 更新：`ProcessCapsuleInterruptPolicy` 的 0.2 / 0.2 默认值已提升为 `dayu.host.tooling` 内的私有命名默认常量；`dayu.config.host_runtime.json` 不写同值配置，避免形成第二个生产默认真源。
- 删除 active `dayu.host.tool_runtime` 路径中的 `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` / `_PROCESS_CAPSULE_KILL_GRACE_SECONDS` 硬编码常量。
- `ConfigLoader` 新增可选 `host_runtime.runtimes.<id>.process_capsule_interrupt_policy` typed config，显式配置时拒绝 bool、负数、NaN、inf、-inf；字段缺省时由 Host typed policy 默认值决定。
- Implementation-fix 更新：`tests/runtime/test_config_loader.py` 直接覆盖该 optional config block，包括 packaged / minimal config 缺省为 `None`、合法 block 解析、两个 grace 字段的 bool / negative / NaN / inf / -inf fail-fast。
- Service assembly 将 host runtime overlay 映射进 `HostToolingOptions.process_capsule_interrupt_policy`。
- 底层 `InterruptibleProcessHandle.terminate/kill` grace validation 同步拒绝 bool、负数、NaN、inf、-inf。
- Code-review fix 更新：
  - F01：`InterruptibleProcessHandle.close()` 新增可选 `kill_grace_seconds` keyword，使用 runtime-local 命名默认 `_DEFAULT_CLOSE_KILL_GRACE_SECONDS`，并复用 `_validate_grace_seconds`；`ProcessBackedToolExecutionCapsule.close()` 显式传入 `ProcessCapsuleInterruptPolicy.kill_grace_seconds`。
  - F02：Host 层新增 failed process envelope 非字符串 `hint` 用例，断言映射为 `process_backed_tool_malformed_envelope`。
- 更新 Host / Config / Tests README，以及 contracts / host 包根导出白名单测试。

## 测试结果

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_tooling_options.py tests/host/test_public_open_host_options.py tests/service/test_host_assembly.py tests/runtime/test_interruptible_process.py -q`
  - 结果：`147 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/contracts/test_package_exports.py tests/host/test_package_exports.py -q`
  - 结果：`17 passed`
- Implementation-fix 验证：
  - `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/host/test_tooling_options.py tests/service/test_host_assembly.py -q`
  - 结果：`127 passed, 3 warnings`
  - `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_public_open_host_options.py tests/runtime/test_interruptible_process.py tests/contracts/test_package_exports.py tests/host/test_package_exports.py -q`
  - 结果：`90 passed`
- Code-review fix 验证：
  - `source .venv/bin/activate && pytest tests/runtime/test_interruptible_process.py tests/host/test_toolruntime_executor.py tests/host/test_tooling_options.py tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q`
  - 结果：`194 passed, 3 warnings`
  - `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/contracts/test_package_exports.py tests/host/test_package_exports.py -q`
  - 结果：`25 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无 whitespace error。
- grep 验证：
  - `rg -n "_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS|_PROCESS_CAPSULE_KILL_GRACE_SECONDS" dayu/host/tool_runtime.py`
  - 结果：无命中；测试中也有同等断言。
  - `rg -n "process_capsule_interrupt_policy|terminate_grace_seconds|kill_grace_seconds|0\\.2" dayu/config/host_runtime.json dayu/host/tooling.py`
  - 结果：`dayu/config/host_runtime.json` 不含 process capsule policy block；process capsule 的 `0.2` 默认只出现在 `dayu.host.tooling` 的命名默认常量中。`host_runtime.json` 中的 `dispatch_poll_interval_seconds: 0.2` 是无关 Host dispatch poll 配置。
  - `rg -n "self\\.kill\\(grace_seconds=0\\.2|_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS|_PROCESS_CAPSULE_KILL_GRACE_SECONDS" dayu/runtime/interruptible_process.py dayu/host/tool_runtime.py`
  - 结果：无命中。`dayu.runtime.interruptible_process` 保留 runtime-local `_DEFAULT_CLOSE_KILL_GRACE_SECONDS`，供 direct runtime users 的 close 默认路径使用；Host process capsule close 覆盖传入 Host policy 值。

## 剩余风险

- covered by later approved slice: 具体 Doc / Fins / Web 工具仍未迁移到 contracts envelope helper；按计划留给 S3。
- covered by later approved slice: process group / nested child cleanup primitive 与 Playwright cleanup smoke 未实现；按计划留给 S2A / S2B。
- covered by later approved slice: Fins AAPL XBRL process-backed fixture breadth 未实现；按计划留给 S3。
- fixed in current slice: Host parser 的 structured hint 支持、cleanup policy typed wiring、config overlay 到 HostToolingOptions、旧 ToolRuntime grace 常量移除均已完成并有测试覆盖。
- fixed in current slice: Code-review F01 / F02 均已修复；close 路径使用 Host process capsule policy 的 kill grace，非字符串 hint 在 Host 层有 malformed 回归测试。

## Completion Status

S1 implementation complete. Next entry point per approved plan: code review for S1, unless controller explicitly directs another gate.
