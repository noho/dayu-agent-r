# Code Review

## Scope

- Mode: current changes (corrective slice, unstaged)
- Branch: `codex/interactive-oracle`
- Base: `main` (against `df99f858` entry HEAD)
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-review-mimo.md`
- Included scope: `docs/cli_init_workspace_manifest_v1.json`, `tests/cli/test_smoke_cli_init_provider_matrix.py`, `tests/host/test_phase5_local_execution_integration.py`, `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`, `tests/service/test_host_assembly.py`, `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md`
- Excluded scope: S8 baseline `README.md`, `dayu/config/README.md`, `dayu/host/README.md`, `tests/README.md` (verified not modified by corrective slice via SHA-256 comparison)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### Verification Summary

以下逐项 adversarial 检查均通过，未发现需要报告的 defect：

#### 1. Publication Digest 真源一致

- `docs/cli_init_workspace_manifest_v1.json:27` — `interactive.json` SHA-256 为 `69339ac8...`，与 `dayu/config/prompts/manifests/interactive.json` 实际文件 hash 一致。✓
- `docs/cli_init_workspace_manifest_v1.json:39` — `conversation_compaction.md` SHA-256 为 `4d107e1f...`，与实际文件一致。✓
- `docs/cli_init_workspace_manifest_v1.json:40` — `conversation_compaction_user.md` SHA-256 为 `b5c1f242...`，与实际文件一致。✓
- `tests/cli/test_smoke_cli_init_provider_matrix.py:96` — frozen manifest SHA-256 常量为 `c646c2a0...`，与 `docs/cli_init_workspace_manifest_v1.json` 文件实际 hash 一致。✓
- manifest 其余 40 个 file entry、5 个 directory、16 个 model_projection_owner_path 均未被修改。✓

#### 2. v2 Compact Source Boundary / Candidate Represented Coverage

- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:734-770` — fake input 已改为 v2 schema（`schema: dayu.context_compaction.input.v2`、`current_input`、`source_boundary`），与 production fake producer `_proposal_boundary_items()` 的 v2 入口一致。✓
- 断言覆盖 v2 output schema、`session_summary.source_labels`（仅 trace_material）、`evidence_facts[].support_labels`（仅 evidence_material）、`answer_anchors[].source_labels`（仅 answer_material）、`explicitly_dropped_sources` 为空、以及 represented_labels 集合完整性。✓
- `_fake_compaction_proposal_from_material_json()` 内部 `_proposal_boundary_items()` 读取 `source_boundary` 字段，按 `source_kind` 分流到 `CompactSourceKindV2` 对应 section，与测试输入和断言一致。✓

#### 3. Phase5 Sole-Flight / Exact-Once

- 六个场景均删除了 `drain_once().dispatched == 1` 竞态断言和 `_wait_for_run_status` sleep-polling。✓
- 替换为 `_ScriptedLocalWorkerHandle` 的两个 `asyncio.Event` lifecycle signal（`_events_started` 在 `events()` 首次 yield 时 set，`_closed_event` 在 `close()` 时 set），不使用 `asyncio.sleep`。✓
- `_assert_exactly_once_dispatch_outcome` helper（line 1535-1639）同时检查：
  - public `get_run(host, run_id).status` — public API 真源
  - durable `host_runs` 单行、status、`current_attempt_id`、`terminal_event_id`/`terminal_event_sequence`
  - durable `host_attempts` 单行、status、terminal ref
  - `host_attempt_dispatch_records` COUNT == 1 — exact-once dispatch
  - `event_log` 中恰好 1 条 `ATTEMPT_RUNNING`、1 条 Run terminal、1 条 Attempt terminal
  - Run terminal ref 与 event_log 一致、Attempt terminal ref 与 event_log 一致
  - Attempt terminal sequence < Run terminal sequence — 顺序正确
  - `worker_factory.created == expected_factory_creations` — 工厂创建次数
- cancel 场景先 `await handle.wait_until_events_started()` 再 `get_run(...).status is RunStatus.RUNNING`，确认 active 状态后再 cancel，再 `await handle.wait_until_closed()` 后断言终态。✓
- promoted 场景先 `await first.wait_until_closed()` + `await promoted.wait_until_closed()`，再对两个 run 分别 `_assert_exactly_once_dispatch_outcome`，`expected_factory_creations=2`。✓
- `_run_status`、`_event_type_count`、`_wait_for_run_status` 三个旧 helper 已移除，`_attempt_status` 保留（cancel 场景 mid-state 断言仍需）。其他文件 `test_active_cancel_dispatch.py` 有自己的 local 副本，不受影响。✓

#### 4. No Production Changes

- `git diff --stat` 仅显示 manifest JSON 和四个测试文件的 unstaged 变更。✓
- production prompt 文件（`conversation_compaction.md`、`conversation_compaction_user.md`、`interactive.json`）的变更在已 commit 的 S5/S7 变更中（`df99f858`、`64c581f1`），不在 corrective slice 中。✓

#### 5. Service Host Assembly Prompt Boundary

- `tests/service/test_host_assembly.py:304-318` — 断言 system prompt 不含 `<<compaction_request>>`、`dayu.context_compaction.input.v2`、`dayu.context_compaction.output.v2`，但含 `完整 replacement candidate` 和 `source label 只是本次请求内的引用标签`；user prompt template 含 placeholder、v2 input/output schema 和 `覆盖规则`。✓
- 已验证 `dayu/config/prompts/scenes/conversation_compaction.md` 和 `conversation_compaction_user.md` 实际内容与上述断言一致。✓

#### 6. Full Suite 6571 Pass 与偶发诊断 Disposition

- artifact §6 报告 `6571 passed, 10 skipped, 6 deselected, 3 warnings in 218.42s`。✓
- cancel-watchdog duplicate observation：artifact 诚实描述为"仅在一次 full-suite load 观察"、"没有稳定 reproduction"、"本 slice 不修改"。✓
- SIGKILL delayed recovery timeout：artifact 诚实描述为"仅在一次 full-suite load 超时"、"没有稳定 root cause"、"不做 timing 放宽"。✓
- 两个偶发均分配给 `later S8 validation owner`，未被错误关闭。✓

#### 7. Artifact Scope/Gate 声明

- artifact 状态为 `READY-FOR-DUAL-CORRECTIVE-CODE-REVIEW`，不宣称 review 已通过。✓
- artifact 声明没有 stage、commit、push、修改 production 或 frozen files，与 diff 一致。✓
- README SHA-256 声明与实际文件 hash 一致。✓
- S8 artifact SHA-256 声明保持不变。✓
- Ruff gate 声明区分 changed Python（已绿）与 full-repository 97 debt（非本 slice blocker）。✓

## Open Questions

无。

## Residual Risk

- `wait_until_events_started` 的时序依赖 scheduler 在 `accept()` 前完成 ATTEMPT_RUNNING 事务提交。当前 scheduler 实现满足此前提，但若未来 scheduler 重构为 accept-then-commit，cancel 场景的 mid-state 断言可能需要调整。风险低，由 scheduler dispatch owner 维护。
