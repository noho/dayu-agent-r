# WU-OBS-00 Slice 1 Implementation Review Controller Adjudication

```text
status=needs-fix-with-acceptance-blocked
work_unit=WU-OBS-00
slice=S1
review_mimo=docs/reviews/code-review-20260724-124007.md
review_ds=docs/reviews/code-review-20260724-123859.md
accepted_findings=1
rejected_findings=1
next=AgentCodex review fix
```

## Review verdicts

- AgentMiMo：`0 actionable findings`。
- AgentDS：`PASS — 0 actionable findings`，另有 1 个低严重度、非 actionable 防御分支观察。

两路均确认 Slice 1 production 实现符合 accepted plan：public Source 五字段、Host-internal lock
owner、hot-first 同事务快照、锁外 same-handle exact-prefix、物理只读 SQLite、strict
current-schema parser、digest/ref、hot/cold join 与 resolver orchestration 均通过对抗检查。

## Controller findings

### CTRL-S1-IMPL-01 — accepted

`tests/host/test_package_exports.py::test_host_all_matches_current_public_contracts` 仍断言旧
`dayu.host.__all__` 集合，未包含 accepted plan 与当前实现新增的：

- `ToolTraceAnalysisPolicy`
- `ToolTraceAnalysisSource`
- `ToolTraceInputMode`

这是 Slice 1 plan allowlist 漏项，不是 production compatibility 要求。完整 Host suite 因此有
1 个确定性失败。fix gate 只允许同步该 owner-level expected set，并运行该测试、Slice 1 focused
tests、完整 Host tests 与 targeted/full pyright。

### CTRL-S1-IMPL-02 — rejected

AgentDS 观察到 `_read_exact_prefix` 在 production `BufferedReader.read(remaining)` 下不会返回
超过 `remaining` 的 bytes，因此 `len(chunk) > remaining` 分支不可达。Controller 不接受将其
作为 fix：

- 该检查表达 exact-prefix 边界的 fail-closed invariant；
- private binary opener/test seam 的静态契约为 `BinaryIO`，保留防御不产生 fallback 或语义漂移；
- 两路均确认它不影响 correctness，删除只会产生无必要 production churn。

## Frozen blocker

真实 workspace DB schema=`20`，current fresh schema=`24`。该 validation environment blocker
继续冻结 Slice 1 acceptance、保护提交与 Slice 2。fix gate 不得修改真实 workspace、增加旧
schema 兼容读取、使用 raw SQLite、跳过 schema validation、降级为 cold-only 或修改
producer/schema 语义。

## Fix scope

允许修改：

- `tests/host/test_package_exports.py`
- `docs/reviews/wu-obs-00-slice-1-implementation-review-fix-codex.md`

不得修改任何 production 文件、accepted plan/design、README 或其它测试。完成后进入
AgentMiMo / AgentDS 双路 implementation re-review；acceptance 仍由 Controller 在 re-review 后
单独裁决。
