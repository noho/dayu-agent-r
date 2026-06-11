# WU-PROJ-01 PR Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review
- Date: 2026-06-11
- Controller: Phaseflow
- Review artifacts:
  - `docs/reviews/wu-proj-01-pr-review-residual-mimo.md`
  - `docs/reviews/wu-proj-01-pr-review-residual-ds.md`

## 结论

PR review accepted with one fix required。

AgentMiMo 与 AgentDS 均裁决 `PASS`，无 blocking correctness finding。总控接受 PASS 部分，同时接受 MiMo NF1 作为当前 PR 文档修复。

## Accepted Findings

### PR-F1: `budget=None` docstring 与生产 dispatch correctness path 不一致

裁决：`accepted`

`ConversationMemoryProjectionCatchupPort` 与 `catch_up_conversation_memory_projection(...)` 的 `budget` 参数 docstring 仍写成 "``None`` 仅供显式审阅的 close-only 或 test-only 调用"。当前生产 `dispatch.py` required catch-up / rebuild correctness path 使用 `budget=None` 表达 "不设固定总预算，追到 required cursor、idle 或 failure"。旧措辞会误导后续维护者重新引入 cap 或误判 production path。

Fix 要求：

- 更新 `dayu/host/memory_repair.py` 中相关 `budget` 参数 docstring。
- 新措辞必须说明 `None` 表示不设置固定批次数 / 扫描事件总预算，适用于 required cursor correctness path；有预算对象时才表示 bounded opportunistic / diagnostic catch-up。
- 不修改生产行为。

## Rejected / Deferred Findings

### PR-F2: `MemoryProjectionRepairPurpose` 单值 enum 后续可简化

裁决：`deferred-with-owner`

当前单值 enum 只用于 `MemoryProjectionCatchupBudget` 的类型校验与日志 metadata，不影响 correctness。是否把 `purpose` 收敛为更简单的 sentinel / literal 属于后续 memory_repair cleanup，不阻塞 PR #136。

Owner：后续 memory repair cleanup / WU-PROJ follow-up。

### PR-F3: `run_input.py` accepted evidence selection cap

裁决：`rejected-with-reason`

`_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8` 属于 ordinary RunInput / compactor input material selection，不是 CAP-R1 的 source builder cap，也不是 current correctness path budget。当前 PR 不重设计 ordinary prompt selection policy。

### PR-F4: reactive compact path broad `except Exception`

裁决：`deferred-with-owner`

该模式不是本次 residual implementation 引入；当前 review 也确认它符合现有 fail-closed 风格。后续如要收窄异常类型，应在 reactive recovery hardening 中单独处理。

Owner：后续 reactive recovery hardening。

## 验证要求

AgentCodex fix 后至少运行：

- `python -m pytest tests/host/test_memory_repair.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py`
- `pyright`
- `git diff --check`
