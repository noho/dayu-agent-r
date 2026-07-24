# WU-OBS-00 Slice 2 Review Fix — Controller Adjudication

## 裁决

- Work Unit：`WU-OBS-00`
- Gate：Slice 2 implementation review fix
- Decision：`pass-to-rereview`
- Acceptance：尚未 accepted
- Blocking open questions：None

AgentCodex fix artifact：
`docs/reviews/wu-obs-00-slice-2-implementation-review-fix-codex.md`

## Closing evidence

- `CTRL-S2-IMPL-01`：`dayu.host.tool_trace_analysis.__all__` 精确包含三个 public
  functions；内部 builder/loader 不在 owner 声明表面。
- `CTRL-S2-IMPL-02`：cold-line 与 resolved-payload measure 的 evidence identity 完全分离。
  non-cold measure 严格要求 available hot store、expected hot DB path 和 matching hot row；
  evidence 使用 `kind=resolved_payload`、hot DB path、`line_number=None`。缺 hot owner facts
  直接 fail closed，没有 requested/cold fallback。
- `CTRL-S2-IMPL-03`：保持冻结非空 `cold_lock_path` shape；contract 与 Markdown 明确该字段
  是 expected owner-derived path，只有 `capabilities.cold=true` 才证明本次实际获取 lock 并
  读取 cold snapshot。

被 Controller 拒绝的 Markdown 索引重构与 helper 公开化均未实施；producer/schema/CLI/
provider/vendor 未修改。

## 验证

- focused：`64 passed`
- clean full Host：`2318 passed, 2 skipped, 6 deselected`
- targeted/full pyright：`0 errors, 0 warnings`
- branch coverage：
  - `dayu/host/__init__.py`：`100%`
  - `dayu/host/tool_trace_analysis.py`：`100%`
  - `dayu/host/tool_trace_analysis_contracts.py`：`85%`
  - `dayu/host/tool_trace_analysis_rules.py`：`91%`
- Controller/AgentCodex 独立关键反例：`4 passed`
- Ruff、`git diff --check`：通过
- README audit：无需更新
- 受保护 control/review artifact 哈希保持不变

## 下一步

AgentMiMo 与 AgentDS 独立 re-review 当前完整 Slice 2 diff，必须验证三项 accepted finding
确实关闭且没有新增 actionable finding。双路明确完成前不得创建 accepted Slice 2 commit。
