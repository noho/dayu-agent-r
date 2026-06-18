# WU-CLI-ACTIVITY-01 Aggregate Final Review

## Scope

- Mode: current branch aggregate (all commits vs main)
- Branch: wu-cli-activity-01
- Base: main
- Output file: docs/reviews/deepreview-wu-cli-activity-01-aggregate-ds-20260617-151950.md
- Plan: docs/host/host-issues/wu-cli-activity-01-activity-composer-plan.md (commit `012fee0a`)
- Commit range:
  - `012fee0a` — plan accepted
  - `992a641d` — Slice A (Host public activity event contract)
  - `152292da` — Slice B (Service activity callback)
  - `1a6f4bb2` — CLI Slices C/D/E/F (activity renderer, composer, running state, docs)
- Full diff: 54 files, +8683 / -438 lines
- Target: GitHub Issue #144 — prompt/interactive user-visible activity stream UI

### Prior Review History

| Gate | Artifacts | Outcome |
|---|---|---|
| Plan review | plan-review-* (2 AgentMiMo + 2 AgentDS + adjudication) | Accepted |
| Slice A implementation | code-review-* + fix + re-review | Accepted |
| Slice B implementation | code-review-* + fix + re-review (MiMo + DS) | Accepted |
| CLI implementation | cli-ds + cli-mimo + review-fix + cli-rereview (MiMo + DS) | Non-blocking, fixes verified |
| **Aggregate** | **This review** | **—** |

## Findings

未发现实质性问题。完整 work unit 在 correctness、contract boundaries、public Host event projection、Service activity callback、CLI behavior、tests 和 docs 方面均合规。

以下为逐维度验证结论，每项包含证据追溯。

## 1. Plan Completeness — All Slices Delivered

### Slice A — Host Public Activity Event Contract ✅

| Plan Requirement | Status | Evidence |
|---|---|---|
| 新增 `HostActivityView` / `HostActivityKind` / `HostActivityStatus` / `HostActivitySeverity` / `HostActivityCounts` | ✅ | `dayu/host/api.py` — 强类型 frozen dataclass + StrEnum，完整校验 |
| 扩展 `HostEvent` 三个新字段: `event_class`, `event_type`, `activity` | ✅ | `dayu/host/api.py` — 保留向后兼容（新字段有默认值/可选） |
| `event_class` 复用已有 `HostEventClass` 枚举 | ✅ | 不新增平行 enum |
| `event_type` 从 EventLog row 直接复制 | ✅ | `dayu/host/read_api.py:_host_event_from_row` |
| Activity allowlist projection 覆盖所有指定 event types | ✅ | `test_host_activity_event_projection.py` (1131 行, 13 tests) 覆盖全部: TOOL_CALL_REQUESTED, TOOL_RESULT_ACCEPTED, TOOL_CALLS_BATCH_DONE, TOOL_AWAITING, RUN_WAITING, CONTEXT_COMPACTION_*, PROVIDER_PROTOCOL_ERROR, run lifecycle |
| REASONING_DELTA / CONTENT_DELTA 保留 identity, activity=None | ✅ | 测试明确断言 raw delta 不投影 |
| 未知 event 保留 identity, activity=None | ✅ | 测试覆盖未知 event 处理 |
| 工具展示名 from Host-owned snapshot, fallback stable tool_name | ✅ | `dayu/host/admission.py` — `effective_tool_display_names` 冻结在 `USER_INPUT_ACCEPTED` |
| 不新增 durable schema migration | ✅ | admission.py 变更是 payload shape 扩展，不是 schema migration |

### Slice B — Service Activity Callback ✅

| Plan Requirement | Status | Evidence |
|---|---|---|
| 新增严格类型 DTO: EntrypointActivity 等 | ✅ | `dayu/service/entrypoint_runtime.py` — 完整中文 docstring，完整校验 |
| `submit_entrypoint_turn_and_wait` 增加可选 `on_activity` | ✅ | 行 520 — 默认 None，向后兼容 |
| non-terminal HostEvent.activity 投影给 callback | ✅ | `_emit_entrypoint_activity_from_host_event` — 过滤 terminal/无 activity/无关 run |
| generic progress 不产生伪工具展示 | ✅ | 测试覆盖 `test_submit_entrypoint_turn_suppresses_progress_without_activity` |
| watcher failure → 有界 diagnostic activity | ✅ | `_emit_watcher_failure_activity` — 去重 + 240 字符截断 |
| 非终态 dedupe key 不抑制终态 | ✅ | `_terminal_result_from_live_event` early return + 独立 `seen_activity_dedupe_keys` |
| callback 异常透传 | ✅ | 无 try/except 包裹，测试覆盖 |

### Slice C/D/E/F — CLI Activity, Composer, Running State ✅

| Plan Requirement | Status | Evidence |
|---|---|---|
| Activity renderer 写 stderr，终态写 stdout | ✅ | `dayu/cli/activity.py` — 所有 `print(file=self._stderr)` |
| non-TTY 默认不输出 live activity | ✅ | `enabled = self._stderr.isatty()` |
| Ctrl+T toggle activity visible/hidden | ✅ | `CliActivityRenderer.toggle_visible` + 运行态 key_task TOGGLE_ACTIVITY 分支 |
| 隐藏时保留一行短状态 | ✅ | `_last_hidden_title` 始终追踪 + "Activity hidden" 提示 |
| Ctrl+C / Esc 运行态 cancel + 第二次 Ctrl+C 本地退出 130 | ✅ | prompt 和 interactive 均实现双路 wait (cancel_task vs second_sigint_task) |
| terminal-first-wins (CANCELLING 中 terminal 优先) | ✅ | 双路 wait 中 cancel_task 先完成返回 terminal |
| Interactive composer: Ctrl+J 换行, Enter 提交 | ✅ | `PromptToolkitInteractiveComposer` + `multiline=False` |
| Ctrl+R 历史搜索 | ✅ | `start_history_lines_completion()` + `InMemoryHistory` |
| Ctrl+X Ctrl+E 外部编辑器 | ✅ | `open_in_editor(validate_and_handle=False)` + 异常 bounded stderr |
| 输入态 Ctrl+C: 空退出, 非空清空 | ✅ | `build_interactive_key_bindings` 中 `_clear_or_interrupt` |
| composer 封装 prompt_toolkit，不扩散类型 | ✅ | `InteractiveComposer` Protocol → command 模块只依赖协议 |

## 2. Cross-Layer Architecture — Clean

### Dependency Direction

```
CLI (dayu/cli/)
  ↓ imports Service DTOs (EntrypointActivity, etc.)
Service (dayu/service/)
  ↓ imports Host public API (Host, HostEvent, HostActivityView, etc.)
Host (dayu/host/)
  ↓ imports Engine contracts (existing, unchanged pattern)
Engine (dayu/engine/)
  (no imports from upper layers)
```

**验证**:
- CLI 不 import Host 内部实现 (read_api, admission, engine_ingest) — ✅
- CLI 不 import Engine — ✅
- Service 不 import CLI — ✅
- Host 不 import Service/CLI — ✅

### Contract Ownership

| 类型 | 定义层 | 消费层 | 正确？ |
|---|---|---|---|
| `HostActivityView` / `HostActivityKind` 等 | Host | Service, CLI (via re-export) | ✅ |
| `HostEvent.event_class` / `event_type` | Host | Service (只读, 不分支) | ✅ |
| `EntrypointActivity` / `EntrypointActivityKind` 等 | Service | CLI | ✅ |
| `CliActivityRenderer` | CLI | CLI commands | ✅ |
| `InteractiveComposer` (Protocol) | CLI | CLI commands | ✅ |
| `RunningKeyMonitor` (Protocol) | CLI | CLI commands | ✅ |

**关键设计决策验证**:
- Service **不根据** `HostEvent.event_class` 做 UI 分支 — ✅ (行内注释说明 `event_class`/`event_type` 不是 UI 分类依据)
- CLI **只消费** Service `EntrypointActivity` DTO，不直接消费 `HostActivityView` — ✅ (grep 确认 CLI 层无 HostActivityView import)
- `__all__` 导出完整 — ✅ (Host `__init__.py` 新增 5 个类型导出, 3 个 CLI 新模块均有完整 `__all__`)

## 3. State Machine Correctness — All Paths Verified

### Submit Turn Running State

```
RUNNING (submit_task, sigint_task, key_task 三路并发)
  ├── submit_task 完成 → return terminal [terminal-first-wins]
  ├── key_task=TOGGLE_ACTIVITY → toggle visible → new key_task → continue
  ├── key_task=CANCEL_RUN → cancel path (Esc)
  └── sigint_task 完成 → cancel path (Ctrl+C)

CANCELLING (cancel_task, second_sigint_task 双路并发)
  ├── cancel_task 完成 → return terminal [terminal-first-wins in CANCELLING]
  └── second_sigint_task 完成 → render_local_exit_after_cancel → return None → EXIT 130
```

### TTY Key Monitor Lifecycle

```
start() → setcbreak → Thread.start → background _read_loop
  └── [failure] → restore terminal attrs → clean state → return

close() → _stop_event.set() → thread.join(0.2s) → restore terminal attrs
```

### Activity Renderer Lifecycle

```
new per turn → record(activity)* → toggle_visible()* → close()
  └── dedupe by key + monotonic sequence
  └── visible: print to stderr / hidden: track title only
  └── close: all subsequent operations silently skipped
```

## 4. Test Coverage — Comprehensive

| Layer | Test File | Tests | Focus |
|---|---|---|---|
| Host | test_host_activity_event_projection.py | 13 | 所有 activity allowlist event types + 边界 + unknown |
| Host | test_public_host_event.py (updated) | ~12 | HostEvent 新字段 validation |
| Host | test_watch_session_events.py (updated) | — | watch path regression |
| Host | test_context_compact_events.py (updated) | — | compaction event identity |
| Service | test_entrypoint_runtime.py (updated) | 26 | activity callback, dedupe, exception propagation, watcher failure |
| CLI | test_activity_renderer.py | 6 | output, dedupe, disabled, hidden toggle, visible→hidden title, cancel messages |
| CLI | test_interactive_composer.py | 5 | TTY routing, all key bindings, editor failure |
| CLI | test_run_keys.py | 6 | byte mapping, non-TTY no-op, PTY read/restore, close idempotent, thread fail recovery |
| CLI | test_prompt_command.py (updated) | 22 | activity stderr, Ctrl+T, Esc cancel, second SIGINT, terminal-first-wins, regression |
| CLI | test_interactive_command.py (updated) | 24 | activity stderr, Esc cancel, regression, two-turn ordering |

**总计**: 179 passed, 3 edgar deprecation warnings (第三方). pyright 0 errors.

**覆盖率**:
- `dayu/cli/activity.py`: 88%
- `dayu/cli/composer.py`: 94%
- `dayu/cli/run_keys.py`: 89%
- `dayu/service/entrypoint_runtime.py`: 88%

## 5. AGENTS.md / CLAUDE.md Compliance — Verified

| 约束 | 状态 |
|---|---|
| 完整中文 docstring (参数、返回值、异常) | ✅ 所有新增公开函数/类 |
| 禁止 `Any`/`object`/无类型参数 | ✅ pyright strict mode, 0 errors |
| 禁止 `hasattr`/`getattr` 逃避类型边界 | ✅ 无使用 |
| 禁止 God object/function/dataclass | ✅ HostActivityView/EntrypointActivity 为窄 DTO |
| 禁止兼容性代码 | ✅ 不保留旧接口 |
| 分层架构严格遵守 (UI→Service→Host→Engine) | ✅ |
| 禁止反向依赖 | ✅ |
| 必须复用 `dayu.runtime` 公共能力 | ✅ N/A (本 WU 未使用 runtime 新能力) |
| 数据处理/存储/工具调用职责分离 | ✅ Host read_api 投影, Service 转发, CLI 渲染 |
| 重复逻辑抽取 | ⚠️ `_cancel_and_await_task` 在 interactive.py 和 prompt.py 中存在重复（低严重度，已知） |

## 6. README Updates — Triggered and Applied

| README | 触发条件 | 更新状态 |
|---|---|---|
| dayu/host/README.md | Host api.py/read_api.py/admission.py 修改 → Host public event contract 变更 | ✅ 已更新 — 新增 HostActivityView 及相关类型说明 |
| tests/README.md | tests/ 修改 → CLI 测试覆盖说明变更 | ✅ 已更新 — 新增 activity renderer/composer/run keys 测试覆盖说明 |
| dayu/README.md | 分层关系变更？→ 本 WU 不改变分层边界 | ✅ 检查后不需要更新 |
| dayu/service/README.md | 不存在 | ✅ N/A |

## 7. Adversarial Failure Pass — Key Results

| 攻击面 | 结论 |
|---|---|
| 终端 cbreak 后进程崩溃 | ⚠️ 无 atexit handler 兜底 — 已知限制，需 `reset` 命令手动恢复 |
| 非终态 dedupe key 抑制终态 | ✅ 已修复 — early return 隔离 |
| callback 异常吞没 | ✅ 已修复 — 透传 + 测试覆盖 |
| 第二次 Ctrl+C 被静默忽略 (prompt) | ✅ 已修复 — 双路 wait |
| _last_hidden_title 首次隐藏无提示 | ✅ 已修复 — title 始终追踪 |
| thread.start() 失败终端不可恢复 | ✅ 已修复 — try/except RuntimeError + 恢复 |
| watcher failure 重复 diagnostic | ✅ 去重 — `_WATCHER_FAILURE_ACTIVITY_DEDUPE_KEY` |
| activity dedupe keys 无限增长 | ✅ 每 turn 新建 renderer, bounded |
| Ctrl+T toggle 中 task leak | ✅ 旧 key_task 已完成, 新 key_task 由 finally 回收 |
| 三路 wait 中 key_task 完成但 sigint_task 也完成 (同轮) | ✅ FIRST_COMPLETED 保证只有一个在 done 中 |
| prompt_toolkit 编辑器启动失败 | ✅ Exception 捕获 + bounded stderr diagnostic |

## 8. Residual Risk

| Risk | Severity | Detail | Mitigation |
|---|---|---|---|
| `cancel_entrypoint_run_and_wait` 无 `on_activity` | 低 | F-2 已裁决延期；cancel 期间无 activity 反馈 | 已知延期，不影响 submit 路径 |
| 无 atexit handler 恢复终端 | 低 | 进程异常退出时终端留 cbreak 模式 | 用户执行 `reset` 或 `stty sane` |
| `_cancel_and_await_task` 代码重复 | 低 | interactive.py 和 prompt.py 中重复 | 后续重构 |
| `build_interactive_key_bindings` 嵌套函数 | 低 | prompt_toolkit API 惯例，轻微违反 CLAUDE.md | 已知，已记录 |
| 手动 TTY smoke test 未执行 | 低 | pty 测试覆盖了核心路径 | 真实终端行为由 CI 或手动验证 |
| Esc 单字节处理可能误触 cancel | 低 | 某些 escape sequence 以 `\x1b` 开头 | fix artifact 已记录，现有行为延续 |
| prompt 第二次 Esc 不本地退出 | 低 | 裁决语义：Esc 是 cancel 请求，Ctrl+C 计数退出 | fix artifact 已说明 |

## 9. Deferred Items (Adjudicated)

| Item | Original Finding | Adjudication | Current Status |
|---|---|---|---|
| F-2: `cancel_entrypoint_run_and_wait` lacks `on_activity` | DS F-2 (Slice B review) | Deferred to Slice E | Still deferred — Slice E scope was CLI interactive running state, not Service cancel path |
| `_cancel_and_await_task` duplication | Aggregate finding (low) | N/A (new observation) | Minor, non-blocking |
| Nested functions in `build_interactive_key_bindings` | CLI review finding (low) | N/A (new observation) | Minor, prompt_toolkit convention |

## 10. Open Questions

无。

## 11. Verification Results

```text
pytest (affected test suite): 179 passed, 3 warnings
pyright (full project): 0 errors, 0 warnings, 0 informations
git diff --check: clean
Coverage (new CLI modules): 88-94%
Coverage (Service entrypoint_runtime): 88%
```

## 12. Aggregate Conclusion

**非阻断。** WU-CLI-ACTIVITY-01 work unit 完整交付了 plan 中所有六个 slice 的目标：

1. **Host public activity event contract** — 正确扩展了 `HostEvent`，activity allowlist 投影覆盖所有 plan 指定的 event types，工具展示名来自 Host-owned snapshot
2. **Service activity callback** — 正确消费 Host public activity 投影为 `EntrypointActivity` DTO，dedupe 隔离非终态/终态，callback 异常正确透传
3. **CLI activity renderer** — stdout/stderr 分离正确，non-TTY 自动禁用，visible/hidden toggle 工作正常
4. **Interactive composer** — prompt_toolkit 隔离良好，Ctrl+J/Ctrl+R/Ctrl+X Ctrl+E 均可用
5. **Interactive running state** — 三路并发状态机正确，terminal-first-wins，第二次 Ctrl+C 本地退出 (prompt + interactive)
6. **Documentation & validation** — README 更新正确，179 tests passed, pyright 0 errors

架构边界干净：分层依赖方向正确，合约归属清晰，无反向依赖，CLI 不穿透读取 Host/Engine 内部实现。

已知剩余风险均为低严重度，无阻断项。已裁决延期项 (F-2) 未扩大范围。
