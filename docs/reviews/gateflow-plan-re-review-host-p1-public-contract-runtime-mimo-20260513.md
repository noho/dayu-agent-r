# Host Phase 1 Plan Re-Review: 公共契约与 runtime 基础设施

## Review Gate

plan re-review

## Reviewer

AgentMiMo

## Reviewed Target

- Plan: `docs/host/phase1-public-contract-runtime-plan.md`
- Fix artifact: `docs/reviews/gateflow-plan-fix-host-p1-public-contract-runtime-codex-20260513.md`
- Controller adjudication: `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-controller-adjudication-20260513.md`
- Original review (MiMo): `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-mimo-20260513.md`
- Original review (DS): `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-ds-20260513.md`
- Design truth: `docs/host/design.md`
- Implementation control: `docs/host/implementation-control.md`
- Project term truth: `dayu/README.md`

## Review Scope

只复核 controller 已接受并由 AgentCodex 修复的 8 个 findings (M1-M4, D1-D4)。不扩大 scope 到新的完整 plan review。

## Per-Finding Fix Verification

### M1: `LaneClaimToken` async method shape 未显式标注

- **Status**: fixed
- **Evidence**:
  - Plan line 291-292: `async def refresh(self) -> None` 和 `async def release(self) -> None` — 已显式标注为 async。
  - Design truth `design.md:116-117`: `refresh() -> Awaitable[None]` 和 `release() -> Awaitable[None]` — plan shape 与 design 一致。
  - Plan line 374: "`LaneClaimToken.release()` 异步、幂等" — 文字描述与 shape 一致。
- **Verdict**: 修复完整，public shape 和 implementation instructions 均已对齐。

### M2: SQLite WAL mode 未在 plan 中显式要求

- **Status**: fixed
- **Evidence**:
  - Plan line 337: "DB 初始化必须设置 `PRAGMA journal_mode=WAL`。该 WAL 设置只属于 runtime lane DB，不改变、不约束 Host durable store 的 SQLite policy。"
  - Plan line 542 (Slice 2 instructions): "DB 初始化设置 `PRAGMA journal_mode=WAL`，且 WAL 只属于 runtime lane DB。"
  - Implementation-control truth (`implementation-control.md`) 中 WAL 要求已通过 plan 的显式声明覆盖。
- **Verdict**: 修复完整。Coordinator / DB decisions 和 Slice 2 instructions 两处均已要求 WAL，并明确 WAL 只属于 runtime lane DB。

### M3: `dayu/runtime/__init__.py` docstring 更新未纳入 docs decision

- **Status**: fixed
- **Evidence**:
  - Plan line 53 (Allowed files): "最小修改 `dayu/runtime/__init__.py` docstring，说明 Phase 1 新增的层中立 lane / filelock runtime 能力；不得从包根 re-export `lane` / `filelock` 符号。"
  - Plan line 75: "`dayu/runtime/__init__.py` 只做包 docstring 最小更新，不作为 README；不得新增 package-root export。"
  - Plan line 747 (Documentation Update Decision): "`dayu/runtime/__init__.py`: 需要最小更新 docstring。原因：新增 `dayu.runtime.lane` 和 `dayu.runtime.filelock` 层中立 runtime 能力；该更新只描述 package-level 当前能力，不得 re-export lane / filelock 符号。"
- **Verdict**: 修复完整。allowed files、scope boundary 和 documentation update decision 三处均已覆盖，且 re-export 禁令明确。

### M4: `tests/runtime/test_import_boundary.py` 新增断言内容不够具体

- **Status**: fixed
- **Evidence**:
  - Plan line 571 (Slice 2 expected assertions): "`tests/runtime/test_import_boundary.py` 现有 runtime import boundary 扫描覆盖新增 `lane.py`，确认 `dayu.runtime.lane` 不 import Engine / Host / Service / UI / Fins。"
  - Plan line 635-636 (Slice 3 expected assertions): "现有 runtime import boundary 扫描覆盖新增 `filelock.py`...新增断言：第三方 `filelock` 只允许出现在 `dayu.runtime.filelock`，其它 runtime 模块和 Host / Service / Fins / Engine 不得直接 import 第三方 `filelock`。"
  - Plan line 734 (failure paths): "第三方 filelock 只允许出现在 `dayu.runtime.filelock`。"
- **Verdict**: 修复完整。Slice 2 和 Slice 3 的 expected assertions 均已明确新增断言内容，包括自动覆盖和第三方 filelock 边界检查。

### D1: acquire stale-cleanup + count + insert 事务边界未明确为同一事务

- **Status**: fixed
- **Evidence**:
  - Plan line 369: "acquire 成功流程的 stale cleanup、active count 和 insert 必须在同一个 SQLite transaction 内完成：" — 后接 bullet list 说明三步。
  - Plan line 546 (Slice 2 instructions): "acquire 成功路径的 stale cleanup、active count 和 insert 必须在同一个 SQLite transaction 内完成。"
  - Design truth `design.md:153`: "coordinator 在短事务内先清理同一 lane 中 `expires_at <= now` 的 stale claims，再在 active claim 数量小于 capacity 时插入一条新 claim" — plan 表述比 design 更明确（"同一个 SQLite transaction"）。
- **Verdict**: 修复完整。claim/release semantics 和 Slice 2 instructions 两处均已明确单事务要求。

### D2: multi-process test DB path 传递方式不够明确

- **Status**: fixed
- **Evidence**:
  - Plan line 573 (Slice 2 expected assertions): "多进程测试由父进程用 `tmp_path` 或 `tempfile` 创建同一个 DB path，并通过 subprocess CLI 参数或环境变量传给子进程；子进程必须使用该共享路径构造 `SQLiteLaneCoordinatorConfig`。"
  - Plan line 335 (Coordinator / DB): "Tests 使用 `tmp_path / 'runtime_lanes.sqlite3'`；不得写入真实 `workspace/`。"
- **Verdict**: 修复完整。明确了父进程创建方式（`tmp_path` 或 `tempfile`）、传递方式（subprocess CLI 参数或环境变量）和子进程使用方式。

### D3: `LaneController.open(owner=None)` auto-generation 逻辑未收敛

- **Status**: fixed
- **Evidence**:
  - Plan line 351 (Coordinator / DB decisions): "`LaneController.open(owner=None)` 时 runtime 自动生成 owner：`owner_id=secrets.token_hex(8)`，`pid=os.getpid()`，`process_start_token=None`；调用方可通过 `owner=` 显式覆盖。"
  - Plan line 545 (Slice 2 instructions): "`LaneController.open(owner=None)` 时使用 `secrets.token_hex(8)` 生成 `owner_id`，`os.getpid()` 生成 `pid`，`process_start_token=None`；调用方可显式传入 `LaneOwner` 覆盖。"
  - Design truth `design.md:154`: "`owner` 默认由 runtime 根据当前进程生成" — plan 给出了具体生成算法，比 design 更具体。
- **Verdict**: 修复完整。decisions 和 implementation instructions 两处均已明确默认生成规则，且允许显式覆盖。

### D4: `LaneAcquireOutcome` 未显式标注 TypeAlias

- **Status**: fixed
- **Evidence**:
  - Plan line 253 (Public API): "`LaneAcquireOutcome`：`typing.TypeAlias`，定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`，不得创建新 dataclass / wrapper class。"
  - Plan line 306 (code block): `LaneAcquireOutcome: TypeAlias = LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`
  - Plan line 544 (Slice 2 instructions): "`LaneAcquireOutcome` 必须使用 `typing.TypeAlias` 定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`，不得创建新 dataclass。"
- **Verdict**: 修复完整。public API 描述、code block 和 implementation instructions 三处均已明确 TypeAlias 语义。

---

## Scope Boundary Audit

逐项核查 fix 是否引入 scope violation：

| 检查项 | 结果 | 证据 |
|---|---|---|
| 无 Engine 生产代码修改 | PASS | Plan 禁止修改列表未变化（line 79-82） |
| 无 Fins 生产代码修改 | PASS | 同上 |
| 无 Host durable store 实现 | PASS | Non-goals 未变化（line 30-31） |
| 无 ToolsDiscovery / ScenePrepare 实现 | PASS | Non-goals 未变化（line 34） |
| 无 ToolRuntime 提前实现 | PASS | Non-goals 未变化（line 33） |
| fix 只修改 plan/review 文档 | PASS | Fix artifact line 40-44: changed files 均为 plan 和 review 文档 |
| 无新增 production API | PASS | 所有 fix 都是澄清已有设计，未新增类型或接口 |

---

## Plan Handoff-Readiness After Fixes

Fix 后 plan 的 handoff readiness 评估：

- **Code-generation-ready**: PASS。所有 8 个 fix 都消除了 implementation agent 需要自行猜测的歧义：async shape、WAL 要求、事务边界、owner 生成、TypeAlias 定义、test DB 传递、import boundary 断言、runtime docstring 更新。
- **Slice ordering**: 未变化。4 个 slice 仍按依赖顺序排列，fix 不影响 slice 间依赖。
- **Stop conditions**: 未变化。所有 stop condition 仍精确且可执行。
- **Test coverage**: 增强。M4 fix 明确了 import boundary test 的新增断言，D2 fix 明确了 multi-process test 的 DB path 传递方式。
- **Documentation**: 增强。M3 fix 将 `dayu/runtime/__init__.py` docstring 更新纳入 documentation update decision。

---

## Finding 数量: 0

所有 8 个 findings (M1-M4, D1-D4) 均已修复。未发现新增 blocker。Plan 保持 handoff-ready 且 code-generation-ready。

## Proceed Recommendation

Plan 可以进入 user confirmation gate。

## Artifact Path

`docs/reviews/gateflow-plan-re-review-host-p1-public-contract-runtime-mimo-20260513.md`
