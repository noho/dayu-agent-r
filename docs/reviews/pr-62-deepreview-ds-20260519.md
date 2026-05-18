# Code Review — PR 62 Deep Review (DS)

## Scope

- Mode: PR review
- Repository: noho/dayu-agent-r
- PR: 62
- Title: Host P10.5 ordinary local multi-turn public contract freeze
- Author: noho
- Head: feat/host-p10-5-public-contract-freeze
- Base: main
- URL: https://github.com/noho/dayu-agent-r/pull/62
- Output file: docs/reviews/pr-62-deepreview-ds-20260519.md
- Included scope: PR 62 relative to main full diff (107 files, +19551/-339 lines)
- Excluded scope: 无
- Review design sources: docs/host/design.md, docs/host/implementation-control.md, docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md, docs/host/post-p10.md

## Verification Results

```text
# Package exports
pytest tests/host/test_package_exports.py -q
# → 8 passed

# Full host test suite
pytest tests/host -q
# → 696 passed, 1 skipped

# Type check
python -m pyright dayu/host tests/host
# → 0 errors, 0 warnings, 0 informations

# Whitespace check
git diff --check main...HEAD
# → trailing whitespace only in review artifacts (pre-existing docs/reviews/), clean production code
```

## Findings

### 1-未修复-中-_event_type_count 直连 SQLite event_log 绕过 public read path 同步等待

- **入口/函数**: `_event_type_count(db_path, event_type)` 与 `_wait_for_event_type_count(db_path, event_type, expected_count)`
- **文件(行号)**:
  - `tests/host/test_public_lifecycle_smoke.py:432` — 定义并用于 wait / compact smoke 同步
  - `tests/host/test_public_retry_replay.py:586` — 定义并用于 steer / retry / replay smoke 同步
  - `tests/host/test_public_cancel_session_runs.py:225` — 定义并用于 cancel session runs smoke 同步
  - `tests/host/test_public_steer.py:50` — 通过 import 使用 `_wait_for_event_type_count`
  - `tests/host/test_public_cancel_smoke.py:45` — 通过 import 使用 `_wait_for_event_type_count`
- **输入场景**: public smoke 测试需要等待特定 EventLog 事件类型（如 `ATTEMPT_RUNNING`）出现后继续断言
- **实际分支**: 直接 `sqlite3.connect(db_path)` 绕过 public read API，查询 `SELECT COUNT(*) FROM event_log WHERE event_type = ?`
- **预期行为**: 同步应通过 public `get_run()` polling 或 `watch_session_events()` event type 过滤完成
- **实际行为**: 五处 smoke 测试文件各自复制同一 SQLite bypass 模式；`test_public_lifecycle_smoke.py:440`、`test_public_retry_replay.py:594`、`test_public_cancel_session_runs.py:233` 均打开 SQLite connection 直查 `event_log` 表
- **直接证据**:
  ```python
  # test_public_lifecycle_smoke.py:440
  with sqlite3.connect(db_path) as connection:
      row = connection.execute(
          "SELECT COUNT(*) FROM event_log WHERE event_type = ?",
          (event_type,),
      ).fetchone()
  ```
- **影响**: 测试同步机制依赖内部表结构；若 EventLog schema 变更（如表重命名）这些 smoke 会静默失败，而 public API 调用不受影响。post-p10.md 明确要求 smoke 不得"直接查询 durable 内部表"
- **建议改法和验证点**: 将 `_wait_for_event_type_count` 替换为基于 public `get_run()` status polling 或 `watch_session_events()` event kind 过滤的同步 helper，或明确将同步用途的内部表读取放进 `public_smoke_support.py` 并加注释声明"仅测试同步、非 correctness 断言"。从 5 个文件删除重复实现
- **修复风险（低）**: 仅替换测试同步机制，不改变生产行为
- **严重程度（中）**: 不影响 production correctness，但违反 smoke public-path 约束，且 5 处代码重复维护负担高

### 2-未修复-中-public smoke 测试引入 `create_host_command_handle` 做 WAITING 状态 seed

- **入口/函数**: `create_host_command_handle` 用于在 public smoke 测试中种子化 WAITING Run
- **文件(行号)**:
  - `tests/host/test_public_steer.py:17` — `from dayu.host.command import create_host_command_handle`
  - `tests/host/test_public_steer.py:90` — `seed_handle = create_host_command_handle(_command_options(tmp_path))`
  - `tests/host/test_public_resolve_wait_resume.py:10` — 同上 import
  - `tests/host/test_public_resolve_wait_resume.py:30` — 同上使用
- **输入场景**: steer `WAITING` Run 与 `resolve_wait` resume smoke 需要预先存在 WAITING Run 来驱动测试
- **实际分支**: 测试通过低层 `create_host_command_handle` 直接操作 durable state，seed 出 WAITING Run 和 active wait record，然后 close seed handle；再用 `open_host(options)` 打开 public handle 继续 public path 验证
- **预期行为**: 理想情况下应有 public API 路径可产出 WAITING Run（例如 mock tool awaiting accept），测试全程只接触 `open_host`
- **实际行为**: 低层 command handle 被 import 后短暂用来 seed state；`test_public_steer.py:90-94` 使用 try/finally 确保 seed handle 在 open_host 前关闭，但这仍意味着 smoke 文件依赖 `dayu.host.command` 内部模块
- **直接证据**:
  ```python
  # test_public_steer.py:90-94
  seed_handle = create_host_command_handle(_command_options(tmp_path))
  try:
      seeded = _seed_waiting_run(seed_handle)
  finally:
      seed_handle.close()
  ```
- **影响**: 若 `create_host_command_handle` 接口变更或被移除，这些 smoke 会断裂；且测试文件显式 import 内部模块，与 post-p10.md "Service 不得直接 import `dayu.host.dispatch`、durable store、scheduler、wakeup port 或 `create_host_command_handle(...)`" 的精神冲突
- **建议改法和验证点**: 在 `public_smoke_support.py` 中提供一个基于 `open_host()` + mock tool（awaiting accept path）产生 WAITING Run 的 seed helper，替代 `create_host_command_handle` 直接操作；或明确记录 WAITING seed 当前没有纯 public API 路径，将其归类为 "not covered but accepted" 并在 plan 中写明 owner
- **修复风险（低）**: 仅影响测试 setup，不改变生产行为
- **严重程度（中）**: 不影响 production correctness，但暴露 public API 缺少 WAITING Run seed 路径的设计空白

### 3-未修复-低-`watch_session_events` iterator 在 handle close 时静默终止而非抛 Host lifecycle termination

- **入口/函数**: `_PublicHostHandle._watch_session_events_after()`
- **文件(行号)**: `dayu/host/open_host.py:319-343`
- **输入场景**: Service 通过 `host.watch_session_events(session_id)` 打开 watch 后，在迭代过程中 Host handle 被 close
- **实际分支**: 第 332 行 `while not self._closed:` — handle close 后 `self._closed` 变为 `True`，循环退出，iterator 静默终止，不抛出任何异常
- **预期行为**: 按 post-p10.md 要求："Host close 时已打开 iterator 结束或抛 Host lifecycle termination"
- **实际行为**: 当前实现选择了"静默结束"，但调用方无法区分"stream 正常结束"和"Host 已关闭导致 stream 中断"。若调用方在 `async for event in host.watch_session_events(sid):` 中等待 terminal event，close 后循环静默退出，调用方可能误以为自己漏掉了 terminal event
- **直接证据**: `dayu/host/open_host.py:332`
  ```python
  while not self._closed:
      ...
  # 循环退出后无 yield、无 raise，协程静默结束
  ```
- **影响**: 调用方可能因 handle close 丢失 terminal event 感知；虽然 post-p10.md 允许"结束或抛"，但静默结束让调用方无法区分正常 watch 关闭与意外 handle close
- **建议改法和验证点**: 在 handle close 后的首次 poll 迭代或循环退出前，`yield` 一个 typed `HostEventKind.CLOSED` 事件或抛出 `HostClosedError`，让调用方能检测 handle close；或在 README / public contract 中明确约定"watcher 在 handle close 后静默终止，调用方通过 handle API 返回 `HostClosedError` 判断"
- **修复风险（低）**: 语义变化可能影响已有 watcher consumer 的行为
- **严重程度（低）**: 当前行为不违反设计真源（post-p10.md 允许"结束"），但静默终止的可用性风险应在文档或后续版本中收口

### 4-未修复-低-`public_smoke_support.py` 依赖内部 `DefaultLocalEngineWorkerFactory`

- **入口/函数**: `public_smoke_support.py` 中的 `open_host_options()` helper
- **文件(行号)**: `tests/host/public_smoke_support.py:80` — `from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory`
- **输入场景**: 真实 runner smoke 需要构造 production worker factory 传给 `open_host(options)`
- **实际分支**: `DefaultLocalEngineWorkerFactory` 是从 `dayu.host.local_proxy`（内部模块）导入的具体实现类，不在 `dayu.host.__all__` 中
- **预期行为**: `LocalEngineWorkerFactory` Protocol 是 public typed contract，具体 factory 应由 Service 或测试自行构造；但在 P10.5 真实 runner smoke 中，测试需要真实 production factory
- **实际行为**: smoke support 绕过 public namespace 导入内部 concrete class。这意味着如果外部 Service 要使用默认 local engine worker，同样需要导入这个内部类
- **直接证据**: `tests/host/public_smoke_support.py:80`
- **影响**: 暴露 public API 缺口——`DefaultLocalEngineWorkerFactory` 是生产路径必需但未从 public namespace 导出；外部 Service 当前无法仅通过 public namespace 构造 `open_host(options)`
- **建议改法和验证点**: 将 `DefaultLocalEngineWorkerFactory` 纳入 `dayu.host.__all__` 或在 `open_host` 文档中明确说明 worker_factory 必须由调用方按 `LocalEngineWorkerFactory` Protocol 自行实现；生产环境建议提供 `default_local_engine_worker_factory()` 构造 helper 从包根导出
- **修复风险（低）**: 仅影响 import 路径，不改变行为
- **严重程度（低）**: 已有 `LocalEngineWorkerFactory` Protocol 作为公共契约，具体 factory 构造路径可通过文档或后续导出收口

## Open Questions

1. `_event_type_count` SQLite bypass 是否作为"测试同步 primitive"被接受？若接受，应集中到 `public_smoke_support.py` 一处，并明确声明其用途仅为 event-type polling sync 非 correctness assertion。
2. `DefaultLocalEngineWorkerFactory` 是否应作为 P10.5 public surface 的一部分导出？若不导出，外部 Service 如何获得默认 production worker factory？

## Residual Risk

### Coverage Gaps (按 post-p10.md Smoke Coverage Matrix)

| 矩阵项 | 覆盖状态 | 证据 |
|--------|---------|------|
| S1 real-runner no-tool multi-turn | covered | `test_real_runner_no_tool_two_turn_public_path` — 仅使用 `open_host`/`submit_followup`/`watch_session_events` |
| S1 multi-client watch | covered | `test_two_watchers_observe_same_terminal_event` — 两个 watcher 独立观察同一 terminal |
| S1 queue idempotency | covered | `test_concurrent_queue_uses_client_request_id_idempotency` |
| S1 per-run override field merge | covered | `test_submit_followup_field_level_execution_override_freezes_effective_config` |
| S2 mock-tool wiring | covered | `test_public_tool_wiring_smoke.py` — 使用 mock tool 经 Host accept barrier |
| S3 real-runner matrix (mimo/deepseek/gemini/qwen) | covered | `test_public_real_runner_matrix_smoke.py` — 四类 provider case |
| S4 compact smoke (real compactor) | covered | `test_public_compact_smoke.py` — 使用显式真实 compactor adapter |
| S5 cancel smoke (all states + close boundary) | covered | `test_public_cancel_smoke.py` — accepted/queued/active/pre-dispatch + `close_session` != cancel |
| S5 session-scope cancel | covered | `test_public_cancel_session_runs.py` |
| steer (RUNNING + WAITING) | covered | `test_steer_running_run_creates_new_attempt_public_path`, `test_steer_waiting_run_creates_new_attempt_public_path` |
| retry/replay | covered | `test_public_retry_replay.py` — FAILED retry, SUCCEEDED replay |
| resolve_wait resume | covered | `test_resolve_wait_resumes_through_open_host_and_terminal_event` |
| Host opener lifecycle (close/repeat-close/closed-error) | covered | `test_public_lifecycle_smoke.py` |
| typed HostEvent terminal answer | covered | `test_public_host_event.py`, `test_watch_session_events.py` |

### Not Covered But Accepted

| 项 | Owner | Destination |
|----|-------|-------------|
| Recovery (LOST/RECOVERING cancel, startup scan, orphan proof) | P10.5 scope exclusion | Phase 11 |
| Outbox offline terminal delivery | P10.5 scope exclusion | Phase 13 |
| Callback HTTP endpoint / poller background loop | P10.5 scope exclusion | 后续生产集成 |
| purge_session destructive cleanup | P10.5 scope exclusion | Phase 15 |
| RemoteProxy | P10.5 scope exclusion | Phase 14 |
| ToolsDiscovery / ScenePrepare | P10.5 scope exclusion | Phase 12 |
| ConfigLoader for runner spec | P10.5 design decision | P10.5 硬编码 runner 参数 |

### Architecture / Import Boundary

| 检查项 | 结果 |
|--------|------|
| `dayu.host` 不导入 Config/Fins/Service/UI | PASS (`test_host_does_not_import_upper_or_business_layers`) |
| `dayu.host` 不扫描业务工具包 | PASS (`test_host_does_not_import_business_tool_scanners`) |
| Host Engine import 仅限边界模块 | PASS (`test_host_engine_imports_stay_on_allowed_boundary_modules`) |
| `dayu.runtime` 不导入 Host/Engine | PASS (`test_runtime_does_not_import_host_or_engine_layers`) |
| projection 不导入 Host mutator owner | PASS (`test_projection_modules_do_not_import_forbidden_layers_or_mutators`) |
| read_api 不引用 projection/fanout | PASS (`test_read_api_stream_does_not_reference_projection_or_fanout_truth`) |
| 包根不导出 ToolRuntime/ToolBundle/ToolDefinition | PASS (`test_host_root_does_not_export_toolruntime_or_tool_declaration_owners`) |
| request dataclass 不携带 `business_tool_bundle` | PASS (`test_host_request_dataclasses_do_not_carry_tool_bundle`) |
| `fetch_more` token 仅限 tool_runtime/tooling owner | PASS |
| pyright 0 errors | PASS |
| 696 tests passed, 1 skipped | PASS |

### README Alignment

- `dayu/host/README.md`: 已更新，表述与 P10.5 public contract 一致；记录 `open_host(options)` 作为非低层入口、`start_run` 降级、`watch_session_events` 语义、HostEvent typed contract
- `tests/README.md`: 已更新，涵盖新增 public-path smoke 测试文件说明
- `dayu/README.md`: 已更新（minor diff），与原表述一致
- `docs/host/post-p10.md`: 无冲突，README 描述与 post-p10 冻结 contract 对齐

### Implementation-Control Recording

`docs/host/implementation-control.md` 已记录 P10.5 gate 从 challenge review → implementation-ready planning → implementation → aggregate deepreview → fix → re-review → draft PR gate 的完整轨迹。

### phaseflow/gateflow Artifact Gaps

- 无 gap：`docs/reviews/` 下包含 slice1-slice6 的所有 code review、fix、re-review 和 controller adjudication artifacts，以及 aggregate deepreview/fix/re-review artifacts
- `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md` 为完整的 P10.5 handoff implementation-ready plan

## Verdict

**PASS** — blocking findings count = 0，high findings count = 0，medium findings count = 2，low findings count = 2。

PR 62 的 public contract freeze、Host layer/import boundary、typed API、README 同步和 test coverage 整体通过严格审查。两个 medium finding 不阻塞 merge——它们均涉及测试 helper 对内部模块/表的依赖，不影响 production correctness，建议在后续 slice 或 PR 中收口。四个 low finding 涉及 consumer ergonomics 和 public namespace 暴露边界，不需要阻塞 merge。
