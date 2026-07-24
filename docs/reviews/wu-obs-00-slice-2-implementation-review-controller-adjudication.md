# WU-OBS-00 Slice 2 Implementation Review — Controller Adjudication

## 裁决

- Work Unit：`WU-OBS-00`
- Gate：Slice 2 implementation review
- Decision：`needs-fix`
- Blocking open questions：None

Review artifacts：

- AgentMiMo：`docs/reviews/code-review-20260724-141635.md`
- AgentDS：`docs/reviews/code-review-20260724-141643.md`

AgentMiMo 判定 `PASS`，0 actionable findings。AgentDS 未发现 correctness/stability 级缺陷，
提出 5 项低严重度 finding。Controller 接受 2 项、部分接受 1 项、拒绝 2 项；另将 DS 的两个
open questions 判为已由 accepted plan 裁决，不形成 blocking question。

## 接受项

### CTRL-S2-IMPL-01 — analysis module public surface 未由 owner 明确声明

- 来源：DS Finding 1
- Decision：`accepted`
- Owner：`dayu.host.tool_trace_analysis`

`dayu.host` root 已精确导出三个 Analyzer public functions，但实现模块自身没有 `__all__`，
导致 `build_tool_trace_analysis_report`、`load_tool_trace_analysis_input` 与 imported types
被 `import *` 视为模块公共表面。它不会改变当前 package root 行为，但会制造第二套、未声明的
module-level public contract。

修复要求：

- 在 `dayu/host/tool_trace_analysis.py` 定义精确 `__all__`，仅包含
  `analyze_tool_trace`、`render_tool_trace_analysis_markdown`、
  `tool_trace_analysis_report_to_json`；
- 在 owner-level test 断言 exact set，并断言内部 builder/loader 不在其中；
- 不增加 re-export wrapper、兼容 alias 或动态导出。

### CTRL-S2-IMPL-02 — resolved payload evidence kind 与 source path 真源不一致

- 来源：DS Finding 2
- Decision：`accepted`
- Owner：Analyzer payload measure projection

`_public_payload_measure` 先按 `event_id` 命中 cold record 并构造 `COLD_LINE` evidence，之后对
所有非 `COLD_LINE` category 只把 `kind` 替换为 `RESOLVED_PAYLOAD`，保留 cold JSONL
`source_path`/`line_number`。这把“cold projection record 的直接位置”和“由 hot row +
descriptor resolver 验证的 payload byte measure”混成一个 evidence identity。

accepted plan 明确 cold record bytes 与 resolved payload bytes 是两个独立 measure，不能互相
覆盖。非 `COLD_LINE` measure 的 owner event 来自 hot snapshot，resolver 结果只携带
`event_id`/`event_sequence`/`payload_ref`/verified bytes，因此 evidence 必须引用 hot store
路径与 owner event/ref；不得借用同 event 的 cold line path/line number。

修复要求：

- `COLD_LINE` category 继续使用 cold record evidence 与
  `cold_jsonl_record_bytes`；
- 其它 category 始终构造 `RESOLVED_PAYLOAD` evidence，`source_path` 指向 hot DB，
  `line_number=None`，保留 verified measure 的 event/ref/size facts；
- 若内部 synthetic dataset 违反“resolved measure 必须有 hot store path”不变量，应在正确
  internal boundary 严格拒绝或在 test fixture 补齐真实 owner facts，不得 fallback 到 cold
  path/requested path；
- 新增反例测试：同一个 `event_id` 同时存在 cold record 与 non-cold resolved measure 时，二者
  的 evidence kind/path/measurement_source 仍严格分离。

### CTRL-S2-IMPL-03 — hot-only `cold_lock_path` 文档承诺漂移

- 来源：DS Finding 3
- Decision：`partially-accepted`
- Owner：`ToolTraceAnalysisInputSummary` contract documentation

accepted plan 已冻结：report 始终投影 Host owner 从 expected `cold_jsonl_path` 唯一派生的单数
`cold_lock_path`；hot-only 模式不把字段改为 nullable，也不改变 S2 冻结 schema。因此拒绝将
字段改成 `Path | None`。

但当前 docstring 写成“内部派生并实际使用的 lock path”，在 hot-only 路径上不成立：input
loader 明确不创建 marker、不 acquire cold lock。接受的最小修复是把 contract/renderer
LLM-readable 文案澄清为“Host owner 唯一派生的 expected lock path；只有
`capabilities.cold=true` 才表示本次实际获取该路径的锁并读取 cold snapshot”。测试必须断言
hot-only 时 path 仍稳定派生且 `capabilities.cold=false`，不能让消费者用 path 非空反推锁已
获取。

## 拒绝项

### DS Finding 4 — Markdown section tuple index coupling

- Decision：`rejected`
- Reason：当前固定 tuple 和固定调用点共同构成 deterministic renderer；所有索引均与冻结章节
  顺序一致，测试覆盖标题/顺序。review 未提供当前行为错误或语义分叉，只是假设未来有人错误
  插入 tuple。改为 enum/命名常量不会关闭当前 correctness 风险，属于可选重构；本 review gate
  不扩大。

### DS Finding 5 — 跨模块使用 `_tool_trace_cold_lock_path`

- Decision：`rejected`
- Reason：accepted plan §7.3/§7.4 和 owner matrix 明确要求 producer 与 Analyzer reader 在
  Host 内复用 `dayu.host.tool_trace` projection owner 的同一个内部 helper，同时禁止从 Host
  root、Service 或 CLI 暴露。当前 package-internal import 正是已 review 并 accepted 的设计，
  不是封装漂移；提升为 public function 或移动到 report contracts 反而违反 plan。

## Open Questions / Residual Risk 裁决

- cross-run repeated request：accepted plan 明确只诊断“同一 run 内
  `tool_name + normalized_arguments_digest`”；不形成 open question。
- median 基准局限：是 accepted detection policy 的统计边界，不是实现缺陷。
- hot-only supplementation coverage：由现有 branch coverage 与后续 aggregate deepreview
  继续审计，不据此新增无直接反例的 finding。
- `_bounded_observed` 白名单：显式白名单是防止 raw payload/schema 漂移进入 report 的安全
  owner；未来 producer schema 变化应通过相应 WU 更新规则，不改成自动接受未知字段。
- reviewer 只运行部分 focused tests 得到 contracts 79% 不能覆盖 implementation artifact 的
  完整 focused coverage 证据；Controller/AgentCodex 完整矩阵结果为 contracts 85%。

## 下一步

只把 `CTRL-S2-IMPL-01`、`CTRL-S2-IMPL-02`、`CTRL-S2-IMPL-03` 派给 AgentCodex 做最小
review fix。修复后重跑 focused、full Host、targeted/full pyright 与逐文件 branch coverage，
更新 review-fix artifact；随后必须由 AgentMiMo / AgentDS 双路 re-review，不能直接 acceptance。
