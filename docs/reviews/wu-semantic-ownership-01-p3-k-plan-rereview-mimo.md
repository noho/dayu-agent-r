# WU-SEMANTIC-OWNERSHIP-01 P3-K Plan Re-Review — AgentMiMo

## Review Metadata

- **Reviewer**: AgentMiMo (adversarial re-review)
- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-p3-k-test-harness-semantic-coupling-plan.md` (post-fix)
- **Re-review date**: 2026-07-11
- **Re-review scope**: P3-K plan fix verification only (PF-01..PF-04 + rejected item)
- **Original reviews**: `docs/reviews/wu-semantic-ownership-01-p3-k-plan-review-mimo.md`, `docs/reviews/wu-semantic-ownership-01-p3-k-plan-review-ds.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-k-plan-review-controller-adjudication.md`
- **Plan fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-k-plan-fix-codex.md`

---

## Verification Method

对每个 accepted fix (PF-01..PF-04)，从修正后的计划中提取对应文本，与控制器裁决要求逐条对照，并用代码事实验证引用的正确性。

---

## PF-01: S1 resume-guidance assertion ownership — 验证结果

**控制器要求**:

1. 区分 dynamic owner-derived content assertions 与 production-owned guidance constants。
2. 明确 helper 应直接断言 production constants 还是断言 named production-owned guidance semantics。
3. helper 不得使用 vague substring checks。
4. 可选共享 helper 文件仅在 reuse 有充分理由时才引入；否则优先 file-local private helper。

**计划修正文本** (S1 `test_run_input_builder.py` 部分):

> The helper must distinguish two assertion classes:
> - dynamic owner-derived content assertions: exact tool name, completion status, and result payload text that are produced from the wait completion projection / payload;
> - named production-owned guidance semantics: the resume guidance owner currently promises an intro that the prior waiting external tool step has completed and a no-repeat instruction for the same request.

> The helper must assert the named production-owned guidance semantics, not vague keyword substrings. If the production owner exposes stable public constants for these guidance fragments, the helper should assert those constants directly. If the constants remain private implementation details, the helper may keep exact expected fragments in the test, but its name/docstring must state that those fragments mirror production-owned resume guidance semantics and must be updated when the owner intentionally changes the guidance.

> Do not add `tests/host/llm_text_assertions.py` unless at least two test modules need the same assertion helper with the same owner semantics. For the current `test_run_input_builder.py` resume guidance case, prefer a file-local private helper.

**Completion signal**:

> Resume guidance helper does not use vague substring checks; it either asserts stable production guidance constants directly or asserts named production-owned guidance semantics with exact expected fragments plus a docstring documenting the owner relationship.

**代码事实验证**:

| 验证点 | 结果 |
|--------|------|
| 两类断言是否正确区分 | ✅ dynamic (tool name, status, result) vs production-owned (intro, no-repeat) |
| vague substring 是否被禁止 | ✅ "not vague keyword substrings" 显式禁止 |
| constant 路径 vs implementation-detail 路径是否覆盖 | ✅ 两条路径均有明确指引 |
| 共享 helper 是否为 optional | ✅ "unless at least two test modules need the same assertion helper" |
| 文件内 helper 是否优先 | ✅ "prefer a file-local private helper" |

**代码事实备注**: 原始 MiMo review 引用了 `_RESUME_WAIT_FALLBACK_INTRO` (run_input.py:3524) 和 `_RESUME_WAIT_FALLBACK_NO_REPEAT` (run_input.py:3528) 作为 production 常量。经代码验证，这些命名常量在当前 `run_input.py` 中不存在——对应文本是内联的。计划修正的 fallback 逻辑（"If the constants remain private implementation details, the helper may keep exact expected fragments in the test"）正确覆盖了这种情况。Implementation agent 实施时会发现常量不存在，直接走 fallback 路径。

**PF-01 结论**: ✅ **已关闭**

---

## PF-02: S2 raw SQL helper final disposition — 验证结果

**控制器要求**:

1. 枚举每个 TF-2 raw SQL helper 的最终处置：replace / diagnostic-only / fault-injection-only。
2. 纠正 `read_by_host_instance_id` 为 `read_host_instance`。
3. 验证 projection checkpoint helper 名称/签名或显式分类为 raw SQL retention。
4. 更新 completion signal：成功标准是消除 exact-replaceable SQL 并记录其余，而非广泛减少 raw SQL。

**计划修正文本** (S2 final disposition list):

| Helper | Disposition | 理由 |
|--------|-------------|------|
| `_diagnostic_event_type_count(...)` | diagnostic-only, keep raw SQL | cross-Run EventLog `event_type` count 无 run_id；production `count_committed_events_by_run_and_type(...)` 需要 run_id，语义不同 |
| `force_owner_pid_missing_and_heartbeat_stale(...)` | fault-injection-only, keep raw SQL | production liveness APIs 不能 fabricate missing pid / stale heartbeat |
| `force_memory_projection_lag(...)` | fault-injection-only, keep raw SQL | production checkpoint helpers (`read_projection_checkpoint`, `ensure_projection_checkpoint`, `advance_projection_checkpoint`) confirmed to exist but are not exact semantic equivalents for forcing backwards / clearing `checkpoint_event_id` |
| `event_type_count(...)` | diagnostic-only, keep raw SQL | same cross-Run EventLog count reason |
| `projection_checkpoint_sequence(...)` | **replace** with `read_projection_checkpoint(transaction, _MEMORY_CONSUMER_ID)` | exact existing owner helper |
| `read_latest_event_sequence(...)` | diagnostic-only, keep raw SQL | global `MAX(event_sequence)` aggregate；production EventLog readers consume by cursor，无 max-sequence helper |
| `read_event_log_count(...)` | diagnostic-only, keep raw SQL | global EventLog row count 无 exact production helper |
| `read_host_instances(...)` | diagnostic-only, keep raw SQL | actual production helper is `read_host_instance(transaction, host_instance_id)`（按 ID 读单行），非 all-instance stress diagnostic |

**Completion signal**:

> Only exact-replaceable raw SQL is removed: for the current S2 scope, `projection_checkpoint_sequence(...)` is the expected replacement. Remaining raw SQL is explicitly diagnostic-only or fault-injection-only in helper names / docstrings, and each retained helper has the final disposition listed above. No production helper is added solely for tests.

**代码事实验证**:

| 验证点 | 结果 |
|--------|------|
| `read_host_instance` 方法名是否正确 | ✅ `liveness.py:164` — `read_host_instance(self, transaction, host_instance_id)` confirmed |
| projection checkpoint helpers 是否存在 | ✅ `read_projection_checkpoint` (line 87), `ensure_projection_checkpoint` (line 117), `advance_projection_checkpoint` (line 152) all confirmed |
| `force_memory_projection_lag` 是否为 fault injection | ✅ 插入/更新 `checkpoint_event_sequence=0` + `checkpoint_event_id=NULL`，production APIs 不允许 backwards movement |
| `projection_checkpoint_sequence` 是否可替换 | ✅ 可被 `read_projection_checkpoint(transaction, _MEMORY_CONSUMER_ID)` 替换 |
| 其余 7 个 helper 是否正确分类为保留 | ✅ 每个都有具体理由说明为何无 production equivalent |
| completion signal 是否不再暗示广泛减少 | ✅ "Only exact-replaceable raw SQL is removed" |

**PF-02 结论**: ✅ **已关闭**

---

## PF-03: S3 ControllableCancellationToken contract — 验证结果

**控制器要求**:

1. 定义 `ControllableCancellationToken()` 为 open by default。
2. 要求显式 `request_cancel(reason)` 转换到 cancelled；不保留 constructor-as-cancelled 语义。
3. 要求外部调用点迁移到 away from `.trigger(...)`；alias 仅在 helper 内部允许。
4. 显式决定 `tests/service/test_fins_direct.py` 处理方式。
5. 要求 focused helper contract test。

**计划修正文本** (S3):

> `ControllableCancellationToken()` must always construct an open token: `is_cancelled()` is `False`, `cancel_reason()` is `None`, and `requested_at()` is `None`. There must be no constructor-as-cancelled semantics. Existing `StubCancellationToken(reason="...")` style call sites must become explicit two-step setup: construct an open token, then call `request_cancel("...")`.

> `request_cancel(...)` must transition the token from open to cancelled, preserve the first reason and first UTC-aware `requested_at`, and be idempotent on repeated calls.

> Optional aliases such as `trigger()` are allowed only inside the canonical helper, only if they call `request_cancel(...)` with identical semantics, and only after all external call sites have migrated away from `.trigger(...)`.

> Default decision: use `ControllableCancellationToken()` for the existing never-cancelled Service pass-through tests; because it is open by default, callers can leave it unmutated. A local stub is allowed only if the test explicitly needs a non-mutable observation object. If retained, it must be named as an open observation stub, must have no `request_cancel` / `trigger` mutation method, and must not encode cancellation semantics beyond the `CancellationToken` observation protocol.

**Additional S3 helper contract validation**:

> Add or migrate a focused helper contract test for `ControllableCancellationToken` covering:
> - construction starts open: `is_cancelled() is False`, `cancel_reason() is None`, `requested_at() is None`;
> - `request_cancel("reason")` transitions to cancelled and exposes the exact reason;
> - `requested_at()` after cancellation is a timezone-aware UTC `datetime`;
> - repeated `request_cancel(...)` calls are idempotent and preserve the first cancellation observation.
> After S3 migration, `.trigger(...)` must not remain in external Engine / Host / Service test call sites.

**Completion signal**:

> There is one protocol-faithful controllable cancellation token helper for tests. No local Engine runner cancellation fake uses naive `datetime.now()`. Service Fins direct tests no longer define an independent cancellable fake. `tests/service/test_fins_direct.py` uses the canonical open token, or documents a clearly named non-mutable open observation stub with no mutation semantics. A focused helper contract test covers open state, UTC-aware `requested_at`, reason, and idempotent cancellation. No external test call site uses `.trigger(...)`.

**代码事实验证**:

| 验证点 | 结果 |
|--------|------|
| open default 定义 | ✅ 显式列出 `is_cancelled() is False`, `cancel_reason() is None`, `requested_at() is None` |
| 无 constructor-as-cancelled | ✅ "There must be no constructor-as-cancelled semantics" + 现有调用点必须改为两步 setup |
| `request_cancel` 契约 | ✅ transition、preserve first reason、UTC-aware `requested_at`、idempotent |
| `.trigger()` 迁移 | ✅ "all external call sites have migrated away from `.trigger(...)`" — 无 "where feasible" 例外 |
| Service handling | ✅ 显式决定：默认用 canonical open token，保留 local stub 的条件明确 |
| focused helper contract test | ✅ 从条件式 ("if not already covered indirectly") 改为强制式 |
| `StubCancellationToken` 当前语义 | ✅ 代码确认：`__init__(reason)` 设置 `_requested_at = datetime.now(UTC)` 即 constructor-as-cancelled，计划正确要求消除此模式 |
| `FakeCancellationToken` 当前语义 | ✅ 代码确认：`datetime.now()` naive + `trigger()` 方法，计划正确要求消除 |
| `test_dispatch_scheduler.py` 未被添加为 required S3 validation | ✅ 不在 S3 focused validation 列表中 |

**PF-03 结论**: ✅ **已关闭**

---

## PF-04: README no-update branch — 验证结果

**控制器要求**: 添加显式 "if none of the README trigger conditions apply, record `tests/README.md: no update needed`" 分支。

**计划修正文本** (Section 6):

> If none of those README trigger conditions apply, the implementation artifact must explicitly record `tests/README.md: no update needed`.

**PF-04 结论**: ✅ **已关闭**

---

## Rejected Item 验证

**控制器裁决**: `test_dispatch_scheduler.py` 不得被添加为 required S3 validation，除非实施中出现 same-path evidence。

**验证结果**:

| 检查点 | 结果 |
|--------|------|
| `test_dispatch_scheduler.py` 是否出现在 S3 focused validation 列表中 | ❌ 未出现 — 正确 |
| `test_dispatch_scheduler.py` 是否出现在 non-goals 中 | ✅ "No attempt to fix unrelated baseline failures, including known `test_dispatch_scheduler.py` compaction previous-view failures, unless same-path evidence appears" |
| `test_dispatch_scheduler.py` 是否 import `fake_cancellation` | ❌ 代码确认不 import — 它使用 production `_HostCancellationToken` |

**Rejected item 结论**: ✅ **已尊重**

---

## New Material Findings

### RER-01-未修复-低-S1 resume guidance production 常量引用与代码实际不一致

- **位置**: S1 `test_run_input_builder.py` 部分，PF-01 修正文本
- **问题类型**: 代码事实偏差
- **当前写法**: 计划说 "If the production owner exposes stable public constants for these guidance fragments, the helper should assert those constants directly"，暗示可能存在 production 常量。
- **反例/失败场景**: 原始 MiMo review 引用 `_RESUME_WAIT_FALLBACK_INTRO` (run_input.py:3524) 和 `_RESUME_WAIT_FALLBACK_NO_REPEAT` (run_input.py:3528) 作为 production 常量。经代码验证，这些命名常量在当前 `run_input.py` 中不存在——对应文本是内联的。Implementation agent 可能搜索这些常量名称，发现不存在，产生困惑。
- **为什么有问题**: 这不是 plan 修正本身的结构缺陷——plan 的 fallback 逻辑（"If the constants remain private implementation details, the helper may keep exact expected fragments in the test"）正确覆盖了这种情况。但原始 review 中的代码引用已被代码演进漂移，plan fix 未更新这些引用。
- **直接证据**: `grep -r "_RESUME_WAIT_FALLBACK" dayu/` 返回空；`run_input.py` 中无这些命名常量。
- **影响**: 低。Implementation agent 会发现常量不存在，走 fallback 路径，最终结果正确。但搜索过程浪费少量时间。
- **建议改法和验证点**: 实施时直接检查 `run_input.py` 中 resume guidance 文本的来源位置，不依赖 review artifact 中的行号引用。
- **修复风险（低）**: 无需 plan 修改，实施时自行验证。
- **严重程度（低）**: 不阻塞，不影响最终产出正确性。

---

## Residual Risks

| # | Risk | Severity | Tracking |
|---|------|----------|----------|
| R1 | S1 resume guidance 文本在 `run_input.py` 中为内联而非命名常量，实施 agent 需自行定位来源 | 低 | 实施时 `grep` 定位 |
| R2 | S3 迁移涉及多文件调用点变更，pyright 可捕获遗漏 import | 低 | S3 完成后 `grep -r "StubCancellationToken\|FakeCancellationToken" tests/` 确认清空 |
| R3 | `ControllableCancellationToken` focused helper contract test 需新增约 10 行测试 | 低 | S3 completion signal 已覆盖 |

---

## Final Re-Review Conclusion

**PASS**

所有四个 accepted fixes (PF-01..PF-04) 已在修正后的计划中正确落地：

| Fix | 状态 | 验证结论 |
|-----|------|----------|
| PF-01 | ✅ 已关闭 | 两类断言区分清晰，vague substring 被禁止，共享 helper 为 optional |
| PF-02 | ✅ 已关闭 | 8 个 raw SQL helper 逐一列出最终处置，`read_host_instance` 名称正确，checkpoint helpers 已验证，completion signal 已修正 |
| PF-03 | ✅ 已关闭 | open default、显式 request_cancel、无 constructor-as-cancelled、无外部 trigger、Service handling 显式、focused contract test 强制 |
| PF-04 | ✅ 已关闭 | README no-update 分支已显式声明 |
| Rejected item | ✅ 已尊重 | `test_dispatch_scheduler.py` 未被添加为 S3 required validation |

发现一个低严重度的新 material finding (RER-01)：原始 MiMo review 中引用的 `_RESUME_WAIT_FALLBACK_INTRO` / `_RESUME_WAIT_FALLBACK_NO_REPEAT` production 常量在当前代码中不存在（文本为内联）。Plan 的 fallback 逻辑已正确覆盖此情况，不阻塞实施。

计划已达到 code-generation-ready 状态，可进入 implementation gate。
