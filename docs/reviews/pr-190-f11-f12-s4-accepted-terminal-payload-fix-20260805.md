# PR 190 F11/F12 S4.2 accepted terminal payload fix

## 状态

- 日期：2026-08-05
- 分支：`codex/interactive-oracle`
- 基线 HEAD：`f7957b6343f4647ce0c6058a08e9ae84ab629f30`
- Implementation owner：AgentCodex
- Gateflow 状态：`FIX_APPLIED_AWAITING_DUAL_REREVIEW`
- 本轮未 commit、未 push、未调用 real provider、未调用 reviewer pane。
- 首轮 review artifacts：
  - `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-mimo-review-20260805.md`
  - `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-review-20260805.md`
- Controller 裁决：`docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-review-adjudication-20260805.md`
- Review fix artifact：`docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-f01-fix-20260805.md`

## 直接证据与定性

冻结证据：`/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-final-k5hWK9/screen/07-deepseek-replacement-retry.txt`。

该 bundle 只作为只读的 partial/superseded failure evidence，不作为通过证据，也未被修改。直接堆栈表明 DeepSeek candidate 已进入 accepted compact commit 路径，但 proactive writer 把完整 `CONTEXT_COMPACTED` canonical payload 全量写入 EventLog inline 字段；payload 超过 EventLog 当前 inline threshold 后由 durable invariant 抛出 `HostPayloadReferenceError`，进而使 promotion critical task fatal。

问题动机成立且是 production blocker：candidate 已被 accept，失败发生在 canonical terminal persistence owner boundary，导致成功 terminal、Memory catch-up 与后续 dispatch 都不能提交。EventLog limit 本身正确，它阻止大 canonical 内容绕过既有 payload descriptor/blob truth。

## 语义 owner 判定

- `context_events` 继续拥有完整 `CONTEXT_COMPACTED` canonical contract 的产生与校验。
- 新增 `dayu.host.context_event_payload`，唯一拥有该完整 contract 到 EventLog inline 或既有 payload descriptor/blob 的 durable 映射，以及反向严格解析。
- `EventLog` 继续只拥有 canonical inline size invariant，不提高 limit。
- compact artifact 继续拥有 accepted compact artifact truth；terminal payload 只引用它，并与 accepted terminal 的完整 canonical payload descriptor 分离。
- terminal permit、proactive reconstruction、projection、Conversation Memory、compact material、RunInputBuilder 与 public Tool Trace response identity 全部复用同一 resolver，不再从 hot `{}` 或 raw `payload_json` 各自解释 accepted terminal。

## 实现

1. `store_context_compacted_payload(...)` 先校验完整 canonical payload。阈值内保持原 inline 行为；超限时调用既有 `PayloadStore.write_bounded_json_payload(...)`，以 deterministic event-id-bound ref 写 descriptor/blob，并让 EventLog row 只保存 `{}`、`payload_ref` 与 exact digest。
2. proactive `dispatch._append_compacted_event` 与 reactive `engine_ingest._append_reactive_compacted_event` 共用该 writer owner；两路都预先确定 event id，再从同一完整 payload 生成存储计划。
3. `resolve_context_compacted_payload(...)` 严格校验 event class/type、ref/digest pairing、descriptor/blob bytes、digest、canonical JSON object 与完整 terminal contract；任一漂移 fail closed。
4. terminal permit、proactive durable projection、generic projection、compact material、RunInputBuilder 和 public Tool Trace compactor response resolver 改为消费该统一 resolver。
5. 未增加 inline limit，未删字段、截断、catch/fallback、兼容 shim 或下游特例；未修改 oracle、scenario、registry，也未修改 `dayu/host/context_events.py`。

## 首轮 review fix

- Controller 只接受 `DS-F01`。直接证据是 `DurableCompactArtifactProvider._load_compact_artifact_tx(...)` 已持有当前 read transaction，却仍从 `row.payload_json` 读取 hot object；descriptor-backed `CONTEXT_COMPACTED` 的 hot object 是 `{}`，strict semantic parser 因缺少 canonical 字段必然失败。
- 修复位于真实 consumer boundary：provider 在同一 read transaction 内调用 `resolve_context_compacted_payload(transaction, row)`；之后仍由 `parse_context_compacted_semantic_payload(...)` 恢复 typed semantics，并继续用现有 required field 读取 compact artifact digest。
- 新 owner test 使用 2048-byte inline threshold 写入真实 artifact-backed terminal，断言 descriptor kind、payload size、compaction event ref、compact artifact ref/digest 与 represented evidence refs；再篡改 EventLog terminal payload digest，断言 provider fail closed。
- `DS-F02` 至 `DS-F08` 均按 controller 裁决保持拒绝状态，生产代码和测试没有实现这些建议。

## Owner tests

- proactive oversized accepted compact：通过真实 background queue promotion 路径触发；断言只提交一个 `CONTEXT_COMPACTED` terminal，EventLog hot payload 为 `{}`，terminal descriptor 为 artifact-backed，digest 与完整 payload 精确一致。
- 同一 proactive test 独立读取 compact artifact bytes，并断言 artifact accepted candidate 与 terminal accepted candidate 同源。
- 同一 test 断言 Conversation Memory latest compaction ref 与 summary 已物化，public Tool Trace compactor response identity 可解析；篡改 terminal digest 后 public resolver fail closed。
- 同一 test 断言 Run 进入 `RUNNING`、promotion task 保持存活、health 为 `READY`，且无 `critical_task.fatal` 或 hang。
- reactive oversized accepted compact：断言 reactive writer 使用相同 descriptor truth，完整 payload 可严格解析，只提交一个 terminal，并只触发一次 recovery wake。
- 既有 inline accepted compact、terminal permit、Memory、RunInput、projection 与 Tool Trace tests 保持通过。

## 验证结果

- affected regression：`684 passed in 7.09s`
- coverage regression：`684 passed in 8.84s`
- 改动生产文件 coverage：总计 `86%`
  - `context_event_payload.py` 91%
  - `compact_material.py` 85%
  - `compaction_terminal.py` 85%
  - `dispatch.py` 82%
  - `durable/tool_trace.py` 87%
  - `engine_ingest.py` 89%
  - `proactive_compaction.py` 86%
  - `projection.py` 92%
  - `run_input.py` 85%
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`
- `python -m compileall -q dayu tests utils`：通过
- changed-file `ruff check`：通过
- `git diff --check`：通过
- `dayu/host/context_events.py`：零 diff
- oracle/scenario/registry：零 diff

DS-F01 review fix 追加验证：

- 定向 owner test：`1 passed in 0.44s`
- 完整 `tests/host/test_run_input_builder.py`：`103 passed in 1.00s`
- 受影响 regression：三组共 `798 passed`
  - changed-test modules：`472 passed in 5.28s`
  - compact material / terminal / proactive / memory / projection：`182 passed in 1.18s`
  - compact contract / pipeline / artifact / operation / memory repair：`144 passed in 0.48s`
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`
- changed-file `ruff check`：通过
- `python -m compileall -q dayu tests utils`：通过
- `git diff --check`：通过

## Scope hygiene

曾执行的全文件 `ruff format` 产生了与本 slice 无关的格式 churn；已逐文件通过 patch 恢复。最终只保留必要 import、transaction-aware resolver 签名/调用、两路 writer owner 改动、owner tests 与 README contract 更新。指定的 `test_proactive_compaction_skips_empty_citable_selection` 保持 HEAD 原有 context budget policy。

## 未完成 gate 与残余风险

- `DS-F01` fix 状态：`已修复`，等待 MiMo、DeepSeek 对完整 S4.2 diff 双路独立 re-review 后确认。
- `DS-F02` 至 `DS-F08`：`rejected-with-reason`；不是当前 slice 的 residual risk，不得在本轮实现。
- 按总控约束，本 implementation owner 不代替 AgentMiMo/AgentDS 做 review，也不调用 reviewer pane。下一 gate 是总控派发两路独立 `/deepreview`。
- frozen real-provider bundle 仍是 partial/superseded evidence。只有双路 review 及其 fix/re-review 收敛后，才允许重新执行 fresh real-provider observation；本轮没有发起任何 provider 调用。
- 当前无未分类 residual risk 或已知代码级 blocker；尚未宣称 final closeout pass，也未创建 commit/push。
