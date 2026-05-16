# P1-P7 Design Conformance Fix：Awaiting Production Wiring

- 日期：2026-05-16
- 分支：`fix/host-p1-p7-awaiting-production-wiring`
- Base：`main` merge commit `c39de2e`
- Controller adjudication：`docs/reviews/p1-p7-design-conformance-controller-adjudication-20260516.md`
- Accepted blocking finding：C-P1P7-001，P7 awaiting production wiring 未接入 `HostDispatchScheduler`

## 结论

已修复 C-P1P7-001。

真实本地 dispatch production path 现在可以在 tool-enabled configuration 下把 `ToolAwaitingOutcome` 提交到 Host awaiting accept path：`HostDispatchScheduler` 构造 `ToolRuntimeBuildRequest` 时注入 `DefaultHostToolAwaitingAcceptPort` 与 Host construction 阶段提供的 `WaitAdapterRegistry`。adapter object 仍只存在于 composition/runtime 层，不进入 per-run request，也不进入 durable wait row。

## 改动

- `dayu/host/tooling.py`
  - `HostToolingOptions` 新增 `wait_adapter_registry: WaitAdapterRegistry | None`。
  - 该字段属于 Host construction / composition 输入，和业务 `ToolBundle`、framework policy 同层。
  - 使用 `TYPE_CHECKING` 导入 `WaitAdapterRegistry`，避免 `api -> tooling -> wait_adapter -> api` 运行期循环依赖。

- `dayu/host/dispatch.py`
  - `HostDispatchScheduler._run_input_builder_for_dispatch(...)` 在 tool-enabled production path 中注入：
    - `DefaultHostToolAwaitingAcceptPort(transaction_runner=..., event_log_store=...)`
    - `wait_adapter_registry=tooling_options.wait_adapter_registry`
  - 未配置 `wait_adapter_registry` 时仍保持现有受治理 awaiting configuration failure 行为；普通工具结果 path 不变。

- `tests/host/test_phase7_waiting_integration.py`
  - 新增 scheduler-level integration test。
  - 测试路径：public `ensure_session` / `start_run` -> `HostDispatchScheduler` -> production ToolRuntime -> awaiting business tool -> Run `WAITING` / Attempt `SUSPENDED` / active wait record -> public `resolve_wait` -> resume Run 与 resume dispatch record。
  - 测试不直接手工构造 `ToolRuntimeBuildRequest`，覆盖此前缺失的 production wiring 断点。

- `dayu/host/README.md`
  - 更新当前 HostDispatchScheduler tool-enabled wiring 说明，补充 `HostToolingOptions.wait_adapter_registry` 启用 awaiting production path 的事实。

- `tests/README.md`
  - 更新 Host 测试覆盖说明，加入真实 scheduler awaiting production wiring。

- `docs/host/implementation-control.md`
  - 记录本 fix gate、修复方向与 non-goals。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_phase7_waiting_integration.py tests/host/test_dispatch_scheduler.py tests/host/test_tooling_options.py tests/host/test_public_contracts.py -q`
  - 60 passed

- `source .venv/bin/activate && pytest tests/host -q`
  - 392 passed

- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 0 errors, 0 warnings, 0 informations

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings, 0 informations

- `git diff --check`
  - 通过

## 残余风险

- 本 fix 不实现 callback endpoint、poller 后台循环、recovery scan、remote worker、external job physical cancel / revoke。
- `create_host_command_handle(..., local_execution=...)` 仍不是本次范围；scheduler lifecycle wiring 仍需后续 composition gate 处理。
- Poller retry 幂等 digest、in-flight fencing、Engine accepted refs 强校验、manual audit projection 仍沿用 Phase 7 accepted residual owners。
