# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Code Re-Review（AgentMiMo）

日期：2026-07-16
Gate：R05-S2 同一 code-review task 第一路完整 re-review
Initial review artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-mimo.md`
Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-controller-adjudication.md`
AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-fix-codex.md`
Fix Controller validation：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-fix-controller-validation.md`

## 1. Verdict

**PASS — 三项 accepted findings 已关闭，无新 material finding 或 blocker。**

本次 re-review 审查了整个 R05-S2 transaction（implementation → initial dual review → Controller adjudication → AgentCodex fix → fix Controller validation），不是只看三处局部 patch。五项 adversarial challenge 逐一验证完毕，结论为三项 accepted findings 按裁决边界实现、四项 no-fix observations 未被偷带、两项 retained residual 保持原 owner/destination。

## 2. Evidence baseline 与 digest 校验

| 冻结证据 | 预期值 | 实际值 | 状态 |
|---|---|---|---|
| tracked transaction digest | `95f24a4e...123fc6` | Controller validation artifact 记录一致 | MATCH |
| new owner-test blob | `1c9c21a0df334709ba8dcb8188c48c5e7fdaa2fc` | `git hash-object tests/host/test_durable_options.py` = `1c9c21a0...2fc` | MATCH |
| transition HEAD | `e077c708` | `git rev-parse HEAD` = `e077c70878bc47a2f1724d30f3ef22b8eb88e56f` | MATCH |

## 3. Finding ledger — 逐 finding 状态

### 3.1 Accepted findings 关闭状态

| Finding | Controller 裁决 | fix 实现 | re-review 关闭判定 |
|---|---|---|---|
| MiMo-001 / DS-02：smoke `_durable_options()` 重复 durable construction 投影 | `ACCEPTED_CURRENT_FIX` | `project_host_durable_store_options` 成为唯一 typed projection owner；旧 private helpers 删除；command/open-host/admin-seed/smoke 四条 construction path 共用 | **CLOSED** |
| MiMo-002 / DS-01：smoke 穿透 `_wait_poller` / runner diagnostics | `ACCEPTED_CURRENT_FIX` | `_WaitPollerDiagnosticsHost`、`cast`、`_wait_poller`、`dropped_count` 全部删除；改用第二轮 observation blocked boundary 上的 public Run/outbox + durable Wait/claim facts | **CLOSED** |
| DS-05：首轮 fake `operation_finished.wait()` 无界阻塞 | `ACCEPTED_CURRENT_FIX` | `_wait_for_poll_adapter_gate` 统一使用 `_TEST_OVERALL_DEADLINE_SECONDS` 有限等待；`abort()` 释放全部 gate | **CLOSED** |

### 3.2 Rejected observations — 未被偷带

| Observation | 裁决 | re-review 确认 |
|---|---|---|
| MiMo-003：单文件约 2200 行 | `NO_CURRENT_DEFECT` | 当前 2205 行，fix 自然删除了不再需要的 private 诊断代码和重复投影代码 |
| MiMo-004：test-effective `backoff_max == initial` | `NO_CURRENT_DEFECT` | 未修改，smoke 只验证首轮 retry initial backoff |
| DS-03：Engine fake operation 同 event loop | `NO_CURRENT_DEFECT` | 未修改，同 event loop 已充分证明 Engine timer 不拥有 accepted operation |
| DS-04：0.03s margin 理论慢 CI | `NO_CURRENT_DEFECT` | 未修改，durable state 一旦成立不会瞬时消失 |

### 3.3 Retained residuals — 保持原 owner

| Residual | 状态 |
|---|---|
| scheduler close / terminal promotion coordination | 未修、未隐藏、未归 Issue 175 |
| cancelled wait abandon observation 持续 timeout 长期重试 | deferred，future Host durable evidence policy 拥有终止 contract |
| Issue 175 process isolation | tracked by existing issue，未实施 |
| callback transport / unified authorization / R06+ | deferred，production added-lines 零命中 |

## 4. Adversarial challenge 逐项验证

### 4.1 `HostDurableStoreOptionsSource` Protocol + `project_host_durable_store_options` 是否属最小 dependency inversion

**是。** 完整走读：

- `HostDurableStoreOptionsSource`（`durable/options.py:25-122`）声明九个 `@property`，全部是 durable storage construction 所需字段（`db_path`、`artifact_root`、`create_parent_dirs`、五个 `sqlite_*`、`payload_inline_threshold_bytes`）。
- 它是 structural Protocol，不是 ABC 或具体类型。`HostCommandHandleOptions`（`api.py`）和 `OpenHostOptions`（`api.py`）都是 frozen dataclass，它们的同名 typed 属性自动满足该 Protocol，无需继承。
- `project_host_durable_store_options`（`durable/options.py:286-319`）是唯一构造 `PayloadStoragePolicy` + `HostSQLiteStoragePolicy` + `HostDurableStoreOptions` 的位置。
- 当前所有 construction path 共用该 helper：
  - `command.py:373` — `create_host_command_handle`
  - `open_host.py:525` — `_ExecutionCommandHandleFactory`
  - `open_host.py:591` — `_AdminCommandHandleFactory`
  - `open_host.py:632` — wait poller factory
  - `open_host.py:1310` — `_OpenHostContextManager.__aenter__`
  - `smoke:1407` — `_read_wait_record` independent durable read
  - `test_public_host_admin.py:209` — admin seed
- 没有旧 `_durable_options_from_public_options` 或 `_durable_options_from_command_options` 残留（grep 零命中）。
- Protocol 不持久化、不查找默认值、不解释额外字段、不拥有上层 opener 语义。
- 朴素直接参数替代方案（九个裸参数传递）会更不 ergonomic 且不改善可维护性。该 Protocol 是 Python 标准 dependency inversion 实践。

**判定：不是过度设计、不是 profile/god bag、不造成 public symbol 扩张或反向依赖。durable.options 作为 construction owner 的 boundary 是正确的。**

### 4.2 第二轮 observation blocked boundary 的 happens-before 证据

**证据充分，无 fake 自证、竞态或 false pass。** 完整时序链：

1. 首轮 observation 进入 → `first_observation_entered.set()` → adapter `operation_finished.wait()` 阻塞（0.30s operation 进行中）
2. observation runner timeout（0.15s）→ `_invalidate_token` → claim release → `ADAPTER_ERROR/wait_observation_timeout` → backoff due = 0.60s
3. 首轮 `operation_finished` 释放 → `late_result_release` 释放 → 首轮 Ready 返回（但因 token 已 invalidated，被 runner 丢弃）
4. 真实 backoff 到期 → 第二轮 observation → `second_observation_entered.set()` → adapter 先确认 `operation_finished.is_set()`，然后阻塞在 `second_observation_release.wait()`
5. **happens-before boundary**：smoke 在第二轮 adapter 尚未返回时断言：
   - `second_observation_release.is_set()` 为 `False`（第 626 行断言）
   - public `RunSnapshot.status == WAITING`
   - durable `WaitRecordStatus == WAITING`
   - 第二轮 claim 四字段均 active
   - `poll_backoff_attempt == 1`（首轮 timeout diagnostic 保持）
   - `poll_last_outcome == ADAPTER_ERROR`、`poll_last_error_code == "wait_observation_timeout"`
   - `terminal_outbox == ()`
6. 只有断言完成后才 `release_second_observation()`
7. 最终经 public terminal/outbox 收为 `SUCCEEDED`，terminal event id 与 outbox item 精确一致

关键逻辑：第一轮已返回而第二轮尚未返回 → 第一轮 result 在第二轮 blocked 时已经过了 durable commit → 但 durable state 仍显示 WAITING + 无 terminal outbox → 第一轮 result 没有 durable publication authority。这不依赖 `dropped_count` 或任何内部诊断字段。

S1 owner-level runner test 继续拥有 `dropped_count` 内部诊断断言，S2 smoke 不再依赖它。

### 4.3 三个 fake gate 的有限等待、deadline、close/drain 与 finally abort

**失败路径不泄漏 thread/task/store。** 完整走读：

- `_wait_for_poll_adapter_gate`（smoke:1659-1678）：`event.wait(timeout=_TEST_OVERALL_DEADLINE_SECONDS)`，超时抛 `RuntimeError` 包含 gate 名和秒数。
- 三个 gate：`operation_finished`、`late_result_release`、`second_observation_release`，全部通过该 helper。
- `abort()`（smoke:350-368）：释放全部三个 gate + cancel operation task + await + catch `CancelledError`。
- smoke `finally` 块（smoke:720-727）：`operation.abort()` + `submit_task.cancel()` + await。
- `_phase_failure`（smoke:1538-1593）：输出 completed/pending phases、monotonic elapsed、Run/Wait/claim/outbox 全字段诊断。
- Host close 路径（`open_host.py` `_close_owned_resources`）：poller close → actor drain → scheduler close → projection flush → actor handle → actor executor → scheduler store，每步独立 try/except 记录首个错误。

### 4.4 Owner tests 是否断言 owner contract；100% coverage 是否可信

**是。** 完整走读：

- `test_durable_options.py`（185 行，9 个 test nodes）：
  - `test_project_host_durable_store_options_maps_every_storage_field`：构造每字段可区分的 `HostCommandHandleOptions`，投影后逐字段 assert equal，覆盖 db_path、payload_policy 三字段、create_parent_dirs、sqlite_policy 五字段。
  - 其余 8 个 test：分别断言 `HostSQLiteStoragePolicy` 的 5 个 validation 分支 + `PayloadStoragePolicy` 的 2 个 + `HostDurableStoreOptions` 的 1 个。
- 不是复制实现：test 通过构造可区分输入值、调用 owner helper、断言输出精确映射，验证 contract 行为。
- 覆盖率 `dayu/host/durable/options.py: 100%（73 statements, 8 branches）`，由 `--cov-branch --cov-fail-under=80` 独立验证。
- Ruff 165→162 解释：fix 删除了三条 touched-file F401（`command.py` unused `AttemptStatus`、unused `read_run_by_id`、`test_public_host_admin.py` unused `create_host_command_handle`），精确等于 pre-fix registry 减去这三条。
- Engine no-diff：`agent.py` 在 fixed base / S1 accepted / transition HEAD 三重 no diff。
- public chain：smoke 保持 packaged `ConfigLoader → provider discovery → Service composition → open_host → durable poller → public terminal/outbox` 主链。

### 4.5 Initial no-fix observations 是否保持 no-fix；retained/deferred boundary

**保持。** 逐项确认：

- `backoff_max == initial`：未修改，smoke 只验证首轮 retry initial backoff。
- 单文件 2200 行：未拆分，accepted fixes 自然删除了不需要的代码。
- Engine fake 同 event loop：未改线程，证据充分。
- 0.03s margin：未调整，durable state 不会瞬时消失。
- scheduler close/terminal promotion coordination：`dispatch.py`、`engine_ingest.py`、`test_dispatch_scheduler.py` no diff，deterministic probe 仍 `1 passed`（以预期 `HostApiError` 为通过条件）。
- Issue 175 / callback / unified authorization / R06+：production added-lines 对 `authorization|permission|callback transport|process isolation|Issue 175` 零命中。

## 5. Re-review 独立验证

所有 Python 命令均在 `source .venv/bin/activate` 后运行。

| 验证 | 结果 |
|---|---|
| fresh public smoke（连续两次） | PASS（两次独立 workspace） |
| Engine full `test_agent_phase3_tool_call.py` | `48 passed` |
| R04 config/Fins/Service exact owner matrix | `35 passed, 3 warnings` |
| R05 ten-file aggregate | `360 passed, 3 warnings` |
| durable owner + public admin focused | `11 passed` |
| durable options owner coverage | `9 passed`；`options.py 100%`（73 statements, 8 branches） |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed-file Ruff | `All checks passed!` |
| full Ruff registry | pre-fix 165，post-fix 162；精确 diff 只删除三条 touched-file F401 |
| `git diff --check` | PASS |
| scheduler deterministic probe | `1 passed`（residual 仍可复现） |
| `_durable_options_from_*` private helpers | 零命中（command + open_host + smoke） |
| `_WaitPollerDiagnosticsHost` / `cast` / `_wait_poller` / `runner_dropped_count` | 零命中（smoke） |
| 裸 `operation_finished.wait()` / `late_result_release.wait()` / `second_observation_release.wait()` | 零命中（smoke） |
| `hasattr/getattr` / `.resolve_wait(...)` / `poll_next_observe_at` mutation | 零命中 |
| Engine `agent.py` / README | no diff |
| S1 protected seven paths | no diff |

## 6. Open Questions

无。

## 7. Residual Risk

| Residual | 分类 | 风险 |
|---|---|---|
| scheduler close / terminal promotion coordination | retained residual | 独立 Host lifecycle owner 缺口，确定性 probe 可复现，不属于 R05 |
| cancelled wait abandon observation 持续 timeout 长期重试 | deferred | R05 只保证 claim CAS、bounded capacity、finite timeout、late-pub fencing、backoff cap |
| Issue 175 process isolation | tracked | 未实施，物理进程终止不自动成为 Host durable terminal fact |
| callback transport / unified authorization / R06+ | deferred | 本 gate 确认未进入 |
| smoke timing margin（0.03s / 5×0.005s） | low | durable state 一旦成立不会瞬时消失；15s deadline 有大量 headroom |
| `backoff_max == initial` | low | smoke 只验证首轮 retry initial backoff，cap 不生效 |

## 8. Conclusion

三项 accepted findings 全部按裁决边界修复完成：

1. **Durable construction projection**：`HostDurableStoreOptionsSource` structural Protocol + `project_host_durable_store_options` 成为唯一 owner；所有 construction path 共用；旧 private helpers 和 smoke 重复构造删除。Protocol 是最小 dependency inversion，不是 profile/god bag/上层语义泄漏。
2. **Late publication evidence**：删除 `_WaitPollerDiagnosticsHost`、`cast`、`_wait_poller`、`dropped_count`；第二轮 observation blocked boundary 上的 public Run/outbox + durable Wait/claim facts 直接证明首轮 result 没有 publication authority。happens-before 证据充分，无 fake 自证、竞态或 false pass。
3. **Fake bounded waits**：三个 adapter gate 统一使用 `_TEST_OVERALL_DEADLINE_SECONDS` 有限等待；`abort()` 释放全部 gate；`finally` 保证 cleanup。失败路径不泄漏 thread/task/store。

四项 no-fix observations 未被偷带。两项 retained residuals 保持原 owner/destination。无新 material finding 或 blocker。

R05-S2 accepted local commit、R05 aggregate、scheduler 产品修复、Issue 175、callback、统一 authorization、R06-R12、push 与 PR 均未授权。等待 Controller 最终裁决。
