# WU-TOOLS-01-F01-02 Slice 1 Re-review — AgentDS

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | re-review after Slice 1 fix |
| slice | Slice 1 - Fins Awaiting Tools Token Bridge |
| fix artifact | `docs/reviews/wu-tools-01-f01-02-slice1-fix-codex.md` |
| original review | `docs/reviews/wu-tools-01-f01-02-slice1-code-review-ds.md` |
| controller adjudication | `docs/reviews/wu-tools-01-f01-02-slice1-code-review-controller-adjudication.md` |
| date | 2026-06-08 |

## Scope

- Mode: re-review of accepted findings S1-F1 through S1-F4 only.
- Included: `dayu/fins/ingestion_runtime.py`, `tests/fins/test_fins_ingestion_runtime.py`, `dayu/fins/README.md`, `tests/README.md` (read-only validation).
- Excluded: Slice 2/3/4, Host/Engine contracts, control documents.
- Validation method: `grep`/`rg` + source read + `pytest` + `pyright` (read-only).

## Verification Items from Re-review Gate

### 1. `_create_queued_job` 死代码是否已删除

**已修复。**

- `rg "def _create_queued_job|_create_queued_job\(" dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` → 无匹配。
- 原 `_create_queued_job`（持有自己的 `self._start_lock` 并调用 `_create_queued_job_record`）已完全移除。现仅保留 `_create_queued_record_with_start_lock`（line 1160），由 `start_download`（line 1051）和 `start_preprocess`（line 1108）在持有 `_start_lock` 后直接调用。
- 无新 wrapper 绕过 create/checkpoint/submit invariant。`start_download` 和 `start_preprocess` 的锁内逻辑清晰：`_create_queued_record_with_start_lock` → `_is_start_cancelled` → `_save_cancelled` 或 `executor.submit`，三步都在同一 `_start_lock` 下。

### 2. create 后、executor.submit 前取消是否收口为 CANCELLED

**已修复。**

- `start_download:1058-1059`：`if _is_start_cancelled(cancellation_token): return _job_start_from_record(self._save_cancelled(start.record))`
- `start_preprocess:1115-1116`：同理。
- `_save_cancelled`（line 1841-1863）写入 `FinsIngestionJobStatus.CANCELLED`、`finished_at=now`、`cancellation_requested=True`。
- 不调用 `executor.submit`。不改 Host/Engine contract——`_save_cancelled` 是已有 Fins 内部私有方法，仅推进 Fins job 终态，不接触 Host wait record 或 Engine run 状态。

### 3. tests 不再断言 `token.check_count == 2`

**已修复。**

- `test_download_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit`（line 564-580）断言：
  - `start.status is FinsIngestionJobStatus.CANCELLED`
  - `record.status is FinsIngestionJobStatus.CANCELLED`
  - `record.cancellation_requested`
  - `executor.operations == []`
  - 无 `token.check_count == 2` 或任何对 `check_count` 的断言。
- `test_preprocess_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit`（line 774-790）：同。

### 4. `_CancelOnSecondCheckToken` 取消后 `cancel_reason()` 和 `requested_at()` 是否一致

**已修复。**

- `_CancelOnSecondCheckToken`（line 192-241）：当 `is_cancelled()` 第二次调用时设置 `self._cancelled = True`（line 218）。
- `cancel_reason()`（line 221-230）：`self._cancelled` 为 `True` 时返回 `"host-cancelled"`，否则返回 `None`。
- `requested_at()`（line 232-241）：`self._cancelled` 为 `True` 时返回 `datetime(2026, 6, 8, tzinfo=timezone.utc)`，否则返回 `None`。
- 取消被观察后两个方法行为一致，不再出现 `is_cancelled() == True` 而 `cancel_reason() != None` 但 `requested_at() == None` 的不一致。

### 5. README 文本从 CANCELLING/cancelling 更新到 CANCELLED/cancelled

**已修复（符合 README 职责）。**

- `dayu/fins/README.md` line 432："durable `queued` job record 创建后、后台 submit 前同步 checkpoint，若命中取消则把 Fins job 收口为 `cancelled` 终态且不提交后台执行"——正确描述 create-before-submit cancel → `cancelled`。
- `tests/README.md` line 151："download / preprocess 在 durable create 后、executor submit 前观察 cancellation token 并标记 job cancelled 且不提交后台操作"——已从 "job cancelling" 更新为 "job cancelled"。
- 状态机图中 `cancelling` 仍作为中间态保留（`queued -> cancelling`、`running -> cancelling -> cancelled`），这是正确的——`cancelling` 仍是 `request_cancel` 后、后台 pipeline 收口前 的有效非终态。create-before-submit cancel 的直接 `queued -> cancelled` 路径由 prose 描述而非状态机图，属于合理的文档分层。

### 6. fix artifact 记录的 pytest 和 pyright 结果是否可信

**已验证通过。**

- `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` → **48 passed, 0 failed**（3 个已有的 `edgar` deprecation warning，与本次修改无关）。与 fix artifact 记录一致。
- `pyright dayu/fins/ingestion_runtime.py dayu/fins/tools/download_tools.py dayu/fins/tools/preprocess_tools.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py` → **0 errors, 0 warnings, 0 informations**。与 fix artifact 记录一致。

## Findings Status Summary

| Finding | 来源 | 最终状态 | 证据 |
|---|---|---|---|
| S1-F1 `_create_queued_job` 死代码 | AgentDS F1 | **已修复** | `rg` 全仓无匹配；`start_download`/`start_preprocess` 直接使用 `_create_queued_record_with_start_lock` |
| S1-F2 create-before-submit cancel → CANCELLING orphan | AgentDS F2 | **已修复** | `_save_cancelled(start.record)` 直接终端化为 `CANCELLED`，不 submit |
| S1-F3 `token.check_count == 2` 断言对 checkpoint 数量敏感 | AgentDS F3 | **已修复** | 测试仅断言 `CANCELLED`、`cancellation_requested`、`executor.operations == []` |
| S1-F4 `_CancelOnSecondCheckToken` metadata 不一致 | AgentDS F4 | **已修复** | `cancel_reason()` 和 `requested_at()` 基于 `_cancelled` flag 一致返回 |

## Open Questions

无。

## Residual Risk

| ID | 状态 | 说明 |
|---|---|---|
| S1-R1 | deferred-with-owner (WU-WAIT-03) | 跨进程并发 cancel + submit 的 orphan 窗口仍存在（`_start_lock` 是 threading.Lock，不跨进程），deferred 到两阶段启动。 |
| S1-R2 | accepted limitation | submit 后 Host token 无法物理抢占正在执行的同步 I/O；后台仍通过 job store durable cancel 观察。 |
| S1-R3 | out of scope (Slice 2/3/4) | Web / Doc / Fins read tools token 传播不属于 Slice 1。 |

## Slice 1 准入裁决

S1-F1 到 S1-F4 全部已修复，无 blocking finding。fix artifact 记录的 pytest 和 pyright 结果已独立复核通过。

**Slice 1 可进入 accepted slice commit。**
