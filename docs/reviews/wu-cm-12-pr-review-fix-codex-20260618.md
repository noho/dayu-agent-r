# WU-CM-12 PR Review Fix Gate

## Scope

- Gate: PR review fix
- Work unit: WU-CM-12 Conversation Memory drift repair
- PR review artifacts:
  - `docs/reviews/pr-150-review-20260618-195915.md`
  - `docs/reviews/pr-150-review-20260618-200404.md`
- Design truth checked:
  - `docs/host/design.md`
  - `docs/engine/design.md`
- Control doc checked:
  - `docs/host/issues-implementation-control.md`

Controller 裁决限定本 gate 只修复两个非阻断本地质量项。本轮未处理 rejected / deferred findings，未进入 re-review、commit、push、PR 或后续 gate。

## First-Principles Judgment

Accepted finding A 成立：`_load_context_fallback_tx` 已经 fail closed，但先做 mismatch 检查会让缺失 `current_input_ref` 的诊断被误报为 mismatch。正确修复是先判断 missing，再判断 mismatch，不改变 fallback 继续执行的安全边界。

Accepted finding B 成立：`build_recent_window_fallback_selection` 是 fallback selected window caps 的 public helper 入口；已有测试覆盖“caps 拒绝后不回填更旧 block”，但 item cap、char cap 和 `memory_policy=None` 的旧调用点无 caps 行为缺少明确回归测试。

## Fixes

### A. fallback current_input_ref 诊断顺序

- File: `dayu/host/context_fallback.py`
- Change: `_load_context_fallback_tx` 读取 fallback window 后，先检查 `_FIELD_CURRENT_INPUT_REF` 是否缺失；缺失时报 `fallback current_input_ref is missing`；字段存在但与当前输入不一致时报 `fallback current_input_ref mismatch`。
- Coverage: `test_eventlog_context_fallback_provider_fail_closes_on_payload_drift` 增加 `missing_current_ref` case；fixture 删除 fallback window 内的 `current_input_ref` 并按缺字段 window 重新计算 digest，直接验证 provider 抛出 `fallback current_input_ref is missing`。
- Behavior: fail closed 不变；只改善诊断分类。

### B. fallback selected window caps 边界测试

- File: `tests/host/test_run_input_builder.py`
- Change: 通过 public helper `build_recent_window_fallback_selection` 增加三个 focused tests：
  - `test_recent_window_fallback_item_cap_rejects_append`
  - `test_recent_window_fallback_char_cap_rejects_append`
  - `test_recent_window_fallback_without_memory_policy_allows_uncapped_append`
- Change: `_memory_policy` 测试 helper 增加 `fallback_selected_recent_window_item_cap` 参数，便于直接表达 item cap 边界。
- Coverage: item cap 拒绝追加、char cap 拒绝追加、`memory_policy=None` 时允许旧调用点无 caps 追加。

## README Decision

- `dayu/host/README.md`: 已读取 Agent 更新约束。本轮只调整内部诊断顺序和测试覆盖，不改变 Host public contract、架构、状态机或稳定开发接口；不更新。
- `tests/README.md`: 已读取测试手册。本轮只在既有 Host 测试文件内增加同层级 focused tests，不新增测试层级、运行方式或维护约定；不更新。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py -q`
  - Result: passed, `80 passed in 0.76s`
- `source .venv/bin/activate && pyright dayu/host/context_fallback.py tests/host/test_run_input_builder.py`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Residual Risks

- Deferred by controller: `compaction_evidence.py` dead production code cleanup remains assigned to later cleanup owner.
- Deferred by controller: `_vnext_compact_candidate_semantic_lines` defensive-depth asymmetry remains out of scope.
- Rejected/deferred by controller: recovery tier rejected attempts EventLog diagnostic gap remains out of scope.
- Note for final closeout: `_facts_from_accepted_event` old bug fix was not part of this local fix gate and should be recorded in final closeout as instructed.

## Changed Files

- `dayu/host/context_fallback.py`
- `tests/host/test_run_input_builder.py`
- `docs/reviews/wu-cm-12-pr-review-fix-codex-20260618.md`

## Completion Status

PASS for the limited PR review fix gate scope. No commit, push, PR, merge, re-review, or subsequent gate was performed.
