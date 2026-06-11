# WU-PROJ-01 Aggregate Deepreview Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: aggregate deepreview controller adjudication
- 日期: 2026-06-11
- Controller: AgentController
- Base reviewed range: accepted plan `fb3cc9ec` through bookkeeping `9191f5ab`

## 输入

- AgentMiMo artifact: `docs/reviews/wu-proj-01-aggregate-deepreview-mimo.md`
- AgentDS artifact: `docs/reviews/wu-proj-01-aggregate-deepreview-ds.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Accepted plan: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`

## 裁决结论

`PASS`。WU-PROJ-01 aggregate deepreview 通过；不进入 aggregate fix gate；进入 ready-to-open-draft-PR。

理由：

- AgentMiMo verdict: `PASS-WITH-FINDINGS`，无 blocking finding。
- AgentDS verdict: `PASS`，无 blocking finding。
- 两路 review 均确认 WU-PROJ-01 的第一性原理目标已达成：compact input truth 来自 EventLog / payload descriptor / artifact truth，Conversation Memory projection 只消费 accepted compact 并服务 ordinary RunInput，Context Governance 只做预算裁决与编排。
- 两路 review 均确认 Slice 1-4 的代码、测试、README / control doc 更新与 accepted plan 一致。
- 两路 review 均确认 `WU-PROJ-01-S3-R1` 与 `WU-PROJ-01-S4-R1` 已有 deferred owner，不阻塞 draft PR gate。

## Findings 裁决

| 来源 | Finding | 裁决 |
|---|---|---|
| AgentMiMo NF1 | `_memory_projection_catchup_budget` unsupported purpose 分支无测试 | rejected-as-nonblocking；该分支是 defensive guard，当前枚举值已覆盖。 |
| AgentMiMo NF2 | dispatch before-worker catch-up happy path 无独立集成测试 | deferred-with-owner；已登记为 `WU-PROJ-01-S3-R1`，由 Host dispatch test hardening 承接。 |
| AgentMiMo NF3 | `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` lane timeout flaky | deferred-with-owner；已登记为 `WU-PROJ-01-S4-R1`，由 Host dispatch scheduler test hardening 承接。 |
| AgentDS Low 1 | proactive path 显式传 `memory_snapshot=None` 可读性可提升 | accepted-as-nonblocking；语义正确，不要求当前 WU 修改。 |
| AgentDS Low 2 | `budget=None` 无运行时 guard | accepted-as-nonblocking；生产 caller 均传 budget，后续新增 caller 可单独加强。 |
| AgentDS Low 3 | scanning budget 检查分散在 batch 前后两处 | accepted-as-nonblocking；当前实现和测试覆盖充分，不要求当前 WU 修改。 |

## Controller 验证

- Slice 4 controller 复验：
  - `source .venv/bin/activate && python -m pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -k "compact_failure_is_attempt_free or compact or governance"`
  - `25 passed, 103 deselected`
  - `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- AgentMiMo aggregate validation:
  - `68 passed, 1 skipped, 123 deselected`
  - `pyright: 0 errors, 0 warnings, 0 informations`
- AgentDS aggregate validation:
  - `143 tests passed`
  - `pyright: 0 errors, 0 warnings, 0 informations`

## Residual Risk

- `WU-PROJ-01-S3-R1`: deferred-with-owner to Host dispatch test hardening。
- `WU-PROJ-01-S4-R1`: deferred-with-owner to Host dispatch scheduler test hardening。

两项 residual risk 均为测试覆盖或测试稳定性增强，不影响本 WU 的生产语义闭环，不阻塞 draft PR gate。
