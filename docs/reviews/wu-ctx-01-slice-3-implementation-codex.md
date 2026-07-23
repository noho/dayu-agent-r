# WU-CTX-01 Slice 3 Implementation

## 1. 状态与边界

- 状态：implementation complete，未 commit、未 push、未创建 PR。
- base：accepted Slice 2 protected commit `126e67ca`。
- 设计与计划：`docs/host/design.md` §25；
  `docs/reviews/wu-ctx-01-plan-codex.md` §5.4、§5.5、§6.5、§8.4、§9。
- `docs/host/issues-implementation-control.md` 在开始前已有 Controller-owned dirty
  内容；本实现未修改、覆盖或提交该文件。
- production 与 tests 变更严格限制在 §8.4 allowlist。README 只修改 Host 与 tests
  的职责内内容；Service README 已审计但无需修改。本 implementation artifact 是用户
  明确要求的固定交付文件。
- 未修改 `context_fallback.py` 或 `compaction_operation.py`：现有
  dispatch / Engine ingest orchestration 已是对应 stage owner，机械修改不会增加
  合法语义。

## 2. 动机判断与 owner 结论

动机成立。Slice 2 已拥有完整 conservative candidate estimator、五阶段 action
matrix、canonical budget fact 与七字段 public projection，但缺少一个能从 durable
事实严格证明 compatible usage anchor 的 Host owner。若在 dispatch、Service 或展示层
从 display text、raw usage 或部分 candidate fields 临时推断，会同时破坏：

- manifest / iteration / usage / completion 的直接 lineage 证明；
- 同一 transaction snapshot 内的确定性；
- startup replay、steer、wait resume 与 Engine continuation 的同源 sizing；
- malformed / ambiguous / incomplete facts 的 fail-closed barrier；
- public fact 与内部 diagnostic 的所有权隔离。

本 slice 的唯一 owner 分工如下：

- `dayu/host/context_anchor.py`：Host-private typed anchor query/result、reverse keyset
  scan、strict lineage conjunction、barrier 与 compatibility 的唯一 owner。
- `dayu/host/_runner_call_manifest.py`：current Runner input serializer schema version
  的共享 strict validator；manifest consumer 不各自复制版本规则。
- `dayu/host/run_input.py`：从同一 frozen
  `PreparedRunnerCallCandidate` 构造 anchor query，并在调用方 transaction 中调用
  resolver 的唯一 projection helper。
- `dayu/host/context_budget.py`：完整 candidate conservative estimate、signed-delta
  公式、range validation、stage pressure/action 与 anchor diagnostic 的唯一 sizing
  owner。
- `dayu/host/context_events.py`：canonical fact schema、strict parse、deterministic
  identity 与 source fact load owner；只序列化同一个 `ContextSizingResult`。
- `dispatch.py`、`engine_ingest.py`、`admission.py`、`waiting.py`：各自生命周期中
  new candidate 的 transaction-local integration owner。
- `recovery.py`：startup exact replay owner；只复用 source sizing/fact atoms，再绑定
  新 candidate cursor 与新 fact identity，不重新解析 anchor。

Host public projector与Service七字段 DTO owner未改变，anchor diagnostic 不进入 public
contract。

## 3. Anchor resolver contract

`context_anchor.py` 新增 frozen typed `ContextAnchorQuery`、
`CompatibleContextAnchor` 与 `ContextAnchorResolution`。resolver 不打开 transaction、
不保存模块级 mutable state；调用方传入的 `HostTransaction` 同时拥有 candidate
freeze、manifest/fact append 与全部 anchor pages。

扫描使用固定 page size 的 reverse keyset，不设事件数量上限，并在 latest accepted
`CONTEXT_COMPACTED` 处停止。candidate 必须同时满足以下 conjunction：

1. strict complete v2 Runner-call manifest，且 hot payload、artifact descriptor、
   payload digest graph 与 serializer schema version 全部有效；
2. 唯一 accepted iteration link，且 run / attempt / execution / iteration / kind /
   trigger / message count / role digest / manifest ref / input digest 全部直接匹配；
3. 若有 usage，必须唯一、strict-valid，并与同一 manifest、link、input digest、
   normalized observation digest 成对；`prompt_tokens` 严格在合法范围；
4. 唯一 strict-valid accepted `ITERATION_COMPLETED` preview，finish reason 仅允许
   `stop`、`length`、`tool_calls`，并满足 manifest < link < usage < completion
   的 canonical 顺序；
5. provider、model、context window、estimator id/version 与 request semantics
   snapshot 全部相容。

complete 且无 usage 的较新 call 可以继续向旧 compatible anchor 扫描；但任何
ambiguous、invalid、incomplete、pairing mismatch 或 lineage gap 都是 barrier，立即
closed fallback，禁止越过寻找更旧 anchor。Run terminal 状态不能代替 iteration
completion。compactor manifest 不可成为 anchor。

`supports_stream_usage` 只属于 request semantics compatibility；usage presence 只由
strict paired usage fact证明。因此测试覆盖：

- `supports_stream_usage=False + actual usage` 可以成为 anchor；
- `supports_stream_usage=True + no usage` 无 anchor，但 Run 使用完整 conservative
  fallback，不因 provider 缺 usage 失败。

## 4. Adaptive sizing 与 fallback

`context_budget.py` 是公式唯一 owner：

```text
signed_delta = E_current - E_anchor
P = U_anchor + signed_delta
```

negative delta 不 clamp。所有输入、差值与结果都执行 strict integer/range validation。
公式得到非正值、overflow，或 usage / anchor 不可用时，结果无失败地退回同一次完整
candidate estimator 的 `E_current`；没有 display-text、subset、tokenizer、remote
count、provider-name branch 或弱算法路径。

公式 owner tests 包括：

- `U=6200,Ea=6000,Ec=6500 => P=6700`；
- `U=6200,Ea=7000,Ec=6000 => P=5200`；
- `window=10000,soft=6500,U=6200,Ea=6000,Ec=6300` 在 ordinary dispatch 前得到
  soft compact；
- non-positive 与 overflow 结果精确 fallback 到 `E_current`。

`ContextAnchorDiagnostic` 只属于 internal canonical fact；nullable fallback reason 与
diagnostic 由同一个 `ContextSizingResult` 产生。Host public
`HostContextUsageView` 和 Service `EntrypointContextUsage` 仍严格只有七字段，不包含
anchor ref、usage、delta、stage、action 或 policy internal。

## 5. Stage integration、compact 与 replay

五阶段 enum 和 action matrix保持不变：

| stage | anchor 行为 | hard pressure action |
| --- | --- | --- |
| ordinary | 可解析 compatible anchor | 既有 terminal owner |
| post-compact | accepted compact immediate candidate 固定 conservative fallback | 既有 lifecycle |
| reactive-post-compact | 固定 conservative fallback，不解析旧 anchor | `ALLOW_DISPATCH` |
| dispatch-fallback | 可解析 compatible anchor | 既有 terminal owner |
| continuation | new candidate 可解析 compatible anchor | `ALLOW_DISPATCH` |

具体 producer 行为：

- ordinary、tier fallback：`dispatch.py` 在 candidate 所属 transaction 中解析。
- accepted proactive compact 与 `REACTIVE_POST_COMPACT`：强制
  `ACCEPTED_COMPACT_INVALIDATED` conservative fallback；即使 prediction 为 hard，
  recovery lifecycle 仍继续，真实 provider overflow 进入既有 Engine reactive owner。
- steer：`admission.py` 先用完整 conservative estimate 冻结 manifest sizing
  snapshot；manifest append 后以 pre-manifest cursor 对新 candidate 解析 anchor，
  fact 使用新的 manifest cursor。
- wait completed / cancelled resume：`waiting.py` 在 resolution transaction 中复用
  source policy/threshold atoms，对新 candidate 解析 anchor。failed/lost 路径不创建
  candidate。
- complete Engine continuation：`engine_ingest.py` 写 manifest 后，以
  `manifest_event_sequence - 1` 作为 scan cursor 排除当前未完成 manifest，再对 frozen
  continuation candidate 解析。limited / source unavailable 路径仍 closed fallback /
  no fact，不从当前 effective config 重建 source。
- startup exact replay：`recovery.py` 不调用 resolver；strict-load matching source
  fact，保留 source method、prediction、diagnostic、threshold 与 estimator atoms，
  再以 `CONTINUATION` stage 和新 manifest cursor 派生新 fact identity。

新 successful ordinary / continuation usage 与 accepted completion 提交后，后续
candidate 才可能刷新 anchor。

## 6. 变更文件

Production：

- 新增 `dayu/host/context_anchor.py`。
- 修改 `dayu/host/_runner_call_manifest.py`、`admission.py`、
  `context_budget.py`、`context_events.py`、`dispatch.py`、
  `engine_ingest.py`、`recovery.py`、`run_input.py`、`waiting.py`。

Tests：

- 新增 `tests/host/test_context_anchor.py`。
- 修改 `test_context_budget.py`、`test_context_budget_evaluated.py`、
  `test_dispatch_scheduler.py`、`test_engine_ingest_mapping.py`、
  `test_public_resolve_wait_resume.py`、`test_public_steer.py`、
  `test_recovery_scan.py`。

Docs：

- 修改 `dayu/host/README.md`、`tests/README.md`。
- 新增本 implementation artifact。

## 7. Owner-level test evidence

新增与更新测试直接覆盖 owner contract，而非通过 mock 固化偶然调用：

- strict valid anchor、跨 page reverse keyset、跨多个 complete/no-usage calls；
- missing/mismatched/duplicate link、duplicate usage/completion、invalid usage、
  missing completion、ineligible finish reason 等 barrier；
- provider、model、window、estimator id/version、request semantics 的逐维反例；
- accepted compact invalidation 与之后的新 anchor refresh；
- signed positive/negative delta、soft threshold crossing、non-positive/overflow
  fallback；
- dispatch ordinary/fallback、reactive accepted compact、complete Engine
  continuation、steer、wait resume、startup anchored source replay；
- fact strict round-trip、new replay identity 与 public七字段 secrecy；
- OpenAI stream/non-stream usage presence 与 capability gating 回归。

## 8. README audit

- `dayu/host/README.md`：按其稳定 contract 写作边界，更新 durable anchor
  conjunction、barrier、compatibility、signed delta、compact invalidation、startup
  replay 与 `supports_stream_usage` 语义。
- `tests/README.md`：更新 focused owner 入口和本 slice 的 lineage/formula/replay/
  public separation 覆盖说明。
- `dayu/service/README.md`：已完整审计。现有内容已明确七字段逐字段复制、不读取
  Host durable state、不重算，因此无需机械修改。
- 根 `README.md` 与 `dayu/README.md`：没有安装、CLI、最终用户工作流、分层或装配
  变化，不命中职责触发。

## 9. 验证记录

- §8.4 exact focused：
  `512 passed in 4.43s`。
- clean full Host：
  `2252 passed, 2 skipped, 6 deselected in 54.99s`。
- whole-WU affected suites（Host / Service / Engine / CLI）：
  `3619 passed, 9 skipped, 6 deselected in 99.98s`。
- 项目标准 suite：
  `5697 passed, 11 skipped, 6 deselected in 176.24s`。
- 独立 branch coverage run（full Host + §8.4 OpenAI usage tests）：
  `2269 passed, 2 skipped, 6 deselected in 64.55s`。
- 完整 pyright：
  `0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- pytest 的三条 warning 均来自已安装 `edgar` 包的 deprecated API，不属于本次
  production 或 tests。

changed production Python file branch coverage：

| file | branch coverage |
| --- | ---: |
| `dayu/host/_runner_call_manifest.py` | 85% |
| `dayu/host/admission.py` | 86% |
| `dayu/host/context_anchor.py` | 82% |
| `dayu/host/context_budget.py` | 83% |
| `dayu/host/context_events.py` | 84% |
| `dayu/host/dispatch.py` | 85% |
| `dayu/host/engine_ingest.py` | 85% |
| `dayu/host/recovery.py` | 84% |
| `dayu/host/run_input.py` | 82% |
| `dayu/host/waiting.py` | 83% |

每个文件均使用独立 coverage data 和 `--branch --fail-under=80` 单独检查。

## 10. §9.4 static/source audits

- 旧 `_estimate_usage_observation_input` 为零命中；`USER_INPUT_ACCEPTED display_text`
  命中仅是 Memory、current input continuity 与既有 validation owner，不存在 usage
  estimator。
- compact source boundary 仍只有 `compact_payload` raw owner、`memory` typed
  consumer，以及 `run_input` 的 current-input / raw-tail 去重；RunInput 未读取 raw
  `source_boundary_refs`。
- manifest v1、changed owner `hasattr/getattr`、Engine→Host import、旧 promotion
  symbols 均为零命中。
- Service durable 搜索唯一命中是 `dayu/service/README.md` 的禁止依赖说明；production
  为零命中。
- context contract、五 stage、continuation、manifest producer/consumer、
  dispatch pending 与 ordering grep 均命中预期 owner/tests/docs，并逐项对账。
- 所有 production `SessionContinuityView` construction site 都显式提供
  `source_refs`。
- `git diff --check` 通过。

## 11. 风险与未覆盖项

- 没有已知 correctness blocker，也没有触发 §8.4 stop condition。
- 本 slice 不实现 provider tokenizer、remote token count 或 dynamic ratio；这些不是
  当前 provider-neutral durable anchor contract 的组成部分。
- 没有新增 UI 展示；public 七字段 DTO 与现有通用 activity formatter保持不变。
- Issue #119 Tool Trace analyzer correlation 不在本 slice owner 边界内，未侵入。
- live provider 是否上报 usage 仍由 provider 行为决定；缺 usage 时本实现严格回退到
  Slice 2 的完整 conservative candidate estimator，Run 行为不会比当前算法更差。
