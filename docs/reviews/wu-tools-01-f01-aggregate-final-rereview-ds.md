# WU-TOOLS-01-F01 Aggregate Final Rereview — F01-AGG-001 Fix Gate

## Gate Metadata

- Work unit: `WU-TOOLS-01-F01`
- Gate: aggregate final fix rereview (deep review of F01-AGG-001 fix)
- Inputs:
  - `docs/reviews/wu-tools-01-f01-aggregate-final-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-aggregate-final-review-ds.md`
  - `docs/reviews/wu-tools-01-f01-aggregate-final-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-aggregate-final-fix-codex.md`
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `docs/host/design.md` (cancellation/wait 语义交叉检查)
  - `docs/engine/design.md` (cancellation commit boundary 交叉检查)
  - `docs/host/issues-implementation-control.md`
- Output artifact: `docs/reviews/wu-tools-01-f01-aggregate-final-rereview-ds.md`

## Verdict

**pass**

F01-AGG-001 的修复正确、完整、可验证。`claim_running_or_cancelled` 在一次 `fcntl` 持锁内完成 queued→running 的 claim 与 cancellation 判断/写入，彻底消除了旧 `read_job` + `save_job` 双锁路径的 TOCTOU race。回归测试使用确定性测试 double 而非 sleep race，可证明旧 race 不会再覆盖 cancellation。无新增 correctness/stability/maintainability 风险，无 AGENTS.md 违规，无 blocking findings。

## Review Axes

### 1. F01-AGG-001 Root Cause 确认

旧 race window（`ingestion_runtime.py` 原实现）：

- `_mark_job_running_or_cancelled` 先调用 `read_job`（获取 `_StoreFileLock` → 读取 → 释放锁），再调用 `save_job`（获取 `_StoreFileLock` → 写入 → 释放锁）。
- 两次锁之间，另一个线程/进程的 `request_cancel` 可获取锁，将 status 从 `QUEUED` 改为 `CANCELLING`，并写入 `cancellation_requested=True`。
- 之后 `save_job` 用旧 queued record 构建的 `RUNNING` record 覆盖 CANCELLING，导致取消请求静默丢失。

**判断：race 真实存在且严重性评估正确。** 虽然窗口极窄，但后果是取消被忽略——这在治理语义上是 correctness bug，不是可延后的 performance/observability 问题。

### 2. 修复方案正确性

#### 2.1 协议层新增

`FinsIngestionJobStore.claim_running_or_cancelled` (`ingestion_runtime.py:546-568`)：
- 单一方法语义清晰：claim running 或按当前取消状态收口为 cancelled。
- 参数设计合理：`started_at` 用于 RUNNING 写入，`updated_at` 用于两种终态写入，且取消收口时 `updated_at` 同时作为 `finished_at`。
- 返回值 `FinsIngestionJobRecord` —— 已持久化的终态或 running record，调用方无需额外读取。

**判断：协议方法语义自足，不泄漏实现细节。**

#### 2.2 文件系统实现

`FsFinsIngestionJobStore.claim_running_or_cancelled` (`ingestion_runtime.py:782-826`)：

```
with _StoreFileLock():           # 单次持锁
    record = _read_record_locked()
    if terminal → return         # 已是终态，不覆盖
    if CANCELLING or cancellation_requested:
        → write CANCELLED        # 取消收口：finished_at=updated_at
        return
    → write RUNNING              # 正常 claim：started_at=record.started_at or started_at
```

逐项验证：

| 检查项 | 结果 | 证据 |
|---|---|---|
| 单次 fcntl 持锁内完成 read-check-write | PASS | `with _StoreFileLock(...)` 包裹全部逻辑 (line 805) |
| 终态不覆盖 | PASS | `record.status in _TERMINAL_STATUSES` → 原样返回 (line 807-808) |
| CANCELLING → CANCELLED 携带 finished_at | PASS | `finished_at=updated_at` (line 814) |
| CANCELLING → CANCELLED 保留 cancellation_requested | PASS | `cancellation_requested=True` (line 815) |
| RUNNING 写入 started_at | PASS | `started_at=record.started_at or started_at` (line 822)，保留已有值优先 |
| RUNNING 写入 updated_at | PASS | `updated_at=updated_at` (line 823) |
| RUNNING 不写入 finished_at | PASS | replace 不传 finished_at，保持 None |

**判断：原子实现正确。**

#### 2.3 Runtime 调用方改造

`_mark_job_running_or_cancelled` (`ingestion_runtime.py:1266-1286`)：

旧实现：
```python
record = self.job_store.read_job(job_id)    # 持锁读取 → 释放
# ← TOCTOU race window
if terminal / cancellation → save cancelled
else → save running                          # 持锁写入
```

新实现：
```python
return self.job_store.claim_running_or_cancelled(
    job_id, started_at=now, updated_at=now,
)
```

**判断：旧双锁路径已完全移除。** `_run_preprocess_job` (`line 1197`) 和 `_run_download_job` (`line 1245`) 的调用方保持不变（仅调用 `_mark_job_running_or_cancelled`），无需改动。

### 3. 回归测试正确性

#### 3.1 测试 double 设计

`_ClaimRaceJobStore` (`tests/fins/test_fins_ingestion_runtime.py:191-412`)：

- `claim_running_or_cancelled` (line 297-343)：模拟 claim 内的 race——首次调用且 QUEUED 时，在读取后插入 cancel (`request_cancel`)，然后重新读取当前状态再裁决。
- `read_job` (line 345-363)：保留旧 race 模拟——首次读取 QUEUED 时，注入 cancel 但返回 stale queued record。这用于验证旧代码路径会被此 race 击中，但在修复后此注入对 claim 路径无影响（runtime 不再走 `read_job` 进 RUNNING）。
- `claim_running_calls` / `save_job_calls` 计数器精确证明 runtime 使用的是新路径还是旧路径。

#### 3.2 测试断言

`test_claim_running_preserves_cancel_between_read_and_running_write` (line 878-910)：

| 断言 | 含义 | 结果 |
|---|---|---|
| `claim_running_calls == 1` | runtime 使用了新的原子 claim 路径 | PASS |
| `save_job_calls == 0` | runtime 未回退到 `read_job` + `save_job` 旧路径 | PASS |
| `record.status is CANCELLED` | 最终状态是 cancelled | PASS |
| `record.status is not RUNNING` | 确认未覆盖为 running | PASS |
| `record.cancellation_requested` | 取消标记保留 | PASS |

#### 3.3 是否为 sleep race

**不是。** `_ClaimRaceJobStore` 通过确定性 flag (`claim_race_triggered`) 和状态检查 (`QUEUED`) 在首次调用时精确注入 cancel，不存在 `time.sleep` 或 timing-dependent 行为。race 注入后 `claim_running_or_cancelled` 重新读取当前状态，模拟的是"在 claim 内发现状态已变"的逻辑路径。

虽然真实的 `FsFinsIngestionJobStore.claim_running_or_cancelled` 持有 fcntl 锁阻止并发修改（所以真实场景中 claim 内不可能有并发 cancel），但测试 double 验证的是：**即使状态在 claim 内以某种方式变化，代码也能正确裁决为 cancelled 而非 running**。这是对裁决逻辑的防御性验证，不是对 fcntl 原子性的验证——fcntl 的原子性由 OS 保证。

**判断：回归测试有效且是确定性测试，不是 sleep race。**

### 4. AGENTS.md 合规检查

| 检查项 | 结果 | 证据 |
|---|---|---|
| 类型签名完整（无 Any/object） | PASS | `claim_running_or_cancelled` 全部参数有类型注解 (line 546-568) |
| 中文 docstring（含 Args/Returns/Raises） | PASS | 协议方法 (line 553-567)、实现方法 (line 789-803)、测试 double (line 304-316) 均有完整中文 docstring |
| 无兼容性胶水 | PASS | 旧 `_mark_job_running_or_cancelled` 直接重写，不保留旧路径包装 |
| 分层边界合规 | PASS | 协议在 `FinsIngestionJobStore`（Fins 层），实现在 `FsFinsIngestionJobStore`（Fins 层），runtime 委托 store；不涉及 Host/Engine/Service/UI |
| 无魔法数字/字符串 | PASS | 状态值通过 `FinsIngestionJobStatus` 枚举引用，时间通过 `_utc_now()` 获取 |
| 无嵌套函数/类 | PASS | `_ClaimRaceJobStore` 是模块级测试类，方法为普通实例方法 |

### 5. README 更新判断

| README | 判断 | 理由 |
|---|---|---|
| `dayu/fins/README.md` | 不更新 | job store 原子状态转换是内部实现优化，README 已描述 job store 治理语义和 cancellation 边界，未出现不一致 |
| `dayu/config/README.md` | 不更新 | provider 配置形态未变 |
| `tests/README.md` | 不更新 | 测试层级和运行方式无变化，仅同一测试文件内新增 regression case |
| 根 `README.md` | 不更新 | 无 CLI/UI 变化，无用户可见命令变化 |
| `dayu/README.md` | 不更新 | 稳定分层关系未变 |

### 6. 交叉检查：Host/Engine Cancellation 语义

- **Host Run cancellation**：Host 通过自身状态机管理 Run CANCELLING→CANCELLED 转换，与 Fins ingestion job 的 cancel 是独立治理域。Host 通过 `FinsIngestionWaitPollAdapter.abandon_wait` → `runtime.request_cancel(job_id)` 桥接到 Fins job store。
- **Engine cancellation commit boundary** (`docs/engine/design.md` §13)：Engine 在多个可中断边界观察 `CancellationToken`，但不参与 Fins job 状态管理。Fins job cancel 是外部长事务的治理域，不属于 Engine run scope。
- **无冲突**：Fins `claim_running_or_cancelled` 的原子性改进只在 Fins job store 内部生效，不影响 Host Attempt 取消或 Engine run 取消的语义。

### 7. 残留风险与新风险检查

| 项目 | 判断 |
|---|---|
| 旧 TOCTOU race 复现 | 已消除——`_mark_job_running_or_cancelled` 不再使用双锁路径 |
| `_save_cancelled` 使用 `save_job` 而非原子方法 | 已有观察（mimo review），不阻塞——仅同一后台线程写入该 job 的终态，无并发写入竞争 |
| `claim_running_or_cancelled` 中 `request_cancel` 并发调用 | 安全——两者都持 `_StoreFileLock`，fcntl 保证互斥 |
| 回归测试覆盖了真实 race 的等价逻辑路径 | 是——测试 double 在 claim 内注入 cancel 并验证裁决逻辑，等价于旧双锁窗口中的 cancel 注入 |
| 新引入的类型错误 | 无——pyright 0 errors |
| 新引入的测试失败 | 无——143 passed |
| 新引入的 whitespace 问题 | 无——`git diff --check` 通过 |

## Findings

### F01-AGG-001-FIX-CONFIRMED (Informational) — 修复确认

- **File**: `dayu/fins/ingestion_runtime.py:1266-1286` (`_mark_job_running_or_cancelled`)，`:782-826` (`claim_running_or_cancelled` 实现)
- **Severity**: 无（确认修复通过）
- **Detail**: `_mark_job_running_or_cancelled` 现在调用 `job_store.claim_running_or_cancelled(...)` 在一次 `_StoreFileLock` 持锁内完成 read-check-write，消除了旧 `read_job` + `save_job` 双锁路径的 TOCTOU race。

### No blocking findings

无 correctness、architecture、contract、security 或 AGENTS.md 层面的阻塞性 findings。

## Validation

```text
source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py \
  tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_public_resolve_wait_resume.py -q

→ 143 passed, 3 warnings in 1.97s
  (3 edgar deprecation warnings, 非本修复相关)

source .venv/bin/activate && pyright

→ 0 errors, 0 warnings, 0 informations

git diff --check

→ 通过，无输出
```

## Residual / Blocker

| ID | 状态 | 说明 |
|---|---|---|
| F01-AGG-001 | fixed | queued→running claim 与取消请求之间的 TOCTOU race 已通过 job store 原子 `claim_running_or_cancelled` 修复 |
| `_save_cancelled` 使用非原子 `save_job` | observed-not-blocking | 同一后台线程写入，无并发写入竞争；已在 mimo review 中记录 |
| 真实 SEC/CN/HK 网络下载 adapter | deferred | 后续 F04/F05 work unit |
| upload ingestion provider | deferred | 后续 work unit |
| SEC/Fins 与 CN/HK CI pipeline/smoke | deferred | 后续 work unit |
| CLI wrapper | deferred | 后续 work unit |

**blocker: none**

## Gate Decision

**建议进入 `ready-to-open-draft-PR` gate。**

理由：
- F01-AGG-001（aggregate final review 唯一 accepted finding）已正确修复。
- 指定 pytest（143 passed）、pyright（0 errors）与 `git diff --check` 均通过。
- 修复不扩大 F01 scope，不触碰 Host/Engine contracts、CLI/UI、真实网络 adapter 或 README 广泛清理。
- `WU-TOOLS-01-S4-R1` 仍可保持关闭状态。
- 无新增 correctness/stability/maintainability 风险。
