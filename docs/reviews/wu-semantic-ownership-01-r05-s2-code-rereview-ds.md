# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Code Re-Review（AgentDS 第二路）

日期：2026-07-16
Reviewer：AgentDS（独立第二路 adversarial full re-review）
Initial review artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-ds.md`
Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-controller-adjudication.md`
AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-fix-codex.md`
Fix Controller validation：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-fix-controller-validation.md`
AgentMiMo initial review：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-mimo.md`

## Evidence baseline

冻结证据均一致：

- tracked transaction digest（9-file exact scope，不含 control doc）：`95f24a4e21e258e47d33bb1bafbe9d8fb25bcc3c2985941df6ed8f1bca123fc6` ✓
- new owner-test Git blob：`tests/host/test_durable_options.py` = `1c9c21a0df334709ba8dcb8188c48c5e7fdaa2fc` ✓

本 re-review 在 transition HEAD `e077c708` 的未提交 working-tree diff 上执行，读取了全部 production diff、test diff、smoke diff、README diff、untracked `test_durable_options.py`，以及所有前序 evidence chain artifacts（implementation → Controller validation → MiMo review → DS review → Controller adjudication → Codex fix → fix Controller validation）。

## Verdict

**PASS — 三项 accepted findings 均关闭，无新 material finding / blocker。**

三项 Controller-accepted 修复均忠实实现且边界正确。`HostDurableStoreOptionsSource` Protocol 是当前最小 dependency inversion；第二轮 observation blocked boundary 的 happens-before 证据链完整；三 gate 均有界 bounded 且 cleanup 保留。四项 no-fix observations 保持，scheduler residual / retained safety / deferred boundaries 均未被偷带。

---

## Finding ledger

### 三项 accepted findings 最终状态

| Finding | 初始状态 | 修复后状态 |
|---|---|---|
| MiMo-001 / DS-02：durable construction projection 重复 | accepted current | **CLOSED** — `project_host_durable_store_options` 成为唯一 typed projection owner，旧 `command.py` private helper 与 smoke `_durable_options()` 均已删除，8 个 call site 全部共用同一 helper |
| MiMo-002 / DS-01：smoke 穿透 `_wait_poller` / runner diagnostics | accepted current | **CLOSED** — `_WaitPollerDiagnosticsHost`、`cast`、`._wait_poller`、`observation_diagnostics_snapshot()`、`runner_dropped_count` 全部删除；late publication 证据改为第二轮 observation blocked boundary 的 public Run/outbox + durable Wait/claim facts |
| DS-05：首轮 fake `operation_finished.wait()` 无界 | accepted current | **CLOSED** — 三个 adapter gate 均通过 `_wait_for_poll_adapter_gate` 使用 `_TEST_OVERALL_DEADLINE_SECONDS` 有限等待，超时携带 gate 名诊断；`abort()` 在 finally 中释放全部 gate |

### 四项 no-fix observations 确认保持

| Observation | 初始结论 | Re-review 确认 |
|---|---|---|
| MiMo-003：单文件约 2200 行 | NO_STRUCTURAL_SPLIT | 保持。fix 已删除 `_durable_options`、`_WaitPollerDiagnosticsHost`、`cast` 等不再需要的代码，helper 职责分离清晰，无 God function |
| MiMo-004：`backoff_max == initial` | NO_FIX | 保持。smoke 只验证首次 retry（attempt=1），cap 不在此场景生效；S1 owner tests 拥有 backoff 算法 contract |
| DS-03：Engine fake 同 event loop | NO_FIX | 保持。独立 task 握手返回后继续、跨越 timeout 且未被取消，已直接证明 Engine timer ownership 边界 |
| DS-04：0.03s margin 理论 false negative | NO_FIX | 保持。durable state 成立后不瞬时消失，event/condition 驱动 + 15s overall deadline 提供充分 headroom |

---

## Adversarial challenge 逐项

### Challenge 1：`HostDurableStoreOptionsSource` structural Protocol + `project_host_durable_store_options`

**问：是否确属 durable construction owner 的最小 dependency inversion，是否违反"朴素直接参数优先"、造成新的 profile/god bag/上层语义泄漏、public symbol 扩张或反向依赖；command/open_host/smoke 是否真正只有一个 nested policy construction source。**

**答：确属最小 dependency inversion，不违反架构约束。**

**Owner 判定**：`OpenHostOptions` / `HostCommandHandleOptions` → `HostDurableStoreOptions` 的字段映射决定 Host durable connection 的 DB 路径、artifact 根目录、payload inline 阈值与 SQLite retry policy。这些是 durable storage construction 事实，只能由 `dayu.host.durable.options` 拥有。修复前 command.py 的 `_durable_options_from_public_options` 和 smoke 的 `_durable_options` 各自复制同一嵌套 policy 构造，形成第二/第三真源。

**Protocol 必要性分析**：

- `HostCommandHandleOptions`（command/admin opener）和 `OpenHostOptions`（execution opener / smoke）均为 frozen typed dataclass，但 `dayu.host.durable.options` 作为下层不能 import 任一上层 opener 类型。Protocol 让 durable owner 通过 structural typing 接收两种 options 而不产生反向依赖。
- Protocol 只声明 9 个 storage construction 字段（`db_path`、`artifact_root`、`create_parent_dirs`、5 个 `sqlite_*`、`payload_inline_threshold_bytes`），不声明 `host_handle_id`、`context_window_size`、`wait_poller_policy` 等上层字段——它是最小 storage projection surface，不是 god bag。
- 所有 9 个 field 语义内聚（均属于 durable storage construction），不存在"把无关字段塞进 Protocol 凑数"。
- 替代方案评估：
  - **9 参数朴素函数**：call site 需逐字段解构传入，8 个 call site 各写 9 个参数，增加了 boilerplate 且丢失 typed options 的 fail-closed 校验。不如 Protocol 简洁。
  - **中间 dataclass**：caller 需先构造中间 dataclass 再传入，等价于把投影逻辑搬到每个 caller，违背"唯一 typed projection source"目标。
  - **ABC / 显式继承**：要求 `OpenHostOptions` 和 `HostCommandHandleOptions` 显式继承同一个基类，这是上层类型修改，侵入性更大。

**朴素接口评估**：AGENTS.md 要求"优先使用直接传参数的朴素接口，使用 callback, factory, profile, query 等形式的接口需有充分理由"。Protocol 不属于 callback/factory/profile/query——它是 structural type annotation，函数签名仍是 `(options: HostDurableStoreOptionsSource) -> HostDurableStoreOptions`，等价于"接受具有这 9 个属性的任何 typed 对象"。充分理由已在上述必要性分析中给出。

**public symbol 扩张**：新增两个 public symbol——`HostDurableStoreOptionsSource`（Protocol）和 `project_host_durable_store_options`（函数）。两者均在 `dayu.host.durable.options` 模块内定义，该模块原本就是 durable store options 的 owner。没有新增模块、没有 re-export、没有修改 `dayu.host.__all__` 或 `dayu.host.api.__all__`。模块未定义 `__all__` 是预存状态（本模块和其他 durable 子模块的惯例不一致），不是 fix 引入。

**唯一 construction source**：8 个 call site 全部直接调用 `project_host_durable_store_options(...)`，不再存在任何重复投影：

| call site | 输入类型 |
|---|---|
| `command.py:create_host_command_handle` | `HostCommandHandleOptions` |
| `open_host.py:_OpenHostWaitPollerFactory` | `HostCommandHandleOptions` |
| `open_host.py:_ExecutionCommandHandleFactory` | `HostCommandHandleOptions` |
| `open_host.py:_AdminCommandHandleFactory` | `HostCommandHandleOptions` |
| `open_host.py:_OpenHostContextManager` | `HostCommandHandleOptions` |
| `smoke:_read_wait_record` | `OpenHostOptions` |
| `test_public_host_admin.py:_seed_nonterminal_runs` | `HostCommandHandleOptions` |
| `test_durable_options.py` | `HostCommandHandleOptions` |

旧 `_durable_options_from_public_options`（command.py private helper）和旧 smoke `_durable_options()` 在整个 `dayu/ tests/ utils/` 中零命中，完全删除，无兼容 wrapper。

**反向依赖检查**：`dayu.host.durable.options` 只 import `dataclasses`、`pathlib`、`typing.Protocol` 和同包 `errors`，不 import `dayu.host.api`、`dayu.host.command` 或任何上层模块。✓

**结论**：Protocol 设计合理，是当前约束下的最小 dependency inversion。不算新的 profile/god bag，不造成上层语义泄漏或反向依赖。

**次要观察（非 finding）**：Protocol 的 9 个 property docstring 均写 `:raises Exception: 具体实现可在读取失败时抛出`，但 frozen dataclass 的 attribute access 从不抛出。这是无害的模板文本，不构成 defect。

---

### Challenge 2：首轮 late Ready 已返回、第二轮 observation entered 且在返回 Ready 前阻塞、durable second claim active 的 happens-before

**问：是否足以证明第一轮没有发布权；是否存在第二轮 fake 自证、竞态、false pass，或仍需要不应暴露的内部 diagnostics。**

**答：证据链完整，足以证明首轮 late Ready 无发布权。**

**修正后的 happens-before 证据链**：

```
T1: 首轮 observation 启动 → first_observation_entered
T2: observation timeout (0.15s) → token invalidated → claim released → backoff written
    （durable: ADAPTER_ERROR/wait_observation_timeout, attempt=1, claim=None×4）
T3: 首轮 late Ready 返回（adapter 在 operation_finished + late_result_release gate 后返回 WaitPollReady）
    → token 已 invalidated → result dropped → late_result_released
T4: backoff (0.6s) 到期 → 第二轮 claim acquired（CAS, 四字段 active）
T5: 第二轮 observation 启动 → second_observation_entered
T6: 第二轮 adapter 在返回 Ready 前阻塞于 second_observation_release gate
    → ⬅ 证据边界 ⬅
T7: smoke 主流程在 T6 边界读取：
    - public Run.status = WAITING
    - durable Wait.status = WAITING
    - second claim 四字段 active (non-None)
    - poll_backoff_attempt = 1（未前进）
    - poll_last_outcome = ADAPTER_ERROR
    - poll_last_error_code = "wait_observation_timeout"
    - terminal_outbox = 空
T8: smoke 释放 second_observation_release → authoritative Ready → resolve → SUCCEEDED
```

**关键 happens-before 关系**：

- T3（首轮返回）happens-before T5（二轮进入），因为首轮 `late_result_released` event 在二轮 `second_observation_entered` 之前被发布，且 `_is_late_ready_rejected_at_second_observation_boundary` 谓词通过 `second_observation_release.is_set() == False` 确保二轮尚未返回。
- T4（二轮 claim active）happens-before T7（snapshot 读取），因为 durable claim acquisition 是同步 CAS 事务，写入在 `second_observation_entered` 发布之前完成，且谓词直接读取 durable Wait row。
- 因此在 T7 边界，首轮已完成且被丢弃、二轮已 claim 但未返回，任何首轮可能产生的 durable publication 都已可见。state 显示 `WAITING + second claim active + terminal_outbox=0` → 首轮无发布权。

**无 fake 自证**：第二轮 observation 的 claim acquisition 经过真实 durable CAS（`release_wait_record_poll_claim` + `claim_wait_record_poll_claim`），不是 fake 写入。claim 四字段（`poll_claim_id`、`poll_claim_owner_id`、`poll_claimed_at`、`poll_claim_expires_at`）由 Host poller 的真实 production 路径写入。

**无竞态**：T6→T7 边界由 `threading.Event` 保证：smoke 在 `second_observation_entered.wait()` 返回后、`second_observation_release` 仍为 False 时读取 state。由于 smoke 是唯一调用 `release_second_observation()` 的一方，此边界确定。

**无需内部 diagnostics**：修改完全删除了对 `_wait_poller`、`observation_diagnostics_snapshot()`、`dropped_count` 的依赖。首轮 late Ready 被丢弃的事实不再通过 runner internal counter 证明，而是通过 public/durable owner state 的 happens-before 边界证明。S1 owner-level runner test 继续拥有 `dropped_count` 内部诊断。

**false pass 风险**：低。若首轮 late Ready 错误地获得了发布权（即存在 production bug），则：
- `resolve_wait` 会被调用 → Run 变为 SUCCEEDED/FAILED/LOST
- 或 Wait record status 会改变
- 或 terminal outbox 会出现

`_is_late_ready_rejected_at_second_observation_boundary` 谓词断言这三者均未发生，且 `poll_backoff_attempt == 1` 确保没有额外的 observation 轮次。只有断言成立的组合才能使 smoke 继续。

**结论**：修正后的证据比原 `dropped_count` 方案更强——它不再依赖内部诊断 counter，而是依赖 public/durable owner 的持久事实和可观察状态边界。happens-before 链完整，无竞态、无 fake 自证。

---

### Challenge 3：三个 fake gate 的有限等待、overall deadline、Host close/drain 与 finally abort

**问：是否保证失败路径不泄漏 thread/task/store；错误是否可诊断。**

**答：保证。无泄漏，错误可诊断。**

**Gate bounded wait 分析**：

三个 provider-thread gate 均通过 `_wait_for_poll_adapter_gate(event, gate_name=...)` 同步，内部实现为：

```python
observed = event.wait(timeout=_TEST_OVERALL_DEADLINE_SECONDS)  # 15.0s
if not observed:
    raise RuntimeError(f"poll adapter gate timed out gate={gate_name} ...")
```

每个 gate 独立使用 15s budget。在正常路径中，gate 由 smoke 主流程在 overall deadline 内释放，adapter 侧不会超时。若 smoke 主流程崩溃（未执行 finally abort），adapter 线程在 15s 后抛出 `RuntimeError`，此异常被 poller supervisor 捕获并写为 `ADAPTER_ERROR` durable outcome。

**overall deadline 执行**：smoke 主流程的所有 phase wait 通过 `_remaining_seconds(phases)`（基于 `started_at + 15.0s`）使用剩余 budget。`_wait_for_async_event` / `_wait_for_thread_event` / `_wait_for_state` / `_wait_for_submit_result` 全部共享同一 deadline 源。

**Host close/drain**：`async with open_host(options) as host` 的 `__aexit__` 调用 `_HostHandle.close()`，依次 close wait poller（`asyncio.to_thread` join）、stop scheduler、drain actor、close stores。不依赖 smoke finally 做 Host 资源清理。

**finally abort**：

```python
finally:
    await operation.abort()     # set all events + cancel task + await
    if not submit_task.done():
        submit_task.cancel()
        await submit_task       # await cancelled task
```

`abort()` 释放 `late_result_release`、`second_observation_release`、`operation_finished` 三个 event，取消并 await operation task（捕获 `CancelledError`）。这确保即使 smoke 在任意 phase 失败，provider thread gate 均被释放，不会泄漏 daemon thread。

**task 泄漏检查**：
- `operation_task` 在 `abort()` 中 cancel + await ✓
- `submit_task` 在 finally 中 cancel + await ✓
- Engine Agent task 由 `async with` 的 Host close 清理 ✓
- poller 线程由 `_HostHandle.close()` → `_wait_poller.close()` → `asyncio.to_thread` join 清理 ✓

**错误可诊断性**：`_phase_failure` 输出 completed/pending phases、monotonic elapsed、Run status、wait record 的 9 个字段（status、claim 四字段、next_observe、backoff_attempt、last_outcome、last_error_code、poll_abandoned_at）、terminal outbox。adapter gate timeout 错误包含 gate 名称和 timeout 秒数。

**结论**：失败路径不泄漏 thread/task/store，错误充分可诊断。

---

### Challenge 4：新 owner tests、coverage、Engine no-diff、public chain、README、Ruff

**问：新 owner tests 是否断言 owner contract 而非复制实现；100% coverage 是否真实；Engine no-diff regression、public chain、README、Ruff 165→162 解释是否可信。**

**答：owner test 断言 owner contract。100% coverage 真实。所有指标可信。**

**owner test contract 分析**：

`test_durable_options.py` 共 9 个测试：

| 测试 | 断言对象 | 类型 |
|---|---|---|
| `test_project_host_durable_store_options_maps_every_storage_field` | 唯一 projection helper 精确映射 9 字段到 `HostDurableStoreOptions` + 嵌套 `PayloadStoragePolicy` / `HostSQLiteStoragePolicy` | **owner contract**：用 `==` 比较 projection 输出与手工构造的 expected，每个字段值从 source options 逐字段取，可与 source 做区分性验证 |
| `test_sqlite_policy_rejects_non_positive_busy_timeout` | `HostSQLiteStoragePolicy(busy_timeout_seconds=0.0)` 抛出 | dataclass validation（预存行为） |
| `test_sqlite_policy_rejects_negative_write_retry_count` | `HostSQLiteStoragePolicy(write_busy_retry_count=-1)` 抛出 | dataclass validation（预存行为） |
| `test_sqlite_policy_rejects_non_positive_retry_initial_delay` | `HostSQLiteStoragePolicy(write_retry_initial_delay_seconds=0.0)` 抛出 | dataclass validation（预存行为） |
| `test_sqlite_policy_rejects_non_positive_retry_multiplier` | `HostSQLiteStoragePolicy(write_retry_backoff_multiplier=0.0)` 抛出 | dataclass validation（预存行为） |
| `test_sqlite_policy_rejects_non_positive_retry_max_delay` | `HostSQLiteStoragePolicy(write_retry_max_delay_seconds=0.0)` 抛出 | dataclass validation（预存行为） |
| `test_payload_policy_rejects_artifact_root_without_name` | `PayloadStoragePolicy(artifact_root=Path("/"))` 抛出 | dataclass validation（预存行为） |
| `test_payload_policy_rejects_non_positive_inline_threshold` | `PayloadStoragePolicy(..., payload_inline_threshold_bytes=0)` 抛出 | dataclass validation（预存行为） |
| `test_durable_store_options_reject_db_path_without_name` | `HostDurableStoreOptions(db_path=Path("/"), ...)` 抛出 | dataclass validation（预存行为） |

测试 1 是直接 owner contract 断言。测试 2-9 断言三个 dataclass 的 `__post_init__` validation——这些 validation 之前未被单独测试（模块此前无直接 test），现在通过新增测试获得覆盖。`project_host_durable_store_options` 通过构造这些 dataclass 间接触发同一 validation，所以覆盖是真实可达的。

**100% coverage 真实性**：Controller 独立验证 `9 passed, dayu/host/durable/options.py: 100% (73 statements, 8 branches)`。73 statements 包括：3 个 validator 函数（~12 statements）、3 个 dataclass `__post_init__`（~30 statements）、`project_host_durable_store_options` 函数体（~10 statements）、Protocol 定义（0 statements——`...` 不算）、dataclass field 定义（~15 statements）、3 个 dataclass class 语句（~6 statements）。8 branches 来自 validators 中的 if 分支和 `__post_init__` 中的多个 validator 调用。所有 statements/branches 由测试 1-9 覆盖，覆盖是真实的。

**注意**：100% coverage 是整个模块级（包括预存的 dataclass validation），不只是 `project_host_durable_store_options` 函数。但函数本身也被测试 1 直接覆盖，验证了每个字段的正确映射。

**Engine no-diff**：`git diff HEAD -- dayu/engine/agent.py` 空输出——6 条 protected no-diff 路径全部确认。Engine regression test `test_accepted_awaiting_external_operation_outlives_handshake_timeout` 在现有 production 上首次即绿。

**public chain**：smoke 仍走 `ConfigLoader → provider discovery → Service composition → open_host → submit/wait → durable poller → public terminal/outbox`，只替换 worker/adapter 为 deterministic fake，未 self-implement Host timeout/backoff/terminal。

**README**：
- `dayu/host/README.md`：S2 原有 +2 行 observation timeout contract 保持准确，fix 未新增 stable public contract，不机械扩写 ✓
- `tests/README.md`：已更新 durable projection owner test 描述，public smoke 描述改为第二轮 observation blocked boundary 的 business owner facts ✓
- `dayu/engine/README.md`：已有 handshake timeout 边界，no diff ✓
- 根 README / `dayu/README.md`：无入口/分层/装配变化，no diff ✓

**Ruff 165→162**：Controller 独立确认：
- pre-fix full registry = 165
- post-fix full registry = 162
- `jq` 精确比较：删除的三条均为 touched-file F401：
  - `dayu/host/command.py` unused `AttemptStatus`
  - `dayu/host/command.py` unused `read_run_by_id`
  - `tests/host/test_public_host_admin.py` unused `create_host_command_handle`
- 无新增 rule/location/fingerprint，无 `noqa`、ignore 或 config 改动 ✓

**结论**：owner test 断言 owner contract（projection 全字段映射），100% module coverage 真实可达。所有指标解释可信。

---

### Challenge 5：Initial no-fix observations、retained safety、scheduler residual、deferred boundaries

**问：Initial no-fix observations 是否保持 no-fix；retained safety、scheduler residual、cancelled long-retry residual、Issue 175/callback/unified authorization/R06+ boundary 是否保持。**

**答：全部保持。无偷带、无弱化、无掩盖。**

**no-fix observations 确认**：

| Observation | 预期状态 | Re-review 确认 |
|---|---|---|
| MiMo-003（单文件规模） | no structural split | fix 已删除不再需要的 helper（`_durable_options`、`_WaitPollerDiagnosticsHost`、`cast` 路径），代码量净减少；helper 职责分离清晰 |
| MiMo-004（backoff_max==initial） | no fix | 仍为 `_TEST_INITIAL_BACKOFF_SECONDS`(0.6)，只验证 attempt=1，cap 不在此场景生效 |
| DS-03（Engine fake 同 event loop） | no fix | `_AwaitingExternalOperationExecutor._run_external_operation` 未被改为 `asyncio.to_thread`，测试设计未变 |
| DS-04（0.03s margin） | no fix | timing constants 未调整，仍为 `_TEST_RELATIVE_MARGIN_SECONDS = 0.03` |

**retained safety 确认**：
- `dayu/host/_wait_observation.py` — no diff（token invalidation / generation / lock 全部保持）
- `dayu/host/wait_adapter.py` — no diff（claim CAS / release / backoff 保持原 owner）
- cancellation、capacity、close-drain、typed LOST tests — no diff（全部保持）

**scheduler residual 确认**：
- `dayu/host/dispatch.py` — no diff
- `dayu/host/engine_ingest.py` — no diff
- `tests/host/test_dispatch_scheduler.py` — no diff
- deterministic probe 仍 `1 passed`（以 `HostApiError` 为预期 failure 证据）
- 未修、未隐藏、未 waive、未归 Issue 175

**deferred boundaries 确认**：

对当前 working tree 做 source scan：

```text
production added-lines 对以下关键词零命中：
  authorization, permission, callback transport, process isolation,
  process_backed, subprocess, Issue 175
```

- cancelled wait abandon observation 持续 timeout 时按 capped backoff 长期重试 → future Host durable evidence policy 拥有，R05 不发明 terminal evidence
- Issue 175 process isolation → 未实施
- callback transport / unified authorization → 未实施
- R06+ → 未进入

**结论**：四项 no-fix 保持，所有 retained safety / residual / deferred boundary 均未被本 fix 偷带、弱化或掩盖。

---

## 跨切面一致性检查

### 语义所有权修复是否完整

| 语义 | Owner | 修复前 | 修复后 |
|---|---|---|---|
| Durable store construction projection | `dayu.host.durable.options` | command.py private helper + smoke 独立复制 | 唯一 `project_host_durable_store_options`，8 call site 共用 |
| Late Ready publication authority | Host poller token invalidation | smoke 通过私有 `_wait_poller` + `dropped_count` 取证 | smoke 通过第二轮 observation blocked boundary 的 public/durable owner facts 取证 |
| Observation thread failure boundary | smoke fake adapter | `operation_finished.wait()` 无界 | `_wait_for_poll_adapter_gate` 有限等待 + 诊断 gate 名 |

### 项目指令合规

| 约束 | 状态 |
|---|---|
| 语义所有权：唯一清晰 owner | ✓ durable construction projection owner 唯一，late publication 证据从 public/durable owner 读取 |
| 朴素接口优先 | ✓ Protocol 有充分理由（见 Challenge 1），不是 callback/factory/profile/query |
| 禁止兼容性代码 | ✓ 旧 private helper 已删除，无 wrapper/facade/re-export |
| 禁止反向依赖 | ✓ `durable.options` 不 import 上层 |
| 不做过度设计 | ✓ 最小 typed helper + Protocol，不新增模块/层/registry |
| LLM-facing 文本 | N/A — 本 fix 不涉及 prompt/schema/LLM text |
| 测试断言 owner contract | ✓ test 1 逐字段断言 projection |
| 禁止 hasattr/getattr | ✓ smoke 零命中 |
| docstring | ✓ 所有新增函数有完整中文 docstring |

### 跨 artifact 一致性

- fix artifact 声称的删除项（`_durable_options_from_public_options`、`_WaitPollerDiagnosticsHost`、`cast`、`_wait_poller`、`dropped_count`）在 working tree 全部零命中 ✓
- fix artifact 声称的 100% coverage 与独立运行结果一致（9 passed） ✓
- fix artifact 声称的 Ruff 165→162 与 3 条 F401 删除一致 ✓
- fix Controller validation 声称的 smoke 输出（`LATE_READY_REJECTED second_observation_blocked=true second_claim_active=true`）与 smoke diff 中的 print 语句一致 ✓
- Control doc gate 已更新为 `R05-S2 dual complete code re-review` ✓

---

## Residual risks 与 uncovered areas

| Risk / area | 分类 | Owner / destination |
|---|---|---|
| scheduler close / terminal promotion coordination | R05 residual | 沿用 Controller 保留项，独立 Host lifecycle owner 缺口，deterministic probe 仍可复现 |
| cancelled wait abandon observation 持续 timeout 时 capped backoff 长期重试 | future work unit | future Host durable evidence policy |
| Issue 175 process isolation | tracked issue | 不进入 R05 |
| callback transport / unified authorization | deferred | R06+ |
| `options.py` 无 `__all__` | 预存 minor inconsistency | 本模块和其他 `dayu/host/durable/` 子模块惯例不一致，不阻塞 |
| Engine coverage：`agent.py` statement 80.458%、branch-aware 78% | 预存 | 不是 S2 changed production file，无新增 debt |

无 unclassified residual risk、blocking open question 或 deferred current finding。

---

## 下一 gate

本 re-review（AgentDS 第二路）完成。三项 accepted findings 已关闭，零新 material finding/blocker。两路 re-review 已完成，下一步 Controller 最终裁决。

R05-S2 accepted local commit、R05 aggregate、scheduler fix、Issue 175、callback、统一 authorization、R06-R12、push 与 PR 均未授权。
