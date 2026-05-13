# Host Phase 1 Plan Review Controller Adjudication

## Work Gate

plan review controller adjudication

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

## Reviewed Artifacts

- Plan: `docs/host/phase1-public-contract-runtime-plan.md`
- AgentMiMo plan review: `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-mimo-20260513.md`
- AgentDS plan review: `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-ds-20260513.md`

## Summary

两份 plan review 均判断 Phase 1 plan handoff-ready 且 code-generation-ready，无 blocking finding。所有 findings 都是 plan 澄清项，但均有助于减少 implementation agent 的现场猜测，因此 controller 全部裁决为 accepted，并要求在进入 plan re-review 前修复。

## Controller Decisions

### M1: `LaneClaimToken` async method shape 未显式标注

- Source: AgentMiMo Finding 1。
- Decision: accepted。
- Rationale: design truth 要求 `refresh()` / `release()` 为 awaitable；plan public shape 应与 design 保持一致。
- Required fix: 在 plan 的 `LaneClaimToken` shape 中写成 `async def refresh(self) -> None` 和 `async def release(self) -> None`。

### M2: SQLite WAL mode 未在 plan 中显式要求

- Source: AgentMiMo Finding 2。
- Decision: accepted。
- Rationale: cross-process SQLite coordinator 依赖多进程读写稳定性；WAL 是 runtime lane DB 的明确实现要求，不应让 implementation agent 自行决定。
- Required fix: 在 coordinator / DB implementation decisions 中要求初始化 runtime lane DB 时设置 `PRAGMA journal_mode=WAL`，并说明该 WAL 只属于 runtime lane DB，不影响 Host durable store。

### M3: `dayu/runtime/__init__.py` docstring 更新未纳入 docs decision

- Source: AgentMiMo Finding 3。
- Decision: accepted。
- Rationale: Phase 1 新增 runtime lane / filelock，runtime package docstring 应同步当前已实现的层中立能力。
- Required fix: 在 allowed files 和 documentation update decision 中明确允许并要求最小更新 `dayu/runtime/__init__.py` docstring，但不得 re-export lane / filelock 符号。

### M4: `tests/runtime/test_import_boundary.py` 新增断言内容不够具体

- Source: AgentMiMo Finding 4。
- Decision: accepted。
- Rationale: import boundary 是 Phase 1 的关键防线，plan 应明确新增断言，避免只把文件列在 allowed files。
- Required fix: 在 Slice 2 / Slice 3 tests 中明确现有 runtime import boundary 扫描会覆盖新增 `lane.py` / `filelock.py`，并新增第三方 `filelock` 只允许出现在 `dayu.runtime.filelock` 的断言。

### D1: acquire stale-cleanup + count + insert 事务边界未明确为同一事务

- Source: AgentDS Finding 1。
- Decision: accepted。
- Rationale: cross-process capacity invariant 的根本正确性依赖 stale cleanup、active count 与 insert 在单个 SQLite transaction 内完成。
- Required fix: 在 claim / release semantics 中明确 acquire 成功路径的 stale cleanup、active count 和 insert 必须在同一个 SQLite transaction 内完成。

### D2: multi-process test DB path 传递方式不够明确

- Source: AgentDS Finding 2。
- Decision: accepted。
- Rationale: 多进程测试必须让父进程和子进程共享同一个 lane DB path；否则 implementation agent 会在 fixture / subprocess 设计上猜测。
- Required fix: 在 Slice 2 multi-process test instructions 中明确父进程用 `tmp_path` 或 `tempfile` 创建 DB path，并通过 subprocess CLI 参数或环境变量传给子进程。

### D3: `LaneController.open(owner=None)` auto-generation 逻辑未收敛

- Source: AgentDS Finding 3。
- Decision: accepted。
- Rationale: owner identity 虽然只用于 runtime cleanup / diagnostics，但多进程测试和 claim ownership 需要稳定的默认生成规则。
- Required fix: 在 lane implementation decisions 中明确 `owner=None` 时使用 `secrets.token_hex(8)` 生成 `owner_id`，`os.getpid()` 生成 `pid`，`process_start_token=None`；调用方可显式覆盖。

### D4: `LaneAcquireOutcome` 未显式标注 TypeAlias

- Source: AgentDS Finding 4。
- Decision: accepted。
- Rationale: public API 应明确 union alias，不应被实现成 wrapper dataclass。
- Required fix: 在 public API shape / Slice 2 implementation instructions 中明确 `LaneAcquireOutcome` 是 `typing.TypeAlias`，定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`。

## Deferred / Rejected Findings

无。

## Next Gate

进入 plan fix。Fix agent 只修 controller-accepted findings，不得修改生产代码，不得进入 implementation。

## Artifact Path

`docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-controller-adjudication-20260513.md`
