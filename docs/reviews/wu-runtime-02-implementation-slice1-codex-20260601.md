# WU-RUNTIME-02 Slice 1 Implementation Artifact

## Gate / Role

- **Gate**: implementation
- **Role**: implementation specialist
- **Work Unit**: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- **Slice**: Slice 1 - TTL 时间真源改为真实 UTC
- **Approved plan**: `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`
- **Artifact path**: `docs/reviews/wu-runtime-02-implementation-slice1-codex-20260601.md`

## Scope / Non-goals

- 只实现 Slice 1 的 lane TTL clock 修正。
- 未启动完整 Gateflow workflow。
- 未提交、未 push、未创建 PR。
- 未修改 Host / Engine / Service / UI / Fins / Config 代码。
- 未处理 Slice 2 的 bounded cancellation cleanup。
- 未处理 `LaneClaimToken.released` public field。
- 未修改、格式化、回滚或 stage controller 已有的 `docs/host/host-core-followup-implementation-control.md` bookkeeping 修改。

## Changed Files

- `dayu/runtime/lane.py`
- `tests/runtime/test_lane.py`
- `docs/host/design.md`
- `tests/README.md`
- `docs/reviews/wu-runtime-02-implementation-slice1-codex-20260601.md`

## Implemented Plan Items

- `_LaneClock` 删除 `monotonic_anchor` / `utc_anchor` 字段，`start()` 返回无 anchor clock。
- `_LaneClock.utc_now()` 直接返回 `datetime.now(UTC)`。
- `_LaneClock.monotonic()` 保留，仅供本进程 acquire timeout / deadline 等等待时长计算使用。
- `_try_claim_once_sync()` 在 SQLite 短事务前读取一次真实 UTC `now`，并在同一事务内复用该值做 stale cleanup、active count、insert 的 `created_at` / `heartbeat_at` / `expires_at`。
- `_refresh_token_sync()` 在 SQLite 短事务前读取一次真实 UTC `now`，并在同一事务内复用该值做 `heartbeat_at` / `expires_at` 更新和 `expires_at > now` 判断。
- 保持 runtime lane DB schema、public API、`__all__` 不变。
- 新增单进程 runtime lane 回归测试，覆盖 monotonic 大幅前跳不会误清理真实 UTC 尚未过期 claim，且 refresh 不会因此误判 lost。
- 同步 `docs/host/design.md` 的 lane clock 表述，明确真实 UTC per SQLite transaction、monotonic 只用于本进程等待 timeout、clock skew 只影响 runtime capacity availability。

## Validation Commands / Results

- `source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
  - Result: passed, `35 passed in 1.50s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `! rg -n "monotonic-to-wall|monotonic.*TTL" docs/host/design.md`
  - Result: passed, no matches
- `rg -n "真实 UTC|datetime.now\\(UTC\\)|SQLite transaction|本进程等待 timeout" docs/host/design.md`
  - Result: passed, matched updated lane clock lines in `docs/host/design.md`
- `git diff --check -- dayu/runtime/lane.py tests/runtime/test_lane.py docs/host/design.md tests/README.md`
  - Result: passed, no whitespace errors

## Docs Decision

- `docs/host/design.md` was updated because the design source previously described a monotonic-to-wall clock strategy, which no longer matches the Slice 1 implementation.
- `tests/README.md` was updated because the runtime lane coverage description did not mention the newly added invariant that TTL time source is not affected by monotonic elapsed jumps.
- Root `README.md`, `dayu/README.md`, and package READMEs were not updated because this slice does not change CLI usage, configuration entry points, public runtime lane responsibility, Host/Engine layering, or package-level extension contracts.

## Residual Risks / Uncovered Areas

- System wall clock skew can still affect runtime capacity availability by making claims expire early or late. This is the accepted boundary from the approved plan and does not affect Host truth / EventLog / Attempt lifecycle.
- Slice 2 cancellation cleanup remains intentionally untouched; outer cancellation cleanup is still governed by the existing implementation until the assigned Slice 2 pass.
- No DB schema, public API, or Host usage change was required. No stop condition was triggered.

## Stop Status

- Slice 1 implementation complete.
- Required validation passed.
- Ready for controller-owned code review gate.
