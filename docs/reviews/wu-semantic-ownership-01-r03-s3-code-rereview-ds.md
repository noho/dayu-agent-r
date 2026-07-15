# WU-SEMANTIC-OWNERSHIP-01 R03-S3 Final Code Re-Review (AgentDS)

## Scope

- Umbrella WU: `WU-SEMANTIC-OWNERSHIP-01`
- Remediation: `R03`
- Slice: `S3 — opaque refs internal-only propagation closure`
- Review type: Final code re-review（非新 WU，非初始 review）
- Branch: `phaseflow/host-issues-control`
- Baseline: `44e68550ed226a3a207a73bd257478ab1bbbdce4`
- Output file: `docs/reviews/wu-semantic-ownership-01-r03-s3-code-rereview-ds.md`
- Review timestamp: 2026-07-15 14:29 CST
- Included scope: `44e68550..worktree` 完整 S3 组合行为与全部新增 artifacts
- Excluded scope: 无

### 审查输入（已完整读取）

1. 根 `AGENTS.md`
2. `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` §11（S3 plan）、§12（smoke contract）
3. `docs/reviews/wu-semantic-ownership-01-r03-s3-implementation-codex.md`（Codex implementation handoff）
4. `docs/reviews/wu-semantic-ownership-01-r03-s3-controller-validation.md`（Controller validation，含 CV-F01..F05）
5. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-mimo.md`（初始 MiMo review）
6. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-ds.md`（初始 DS review）
7. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-controller-adjudication.md`（Controller adjudication）
8. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-fix-codex.md`（AgentCodex zero-change fix record）
9. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-fix-controller-validation.md`（Controller fix validation）

### 审查的生产文件

- `dayu/host/accepted_result_projection.py`
- `dayu/host/evidence.py`
- `dayu/host/run_input.py`
- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/tool_trace.py`

### 审查的测试/smoke 文件

- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py`（新增）
- `utils/smoke_host_public_r03_semantic_ownership.py`（新增）

### 审查的文档文件

- `dayu/host/README.md`
- `tests/README.md`

---

## Independent Verification Evidence

### V1: Protected target digests — AgentCodex record 与 Controller 独立复现

**Path-set SHA-256**：AgentDS 独立计算结果为 `acb20b019768832b83e99d0570c82638da478835ed6b8bb70ddd7894a76884aa`，与 AgentCodex record 及 Controller 独立复现一致。

**Per-file SHA-256**：对 26 个 protected targets 逐文件计算 SHA-256。其中 25 个非 control-doc 文件的 SHA-256 与 AgentCodex record §3.1 逐条匹配：

| Protected target | 匹配 |
|---|---|
| `dayu/host/accepted_result_projection.py` | `ff2b2204...` ✓ |
| `dayu/host/evidence.py` | `3738ee06...` ✓ |
| `dayu/host/run_input.py` | `9111e6ca...` ✓ |
| `dayu/host/memory.py` | `32c2a831...` ✓ |
| `dayu/host/durable/memory.py` | `9423b7d6...` ✓ |
| `dayu/host/compact_material.py` | `c8e1ddb8...` ✓ |
| `dayu/host/compact_pipeline.py` | `70cd1c87...` ✓ |
| `dayu/host/tool_trace.py` | `9a9b157b...` ✓ |
| `tests/host/test_accepted_result_projection.py` | `a4dbaad8...` ✓ |
| `tests/host/test_run_input_builder.py` | `f4e90d9b...` ✓ |
| `tests/host/test_memory_projection.py` | `c9915e94...` ✓ |
| `tests/host/test_compact_material.py` | `a82e2f03...` ✓ |
| `tests/host/test_tool_trace_projection.py` | `236dde54...` ✓ |
| `tests/host/test_tool_trace_queries.py` | `5897d4df...` ✓ |
| `tests/host/test_public_compact_smoke.py` | `25768c58...` ✓ |
| `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py` | `3bd5ebb8...` ✓ |
| `utils/smoke_host_public_r03_semantic_ownership.py` | `516b7590...` ✓ |
| `dayu/host/README.md` | `16e9280f...` ✓ |
| `tests/README.md` | `f3826a5c...` ✓ |
| `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` | `668d65d2...` ✓ |
| `docs/reviews/wu-semantic-ownership-01-r03-s3-implementation-codex.md` | `5fabadf2...` ✓ |
| `docs/reviews/wu-semantic-ownership-01-r03-s3-controller-validation.md` | `840e2806...` ✓ |
| `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-mimo.md` | `9d60a2c1...` ✓ |
| `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-ds.md` | `4b03324b...` ✓ |
| `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-controller-adjudication.md` | `fa365b10...` ✓ |

**唯一允许漂移**：`docs/host/issues-implementation-control.md` 的 SHA-256 从 AgentCodex record 中的 `0ce1da45...` 变为当前 `80d8fc1c...`。这是 Controller 在 zero-change fix 后新增 fix validation 并更新 control gate 的预期行为，与 Controller adjudication 中"record 后仅允许 Controller 新增 fix validation并更新 control gate"一致。

**Status/path 稳定性**：`tests/host/test_tool_trace_queries.py` 与 accepted plan 保持 CLEAN；S3 product/test/README 保持原 `M`；新增 smoke/assembly 与既有 S3 artifacts 保持 `??`；`docs/host/issues-implementation-control.md` 的 `M` 状态属 Controller 更新 control gate 的预期变化。其余 25 个 protected targets 的 status/path 与 AgentCodex record 一致。

### V2: Controller 独立复现可信

Controller fix validation（`docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-fix-controller-validation.md`）独立复算了全部 26 个 targets 的 path/content/status 三项 digest，与 AgentCodex record 一致。AgentDS 本次独立复算再次确认同一结果（除预期的 control doc drift）。

### V3: Zero-change fix record 真实性

AgentCodex 的 `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-fix-codex.md` 确认：
- 未修改任何 production、test、README、smoke、plan、design、control 或既有 artifact
- 唯一新增文件是该 fix artifact 本身
- `git diff --check` PASS
- 所有 protected target digests before/after 一致

### V4: pyright 与测试

```text
pyright (8 production files): 0 errors, 0 warnings, 0 informations
pytest S3 exact suites: 354 passed, 1 skipped, 3 warnings
pytest propagation filter: 261 passed, 63 deselected
```

skip 是既有 opt-in real compactor smoke；不是 R03 aggregate 外部 smoke 的 pass/skip。

### V5: Active source propagation scans

| 扫描目标 | 范围 | 结果 |
|---|---|---|
| `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` | `dayu/ tests/ utils/` | 零命中 |
| `ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT` | `dayu/ tests/ utils/` | 零命中 |
| `参数未安全展开` | `dayu/ tests/ utils/` | 零命中 |
| 旧 safe-display 文案 | `dayu/ tests/ utils/` | 零命中 |
| `_INTERNAL_SOURCE_REF_KINDS` | `dayu/ tests/ utils/` | 零命中 |
| `_READABLE_SOURCE_SEPARATOR` | `dayu/ tests/ utils/` | 零命中 |
| `_readable_ref_text` | `dayu/ tests/ utils/` | 零命中 |
| `OpaqueEvidenceRef` in 5 consumer files | production | 零命中 |
| `hasattr`/`getattr` in 8 production files | production | 零命中 |

### V6: Allowlist 与 no-diff

- All tracked diffs（`git diff --name-only 44e68550`）：16 个 implementation paths（8 production + 6 tests + 2 READMEs）在 accepted plan §11.2 allowlist 内；另 1 个 `docs/host/issues-implementation-control.md` 是 Controller-authorized governance diff
- `test_tool_trace_queries.py`：CLEAN（未修改）
- Four no-diff owners（`git diff --exit-code`）：exit 0 ✓
  - `dayu/host/compaction.py`
  - `dayu/host/durable/tool_trace.py`
  - `dayu/fins/tools/read_runtime.py`
  - `dayu/fins/domain/tool_models.py`
- Fins/config owner no-diff（`git diff --exit-code`）：exit 0 ✓
  - `dayu/fins/tools/fins_tools.py`
  - `dayu/config/prompts/base/tools.md`

### V7: 四消费者 strict no-fallback 逐路径证据

| 消费者 | 文件:行号 | 检查 | 错误类型 |
|---|---|---|---|
| RunInput | `run_input.py:_memory_projection_event_from_row` | `projection.llm_material is None` | `HostDurableError` |
| RunInput | `run_input.py:_fallback_message_from_material_block` | `block.accepted_tool_evidence is None` | `HostDurableError` |
| Memory | `memory.py:_selected_evidence_text` | `material is None` | `HostDurableError` |
| Durable Memory | `durable/memory.py:_tool_result_memory_payload_view` | `projection.llm_material is None` | `HostDurableError` |
| Compact Material | `compact_material.py:292` | `accepted_tool_evidence is None`（dataclass typed material invariant） | `ValueError` |
| Compact Pipeline | `compact_pipeline.py:1108` | `block.accepted_tool_evidence is None`（consumer） | `HostDurableError` |
| Tool Trace (request) | `tool_trace.py:1089` | `read_event_by_id` → row `None` | `HostDurableError` |
| Tool Trace (result) | `tool_trace.py:1111` | `projection.llm_material is None` | `HostDurableError` |
| Tool Trace (result) | `tool_trace.py:1273` | `llm_material/raw_outcome/result_text` 任一 `None` | `HostDurableError` |

四个消费者八条路径均无 skip、fallback、limited signal 或 consumer-specific recovery。

### V8: Opaque refs internal-only

- `OpaqueEvidenceRef` 仍由 `evidence.py`（L70-93）定义并由 `AcceptedEvidenceEnvelope`（L238-259）持有 `source_refs`/`locator_refs`
- `AcceptedToolResultProjection`（`accepted_result_projection.py` L111-148）不再携带任何 opaque ref field
- Sentinal 注入测试（`test_accepted_result_projection.py` L102-113, `test_run_input_builder.py` L228-239）证明 `fliing-typo`/`eventlogg` sentinel 在 envelope round-trip 后保留，但在 RunInput、Memory、Compact、Tool Trace 四消费者 LLM-facing 文本中均不可见

### V9: Explicit citation 唯一 readable business source

- `_source_projection`（`accepted_result_projection.py` L549-576）：只接受 `raw_outcome` 参数（不依赖 envelope），通过 `_explicit_citation` 查找精确 JSONPath `kind==completed → result.ok==True → value.citation`
- `_explicit_citation`（L579-598）：严格 shape 校验，不枚举 key，不猜测 ref kind
- 缺失/拼错/非 object citation 均返回唯一文案 `该工具结果未提供业务来源。`
- Host 通过 `canonical_json_dumps(完整 citation object)` 机械渲染，不解释 Fins domain

### V10: Tool Trace strict canonical request atoms

- Request（`tool_trace.py` L1089）：`read_event_by_id(transaction, event.event_id)` → `tool_call_request_atoms(transaction, request_row)` → exact bounded args/query
- Result（L1103）：`read_event_by_id` → `project_accepted_tool_result` → shared projection
- `business_source_text` / `business_source_state` 分别映射 `projection.source.text` / `projection.source.state.value`
- Old `_tool_request_summary_from_payload`、`_inline_arguments_json`、raw-payload/redaction/descriptor-placeholder 行为已删除

### V11: R03-S3-CV-F01..F05 闭合

| ID | 直接证据 | 状态 |
|---|---|---|
| CV-F01 | `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 从 `evidence.py` 删除；active source scan 零命中；无 compatibility alias | CLOSED |
| CV-F02 | `list_documents` 无 citation → `get_document_sections` 作为 citation producer；smoke round specs 确认 grounding 顺序；Fins owner files no-diff | CLOSED |
| CV-F03 | `_expected_required_tool_calls` 构造五个 typed expected calls；`_validate_required_request_atoms` 校验 exactly-once、exact arguments；`_forbidden_awaiting_duplicate_fields` 拒绝全部 arguments/digest 副本；`_validate_tool_awaiting_payload_contract` 校验 strict request link | CLOSED |
| CV-F04 | `_workspace_retention_summary` 恒定 `WORKSPACE_KEPT true ... cleanup=never`；assembly test 逐参数验证 | CLOSED |
| CV-F05 | `fins-list` round 只传 `{"ticker": fins_ticker}`；`fins-read` prompt 自足携带 "只有当上一轮同 ticker...确实包含...才执行"、"本轮必须停止且不得调用工具"、"禁止猜测"；Fins/config owner no-diff | CLOSED |

### V12: Aggregate 外部 smoke 未运行/未 PASS

在全部 artifacts 中均明确记录：
- AgentCodex fix record §4.2："§12 aggregate 外部 public-run smoke 特别地没有运行，也没有被标记为 skip 或 PASS"
- Controller fix validation §4："accepted plan §12 的真实 provider/Web/Fins public-run smoke仍未运行、未标 skip/PASS，继续作为 R03 aggregate hard gate"
- 初始 DS review Residual Risk §1："Aggregate 外部 public-run smoke 未执行"
- 初始 MiMo review Residual Risk："§12 aggregate 真实外部 public-run smoke未运行、未标 PASS"

### V13: 安全与 deferred scope

- 安全机制保留：Doc `allowed_paths`、Web 网络防御、path containment、symlink 防护、DNS/peer/resource budget、atomic write、process fencing、Host durable integrity checks — 均未被本 slice 修改
- 未偷带：Issue 177、Issue 178、Fins Docling isolation Issue 175、Issue 142/151、真实 Web/WeChat/render tracker、统一 tool authorization、BusinessSource abstraction — 在八个 production files 中零命中

---

## Findings

### 未发现实质性问题

经过对完整 `44e68550..worktree` S3 组合行为的逐文件、逐路径独立 re-review，包括：

1. **26 protected target digest 独立复现**：25 个非 control-doc 文件 SHA-256 与 AgentCodex record 完全一致；唯一漂移的 `issues-implementation-control.md` 是 Controller 新增 fix validation 更新 control gate 的预期行为。

2. **Zero-change fix record 真实性**：AgentCodex 未修改任何 production/test/README/smoke/plan/design/control/既有 artifact；其 before/after digest 与 Controller 独立复算一致，AgentDS 第三次独立复算再次确认。

3. **Semantic owner 边界**：`_explicit_citation` 通过精确 JSONPath `kind==completed → result.ok==True → value.citation` 识别 producer-owned citation；Host 不枚举 key、不猜测 ref kind/id、不新增 BusinessSource abstraction。

4. **Opaque refs internal-only**：`OpaqueEvidenceRef` 已从 `AcceptedToolResultProjection` 的公共 contract 移除，仅由 `AcceptedEvidenceEnvelope` 保留用于 EventLog/audit/internal provenance round-trip。五个 consumer production files 中 `OpaqueEvidenceRef` 零命中。Sentinel 注入测试证明 envelope round-trip 保留 opaque refs 但四消费者 LLM-facing 文本均不可见。

5. **四消费者 strict typed material/no fallback**：RunInput、Memory、Compact Material、Compact Pipeline、Tool Trace 共八条路径在 `llm_material`/`accepted_tool_evidence` 缺失时统一 fail closed（`HostDurableError` 或 `ValueError`）。无 skip、fallback、limited signal 或 consumer-specific recovery。

6. **Tool Trace strict canonical request atoms**：Request 分支使用 `read_event_by_id` + strict `tool_call_request_atoms` 恢复 bounded exact args/query；Result 分支使用 `project_accepted_tool_result` shared projection。缺失、错类型、storage/digest mismatch 均 fail closed。`business_source_text/state` 从 shared projection 映射。

7. **Explicit citation 唯一 readable business source**：`_source_projection` 直接消费 digest-checked `raw_outcome`，不依赖 envelope。缺失、拼错 `citaiton`、非 object citation 均输出同一中性文案 `该工具结果未提供业务来源。`。

8. **CV-F01..F05 闭合**：五个 finding 均有直接代码证据支持闭合，无回归。

9. **Fins grounding/read contract**：smoke 执行链为 `list_documents`（`{"ticker": ...}`）→ `get_document_sections`（`{"ticker": ..., "document_id": ...}`）。read prompt 自足携带 "只有当上一轮同 ticker...确实包含...才执行" 和 "本轮必须停止且不得调用工具"/"禁止猜测"。

10. **TOOL_AWAITING no-copy/link**：`_forbidden_awaiting_duplicate_fields` 拒绝所有含 "arguments" 子串或等于 `normalized_arguments_digest` 的字段；`_validate_tool_awaiting_payload_contract` 通过 digest-checked payload 严格链接 selected awaiting request。

11. **Allowlist/no-diff/安全/deferred scope**：全部验证通过，无漂移。

---

## Open Questions

无。

---

## Residual Risk

1. **Aggregate 外部 public-run smoke 未运行**：`utils/smoke_host_public_r03_semantic_ownership.py` 脚本和 assembly guard tests 已交付并通过（17 passed），但 §12 要求的真实 Web/provider/Fins 外部环境 smoke 仍未运行。此 gate 继续作为 R03 aggregate hard gate，不阻塞 S3 slice review closure，但阻塞 R03 整体完成。

2. **单文件 coverage 有未覆盖行**：八个 production files 的 line coverage 在 85%–96% 之间，全部满足 accepted plan 的 `>=80%` gate；`evidence.py` branch coverage 91% 满足 `>=90%` gate。未覆盖行属于既有模块的 residual area，不是本 slice 新增的未测试路径。

3. **`AcceptedToolEvidenceLLMMaterial` non-empty text constraint**：`evidence.py` 的 `__post_init__` 要求四个字段均为非空文本。如果 producer citation 产生空 JSON object `{}`，`canonical_json_dumps({})` 返回 `"{}"`（非空字符串），会通过校验。这是正确的 mechanical rendering——Host 不解释 citation 内容，空 citation 是 producer 的决策。此行为与 accepted plan 一致，不构成 finding。

---

## Verdict

**PASS — 未发现实质性问题。初始 accepted finding 仍为 0。**

AgentDS 独立复现了 AgentCodex zero-change record 的全部 26-target path/content/status 三项 digest（除 Controller 预期更新的 control doc），确认 Controller 独立复现可信。Protected targets 中仅 `docs/host/issues-implementation-control.md` 发生预期内的 Controller fix validation 更新，其余 25 个 targets 无漂移。

R03-S3 的完整组合行为与 accepted plan §11/§12 一致：
- opaque refs 收敛于 internal provenance/audit owner
- explicit citation 是唯一 producer-owned readable business source
- 四消费者在 typed material 缺失时统一 fail closed
- Tool Trace request/result 使用 strict canonical atom resolver
- CV-F01..F05 全部闭合
- Fins grounding/read contract、TOOL_AWAITING no-copy/link、allowlist/no-diff、安全/deferred scope 均验证通过
- aggregate 外部 smoke 仍未运行/未 PASS

本 re-review 不授权 R03-S3 accepted local commit；最终裁决权归 Controller。
