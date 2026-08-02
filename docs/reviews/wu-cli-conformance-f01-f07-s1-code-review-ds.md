# Code Review — WU-CLI-CONFORMANCE-F01-F07 S1 / F01

## Scope

- **Mode**: current changes（workspace uncommitted diff）
- **Branch**: `codex/interactive-oracle`
- **Base**: accepted plan commit `4a3dca64466717ebbc1f8c36f4114207b8aed6de`
- **HEAD**: `4a3dca64466717ebbc1f8c36f4114207b8aed6de`（HEAD = plan commit，全部变更为 uncommitted）
- **Output file**: `docs/reviews/wu-cli-conformance-f01-f07-s1-code-review-ds.md`
- **Included scope**: 15 个生产/测试文件，匹配 plan §3.1 allowlist：`dayu/cli/arg_parsing.py`、`dayu/cli/agent_entrypoint.py`、`dayu/cli/commands/session.py`、`dayu/cli/session_execution.py`、`dayu/service/entrypoint_runtime.py`、`dayu/service/host_admin.py`、以及对应 9 个 test 文件。另外走读了 `dayu/runtime/location.py`（独立 runtime location owner）与 `dayu/service/host_assembly.py`（诊断投影消费者）。
- **Excluded scope**: `dayu.runtime` 生产代码（独立 owner，不在本 slice 修改范围）；所有 Host/Engine/Fins 文件；frozen docs/registry；README；`dayu/service/host_assembly.py` 生产逻辑。
- **Parallel review coverage**: 无（单 reviewer 全链路走读）。

### 验证基线

| 项目 | 值 | 状态 |
|---|---|---|
| `docs/cli_ci_oracles.json` SHA-256 | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` | 匹配 plan §0.1 基线 |
| `docs/cli_ci_scenarios.json` SHA-256 | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` | 匹配 plan §0.1 基线 |
| Focused pytest (692 tests) | `692 passed, 3 warnings in 11.47s` | 全部通过 |
| Focused pyright (12 files) | `0 errors, 0 warnings, 0 informations` | 通过 |
| `git diff --cached --name-only` | 空 | index 未污染 |

---

## Findings

### 未发现实质性问题

对全部 15 个 allowlist 文件及独立 runtime location owner 做完备走读后，未发现 correctness、stability、maintainability、semantic ownership drift、overcoupling 或架构违规的实质性问题。以下逐项列出各审查维度的直接证据。

---

#### 1. `--config` action/help/namespace/helper/export/forwarding/request 字段彻底删除

**直接证据**：

- `dayu/cli/arg_parsing.py`：
  - `ParsedCliArgs`（行 161–211）：`config_dir` 字段不存在。
  - `_new_default_namespace()`（行 339–387）：无 `config_dir` 默认赋值。
  - `_build_runtime_arguments_parent(...)` 整函数删除（原行 490–507）；`build_parser()`（行 231–263）中 `root_runtime_parent`/`command_runtime_parent`/`action_runtime_parent` 三个变量全部删除，17 个 parser scope 全部直接使用 `*_common_parent`。
  - `_reject_disallowed_explicit_config(...)` 整函数及 `parse_cli_args()` 中的调用删除。
  - `rg -n '"--config"' dayu/cli/arg_parsing.py`：零命中。
  - `rg -n '_build_runtime_arguments_parent|_reject_disallowed_explicit_config' dayu/`：零命中。

- `dayu/cli/agent_entrypoint.py`：
  - `CONFIG_DIR_OPTION_NAME` 常量删除（行 25）。
  - `resolve_explicit_config_dir(...)` 整函数删除（原行 198–241）。
  - `__all__` 中对应 export 删除（行 294）。
  - `rg -n 'CONFIG_DIR_OPTION_NAME|resolve_explicit_config_dir' dayu/`：零命中。

- `dayu/cli/commands/session.py`：
  - `_prepare_session_admin()`（行 201–221）：删除 `resolve_explicit_config_dir` 调用及 `ServiceHostAdminRequest.config_overlay_dir` 传参。
  - import 中删除 `resolve_explicit_config_dir`（行 17–21）。

- `dayu/cli/session_execution.py`：
  - `_prepare_session_runtime()`（行 598–613）：`EntrypointRuntimeRequest` 构造不传 `explicit_config_dir=None`。

- `dayu/service/entrypoint_runtime.py`：
  - `EntrypointRuntimeRequest`（行 433–450）：`explicit_config_dir` 字段不存在。
  - `prepare_entrypoint_runtime()`（行 885–888）：调用 `resolve_runtime_locations(workspace_root=..., package_config_root=...)` 不传 `explicit_config_overlay_dir`。

- `dayu/service/host_admin.py`：
  - `ServiceHostAdminRequest`（行 28–30）：`config_overlay_dir` 字段不存在；`__post_init__` 中对应类型校验删除（行 43–48）。
  - `prepare_host_admin()`（行 74–77）：新增 `resolve_runtime_locations(...)` 调用，消费 `locations.config_overlay_dir`。

- `rg -n 'explicit_config_dir' dayu/cli/ dayu/service/`：零命中。
- `rg -n 'config_overlay_dir' dayu/cli/`：零命中。
- `rg -n 'config_overlay_dir' dayu/service/`：仅命中 `locations.config_overlay_dir`（独立 runtime location owner 消费）及 `ServiceOpenHostAssemblyDiagnostics.config_overlay_dir`（诊断投影字段，非被删除的 request 字段）。

**结论**：零残留、零 alias、零 wrapper、零 hidden path。

---

#### 2. root/init/prompt/interactive/其它 leaf 在 command 前后均不接受 `--config`

**直接证据**：

- 测试 `test_every_parser_scope_omits_removed_config_action`（`tests/cli/test_arg_parsing.py:426`）：通过 `_collect_parser_tree()` 递归收集 17 个 parser scope，逐 scope 断言 `_actions` 的 `option_strings` 不含 `--config`。
- 测试 `test_every_parser_help_omits_removed_config`（行 444）：参数化 17 个 help 路径（root、12 command、3 session action、1 tool_trace action），全部断言 help 不含 `--config`。
- 测试 `test_removed_config_is_argparse_unknown_in_every_parser_scope`（行 1581）：参数化 12 个 `--config=/tmp/x` 调用（覆盖 root、init、prompt、interactive、download、session list/resume/purge、tool_trace analyze 的 root/command/action scope），全部断言 `SystemExit(2)` + `"unrecognized arguments"` + `"--config"` in stderr。
- 测试 `test_removed_config_split_value_form_never_produces_namespace`（行 1662）：参数化 5 个旧 `--config /tmp/x` 调用（覆盖 root、prompt/interactive command、session command/action scope），全部断言 `SystemExit(2)` + `"error:"` in stderr。

**结论**：`--config` 在所有 parser scope 的 `=` 形式和 split-value 形式均被 argparse 原生 unknown-option 路径拒绝，无有效 namespace 返回。

---

#### 3. split `--config /tmp/x` 原生 argparse 诊断差异

**直接证据**：

- 测试 `test_removed_config_split_value_form_never_produces_namespace` 的 docstring（行 1618–1621）明确记录了诊断措辞随 scope 变化的事实：root scope 可能报 `invalid choice: '/tmp/x'`（因为孤立 token 被当作非法 command），command/action scope 报 `unrecognized arguments: --config /tmp/x`。
- 测试断言仅检查 `SystemExit(2)` 和 stderr 包含 `"error:"`，不强求诊断措辞一致。这符合计划 §3.3 的约束：parser 失败发生在任何 Service/Host 调用前。
- 三个 sentinel 测试（`test_prompt_removed_config_fails_before_service_preparation`、`test_interactive_removed_config_fails_before_service_preparation`、`test_session_removed_config_fails_before_service_preparation`）通过 `monkeypatch` 安装"调用即失败"的 sentinel，覆盖 root 和 command scope 的 `=` 形式 split 调用，证明 Service preparation 未被调用（`captured_requests == []`）。

**结论**：满足 frozen contract 的"parser-owned exit 2，无有效 namespace、Service/Host 调用或副作用"。实现未添加预扫描、hidden action 或二次 reject 兼容特例，符合计划"删除 grammar"和"无兼容/特例"的高优先级约束。

**细微覆盖缺口**（非 finding）：split-value 形式的 action-scope 参数化未覆盖 `session resume`、`session purge`、`tool_trace analyze`。`=` 形式已完整覆盖这些 scope；split-value 在 action scope 的行为（`--config` 无 action → `unrecognized arguments` → SystemExit(2)）与已测试的 `session list --config /tmp/x` 相同。此缺口不影响 verdict，记入 Residual Risk。

---

#### 4. parse 失败在 Service/Host/副作用前

**直接证据**：

- `parse_cli_args()`（`dayu/cli/arg_parsing.py:267–281`）：argparse 解析是同步、在 `asyncio.run()` 或任何 Service/Host 调用之前完成。`--config` 作为 unknown option 时，argparse 在 `parser.parse_args()` 内部直接 `SystemExit(2)`，不返回 namespace。
- 三个 sentinel 测试（见上条）通过 sentinel 未被调用（`captured_requests == []`）直接证明。
- `run_session_command()`（`dayu/cli/commands/session.py:135–167`）：`_prepare_session_admin()` 在 `asyncio.run(_run_session_command_async(...))` 内部调用，此时 parse 已成功完成（无 `--config`）。parse 失败时该函数根本不被调用。

**结论**：parse 失败严格在 Service/Host 打开、workspace mutation 和 Run 创建之前。

---

#### 5. Service runtime/admin 使用 workspace config/package fallback 正确

**直接证据**：

- `prepare_entrypoint_runtime()`（`dayu/service/entrypoint_runtime.py:885–891`）：
  ```python
  locations = resolve_runtime_locations(
      workspace_root=request.workspace_root,
      package_config_root=request.package_config_root,
  )
  runtime_config = ConfigLoader(package_config_dir=request.package_config_root).load(
      workspace_config_dir=locations.config_overlay_dir
  )
  ```
  `locations.config_overlay_dir` 由 runtime location owner 根据 `<workspace>/config` 磁盘存在性决定：存在时为该目录，不存在时为 `None`。`ConfigLoader.load()` 在 `workspace_config_dir=None` 时走 package fallback。

- `prepare_host_admin()`（`dayu/service/host_admin.py:74–80`）：
  ```python
  locations = resolve_runtime_locations(
      workspace_root=request.workspace_root,
      package_config_root=request.package_config_root,
  )
  host_runtime_config = ConfigLoader(
      package_config_dir=request.package_config_root
  ).load_host_runtime(workspace_config_dir=locations.config_overlay_dir)
  ```
  同 pattern。

- 测试 `test_prepare_entrypoint_runtime_uses_package_fallback_without_workspace_config`（`tests/service/test_entrypoint_runtime.py:1066`）：workspace config 不存在时 `config_overlay_dir is None`，`prompt_asset_root` 与 `scene_manifest_root` 正确回退到 package 路径。
- 测试 `test_prepare_host_admin_uses_workspace_config_when_present`（`tests/service/test_host_admin.py:120`）：workspace `config/` 存在时 `host_runtime_id == "workspace-admin"`、db_path 指向 workspace 路径；即 workspace config 正确覆盖 package fallback。

**结论**：workspace config 与 package fallback 的选择由同一 runtime location owner 决定，两个 Service 入口均正确消费。

---

#### 6. `RuntimeLocations.config_overlay_dir` 保持独立 owner

**直接证据**：

- `dayu/runtime/location.py` 完整未修改：
  - `RuntimeLocations.config_overlay_dir: Path | None`（行 29）保持不变。
  - `resolve_runtime_locations(..., explicit_config_overlay_dir: Path | None = None)`（行 38）签名不变；显式路径分支（行 52–60）保持不变。
  - `rg -n 'explicit_config_overlay_dir' dayu/runtime/location.py`：命中 5 处，均为既有独立 contract。
- Service 层从 `EntrypointRuntimeRequest` 和 `ServiceHostAdminRequest` 删除的是**消费者侧**的转发字段，不是 runtime location 的独立能力。两个 Service 入口现在直接调用 `resolve_runtime_locations(workspace_root, package_config_root)`（不传 `explicit_config_overlay_dir`），由 location owner 自行探测 `<workspace>/config`。
- 非 CLI 消费者（如测试、WeChat、未来编程入口）仍可通过 `resolve_runtime_locations(..., explicit_config_overlay_dir=...)` 显式指定覆盖目录。本 slice 不删除、不修改该能力。

**结论**：`RuntimeLocations.config_overlay_dir` 维持独立 owner，未被误删。CLI/Service 消费者正确移交 config location 决策权给 runtime location owner。

---

#### 7. typed construction sites 完整

**直接证据**：

- plan §3.2 的 construction-site allowlist 表中 6 个 typed construction/assertion 类别已全部机械更新：

| typed construction | 旧 keyword | 文件 | 状态 |
|---|---|---|---|
| `EntrypointRuntimeRequest(...)` CLI 生产 | `explicit_config_dir=None` | `dayu/cli/session_execution.py:599` | 已删除 |
| `EntrypointRuntimeRequest(...)` CLI tests | `explicit_config_dir=None` | `test_prompt_command.py:2936`, `test_interactive_command.py:3338`, `test_transient_delivery_interruption_path.py:306` | 已删除 |
| `EntrypointRuntimeRequest(...)` Service tests | `explicit_config_dir=None` | `test_entrypoint_runtime.py:3334`, `test_entrypoint_runtime_interactive_path.py:971,1280`, `test_entrypoint_runtime_prompt_path.py:298,364` | 已删除 |
| `ServiceHostAdminRequest(...)` 生产 | `config_overlay_dir=...` | `dayu/cli/commands/session.py:217` | 已删除 |
| `ServiceHostAdminRequest(...)` tests | `config_overlay_dir=None` | `test_session_command.py:736`, `test_host_admin.py:95,157` | 已删除 |

- `rg -n 'EntrypointRuntimeRequest\(|ServiceHostAdminRequest\(' dayu/cli/ dayu/service/ tests/cli/ tests/service/`：全部构造点均不含已删除 keyword。零残留。

**结论**：全部 typed construction site 已机械更新，无 dataclass default、`**kwargs`、兼容字段或下游忽略残留。

---

#### 8. tests 断言 owner 级 contract 而非 fixture 偶然

**直接证据**：

- **field inventory 断言**：`test_entrypoint_runtime_request_has_no_explicit_config_field`（行 1054）和 `test_service_host_admin_request_has_no_config_override_field`（行 120）通过 `dataclasses.fields()` 枚举字段名，断言旧字段不在 schema 中。这类断言不依赖 fixture 状态，属于 owner contract 级验证。
- **parser action 枚举**：`test_every_parser_scope_omits_removed_config_action` 递归遍历 parser tree 的 `_actions`，断言 option strings 不含 `--config`。这是对 parser owner 的完整 contract 断言。
- **workspace config 行为**：`test_prepare_entrypoint_runtime_uses_package_fallback_without_workspace_config` 和 `test_prepare_host_admin_uses_workspace_config_when_present` 断言 `locations.config_overlay_dir` 的实际值（`None` 或指向正确目录），而非仅验证中间对象形状。
- **正常路径不退化**：`test_prompt_command_outputs_fast_live_terminal_and_converts_requests`（行 1318）中断言 `captured_requests[0].workspace_root == workspace_root`；`test_session_list_calls_host_public_api_and_renders_sessions`（行 616）中断言 `runtime_capture.requests[0].workspace_root == str(tmp_path)`。这些断言确保正常路径仍将 typed workspace root 传递给 Service，而非退化到仅验证"无 crash"。

**结论**：tests 断言 owner 级 contract，不依赖 fixture 偶然。

---

#### 9. scope/分层/类型/docstring 符合计划

**直接证据**：

- **分层**：变更严格限定在 CLI（argparse/entrypoint/session）和 Service（request schema/assembly）层。`dayu.runtime`、Host、Engine、Fins 未修改。删除的是上游 CLI→Service 的转发字段，下游 runtime location owner 保持不变。
- **类型**：所有修改保持严格类型注解。`ParsedCliArgs` 删除 `config_dir: str | None` 不影响其余 40+ 字段的类型完整性。`EntrypointRuntimeRequest` 和 `ServiceHostAdminRequest` 均为 `@dataclass(frozen=True, slots=True)`，字段删除后类型检查自动覆盖全部构造点。
- **docstring**：所有新增/修改函数均有完整中文 docstring（参数、返回值、异常）。新增测试 docstring 均描述 contract 与失败条件。
- **pyright**：focused pyright `0 errors, 0 warnings, 0 informations`。
- **覆盖率**：按 implementation artifact 报告，6 个生产文件均 ≥80%（最低 85%）。

**结论**：scope/分层/类型/docstring/覆盖率均符合计划。

---

#### 10. adversarial failure 与 semantic ownership drift

**adversarial failure pass**：

- auth/permissions/tenant isolation：不适用（CLI parser 层无认证）。
- data loss/corruption：不适用（parse 失败在副作用前）。
- race conditions：不适用（argparse 解析是同步的）。
- empty-state/null：`resolve_runtime_locations` 在 workspace config 不存在时返回 `config_overlay_dir=None`，`ConfigLoader` 正确走 package fallback。有专门测试覆盖。
- missing required parameters：argparse 原生处理，不受本变更影响。
- version skew/schema drift：fresh schema 处理，无兼容迁移需求。
- observability gaps：parse 失败 stderr 包含 `"unrecognized arguments"` 和 `"--config"`，用户可据此诊断。
- external protocol/API boundary：无外部协议涉及。

**semantic ownership drift pass**：

- CLI parser 是"哪些 option 可接受"的唯一 owner。删除 `--config` action 后，CLI 不再承担"配置目录覆盖"语义的传递责任。
- Service request dataclass 是"Service 入口接受哪些参数"的唯一 owner。删除 `explicit_config_dir`/`config_overlay_dir` 字段后，Service 不再暴露该语义给调用方。
- `dayu.runtime.location.resolve_runtime_locations` 是"runtime 位置如何从 workspace + package config 解析"的唯一 owner。该函数及其 `explicit_config_overlay_dir` 参数保持不变，供非 CLI 消费者使用。
- 三个 owner 边界清晰：CLI 删除 syntax → Service 删除 forwarding → Runtime location 保持独立能力。无下游用 fallback、特例或 loose parsing 补偿。
- 无 `hasattr`/`getattr`、无兼容 shim、无测试固化旧行为。

**overcoupling pass**：

- 变更减少耦合：CLI→Service 的 `explicit_config_dir` 传递链被切断，CLI 和 Service 现在只通过 typed `workspace_root` + `package_config_root` 通信。config location 解析是 `dayu.runtime` 的内部决策。
- `EntrypointRuntimeRequest`、`ServiceHostAdminRequest` 各自独立，不共享 config 字段。
- `RuntimeLocations.config_overlay_dir` 消费者（`entrypoint_runtime.py`、`host_admin.py`、`host_assembly.py` diagnostics）都从同一 `RuntimeLocations` 实例读取，复用同一真源。

**结论**：无 adversarial failure 或 semantic ownership drift 问题。

---

#### 11. README 延迟符合计划

plan §3.1 明确："根 `README.md` 的用户文档删除延迟到 S8，以便按最终实际 CLI 一次同步。S1 不允许修改任何 README。" 当前变更未修改任何 README 文件。符合计划。

---

## Open Questions

无。

---

## Residual Risk

1. **split-value `--config /tmp/x` 在 action scope 的测试参数化缺口**：`test_removed_config_split_value_form_never_produces_namespace` 覆盖了 root scope（`--config /tmp/x prompt hello`）、command scope（`prompt --config /tmp/x hello`、`interactive --config /tmp/x`、`session --config /tmp/x list`）和 action scope（`session list --config /tmp/x`）。未参数化 `session resume`、`session purge`、`tool_trace analyze` 的 action-scope split-value 形式。`=` 形式已完整覆盖这些 scope；split-value 在 action scope 的行为（`--config` 无注册 action → `unrecognized arguments: --config /tmp/x` → SystemExit(2)）与已测试的 `session list --config /tmp/x` 完全一致，因为 argparse 在 action scope 遇到 unknown optional 的处理逻辑不依赖具体 action 名称。**风险等级：极低**。

2. **全仓 pytest/pyright 与真实 CLI evidence 延迟到 S8**：按计划，S1 只做 focused validation。全仓回归和真实 CLI 端到端验证在 S8 integration/closeout 执行。**风险等级：低**，因为 S1 变更范围严格限定、focused tests 全部通过、且每个 production construction site 都被 typed dataclass 约束。

3. **`dayu/service/host_assembly.py` 中 `ServiceOpenHostAssemblyDiagnostics.config_overlay_dir`**（行 332）：该诊断字段仍然存在，从 `locations.config_overlay_dir` 取值（行 1752）。S1 不修改该文件，诊断投影语义不受影响；若未来有人误以为该字段是"被删除的 request 字段"并删除，会导致诊断输出缺失 config overlay 信息。已在本 review 中核验其为独立的诊断投影消费者，非被删字段。**风险等级：极低**。

---

## Verdict

**PASS** — S1/F01 implementation 满足 accepted plan §3 全部 contract 与约束：

- `--config` action/help/namespace/helper/export/forwarding 在所有 17 个 parser scope 彻底删除，零残留。
- 所有位置（root/command/action）的 `--config` 均由 argparse 原生 unknown-option 路径以 exit 2 拒绝，无有效 namespace。
- Parse 失败严格在 Service/Host/副作用之前（三个 sentinel 测试直接证明）。
- Service runtime/admin 正确使用 workspace config/package fallback，由同一 runtime location owner 决定。
- `RuntimeLocations.config_overlay_dir` 保持独立 owner，未被误删。
- 全部 typed construction sites 已机械更新，零残留。
- Tests 断言 owner 级 contract（field inventory、parser action 枚举、workspace config 行为）。
- Scope/分层/类型/docstring/覆盖率符合计划。
- 无 adversarial failure、semantic ownership drift 或 overcoupling 问题。
- Frozen oracle SHA-256 未变。
- 692 focused tests 全部通过，pyright 零错误。

**下一合法入口**：按 plan §3，S1 code review 完成后进入下一 slice（S2/F02 或按 Gateflow 裁决顺序）。
