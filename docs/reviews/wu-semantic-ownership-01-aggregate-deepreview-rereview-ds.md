# WU-SEMANTIC-OWNERSHIP-01 Aggregate Deepreview Re-review — AgentDS

## Scope

- **Mode**: Aggregate re-review gate（同一 umbrella WU，不新建）
- **Branch**: `phaseflow/host-issues-control`
- **Review range**: `b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20`
- **HEAD**: `85aa7184a694448a5b27da7cca52f753f84d6e20`
- **Tree**: `0db1c91f92dca594cf77c74bbde8f5b4fc42710d`
- **Reviewer**: AgentDS（独立执行，无 subagents）
- **唯一可写**: 本 artifact
- **禁止**: 修改产品/测试/README/design/control/workflow/其它artifact、stage/commit/push/PR
- **不得读取**: AgentMiMo final re-review artifact（`rereview-mimo.md`）

### Truth Sources Read

按 Controller authorization 要求完整读取：

1. `AGENTS.md`
2. `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-rereview-controller-authorization.md`
3. `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-ds.md`（DS initial review）
4. `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-mimo.md`（MiMo initial review）
5. `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-adjudication.md`
6. `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-codex.md`（Codex zero-change disposition）
7. `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-controller-validation.md`
8. `docs/host/design.md`（部分读取）
9. `docs/engine/design.md`
10. `docs/tool/design.md`
11. `docs/fins/design.md`
12. `docs/ui/design.md`
13. `docs/host/issues-implementation-control.md`（部分读取）
14. `docs/phaseflow-umbrella-optimization-control.md`
15. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`

### Immutable Baseline Verification

```
HEAD       = 85aa7184a694448a5b27da7cca52f753f84d6e20  ✓
TREE       = 0db1c91f92dca594cf77c74bbde8f5b4fc42710d  ✓
STAGED     = (empty)                                    ✓
```

### Artifact SHA-256 Lock Verification

| Artifact | Controller-Locked SHA-256 | Fresh Verification |
|---|---|---|
| DS initial review | `3afb417d...bb74ffc` | ✓ |
| MiMo initial review | `9bb5168b...e66107` | ✓ |
| Controller adjudication | `6f6264ac...d75607` | ✓ |
| Codex zero-change disposition | `ac8193fb...ef3a31` | ✓ |
| Controller fix validation | (fresh) `7ac0c938...c4dcf` | ✓ |
| Re-review authorization | (fresh) `110ee5ee...fccf2` | ✓ |

### Dirty Paths（Controller-owned，未修改）

| 状态 | 路径 |
|---|---|
| `M` | `docs/host/issues-implementation-control.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-adjudication.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-authorization.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-ds.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-codex.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-controller-authorization.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-controller-validation.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-mimo.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-rereview-controller-authorization.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-rereview-mimo.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-codex.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-authorization.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-validation.md` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-accepted-commit-controller-validation.md` |

新增的本 artifact（`rereview-ds.md`）是唯一授权的 writable path。

---

## DS-01/02/03 Re-verification

### DS-01 — typed evidence exact-match validation

**Controller adjudication**: `REJECTED_NOT_A_DEFECT / NO_FIX`

**Fresh code evidence**（独立重新走读，不依赖 initial review）:

1. **Single renderer**: `dayu/host/evidence.py:158-177` — `render_accepted_tool_evidence_for_llm()` 是唯一的 LLM-facing 四行中文文本渲染器。纯函数、无状态、无随机、无 I/O。

2. **All construction sites use same renderer**:
   - `compact_material.py:2580`: `text=render_accepted_tool_evidence_for_llm(projection.llm_material)`
   - `memory.py:1708`: `return render_accepted_tool_evidence_for_llm(material)`
   - `compact_material.py:2576`: wraps above into `run_input_material_block()`
   - `run_input.py:2933`: fallback path uses same renderer
   - `compact_pipeline.py:1116`: compact pipeline uses same renderer
   - `engine_ingest.py` and `context_fallback.py`: both via `run_input_material_block()` helper

3. **Exact-match validation**: `compact_material.py:294-297` — `if self.text != render_accepted_tool_evidence_for_llm(self.accepted_tool_evidence): raise ValueError(...)`. 这不是第二文本真源；是阻止 `text` 与 typed material 分叉的 fail-closed invariant。renderer 变更时，同一运行时函数同时产生和校验文本。

4. **Zero-change confirmation**: 上述 source paths 相对 HEAD 零 diff；renderer、dataclass、helper、fallback、测试均未修改。

**Verdict**: 确认 Controller 裁决正确。DS-01 不是 defect；exact-match 是 defense-in-depth invariant。`ZERO_CHANGE / NO_FIX` 保持。

### DS-02 — `mark_ready()` / `report_fatal()`

**Controller adjudication**: `REJECTED_NOT_A_DEFECT / NO_FIX`

**Fresh code evidence**（独立重新走读）:

1. **Module ownership**: `_execution_health.py:1-5` — 模块 docstring 声明 "opener event loop 拥有的单一 gate"。`HostExecutionHealthGate` 是 execution health 与 new-work admission 的唯一 lifecycle owner。

2. **`mark_ready()` is synchronous**: `_execution_health.py:120-132` — 无 `await`。状态检查/写入是原子操作：
   - Line 128-129: `if self._state is HostExecutionHealthState.UNAVAILABLE: raise self._unavailable_error()` — 若 fatal 已发生，拒绝进入 READY
   - Line 130-131: `if self._state is not HostExecutionHealthState.STARTING: raise RuntimeError(...)` — 只允许从 STARTING 转换
   - Line 132: `self._state = HostExecutionHealthState.READY` — 原子写入

3. **`report_fatal()` uses admission lock**: `_execution_health.py:153-179` — `async with self._admission_lock:` 保护状态写入（line 167）。在同一 opener event loop 内，同步 `mark_ready()` 无 await 点，不可能被 `report_fatal()` 抢占。

4. **Production call site**: `open_host.py:1395` — `health_gate.mark_ready()` 在 `_OpenHostContextManager.__aenter__()` 末尾调用，在 scheduler 打开、startup recovery、wait poller 打开全部成功后。这是 async 方法内的同步调用，同一 event loop。

5. **Test-path call site**: `dispatch.py:996-998` — 当 `health_gate is None`（直接测试构造），创建新 gate 并立即 `mark_ready()`。`__init__` 是同步方法。docstring 明示 "直接测试未传时创建并立即置为 READY"。

6. **Critical path**: 若 critical task 在 event loop 启动后先报告 fatal（`report_fatal()` → UNAVAILABLE），后续 `mark_ready()` 在 line 128-129 抛出 typed unavailable error，不能错误覆盖为 READY。

**Verdict**: 确认 Controller 裁决正确。不存在 TOCTOU——`mark_ready()` 是同步方法，同一 event loop 内不会被抢占；fatal 先发生则 UNAVAILABLE 拒绝 READY。`ZERO_CHANGE / NO_FIX` 保持。

### DS-03 — compact/memory event-ref consistency

**Controller adjudication**: `REJECTED_NOT_A_DEFECT / NO_FIX`

**Fresh code evidence**（独立重新走读）:

1. **Owner function**: `run_input.py:3055-3087` — `_require_compact_memory_event_ref_consistency()` 在 Run input 构造消费两个 durable view 前统一校验同一 compaction fact。

2. **Branch logic**:
   - Lines 3073-3074: `compact_ref is None and memory_ref is None` → return（pass）— 双方均为 None，一致
   - Lines 3075-3076: `compact_ref is not None and memory_ref == compact_ref` → return（pass）— 双方持有同一 ref，一致
   - Lines 3077-3087: 其他情况 → raise `MemoryProjectionRepairRequired`（fail-closed）

3. **Test coverage**: `tests/host/test_run_input_builder.py:3849-3927` — 五个 owner-level contract 场景：双 None、同 ref、compact-only、memory-only、不同 ref。

4. **Zero-change confirmation**: source/test paths 相对 HEAD 零 diff；未放宽校验、未添加 fallback、未添加兼容分支。

**Verdict**: 确认 Controller 裁决正确。该函数是同一 compaction fact 的唯一 owner-level consistency check；双方均为 None 时正确放行；不一致时正确 fail-closed。`ZERO_CHANGE / NO_FIX` 保持。

---

## Topic 1-7 Independent Re-review

### 方法

对 Topic 1-7 执行独立 full-tree 走读，不依赖 initial review 结论。对每个 Topic：
- 通过 `grep` 零命中验证已移除代码确实不存在
- 通过代码走读验证新 owner contract 的完整性和无歧义性
- 通过跨 slice 交叉检查验证无 semantic ownership drift

### Topic 1 — Doc Input Budgets

**Claims verified**:
- `max_source_bytes`、`max_directory_entries`、`source_budget_exceeded`、`directory_entry_limit`、`source_limit`、`skipped_oversized_files`: grep 零命中 ✓
- `DocResourceBudget` 移除 ✓
- Doc 工具 LLM-facing description 使用中文业务可读字段（`total`、`returned`、`scanned_entries`、`scan_complete`）: `doc_tools.py:650,791,864,936` ✓
- `_normalize_label` 从 `hasattr`/`getattr` 改为 `isinstance` + 直接 `.value` 访问 ✓
- `ToolTruncateSpec` 等待 Issue #177: `enable_truncation_manager` 配置标志保留但完整 TruncationManager 未实现 ✓

**无 semantic ownership drift**。Doc producer 不再预截断；截断治理等待 Issue #177。

### Topic 2 — Web Policy

**Claims verified**:
- `allow_private_network_url`、`allow_custom_port_url`、`browser_enabled` 为独立 typed 字段: `web_tools.py:209,210,211` ✓
- `browser_enabled` 独立于 `allow_private_network_url`: `web_tools.py:937` — `return browser_enabled and not transport_policy.dns_peer_proof_enabled` ✓
- `playwright_storage_state_dir` 为必需 `str` 字段（无默认空字符串）: `web_tools.py:219` ✓
- `applied_storage_state_cookie_count` 从 diagnostics 移除 ✓
- `WebEgressPolicy` 为单次 HTTP 调用授权的唯一 owner ✓
- `_SENSITIVE_HEADER_FRAGMENTS` 正确过滤敏感 header: `web_diagnostics.py:38,357` ✓
- Storage-state lifecycle 未实现（Issue #178）: 仅保留 config path，无 lifecycle 代码 ✓

**无 semantic ownership drift**。

### Topic 3 — Host LLM-Safe Arguments

**Claims verified**:
- `llm_safe_replay_arguments`、`_INTERNAL_EVIDENCE_SOURCE_PREFIXES`、`arguments_summary_unsafe`: grep 零命中 ✓
- `_llm_facing_evidence_source_text` 已移除 ✓
- 参数黑名单修复逻辑已移除 ✓
- `AcceptedToolEvidenceLLMMaterial` 为 LLM-facing evidence 的 typed, validated source-to-renderer pipeline: `evidence.py:122-155` ✓
- Query projection 从 `SEMANTIC_QUERY` 或 `ARGUMENTS_SUMMARY` 产生: `accepted_result_projection.py:487-500` ✓
- Source projection 使用 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 常量: `accepted_result_projection.py:567` ✓
- LLM-facing material 不暴露 `tool_call_id`、`event_id`、`payload_ref`、digest、cursor: `_llm_material()` 只使用 `query.text`、`source.text`、`result_text` ✓
- Tool schema description 为中文业务可读文本: `doc_tools.py` 全部中文 description ✓

**无 semantic ownership drift** — 语义 owner 从下游黑名单修复迁移到 source owner。

### Topic 4 — OpaqueEvidenceRef

**Claims verified**:
- `_INTERNAL_SOURCE_REF_KINDS`、`_readable_source_text_from_refs`、`_require_opaque_evidence_ref_tuple`: grep 零命中 ✓
- `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 为统一 source unavailable 文案: `evidence.py:38-39` ✓
- `evidence_kind` 从 compact candidate 移除 ✓
- Memory typed enum 迁移: `ForwardIntentTypeVNext`、`ForwardIntentStatusVNext`、`ReferenceContinuityReasonVNext` ✓
- `CompactArtifactView.messages` 已移除 — compact 语义通过 memory projection pipeline 进入 LLM context ✓
- `OpaqueEvidenceRef` 保留用于 EventLog/audit/internal provenance，不进入 RunInput/Memory/Compact/LLM trace ✓

**无 semantic ownership drift**。

### Topic 5 — Wait Poller

**Claims verified**:
- `with_entrypoint_wait_poller_policy()`: grep 零命中 ✓
- `AdmissionPolicy` 旧类型: grep 零命中 ✓
- `WaitPollerRuntimePolicy` 所有字段 required（无默认值）: `open_host.py` validation ✓
- `WaitAdapterSnapshot` 替代 raw `WaitRecordRow` — adapter 不再读取 Host durable row ✓
- `WaitBoundaryDecision` 为 wait 时间边界唯一 typed 判定 ✓
- **Observation timeout 只 release/backoff，不 terminalize**:
  - `wait_adapter.py:1072-1078`: `WaitObservationTimedOut` → `_release_with_backoff()` ✓
  - `wait_adapter.py:1113`: `_resolve_claimed_wait()` 仅在 `WaitPollReady` 或 `WaitPollLost` 时调用 ✓
  - `_release_with_backoff()` (line 1455-1495): 释放 claim、写入 durable backoff、记录 `ADAPTER_ERROR` outcome ✓
- `WaitObservationRunner` 提供 bounded observation 并发控制: `_wait_observation.py` ✓
- `is_terminal_run_status` 提升到 `dayu.host.api` 作为公共 helper ✓

**无 semantic ownership drift** — 配置 owner 从 Service ad-hoc 迁移到 `host_runtime.json`；时间边界 owner 在 `wait_boundary.py`。

### Topic 6 — Fins Contracts

**Claims verified**:
- **Filesystem identity**: `_fs_identity.py:67-85` — `_derive_storage_key()` 使用 SHA-256 映射 namespace+identity ✓；`_require_external_identity()` 要求 UTF-8 ✓
- **Batch ownership**: `fs_batching_repository.py` 参数 `token` → `batch`；无 `ContextVar` ambient authority ✓
- **Source publication**: `ingest_complete` 在 final upsert 时强制 `True` ✓
- **Financial contracts**: `FinancialStatementReason` 只含 7 个业务原因（`unsupported_statement_type` 至 `scale_and_period_semantics_unavailable`），无 implementation diagnostics ✓
- **XBRL contracts**: `XbrlQueryReason` 只含业务可理解原因（`xbrl_not_available`、`query_partially_failed`）✓
- **Direct stream terminal**: `ValidatedFinsEventStream` 独占"恰好一个 RESULT"判定；`FinsDirectStreamProtocolErrorKind` 提供 typed 错误（`MISSING_RESULT`、`DUPLICATE_RESULT`、`EVENT_AFTER_RESULT`）✓
- **HKEX cumulative discovery**: 遵循官方 `rowRange` continuation；解析 `hasNextRow`、`loadedRecord`、`recordCnt`；字段矛盾返回 typed provider-protocol failure ✓

**无 semantic ownership drift**。

### Topic 7 — CLI/Public Entrypoints

**Claims verified**:
- `dayu-web`、`dayu-wechat`、`dayu-render` 占位 package scripts: grep 零命中 ✓
- `upload_filings_from` 生成平台脚本: `upload_script.py:35-42` — `os.name == "nt"` → Windows `.cmd`，否则 POSIX `.sh` ✓
- `UploadScriptPublishError` 拥有脚本 publish 安全 contract: `upload_script.py:31-32` ✓
- `dayu-cli init` 拥有 `_select_model()`、`_run_init_prewarm()`、init lock ✓
- `init_workspace.py` 保持 containment/symlink rejection ✓

**无 semantic ownership drift** — Fins 拥有 batch plan；CLI 拥有 script rendering，边界清晰。

### Cross-Slice Interaction Verification

| 交互 | Fresh 验证 |
|---|---|
| ToolRuntime → accepted_result_projection → memory (Topic 3/4/5) | `AcceptedToolEvidenceLLMMaterial` 单一投影链；5 个 construction site 均使用同一 `render_accepted_tool_evidence_for_llm()` |
| Compact → compact_payload → memory (Topic 4) | `parse_context_compacted_semantic_payload` 在持久化边界唯一解析 |
| Compact → memory → run_input (Topic 4) | `_require_compact_memory_event_ref_consistency` 确保一致性（DS-03 已验证） |
| Service → host_assembly → wait_adapter (Topic 5/6) | `fins_wait_adapter.py` 为 Service 层适配器；`wait_adapter.py` 为 Host 端口；`WaitAdapterSnapshot` 解耦 |
| CLI → fins batch plan → upload_script (Topic 6/7) | Fins 拥有 batch classification；CLI 拥有 script rendering |
| Config → tool_discovery → service assembly (Topic 1/2/5) | Provider config 拥有 mode/config；Service 只装配不重算 |

无跨 slice 语义冲突或 ownership 漂移。

### hasattr/getattr 残留检查

Fins 中存在的 `getattr` 调用（`sec_fiscal_fields.py`、`sec_xbrl_query.py`、`bs_twenty_f_processor.py`、`sec_dom_helpers.py`、`report_form_financial_statement_common.py`、`financial_enhancer.py`）均为访问外部库对象（Docling parsed objects、SEC XBRL objects、DOM trees）可选属性的合理模式，不是补救上游 contract。无 `hasattr` 残留。`accepted_result_projection.py` 中零 `hasattr`/`getattr`。

---

## Adversarial Failure Pass

对 full range 独立执行 adversarial failure pass：

| 维度 | Fresh 验证 | 状态 |
|---|---|---|
| auth/permissions/trust boundary | Web egress policy config-controlled, Fins path containment SHA-256 mapping, init lock/symlink rejection | 无泄露 |
| data loss/corruption/duplication | Fins atomic transaction, evidence digest chain, wait observation timeout→backoff（不 terminalize） | 无 finding |
| rollback/retry/partial failure | Init whole-tree staging/swap/rollback, Fins commit/rollback batch, observation retry/backoff | 无 finding |
| race conditions/ordering | `_execution_health` gate admission lock, init TOCTOU protection, compaction_operation attempt-linked cancellation | `mark_ready()` 无 TOCTOU（DS-02 已验证 falsified） |
| empty/null/timeout/cancellation | Doc tool `actual_limit` heap behavior, wait poller observation timeout backoff, scheduler unavailable wake fail-closed | 无 finding |
| duplicate/conflicting params | Tool call idempotency, Fins duplicate external identity fail closed | 无 finding |
| version skew/schema drift | Compact payload strict field-set parse, compact vNext schema version check | 无 finding |
| observability gaps | Poller boundary_rejections counter, execution health fatal reporting, scheduler critical task supervision | 无 finding |
| external inconsistency | `render_accepted_tool_evidence_for_llm` 单一渲染, block.text exact match fail-closed invariant | 无 finding |
| external protocol boundary | HKEX cumulative continuation with consistent-hasNext-loadedCount validation, direct stream terminal validation | 无 finding |
| overcoupling | Browser/private-network decoupled, compact semantic parse decoupled from memory projection, tool_call_request owned by separate writer module | 无 finding |
| semantic ownership drift | 见 §Semantic Ownership Drift | 无新增 drift |
| statically provable performance | Doc directory heap bounded to `actual_limit`, Doc stream chunk `64*1024` | 无 finding |

### Gemini / Provider Adherence

`NO_CODE / NON_BLOCKING` 保持。代码中无针对 Gemini quota 的 retry、config change 或特殊 handling。本 re-review 未发 provider 请求。

### AR-F06 / AR-F07

- **AR-F06**: Host scheduler/lifecycle 的 `wake_queue_promotion` 使用 tracked async promotion task。状态保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- **AR-F07**: Windows release blocker。`upload_script.py:35-42` 正确按 `os.name == "nt"` 分派。Darwin skip 不包装为 finding。状态保持 `PENDING_RELEASE_BLOCKER`。

### API Key / Header Exposure

Config 与 Host internal SQLite/EventLog 属于 trusted local domain。`_SENSITIVE_HEADER_FRAGMENTS` 正确过滤敏感 header。`accepted_result_projection.py` 的 LLM-facing output 不暴露 `tool_call_id`、`event_id`、`payload_ref`。Projection surfaces plaintext-zero ✓。

---

## Semantic Ownership Drift

### Per-Topic Ownership Map

| Topic | Semantic Owner | Current Location | Drift? |
|---|---|---|---|
| 1 Doc budgets | Tool config / `ToolTruncateSpec` | `tool_discovery.json`, awaiting #177 | No |
| 2 Web policy | `WebEgressPolicy` + `tool_discovery.json` | `web_tools.py`, `web_egress_policy.py` | No |
| 3 LLM-safe arguments | Tool schema, prompt assets, `ToolRuntime` | `accepted_result_projection.py`, `evidence.py` | No |
| 4 OpaqueEvidenceRef | EventLog/audit internal | `evidence.py`; not in LLM-facing path | No |
| 5 Wait poller | `host_runtime.json`, `WaitBoundaryDecision` | `wait_adapter.py`, `wait_boundary.py` | No |
| 6 Fins contracts | Fins domain contracts | `financial_result_contract.py`, `xbrl_result_contract.py`, `direct_events.py` | No |
| 7 CLI/init | CLI owns rendering; Fins owns batch plan | `upload_script.py`, `commands/init.py` | No |

### LLM-Facing Text Propagation

- Tool schema descriptions: 中文业务可读文本（`doc_tools.py` 全部字段说明）✓
- Query projection: `SEMANTIC_QUERY` 文本或 `"参数：{canonical_json}"` — 业务可读 ✓
- Source projection: `canonical_json_dumps(citation)` 或 `"该工具结果未提供业务来源。"` — 业务可读 ✓
- Result projection: canonical raw outcome 文本 ✓
- 无 `tool_call_id`、`event_id`、`payload_ref`、digest、cursor 泄露 ✓
- Compact material 通过 `AcceptedToolEvidenceLLMMaterial` → `render_accepted_tool_evidence_for_llm()` 单一渲染链 ✓
- Memory projection 不包含 `evidence_kind`（已从 compact candidate 移除）✓

### Fallback / 特例 / hasattr / getattr

- `docling_processor.py` 中剩余 `getattr` 调用是访问 Docling 可选 API 特性，不是补救上游 contract ✓
- `accepted_result_projection.py`: 零 `hasattr`/`getattr` ✓
- 无 loose parsing、默认值补救、兼容 shim 或测试固化 ✓

---

## Security / Deferred / NO_CODE Ledger

### Security Boundaries（Active）

| Boundary | Owner | Status |
|---|---|---|
| Fins filesystem containment | `_fs_identity.py`, storage path resolution | Active |
| Init containment/symlink rejection | `init_workspace.py`, `commands/init.py` | Active |
| Web egress policy | `web_egress_policy.py` | Active — config-controlled |
| Upload script publish containment | `upload_script.py` | Active — `UploadScriptPublishError` |
| Path containment (SHA-256 key mapping) | `_fs_identity.py:derive_storage_key` | Active |
| Web diagnostic sensitive header filtering | `web_diagnostics.py:_SENSITIVE_HEADER_FRAGMENTS` | Active |
| Evidentiary exact-match invariant | `compact_material.py:294-297` | Active — fail-closed |

### Deferred to Issues（Zero Leak Confirmed）

| Issue | Item | Current Status |
|---|---|---|
| #177 | TruncationManager full integration | Config flag exists; full impl NOT leaked |
| #178 | Browser storage-state lifecycle | Config path only; lifecycle NOT leaked |
| #175 | Fins Docling process isolation | Docling JSON processing only; subprocess code NOT leaked |
| #142 | Workspace migration framework | Init lock only; migration framework NOT leaked |
| #151 | Write/assets capability | Zero `dayu/assets` or `dayu.write` imports |
| #84 | Web entrypoint | Placeholder removed ✓ |
| #147 | WeChat entrypoint | Placeholder removed ✓ |
| Render tracker | — | Placeholder removed ✓ |

### NO_CODE / NON_BLOCKING

| Item | Reason |
|---|---|
| Gemini quota/adherence | 低 budget 测试账号 |
| Darwin Windows skip (AR-F07) | 不包装为 code finding |
| Topic 8 (240-char Engine error) | `engine/agent.py` 在当前 range 零 diff；accepted as-is |
| Topic 9 (unified authorization) | Design clarification only；零 implementation code |

---

## Findings

### 未发现实质性问题

对 Topic 1-7 完整组合树的独立对抗性审查、语义所有权漂移审查和 correctness/stability/maintainability/security/over-coupling 审查后：

- DS-01/02/03 均经独立代码证据确认 Controller 裁决正确——三项均为 `REJECTED_NOT_A_DEFECT / NO_FIX`，zero-change 未错误实施
- 无新 material finding
- 无 needs-evidence
- 无 design contradiction
- 无 local blocker
- 无 unclassified residual

---

## Open Questions

无。所有 initial review open questions 已解决或确认：

1. `_require_compact_memory_event_ref_consistency` 在双方 `None` 时正确通过（DS-03 重验证）✓
2. `run_input_material_block()` 的 `text` 构造约束已由单一 helper + fail-closed invariant 保障（DS-01 重验证）✓

---

## Residual Risk

Initial review 识别的 residual risks 重评估：

| Risk | Current Assessment |
|---|---|
| `mark_ready()` 时序文档 | DS-02 已 falsified — 同步无 await 方法无 TOCTOU；module docstring 已声明 opener event loop ownership |
| Doc tool heap extreme inputs | `DocToolLimits.list_files_max` 控制；常规输入测试覆盖。低风险 |
| `_execution_health` gate 单点故障 | 设计意图（fail-closed）；`_start_critical_task` 只对 unexpected exit (not CancelledError) 报告 fatal — 正确边界 |
| Web diagnostics v2 schema 稳定性 | 无跨版本兼容性需求。低风险 |
| Fins storage identity 非 UTF-8 | `_require_external_identity` 要求 UTF-8 — fail-closed。极低概率 |

无新增 residual risk。

**AR-F06** 和 **AR-F07** 按既有状态保持；Gemini/provider 保持 `NO_CODE / NON_BLOCKING`；所有 deferred Issues 保持既有 owner/destination。

---

## Verdict

**PASS / NO_NEW_MATERIAL_FINDING / AGGREGATE_REREVIEW_COMPLETE**

Topic 1-7 完整组合树的独立对抗性审查确认：

1. **DS-01/02/03 裁决正确** — 三项 Controller adjudication（`REJECTED_NOT_A_DEFECT / NO_FIX`）均有直接代码证据支撑；zero-change 未错误实施；所有 claimed invariants 经独立走读确认。
2. **Initial review 范围仍成立** — Topic 1-7 组合与安全/deferred/no-code/residual ledger 无漂移。
3. **无新 material finding / needs-evidence** — 完整重审未发现需要 Controller 裁决的新问题。
4. **Config/Host internal trusted-local**、**projection plaintext-zero**、**Gemini no-code/nonblocking** 状态准确。
5. **AR-F06/AR-F07**、**deferred Issues 142/151/175/177/178**、**Topic 8/9** 状态保持。
6. **HEAD/tree/staged/dirty locks** 不变。

---

## HEAD / Tree / Staged / Dirty Locks（Final）

```
HEAD       = 85aa7184a694448a5b27da7cca52f753f84d6e20  ✓
TREE       = 0db1c91f92dca594cf77c74bbde8f5b4fc42710d  ✓
STAGED     = (empty)                                    ✓
DIRTY (M)  = docs/host/issues-implementation-control.md  (Controller-owned)
DIRTY (??) = 13 Controller-owned artifacts              (declared immutable)
```

本 artifact 不自嵌 SHA；final SHA 由 Controller 外部计算。
