# WU-OBS-00 Slice 2 Implementation — Controller Adjudication

## 裁决

- Work Unit：`WU-OBS-00`
- Gate：Slice 2 implementation
- Decision：`pass-to-review`
- Acceptance：尚未 accepted；必须完成 AgentMiMo / AgentDS 双路 code review、Controller
  adjudication、必要 fix 与 re-review。
- Blocking open questions：None

## 动机与语义 owner

Slice 1 已交付 trusted Tool Trace dataset 与严格只读 input boundary，但仓库当时没有
`analyze_tool_trace`、规则 owner 或 deterministic structured report。因此 Slice 2 的真实缺口
成立：Analyzer 应拥有聚合、finding、priority、recommendation、limitation 和 report
projection；EventLog / Tool Trace producer 与 typed input dataset 继续拥有 canonical facts。

本实现没有扩张 producer/schema，没有用 fallback、loose parsing、时间戳计算、arguments 文本
或偶然顺序反推业务事实。

## 实现范围

accepted plan 的 Slice 2 production / owner tests 已完成：

- `dayu/host/tool_trace_analysis_contracts.py`
- `dayu/host/tool_trace_analysis_rules.py`
- `dayu/host/tool_trace_analysis.py`
- `dayu/host/__init__.py`
- `tests/host/test_tool_trace_analysis_rules.py`
- `tests/host/test_tool_trace_analysis.py`

Controller 批准唯一 test-only scope exception：
`tests/host/test_package_exports.py`。它只同步 Slice 2 新 public exports 的 package owner
allowlist；不得把该例外解释为 production scope 扩张。

AgentCodex implementation artifact：
`docs/reviews/wu-obs-00-slice-2-implementation-codex.md`

## Implementation gate 内 needs-fix

AgentCodex 初次 completion 后独立审计发现并在同一 gate 内关闭以下 owner-level 缺口：

1. contracts 模块概览和模块 `__all__` 未随已冻结 public schema 更新；
2. public `ToolTraceFinding` 允许空 `finding_id`，把规则构建中间态泄漏到 public contract；
3. `ToolTraceAnalysisInputSummary` 与最终 report 缺少 owner-boundary invariant 校验。

最终实现使用私有 `_FindingDraft` 承载未分配 ID 的中间态，严格校验 public finding/report
contract，并补齐 owner-level regression tests。

## 验证

- focused：`47 passed`
- full Host：`2314 passed, 2 skipped, 6 deselected`
- targeted pyright：`0 errors, 0 warnings`
- full pyright：`0 errors, 0 warnings`
- branch coverage：
  - `dayu/host/__init__.py`：`100%`
  - `dayu/host/tool_trace_analysis_contracts.py`：`85%`
  - `dayu/host/tool_trace_analysis_rules.py`：`89%`
  - `dayu/host/tool_trace_analysis.py`：`98%`
- `git diff --check`：通过

首次 full Host 的 package export 与 `fetch_more` owner violations 已修复。一次 runtime
cancel-watchdog token count 波动在隔离复跑中通过，最终 clean full Host 通过；没有直接证据
指向本 Slice regression，因此不扩张到 runtime owner。

## Review 风险指引

双路 review 必须至少挑战：

- 约 1,700 行 rules 模块是否形成 God function、重复 owner 或无法独立验证的耦合；
- finding 必须有 direct evidence，limitation 不得计为 confirmed error；
- duplicate/governance、truncation/fetch_more、context pressure、timing、large payload 是否
  仅使用 typed direct facts；
- deterministic order / ID、JSON / Markdown renderer 是否从同一 report truth 投影；
- public contract invariants、private draft boundary 与 package exports 是否一致；
- `vendor_debugging=[]` 是否保持 Slice 2 冻结 shape，未偷跑 Slice 3 provider/vendor rules；
- raw payload body、timestamp latency、arguments-text duplicate、percentile-only alert、
  provider/CLI 逻辑是否渗入。

## 下一步

同时派发 AgentMiMo 与 AgentDS 对当前未提交 Slice 2 diff 做独立深度 code review。Controller
逐项编号并裁决两路 findings；在 review gate 闭环前不得创建 accepted Slice 2 commit 或进入
Slice 3。
