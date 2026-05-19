# P10.5 Slice 1 Code Review

## Gate

- Work unit: Phase 10.5 Ordinary Local Multi-turn Public Contract Freeze
- Gate: P10.5 Slice 1 code review
- Slice: Public Opener Types, Export Boundary And Options
- Review agent: MiMo
- Date: 2026-05-18

## Review Target

- 当前工作区 uncommitted Slice 1 diff，相对 HEAD (`f38540b`)
- Changed files:
  - `dayu/host/api.py`：新增 `OrdinaryRunExecutionBaseline`、`CompactorExecutionBaseline`、`OpenHostOptions`、`HostEventKind`、`HostTerminalStatus`、`HostFinalAnswerView`、`HostEvent`、`HostClosedError`、`Host` Protocol、`HostHandle` TypeAlias；`__all__` 补齐新类型
  - `dayu/host/open_host.py`（新增）：`open_host(options)` async context manager 骨架
  - `dayu/host/__init__.py`：新增 public imports、`__all__` 移除 7 个旧 Service-facing 导出、新增 `open_host` 与新类型
  - `tests/host/test_public_open_host_options.py`（新增）：options 校验、frozen slots 断言、HostEvent terminal contract、open_host 骨架边界
  - `tests/host/test_package_exports.py`：补齐 removed symbols 断言、ROOT_INTERNAL_API_NAMES 逻辑
  - `docs/host/implementation-control.md`：gate 状态推进
  - `dayu/host/README.md`：公共命名空间描述同步

## Approved Plan Reference

`docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md` §Slice 1

## Design Truth Reference

`docs/host/design.md` §11 (Service-facing opener / public handle / HostEvent typed view)

---

## Findings

### N1. Removed symbols 仍可通过 `from dayu.host import X` 直接导入 —— Non-blocking

**严重程度**: Non-blocking / Accepted residual risk

**证据**:
- `dayu/host/__init__.py` 仍从 `dayu.host.command` 导入 `HostCommandHandle`、`create_host_command_handle`、`start_run`，从 `dayu.host.read_api` 导入 `stream_run_events`，从 `dayu.host.api` 导入 `HostEventStream`、`HostEventView`、`HostLocalExecutionOptions`。
- 这些符号已从 `__all__` 移除，`from dayu.host import *` 不再导出它们；但 `from dayu.host import HostCommandHandle` 等直接导入仍可用。
- 8 个现有测试文件（`test_command_handle.py`、`test_public_event_stream.py`、`test_public_run_api.py`、`test_phase7_waiting_integration.py`、`test_phase5_local_execution_integration.py`、`test_public_contracts.py`、`test_public_session_api.py`、`test_active_cancel_dispatch.py`）仍从 `dayu.host` 直接导入这些符号。

**影响**: `__all__` 移除对 `from dayu.host import *` 生效，但直接导入路径未断开。现有低层测试无需迁移即可继续运行，但 Service-facing 边界隔离仅为约定级别，非 import 级别。

**修复建议**: 无需本 slice 修复。Implementation artifact 已明确记录为 residual risk：现有低层测试的导入路径迁移属于后续 slice 的 allowed test file set。当后续 slice 修改这些测试文件时，应将导入路径从 `dayu.host` 改为内部模块路径（如 `dayu.host.command`、`dayu.host.api`）。

**Plan alignment**: Plan §Slice 1 Non-goals 与 Residual Risks 明确承认此状态："existing low-level command functions and diagnostic stream types remain importable from their internal modules... Service-facing star import / `__all__` no longer exposes them."

---

## Verification Checklist

### Slice 1 scope compliance

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 仅实现 Slice 1 scope | PASS | 无 Slice 2 runtime wiring、scheduler wakeup、live fanout、Session wrappers、steer/retry/replay、resolve_wait、compactor wiring 或 ToolRuntime behavior 变更 |
| 不进入 Engine contract | PASS | diff 不涉及 `dayu/engine/` |
| 不引入 schema/state-machine/persistence 变更 | PASS | 不涉及 `dayu/host/durable/` |
| 不引入 ConfigLoader 或 service locator | PASS | 所有 required fields 均为显式 typed fields |
| `open_host` 骨架未假装 runtime 可用 | PASS | `__aenter__` raise `NotImplementedError` |

### Type surface compliance

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| `OrdinaryRunExecutionBaseline` frozen slots dataclass | PASS | `api.py` L855+；含 `runner_spec: RunnerSpec`、`runner_options: RunnerCallOptions`、`agent_policy: AgentPolicy`；`__post_init__` 校验 isinstance |
| `CompactorExecutionBaseline` frozen slots dataclass | PASS | `api.py` L883+；含 `context_compactor`、`compactor_runner_spec/options`、`compactor_policy_ref`、`compact_artifact_root`；`__post_init__` 校验 path/bool/runner type |
| `OpenHostOptions` frozen slots dataclass | PASS | `api.py` L915+；27 个字段覆盖 plan 所列全部 construction-time 项；`__post_init__` 校验全部字段类型与语义约束 |
| `HostClosedError` standalone lifecycle exception | PASS | `api.py` L2538+；继承 `Exception`；`__init__` 校验 message 非空 |
| `Host` Protocol（异步 handle） | PASS | `api.py` L2621+；13 个 async 方法覆盖 plan 所列 public commands；不含 store/scheduler/registry internals |
| `HostHandle: TypeAlias = Host` | PASS | `api.py` L2715 |
| `HostEventKind` / `HostTerminalStatus` StrEnum | PASS | `api.py` L2319+、L2338+；覆盖 PROGRESS/SUCCEEDED/FAILED/CANCELLED |
| `HostFinalAnswerView` frozen dataclass | PASS | `api.py` L2352+；`content`/`filtered`/`degraded`/`finish_reason`/`terminal_status`；`__post_init__` 强制 `terminal_status == SUCCEEDED` |
| `HostEvent` frozen dataclass | PASS | `api.py` L2385+；common fields + terminal payload；`_validate_host_event_terminal_payload` 校验 kind/status/payload 组合一致性 |
| 签名避免 Any/object/untyped payload | PASS | 所有字段均为显式 typed contract |
| 完整中文 docstring（参数/返回值/异常） | PASS | 全部新增类型、方法、函数、模块均有完整中文 docstring |

### Export boundary compliance

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| `__all__` 移除 `HostCommandHandle` | PASS | `__init__.py` `__all__` 中无此项 |
| `__all__` 移除 `create_host_command_handle` | PASS | 同上 |
| `__all__` 移除 `HostLocalExecutionOptions` | PASS | 同上 |
| `__all__` 移除 `HostEventView` | PASS | 同上 |
| `__all__` 移除 `HostEventStream` | PASS | 同上 |
| `__all__` 移除 `start_run` | PASS | 同上 |
| `__all__` 移除 `stream_run_events` | PASS | 同上 |
| `__all__` 新增 `open_host` | PASS | `__init__.py` L197 |
| `__all__` 新增全部新类型 | PASS | `Host`、`HostClosedError`、`HostEvent`、`HostEventKind`、`HostFinalAnswerView`、`HostHandle`、`HostTerminalStatus`、`OpenHostOptions`、`OrdinaryRunExecutionBaseline`、`CompactorExecutionBaseline` 均在 `__all__` |
| 无兼容性 re-export | PASS | 旧符号无 wrapper、无 facade 转发 |
| `_start_run` 保持内部 | PASS | `__init__.py` 不导出 `_start_run` |

### open_host skeleton compliance

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| importable / type-checkable | PASS | `from dayu.host import open_host` 可用；返回 `AbstractAsyncContextManager[Host]` |
| options 类型校验 | PASS | `_OpenHostContextManager.__init__` isinstance 校验 |
| 未假装 runtime 可用 | PASS | `__aenter__` raise `NotImplementedError("open_host runtime composition is owned by a later P10.5 slice")` |
| 不破坏后续 Slice 2 | PASS | `_OpenHostContextManager` 是独立类，Slice 2 可替换 `__aenter__` 实现而无需改签名 |

### Tests compliance

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| frozen slots 断言 | PASS | `test_open_host_option_types_are_frozen_slots_dataclasses` 校验 5 个类型 |
| options validation | PASS | `test_open_host_options_validate_lane_and_baseline`、`test_compactor_baseline_validates_typed_fields` |
| HostEvent terminal contract | PASS | `test_host_event_terminal_final_answer_contract` 校验 succeeded 必须内联 final_answer |
| open_host 骨架边界 | PASS | `test_open_host_rejects_untyped_options`、`test_open_host_slice1_context_body_is_deferred` |
| package exports 断言 | PASS | `test_removed_low_level_symbols_are_not_service_facing_all_exports` 校验 7 个符号不在 `__all__` |

### README compliance

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 仅同步当前事实 | PASS | README 只描述 Slice 1 当前 public contract surface，不写 Slice 2 runtime wiring、live fanout、compactor behavior |
| 无未来行为描述 | PASS | 无 "将会"、"计划" 等前瞻性表述 |
| 术语一致 | PASS | 旧术语（`start_run`、`create_host_command_handle`、`HostEventView`、`run-level stream_run_events`）已降级为 "低层" 描述 |

### Layer boundary compliance

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 不让 Engine 理解 Host 状态 | PASS | diff 不涉及 Engine 代码 |
| 不把 Service 引向 internals | PASS | `__all__` 收口 public surface；低层类型从 `__all__` 移除 |
| 无反向依赖 | PASS | 新增代码只依赖 `dayu.engine.contracts`（允许方向）与 `dayu.host` 内部模块 |

---

## Implementation Artifact Cross-check

Implementation artifact `docs/reviews/phase10-5-slice1-implementation-codex-20260518.md` claims:

| Claim | Verified |
| --- | --- |
| Tests passed: `13 passed in 0.18s` | Consistent with diff (5 tests in `test_public_open_host_options.py` + 8 in `test_package_exports.py`) |
| Pyright: `0 errors, 0 warnings, 0 informations` | Claim accepted; not re-run in this review |
| `HostToolingOptions` reused, no extra payload | PASS — `OpenHostOptions.tooling_options: HostToolingOptions | None` |
| `HostClosedError` standalone lifecycle exception | PASS |
| `HostEvent` terminal types frozen | PASS |
| `open_host` skeleton with `NotImplementedError` | PASS |
| `__all__` removed 7 old exports | PASS — verified against actual `__init__.py` |
| No Slice 2 scope creep | PASS |

---

## Verdict

**PASS**

- Blocking count: **0**
- Accepted non-blocking findings: **1** (N1: removed symbols 仍可通过直接导入访问；属于 plan 承认的 residual risk，后续 slice 负责迁移测试导入路径)
- Residual risks:
  - `open_host(options)` 在 Slice 1 仅为 contract 骨架，`__aenter__` raise `NotImplementedError`；runtime 接线由 Slice 2 负责
  - `Host` / `HostHandle` 仅为 Protocol，无 production concrete handle
  - 8 个现有测试文件仍从 `dayu.host` 直接导入已从 `__all__` 移除的符号；后续 slice 修改这些文件时应迁移导入路径
  - `HostClosedError` 行为测试（closed handle 方法抛出 `HostClosedError`）依赖 Slice 2 concrete handle 实现
- Artifact path: `docs/reviews/phase10-5-slice1-code-review-mimo-20260518.md`
