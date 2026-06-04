# WU-CM-01 Slice D Code Review - Controller Adjudication

## 裁决

- Gate: WU-CM-01 Slice D code review
- Verdict: pass
- Next gate: accepted slice commit

Controller 接受 Slice D implementation。AgentMiMo 与 AgentDS 均裁决 pass，无 blocking finding。Slice D 只修改 public smoke 脚本、根 README、`test_purge_session.py` vNext fixture 与 implementation / review artifacts，未扩大到生产 Host / Runtime / Service 代码。

## Findings 裁决

### F-01 `_compact_pressure_reserve_tokens` 分支当前返回相同值

- 来源：MiMo F-01 / DS Finding 1。
- 裁决：rejected-with-reason。

这是 smoke 脚本 pressure 策略的可读性问题，不影响当前 1M profile smoke 覆盖。场景 smoke 的 reserve 调整已通过真实命令验证，并仍保留 context pressure 覆盖。当前不为低价值 cleanup 进入 fix gate。

### F-02 `_resolve_workspace_root` 在三个 smoke 脚本中重复

- 来源：MiMo F-02 / DS Finding 2。
- 裁决：rejected-with-reason。

三个脚本是 `utils/` 下自包含 public smoke，prefix 常量不同；保持局部 helper 可读且不引入新的 utils 共享模块依赖。当前重复不构成 correctness 或 maintainability blocker。

## Accepted Verification

- Fresh workspace 默认行为正确：未显式传 `--workspace-root` 时生成 `workspace/tmp/<prefix>-<id>`；显式传入时保持路径语义。
- `--reuse-session` 语义未破坏；复用 durable session 需要显式 `--workspace-root` 和 `--reuse-session`。
- Fresh workspace 只作用于 smoke 默认行为，不改变 production path 的 old schema fail-closed 语义。
- `test_purge_session.py` 的 seed item kind 迁移为 `selected_recent_window`，与 vNext durable schema CHECK 一致。
- 根 README 只同步已落地 smoke 行为，不写未来 eval / recall / User Profile 内容。
- Residual owners 与 plan 一致：Issue 80 / WU-CM-10、Issue 115 / WU-CM-11、Issue 39、后续 Context Governance tokenizer work unit、Fins integration work unit。

## Validation

Implementation artifact 记录：

- `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q` -> `64 passed, 1 skipped`
- `python utils/smoke_host_public_conversation_memory.py` -> pass
- `python utils/smoke_host_public_conversation_memory_scenarios.py` -> pass
- `python utils/smoke_host_public_multiturn.py` -> pass
- `pytest tests/host/test_purge_session.py -q` -> `28 passed`
- `pytest tests/host -q` -> `1100 passed, 1 skipped, 5 deselected`
- `python -m pyright dayu/ tests/ utils/` -> `0 errors`

Controller light checks:

- `git diff --check` -> pass
- old memory policy / snapshot terminology scan over README and changed smoke files -> no match

## Residual Risk

- Default smoke workspaces remain under `workspace/tmp/` and are intentionally not deleted by scripts; cleanup remains manual / workspace maintenance.
- Explicit `--workspace-root` pointing at an old schema DB will still fail closed. This is expected under the fresh schema constraint and is not a compatibility bug.
