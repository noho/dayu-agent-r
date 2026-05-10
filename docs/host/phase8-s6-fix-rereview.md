# P8-S6 Fix Re-Review: F1 / F2 修复复审

- **Branch**: `migration/host-p8-attempt-lease-recovery`
- **Baseline**: `7119573 host: add p8 attempt-scoped event fencing`
- **Re-review date**: 2026-05-09
- **Reviewer**: Fix Re-Review Agent (Claude)
- **Review scope**: F1 / F2 修复验证，不涉及新实现

## 结论: PASSED

F1 / F2 两项修复均已正确落地, 无新增 finding。允许进入 user confirmation + commit gate。

---

## 验证结果

| 检查项 | 结果 |
|--------|------|
| `pytest tests/host/test_phase8_attempt_recovery.py -q` | 8 passed |
| `pytest tests/host/test_phase8_tool_runtime_fencing.py -q` | 7 passed |
| `pytest tests/host/test_phase6_review_fixes.py -q` | 14 passed |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

---

## F1 复审: `_process_recovery_candidate` NOOP_TERMINAL reason masking

**结论: PASSED**

### 代码证据

1. **supervisor 透传路径正确** (`_attempt_supervisor.py:858-888`):
   `_process_recovery_candidate` 在 `mark_recovering_and_create_attempt` 返回非 `MARK_RECOVERING_AND_CREATE_ATTEMPT` 时, 直接 `return decision`, 不覆盖 `decision.action` / `decision.reason`。仅记录一条 `host.attempt.recovery_store_decision` debug 日志保留可观测性。

2. **store 层原始 reason 保留** (`_run_state_store.py:993-1000`):
   `mark_recovering_and_create_attempt` CAS rowcount!=1 时返回 `AttemptRecoveryDecision(reason=_RECOVERY_REASON_CAS_NOOP)`, 其中 `_RECOVERY_REASON_CAS_NOOP = "cas_failed_noop"`。该 reason 直接落到 caller。

3. **无 silent masking / fallback reason**:
   - supervisor 模块层已移除旧常量 `_RECOVERY_REASON_NOOP_TERMINAL` (原值 `"attempt_already_terminal"`), 不再存在覆盖路径。
   - 除 run terminal / orphan CREATED / UNIQUE collision 三条显式路径外, supervisor 不构造自建 reason。

### 测试覆盖

- `test_recover_returns_noop_when_cas_misses` (`test_phase8_attempt_recovery.py:326-392`):
  直接调用 store 层 CAS 入口模拟 token race, 断言 `decision.reason == "cas_failed_noop"`。

- `test_supervisor_preserves_store_reason_on_cas_noop` (`test_phase8_attempt_recovery.py:396-454`):
  通过 monkeypatch `list_recovery_candidates` 在 scan 后覆写 `fencing_token` 让 CAS rowcount=0, 断言 supervisor `recover_stale_attempts` 返回 `decision.reason == "cas_failed_noop"`。测试注释明确: "不允许把它静默替换为 supervisor 自建的 `attempt_already_terminal`; 同时也不允许替换为本 slice 新增的 `unique_index_collision`"。

---

## F2 复审: `UNIQUE(run_id, attempt_index)` 并发 recovery race

**结论: PASSED**

### 代码证据

1. **typed 异常定义** (`_run_state_store.py:116-154`):
   `AttemptIndexCollisionError(Exception)` 字段类型明确: `run_id: str`, `attempt_index: int`, `source_attempt_id: str`。中文 docstring 完整, 说明了从裸 `sqlite3.IntegrityError` 转换的意图与事务回滚语义。

2. **INSERT 冲突抛 typed 异常** (`_run_state_store.py:1033-1044`):
   `mark_recovering_and_create_attempt` 在 INSERT `host_attempts` 时捕获 `sqlite3.IntegrityError`, 转抛 `AttemptIndexCollisionError`, 保留 `from exc` 链。

3. **异常逃出事务触发 rollback**:
   - `AttemptIndexCollisionError` 是 `Exception` 子类, 满足 `HostStorage.transaction()` 的 rollback 条件 (`BaseException` 触发 ROLLBACK)。
   - 异常从 `mark_recovering_and_create_attempt` 内部抛出, 穿透 `async with storage.transaction() as tx:` 上下文, 触发整事务 `ROLLBACK`。
   - rollback 后: 旧 attempt 的 `RECOVERING` CAS (UPDATE) 与新 recovery attempt 的 INSERT 同时未提交, 不存在半状态。

4. **supervisor 事务外捕获** (`_attempt_supervisor.py:889-908`):
   `except AttemptIndexCollisionError as exc:` 位于 `async with self.storage.transaction() as tx:` 块之外, 捕获后返回 typed `AttemptRecoveryDecision(action=NOOP_TERMINAL, reason="unique_index_collision", recovery_attempt_id=None, recovery_attempt_index=None)`。

5. **无 multiprocessing 引入**: P8-S7 范围, 本 slice 不引入。

### 测试覆盖

- `test_mark_recovering_unique_index_collision_rolls_back_atomically` (`test_phase8_attempt_recovery.py:457-539`):
  store 层断言: 预置 `attempt_index=1` 占位行, 让 `mark_recovering_and_create_attempt` INSERT 命中 UNIQUE 冲突; 断言抛 `AttemptIndexCollisionError` 且字段正确; 事务回滚后旧 attempt 仍 `RUNNING`, 占位行未被改写, 无残留 recovery attempt 行。

- `test_supervisor_unique_index_collision_returns_typed_noop` (`test_phase8_attempt_recovery.py:543-627`):
  supervisor 层断言: monkeypatch `next_attempt_index` 强制返回已被占用的 index; 断言 `recover_stale_attempts` 返回 `reason == "unique_index_collision"`, `action is NOOP_TERMINAL`, `recovery_attempt_id is None`, `recovery_attempt_index is None`; SQL 验证旧 attempt 仍 `RUNNING`, 占位行不变, 无残留 recovery 行。

- 测试不依赖真实 sleep: 全部使用 `_FakeClock` + `clock.advance()`。

---

## 测试充分性总结

| 测试 | 覆盖目标 | 状态 |
|------|----------|------|
| `test_recover_stale_running_attempt_creates_recovery_attempt` | MARK_RECOVERING_AND_CREATE_ATTEMPT 主路径 | ✅ |
| `test_recover_skips_when_run_is_terminal` | run terminal → MARK_LOST | ✅ |
| `test_recover_marks_orphan_created_attempt_lost` | CREATED orphan → MARK_LOST | ✅ |
| `test_recover_returns_noop_when_cas_misses` | CAS miss → NOOP, store reason 断言 | ✅ |
| `test_supervisor_preserves_store_reason_on_cas_noop` | F1: supervisor 透传 store reason | ✅ |
| `test_mark_recovering_unique_index_collision_rolls_back_atomically` | F2: store 层 rollback 原子性 | ✅ |
| `test_supervisor_unique_index_collision_returns_typed_noop` | F2: supervisor 层 typed NOOP | ✅ |
| `test_recover_does_not_advance_projection_checkpoint` | recovery scan 不修改 checkpoint | ✅ |

---

## Review Artifact 状态

- `docs/host/phase8-s6-code-review.md`: 已准确记录 F1/F2 `accepted` + `fixed`, 结论 `PASSED (after review-fix)`。
- 残余风险仍都有 owner:
  - recovery scan 自动接入 Host bootstrap → P8-S7
  - 新 recovery attempt 可执行性 / owner token 返回 / renew session 绑定 → P8-S7 或 P9
  - 多进程真实并发验证 → P8-S7 / issue #38

---

## Git 状态

`git status --short` 显示 `docs/host/phase8-s6-code-review.md` 和 `tests/host/test_phase8_attempt_recovery.py` 为 untracked 新文件; `_attempt_supervisor.py`、`_run_state_store.py` 等为 modified。`git diff --check` clean, 无 whitespace 错误。

---

## 最终判定

**PASSED** — F1 / F2 修复均正确落地, 无新增 finding, 无阻断项。允许进入 user confirmation + commit gate。
