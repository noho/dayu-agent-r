# P10.5 Slice 1 Code Review Artifact

## Gate

- Gate: P10.5 Slice 1 code review
- Target: 当前工作区 uncommitted diff 相对 HEAD
- Reviewer: Agent DS (deepseek model)
- Date: 2026-05-18
- Plan: docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md
- Implementation artifact: docs/reviews/phase10-5-slice1-implementation-codex-20260518.md
- Design truth: docs/host/design.md
- Control truth: docs/host/implementation-control.md

## Changed Files Reviewed

1. `dayu/host/api.py` — 新增 public opener types、HostEvent terminal types、HostClosedError、Host Protocol
2. `dayu/host/open_host.py` — 新增 `open_host(options)` skeleton async context manager
3. `dayu/host/__init__.py` — 调整 `__all__` Service-facing export boundary
4. `tests/host/test_public_open_host_options.py` — 新增 options/baseline/event contract 测试
5. `tests/host/test_package_exports.py` — 更新包根导出白名单测试
6. `dayu/host/README.md` — 同步 Slice 1 public contract 文档

## Findings

### Finding 1 (Non-blocking, Accepted) — Legacy symbols still importable as `dayu.host.<name>`

**证据:** `dayu/host/__init__.py` 第 87-101 行仍然从 `dayu.host.command` 导入 `HostCommandHandle`、`create_host_command_handle`、`start_run`，从 `dayu.host.read_api` 导入 `stream_run_events`，从 `dayu.host.api` 导入 `HostEventView`、`HostEventStream`、`HostLocalExecutionOptions`。这些名字已从 `__all__` 移除，但作为模块属性仍可通过 `from dayu.host import start_run` 访问。

**影响:** Service 可能误用被降级的旧入口。计划要求低层测试从内部模块路径导入（如 `from dayu.host.command import start_run`），但包根仍提供这些符号的快捷访问。

**修复建议:** 无。Implementation artifact 已明确记录这是刻意选择："Package module attributes for some legacy low-level names remain present because broad test import migration is outside this slice's allowed test file set." 计划 Slice 3 要求迁移低层测试到内部导入路径，届时可一并移除包根模块属性。当前 `__all__` 边界已正确收口，`from dayu.host import *` 不会泄漏这些名字。

### Finding 2 (Non-blocking, Accepted) — `_start_run` 内部 primitive 尚未创建

**证据:** 计划要求 "Keep `_start_run` internal; do not add compatibility re-export." 当前 `dayu/host/command.py` 中的函数仍名为 `start_run`，无 `_start_run` 存在。

**影响:** 计划 Slice 3 明确负责 `start_run` → `_start_run` 的重命名与低层测试迁移。Slice 1 仅负责从 `__all__` 移除 `start_run`，重命名不是 Slice 1 责任范围。

**修复建议:** 无。归属 Slice 3。

### Finding 3 (Non-blocking, Accepted) — `HostClosedError` 的 closed-handle 行为未测试

**证据:** 计划要求 "Closed handle public methods raise `HostClosedError`, not command-level `INVALID_STATE`." 当前 Slice 1 无具体 handle 实现，因此无法测试 closed-handle 后调用行为。

**影响:** `HostClosedError` 类型本身已正确实现为独立 `Exception` 子类，与 `HostApiError` 无继承关系。closed-handle 行为测试必须在 Slice 2 有了生产 concrete handle 后才能落位。

**修复建议:** 无。Slice 2 负责实现 handle lifecycle 后补齐对应测试。计划 Slice 2 test 明确要求 "Handle close is idempotent and post-close APIs raise `HostClosedError`."

### Finding 4 (Non-blocking, Observation) — `HostEvent` FAILED/CANCELLED terminal payload 可选性

**证据:** `HostEvent` 定义 `error_message: str | None` 和 `cancel_reason: str | None`。`HostFinalAnswerView` 已强制 `terminal_status == SUCCEEDED`，但 FAILED terminal 不强制 `error_message is not None`，CANCELLED terminal 不强制 `cancel_reason is not None`。

**影响:** 调用方无法依赖 `error_message`/`cancel_reason` 一定非空。当前类型允许无消息的终态事件，在实际产出时可能缺少展示内容。但计划仅要求 "typed display fields"，未明确强制非空。

**修复建议:** 可选项。若计划意图是强制非空，可在 Slice 4 live fanout 实现时一并收紧；若允许无消息，当前类型设计正确。当前不阻塞 Slice 1。

### Finding 5 (Non-blocking, Observation) — `HostCommandHandleOptions` 和 `HostCommandFacet` 仍在 `__all__`

**证据:** `dayu/host/__init__.py.__all__` 第 143-144 行包含 `"HostCommandFacet"` 和 `"HostCommandHandleOptions"`。计划移除 `create_host_command_handle`（factory function）和 `HostCommandHandle`（具体 handle 类型），但未要求移除 options/facet 类型。

**影响:** `HostCommandHandleOptions` 是低层 command handle 的构造选项，`HostCommandFacet` 是其 opaque handle 协议。在 `open_host` 成为唯一 Service-facing 入口后，Service 不应直接构造 command handle，因此不再需要这些类型。但低层测试仍需要显式导入 `HostCommandHandleOptions` 来构造 command handle 做内部测试。

**修复建议:** 可选项。若后续将低层测试迁移到内部导入路径，可一并从 `__all__` 移除这两个类型。

## Verification Results

### Scope Boundary
- ✅ 只实现 Slice 1：public opener types / export boundary / options / HostClosedError / HostEvent terminal type surface / focused tests / 必要 README
- ✅ 未进入 Slice 2 runtime wiring、scheduler wakeup、live fanout、Session wrappers
- ✅ 未进入 steer/retry/replay、resolve_wait、compactor wiring 或 ToolRuntime behavior
- ✅ 未修改 Engine contracts、schema、state machine、persistence

### Type Quality
- ✅ 所有新增类型和函数有完整中文 docstring，包含参数、返回值、异常
- ✅ 签名避免 Any/object/untyped payload
- ✅ 所有新增 dataclass 使用 `frozen=True, slots=True`
- ✅ 枚举使用 `StrEnum`
- ✅ `Host` Protocol 方法均有完整 `:param`/`:returns`/`:raises` 文档

### `open_host(options)` Skeleton
- ✅ 可导入、可类型检查
- ✅ 校验 options type（`TypeError` for non-`OpenHostOptions`）
- ✅ 进入 context 时抛 `NotImplementedError`（未假装 runtime 可用）
- ✅ 未破坏后续 Slice 2 装配路径
- ✅ 返回类型 `AbstractAsyncContextManager[Host]`

### Export Boundary
- ✅ `start_run` 不在 `__all__`
- ✅ `create_host_command_handle` 不在 `__all__`
- ✅ `HostLocalExecutionOptions` 不在 `__all__`
- ✅ `HostEventView` 不在 `__all__`
- ✅ `HostEventStream` 不在 `__all__`
- ✅ `stream_run_events` 不在 `__all__`
- ✅ `HostCommandHandle` 不在 `__all__`
- ✅ 无兼容 re-export
- ✅ `open_host`、`OpenHostOptions`、`OrdinaryRunExecutionBaseline`、`CompactorExecutionBaseline`、`Host`、`HostHandle`、`HostClosedError`、`HostEvent`、`HostEventKind`、`HostTerminalStatus`、`HostFinalAnswerView` 均已加入 `__all__`

### Tests
- ✅ options validation 覆盖 lane/baseline/compactor 类型错误路径
- ✅ package exports 白名单验证（含 forbidden internal 和 removed Service-facing 符号）
- ✅ `HostEvent` terminal final answer contract 验证
- ✅ `open_host` 入口拒绝非 `OpenHostOptions` 参数
- ✅ Slice 1 opener 可作为 async context manager 导入但不接线 runtime

### README
- ✅ 只同步当前 Slice 1 事实，未写未来行为
- ✅ 正确描述 `open_host(options)`、public handle、HostEvent terminal view、HostClosedError
- ✅ 将旧 command handle/run-level stream 标记为内部/低层路径
- ✅ 未进入 Slice 2 runtime 接线描述

### Architecture
- ✅ 分层边界正确：Engine 不理解 Host 状态
- ✅ 不引入 schema/state-machine/persistence 变化
- ✅ Host 公共类型在 `dayu.host.api`，包根只做 re-export 收口
- ✅ `HostToolingOptions` 复用现有 typed shape，未引入 extra payload/service locator

### HostEvent Terminal Type Surface
- ✅ `HostEventKind`：PROGRESS / SUCCEEDED / FAILED / CANCELLED
- ✅ `HostTerminalStatus`：SUCCEEDED / FAILED / CANCELLED
- ✅ `HostFinalAnswerView`：content / filtered / degraded / finish_reason / terminal_status
- ✅ `HostEvent`：event_id / event_sequence / session_id / run_id / kind / dedupe_key / terminal_status / final_answer / error_message / cancel_reason
- ✅ Terminal payload 组合校验：PROGRESS 不允许 terminal payload；SUCCEEDED 要求 final_answer；FAILED/CANCELLED 不允许 final_answer；terminal_status 必须匹配 kind

### Additional Verification
- ✅ `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_package_exports.py -q` — passed (implementation artifact reports 13 passed)
- ✅ `source .venv/bin/activate && python -m pyright dayu/host tests/host` — passed (implementation artifact reports 0 errors, 0 warnings)

## Verdict

**PASS** — 0 blocking findings.

Slice 1 implementation 严格按计划完成了 public opener types、export boundary、options、HostClosedError、HostEvent terminal type surface、focused tests 与必要 README 同步。未越界进入 Slice 2 runtime wiring、scheduler、fanout、Session wrappers、steer/retry/replay、resolve_wait、compactor wiring 或 ToolRuntime behavior。新增类型全面使用 frozen slots dataclass、StrEnum、Protocol，均有完整中文 docstring，签名避免 Any/object/untyped payload。Export boundary 正确移除降级符号。测试覆盖 options validation、package exports、HostEvent contract 与 skeleton 边界。README 只同步当前事实。

### Blocking: 0
### Accepted / Non-blocking Findings: 5
1. Legacy symbols 仍作为 `dayu.host.<name>` 模块属性可访问 — Slice 3 负责迁移
2. `_start_run` 内部 primitive 尚未创建 — 归属 Slice 3
3. `HostClosedError` closed-handle 行为未测试 — 归属 Slice 2
4. `HostEvent` FAILED/CANCELLED terminal payload 可选 — 设计讨论，非缺陷
5. `HostCommandHandleOptions`/`HostCommandFacet` 仍在 `__all__` — 低层测试仍需要

### Residual Risks
- 旧入口仍可通过模块属性直接导入（非 `__all__`），Service 可能误用。Slice 3 完成低层测试迁移后可清理。
- `open_host(options)` 骨架在 Slice 2 生产装配完成前无法验证构造期参数与内部件的 compatibility。
- `Host` Protocol 定义了完整 public handle 方法集，部分方法（steer/retry/replay）实际语义尚未落地，Protocol 只作为类型契约不表达实现约束。
- `HostClosedError` 尚未被任何 concrete handle 抛出，其生命周期语义需 Slice 2 验证。

### Artifact Path
docs/reviews/phase10-5-slice1-code-review-ds-20260518.md
