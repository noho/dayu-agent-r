# WU-SEMANTIC-OWNERSHIP-01 R03-S3 Final Code Re-Review (AgentMiMo)

## 1. Scope

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`
- slice：`R03-S3`（opaque refs internal-only propagation closure）
- gate：双路 final code re-review（不是新 WU）
- branch：`phaseflow/host-issues-control`
- baseline / HEAD：`44e68550ed226a3a207a73bd257478ab1bbbdce4`
- review date：2026-07-15
- output file：`docs/reviews/wu-semantic-ownership-01-r03-s3-code-rereview-mimo.md`
- included scope：`44e68550..worktree` 全部 S3 改动（8 production、7 test/smoke、3 docs）+ 全部 S3 review/validation/fix artifacts
- excluded scope：无

### 审查输入

已完整读取：

1. `AGENTS.md`（根项目指令）
2. `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` §11/§12
3. `docs/reviews/wu-semantic-ownership-01-r03-s3-implementation-codex.md`
4. `docs/reviews/wu-semantic-ownership-01-r03-s3-controller-validation.md`（含 CV-F01..F05）
5. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-mimo.md`（初始 MiMo review）
6. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-ds.md`（初始 DS review）
7. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-controller-adjudication.md`
8. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-fix-codex.md`（zero-change record）
9. `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-fix-controller-validation.md`
10. `docs/host/issues-implementation-control.md`
11. 全部 8 个 S3 production files（完整内容）
12. 完整 `git diff 44e68550..worktree`

---

## 2. 26-Target Protected Digest 验证

Controller validation 独立复现的 26-target 三重 digest：

| proof | fix-codex recorded | Controller independent | 本次 re-review 独立复现 | 结果 |
|---|---|---|---|---|
| path-set SHA-256 | `acb20b...84aa` | 同值 | `acb20b...84aa` | **PASS** |
| content SHA-256 | `fff589...5bfa` | 同值 | 见下方逐文件 | **25/26 PASS** |
| status/path SHA-256 | `e0c679...d481` | 同值 | 见下方 | **PASS** |

### 2.1 Per-file SHA-256 逐文件核验

以下 25 个文件 SHA-256 与 fix-codex §3.1 记录**完全一致**：

| 文件 | SHA-256 |
|---|---|
| `dayu/host/accepted_result_projection.py` | `ff2b22...9f3b` ✓ |
| `dayu/host/evidence.py` | `3738ee...5b40` ✓ |
| `dayu/host/run_input.py` | `9111e6...438d` ✓ |
| `dayu/host/memory.py` | `32c2a8...7f72` ✓ |
| `dayu/host/durable/memory.py` | `9423b7...7fce` ✓ |
| `dayu/host/compact_material.py` | `c8e1dd...2680` ✓ |
| `dayu/host/compact_pipeline.py` | `70cd1c...56e6` ✓ |
| `dayu/host/tool_trace.py` | `9a9b15...1569` ✓ |
| `tests/host/test_accepted_result_projection.py` | `a4dbaa...d1b1` ✓ |
| `tests/host/test_run_input_builder.py` | `f4e90d...cab3` ✓ |
| `tests/host/test_memory_projection.py` | `c9915e...28f8` ✓ |
| `tests/host/test_compact_material.py` | `a82e2f...c267` ✓ |
| `tests/host/test_tool_trace_projection.py` | `236dde...4fbd` ✓ |
| `tests/host/test_tool_trace_queries.py` | `5897d4...a6eb` ✓ |
| `tests/host/test_public_compact_smoke.py` | `25768c...6b31` ✓ |
| `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py` | `3bd5eb...1ae6` ✓ |
| `utils/smoke_host_public_r03_semantic_ownership.py` | `516b75...07321` ✓ |
| `dayu/host/README.md` | `16e928...9846` ✓ |
| `tests/README.md` | `f3826a...f8bae` ✓ |
| accepted plan | `668d65...d178` ✓ |
| implementation codex | `5fabad...abc37c` ✓ |
| controller validation | `840e28...ca993` ✓ |
| initial MiMo review | `9d60a2...cb11` ✓ |
| initial DS review | `4b0332...eb84` ✓ |
| controller adjudication | `fa365b...264d` ✓ |

### 2.2 Controller 允许漂移：control doc

`docs/host/issues-implementation-control.md`：

- fix-codex 记录 SHA：`0ce1da456d138e24ba9e7614aaf0ffbbf321a6a5170778b2768a420c8509f7ff`
- 当前 SHA：`80d8fc1c5f93bcde133eff3f8dfeb7b60b8863d3fdec01d6a51c02d27e5073ab`
- diff：`5 insertions, 2 deletions`

变更内容为 Controller validation gate 更新（已由 `git diff` 独立验证）：

1. gate 字段从 `R03-S3 implementation` 更新为 `R03-S3 dual final code re-review`
2. next entry point 更新为引用 zero-change record 和 Controller validation artifacts
3. 新增 3 行状态记录（R03-S3 Controller validation、code review、zero-change fix）

这是 Controller 验证流程的**正常治理行为**，不是 implementation drift。所有 25 个 implementation/test/README/plan/review artifact 内容未变。

---

## 3. 初始 Accepted Finding 确认

| 来源 | finding 数 | 状态 |
|---|---|---|
| MiMo 初始 review | 0 material finding | ACCEPT |
| DS 初始 review | 0 material finding | PASS |
| Controller adjudication | accepted 0 / rejected 0 / deferred 0 | PASS |
| fix-codex zero-change record | 无代码变更 | ZERO_CHANGE_FIX_RECORDED |
| fix Controller validation | 无代码变更 | PASS |

**初始 accepted finding 仍为 0。**

---

## 4. Record 后变更确认

fix-codex artifact 创建后，唯一新增文件为：

- `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-fix-controller-validation.md`（Controller fix validation）

Controller 对 control doc 的 5 行变更为 gate 状态更新（§2.2）。**无 production/test/README/smoke/plan/design 变更。**

---

## 5. 关键语义闭合复核

### 5.1 语义 owner 收束

`accepted_result_projection.py:_source_projection`（L549-576）只从 digest-checked `raw_outcome` 的精确 JSONPath `kind==completed -> result.ok==True -> value.citation` 读取 producer-owned 显式 citation object。`_explicit_citation`（L579-598）严格 shape 校验，不枚举 key、不猜测 ref_kind、不 fallback。

旧符号 `_INTERNAL_SOURCE_REF_KINDS`、`_READABLE_SOURCE_SEPARATOR`、`_readable_ref_text`、`ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`、`ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT` 在 `dayu/`、`tests/`、`utils/` active source 中**零命中**。

### 5.2 Opaque refs internal-only

`OpaqueEvidenceRef` 在五个 shared/consumer production 文件（`accepted_result_projection.py`、`run_input.py`、`memory.py`、`compact_material.py`、`tool_trace.py`）中**零命中**。`evidence.py` 是 internal envelope/ref codec owner，保留 `OpaqueEvidenceRef` 定义和 `AcceptedEvidenceEnvelope.source_refs`/`locator_refs` 字段用于 EventLog/audit round-trip；`PromptLocalProvenanceEntry`（`compaction.py`，no-diff owner）仍接受 `source_locator_refs` 用于 internal provenance。opaque refs 不进入 LLM-facing material。

### 5.3 四消费者 strict no-fallback

| 消费者 | 检查点 | 缺 material 行为 |
|---|---|---|
| RunInput | `run_input.py::_fallback_message_from_material_block` / `_memory_projection_event_from_row` | `HostDurableError` |
| Memory | `memory.py::_selected_evidence_text` / `durable/memory.py::_tool_result_memory_payload_view` | `HostDurableError` |
| Compact | `compact_material.py::_pack_evidence_blocks` / `compact_pipeline.py::_message_from_material_block` | `HostDurableError` |
| Tool Trace | `tool_trace.py::_canonical_trace_summary_signals` / `_tool_result_summary_from_projection` | `HostDurableError` |

四路径均无 skip、limited signal、consumer-specific recovery 或 fallback。`hasattr`/`getattr` 在 8 个 production 文件中**零命中**。

### 5.4 Tool Trace strict canonical request atom

`_canonical_trace_summary_signals`（L1055）→ `_tool_request_summary_from_row`（L1176）→ `tool_call_request_atoms`（L1190）通过真实 EventLog row + strict `EventClass.CANONICAL_FACT` 检查恢复 bounded exact args/query。missing row、wrong type/class、storage conflict、descriptor/digest corruption 在 summary 发布前 fail closed。readable result 携带 `business_source_text`/`business_source_state`，不暴露 `raw_outcome_digest`/`payload_ref`/`payload_digest`/`limited_signal`。

### 5.5 CV-F01..F05 关闭确认

| ID | 本次独立验证 | 状态 |
|---|---|---|
| F01 | `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 已从 `evidence.py` 删除；active source scan 零命中 | **CLOSED** |
| F02 | `list_documents` 无 citation；`get_document_sections` 作为 citation producer；Fins owner no-diff | **CLOSED** |
| F03 | 五个 required calls exactly-once、exact arguments、normalized/payload digest 同源；`TOOL_AWAITING` strict link/no-copy | **CLOSED** |
| F04 | `_workspace_retention_summary` 恒定 `WORKSPACE_KEPT true ... cleanup=never` | **CLOSED** |
| F05 | `fins-list` → `fins-read` grounding 顺序、同 ticker 条件、exact tool sets；Fins/config owner no-diff | **CLOSED** |

### 5.6 Fins 同 ticker grounding → get_document_sections

smoke 中 `fins-list` round 只传 `{"ticker": fins_ticker}`；`fins-read` prompt 自足携带前置验证条件（"只有当上一轮同 ticker...确实包含...才执行"）和 stop/no-guess 规则。assembly guard 验证两个 round 的 exact tool set、顺序与参数。Fins/config producer owner（`fins_tools.py`、`tools.md`）no-diff。

### 5.7 五个 exact calls

`_validate_required_request_atoms` 校验 `read_file`、`search_web`、selected Fins awaiting tool、`list_documents`、`get_document_sections` 的 exactly-once、exact arguments equality、normalized/payload digest 同源。

### 5.8 TOOL_AWAITING no-copy/link

`_validate_tool_awaiting_payload_contract` 通过 `event_payload_object` 读取 digest-checked payload，校验 strict request link，`_forbidden_awaiting_duplicate_fields` 拒绝所有含 `"arguments"` 子串或 `normalized_arguments_digest` 的字段。

### 5.9 Allowlist / no-diff

实际 diff 中 16 个 tracked implementation paths（8 production + 6 test + 2 README）全部在 §11.2 allowlist 内。`docs/host/issues-implementation-control.md` 不在 §11.2 implementation allowlist 中，其变更为 Controller-authorized governance gate 更新（§2.2）。6 个 no-diff owner 文件经 `git diff --exit-code 44e68550` 验证为零差异：

- `dayu/host/compaction.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/domain/tool_models.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/config/prompts/base/tools.md`

### 5.10 安全 / deferred scope

Doc `allowed_paths`、Web 网络防御、path containment、symlink 防护、DNS/peer/resource budget、atomic write、process fencing、Host durable integrity checks 均保留。Issue 177、178、175、142、151 和 Web/WeChat/render tracker 范围均未实施。未引入统一 tool authorization、BusinessSource abstraction 或 compatibility shim。

---

## 6. 独立测试与静态检查

```text
S3 核心测试套件：337 passed, 1 skipped（skip 为既有 opt-in real compactor smoke）
pyright 8 production files：0 errors, 0 warnings
git diff --check：PASS
```

---

## 7. Findings

未发现实质性问题。

本 re-review 对全部 8 个 production 文件做了完整内容走读（非仅 diff 抽样），覆盖：

- 语义 owner boundary 收束（§5.1）
- opaque refs internal-only 隔离（§5.2）
- 四消费者 strict typed material / no fallback（§5.3）
- Tool Trace strict canonical request atom（§5.4）
- CV-F01..F05 闭合证据（§5.5）
- Fins grounding/read producer contract（§5.6）
- allowlist / no-diff / 安全 / deferred scope（§5.9, §5.10）

所有验证点均有直接代码 evidence 或独立命令输出支撑。初始两路 review 零 finding、Controller adjudication 零 accepted finding、zero-change record 无代码变更、Controller fix validation 仅新增自身 artifact——整个 gate 链完整闭合。

---

## 8. Open Questions

无。

---

## 9. Residual Risk

- **§12 aggregate 外部 public-run smoke 未运行**：`utils/smoke_host_public_r03_semantic_ownership.py` 和 assembly guard 已交付，但真实 Web/provider/Fins 外部环境 smoke 尚未运行。这是 R03 aggregate hard gate，不阻塞 S3 slice re-review，但阻塞 R03 aggregate completion。不属于 S3 implementation 缺陷。

---

## 10. Verdict

**PASS — 未发现实质性问题。**

R03-S3 final code re-review 确认：

1. 26-target protected set 中 25 个 implementation/test/README/plan/review artifact SHA-256 完全未变；control doc 的 5 行变更为 Controller 正常治理更新。
2. 初始 accepted finding 仍为 0。
3. zero-change record 后仅 Controller 新增 fix validation artifact，无其它变更。
4. CV-F01..F05 全部 CLOSED。
5. Fins grounding/read、五个 exact calls、TOOL_AWAITING no-copy/link、四消费者 strict no-fallback、opaque ref internal-only、Tool Trace canonical atoms、allowlist/no-diff、安全/deferred scope 全部闭合。
6. aggregate 外部 smoke 未运行/未 PASS，继续作为 R03 aggregate hard gate。

S3 implementation 正确地将业务来源语义从 opaque envelope ref guessing 收束到 producer-owned explicit citation 的唯一 owner boundary。四消费者在 typed material 缺失时统一 fail closed，Tool Trace request 通过 strict canonical atom resolver 恢复 exact arguments/query。实现与 accepted plan §11/§12 一致，无偷带、无 compatibility shim、无 downstream repair。
