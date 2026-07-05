# Re-review — WU-TOOLS-CANCEL-01 Residual Hardening Aggregate Fixes

## Scope

- Mode: current changes (targeted re-review of aggregate fixes)
- Branch: `phase/wu-tools-cancel-01`
- Base: workspace vs HEAD
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-rereview-mimo.md`
- Reviewer: AgentMiMo
- Review date: 2026-07-05T17:02:37
- Fix artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-fix-codex.md`

### Changed files

| File | Lines added | Nature |
|------|-------------|--------|
| `tests/runtime/test_config_loader.py` | +29 | New test for unknown field rejection |
| `tests/host/test_toolruntime_executor.py` | +85 | New test for factory wiring path |

**Production code changed:** 无。仅测试文件。

### Accepted findings being verified

| Finding | Description | Fix claimed |
|---------|-------------|-------------|
| MiMo-001 LOW | Config `process_capsule_interrupt_policy` 未知字段无专项测试 | 新增 `test_host_runtime_process_capsule_policy_rejects_unknown_fields` |
| MiMo-002 LOW | Factory wiring path 无端到端测试 | 新增 `test_tool_runtime_default_factory_wires_process_capsule_interrupt_policy` |

---

## Verification: MiMo-001 — Config unknown field rejection

### Test analysis

`test_host_runtime_process_capsule_policy_rejects_unknown_fields` (新增，`test_config_loader.py` line 543+):

- 构造包含三个字段的 policy 块：`terminate_grace_seconds=0.35`、`kill_grace_seconds=0.75`、`cleanup_deadline_seconds=2.0`（未知字段）
- 调用 `ConfigLoader.load_host_runtime()`
- 断言 `ConfigFieldError` 且消息匹配 `"has unknown fields"`

**路径覆盖验证：** 测试直接触发 `_optional_process_capsule_interrupt_policy` → `_require_exact_fields` (line 1923-1926) → `ConfigFieldError`。这是真实的配置解析路径，不是绕过路径。

**结论：** MiMo-001 已关闭。测试覆盖了真实路径，断言具体，非脆弱。

---

## Verification: MiMo-002 — Factory wiring path

### Test analysis

`test_tool_runtime_default_factory_wires_process_capsule_interrupt_policy` (新增，`test_toolruntime_executor.py` line 1701+):

**wiring 路径追踪：**

1. 构造 `ProcessCapsuleInterruptPolicy(kill_grace_seconds=0.73)` (自定义值)
2. 传入 `ToolRuntimeBuildRequest(process_capsule_interrupt_policy=policy)`
3. 调用 `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(request)`
4. 这触发 `tool_runtime.py:4010-4016` → `DeclaredToolExecutionCapsuleFactory(effective_bundle, request.process_capsule_interrupt_policy)`
5. 执行 tool call → `_declared_capsule_for_execution` → `ProcessBackedToolExecutionCapsule(target, interrupt_policy=process_capsule_interrupt_policy)`
6. Process 正常完成后 capsule close → `InterruptibleProcessHandle.close(kill_grace_seconds=self._interrupt_policy.kill_grace_seconds)`

**拦截机制：** monkeypatch `InterruptibleProcessHandle.close` 为 `_recording_interruptible_process_handle_close`，记录传入的 `kill_grace_seconds` 后继续执行真实 close。

**关键断言：**
- `_RECORDED_PROCESS_HANDLE_CLOSE_KILL_GRACES == [0.73]` — 证明自定义 policy 值通过完整 factory 路径到达了 capsule close

**是否只是重复直接构造？** 否。此测试通过 `DefaultToolRuntimeFactory` → `DeclaredToolExecutionCapsuleFactory` 路径，不直接构造 `ProcessBackedToolExecutionCapsule`。与 line 1785 的旧测试（直接构造 capsule）形成互补。

**是否脆弱？** 不脆弱。monkeypatch 目标是公共方法 `InterruptibleProcessHandle.close`，不是内部实现细节。录制列表在测试开始时 clear，避免跨测试污染。

**结论：** MiMo-002 已关闭。测试覆盖了真实的 factory wiring 路径（`ToolRuntimeBuildRequest` → `DefaultToolRuntimeFactory` → `DeclaredToolExecutionCapsuleFactory` → `ProcessBackedToolExecutionCapsule` → close），断言精确。

---

## Validation verification

| Check | Claimed | Verified |
|-------|---------|----------|
| `pytest tests/runtime/test_config_loader.py tests/host/test_toolruntime_executor.py -q` | 114 passed | 114 passed ✓ |
| `pyright` | 0 errors | 0 errors ✓ |
| `git diff --check` | passed | passed ✓ |
| Production code changed | none | only `tests/` files modified ✓ |

---

## Findings

未发现实质性问题。

---

## Open Questions

- 无。

## Residual Risk

- 无新增。MiMo-003（hint 一致性）和其余 rejected findings 保持 no-current-fix 状态，不影响 gate 结论。
