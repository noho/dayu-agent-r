# PR Review Fix Re-Review — Draft PR #172

## Gate

- **Review type**: re-review (AgentMiMo)
- **Date**: 2026-07-06
- **PR**: https://github.com/noho/dayu-agent-r/pull/172
- **Branch**: `phase/host-issues-control` → `main`
- **Work unit**: WU-CLI-SMOKE-01
- **Re-review inputs**: `docs/reviews/pr-172-review-ds.md`, `docs/reviews/pr-172-review-20260706-210832.md`, `docs/reviews/pr-172-review-fix-codex.md`
- **Controller adjudication**: fix DS-F01 and DS-F02 now; defer DS-F03

## Scope

Controller-accepted PR review fix gate diff：

- `docs/host/design.md`（DS-F01 设计真源映射表更新）
- `tests/host/test_host_activity_event_projection.py`（DS-F02 防卫性 ValueError 测试）
- `docs/host/issues-implementation-control.md`（control doc 状态更新）
- `docs/reviews/pr-172-review-fix-codex.md`（fix artifact）

PR review artifacts `docs/reviews/pr-172-review-20260706-210832.md` 和 `docs/reviews/pr-172-review-ds.md` 作为 review 输入核对。

## Finding Status Reconciliation

### DS-F01：design.md reasoning_delta 映射需同步为 live thinking PREVIEW row

**裁决：已修复。**

证据链：

1. `docs/host/design.md:1602`：原为 `reasoning_delta -> accepted non-durable delta; no EventLog row by default`，现为 `reasoning_delta -> preview (live thinking display only; not canonical replay truth)`。✅
2. `docs/host/design.md:1593`：新增解释——"当前 transient delta 子集是 `content_delta` 与 `tool_call_delta`。`reasoning_delta` 因 live thinking 展示需要写入 `PREVIEW` row，但仅供运行态 Host event stream 投影，不成为 memory、audit、resume、outbox terminal 或 canonical replay 真源。"✅
3. 映射表中 `content_delta` 和 `tool_call_delta` 行保持不变（`accepted non-durable delta; no EventLog row by default`），与实现一致。✅
4. 设计真源更新后，与 `dayu/host/README.md:534`（"reasoning delta 写入 PREVIEW row 只用于 live thinking 展示"）和 `engine_ingest.py:897-903`（REASONING_DELTA 写入 PREVIEW row）不再矛盾。✅

**结论**：设计真源映射表已正确更新，transient delta 子集描述准确，reasoning_delta 的 PREVIEW row 行为有完整设计-实现-文档一致性。

### DS-F02：terminal HostEvent 携带 thinking 的防卫性 ValueError 测试

**裁决：已修复。**

证据链：

1. `tests/host/test_host_activity_event_projection.py:766-785`：新增 `test_terminal_host_event_rejects_thinking_payload`。✅
2. 测试构造 `kind=HostEventKind.FAILED` 的 terminal HostEvent，`thinking=HostThinkingView(text_delta="hidden reasoning")`。✅
3. 断言 `pytest.raises(ValueError, match="terminal kind must not include thinking")`，精确匹配 `api.py:3116` 的 raise 消息。✅
4. 测试不依赖 EventLog / durable store——直接构造 HostEvent 触发 `__post_init__` → `_validate_host_event_terminal_payload`，覆盖了此前未执行的防卫分支。✅

**补充观察**：DS 原始建议同时覆盖 `HostFinalAnswerView` 检查（`api.py:3120-3124`），但 controller 只 accepted DS-F02（thinking 检查）。当前测试覆盖了 controller 要求的范围。`HostFinalAnswerView` 检查未被测试覆盖，但属于同一低严重性防卫类别，不阻塞本次 re-review。

### DS-F03：CliThinkingRenderer._seen_dedupe_keys 无界增长

**裁决：deferred，与 controller 裁决一致。**

- Owner：Future CLI UI/runtime hardening
- 当前 renderer 为 per-turn 实例，thinking delta 数量受 token 生成限制（典型 < 1000），内存影响可忽略。
- 不阻塞 PR merge。

## 新增问题检查

**未发现新增问题。**

逐项检查：

1. **design.md 更新范围**：只修改了映射表条目（line 1602）和 transient delta 子集描述（line 1593）。未引入新的架构决策、状态机变更或跨层契约变更。✅
2. **测试质量**：`test_terminal_host_event_rejects_thinking_payload` 直接测试 `HostEvent.__post_init__` 触发路径，不依赖外部 fixture / durable store，断言精确。✅
3. **control doc 更新**：WU-CLI-SMOKE-01 状态行（line 265）和 next entry point（line 162）正确记录了 PR review fix 和 re-review 入口。✅
4. **fix artifact**：`pr-172-review-fix-codex.md` 准确记录了 finding status、validation 结果和 residual risks。✅
5. **无反向依赖或架构违规**：所有修改都在 scope 内，未触及生产代码。✅

## Open Questions

无。

## Residual Risk

| Risk | Classification | Owner / Destination |
|---|---|---|
| `HostFinalAnswerView` terminal 防卫检查无测试覆盖 | deferred-with-owner | Future Host API test hardening，与 DS-F02 同类低严重性防卫 |
| `CliThinkingRenderer._seen_dedupe_keys` 无界增长 | deferred-with-owner | Future CLI UI/runtime hardening（DS-F03） |
| PREVIEW row retention / cleanup policy | deferred-with-owner | WU-RET-03 / GitHub Issue #78（已在 control doc 追踪） |
| 160-char CLI thinking truncation UX | deferred-with-owner | Future CLI UI enhancement（已在 control doc 追踪） |

## Verdict

**pass**

DS-F01 已修复：`docs/host/design.md` 映射表正确反映 `reasoning_delta` 写入 PREVIEW row 的新行为，transient delta 子集准确缩小为 `content_delta` 和 `tool_call_delta`，设计真源与实现、Host README 一致。

DS-F02 已修复：`test_terminal_host_event_rejects_thinking_payload` 覆盖了 terminal kind HostEvent 携带 thinking 时的 `ValueError` 防卫分支，断言精确匹配实现消息。

DS-F03 按 controller 裁决 deferred，residual owner 清晰。

未发现新增问题。所有 residual risks 均有明确 owner / destination。PR review fix gate 可进入 accepted PR review commit / push。
