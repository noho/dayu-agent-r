# WU-CM-01 Compact Contract Closure Fix - Codex

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure fix gate |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| implementation artifact | `docs/reviews/wu-cm-01-compact-contract-closure-implementation-retry-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-code-review-controller-adjudication.md` |
| fix agent | AgentCodex |
| date | 2026-06-04 |

## Scope

本 fix gate 只修复 Controller accepted findings，不 commit、不 push、不开 PR、不进入 re-review 或其它 gate。

变更文件：

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_dispatch_scheduler.py`
- `docs/host/wu-cm-01-conversation-memory-plan.md`
- `docs/reviews/wu-cm-01-compact-contract-closure-fix-codex.md`

## Accepted Finding Fixes

### 1. Blocking correctness: forward intent enum mismatch

状态：已修复。

修复内容：

- `conversation_compaction_user.md` 的 `forward_intents[*].intent_type` 示例从 parser 不接受的 `user_constraint`、`working_assumption` 改为 `pending_clarification`、`pending_user_visible_task`，保留 `next_step_note`、`open_question`。
- `forward_intents[*].status` 示例从 parser 不接受的 `resolved` 改为 `blocked`、`superseded`，保留 `open`。
- `tests/host/test_llm_compaction.py::test_prompt_forward_intent_enum_values_match_parser_vnext` 从 prompt template 中读取 schema 示例的 pipe-separated enum 值，并逐个构造 `ForwardIntentTypeVNext` / `ForwardIntentStatusVNext`，确保模板列出的值均被 parser enum 接受。

直接证据：

- `dayu/config/prompts/scenes/conversation_compaction_user.md:35`
- `dayu/config/prompts/scenes/conversation_compaction_user.md:37`
- `tests/host/test_llm_compaction.py:155`

### 2. Blocking test regression: repeated reactive overflow attempt count

状态：已修复。

根因判断：

- `FakeContextCompactor` 本身无跨测试可变状态；每次 `compact()` 都从 request material 生成 deterministic vNext output。
- 原测试只等待第一个 `CONTEXT_COMPACTED`，此时 reactive recovery 后台 loop 可能尚未推进到 budget limit，也可能已创建下一次 Attempt。`actual_attempt_count` 的 2 / 3 差异来自测试读取中间态的竞态，不是 production attempt accounting 的语义错误。

修复内容：

- `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 改为等待最终 `CONTEXT_COMPACTION_FAILED`。
- 断言最终稳定状态：`max_reactive_compactions_per_run=2` 时产生 2 个 `CONTEXT_COMPACTION_REQUESTED`、2 个 `CONTEXT_COMPACTED`，第三个 worker overflow 因 `reactive_compact_limit_reached` fail closed，因此 attempt count 为 `max_reactive_compactions_per_run + 1`。
- 断言不写 `RUN_LOST`，failed payload 为 no-fallback diagnostic 形态。

直接证据：

- `tests/host/test_dispatch_scheduler.py:4276`
- `tests/host/test_dispatch_scheduler.py:4293`
- `tests/host/test_dispatch_scheduler.py:4313`
- `tests/host/test_dispatch_scheduler.py:4324`

### 3. Non-blocking scope record: necessary dependency fallout

状态：已记录。

修复内容：

- 在 `docs/host/wu-cm-01-conversation-memory-plan.md` 的 Pre-Slice C allowed files 后补记 necessary dependency fallout。
- 记录 `dayu/config/prompts/scenes/conversation_compaction.md` / `conversation_compaction_user.md` 仅限 vNext prompt schema、vNext material field name 与 parser enum member replacement。
- 记录 `dayu/host/context_fallback.py` 仅限 fallback recent-window view 对 vNext material section / enum member 的类型对齐。
- 明确不扩大到 config-service、scene assembly、runtime prompt loading、fallback behavior、memory durable/projection 语义。

直接证据：

- `docs/host/wu-cm-01-conversation-memory-plan.md:264`

## Not Fixed / Deferred / Rejected Items

- memory-owned legacy projection parser path：未修复；Controller 裁决为 `deferred-with-owner`，owner 是后续 Slice C memory projection closure。本 fix artifact 保留该 residual risk，不在本 gate 删除。
- `compaction.py.__all__` 未导出 7 个 `MAX_VNEXT_*` char/label 常量：未修复；Controller 已 rejected，保持内部实现细节。

## Validation

均在 `source .venv/bin/activate` 后运行。

```bash
pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q
```

Result: `28 passed in 0.27s`

```bash
pytest tests/host/test_dispatch_scheduler.py -q
```

Result: `60 passed in 1.33s`

```bash
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_compact_artifact_store.py -q
```

Result: `88 passed in 0.51s`

```bash
pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q
```

Result: `99 passed in 0.87s`

```bash
pytest tests/host/test_package_exports.py tests/host/test_public_compact_smoke.py -q
```

Result: `15 passed, 1 skipped in 0.84s`

```bash
python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`

Pyright reported an available version update (`v1.1.409 -> v1.1.410`); this does not affect validation status.

## README Check

- `dayu/config/README.md` checked. It documents prompt directory duties, scene assembly, and the compactor user prompt template path, but does not document compact output enum members. No README change needed for enum replacement.
- `tests/README.md` checked. It already records `test_llm_compaction.py` and `test_dispatch_scheduler.py` as compact / reactive compaction coverage owners. The added enum consistency assertion and stabilized repeated-overflow assertion do not change test-layer responsibilities. No README change needed.

## Residual Risks

- Deferred Slice C memory legacy path remains: `dayu/host/memory.py` still has a memory-owned legacy projection fixture/parser path. It is not exported as compact public contract; owner remains later Slice C.
- This fix gate did not re-review, commit, push, create PR, or enter any other gate by instruction.

## Completion Status

`fix-complete` for Controller accepted findings. Stop at fix artifact completion.

Artifact path: `docs/reviews/wu-cm-01-compact-contract-closure-fix-codex.md`
