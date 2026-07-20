# WU-SEMANTIC-OWNERSHIP-01 R03-S3 Controller Validation

## 1. 结论

- verdict：`PASS / READY_FOR_DUAL_CODE_REVIEW`
- work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R03 remediation sub-WU、Slice S3；不是新 WU。
- baseline：`44e68550ed226a3a207a73bd257478ab1bbbdce4`
- implementation artifact：`docs/reviews/wu-semantic-ownership-01-r03-s3-implementation-codex.md`
- aggregate R03 外部 public-run smoke：**未运行、未标记 PASS**；它仍是 accepted plan §12 的 aggregate hard gate，不由本 slice 的 deterministic assembly tests 替代。

Controller 对完整 S3 diff、accepted plan §11/§12、Fins producer-owned tool contract、测试、覆盖率、类型检查、lint、allowlist、no-diff owner 和传播扫描进行了独立复核。当前没有阻止双路 code review 的 accepted validation finding。

## 2. 动机与 root cause / owner 裁决

问题真实存在，且不是展示层文本问题：旧实现把 EventLog envelope 中的 opaque provenance ref 当作可读业务来源，并让 RunInput、Memory、Compact、Tool Trace 各自承担降级或重建语义。opaque ref 的唯一 owner 是 internal provenance/audit；LLM-readable 业务来源的 owner 是 accepted tool result 中 producer 明确产生的 `citation`，Host shared projection 只机械投影该对象。

修复位于正确 owner boundary：

- `accepted_result_projection.py` 只从 canonical completed-success outcome 的 exact `result.value.citation` object 产生共享 source projection，不枚举 citation keys，不猜测 ref kind/id；
- `evidence.py` 的 renderer 只消费 required typed material，不拥有缺失 material 的 fallback；
- RunInput、Memory、Compact、LLM-ready Tool Trace 在 canonical accepted-result material 缺失时统一 fail closed 为 `HostDurableError`；
- Tool Trace 的 request readable view 通过真实 EventLog row 与 `tool_call_request_atoms` 读取 exact canonical arguments/query，内部 digest/ref 仅用于 integrity/audit；
- EventLog envelope 与 internal provenance 仍原样保留 opaque refs，没有删除 durable/audit 真源。

因此本实现没有新增 speculative `BusinessSource` abstraction、字段名 blacklist、LLM-safe normalization、consumer fallback 或兼容分支。

## 3. 范围与边界复核

实际 production/test/README/smoke diff 全部位于 accepted plan §11.2 allowlist；新增文件仅为 S3 implementation artifact、assembly test 与 `utils/` public-run smoke。以下明确 owner 相对 baseline 均为 no-diff：

- `dayu/host/compaction.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/domain/tool_models.py`

Controller 还复核了 Fins producer contract 真源无改动：

- `dayu/fins/tools/fins_tools.py`
- `dayu/config/prompts/base/tools.md`

Issue 177、Issue 178、统一 tool authorization、Fins storage/citation schema 和后续 R03 aggregate 行为均未偷带进本 slice。

## 4. Controller validation findings

| ID | 直接证据与裁决 | 最终状态 |
|---|---|---|
| `R03-S3-CV-F01` | `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 仅为 strict atom 之后无 owner/消费者的旧 query fallback。接受删除该常量/export；active `dayu tests utils` 中符号和旧文案零命中，历史 review 记录不属于 active consumer。 | `CLOSED` |
| `R03-S3-CV-F02` | `list_documents` 的结果没有 citation，不能冒充显式业务来源。接受保留真正返回 citation 的 `get_document_sections` 作为 read producer。 | `CLOSED` |
| `R03-S3-CV-F03` | 初版 smoke 只重算 observed digest，未对照 typed expected arguments，也未读取 `TOOL_AWAITING`。接受补齐五个 required request 的 exactly-once、exact arguments、normalized/payload digest 同源校验，以及 awaiting strict link/no-copy 校验。 | `CLOSED` |
| `R03-S3-CV-F04` | smoke 从不删除 workspace，却曾可能输出 `WORKSPACE_KEPT=false`。接受把事实收敛为恒定 `kept=true, cleanup=never`，flag 只记录 caller request。 | `CLOSED` |
| `R03-S3-CV-F05` | Fins tool schema 与 base prompt 明确要求 `document_id` 先来自同 ticker `list_documents.documents[].document_id`。直接 read 会绕过 producer-owned LLM contract。接受新增独立 `fins-list` public round，随后 `fins-read` 仅在上一轮同 ticker 确实包含调用方 ID 时调用，否则 stop/no-guess。两个 round 的 exact tool set、顺序与参数都有 assembly guard。 | `CLOSED` |

## 5. 关键传播证据

- 同一 accepted result envelope codec round-trip 后仍保留 typo/internal/opaque sentinel refs，证明 internal provenance 未被删除。
- shared projection、RunInput message、Memory selected evidence、Compact readable material、Tool Trace readable result 均不包含这些 refs；explicit citation object（包括未知 JSON member）在四消费者中 canonical text 同源。
- no citation、拼错 `citaiton`、非 object citation 均只得到中性文案 `该工具结果未提供业务来源。`，不退回 ref guess。
- 四个 consumer 对 `llm_material=None` corruption 均抛 `HostDurableError`，没有 skip、limited signal 或 consumer-specific recovery。
- Tool Trace request 的 inline/descriptor arguments/query 都由 strict canonical atom resolver 产生；missing/wrong-type/storage/digest mismatch fail closed，readable view 不显示 payload ref/digest placeholder。
- real smoke 执行链使用 `ConfigLoader -> ToolsDiscovery -> Service assembly -> open_host -> ensure_session -> submit_followup`，不使用 fake/scripted runner/tool、不手写 wait result；内部 read 只用于 public run 后的诊断验证。
- public smoke 的五个 required calls 是 `read_file`、`search_web`、selected Fins awaiting tool、`list_documents`、`get_document_sections`；Fins grounding/read 顺序与同 ticker/document-id 条件均有 deterministic guard。

## 6. Controller 独立验证

### 6.1 Accepted S3 matrix

```text
354 passed, 1 skipped, 3 warnings
```

skip 是既有 opt-in real compactor smoke；不是新增 R03 aggregate smoke 的 pass/skip 结果。

### 6.2 Propagation filter matrix

```text
261 passed, 63 deselected
```

### 6.3 Full Host regression

```text
1972 passed, 2 skipped, 5 deselected
```

该轮在 F05 前完成；F05 只修改新 `utils/` smoke、对应 assembly test 与 implementation artifact，不修改 production Host。F05 后 Controller 已重新执行完整 accepted S3 matrix，覆盖新 assembly guard。

### 6.4 Coverage

Controller 的 full Host per-file coverage 复核结果：

| production file | coverage |
|---|---:|
| `accepted_result_projection.py` | 96% |
| `compact_material.py` | 86% |
| `compact_pipeline.py` | 94% |
| `durable/memory.py` | 88% |
| `evidence.py` | 95% |
| `memory.py` | 92% |
| `run_input.py` | 90% |
| `tool_trace.py` | 89% |

八个修改 production files 均达到 `>=80%`。`evidence.py` 独立 branch coverage 为 `91%`（200 statements、12 miss、52 branches、10 partial），达到 accepted plan 对 renderer/source branch 的 `>=90%` gate。

### 6.5 Static / repository gates

```text
Ruff affected files: PASS
pyright dayu/ tests/ utils/: 0 errors, 0 warnings, 0 informations
git diff --check: PASS
allowlist scan: PASS
explicit no-diff owners: PASS
active dead-query/source propagation scans: PASS
```

README 触发已处理：`dayu/host/README.md` 与 `tests/README.md` 在 allowlist 内同步；本 slice 不改变最终用户入口、分层装配或其它 README 职责。

## 7. 安全与 deferred scope

本 slice 只移除 opaque ref 被误投影为业务来源的路径和下游展示 repair，不移除任何既有安全机制。Doc `allowed_paths`、Web 网络防御、path containment、symlink 防护、DNS/peer/resource budget、atomic write、process fencing 与 Host durable integrity checks 均保留。没有实现、设计或暗示统一 tool authorization framework。

Doc/Truncation Issue 177、Web storage-state lifecycle Issue 178、Fins Docling process isolation Issue 175，以及 Issue 142/151 和真实 Web/WeChat/render tracker 范围均未实施。

## 8. Gate 决定

R03-S3 可以进入 AgentMiMo / AgentDS 双路完整 code review。Reviewer 必须审查 `44e68550..worktree` 的完整 S3 组合行为、accepted plan §11/§12、`R03-S3-CV-F01..F05` 关闭证据、Fins grounding/read producer contract、strict failure/no-fallback、allowlist/no-diff/security/deferred scope。

该决定不接受 R03-S3 code、不授权 accepted local commit、不授权 R03 aggregate，也不关闭 R03 或 umbrella WU。所有 reviewer accepted findings 必须由 AgentCodex 修复并经双路 re-review 关闭后，才可接受本 slice。
