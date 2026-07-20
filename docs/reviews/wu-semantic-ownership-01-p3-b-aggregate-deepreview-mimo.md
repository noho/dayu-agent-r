# WU-SEMANTIC-OWNERSHIP-01 P3-B Aggregate Deepreview

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `4c6ec694`
- Head: `08394e52`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-deepreview-mimo.md`
- Included scope: `_terminal_answer.py` resolver required/optional contract, `read_api.py` HostEvent succeeded projection, `outbox.py` Outbox projection, `durable/outbox.py` durable row validation, `api.py` public invariants, all focused/propagation tests, Host README, and review fixes (F01/F02)
- Excluded scope: CLI-CI 并发文件、P3-C/P3-J scope、docs 下非 P3-B artifact
- Parallel review coverage: 无

## 输入

- Accepted plan: `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-controller-validation.md`
- Code review (MiMo): `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-mimo.md`
- Code review (DS): `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-ds.md`
- Code review controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-fix-codex.md`
- Re-review (MiMo): `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-rereview-mimo.md`
- Re-review (DS): `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-rereview-ds.md`
- Re-review controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-rereview-controller-adjudication.md`
- Host/Engine design: `docs/host/design.md`, `docs/engine/design.md`

## Findings

未发现实质性问题。

## Adversarial Failure Pass

逐项验证 plan §8 failure matrix 与 P3-B 成功信号，沿真实代码路径走读：

### 1. Resolver source-selection core

`_terminal_answer.py:101-155` 的 `_resolve_assistant_final_answer_continuity_text` 是 required/optional 共用的唯一 source-selection core。

- **inline precedence**: `assistant_final_answer_text_from_run_payload` (strict/lenient 由 caller 传入) 先于 descriptor 读取；非空 inline 直接返回 `(answer, None)`，不读取 descriptor。`test_descriptor_only_and_inline_precedence_materialize_complete_answer` 与 `test_continuity_resolver_prefers_run_final_answer_over_artifact` 锁定。
- **descriptor pair validation**: ref/digest 双缺失返回 `(None, "inline answer and descriptor pair are missing")`；单边缺失抛 `HostDurableError("terminal_summary_ref and terminal_summary_digest must pair")`。`test_continuity_resolver_requires_complete_terminal_descriptor` 锁定两 policy 均 fail closed。
- **descriptor structural integrity**: 通过 `payload_resolution.sqlite_payload_object` 读取；descriptor missing / kind illegal / digest mismatch / SQLite row missing / JSON invalid / JSON non-object 均抛 `HostDurableError`，optional 与 required 一致。`test_required_continuity_resolver_rejects_missing_descriptor_row`、`test_continuity_resolver_rejects_malformed_terminal_descriptor`、`test_continuity_resolver_rejects_digest_mismatch` 锁定。
- **descriptor content taxonomy**: `terminal_payload_content_text_from_payload(..., STRICT_NON_EMPTY)` 读取顶层 `content`。content 缺失返回 `(None, "content is missing")`；空白返回 `(None, "content is blank")`；非文本抛 `HostDurableError`（STRICT policy 行为）。`test_required_continuity_resolver_rejects_missing_sources`、`_resolve_...content_blank/missing/non_text` 参数化测试锁定。
- **required contract**: `required_assistant_final_answer_continuity_text` 固定 `inline_text_policy=STRICT_NON_EMPTY`；core 返回 `(None, error)` 时抛 `HostDurableError(error)`；`(None, None)` 时抛 generic error。返回类型 `str`（非 nullable），保证 HostEvent 与 Outbox 不产生 nullable final answer。

### 2. HostEvent / read API source convergence

`read_api.py:904-950` 的 `_succeeded_host_event` 改用 `required_assistant_final_answer_continuity_text(transaction, payload)` 获取 content。`filtered`、`degraded`、`finish_reason` 从 canonical `RUN_SUCCEEDED` payload 读取（`_required_payload_bool` / `_optional_payload_text`）。原 `_terminal_payload_object` / `_sqlite_payload_object` 私有 descriptor/SQLite parser 已删除（diff 确认 -67 行删除）。

- `HostFinalAnswerView.__post_init__` (`api.py:2737-2750`) 拒绝空白 content (`_require_non_empty`)、非 bool filtered/degraded、非 SUCCEEDED terminal_status。
- `_final_answer_from_outbox_json` (`read_api.py:823-865`) 增加 `content.strip() == ""` 检查 (`read_api.py:847-850`)；断言 `terminal_status == SUCCEEDED`。raw row 损坏在 public read boundary fail closed。
- source scan 确认：`_terminal_payload_object` 在 `read_api.py` 中零引用；`required_assistant_final_answer_continuity_text` 消费者只有 `read_api._succeeded_host_event` 和 `outbox._final_answer_json`。

### 3. Outbox projection source convergence

`outbox.py:354-387` 的 `_final_answer_json` 接收 `HostTransaction`；succeeded 调 `required_assistant_final_answer_continuity_text(transaction, payload)`；非 succeeded 立即返回 `None`。`filtered` / `degraded` / `finish_reason` 从 canonical payload 读取，不从 descriptor artifact shape 读取。

- `build_outbox_terminal_item_row` (`outbox.py:230-295`) 接收显式 `HostTransaction` 参数；consumer 在 ProjectionRunner 提供的同一 transaction 中调用。
- Outbox 不再定义 `_PAYLOAD_FIELD_FINAL_ANSWER`（diff 确认删除）；不再有 inline-only final answer reader。
- `failed` / `cancelled` path (`_error_message` / `_cancel_reason`) 不调用 resolver；`final_answer_json` 为 `None`。`lost` 在 consumer 层显式 skip，不进入 row builder。

### 4. Durable / public invariants

- **durable write boundary** (`durable/outbox.py:842-851`): `_validate_item_row` 检查 `terminal_status == "succeeded"` 时 `final_answer_json` 必填；非 succeeded 时必须为 `None`。
- **durable read boundary** (`durable/outbox.py:921-978`): `_item_row_from_host_row` 构造 row 后调用 `_validate_item_row`；raw DB 损坏在 read boundary fail closed。`test_durable_read_rejects_raw_succeeded_row_without_final_answer` 锁定。
- **public dataclass** (`api.py:3159-3170`): `_validate_outbox_terminal_payload` 要求 succeeded 必有 `final_answer`；failed/cancelled/lost 禁止。错误文案列出全部三类。
- **HostFinalAnswerView** (`api.py:2739-2742`): `content` 非空校验。

### 5. Projection rollback / retry / idempotency

- **原子性**: `ProjectionRunner.run_once` → `run_write(_process_next_event)` → `apply_event(transaction, event)` → `build_outbox_terminal_item_row(transaction, event)` → `insert_outbox_terminal_item_if_absent(transaction, row)` → `advance_projection_checkpoint(transaction, ...)` 全在同一 `HostTransaction`。resolver / row validation / insert 任一步抛错 → 整个 apply transaction rollback → item 不存在、checkpoint 不动。
- **failure 独立持久化**: `ProjectionRunner._record_failure` 在 apply rollback 后的独立 `run_write` 中写 failure row。`test_descriptor_failure_rolls_back_and_same_descriptor_retry_is_idempotent` 锁定：descriptor 删除 → catch-up failure=1、item=None、checkpoint=0、failure 指向该 event；test-only 原样恢复 descriptor → 重试 → item + checkpoint 提交、failure 清除。
- **idempotency**: 同一 typed event 再次 apply 返回 `DUPLICATE`；按 terminal event id 与 item id 计数均为 1。

### 6. Failed / cancelled / lost negatives

- `test_failed_and_cancelled_ignore_forged_final_answer_sources`: payload 含伪造 `final_answer`、`content`、descriptor pair → failed/cancelled row 的 `final_answer_json` 均为 `None`。
- `test_run_lost_is_skipped_without_public_outbox_item`: lost payload 含伪造 answer/descriptor → consumer 返回 SKIPPED，无 Outbox item。
- `test_failed_terminal_projection_never_builds_final_answer` / `test_cancelled_...` / `test_lost_...`: HostEvent 投影 `final_answer=None`，伪造 payload 字段不影响。

### 7. Canonical metadata source

- `filtered` / `degraded` / `finish_reason` 始终从 canonical `RUN_SUCCEEDED` payload 读取，不从 descriptor artifact shape 读取。
- Outbox `final_answer_json` 的 `terminal_status` 由 `_final_answer_json` 从 `terminal_status` enum 写入，不由 descriptor 决定。
- `test_succeeded_terminal_projection_reads_descriptor_content_and_canonical_metadata`: descriptor content 与 canonical metadata 分别同源投影，`filtered`/`degraded`/`finish_reason` 来自 canonical payload。

### 8. Memory / compact / run-input propagation

source scan 确认：
- `durable/memory.py` 调 `assistant_final_answer_continuity_text(..., STRICT_NON_EMPTY)`（optional strict）。
- `compact_material.py` 调同一 optional resolver。
- `run_input.py` 调同一 optional resolver。
- `memory.py` 纯 consumer 不调用 resolver，只消费 typed material。
- 305 propagation regression tests 通过。

### 9. Production smoke

`test_public_offline_outbox_smoke.py` 的 `_descriptor_only_terminal_payloads` 从 SQLite 读取 canonical `RUN_SUCCEEDED` payload，断言 `final_answer` key 不存在、`terminal_summary_ref` / `terminal_summary_digest` 均为非空文本，且 descriptor digest 与 canonical digest 相等。live HostEvent、Outbox read、Outbox drain 三者的 `final_answer.content` 均等于 `final:1:<run_id>`，metadata 一致，terminal event id / dedupe key 一致。

## Semantic Ownership Drift Pass

| 检查项 | 结果 |
|---|---|
| descriptor parser 重复 | 已消除。`read_api.py` 删除私有 `_terminal_payload_object` / `_sqlite_payload_object`；`outbox.py` 删除私有 `_PAYLOAD_FIELD_FINAL_ANSWER` reader |
| source precedence 定义点 | 唯一在 `_terminal_answer.py:101-155` |
| descriptor pair validation | 唯一在 `_terminal_answer.py:131-138` |
| answer content 读取 | 唯一通过 `terminal_payload.terminal_payload_content_text_from_payload` |
| metadata 读取 | Outbox 与 read_api 均从 canonical `RUN_SUCCEEDED` payload 读取，不从 descriptor |
| second-of-truth | 无。required/optional 共用 core；Outbox/read_api 不再各自重建 parser |
| fallback / hasattr / getattr / loose parsing / compat shim | 无 |
| 纯 memory consumer 反向打开 descriptor | 无。`memory.py` 只消费 typed material |

## Overcoupling Pass

| 检查项 | 结果 |
|---|---|
| 修改范围 | 5 production files、7 test files、1 README；全部在 plan 允许范围 |
| 新增跨层依赖 | 无。`outbox.py` 和 `read_api.py` 导入 `_terminal_answer`，这是 Host 内部模块间的 owner→consumer 关系 |
| 新增 callback / factory / registry | 无 |
| 新增 schema / DDL / migration | 无 |
| 新增 compatibility wrapper / facade / re-export | 无 |
| slice 可独立审查 | 是。单一 contract 闭环，不依赖 P3-C / P3-J |

## Propagation Audit

```text
Engine FinalAnswerData.content
  -> engine_ingest._final_answer_plan rejects blank success
  -> _write_terminal_payload writes {content, finish_reason, filtered, degraded}
  -> payload descriptor + SQLite payload row
  -> terminal_closeout_in_transaction
  -> RUN_SUCCEEDED canonical payload
       terminal_summary_ref / terminal_summary_digest
       finish_reason / filtered / degraded
  -> Host terminal-answer continuity resolver (single source-selection core)
       inline final_answer first (STRICT_NON_EMPTY for required, caller policy for optional)
       otherwise digest-checked descriptor top-level content (STRICT_NON_EMPTY)

required strict branch
  -> read_api._succeeded_host_event
  -> HostFinalAnswerView (content non-empty, metadata from canonical)
  -> live HostEvent / watch public read

required strict branch inside Outbox projection transaction
  -> final_answer_json (canonical JSON: content + metadata + terminal_status)
  -> host_outbox_terminal_items row
  -> _final_answer_from_outbox_json (JSON parse + field validation + non-empty content)
  -> OutboxTerminalItem.final_answer
  -> public read/drain

optional strict typed-material branch
  -> durable memory projection -> MemoryProjectionEvent.assistant_final_answer_text
  -> compact material answer block -> LLM compact input material
  -> RunInputBuilder inline repair / selected recent continuity -> LLM-facing run input

negative propagation:
  RUN_FAILED / RUN_CANCELLED / RUN_LOST
    -> never call/promote terminal answer resolver as final answer
    -> HostEvent.final_answer = None
    -> failed/cancelled Outbox final_answer_json = None
    -> lost Outbox skip
    -> no assistant answer memory/compact/run-input producer

failure/retry:
  resolver/validation/insert failure
    -> rollback whole apply transaction (no item, checkpoint unchanged)
    -> ProjectionRunner records failure row in separate transaction
    -> external descriptor restoration + retry
    -> item + checkpoint commit atomically, failure cleared
    -> replay returns DUPLICATE, item count = 1
```

每条路径有行为测试覆盖：

| 路径 | 测试证据 |
|---|---|
| descriptor-only success → Outbox + HostEvent | `test_descriptor_only_and_inline_precedence_materialize_complete_answer` + `test_offline_read_and_idempotent_drain_do_not_write_eventlog` |
| inline precedence | `test_descriptor_only_and_inline_precedence_materialize_complete_complete_answer` (inline row) + `test_continuity_resolver_prefers_run_final_answer_over_artifact` |
| descriptor taxonomy (pair/missing/digest/JSON/content) | `test_required_continuity_resolver_rejects_missing_sources` + 8 parameterized cases |
| HostEvent descriptor content + canonical metadata | `test_succeeded_terminal_projection_reads_descriptor_content_and_canonical_metadata` |
| HostEvent descriptor errors fail closed | `test_succeeded_terminal_projection_fails_closed_for_descriptor_errors` (4 cases) |
| Outbox failure atomicity + retry | `test_descriptor_failure_rolls_back_and_same_descriptor_retry_is_idempotent` |
| Outbox missing answer → failure | `test_missing_required_answer_records_actionable_projection_failure` |
| Outbox invalid metadata → failure | `test_succeeded_projection_rejects_invalid_metadata_or_summary_pair` (6 cases) |
| failed/cancelled negatives | `test_failed_and_cancelled_ignore_forged_final_answer_sources` |
| lost skip | `test_run_lost_is_skipped_without_public_outbox_item` |
| durable invariant write | `test_item_write_rejects_invalid_terminal_final_answer_combinations` |
| durable invariant read (raw corruption) | `test_durable_read_rejects_raw_succeeded_row_without_final_answer` |
| public invariant | `test_public_outbox_terminal_final_answer_invariants` |
| public raw blank content | `test_public_outbox_read_rejects_raw_blank_final_answer_content` |
| production smoke (descriptor-only) | `test_offline_read_and_idempotent_drain_do_not_write_eventlog` + `_descriptor_only_terminal_payloads` |
| propagation regression | 305 tests (engine ingest, memory, compact, run input, projection runner) |

## Validation

```text
focused behavior tests:  75 passed
propagation regression:  305 passed
pyright:                 0 errors, 0 warnings, 0 informations
git diff --check:        clean (working tree 无 whitespace 问题)
owner/source scan:       resolver 只在 _terminal_answer.py；Outbox/read API 无独立 descriptor parser
```

## Finding Final Status

| Finding | Status | Evidence |
|---|---|---|
| Finding 01 (descriptor-only production continuity) | fixed | Outbox + HostEvent 均通过 required resolver 读取 descriptor-backed content；production smoke 证明 descriptor-only canonical shape → 非空 final answer |
| DS-2 (semantic ownership drift: 4+ independent paths) | fixed | read_api 删除私有 descriptor/SQLite parser；outbox 删除私有 inline reader；两者共用 required resolver；memory/compact/run-input 仍用 optional resolver |
| DS-4 (Outbox inline-only reader bypassing owner) | fixed | Outbox `_final_answer_json` 改用 required resolver；不再定义 `_PAYLOAD_FIELD_FINAL_ANSWER` |
| P3-B-S1-CR-F01 (raw durable row blank content) | closed | `read_api._final_answer_from_outbox_json` 增加 `content.strip() == ""` 检查；public read 抛 `HostApiError(INTERNAL_ERROR)` cause `HostDurableError` |
| P3-B-S1-CR-F02 (non-text finish_reason) | closed | Outbox projection + HostEvent read 均 fail closed；参数化测试锁定 |

## Open Questions

无。

## Residual Risk

| 项目 | Owner | 说明 |
|---|---|---|
| P3-J DDL conditional CHECK | P3-J | SQLite DDL 无 `CHECK (terminal_status != 'succeeded' OR final_answer_json IS NOT NULL)`；当前由 producer + durable validator + public validator 覆盖 |
| descriptor 自动 repair | 未分配 | P3-B 只保证 failure 可观察、无半成品、恢复后可 retry；自动 repair 不在本 WU scope |
| optional-material policy tightening | 未分配 | optional resolver 在"完整缺失 answer source"时返回 None，public boundary 会 fail closed；业务用途不同，非 source drift |

## Verdict

**P3-B aggregate deepreview: PASS — 0 material findings.**

全部 P3-B 成功信号已通过直接代码路径证据验证：

1. **descriptor-only production continuity**: Outbox 与 HostEvent 通过 required resolver 从 descriptor-backed content 读取 final answer；production smoke 证明 descriptor-only canonical `RUN_SUCCEEDED` → 非空 final answer。
2. **inline precedence**: resolver core 固定 inline 优先；inline + descriptor 共存时 inline 获胜。
3. **canonical metadata**: `filtered` / `degraded` / `finish_reason` 始终从 canonical `RUN_SUCCEEDED` payload 读取，不随 content source 切换。
4. **public/durable invariants**: succeeded 必填 final answer、非成功禁止、空白 content 拒绝、raw row 损坏 fail closed。
5. **projection rollback/retry/idempotency**: resolver failure 整体回滚、failure 独立持久化、descriptor 恢复后重试原子提交、replay 返回 DUPLICATE。
6. **memory/compact/run-input 同源**: optional resolver typed material → memory/compact/run-input；纯 memory consumer 不反向打开 descriptor。
7. **failed/cancelled/lost negatives**: 不调用 resolver、不提升伪造 answer、lost 显式 skip。

Previous findings F01/F02 均已完整修复并经 controller adjudication closed。无跨 slice/aggregate 遗漏。
