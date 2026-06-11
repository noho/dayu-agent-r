# WU-PROJ-01 Plan Re-Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: plan re-review controller adjudication
- 日期: 2026-06-11
- Plan artifact: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- Plan fix artifact: `docs/reviews/wu-proj-01-plan-fix-codex.md`
- AgentMiMo re-review artifact: `docs/reviews/wu-proj-01-plan-rereview-mimo.md`
- AgentDS re-review artifact: `docs/reviews/wu-proj-01-plan-rereview-ds.md`
- Controller verdict: accepted plan; proceed to accepted plan commit

## Re-Review Verdicts

| Lane | Verdict | Controller decision |
|---|---|---|
| AgentMiMo | pass | accepted |
| AgentDS | pass | accepted |

两路 re-review 均确认 AgentCodex plan fix 已修复 controller accepted findings，修正后的 plan 为 code-generation-ready。无 blocking open questions。

## Findings Adjudication

### Prior Accepted Findings

AgentMiMo 与 AgentDS 均确认 controller adjudication 中 12 条 accepted findings 已修复。Controller 接受该结论，不要求额外 plan fix gate。

### New Finding

| Finding | 裁决 | 理由 / Owner |
|---|---|---|
| DS NF1: Validation Commands 缺少 `tests/host/test_memory_repair.py` | deferred-with-owner | 该 finding 为低严重度，DS 明确不影响 code-generation-readiness，且 Slice 3 已把 memory repair 测试列为 implementation 测试范围。Owner 为 WU-PROJ-01 implementation gate：implementation dispatch 必须在 validation 中加入 `python -m pytest tests/host/test_memory_repair.py`；若新增 `tests/host/test_memory_projection_repair.py`，也必须运行对应测试。 |

## Residual Risks

| ID | 状态 | Owner / Destination | 处理方式 |
|---|---|---|---|
| WU-PROJ-01-RR1 | deferred-with-owner | WU-PROJ-01 implementation Slice 2 / later reactive hardening owner | Reactive compact 只做 shared previous-view helper 的最小适配；若需要 multi-pass 或大规模重写，停止并转后续 owner。 |
| WU-PROJ-01-RR2 | deferred-with-owner | WU-PROJ-01 implementation Slice 1 | EventLog-backed builder 必须用 latest compact boundary、current input cursor 和 caps 限定读取范围。 |
| WU-PROJ-01-RR3 | deferred-with-owner | WU-PROJ-01 implementation tests | 若现有 proactive compact fixture 不足，新增最小 Host durable fixture。 |
| WU-PROJ-01-RR4 | deferred-with-owner | WU-PROJ-01 implementation Slice 3 | `budget is None` 只能用于 explicitly reviewed close-only / test-only path，不能进入 command / admission hot path。 |
| WU-PROJ-01-RR5 | deferred-with-owner | WU-PROJ-01 implementation failure diagnostics | 确保 budget exhausted 不被包装成 worker startup timeout；若需新增 HostEvent 或 durable schema，按 stop condition 回报总控。 |

## 下一步

- 进入 accepted plan commit gate。
- Commit scope 仅包含 WU-PROJ-01 goal/design/control/plan/review artifacts。
- Commit 后更新 `docs/host/issues-implementation-control.md` 的 accepted plan commit hash，并将 next entry point 指向 WU-PROJ-01 implementation gate via AgentCodex。
