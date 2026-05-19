# PR 62 Deepreview Controller Adjudication

## Verdict

PR 62 不直接进入 draft-PR-pass。当前进入 PR 62 review fix。

AgentMiMo verdict：PASS，blocking = 0，high = 0，medium = 3。
AgentDS verdict：PASS，blocking = 0，high = 0，medium = 2，low = 2。

Controller 裁决：P10.5 的核心 success signal 不是“测试能过”，而是普通本地多轮能力由 `open_host(options)`、public command、`watch_session_events(session_id)` 与 typed terminal `HostEvent` 证明。PR review 中发现的 public smoke 内部 durable 表查询与 `create_host_command_handle` WAITING seed 依赖，会削弱该证明，必须在 PR review fix 中收口。两个 low findings 不改变当前 production correctness，也不应在 PR gate 临时扩大 public surface，按 owner 记录为 deferred / rejected-current-fix。

## Accepted Current Fix Findings

### PR62-F1 — Public smoke uses direct SQLite `event_log` reads

来源：AgentDS medium 1，AgentMiMo medium 1 的同类证据。

裁决：接受为当前 PR review fix。

要求：

- public smoke tests 不得用直接 SQLite `event_log` 查询作为 correctness assertion。
- 优先改为通过 public `Host` handle 的 `get_run(...)`、`watch_session_events(...)` 或已有 typed public snapshot / event helper 观察状态。
- 若确实需要等待非 public-display diagnostic event 作为同步 primitive，必须集中到 `tests/host/public_smoke_support.py`，并用中文注释说明仅用于测试同步，不作为 public smoke correctness assertion；但 final answer、cancel、close、retry、replay、resolve_wait 等结果断言仍必须走 public snapshot / public HostEvent。
- 删除 public smoke 文件中重复的 `_event_type_count` / `_wait_for_event_type_count` 直连 durable 表实现。

### PR62-F2 — WAITING public smoke seeds via `create_host_command_handle`

来源：AgentDS medium 2，AgentMiMo medium 1 的同类证据。

裁决：接受为当前 PR review fix。

要求：

- `tests/host/test_public_steer.py` 与 `tests/host/test_public_resolve_wait_resume.py` 不得直接 import / 使用 `create_host_command_handle` 作为 public smoke 前置条件。
- 优先通过 `open_host(options)` + public command + mock waiting / awaiting support 产生 `WAITING` Run，再用 public `resolve_wait(...)` 或 `submit_followup(steer)` 验证后续 public path。
- 如果 implementation agent 发现当前 Host 缺少纯 public WAITING 生成路径，必须停止并说明缺口，不能用低层 handle 继续伪装 public smoke。

### PR62-F3 — Branch-level `git diff --check main...HEAD` fails on trailing whitespace in review artifacts

来源：AgentDS verification、AgentMiMo verification。

裁决：接受为当前 PR review fix。

要求：

- 清理已提交 review artifacts 中的 trailing whitespace，使 `git diff --check main...HEAD` clean。

## Rejected Or Deferred Findings

### PR62-L1 — `watch_session_events` handle close silently ends iterator

来源：AgentDS low 3。

裁决：defer，不进入当前 PR review fix。

理由：`docs/host/post-p10.md` 已允许 Host close 时已打开 iterator “结束或抛 Host lifecycle termination”。当前 silent end 不违反 P10.5 freeze；若后续要改为抛 `HostClosedError` 或 emit closed event，属于 public lifecycle ergonomics 变更，应在 Phase 11 / later public lifecycle hardening 中讨论。

### PR62-L2 — `DefaultLocalEngineWorkerFactory` not exported from package root

来源：AgentDS low 4。

裁决：rejected-current-fix / needs design discussion。

理由：将 concrete `DefaultLocalEngineWorkerFactory` 加入 `dayu.host` 包根会扩大 P10.5 public surface，且 P10.5 已冻结 `OpenHostOptions.worker_factory` 为 `LocalEngineWorkerFactory` Protocol typed construction boundary。若后续真实 Service 需要 Host-provided default worker factory helper，必须先回到 design discussion 更新 `docs/host/design.md` / `docs/host/post-p10.md`，不能在 PR gate 临时导出 concrete implementation。

### PR62-N1 — Intentional breaking public dataclass field changes

来源：AgentMiMo medium 2 / 3。

裁决：accepted-as-non-issue。

理由：`FollowupSnapshot.current_cursor -> command_watermark` 与 `SubmitFollowupRequest.input -> flat typed fields` 是 P10.5 public contract freeze 的有意变更，README 与 tests 已同步；不需要兼容 wrapper 或旧字段。

## Required Validation

PR review fix agent 必须运行：

```bash
source .venv/bin/activate && pytest tests/host/test_public_steer.py tests/host/test_public_resolve_wait_resume.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_retry_replay.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py -q
source .venv/bin/activate && pytest tests/host/test_package_exports.py -q
source .venv/bin/activate && pytest tests/host -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
git diff --check main...HEAD
```
