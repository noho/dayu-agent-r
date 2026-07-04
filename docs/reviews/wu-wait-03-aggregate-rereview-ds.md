# WU-WAIT-03 Aggregate Re-Review

## Scope

- Mode: current changes (relative to HEAD)
- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: aggregate re-review
- Source adjudication: `docs/reviews/wu-wait-03-aggregate-deepreview-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-wait-03-aggregate-fix-codex.md`
- Reviewed files:
  - `dayu/host/README.md`
  - `tests/README.md`
  - `docs/host/issues-implementation-control.md`
- Excluded scope: production code, config, test logic (not changed by fix)

## Verification Targets

只验证 controller adjudication 中 accepted 的两个 README sync findings 是否已关闭：

| Finding | Source | Required action |
|---|---|---|
| `tests/README.md` does not reflect external lifecycle wait test coverage | AgentMiMo F01 | Update without WU-specific process text; add current-test-layer coverage for Host cancelled-wait lifecycle abandon diagnostics and Fins observation cancel/abandon runtime behavior. |
| `dayu/host/README.md` does not describe the new Host wait external lifecycle adapter contract | AgentMiMo F02 | Update within existing section responsibilities; describe stable wait adapter lifecycle result types and cancelled WAITING external job cleanup semantics without adding work-unit history or future roadmap. |

## Evidence

### git diff --check

```text
(no output — pass)
```

已由 controller 通过，本次复验一致。

### Changed files

```
dayu/host/README.md                        |  2 ++
docs/host/issues-implementation-control.md | 10 +++++-----
tests/README.md                            |  8 ++++----
3 files changed, 11 insertions(+), 9 deletions(-)
```

无代码、配置或测试逻辑文件变更。与 fix-codex 声明一致。

### dayu/host/README.md diff

在 Waiting 节 Production wait poller 段落后新增一个段落（`dayu/host/README.md:381-382`）：

- 描述 cancel command transaction 只写 Host durable wait/Run/Attempt 事实，不在事务内执行 provider I/O。
- 描述 production wait poller 在 cancelled wait row 上 claim 后调用 provider wait adapter 的 external lifecycle 端口。
- 列出三类封闭 lifecycle 结果：`WaitExternalJobLifecycleApplied`、`WaitExternalJobLifecycleUnsupported`、`WaitExternalJobLifecycleNoop`。
- 描述 Host poller 折叠为有界 durable outcome：`abandoned`、`abandon_unsupported`、`abandon_noop`，adapter 异常记录为 `error`/`abandon_error` 并按 backoff 重试，缺失 adapter 记录为 missing-adapter retry 诊断。
- 描述 Fins 当前使用 `ABANDON` 语义做 best-effort observation cancel/cleanup，Host 不把 Fins observation 细节写入自身业务事实。

### tests/README.md diff

三处覆盖描述补充，均为对已有 coverage 段落的内联追加：

1. `tests/fins/` 总括段（行 179）：追加 `observation cancel / abandon 的 valid、corrupt token、missing observation、LOST snapshot、non-transient error 与 transient unavailable 分支`。
2. `test_fins_ingestion_tools.py` 段（行 183）：追加 `abandon 对 valid、corrupt token、missing observation、LOST snapshot、non-transient error 和 transient unavailable 的分支处理`。
3. `test_fins_ingestion_runtime.py` 段（行 185）：追加 `prepared observation cancel 后 abandon 不提交后台操作且释放 handle、submitted observation abandon 触发协作取消并保留已写入仓储产物`。
4. `tests/host/` public run/wait/event API 段（行 194）：追加 `cancelled WAITING wait external lifecycle applied / unsupported / noop / error / missing-adapter / CAS / late-result 处理、wait lifecycle outcome schema`。

### docs/host/issues-implementation-control.md diff

Gate 状态追踪更新：`gate: accepted-slice → aggregate-rereview`，WU-WAIT-03 status `accepted-slice → review`，implementation status 与 next entry point 同步更新为 aggregate README fix completed / aggregate re-review gate。WU-WAIT-03 状态节追加 aggregate deepreview artifacts、controller adjudication、fix artifact 与当前 gate 记录。均为正常控制文档追踪更新，无代码/配置/测试逻辑变更。

## Findings

### 判断点 1：dayu/host/README.md 是否在现有约束下说明当前 Host wait external lifecycle adapter contract，且不写 WU 历史/未来路线图

**通过。** 新增段落位于 Waiting 节内，与现有 Production wait poller 段落相邻，符合 README 自身 `Agent更新约束【必须遵守】` 中的"按本文档现有章节职责写作"要求。内容描述当前已实现的 cancelled WAITING poller lifecycle adapter contract：cancel transaction 不执行 provider I/O、poller 调用 external lifecycle 端口、三类 lifecycle 结果、有界 durable outcome 映射、Fins ABANDON 语义。使用 `WaitExternalJobLifecycleApplied` 等已实现类型名，与 README 全文使用内部类型名的风格一致（如 `ResolveWaitRequest`、`WaitCallbackCompletionEnvelope`、`CallbackWaitResolvePort`）。未出现 WU 编号、slice 编号、PR 编号、issue 引用、未来路线图或未落地能力描述。

### 判断点 2：tests/README.md 是否说明当前 Host/Fins external lifecycle wait 测试覆盖，且不写 WU 流水账

**通过。** 四处修改均为对已有 coverage 段落的内联事实追加，描述当前 `tests/host/` 和 `tests/fins/` 下已存在的测试覆盖行为：Host 侧 cancelled-wait lifecycle applied/unsupported/noop/error/missing-adapter/CAS/late-result；Fins 侧 observation cancel/abandon 各分支。文本风格与所在段落原有逗号分隔的覆盖枚举一致。未出现"WU-WAIT-03"、slice、gate、PR、issue 引用或流水账式过程描述。

### 判断点 3：是否有代码/config/test logic 意外改动，README 文本是否误导或越界

**无意外改动。** `git diff --stat HEAD` 仅三个文件变更，均为文档。无 `.py`、`.json`、`.yaml`、`.toml` 或测试 fixture 变更。README 文本未引入误导或越界内容：

- `dayu/host/README.md` 新增段落描述的行为与 fix-codex 记录和已知 WU-WAIT-03 Slice 1/2 实现一致。使用的 durable outcome 名称（`abandoned`、`abandon_unsupported`、`abandon_noop`）与实际 schema 一致。Fins ABANDON 语义描述准确。
- `tests/README.md` 追加的覆盖项与当前 `test_wait_poller_runtime.py`、`test_wait_cancel_late_result.py`、`test_fins_ingestion_tools.py`、`test_fins_ingestion_runtime.py` 中实际存在的测试用例一致。
- `docs/host/issues-implementation-control.md` 的 gate 追踪更新准确反映当前 aggregate re-review gate 状态，WU-WAIT-03 状态节记录与已完成的 aggregate deepreview / fix artifacts 一致。

### 判断点 4：git diff --check 已由 controller 通过

**通过。** 复验 `git diff --check HEAD` 无输出（pass）。

## Accepted Findings Closure

| Finding | Status | Evidence |
|---|---|---|
| `dayu/host/README.md` wait external lifecycle adapter contract sync | **closed** | `dayu/host/README.md:381-382` 新增段落描述 cancelled WAITING poller lifecycle adapter contract，三类 lifecycle 结果、有界 durable outcome 映射、Fins ABANDON 语义。无 WU 历史/路线图。 |
| `tests/README.md` external lifecycle wait coverage sync | **closed** | `tests/README.md` 四处内联追加 Host cancelled-wait lifecycle 与 Fins observation cancel/abandon 覆盖描述。无 WU 流水账。 |

## Verdict

**pass** — 0 blocking findings.

两个 accepted README sync findings 均已关闭。变更范围严格限定于文档文本，未触及代码、配置或测试逻辑。README 文本在各自约束下准确描述当前实现事实，无误导或越界。`git diff --check` 通过。

## Residual Risk

- 无。本轮 re-review 范围内未发现新的 material finding、未覆盖区域或文档与实现不一致。
- Controller adjudication 中原有的三个 residual risks（provider lifecycle best-effort、poller-disabled deployments、future CANCEL/REVOKE granular diagnostics）不属于 README sync scope，状态不变。
