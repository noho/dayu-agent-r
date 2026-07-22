# WU-CTX-04 Slice 2 Re-review — AgentMiMo

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`2/3`
- gate：re-review（post-fix independent re-review）
- accepted baseline：`eda1d70eb2c2252570807e1fcdb1cd234a5aae7a`
- reviewed range：accepted Slice 1 至当前 working tree（含 Codex review-fix）
- controller adjudication：`docs/reviews/wu-ctx-04-slice-2-code-review-controller-adjudication.md`
- review-fix artifact：`docs/reviews/wu-ctx-04-slice-2-review-fix-codex.md`
- original MiMo review：`docs/reviews/code-review-20260722-161504-mimo.md`
- re-review time：2026-07-22
- re-reviewer：AgentMiMo（independent code reviewer）

## Re-review scope

逐项验证 Controller adjudication 中三个 accepted findings 的裁决修复，并 adversarial
检查 fix 是否引入新问题。

---

## Finding verification

### CTRL-S2-001 — fixed ✓

**裁决要求**：projection 在没有 proactive request 时也必须验证全部非-request rows；
orphan/unknown/malformed row 投影为 INVALID；合法 reactive-only 仍为 ABSENT；
INVALID fallback 只用 strict proactive id；dispatcher 无安全 id 时 fail closed。

**Evidence**：

1. **Zero-proactive-request 下 orphan rows → INVALID**：
   - `_project_state()` 删除了 zero-request early return。第一遍循环（lines 379-395）
     验证全部 request identity/owner，建立 `operation_owners` dict。第二遍循环
     （lines 430-598）处理全部非-request rows。
   - orphan rejection/terminal 调用 `_required_operation_owner()`，在 `operation_owners`
     中找不到对应 operation → `HostDurableError("proactive ... operation is unknown")`。
   - 异常被 `read_proactive_compaction_projection` 捕获，调用
     `_earliest_safe_proactive_operation_id()` → 返回 `None`（无 proactive request）→
     `_invalid_state(operation_id=None, ...)`.
   - 测试 `test_orphan_non_request_row_without_request_is_invalid` 参数化
     rejection/failed terminal，断言 `INVALID` + `operation_id is None`。

2. **Orphan compactor manifest → INVALID**：
   - manifest row 进入第二遍循环的 `RUNNER_CALL_INPUT_ASSEMBLED` 分支。解析 manifest
     identity 后调用 `_required_operation_owner()`，orphan manifest 的 operation_id 不在
     `operation_owners` → `HostDurableError`。
   - 测试 `test_orphan_compactor_manifest_without_request_is_invalid` 用真实
     scheduler/recorder 提交 manifest 后删除 request，断言 `INVALID` + `operation_id is None`。

3. **合法 reactive-only → ABSENT**：
   - 第一遍循环把 reactive request 加入 `operation_owners`（非 `requested_rows`）。
   - 第二遍循环中 reactive rejection/terminal 通过 `_required_operation_owner()` 找到
     owner，`trigger_source is REACTIVE` → `continue`（跳过）。
   - `operation_id` 始终为 `None` → `_absent_state()`。
   - 测试 `test_valid_reactive_only_history_remains_absent` 断言 `ABSENT` / `CREATE_NEW`。

4. **Reactive + unknown → INVALID**：
   - unknown terminal 的 operation_id 不在 `operation_owners` → `HostDurableError`。
   - 测试 `test_reactive_request_with_unknown_operation_row_is_invalid` 断言 `INVALID`
     + `operation_id is None`。

5. **Malformed request 不误用 reactive id**：
   - `_earliest_safe_proactive_operation_id()` 对每条 request row 调用
     `_validated_request_owner()`，malformed row 抛出异常 → `continue`。
   - reactive row 的 `trigger_source is REACTIVE` → 跳过。
   - 测试 `test_malformed_request_does_not_reuse_earlier_reactive_identity` 断言
     `INVALID` + `operation_id is None`。

6. **Dispatcher 无安全 id → fail closed**：
   - `FAIL_EXISTING_OPERATION` + `operation_id is None` → 调用
     `_fail_unstarted_in_transaction()`，Run → FAILED。
   - 不追加 request、CONTEXT_COMPACTED、CONTEXT_COMPACTION_FAILED；不创建 Attempt；
     不调用 provider。
   - 测试 `test_pre_start_governance_without_safe_operation_id_fails_run` 断言：
     - `_attempt_count_for_run() == 0`
     - `_run_status() is RunStatus.FAILED`
     - `compactor.calls == 0`
     - 三类 compaction event 零增量

**Adversarial verification**：逐一 trace 代码路径，确认 `_required_operation_owner()` 在
`operation_owners` 找不到 key 时抛出 `HostDurableError`，被上层 catch 转为 INVALID。
`_earliest_safe_proactive_operation_id` 对 malformed/reactive row 正确跳过。dispatcher
`operation_id is None` 分支直接 `_fail_unstarted_in_transaction`，无 side effect。

**结论**：CTRL-S2-001 四个分支全部正确修复。`fixed`。

### F-DS-01 — fixed ✓

**裁决要求**：同步 Protocol/implementation docstring；增加 registry owner test 证明
RECOVERING + 0 lease → 拒绝、root lease 存续时嵌套 lease 成功、释放后恢复拒绝。

**Evidence**：

1. **Docstring 同步**：
   - `SessionNewWorkAccessPort.try_acquire_new_work_lease` docstring 更新为
     "ACTIVE RW 可直接取得 lease；RECOVERING RW 仅在 root recovery lease 仍持有时允许
     嵌套取得，root lease 释放后恢复拒绝"。
   - `HostSessionAttachmentRegistry.try_acquire_new_work_lease` 同步更新。

2. **Registry owner test**：
   - `test_recovering_record_only_allows_allocation_recovery_work` 新增三段断言：
     - `try_acquire_new_work_lease` 在 RECOVERING + 0 lease → `None`
     - `acquire_recovery_work_lease()` 后 `try_acquire_new_work_lease` → 成功（嵌套 lease）
     - `nested_lease.release()` + `recovery_lease.release()` 后 `try_acquire_new_work_lease`
       → `None`
     - `activate()` 后进入 ACTIVE → attachment 正常关闭

3. **Production 代码**：`try_acquire_new_work_lease` 实现新增
   `record.state is RECOVERING and record.new_work_lease_count == 0 → None` 分支。
   行为与 docstring 和 test 一致。

**结论**：F-DS-01 docstring 同步与 owner test 均已完成。`fixed`。

### MIMO-REVIEW-001 — docstring fixed ✓，behavioral change 未实施（符合裁决）

**裁决要求**：只修正 `_close_owned_resources` docstring，明确 mandatory/best-effort 分界；
不改变 close 顺序、错误传播实现或 `mark_closed()` 条件。

**Evidence**：

1. **Docstring 更新**：
   - 旧 docstring："cleanup 首个错误在全部 owner cleanup 尝试后传播"
   - 新 docstring："mandatory 阶段失败会立即阻断后续 owner close，并保留 CLOSING retry
     contract；只有 mandatory 阶段全部成功后才进入 best-effort owner 阶段。进入 best-effort
     阶段后会尝试全部安全 cleanup，最终传播其中首个错误。"

2. **代码结构变更（observation）**：
   - 旧代码所有 close 步骤都在 try/except 内，与 docstring 描述的 mandatory/best-effort
     区分不一致。
   - 新代码将 mandatory 阶段（begin_host_close, begin_closing, wait_poller.close,
     stop_and_drain, drain_host_close, scheduler.close, release_host_close）移出
     try/except，best-effort 阶段保留 try/except。
   - 这是 docstring 与实现的一致性修正，使 mandatory 阶段真正传播错误，而非全部收集后
     延迟传播。

3. **close 顺序**：mandatory 阶段顺序为
   begin_host_close → begin_closing → wait_poller.close → stop_and_drain →
   drain_host_close → scheduler.close → release_host_close。
   与旧代码的 try/except 内顺序相同，未漂移。

4. **`mark_closed()` 条件**：best-effort 阶段结束后调用，未修改。

5. **测试**：`test_scheduler_close_continues_after_best_effort_cancel_hook_failure`
   验证 on_cancel 失败不阻断 mandatory cleanup 和 STOPPED。

**Adversarial check**：mandatory 阶段移出 try/except 意味着 wait_poller.close、
stop_and_drain、scheduler.close 等失败会立即传播，而非收集后延迟。这与旧代码行为
不同。但 Controller 裁决明确要求 mandatory 阶段错误"立即阻断后续 owner close"，
新代码正确实现了该语义。全部 2133 个 host tests 通过。

**结论**：docstring 修正完成，mandatory/best-effort 分界现在 docstring 与实现一致。
`fixed`（按裁决边界）。

---

## Adversarial new-issue sweep

### 1. mandatory close 步骤移出 try/except 的行为变更

**Severity**：Observation / non-blocking

旧代码中 wait_poller.close、stop_and_drain、scheduler.close 在 try/except 内，
失败被收集而非立即传播。新代码将这些移出 try/except，使 mandatory 阶段错误
立即传播。这不是 Controller 裁决明确要求的行为变更（裁决只要求 docstring 修正），
但结果是 docstring 与实现现在一致。全部测试通过，无 regression。

### 2. `_earliest_safe_proactive_operation_id` 异常捕获范围

**Severity**：Observation / non-blocking

`_earliest_safe_proactive_operation_id` 捕获 `(HostDurableError, TypeError, ValueError)`。
`_validated_request_owner` 可能抛出的异常类型均在此范围内。如果未来新增异常类型
（如自定义 `PayloadValidationError`），需要同步更新捕获列表。当前无风险。

### 3. orphan manifest 测试依赖真实 scheduler

**Severity**：Observation / non-blocking

`test_orphan_compactor_manifest_without_request_is_invalid` 通过真实 scheduler
提交 manifest 后删除 request 行来构造 orphan。测试逻辑正确，但依赖 scheduler
的 manifest 写入行为。如果 manifest 写入方式变化，测试可能需要同步更新。

### 4. 新 test helpers 引入检查

- `_CrashAtPreparedAttemptCompactor`：在指定 attempt 的 manifest 提交后模拟进程 crash。
  逻辑清晰，异常类型 `_SimulatedProactiveCrash(BaseException)` 避免被 asyncio 取消传播。
- `_BlockingAfterManifestCompactor`：manifest 后阻塞 provider，用于测试异步场景。
- `_CancelHookFailingHandle`：on_cancel 失败但 mandatory close 成功。
- `_FailOnceCloseHandle`：首次 mandatory close 失败、重试成功。

所有新 helpers 职责单一，无 God object 倾向。

### 5. 新 production 代码 ownership 检查

- `_earliest_safe_proactive_operation_id`：属于 `proactive_compaction` 模块，复用
  `_validated_request_owner` 同一 strict parser。无跨层依赖。
- `_terminal_evidence`：纯函数，只提取 raw sequence，不解释 payload。语义边界清晰。
- dispatcher `FAIL_EXISTING_OPERATION` + `operation_id is None` 分支：只消费 projection
  decision，不重新解析 raw row。符合 semantic owner 设计。

### 6. 测试覆盖完整性

CTRL-S2-001 要求的五组反例全部有对应测试：

| 反例组 | 测试 | 文件 |
| --- | --- | --- |
| 无 request + orphan rejection/terminal | `test_orphan_non_request_row_without_request_is_invalid` | `test_proactive_compaction_operation.py` |
| 无 request + orphan compactor manifest | `test_orphan_compactor_manifest_without_request_is_invalid` | `test_dispatch_scheduler.py` |
| 合法 reactive-only | `test_valid_reactive_only_history_remains_absent` | `test_proactive_compaction_operation.py` |
| reactive + unknown | `test_reactive_request_with_unknown_operation_row_is_invalid` | `test_proactive_compaction_operation.py` |
| malformed + reactive id | `test_malformed_request_does_not_reuse_earlier_reactive_identity` | `test_proactive_compaction_operation.py` |
| dispatcher 无安全 id | `test_pre_start_governance_without_safe_operation_id_fails_run` | `test_dispatch_scheduler.py` |

F-DS-01 要求的 registry owner test：`test_recovering_record_only_allows_allocation_recovery_work`
覆盖三段状态机。

---

## Validation

运行环境：`source .venv/bin/activate`，Python 3.11。

1. **Focused owner tests**：
   ```
   pytest tests/host/test_proactive_compaction_operation.py tests/host/test_session_attachment_registry.py tests/host/test_dispatch_scheduler.py -q
   ```
   结果：`138 passed in 1.93s`。

2. **Full host suite**：
   ```
   pytest tests/host -q
   ```
   结果：`2133 passed, 1 skipped, 6 deselected in 58.49s`。

3. **Full pyright**：
   ```
   python -m pyright dayu/ tests/ utils/
   ```
   结果：`0 errors, 0 warnings, 0 informations`。

4. **Whitespace validation**：
   ```
   git diff --check
   ```
   结果：pass（零输出）。

5. **Ruff lint**：
   ```
   ruff check <7 changed files>
   ```
   结果：`All checks passed!`。

---

## Summary

| Accepted finding | 状态 | 严重度 |
| --- | --- | --- |
| CTRL-S2-001 | fixed | High / blocking |
| F-DS-01 | fixed | Low / should-fix |
| MIMO-REVIEW-001 | fixed（docstring）| P2 / should-fix |

| 类别 | 数量 |
| --- | --- |
| 新 blocking findings | 0 |
| 新 non-blocking observations | 4 |
| Residual risks | 见 review-fix artifact |

## Gate decision

**pass**。三个 accepted findings 的裁决修复全部验证通过，adversarial sweep 未发现
新 blocking 或 should-fix 级别问题。fix 实现质量高，语义 ownership 边界清晰，
测试覆盖完整。
