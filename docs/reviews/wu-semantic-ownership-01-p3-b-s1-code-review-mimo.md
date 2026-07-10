# Code Review: WU-SEMANTIC-OWNERSHIP-01 P3-B S1

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `4c6ec694` (accepted plan bookkeeping commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-mimo.md`
- Included scope: P3-B intended diff — `dayu/host/_terminal_answer.py`, `dayu/host/api.py`, `dayu/host/read_api.py`, `dayu/host/outbox.py`, `dayu/host/durable/outbox.py`, `dayu/host/README.md`, 及对应测试文件 7 个
- Excluded scope: CLI-CI 并发文件（`docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对抗性审查的详细走读与裁决。

### 1. Resolver source precedence / strict/lenient / 双缺失 / 单边 pair

**走读**: `_resolve_assistant_final_answer_continuity_text` (`_terminal_answer.py:101-155`) 是唯一的 source-selection core。`assistant_final_answer_continuity_text` 和 `required_assistant_final_answer_continuity_text` 均委托它。source precedence 固定为：inline `final_answer` > descriptor-backed `content`。

- **双缺失**: `_optional_descriptor_text` 把 `None` 和纯空白统一归为 absent（`_terminal_answer.py:172-178`）。当 ref 和 digest 都 absent 时返回 `("assistant final answer inline answer and descriptor pair are missing", None)`（`_terminal_answer.py:131-135`）。optional 返回 `None`，required 抛 `HostDurableError`。
- **单边 pair**: ref absent + digest present（或反之）触发 `HostDurableError("terminal_summary_ref and terminal_summary_digest must pair")`（`_terminal_answer.py:136-139`）。测试 `test_continuity_resolver_requires_complete_terminal_descriptor` 覆盖两种单边情况，确认 strict/lenient 均抛错。
- **strict/lenient 边界**: lenient 只影响 inline `final_answer` 的非文本类型（`terminal_payload.py:95-97`）。descriptor pair、descriptor、digest、SQLite row、JSON 结构在所有策略下均 fail closed。测试 `test_continuity_resolver_rejects_non_text_descriptor_content_even_lenient` 确认 lenient 不吞掉 descriptor content 损坏。
- **descriptor/storage/digest/JSON/content taxonomy**: plan §5.5 的完整 taxonomy 在 `_resolve_assistant_final_answer_continuity_text` 中逐条实现：content 缺失 vs 空白有区分诊断（`_terminal_answer.py:152-155`），content 非文本由 `terminal_payload_content_text_from_payload` 的 strict 策略拒绝。测试 `test_required_continuity_resolver_distinguishes_missing_and_blank_content` 和 `test_required_continuity_resolver_rejects_invalid_sqlite_payload_json` 覆盖所有 taxonomy case。

**裁决**: 无缺陷。source precedence、strict/lenient、双缺失/单边 pair、taxonomy 均正确实现并有测试覆盖。

### 2. Canonical metadata 始终来自 RUN_SUCCEEDED，content 可 descriptor fallback

**走读**:

- **HostEvent path** (`read_api.py:909-931`): `content` 来自 `required_assistant_final_answer_continuity_text(transaction, payload)`，`filtered`/`degraded`/`finish_reason` 来自同一个 canonical `payload` 对象。不读取 descriptor 中的 metadata。
- **Outbox path** (`outbox.py:354-387`): `_final_answer_json` 调用 `required_assistant_final_answer_continuity_text(transaction, payload)` 获取 content，然后从 canonical `payload` 读取 `_required_payload_bool(payload, field_name=_PAYLOAD_FIELD_FILTERED)` 等 metadata。
- **关键测试**: `test_succeeded_terminal_projection_reads_descriptor_content_and_canonical_metadata` 写入包含 `filtered: False, degraded: True, finish_reason: "artifact-must-not-own-metadata"` 的 descriptor artifact payload，但断言 HostEvent 的 metadata 来自 canonical payload（`filtered: True, degraded: False, finish_reason: "stop"`）。test_read_api_terminal_policy.py:190-205。`test_descriptor_only_and_inline_precedence_materialize_complete_answer` 在 Outbox 层做同样断言。test_outbox_projection.py:305-340。
- **Production smoke**: `test_offline_read_and_idempotent_drain_do_not_write_eventlog` 从 SQLite 读取 canonical payload 断言 `final_answer` key 不存在、`filtered`/`degraded`/`finish_reason` 值正确，同时断言 live HostEvent、Outbox read item、drained item 的 content 与 metadata 一致。test_public_offline_outbox_smoke.py:91-131。

**裁决**: 无缺陷。content 和 metadata 的 source separation 在 HostEvent 和 Outbox 两条路径上均正确实现，测试覆盖了 descriptor 与 canonical metadata 不一致的 adversarial 场景。

### 3. Outbox consumer 同事务 resolve/insert/checkpoint，异常 rollback + 独立 failure

**走读**:

- **原子性**: `OutboxTerminalProjectionConsumer.apply_event` (`outbox.py:149-180`) 使用 `ProjectionRunner` 传入的同一 `HostTransaction`。`build_outbox_terminal_item_row(transaction, event)` 在同一事务内调用 resolver、构造 row。`insert_outbox_terminal_item_if_absent(transaction, row)` 在同一事务内校验、判重、insert。`projection.py:626-644` 在同一事务内推进 checkpoint 并清除旧 failure。`durable/transaction.py:288-360` 的 `run_write` 在 `BEGIN IMMEDIATE` 后运行整个 operation，任何异常在透传前 rollback。
- **独立 failure**: `projection.py:472-489` 只在 `run_write` 异常退出后调用 `_record_failure`，后者开启独立 `run_write` 写 failure row。failure 诊断不会被 apply transaction 的 rollback 撤销。
- **Retry/recovery**: `test_descriptor_failure_rolls_back_and_same_descriptor_retry_is_idempotent` 完整覆盖：删除 descriptor row → catch-up 得到 failure（`last_error_code == "HostDurableError"`, `last_error_message` 含 `"descriptor is missing"`）、item 不存在、checkpoint 不动 → 原样恢复 descriptor → retry 成功（item + checkpoint commit、failure 清除）→ replay 得到 DUPLICATE、item 计数仍为 1。
- **Failure clear**: retry 成功后 `failure_after_retry is None`（test_outbox_projection.py:566）。checkpoint 推进到 `terminal.event_sequence`（test_outbox_projection.py:565）。

**裁决**: 无缺陷。原子性、rollback、独立 failure、retry/recovery、failure clear 均正确实现并有完整测试覆盖。

### 4. Public/durable succeeded 必填，non-success 禁止 final answer

**走读**:

- **Durable write boundary**: `_validate_item_row` (`durable/outbox.py:843-851`) 校验 `terminal_status == "succeeded"` 时 `final_answer_json` 必填，否则抛 `HostDurableError("succeeded outbox item requires final_answer_json")`；非 succeeded 时 `final_answer_json` 必须为 `None`。`insert_outbox_terminal_item_if_absent` 调用 `_validate_item_row`。
- **Durable read boundary**: `_item_row_from_host_row` (`durable/outbox.py:979`) 在构造 row 后调用 `_validate_item_row`，raw DB 损坏（succeeded + NULL）在读取时 fail closed。
- **Public construction**: `_validate_outbox_terminal_payload` (`api.py:3161-3174`) 校验 succeeded 的 `final_answer` 必填，failed/cancelled/lost 禁止。`HostFinalAnswerView.__post_init__` (`api.py:2737-2750`) 校验 `content` 非空非空白。
- **Lost forged answer**: `_final_answer_json` (`outbox.py:368`) 非 succeeded 立即返回 `None`，不检查或提升 payload 中伪造的 `final_answer`/`content`/descriptor content。测试 `test_failed_and_cancelled_ignore_forged_final_answer_sources` 覆盖 failed/cancelled 携带伪造 answer/descriptor 的场景。`test_run_lost_is_skipped_without_public_outbox_item` 的 payload 也包含伪造字段。
- **Tests**: `test_item_write_rejects_invalid_terminal_final_answer_combinations` 覆盖 durable write boundary（succeeded + None → 错误，failed + non-None → 错误）。`test_durable_read_rejects_raw_succeeded_row_without_final_answer` 覆盖 durable read boundary。`test_public_outbox_terminal_final_answer_invariants` 覆盖 public construction。

**裁决**: 无缺陷。succeeded 必填、non-success 禁止在 construction/write/raw-read 三个边界均闭合。lost/forged answer 被正确忽略。

### 5. Production smoke 断言

**走读**: `test_offline_read_and_idempotent_drain_do_not_write_eventlog` 通过 `FinalAnswerWorkerFactory` 走 production closeout 路径，然后：

1. 从 SQLite 读取 canonical `RUN_SUCCEEDED` payload，断言 `final_answer` key 不存在（descriptor-only shape），`terminal_summary_ref`/`terminal_summary_digest` 均为非空文本。再读取 descriptor 并断言 digest 与 canonical digest 相等。test_public_offline_outbox_smoke.py:91-100。
2. 断言 live HostEvent、read item、drained item 的 `final_answer.content` 严格等于 `f"final:1:{run_id}"`，metadata 等于 factory 产生的 `filtered=False`、`degraded=False`、`finish_reason=stop`。test_public_offline_outbox_smoke.py:101-131。
3. 断言 `terminal_event_id`/`dedupe_key` 指向同一个 canonical terminal identity（test_public_offline_outbox_smoke.py:119-121），read/drain 不新增 EventLog row（test_public_offline_outbox_smoke.py:132）。

**裁决**: 无缺陷。Production smoke 真实断言了 descriptor-only canonical shape、content 来自 descriptor、metadata 来自 canonical payload、identity 一致。不是 inline-only fixture。

### 6. 删除 read_api 第二 parser 和 Outbox inline parser 后的完整性

**走读**:

- **read_api.py 删除项**: `_terminal_payload_object`、`_sqlite_payload_object`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST`（read_api.py:110-113 已删除）。`from dayu.host.durable.payload import PayloadKind, read_payload_descriptor` 和 `TABLE_SQLITE_PAYLOADS` import 已删除（read_api.py:75-78）。
- **调用方检查**: `grep` 确认 `read_api.py` 中无残留调用 `_terminal_payload_object`、`_sqlite_payload_object`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST`、`read_payload_descriptor` 或 `TABLE_SQLITE_PAYLOADS`。
- **Outbox inline parser 删除**: `_PAYLOAD_FIELD_FINAL_ANSWER` 常量从 `outbox.py` 删除（diff 确认）。`_final_answer_json` 不再读取 inline `final_answer`，改用 `required_assistant_final_answer_continuity_text`。
- **无兼容 wrapper**: 删除的函数和常量没有 compatibility re-export 或 wrapper。
- **类型/docstring**: 所有新增函数有完整类型签名和中文 docstring。`_resolve_assistant_final_answer_continuity_text` 返回 `tuple[str | None, str | None]`，类型严格。无 `Any`/`object`/`hasattr`/`getattr`/lazy import。

**裁决**: 无缺陷。删除干净，无遗漏调用，无兼容 wrapper，类型和 docstring 符合约束。

### 7. Propagation audit

**走读**: `final_answer` 语义从产生到用户可见的完整路径：

| 层 | 文件 | 语义 |
|---|---|---|
| 产生 | `_terminal_answer.py` | `_resolve_assistant_final_answer_continuity_text` 统一 source selection |
| HostEvent 投影 | `read_api.py:910-931` | 调用 `required_assistant_final_answer_continuity_text` + canonical metadata → `HostFinalAnswerView` |
| Outbox 投影 | `outbox.py:354-387` | 调用 `required_assistant_final_answer_continuity_text` + canonical metadata → `final_answer_json` |
| Durable 写入 | `durable/outbox.py:843-851` | `_validate_item_row` 校验 succeeded 必填 |
| Durable 读取 | `durable/outbox.py:979` | `_item_row_from_host_row` → `_validate_item_row` fail closed |
| Public 构造 | `read_api.py:811` | `_final_answer_from_outbox_json` 解析 JSON → `HostFinalAnswerView` |
| Public 校验 | `api.py:3161-3174` | `_validate_outbox_terminal_payload` 校验 succeeded 必填 |
| Memory/compact/run input | `durable/memory.py:393`, `compact_material.py:2213`, `run_input.py:3236` | 调用 optional resolver strict policy，已有 typed material consumer 不变 |

所有层从同一个 `_resolve_assistant_final_answer_continuity_text` core 派生 content。metadata 从 canonical `RUN_SUCCEEDED` payload 派生。memory/compact/run input 继续消费 optional resolver 的 typed text，不反向打开 descriptor。纯 `dayu.host.memory` consumer 保持 lenient descriptor-blind inline fallback。

**裁决**: 无缺陷。语义从产生、持久化、审计、投影到用户/LLM 可见输出的每一处均一致。

## Open Questions

无。

## Residual Risk

1. `_final_answer_json` 产出的 JSON 包含 `terminal_status: "succeeded"` 字段（`outbox.py:385`），但 `_final_answer_from_outbox_json`（read_api.py:823）读取后不做验证。该字段当前是冗余信息（只有 succeeded 行有 `final_answer_json`），不影响正确性，但若未来 schema 演进可能成为 silent drift 入口。当前不构成 defect。

## Verification

- `pyright dayu/host/_terminal_answer.py dayu/host/api.py dayu/host/read_api.py dayu/host/outbox.py dayu/host/durable/outbox.py`: 0 errors, 0 warnings
- `pytest tests/host/test_terminal_payload.py tests/host/test_read_api_terminal_policy.py tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_public_outbox_api.py tests/host/test_public_open_host_options.py tests/host/test_public_offline_outbox_smoke.py`: 71 passed
- `README` 更新已审查：`dayu/host/README.md` 新增段落准确描述 resolver 共用、metadata 来源、原子性、failure/retry 语义

## Verdict

**Accept — 0 findings**。

P3-B S1 implementation 正确实现了 accepted plan 的全部设计决策：resolver source selection 统一、required/optional contract 分离、canonical metadata 与 descriptor content 同源但不混用、Outbox 同事务原子写入、succeeded 必填 invariant 在 durable/public 三层闭合、删除第二 parser 无遗漏、production smoke 真实断言 descriptor-only shape。测试覆盖了全部 failure matrix case、rollback/recovery/idempotency 闭环、forged answer 伪造场景和 boundary conditions。
