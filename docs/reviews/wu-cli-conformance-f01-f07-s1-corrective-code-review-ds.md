# WU-CLI-CONFORMANCE-F01-F07 S1/F01 Corrective Fix Code Review（DeepSeek）

## Scope

- Mode: current changes（未提交 workspace diff 相对 HEAD `e5b572d4`）
- Branch: `codex/interactive-oracle`
- Base: `e5b572d44fa86beac8a23413007cc48805c9ba67`
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s1-corrective-code-review-ds.md`
- Included scope:
  - `utils/smoke_cli_init_provider_matrix.py`（unstaged diff，删除一行 `explicit_config_dir=None`）
  - `utils/smoke_host_public_awaiting_entrypoint.py`（unstaged diff，删除一行 `explicit_config_dir=None`）
  - `docs/reviews/wu-cli-conformance-f01-f07-s1-corrective-fix-codex.md`（corrective artifact，untracked）
  - 全仓 `explicit_config_dir` / `CONFIG_DIR_OPTION_NAME` / `resolve_explicit_config_dir` 残留扫描
  - 全部 13 个 `EntrypointRuntimeRequest(...)` 与 4 个 `ServiceHostAdminRequest(...)` typed constructor call site 逐点核验
  - `EntrypointRuntimeRequest` 与 `ServiceHostAdminRequest` owner dataclass 定义
  - `dayu/runtime/location.py` 独立 lower-level `explicit_config_overlay_dir` owner boundary 核验
  - Focused pyright（两个修改文件）、full pyright、compile、import、registry JSON/SHA-256、git diff --check、index
- Excluded scope:
  - `tests/` 下所有 owner-level test 文件（已在 S1 accepted commit 中完成，不在本次 corrective diff 内）
  - `dayu/` 生产代码（S1 已修改完毕，不在本次 diff 内）
  - 真实 smoke 外部 provider/Host 场景执行（不在本 review gate 授权范围）
  - 本次不运行 pytest（两个修改文件位于 `utils/`，按项目约束默认无需测试与覆盖率）
- Parallel review coverage: 无（scope 紧凑，单一 reviewer 逐路径走读）

## Findings

未发现实质性问题。

### 逐项核验记录

#### 1. 因果链确认

- **root cause**：S1 commit `a41526ec` 从 `EntrypointRuntimeRequest`（`dayu/service/entrypoint_runtime.py:434`）owner dataclass 删除了 `explicit_config_dir` 字段。当前 class 定义（lines 433-450）仅有 6 个字段：`workspace_root`、`package_config_root`、`scene_id`、`context_slot_values`、`assembly_overrides`、`env`。
- **遗漏点**：S1 accepted plan §3.2 的 construction-site inventory table 与 `rg` 扫描命令 scope 为 `dayu/cli dayu/service tests/cli tests/service`，未覆盖 `utils/` 目录下的两个 smoke 脚本。
- **直接证据**：修复前 focused pyright 在 `utils/smoke_cli_init_provider_matrix.py:2386` 与 `utils/smoke_host_public_awaiting_entrypoint.py:808` 各报告 `No parameter named "explicit_config_dir" (reportCallIssue)`。修复后两个文件各自 `0 errors, 0 warnings, 0 informations`。
- **修复边界正确**：机械删除过期 keyword，未恢复字段、未增加 alias/wrapper/default/loose parsing/下游补偿。

#### 2. 精确 scope 验证

| 检查项 | 状态 | 直接证据 |
|---|---|---|
| diff 仅含两个 utils 文件各删除一行 | `pass` | `git diff HEAD` 输出精确为两处 `-explicit_config_dir=None` 删除 |
| 无其他文件被修改 | `pass` | `git diff HEAD --stat` 仅两个文件，各 1 insertion / 1 deletion |
| 无兼容字段/alias/wrapper | `pass` | `rg -n 'explicit_config_dir\|CONFIG_DIR_OPTION_NAME\|resolve_explicit_config_dir' --glob '*.py' dayu tests utils` 仅命中 `tests/service/test_entrypoint_runtime.py:1063` 的 owner 负向断言 `assert "explicit_config_dir" not in field_names` |
| staged index 为空 | `pass` | `git diff --cached --name-only` 零行输出 |
| registry 未变 | `pass` | SHA-256 与 S1 冻结基线一致：`f9972d94...` / `7f283b03...` |
| registry JSON 有效 | `pass` | `python -m json.tool` 两个文件均通过 |

#### 3. 全部 typed constructor call site 逐点核验

对全部 13 个 `EntrypointRuntimeRequest(...)` call site 逐一搜索 `explicit_config_dir`：

| 文件 | 行号 | 状态 |
|---|---|---|
| `dayu/cli/session_execution.py` | 599 | 无旧 keyword（S1 已清理） |
| `tests/cli/test_prompt_command.py` | 2130, 2936 | 无旧 keyword（S1 已清理） |
| `tests/cli/test_interactive_command.py` | 3574 | 无旧 keyword（S1 已清理） |
| `tests/cli/test_transient_delivery_interruption_path.py` | 306 | 无旧 keyword（S1 已清理） |
| `tests/service/test_entrypoint_runtime.py` | 1078, 3334 | 无旧 keyword（S1 已清理）；line 1063 含 owner 负向断言 |
| `tests/service/test_entrypoint_runtime_prompt_path.py` | 298, 364 | 无旧 keyword（S1 已清理） |
| `tests/service/test_entrypoint_runtime_interactive_path.py` | 971, 1280 | 无旧 keyword（S1 已清理） |
| `utils/smoke_cli_init_provider_matrix.py` | 2383 | 本次修复删除旧 keyword |
| `utils/smoke_host_public_awaiting_entrypoint.py` | 805 | 本次修复删除旧 keyword |

全部 4 个 `ServiceHostAdminRequest(...)` call site（`dayu/cli/commands/session.py:217`、`tests/cli/test_session_command.py:736`、`tests/service/test_host_admin.py:95,157`）同样零残留 `config_overlay_dir` keyword。

对全部 13 个 call site 的逐文件 `rg -n 'explicit_config_dir' <file>` 搜索结果为：仅 `tests/service/test_entrypoint_runtime.py:1063` 命中（owner 负向断言），其余文件零命中。

#### 4. `dayu/runtime/location.py` 独立 lower-level API 核验

- `resolve_runtime_locations(..., explicit_config_overlay_dir: Path | None = None)` — 该参数属于 `dayu.runtime` 公共基础设施的独立 location resolver API。
- S1 accepted plan §3.2 明确："保留 `dayu.runtime` 中可独立复用的底层 location resolver，不把 CLI 兼容语义带入该公共基础设施。"
- S1 controller adjudication 确认："`RuntimeLocations.config_overlay_dir` 与 lower-level `explicit_config_overlay_dir` 未修改，仍由 `dayu.runtime.location` 独立拥有。"
- `tests/runtime/test_runtime_location.py` 仍有独立测试覆盖该 API。
- **结论**：该参数不是 F01 残留，是独立 runtime 能力。不报告。

#### 5. 验证命令与结果复验

| 验证项 | 命令 | 结果 |
|---|---|---|
| Focused pyright（两个修改文件） | `python -m pyright utils/smoke_cli_init_provider_matrix.py utils/smoke_host_public_awaiting_entrypoint.py` | `0 errors, 0 warnings, 0 informations` |
| Full pyright | `python -m pyright` | `0 errors, 0 warnings, 0 informations` |
| Compile | `python -m py_compile utils/smoke_cli_init_provider_matrix.py utils/smoke_host_public_awaiting_entrypoint.py` | exit 0，无输出 |
| Import | `python -c 'import utils.smoke_cli_init_provider_matrix; import utils.smoke_host_public_awaiting_entrypoint'` | exit 0，无输出 |
| git diff --check | `git diff --check` | 通过 |
| F01 全仓残留扫描 | `rg -n 'explicit_config_dir' --glob '*.py' .` | 仅 `tests/service/test_entrypoint_runtime.py:1063`（owner 负向断言） |
| Registry SHA-256 | `shasum -a 256 docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` | 与 S1 冻结基线一致 |
| Registry JSON | `python -m json.tool` 两个文件 | 均通过 |
| Index | `git diff --cached --name-only` | 空 |

#### 6. Corrective artifact 核验

- artifact 路径：`docs/reviews/wu-cli-conformance-f01-f07-s1-corrective-fix-codex.md`
- 结构完整：Gate 元数据、动机/因果/语义 owner、Scope 与实际修改、验证命令与结果、Docs decision、Findings/residual risks/下一入口。
- 所有声称的验证结果与本 review 独立复验一致。
- 未发现 artifact 与代码实际状态之间的偏差。

#### 7. 是否遗漏其它 typed constructor

- 全仓 `rg -n 'EntrypointRuntimeRequest\(' --glob '*.py' .` 输出 13 个 call site，全部逐点核验，仅两个 utils 文件曾有旧 keyword。
- 全仓 `rg -n 'ServiceHostAdminRequest\(' --glob '*.py' .` 输出 4 个 call site，全部清洁。
- 全仓 `rg -n 'explicit_config_dir' --glob '*.py' .` 仅 owner 负向断言。
- **结论**：没有遗漏其它 typed constructor。

## Open Questions

无。

## Residual Risk

- **未运行真实 smoke**：两个修改文件是 smoke 脚本，修复后未在真实外部 provider/Host 场景中执行。但这是机械 contract 修复（删除过期 keyword），不改变运行时语义；focused/full pyright、compile 与 import 已覆盖类型安全。真实场景执行属于 S8 integration gate，不在本 corrective review gate 授权范围。
- **Plan inventory gap**：S1 accepted plan §3.2 的 construction-site inventory table 与 `rg` 扫描命令 scope 未覆盖 `utils/` 目录。这是原 plan 的 inventory 边界选择（`utils/` 下的 smoke 脚本不在 S1 允许修改文件列表中），不是代码缺陷。两个 missed call site 现已被 corrective fix 覆盖，且全仓 `explicit_config_dir` 搜索证实再无遗漏。

## Verdict

**PASS** — 无 accepted finding。两个机械 keyword 删除与 owner contract 一致；F01 Python 实现零残留；无兼容字段/alias/wrapper；focused 与 full pyright 均为 0；compile/import/diff/registry/index 均通过；无遗漏 typed constructor。corrective artifact 与代码实际状态一致。
