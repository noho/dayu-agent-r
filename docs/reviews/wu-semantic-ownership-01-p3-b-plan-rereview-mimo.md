# WU-SEMANTIC-OWNERSHIP-01 P3-B plan re-review（AgentMiMo）

## Review metadata

- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`（plan-fix 版）
- **Review type**: adversarial plan re-review；仅复核 controller accepted PF-01..PF-05 的修复完整性
- **Gate**: plan re-review only；不修改 plan / 生产代码 / 测试 / control doc / 其它 artifact
- **Reviewer**: AgentMiMo（adversarial re-review）
- **Timestamp**: `2026-07-10T14:27:55+08:00`（本机系统时钟）
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-rereview-mimo.md`

## Review scope

本 re-review 仅复核以下内容：

1. plan 是否按 controller 真源 `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-controller-adjudication.md` 完整修复 `P3-B-PF-01` 至 `P3-B-PF-05`。
2. 核对 `docs/reviews/wu-semantic-ownership-01-p3-b-plan-fix-codex.md` 的修复声称。
3. 逐项给 final status。
4. 检查直接代码证据、ProjectionRunner 同事务 + 独立 failure 记录、FinalAnswerWorkerFactory descriptor-only production smoke、test-only 同 ref/digest 恢复、descriptor pair/storage/JSON/content 错误 taxonomy。
5. Controller rejected concerns 不得重开，除非给出新的直接证据。
6. 检查 0 新 blocking finding、1 slice 合理性。

## Inputs

- `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`（plan-fix 版）
- `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-controller-adjudication.md`（controller 真源）
- `docs/reviews/wu-semantic-ownership-01-p3-b-plan-fix-codex.md`（Codex 修复声称）
- `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-mimo.md`（首轮 MiMo review）
- `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-ds.md`（首轮 DS review）
- 直接代码证据（4 个 parallel Explore agent 验证）

## PF-01：correct source evidence — final status: `fixed`

### Controller 要求

> Correct the stale `run_transition.py:4569-4584` citation. Identify the actual Engine-origin and Host-lifecycle closeout locations in `engine_ingest.py` and the exact durable payload builder that persists `terminal_summary_ref/digest` plus canonical metadata without inline answer text.

### Plan 修复

- §3.1 将 Engine-origin 事实产生点精确到 `engine_ingest._final_answer_plan`（`4885-4931`）。
- §3.1 将 Engine-origin closeout 精确到 `engine_ingest._close_terminal`（`1184-1283`）和 `_write_terminal_payload`（`3533-3573`）。
- §3.1 将 Host-lifecycle closeout 精确到 `engine_ingest._close_host_lifecycle_terminal`（`1285-1372`）。
- §3.1 将最终 durable canonical payload builder 精确到 `durable/run_transition._run_terminal_payload`（`4551-4584`），明确它写 descriptor pair 与 canonical metadata、不写 inline answer。
- §3.1 引用 `docs/host/design.md:3082`：inline `RUN_SUCCEEDED.final_answer` 与 digest-checked terminal artifact `content` 都是明确允许的 continuity source。

### 直接代码证据

- `engine_ingest.py:4885-4931` — `_final_answer_plan`：构建 `_EngineTerminalPlan`，拒绝对空白 content 产生成功 terminal。**确认。**
- `engine_ingest.py:1184-1283` — `_close_terminal`：写 terminal payload、调用 `terminal_closeout_in_transaction`。**确认。**
- `engine_ingest.py:3533-3573` — `_write_terminal_payload`：写 SQLite payload descriptor。**确认。**
- `engine_ingest.py:1285-1372` — `_close_host_lifecycle_terminal`：Host lifecycle closeout，`finish_reason=None, filtered=None, degraded=None`。**确认。**
- `durable/run_transition.py:4551-4584` — `_run_terminal_payload`：构建 canonical payload，写 `terminal_summary_ref/digest`，succeeded 时追加 `finish_reason/filtered/degraded`，不写 `final_answer`。**确认。**
- `docs/host/design.md:3082` — Trace Memory 章节，描述 `RUN_SUCCEEDED` assistant final-answer continuity。**确认行引用存在，但该行未显式逐字提到 inline `final_answer` 字段名。plan 的 §3.1 引用措辞略过强，但 controller 在 DS F01 rejection 中已接受"引用 design evidence"的要求，不构成本轮新 finding。**

### 结论

行引用全部准确，stale citation 已纠正。`PF-01: fixed`。

---

## PF-02：prove ProjectionRunner atomicity — final status: `fixed`

### Controller 要求

> Add concrete code references showing consumer apply, Outbox insert, checkpoint advance, rollback, and separate failure recording. Make non-atomic behavior a stop condition rather than an implementation-time assumption.

### Plan 修复

- §6.3 增加 `projection.py:464-471,626-644`、`outbox.py:147-168`、`durable/outbox.py:243-305` 和 `durable/transaction.py:288-360` 的具体事务证据。
- §6.3 增加 `projection.py:472-489,653-685` 的证据，证明 failure row 在 apply transaction rollback 后由独立 `run_write` 持久化。
- §6.3 固定 Outbox 专项原子性断言，并把任何非原子代码事实设为 implementation stop condition。

### 直接代码证据

- `projection.py:464-471` — `run_write(lambda: _process_next_event(...))`。**确认：整个 apply + checkpoint + failure clear 在同一 `BEGIN IMMEDIATE` 内。**
- `projection.py:626-644` — `apply_event(transaction, event)` → `advance_projection_checkpoint(transaction, ...)` → `clear_projection_failure(transaction, ...)`。**确认：同一 transaction。**
- `projection.py:472-489` — `except _ProjectionApplyFailed: self._record_failure(...)` 在 `run_write` 外。**确认：failure 记录在 transaction rollback 后。**
- `projection.py:653-685` — `_record_failure` 开启独立 `run_write` 写 failure row。**确认：独立事务。**
- `outbox.py:147-168` — `apply_event(transaction, event)` 内调 `build_outbox_terminal_item_row(event)` + `insert_outbox_terminal_item_if_absent(transaction, row)`。**确认：使用同一 transaction。**
- `durable/outbox.py:243-305` — `insert_outbox_terminal_item_if_absent(transaction, row)`：`_validate_item_row`、`read_by_event_id`、`INSERT`、read-back 都在同一 transaction。**确认。**
- `durable/transaction.py:288-360` — `BEGIN IMMEDIATE` → `operation(HostTransaction(...))` → `COMMIT`；任何异常 → `_rollback_if_needed_or_mark_unusable()`。**确认。**

### 结论

事务原子性由 7 处直接代码证据确认。plan 正确将非原子行为设为 stop condition。`PF-02: fixed`。

---

## PF-03：prove the production smoke path — final status: `fixed`

### Controller 要求

> Verify the actual `FinalAnswerWorkerFactory` or replacement fixture exists and exercises the production descriptor-only closeout. Name the exact test/support file and assertions; do not let an inline-only fixture satisfy the smoke.

### Plan 修复

- §6.5 核实 `tests/host/public_smoke_support.py:242-292,314-371` 的 `FinalAnswerHandle` / `FinalAnswerWorkerFactory` 实际产出 `EngineEventType.FINAL_ANSWER`。
- §6.5 规格化新增 smoke 门槛：直接读取 canonical `RUN_SUCCEEDED.payload_json`，断言无 inline `final_answer` key、有完整 descriptor pair 且 digest 可校验；随后断言 live/read/drain answer content 和 terminal identity 一致。
- §6.5 明确 inline-only `ProjectionEventView` fixture 不能代替 production smoke。

### 直接代码证据

- `public_smoke_support.py:242-292` — `FinalAnswerHandle`：`events()` 产出 `EngineEvent(type=FINAL_ANSWER, data=FinalAnswerData(content=..., filtered=False, degraded=False, finish_reason=FinishReason.STOP))`。**确认。**
- `public_smoke_support.py:314-371` — `FinalAnswerWorker.accept()` 返回 `FinalAnswerHandle`，content 为 `f"final:{len(requests)}:{run_id}"`。`FinalAnswerWorkerFactory.create_worker()` 返回 `FinalAnswerWorker`。**确认。**
- `engine_ingest.py:1016` — `EngineEventType.FINAL_ANSWER` 匹配 → `_close_terminal()` + `_final_answer_plan(event.data)`。**确认：走 production ingest/closeout 路径。**
- `test_public_offline_outbox_smoke.py:28-227` — 3 个 smoke test，断言 terminal identity/ref/dedupe/drain，**但当前不断言 final answer content**。**确认：plan 正确识别了此 gap 并要求扩展。**

### 结论

`FinalAnswerWorkerFactory` 存在且经 production closeout 路径，但当前 smoke 不断言 final answer content。plan 正确要求扩展 smoke 并设定了具体门槛。`PF-03: fixed`。

---

## PF-04：specify descriptor restoration and retry — final status: `fixed`

### Controller 要求

> Replace the vague "PayloadStore restores the same ref/digest" wording with the repository's real test mechanism. State whether recovery uses the typed payload writer or a test-only direct durable row insertion, how the same digest is preserved, and why retry observes the restored row without adding a production repair API.

### Plan 修复

- §6.4 否定模糊的"正式 PayloadStore 恢复同 ref/digest"说法：typed SQLite payload writer 会同时插 payload row 与 descriptor，不能在 payload row 仍存在时只恢复缺失 descriptor。
- §6.4 固定使用仓库已有 test-only durable mutation 模式（参见 `tests/host/test_storage_maintenance.py:837-857`）。
- §6.4 规定了 5 步测试流程：保存 descriptor 全部 durable columns → 只删除 descriptor row → 验证 failure → 原样 `INSERT` 回同一 row → 重试验证 success + DUPLICATE。

### 直接代码证据

- `test_storage_maintenance.py:837-857` — `_delete_payload_descriptor(host, payload_ref)`：嵌套函数内执行 `DELETE FROM {TABLE_PAYLOAD_DESCRIPTORS} WHERE payload_ref = ?`。**确认：test-only durable mutation pattern。**
- `durable/payload.py:243-285` — typed `write_sqlite_payload` 同时插入 SQLite payload row 与 descriptor。**确认：不能在 payload row 仍存在时只恢复 descriptor。**

### 结论

恢复机制已从模糊的"PayloadStore 恢复"改为具体的 test-only durable row INSERT，5 步测试流程完整可行。`PF-04: fixed`。

---

## PF-05：close descriptor-pair and error taxonomy — final status: `fixed`

### Controller 要求

> Specify how the resolver distinguishes both descriptor fields absent from a one-sided malformed pair, missing descriptor row, digest mismatch, invalid JSON/object, and missing/blank/non-text `content`. Identify the check location and required behavioral assertions so projection failure rows retain actionable cause text while remaining internal diagnostics.

### Plan 修复

- §5.5 固定 descriptor pair owner check 在 `_terminal_answer.py`，required/optional 共用一个模块级私有 resolution core。
- §5.5 封闭 taxonomy 表区分 11 种 case，每类指定 owner check location、required/public 结果与稳定诊断语义。
- §5.5 要求每类 failure 的 `HostDurableError` 消息含可区分的稳定 cause fragment。
- §5.5 ProjectionRunner failure row 断言 `last_error_code == "HostDurableError"` 且 `last_error_message` 保留对应根因。
- §5.5 诊断保持 internal，不进入 LLM-facing material。

### 直接代码证据

- `payload_resolution.py:158-217` — `sqlite_payload_object`：descriptor missing → `HostDurableError`；kind check → `HostDurableError`；digest mismatch → `HostDurableError`；sqlite_payload_id missing → `HostDurableError`；row missing → `HostDurableError`；payload_json 非 str → `HostDurableError`；JSON parse 失败 → `HostDurableError`。**确认：已有可区分的 cause text。**
- `_terminal_answer.py:35-83` — `assistant_final_answer_continuity_text`：inline 优先 → pair check（`_optional_descriptor_text` 返回 None 则无 candidate）→ `sqlite_payload_object` → `terminal_payload_content_text_from_payload`。**确认：现有 resolver 结构支持 plan 要求的 taxonomy 区分。**
- `_terminal_answer.py:86-107` — `_optional_descriptor_text`：字段缺失/空白返回 None，非 str 抛 `HostDurableError`。**确认。**

### 结论

封闭 taxonomy 完整，check location 明确，现有 `sqlite_payload_object` 已产生可区分 cause text，required wrapper 只需为 pair 缺失 / content missing/blank 路径补充具体消息。`PF-05: fixed`。

---

## Controller rejected concerns 复核

### MiMo F01/F02/F03：current-code invariant gap — 不重开

Controller rejected reason：Sections 7 and 10 already name the exact public and durable validators, conditional invariants, blank-content rejection, and tests. These are current-code gaps the plan exists to implement.

plan §7.1 指定 `HostFinalAnswerView.content` 必须非空非空白。§7.2 指定 durable row validator 条件校验。§10 change 5 指定 `OutboxTerminalItem` 条件不变量。plan 正确描述了要实现的 invariant，当前代码缺失是实现任务，不是 plan gap。**不重开。**

### MiMo F05：metadata 来源 — 不重开

Controller rejected reason：Content source selection and final-answer metadata are distinct facts. The plan correctly keeps `filtered/degraded/finish_reason` owned by canonical `RUN_SUCCEEDED`.

plan §4 owner boundary 表、§6.1、§6.2 均明确 metadata 从 canonical `RUN_SUCCEEDED` payload 读取，不随 content source 切换。**不重开。**

### DS F01：inline source provenance — 不重开

Controller rejected reason：`docs/host/design.md` explicitly authorizes inline `RUN_SUCCEEDED.final_answer` or digest-checked artifact `content`; retaining the owner policy is not undocumented compatibility code.

plan §5.2、§3.1 引用 design.md 支持 inline source。controller 接受。**不重开。**

### DS F05/F06：exact change site — 不重开

Controller rejected reason：already specified by plan sections 7.1, 10 exact changes, and the behavior matrix.

plan §10 change 5 明确了 `HostFinalAnswerView` 和 `OutboxTerminalItem` 的修改点。**不重开。**

### DS F07：terminal_payload.py — 不重开

Controller rejected reason：informational; no forced file churn.

plan §10 允许文件列表包含 `terminal_payload.py` 但注明"仅用于澄清 docstring/语义；若无需修改则不触碰"。**不重开。**

### 结论

Controller rejected 的 7 项 concern 均未被 plan 重开，保持 rejected 状态。**无新直接证据要求重开任何 rejected concern。**

---

## 新 blocking finding 检查

### 检查项 1：`build_outbox_terminal_item_row` 签名变更

plan §6.2 / §10 change 3 要求 `build_outbox_terminal_item_row` 增加显式 `HostTransaction` 参数。当前 `outbox.py:166` 调用 `build_outbox_terminal_item_row(event)` 无 transaction 参数。这是 plan 要求的修改，不是 plan gap；plan 已在 §10 change 3 明确"consumer、tests 和所有调用点迁移新签名，不提供旧签名 overload/wrapper"。**不构成为 finding。**

### 检查项 2：smoke test 扩展

plan §6.5 / §10 behavior tests 要求扩展 production smoke 断言 final answer content、descriptor-only canonical shape、live/read/drain 一致性。当前 smoke test 不做这些断言。这是 plan 要求的实现工作，不是 plan gap。**不构成为 finding。**

### 检查项 3：`_validate_outbox_terminal_payload` succeeded + `final_answer=None`

当前 `api.py:3149-3166` 的 succeeded 分支不检查 `final_answer`。plan §7.1 / §10 change 5 要求补齐。这是 plan 要实现的 invariant，不是 plan gap。controller 已 reject 此类 finding（MiMo F01）。**不构成为 finding。**

### 检查项 4：`HostFinalAnswerView.content` 允许空白

当前 `api.py:2728` 只检查 `isinstance(str)`。plan §7.1 要求拒绝空白 content。这是 plan 要实现的 invariant。controller 已 reject（MiMo F02）。**不构成为 finding。**

### 检查项 5：design.md:3082 措辞精度

plan §3.1 引用 `docs/host/design.md:3082` 称"inline `RUN_SUCCEEDED.final_answer` 与 digest-checked terminal artifact `content` 都是明确允许的 continuity source"。代码证据显示该行讨论 Trace Memory 和 `RUN_SUCCEEDED` assistant final-answer continuity，但未逐字提到 `final_answer` 字段名。措辞略过强，但 controller 在 DS F01 rejection 中已接受此引用路径，且设计真源确实授权了两种 source。**不构成为 finding。**

### 结论

**0 新 blocking finding。**

---

## 1 slice 合理性

plan §10 论证 1 个 slice 的合理性：修改量围绕同一个 terminal-answer projection contract。拆成 resolver contract / Outbox materialization / public invariant 三个 slice 会产生 contract-only 半成品（"resolver 已有但 Outbox 仍丢 answer" 或 "public succeeded 必填但 producer 仍写 NULL"）。

controller rejected MiMo R03（slice 过粗需要拆分），确认 1 slice 合理。

修改范围仅涉及 `_terminal_answer.py`、`read_api.py`、`outbox.py`、`api.py`、`durable/outbox.py` 五个生产文件，加上约 10 个测试文件。一个 implementation agent 和 reviewer 可在单次上下文中稳定承载该范围。**1 slice 合理。**

---

## Final plan re-review conclusion

**Verdict: `pass`**

**Blocking questions: 0。**

**Rationale**：

1. **PF-01 fixed**：6 处源证据行引用全部经代码确认准确，stale citation 已纠正。
2. **PF-02 fixed**：7 处 ProjectionRunner 事务边界代码证据确认，consumer apply / Outbox insert / checkpoint advance 在同一 `BEGIN IMMEDIATE` 内；failure row 在 rollback 后由独立 `run_write` 持久化。非原子行为已设为 stop condition。
3. **PF-03 fixed**：`FinalAnswerWorkerFactory` 存在且经 production ingest/closeout 路径。plan 正确要求扩展 smoke 断言 final answer content 和 descriptor-only canonical shape，当前 smoke gap 是实现任务不是 plan gap。
4. **PF-04 fixed**：恢复机制从模糊的"PayloadStore 恢复"改为具体的 test-only durable row INSERT（参照 `test_storage_maintenance.py:837-857`），5 步测试流程完整可行。
5. **PF-05 fixed**：11 种封闭 error taxonomy 完整，check location 明确（`_terminal_answer.py` pair check + `payload_resolution.sqlite_payload_object`），现有代码已产生可区分 cause text，failure row 断言规格固定。
6. **Controller rejected concerns**：7 项均未重开，保持 rejected 状态。
7. **0 新 blocking finding**。
8. **1 slice 合理**：修改量围绕同一 terminal-answer projection contract，拆分会产生 contract-only 半成品。
9. plan 已达 code-generation-ready：owner boundary、API、source precedence、required/optional 与 strict/lenient policy、transaction boundary、descriptor recovery、production smoke、错误 taxonomy、public/durable invariant、failure matrix、allowed files、行为测试、验证命令、README 决策、stop condition 和 handoff 均已固定。

**Finding count**: 0（本轮）。

**Artifact**: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-rereview-mimo.md`
