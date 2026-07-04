# Code Review — WU-WAIT-03 PR #166

## Scope

- Mode: PR
- PR: [#166](https://github.com/noho/dayu-agent-r/pull/166)
- Title: WU-WAIT-03: external wait lifecycle abandon target
- Author: noho
- Head branch: `phase/wu-wait-03-issue-92`
- Base branch: `main`
- Draft: **true**
- State: OPEN
- Review decision: (none — no reviews submitted)
- URL: https://github.com/noho/dayu-agent-r/pull/166
- Output file: `docs/reviews/wu-wait-03-pr-166-review-mimo.md`
- Included scope: PR diff against `main`（36 个文件，+3749/-39 行）
- Excluded scope: 无
- Parallel review coverage: 无，本 review 由单一 reviewer 沿全部关键路径逐行走读
- Design sources consulted:
  - `docs/host/design.md`（Host 分层边界、治理真源）
  - `docs/engine/design.md`（Engine 不拥有 wait record / external job lifecycle）
  - `docs/host/issues-implementation-control.md`（WU-WAIT-03 实施编排状态）
  - `docs/host/wu-wait-03-external-job-lifecycle-plan.md`（accepted plan 真源）

## PR Metadata 核对

| 项目 | 实际值 | 预期值 | 判定 |
|---|---|---|---|
| PR URL | `https://github.com/noho/dayu-agent-r/pull/166` | — | ✅ |
| PR body `Closes #92` | 第 30 行 `Closes #92` | 必须包含 | ✅ |
| Draft status | `true` | draft PR gate 阶段应为 draft | ✅ |
| Review decision | 空（无 review submitted） | — | ℹ️ 当前无 reviewer feedback |
| Checks | `no checks reported on the 'phase/wu-wait-03-issue-92' branch` | — | ℹ️ 无 CI 阻塞 |

## PR Body 核对

PR body 包含：

- **Summary**: 4 条变更描述，准确覆盖 Host lifecycle contract、poller diagnostics、Fins adapter mapping、README 更新。
- **Validation**: 列出 6 条 pytest / pyright / git diff --check 命令，与本地实际验证一致。
- **Review Artifacts**: 列出 plan、slice 1/2 review/fix/re-review artifacts、aggregate deepreview artifacts，与 `docs/reviews/` 下文件一致。
- **Residual Risks**: 3 条（provider lifecycle best-effort、poller-disabled deployments、future CANCEL/REVOKE granularity），与 plan 和 aggregate review 记录一致。
- **Closes #92**: 存在，merge 时会自动关闭 issue。

## Verdict

**pass** — 未发现 blocking findings。PR diff 完整实现 WU-WAIT-03 accepted plan，state machine 无回归，Host/Fins 分层边界干净，durable schema 变更安全，测试覆盖充分。

Blocking findings count: **0**
Required fixes: **无**
可 final closeout: **是**（PR body 准确，checks 无阻塞，实现与 plan 对齐，所有 gate artifacts 完整）

## Findings

未发现实质性问题。

## 逐项核对

### 1. PR diff 是否完整实现 WU-WAIT-03 accepted plan

**通过。** 逐项对照 plan 的两个 implementation slices：

#### Slice 1: Host Lifecycle Contract And Poller Diagnostics

| Plan 要求 | 实现状态 | 证据 |
|---|---|---|
| `WaitExternalJobLifecycleAction(StrEnum)` 定义 `CANCEL/REVOKE/ABANDON` | ✅ | `dayu/host/wait_adapter.py:77-82` |
| `WaitExternalJobLifecycleApplied` dataclass | ✅ | `dayu/host/wait_adapter.py:86-108`，含 `__post_init__` 校验 |
| `WaitExternalJobLifecycleUnsupported` dataclass | ✅ | `dayu/host/wait_adapter.py:110-128`，含 `__post_init__` 校验 |
| `WaitExternalJobLifecycleNoop` dataclass | ✅ | `dayu/host/wait_adapter.py:130-148`，含 `__post_init__` 校验 |
| `WaitExternalJobLifecycleResult` TypeAlias 封闭联合 | ✅ | `dayu/host/wait_adapter.py:149-153` |
| `WaitPollAdapter.abandon_wait(...)` 返回类型更新 | ✅ | `dayu/host/wait_adapter.py:196-213`，docstring 更新 |
| `WaitPollLastOutcome.ABANDON_UNSUPPORTED` / `ABANDON_NOOP` | ✅ | `dayu/host/durable/state.py:187-188` |
| Schema CHECK constraint 新增枚举值 | ✅ | `dayu/host/durable/schema.py:725-726`，`HOST_SCHEMA_VERSION=19` |
| `mark_wait_record_poll_abandoned(...)` 参数化 `last_outcome` | ✅ | `dayu/host/durable/state.py:2211`，keyword-only，默认 `ABANDONED` |
| `_abandon_cancelled_wait(...)` 分类处理三种 lifecycle result | ✅ | `dayu/host/wait_adapter.py:983-1018`，含 `_last_outcome_for_lifecycle_result` 映射 |
| `_last_outcome_for_lifecycle_result()` 映射函数 | ✅ | `dayu/host/wait_adapter.py:1356-1372`，封闭联合 + TypeError defensive raise |
| `__all__` 导出新类型 | ✅ | `dayu/host/wait_adapter.py:1548-1552` |
| `_MarkWaitRecordAbandonedOperation` 更新 `last_outcome` 字段 | ✅ | `dayu/host/wait_adapter.py:564-567` |
| Host 测试更新（adapter 返回类型、新枚举测试、CAS conflict、late result） | ✅ | `tests/host/test_wait_adapter_polling.py` +345 行，`test_wait_poller_runtime.py` +17 行，`test_wait_cancel_late_result.py` 未修改（行为不变），`test_durable_schema.py` +6 行，`test_wait_record_state.py` +38 行 |

#### Slice 2: Fins Adapter/Runtime Mapping And Provider-focused Tests

| Plan 要求 | 实现状态 | 证据 |
|---|---|---|
| `FinsIngestionWaitPollAdapter.abandon_wait(...)` 返回 `WaitExternalJobLifecycleResult` | ✅ | `dayu/fins/ingestion/wait_adapter.py:150-189` |
| Valid handle → `WaitExternalJobLifecycleApplied(action=ABANDON)` | ✅ | 行 170-179，调用 `cancel_observation` + `abandon_observation` |
| Corrupt token → `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")` | ✅ | 行 165-168，`_handle_from_wait_record` 返回 None |
| Missing observation / LOST → `WaitExternalJobLifecycleNoop(reason="observation_missing")` | ✅ | 行 171-174（LOST snapshot），行 183-186（PERMANENT_NOT_FOUND） |
| Non-transient observation error → `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")` | ✅ | 行 187-189，`_observation_error_reason` helper |
| TRANSIENT_UNAVAILABLE → re-raise | ✅ | 行 181-182 |
| `_observation_error_reason` helper | ✅ | `dayu/fins/ingestion/wait_adapter.py:375-387` |
| LLM-facing 文本不泄漏 internal ids | ✅ | `_ABANDON_APPLIED_MESSAGE` 不含 `finsobs_` 前缀 |
| Fins 测试覆盖各分支 | ✅ | `tests/fins/test_fins_ingestion_tools.py` +136 行，`test_fins_ingestion_runtime.py` +151 行 |

### 2. State machine / durable schema / Host/Fins boundary regression

**无回归。**

- `cancel_waiting_run_in_transaction(...)` 未被修改。Host cancel command path 不调用 provider I/O。
- Durable schema 变更为 additive：`HOST_SCHEMA_VERSION` 18→19，CHECK 约束新增 `'abandon_unsupported'` 和 `'abandon_noop'`。无新增 column/table/index。
- `WaitPollLastOutcome` 新枚举值的 StrEnum value-based serialization/deserialization 正确：`serialize_wait_poll_last_outcome` 写入 `enum.value`，`deserialize_wait_poll_last_outcome` 通过枚举成员集验证。
- `mark_wait_record_poll_abandoned(...)` 的参数化保持现有调用者兼容：`last_outcome` keyword-only，默认 `WaitPollLastOutcome.ABANDONED`。
- Fins adapter 通过 Host adapter protocol import `dayu.host.wait_adapter` 类型，不是新的反向依赖——`main` 分支上 Fins adapter 已 import `dayu.host`。
- Engine public contract 无变更。
- `resolve_wait(...)` late-result rejection 路径未被修改。

### 3. PR body 是否准确描述变更、验证、review artifacts、residual risk

**通过。**

- Summary 4 条变更描述与实际 diff 一致。
- Validation 6 条命令与本地验证结果一致（35 passed / 126 passed / 60 passed / pyright 0 errors / git diff --check passed）。
- Review Artifacts 列出 plan → slice 1/2 → aggregate deepreview 全链路 artifacts，文件均存在于 `docs/reviews/`。
- Residual Risks 3 条与 plan 和 aggregate review 一致。
- `Closes #92` 存在。

### 4. Checks / reviews 状态

- `gh pr checks 166`: `no checks reported on the 'phase/wu-wait-03-issue-92' branch`。无 CI 阻塞。
- `gh pr view 166 --json reviews`: 无 reviewer feedback。
- Draft status 正确。

### 5. 本地验证

| 验证项 | 结果 |
|---|---|
| `pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q` | 35 passed |
| `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` | 126 passed（3 edgar deprecation warnings） |
| `pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py -q` | 60 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |

## Open Questions

无。

## Residual Risk

记录 plan 和 aggregate review 已识别的 residual risks，当前 review 不新增：

1. **Provider lifecycle cleanup 仍为 best-effort**: 部分 provider 可能不支持 physical cancel。Owner: provider-specific adapter owners under #92/#87。
2. **Poller-disabled 部署不执行 external lifecycle**: `WaitPollerRuntimePolicy.enabled=False` 时，cancelled wait 的 provider cleanup 不执行。Owner: Service composition / WU-WAIT-04。
3. **Running Fins 操作只在 checkpoint 响应取消**: cooperative cancellation 仅在下一次 `cancellation_checker()` 调用时生效。Owner: Fins provider/runtime owners。
4. **Future CANCEL/REVOKE durable 区分**: `_last_outcome_for_lifecycle_result()` 对三种 action 都映射为 `ABANDONED`，如未来有 adapter 实现 CANCEL/REVOKE，可能需要 durable outcome 区分。Owner: future adapter/schema work。

## Gate 状态判定

| 检查项 | 判定 |
|---|---|
| PR diff 完整实现 accepted plan | ✅ 通过 |
| State machine / durable schema / Host/Fins boundary 无回归 | ✅ 通过 |
| PR body 准确且含 `Closes #92` | ✅ 通过 |
| Checks 无 CI 阻塞 | ✅ 通过（无 checks reported） |
| Reviews 无阻塞 feedback | ✅ 通过（无 reviews） |
| Correctness / testing / README/doc sync 无阻塞问题 | ✅ 通过 |
| Residual risk 已归属 | ✅ 通过 |

**结论**: PR #166 可进入 final closeout gate。
