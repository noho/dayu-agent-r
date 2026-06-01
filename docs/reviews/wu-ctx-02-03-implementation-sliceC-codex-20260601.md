# WU-CTX-02 + WU-CTX-03 implementation Slice C artifact

## Gate / Scope

- 当前 gate：WU-CTX-02 + WU-CTX-03 implementation Slice C。
- Approved plan：`docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`。
- Accepted plan commit：`9d89db3`。
- 已有前置 slice：Slice A `2f2f22c`；Slice B `e6156de`。
- 本次只实现 proactive deterministic recent-window fallback；未启动 `$gateflow`，未进入 review、commit、push 或 PR。

## Changed Files

- `dayu/host/context_fallback.py`
- `dayu/host/run_input.py`
- `dayu/host/dispatch.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_dispatch_scheduler.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-ctx-02-03-implementation-sliceC-codex-20260601.md`

## Implemented Items

- 新增 Host 内部 `context_fallback` helper，负责 deterministic recent-window fallback selection、fallback input window digest、fallback budget re-estimate payload，以及从 failed EventLog 读取 active fallback view。
- fallback selection 不接受 public N 配置，也未新增任意 max-N 常量；选择逻辑固定 current input anchor、stable / compact represented context、`MemoryProjectionPolicy.recent_raw_turns_floor` 下限，再按 reverse chronological raw turn block order 追加，直到下一 block 会触发 hard threshold。
- fallback budget re-estimate 复用现有 `estimate_context_budget` / `BudgetEstimateInput.message_fragments`，未改估算算法，未新增 provider tokenizer，未新增 `ContextBudgetPolicy` public field。
- `RunInputBuilder` 新增内部可选 `ContextFallbackProvider`，默认 no-op；active fallback 时用同源 ordinary material blocks 过滤渲染 selected bounded view，再追加当前 input。
- `HostDispatchScheduler` 在 proactive compact failure 路径写 `CONTEXT_COMPACTION_FAILED` 后，根据 fallback budget 结果直接 governed start 或 fail closed。
- compactor missing / artifact store missing、compaction operation final failure、pre-dispatch hard threshold over-budget 都写 failed payload；预算通过时创建一次 Attempt，预算失败时零 Attempt fail closed。

## State Machine / Payload Changes

- proactive fallback dispatch：`ACCEPTED|QUEUED -> CONTEXT_COMPACTION_REQUESTED? -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED -> ATTEMPT_STARTED -> dispatch`。
- proactive fallback fail closed：`ACCEPTED|QUEUED -> CONTEXT_COMPACTION_FAILED(fallback_action=fail_closed) -> RUN_FAILED`，不创建 Attempt。
- fallback dispatch 不进入 `RECOVERING`。
- fallback 不写 `CONTEXT_COMPACTED`，不写 compact artifact，不改历史 EventLog facts。
- failed payload 的 fallback window 只包含 selected / dropped block ids、current input ref、source refs、floor、trigger、policy、cursor、raw turn count 和 blocked next block id；不包含 raw prompt 或 provider payload。

## Tests

已运行并通过：

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q
```

结果：`97 passed in 1.19s`。

新增 / 更新覆盖：

- fallback selection determinism、floor 保留、blocked next block 不越 hard budget。
- fallback budget estimate：normal、empty stable input、over-budget。
- RunInputBuilder fallback provider rendering：只包含 selected recent window / current input，不包含 dropped older raw turn。
- proactive compactor missing + fallback budget pass：创建一个 Attempt，无 `CONTEXT_COMPACTED`。
- proactive fallback budget fail：零 Attempt，Run `FAILED`，无 `CONTEXT_COMPACTED`。
- proactive compaction proposal failure：保留 rejected attempt facts，并通过 fallback dispatch。

## Pyright

已运行并通过：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

## Docs Decision

- `dayu/host/README.md` 已更新：补充 proactive deterministic recent-window fallback 的稳定语义，明确 fallback 不是 compact success、不写 `CONTEXT_COMPACTED`、不写 compact artifact、不进入 `RECOVERING`、不物化 memory stable fact、over-budget / selection / estimate failure fail closed。
- `tests/README.md` 已更新：补充 `test_run_input_builder.py` 与 `test_dispatch_scheduler.py` 对 fallback rendering、fallback dispatch / hard-budget fail closed 的覆盖说明。

## Invariants

- 未新增 Service-facing public API、request shape、durable schema 或 execution profile schema。
- 未新增 `ContextBudgetPolicy` public fallback 字段。
- 未新增 provider tokenizer。
- fallback selection / digest 完全由 committed material view、current input cursor、policy ref 和现有 budget estimator 决定。
- 若必保留集合本身超过 hard budget，fallback payload 标记 over-budget 并 fail closed，不降低 floor 偷偷 dispatch。
- fallback failed event 不作为 compact success；memory projection 仍只从 committed canonical fact 规则消费，不因 fallback failed event 生成 stable facts。

## Residual Risks

- Slice C 只实现 proactive fallback；reactive fallback recovery path 仍属于后续 Slice D。
- proactive material source 仍沿用当前已实现的 proactive ordinary material view：当前输入和 bounded accepted tool evidence；更完整的 memory raw-turn proactive material 扩展未在本 slice 内扩大。
- fallback dispatch 后真实 provider 仍可能再次 overflow；该路径由既有 reactive overflow governance 和后续 Slice D / E 覆盖。

## Stop Status

- 未触发 stop condition。
- 不需要 public request 参数让 RunInputBuilder 知道 fallback view；通过 Host 内部 EventLog failed payload provider 完成。
- 不需要新增 public policy field、provider tokenizer、durable schema 或 Service request shape。
- 未写 `CONTEXT_COMPACTED`、memory table/projection stable facts 或 compact artifact。
- proactive failure 未进入 `RECOVERING`。
