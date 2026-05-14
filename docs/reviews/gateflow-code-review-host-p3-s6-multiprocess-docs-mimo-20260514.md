# Code Review: Host P3-S6 Multiprocess Tests And Documentation Sync

- **reviewer**: AgentMiMo
- **review date**: 2026-05-14
- **review scope**: P3-S6 implementation artifact, test file, README changes
- **baseline HEAD**: `be104de`
- **review gate**: code review (MiMo only)

## Files Reviewed

| file | type | status |
|------|------|--------|
| `tests/host/test_admission_multiprocess.py` | new test | reviewed |
| `dayu/host/README.md` | README update | reviewed |
| `tests/README.md` | README update | reviewed |
| `docs/reviews/gateflow-implementation-host-p3-s6-multiprocess-docs-20260514.md` | implementation artifact | reviewed |

## Validation Results

| command | result |
|---------|--------|
| `pytest tests/host/test_admission_multiprocess.py -q` | 6 passed in 1.23s |
| `pytest tests/host/test_admission_multiprocess.py tests/host -q` | 157 passed in 2.06s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed |

## Finding Summary

**0 blocking, 2 non-blocking, 2 residual risk.**

无 blocking finding。P3-S6 accepted。

---

## Detailed Review

### 1. Scope Correctness

`git diff` 确认只修改 `dayu/host/README.md` 和 `tests/README.md`，新增 `tests/host/test_admission_multiprocess.py` 和 implementation artifact。未修改任何生产代码（`dayu/host/admission.py` 等均未被触及）。符合 P3-S6 plan scope 约束。

### 2. 多进程测试是否真的验证 P3-S6 目标

6 个测试函数逐一对应 plan 的 6 个 expected assertions，且断言均以 durable rows 和 EventLog 为真源，不依赖进程调度顺序：

| plan 要求 | test function | 断言方式 |
|-----------|--------------|----------|
| 同 slot 并发 ensure 只返回一个 Session binding | `test_multiprocess_same_slot_ensure_returns_one_bound_session` | durable rows: `host_sessions` count=1, `host_session_slots` count=1, 所有进程返回相同 session_id |
| 同 Session 并发 start/follow-up 至多一个 active Run | `test_multiprocess_same_session_admission_keeps_one_active_run` | durable rows: total runs=4, running=1, queued=3, attempt=1 |
| 重复 `(session_id, client_request_id)` 返回同一 Run；变更 digest 冲突 | `test_multiprocess_duplicate_followup_idempotency_returns_one_result_and_conflicts` | durable rows: unique run_ids=1, conflict error code=IDEMPOTENCY_CONFLICT |
| queued follow-up 按 accepted `event_sequence` FIFO promotion | `test_multiprocess_queued_followups_promote_by_accepted_sequence` | durable rows: promoted_run == first_queued.run_id, accepted sequences sorted |
| queued cancel vs promotion first-committer-wins | `test_multiprocess_cancel_queued_vs_promotion_first_committer_wins` | durable rows + event_types: 双路径终态互斥验证（cancelled 或 running） |
| EventLog `event_sequence` 全局唯一递增 | `test_multiprocess_admission_event_sequence_is_global_unique_and_increasing` + 每个 test 末尾 | durable rows: sequence == range(1, N+1)，无间隙、无重复 |

关键设计选择：`test_multiprocess_cancel_queued_vs_promotion_first_committer_wins` 不假设谁先提交，而是读取 durable final status 后分支断言——若 cancelled 则 cancel 先提交、若 running 则 promote 先提交，两条路径都验证 EventLog 事实一致性。这避免了调度偶然性。

### 3. 子进程 connection 独立性

每个子进程 worker 函数内部独立调用 `open_host_durable_store(_options(...))` 打开 SQLite connection，不共享父进程 connection。模式与 `tests/host/test_event_log_multiprocess.py` 一致。`_PROCESS_COUNT = 4` modest，SQLite busy timeout 3s、write retry 80 次、backoff 1.2x、max delay 0.03s 合理覆盖文件锁竞争。

### 4. 覆盖范围逐项核对

- 同 slot ensure 单 session：`test_multiprocess_same_slot_ensure_returns_one_bound_session` ✅
- 同 session 最多一个 active Run：`test_multiprocess_same_session_admission_keeps_one_active_run` ✅
- 跨进程 follow-up 幂等与 conflict：`test_multiprocess_duplicate_followup_idempotency_returns_one_result_and_conflicts` ✅
- queued FIFO promotion by accepted event_sequence：`test_multiprocess_queued_followups_promote_by_accepted_sequence` ✅
- queued cancel vs promotion first-committer-wins：`test_multiprocess_cancel_queued_vs_promotion_first_committer_wins` ✅
- EventLog sequence 全局唯一递增连续：`test_multiprocess_admission_event_sequence_is_global_unique_and_increasing` + 每个 test 末尾 `_assert_event_sequences_global_unique_and_increasing` ✅

### 5. README 同步审查

**`dayu/host/README.md`**（diff 两处）：
- Internal Admission 段新增一条 bullet，陈述多进程 durable invariant 测试覆盖事实。
- 测试段末尾追加 "admission 多进程 durable invariant"。
- 内容只描述当前已实现/已测试的事实，无未来设计、无旧术语残留、无 public facade 承诺。符合 Host 开发手册职责。

**`tests/README.md`**（diff 两处）：
- 常用命令段新增 `pytest tests/host/test_admission_multiprocess.py tests/host -q`。
- `tests/host/` 描述段 durable foundation / internal admission bullet 追加多进程测试覆盖描述。
- 内容只描述当前事实，符合测试手册职责。

两个 README 均未越界：不写未来设计、不写实现细节、不承诺未实现的 public API。

### 6. 项目约束合规

- **分层**：测试只 import `dayu.host.admission`、`dayu.host.api`、`dayu.host.durable.*`，未跨层依赖。
- **过度设计**：测试 helper（`_options`、`_bootstrap_store`、`_seed_*`、`_run_processes`、`_write_*_result`、`_read_*`、`_count_rows`、`_assert_*`）均为模块级私有函数，无嵌套类或不必要的抽象。
- **弱类型**：所有函数有完整类型签名和中文 docstring。`_count_rows` 的 parameters 类型 `tuple[None | int | float | str | bytes, ...]` 与 SQLite 参数绑定一致。
- **魔法字符串**：`_SCOPE = "workspace"`、`_SLOT_KEY = "multiprocess"` 等均为模块级命名常量。Event ID 字符串（`"event-cancel-requested"` 等）属于测试 fixture 构造，非业务魔法字符串。
- **测试可维护性**：每个 test 使用 `tmp_path` 隔离 DB，seed helper 职责清晰，断言源为 durable rows 而非内存状态。

---

## Non-blocking Findings

### NB-1: `_duplicate_followup_worker` docstring 拼写

- **文件/行号**: `tests/host/test_admission_multiprocess.py:760`
- **证据**: `:raises AssertionError:` — 应为 `AssertionError`（但项目中已有此拼写模式，属历史一致性）
- **影响**: 无功能影响，仅文档准确性。
- **建议**: 可在后续 cleanup 中统一修正。

### NB-2: cancel/promotion 竞争 test 的 seed helper 使用低层 transition

- **文件/行号**: `tests/host/test_admission_multiprocess.py:555-622`（`_seed_single_eligible_queued_run`）
- **证据**: seed helper 直接调用 `terminal_closeout_in_transaction` 释放 active slot，绕过 `closeout_attempt_terminal` 的自动 promotion，用于构造"active slot 已释放但尚未 promotion"的竞争窗口。
- **影响**: 测试了低层 transition 的 first-committer-wins 语义，但未覆盖 public facade 入口的相同竞争。implementation artifact 已如实记录此 residual risk。
- **建议**: public facade 阶段需补充 API 级别的 cancel/promotion 竞争测试。

---

## Residual Risks

1. **SQLite 调度依赖**：多进程测试仍依赖本机 SQLite 文件锁与 OS 调度。文件 gate + modest process count + 较宽 busy timeout 已降低偶发 busy 风险，但在极慢 CI 上仍有小概率 flaky。
2. **低层 helper 构造竞争窗口**：cancel/promotion 竞争 test 使用 `terminal_closeout_in_transaction` 直接释放 active slot 而不经过 public API。public facade 阶段需覆盖最终 API 入口的相同竞争语义。

---

## Conclusion

P3-S6 accepted / no blocking findings。6 个测试函数完整覆盖 plan 所列全部 durable invariant 场景，断言以 durable rows 和 EventLog 为真源，不依赖调度偶然性。README 同步只陈述当前事实，未越界。未修改生产代码。所有验证命令通过。
