# Code Review

## Scope

- Mode: current changes (deepreview — aggregate targeted re-review)
- Branch: `phase/wu-tools-cancel-01`
- Base: commit `aa10ab0f` (S4 accepted slice commit) — only unstaged workspace changes reviewed
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-rereview-ds.md`
- Review date: 2026-07-05T17:01:49+08:00
- Reviewer: AgentDS (code-review stance)
- Included scope:
  - `tests/host/test_toolruntime_executor.py` (+85 lines): `_recording_interruptible_process_handle_close` helper + `test_tool_runtime_default_factory_wires_process_capsule_interrupt_policy`
  - `tests/runtime/test_config_loader.py` (+29 lines): `test_host_runtime_process_capsule_policy_rejects_unknown_fields`
  - Fix artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-fix-codex.md`
- Excluded scope: production code (unchanged), previously reviewed S1-S4 code, existing review artifacts
- Parallel review coverage: 无。fix 仅涉及 2 个测试文件 + 1 个 artifact，单一 reviewer 完整走读

## Evidence Collected

### Independent Validation (Controller-Rerun)

```text
$ source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/host/test_toolruntime_executor.py -q
114 passed in 7.13s

$ source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

$ git diff --check
(no output — clean)
```

### Production Code Unchanged

```text
$ git diff --name-only
tests/host/test_toolruntime_executor.py
tests/runtime/test_config_loader.py
```

Zero production files modified. ✓

### Accepted Finding Closure Verification

#### MiMo-001: unknown-field rejection coverage for `process_capsule_interrupt_policy`

**Test**: `test_host_runtime_process_capsule_policy_rejects_unknown_fields` (config_loader.py:543)

**Root path trace**:
1. Test constructs `host_runtime.json` fixture via `_host_runtime_config_record(include_process_capsule_interrupt_policy=True, process_capsule_interrupt_policy={"terminate_grace_seconds": 0.35, "kill_grace_seconds": 0.75, "cleanup_deadline_seconds": 2.0})` — an unknown field `cleanup_deadline_seconds` not in the allowed set
2. `ConfigLoader(package_config_dir=package_root).load_host_runtime()` → `_parse_host_runtime_record` → `_optional_process_capsule_interrupt_policy` → `_require_exact_fields(policy, allowed={"terminate_grace_seconds", "kill_grace_seconds"}, context="host_runtime.runtimes.local.process_capsule_interrupt_policy")` (`config_loader.py:1923-1926`)
3. `_require_exact_fields` (`config_loader.py:2309-2311`): `unknown = keys - allowed` → non-empty → raises `ConfigFieldError(f"{context} has unknown fields: {sorted(unknown)}")`
4. Test asserts `pytest.raises(ConfigFieldError, match="...has unknown fields")`

**Evidence quality**: 完整闭环。测试从 JSON fixture → ConfigLoader 入口 → `_require_exact_fields` → `ConfigFieldError` 逐层验证，未跳过任何解析步骤。错误消息精确匹配生产代码的 context 字符串。✓

**Non-brittleness**: 测试依赖 `_host_runtime_config_record` fixture helper（已存在的稳定测试辅助函数），不依赖具体实现细节。若将来 `process_capsule_interrupt_policy` 的 allowed fields 集合变化，该测试的断言会自然失败（这是预期的 regression guard）。✓

#### MiMo-002: default factory wiring coverage for `process_capsule_interrupt_policy` → capsule close

**Test**: `test_tool_runtime_default_factory_wires_process_capsule_interrupt_policy` (toolruntime_executor.py:1701)

**Root path trace**:
1. Test monkeypatches `InterruptibleProcessHandle.close` → `_recording_interruptible_process_handle_close`，该 wrapper 记录 `kill_grace_seconds` 参数后调用真实 `close`
2. 构造 `ProcessCapsuleInterruptPolicy(kill_grace_seconds=_CUSTOM_PROCESS_CLOSE_GRACE_SECONDS)` where `_CUSTOM_PROCESS_CLOSE_GRACE_SECONDS = 0.73`（与默认值 0.2 明确区分）
3. 通过 `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(ToolRuntimeBuildRequest(process_capsule_interrupt_policy=policy))` 走完整 factory 路径
4. 执行 process-backed tool（`ProcessBackedToolExecutionCapability` → `_RecordingProcessTargetFactory`）
5. 工具完成后 factory 关闭进程 capsule，触发 `InterruptibleProcessHandle.close(kill_grace_seconds=...)`
6. 断言 `_RECORDED_PROCESS_HANDLE_CLOSE_KILL_GRACES == [_CUSTOM_PROCESS_CLOSE_GRACE_SECONDS]`

**Wiring chain covered**:
```
ToolRuntimeBuildRequest.process_capsule_interrupt_policy
  → DefaultToolRuntimeFactory.create_tool_runtime
    → DeclaredToolExecutionCapsuleFactory.__init__ (stores policy)
      → DeclaredToolExecutionCapsuleFactory.create_capsule
        → _declared_capsule_for_execution
          → ProcessBackedToolExecutionCapsule (receives policy)
            → capsule close
              → InterruptibleProcessHandle.close(kill_grace_seconds=0.73)
```

**Evidence quality**: 完整闭环。测试从 `ToolRuntimeBuildRequest`（Host 公共入口）→ `DefaultToolRuntimeFactory`（生产 factory）→ 真实 capsule 构造 → 进程 close 全程验证。使用 monkeypatch 记录实际参数值而非 mock 整个 close 方法，保留了进程生命周期的真实行为。✓

**Non-brittleness**: 测试依赖 `ProcessCapsuleInterruptPolicy`（Host public typed dataclass）、`ToolRuntimeBuildRequest`（Host public request）、`DefaultToolRuntimeFactory`（Host public factory）这些稳定公共接口。`InterruptibleProcessHandle.close` 的签名（`kill_grace_seconds: float`）是 runtime public API 的一部分。monkeypatch wrapper 委托到真实 `close`，不修改进程行为。`_RECORDED_PROCESS_HANDLE_CLOSE_KILL_GRACES` 在测试开始时 `.clear()`，不跨测试泄漏状态。使用区分度足够的值 `0.73`（≠ 默认 0.2）。✓

**Not merely duplicating direct capsule construction**: 测试走 `DefaultToolRuntimeFactory` + `ProcessBackedToolExecutionCapability` + `_RecordingProcessTargetFactory`，即完整的 Host capsule 装配路径。与已有的 `test_tool_runtime_process_backed_capsule_close_uses_custom_kill_grace`（使用 `ProcessBackedToolExecutionCapsule(...)` 直接构造）不同，该测试证明 policy 通过 factory wiring 到达 capsule，而非仅在直接构造时生效。✓

### Fix Artifact Accuracy

`docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-fix-codex.md` 的声明与代码证据一致：

- "added unknown-field rejection coverage" — 代码证据已确认 ✓
- "added default factory wiring coverage" — 代码证据已确认 ✓
- "no production code changes" — `git diff --name-only` 确认仅 2 个测试文件 ✓
- "114 passed" — 独立重跑确认 ✓
- "pyright 0" — 独立重跑确认 ✓
- "git diff --check passed" — 独立重跑确认 ✓
- Rejected findings remain no-current-fix — 已确认无一例外 ✓
- tests/README "no update needed" — 已确认无新 fixture category/marker/rule ✓

## Findings

未发现实质性问题。

两个 accepted findings（MiMo-001、MiMo-002）均已通过针对性测试关闭。测试覆盖完整 root path，非脆弱性测试，非直接 capsule 构造重复。无生产代码变更。Fix artifact 声明准确。验证矩阵完整且通过。

## Open Questions

无。

## Residual Risk

- 与 aggregate review 相同的 residual risk 保持不变：live Chromium cleanup 环境依赖、Web cold-start performance-only、AAPL XBRL fixture 未来可能需要 taxonomy 文件扩展。本次 fix 未引入新 risk。

## Conclusion

**PASS**

两项 accepted aggregate review findings 均已关闭。新测试覆盖完整 root path（ConfigLoader 入口 → `_require_exact_fields` 拒绝未知字段；`DefaultToolRuntimeFactory` → capsule close 使用自定义 policy），非 brittle 且非重复覆盖。无生产代码变更。验证通过（114 passed, pyright 0 errors）。
