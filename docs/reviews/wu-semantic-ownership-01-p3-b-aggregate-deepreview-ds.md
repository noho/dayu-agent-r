# Aggregate Deep Review — WU-SEMANTIC-OWNERSHIP-01 P3-B S1

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-B`
- Gate: S1 aggregate deep review（完整 accepted plan / S1 范围：base `4c6ec694` → head `08394e52`）
- 此前 review chain:
  - S1 code review（DS + MiMo）→ 3 low findings（F01: content blank check delegation、F02: finish_reason 缺少行为测试、F03: content check 校验层次不一致）
  - S1 controller adjudication → accepted F01、F02；F03 合并入 F01
  - S1 fix → F01/F02 修复
  - S1 code re-review（DS + MiMo）→ both fixed, 0 new material findings
  - S1 re-review controller adjudication → accepted, S1 进入 aggregate deep review gate

## Scope

- **Mode**: current changes（aggregate，完整 accepted plan / S1 范围）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `4c6ec694`（accepted P3-B plan bookkeeping commit）
- **Head**: `08394e52`（P3-B S1 acceptance）
- **Intermediate**: `51ff4e28`（F01/F02 fix commit）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-deepreview-ds.md`
- **Included scope**:
  - 生产代码: `dayu/host/_terminal_answer.py`、`dayu/host/outbox.py`、`dayu/host/read_api.py`、`dayu/host/api.py`、`dayu/host/durable/outbox.py`
  - 依赖模块（只读）: `dayu/host/terminal_payload.py`、`dayu/host/payload_resolution.py`、`dayu/host/_event_payload.py`、`dayu/host/_public_validation.py`
  - 测试: `tests/host/test_terminal_payload.py`、`tests/host/test_outbox_projection.py`、`tests/host/test_outbox_durable.py`、`tests/host/test_read_api_terminal_policy.py`、`tests/host/test_public_outbox_api.py`、`tests/host/test_public_offline_outbox_smoke.py`、`tests/host/test_public_open_host_options.py`
  - 文档: `dayu/host/README.md`
- **Excluded scope**: `docs/cli_ci*.md|json`（并发无关）；`docs/reviews/*`（既有 review artifacts）；`docs/host/issues-implementation-control.md`（仅行号修正）

## 审阅依据

- `CLAUDE.md` / `AGENTS.md`
- `docs/host/design.md`（Host 架构真源）
- `docs/engine/design.md`（Engine 不拥有 Host 持久化 / Outbox / memory / read API）
- Accepted plan: P3-B（terminal final answer Outbox 语义收敛）
- 此前 review chain: S1 code review / controller adjudication / fix / re-review

## 验证结果

| 验证项 | 结果 |
|---|---|
| P3-B 聚焦测试（75 个） | 全部通过 |
| Host 全量回归测试（1716 个） | 全部通过，1 skipped，5 deselected |
| pyright（dayu/host/） | 0 errors, 0 warnings, 0 informations |
| git diff --check | 通过（无空白诊断） |

---

## P3-B 成功信号逐项复议

### 1. descriptor-only production continuity

**结论: 通过。** `_resolve_assistant_final_answer_continuity_text`（`_terminal_answer.py:101-155`）在 inline `final_answer` 缺失时通过 terminal descriptor pair（ref + digest）定位 SQLite artifact，校验 digest 后读取顶层 `content`。`test_descriptor_only_and_inline_precedence_materialize_complete_answer`（`test_outbox_projection.py:285-370`）验证 descriptor-only 场景下 Outbox projection 正确生成非空 final answer JSON，`filtered`/`degraded`/`finish_reason` 来自 canonical `RUN_SUCCEEDED` payload。production smoke（`test_public_offline_outbox_smoke.py`）通过 `FinalAnswerWorkerFactory` → `open_host` → `submit_followup` 完整路径验证 descriptor-only production shape：canonical payload 不含 `"final_answer"` key，`terminal_summary_ref`/`terminal_summary_digest` 均为非空文本，descriptor digest 与 canonical digest 一致，live/read/drain 的 `final_answer.content` 严格相等。

### 2. inline precedence（inline `final_answer` 优先于 descriptor `content`）

**结论: 通过。** Resolver core 固定先读 inline `final_answer`（行 119-124），命中后不访问 descriptor。`test_inline_final_answer_takes_precedence_over_descriptor`（`test_terminal_payload.py`）验证 inline 存在时 descriptor 不被读取；`test_descriptor_only_and_inline_precedence_materialize_complete_answer`（`test_outbox_projection.py`）验证 inline 优先路径下 metadata 仍来自 canonical payload。所有 consumer（HostEvent live read、Outbox projection、memory/compact/run_input）共用同一 resolver core，precedence 一致。

### 3. canonical metadata（filtered/degraded/finish_reason 始终来自 RUN_SUCCEEDED）

**结论: 通过。** `read_api._succeeded_host_event`（行 914-934）和 `outbox._final_answer_json`（行 354-387）均从同一 `payload`（`_payload_object(row)` 或 `event.payload`，即 canonical `RUN_SUCCEEDED` inline payload）读取 `filtered`、`degraded`、`finish_reason`。`test_succeeded_terminal_projection_reads_descriptor_content_and_canonical_metadata`（`test_read_api_terminal_policy.py:180-206`）显式验证 artifact 中 `filtered=False, degraded=True` 但 canonical payload 中 `filtered=True, degraded=False` 时 HostEvent 使用后者。`test_descriptor_only_and_inline_precedence_materialize_complete_answer` 对 Outbox 做同等验证。

### 4. public/durable invariants（succeeded 必填 final answer，non-success 禁止）

**结论: 通过。** 五层边界全部闭合：

| 边界 | 文件（行号） | 校验内容 |
|---|---|---|
| Public `HostFinalAnswerView` 构造 | `api.py:2728-2750` | content 非空 + terminal_status 必须为 SUCCEEDED |
| Public `HostEvent` terminal payload | `api.py:3104-3131` | SUCCEEDED 必须携带 final_answer；非成功禁止 |
| Public `OutboxTerminalItem` terminal payload | `api.py:3153-3174` | SUCCEEDED 必填 final_answer + 禁止 error/cancel；非成功（含 LOST）禁止 final_answer |
| Durable write（`_validate_item_row`） | `durable/outbox.py:822-882` | SUCCEEDED → final_answer_json 必填；非成功 → 禁止；LOST 被 terminal_status enum 拒绝 |
| Durable read（`_item_row_from_host_row` → `_validate_item_row`） | `durable/outbox.py:916-980` | 每次 DB 读出后立即校验，raw DB 损坏 fail closed |
| Outbox JSON read（`_final_answer_from_outbox_json`） | `read_api.py:823-865` | content 非空 + terminal_status 必须为 succeeded |

F01 fix 加固后：`_final_answer_from_outbox_json` 显式拒绝 `content == ""` 与纯空白文本（行 847-850），错误消息包含 `Outbox` / `field` / `content` 语义。测试 `test_read_corrupted_outbox_final_answer_content_rejected`（`test_public_outbox_api.py:105-187`）走 production Host 路径污染真实 SQLite raw row → public read → `HostApiError(INTERNAL_ERROR)` cause 含 Outbox field 诊断。

### 5. projection rollback/retry/idempotency

**结论: 通过。** `OutboxTerminalProjectionConsumer.apply_event`（`outbox.py:149-180`）在同一 `HostTransaction` 内完成 resolver → row builder → INSERT → checkpoint advance。`test_descriptor_failure_rolls_back_and_same_descriptor_retry_is_idempotent`（`test_outbox_projection.py:438-639`）完整验证：
- 删除 descriptor → catch-up 得 1 failure + item 不存在 + checkpoint 未推进 + failure row 含 `"descriptor is missing"`
- 恢复 descriptor → retry 原子写 item + 推进 checkpoint + 清除 failure
- 同 typed event 再次 apply → `DUPLICATE` + item 数仍为 1

`test_same_terminal_event_replay_does_not_duplicate` 验证 checkpoint 已推进后的 replay 幂等。`insert_outbox_terminal_item_if_absent` 的 duplicate check（`durable/outbox.py:259-270`）校验 identity（item_id/idempotency_key/event_sequence/run_id）一致才返回 DUPLICATE，否则抛 `"identity conflicts"`。

### 6. memory/compact/run-input 同源

**结论: 通过。** 逐路径核查：

| 消费路径 | 文件 | 调用 | 策略 |
|---|---|---|---|
| durable memory | `durable/memory.py:393` | `assistant_final_answer_continuity_text(..., STRICT_NON_EMPTY)` | optional contract，strict inline |
| compact material | `compact_material.py:2213` | `assistant_final_answer_continuity_text(...)` | optional contract |
| RunInputBuilder | `run_input.py:3236` | `assistant_final_answer_continuity_text(...)` | optional contract |
| 纯 Conversation Memory | `memory.py:1650-1657` | 消费 typed `assistant_final_answer_text`；仅在 typed material 缺失时 descriptor-blind lenient inline fallback | 不新增 transaction/artifact 依赖 |

所有路径通过同一 resolver（`_terminal_answer.py`）的 public contract 接入，无独立 parser、无重复 descriptor 读取、无绕过 resolver 直接访问 SQLite payload table。

### 7. failed/cancelled/lost negatives

**结论: 通过。** 三种非成功终态的负向传播均闭合：
- `RUN_FAILED`/`RUN_CANCELLED`: `_final_answer_json`（`outbox.py:368-369`）对 `HostTerminalStatus.SUCCEEDED` 以外的状态返回 `None`。`HostEvent.final_answer = None`（`read_api.py:978,1016`）。
- `RUN_LOST`: `OutboxTerminalProjectionConsumer.apply_event`（`outbox.py:162-167`）显式 skip，返回 `SKIPPED` + `detail_code="run_lost_not_public_terminal_item"`，不创建 public Outbox item。`HostEvent.final_answer = None`（`read_api.py:1046`）。
- `test_failed_and_cancelled_ignore_forged_final_answer_sources` 验证 forged `final_answer`/`content`/descriptor 不被提升为 answer。
- `test_failed_terminal_projection_never_builds_final_answer` / `test_cancelled_terminal_projection_never_builds_final_answer` / `test_lost_terminal_projection_never_builds_final_answer` 覆盖三种终态。
- `test_run_lost_is_skipped_without_public_outbox_item` 验证 LOST 显式 skip + 不创建 public item。

---

## F01 / F02 修复状态

| Finding | 来源 | 状态 | 证据 |
|---|---|---|---|
| P3-B-S1-CR-F01 | S1 code review DS Finding 1 + 3 | **FIXED** | `read_api.py:847-850` 显式拒绝空/空白 content；`HostDurableError` 含 Outbox/field/content 语义；`test_public_outbox_api.py:105-187` 走 production Host 路径验证 raw row 污染 → public read → `HostApiError(INTERNAL_ERROR)` cause 含 Outbox field 诊断 |
| P3-B-S1-CR-F02 | S1 code review DS Finding 2 | **FIXED** | `test_outbox_projection.py:736-738`（Outbox projection failure 参数化矩阵新增 `finish_reason=123` case）+ `test_read_api_terminal_policy.py:208-228`（HostEvent read 独立测试 `test_succeeded_terminal_projection_rejects_non_text_finish_reason`）；无兼容转换 |

F01 修复中同时加固了 durable read boundary：`_item_row_from_host_row` 现在调用 `_validate_item_row(item_row)` 后再返回（`durable/outbox.py:979-980`），使 `OUTBOX_TERMINAL_ITEMS` 表的每次读操作都经过完整 row 校验（`terminal_status`/`final_answer_json`/ref pair/drain marker），raw DB 损坏在 durable read boundary 即被拦截。

---

## Adversarial 审查

### 1. descriptor pair 不成对 → fail closed

**结论: 通过。** `_resolve_assistant_final_answer_continuity_text` 行 136-139：ref 和 digest 单边存在时立即抛 `"terminal_summary_ref and terminal_summary_digest must pair"`，不降级为缺失、不回退到 inline。`_optional_descriptor_text` 将纯空白归一为 absent（行 177-178），不会因空白 ref 触发单边错误。

### 2. descriptor artifact 损坏 → fail closed

**结论: 通过。** `sqlite_payload_object`（`payload_resolution.py:158-197`）六个 fail point：
1. descriptor row 缺失 → `"descriptor is missing"`
2. payload_kind 非 SQLITE_PAYLOAD → `"must be sqlite payload"`
3. digest 不匹配 → `"digest mismatch"`
4. sqlite_payload_id 缺失 → `"sqlite payload id is missing"`
5. SQLite payload row 缺失 → `"sqlite payload row is missing"`
6. payload_json 非文本 → `"JSON is invalid"`

外加 `_json_object`（行 200-215）：JSON decode 失败 → `"JSON is invalid"`；非 object → `"JSON must be object"`。

以上均抛 `HostDurableError`，不降级为空或回退到 lenient inline。`test_continuity_resolver_rejects_non_text_descriptor_content_even_lenient` 验证即使 lenient inline policy，descriptor content 非文本仍 fail closed。

### 3. Outbox JSON round-trip integrity

**结论: 通过。** `_final_answer_json`（`outbox.py:354-387`）使用 `canonical_json_dumps` 序列化；`_final_answer_from_outbox_json`（`read_api.py:823-865`）逐字段校验类型和语义。写入侧保证 succeeded 的 `final_answer_json` 非 None（通过 `required_assistant_final_answer_continuity_text` + `_validate_item_row` 双层保证）；读取侧对 JSON 解析失败、字段类型/语义非法均抛 `HostDurableError`。field name 常量 (`"content"`, `"filtered"`, `"degraded"`, `"finish_reason"`, `"terminal_status"`) 在写侧（`outbox.py:64-68`）和读侧（`read_api.py:113-121`）独立定义但值一致，均为 `"content"` / `"filtered"` / `"degraded"` / `"finish_reason"` / `"terminal_status"`。

### 4. Outbox item identity 不与 answer text 耦合

**结论: 通过。** `build_outbox_terminal_item_identity`（`outbox.py:183-227`）的 idempotency key 基于 `{terminal_event_id, run_id, result_ref, result_digest, terminal_summary_ref, terminal_summary_digest}` 计算 sha256 digest，不包含 `final_answer_json`。answer 展示文本变化不影响幂等语义。identity JSON 中 ref/digest 的 `None` 值通过 `_require_ref_pair` 保证成对。

### 5. drain 幂等（request id + digest）

**结论: 通过。** `drain_outbox_terminal_items`（`durable/outbox.py:427-527`）使用 `(session_id, drain_request_id)` 幂等记录 + request digest（基于 session_id/cursor/seen_ids/limit）防止语义冲突。同 request id 不同输入抛 `HostIdempotencyConflictError`。同输入重放返回同一 item id 集合。drain 仅更新 `item_state` → `drained` + drain 时间戳，不修改 EventLog。

### 6. 非预期输入

**结论: 通过。** 逐输入类检查：

| 输入类 | 处理 | 文件（行号） |
|---|---|---|
| inline `final_answer` 非文本（strict） | `HostDurableError("payload field final_answer must be text")` | `terminal_payload.py:98` |
| inline `final_answer` 非文本（lenient） | 返回 `None`，不抛错 | `terminal_payload.py:96-97` |
| descriptor ref/digest 非文本 | `HostDurableError("payload field ... must be text")` | `_terminal_answer.py:176` |
| descriptor content 非文本 | `HostDurableError("payload field content must be text")` | `terminal_payload.py:98` |
| descriptor content 缺失/空白 | optional → `None`；required → `HostDurableError("content is missing/blank")` | `_terminal_answer.py:152-155` |
| `filtered`/`degraded` 非 bool | `HostDurableError("payload field ... must be bool")` | `outbox.py:468-469` |
| `finish_reason` 非文本（canonical payload） | `HostDurableError` | `_event_payload.py:442-444` |
| `finish_reason` 非文本（Outbox JSON, 非 None） | `HostDurableError("outbox final answer finish_reason is invalid")` | `read_api.py:855-856` |
| Outbox JSON 非法 | `HostDurableError("outbox final answer JSON is invalid")` | `read_api.py:837` |
| Outbox JSON 非 object | `HostDurableError("outbox final answer JSON must be object")` | `read_api.py:839` |
| `content` 空/纯空白（Outbox JSON） | `HostDurableError("Outbox final answer field content must be non-empty text")` | `read_api.py:848-849` |
| `terminal_status` 非 `"succeeded"`（Outbox JSON） | `HostDurableError("outbox final answer terminal_status is invalid")` | `read_api.py:858` |

### 7. 并发 / 竞争写入

**结论: 通过。** `insert_outbox_terminal_item_if_absent` 在同一 transaction 内先查询后插入，依赖 SQLite 的 serialized transaction 隔离。同一 terminal_event_id 的并发写入在 transaction 序列化下不会同时 INSERT；先提交者写入成功，后提交者在 `read_outbox_terminal_item_by_event_id` 中读到 existing row → DUPLICATE（identity 一致）或 `"identity conflicts"`（identity 不一致）。checkpoint 推进在 `ProjectionRunner._run_write` 同一 transaction 内完成，异常 rollback 保持 checkpoint 不变。

### 8. semantic ownership drift

**结论: 无新增 drift。** 确认：
- `_terminal_answer.py` 是 descriptor-aware source selection 的唯一 owner。所有消费者通过 `required_assistant_final_answer_continuity_text` 或 `assistant_final_answer_continuity_text` 两个 public contract 接入。
- `read_api.py` 的旧 `_terminal_payload_object` / `_sqlite_payload_object` 已完全删除（零 grep 命中），不保留兼容 wrapper 或 lazy import。
- `outbox.py` 的旧 inline-only `final_answer` 字段 reader 已删除，`_final_answer_json` 现调用 `required_assistant_final_answer_continuity_text` 统一解析。
- `payload_resolution.sqlite_payload_object` 是唯一的 SQLite payload descriptor → JSON object 解析入口。
- 纯 memory consumer 在 typed material 缺失时保留 lenient inline fallback，但这是 design-approved bounded memory policy，不绕过 owner。
- 无下游通过 `hasattr`/`getattr`、loose parsing、字符串格式化或测试固化补齐上游 contract。

### 9. 过度耦合

**结论: 无新增过度耦合。** 确认：
- Host 层各模块通过稳定 public function contract（`required_assistant_final_answer_continuity_text`、`assistant_final_answer_continuity_text`、`build_outbox_terminal_item_row`、`insert_outbox_terminal_item_if_absent`）协作，不依赖具体实现类。
- Outbox projection 不直接调用 `payload_resolution.sqlite_payload_object`；descriptor 读取封装在 resolver 内。
- `HostFinalAnswerView` 不暴露 `payload_ref`、`digest`、`cursor` 等内部治理字段。
- 测试通过 public contract 验证行为，不 mock 私有函数。

### 10. 参数有效性

**结论: 通过。** 关键参数链路：
- `HostTransaction`: `ProjectionRunner` → `apply_event` → `build_outbox_terminal_item_row` → `_final_answer_json` → resolver → `sqlite_payload_object` 全链路透传同一实例。
- `inline_text_policy`: 仅影响 inline `final_answer` 字段的 strict/lenient 行为。Descriptor content 校验固定使用 `STRICT_NON_EMPTY`，不随 caller policy 变化。
- `text_policy`（optional resolver）: caller 传入 → `assistant_final_answer_continuity_text` → `_resolve_assistant_final_answer_continuity_text(inline_text_policy=text_policy)`。Descriptor 路径不受影响。

---

## Findings

### 1 — 未修复 — 低 — `_final_answer_from_outbox_json` 的 `finish_reason` 空白校验与 `content` 不对齐

- **入口/函数**: `read_api._final_answer_from_outbox_json`
- **文件（行号）**: `dayu/host/read_api.py:855-856`
- **输入场景**: raw SQLite `final_answer_json` 列被外部 corruption 写入 `{"content": "valid", "filtered": false, "degraded": false, "finish_reason": "  ", "terminal_status": "succeeded"}`。
- **实际分支**: 行 855-856 的 `isinstance(finish_reason, str)` 通过（空白字符串仍是 str），无 `.strip() == ""` 排除逻辑。随后 `HostFinalAnswerView(finish_reason="  ")` 在 `__post_init__` 中被 `_require_optional_non_empty` 抛出 `ValueError("HostFinalAnswerView.finish_reason must be non-empty")`。
- **预期行为**: 正常路径下 producer（`outbox._final_answer_json` → `optional_payload_text`）保证 `finish_reason` 为 `None` 或非空文本，不会产生纯空白值。正常路径行为正确。与已修复的 F01（`content` 空白）属于同一类防御层次不一致问题：`content` 在 read boundary 有显式空白检查 + `HostDurableError`，`finish_reason` 仅有 `isinstance` 检查，空白值委托给下游 `HostFinalAnswerView` 以 `ValueError` 抛出。
- **直接证据**: `read_api.py:855-856` — `if finish_reason is not None and not isinstance(finish_reason, str)`，对比行 847-848 — `if content.strip() == "": raise HostDurableError(...)`。F01 fix 已为 `content` 加固 read boundary，`finish_reason` 未同期待遇。
- **影响**: 仅在 raw DB 损坏场景下错误类型（`ValueError` vs `HostDurableError`）和错误消息精度略低于预期，正常路径不受影响。`finish_reason` 是可选展示元数据，不是核心 answer content，影响比 F01 更小。
- **建议改法和验证点**: 在 `_final_answer_from_outbox_json` 行 856 后增加 `if isinstance(finish_reason, str) and finish_reason.strip() == "": raise HostDurableError("Outbox final answer field finish_reason must be non-empty text")`。补充测试：构造 raw row 含纯空白 `finish_reason` 的 JSON，断言 public read 返回 `HostApiError(INTERNAL_ERROR)` 且 cause 含 `finish_reason` 诊断。与 F01 的 `test_read_corrupted_outbox_final_answer_content_rejected` 对称。
- **修复风险**: 低 — 仅加固 read boundary 防御层，不改变正常路径。
- **严重程度**: 低

---

## 跨 Slice / Aggregate 遗漏检查

### 1. Outbox JSON field name 常量独立定义

`outbox.py:64-68` 和 `read_api.py:113-121` 各自独立定义了 `_PAYLOAD_FIELD_CONTENT`、`_PAYLOAD_FIELD_FILTERED`、`_PAYLOAD_FIELD_DEGRADED`、`_PAYLOAD_FIELD_FINISH_REASON`、`_PAYLOAD_FIELD_TERMINAL_STATUS`。当前所有常量值一致（均为 `"content"` / `"filtered"` / `"degraded"` / `"finish_reason"` / `"terminal_status"`）。这是同一 contract 在两个模块中的独立副本，无自动 drift 保护。**不构成 material finding** — 两个模块各自是 Outbox JSON 格式的唯一 writer 和唯一 reader；字段名是简单稳定字符串；行为测试会捕获任何 drift。若未来 Outbox JSON 格式演化为更复杂的多 producer/consumer 场景，建议抽取 shared contract 常量模块。

### 2. durable read boundary 的 `_validate_item_row` 新增调用

`durable/outbox.py:979-980` 在 `_item_row_from_host_row` 中新增 `_validate_item_row(item_row)` 调用。该变更使 `OUTBOX_TERMINAL_ITEMS` 表的每次读操作（`read_outbox_terminal_item_by_event_id`、`read_outbox_terminal_item_by_id`、`read_outbox_terminal_items_after` 及其它内部调用）均经过完整 row 校验。`insert_outbox_terminal_item_if_absent` 中 `_validate_item_row` 被调用两次（insert 前一次 + read-back 的 `_item_row_from_host_row` 内一次），冗余但无害。**不构成 defect** — 这是 durable read boundary 的防御加固，与 F01 fix 中 `_final_answer_from_outbox_json` 的加固方向一致。

### 3. `filtered` / `degraded` 为 JSON `null` 时的行为

`_final_answer_from_outbox_json` 行 851-854：
```python
if not isinstance(filtered, bool):
    raise HostDurableError("outbox final answer filtered is invalid")
if not isinstance(degraded, bool):
    raise HostDurableError("outbox final answer degraded is invalid")
```

JSON `null` 在 Python `json.loads` 中解析为 `None`，`isinstance(None, bool)` 为 `False`，因此被拒绝。行为正确。Producer（`_final_answer_json`）通过 `_required_payload_bool` 保证写入的值为 Python `bool`，`canonical_json_dumps` 将其序列化为 JSON `true`/`false`。正常路径不会产生 `null`。

### 4. propagation audit（完整真源路径）

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

**分叉消费：**

| 消费路径 | 文件 | 调用 | 返回类型 |
|---|---|---|---|
| HostEvent live read | `read_api.py:915` | `required_assistant_final_answer_continuity_text` | `str`（非空） |
| Outbox row JSON | `outbox.py:370` | `required_assistant_final_answer_continuity_text` | `str`（非空） |
| Outbox public read | `read_api.py:811` | `_final_answer_from_outbox_json(row.final_answer_json)` | `HostFinalAnswerView` |
| durable memory | `durable/memory.py:393` | `assistant_final_answer_continuity_text(..., STRICT_NON_EMPTY)` | `str | None` |
| compact material | `compact_material.py:2213` | `assistant_final_answer_continuity_text(...)` | `str | None` |
| RunInputBuilder | `run_input.py:3236` | `assistant_final_answer_continuity_text(...)` | `str | None` |
| 纯 Conversation Memory | `memory.py:1650` | typed `assistant_final_answer_text` → lenient inline fallback | `str | None` |

**负向传播：**
```
RUN_FAILED / RUN_CANCELLED
  → _final_answer_json 返回 None（outbox.py:368-369）
  → HostEvent.final_answer = None（read_api.py:978,1016）
  → 不调用 terminal-answer resolver

RUN_LOST
  → Outbox consumer 显式 skip（outbox.py:162-167）
  → HostEvent.final_answer = None（read_api.py:1046）
  → 不创建 public Outbox item
```

**一致性：**
- Content 等值: production smoke 断言 live/read/drain content 严格相等。
- Terminal identity 不变: live/read/drain 的 `terminal_event_id`/`dedupe_key` 一致。
- Descriptor/digest 不泄漏到 LLM-facing text: resolver 只返回 content 文本，不拼接 ref/digest。
- Outbox failure 不改变 Run truth: Outbox projection 只读 EventLog，不写 Run/Attempt。
- Memory/compact/run input 没有新增独立 parser: 全部通过同一 resolver 的 typed material 消费。

---

## 状态机审查

**Outbox projection 状态转换（完整）：**

| 当前状态 | 触发事件 | 下一状态 | 验证测试 |
|---|---|---|---|
| (初始) | terminal EventLog row committed | item INSERT + checkpoint advance | `test_same_terminal_event_replay_does_not_duplicate` |
| checkpoint 已过 event | 同 terminal event replay | DUPLICATE（不新增 item） | 同上 |
| resolver/row builder 抛异常 | apply transaction 内异常 | rollback（item + checkpoint 均不提交）→ failure row 独立持久化 | `test_descriptor_failure_rolls_back_and_same_descriptor_retry_is_idempotent` |
| failure row 存在 + checkpoint 未推进 | catch-up 重试 | catch-up 停在 failure event 前（不越过） | 同上 |
| descriptor 恢复 + 重试 | 同 event 再次 apply | item 原子写入 + checkpoint 推进 + failure 清除 | 同上 |
| 终态 item 存在 + checkpoint 已推进 | 同 event 再次 apply | DUPLICATE（idempotency） | 同上 |
| insert 成功但 identity 冲突 | 另一 event 写入相同 terminal_event_id | `HostDurableError("identity conflicts")` | `test_item_write_rejects_terminal_identity_conflict` |

所有状态转换均经行为测试验证。终态均为 absorbing：checkpoint 推进后不重复生成 item；failure 清除后不重复记录 failure。

**Outbox drain 状态转换：**

| 当前状态 | 触发事件 | 下一状态 | 验证测试 |
|---|---|---|---|
| item_state=pending | drain（新 request） | item_state=drained + drain 幂等记录 | `test_offline_read_and_idempotent_drain_do_not_write_eventlog` |
| item_state=pending | drain（同 request 重放） | 返回同 item_ids，不重复更新 | 同上 |
| item_state=pending | drain（同 request id 不同输入） | `HostIdempotencyConflictError` | `test_drain_rejects_idempotency_conflict` |

---

## README

`dayu/host/README.md` 新增段落（行 691-693）准确描述了：
- 成功终态 live `HostEvent` 与 Outbox item 必须携带非空 final answer
- 两者共用 terminal-answer continuity resolver
- inline precedence + descriptor fallback
- canonical metadata 来源
- failed/cancelled/lost 禁止 final answer；lost 不生成 public Outbox item
- projection transaction 原子性

README 更新范围与代码变更一致，不引入新的架构决策或接口承诺。

---

## Open Questions

无。

---

## Residual Risk

1. **P3-J DDL conditional CHECK**: SQLite schema 无 conditional CHECK 强制 `succeeded` row 的 `final_answer_json` 非 NULL。Producer + durable row validator（write + read）+ public JSON reader + public dataclass validator 四层覆盖正常路径。raw DB 手动损坏在 durable read boundary 被 `_validate_item_row` 拒绝。数据库级 closed-set hardening 仍归 P3-J，不在本 WU 范围。

2. **Descriptor storage auto repair**: 超出 P3-B 范围。当前保证 failure 可观察、无半成品、恢复后可 retry。

3. **Finding 1 — `finish_reason` 空白校验不对称**: `_final_answer_from_outbox_json` 对 `finish_reason` 的空白校验委托给下游 `HostFinalAnswerView`，与已加固的 `content` 显式空白检查不对称。正常路径不受影响（producer 保证非空）；仅 raw DB 损坏场景下错误类型不一致。优先级低，建议后续跟进。

4. **read boundary `finish_reason` 校验与 producer 独立**: `_final_answer_from_outbox_json:855-856` 对 `finish_reason` 的类型校验与 producer 端（`optional_payload_text`）独立且语义等价。若 producer 端未来变更错误消息格式，read boundary 的独立错误消息可能产生诊断差异。当前不构成 defect — 两层校验各自 fail closed，且测试覆盖 producer 端诊断片段。建议后续统一 `finish_reason` 的 canonical 校验 helper。

---

## Verdict

**P3-B S1 aggregate implementation 达到 ship 标准。**

- 7 项 P3-B 成功信号逐项复议全部通过。
- F01 / F02 完整修复（controller accepted → re-review verified）。
- Adversarial 审查 10 项全部通过。
- 1 项 new low-severity finding（`finish_reason` 空白校验不对称），严重程度低于已关闭的 F01。
- Propagation audit 确认真源收敛、无下游绕过、无语义漂移。
- 75 项聚焦测试全部通过，1716 项 Host 全量回归全部通过，pyright 零报错。

**Resolved source findings 状态：**
- Finding 01: **fixed** — Outbox/read API 统一调用 terminal-answer resolver，descriptor-only production shape 正确生成非空 final answer。
- DS-2: **fixed** — Outbox 的 inline-only final answer reader 已删除；read API 的第二套 descriptor/SQLite parser 已删除。
- DS-4: **fixed** — Outbox 不再自行决定 final answer 来源；`_final_answer_json` 调用 required resolver。
- Controller P3-B: **fixed** — 所有消费者通过 typed boundary 调用同一 resolver/helper。

**Residual owners:**
- P3-J DDL CHECK: P3-J owner
- Finding 1（finish_reason 空白校验）: P3-B residual，可纳入后续 Host hardening WU

**Material finding 数: 1（Low），Verdict: PASS**

Artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-deepreview-ds.md`
