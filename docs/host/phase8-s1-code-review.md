# Host P8-S1 Code Review：Attempt Lease / Fencing Store 层

- 分支：`migration/host-p8-attempt-lease-recovery`
- 日期：2026-05-09
- 范围：`_attempt_lease.py`、`_internal_contracts.py`、`_durable_event_store.py` schema、`_run_state_store.py`、`test_phase8_attempt_lease_store.py`、`dayu/host/README.md`

## 结论

**通过，有 2 个 accepted findings 已修复，4 个低风险观察项已由总控判定为无需本轮修复或后移。**

P8-S1 store 层实现正确。FencingToken 全局单调 durable、owner secret / fencing token 语义分离完整、CAS 条件覆盖 plan 全部要求、typed result / error 无裸 SQLite 泄漏、测试覆盖 plan §16 全部 P8-S1 场景。Finding 1（`__all__` 遗漏）和 Finding 2（README 状态机同步）已修复并验证。

## 总控 Finding 状态

| Finding | Gateflow 状态 | 总控结论 |
|---|---|---|
| Finding 1：`AttemptLeaseStore` 未加入 `__all__` | `accepted` / `[已修复]` | 有效且属于 P8-S1，已加入 `__all__`。 |
| Finding 2：README 残留过时状态机描述 | `accepted` / `[已修复]` | 有效且属于 P8-S1，README 已同步当前 internal 状态与未接入边界。 |
| Finding 3：review 历史文档残留 `lease_generation` 术语 | `rejected-with-reason` | review 文档是 historical snapshot，不作为当前契约真源；当前 plan/design/code 已使用 `fencing_token`。 |
| Finding 4：`_diagnose_fence` fallthrough 到 `STORAGE_CONFLICT` | `rejected-with-reason` | 防御性 typed 收口合理，注释已说明理论不可达路径，不需要本轮修改。 |
| Finding 5：`AttemptLeaseStore` 放置位置与 plan §13 略有出入 | `rejected-with-reason` | `_attempt_lease.py` 承载契约，`_run_state_store.py` 承载 SQL store 实现更符合当前模块边界；plan §13 已允许修改 `_run_state_store.py` 的 CAS acquire / renew 查询。 |
| Finding 6：renew 成功返回 `ACQUIRED` 而非 `RENEWED` | `rejected-with-reason` | 这是 plan 内自洽的枚举设计；如后续 supervisor 需要区分再另行扩展。 |

## 审查维度

### 1. FencingToken 全局单调性

**通过。**

- `host_fencing_tokens` 表使用 `INTEGER PRIMARY KEY AUTOINCREMENT`（`_durable_event_store.py:118`），SQLite 严格保证全局单调递增。
- `_allocate_fencing_token`（`_run_state_store.py:584-620`）在 `BEGIN IMMEDIATE` 事务内 INSERT 取 `lastrowid`，不依赖 owner token / attempt_index / run_id / per-attempt generation。
- `FencingToken.__post_init__`（`_internal_contracts.py:52-60`）校验 `value > 0`，禁止构造非法 token。
- `test_fencing_token_strictly_monotonic_across_runs` 覆盖跨 run / 跨 attempt 单调性 + 不复用。
- `test_acquire_returns_busy_on_attempt_index_conflict` 覆盖 BUSY 后下一次 acquire token 仍严格更大（gap 允许）。
- 允许 gap（acquire 冲突 / 回滚导致），禁止倒退或复用。与 plan §6.1 / §6.2 一致。

### 2. Owner secret 与 fencing token 语义分离

**通过。**

- `AttemptOwnerToken.value`（明文）只在 `AttemptOwnerContext` 内存对象中流动。
- DB 只存 `owner_token_hash`（SHA-256 hex），`acquire_new_attempt` 调用 `owner_token.digest()`（`_run_state_store.py:402`）。
- `AttemptFencingError.__init__` 构造的 `super().__init__()` 消息只含 `attempt_id`、`run_id`、`reason`、`state`、`owner_id`、`fencing_token`，不含 owner token 明文。
- `masked()` 形如 `***abcd`，仅暴露末尾 4 位。
- `test_verify_owner_raises_typed_fencing_when_expired` 断言 `token.value not in str(err)`。
- CAS 校验同时检查 `owner_token_hash + fencing_token + lease_expires_at > now`，见 `renew` WHERE（`_run_state_store.py:488-503`）和 `verify_owner` WHERE（`_run_state_store.py:549-563`）。

### 3. Store API 是否符合 plan

**通过。**

- `AttemptLeaseStore` 不持有 `AttemptLeaseConfig`，只接收计算好的 `lease_expires_at`。
- `clock` 只用于 WHERE 子句取 `now` 与 fencing 判断时间，store 不在此处生成 lease 截止时刻。
- `_DEFAULT_LEASE_TTL_SECONDS` / `_DEFAULT_LEASE_RENEW_INTERVAL_SECONDS` 只用于构造 `DEFAULT_ATTEMPT_LEASE_CONFIG`，不是 store 运行时真源。
- plan §6.4 要求"store 只接收计算好的 `lease_expires_at`"，实现满足。

### 4. Fencing token `resource_id` 语义一致性

**通过。**

- plan §6.2 写 `resource_type='attempt', resource_id=attempt_id`。
- 实现 `_allocate_fencing_token`（`_run_state_store.py:607-619`）传入 `resource_id=attempt_id`。
- 测试 `test_acquire_inserts_running_attempt_with_owner_lease` 断言 `resource_id == "a1"`（即 attempt_id）。
- plan 和实现一致。

### 5. Schema 与状态机

**通过。**

- Schema（`_durable_event_store.py:117-160`）与 plan §6.2 完全一致：`host_fencing_tokens` 表 + `host_attempts` 新列 + 三个索引。
- `AttemptState`（`_internal_contracts.py:63-87`）已拆分 `STALE / RECOVERING / LOST`，无 `STALE_DIAGNOSTIC` 残留。
- 无 `lease_generation` / `GENERATION_MISMATCH` 残留在生产代码中（仅在 docs review 历史中出现）。
- `_ATTEMPT_TERMINAL_STATES` 包含 `LOST`，`_ATTEMPT_FINISHED_STATES` 包含 `STALE / RECOVERING / LOST`，与 plan 语义一致。
- 合法迁移由 plan §6.3 定义，store 层 CAS 条件强制执行。

### 6. 类型与编码约束

**通过。**

- 无新增 `Any` / `object`。
- `AttemptFencingError` 继承 `Exception`，使用显式 `__init__` 赋值属性，类型注解完整。
- `_row_to_attempt_record` / `_row_to_run_record` 使用 `# type: ignore[index]` 处理 `sqlite3.Row` 动态索引，这是 pyright 已知限制，可接受。
- 所有函数有完整中文 docstring。
- `frozen=True, slots=True` 用于所有 dataclass。

### 7. 测试覆盖度

覆盖 plan §16 要求的所有 P8-S1 场景：

| 场景 | 测试 |
|---|---|
| acquire 成功 + fencing_token + owner_token_hash | `test_acquire_inserts_running_attempt_with_owner_lease` |
| UNIQUE 冲突 -> BUSY | `test_acquire_returns_busy_on_attempt_index_conflict` |
| renew 延长 lease 不改 token | `test_renew_extends_lease_without_changing_fencing_token` |
| lease 过期 -> FENCED+LEASE_EXPIRED | `test_renew_fenced_when_lease_expired` |
| owner mismatch -> FENCED+OWNER_MISMATCH | `test_renew_fenced_on_owner_mismatch` |
| fencing token mismatch -> FENCED+FENCING_TOKEN_MISMATCH | `test_renew_fenced_on_fencing_token_mismatch` |
| terminal -> TERMINAL+ATTEMPT_TERMINAL | `test_renew_terminal_when_attempt_terminal_state` |
| verify_owner 通过 | `test_verify_owner_passes_for_valid_lease` |
| verify_owner lease 过期 | `test_verify_owner_raises_typed_fencing_when_expired` |
| verify_owner unknown attempt | `test_verify_owner_raises_owner_missing_for_unknown_attempt` |
| recovery attempt recovered_from | `test_acquire_records_recovered_from_attempt_id` |
| 跨 run 跨 attempt 单调性 | `test_fencing_token_strictly_monotonic_across_runs` |
| naive datetime 拒绝 | `test_acquire_rejects_naive_lease_expires_at` |
| token digest / masked | `test_owner_token_digest_and_masked` |
| config 校验 | `test_attempt_lease_config_validates` |
| FencingToken 正整数 | `test_fencing_token_rejects_non_positive` |

未覆盖（P8-S6 scope，不在 P8-S1 范围内）：

- `mark_stale_or_lost` 和 `mark_recovering_and_create_attempt` 未测试。
- `verify_owner` 在 owner_mismatch / fencing_token_mismatch 场景下只通过 renew 间接覆盖，没有独立的 verify_owner 测试。风险低，因为 verify_owner 和 renew 共享 `_diagnose_fence`。

## Findings

### Finding 1 [accepted / 已修复]：`AttemptLeaseStore` 未加入 `__all__`

- 严重度：低
- 文件：`_run_state_store.py:1000-1003`
- 描述：`__all__` 只导出 `AttemptStateStore` 和 `RunStateStore`，遗漏 `AttemptLeaseStore`。测试通过私有路径 `from dayu.host._run_state_store import AttemptLeaseStore` 导入，当前功能不受影响；但它是 P8 store 层的公共类，应加入 `__all__`。
- 建议：将 `"AttemptLeaseStore"` 加入 `__all__`。
- 修复状态：已加入 `dayu.host._run_state_store.__all__`。

### Finding 2 [accepted / 已修复]：README 残留过时状态机描述

- 严重度：中
- 文件：`dayu/host/README.md:427-438`
- 描述：README "当前状态机"段落仍写：

  > ```text
  > RUNNING -> SUCCEEDED
  > RUNNING -> FAILED
  > RUNNING -> CANCELLED
  > RUNNING -> SUSPENDED
  > ```
  >
  > 完整 `CREATED / QUEUED / WAITING / RECOVERING / CANCELLING / LOST` 治理状态尚未落地。

  但 P8-S1 已扩展 `AttemptState` 枚举到包含 `STALE / RECOVERING / LOST`，`_ATTEMPT_FINISHED_STATES` 和 `_ATTEMPT_TERMINAL_STATES` 已包含这些状态，store 层 CAS 已支持。虽然 P8-S1 不接入 harness 主路径，但枚举和 store 层已是当前代码事实。README 应同步更新。

- 建议：更新"当前状态机"段落，说明 P8-S1 已落地 `STALE / RECOVERING / LOST` 枚举与 store CAS 基础，尚未接入 harness 主路径。
- 修复状态：README 已同步 P8-S1 internal 状态与未接入边界。

### Finding 3 [rejected-with-reason]：review 历史文档残留 `lease_generation` 术语

- 严重度：低
- 文件：`docs/host/phase8-optimal-review.md`、`docs/host/phase8-open-review.md`
- 描述：这些 review 历史文档多处使用 `lease_generation`，但最终实现已替换为全局 `fencing_token`（`host_fencing_tokens` 表）。不影响代码正确性，但后续 reader 可能被误导。
- 建议：在 P8 文档收口 slice 中标注这些文档为 historical snapshot，或在文档头部注明术语已演进。
- 总控结论：不修。review artifact 是 historical snapshot，不能回写改写当时审查上下文；当前 `phase8-plan.md` / `design.md` / 代码已统一为全局单调 `fencing_token`。

### Finding 4 [rejected-with-reason]：`_diagnose_fence` fallthrough 到 `STORAGE_CONFLICT`

- 严重度：低
- 文件：`_run_state_store.py:721-731`
- 描述：当所有显式条件（terminal / not_running / owner_mismatch / fencing_token_mismatch / lease_expired）都不匹配但 `rowcount == 0` 时，fallthrough 到 `STORAGE_CONFLICT`。这个分支理论上不可达——如果 state=running + hash 匹配 + token 匹配 + lease 未过期，UPDATE 应该命中。但作为防御性编程可接受，注释已说明意图。
- 建议：无需修改。
- 总控结论：不修。该分支是理论不可达路径的 typed 防御性收口，优于抛裸 SQLite / RuntimeError。

### Finding 5 [rejected-with-reason]：`AttemptLeaseStore` 放置位置与 plan §13 略有出入

- 严重度：低
- 描述：plan §13 将 `AttemptLeaseStore` 归入 `_attempt_lease.py` 范围，但实现把它放在 `_run_state_store.py`。`_attempt_lease.py` 只放契约类型。这个拆分是合理的——store 实现共享 `HostStorage` / `HostStorageTransaction` / `_require_aware` 等基础设施，与 `AttemptStateStore` 同模块更自然。
- 建议：无需修改，但 plan §13 应在后续收口时更新以反映实际模块拆分。
- 总控结论：不修。`_attempt_lease.py` 保持契约模块，`_run_state_store.py` 承载 SQL store 实现，符合依赖边界；plan §13 已允许 `_run_state_store.py` 实现 CAS acquire / renew / close / recover 查询。

### Finding 6 [rejected-with-reason]：renew 成功返回 `ACQUIRED` 而非 `RENEWED`

- 严重度：低
- 文件：`_run_state_store.py:504-521`
- 描述：`renew` 方法在成功时返回 `AttemptLeaseDecision.ACQUIRED`。Plan §6.1 的 `AttemptLeaseDecision` 只有 `ACQUIRED / BUSY / TERMINAL / FENCED` 四个值，没有 `RENEWED`。这是 plan 本身的决策——renew 成功复用 `ACQUIRED` 枚举。语义上略有歧义（acquire vs renew），但当前设计是自洽的。
- 建议：无需修改。如果后续 supervisor 层需要区分 acquire 和 renew 成功，可在那时新增 `RENEWED` 枚举值。
- 总控结论：不修。当前 `AttemptLeaseDecision` 只区分成功 / busy / terminal / fenced，renew 成功复用 `ACQUIRED` 与 plan 一致。

## 验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_phase8_attempt_lease_store.py -v
python -m pyright
```
