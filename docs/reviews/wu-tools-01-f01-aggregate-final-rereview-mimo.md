# WU-TOOLS-01-F01 Aggregate Final Review Rereview

## Gate Metadata

- Work unit: `WU-TOOLS-01-F01`
- Gate: aggregate final review fix rereview
- Accepted finding: `F01-AGG-001`
- Fix artifact: `docs/reviews/wu-tools-01-f01-aggregate-final-fix-codex.md`
- Inputs: `dayu/fins/ingestion_runtime.py` diff, `tests/fins/test_fins_ingestion_runtime.py` diff, controller adjudication, DS review, mimo review, codex fix artifact
- Review date: 2026-06-07

## Conclusion

**pass**

F01-AGG-001 已正确修复。queued -> running claim 与 cancellation 判断/写入已在 Fins job store 单次原子文件锁边界内完成。修复不引入新的 correctness、stability 或 maintainability 风险。无 blocker。

## Findings

未发现新的实质性问题。

### 观察项（不阻塞）

#### OBS-1 (Info) — `_save_cancelled` 仍使用 `save_job` 而非原子终态方法

- **File**: `dayu/fins/ingestion_runtime.py:1813-1835`
- **Evidence**: `_save_cancelled` 直接调用 `self.job_store.save_job(...)` 而非 `save_succeeded_or_cancelled`。`save_job` 不检查终态，理论上可在 `read_job` 与 `save_job` 之间被另一个终态写入覆盖。实际正确性无问题：`_save_cancelled` 调用点（`_run_preprocess_job:1203` 和 `_run_download_job:1251`）在 `read_job` 确认 `cancellation_requested` 后调用，且同一 pipeline 是该 job 的唯一终态写入者（除 `request_cancel` 外，而 `request_cancel` 只写 CANCELLING 不写终态）。
- **来源**: 已在 mimo aggregate final review residual §2 中记录，本次不重复判定。
- **建议**: 后续 job store 演进时统一使用 `save_succeeded_or_cancelled`。

## F01-AGG-001 修复正确性逐项验证

### 1. 协议层新增 `claim_running_or_cancelled`

**判断：正确。**

- `FinsIngestionJobStore` 协议（`ingestion_runtime.py:546-568`）新增 `claim_running_or_cancelled(job_id, *, started_at, updated_at) -> FinsIngestionJobRecord`。
- 签名与文档与已有的 `save_succeeded_or_cancelled` 对称：参数只传时间戳，不传 `record`；返回持久化后的 record。
- 协议 docstring 说明了 Args、Returns、Raises，符合编码硬约束。

### 2. 文件系统实现原子性

**判断：正确。**

`FsFinsIngestionJobStore.claim_running_or_cancelled`（`ingestion_runtime.py:782-826`）在单次 `_StoreFileLock` 内完成：

1. `_read_record_locked(job_id)` — 持锁读取当前状态。
2. `record.status in _TERMINAL_STATUSES` → 原样返回。
3. `record.cancellation_requested or record.status is CANCELLING` → 写入 CANCELLED，`finished_at=updated_at`，`cancellation_requested=True`。
4. 其它非终态 → 写入 RUNNING，`started_at=record.started_at or started_at`，`updated_at=updated_at`。

与 `save_succeeded_or_cancelled`（`ingestion_runtime.py:733-780`）使用相同的 `_StoreFileLock` + `_read_record_locked` + `_write_record_locked` 模式。锁边界内无异常路径泄漏。

### 3. `_mark_job_running_or_cancelled` 不再使用双锁路径

**判断：正确。**

旧实现（diff `-` 侧）：

```python
record = self.job_store.read_job(job_id)       # 第一次锁
if record.cancellation_requested or ...:
    return self._save_cancelled(record)         # 第二次锁
if record.status in _TERMINAL_STATUSES:
    return record
return self.job_store.save_job(replace(...))    # 第二次锁
```

新实现（`ingestion_runtime.py:1281-1286`）：

```python
now = _utc_now()
return self.job_store.claim_running_or_cancelled(
    job_id,
    started_at=now,
    updated_at=now,
)
```

单次调用，单次锁。`read_job` + `save_job` 双锁路径已完全消除。

### 4. `claim_running_or_cancelled` 状态转换正确性

**判断：正确。**

| 输入状态 | 条件 | 输出状态 | 时间戳处理 |
|---|---|---|---|
| 终态 (SUCCEEDED/FAILED/CANCELLED) | `status in _TERMINAL_STATUSES` | 原样返回 | 无写入 |
| CANCELLING 或 `cancellation_requested=True` | 取消条件命中 | CANCELLED | `updated_at=updated_at`, `finished_at=updated_at`, `cancellation_requested=True` |
| QUEUED/RUNNING (非终态、非取消) | 默认 | RUNNING | `started_at=record.started_at or started_at`, `updated_at=updated_at` |

与 `save_succeeded_or_cancelled` 的终态/取消判断逻辑一致。`started_at` 使用 `record.started_at or started_at` 保留首次进入 running 的时间，正确。

### 5. 回归测试有效性

**判断：有效。**

`_ClaimRaceJobStore`（测试文件 line 191-412）精确模拟旧 race：

- `claim_running_or_cancelled` 在首次遇到 QUEUED 状态时，内部调用 `request_cancel` 将状态改为 CANCELLING，然后重新读取，模拟 claim 窗口中的取消请求。
- `read_job` 同时保留了旧 read/save 窗口的取消模拟（首次读取 QUEUED 时调用 `request_cancel` 并返回旧 record），但修复后的 runtime 不再通过 `read_job` 进入 running，该路径不被触发。

回归测试 `test_claim_running_preserves_cancel_between_read_and_running_write`（测试文件 line 878-910）断言：

- `claim_running_calls == 1` — runtime 使用了新的原子 claim 方法。
- `save_job_calls == 0` — runtime 未使用旧 read/save 双锁路径。
- `record.status is CANCELLED` — 取消请求未被覆盖为 RUNNING。
- `record.cancellation_requested` — 取消标记被保留。

**不是 sleep race**：测试通过 `_ClaimRaceJobStore` 测试 double 在 claim 调用内部同步触发取消，不依赖 `time.sleep` 或线程调度时序。

**回归证明**：若 runtime 回退到旧 `_mark_job_running_or_cancelled` 实现（`read_job` + `save_job`），`claim_running_calls` 将为 0，`save_job_calls` 将为 1，测试断言失败。

### 6. AGENTS.md 合规检查

| 检查项 | 结果 | 证据 |
|---|---|---|
| 类型签名完整 | PASS | `claim_running_or_cancelled` 参数和返回值全部有类型注解 |
| 中文 docstring | PASS | 协议方法和实现均有完整中文 docstring（Args/Returns/Raises） |
| 无 `Any`/`object` | PASS | diff 中无新增 `Any` 或 `object` 类型 |
| 无兼容胶水 | PASS | 新方法是协议新增，非 wrapper/facade |
| 分层边界 | PASS | 只修改 `dayu.fins` 内部 job store 协议和实现，不触碰 Host/Engine/Service/UI |
| README no-update decision | PASS | codex fix artifact §README No-update Decision 逻辑成立：只修 job store 内部原子状态转换，README 未出现不一致 |
| 禁止魔法数字/字符串 | PASS | 无新增字面量 |
| 模块级私有辅助函数 | PASS | `_is_terminal_job_status` 是模块级测试 helper |

### 7. 新增 correctness/stability/maintainability 风险

**判断：无新增风险。**

- `claim_running_or_cancelled` 的逻辑与 `save_succeeded_or_cancelled` 对称，复用相同的锁和读写模式。
- 不改变 `request_cancel`、`save_succeeded_or_cancelled` 或其它 job store 方法的行为。
- 不引入新的跨组件依赖或状态泄漏。

## Verification Results

### pytest

```
source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py -v

143 passed, 3 warnings in 2.00s
```

### pyright

```
source .venv/bin/activate && pyright

0 errors, 0 warnings, 0 informations
```

### git diff --check

```
git diff --check

无输出，通过。
```

## README 判断

codex fix artifact 的 README no-update decision 成立：

- `dayu/fins/README.md`：不更新。只修 job store 内部原子状态转换；README 已描述 job store 存治理状态和 cancellation/wait adapter 边界，未出现不一致。
- `dayu/config/README.md`：不更新。provider config 形态无变化。
- `tests/README.md`：不更新。测试层级和运行方式无变化，仅新增同一测试文件内的 regression case。
- 根 `README.md`：不更新。未恢复 CLI/UI，也未新增用户可见命令。
- `dayu/README.md`：不更新。未改变稳定分层关系。

## Residual / Blocker

- **fixed in current fix gate**: `F01-AGG-001` queued -> running claim 与取消请求之间的 TOCTOU race 已通过 job store 原子 claim 修复。
- **assigned to later work unit**:
  - 真实 SEC/CN/HK 网络 download adapters。
  - upload ingestion provider。
  - SEC/Fins 与 CN/HK CI pipeline/smoke。
  - 未来 NEW CLI download/process wrapper。
- **blocker**: none。

## Gate Decision

**建议进入 accepted deepreview commit / ready-to-open-draft-PR gate。**

理由：

- Aggregate final review 唯一 accepted finding F01-AGG-001 已正确修复。
- 协议新增、文件系统实现、调用方简化、回归测试四方面全部验证通过。
- 指定 pytest 143 passed、pyright 0 errors、`git diff --check` 通过。
- 修复未扩大 F01 scope，未触碰 Host/Engine contracts、CLI/UI、真实网络 adapter。
- 无新增 correctness/stability/maintainability 风险。
- `WU-TOOLS-01-S4-R1` 仍可保持关闭。
