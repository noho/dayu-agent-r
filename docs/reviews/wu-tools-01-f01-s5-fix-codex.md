# WU-TOOLS-01-F01 Slice S5 Fix - Codex

## Gate Metadata

- Gate: fix.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S5 - Fins Wait Adapter And Service Assembly Wiring`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s5-fix-codex.md`.
- Scope guard: no commit, no push, no review gate.

## Fix Scope

本 fix 只处理 Controller accepted findings。未修改 Host / Engine contract、Fins production mapping、Service provider detection semantics、production poller loop、默认 `tool_discovery.json` 或真实网络 adapter。

## Changed Files

- `tests/fins/test_fins_ingestion_tools.py`
- `tests/service/test_host_assembly.py`
- `docs/reviews/wu-tools-01-f01-s5-fix-codex.md`

## Accepted Findings Fix Status

### F01-S5-001

状态：已修复。

修复：在 `test_fins_wait_poll_adapter_maps_terminal_and_missing_jobs` 中新增 `RUNNING` 与 `CANCELLING` job records，并直接断言二者 `poll_wait(...)` 返回 `WaitPollNotReady`。

### F01-S5-002

状态：已修复。

修复：新增 `test_tooling_options_without_fins_awaiting_providers_has_no_wait_adapter_registry`，使用普通非 Fins provider config 与普通工具装配 `HostToolingOptions`，断言工具正常保留且 `wait_adapter_registry is None`。

### F01-S5-003

状态：已修复。

修复：新增 `test_fins_wait_poll_adapter_maps_corrupt_job_evidence_to_lost`，写入损坏 job evidence 文件后调用 `poll_wait(...)`，断言返回 `WaitPollLost` 且 outcome 为 `ResolveWaitLostOutcome`，证明 corrupt evidence 不走 adapter error。

### F01-S5-004

状态：已修复。

修复：新增三个 `abandon_wait` defensive tests：

- `test_fins_wait_poll_adapter_abandon_without_external_job_ref_is_noop`：`external_job_ref=None` 不抛错，不修改已有 Fins job。
- `test_fins_wait_poll_adapter_abandon_missing_job_evidence_is_noop`：missing job evidence 不抛错。
- `test_fins_wait_poll_adapter_abandon_corrupt_job_evidence_is_noop`：corrupt job evidence 不抛错，且 evidence 文件仍存在。

这些测试证明 adapter 只请求取消，不删除业务数据或 Host wait records。

### F01-S5-005

状态：已修复。

修复：新增两个 Service assembly fail-fast tests：

- `test_fins_awaiting_provider_missing_workspace_root_fails_before_open_host`：缺失 `config.workspace_root` 时抛 bounded `ValueError`。
- `test_fins_awaiting_provider_relative_workspace_root_fails_before_open_host`：相对 `workspace_root` 时抛 bounded `ValueError`。

两条路径都通过 `_tooling_options_from_discovery(...)` 触发，发生在 `open_host` 前。

## Validation

已运行并通过：

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/fins/test_fins_ingestion_tools.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py
```

结果：`56 passed, 3 warnings`。warnings 为第三方 `edgar` deprecation。

```bash
source .venv/bin/activate && pytest tests/service -q
```

结果：`37 passed, 3 warnings`。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过。

## README Decision

No-update decision：本 fix 只补 review 要求的测试覆盖，没有改变生产行为、公共接口、配置入口、用户命令、架构边界或测试分层说明。S5 implementation gate 已同步相关 README，本 fix 不需要再更新 README。

## Residual / Blocker

- Residual risk: none introduced by this fix.
- Blocker: none.

## Completion Status

All five Controller accepted findings are fixed.
