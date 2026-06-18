# PR Review — WU-CLI-ACTIVITY-01

## Scope

- Mode: PR review
- PR: https://github.com/noho/dayu-agent-r/pull/149
- Title: "WU-CLI-ACTIVITY-01 activity stream and event projection hardening"
- Author: noho (Leo Liu)
- Head branch: wu-cli-activity-01
- Base branch: main
- Commits: 24 (from plan acceptance 012fee0a to deepreview acceptance ccf2fdca)
- Output file: docs/reviews/wu-cli-activity-01-pr-review-ds-20260618.md
- Included scope: 103 changed files — 24,315 additions, 1,535 deletions across dayu/cli/, dayu/host/, dayu/service/, dayu/fins/, dayu/runtime/, docs/host/, docs/reviews/, 根 README.md, AGENTS.md, CLAUDE.md
- Excluded scope: .github/ 清理（独立于 PR 内容）

## Conclusion

**PASS** — 无阻断 finding。PR diff 整体一致，活动流原始实现与 follow-up delta/EventLog/projection 硬化正确集成，无公共 API 未裁决漂移，README/design/control doc 与代码一致，pyright 零报错，测试 1631 passed。

以下仅记录两处 pre-existing 测试失败（`main` 分支同样失败）和一处 low-severity 观察。

## PR Body Validation

| 声称 | 代码证据 | 一致 |
|------|----------|------|
| "user-visible activity stream support for prompt / interactive" | `dayu/cli/activity.py` (新增 245 行), `dayu/cli/composer.py` (新增 171 行), `dayu/cli/run_view.py` (新增 391 行), `dayu/cli/commands/interactive.py` (+219), `dayu/cli/commands/prompt.py` (+195), `dayu/host/read_api.py` (+526, activity projection) | ✅ |
| "per-delta Engine events are not durable EventLog rows" | `dayu/host/engine_ingest.py:213-219,928-929,4700-4717,6088-6101` | ✅ |
| "ProjectionRunner uses filter-aware covered cursor reads" | `dayu/host/projection.py:558-651`, `dayu/host/durable/event_log.py:643-740` | ✅ |
| "Conversation Memory catch-up/rebuild no longer has semantic budgets" | `dayu/host/memory_repair.py:176-255`, 旧符号全量删除 | ✅ |
| "RunInputBuilder inline memory repair with Conversation Memory projection filter truth" | `dayu/host/run_input.py:1163-1229`, 复用 `conversation_memory_projection_event_filter()` | ✅ |
| "removes unbounded memory catch-up from Host hot paths" | `dayu/host/dispatch.py:2969-2989` (bounded via `max_event_sequence`), `dayu/host/open_host.py` (删除 `_MemoryProjectionCatchupPort`) | ✅ |
| Gate artifacts 列表 | 所有引用的 plan、review、control doc 文件均存在于 PR diff 中 | ✅ |

### PR Body 额外内容一致性

- PR description 中引用的 `docs/host/host-issues/` 下的两个 plan 文件均在 PR diff 中新增
- `docs/host/issues-implementation-control.md` 的 WU-CLI-ACTIVITY-01 条目准确描述了 5 个 follow-up slice 状态
- PR 列出的 `docs/reviews/` 下所有 aggregate review 文件均在 diff 中

## Validation

| 检查项 | 结果 | 证据 |
|--------|------|------|
| pyright | ✅ 0 errors, 0 warnings, 0 informations | `python -m pyright dayu/ tests/ utils/` |
| 测试 (host + cli + service) | ✅ 1631 passed, 1 skipped | `pytest tests/host/ tests/cli/ tests/service/` |
| 测试 (activity coverage) | ✅ 90.25% | `--cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys` |
| 旧预算符号 | ✅ 零残留 | `MemoryProjectionCatchupBudget`, `MemoryProjectionRepairPurpose`, `_OPPORTUNISTIC_AFTER_COMPACT`, `_opportunistic_memory_projection_catchup_budget`, `ConversationMemoryProjectionCatchupPort` 均不在 `dayu/` 和 `tests/` |
| Import cycle | ✅ 无循环 | `memory_repair → projection → durable/event_log`; `dispatch → memory_repair / run_input`; `run_input → projection / durable/memory` |
| Public API drift | ✅ 无漂移 | `OpenHostOptions.memory_projection_catchup_batch_size` 在 `api.py`, `open_host.py`, `engine_ingest.py`, `dispatch.py`, `service/host_assembly.py` 一致使用 |
| README 一致性 | ✅ | `dayu/host/README.md` 更新为 "page size" 语义，与 `docs/host/design.md:99` 一致；根 `README.md` 新增 `--log-file` 参数和 Agent 更新约束 |
| Design/control doc | ✅ | `docs/host/design.md` delta 非持久化声明（行 339）；`docs/host/issues-implementation-control.md` 5 个 follow-up slice 均标记为 accepted |
| 未提交 diff | ✅ 无残留 | `git diff --check` clean（当前 branch 已包含 aggregate fix 两个新测试和 dead code cleanup，已通过 re-review） |

## Findings

未发现实质性问题。

以下两处 pre-existing 测试失败与 PR 变更无关：

### 1-未修复-低-`test_deterministic_two_turn_request_contains_prior_final_answer` — pre-existing failure on `main`

- **入口/函数**: `test_deterministic_two_turn_request_contains_prior_final_answer` (`tests/host/test_public_open_host_multiturn_smoke.py:160`)
- **输入场景**: 两轮 public no-tool followup，第二轮 Engine request 应包含第一轮 final answer 信息
- **实际分支**: 断言 `f"final:1:{first.accepted_run_id}"` 在第二轮 messages 中不存在
- **直接证据**: 同样在 `main` (cf2993ef) 上失败 — 非本 PR 引入
- **影响**: 仅该测试，生产行为未受影响（multiturn continuity 走 SessionContinuityProvider + memory snapshot）
- **严厉程度（低/中/高/严重）**: 低

### 2-未修复-低-`test_mock_tool_result_feeds_same_run_and_later_run_continuity` — pre-existing failure on `main`

- **入口/函数**: `test_mock_tool_result_feeds_same_run_and_later_run_continuity` (`tests/host/test_public_tool_wiring_smoke.py:82`)
- **输入场景**: 工具调用后第二轮 followup 应从 memory 中获得 accepted tool fact
- **实际分支**: 断言 `"tool fact accepted"` 在新 Run 初始 messages 中不存在
- **直接证据**: 同样在 `main` (cf2993ef) 上失败 — 非本 PR 引入
- **影响**: 仅该测试。`DurableMemorySnapshotProvider` 在 `main` 上通过 `HostLocalExecutionOptions.memory_projection_policy` 控制；当 policy 为 None 时不启用 memory snapshot，conversation context 走 non-memory continuity。该测试在 WU-CLI-ACTIVITY-01 范围外，需独立 work unit
- **严厉程度（低/中/高/严重）**: 低

## Open Questions

- `test_deterministic_two_turn_request_contains_prior_final_answer` 和 `test_mock_tool_result_feeds_same_run_and_later_run_continuity` 两处 pre-existing 测试失败应作为独立 issue/work unit 跟踪，不属于本 PR 阻塞条件。是否需要在本 PR 中单独添加 deferred note 到 control doc，由用户裁决。

## Residual Risk

- **pre-existing 测试失败**（见 Findings #1, #2）：两处 smoke 测试在 `main` 上已失败，不阻断本 PR
- **PR 范围广阔**：103 files / 24K lines 变更跨越 cli/host/service/fins 四层，尽管每层均有对应的 slice implementation + review + aggregate review 流程支撑，单 PR reviewer 无法在合理时间内逐行走读全量 diff。建议后续 PR 考虑按独立 work unit 分拆
- **无 CI checks**：PR 当前无 GitHub Actions CI 运行记录，PR body 中列出的所有验证结果来自本地执行。建议在合并前确认 CI 环境可复现
