# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-B S1 Deepreview

## Scope

- **Mode**: current changes（相对 accepted plan bookkeeping commit）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `4c6ec694`（accepted P3-B plan bookkeeping commit）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-ds.md`
- **Included scope**: P3-B intended diff — `dayu/host/_terminal_answer.py`, `dayu/host/read_api.py`, `dayu/host/outbox.py`, `dayu/host/api.py`, `dayu/host/durable/outbox.py`, `dayu/host/terminal_payload.py`, `dayu/host/README.md`, `tests/host/test_terminal_payload.py`, `tests/host/test_read_api_terminal_policy.py`, `tests/host/test_outbox_projection.py`, `tests/host/test_outbox_durable.py`, `tests/host/test_public_open_host_options.py`, `tests/host/test_public_outbox_api.py`, `tests/host/test_public_offline_outbox_smoke.py`
- **Excluded scope**: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`（并发无关文件，按要求排除）；`docs/reviews/*`（既有 review artifacts）；`docs/host/issues-implementation-control.md`（仅 control doc 行号修正，非实现变更）
- **Parallel review coverage**: 无（单 reviewer 逐文件走读全部 diff）

## 审阅依据

- `AGENTS.md` / `CLAUDE.md`
- `docs/host/design.md`（特别是 terminal answer continuity resolver 与 Outbox 派生语义）
- `docs/engine/design.md`（Engine 不拥有 Host 持久化/Outbox/memory/read API）
- Accepted plan: `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`

## 验证结果摘要

| 验证项 | 结果 |
|---|---|
| 聚焦行为测试（71 个） | 全部通过 |
| 传播回归测试（290 个） | 全部通过 |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | 通过（无空白诊断） |
| owner/source scan | 单 owner，无遗留越界 parser |

---

## Findings

### 1 — 未修复 — 低 — `HostFinalAnswerView.content` 空白字符串防御差异

- **入口/函数**: `read_api._final_answer_from_outbox_json` → `HostFinalAnswerView.__post_init__`
- **文件（行号）**: `dayu/host/read_api.py:845-855`
- **输入场景**: Outbox durable row 的 `final_answer_json` 被外部 corruption 写入 `{"content": "", ...}` 且 `terminal_status`、`filtered`、`degraded` 均合法。
- **实际分支**: `_final_answer_from_outbox_json` 仅检查 `isinstance(content, str)`（行 845），空字符串通过该检查。随后 `HostFinalAnswerView(content="")` 在 `__post_init__` 中由 `_require_non_empty` 抛出 `ValueError("HostFinalAnswerView.content must be non-empty")`。
- **预期行为**: 当前行为在功能上正确——空白 content 被下游 `HostFinalAnswerView` 构造拒绝，且 producer（`required_assistant_final_answer_continuity_text`）保证不产生空 content。异常只会在 raw DB 损坏时触发。
- **实际行为**: 与预期一致；异常类型为 `ValueError` 而非 `HostDurableError`，`_outbox_item_from_row` docstring 声明的异常类型与实际抛出不严格一致。
- **直接证据**: `read_api.py:845` 的 `isinstance(content, str)` 检查不含 `.strip() == ""` 排除逻辑；对比 `_final_answer_json`（`outbox.py:370-372`）通过 `required_assistant_final_answer_continuity_text` 保证非空。`read_api.py:855` 构造 `HostFinalAnswerView` 时由 `api.py:2739-2742` 的 `_require_non_empty` 兜底。
- **影响**: 仅在 raw DB 损坏场景下错误类型/消息精度略低于预期，不影响正常路径正确性。
- **建议改法和验证点**: 在 `_final_answer_from_outbox_json` 中增加非空/非空白校验，使 durable read boundary 提供 Outbox-row-specific 错误诊断。补充测试：构造 `final_answer_json` 含空 content 的 raw row，断言 `HostDurableError` 且消息含 `outbox` 标识。
- **修复风险**: 低——仅加固 read boundary 防御层，不改变正常路径。
- **严重程度**: 低

### 2 — 未修复 — 低 — `finish_reason` 非文本字段在 Outbox/resolver 路径缺少显式行为测试

- **入口/函数**: `outbox._final_answer_json` / `read_api._succeeded_host_event`
- **文件（行号）**: `dayu/host/outbox.py:381-384`，`dayu/host/read_api.py:925-929`
- **输入场景**: canonical `RUN_SUCCEEDED` payload 中 `finish_reason` 为非文本值（如整数 `123`）。
- **实际分支**: `outbox.py` 通过 `_event_payload.optional_payload_text` 读取 `finish_reason`（行 381-384）；`read_api.py` 通过 `_optional_payload_text` 读取（行 925-929）。两者均对非文本值抛出 `HostDurableError`——行为正确。
- **预期行为**: malformed canonical metadata 应 fail closed，当前实现已正确满足。
- **实际行为**: 与预期一致。
- **直接证据**: `_event_payload.py:442-444`：`isinstance(value, str) and value.strip() != ""` 之外的路径抛 `HostDurableError`。`read_api.py:1655`：`not isinstance(value, str) or value.strip() == ""` 抛 `HostDurableError`。两者语义等价。但 `tests/host/test_outbox_projection.py:694-790` 的 `test_succeeded_projection_rejects_invalid_metadata_or_summary_pair` 参数化矩阵覆盖了 `filtered` 缺失/非 bool、`degraded` 缺失/非 bool、单边 summary ref，未覆盖 `finish_reason` 非文本。`tests/host/test_read_api_terminal_policy.py:208-238` 的 descriptor error 参数化矩阵同样未覆盖 `finish_reason` 类型非法。
- **影响**: 代码路径正确，但缺少显式回归保护。若未来重构 `optional_payload_text` 行为，该 case 可能被静默吞掉。
- **建议改法和验证点**: 在 `test_outbox_projection.py` 的 parameterized matrix 或独立测试中增加 `finish_reason=123` 的 case，断言 `HostDurableError` 且 `failure.last_error_message` 包含 `finish_reason`。
- **修复风险**: 低——仅新增测试用例。
- **严重程度**: 低

### 3 — 未修复 — 低 — `read_api._final_answer_from_outbox_json` 对 `content` 非空的校验完全委托给下游 `HostFinalAnswerView`

- **入口/函数**: `read_api._final_answer_from_outbox_json`
- **文件（行号）**: `dayu/host/read_api.py:845-855`
- **输入场景**: 同 Finding 1。
- **实际分支**: 同 Finding 1。
- **预期行为**: durable read boundary 应提供与 durable write boundary（`_validate_item_row` 行 843-846）同等级的 field-level 校验。当前 write boundary 明确拒绝 `succeeded + final_answer_json=None`，但 read boundary 对 content 非空的校验委托给了 public dataclass 构造层。
- **实际行为**: 功能正确但校验层次不一致。
- **直接证据**: 对比 `durable/outbox.py:843-846`（write boundary 显式检查 succeeded + None）与 `read_api.py:845`（read boundary 仅检查 str 类型，非空检查由 `HostFinalAnswerView` 间接提供）。
- **影响**: 同 Finding 1。
- **建议改法和验证点**: 同 Finding 1。
- **修复风险**: 低。
- **严重程度**: 低

---

## Adversarial 审查逐项结论

### 1. required/optional resolver source precedence、strict/lenient 边界

**结论：通过。**

- Source precedence 固定为 inline `final_answer` → descriptor pair 双缺失 → descriptor 校验 → 顶层 `content`。`_resolve_assistant_final_answer_continuity_text`（`_terminal_answer.py:101-155`）在单个私有 core 中实现全部逻辑，required helper（行 72-98）和 optional helper（行 35-69）共用同一 core。
- `_optional_descriptor_text`（行 158-179）正确将 descriptor 字段缺失、None、纯空白归一为 absent；非文本立即抛 `HostDurableError`。
- Descriptor pair 双缺失：optional 返回 `None`，required 抛 `"inline answer and descriptor pair are missing"`。
- Descriptor pair 单边：无论 lenient/strict/required 均立即抛 `"must pair"`，不降级。
- Descriptor row missing / digest mismatch / SQLite row missing / JSON invalid / non-object：由 `sqlite_payload_object` 内部抛 `HostDurableError`，含稳定 `"descriptor is missing"` / `"payload digest mismatch"` / `"sqlite payload row is missing"` / `"JSON is invalid"` / `"JSON must be object"` cause fragment。
- Content missing/blank：optional 返回 `None`（含分类诊断供 required 使用），required 抛 `"content is missing"` / `"content is blank"`。
- Content 非文本：`terminal_payload_content_text_from_payload` + `STRICT_NON_EMPTY` → `"content must be text"`，lenient 也 fail closed（`test_continuity_resolver_rejects_non_text_descriptor_content_even_lenient` 验证）。
- 裸 `content`、`summary_text`、nested `summary` 均不被读取（`terminal_payload.py` 只读 `final_answer` 和 artifact `content`）。
- 测试覆盖：`tests/host/test_terminal_payload.py` 全覆盖上述 taxonomy。

### 2. canonical metadata 始终来自 RUN_SUCCEEDED，content 可 descriptor fallback

**结论：通过。**

- `read_api._succeeded_host_event`（行 900-946）：`filtered`（行 915-919）、`degraded`（行 920-924）、`finish_reason`（行 925-929）全部从同一 `payload`（即 `_payload_object(row)` 返回的 canonical RUN_SUCCEEDED inline payload）读取。Content 从 `required_assistant_final_answer_continuity_text` 获取。
- `outbox._final_answer_json`（行 354-387）：`filtered`/`degraded` 从同一 `payload` 读取，`finish_reason` 同理。Content 从同一 resolver 获取。
- `test_succeeded_terminal_projection_reads_descriptor_content_and_canonical_metadata`（`test_read_api_terminal_policy.py:180-206`）显式验证 metadata 来自 canonical payload 而非 artifact：artifact 中 `filtered=False, degraded=True` 但 canonical payload 中 `filtered=True, degraded=False`，断言 HostEvent 使用后者。
- `test_descriptor_only_and_inline_precedence_materialize_complete_answer`（`test_outbox_projection.py:285-370`）对 Outbox 做同等验证。

### 3. Outbox consumer 同事务 resolve/insert/checkpoint

**结论：通过。**（代码核对确认 §6.3 事务假设成立，未触发 stop condition）

- `OutboxTerminalProjectionConsumer.apply_event`（`outbox.py:149-180`）接收 `ProjectionRunner` 传入的同一 `HostTransaction`，传给 `build_outbox_terminal_item_row` 和 `insert_outbox_terminal_item_if_absent`。
- `build_outbox_terminal_item_row`（行 230-295）内 `_final_answer_json` 调用 `required_assistant_final_answer_continuity_text(transaction, payload)`，使用同一 transaction。
- `insert_outbox_terminal_item_if_absent`（`durable/outbox.py:244-306`）在同一 transaction 内校验、判重、INSERT、读回确认。
- Plan §6.3 描述的 `ProjectionRunner._process_next_event` 在 `run_write` 内执行整条链（resolver → row builder → insert → checkpoint advance），异常 rollback 后 `_record_failure` 在独立 transaction 写 failure row。
- `test_descriptor_failure_rolls_back_and_same_descriptor_retry_is_idempotent`（`test_outbox_projection.py:438-639`）完整验证：删除 descriptor → catch-up 得到 1 failure + item 不存在 + checkpoint 未推进 + failure row 含 `"descriptor is missing"`；恢复 descriptor → retry 原子写 item + 推进 checkpoint + 清除 failure；同 typed event 再次 apply 返回 `DUPLICATE` + item 数仍为 1。

### 4. public/durable succeeded 必填、non-success 禁止

**结论：通过。**每层边界均闭合：

| 边界 | 文件（行号） | 校验内容 |
|---|---|---|
| Public `HostFinalAnswerView` 构造 | `api.py:2728-2750` | content 非空、非纯空白 + terminal_status 必须为 SUCCEEDED |
| Public `HostEvent` terminal payload | `api.py:3104-3131` | SUCCEEDED 必须携带 final_answer；非成功禁止 final_answer |
| Public `OutboxTerminalItem` terminal payload | `api.py:3153-3174` | SUCCEEDED 必须携带 final_answer 且禁止 error/cancel；非成功（含 LOST）禁止 final_answer |
| Durable write（`_validate_item_row`） | `durable/outbox.py:843-851` | SUCCEEDED → final_answer_json 必填；非成功（含 failed/cancelled）→ 禁止 final_answer_json；LOST 被 terminal_status enum 拒绝（行 837-838） |
| Durable read（`_item_row_from_host_row` → `_validate_item_row`） | `durable/outbox.py:916-980` | 每次从 DB 读出 row 后立即校验，raw DB 损坏在 read boundary fail closed |
| Outbox JSON read（`_final_answer_from_outbox_json`） | `read_api.py:823-861` | terminal_status 必须为 succeeded（行 853-854）；content 必须为 str（行 845） |

测试覆盖：
- `test_public_outbox_terminal_final_answer_invariants`：succeeded+None 拒绝、failed/cancelled/lost+final_answer 拒绝。
- `test_item_write_rejects_invalid_terminal_final_answer_combinations`：durable write boundary 拒绝 succeeded+NULL 和 non-success+JSON。
- `test_durable_read_rejects_raw_succeeded_row_without_final_answer`：raw DB NULL corruption 在 read boundary 被拒绝。
- `test_host_event_terminal_final_answer_contract`（含新增空白 content case）：HostEvent succeeded 必填 + HostFinalAnswerView 空白拒绝。

### 5. production FinalAnswerWorkerFactory smoke

**结论：通过。**

`test_offline_read_and_idempotent_drain_do_not_write_eventlog`（`test_public_offline_outbox_smoke.py:34-132`）：
- 使用 production `FinalAnswerWorkerFactory` → `open_host` → `submit_followup` 完整路径（非 inline fixture）。
- 从 SQLite `TABLE_EVENT_LOG` 直读 canonical `RUN_SUCCEEDED` payload（`_descriptor_only_terminal_payloads` 行 293-340），断言 `"final_answer"` key 不存在、`terminal_summary_ref`/`terminal_summary_digest` 均为非空文本、descriptor digest 与 canonical digest 相等。
- 断言 live `HostEvent.final_answer.content`、read `OutboxTerminalItem.final_answer.content`、drained `item.final_answer.content` 三者均等于 `final:1:<run_id>`。
- 断言 metadata：`filtered=False`、`degraded=False`、`finish_reason="stop"` 三者一致。
- 断言 `terminal_event_id` / `dedupe_key` 在 live、read、drained 间对齐。
- 断言 drain 幂等（同 request 重放返回同 item_ids）、drain 不写 EventLog。

### 6. 删除 read_api 第二 parser 和 Outbox inline parser

**结论：通过。**无遗漏调用、无兼容 wrapper。

- `rg "_terminal_payload_object\|_sqlite_payload_object" dayu/host` — 零命中（read_api 旧私有 descriptor/SQLite parser 已完全删除）。
- `rg "_PAYLOAD_FIELD_FINAL_ANSWER" dayu/host` — 仅在 `terminal_payload.py`（低层 helper 的字段名常量）中出现，Outbox 不再定义/使用自己的 inline final_answer 字段 reader。
- `read_api.py` 仅 import `required_assistant_final_answer_continuity_text`（行 49-51），不保留旧 parser 的 import 或透传 facade。
- `outbox.py` 仅 import `required_assistant_final_answer_continuity_text`（行 17-19），`_final_answer_json` 不再读取 `_PAYLOAD_FIELD_FINAL_ANSWER` 常量或自行解析 inline answer。
- 严格类型：所有新增/修改函数均有完整类型标注（`str | None`、`tuple[str | None, str | None]`、`Mapping[str, JsonValue]`），无 `Any`、`object`、`hasattr`、`getattr`。
- 中文 docstring：所有新增 public/private 函数均含完整中文 docstring（参数、返回值、异常）。
- 无 lazy import：所有 import 均为模块顶层静态导入。

### 7. propagation audit

**结论：通过。**逐路径核查：

**正向传播：**
```
Engine FinalAnswerData.content
  → engine_ingest._final_answer_plan（拒绝空白成功 content）
  → _write_terminal_payload（写入 {content, finish_reason, filtered, degraded}）
  → payload descriptor + SQLite payload row
  → terminal_closeout_in_transaction
  → RUN_SUCCEEDED canonical payload
       terminal_summary_ref / terminal_summary_digest
       finish_reason / filtered / degraded
  → Host terminal-answer continuity resolver（_terminal_answer.py:101-155）
       inline final_answer first
       otherwise digest-checked descriptor top-level content
```

从 resolver 分叉验证：

| 消费路径 | 文件 | 调用 | 状态 |
|---|---|---|---|
| HostEvent/live read | `read_api.py:911` | `required_assistant_final_answer_continuity_text(transaction, payload)` | ✅ |
| Outbox row | `outbox.py:370` | `required_assistant_final_answer_continuity_text(transaction, payload)` | ✅ |
| Outbox public read | `read_api.py:811` | `_final_answer_from_outbox_json(row.final_answer_json)`（不回读 descriptor） | ✅ |
| durable memory | `durable/memory.py:393-400` | `assistant_final_answer_continuity_text(..., STRICT_NON_EMPTY)` | ✅ |
| compact material | `compact_material.py:2213-2219` | `assistant_final_answer_continuity_text(...)` | ✅ |
| RunInputBuilder | `run_input.py:3220-3240` | `assistant_final_answer_continuity_text(...)` | ✅ |
| 纯 Conversation Memory | `memory.py:1650-1657` | 消费 typed `assistant_final_answer_text`；仅在 typed material 缺失时 descriptor-blind lenient inline fallback | ✅（不新增 transaction/artifact 依赖） |

**负向传播：**
```
RUN_FAILED / RUN_CANCELLED / RUN_LOST
  → never call/promote terminal answer resolver as final answer
  → HostEvent.final_answer = None（read_api.py:949-1049）
  → failed/cancelled Outbox final_answer_json = None（outbox.py:368-369）
  → lost Outbox skip（outbox.py:162-167）
  → no assistant answer memory/compact/run-input producer
```

- `test_failed_and_cancelled_ignore_forged_final_answer_sources` 验证 forged `final_answer`/`content`/descriptor 不被提升。
- `test_failed_terminal_projection_never_builds_final_answer` / `test_cancelled_terminal_projection_never_builds_final_answer` / `test_lost_terminal_projection_never_builds_final_answer` 覆盖三种非成功终态。
- `test_run_lost_is_skipped_without_public_outbox_item` 验证 LOST 显式 skip + 不创建 public item。

**一致性检查：**
- 内容等值：production smoke 断言 live/read/drain content 严格相等（`==`）。
- terminal identity 不变：live/read/drain 的 `terminal_event_id` / `dedupe_key` 一致。
- descriptor/digest 不泄漏到 LLM-facing text：resolver 只返回 content 文本，不拼接 ref/digest。
- Outbox failure 不改变 Run truth：Outbox projection 只读取 EventLog，不写 EventLog/Run/Attempt。
- memory/compact/run input 没有新增独立 parser：全部通过同一 resolver 的 typed material 消费。

---

## 过度耦合 / Semantic Drift 扫描

- **单一 owner**：`_terminal_answer.py` 是 descriptor-aware source selection 的唯一 owner。所有消费者通过 `required_assistant_final_answer_continuity_text` 或 `assistant_final_answer_continuity_text` 两个 public contract 接入。
- **无跨层穿透**：Outbox 和 read API 不直接读取 `payload_resolution` 或 `sqlite_payload_object`；descriptor 读取完全封装在 resolver 内。
- **无协议泄漏**：`HostFinalAnswerView` 不暴露 `payload_ref`、`digest`、`cursor` 或内部治理字段给 LLM-facing 上下文。
- **无下游修正上游语义**：纯 memory consumer 在 typed material 缺失时保留 lenient inline fallback，但这是 design-approved bounded memory policy，不是语义漂移——该 consumer 明确不跟随 descriptor、不开启 transaction、不新增 artifact 依赖。
- **无测试越过 owner**：所有测试通过 resolver public contract 或 typed material 验证行为，没有测试直接 mock `_resolve_assistant_final_answer_continuity_text` 内部私有函数或跳过 owner 自行构造 content。

---

## 状态机审查

**Outbox projection 状态转换：**

| 当前状态 | 触发事件 | 下一状态 | 验证 |
|---|---|---|---|
| (初始) | terminal EventLog row committed | ProjectionRunner catch-up → apply_event → item INSERT + checkpoint advance | `test_same_terminal_event_replay_does_not_duplicate` |
| checkpoint 已过 event | 同 terminal event replay | DUPLICATE（不新增 item，checkpoint 可推进） | 同上 |
| resolver/row builder 抛异常 | apply transaction 内异常 | rollback（item + checkpoint 均不提交）→ failure row 独立持久化 | `test_descriptor_failure_rolls_back_and_same_descriptor_retry_is_idempotent` |
| failure row 存在 + checkpoint 未推进 | catch-up 重试 | catch-up 停在 failure event 前（不越过） | 同上 |
| descriptor 恢复 + 重试 | 同 event 再次 apply | item 原子写入 + checkpoint 推进 + failure 清除 | 同上 |
| 终态 item 存在 + checkpoint 已推进 | 同 event 再次 apply | DUPLICATE（idempotency） | 同上 |

所有状态转换均经行为测试验证。终态均为 absorbing：checkpoint 推进后不再为该 event 重复生成 item；failure 清除后不再为该 event 重复记录 failure。

---

## 参数有效性

- `inline_text_policy`：仅影响 inline `final_answer` 字段的 strict/lenient 行为；不影响 descriptor pair、descriptor integrity、digest 或 content 类型校验。Optional resolver 接收 caller 传入的 policy，required resolver 固定使用 `STRICT_NON_EMPTY`。
- `text_policy` 对 descriptor content：resolver core 固定使用 `STRICT_NON_EMPTY`，不随 caller policy 变化——descriptor content 校验始终 strict fail closed。
- `HostTransaction`：从 `ProjectionRunner` → `apply_event` → `build_outbox_terminal_item_row` → `_final_answer_json` → resolver 全链路透传同一实例，无重新 open、替换或 nil 穿透。

---

## Open Questions

无。

---

## Residual Risk

1. **DDL conditional CHECK**：当前 SQLite schema 无 conditional CHECK 强制 `succeeded` row 的 `final_answer_json` 非 NULL。Producer + durable row validator + read boundary validator 三层覆盖正常路径；raw DB 手动损坏在 read boundary 被 `_validate_item_row` 拒绝。数据库级 closed-set hardening 仍归 P3-J，不在本 WU 范围。
2. **P3-C compact/evidence contract**：当前不修改 compact payload/evidence contract。若未来要求 answer 自动升级为 evidence-backed fact 或 session summary，需先修改 design truth。
3. **Descriptor storage 自动 repair**：超出 P3-B 范围。当前保证 failure 可观察、无半成品、恢复后可 retry。
4. **Finding 1/3 的低严重度 gap**：`_final_answer_from_outbox_json` 对 content 非空的校验依赖下游 `HostFinalAnswerView`。正常路径下 producer 保证非空；raw DB 损坏时可触发，但已有 `_validate_item_row` 在 durable read boundary 提供第一道防线（仅在 `_item_row_from_host_row` 调用路径生效；`_final_answer_from_outbox_json` 的独立调用路径无此保护）。建议后续加固。

---

## Verdict

**P3-B S1 implementation 达到 ship 标准。** 所有 plan 成功信号均被验证通过，7 项 adversarial 审查逐项结论为"通过"，无 critical/high severity finding。3 项 low severity findings 均为防御层加固建议，不阻塞 merge。

Resolved source findings 状态：
- Finding 01：**fixed** — Outbox/read API 统一调用 terminal-answer resolver，descriptor-only production shape 正确生成非空 final answer。
- DS-2：**fixed** — Outbox 的 inline-only final answer reader 已删除；read API 的第二套 descriptor/SQLite parser 已删除。所有消费者收敛到同一 resolver。
- DS-4：**fixed** — Outbox 不再自行决定 final answer 来源；`_final_answer_json` 调用 required resolver，result refs/summary refs/terminal diagnostics/idempotency identity 仍由 Outbox owner 持有。
- Controller P3-B：**fixed** — 所有消费者通过 typed boundary 调用同一 resolver/helper；纯 memory consumer 消费 typed value 不反向打开 descriptor；Outbox public read 消费已 materialize 的 `final_answer_json` 不二次打开 artifact。

**Findings: 3（均为 Low），Verdict: PASS，Artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-ds.md`**
