# P10.5 Aggregate Re-Review Controller Adjudication

## Verdict

P10.5 aggregate fix accepted。

AgentMiMo re-review：PASS，blocking findings count = 0。
AgentDS re-review：PASS，blocking findings count = 0。

Controller 裁决：AG1-AG4 已完整收口，`dayu.host` 包根不再通过模块属性或 `__all__` 暴露低层 command primitive、command-handle construction types、`HostLocalExecutionOptions` 与 `StartRunRequest`。低层测试已迁移到 `dayu.host.api` / `dayu.host.command`，README 已同步当前 public contract 事实。当前可以进入 accepted aggregate fix commit。

## Accepted Evidence

- `dayu/host/__init__.py` 不再导入或导出 `start_run`、`create_host_command_handle`、`HostCommandHandle`、`HostCommandFacet`、`HostCommandHandleOptions`、`HostLocalExecutionOptions`、`StartRunRequest`。
- `tests/host/test_package_exports.py` 同时检查 removed low-level symbols 不在 `dayu.host.__all__` 且不在 `vars(dayu.host)`。
- 需要低层符号的 tests 已从 `dayu.host.api` 或 `dayu.host.command` 导入；未新增兼容 re-export / wrapper。
- `dayu/README.md` 与 `dayu/host/README.md` 明确低层符号不属于 `dayu.host` 包根 ordinary Service-facing public surface。

## Validation

Controller 本地复跑：

```bash
source .venv/bin/activate && pytest tests/host/test_package_exports.py -q
# 8 passed

source .venv/bin/activate && pytest tests/host -q
# 696 passed, 1 skipped

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```

AgentDS 同样复跑 `tests/host/test_package_exports.py`、`tests/host`、`pyright dayu/host tests/host` 与 `git diff --check` 并全部通过。

AgentMiMo 复跑 `tests/host/test_package_exports.py` 与 pyright 通过；其 `tests/host` 运行中 `test_mimo_public_real_runner_two_turn_path` 因外部 provider 返回 `finish_reason=length` 失败。该测试未被本次 aggregate fix 修改，且 controller / DS 本地 `tests/host` 已通过，因此裁决为 provider 环境 residual，不阻塞 AG1-AG4 收口。

## Residual Risks

- 全仓测试未运行；当前 gate 验证范围为 `dayu/host` 与 `tests/host`，符合本次 public surface 收口范围。
- `HostEventView` / `HostEventStream` 仍在 `dayu.host.api.__all__`，已在 aggregate deepreview 裁决中 deferred，不阻塞 `dayu.host` 包根 service-facing freeze。
- 跨测试模块私有 helper 依赖与 scheduler 私有方法测试依赖 deferred 到 Phase 11 test hardening。
