# P8.5 Plan Re-Review Artifact

- **review gate name**: plan re-review
- **reviewed target**: `docs/host/phase8.5-plan.md`
- **source review artifact**: `docs/host/phase8.5-plan-review.md`
- **source fix artifact**: `docs/host/phase8.5-plan-fix-report.md`
- **related source-of-truth docs**: `docs/host/design.md`, `docs/host/migration-plan.md`
- **work-unit name**: P8.5 - P8 Stabilization / ToolRuntime Event Model
- **artifact path**: `docs/host/phase8.5-plan-rereview.md`
- **reviewer conclusion**: **pass**

## Scope

本轮只 re-review P8.5 re-plan review F01-F07 的修复状态，以及 controller payload policy
correction 是否一致写入 plan / design / migration 文档。不修改 plan、生产代码、测试代码，不进入
implementation、commit、PR 或 closeout。

## Summary

- F01-F07 均已修复到 handoff-ready 水平。
- 未发现 blocker 或 high-risk plan gap。
- Blocking open questions: none.
- Findings: 0.

## Per-Finding Verification

### F01 - framework `fetch_more` schema 自动投影路径不够 handoff-ready

- **原始问题**: plan 未裁决 Host 私有 `fetch_more` schema 如何自动投影到 Engine-visible schemas，也未写清
  owner、call path、`RunOptions` mutation 边界和 RunInput context fact 应记录哪组 schemas。
- **修复证据**:
  - `docs/host/phase8.5-plan.md:122-136` 明确 schema 投影 owner 是 Host runtime assembly，不是
    Engine 或调用方；推荐 Host-private provider；在构造 `AgentRunRequest` 前生成 enhanced schemas；
    `StartRunRequest.options.tool_schemas` / `RunOptions` 不做 in-place mutation；`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`
    记录 Engine 实际收到的 enhanced schemas。
  - `docs/host/phase8.5-plan.md:391-399` 在 Slice 1 implementation instructions 中给出 provider /
    `_run_harness.py` / `_worker.py` / durable assembly 的 call path 和测试目标。
  - `docs/host/phase8.5-plan.md:263-266` 将 schema provider、`_worker.py`、`_run_harness.py`、
    `_durable_harness.py` 纳入 affected files。
- **re-review 判断**: fixed。该项已足够交给 implementation agent，不需要其重新决定 owner 或 public
  mutation 策略。

### F02 - memory / RunInput capability boundary 未定义

- **原始问题**: EventLog / trace 保留 cursor、`scope_token` 后，plan 未写清 Conversation Memory /
  RunInput 如何避免跨 run 复用短期 capability。
- **修复证据**:
  - `docs/host/phase8.5-plan.md:138-148` 明确 EventLog / trace ordinary payload 默认保留，但
    Conversation Memory / RunInput 是独立 ingestion policy；raw cursor、raw `scope_token`、
    `truncation.fetch_more_args` 只可生成不可复用摘要，不进入长期 memory 或下一轮 RunInput。
  - `docs/host/phase8.5-plan.md:406-417` 要求 `_conversation_memory.py` 摘要化短期 capability，并测试
    EventLog / trace 可见 raw payload，但 memory snapshot / RunInput rendered tool facts 不包含 raw
    cursor / raw `scope_token`。
  - `docs/host/migration-plan.md:46-49` 将同一长期口径写入 migration registry。
- **re-review 判断**: fixed。plan 已区分 credential scrub 与 memory ingestion policy，不再把
  local-agent payload retention 误扩展为长期 capability retention。

### F03 - `ToolTruncationInfo` shared contract impact 未纳入

- **原始问题**: 新 payload policy 改变了 shared tool result contract 语义，但 plan 漏列
  `dayu/contracts/tool_result.py` 和 contract-level tests。
- **修复证据**:
  - `docs/host/phase8.5-plan.md:268-270`、`:307-309` 将 shared contract 文件和 contract tests 纳入
    affected files。
  - `docs/host/phase8.5-plan.md:331-337` 明确 `ToolTruncationInfo` 是 ordinary LLM-facing tool result
    payload，可进入 EventLog / trace，但不得进入 memory、下一轮 RunInput、普通日志或 README 大块输出。
  - `docs/host/phase8.5-plan.md:401-402` 要求 Slice 1 更新 `ToolTruncationInfo` 文档并加 contract-level
    test。
- **re-review 判断**: fixed。shared contract 与测试影响已纳入 plan。

### F04 - RunInput raw payload side store schema / API / transaction ownership 未定义

- **原始问题**: raw payload side store 的表、字段、key、索引、writer/reader API、transaction ownership 和
  missing/corrupt 行语义留给 implementation agent 设计。
- **修复证据**:
  - `docs/host/phase8.5-plan.md:180-198` 固定 `run_input_raw_payloads` schema、allowed
    `payload_kind`、unique key、索引、writer owner、reader owner、同事务要求和 typed projection failure。
  - `docs/host/phase8.5-plan.md:342-348` 在 schema/index impact 中重复固定 schema。
  - `docs/host/phase8.5-plan.md:596-617` 在 Slice 4 写清 side-store API 形状、reader 校验、
    `RunInputContextSnapshotBuiltData` 删除 inline raw 字段并保存 blob id / hash / byte size。
  - `docs/host/phase8.5-plan.md:637-641` 要求验证 rollback 无 orphan row、blob hash/size 校验、
    missing/hash mismatch/corrupt JSON 导致 typed projection failure 且 checkpoint 不推进。
- **re-review 判断**: fixed。schema/API/事务边界已经足够具体；实现若无法同事务提交有 stop condition。

### F05 - design / migration 旧事实冲突

- **原始问题**: `design.md` 仍残留旧专属 fact / observer 同事务口径，可能和 re-plan 的 current design 冲突。
- **修复证据**:
  - `docs/host/phase8.5-plan.md:11-13` 明确 `docs/host/design.md` §11 与本 plan supersede 旧 P2/P7/P8
    wording。
  - `docs/host/design.md:1092-1113` 将 cursor store 归属收敛到 Host 私有 `RuntimeTruncateManager`。
  - `docs/host/design.md:1121-1156` 明确 Engine 不看 `ToolDefinition` / callable / manager，Runtime
    通过闭包注入 manager Protocol，Runtime 不构造或消费 `ToolFetchMore*`。
  - `docs/host/design.md:1180-1195` 明确 EventLog 只看到普通 tool calling，不新增 cursor /
    truncation / `fetch_more` 专属 RunEventType。
  - `docs/host/migration-plan.md:71`、`:89` 已把 P8.5 phase 边界更新为 generic tool calling /
    Host-private `fetch_more` / `RuntimeTruncateManager` 口径。
- **re-review 判断**: fixed。旧事实已通过 priority statement 和 design current section 收敛；Slice 6 仍保留
  docs closeout，但不阻塞 implementation handoff。

### F06 - trace observer at-least-once / checkpoint / duplicate idempotency semantics 不明确

- **原始问题**: plan 只说把 I/O 移出 transaction，未裁决 checkpoint crash window、重复 JSONL 行、
  failure status 和 required/non-required observer 分离语义。
- **修复证据**:
  - `docs/host/phase8.5-plan.md:167-173` 明确 non-required trace JSONL/blob sink 是 at-least-once；
    sink success 后 checkpoint 前 crash 或 checkpoint failure 允许 replay duplicate；reader/analyzer
    按 `idempotency_key` 去重；sink failure 不推进 checkpoint；checkpoint failure 不得报告 success；
    non-required trace failure 不阻塞 required memory observer。
  - `docs/host/phase8.5-plan.md:537-547` 在 Slice 3 implementation instructions 中重复这些状态机规则。
  - `docs/host/phase8.5-plan.md:558-562` 写入 expected assertions。
- **re-review 判断**: fixed。at-least-once 与 checkpoint 语义已可测试、可 review。

### F07 - grep guard 未区分 production/current docs 与 historical docs

- **原始问题**: grep guard 可能被 migration/review 历史上下文命中，导致 implementation agent 为了零命中删除审计上下文。
- **修复证据**:
  - `docs/host/phase8.5-plan.md:418-419` 对 Slice 1 生产代码 guard 写明生产代码不得命中，negative
    forbidden-name tests 可命中但必须注释。
  - `docs/host/phase8.5-plan.md:782-791` 在 Slice 6 validation 中拆分 production/current-doc guard
    与 historical-doc audit guard，明确 migration plan、旧 review artifacts、本 plan 可作为历史 /
    residual context 命中旧名字。
- **re-review 判断**: fixed。guard 的 expected-result 语义清楚。

## Payload Policy Consistency

- `docs/host/phase8.5-plan.md:31-33`、`:68-69`、`:88-89`、`:351-354` 均写明 EventLog / trace
  ordinary payload 默认保留，只 scrub `API_KEY` / explicit credentials，不因 cursor、`scope_token`、
  tool args/result 字段名 redaction。
- `docs/host/design.md:1173-1188` 写明 `scope_token` / cursor 可短期进入 LLM roundtrip 与 EventLog /
  trace 诊断，但不得进入 memory projection、普通日志或文档 / smoke 大块输出。
- `docs/host/migration-plan.md:46-49` 已把该政策写入长期 migration registry。

re-review 判断：policy 一致。唯一保留的是 plan §11 的 non-blocking watch item：implementation agent 不得把
普通业务字段、cursor、`scope_token`、tool args/result 扩大解释为 credentials。该 watch item 不阻塞 plan
handoff。

## Open Questions And Residual Risk

- Blocking open questions: none.
- Non-blocking watch item: credential scrub 只能窄定义为 `API_KEY` / explicit credentials；如果发现新的明确
  credential 字段，implementation slice report 必须列直接证据并补测试。
- Deferred-by-plan risks remain assigned to later slices / phases in `docs/host/phase8.5-plan.md:850-869`，
  including P15 observer hard-gate / watchdog and P16 public/internal interface freeze。

## Conclusion

F01-F07 均已修复。未发现 blocker、高风险 plan gap 或未收敛的 blocking open question。

**re-review 结论：pass**。plan 可进入 user confirmation gate；按 Gateflow，仍需用户确认后才能创建新的
accepted plan commit 并进入 implementation。
