# PR 190 F17 Plan Acceptance

## Gate result

- Goal Confirmation：`pass`
- Initial AgentMiMo plan review：`pass`，0 findings
- Initial AgentDS plan review：`pass`，3 low findings
- Controller adjudication：F17-P1/P2 `accepted`，F17-P3 `rejected-with-reason`
- AgentCodex plan fix：只落实 F17-P1/P2；无 implementation write
- AgentMiMo re-review：`pass`，0 remaining findings
- AgentDS re-review：`pass`，0 remaining findings
- Final plan gate：`accepted`

## Accepted implementation boundary

实施是一个两-hunk 原子 slice：

1. 只把 `docs/cli_init_workspace_manifest_v1.json` 中
   `config/prompts/scenes/conversation_compaction_user.md` 的唯一 `content_sha256`
   更新为从 prompt raw bytes 计算的
   `22e7bc5015cb369ff228a754b557493594b8313c99877944b5a7c08da0dc1c88`。
2. 保存 manifest 后，从其实际 raw bytes 重新计算 SHA-256；只更新
   `tests/cli/test_smoke_cli_init_provider_matrix.py::FROZEN_MANIFEST_SHA256`。

严禁修改 prompt、production transaction、validator、fixture/assertion 逻辑、5/43/16 inventory、
Oracle/scenario/readiness、schema/public contract 或 CLI 产品行为。

## Evidence

- Goal：`docs/gateflow/pr-190-f17-goal-confirmation-20260807.md`
- Accepted plan：`docs/gateflow/pr-190-f17-plan-20260807.md`
- Initial reviews：
  - `docs/reviews/plan-review-20260807-143241.md`
  - `docs/reviews/plan-review-20260807-143636.md`
- Adjudication：`docs/gateflow/pr-190-f17-plan-review-adjudication-20260807.md`
- Re-reviews：
  - `docs/reviews/plan-review-20260807-144241.md`
  - `docs/reviews/plan-review-20260807-144253.md`

下一 gate 为 implementation；进入前必须重新发现 Agent pane，并由 AgentCodex 按 accepted plan 实施。
