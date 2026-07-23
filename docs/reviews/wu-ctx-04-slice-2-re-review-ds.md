# WU-CTX-04 Slice 2 独立 code re-review（AgentDS）

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`2/3`
- accepted baseline：`eda1d70eb2c2252570807e1fcdb1cd234a5aae7a`
- reviewed range：accepted Slice 1 baseline 至当前 working tree（未提交）
- previous review-fix artifact：`docs/reviews/wu-ctx-04-slice-2-review-fix-codex.md`
- Controller adjudication（本 re-review 的输入）：`docs/reviews/wu-ctx-04-slice-2-code-review-controller-adjudication.md`
- scope amendment：`docs/reviews/wu-ctx-04-slice-2-scope-amendment-controller.md`
- task：只读审查，不得修改 production/test/control/plan/fix artifact
- 可运行验证但不得改代码
- 本 review 不读取或引用 AgentMiMo 本轮结论

## Re-review methodology

本 re-review 严格遵循以下原则：

1. **不从原结论推理**：每条 finding 都从 direct control flow 重新验证，不假设原 Controller adjudication 或 AgentCodex 修复已正确。
2. **孤立 durable row = malformed state**：EventLog row 本身就是状态机证据。缺失 owner 不等于 row 可忽略 —— 只有通过 strict request/identity/sequence/schema 校验并确认属于 reactive operation 的 rows 才能从 proactive projection 隔离。
3. **corruption 路径 fail closed**：任何损坏/mismatch/unknown 状态必须投影为 INVALID 且 provider 零调用。无法安全构造 fallback identity 时，只能用既有 governance failure 收口 Run。

## Direct control flow verification

### CTRL-S2-001：zero-proactive-request early return

#### 原始缺陷

原 `_project_state(...)` 第一遍只扫描 request rows，随后在 `len(requested_rows) == 0` 时直接返回 `_absent_state()`。第二遍对 compactor manifest、rejection、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED` 的 strict owner/sequence/payload 校验完全未执行。

#### 当前控制流逐路径验证

**路径 A：无 request + orphan rejection/terminal（`test_orphan_non_request_row_without_request_is_invalid`）**

1. `_project_state` 第一遍（line 377-396）：遍历全部 rows，按 `event_type != CONTEXT_COMPACTION_REQUESTED` continue。因为没有任何 request row，`requested_rows` 保持为空 `[]`。`operation_owners` dict 也为空 `{}`。
2. `_project_state` 第二遍（line 430-598）：对于 orphan rejection（`CONTEXT_COMPACTION_ATTEMPT_REJECTED`）：
   - `validate_context_compaction_attempt_rejected_payload` 通过（payload 格式正确）
   - `_required_text(payload, "operation_id")` → ID="orphan-operation-without-request"
   - `_required_operation_owner(operation_owners={}, operation_id="orphan-operation-without-request", ...)` → `operation_owners.get(...)` 返回 `None` → **`raise HostDurableError("proactive rejection operation is unknown")`**
3. 异常从 `_project_state` 透传到 `read_proactive_compaction_projection` line 310 的 `except (HostDurableError, TypeError, ValueError)`。
4. `_earliest_safe_proactive_operation_id(rows, ...)` — 没有 valid proactive request → 返回 `None`。
5. `_terminal_evidence(rows)` → 返回 `(None, failed_sequence)`（提取到 raw terminal 证据）。
6. 构造 `_invalid_state(operation_id=None, reason="HostDurableError", ...)`。
7. `_decision_from_state` 对 INVALID → `FAIL_EXISTING_OPERATION`。

**结论**：orphan row 正确被转成 INVALID → FAIL_EXISTING_OPERATION，没有经过 ABSENT → CREATE_NEW。✅

**路径 B：合法 reactive-only request/history（`test_valid_reactive_only_history_remains_absent`）**

1. 第一遍：reactive request 通过 `_validated_request_owner` 校验，`operation_owners` 注册为 `{reactive_operation_id: _CompactionOperationOwner(trigger_source=REACTIVE, ...)}`。`requested_rows` 仍为空（trigger_source 不是 PROACTIVE）。
2. 第二遍：failed terminal row：
   - `_required_text(payload, "operation_id")` → reactive_operation_id
   - `_required_operation_owner` → 找到 reactive owner
   - `row_owner.trigger_source is REACTIVE` → **continue（隔离）**
3. 第二遍完成，`operation_id` 仍为 `None`（没有 proactive request）→ `_absent_state()`。
4. Decision：ABSENT → `CREATE_NEW`。

**结论**：reactive-only history 正确隔离，不影响 proactive projection。✅

**路径 C：合法 reactive request + unknown-operation row（`test_reactive_request_with_unknown_operation_row_is_invalid`）**

1. 第一遍：reactive request 注册到 `operation_owners`。
2. 第二遍：failed terminal row with `operation_id="unknown-operation"`：
   - `_required_operation_owner` → `operation_owners` 中没有 "unknown-operation" → **`raise HostDurableError`**
3. → INVALID with `operation_id=None`。

**结论**：reactive request 不能为 unknown-operation row 提供"已知 owner"保护，unknown row 正确触发 INVALID。✅

**路径 D：malformed request 不误用 reactive id（`test_malformed_request_does_not_reuse_earlier_reactive_identity`）**

1. 第一遍：
   - Row 1（reactive request）：通过 `_validated_request_owner`，注册到 `operation_owners`。
   - Row 2（malformed proactive request, `payload={"trigger_source": 7}`）：`_validated_request_owner` 调用 `ContextCompactionTriggerSource("7")` → **`ValueError` 从第一遍直接抛出**。
2. `read_proactive_compaction_projection` 的 except 捕获 `ValueError`。
3. `_earliest_safe_proactive_operation_id`：
   - Row 1：`_validated_request_owner` 通过 → trigger_source 是 REACTIVE → skip
   - Row 2：`_validated_request_owner` 抛 ValueError → except → skip
   - 返回 **`None`**
4. INVALID with `operation_id=None`。不误用 reactive id。

**结论**：安全 proactive id 提取正确排除 malformed 和 reactive request。✅

**路径 E：dispatcher 无安全 id 时 zero side-effect（`test_pre_start_governance_without_safe_operation_id_fails_run`）**

dispatcher `_run_pre_start_governance` 中（dispatch.py diff lines 59-135）：
```python
if projection.decision is ProactiveCompactionDecision.FAIL_EXISTING_OPERATION:
    operation_id = projection.state.operation_id
    if operation_id is None:
        return _GovernanceStageResult(
            pending_dispatch=None,
            compact_accepted=None,
            terminal_notice=self._fail_unstarted_in_transaction(
                transaction, run,
                reason=_GOVERNANCE_FAILURE_REASON,
                error_code=_PROACTIVE_INVALID_OR_EXHAUSTED_REASON,
                message="Proactive compaction history has no safe operation identity",
            ),
        )
```

- `pending_dispatch=None` → 不创建新 Attempt/dispatch
- `compact_accepted=None` → 不创建 compacted closeout
- `_fail_unstarted_in_transaction` → Run 标记为 FAILED
- 不追加 `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTION_FAILED`、`CONTEXT_COMPACTED`
- `compactor.calls == 0` → provider 零调用

测试断言精确验证：compactor.prepared_requests 为空、attempt_count=0、Run status=FAILED、三种 compaction event type 计数不变。

**结论**：dispatcher 在无安全 proactive id 时零 provider side effect，只用 governance failure 收口 Run。✅

#### CTRL-S2-001 反例矩阵验证结果

| 反例组 | 测试 | projection phase | operation_id | decision | 通过 |
| --- | --- | --- | --- | --- | --- |
| 无 request + orphan rejection | `test_orphan_non_request_row...[REJECTED]` | INVALID | None | FAIL_EXISTING | ✅ |
| 无 request + orphan failed terminal | `test_orphan_non_request_row...[FAILED]` | INVALID | None | FAIL_EXISTING | ✅ |
| 无 request + orphan compactor manifest | `test_orphan_compactor_manifest_without_request_is_invalid` | INVALID | None | FAIL_EXISTING | ✅ |
| 合法 reactive-only history | `test_valid_reactive_only_history_remains_absent` | ABSENT | None | CREATE_NEW | ✅ |
| reactive request + unknown-row | `test_reactive_request_with_unknown_operation_row_is_invalid` | INVALID | None | FAIL_EXISTING | ✅ |
| malformed request 不误用 reactive id | `test_malformed_request_does_not_reuse_earlier_reactive_identity` | INVALID | None | FAIL_EXISTING | ✅ |
| dispatcher 无安全 id | `test_pre_start_governance_without_safe_operation_id_fails_run` | n/a | n/a | Run FAILED / 0 provider | ✅ |

#### CTRL-S2-001 判决：**FIXED**

### F-DS-01：recovery nested work lease

#### 原始问题

`SessionNewWorkAccessPort.try_acquire_new_work_lease` 与 registry implementation 的 docstring 声称只允许 `ACTIVE RW`，但 production target-recovery 的 committed-batch wake 会在 root recovery lease 仍持有时调用 scheduler wake，继而在 `RECOVERING + new_work_lease_count > 0` 下取得嵌套 work lease。

#### 当前实现验证

**Protocol docstring（`session_attachment.py` line 195-198）**：
```
ACTIVE RW 可直接取得 lease；RECOVERING RW 仅在 root recovery lease
仍持有时允许嵌套取得，避免无 recovery owner 的外部工作进入半状态。
```

**Implementation docstring（line 494-496）**：
```
ACTIVE RW 可直接取得 lease；RECOVERING RW 仅在 root recovery lease
仍持有时允许嵌套取得，root lease 释放后恢复拒绝。
```

**Implementation control flow（lines 508-518）**：
```python
if (
    record is None
    or record.state not in (
        _AttachmentLifecycleState.RECOVERING,
        _AttachmentLifecycleState.ACTIVE,
    )
    or record.access_mode is not HostSessionAccessMode.READ_WRITE
):
    return None
if (
    record.state is _AttachmentLifecycleState.RECOVERING
    and record.new_work_lease_count == 0
):
    return None
```

三段状态机：
1. `RECOVERING + new_work_lease_count == 0` → 拒绝（root lease 不存在）
2. `RECOVERING + new_work_lease_count > 0` → 允许（root lease 存续期间嵌套）
3. `ACTIVE` → 允许（root lease 已释放，record 已转为 ACTIVE）

**测试验证（`test_recovering_record_only_allows_allocation_recovery_work`）**：
```python
recovery_lease = allocation.acquire_recovery_work_lease()
# Stage 1: root lease exists → nested succeeds
nested_lease = registry.try_acquire_new_work_lease("session-1")
assert isinstance(nested_lease, SessionWorkLease)
nested_lease.release()
# Stage 2: root lease released → nested fails
recovery_lease.release()
assert registry.try_acquire_new_work_lease("session-1") is None
```

#### F-DS-01 判决：**FIXED**

### MIMO-REVIEW-001：`_close_owned_resources` docstring

#### Controller 裁决

只修正 docstring，明确 mandatory 阶段错误立即阻断后续 owner close；进入 best-effort 阶段后才"全部安全 cleanup 尝试后传播首错"。不得改变控制流和 `mark_closed()` 条件。

#### 当前实现验证

**Docstring（`open_host.py` lines 1514-1521）**：
```
mandatory 阶段失败会立即阻断后续 owner close，并保留 Host 的
``CLOSING`` retry contract；只有 mandatory 阶段全部成功后才进入
best-effort owner 阶段。进入 best-effort 阶段后会尝试全部安全 cleanup，
最终传播其中首个错误。
```

**控制流验证**：
- Mandatory 阶段（lines 1524-1535）：任何步骤失败立即传播，不进入后续步骤。
- Best-effort 阶段（lines 1537+）：每个步骤独立 try/except，收集首个错误但继续执行后续 cleanup。

控制流与 Slice 2 implementation artifact 记录的 close order 一致，`release_host_close()` 仍在 `scheduler.close()` 之后（保证 STOPPED 先于 mutex 释放）。

#### MIMO-REVIEW-001 判决：**FIXED**（docstring 已修正，控制流未变）

## 新增 diff 质量检查

### correctness

1. **`_earliest_safe_proactive_operation_id` 的正确性**（`proactive_compaction.py` lines 931-962）：
   - 只处理 `CONTEXT_COMPACTION_REQUESTED` rows
   - 每个 request 都用同一 strict `_validated_request_owner` parser
   - malformed request（`HostDurableError`/`TypeError`/`ValueError`）→ except → skip
   - reactive request → trigger_source 不是 PROACTIVE → skip
   - 返回第一个 valid proactive operation_id
   - 没有 valid proactive request → `None`

   验证通过。不引入兼容 parser，是同一 semantic owner 的复用。

2. **dispatcher FAIL_EXISTING_OPERATION 两个子分支**（dispatch diff lines 59-135）：

   **分支 2a：`operation_id is None`** → `_fail_unstarted_in_transaction`（Run FAILED，零增量）

   **分支 2b：`operation_id is not None` 但有 terminal 证据** → 同样 `_fail_unstarted_in_transaction`

   **分支 2c：`operation_id is not None` 且无 terminal 证据** → `_append_compaction_failed_with_proactive_fallback`（写 FAILED terminal + fallback dispatch）

   三个分支覆盖了所有 FAIL_EXISTING_OPERATION 子情况。分支 2c 正确使用了 safe proactive id（不是 reactive id），并正确传递 `attempt_count`（prepared ∪ rejected 的并集大小）和 `retry_repair_budget_exhausted=True`。

3. **scheduler close retry contract**（dispatch diff lines 707-818）：

   `_close_cleanup_done` 的语义从"cleanup 尝试过"改为"cleanup 成功完成"。关键标志位：
   - `_host_instance_stopping_marked`：防止重复写 STOPPING
   - `_lane_close_done`：lane 已关闭不重复关闭
   - `_host_instance_stopped_marked`：防止重复写 STOPPED
   - `_close_cleanup_done`：只在所有 mandatory 步骤成功后置 True

   测试 `test_scheduler_close_keeps_cleanup_incomplete_when_cleanup_raises` 验证：lane close 失败 → `_close_cleanup_done=False`，重试后成功。
   测试 `test_scheduler_close_retries_mandatory_residual_handle_before_stopped` 验证：handle close 失败 → STOPPING，重试 → STOPPED。
   测试 `test_scheduler_close_retries_stopped_write_without_reclosing_lane` 验证：STOPPED 写入失败 → STOPPING + lane 已关闭，重试 → STOPPED（不重新关闭 lane）。

### state machine

1. **Proactive operation phase 的封闭性**：`ProactiveCompactionPhase = ABSENT | INCOMPLETE | COMPACTED | FAILED | INVALID`。每个 phase 到 decision 的映射由 `_decision_from_state` 唯一确定，没有隐含 fallthrough。

2. **INVALID 的 terminal evidence**：`_invalid_state` 保留 `compacted_event_sequence` 和 `failed_event_sequence` 作为 raw terminal 证据。dispatcher 在 `operation_id is not None` 且 terminal evidence 存在时避免追加第二 terminal（分支 2b）。这是正确的 fail-closed 行为。

3. **Nested recovery lease 三段状态机**：已在前文 F-DS-01 节验证。

4. **Scheduler close 状态机**：
   ```
   RUNNING → (close called) → STOPPING → (mandatory cleanup success) → STOPPED
   ```
   任一步骤失败均保持在当前状态，允许重试。`STOPPED` 仅在全部 mandatory 步骤成功后写入。

   该设计保证了 accepted plan 的关键不变量：release_host_close()（释放 mutex）之前 scheduler 必须已完成 STOPPED 写入，fresh RW attachment 的 target recovery 才能以 STOPPED 作为 positive orphan proof。

### semantic ownership

所有 review-fix 变更均保持在 Controller adjudication 指定的 owner 边界内：

| 语义 | Owner | 修改文件 | 越界？ |
| --- | --- | --- | --- |
| proactive projection | `dayu/host/proactive_compaction.py` | 同一文件 | 否 |
| dispatcher decision 消费 | `dayu/host/dispatch.py` | 同一文件 | 否 |
| recovery nested lease contract | `dayu/host/session_attachment.py` | 同一文件 | 否 |
| close mandatory/best-effort docstring | `dayu/host/open_host.py` | 同一文件（仅 docstring） | 否 |
| projection owner 测试 | `tests/host/test_proactive_compaction_operation.py` | 同一文件 | 否 |
| dispatcher integration 测试 | `tests/host/test_dispatch_scheduler.py` | 同一文件 | 否 |
| lease state machine 测试 | `tests/host/test_session_attachment_registry.py` | 同一文件 | 否 |

没有引入第二套 integrity checker、兼容 parser、fallback operation id 或 default/alias。

### 测试真实性

1. **`test_orphan_compactor_manifest_without_request_is_invalid`**：使用真实 scheduler + real compactor + real manifest submit → 删除 request → 读取 projection。这是真实的 integration 路径，不是纯单元 mock。

2. **`test_pre_start_governance_without_safe_operation_id_fails_run`**：注入 corrupted request（`{"trigger_source": 7}`）后走完整 `run_queue_promotion` → `_run_pre_start_governance` → `read_proactive_compaction_projection` → dispatcher decision 路径。断言 Run status、compactor calls、event types 均为零增量。

3. **`test_malformed_request_does_not_reuse_earlier_reactive_identity`**：真实写入两条 request row（一条 valid reactive + 一条 malformed proactive），走完整 `_project_state` → exception → `_earliest_safe_proactive_operation_id` 路径。

4. **Crash-resume tests**：使用 `_CrashAtPreparedAttemptCompactor` 的 `BaseException` 子类（`_SimulatedProactiveCrash`）模拟 manifest 后进程 crash，避免 `Task.cancel()` 与合法业务取消的次序竞争。这是正确的测试设计。

### 过度耦合检查

1. **测试间的 import 依赖**：`test_dispatch_scheduler.py` 新增的 projection 相关测试使用 `read_proactive_compaction_projection` 的 public import（来自 `dayu.host.proactive_compaction`），不是 private import 或跨测试模块引用。符合。

2. **`ExplicitFakeSessionAccess`**：`test_dispatch_scheduler.py` 使用 `tests/host/fake_session_access.py` 中的 fake access port。这是测试辅助模块，不是 production 代码。符合测试夹具模式。

3. **测试不绑定 production 内部实现细节**：测试断言的是 typed decision、phase、operation_id 和事件计数，不绑定 `_project_state` 内部实现（如 `requested_rows` 的内部列表结构）。

## 新 findings

### N-DS-01：非 request row 缺少直接 session_id/run_id identity 校验（Low / observation）

**位置**：`dayu/host/proactive_compaction.py:_project_state` lines 377-396 vs 430-598

**证据**：
- 第一遍（line 380-381）对每个 `CONTEXT_COMPACTION_REQUESTED` row 执行 `row.session_id != session_id or row.run_id != run_id` 校验。
- 第二遍处理 rejection/terminal/runner-call rows 时没有同等的顶层 identity 校验。

**分析**：
- 对于 manifest rows：`identity.parent_session_id` 和 `identity.parent_host_run_id` 提供了间接校验。
- 对于 rejection/terminal rows：操作通过 `_required_operation_owner` 关联到已验证的 request owner 来间接保证，但没有直接校验 row 自身的 session_id/run_id。
- 当前 EventLog 写入路径保证同一 run_id 始终对应同一 session_id，SQLite FK 约束也阻止跨 session 的 row 污染。

**实际影响**：在正常 EventLog 语义下不可达。SQLite 事务和 schema 约束阻止了跨 session/run identity mismatch。但 strict reader 原则被轻微削弱：如果未来 EventLog 模型允许跨 session 读取，当前代码不会捕获非 request row 的 identity mismatch。

**严重度**：Low。当前 schema/transaction 模型下不可利用，且现有 manifest identity 校验已提供独立防线。

**建议**：不阻塞 Slice 2。可以在后续 work unit 中将 identity 校验统一到第二遍循环入口，使 strict reader 对所有 row type 一致。

### N-DS-02：INVALID reason 丢失具体语义（Low / observation）

**位置**：`dayu/host/proactive_compaction.py:read_proactive_compaction_projection` line 310-326

**证据**：
```python
except (HostDurableError, TypeError, ValueError) as exc:
    ...
    state = _invalid_state(..., reason=exc.__class__.__name__, ...)
```

`reason` 仅保存异常类名（如 `"HostDurableError"`），不区分 `"proactive rejection operation is unknown"` vs `"proactive manifest is missing proactive request owner"` 等具体根因。

**分析**：
- 类名作为 stable reason 符合"不嵌入 durable 原文"的要求。
- dispatcher decision 是二值的（`FAIL_EXISTING_OPERATION`），不需要区分具体原因。
- 实际诊断信息在 exception 的 logging 中可得。

**实际影响**：运维诊断时需查日志才能确定具体损坏原因。不影响正确性。

**严重度**：Low。

**建议**：不阻塞 Slice 2。可考虑将 `invalid_reason` 改为更细粒度的 enum member，但当前设计已满足 fail-closed 要求。

## 残余风险分类

| 风险 | 分类 | Owner | 说明 |
| --- | --- | --- | --- |
| `read_cancelling_runs` workspace-wide periodic path | `deferred-to-Slice-3` | WU-CTX-04 Slice 3 execution-owner cancel reconcile | Controller 已裁决，当前 `read_cancelling_runs` 仍有 3 处命中（定义、global watchdog 调用、owner 测试），Slice 3 Exact change 2 归零 |
| consumer task exception observation | `deferred-to-later-WU` | HostDispatchScheduler consumer-task lifecycle | 两路 review 未证明由 Slice 2 引入 |
| provider crash 不承诺 exactly-once | `deferred-to-later-WU` | provider/idempotency contract owner | manifest 已提交但 provider 结果未 durable 时保守消耗 budget 并从下一 schedule stage 恢复 |
| Windows native mutex 环境验证 | `deferred-to-later-WU` | cross-platform validation owner | POSIX 已验证；Windows 需在目标环境执行 `test_native_mutex.py` |
| 旧 config/request shape 迁移 | `deferred`（无 owner） | 无 | fresh schema 严格拒绝；无迁移路径 |
| 既有 ruff 告警 130 条 | `pre-existing` | 非本 Slice scope | baseline comparison 证明新增/扩散为 0 |

## 综合判决

| Finding | 状态 | 证据 |
| --- | --- | --- |
| CTRL-S2-001 | **FIXED** | 7 个反例全绿；投影对所有 orphan/unknown/malformed 行 fail closed；safe proactive id 不误用 reactive id；dispatcher 无安全 id 时零 side-effect |
| F-DS-01 | **FIXED** | docstring 三段状态机描述准确；测试直接证明 RECOVERING+0→拒绝、嵌套→成功、释放后→拒绝 |
| MIMO-REVIEW-001 | **FIXED** | docstring 明确 mandatory/best-effort 分界；控制流零修改 |
| N-DS-01 | **observation** | 非 request row 缺少顶层 identity 校验；当前 schema 下不可达 |
| N-DS-02 | **observation** | INVALID reason 仅含类名；不影响正确性 |

**Overall：pass-for-controller-adjudication**

修改文件全部在 Controller adjudication 允许的 7 个既有 production/test 文件范围内，没有新增文件（除本 artifact 外）。新增 behavior 分支全部由 focused owner/integration 测试执行，测试真实使用 production API 而非 mock private internal。

验证结果：
- Focused owner tests：138 passed
- Full Host suite：2133 passed, 1 skipped, 6 deselected
- Full pyright：0 errors, 0 warnings, 0 informations
- `git diff --check`：pass

## 未验证项

本 re-review 未验证以下内容（不在此次 review scope 内或需要其他环境）：
- AgentMiMo 本轮结论（按 task 明确要求不读取）
- Windows native mutex（需要 Windows 环境）
- provider idempotency（需要 external provider 集成测试）
- 既有 130 条 ruff 告警的修复（不属于本 Slice scope）
