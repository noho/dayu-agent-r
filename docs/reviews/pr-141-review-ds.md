# PR Review — WU-CLI-01 CLI Entrypoint Integration

## Scope

- Mode: PR review
- Repository: `noho/dayu-agent-r`
- PR: [#141](https://github.com/noho/dayu-agent-r/pull/141)
- Title: WU-CLI-01 CLI entrypoint integration
- Head: `phase/host-ui-implementation`
- Base: `main`
- State: OPEN (draft)
- Output file: `docs/reviews/pr-141-review-ds.md`
- Review timestamp: 2026-06-14 18:36 CST
- Included scope: all 99 changed files (21500+ insertions); production code under `dayu/cli/`, `dayu/service/`, `dayu/fins/`, `dayu/runtime/`; tests under `tests/cli/`, `tests/service/`, `tests/fins/`, `tests/runtime/`; design and review artifacts under `docs/`
- Excluded scope: none
- Parallel review coverage:
  - Agent 1: CLI UI adapter boundary (`dayu/cli/` + import audit across all layers)
  - Agent 2: Service boundary (`dayu/service/` — entrypoint_runtime, fins_direct, host_assembly)
  - Agent 3: init command, Fins batch (`dayu/cli/commands/init.py`, `dayu/fins/upload_batch.py`, `dayu/runtime/location.py`)
  - Main reviewer: adjudication, evidence cross-check, outbox cursor path, cancel race paths, PR body claims vs implementation

## Review Method

本次 review 基于三个并行 agent 对 CLI adapter、Service boundary、init/Fins batch 的走读结果，以及主 reviewer 对以下关键路径的复核：

- `_close_watcher` 的 cancellation cleanup（entrypoint_runtime.py:534-551）
- `cancel_entrypoint_run_and_wait` 的初始 terminal snapshot race 处理（entrypoint_runtime.py:456-469）
- `cancel_entrypoint_run_and_wait` 的 cancel_run 与终态竞争处理（entrypoint_runtime.py:484-487）
- `submit_entrypoint_turn_and_wait` 的 watcher-attach-before-submit 顺序（entrypoint_runtime.py:402 vs 419）
- Outbox cursor 初始化与分页推进（entrypoint_runtime.py:713-755）
- `_resolve_explicit_config_dir` 的 workspace containment 检查（prompt.py:530-535, interactive.py:798-803）
- `_reset_whitelist_paths` 的 symlink/containment 预检（init.py:308-331）
- `_raise_if_legacy_asset_selected` 的 legacy schema 防御（init.py:208-221）
- `SourceKind` 在 CLI fins.py 的依赖范围（fins.py:42）
- PR body 声明的功能与实现的一致性

裁决标准：迁移旧 dayu-agent CLI / Fins 命令的业务语义、用户可见行为、参数面和 cancel 语义，并适配当前 Service boundary、Fins runtime 与 Host public contracts / API。不是迁移旧代码实现。

## Findings

### 已修复项（aggregate deepreview fix gate）

以下 aggregate deepreview 发现已在 WU-CLI-01 aggregate deepreview fix gate（commit `9b4a4407`）中修复，当前代码通过复核：

- **AGG-RV-F01 (已关闭)**：`_close_watcher` cancellation 穿透 cleanup 已修复。`entrypoint_runtime.py:534-551` 使用 `try/finally` 保证：无论 `watcher.aclose()` 成功、抛 `CancelledError` 还是普通异常，`drain_task` 都会被 cancel 并 await 回收。finally 块不吞 watcher close 原始异常。测试覆盖 `aclose()` 抛 `CancelledError` 与普通异常时 drain task 仍被 cancel/awaited（test_entrypoint_runtime.py:844-877）。

### 未发现实质性问题

经逐路径走读和并行专项 review，**未发现**可确认的 correctness defect、boundary violation、semantic mismatch、state machine race、data loss risk 或 architecture regression。PR 在所有 review 重点上均通过：

#### CLI UI adapter 边界 ✅

- CLI 层零 `dayu.engine` import；零 Host durable/command/internal import（仅使用 `dayu.host.api` 与 `dayu.host.open_host` 的 public contract）。
- CLI 层不直接调用 `host.ensure_session()` / `host.submit_followup()` / `host.cancel_run()` / `host.watch_session_events()` / `host.get_run()` / `host.read_outbox_terminal_items()`；所有 Host mutating 操作经 Service helper（`entrypoint_runtime.py`、`fins_direct.py`）。
- CLI 层不直接读取 Fins storage；`SourceKind` import（fins.py:42）是 Fins domain enum，已在 S5 review 中裁决为 accepted plan 允许的依赖。
- Signal handler 仅存在于 CLI 层（prompt.py `_PromptSigintMonitor`、interactive.py `_InteractiveSigintMonitor`、fins.py `_FinsSigintMonitor`），不进入 Service。

#### Service helper 可复用性 ✅

- `entrypoint_runtime.py` 与 `fins_direct.py` 不含 `argparse`、`sys.stdout`/`sys.stderr`、`signal`、`SIGINT`、终端渲染或 CLI 专用格式化概念。
- Service helper 通过 typed dataclass（`EntrypointRuntimeRequest`、`EntrypointTurnRequest`、`EntrypointCancelRequest`、`FinsDirectStartRequest`）暴露接口，可被未来 WeChat/GUI adapter 复用。
- `FinsDirectCommandService` 提供三组构造路径（direct injection、`from_runtime_request`、`from_workspace_root`），支持可注入 `sleep` coroutine，便于测试。
- 测试 `test_import_boundary.py` 强制执行 Service 包不 import `dayu.cli` / `dayu.ui` / `dayu.config` 的边界约束。

#### Host public API 调用链正确 ✅

- `submit_entrypoint_turn_and_wait` 在 submit 前 attach watcher（line 402 watcher attach 早于 line 419 submit），满足 race-free 要求。
- `cancel_entrypoint_run_and_wait` 初始 `get_run` 已终态时跳过 cancel 和 watcher 创建（lines 459-469），直接走 outbox fallback。
- `cancel_run` 与终态竞争时 catch `HostApiError` 后二次 `get_run`，确认终态后继续 observation，未终态则 re-raise（lines 484-487）。
- `command_watermark` 零引用于 CLI/Service 层，不被用作 watch cursor。
- `close_session` 零引用于 CLI/Service 层，不被用于用户 cancel 语义。

#### Outbox terminal observation 路径正确 ✅

- `outbox_cursor` 首次读取时初始化为 `OutboxTerminalCursor(event_sequence=last_observed_event_sequence)`，watcher 无事件时从 0 开始。
- `projection_status.FAILED` → `EntrypointRuntimeError`；`CAUGHT_UP` + 无匹配 terminal → `EntrypointRuntimeError`；`LAGGED` → 返回 `None` 继续 poll。
- `has_more=True` 时按 `next_cursor` 继续分页（line 743-744），不睡眠重读。
- 去重使用 `event_id` + `dedupe_key` + `seen_terminal_event_ids`（lines 648-658）。

#### Fins direct commands 边界正确 ✅

- 不创建 Host Run、不写 Host EventLog；零 `dayu.host` import 在 fins_direct.py 与 CLI fins.py。
- 经 `FinsDirectCommandService` → `DefaultFinsRuntime.get_ingestion_runtime()` → `runtime.start_*` 触达 Fins runtime。
- Cancel 语义正确：job id 前 SIGINT → exit 130；第一次 SIGINT 后发 `request_cancel(job_id)` 并继续 poll；第二次 SIGINT 本地 exit 130 并打印 job id（fins.py:556-565）。
- `upload_filings_from` 只生成 typed batch plan script，不启动 ingestion job。

#### init current-schema bootstrap ✅

- 只做 filesystem bootstrap（workspace root 创建、config/assets 复制）；零 Host open、零 Fins job 创建。
- 旧 `llm_models.json` / `run.json` 不生成——双重防御：`config_file_names()` 不含 legacy 名称（config_loader.py:892-899），`_raise_if_legacy_asset_selected()` 防御性扫描全部 assets（init.py:208-221）。
- 不执行旧 workspace migrations。

#### reset safety ✅

- 白名单硬编码（init.py:291-305）：`workspace/config/`、`workspace/.dayu/host/`、`workspace/.dayu/artifacts/`、`workspace/.dayu/web_tools_storage_states/`。
- 预检 symlink（line 321）→ 不安全则 exit 2；预检 path containment（lines 325-331）→ escape 则 exit 2。
- 保护 `workspace/.dayu/runtime/runtime_lanes.sqlite3`、`<root>/.dayu/`（Fins jobs/SEC cache）、`workspace/fins/` 等不在白名单内的路径。
- 白名单路径不存在时跳过，不算错误（line 285）。

#### _close_watcher cleanup ✅

- `try/finally` 正确（entrypoint_runtime.py:534-551）：`aclose()` 成功/失败/取消后均 cancel 并 await drain task。
- drain task `CancelledError` 被 finally 块吞掉（line 550-551），不吞 watcher close 原始异常。
- 测试覆盖已确认（test_entrypoint_runtime.py:844-877）。

#### Residual risks 追踪 ✅

- Control doc 登记 10 条 residual risks（WU-CLI-01-RR-01 到 WU-CLI-01-RR-10），全部处于 `deferred-with-owner` 状态，每条有明确 owner/destination 和下一步动作。
- AGG-RV-F02（sigint_monitor.install 在 try 块外）→ WU-CLI-01-RR-09，owner CLI hardening follow-up。
- AGG-RV-F03（cancel wait caller-owned timeout）→ WU-CLI-01-RR-10，owner Service/CLI hardening follow-up。

#### PR body 准确性 ✅

- PR body 声称的 5 项功能均与代码实现一致。
- 未将 write workflow、host management、provider interactive、migrations、label registry 或旧 Fins helper 写成已完成。
- PR body 记录的 validation 命令与 control doc 各 gate 验证记录一致。

### 观察（非阻塞）

以下观察不构成 correctness 或 boundary defect，不阻塞 merge，但可作为后续改进参考：

1. **`_resolve_explicit_config_dir` 重复实现**：`prompt.py:513-538` 与 `interactive.py:781-808` 包含逻辑完全相同的 `--config` 路径解析和 containment 校验。这两个函数是 CLI adapter 内的代码重复，不影响 Service 可复用性或 Host boundary。若未来需要统一 CLI config 解析，可提取为 `dayu/cli/` 内共享 helper；当前不阻塞本 WU。

2. **`resolve_runtime_locations` 不做 containment 检查**：该函数接受 `explicit_config_overlay_dir` 后只检查 `is_dir()`，不检查路径 containment。当前所有 CLI caller（prompt.py、interactive.py）在调用前已完成 containment 校验，符合 plan 要求（"调用方已完成 --config path 解析和 containment 校验"）。若未来有非 CLI caller 直接调用此函数且不经外部校验，可能指向任意目录。但这是调用方责任，不是 `resolve_runtime_locations` 当前 contract 的缺陷——其 docstring 未承诺 containment。

3. **`_raise_if_legacy_asset_selected` 的检查范围偏宽**：该函数对所有复制 assets（config + prompts）检查 destination name 是否为 legacy config name（`llm_models.json` / `run.json`）。当前 prompt assets 不含这些文件名，防御有效且无误伤。若未来有人故意将 prompt 文件命名为 `llm_models.json`，init 会拒绝复制——但该场景概率极低且 fail-closed 优于 fail-open。

## Open Questions

无。当前代码核对已覆盖所有 review 重点要求检查的入口、路径和边界。未发现需要额外证据才能判断的不确定行为。

## Residual Risk

| ID | 来源 | 状态 | Owner | 影响范围 |
|---|---|---|---|---|
| WU-CLI-01-RR-01 | plan re-review | deferred-with-owner | Fins owner | `--infer` alias inference 无 approved boundary |
| WU-CLI-01-RR-02 | plan re-review | deferred-with-owner | Fins/tooling owner | `--ci` process snapshot 无 public contract |
| WU-CLI-01-RR-03 | plan re-review | deferred-with-owner | Host/Service owner | Debug/trace/duplicate governance flags 无 Host public per-run contract |
| WU-CLI-01-RR-04 | plan re-review / S6 | deferred-with-owner | Fins owner | `upload_filings_from` 文件识别与旧 CLI 不完全一致 |
| WU-CLI-01-RR-05 | plan re-review | deferred-with-owner | Config/Service owner | `--thinking` / `--no-thinking` 非独立布尔开关 |
| WU-CLI-01-RR-06 | plan re-review / S5 | deferred-with-owner | Fins runtime / CLI signal adapter owner | Fins cancel 协作式、无 `add_signal_handler` 平台 durable cancel UX |
| WU-CLI-01-RR-07 | plan re-review | deferred-with-owner | Fins owner | `upload_filing --action delete` 依赖 upload runtime 支持 |
| WU-CLI-01-RR-08 | S5 review | deferred-with-owner | CLI/Fins product owner | Direct command SUCCEEDED 输出未展示 result_summary |
| WU-CLI-01-RR-09 | aggregate deepreview | deferred-with-owner | CLI hardening follow-up | `sigint_monitor.install()` 在 try 块外，极端异常下可能泄漏 signal handler |
| WU-CLI-01-RR-10 | aggregate deepreview | deferred-with-owner | Service/CLI hardening follow-up | Cancel wait caller-owned timeout 兑现策略未明确定义 |

以上 10 条 residual risks 均已在 control doc 中记录，有明确 owner/destination，均不阻塞本 PR merge。

### CI/check 状态

- GitHub PR checks：**no checks reported** 在本分支（`phase/host-ui-implementation`）上。该仓库可能未配置 CI workflow 或 CI 未对 draft PR 自动触发。
- 本地验证（按 PR body 与 control doc 记录）：
  - `pytest tests/cli -q`：94 passed（control doc S7 re-review gate）
  - `python -m pyright dayu/ tests/ utils/`：0 errors（所有 slice gate 均确认）
  - `git diff --check`：clean（所有 gate 均确认）
- CI 缺失本身是项目级 CI 配置问题，不属于本 PR scope；不应阻塞 merge。

### PR readiness 结论

**PR 已通过本轮 deep review。** 实现符合 WU-CLI-01 accepted plan，架构边界清晰（CLI → Service → Host/Fins），关键路径（watcher attach-before-submit、cancel race handling、outbox fallback、watcher lifecycle cleanup、init reset safety、Fins durable cancel）均沿真实代码路径走读验证通过。未发现 correctness defect、boundary violation 或 behavior regression。

10 条 residual risks 均有明确 owner/destination，不阻塞 merge。PR body 与实际实现一致，未将 future work 写成已完成。

建议：merge-ready（等待用户批准）。

---

审阅人：Claude (deepreview via DeepSeek v4)  
审阅时间：2026-06-14T18:36 CST  
审阅模式：PR Review Mode（并行专项 review + 主 reviewer 关键路径复核）
