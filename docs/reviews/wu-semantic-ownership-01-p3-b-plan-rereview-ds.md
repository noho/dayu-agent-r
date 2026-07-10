# WU-SEMANTIC-OWNERSHIP-01 P3-B Plan Re-Review — Adversarial (AgentDS)

## Review metadata

- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`（plan-fix 后版本）
- **Review type**: adversarial plan re-review（planreview skill）
- **Gate**: parallel plan re-review；复核 controller 真源 `P3-B-PF-01` 至 `P3-B-PF-05` 的完整修复状态，不修改 plan / code / test / control / 其它 artifact
- **Reviewer**: AgentDS
- **Timestamp**: 2026-07-10T14:25:55+08:00（本机系统时钟）
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-rereview-ds.md`

## Inputs

- Target plan: `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`
- Controller 真源: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-controller-adjudication.md`
- Plan-fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-fix-codex.md`
- 原始 review artifacts: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-ds.md`, `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-mimo.md`
- 真源: `CLAUDE.md`, `docs/host/design.md`, `docs/engine/design.md`, `docs/host/issues-implementation-control.md`

## Review scope

本次 re-review 的 scope 严格限定为：

1. 逐项验证 `P3-B-PF-01` 至 `P3-B-PF-05` 是否已在 plan-fix 中完整修复。
2. 核对 plan-fix artifact 是否与 controller 裁决一致。
3. 检查 controller rejected concerns 是否被正确保留（未重开）。
4. 验证 0 个新 blocking finding。
5. 验证 1 个 slice 的合理性。

本 review 不做：plan 全新 review、代码实施、修改任何 artifact、触碰 CLI-CI 并发文件、commit/push/PR。

## Direct code evidence verification

以下逐项核验 plan-fix 中引用的代码证据。

### 证据 1: `_final_answer_plan` (`engine_ingest.py:4885-4931`)

**Plan 声称**: Engine-origin 事实产生点，拒绝空白成功 content，将回答写入 terminal payload 顶层 `content`。

**实际代码**:
- Line 4893: `if data.content.strip() == "":` → 拒绝空白 content
- Line 4915-4920: `terminal_payload={"content": data.content, "finish_reason": ..., "filtered": ..., "degraded": ...}` → 将 content 写入 terminal descriptor payload，**不写** inline `final_answer`

**Verification**: ✅ 准确。行号、逻辑、字段均匹配。

### 证据 2: `_close_terminal` (`engine_ingest.py:1184-1283`)

**Plan 声称**: Engine-origin closeout，先 `_write_terminal_payload` 再 `terminal_closeout_in_transaction`，传递 descriptor pair。

**实际代码**:
- Line 1230-1235: `descriptor = self._write_terminal_payload(transaction, ...)` → 写入 payload 并获取 descriptor
- Line 1236-1267: `terminal_closeout_in_transaction(transaction, ..., terminal_summary_ref=descriptor.payload_ref, terminal_summary_digest=descriptor.payload_digest, ...)` → 传递 descriptor pair

**Verification**: ✅ 准确。

### 证据 3: `_write_terminal_payload` (`engine_ingest.py:3533-3573`)

**Plan 声称**: SQLite payload writer，调用 `write_sqlite_payload`。

**实际代码**:
- Line 3550-3573: 构造 `payload_json`，通过 `self._payload_store.write_sqlite_payload(transaction, ...)` 写入

**Verification**: ✅ 准确。

### 证据 4: `_run_terminal_payload` (`run_transition.py:4551-4584`)

**Plan 声称**: Durable canonical payload builder，持久化 `terminal_summary_ref/digest` 和 succeeded metadata，**不写** inline `final_answer`。

**实际代码**:
- Line 4569-4577: `payload = {"run_id": ..., "terminal_summary_ref": ..., "terminal_summary_digest": ..., "reason": ...}` → 固定持久化 descriptor pair
- Line 4580-4584: `if request.run_terminal_status == RunStatus.SUCCEEDED: payload["finish_reason"] = ...; payload["filtered"] = ...; payload["degraded"] = ...` → 仅 succeeded 写 metadata
- **无** `final_answer` 字段写入

**Verification**: ✅ 准确。行号、逻辑完全匹配。

### 证据 5: `docs/host/design.md:3082`

**Plan 声称**: 设计真源明确 inline `final_answer` 与 digest-checked artifact `content` 都是合法 continuity source。

**实际文本**:
> terminal answer continuity resolver 可以从已提交 terminal fact 的 inline `final_answer` 或 digest-checked terminal artifact `content` 读取 LLM-facing answer text。

**Verification**: ✅ 准确。inline source 是 design-approved，不是旧兼容代码。

### 证据 6: ProjectionRunner 事务原子性

**Plan 声称**: consumer apply、Outbox insert、checkpoint advance 在同一 `HostTransaction`，failure row 在独立事务写入。

**实际代码**:
- `projection.py:464-471`: `self._transaction_runner.run_write(lambda transaction: self._process_next_event(...))` → 一笔 write transaction
- `projection.py:626-644`: `_process_next_event` 内依次调用 `consumer.apply_event(transaction, event)`（line 632），`advance_projection_checkpoint(transaction, ...)`（line 637），`clear_projection_failure(transaction, ...)`（line 644）
- `outbox.py:147-168`: `apply_event` 接收 `transaction` 并调用 `insert_outbox_terminal_item_if_absent(transaction, row)`（line 167）
- `durable/outbox.py:243-305`: `insert_outbox_terminal_item_if_absent` 在传入 transaction 内 validate、判重、INSERT、读回
- `durable/transaction.py:288-360`: `run_write` 执行 `BEGIN IMMEDIATE` → operation → `COMMIT`；任何异常 rollback 后透传
- `projection.py:472-489`: `except _ProjectionApplyFailed as exc:` → 调用 `self._record_failure(...)` → 这是 out-of-transaction 调用
- `projection.py:653-685`: `_record_failure` 独立开启 `self._transaction_runner.run_write(lambda transaction: write_projection_failure(...))`（line 675）

**Verification**: ✅ 完全准确。apply/insert/checkpoint 共享同一事务，failure 在 rollback 后的独立事务写入。

### 证据 7: `FinalAnswerWorkerFactory` production smoke path

**Plan 声称**: factory 经 `EngineEvent(FINAL_ANSWER)` 产出，经 `open_host` production ingest/closeout 运行。

**实际代码**:
- `tests/host/public_smoke_support.py:280-292`: `FinalAnswerHandle.events()` 产出 `EngineEvent(type=EngineEventType.FINAL_ANSWER, data=FinalAnswerData(content=..., filtered=False, degraded=False, finish_reason=FinishReason.STOP))` → 真实 EngineEvent
- `tests/host/public_smoke_support.py:344`: `content = f"final:{len(self.factory.requests)}:{snapshot.run_id}"` → 确定性 answer content
- `tests/host/public_smoke_support.py:348-371`: `FinalAnswerWorkerFactory` 完整实现
- `tests/host/test_public_offline_outbox_smoke.py:28-97`: 已有 smoke 使用该 factory，经 `open_host` + `submit_followup` + `wait_for_status(SUCCEEDED)` 走完整 production 路径

**Verification**: ✅ 准确。factory 存在、经 production 路径产出 descriptor-only `RUN_SUCCEEDED`。

### 证据 8: test-only descriptor deletion/restore 模式

**Plan 声称**: `tests/host/test_storage_maintenance.py:837-857` 的 `_delete_payload_descriptor` 为 test-only durable mutation。

**实际代码**:
- Line 845-857: `def delete_descriptor(transaction): transaction.execute(f"DELETE FROM {TABLE_PAYLOAD_DESCRIPTORS} WHERE payload_ref = ?", ...)` → test-only mutation within `host._run_write(delete_descriptor)`

**Verification**: ✅ 准确。test-only pattern 存在且可复用。

### 证据 9: 当前 Outbox inline-only reader 证据

**Plan 声称**: `_final_answer_json` 只读 inline `final_answer`，缺失即返回 `None`。

**实际代码**:
- `outbox.py:346-379`: `_final_answer_json` — 只接收 `payload` 和 `terminal_status`，**无** `transaction` 参数
- Line 360: `content = optional_payload_text(payload, field_name=_PAYLOAD_FIELD_FINAL_ANSWER)` → 只读 inline `final_answer`
- Line 361-362: `if content is None: return None` → 无 descriptor fallback

**Verification**: ✅ 准确。当前确实 inline-only，production descriptor 不会被读取。

### 证据 10: 当前 public validator gaps

**Plan 声称**: `HostFinalAnswerView.content` 允许空白，`_validate_outbox_terminal_payload` 不检查 succeeded + `final_answer=None`，durable `_validate_item_row` 不做 status-aware `final_answer_json` 校验。

**实际代码**:
- `api.py:2728-2729`: `if not isinstance(self.content, str): raise TypeError(...)` → **无** `.strip() == ""` 检查
- `api.py:3157-3162`: succeeded 分支只检查 `error_message`/`cancel_reason` 为 None，**不检查 `final_answer` 是否存在**，然后直接 `return`
- `durable/outbox.py:821-873`: `_validate_item_row` 对 `final_answer_json` 只调用 `_require_optional_non_empty_text`（line 841），不与 `terminal_status` 关联
- `read_api.py:826-864`: `_final_answer_from_outbox_json` — `None` 直接返回 `None`（line 835-836），不检查 `terminal_status`

**Verification**: ✅ 全部准确。

## PF-01 至 PF-05 逐项 final status

### PF-01 — 修正源证据引用 ✅ FIXED

**Controller 要求**: 修正 `run_transition.py:4569-4584` 的旧引用，精确定位 Engine-origin 和 Host-lifecycle closeout 位置、durable payload builder、明确 inline 的 design authority。

**Plan-fix 实施**:
- §3.1 精确定位 4 个事实产生/持久化点（`_final_answer_plan`、`_close_terminal`、`_write_terminal_payload`、`_close_host_lifecycle_terminal`）
- 明确 `_run_terminal_payload:4551-4584` 写 descriptor pair + metadata、不写 inline
- 引用 `docs/host/design.md:3082` 作为 inline source 的 design authority
- §5.2 明确 inline 是 "当前明确契约，不是旧库兼容"

**直接证据核验**: 见上 §证据 1-5。所有行引用在代码中均精确匹配。

**Final status**: **FIXED**。无残留问题。

### PF-02 — 证明 ProjectionRunner 原子性 ✅ FIXED

**Controller 要求**: 添加具体代码引用证明 consumer apply、Outbox insert、checkpoint advance、rollback 和独立 failure recording；将非原子行为设为 stop condition。

**Plan-fix 实施**:
- §6.3 引用 `projection.py:464-471,626-644`、`outbox.py:147-168`、`durable/outbox.py:243-305`、`durable/transaction.py:288-360` 的事务证据
- §6.3 引用 `projection.py:472-489,653-685` 的独立 failure recording 证据
- §6.3 增加目标事务流程和 rollback 流程描述
- §6.3 增加 stop condition：若代码核对发现 apply/insert/checkpoint 不在同一事务，立即停止
- §10 将 stop condition 写入 S1 实现前检查点

**直接证据核验**: 见上 §证据 6。所有事务边界在代码中均精确匹配。

**Final status**: **FIXED**。原子性假设成立，stop condition 已设。

### PF-03 — 证明 production smoke 路径 ✅ FIXED

**Controller 要求**: 核实 `FinalAnswerWorkerFactory` 存在且经 production descriptor-only closeout；命名确切测试/支持文件和断言；不允许 inline-only fixture 替代 smoke。

**Plan-fix 实施**:
- §6.5 核实 `tests/host/public_smoke_support.py:242-292,314-371` 的 factory 实现
- §6.5 规格化 smoke 门槛：读取 canonical `RUN_SUCCEEDED.payload_json`，断言无 inline `final_answer` key、有完整 descriptor pair、digest 可校验
- §6.5 要求 live/read/drain answer content 都等于 `final:1:<run_id>`
- §6.5 stop condition：若 factory 不再产生 `FINAL_ANSWER` 或 smoke 只能靠 inline fixture 通过

**直接证据核验**: 见上 §证据 7。factory 存在、经 production ingest/closeout、产出 descriptor-only shape。

**Final status**: **FIXED**。smoke path 已验证且描述充分。

### PF-04 — 指定 descriptor 恢复与 retry 机制 ✅ FIXED

**Controller 要求**: 替换模糊的 "PayloadStore 恢复同 ref/digest" 说法；使用仓库真实 test mechanism；说明 recovery 方式、digest 保留方式、不使用 production repair API。

**Plan-fix 实施**:
- §6.4 否定模糊说法：明确 typed `write_sqlite_payload` 同时写 payload row + descriptor，不能做 descriptor-only restore
- §6.4 固定使用 `test_storage_maintenance.py:837-857` 的 test-only durable mutation 模式
- §6.4 给出 5 步精确步骤：保存 descriptor columns → test-only delete → catch-up 验证 failure → test-only INSERT 恢复（同 ref/digest/sqlite_payload_id）→ retry 验证 item+checkpoint+clear → replay 验证 DUPLICATE
- §6.4 禁止新增 production repair API、更换 ref/digest、删除既有 item

**直接证据核验**: 见上 §证据 8。test-only mutation pattern 存在且可复用。

**Final status**: **FIXED**。恢复机制具体、可执行、不越界。

### PF-05 — 封闭 descriptor-pair 与错误 taxonomy ✅ FIXED

**Controller 要求**: 指定 resolver 区分双缺失/单边损坏/missing descriptor/digest mismatch/invalid JSON/content missing/blank/non-text 的方法；明确检查位置和行为断言；failure row 保留可行动 cause。

**Plan-fix 实施**:
- §5.5 固定 owner check 在 `_terminal_answer.py` 模块级私有 resolution core
- §5.5 给出封闭 taxonomy 表（11 行）：双缺失、单边、descriptor missing、SQLite row missing、digest mismatch、JSON invalid、top-level non-object、content missing、content blank、content non-text、filtered/degraded 非 bool（见 §8 failure matrix 补充）
- 每类 failure 对应 `HostDurableError` + 可区分 cause fragment
- §10 behavior tests 要求每个 failure 断言 `last_error_code == "HostDurableError"` + 对应 `last_error_message`
- §5.5 明确诊断保持 internal，不进入 LLM-facing material
- 要求 required/optional 共用一个 resolution core

**直接证据核验**:
- `payload_resolution.py:175-177` → `descriptor is missing` ✅
- `payload_resolution.py:180-181` → `digest mismatch` ✅
- `payload_resolution.py:184-193` → `sqlite payload row is missing` ✅
- `payload_resolution.py:194-196` → `JSON is invalid` ✅
- `payload_resolution.py:213-215` → `JSON must be object` ✅
- 当前 `_terminal_answer.py:72-73` 对 ref/digest 缺失统一返回 `None` → 需要区分双缺失 vs 单边损坏（plan §5.5 已明确）

**Final status**: **FIXED**。taxonomy 封闭、每类有可区分 cause、location 和行为断言明确。

## Controller rejected concerns 保留检查

| Original Concern | Controller 裁决 | Plan-fix 状态 |
|---|---|---|
| MiMo F01/F02/F03 (invariant gaps) | Rejected: plan 已命名 exact changes，不是 plan gap | ✅ §7、§10 保留原 exact changes，未重开 |
| MiMo F05 (metadata 来源) | Rejected: metadata 继续从 canonical `RUN_SUCCEEDED` 派生 | ✅ §4 owner boundary 表、§6.2 明确 metadata 只从 canonical payload |
| DS F01 (inline provenance) | Rejected: design.md 明确允许 inline source | ✅ §3.1、§5.2 引用 design.md:3082，inline 保留 |
| DS F05/F06 (blank/site enumeration) | Rejected: plan 已明确 | ✅ §7.1、§10 exact changes 保留原规格 |
| DS F07 (terminal_payload.py) | Rejected: informational，不强制修改 | ✅ §10 allowed files: "仅用于澄清...若无需修改则不触碰" |
| MiMo F08 / DS F02 → PF-04 | Merged into PF-04 | ✅ §6.4 已覆盖 |
| DS F04 → PF-05 | Covered by PF-05 | ✅ §5.5 已覆盖 |
| DS F03 → PF-05 | Covered by PF-05 | ✅ §5.5 已覆盖 |
| MiMo F06 → PF-02 | Merged into PF-02 | ✅ §6.3 已覆盖 |
| MiMo F07 → PF-03 | Merged into PF-03 | ✅ §6.5 已覆盖 |

**Verification**: ✅ 所有 controller rejected concerns 均被正确保留，未重开。

## 0 个新 blocking finding 检查

逐项扫描后：

1. **Plan structure**: §1-§14 完整，从 gate/goals 到 completion format，无遗漏。
2. **Code evidence accuracy**: 所有代码引用（10+ 处）均与实际代码精确匹配。
3. **Allowed files boundary**: §10 明确列出 allowed production files（6 个）和 allowed test files（11 个），无越界。
4. **Stop conditions**: §10 列出 7 个 concrete stop conditions，覆盖 schema/DDL、import cycle、transaction non-atomic、factory path、cross-WU dependency、existing legitimate consumer conflict。
5. **Validation commands**: §10 提供完整 pytest + pyright + git diff + rg scan 命令。
6. **README decision**: §11 明确哪些 README 更新、哪些不更新、为什么。
7. **Non-goals**: §12 列出 8 项明确的 non-goals，边界清晰。
8. **Residual risks**: §12 列出 4 项 residual risks，均分配 owner（P3-J、future design truth 裁决）。
9. **Completion format**: §13 提供 structured handoff template。
10. **Propagation audit**: §9 给出正向和负向两条完整 audit trail。

**结论**: 0 个新 blocking finding。

## 1 个 slice 合理性检查

Plan §10 给出的 1-slice 论证：

> 修改量围绕同一个 terminal-answer projection contract。若拆成 resolver contract、Outbox materialization、public invariant 三个 slice，任一中间提交都会暂时保留 "resolver 已有但 Outbox 仍丢 answer" 或 "public succeeded 必填但 producer 仍写 NULL" 的 contract-only 半成品。一个 implementation agent 和 reviewer 可在单次上下文中稳定承载该范围。

**Re-review 判断**: ✅ 论证成立。

理由：
- Contract closure 问题：resolver → Outbox → public read → durable validator 四个边界必须同步关闭，否则中间任一 gate 会提交不一致的 contract
- 事务耦合：所有修改共享同一个 ProjectionRunner transaction，拆 slice 不会降低事务风险
- 认知负载：修改的生产文件仅 6 个，且围绕同一 `_terminal_answer.py` owner，一个 implementation agent 可以承载
- 对齐 control doc：`issues-implementation-control.md` 要求 slice 按语义闭环切分，不能按文件机械拆分
- 当前 6 个 production files 的修改是内聚的：新增 required helper → 迁移两个 consumer → 补齐三个 validator

**结论**: 1 slice 是最小可维护方案，不拆分的理由充分。

## Plan review conclusion

### PF fix status summary

| Fix | Status | Evidence |
|---|---|---|
| PF-01 (source evidence) | ✅ FIXED | §证据 1-5，5 处代码均精确匹配 |
| PF-02 (ProjectionRunner atomicity) | ✅ FIXED | §证据 6，事务边界证实成立 |
| PF-03 (production smoke) | ✅ FIXED | §证据 7，factory 存在且经 production 路径 |
| PF-04 (descriptor restore/retry) | ✅ FIXED | §证据 8，test-only mutation pattern 可用 |
| PF-05 (error taxonomy) | ✅ FIXED | §证据 9-10，taxonomy 封闭，所有 error cause 有对应代码锚点 |

### Final verdict: **pass**

**Blocking questions: 0.**
**New blocking findings: 0.**
**Controller rejected concerns reopened: 0.**

**Rationale**: Plan-fix 完整修复了 controller 要求的全部 5 项 plan fix。所有代码引用经实际文件逐项核验，行号精确、逻辑匹配。plan 已达到 code-generation-ready 标准：owner boundary 清晰、API signature 固定、source precedence 有 design authority、descriptor pair error taxonomy 封闭、transaction boundary 验证、production smoke path 确认、test restore mechanism 可执行、allowed files 受控、stop conditions 具体、propagation audit 完整、README 决策明确、1 slice 合理。controller rejected concerns 均被正确保留。

Plan-fix artifact（`docs/reviews/wu-semantic-ownership-01-p3-b-plan-fix-codex.md`）与 controller 裁决一致，其 PF-01 至 PF-05 的完成声明经代码核验后均可确认。

### Residual observations (non-blocking)

1. **`_terminal_answer.py:72-73` 当前将 ref/digest 双缺失和单边缺失统一返回 `None`**：这是一致性问题，plan §5.5 的 taxonomy 表已明确要求区分。plan 已规定了 resolution core 的实现要求，不需要额外的 plan-level 修改。

2. **`_final_answer_from_outbox_json` 在 `read_api.py:826-864` 目前未校验 blank content**：plan §7.1 和 §10 exact changes item 5 已明确 `HostFinalAnswerView.content` 必须拒绝空白，implementation 时需确保该 check 同时覆盖 `_final_answer_from_outbox_json` 中的 `content` 校验和 `HostFinalAnswerView.__post_init__`。

3. **Plan §6.4 的 test-only restore 使用 `TABLE_PAYLOAD_DESCRIPTORS` INSERT**：implementation agent 需确认 `_delete_payload_descriptor` 的删除未触发 foreign key cascade 删除 `TABLE_SQLITE_PAYLOADS` 中的对应 row。当前代码 `test_storage_maintenance.py:852-855` 仅 `DELETE FROM TABLE_PAYLOAD_DESCRIPTORS`，应无 cascade 风险，但实现时须确认 DDL 未设 `ON DELETE CASCADE`。

### Suggested tracking

无新增风险需追踪。现有 residual risks 已在 plan §12 中正确分配：
- DDL conditional CHECK → P3-J
- 跨副本 metadata 一致性 → future design truth 裁决
- descriptor storage 自动 repair → 不属于 P3-B

---

**Artifact path**: `docs/reviews/wu-semantic-ownership-01-p3-b-plan-rereview-ds.md`
