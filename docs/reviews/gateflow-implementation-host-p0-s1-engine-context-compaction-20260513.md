# Gateflow Implementation — Host P0 S1 Engine Context Compaction

- Work gate: `implementation`
- Work unit: Host Phase 0 / P0 - Engine Context Compaction Event 语义前置
- Assigned slice: `P0-S1 engine-contract-unknown-budget`
- Approved plan path: `docs/host/phase0-engine-context-compaction-plan.md`
- Accepted plan commit: `866f6f5`
- Artifact path: `docs/reviews/gateflow-implementation-host-p0-s1-engine-context-compaction-20260513.md`

## Assigned Scope

Allowed files/modules used:

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/agent.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/runners/openai/test_http_error_event.py`

Explicit non-goals honored:

- 未修改 Host implementation code。
- 未执行 P0-S2 文档同步；未修改 README、`docs/engine/design.md`、`docs/host/design.md` 或 `docs/host/implementation-control.md`。
- 未把 proactive context governance 放进 Engine。
- 未让 Engine compact、retry、估算 provider-aware budget 或新增 tokenizer。
- 未新增兼容 wrapper / facade / re-export。
- 未把 required contract facts 放进 metadata。

注意：工作区已有 controller 更新的 `docs/host/implementation-control.md` dirty 状态，本 slice 未修改、revert、stage 或格式化该文件。

## Changed Files

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/agent.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `docs/reviews/gateflow-implementation-host-p0-s1-engine-context-compaction-20260513.md`

## Implemented Plan Items

- `ContextCompactionRequestedData.budget_state` 改为 `ContextBudgetSnapshot | None`，字段仍必填且无默认值。
- `ContextCompactionRequestedData` 中文 docstring 已说明 `None` 表示 provider overflow 边界预算未知 / 未上报。
- `ContextBudgetSnapshot` 中文 docstring 删除 `0/0/0` 占位语义，改为真实、可解释 snapshot；不承载 unknown marker，不负责预算计算。
- `dayu/engine/agent.py` context overflow 分支改为 `budget_state=None`。
- 保留 `reason`、`provider_request_id`、`iteration_completed`、recoverable `run_failed(context_compaction_required)` 语义。
- Contract tests 覆盖 `budget_state=None` 合法，以及 `ContextBudgetSnapshot(1000, 500, 1500)` 真实 snapshot 合法；没有把 `ContextBudgetSnapshot(0, 0, 0)` 做成类型级非法。
- Agent context overflow 测试新增 `compact_event.data.budget_state is None` 断言，并保留 event ordering、`provider_request_id`、recoverable terminal 断言。
- Runner HTTP context overflow event-path 测试新增：HTTP 400 context overflow body 产出 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`，保留 `provider_request_id`，并以 `RunnerDoneData(FinishReason.ERROR)` 收口。

未实现项：

- 无。P0-S2 文档同步按 plan 属于后续 slice，当前 slice 未执行。

## Validation Commands And Results

```bash
source .venv/bin/activate && pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase2.py::test_context_overflow_http_error_maps_to_compaction_required_fact tests/engine/runners/openai/test_http_error_event.py::test_http_context_overflow_maps_to_context_length_exceeded -q
```

Result: passed, `13 passed in 0.21s`.

```bash
source .venv/bin/activate && pyright
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

```bash
rg -n "ContextBudgetSnapshot\\(|prompt_tokens=0|completion_tokens=0|total_tokens=0|0/0/0|占位快照" dayu tests docs README.md
```

Result: completed with matches requiring classification.

Sentinel / multiline check classification:

- Production code under `dayu/`: no old unknown-budget sentinel construction remains. `dayu/engine/agent.py` now passes `budget_state=None`.
- Current tests: only the intended real snapshot coverage in `tests/engine/test_engine_event_contract.py` matches `ContextBudgetSnapshot(` with `prompt_tokens=1000`, `completion_tokens=500`, `total_tokens=1500`; no current test retains old unknown-budget sentinel semantics.
- Historical review artifacts under `docs/reviews/`: expected old-text matches.
- `docs/host/phase0-engine-context-compaction-plan.md`: approved plan text intentionally describes the old sentinel as problem evidence and validation criteria.
- `docs/engine/design.md`: still contains old `0/0/0` wording; this is P0-S2 documentation sync scope, not this assigned slice.
- `docs/host/implementation-control.md`: dirty controller tracking file still contains old tracking text and new controller status; this file was explicitly out of scope for P0-S1 and was not modified.
- `README.md`: no relevant match in the command output.

## Documentation Update Decision

No documentation sync was performed. This is intentional: P0-S1 excludes README, `docs/engine/design.md`, `docs/host/design.md`, and `docs/host/implementation-control.md`. P0-S2 should perform the required documentation and tracking sync after P0-S1 is accepted.

## Plan Gaps Or Controller Decisions Needed

None for P0-S1. Implementation did not require Host estimator, tokenizer, compact retry, Host state transition, or breaking public exports beyond this slice.

## Residual Risks And Uncovered Areas

- Fixed in current slice: Engine overflow event no longer uses `ContextBudgetSnapshot(0, 0, 0)` as unknown budget; contract and event-path tests cover the new semantics.
- Accepted as covered by later slice: `docs/engine/design.md`, `dayu/engine/README.md`, `dayu/README.md`, and tracking copy in `docs/host/implementation-control.md` still need P0-S2 sync.
- Assigned to later phase: Host EngineEvent ingest validation for `budget_state=None` remains Phase 5 responsibility.
- Assigned to later phase: Host Context Governance semantic interpretation, estimator / policy, before / after budget refs, and compact / recovery decision remain Phase 10 responsibility.
- Deferred capability: provider-specific tokenizer adapter remains a later Host capability, outside P0-S1.

## Completion Signal

P0-S1 implementation is complete:

- Required code changes are implemented.
- Required tests and pyright passed.
- Sentinel / multiline check was run and classified.
- No stop condition was hit.

P0-S2 can start after the P0-S1 review loop reaches the controller-approved handoff point. There is no technical blocker from this implementation.

## Stop Condition Status

No stop condition hit.

