# P10.5 Aggregate Deepreview Controller Adjudication

## Verdict

不直接进入 ready-to-open-draft-PR。当前进入 P10.5 aggregate fix。

MiMo aggregate deepreview：PASS，blocking count = 0，提出 2 个 Medium public surface finding。
DS aggregate deepreview：PASS，blocking count = 0，认为可进入 ready-to-open-draft-PR，但同样列出 public surface cleanup findings。

Controller 裁决：P10.5 的第一目标是冻结 ordinary local multi-turn 的 Service-facing public contract。`start_run` / `create_host_command_handle` / command-handle construction types / local execution options 仍从 `dayu.host` 包根可导入或在 `__all__` 中出现，会削弱该目标。即使 reviewers 标记为不阻塞，基于 design_doc 的 public namespace 边界与 plan 明确要求，本项应在 P10.5 aggregate fix 内收口，而不是留到 draft PR 后。

## Accepted Findings

### AG1 — Root namespace still exposes demoted low-level command primitives

来源：MiMo M2、DS H1。

裁决：接受为 aggregate fix。

要求：

- 从 `dayu.host` 包根移除 `start_run` 与 `create_host_command_handle` 模块属性，不仅仅是移出 `__all__`。
- 低层测试如仍需这些符号，必须从 `dayu.host.command` 等内部 / 低层模块路径导入。
- 不新增兼容 re-export / wrapper。

### AG2 — Root `__all__` still contains command-handle construction types

来源：MiMo L2、DS H2。

裁决：接受为 aggregate fix。

要求：

- 从 `dayu.host.__all__` 移除 `HostCommandFacet`、`HostCommandHandleOptions` 等低层 command-handle construction types。
- 低层测试如仍需这些类型，应从 `dayu.host.api` 导入。

### AG3 — Root namespace still exposes internal local execution type

来源：MiMo M1、DS H3。

裁决：接受为 aggregate fix。

要求：

- 从 `dayu.host` 包根模块属性移除 `HostLocalExecutionOptions`。
- `HostLocalExecutionOptions` 可继续保留在 `dayu.host.api` 作为低层 internal / test boundary，除非实现 agent 发现无需保留。
- README / package export tests 必须同步。

### AG4 — Service-facing root should not expose `StartRunRequest`

来源：DS M3 与 design_doc §11。

裁决：接受为 aggregate fix。

要求：

- 从 `dayu.host.__all__` 与包根模块属性移除 `StartRunRequest`。
- 低层 admission / command tests 如仍需此 request type，应从 `dayu.host.api` 导入。

## Deferred Findings

- 跨测试模块私有 helper 依赖：defer 到 Phase 11 test hardening。
- scheduler `_run_pre_start_governance` 私有方法测试依赖：defer 到 Phase 11 scheduler test hardening。
- `HostEventView` / `HostEventStream` 在 `dayu.host.api.__all__`：defer；它们已不在 Service-facing `dayu.host.__all__`。
- Provider / compactor quota skip residual：accepted environment residual，非 Host public contract residual。

## Required Validation

Aggregate fix agent 必须运行：

```bash
source .venv/bin/activate && pytest tests/host/test_package_exports.py -q
source .venv/bin/activate && pytest tests/host -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```
