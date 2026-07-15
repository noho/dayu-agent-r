# WU-SEMANTIC-OWNERSHIP-01 / R03-S2 Code Review Controller Adjudication

## 0. Gate 与结论

| 项目 | 值 |
| --- | --- |
| umbrella / remediation / slice | `WU-SEMANTIC-OWNERSHIP-01 / R03 / R03-S2` |
| review baseline | `fe497da395e8511c684945b9282894fe322a90df` |
| MiMo artifact | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-mimo.md` |
| DS artifact | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-ds.md` |
| Controller validation | `docs/reviews/wu-semantic-ownership-01-r03-s2-controller-validation.md` |
| accepted code finding | `0` |
| blocking question | `0` |
| verdict | `PASS / ZERO-CHANGE RECORD REQUIRED` |

两路 reviewer 均确认 S2 的主要 owner contract、测试、coverage、pyright、README、安全保留与 deferred boundary 正确。AgentDS 返回零 finding；AgentMiMo 返回一个 `query_state` finding。Controller 依据 accepted plan 与当前调用链拒绝该 finding，不接受任何代码修复。

本结论不直接接受 R03-S2。按用户规定的 `code review -> AgentCodex fix -> dual re-review -> accepted local commit` 顺序，以及本 umbrella 已采用的零 finding 处理方式，下一 gate 是 AgentCodex 生成 mandatory zero-change fix/disposition artifact，再由 MiMo/DS 完整 final re-review。

## 1. Finding 裁决

### `S2-CR-F01` — rejected / no-fix

MiMo 主张 Tool Trace readable summary 的 `query_state` 泄漏 Host 内部投影状态，建议从两个 request-summary builder 删除。该 finding 不成立：

1. **事实前提不准确**：当前 `rg -n 'query_state' dayu/host/tool_trace.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py` 只有 `dayu/host/tool_trace.py::_tool_request_summary_from_tool_result` 一处 production 命中；`_tool_request_summary_from_payload` 当前没有该字段，两个测试文件也没有 reviewer 所称的多处 `query_state` 断言。
2. **accepted plan 明确保留该语义**：§4.7 规定 `trace_summary.tool_request` readable fields 包含 tool name、query、exact arguments/text 和“明确状态”；§4.6 固定 query 的两个合法来源为 producer `semantic_query_text` 或 canonical accepted arguments；§7.3 只删除 `LIMITED_SIGNAL` 与 blacklist/limited branch，没有删除 `AcceptedToolResultQueryState` 或其剩余 `semantic_query | arguments_summary` 来源状态。
3. **语义 owner 正确**：该值描述当前 readable query 文本来自 producer query 还是 accepted arguments summary，是 query projection 的 provenance，不是 Run、Attempt、wait、poll、dispatch、Engine 或 Host governance 状态，也没有被伪装成财报事实。
4. **建议修复会造成 contract drift**：无证据地删除该字段会削弱 accepted plan 要求的 readable query 来源状态，并在 S2 之外重定义 Tool Trace summary schema。若未来产品决定不展示 query provenance，需要先修改设计/accepted plan owner contract，不能由 code review 在本 gate 静默改写。

因此 `S2-CR-F01` 状态是 `rejected-with-direct-evidence / no-fix`。它不得进入 AgentCodex production/test/README 修改。

## 2. 其它 reviewer observations

| 观察 | Controller 裁决 |
| --- | --- |
| descriptor strict resolution、exact descriptor args/query | R03-S3 accepted owner；S2 不修、不建 loose resolver |
| opaque source guessing / refs propagation | R03-S3 accepted owner；不是 S2 finding |
| `business_source_text/state`、non-optional material | R03-S3 accepted owner；不是 S2 finding |
| Web default Ruff 14 项 | baseline observation；与 `fe497da3` 同源且零扩散，不作为本 WU residual，不创建新 owner/issue |
| DS extra full Host run 的 scheduler 单节点失败 | 非 S2 调用链；Controller 对同一 node 独立复跑 `1 passed`，不接受为 finding 或 residual |
| DS 关于当前 producer 不写 opaque refs 的可达性陈述 | 非裁决必要前提；S3 必须按 accepted propagation contract关闭，不能因当前可达性意见弱化 |
| reviewer “可进入 S3”措辞 | reviewer 无 gate authority；仍须 zero-change record、dual final re-review、Controller adjudication与 accepted local commit |

## 3. 已确认的 retained / deferred boundary

- Engine provider diagnostic、runtime diagnostic text、compaction diagnostic 的敏感值脱敏 owner保留且无 diff。
- Doc allowed paths、Fins filesystem containment、Web DNS/peer/budget/challenge、Host file lock 等安全边界未被删除。
- 没有新增 LLM-safe normalization、compatibility、BusinessSource、统一 authorization 或 Issue 177/178 实现。
- R03-S3 继续唯一拥有 opaque refs internal-only、explicit citation/source projection、四消费者 strict material、descriptor strict row resolution 与 Tool Trace source fields。
- aggregate 继续唯一拥有真实 public Doc/Web/Fins smoke。

## 4. 下一 gate

AgentCodex 必须只新增 `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-fix-codex.md`：记录 accepted finding 为零、`S2-CR-F01` 的 no-fix 裁决、protected target 内容/状态摘要与零产品修改证据。不得修改 production、tests、README、design、plan、control 或既有 artifacts。完成并经 Controller 验证后，MiMo/DS 必须对完整 final slice 并发 re-review；R03-S2 在 final re-review 与 Controller 接受前不得 commit 或进入 S3。
