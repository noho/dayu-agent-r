# Host Phase 1 Plan Re-Review — 公共契约与 runtime 基础设施

## Review Gate

plan re-review

## Reviewer

AgentDS

## Re-Review Scope

只复核 controller 已接受并由 AgentCodex 修复的 plan review findings：M1、M2、M3、M4、D1、D2、D3、D4。不扩大 scope 到新的完整 plan review。

## Reviewed Artifacts

- Plan (post-fix): `docs/host/phase1-public-contract-runtime-plan.md`
- Fix report: `docs/reviews/gateflow-plan-fix-host-p1-public-contract-runtime-codex-20260513.md`
- Controller adjudication: `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-controller-adjudication-20260513.md`
- Original MiMo review: `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-mimo-20260513.md`
- Original DS review: `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-ds-20260513.md`

## Per-Finding Re-Review

### M1: `LaneClaimToken` async method shape

- **Status**: fixed
- **Required fix** (controller): 在 plan 的 `LaneClaimToken` shape 中写成 `async def refresh(self) -> None` 和 `async def release(self) -> None`。
- **Evidence**: plan:291-292 — `LaneClaimToken` public shape 中 `refresh` 和 `release` 均已标注 `async def ... -> None`。与设计真源 `docs/host/design.md` 的 `Awaitable[None]` 语义一致。
- **No regression**: 周围类型（`LaneOwner`、`LaneAcquired` 等）未受影响。

### M2: SQLite WAL mode

- **Status**: fixed
- **Required fix** (controller): 在 coordinator / DB implementation decisions 中要求初始化 runtime lane DB 时设置 `PRAGMA journal_mode=WAL`，并说明该 WAL 只属于 runtime lane DB，不影响 Host durable store。
- **Evidence**:
  - plan:337 — Coordinator / DB 段："DB 初始化必须设置 `PRAGMA journal_mode=WAL`。该 WAL 设置只属于 runtime lane DB，不改变、不约束 Host durable store 的 SQLite policy。"
  - plan:542 — Slice 2 implementation instructions："DB 初始化设置 `PRAGMA journal_mode=WAL`，且 WAL 只属于 runtime lane DB。"
- **Scope check**: WAL 声明限定在 runtime lane DB，未对 Host durable store 做任何约束或假设。不违反 scope boundary。

### M3: `dayu/runtime/__init__.py` docstring 更新

- **Status**: fixed
- **Required fix** (controller): 在 allowed files 和 documentation update decision 中明确允许并要求最小更新 `dayu/runtime/__init__.py` docstring，但不得 re-export lane / filelock 符号。
- **Evidence**:
  - plan:53 — Allowed files："最小修改 `dayu/runtime/__init__.py` docstring，说明 Phase 1 新增的层中立 lane / filelock runtime 能力；不得从包根 re-export `lane` / `filelock` 符号。"
  - plan:747 — Documentation Update Decision："`dayu/runtime/__init__.py`: 需要最小更新 docstring。原因：新增 `dayu.runtime.lane` 和 `dayu.runtime.filelock` 层中立 runtime 能力；该更新只描述 package-level 当前能力，不得 re-export lane / filelock 符号。"
- **Scope check**: 只允许 docstring 更新，明确禁止 package-root re-export。不违反 scope boundary。

### M4: Import boundary test assertions

- **Status**: fixed
- **Required fix** (controller): 在 Slice 2 / Slice 3 tests 中明确现有 runtime import boundary 扫描会覆盖新增 `lane.py` / `filelock.py`，并新增第三方 `filelock` 只允许出现在 `dayu.runtime.filelock` 的断言。
- **Evidence**:
  - plan:571 — Slice 2 expected assertions："`tests/runtime/test_import_boundary.py` 现有 runtime import boundary 扫描覆盖新增 `lane.py`，确认 `dayu.runtime.lane` 不 import Engine / Host / Service / UI / Fins。"
  - plan:635 — Slice 3 expected assertions："`tests/runtime/test_import_boundary.py` 现有 runtime import boundary 扫描覆盖新增 `filelock.py`，确认 `dayu.runtime.filelock` 不 import Engine / Host / Service / UI / Fins。"
  - plan:636 — Slice 3 expected assertions："新增断言：第三方 `filelock` 只允许出现在 `dayu.runtime.filelock`，其它 runtime 模块和 Host / Service / Fins / Engine 不得直接 import 第三方 `filelock`。"
- **Scope check**: 仅新增 import boundary 测试断言，不涉及生产代码变更。

### D1: acquire stale-cleanup + count + insert transaction boundary

- **Status**: fixed
- **Required fix** (controller): 在 claim / release semantics 中明确 acquire 成功路径的 stale cleanup、active count 和 insert 必须在同一个 SQLite transaction 内完成。
- **Evidence**:
  - plan:369-373 — Claim / release semantics："acquire 成功流程的 stale cleanup、active count 和 insert 必须在同一个 SQLite transaction 内完成：短事务内删除同 lane `expires_at <= now` 的 stale claims。统计 active claims。active count 小于 capacity 时 insert claim。返回 `LaneAcquired(token=...)`。"
  - plan:546 — Slice 2 implementation instructions："acquire 成功路径的 stale cleanup、active count 和 insert 必须在同一个 SQLite transaction 内完成。"
- **Correctness check**: 两处均使用了"同一个 SQLite transaction"的明确语言，消除了原 finding 指出的"三步独立短事务"歧义。capacity invariant 的正确性依赖已明确写入 plan。

### D2: Multi-process test DB path

- **Status**: fixed
- **Required fix** (controller): 在 Slice 2 multi-process test instructions 中明确父进程用 `tmp_path` 或 `tempfile` 创建 DB path，并通过 subprocess CLI 参数或环境变量传给子进程。
- **Evidence**: plan:573 — Slice 2 expected assertions："多进程测试由父进程用 `tmp_path` 或 `tempfile` 创建同一个 DB path，并通过 subprocess CLI 参数或环境变量传给子进程；子进程必须使用该共享路径构造 `SQLiteLaneCoordinatorConfig`。"
- **Scope check**: 仅涉及测试 fixture 设计指导，不改变生产 API。

### D3: `LaneController.open(owner=None)` auto-generation

- **Status**: fixed
- **Required fix** (controller): 在 lane implementation decisions 中明确 `owner=None` 时使用 `secrets.token_hex(8)` 生成 `owner_id`，`os.getpid()` 生成 `pid`，`process_start_token=None`；调用方可显式覆盖。
- **Evidence**:
  - plan:351 — Coordinator / DB："`LaneController.open(owner=None)` 时 runtime 自动生成 owner：`owner_id=secrets.token_hex(8)`，`pid=os.getpid()`，`process_start_token=None`；调用方可通过 `owner=` 显式覆盖。"
  - plan:545 — Slice 2 implementation instructions："`LaneController.open(owner=None)` 时使用 `secrets.token_hex(8)` 生成 `owner_id`，`os.getpid()` 生成 `pid`，`process_start_token=None`；调用方可显式传入 `LaneOwner` 覆盖。"
- **Scope check**: 使用标准库 `secrets` 和 `os`，无新依赖引入。只涉及 runtime lane owner identity 生成，不影响 Host truth。

### D4: `LaneAcquireOutcome` TypeAlias

- **Status**: fixed
- **Required fix** (controller): 在 public API shape / Slice 2 implementation instructions 中明确 `LaneAcquireOutcome` 是 `typing.TypeAlias`，定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`。
- **Evidence**:
  - plan:253 — Public API 文字说明："`LaneAcquireOutcome`：`typing.TypeAlias`，定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`，不得创建新 dataclass / wrapper class。"
  - plan:306 — Public shape 代码块：`LaneAcquireOutcome: TypeAlias = LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`
  - plan:544 — Slice 2 implementation instructions："`LaneAcquireOutcome` 必须使用 `typing.TypeAlias` 定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`，不得创建新 dataclass。"
- **Scope check**: 类型标注澄清，不涉及实现变更。

## Scope Boundary Check (新增 Blocker 排查)

逐项检查 fix 是否引入了 scope creep：

| 检查项 | 结果 |
|---|---|
| Plan 是否引入了 implementation 代码？ | 否 — 所有变更仅限 plan 文档文字澄清 |
| Plan 是否引入了 Host durable store？ | 否 — WAL 声明明确限定 runtime lane DB，与 Host store 隔离 |
| Plan 是否引入了 Engine / Fins 生产代码变更？ | 否 — 禁止修改列表未变 |
| Plan 是否引入了 ToolsDiscovery / ScenePrepare 实现？ | 否 — Slice 4 stop condition 未变 |
| Plan 是否引入了新的 production dependency？ | 否 — filelock 依赖在 fix 前已存在 |
| Plan 是否扩大了 slice 的文件所有权？ | 否 — allowed files 列表仅在 M3 增加了 `dayu/runtime/__init__.py` docstring 更新，这是 controller 明确要求的 |
| Plan 是否弱化了 stop condition？ | 否 — 所有 stop condition 保持原样 |
| Plan 是否引入了新的 public API 符号？ | 否 — 公共 API 列表未变，只是澄清了现有符号的 async / TypeAlias 语义 |
| Plan 是否允许了 package-root re-export？ | 否 — M3 明确禁止 re-export |

**无新增 blocker。**

## Special Item Verification

按 re-review 要求逐项确认以下关键点已在 plan 中收敛：

1. **LaneClaimToken refresh 和 release async shape**: plan:291-292 已明确 `async def`。
2. **SQLite WAL runtime lane DB 决策**: plan:337, plan:542 已明确 `PRAGMA journal_mode=WAL` 且不影响 Host store。
3. **Runtime package init docstring 更新且无 root re-export**: plan:53, plan:747 已明确。
4. **Import-boundary tests 包含第三方 filelock 只在 dayu.runtime.filelock**: plan:571, plan:635-636 已明确。
5. **同一 SQLite transaction 完成 stale cleanup + active count + insert**: plan:369-373, plan:546 已明确。
6. **Multi-process test DB path 通过 tmp_path 或 tempfile 传给子进程**: plan:573 已明确。
7. **Owner None 默认使用 secrets.token_hex 和 os.getpid**: plan:351, plan:545 已明确。
8. **LaneAcquireOutcome TypeAlias union**: plan:253, plan:306, plan:544 已明确。

全部 8 项已收敛，实现 agent 无需自行决定 material choices。

## Re-Review Conclusion

Finding 数量: 0。无剩余 finding，无 blocking finding。

Plan 在 fix 后保持 handoff-ready 且 code-generation-ready。所有 8 个 controller-accepted findings 均已在 plan 中以具体文字修复，且修复未引入 scope creep 或新增风险。建议 plan 进入 user confirmation gate。

## Artifact Path

`docs/reviews/gateflow-plan-re-review-host-p1-public-contract-runtime-ds-20260513.md`
