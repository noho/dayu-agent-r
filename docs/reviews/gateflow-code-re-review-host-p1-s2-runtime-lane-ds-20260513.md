# Gateflow Code Re-Review — Host Phase 1 Slice 2: `dayu.runtime.lane`

## Review Metadata

- **Review role**: AgentDS
- **Gate**: code re-review (focused)
- **Work unit**: Host Phase 1 公共契约与 runtime 基础设施
- **Assigned slice**: Slice 2: `dayu.runtime.lane` cross-process coordinator
- **Re-review scope**: controller-accepted findings M1/D1, M2, D2 的 fix 验证，以及 fix 是否引入新问题
- **Reviewed artifacts**:
  - Controller adjudication: `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-controller-adjudication-20260513.md`
  - Fix artifact: `docs/reviews/gateflow-fix-host-p1-s2-runtime-lane-20260513.md`
  - Original MiMo review: `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-mimo-20260513.md`
  - Original DS review: `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-ds-20260513.md`
  - Implementation artifact: `docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`
- **Review date**: 2026-05-13

## Files Reviewed

- `dayu/runtime/lane.py`
- `tests/runtime/test_lane.py`
- `tests/runtime/test_lane_multiprocess.py`
- `tests/runtime/test_import_boundary.py` (diff only)
- `docs/reviews/gateflow-fix-host-p1-s2-runtime-lane-20260513.md`

## Per-Finding Re-Review

### M1/D1: `LaneController.open` 已改为 async classmethod — **已修复，无新问题**

**Fix 验证**:

- `lane.py:380`: `@classmethod` + `async def open(...)` — 签名与 approved plan 的 public API shape 一致。
- `lane.py:409`: `await asyncio.to_thread(_prepare_and_initialize_database, coordinator)` — 同步的 DB parent 准备与 SQLite 初始化通过 `asyncio.to_thread` 执行，不阻塞事件循环。
- `test_lane.py`: 所有 `LaneController.open(...)` 调用已改为 `await LaneController.open(...)`。
- `test_lane_multiprocess.py:227`: 同步父进程测试使用 `asyncio.run(LaneController.open(...))`。
- `test_lane_multiprocess.py:296,323`: async 测试与子进程 helper 使用 `await LaneController.open(...)`。

**无新问题引入**。

### M2: heartbeat `RuntimeLaneError` 已正确处理 — **已修复，无新问题**

**Fix 验证**:

- `lane.py:785-807` (`_heartbeat_loop`): 区分了两个异常分支：
  - `RuntimeLaneClaimLostError` (line 800): 只标记 token lost，continue 处理其余 token。
  - `RuntimeLaneError` (line 803): 调用 `_record_heartbeat_error(exc)` 后 return。
  - 异常捕获顺序正确：子类 `RuntimeLaneClaimLostError` 先于父类 `RuntimeLaneError`。
- `lane.py:809-820` (`_record_heartbeat_error`): 记录首次 heartbeat error，设置 `_closed = True`，设置 `_close_reason`，唤醒所有 pending waiter。注意此处不设置 `_close_completed = True`，因此 `close()` 仍可被调用并执行 best-effort release。
- `lane.py:822-830` (`_raise_heartbeat_error_if_present`): 若已记录 heartbeat error 则抛出该结构化错误。
- `lane.py:440`: `acquire()` 入口处即调用 `_raise_heartbeat_error_if_present()`，新 acquire 立即被拒绝。
- `lane.py:455`: acquire 循环内再次检查，覆盖等待期间 heartbeat 失败场景。
- `lane.py:469-471`: claim 成功后二次检查 heartbeat error，若有则先 release 新 claim 再抛出结构化错误，防止在 heartbeat 失败后仍然发放 token。
- `test_lane.py:458-501` (`test_heartbeat_runtime_error_stops_new_acquire`): monkeypatch `_refresh_token_sync` 模拟不可恢复错误，轮询 acquire 直至捕获到结构化 `RuntimeLaneError("heartbeat failed")`，验证错误消息匹配，并断言 close 后无残留 claim。

**无新问题引入**。额外验证了 `_mark_token_lost` 在 `_refresh_token` (line 637) 与 `_heartbeat_loop` (line 801) 各调用一次的场景下是幂等的——设置同样的 bool 字段、对同一 key 做 `pop(..., None)`，不会产生副作用。

### D2: 单 token lost 不关闭 controller — **已修复，无新问题**

**Fix 验证**:

- `lane.py:800-802`: heartbeat loop 中对 `RuntimeLaneClaimLostError` 只调用 `_mark_token_lost(token)` 并 continue，不调用 `_record_heartbeat_error`，不设置 `_closed = True`。
- `lane.py:832-841` (`_mark_token_lost`): 只标记 `token._lost = True`、`token.released = True`，从 `_held_tokens` 移除该 token。不触碰 `_closed`、`_close_reason`、`_heartbeat_error`。
- `lane.py:514-515`: `close()` 的幂等守卫从旧的 `_closed` 检查改为 `_close_completed` 检查。即使 `_closed` 已被 `_record_heartbeat_error` 设为 True（M2 路径），`close()` 仍会执行后续的 token release 循环 (lines 520-527) 和 heartbeat task cancel (lines 528-532)。
- `lane.py:520-527`: `close()` 遍历 `_held_tokens` 并逐个 release。若 token 已被 `_mark_token_lost` 标记 released，`_release_token` (line 691) 会直接 return，不会重复 DB 操作。
- `test_lane.py:504-535` (`test_heartbeat_lost_claim_does_not_close_controller`): capacity=2，acquire 两个 token，删除第一个 token 的 DB row，等待 heartbeat 检测到 lost，断言第一个 token released、第二个 token 未 released、第二个 token 仍可 refresh、release 第二个后仍可 acquire 新 token、close 后无残留 claim。

**无新问题引入**。

## Forbidden Files / Host Truth Check

**变更文件清单**:

| 文件 | 状态 | 允许 |
|---|---|---|
| `dayu/runtime/lane.py` | new (untracked) | ✅ |
| `tests/runtime/test_lane.py` | new (untracked) | ✅ |
| `tests/runtime/test_lane_multiprocess.py` | new (untracked) | ✅ |
| `tests/runtime/test_import_boundary.py` | modified | ✅ (仅新增 lane.py 扫描覆盖断言) |
| `dayu/README.md` | modified | ✅ (原实现阶段的文档同步，非 fix 引入) |
| `tests/README.md` | modified | ✅ (原实现阶段的文档同步，非 fix 引入) |
| `docs/reviews/*.md` | new (untracked) | ✅ (review/fix artifact) |

**未修改的禁止文件**: Host / Engine / Fins / Service / UI、`dayu.runtime.filelock`、`pyproject.toml`、`dayu/runtime/__init__.py`。

**lane.py import 清单验证**:
- 标准库: `asyncio`, `os`, `secrets`, `sqlite3`, `time`, `collections.abc.Sequence`, `dataclasses`, `datetime`, `pathlib`, `types`, `typing`
- 项目内: 仅 `dayu.contracts.cancellation.CancellationToken`
- 无 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` import。

**无 Host truth / lease / fencing / EventLog identity 引入**。

## Validation Re-run

| Command | Result |
|---|---|
| `pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q` | 16 passed |
| `pytest tests/runtime/test_import_boundary.py -q` | 3 passed |
| `python -m pyright dayu/runtime/lane.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | no output (clean) |

## Summary

| Category | Count |
|---|---|
| **Total findings** | 0 |
| **Blocking findings** | 0 |

## Recommendation

**proceed** — 三个 controller-accepted finding (M1/D1, M2, D2) 均已正确修复，fix 未引入新问题。所有验证命令通过，无禁止文件被修改，无 Host truth / lease / EventLog identity 泄漏。controller 可进入 user confirmation gate。
