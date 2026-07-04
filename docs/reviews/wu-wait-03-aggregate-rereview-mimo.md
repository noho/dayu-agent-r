# WU-WAIT-03 Aggregate Re-Review — AgentMiMo

## Scope

- Mode: current changes
- Branch: `phase/wu-wait-03-issue-92`
- Base: `main`
- Output file: `docs/reviews/wu-wait-03-aggregate-rereview-mimo.md`
- Included scope: verification of two accepted README sync fixes from `docs/reviews/wu-wait-03-aggregate-deepreview-controller-adjudication.md`
- Excluded scope: code / config / test logic changes (not part of README fix scope)
- Parallel review coverage: 无

## Verification Target

Controller adjudication accepted two README sync findings:

| Finding | Source | Required Action |
|---|---|---|
| `tests/README.md` does not reflect external lifecycle wait test coverage | AgentMiMo F01 | Update without WU-specific process text; add current-test-layer coverage for Host cancelled-wait lifecycle abandon diagnostics and Fins observation cancel / abandon runtime behavior. |
| `dayu/host/README.md` does not describe the new Host wait external lifecycle adapter contract | AgentMiMo F02 | Update within existing section responsibilities; describe stable wait adapter lifecycle result types and cancelled WAITING external job cleanup semantics without adding work-unit history or future roadmap. |

## Findings

未发现实质性问题。

### Verification Detail

#### F02 — `dayu/host/README.md` wait external lifecycle adapter contract

**文件**: `dayu/host/README.md` (unstaged diff, inserted after line 380)

**新增段落内容核对**:

- 位于 `### Waiting` section 内，`### Context governance` 之前，符合"按现有章节职责写作"约束。
- 描述了 cancel command transaction 只写 Host durable facts、不执行 provider I/O — 正确。
- 描述了 production wait poller 在 cancelled wait row 上 claim 后调用 provider wait adapter 的 external lifecycle 端口 — 正确。
- 列出三类封闭结果：`WaitExternalJobLifecycleApplied`、`WaitExternalJobLifecycleUnsupported`、`WaitExternalJobLifecycleNoop` — 与 `dayu/host/wait_adapter.py` 中定义一致。
- 描述了 Host poller 折叠成有界 durable outcome：`abandoned`、`abandon_unsupported`、`abandon_noop`；异常记录为 `error` / `abandon_error` 诊断 — 正确。
- 描述了 Fins 使用 `ABANDON` 语义做 best-effort observation cancel / cleanup — 正确。
- 未添加 WU 历史、未来路线图、安装指南或测试清单。
- 文本属于 LLM-facing 语义说明，不包含内部治理标识泄漏。

**判定**: F02 已关闭。

#### F01 — `tests/README.md` external lifecycle wait coverage

**文件**: `tests/README.md` (unstaged diff, 4 处修改)

**修改 1 — `tests/fins/` 总述段**:

- 新增 "observation cancel / abandon 的 valid、corrupt token、missing observation、LOST snapshot、non-transient error 与 transient unavailable 分支" — 覆盖了 Slice 2 新增的 abandon 分支测试场景。
- 替换了原 "abandon wait 请求 observation cancellation & cleanup" 简述。

**修改 2 — `test_fins_ingestion_tools.py` 描述**:

- 新增 "abandon 对 valid、corrupt token、missing observation、LOST snapshot、non-transient error 和 transient unavailable 的分支处理" — 精确对应当前测试覆盖。

**修改 3 — `test_fins_ingestion_runtime.py` 描述**:

- 新增 "prepared observation cancel 后 abandon 不提交后台操作且释放 handle、submitted observation abandon 触发协作取消并保留已写入仓储产物" — 对应 Slice 2 新增的 cancel-side runtime 行为测试。

**修改 4 — `tests/host/` public run / wait / event API 描述**:

- 新增 "cancelled WAITING wait external lifecycle applied / unsupported / noop / error / missing-adapter / CAS / late-result 处理、wait lifecycle outcome schema" — 精确对应 Slice 1 新增的 Host wait lifecycle 测试覆盖。

**整体判定**:

- 未添加 WU 流水账或过程状态。
- 描述只反映当前已存在的测试覆盖事实。
- 不包含误导或越界文本。

**判定**: F01 已关闭。

#### 意外改动检查

- `git diff --check` 已由 controller 通过，本次 re-verify 确认无 whitespace error。
- unstaged changes 仅涉及 `dayu/host/README.md`、`tests/README.md`、`docs/host/issues-implementation-control.md` 三处 README / 控制文档。
- 无代码、配置或测试逻辑意外改动。
- `docs/host/issues-implementation-control.md` 的 gate 状态更新属于正常总控推进，不引入架构决策或越界内容。

## Verdict

**pass** — 两个 accepted findings 均已关闭，无 blocking finding，无意外改动。

## Blocking Findings Count

0

## Accepted Findings Closure Status

| Finding | Status |
|---|---|
| `tests/README.md` external lifecycle wait coverage sync (F01) | closed |
| `dayu/host/README.md` wait external lifecycle adapter contract sync (F02) | closed |

## Residual Risk

- Provider lifecycle cleanup 仍然是 best-effort 且 provider-specific。
- Poller-disabled deployments 不会执行 external lifecycle adapter actions，直到 production polling 配置启用。
- 未来实现 `CANCEL` 或 `REVOKE` 的 provider adapters 可能需要更细粒度的 durable diagnostics，如果运维需要 action-level 区分。

上述 residual risks 与 controller adjudication 记录一致，不属于当前 WU blocking scope。
