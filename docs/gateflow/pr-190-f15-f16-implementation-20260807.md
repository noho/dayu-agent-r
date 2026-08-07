# PR 190 F15 / F16 Implementation Gate

## Gate / scope

- Gate: accepted Gateflow `implementation` only。
- Work unit: PR 190 F15 / F16。
- Binding artifacts:
  - `docs/gateflow/pr-190-f15-f16-plan-acceptance-20260807.md`
  - `docs/gateflow/pr-190-f15-f16-plan-20260807.md`
  - `docs/gateflow/pr-190-f15-f16-plan-review-adjudication-20260807.md`
- Branch: `codex/interactive-oracle`。
- 未 commit、未 push、未创建或修改 PR。
- 未修改 prompts、formal oracle、scenario registry、scenario predicate / expected behavior、Engine contract、CLI public options、durable DDL、compact schema 5 或 F14 cumulative `compacted_source_refs` frontier。

## First-principles / owner decision

动机成立。旧故障不是 validator 过严，而是 Host previous-pair projection owner 对同一 accepted replacement 产生了两套文本：packed block 经 `normalized_material_text()`，readable view 保留 raw typed text；exact validator 因而确定性拒绝合法多行/空白 Markdown。正确修复点是 `dayu.host.compact_material` 的 replacement -> pair owner，不是 Engine、validator、prompt、consumer fallback 或 fixture。

F16 的事实 owner 保持为 Host EventLog/shared Run lifecycle terminal contract。tracked helper 只做物理只读投影；process outcome、Run terminal、dependency gate 与 evidence integrity互不覆盖。terminal reason 只取 `reason_json.reason`，不读取 payload/status/log fallback。

## Pre-fix regression evidence

先新增 `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact`，再在旧生产实现上运行：

```text
source .venv/bin/activate
pytest tests/host/test_compact_material.py::test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact -q
```

修复前结果：`1 failed`。直接失败链为 `validate_previous_compacted_view_pair` 报 `previous session summary block mismatch`，随后 `_previous_compacted_view_pair_from_replacement` 上抛 `HostDurableError("previous compacted view pair is invalid")`。这与 production `runner_candidate_invalid` 的原始根因同源，且不是间接日志推断。

## Slice 1 — F15 Host canonical previous pair

### Implementation

- `dayu/host/compact_material.py`
  - 增加 private frozen `_CanonicalMaterialText` 与五区 typed canonical projection atoms。
  - accepted replacement 的 summary、fact claim、answer anchor title/detail、forward intent text、reference text 每个叶子只在 projection factory 调用一次现有 `normalized_material_text()`。
  - packed blocks 与 `PreviousCompactReadableView` 同时消费同一 canonical atoms；fact evidence refs、intent type/status、reference reason 原样携带。
  - answer anchor 先构造 canonical typed anchor，再用 shared `previous_answer_anchor_block_text()` 正向渲染；没有从 packed string 逆向解析。
  - private canonical block builder直接从 typed wrapper派生 text/size/digest，不再次执行 raw normalizer。
  - accepted tool evidence 保留既有 exact renderer text 例外路径，不借用 canonical wrapper，也不被普通 normalizer改写。
  - `validate_previous_compacted_view_pair()`、recovery同步过滤、packing/label order与 F14 frontier均未修改。

### Tests

- 全 section canonical projection、leading/trailing/repeated whitespace、blank lines、multiline prose、Markdown bullet/numbered list/table与 answer anchor exact renderer。
- 关闭 writable store 后以物理只读 `open_host_durable_read_store` reopen，重新从 durable accepted event/artifact 构造 pair；完整 readable JSON 与每个 block text/size/digest byte-exact 相同，不复用首次构造对象。
- Controller completion test `test_durable_reopen_previous_pair_freezes_and_dispatches_next_ordinary_run` 进一步使用既有 owner helpers 完成实际 ordinary dispatch，而非停在 view：首次 writable store 通过 `_append_previous_compacted_event` 持久化含上述格式矩阵的 accepted pair，并用 `_seed_accepted_run` 只创建下一 ordinary `ACCEPTED` Run；关闭后由新的 writable store / scheduler `run_queue_promotion` 进入 `prepare_runner_call_candidate_in_transaction` → `record_prepared_runner_call_candidate_in_transaction` → governed start → worker `accept`。测试最后用 `load_prepared_runner_call_source_in_transaction` strict-load frozen candidate，断言其 messages 与 `_FinalAnswerWorkerFactory.accepted_requests[0].messages` exact 相等、Attempt/execution identity同源且 Run真实收口为 `SUCCEEDED`。该调用链直接覆盖 run_input candidate owner与 dispatch consumer，不是 direct Host smoke。
- 既有 strict mismatch与 recovery exact tests保留并通过；没有改成 loose acceptance。
- accepted candidate / strict persisted parser 对 blank required text 的既有 owner contract未增加 projector skip、default或 renumber。

## Slice 2 — F16 observation contract

### Tracked helper

- 新增 `utils/cli_ci_run_observation.py`：
  - 通过 `open_host_durable_read_store(...)` + `run_read` + `EventLogStore.read_events_after_matching(...)` 读取只含 `RUN_ACCEPTED` 与 `HOST_RUN_TERMINAL_EVENT_TYPES` 的 canonical-fact filter。
  - frozen window 为 `(start_event_sequence, end_event_sequence]`；按 `covered_event_sequence` keyset推进到 end；no-progress/backward/overrun fail closed，page size只影响批次。
  - accepted ordinal按真实 accepted event sequence确定，并支持跨 segment offset；事实 identity仍保存 session/run/event id/sequence。
  - 同 Run 任意第二条 shared Run terminal fact均 duplicate；Attempt terminal与非 terminal lifecycle不进入 filter。
  - `RUN_LOST` 保持独立 `lost`，并显式 `public_outbox_terminal=false`。
  - missing accepted/terminal归属、missing terminal、duplicate、malformed JSON、wrong shape/type、blank reason或 role mapping不完整均抛 `RunObservationError`。
  - dependency pure function只有 `succeeded` 返回 `proceeded`；failed/cancelled/lost返回 `stopped`，deadline前 missing为 `pending`，deadline后为 `invalid`。
  - deterministic `to_json()` 只投影 window、summary与逐 Run facts，不读取或推导 process outcome，不判定业务 oracle，不写文件/Host state。

### Controller scope correction

实施中最初按 plan 中“exact `{"reason": ...}` object”文字尝试收敛两个 Run terminal writers。Controller 随即裁决：F16不得修改 product lifecycle/audit contract；现有 waiting `RUN_CANCELLED` 合法携带 `mode`，startup orphan `RUN_LOST` 合法携带 `orphan_proof`。两处 writer改动已立即完全撤回，`dayu/host/durable/run_transition.py` 最终无 diff。

随后审计全部 Host Run terminal producer，得到并锁定 event-specific existing shapes：

- `RUN_SUCCEEDED` / `RUN_FAILED`: exact `{"reason": <non-empty str>}`；
- `RUN_CANCELLED`: `reason`，或 waiting cancel 的 `reason + mode`；`mode` 必须属于现有 `CancelMode`；
- `RUN_LOST`: `reason`，或 startup orphan 的 `reason + orphan_proof`；`orphan_proof` 必须为非空字符串。

helper 的 reason 仍唯一读取 `reason_json.reason`；已知治理字段只参与 shape validation，不成为 reason 第二真源。unknown extra、非法 mode、空 orphan proof仍 fail closed。新增真实 waiting cancel / startup orphan producer tests与 helper accept/reject矩阵。

### Temporary real harness consumers

以下文件受 `.gitignore` 的 `workspace/` 规则管理，已作为本机临时消费者更新，不进入 tracked diff：

- `workspace/tmp/prompt_observe_calibration.py`
  - `PtyAction.required_success_accepted_ordinal: int | None`；
  - 记录 process outcome 与独立 `run-terminals.json`；
  - dependent action发送前调用 tracked helper / dependency gate；stop/invalid时由 tracked pure control helper一次分类全部 remaining actions，逐项记录 dependent `not_run`，不发送依赖输入，立即只发送一次显式 cleanup/EOT，并用10秒 cleanup deadline确保 PTY 不再等待原计划 terminal count；
  - cleanup后的 process exit仍只保留为 process fact，不覆盖 canonical non-succeeded Run；process artifact、terminal evidence、public evidence与secret scan等 process 外独立取证继续；
  - 全部scenario evidence落盘后先写final `run-completion.json`，其中只引用`evidence/public/secret-scan.json`路径，不复制尚未形成的scan status/digest；随后调用tracked final-tree helper扫描完整evidence tree并独占创建唯一report；
  - 删除 row 级含混 `execution_outcome=success`，使用 `process_outcome.kind/exit_code/timed_out`；
  - 未修改 `_scenario_matrix()` 的 prompts、predicate或 expected behavior。
- `workspace/tmp/f14_real_cli_observation.py`
  - chain从实际 `run-terminals.json` accepted/terminal facts推进，不再按 action数量机械增加 terminal count；
  - follow-up action显式绑定直接 upstream cumulative accepted ordinal；
  - `_run_scenario` error、run-terminals缺失/invalid shape不再二次抛错或静默降为 `(0, false)`；保留 validation diagnostics，标 evidence/harness invalid，安全停止依赖链，主 harness仍生成最终 index；
  - upstream valid non-succeeded时当前 evidence为 `insufficient`，后续 dependent segment写 `not_run`；canonical observation破损才为`invalid`，两者均不标complete；
  - index改为 `execution-index-f15-f16.json`，逐项/汇总分离 process outcomes、accepted/succeeded/failed/cancelled/lost/missing/invalid terminal counts、per-Run record path/digest、dependency gates、strict context compaction count/refs与public evidence。valid summary按四类`terminal_class`与per-Run records exact对账；invalid observation只确认`invalid=1`，其余无法确认的计数为`null`，不从diagnostic message反推missing/duplicate。
  - final execution index先落盘，`evidence_status`只表达Run/context/tool collection且scan字段只引用report path；随后由同一tracked final-tree helper扫描包含index在内的完整evidence tree并独占写report，不做pre/post双扫；
  - public scan分离secret与path hygiene：exact secret probes只使用实际secret环境值和canary，不把repo/run/corpus普通路径当credential；path hygiene扫描public evidence tree中的raw `*.sqlite`/`*.sqlite3`/`*.db`文件、文本raw database路径及leaf/ancestor symlink并fail closed。report target拒绝path traversal、resolved root逃逸、stale/既有report与symlink；raw Host SQLite不进入public evidence；formal `oracle_status`精确为`unadjudicated`。

本轮 SHA-256：

- tracked helper: `239bfd1f762fa44fd4e0e2131fe577f64cc2c7f240bcd2d00f2b46da2cc06872`；
- temporary prompt harness: `15c6e2dbcc081b20c63197aba03544d00042ecf1718ab0e44214b09a5dea5e60`；
- temporary F14 harness: `dfc3d61853e0c2bf5b7b6421ae57bd1440ad09d33446c72e5c1e28941bb1535e`。

## Documentation decision

- 更新 `docs/host/design.md` / `dayu/host/README.md`：Host previous-pair 的全 section canonical single projection、exact validator、reopen/recovery与 F14 frontier隔离。
- 更新 `docs/cli_ci.md`：process/per-Run/dependency/evidence分离、filtered keyset window、event-specific reason shape、lost语义、dependent stop与 index字段。
- 更新 `tests/README.md`：tracked helper focused入口、reason/terminal owner tests与 fail-closed矩阵。
- `docs/engine/design.md` 不更新：Engine不拥有 accepted replacement、previous pair或 Host terminal observation，Engine contract/code无变化。
- 根 `README.md` / `dayu/README.md` 不更新：CLI public command/options、用户工作流与分层装配无变化。

## Validation

已执行：

1. F15/F16 + producer focused aggregate：482 tests中 `481 passed, 1 failed`；唯一失败为 `test_active_cancel_watchdog_times_out_non_cooperative_worker` 的 runtime lane acquire 0.01s超时，日志显示 `dispatch.lane_acquire.timed_out`，与本次 diff无关。该 node立即独立重跑 `1 passed`；此前同一完整文件独立运行 `185 passed`。
2. 最终 F15/helper focused：`102 passed`；新增 malformed/controller correction focused：`18 passed`。
3. F15 coverage：`dayu/host/compact_material.py` 1124 statements，157 missed，`86%`，达到单文件 >=80%目标。
4. 相关 pyright（含两个 temporary harness）：`0 errors, 0 warnings`。
5. 全量 `python -m pyright dayu/ tests/ utils/`：完成且无错误输出。
6. `python -m py_compile`：两个 temporary harness与 tracked helper通过。
7. `git diff --check`：通过。
8. Controller completion owner node：`test_durable_reopen_previous_pair_freezes_and_dispatches_next_ordinary_run` 单独运行 `1 passed`；连同所有复用 `_append_previous_compacted_event` 的 dispatch/recovery场景运行 `9 passed`。
9. 最终交付 focused（上述 owner node + pre-fix regression node + F16 helper全文件）：`17 passed`；随后相关 pyright再次确认 `0 errors, 0 warnings`。
10. review-fix focused：F15 compact/context owner、F16 helper、ordinary freeze/dispatch 共 `217 passed`；terminal producer exact reason nodes `6 passed`；review-fix新增最小矩阵 `26 passed`。
11. final re-review fix focused：`pytest tests/cli/test_cli_ci_run_observation.py tests/host/test_event_log_store.py tests/host/test_run_attempt_transitions.py tests/host/test_wait_cancel_late_result.py -q`为`126 passed`；其中tracked helper全文件`31 passed`。
12. 两个ignored harness再次`py_compile`通过且定向pyright为`0 errors, 0 warnings`；全量`python -m pyright dayu/ tests/ utils/`为`0 errors, 0 warnings`；`git diff --check`通过。

## Review-fix implementation correction

- terminal accepted/terminal pair新增 exact `session_id` 校验；terminal class改用 lifecycle owner `run_status_for_terminal_event()`，public-outbox membership改用`is_public_outbox_terminal_item_event()`，删除手写四分支与“非lost”否定映射。
- `RunObservationRole.INDEPENDENT`保留为复用contract；新增pure harness-role projector与test，required/dependent/independent不再混用。
- upstream→dependent ordinal的`+1`集中为typed pure helper；temporary harness仅消费helper并校验action顺序。
- accepted tool exact renderer与ordinary canonical normalizer分别由`_AcceptedToolEvidenceText` / `_CanonicalMaterialText`表达，二者union进入唯一low-level block constructor；没有dict、bool、trusted string或raw exact冒充canonical。
- whitespace boundary新增typed accept、strict persisted read和two-anchor projector label `P3/P4`不skip/renumber focused tests。
- deterministic evidence classifier精确区分`complete`、valid non-success `insufficient`与canonical破损/缺失`invalid`；dependency stop后的remaining action处置由tracked pure helper覆盖。

## Final re-review fix correction

- MiMo 001-P2：calibration harness不再遗漏final publication scan；先写含scan record path且不含推断verdict的`run-completion.json`，再调用tracked helper覆盖completion与全部此前evidence。
- MiMo 002-P3：F14 harness删除pre-scan及index中的scan status/digest projector；先写只表达Run/context/tool collection的final index，再进行唯一final-tree scan，index本身进入report descriptors。
- Controller补充：tracked helper在owner boundary同时拒绝显式`..` traversal并校验`resolve(strict=False)`后的root containment；保留report ancestor symlink检查与`open("x")`独占创建。既有/stale report一律fail closed，不覆盖、不形成第二truth。
- owner tests锁定final completion/index descriptor coverage、只自排除尚不存在的report、stale report拒绝、traversal/outside target拒绝，以及final-tree对secret/raw DB/leaf与ancestor symlink候选的既有fail-closed行为。

## Schema / public contract no-change proof

- `dayu/host/durable/run_transition.py` 最终无 diff；durable DDL、EventLog payload字段、lifecycle enum与 audit contract未改。
- `CompactAcceptedReplacementV4`、schema 5、compactor LLM schema、Engine contract与 CLI public surface未改。
- `validate_previous_compacted_view_pair()` 未改，仍 exact。
- `git diff` 不包含 `compacted_source_refs` / frontier实现改动。
- `docs/cli_ci_scenarios.json`、`docs/cli_ci_oracles.json`、prompt目录与 formal scenario matrix未改。
- helper无 payload/log/status fallback，无写 Host state路径。

## Residual risks / uncovered areas

- **assigned to subsequent accepted post-commit validation gate / Controller**：accepted plan要求 fresh production real rerun只针对 clean committed target；当前用户明确限制 implementation gate且禁止 commit/push，因此本 gate未启动真实 provider/AAPL rerun、未生成新的 external run root、public evidence bundle或 secret scan。不得把 deterministic pass表述成 real-evidence completion。
- **fixed in current slice**：Controller指出的 product writer scope drift已撤回，并由 product file zero-diff审计与 cancel/lost producer tests覆盖。
- **fixed in current slice**：旧 multiline previous-pair failure已有 pre-fix fail与 post-fix/reopen exact pass。
- **fixed in current slice**：accepted pair durable reopen 后下一 ordinary Run 的 candidate freeze与 worker dispatch，已有上述 owner node及 exact frozen-candidate/request同源断言，不依赖 direct Host smoke。
- **covered by existing + current deterministic suite**：strict mismatch/recovery、dispatch candidate paths、active cancel、recovery与 EventLog filtered reader均通过 focused suites；未放宽 validator或 lifecycle语义。
- Formal financial/business Oracle仍为 `unadjudicated`，owner不在本 implementation gate。

## Completion status / next entry point

- F15 implementation: complete。
- F16 tracked helper、temporary consumer、owner/regression tests与 handbook implementation: complete。
- Implementation gate artifact: `docs/gateflow/pr-190-f15-f16-implementation-20260807.md`。
- Next Gateflow entry point由 Controller决定；本执行者不进入 code review、commit、push或 PR gate。
