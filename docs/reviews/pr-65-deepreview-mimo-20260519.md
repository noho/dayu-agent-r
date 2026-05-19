# PR 65 Deep Review — AgentMiMo

- PR: [#65 Host Phase 11 lifecycle recovery hardening](https://github.com/noho/dayu-agent-r/pull/65)
- Branch: `feat/host-phase-11-recovery` → `main`
- Date: 2026-05-19
- Reviewer: AgentMiMo

---

## Verdict: PASS

PR 65 满足 Phase 11 设计要求，实现正确、边界清晰、测试充分。无 blocking finding。

---

## 1. 验证结果

| 检查项 | 结果 |
|--------|------|
| `pytest tests/host -q` | 793 passed, 1 skipped |
| `pytest tests/runtime -q` | 107 passed |
| `pyright dayu/host dayu/runtime tests/host tests/runtime` | 0 errors, 0 warnings, 0 informations |
| `git diff --check main...HEAD` | 1 trailing whitespace in `docs/reviews/phase11-slice5-code-review-ds-20260519.md:78`（review artifact，非生产代码） |
| CI checks | 未配置（branch 无 checks reported） |

---

## 2. 设计合规性：§27 / §27.1

### 2.1 Startup recovery scan 语义

| 设计要求 | 实现状态 |
|----------|----------|
| `ACCEPTED` Run 保持 `ACCEPTED` | ✅ `recovery.py:225-226` |
| `QUEUED` Run 保持 `QUEUED` | ✅ `recovery.py:227-231` |
| `WAITING` Run 保持 `WAITING` | ✅ `recovery.py:232-238` |
| `RUNNING`/`CANCELLING` 需 positive orphan proof 才进 `LOST` | ✅ `recovery.py:303-349`，`recovery_process.py` classifier |
| 可恢复 Run 进入 `RECOVERING` | ✅ `recovery.py:402-409`，`_run_has_recoverable_facts` 检查 |
| 不可恢复 Run 进入 `LOST` | ✅ `recovery.py:407-409`，`_startup_closeout_reason` |
| Recovery 不让旧 Attempt takeover | ✅ 创建新 Attempt + 新 execution_id |
| Recovery 输入只能是 durable truth | ✅ scanner 只读 Run/Attempt/dispatch/liveness rows |
| 每个 Run 最多一次 automatic recovery dispatch | ✅ `count_recovery_dispatches_for_run` + `recovery_dispatch_limit=1` |
| heartbeat stale 但无 positive proof 时只记录 diagnostic | ✅ `OrphanProofInconclusive` 分支不写 `ATTEMPT_LOST` |
| 多进程 recovery 不把"当前进程不可确认控制"当 orphan proof | ✅ `recovery_process.py:274-281`，PID live without identity → inconclusive |

### 2.2 Positive orphan proof 最小判定

| 条件 | 实现 |
|------|------|
| dispatch record 关联到旧 Attempt、owner_host_instance_id、durable host instance row | ✅ `recovery.py:365-378` |
| owner heartbeat 超过 stale threshold | ✅ `recovery_process.py:250-256` |
| 本机进程证据证明 owner pid 不存在或 pid 复用且 start_token/boot_id 不匹配 | ✅ `recovery_process.py:298-338` |
| CAS recheck 时 Run/Attempt/dispatch record 仍与分类输入一致 | ✅ `run_transition.py:close_startup_orphan_attempt_in_transaction` 内 recheck |

### 2.3 RECOVERING dispatch + cancel

| 要求 | 实现 |
|------|------|
| RECOVERING Run 可被 cancel 直接收口为 CANCELLED | ✅ `admission.py:2221-2252`，`cancel_recovering_run_in_transaction` |
| 取消不追加旧 Attempt terminal fact | ✅ `run_transition.py` CancelRecoveringRunInput 设计注释明确 |
| 新 recovery dispatch 提交前可被 cancel | ✅ RECOVERING 状态在 dispatch 前即可被 cancel |

### 2.4 Graceful shutdown

| 要求 | 实现 |
|------|------|
| 停止接收新 prompt admission | ✅ `_PublicHostHandle._closed` gate |
| 尽力向 active Attempt 传播 cancel/shutdown signal | ✅ `scheduler.close()` 取消 drain task、active tasks |
| 持久化 shutdown diagnostic fact | ✅ `mark_current_instance_stopping/stopped` |
| 不伪造成功 terminal | ✅ close 路径不写 terminal facts |

### 2.5 Runtime lane 不升级为 Host truth

| 要求 | 实现 |
|------|------|
| lane 只表达资源容量 | ✅ `dispatch.py` docstring 明确 |
| lane 不替代 Host admission / CAS / EventLog ordering | ✅ 无越界使用 |
| Host instance liveness 不是 lease / fencing / takeover grant | ✅ `dispatch.py` / `recovery.py` docstring 明确 |

---

## 3. 边界检查

### 3.1 No Engine changes

`git diff main...HEAD --name-only | grep '^dayu/engine/'` — 无输出。✅

### 3.2 Public API preservation

- `cancel_run` / `cancel_session_runs` public API 签名未变，行为扩展覆盖 RECOVERING 状态。
- `open_host` 返回的 `Host` 接口未变。
- `HostDispatchScheduler` 新增 `host_instance_id` property，不影响已有 API。

### 3.3 dayu.runtime 边界

- `tests/runtime/test_lane.py` 新增 close/acquire 并发测试，不涉及业务层导入。
- `dayu.runtime.lane` 无新增对 `dayu.host` / `dayu.engine` 的导入。✅

### 3.4 架构分层

- `recovery.py` / `recovery_process.py` 只依赖 `dayu.host.durable` 和 `dayu.host.admission`，不反向依赖 Engine / Service / UI。✅
- `recovery_process.py` 是只读 classifier，不写数据库，不推进状态。✅

---

## 4. Findings

### 4.1 非阻塞 Finding

| # | 严重性 | 描述 | 位置 |
|---|--------|------|------|
| F1 | Info | `git diff --check` 报告 `docs/reviews/phase11-slice5-code-review-ds-20260519.md:78` trailing whitespace。review artifact 非生产代码，不影响功能。 | review artifact |
| F2 | Info | `_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS = 1.0` 是新增魔法数字，但属于 scheduler 内部常量且有清晰语义，符合"工具 schema 例外"精神。 | `dispatch.py:192` |

---

## 5. 测试覆盖

Phase 11 新增测试文件：

| 文件 | 覆盖范围 |
|------|----------|
| `tests/host/test_recovery_scan.py` (854 行) | startup scan 全路径：accepted/queued/waiting 保持、running/cancelling orphan classification、positive proof CAS closeout、recovery dispatch、dispatch limit、recovering lost、inconclusive |
| `tests/host/test_recovery_orphan_classifier.py` (290 行) | `recovery_process.py` classifier：pid missing、start_token mismatch、boot_id mismatch、heartbeat recent、heartbeat stale + inconclusive |
| `tests/host/test_recovery_dispatch.py` (699 行) | recovery dispatch 集成：scheduler open → scan → dispatch → worker accept → terminal |
| `tests/host/test_recovery_multiprocess.py` (224 行) | 多进程 recovery：live owner 不误杀、crash 后恢复 |
| `tests/runtime/test_lane.py` (+77 行) | close/acquire 并发、active claim count invariant |
| 其他已有测试更新 | `test_active_cancel_dispatch`、`test_dispatch_scheduler`、`test_host_instance_liveness`、`test_open_host_runtime`、`test_public_cancel_session_runs`、`test_public_cancel_smoke`、`test_run_attempt_transitions`、`test_run_input_builder` |

测试覆盖了 §27 设计的所有分类规则和边界条件。

---

## 6. README 同步

| README | 变更 | 评估 |
|--------|------|------|
| `dayu/host/README.md` | 更新 cancel_run/cancel_session_runs 覆盖范围、RECOVERING 状态语义、startup recovery scan 描述、Host instance liveness 说明 | ✅ 与实现一致 |
| `tests/README.md` | 新增 recovery 测试运行命令、更新测试覆盖描述 | ✅ 与实现一致 |
| 根目录 `README.md` | 未变更 | ✅ Phase 11 不涉及 CLI / 用户入口变化 |
| `dayu/README.md` | 未变更 | ✅ 不涉及分层关系变化 |

---

## 7. PR Branch 状态

- Branch: `feat/host-phase-11-recovery`
- State: DRAFT
- Commits: 干净，无混合无关变更
- Diff: 75 files changed, 11783 insertions, 149 deletions
- 变更范围严格限定在 `dayu/host/`、`docs/`、`tests/host/`、`tests/runtime/`
- 无 Engine / Service / UI / Config 变更

---

## 8. 结论

PR 65 满足 `docs/host/design.md` §27/§27.1 的全部设计要求：

1. Startup recovery scan 正确实现 positive orphan proof + CAS closeout
2. RECOVERING dispatch + cancel 路径完整
3. Graceful shutdown 通过 heartbeat + stopping/stopped 标记实现
4. Runtime lane 不升级为 Host truth
5. 多进程 recovery 不误杀 live owner
6. 无 Engine 变更，public API 保持
7. 测试全部通过，pyright 零错误
8. README 同步到位

**判定：PASS**
