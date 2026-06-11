# WU-PROJ-01 Slice 4 Code Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Slice: Slice 4 accepted compact -> Conversation Memory -> ordinary RunInput regression
- Gate: controller adjudication
- 日期: 2026-06-11
- Controller: AgentController

## 输入

- Implementation artifact: `docs/reviews/wu-proj-01-slice4-implementation-codex.md`
- AgentMiMo review: `docs/reviews/wu-proj-01-slice4-code-review-mimo.md`
- AgentDS review: `docs/reviews/wu-proj-01-slice4-code-review-ds.md`

## 裁决结论

`PASS`。接受 Slice 4 implementation；不进入 fix gate。

理由：

- 两路 review 均确认 accepted `CONTEXT_COMPACTED` 通过 durable `ProjectionRunner` 物化五类 Conversation Memory section，并推进 checkpoint。
- 两路 review 均确认 ordinary RunInput 能读取 projection snapshot 中的五类业务 section。
- 两路 review 均确认 failed compact negative regression 覆盖了不写 memory snapshot/items 与不生成 compact artifact。
- AgentMiMo 的 findings 均为低严重度测试维护观察，不影响 Slice 4 验收。
- AgentDS 的 notes 与 residual risk 均不构成本 slice 阻断项。

## Findings 裁决

| 来源 | Finding | 裁决 |
|---|---|---|
| AgentMiMo | accepted compact test 与 fixture 字符串精确耦合 | accepted-as-nonblocking；这是确定性 regression fixture 的合理断言方式。 |
| AgentMiMo | RunInput test 混合 section header 与 content fragment 断言 | accepted-as-nonblocking；两类断言覆盖结构与业务内容两个维度。 |
| AgentMiMo | `_memory_item_count` 当前单测使用 | accepted-as-nonblocking；模块级 helper 符合 AGENTS.md，后续可复用。 |
| AgentDS | per-message 与 system_content 断言存在部分语义重叠 | accepted-as-nonblocking；属于防回归冗余，不要求修复。 |
| AgentDS | `_memory_item_count` 使用 f-string SQL | accepted-as-nonblocking；表名来自常量，无用户输入；当前测试文件既有风格允许该模式。 |
| AgentDS | `_compact_artifact_files` 当前仅被一个测试使用 | accepted-as-nonblocking；负向 artifact 断言目标集中，暂不抽象。 |

## Residual Risk

- `WU-PROJ-01-S3-R1` 仍为 deferred-with-owner：dispatch before-worker catch-up happy path 未被 Slice 4 自然覆盖，后续 Host dispatch test hardening 承接。
- `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 的 lane timeout flaky 由 AgentDS 观察到；该测试不在 Slice 4 修改范围，不阻断本 slice，后续单独追踪。

## Controller 验证

- `source .venv/bin/activate && python -m pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -k "compact_failure_is_attempt_free or compact or governance"`
  - `25 passed, 103 deselected`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - pass
