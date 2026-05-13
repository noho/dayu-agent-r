# Gateflow Code Re-Review — Host Phase 1 Slice 2: `dayu.runtime.lane`

## Review Metadata

- **Review role**: AgentMiMo
- **Gate**: code re-review
- **Work unit**: Host Phase 1 公共契约与 runtime 基础设施
- **Assigned slice**: Slice 2: `dayu.runtime.lane` cross-process coordinator
- **Source artifacts**:
  - Controller adjudication: `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-controller-adjudication-20260513.md`
  - Fix artifact: `docs/reviews/gateflow-fix-host-p1-s2-runtime-lane-20260513.md`
  - AgentMiMo code review: `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-mimo-20260513.md`
  - AgentDS code review: `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-ds-20260513.md`
- **Review date**: 2026-05-13

---

## Finding 数量: 0

## Blocking Finding 数量: 0

---

## M1/D1 Re-Review: `LaneController.open` async classmethod

**Controller requirement**: 将 `LaneController.open` 改为 async classmethod，DB parent 准备和初始化通过 `asyncio.to_thread` 包装，测试/子进程 helper 同步 `await` 调用。

**Evidence**:

- `lane.py:380-382`: `@classmethod async def open(cls, ...) -> LaneController` — 已改为 async classmethod。✅
- `lane.py:409`: `await asyncio.to_thread(_prepare_and_initialize_database, coordinator)` — DB 准备与初始化通过 `asyncio.to_thread` 执行，不阻塞 event loop。✅
- `lane.py:953-966`: `_prepare_and_initialize_database` 独立模块级函数，供 `to_thread` 调用。✅
- `test_lane.py`: 所有测试用例使用 `await LaneController.open(...)`（例如 line 196, 201, 215, 224, 238, 275, 302, 329, 354, 391, 417, 444, 510, 546）。✅
- `test_lane_multiprocess.py:227-232`: 父进程使用 `asyncio.run(LaneController.open(...))`。✅
- `test_lane_multiprocess.py:323-326`: 子进程 helper `_child_acquire` 使用 `await LaneController.open(...)`。✅

**结论**: M1/D1 已正确修复。`open` 回到 approved async public API shape，DB 阻塞操作通过 `to_thread` 包装。

---

## M2 Re-Review: heartbeat `RuntimeLaneError` 处理

**Controller requirement**: heartbeat loop 增加 `RuntimeLaneError` 分支，记录 first heartbeat error，停止新 acquire，唤醒 pending acquire，后续 acquire 抛结构化 `RuntimeLaneError`。增加 focused test。

**Evidence**:

- `lane.py:785-807`: `_heartbeat_loop` 已区分两种异常：
  - `RuntimeLaneClaimLostError` → `_mark_token_lost(token)` + `continue`（只标记单个 token lost，继续处理其它 token）。✅
  - `RuntimeLaneError` → `_record_heartbeat_error(exc)` + `return`（记录不可恢复错误，停止 heartbeat loop）。✅
- `lane.py:809-820`: `_record_heartbeat_error` 记录首次 error（`if self._heartbeat_error is None`），设置 `_closed = True`，设置 `_close_reason = "lane heartbeat error"`，唤醒 waiters。✅
- `lane.py:822-830`: `_raise_heartbeat_error_if_present` 在 acquire 入口（line 440）和循环内（line 455）调用，确保后续 acquire 抛出结构化 `RuntimeLaneError`。✅
- `lane.py:469-471`: acquire 成功后的二次检查也覆盖 heartbeat error 场景：若 `_heartbeat_error is not None`，先 release untracked claim 再 raise。✅
- `test_lane.py:459-501`: `test_heartbeat_runtime_error_stops_new_acquire` — 通过 monkeypatch 替换 `_refresh_token_sync` 抛出 `RuntimeLaneError`，验证后续 acquire 抛出结构化 `RuntimeLaneError`（`str(observed_error) == "heartbeat failed"`），close 后 claim count 归零。✅

**结论**: M2 已正确修复。heartbeat 不可恢复错误的传播路径完整：记录首次错误 → 停止 heartbeat → 停止新 acquire → 唤醒 pending → 后续 acquire 抛结构化错误。

---

## D2 Re-Review: 单个 claim lost 不关闭 controller

**Controller requirement**: `RuntimeLaneClaimLostError` 分支只标记对应 token lost/released，不关闭 controller；其余 held tokens 可 refresh/release；`close()` 在 heartbeat error 后仍 best-effort release 剩余 tokens。增加 focused test。

**Evidence**:

- `lane.py:800-801`: heartbeat loop 中 `RuntimeLaneClaimLostError` 分支只调用 `_mark_token_lost(token)` + `continue`，不设置 `_closed = True`。✅
- `lane.py:832-841`: `_mark_token_lost` 设置 `token._lost = True`、`token.released = True`，从 `_held_tokens` 移除，不影响其它 token。✅
- `lane.py:506-535`: `close()` 逻辑：
  - line 514: `_close_completed` 幂等守卫。✅
  - line 516: 设置 `_closed = True`。✅
  - line 520: `tokens = tuple(self._held_tokens.values())` — 取当前 held tokens 快照。✅
  - line 522-527: 遍历 tokens 尽力 release，捕获首个 `RuntimeLaneError` 但不中断循环。✅
  - line 528-532: 取消 heartbeat task。✅
  - line 533: `_close_completed = True`。✅
  - 即使 `_closed` 已被 `_record_heartbeat_error` 设置为 `True`，`close()` 仍执行 release 循环，不会因 line 514 提前返回（因为 `_close_completed` 此时仍为 `False`）。✅
- `test_lane.py:504-535`: `test_heartbeat_lost_claim_does_not_close_controller` —
  - 创建 capacity=2 的 controller，acquire 两个 token。✅
  - 通过 `_delete_claim` 删除第一个 token 的 DB row。✅
  - 等待 heartbeat 标记第一个 token 为 `released`。✅
  - 断言 `first.token.released is True`。✅
  - 断言 `second.token.released is False`，且 `second.token.refresh()` 成功。✅
  - release second token 后，可成功 acquire 新 token（验证 controller 未关闭）。✅
  - 最终 close 清理所有 claim。✅

**结论**: D2 已正确修复。单个 claim lost 只影响该 token，controller 继续正常工作，其余 token 可正常 refresh/release/close。

---

## 新问题检查

**Fix 是否引入新问题**: 无。

- `_record_heartbeat_error` 中 `self._closed = True` 与 `close()` 中的 `_close_completed` 幂等守卫配合正确：heartbeat error 设置 `_closed` 但不设置 `_close_completed`，因此 `close()` 仍会执行 release 循环。
- `_raise_heartbeat_error_if_present` 在 acquire 循环中多次调用（entry + loop body + post-claim），确保错误窗口最小化。
- `_heartbeat_loop` 中 `RuntimeLaneError` 分支直接 `return`，不会继续处理后续 token — 这是正确的，因为不可恢复错误影响整个 DB 连接，继续刷新其它 token 也会失败。
- `close()` 中 first_release_error 只记录不中断，确保所有 held tokens 都被尝试 release。
- 无 forbidden 文件修改，无 Host truth / lease / EventLog identity 引入。

---

## 验证证据

| 验证项 | 命令 | 结果 |
|---|---|---|
| lane + multiprocess tests | `pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q` | 16 passed |
| import boundary tests | `pytest tests/runtime/test_import_boundary.py -q` | 3 passed |
| pyright | `python -m pyright dayu/runtime/lane.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py` | 0 errors, 0 warnings, 0 informations |
| git diff --check | `git diff --check` | passed |

---

## Recommendation

**Proceed to user confirmation** — 三个 controller-accepted findings（M1/D1、M2、D2）均已正确修复，无新引入的 blocking finding，所有验证命令通过。

## Artifact Path

`docs/reviews/gateflow-code-re-review-host-p1-s2-runtime-lane-mimo-20260513.md`
