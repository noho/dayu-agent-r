# WU-TOOLS-CANCEL-01 Residual Hardening S1 Code Review - AgentMiMo

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: `HEAD`（workspace 未提交改动）
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-code-review-mimo.md`
- Included scope: S1 `Process Envelope Contract And Cleanup Policy` 的全部未提交改动：
  - `dayu/contracts/tool_execution.py`（envelope 常量、构造 helper、parser、封闭联合）
  - `dayu/contracts/__init__.py`（包导出）
  - `dayu/host/tool_runtime.py`（Host parser 切换、policy wiring、旧常量移除）
  - `dayu/host/tooling.py`（`ProcessCapsuleInterruptPolicy`、`HostToolingOptions` 扩展）
  - `dayu/host/__init__.py`（包导出）
  - `dayu/host/dispatch.py`（policy 传递到 `ToolRuntimeBuildRequest`）
  - `dayu/runtime/config_loader.py`（可选 `process_capsule_interrupt_policy` 配置解析）
  - `dayu/runtime/interruptible_process.py`（`_validate_grace_seconds` 增强）
  - `dayu/service/host_assembly.py`（config → `HostToolingOptions` 映射）
  - `dayu/config/host_runtime.json`（无 policy block，符合预期）
  - `tests/host/test_toolruntime_executor.py`（envelope 测试、hint 映射、旧常量 grep）
  - `tests/host/test_tooling_options.py`（policy validation 测试）
  - `tests/host/test_public_open_host_options.py`（`OpenHostOptions` 不暴露 policy）
  - `tests/service/test_host_assembly.py`（config overlay 测试）
  - `tests/runtime/test_interruptible_process.py`（grace validation 测试）
  - `tests/runtime/test_config_loader.py`（config block 测试）
  - `tests/contracts/test_package_exports.py`（导出白名单）
  - `tests/host/test_package_exports.py`（导出白名单）
  - `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md`（文档更新）
- Excluded scope: S2A/S2B/S2C/S3/S4 未实现的工具迁移、process-group cleanup、Playwright smoke
- Parallel review coverage: 无

## Findings

### 01-未修复-低-InterruptibleProcessHandle.close() 存在未治理的硬编码 grace

- **入口/函数**: `InterruptibleProcessHandle.close()`
- **文件(行号)**: `dayu/runtime/interruptible_process.py:252`
- **输入场景**: 任何 process-backed capsule 被显式 close 或垃圾回收时
- **实际分支**: `self._started and self._process.is_alive()` 为 `True` 时
- **预期行为**: cleanup kill 的 grace 值应与 `ProcessCapsuleInterruptPolicy` 的 `kill_grace_seconds` 默认值保持单一真源，或至少是 `dayu.runtime` 层内的命名常量
- **实际行为**: `close()` 方法直接写死 `grace_seconds=0.2` 字面量
- **直接证据**: `dayu/runtime/interruptible_process.py:252` 的 `await self.kill(grace_seconds=0.2)`。`dayu/host/tooling.py:29` 的 `_DEFAULT_PROCESS_CAPSULE_KILL_GRACE_SECONDS: Final[float] = 0.2` 是 policy 默认真源。两者当前数值相同但各自独立维护
- **影响**: 若将来 policy 默认值调整（如 S2B smoke 验证后上调），`close()` 路径的 grace 不会同步变化。`close()` 是 best-effort cleanup 路径（非 Host 治理主路径），且 `dayu.runtime` 不能 import `dayu.host.tooling`，因此风险有限
- **建议改法和验证点**: 在 `dayu.runtime.interruptible_process` 模块内新增 `_DEFAULT_CLOSE_KILL_GRACE_SECONDS: Final[float] = 0.2` 命名常量，替换 `close()` 中的裸字面量。或在 `InterruptibleProcessHandle.__init__` 接受可选 `close_grace_seconds` 参数。验证点：`close()` 仍使用同一数值，只是来源变为命名常量
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未通过-低-Host 层非字符串 hint 映射缺少独立测试

- **入口/函数**: `_tool_outcome_from_process_envelope()`
- **文件(行号)**: `dayu/host/tool_runtime.py:6568-6590`
- **输入场景**: process-backed 子进程返回 failed envelope 且 `hint` 字段为非字符串类型（如整数）
- **实际分支**: `parse_process_tool_envelope()` 返回 `ProcessToolMalformedEnvelope`，Host 将其映射为 `_malformed_process_envelope_outcome()`
- **预期行为**: Host parser 对非字符串 hint 应 fail-closed，返回 malformed 工具失败 outcome
- **实际行为**: contracts parser `parse_process_tool_envelope()` 正确拒绝非字符串 hint（`dayu/contracts/tool_execution.py:165-167`），Host 通过 `_tool_outcome_from_process_envelope` 的 `isinstance(parsed, ProcessToolMalformedEnvelope)` 分支正确映射
- **直接证据**: contracts 层已有测试覆盖非字符串 hint（`parse_process_tool_envelope` 返回 `ProcessToolMalformedEnvelope`）。Host 层的 `test_toolruntime_executor.py` 覆盖了 malformed envelope 的通用路径，但没有专门测试 "failed status + non-string hint" 这一特定 malformed 场景在 Host 中的 outcome 映射
- **影响**: 当前行为正确（contracts parser 拦截 → Host malformed outcome），但 Host 层缺少对此特定 malformed 场景的回归保护。如果 contracts parser 的 hint 校验被意外移除，Host 层测试不会捕获
- **建议改法和验证点**: 在 `tests/host/test_toolruntime_executor.py` 新增测试用例，直接传入 `{"status": "failed", "error_type": "err", "message": "msg", "hint": 123}` 给 `_tool_outcome_from_process_envelope()`，断言返回 `ToolFailedOutcome` 且 `error == "process_backed_tool_malformed_envelope"`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- S1 不包含具体工具（Doc/Fins/Web）迁移到 contracts envelope helper，旧 `_DOC_PROCESS_*` / `_FINS_PROCESS_*` / `_WEB_PROCESS_*` 常量仍在各自工具文件中。按计划留给 S3。
- S1 不包含 process-group cleanup primitive 和 Playwright cleanup smoke。按计划留给 S2A/S2B。
- `InterruptibleProcessHandle.close()` 的 `0.2` grace 与 `ProcessCapsuleInterruptPolicy` 默认值 `0.2` 数值相同但独立维护，存在未来分叉风险（见 Finding 01）。

## Review Checklist

### 1. 层级 / 反向依赖

- `dayu.contracts.tool_execution` 不 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` ✅
- `dayu.runtime.interruptible_process` 不 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` ✅
- `dayu.host.tool_runtime` 不 import `dayu.tools` / `dayu.fins` ✅
- envelope contract 定义在 `dayu.contracts`，Host 消费 parser，具体工具消费构造 helper ✅

### 2. hint 结构化映射

- `process_tool_failed_envelope(hint=None)` 不写入 hint 字段 ✅
- `process_tool_failed_envelope(hint="   ")` 不写入 hint 字段 ✅
- `parse_process_tool_envelope` 对非字符串 hint 返回 `ProcessToolMalformedEnvelope` ✅
- Host `_tool_outcome_from_process_envelope` 将 `ProcessToolFailedEnvelope.hint` 映射到 `ToolResultFailure.hint` ✅
- reserved status（`awaiting` / `cancelled` / `timeout` / `host_cancelled`）fail-closed ✅
- unknown status fail-closed ✅

### 3. cleanup grace policy 生效链

完整链路已验证（7 跳，4 文件）：
```
ConfigLoader (ProcessCapsuleInterruptPolicyConfig)
  → Service assembly (_process_capsule_interrupt_policy_from_config)
    → HostToolingOptions.process_capsule_interrupt_policy
      → dispatch.py (ToolRuntimeBuildRequest.process_capsule_interrupt_policy)
        → DefaultToolRuntimeFactory (DeclaredToolExecutionCapsuleFactory.__init__)
          → _declared_capsule_for_execution (ProcessBackedToolExecutionCapsule.__init__)
            → terminate() / kill() 使用 self._interrupt_policy.terminate_grace_seconds / kill_grace_seconds
```
✅ 每跳正确传递 policy 值。

### 4. config overlay 缺省行为

- `host_runtime.json` 不含 `process_capsule_interrupt_policy` block ✅
- `ConfigLoader` 返回 `HostRuntimeProfileConfig.process_capsule_interrupt_policy = None` ✅
- `Service assembly` 的 `_process_capsule_interrupt_policy_from_config(None)` 返回 `ProcessCapsuleInterruptPolicy()` 默认值 ✅
- 不复制默认真源到 config 文件 ✅

### 5. runtime grace validation

- `_validate_grace_seconds` 拒绝 `bool` → `TypeError` ✅
- `_validate_grace_seconds` 拒绝非 `int | float` → `TypeError` ✅
- `_validate_grace_seconds` 拒绝 `NaN` → `ValueError` ✅
- `_validate_grace_seconds` 拒绝 `+inf` → `ValueError` ✅
- `_validate_grace_seconds` 拒绝 `-inf` → `ValueError` ✅
- `_validate_grace_seconds` 拒绝负数 → `ValueError` ✅
- `ProcessCapsuleInterruptPolicy.__post_init__` 同样拒绝上述所有非法值 ✅
- `ConfigLoader._require_non_negative_finite_float_field` 同样拒绝上述所有非法值 ✅

### 6. README 更新边界

- `dayu/host/README.md`: 更新 `OpenHostOptions` 描述和 `HostToolingOptions` 公共契约列表，新增 `ProcessCapsuleInterruptPolicy`。符合 Host README 职责 ✅
- `dayu/config/README.md`: 新增 `process_capsule_interrupt_policy` 配置说明。符合 Config README 职责 ✅
- `tests/README.md`: 更新 config loader 和 host assembly 测试覆盖描述。符合 Tests README 职责 ✅
- `dayu/README.md`: 无变更。S1 不改变跨包契约边界文本，无需更新 ✅

### 7. 测试覆盖

- completed envelope roundtrip ✅
- failed envelope with hint ✅
- failed envelope without hint（`hint is None`）✅
- malformed envelope（非 object、缺 status、非字符串 status）✅
- reserved status fail-closed ✅
- unknown status fail-closed ✅
- `ProcessCapsuleInterruptPolicy` 默认值 ✅
- `ProcessCapsuleInterruptPolicy` 自定义值 ✅
- `ProcessCapsuleInterruptPolicy` 拒绝 bool / negative / NaN / inf / -inf ✅
- `HostToolingOptions` 拒绝非法 policy 类型 ✅
- `OpenHostOptions` 不暴露 `process_capsule_interrupt_policy` 直接字段 ✅
- config loader 缺省 block → `None` ✅
- config loader 合法 block → parsed config ✅
- config loader 拒绝 bool / negative / NaN / inf / -inf ✅
- service assembly config overlay 到 `HostToolingOptions` ✅
- `InterruptibleProcessHandle` terminate / kill 拒绝非法 grace ✅
- 旧常量 `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` / `_PROCESS_CAPSULE_KILL_GRACE_SECONDS` 不在 `tool_runtime.py` 中 ✅
- 包导出白名单（contracts / host）✅
- 测试未为实现削弱断言 ✅

## Conclusion

**PASS_WITH_FINDINGS**

S1 implementation 正确完成了计划要求的所有改动：envelope contract 单一真源、Host parser 切换到 contracts parser、hint 结构化映射、cleanup grace policy typed wiring（7 跳完整链路）、config overlay、runtime grace validation、旧常量移除、README 更新。架构边界完整保持，fail-closed 行为正确，测试覆盖真实行为和失败路径。

两个低严重程度 finding：
1. `InterruptibleProcessHandle.close()` 的 `0.2` grace 是裸字面量，与 policy 默认值独立维护（低风险，因 `close()` 是 best-effort 路径且 `dayu.runtime` 不能 import policy）。
2. Host 层缺少非字符串 hint 的专门 malformed 测试（低风险，因 contracts parser 已拦截且 Host malformed 通用路径已覆盖）。
