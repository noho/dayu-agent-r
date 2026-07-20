# WU-SEMANTIC-OWNERSHIP-01 / R03 aggregate deepreview（AgentMiMo 第一路）

## Scope

- Mode: current changes（working tree，含未提交 F01-F03 fixes）
- Branch: `phaseflow/host-issues-control`
- Base: `8c6ae966`（R03 accepted plan commit）
- Baseline range: `b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`
- Output file: `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-mimo.md`
- Included scope: S1=`3e48f09e`、S2=`4b4696e5`、S3=`3f777753` + working tree F01-F03 fixes（`accepted_result_projection.py`、`compact_material.py`、`smoke_host_public_r03_semantic_ownership.py`）
- Excluded scope: credential/raw config、design truth、prior artifacts、Issue #177/#178
- Parallel review coverage: 3 subagents 覆盖全部 R03 production files（15 个）和 6 个关键 test files；主 reviewer 整合、去重、adversarial 复核

## 真源文档确认

已完整读取并以之为真源：
- `AGENTS.md`（CLAUDE.md）
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
- `docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`
- `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`（accepted plan）
- `docs/reviews/wu-semantic-ownership-01-r03-aggregate-controller-validation.md`（Controller validation）

裁决优先级：controller discussion > design truth > accepted plan > 直接代码/数据证据。

## Findings

### 未发现实质性问题

对 R03 完整组合行为（S1+S2+S3+F01-F03）的 adversarial deepreview 未发现可由直接代码/数据证据支撑的实质性 defect。

以下逐维度说明审查结论：

## 1. Correctness — shared request atom

**S1 contract 验证：**

- `dayu/host/tool_call_request.py`：唯一 writer `build_tool_call_requested_event_request`，接受 `AcceptedToolCallRequestAtomInput` 15 字段 frozen dataclass。`__post_init__` 校验所有 identity 字段非空、所有 digest 为 sha256 格式。writer 写 `EventClass.CANONICAL_FACT`，arguments/semantic query 按 `payload_inline_threshold_bytes` 选择 inline/descriptor。arguments digest 不变量 `sha256_digest_json({"arguments": dict(args)}) == normalized_arguments_digest` 在写前强制校验。
- ordinary/awaiting 两入口均通过同一 writer 写 `TOOL_CALL_REQUESTED`。`ToolFactAcceptCandidate.tool_identity_digest` 和 `ToolAwaitingAcceptCandidate.tool_identity_digest` 原样传入，builder 不重算。
- `tool_call_request_atoms` reader 额外校验 `arguments_payload_digest == normalized_arguments_digest`，不一致抛 `HostDurableError`。

**验证结果：** ordinary/awaiting 的 `TOOL_CALL_REQUESTED` 使用同一 builder、同一字段集合、同一 digest 不变量。payload key set 完全相同，只有业务值（`tool_fact_kind`、idempotency）不同。

## 2. Owner boundary — TOOL_AWAITING payload

**直接证据：** `dayu/host/_event_payload.py::tool_awaiting_payload` 签名只含 identity/awaiting metadata 字段。`accepted_arguments`、`normalized_arguments_digest`、`accepted_arguments_source_digest` 和任何 `arguments_*` 字段均已删除。`TOOL_AWAITING` 通过 `tool_call_requested_event_ref={event_id, event_sequence}` 显式链接 request atom。

**awaiting accept sequencing 验证：** `waiting.py::_accept_in_transaction` 执行顺序为：(1) idempotency check → (2) shared writer 构造 `TOOL_CALL_REQUESTED` → (3) `append_event(...).row` 取得真实 row → (4) 以 row 的 `event_id/event_sequence` 构造 ref → (5) append `TOOL_AWAITING` → (6) 后续 facts/state/idempotency。全部在 `run_write` 事务中，任一异常整组 rollback。

## 3. Hot/cold accepted-result integrity — F02 fix

**直接证据：** `accepted_result_projection.py::_result_payload` 当前逻辑（working tree diff）：

```python
if fallback_payload.get(_FIELD_RAW_TOOL_OUTCOME) is not None:
    return fallback_payload, ()
if envelope is None:
    return fallback_payload, ("accepted_evidence_envelope_missing",)
return event_payload_object_for_result_ref(...)  # cold descriptor resolution
```

F02 修复正确：不再用 `resolved_payload_available` 布尔标志（该标志只证明 EventLog hot payload 已读取，不证明其中引用的 cold result payload 已解析）。改为直接检查 hot payload 是否含 `raw_tool_outcome`。inline 路径直接使用；descriptor 路径通过 envelope 的 `payload_ref/payload_digest` 解析冷 payload 并严格校验 ref/digest。

**测试覆盖：** `test_accepted_result_projection.py` 含 hot-inline + cold-result descriptor shape 覆盖、cold descriptor corruption（ref mismatch、digest mismatch、ref missing、digest missing）四个反例。

## 4. Canonical request/result typed selection — F03 fix

**直接证据：** `utils/smoke_host_public_r03_semantic_ownership.py` 新增 `_canonical_fact_rows` 和 `_strict_accepted_request_atoms` 两个辅助函数。两者都按 `EventClass.CANONICAL_FACT` 过滤 row，不按 event type 独立选择。Engine `preview` 与 Host `canonical_fact` 共享同一 event type 时，只有 `CANONICAL_FACT` 进入 strict resolver。

**测试覆盖：** `test_smoke_host_public_r03_semantic_ownership_assembly.py::test_strict_diagnostic_collection_ignores_engine_previews` 构造同 session 的 PREVIEW 和 CANONICAL_FACT row 对，断言 preview 不进入 strict atom/accepted-result validation。

## 5. RunInput/Memory/Compact/LLM-ready Trace 同源

**四消费者同源验证：**

| 消费者 | evidence 文本来源 | material 缺失处理 |
|---|---|---|
| RunInput | `render_accepted_tool_evidence_for_llm(material)` | `HostDurableError` |
| Memory | `render_accepted_tool_evidence_for_llm(material)` via `_selected_evidence_text` | `HostDurableError` |
| Compact | `render_accepted_tool_evidence_for_llm(projection.llm_material)` | `HostDurableError` |
| Tool Trace | `project_accepted_tool_result` → `_tool_result_summary_from_projection` | `HostDurableError` |

所有四消费者从同一 shared `AcceptedToolEvidenceLLMMaterial` 通过唯一 renderer `render_accepted_tool_evidence_for_llm` 生成 LLM-facing 文本。缺 material 时均抛 `HostDurableError`，不走 skip/fallback/limited signal。

**F01 fix（compact_material.py）验证：** `run_input_material_block` 对 accepted evidence block 跳过 `normalized_material_text()`（因文本来自 shared renderer），直接使用 renderer exact text。`RunInputMaterialBlock.__post_init__` 校验 `block.text == render_accepted_tool_evidence_for_llm(block.accepted_tool_evidence)`，不允许 generic normalization 改写 shared renderer 输出。

## 6. Opaque provenance internal-only

**直接证据扫描：**

- `OpaqueEvidenceRef` 在 `accepted_result_projection.py`、`run_input.py`、`memory.py`、`compact_material.py`、`tool_trace.py` 五个共享/LLM path 中零命中。
- `compact_material.py` 所有 `source_locator_refs` 均设为空 tuple `()`。
- `memory.py` 的 `source_refs` 类型为 `OpaqueMemoryRef`（内部 memory provenance），不出现在 LLM-facing 文本中。
- `tool_trace.py` 的 `ref_kind`/`ref_id` 仅用于 hot row/cold JSONL 诊断字段，不进入 readable summary。

**sentinel 测试验证：** `test_opaque_provenance_round_trips_but_stays_out_of_projection` 和 `test_same_accepted_result_has_equivalent_consumer_projection` 使用三组 sentinel refs（含故意 typo "fliing-typo" 和 "eventlogg"），断言它们在 projection text、RunInput messages、Memory evidence、compactor source_note 和 Tool Trace business_source_text 中均不存在。

## 7. LLM-facing 文本

**source projection 验证：** `_source_projection` 只从 completed+ok outcome 的 `result.value.citation` object 提取 producer-owned 业务来源。Host 机械渲染整个 citation object（`canonical_json_dumps`），不枚举/筛选/排序 citation 业务 key。缺 citation 时使用唯一业务中性文案 `"该工具结果未提供业务来源。"`。

**旧 safe/fallback 文本扫描：** `rg -n '工具证据不可用；缺少可安全展示|业务来源不可用；工具结果未提供可安全展示|参数正文由 accepted-result 同源投影提供' dayu tests` 零命中。旧 safe-arguments repair、`json_redaction`、`_SENSITIVE_KEY_FRAGMENTS`、`JSON_REDACTION_MARKER`、`_INTERNAL_SOURCE_REF_KINDS`、`_readable_ref_text` 等已删除符号在 production/test 中零残留。

**query projection 验证：** `semantic_query_text` 存在时原样使用；否则对 exact `arguments_json` 做 bounded canonical JSON 展示（1200 字符上限），不做 key 分类。

## 8. 安全保留项

- DNS/peer、path containment、symlink、resource budget、atomic/process fencing 语义均保持。
- `file_path`、上传文件路径、合法业务字段和 framework `scope_token` 不因字段名被删除或改写。
- `dayu/tools/web/web_tools.py::password` 只属于 URL userinfo 解析，不是 LLM schema 参数。
- current production tool schemas 没有 `api_key/password/credential/access_token` 参数。
- `run_input.py::_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 包含 `policy_snapshot_ref=`、`tool_call_id=`、`event_id=`、`payload_ref=`、`artifact_ref=` 等 16 个内部治理标识，不得出现在 LLM-facing system content 中。

## 9. 统一 tool authorization 检查

`rg -rn 'unified.*tool.*auth|tool.*authorization|authorization.*framework|credential.*broker' dayu/ tests/` 在 production code 中零命中。未引入统一 tool authorization。

## 10. Deferred Issue 边界

- Issue #177（Doc output continuation wiring）：不在 R03 scope。`fetch_more` schema 文案修正是 S2 owner-level 修改，不声称 #177 完成。
- Issue #178：完全不进入 R03。
- Issue #142、#151、#175：代码中无引用。
- 未新增第四 slice、兼容分支或 legacy fallback。

## 11. Wait-resolution execution identity

**直接证据：** `durable/run_transition.py::_invalid_waiting_resolution_precondition` 校验 `wait_record.execution_id == source_attempt.execution_id`。不一致返回 `INVALID_STATE`，发生在任何 result/resume/terminal append 及 state mutation 之前。`_waiting_tool_result_event_request` 写入 `attempt_id=source_attempt.attempt_id`、`execution_id=source_attempt.execution_id`。

**测试覆盖：** `test_resolve_wait_command.py::test_waiting_resolution_transition_rejects_execution_identity_mismatch` 参数化 `completed` 和 `failed` 两个 transition branch，用 `_ResolutionTables` 全表 before/after 快照断言零 mutation。

## 12. 测试验证

```text
pytest <§13.1 第一组 22 个 suites> -q
=> 432 passed, 1 skipped, 3 warnings

python -m pyright dayu/ tests/ utils/
=> 0 errors, 0 warnings, 0 informations
```

三条 warning 均为 edgar 依赖弃用提示。

## 13. 源码扫描

| 扫描命令 | 结果 |
|---|---|
| `llm_safe_replay_arguments\|arguments_summary_unsafe\|safe_arguments\|accepted_arguments_source_digest` | 零 production/test 命中 |
| `redact_sensitive_json_fields\|json_redaction\|_SENSITIVE_KEY_FRAGMENTS\|JSON_REDACTION_MARKER` | 零 production/test 命中 |
| `_INTERNAL_SOURCE_REF_KINDS\|_readable_ref_text` | 零 production/test 命中 |
| `OpaqueEvidenceRef` 在 5 个 shared path | 零命中 |
| 旧 safe/fallback 中文文案 | 零命中 |

## Open Questions

无。

## Residual Risk

- 真实 public-run smoke 依赖外部环境（provider credential、Web 网络、Fins fixture）。Controller 已在独立 fresh root 验证通过。若环境变化需重跑。
- macOS coverage 预载入 NumPy/Pandas 破坏 `spawn` pickling identity，Web/Fins coverage run 排除各 6 个子进程用例；这些用例在无 instrumentation 的完整文件测试中通过。
- `waiting.py::_expire_wait_in_transaction` 本地实例化 `IdempotencyStore()` 和 `EventLogStore()`，功能正确但与类 DI 模式不一致，属于 minor design inconsistency。
- `waiting.py::_WAIT_EXPIRY_MESSAGE` 硬编码中文字符串 `"等待任务已超过 Host 期限，结果未被接受。"` 流入 failed tool result，可能出现在 LLM 上下文中。这是 Host 框架层面的 wait 超时提示，语义自解释，当前无歧义。

## 审查覆盖总结

| 区域 | 覆盖方式 | 结论 |
|---|---|---|
| S1 shared request atom + durable replay identity | subagent 1 全文读取 + 主 reviewer adversarial 复核 | PASS |
| S2 blacklist 删除 + owner schema 修正 | subagent 1/2 读取 + source scan | PASS |
| S3 opaque refs internal-only propagation | subagent 1 读取 + sentinel test 验证 + propagation scan | PASS |
| F01 compact whitespace preservation | 主 reviewer 直接读取 working tree diff + test 验证 | PASS |
| F02 cold descriptor resolution | 主 reviewer 直接读取 working tree diff + 4 corruption 反例 | PASS |
| F03 EventClass.CANONICAL_FACT selection | 主 reviewer 直接读取 working tree diff + assembly test 验证 | PASS |
| Wait-resolution execution identity | subagent 2 读取 + parametrized transition test | PASS |
| LLM-facing 文本 / 安全保留项 | 全仓 scan + 子代理逐文件审计 | PASS |
| Deferred Issue 边界 | 代码零引用确认 | PASS |
| 统一 tool authorization | 全仓 scan 零命中 | PASS |

## Final Verdict

**PASS。**

| 指标 | 值 |
|---|---|
| 总体 verdict | **PASS** |
| accepted findings | **0** |
| blocking open questions | **0** |
| 审查覆盖维度 | 10/10 PASS |

Residual Risk 中两项明确分类：

- **`waiting.py::_expire_wait_in_transaction` DI inconsistency**：**不是 accepted finding，不要求当前 fix。** 该 helper 是模块级私有函数，在 `run_write` 事务内调用，功能正确；本地实例化 store 只影响测试隔离性，不影响 production 行为或 R03 owner contract。归类为 minor design observation，不阻塞 R03 completion。
- **`waiting.py::_WAIT_EXPIRY_MESSAGE` 硬编码中文**：**不是 accepted finding，不要求当前 fix。** 该文案是 Host 框架层面的 wait 超时提示，语义自解释、无歧义、无 opaque ref、无 credential。它流入 failed tool result 属于正常 Host governance 行为，与 R03 Topic 3/4 的 accepted-call 语义/provenance 修复无关。若未来需统一 Host 框架级 LLM-facing 文案治理，应在独立 sub-WU 中处理。

两项均不阻塞 R03 aggregate completion，不要求在当前 gate 内修复。
