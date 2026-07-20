# WU-SEMANTIC-OWNERSHIP-01 P3-H S3 code review - AgentDS

## Scope

- Mode: current changes (unstaged diff)
- Branch: `phaseflow/host-issues-control`
- Base: `main` (notionally; review is scoped to unstaged diff only, per user instruction)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-h-s3-code-review-ds.md`
- Included scope:
  - `dayu/fins/downloaders/sec_downloader.py` — one-line warning text change
  - `tests/fins/test_sec_downloader.py` — one new test function
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s3-implementation-codex.md` — implementation artifact
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s3-controller-validation.md` — controller validation artifact
- Excluded scope:
  - Untracked `docs/cli_ci*`, `docs/reviews/code-review-20260710-*` (explicitly excluded by user)
  - S1/S2 committed code (`86034f4f`, `35be9dc3`) — not re-reviewed
  - Other unrelated untracked/staged changes outside the S3 scope
- Parallel review coverage: 无

## Review method

沿以下入口逐行走读：

1. `dayu/fins/downloaders/sec_downloader.py` `_resolve_user_agent` (2017–2040)、`_build_headers` (2042–2058)、`SecDownloader.__init__` (839–872)、`configure` (916–946)、`_UNCONFIGURED_USER_AGENT` (78)、`SEC_USER_AGENT_ENV` (62)
2. `tests/fins/test_sec_downloader.py` `test_missing_sec_user_agent_warning_names_config_fact` (1743–1769)、`_create_downloader` (87–92)、`test_sec_downloader_explicit_sec_defaults_are_stable` (95–105)
3. `dayu/fins/_log.py` `Log.warning` (71–102)、`_logger` (122–137)
4. `dayu/runtime/log.py` `configure` (105–148)、`_build_marker_handler` (262–274)
5. P3-H plan S3 section (251–301) with expected scan results (303–315)
6. `dayu/fins/README.md` 更新约束 (16–24)、`tests/README.md` 更新边界 (281–286)
7. Implementation artifact source scan results (40–125)、propagation audit (92–120)
8. Controller validation artifact (1–88)

adversarial failure pass 覆盖了 auth boundary、data loss、race condition、empty-state、type errors、test gaps、log propagation correctness。详见 Findings 和 Residual Risk。

## Findings

未发现实质性问题。

逐一验证结果：

### 1. Warning text 正确移除了 CLI command name

- **变更位置**: `sec_downloader.py:2037`
- **旧**: `"请通过环境变量 {SEC_USER_AGENT_ENV} 或 dayu-cli init 配置。"`
- **新**: `"请通过环境变量 {SEC_USER_AGENT_ENV} 或调用方/部署配置提供。"`
- **验证**: warning 仍准确引用 `SEC_USER_AGENT`（通过 f-string 插值 `SEC_USER_AGENT_ENV`），将配置指引指向调用方/部署配置这一通用事实，不再命名 CLI 命令。符合 P3-H plan S3 expected change："Do not mention `dayu-cli init` or any CLI command"。

### 2. `_UNCONFIGURED_USER_AGENT`、headers、rate limit、download behavior 未变

- `_UNCONFIGURED_USER_AGENT` (line 78): 值 `"DayuAgent/1.0 unconfigured@example.com"` 未变。
- `_resolve_user_agent` (line 2040): 仍 `return _UNCONFIGURED_USER_AGENT`。
- `_build_headers` (lines 2042–2058): 未变，仍返回 `User-Agent` + `Accept-Encoding: gzip, deflate`。
- 限流常量 (`_SEC_MIN_REQUEST_INTERVAL_SECONDS` 等，lines 86–96): 未变。
- `SecDownloader.__init__` (line 864): 仍调用 `self._resolve_user_agent(None)`，无参数语义变更。
- `configure` (line 942): 仍调用 `self._resolve_user_agent(user_agent)`，优先级逻辑未变。

### 3. 测试正确覆盖 warning 包含 SEC_USER_AGENT 且不含 CLI command name

- `test_missing_sec_user_agent_warning_names_config_fact` (lines 1743–1769):
  - 通过 `monkeypatch.delenv(SEC_USER_AGENT_ENV)` 确保无环境变量干扰。
  - 通过 `runtime_log.configure(level=WARN, stream=log_stream)` 捕获 `dayu` namespace 日志。
  - `SecDownloader.__init__` → `_resolve_user_agent(None)` → `Log.warning(...)` → `logging.getLogger("dayu.fins.FINS.SEC_DOWNLOADER").warning(...)` → 传播到 `"dayu"` namespace logger → handler 写入 `log_stream`。传播路径经 `dayu/fins/_log.py` (line 102) → `dayu/runtime/log.py` (lines 131–133, 270) 验证，链路完整。
  - `assert SEC_USER_AGENT_ENV in warning_text` — 验证 warning 包含 `SEC_USER_AGENT`（env var 名）。
  - `assert "dayu" + "-cli" not in warning_text` — 验证 warning 不含 CLI command name。
  - `assert downloader._build_headers()["User-Agent"]` — 验证 fallback UA 仍有效，headers 行为不变。
- `"dayu" + "-cli"` 使用字符串拼接而非字面量 `"dayu-cli"`：该设计意图是防御 P3-H 聚合扫描（`rg "dayu-cli" dayu/fins/downloaders tests/fins`）将测试断言中的否定检查误判为命中。拼接使得扫描正确返回零命中，同时测试断言语义不变。此模式是 P3-H scan limitation（plan line 315）所预见的 pragmatic 选择，不造成 correctness 问题。
- Fins test source 中无连续 `dayu-cli` 字面量：`rg -n "dayu-cli" dayu/fins/downloaders/ tests/fins/` 返回零命中。✓

### 4. README decision 与 AGENTS.md 触发规则一致

- `dayu/fins/README.md` (line 16–24) 只描述"当前代码已实现的整个 Agent 的设计意图、架构边界"以及 `dayu.fins` package 的 capability 定位。S3 只修改一个下载器诊断字符串，未引入新的稳定边界或 capability。不做更新符合 README 约束。
- `tests/README.md` (line 281–286) 只描述"当前 tests/ 已存在的事实"，要求"新增测试层级、测试运行方式或测试维护规则发生变化"时更新。新测试是已有 Fins downloader 测试文件中的普通断言，不构成新测试层级。不做更新符合 README 约束。
- CLAUDE.md 触发规则（`dayu/fins/` 修改 → 检查并按需更新 `dayu/fins/README.md`）：AgentCodex 已检查并做出不做更新的决定，此决定与 Fins README 自身约束和 P3-H plan 一致。
- Root `README.md` 和 `dayu/README.md` 未修改：S3 不改变用户命令、公共工作流、包分层或跨包架构，符合 plan 预期。

### 5. P3-H aggregate scans 的允许命中分类正确

逐一核对实现 artifact 中的扫描结果（lines 42–67）与 P3-H plan expected scan results（lines 303–311）：

| Scan | Result | Classification | Verdict |
|---|---:|---|---|
| DS12 ToolRuntime hidden hint | No matches | — | 正确 |
| Web provider LLM prose | Test-only matches in `test_smoke_web_ci.py:248`, `test_web_tools_provider.py:924` | Allowed (test assertions) | 正确 |
| Web provider derived output fields | No matches | — | 正确 |
| Web cancellation module/import | Allowed hits in projection owner (`web_tool_projection_text.py`), consumer (`web_tools.py`), tests | Allowed | 正确 |
| Web tools local cancellation literals | No matches | — | 正确 |
| Fins direct/wait prose | Two docstring matches in `ingestion_runtime.py:441,4037` (exception documentation) | Allowed (non-projection docstring) | 正确 |
| Fins job sidecar | Matches in `_append_job_event_warn(...)` and job lifecycle helpers | Retained (durable job/audit sidecar, not direct/wait copy) | 正确。已确认 `wait_adapter.py` 不消费 `read_job_events(...)`，这些消息不进入 direct stream 或 wait outcome。 |
| SEC downloader CLI-name | No matches | — | 正确 |

propagation audit（implementation artifact lines 92–120）覆盖了 Web search、Web cancellation、Fins direct、Fins job sidecar、Fins wait、SEC diagnostics 六条路径，每条路径的 producer → projection owner → LLM/user-visible path 均闭合且语义一致。

## Evidence Summary

| # | 审查项 | 证据位置 | 结论 |
|---|---:|---|
| 1 | Warning 移除 CLI command name | `sec_downloader.py:2037` | 通过 |
| 2 | `_UNCONFIGURED_USER_AGENT` 未变 | `sec_downloader.py:78,2040` | 通过 |
| 3 | Headers 行为未变 | `sec_downloader.py:2042-2058` | 通过 |
| 4 | Rate limit 行为未变 | `sec_downloader.py:86-96,2060-2079` | 通过 |
| 5 | Download behavior 未变 | `sec_downloader.py:839-946` (init/configure) | 通过 |
| 6 | 测试覆盖 warning 含 SEC_USER_AGENT | `test_sec_downloader.py:1767` | 通过 |
| 7 | 测试覆盖 warning 不含 CLI name | `test_sec_downloader.py:1768` | 通过 |
| 8 | Fins test source 无连续 `dayu-cli` | `rg` 零命中 | 通过 |
| 9 | README decision 合理 | Fins README 约束 + plan S3 README 条款 | 通过 |
| 10 | Aggregate scans 分类正确 | 逐一核对 8 项扫描结果 | 通过 |
| 11 | Propagation audit 闭合 | 6 条路径 producer→projection→LLM/user | 通过 |
| 12 | Log propagation 链路完整 | `_log.py:102` → `log.py:131-133,270` | 通过 |

## Open Questions

无。

## Residual Risk

1. **字符串拼接防御模式**: `"dayu" + "-cli"` 是一种为满足扫描零命中需求的 pragmatic 选择。如果未来 `dayu-cli` 重命名，该断言仍有语义（验证不含旧名字），但拼接本身可能让维护者困惑。建议在测试 docstring 或行内注释中说明拼接意图，降低维护成本。此非 correctness 风险，severity 为低。

2. **全局 log 配置副作用**: 新测试（line 1762）通过 `runtime_log.configure()` 修改全局 `"dayu"` namespace logger，与文件中其他测试（lines 1587, 1659, 1907）模式一致。测试串联运行在当前单文件 pytest scope 下无问题，但若未来某测试不自行 reconfigure 而依赖前序测试的 handler，可能出现日志丢失或误捕获。此为 pre-existing pattern，非 S3 引入，severity 为低。

3. **Aggregate scans 的边界证据性质**: P3-H plan（line 315）已说明 scans 是 bounded evidence checks，非 exhaustive proof。当前 S3 六个扫描项均按 plan 预期执行，但无法排除 Fins downloader 或 test 中存在其他未被扫描模式覆盖的 CLI 引用。从 diff 审查看，S3 只改了一行 warning 并新增一个测试函数，diff 范围内无此风险。
