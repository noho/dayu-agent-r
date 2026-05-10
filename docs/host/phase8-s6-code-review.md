# P8-S6 Code Review: Stale / Orphan Recovery 新 Attempt 主路径

- **Branch**: `migration/host-p8-attempt-lease-recovery`
- **Baseline**: `7119573 host: add p8 attempt-scoped event fencing`
- **Review date**: 2026-05-09
- **Reviewer**: Code Review Agent (Claude)
- **Last update**: 2026-05-09 (post review-fix)

## 结论: PASSED (after review-fix)

初次 review 给出 CONDITIONALLY PASSED, 列出 F1 / F2 两项 Medium 级发现。
controller decision 接受这两项, 并要求当前 slice 修复, 不允许带病进入
P8-S7。修复已落地, F1 / F2 状态均改为 ``accepted``。

---

## 验证结果 (post review-fix)

| 检查项 | 结果 |
|--------|------|
| `pytest tests/host/test_phase8_attempt_recovery.py -q` | 8 passed |
| `pytest tests/host/test_phase8_tool_runtime_fencing.py -q` | 7 passed |
| `pytest tests/host/test_phase6_review_fixes.py -q` | 14 passed |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

---

## 发现

### F1 — `_process_recovery_candidate` NOOP_TERMINAL reason masking

- **Severity**: Medium
- **Status**: accepted (fixed in this slice)
- **Entry**: `_process_recovery_candidate` in `_attempt_supervisor.py`
- **Location (post-fix)**: `_attempt_supervisor.py` `_process_recovery_candidate` 末段非 ``MARK_RECOVERING_AND_CREATE_ATTEMPT`` 分支

**Evidence (原)**: 旧实现在 store 返回非 ``MARK_RECOVERING_AND_CREATE_ATTEMPT``
时, 重新构造一个 ``AttemptRecoveryDecision(action=NOOP_TERMINAL, reason=
_RECOVERY_REASON_NOOP_TERMINAL)``, 静默丢失 store 层 typed reason
(``cas_failed_noop`` 等)。

**Impact (原)**: 当前 store 实现仅返回 ``MARK_RECOVERING_AND_CREATE_ATTEMPT``
或 ``NOOP_TERMINAL``, 行为可观测; 但若 store 将来扩展更多 action 或新
reason 字面量, supervisor 会静默吞掉, 违反"所有 store 层决策必须被
supervisor 层尊重"的设计契约。

**Fix**:
- `_process_recovery_candidate` 在 ``MARK_RECOVERING_AND_CREATE_ATTEMPT``
  分支保持原有 debug 日志 + 直接返回 store decision;
- 其它分支不再覆盖 ``decision.action`` / ``decision.reason``, 直接返回
  store 层 typed decision; 仅记录一条
  ``host.attempt.recovery_store_decision`` debug 日志保留 action/reason 可观察性;
- supervisor 模块层移除不再使用的常量 ``_RECOVERY_REASON_NOOP_TERMINAL``,
  store 层带回的 ``cas_failed_noop`` 直接落到 caller。

**测试**: 新增 `test_supervisor_preserves_store_reason_on_cas_noop`
通过 monkeypatch ``list_recovery_candidates``, 在 scan 后强制覆写
``fencing_token`` 让短事务内 CAS rowcount=0; 断言 supervisor 返回
``decision.reason == "cas_failed_noop"``。

---

### F2 — `UNIQUE(run_id, attempt_index)` 并发 recovery race

- **Severity**: Medium
- **Status**: accepted (fixed in this slice)
- **Entry**: `_process_recovery_candidate` → `mark_recovering_and_create_attempt`
- **Location (post-fix)**:
  - `_run_state_store.py` 新增 typed 异常 ``AttemptIndexCollisionError``
    + ``mark_recovering_and_create_attempt`` INSERT 包裹
    ``try/except sqlite3.IntegrityError`` 抛 typed 冲突;
  - `_attempt_supervisor.py` `_process_recovery_candidate` 在
    ``async with storage.transaction()`` 外捕获 ``AttemptIndexCollisionError``,
    返回 typed ``NOOP_TERMINAL(reason="unique_index_collision")``。

**Evidence (原)**: ``next_attempt_index`` 使用 ``SELECT MAX(attempt_index)
+ 1``, 与同事务内的 INSERT 一起组成 RMW; 跨进程并发场景下两个独立
``BEGIN IMMEDIATE`` 短事务可能算出相同 ``attempt_index``, 第二个 INSERT
触发 ``UNIQUE(run_id, attempt_index)`` 抛裸 ``sqlite3.IntegrityError``。

**Impact (原)**: 裸 ``sqlite3.IntegrityError`` 泄漏到 supervisor 调用方;
违反 "store 层结果必须是 typed decision" 契约。

**Fix 设计要点 (controller 接受方案)**:
- ``mark_recovering_and_create_attempt`` 的 INSERT 抛
  ``AttemptIndexCollisionError`` (``run_id`` / ``attempt_index`` /
  ``source_attempt_id`` 都打包进 typed 异常), 不返回伪 ``NOOP_TERMINAL``、
  也不在事务内吞掉。
- typed 异常向上冒泡到 ``async with storage.transaction()``, 由 host
  storage transaction 整事务 ``ROLLBACK`` —— 旧 attempt 的
  ``RECOVERING`` CAS 与 fencing token 分配 (写入 ``host_fencing_tokens``
  / ``host_attempts``) 全部回滚, **没有"旧 attempt RECOVERING 但无新
  recovery attempt"的半状态**。
- supervisor 在事务外(`except AttemptIndexCollisionError`)捕获后构造
  typed ``AttemptRecoveryDecision(action=NOOP_TERMINAL,
  reason="unique_index_collision", recovery_attempt_id=None,
  recovery_attempt_index=None)``。
- 裸 ``sqlite3.IntegrityError`` 不再泄漏到 ``recover_stale_attempts``
  调用方。

**原子性证明**:
1. SQLite `BEGIN IMMEDIATE` 事务在 host storage 层由
   ``HostStorage.transaction()`` 统一管理: 任意 ``BaseException`` 会触发
   ``ROLLBACK``;
2. ``AttemptIndexCollisionError`` 是 ``Exception`` 子类, 满足触发
   ``ROLLBACK`` 的条件;
3. 因此 INSERT 失败必然导致同事务内的 ``UPDATE host_attempts SET
   state='recovering' ...`` 与 ``INSERT INTO host_fencing_tokens ...``
   全部回滚。

**测试**:
- `test_mark_recovering_unique_index_collision_rolls_back_atomically`
  (store 层): 直接预置占位 ``attempt_index=1`` 行, 让
  ``mark_recovering_and_create_attempt`` 在 INSERT 时命中 UNIQUE 冲突,
  断言抛 ``AttemptIndexCollisionError``; 事务回滚后旧 attempt 仍处于
  ``RUNNING``, 占位行未被改写, 没有残留 recovery attempt 行。
- `test_supervisor_unique_index_collision_returns_typed_noop`
  (supervisor 层): monkeypatch ``next_attempt_index`` 强制返回已被占用
  的 index, 模拟两个并发进程算出相同 ``attempt_index``; 断言
  ``recover_stale_attempts`` 返回
  ``decision.reason == "unique_index_collision"``,
  ``decision.action is NOOP_TERMINAL``, 且 SQL 验证旧 attempt 仍
  ``RUNNING``、占位行不变、无残留 recovery 行。
- 测试不引入 multiprocessing; 真实多进程验证仍归 P8-S7 / issue #38。

---

## 残余风险

| 风险 | 影响 | Owner | 目标阶段 |
|------|------|-------|----------|
| recovery scan 自动接入 Host bootstrap | 当前 recovery 只有手动入口, 无自动触发 | Host 治理层 (P8-S7 owner) | P8-S7 / Session lifecycle |
| 新 recovery attempt 可执行性 | 新 attempt 创建后无 owner token 返回给调用方, 无 renew session 绑定 | Host 治理层 (P8-S7 owner) | P8-S7 或 P9 |
| 多进程确定性测试 | 当前 recovery 测试均为单进程内存 SQLite, F2 collision 测试也是单进程 monkeypatch | 测试基础设施 owner | P8-S7 / issue #38 |

---

## 覆盖度确认

| 关注域 | 状态 | 说明 |
|--------|------|------|
| Slice 边界 | ✅ | recovery scan 不越权写 EventLog / projection checkpoint |
| Recovery 状态机 | ✅ | RUNNING→RECOVERING, CREATED orphan→LOST, run terminal→LOST, CAS miss→NOOP, UNIQUE collision→NOOP (typed) |
| Store CAS | ✅ | `mark_recovering_and_create_attempt` 使用 `state='running' AND fencing_token=?` CAS |
| Recovery atomicity | ✅ | F2 fix 后, INSERT 冲突触发整事务回滚, 旧 attempt 不进入 RECOVERING 半状态 |
| Recovery attempt 可执行性 | ⚠️ | 新 attempt 行结构完整 (fencing token, owner, recovered_from), 但端到端可执行性归 P8-S7 |
| EventLog / Projection 边界 | ✅ | recovery scan 不写 EventLog, 不推进 checkpoint |
| P8-S5 deferred fetch_more 测试 | ✅ | `test_phase8_tool_runtime_fencing.py` 新增 2 个 E2E fenced 测试 |
| 类型 / 架构 / 文档 | ✅ | pyright 0 errors; README 已同步更新; typed 异常 `AttemptIndexCollisionError` 不泄漏裸 SQLite 错误 |
