# PR 190 F11/F12 S1/F11 Code Review Adjudication

## Gate identity

- Gate: S1/F11 implementation code review adjudication
- Base: `19a6d6257504876e01da3067bbc4cf33ae99525d`
- MiMo review: `docs/reviews/pr-190-f11-f12-s1-f11-code-review-mimo-20260805.md`
- DS review: `docs/reviews/pr-190-f11-f12-s1-f11-code-review-ds-20260805.md`
- Controller decision: `fix-required`（仅一项文档性 owner clarification）

两路 review 都是独立证据输入；以下逐项裁决，不以 reviewer 结论一致替代代码证据。

## MiMo findings

### M-001：matching operation/attempt 但 terminal 无 manifest binding

- 裁决：`rejected-as-non-finding`。
- 证据：`_resolved_compactor_response_from_row` 要求 operation/attempt 与 manifest
  ref/digest 同时匹配；同一 proposal attempt 若缺 manifest binding，canonical truth 已损坏。
- 理由：抛出 `CompactorResponseResolutionError` 是设计真源要求的 fail-closed，不是缺陷。
- 动作：无代码修改。

### M-002：analysis summary 缺 parent Host Run id 时抛错

- 裁决：`rejected-as-non-finding`。
- 证据：compactor response 查询由 manifest 中的 `parent_host_run_id` 定位 canonical terminal，
  analysis summary 若缺该 owner identity 不能诚实投影。
- 理由：跳过会把 identity corruption 伪装成没有 response；当前 fail-closed 正确。
- 动作：无代码修改。

### M-003：terminal scan page size 不可由调用方配置

- 裁决：`rejected-as-non-finding`。
- 证据：correctness 由完整 keyset exhaustion 拥有，page size 只限制单次 read I/O；允许调用方
  配置会扩大 public surface，accepted contract 未要求。
- 动作：无接口修改。

## DS findings

### DS-01：validator 与 typed parser 重复调用 strict identity parser

- 裁决：`rejected-as-non-finding`。
- 直接证据：两处都调用同一个公开 owner
  `parse_successful_runner_response_identity`，没有各自读取 raw fields，也没有第二套 schema 或
  semantic truth。
- 理由：validator 的 `None` return contract 负责验证完整 event payload；terminal binding parser
  在 validation 后构造 immutable typed value。为消除一次纯函数调用而让 validator 返回隐藏缓存值，
  会混合 validator/parser 职责并扩大接口，收益不足。
- 动作：无代码修改。

### DS-02：cursor 防御未显式逐行比较起始 cursor

- 裁决：`rejected-as-false-positive`。
- 直接证据：`previous_sequence` 在进入页内循环前初始化为 `cursor`；每一行都执行
  `row.event_sequence <= previous_sequence` 检查，随后才更新 `previous_sequence`。因此首行已
  显式保证 `> cursor`，后续行保证严格单调，逻辑上同时蕴含每行 `> cursor`。
- 理由：再增加 `row.event_sequence > cursor` 只会重复同一不变量，不提高防御性。
- 动作：无代码修改。

### DS-03：固定 page size 128 缺选择说明

- 裁决：`accepted-low-documentation`。
- 直接证据：常量已经命名并集中在 durable Tool Trace owner，不是散落业务分支；但代码未说明
  correctness 与该值无关、该值只界定单次 SQLite read I/O。
- Required fix：在常量 owner 处增加简短中文说明；不改数值、不开放配置、不更新 public surface。

## DS open questions

### OQ-01：failure category identity constraints 是否要变成完整 closed set

- 裁决：`not-blocking / no-change`。
- 理由：两个私有集合只约束已知必须 post-success 或必须 no-success 的类别，并不拥有完整 failure
  taxonomy。未列入集合的 category 是否有 response 由真实 Engine terminal 阶段决定；擅自闭集化会
  扩张 F11 产品语义。

### OQ-02：resolver corruption 向 Service/CLI 的呈现

- 裁决：`covered-by-later-integration-observation`。
- 理由：F11 owner contract 要求 mismatch fail closed，当前错误不会被降级为 missing limitation。
  operator-facing presentation 不是本 slice owner；S4 真实 evidence 会记录 formal CLI/API 行为。

## Residual risk classification

- `fixed-in-current-gate`：page-size owner comment。
- `covered-by-later-approved-slice`：真实 provider 的 successful/rejected Tool Trace evidence 与错误呈现，
  由 S4 拥有。
- `assigned-to-external-consumer-owner`：fresh Tool Trace analysis schema v2 的仓外 consumer 显式升级；
  不提供 compatibility reader。
- `not-a-risk`：validator/parser 使用同一 strict parser；cursor 逐行不变量；private page size 不可配置。

没有 blocking open question，也没有未分类 residual risk。

## Fix and re-review request

AgentCodex 只需在 `_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE` owner 处补充选择说明，重跑 Ruff、affected
pyright、focused owner tests 与 `git diff --check`，并更新 S1 implementation artifact 的 fix
记录。随后 MiMo、DS 分别 re-review：确认唯一 accepted finding 已关闭、rejected findings 未被误改、
没有新增 public config/compatibility path 或 semantic drift。
