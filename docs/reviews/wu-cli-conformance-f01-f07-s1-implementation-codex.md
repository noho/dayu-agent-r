# WU-CLI-CONFORMANCE-F01-F07 S1 Implementation 记录（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S1 / F01 — 删除全局 --config`
- Gate：`implementation`
- Accepted plan commit：`4a3dca64466717ebbc1f8c36f4114207b8aed6de`
- 分支：`codex/interactive-oracle`
- 状态：`IMPLEMENTATION COMPLETE — next: S1 code review`
- Artifact：`docs/reviews/wu-cli-conformance-f01-f07-s1-implementation-codex.md`

## Preflight 与 scope

实施前直接检查结果：

- `git status --short` 无输出，工作树 clean。
- `git diff --cached --name-only` 无输出，index empty。
- HEAD 精确为 accepted plan commit `4a3dca64466717ebbc1f8c36f4114207b8aed6de`。
- `docs/cli_ci_oracles.json` SHA-256 为
  `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- `docs/cli_ci_scenarios.json` SHA-256 为
  `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
- typed constructor inventory 与 plan §3.2 表一致。allowlist 外的
  `RuntimeLocations.config_overlay_dir`、`resolve_runtime_locations(...,
  explicit_config_overlay_dir=...)` 及 Host assembly diagnostics 属于独立
  runtime location contract，不是被删除的 CLI/Service request 字段。

实际修改严格限于 plan §3.1 的 15 个生产/测试文件，并新增本 artifact：

- `dayu/cli/arg_parsing.py`
- `dayu/cli/agent_entrypoint.py`
- `dayu/cli/commands/session.py`
- `dayu/cli/session_execution.py`
- `dayu/service/entrypoint_runtime.py`
- `dayu/service/host_admin.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_transient_delivery_interruption_path.py`
- `tests/cli/test_session_command.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_host_admin.py`

未修改 README、design、frozen docs/registry、Host、Engine 或 `dayu.runtime`。
未 stage、commit、push 或操作 PR。

## 语义 owner 与实现决策

### CLI parser owner

- 从 `ParsedCliArgs` 删除 `config_dir`。
- 删除所有 root/command/action parser 的 `--config` action 与 help。
- 删除 namespace default、`_reject_disallowed_explicit_config(...)` 及调用。
- 删除只为配置选项存在的 runtime parent parser；所有 parser scope 直接复用
  common parent，不保留 alias、wrapper、hidden action 或二次 reject。
- root、12 个 command、3 个 session action 与 `tool_trace analyze` 共 17 个
  parser scope 的 action/help inventory 均无 `--config`。

### CLI entrypoint 与 session call path

- 从 `dayu.cli.agent_entrypoint` 删除 `CONFIG_DIR_OPTION_NAME`、
  `resolve_explicit_config_dir(...)` 和 `__all__` export。
- session admin preparation 不再读取 `args.config_dir`，只把 typed
  `workspace_root` 与 package config root 传给 Service。
- prompt/interactive/session runtime construction 不再传
  `explicit_config_dir=None`。

### Service request 与 runtime location owner

- 从 `EntrypointRuntimeRequest` 删除 `explicit_config_dir`。
- 从 `ServiceHostAdminRequest` 删除 `config_overlay_dir` 及其校验。
- `prepare_entrypoint_runtime(...)` 与 `prepare_host_admin(...)` 都直接调用既有
  `resolve_runtime_locations(workspace_root, package_config_root)`，再消费其
  `RuntimeLocations.config_overlay_dir` 投影。workspace `<base>/config` 与 package
  fallback 因而由同一个 runtime location owner 决定。
- 独立 `RuntimeLocations.config_overlay_dir` 与
  `resolve_runtime_locations(..., explicit_config_overlay_dir=...)` 保持不变。

## Owner-level tests

新增或加强以下断言：

- 递归枚举 root/command/action parser `_actions`，17 个 scope 均无
  `--config`；所有对应 help 均无该选项。
- `--config=/tmp/x` 在 root、command、action 位置均由 argparse 以
  `unrecognized arguments` 和 exit 2 拒绝；正常 namespace 无 `config_dir`。
- 旧 split-value 形式 `--config /tmp/x` 在 root、command、action 位置均在
  有效 namespace 返回和命令分发前 exit 2。
- prompt、interactive、session 的 removed-option tests 安装“调用即失败”的
  Service preparation sentinel，证明 parser failure 前不会进入 Service。
- 正常 prompt、interactive、session 路径继续传递 typed workspace root。
- request dataclass field inventory 证明两个旧字段均不存在；全部 construction
  site 已机械删除旧 keyword。
- entrypoint runtime 验证 workspace config 与无 workspace config 时的 package
  prompt/manifest fallback；Host admin 验证 package fallback 和 workspace
  `config/host_runtime.json` overlay。

原生 argparse 对 split-value 的诊断有位置差异：当未知 option 位于 subcommand
前时，孤立的 `/tmp/x` 可能被报告为非法 command/action；该调用仍是 parser-owned
exit 2，且没有有效 namespace、Service/Host 调用或副作用。实现未为诊断措辞增加
removed-option 预扫描、hidden action 或二次 reject；S1 code review 应显式核验该
取舍符合“删除 grammar”与“无兼容/特例”的高优先级约束。

## 验证命令与结果

### Focused pytest

```bash
source .venv/bin/activate
pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_transient_delivery_interruption_path.py tests/cli/test_session_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_host_admin.py -q
```

结果：`692 passed, 3 warnings in 11.18s`。三条 warning 均来自 `edgar`
依赖的既有 deprecation warning。

### Focused pyright

按 plan §3.4 对六个生产文件和列出的 CLI/Service tests 执行 focused pyright，
结果：`0 errors, 0 warnings, 0 informations`。计划命令未列但本 slice 修改的
`tests/cli/test_arg_parsing.py` 另行执行同一检查，结果同样为零错误。

### 单文件覆盖率

使用同一 focused pytest 集合执行 coverage，并逐生产文件使用
`--fail-under=80`：

| 文件 | 覆盖率 |
|---|---:|
| `dayu/cli/arg_parsing.py` | 99% |
| `dayu/cli/agent_entrypoint.py` | 93% |
| `dayu/cli/commands/session.py` | 85% |
| `dayu/cli/session_execution.py` | 86% |
| `dayu/service/entrypoint_runtime.py` | 88% |
| `dayu/service/host_admin.py` | 86% |

### Parser inventory、source scan 与完整性

- parser inventory：17 个 scope；action/help 中 `--config` 零命中；正常
  `ParsedCliArgs` namespace 中 `config_dir` 不存在。
- 被删生产符号扫描：`--config`、`resolve_explicit_config_dir`、
  `explicit_config_dir`、`CONFIG_DIR_OPTION_NAME`、request/call-path
  `config_dir` 在六个生产 owner 文件中零命中。
- constructor inventory：所有 `EntrypointRuntimeRequest(...)` 与
  `ServiceHostAdminRequest(...)` construction site 均不再传旧 keyword。
- 独立 runtime location scan：`RuntimeLocations.config_overlay_dir` 与
  lower-level explicit location input 仍存在，未误删。
- `git diff --check`：通过。
- `python -m json.tool docs/cli_ci_oracles.json`：通过。
- `python -m json.tool docs/cli_ci_scenarios.json`：通过。
- registry SHA-256：与 preflight/plan 固定值完全一致。
- `git diff --cached --name-only`：无输出，index 仍为空。

## Docs decision

README 更新按 accepted plan 延迟到 S8。本 slice 不改变或提前同步 README、design、
`docs/cli_ci.md` 或 registry；唯一新增 docs 文件是本 implementation gate artifact。

## Residual risks 与未覆盖项

- `covered by later approved slice (S8)`：全仓 pytest、全仓 pyright、最终真实 CLI
  evidence 与 README 同步不属于 S1 focused implementation validation，将在 S8
  integration/closeout 执行。
- 没有未分类 residual risk；没有发现需要扩展 allowlist 的 typed owner。

## Completion 与下一入口

S1 implementation 已完成，生产与测试 diff 未 stage。当前停止，不进入 review、
fix、commit、push 或 PR 操作。下一合法入口为 **S1 code review**。
