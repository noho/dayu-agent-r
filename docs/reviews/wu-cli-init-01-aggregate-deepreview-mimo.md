# WU-CLI-INIT-01 Aggregate Deep Review — MiMo

## 审查范围

- **Work unit**：`WU-CLI-INIT-01`
- **审查类型**：aggregate deep review（Goal Confirmation → ae907b26 全部组合变更）
- **base commit**：`3bfbd7f9`
- **head commit**：`ae907b26`
- **变更规模**：80 files changed, 21683 insertions(+), 348 deletions(-)
- **审查者**：AgentMiMo（Claude Code / MiMo）
- **审查日期**：2026-07-30

## Contract 基准

| 来源 | 版本 / commit |
|---|---|
| `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md` | 2026-07-30 用户确认 |
| 用户补充裁决：Host SQLite resolved credential 明文允许 | 2026-07-30 |
| 用户补充裁决：compactor 同 family | Goal Confirmation |
| 用户补充裁决：`--model/-m` 单次主 Run 不覆盖 compactor | Goal Confirmation |
| `AGENTS.md`（编码硬约束、语义所有权、LLM-facing 文本约束） | 项目级 |
| `docs/cli_ci_oracles.json` → `cli.init.workspace-initialization@1` | version 1 |

## 审查维度

| # | 维度 | 判定 |
|---|---|---|
| 1 | Correctness against oracle predicates | ✅ PASS |
| 2 | Semantic owner boundary | ✅ PASS |
| 3 | Cross-slice combination defects | ✅ PASS |
| 4 | Scope creep | ✅ PASS |
| 5 | Stale contract | ✅ PASS |
| 6 | 15-provider no-fallback / evidence | ✅ PASS |
| 7 | README / oracle JSON consistency | ✅ PASS |
| 8 | pyright / test / whitespace | ✅ PASS |

---

## 1. Correctness Against Oracle Predicates

### 1.1 `init.workspace-resolution`

| 证据 | 判定 |
|---|---|
| `arg_parsing.py:415-432` `_register_init_command` 使用 `common_parent`（不含 `--config`），其它命令使用 `runtime_parent`（含 `--config`） | ✅ |
| `arg_parsing.py:234-236` `parse_cli_args` 显式拒绝 init 的 `--config`：`parser.error("init 命令不接受 --config")` → exit 2 | ✅ |
| `arg_parsing.py:14` `DEFAULT_WORKSPACE = "./workspace"` | ✅ |
| `README.md:83-84` "init 不接受 --config；无论把它写在命令前还是命令后，都会作为用法错误退出 2" | ✅ |

### 1.2 `init.model-defaults-and-overrides`

| 证据 | 判定 |
|---|---|
| `arg_parsing.py:715` `--model, -m` 注册，`dest="model"`；无 `--model-name` 兼容入口 | ✅ |
| `session_execution.py:92` `_MODEL_OPTION = "--model"`；`session_execution.py:521-525` 读取 `args.model` | ✅ |
| `conversation_compaction.json:11` `"default_model_id": "mimo-v2.5-pro-plan"` 与 `execution_profiles.json` 全部 profile 的 `compactor_baseline.model_id` 一致 | ✅ |
| `host_assembly.py:619-628` compactor_selection 使用 `compactor_baseline` + compactor scene hints，不消费 `run_override` | ✅ |
| `host_assembly.py:685-712` `_require_matching_model_families` 校验 primary_default 与 compactor 的 provider/provider_model/endpoint/credential_ref 四字段 | ✅ |
| `host_assembly.py:637-640` 校验在 secret header 解析和 Host 打开前完成 | ✅ |
| README: "单次 CLI --model/-m 只覆盖本次主 Run，不改变 workspace 默认配置，也不隐式覆盖辅助 compactor Run" | ✅ |
| `ParsedCliArgs.model: str | None` 无 `model_name` 字段 | ✅ |

### 1.3 `init.secret-handling`

| 证据 | 判定 |
|---|---|
| `init.py:681-706` `_read_secret_input` 使用 `getpass.getpass` 隐藏输入 | ✅ |
| `init_workspace.py` 全模块不含 secret 处理；`init.py` 只在 `_collect_environment_persistence_plan` 收集 | ✅ |
| 用户裁决：Host SQLite 持久化 resolved credential 明文允许；init-owned workspace 配置仍只保存 ref | ✅ |
| `init_catalog.py:763-783` `_build_custom_openai_record` 只写 `api_key_ref`，不写 value | ✅ |

### 1.4 `init.interactive-validation-and-exit`

| 证据 | 判定 |
|---|---|
| `init.py:558-594` `_read_model_choice` 循环直到 owner validator 接受 | ✅ |
| `init.py:597-616` `_read_dynamic_model_name` 循环 | ✅ |
| `init.py:619-638` `_read_dynamic_endpoint` 循环 | ✅ |
| `init.py:641-678` `_read_context_window` 循环 | ✅ |
| `init.py:947-970` `_confirm`：EOF → `CliInitOperationError` → exit 1；Enter → `""` → `_NEGATIVE_ANSWERS` → False → exit 0 | ✅ |
| `init.py:238-239` `KeyboardInterrupt` → `EXIT_KEYBOARD_INTERRUPT` (130) | ✅ |
| `init.py:235-236` `CliInitUsageError` → `EXIT_USAGE_ERROR` (2) | ✅ |

### 1.5 `init.preserve`

| 证据 | 判定 |
|---|---|
| `init_workspace.py:858-879` PRESERVE 路径：`shutil.copytree` 用户 config → staging → `_copy_missing_root_config_files` + `_copy_missing_prompt_files` | ✅ |
| `init_workspace.py:922-957` `_copy_missing_root_config_files` 跳过已存在/已 symlink 的目标 | ✅ |
| `init_workspace.py:960-993` `_copy_missing_prompt_files` 跳过已存在/已 symlink 的目标 | ✅ |
| `init_workspace.py:482-486` `apply_model_selection` + `project_known_manifest_models` 只改写模型相关字段 | ✅ |

### 1.6 `init.overwrite`

| 证据 | 判定 |
|---|---|
| `init_workspace.py:880-884` OVERWRITE 路径：`_copy_package_config_defaults` 完整重建 | ✅ |
| `init_workspace.py:1099-1111` `_roots_replaced_by_mode`：OVERWRITE 只替换 config root | ✅ |
| `init_workspace.py:646-706` publication 使用 `os.replace` 原子替换 + backup + rollback | ✅ |

### 1.7 `init.reset`

| 证据 | 判定 |
|---|---|
| `init.py:355-376` `_confirm_reset`：显示 targets，默认 No | ✅ |
| `init_workspace.py:1109-1110` RESET 替换 `.dayu` 和 `config` 两个 root | ✅ |
| `init.py:138-139` reset cancelled → exit 0 | ✅ |

### 1.8 `init.provider-matrix`（15-provider no-fallback）

| 证据 | 判定 |
|---|---|
| `init_catalog.py:107-228` `INIT_MODEL_CHOICES` 精确 15 项 | ✅ |
| `init_catalog.py:580-599` `_validate_choice_tuple_shape` 强制 `len == 15` | ✅ |
| `utils/smoke_cli_init_provider_matrix.py` 4413 行，`MATRIX_ROW_COUNT = 15`，每行独立 init + real prompt + Host durable read | ✅ |
| smoke 无 mock/fake provider；credential 缺失时 fail closed | ✅ |

---

## 2. Semantic Owner Boundary

| 语义 | Owner | 边界是否清晰 |
|---|---|---|
| CLI 命令面 / 参数注册 | `dayu/cli/arg_parsing.py` | ✅ init 用 `common_parent`，其它用 `runtime_parent` |
| 模型选择目录 / manifest 投影 | `dayu/cli/init_catalog.py` | ✅ 不碰 workspace transaction |
| Workspace transaction lifecycle | `dayu/cli/init_workspace.py` | ✅ 不碰 secret、不碰 CLI 交互 |
| Init 交互 orchestrator | `dayu/cli/commands/init.py` | ✅ 只编排，不实现 transaction 或 catalog |
| 层中立 assembly helper | `dayu/runtime/assembly.py` | ✅ 不 import Host/Engine/Service/UI/Fins |
| Service Host opener assembly | `dayu/service/host_assembly.py` | ✅ `_require_matching_model_families` 在此处 |
| CLI session 执行 | `dayu/cli/session_execution.py` | ✅ `args.model` → `ServiceAssemblyOverrides.model_id` |
| Execution profiles | `dayu/config/execution_profiles.json` | ✅ 全部 profile compactor_baseline 使用 mimo-v2.5-pro-plan |
| Compactor scene manifest | `dayu/config/prompts/manifests/conversation_compaction.json` | ✅ `default_model_id: mimo-v2.5-pro-plan` |

**无跨层泄漏**：`runtime/assembly.py` 不 import 业务层；`init_catalog.py` 不碰 workspace mutation；`init_workspace.py` 不碰 CLI 交互。

---

## 3. Cross-Slice Combination Defects

### 3.1 `--model/-m` 跨 CLI → Service → Runtime 完整链路

```
arg_parsing.py:715  --model, -m → dest="model"
    ↓
session_execution.py:521-525  args.model → ServiceAssemblyOverrides.model_id
    ↓
host_assembly.py:612-618  _model_runner_override_from_overrides → ModelRunnerHintOverride
    ↓
assembly.py:321-395  select_runner_option_hint: run_override > scene > baseline > base
```

**结论**：`--model/-m` 覆盖 ordinary selection，不覆盖 compactor（compactor 的 `run_override=None`）。✅

### 3.2 Compactor family 一致性跨 init → config → runtime

```
init_catalog.py:564-569  project_known_manifest_models: compaction → ordinary_model_id
    ↓
conversation_compaction.json:11  default_model_id: mimo-v2.5-pro-plan
    ↓
execution_profiles.json  compactor_baseline.model_id: mimo-v2.5-pro-plan
    ↓
host_assembly.py:619-628  compactor_selection = select_runner_option_hint(compactor_baseline + scene_hints)
    ↓
host_assembly.py:685-712  _require_matching_model_families(primary_default, compactor)
```

**结论**：compactor 与 ordinary 使用相同 provider/model family，runtime 校验在 Host 打开前执行。✅

### 3.3 PRESERVE 补齐 + 模型投影组合

```
init_workspace.py:858-879  PRESERVE: copytree → _copy_missing_root_config_files → _copy_missing_prompt_files
    ↓
init_workspace.py:482-486  apply_model_selection → project_known_manifest_models
```

**结论**：PRESERVE 先复制用户 config，再补齐缺失文件，最后只投影模型选择。已有文件不被覆盖。✅

### 3.4 session resume 继承 `--model/-m`

`session_execution.py:282-335` `prepare_interactive_session_execution` 使用相同的 `_prepare_session_runtime` helper，读取 `args.model`。✅

---

## 4. Scope Creep

| Scope boundary（Goal Confirmation） | 实际变更 | 判定 |
|---|---|---|
| 允许：`dayu/cli/arg_parsing.py` | ✅ 修改 | ✅ |
| 允许：`dayu/cli/commands/init.py` | ✅ 修改 | ✅ |
| 允许：`dayu/cli/init_catalog.py` | ✅ 修改 | ✅ |
| 允许：`dayu/cli/init_workspace.py` | ✅ 修改 | ✅ |
| 允许：`dayu/runtime/assembly.py` + `dayu/service/host_assembly.py` 调用边界 | ✅ `_require_matching_model_families` + `primary_default_selection` | ✅ |
| 允许：`dayu/config/` 消除 init-generated incompatibility | ✅ `execution_profiles.json` + `conversation_compaction.json` | ✅ |
| 允许：`tests/cli/**`、`tests/runtime/**`、`tests/service/**` | ✅ 修改 | ✅ |
| 允许：`utils/` 下窄 smoke | ✅ `smoke_cli_init_provider_matrix.py` | ✅ |
| 允许：README、oracle、Gateflow artifacts | ✅ 修改 | ✅ |
| 禁止：Host lifecycle / Engine loop / Fins storage / memory schema | ✅ 未触碰 | ✅ |
| 禁止：`--model-name` 兼容 alias | ✅ 不存在 | ✅ |
| 禁止：mock/fake provider | ✅ smoke 使用真实 provider | ✅ |

**额外变更说明**：
- `dayu/cli/session_execution.py`：只改 `_MODEL_NAME_OPTION` → `_MODEL_OPTION` 和 `args.model_name` → `args.model`，是 `--model-name` → `--model` 重命名的必要传播。
- `dayu/service/README.md`：新增模型装配三路选择和 family 校验说明，是 `_require_matching_model_families` 的 README 触发规则要求。
- `docs/cli_init_workspace_manifest_v1.json`：新增 workspace manifest，供 smoke 使用。
- `docs/reviews/` 下 20+ 个 review/plan/implementation artifact：Gateflow 流程产物。

**无 scope creep**。

---

## 5. Stale Contract

| 检查项 | 判定 |
|---|---|
| Goal Confirmation 中 "compactor selection 显式传 `scene_model_hints=None`" 已过时 | ⚠️ 见 Finding F-01 |
| Goal Confirmation 中 "Custom 默认 context window 为 131072" 已过时 | ⚠️ 见 Finding F-02 |
| 其它 Goal Confirmation 陈述与当前代码一致 | ✅ |
| Oracle predicates 与当前代码一致 | ✅ |
| README 与当前代码一致 | ✅ |

---

## 6. README / Oracle JSON Consistency

逐 predicate 比对 `cli_ci_oracles.json` 与 `README.md`：

| Predicate | Oracle | README | 一致 |
|---|---|---|---|
| `init.workspace-resolution` | init 不接受 --config；默认 ./workspace | ✅ README:83-84 | ✅ |
| `init.first-publication` | 空 workspace 从包内默认创建 | ✅ README:88 | ✅ |
| `init.model-defaults-and-overrides` | compactor 同 family；--model/-m 不覆盖 compactor | ✅ README:200-204 | ✅ |
| `init.secret-handling` | workspace 只保存 ref；Host SQLite 允许明文 | ✅ README:100-101 | ✅ |
| `init.interactive-validation-and-exit` | EOF=1, SIGINT=130, parser=2 | ✅ README:96-100 | ✅ |
| `init.preserve` | 保留用户文件，补齐缺失，只投影模型 | ✅ README:89-91 | ✅ |
| `init.overwrite` | 从包内默认完整重建 | ✅ README:92 | ✅ |
| `init.reset` | 默认 No，确认后重建 .dayu + config | ✅ README:93-94 | ✅ |

`dayu/config/README.md` 与 `dayu/service/README.md` 的更新也与代码一致。

---

## 7. pyright / Test / Whitespace

| 检查 | 结果 |
|---|---|
| pyright（7 个核心生产模块） | 0 errors, 0 warnings, 0 informations |
| 测试（669 tests） | 412 + 148 + 109 = 669 passed |
| `git diff --check` | clean |

---

## Findings

### F-01（Informational）：Goal Confirmation 中 compactor scene_model_hints 描述过时

**位置**：`docs/reviews/wu-cli-init-01-goal-confirmation-controller.md:122`

**描述**：Goal Confirmation 直接代码证据写道 "compactor selection 显式传 `scene_model_hints=None`"。当前代码 `host_assembly.py:619-628` 的 compactor_selection 使用 `compactor_scene_inputs.model_hints`（非 None），因为 compactor scene manifest 现在与 ordinary 使用相同的 `mimo-v2.5-pro-plan` model，scene hints 自然指向同一 model。

**严重性**：Informational。不影响产品代码或 oracle 判定；Goal Confirmation 的直接代码证据是修复前基线描述，不构成运行时 contract。

**建议**：无需修改。Goal Confirmation 记录的是 `933908a8` 基线的直接证据，属于历史快照。

### F-02（Informational）：Goal Confirmation 中 Custom context window 描述过时

**位置**：`docs/reviews/wu-cli-init-01-goal-confirmation-controller.md:44-45`

**描述**：Goal Confirmation 写道 "Custom 默认 context window 为 131072，而默认 `standard-256k` profile 要求 262144"。当前代码 `init.py:540-546` Custom 的默认 context window 取 `min_context_window_tokens`（来自 target profile），因此 Custom 默认值现在是 262144，消除了 init-generated internal incompatibility。

**严重性**：Informational。Goal Confirmation 描述的是修复前问题，当前代码已修复。

**建议**：无需修改。

### F-03（Informational）：`_confirm` 空输入行为与 Oracle 措辞的细微差异

**位置**：`dayu/cli/commands/init.py:957-970`

**描述**：Oracle 写道 "reset 确认时直接 Enter 选择默认 No，workspace 不变并退出 0"。代码中 `_confirm` 返回 False（No），调用方 `_confirm_reset` 返回 False → `run_init_command` 打印 "reset cancelled" 并返回 `EXIT_SUCCESS`（0）。这在行为上完全正确。但 `_confirm` 是通用 helper，被 `_confirm_reset` 和 `_collect_environment_persistence_plan` 复用。后者的 "确认持久化?" 空输入也返回 False → 抛出 `CliInitOperationError` → exit 1。这符合 oracle 的 "需要持久化必需 secret 时，最终确认输入 No、直接按 Enter 或 EOF 都表示初始化未完成并退出 1"。

**严重性**：Informational。行为正确，只是 `_confirm` 的空输入语义在两个上下文中产生不同退出码（reset=0, persistence=1），这是正确的业务语义区分。

**建议**：无需修改。

---

## Residual Risks

### R-01（Low）：Smoke test 外部依赖可用性

`utils/smoke_cli_init_provider_matrix.py` 执行真实 provider 请求。当外部 provider 不可用时，matrix row 会按 `preclassification` 记录为 expected failure（credential missing / provider refused / endpoint unreachable），不伪装 pass。CI 环境需要至少一个 provider credential 才能产生有意义的 evidence。

**缓解**：smoke 设计已支持 credential 缺失时的 fail-closed 分类。

### R-02（Low）：`--model/-m` 跨 family override 的用户预期

README 明确说明 "即使本次主 Run 显式选择不同的 provider family，会话压缩仍使用 init 选择的 family"。这是正确的 contract，但用户可能误以为 `--model/-m` 会全局生效。README 已充分说明。

**缓解**：README 和 oracle 均已明确记录此行为。

### R-03（Informational）：workspace manifest v1 与 managed file count 的版本耦合

`docs/cli_init_workspace_manifest_v1.json` 记录了 5 directories / 43 files 的版本化 manifest。未来新增或删除 config 文件时需要同步更新此 manifest 和 smoke 的 `EXPECTED_FILE_COUNT`。

**缓解**：`init_catalog.py:663-680` `_validate_package_manifest_names` 在 init 运行时校验 manifest 集合一致性。

---

## 最终判定

# **PASS**

全部 8 个审查维度通过。无可复现的 correctness、semantic owner、cross-slice combination、scope creep、stale contract 或 consistency findings。3 个 Informational findings 均为历史文档描述与当前代码的非功能性差异，不影响产品行为、oracle 判定或 contract 一致性。

### 验证总结

| 验证项 | 结果 |
|---|---|
| pyright（核心模块） | 0 errors |
| 测试（669 tests） | 669 passed |
| `git diff --check` | clean |
| Oracle predicates 逐项比对 | 全部一致 |
| README / oracle JSON 一致性 | 全部一致 |
| 语义 owner 边界 | 无泄漏 |
| Scope boundary | 无 creep |
| 15-provider no-fallback | 已验证 |
| `--model/-m` 跨层链路 | 完整正确 |
| Compactor family 同源 | 已验证 |
| EOF=1 / SIGINT=130 / parser=2 | 已验证 |
| Host SQLite credential 明文 | 按用户裁决 accepted |
