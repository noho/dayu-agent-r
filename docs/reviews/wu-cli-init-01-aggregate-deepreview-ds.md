# WU-CLI-INIT-01 Aggregate Deep Review

## Review metadata

- **Work unit**: `WU-CLI-INIT-01`
- **Review type**: aggregate deep review（全部 slice 组合后一次性审查）
- **Reviewer**: AgentDS（Claude Code / DeepSeek）
- **日期**: 2026-07-30
- **Scope range**: `3bfbd7f9`（Goal Confirmation 前基线）→ `ae907b26`（S6 acceptance）
- **Slices in scope**: S1, S2, S3, S4, S5-A, S5-B, S6（含 plan amendment 和 scope correction）
- **Contract documents**:
  - `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`（含 2026-07-30 用户补充裁决）
  - `AGENTS.md`（项目全局约束）
  - 各 slice adjudication controller（plan review + S1–S6 code review）
  - 用户裁决：compactor 同 family、--model/-m 单次主 Run、Host SQLite resolved credential 明文允许

## Verdict

**PASS** — 有可复现 findings（见 §Findings），无 blocking issue。

所有 8 项目标均已满足，15 个 provider choice 的 no-fallback evidence 完整，内部 contract 15/15 valid，跨 slice 组合无缺陷。以下 findings 均为低-中 severity，不影响整体 pass 判定。

---

## 1. 审查方法

按以下维度逐项检查全部 80 个变更文件的组合效果：

1. **Correctness**: 对照 goal confirmation §目标 1–8 逐条验证
2. **Semantic owner**: 检查新增语义是否有唯一清晰 owner，是否存在下游补偿或重复 ownership
3. **跨 slice 组合缺陷**: 检查 S1→S2→S3→S4→S5-A→S5-B→S6 的数据流、状态机和边界交互
4. **Scope creep**: 检查是否存在 approved scope boundary 之外的变更
5. **Stale contract**: 检查是否存在与当前实现矛盾的文档、常量或公开 surface
6. **15-provider no-fallback/evidence**: 验证 retained report 与 oracle contract 一致性
7. **README/oracle JSON 一致性**: 检查四份 README + oracle predicates + frozen manifest 的交叉一致性
8. **Transaction/rollback**: 确认未引入新的 transaction/rollback 需求（仅验证既有实现未被破坏）

---

## 2. 目标逐条验证

### 目标 1：裸 init 使用 `./workspace`；init 命令面彻底不存在 `--config`

**✅ 通过。**

- `arg_parsing.py`: `_build_common_arguments_parent()` 不含 `--config`，`_build_runtime_arguments_parent()` 在 common 之上叠加 `--config`
- init subparser 使用 `common_parent` → `init --help` 不展示 `--config`
- `parse_cli_args()` 中 post-parse 检查：`parsed_args.command_name == COMMAND_INIT and parsed_args.config_dir is not None` → `parser.error("init 命令不接受 --config")`
- command 后位置（`init --config PATH`）由 init subparser 自身报 unknown option exit 2
- command 前位置（`--config PATH init`）由 post-parse rejection exit 2
- 测试覆盖：`test_init_rejects_config_before_and_after_command`（两个位置均 exit 2）、`test_init_help_absence_of_config`、非 init 命令的正向 `--config` 回归测试

### 目标 2：正式主 Run 模型覆盖参数为 `--model/-m`，不保留 `--model-name` 兼容入口

**✅ 通过。**

- `ParsedCliArgs.model_name` → `model`
- `_add_agent_execution_arguments` 注册 `--model/-m`（dest=`model`）
- `session_execution.py`: `_MODEL_NAME_OPTION` → `_MODEL_OPTION`，使用 `args.model`
- 测试覆盖：Agent commands（prompt/interactive/session resume）均接受 `--model/-m`；`--model-name` 在所有三个命令上均 exit 2；help 文本不含 `--model-name`

### 目标 3：compactor 与其它 scene 的 resolved provider/model/endpoint/credential ref 同源

**✅ 通过。**

- **Package default 层（S3）**: `conversation_compaction.json` manifest 的 `default_model_id` 从 `deepseek-v4-flash` 改为 `mimo-v2.5-pro-plan`；全部 4 个 execution profile 的 `run_baseline.model_id` 和 `compactor_baseline.model_id` 从 `deepseek-v4-flash` 改为 `mimo-v2.5-pro-plan`
- **Service assembly 层（S3）**: 新增 `primary_default_selection`（run_override=None），传给 `_require_matching_model_families` 与 `compactor_selection` 比较四字段 identity；`compactor_selection` 改为消费 `scene_model_hints`（不再传 `None`）
- **运行时校验**: `_mismatched_model_family_fields` 比较 provider/provider_model/endpoint/credential_ref 四个字段，不一致时抛 `ValueError` 且错误信息只含 model id 与字段名，不泄露 secret
- **单次 `--model/-m` 不改变 compactor**: `ordinary_selection` 消费 `run_override`，`compactor_selection` 固定 `run_override=None`；`_require_matching_model_families` 只比较 primary_default vs compactor，不比较 ordinary vs compactor
- **测试覆盖**: `test_compactor_family_mismatch_fails_before_host_options_without_secret_leak`（family mismatch fail closed）；`test_primary_default_and_compactor_selections_share_family`（正常路径）；`test_single_run_model_override_does_not_affect_compactor`

### 目标 4：未 init 时所有 scene 的默认 provider/model family 一致

**✅ 通过。**

- 所有 16 个 package-known manifest 的 default_model_id 均属于 Mimo Token Plan family
- 4 个 execution profile 的 run_baseline 和 compactor_baseline 均使用 `mimo-v2.5-pro-plan`
- `conversation_compaction.json` manifest 不再使用 `deepseek-v4-flash`
- 未 init 用户只需 `MIMO_PLAN_API_KEY` 一个环境变量即可运行包括 compactor 在内的所有 scene
- 测试覆盖：`test_package_defaults_require_single_provider_family`（S3）；Service assembly 的单 credential 测试（S3）

### 目标 5：可恢复交互错误原地重试；EOF=1、parser misuse=2、SIGINT=130

**✅ 通过。**

- **模型 choice 输入**: `_read_model_choice` 循环调用 `_parse_model_choice`，非法输入通过 `_report_recoverable_input_error` 报告后继续
- **动态 model name**: `_read_dynamic_model_name` 循环读取并由 `validate_dynamic_model_name` 校验
- **动态 endpoint**: `_read_dynamic_endpoint` 循环读取并由 `validate_dynamic_endpoint` 校验
- **context window**: `_read_context_window` 循环读取，校验正整数值且不低于 target minimum
- **secret 输入**: `_read_environment_persistence_entry` 循环读取，校验 `EnvironmentPersistenceEntry` 构造
- **确认输入**: `_confirm` 循环读取，非法 yes/no 重试；EOF → `CliInitOperationError`；No/Enter → False
- **RESET 确认**: `_confirm_reset` 中 EOF → `CliInitOperationError`（exit 1）；No/Enter → exit 0
- **退出码映射**: `run_init_command` 的 except 链：`CliInitUsageError` → 2，`CliInitOperationError` → 1，`KeyboardInterrupt` → 130
- 测试覆盖：可恢复输入的循环重试（S2）；EOF/SIGINT/parser misuse 退出码（S1, S2）

### 目标 6：FIRST/PRESERVE/OVERWRITE/RESET/repair 以真实 managed tree 结果判定

**✅ 通过。**

- **FIRST**: 从 package 发布完整 managed tree → 43 文件（frozen manifest 验证）
- **PRESERVE**: copytree 用户 config + `_copy_missing_root_config_files` 补齐 5 个根配置文件 + `_copy_missing_prompt_files` 补齐 prompt → 已有文件零改写
- **OVERWRITE**: 从 package 重建 `config/`，保留 `.dayu`
- **RESET**: 确认后移除 `config/` 和 `.dayu/`，保留 portfolio/assets，再从 package 重建
- **普通文件占据的修复**: `snapshot_managed_roots` 新增 `repair_mode` 参数；OVERWRITE 可修复 `config` 普通文件占据，RESET 可修复 `config` 和 `.dayu` 普通文件占据；symlink/dangling/special file 所有模式拒绝
- **no-follow 安全**: `_workspace_execution_profile_is_regular_file` 使用 `os.stat(follow_symlinks=False)`；cleanup 使用 `PathIdentity.mode` 真源分派 `unlink`/`rmtree`
- 测试覆盖：FIRST publication tree（S5-A frozen manifest 42 tests）；PRESERVE bytes/prompt/config 补齐（S4）；OVERWRITE 旧 entries 消失（S4）；RESET `.dayu` 重建 + No/EOF/SIGINT（S4）；普通文件占据 repair（S4）

### 目标 7：无 workspace config 与有 workspace config 两条路径均用真实 prompt 验证

**✅ 通过。**

- S5-B 的 retained provider report（`matrix-report.json` SHA-256: `b3eb7a1a...`）包含 15 个 choice 的完整 real-prompt evidence
- 7 available（真实 provider 响应）、3 credential_missing（API key 缺失，安全失败）、1 endpoint_unconfigured、2 provider_rejected、2 rate_limited
- 每条记录包含 precondition classification、effective model/identity、request attempt 标记、terminal outcome、脱敏诊断
- 测试覆盖：frozen manifest 的 42 项 deterministic 验证 + 68 项 smoke harness 测试

### 目标 8：15 个模型选择完整真实 evidence matrix

**✅ 通过。**

- `utils/smoke_cli_init_provider_matrix.py`（4115 行）：完整 15-row provider matrix harness
- 每条 row 记录：precondition、effective identity（仅来自 assembly）、expected identity（独立从 package/init-owned ConfigLoader 派生）、no-fallback verdict（fail-closed）、secret scan（两通道互斥）、persisted scan（Host SQLite accepted observation vs 其它 violation）
- Retained report：15/15 internal contract valid，15/15 no-fallback valid，overall exit 0，0 persistence violations
- Reconciliation 从 canonical evidence 独立重算 no-fallback，不读旧 report verdict
- Host SQLite credential：10 rows 中 20 exact-byte matches 正确归类为 `accepted_observation`
- 测试覆盖：68 项 focused pytest，81% utils 文件覆盖率

---

## 3. Semantic Ownership 检查

### 3.1 新增 public contract

| 语义 | Owner | 位置 | 判定 |
|------|-------|------|------|
| `ModelFamilyIdentity`（四字段 provider identity） | `dayu.runtime.assembly` | 层中立 dataclass | ✅ 正确 owner；被 Service 和 CLI catalog 消费但不反向依赖 |
| `model_family_identity()` | `dayu.runtime.assembly` | 同模块 helper | ✅ 正确 owner；单一真源 |
| `_require_matching_model_families()` | `dayu.service.host_assembly` | Service 层 private | ✅ 正确 owner；Service 是 primary/compactor 汇合点 |
| `validate_dynamic_model_name()` | `dayu.cli.init_catalog` | Catalog owner | ✅ 正确 owner；catalog 拥有动态模型名 schema |
| `validate_dynamic_endpoint()` | `dayu.cli.init_catalog` | Catalog owner | ✅ 正确 owner；catalog 拥有 endpoint schema |
| `_load_target_min_context_window()` | `dayu.cli.commands.init` | CLI adapter | ✅ 正确 owner；是 ConfigLoader 的上游调用者 |
| `_copy_missing_root_config_files()` | `dayu.cli.init_workspace` | Workspace mutation owner | ✅ 正确 owner；复用 `config_file_names()` 真源 |

### 3.2 潜在 ownership 问题

无实质性 semantic ownership drift。以下为已识别但 non-blocking 的备注：

- **`_EXECUTION_PROFILES_FILE_NAME` 常量重复**（见 Finding F3）：CLI adapter 中的 `"execution_profiles.json"` 字面量与 `ConfigLoader.config_file_names()` 中的文件名重复。原因是 S2 将此 deferred 到 S4，S4 scope correction 后窄化为 managed-tree modes，未包含 ConfigLoader 重构。当前该常量仅用于 PRESERVE workspace profile 的 no-follow shape 分类——这是一个上游 shape guard，不是语义 owner 冲突。风险低。

### 3.3 下游消费者检查

- `session_execution.py` 消费 `args.model`（原 `args.model_name`）→ 单一真源（Parser）
- `host_assembly.py` 消费 `ModelFamilyIdentity` 和 `model_family_identity()` → 单一真源（`dayu.runtime.assembly`）
- `init_catalog.py` 消费 `model_family_identity()` → 单一真源（`dayu.runtime.assembly`），用于 `_validate_resolved_choice`
- 无下游 fallback、重算或兼容分支

---

## 4. 跨 Slice 组合检查

### 4.1 S1 → S2：Parser contract → Model selection state machine

- S1 删除 `ParsedCliArgs.model_name`，S2 的 `session_execution.py` 使用 `args.model`
- S1 建立 `common_parent`/`runtime_parent` 双 parent 架构，S2 的 init command 使用 `common_parent`（不含 `--config`）
- **无组合缺陷** ✅

### 4.2 S2 → S3：Model selection → Package defaults + Compactor assembly

- S2 的 `_select_model()` 产生 `InitModelSelection` → `apply_model_selection()` 投影到 workspace manifests
- S3 的 Service assembly 消费 workspace scene model hints（来自 S2 的 manifest 投影）
- S3 的 `_require_matching_model_families` 使用 `primary_default_selection`（run_override=None）与 `compactor_selection` 比较
- **关键验证**: 当用户 init 选择非 Mimo 家族（如 DeepSeek）时，S2 的 manifest 投影将所有 scene default_model_id 改为 DeepSeek model → S3 的 Service assembly 从 scene hints 读取 DeepSeek model → compactor 同样使用 DeepSeek → family match 通过
- **无组合缺陷** ✅

### 4.3 S2/S3 → S4：Managed tree modes

- S2 的 `_load_target_min_context_window` 接收 `locked_mode` 参数 → PRESERVE 模式下使用 workspace config dir → 加载 workspace profile minimum
- S4 的 `_build_staged_config` 中 PRESERVE 路径：先 copytree 再 `_copy_missing_root_config_files` → 补齐缺失的 5 个根配置文件 → 然后 `_copy_missing_prompt_files`
- S4 的 `snapshot_managed_roots` 新增 `repair_mode` 参数在所有 3 个调用点正确传递（unlocked snapshot、locked snapshot、`_require_snapshot_unchanged` 内）
- **无组合缺陷** ✅

### 4.4 S4 → S5-A：Managed tree → Deterministic publication tests

- S5-A 的 frozen manifest（`docs/cli_init_workspace_manifest_v1.json`）描述 FIRST init 的精确 publication tree
- 5 个目录、43 个文件（42 个 package-owned + 1 个 `.dayu-init.lock`）、16 个 model_projection_owner_paths
- 42 项 deterministic tests 全部通过
- **无组合缺陷** ✅

### 4.5 S5-A → S5-B：Deterministic contract → Live provider smoke

- S5-A 拒绝 live 执行（`main()` 抛 `NotImplementedError`），S5-B 实现完整 live matrix
- Retained report 的 no-fallback verdict 从 canonical evidence 独立派生，不读旧 report 字段
- Reconciliation 重算 availability class，不使用旧 oracle 的错误派生值
- **无组合缺陷** ✅

### 4.6 S5-B → S6：Provider evidence → README/CI integration

- S6 的 README 更新正确反映所有 8 项目标
- Retained report SHA-256 验证匹配（`b3eb7a1a...`）
- 740 focused tests passed，pyright 0 errors
- **无组合缺陷** ✅

### 4.7 全局数据流验证

```
CLI Parser (S1)
  → Init Model Selection (S2)
    → Manifest Projection (S2)
      → Package Defaults (S3)
      → Service Assembly (S3)
        → Managed Tree Publication (S4)
          → Deterministic Verification (S5-A)
            → Live Provider Smoke (S5-B)
              → README/CI Integration (S6)
```

每个阶段的输出是下一阶段的输入，无循环依赖或隐式状态传递。

---

## 5. Findings

### F1（中）: `docs/cli_ci.md` 820 行方法论变更 scope boundary 模糊

- **证据**: `git diff 3bfbd7f9..ae907b26 -- docs/cli_ci.md` 显示 820 行新增/修改，涵盖完整的 CLI CI 方法论重构（goal-discovery evidence acquisition 流程、preflight 增强、inventory 要求、calibration 循环）
- **为何是 finding**: Goal confirmation §Scope boundary 允许"触发规则要求的 README、accepted oracle/provider availability 修订和 Gateflow artifacts"，但 `docs/cli_ci.md` 的变更规模（从 ~23 行扩到 ~843 行）超出"修订"范畴，实质上是一次独立方法论重写
- **实际影响**: 低。这些变更支持 init oracle calibration 工作，与 WU 目标一致。但作为独立的方法论文档，它未在 plan gate 中作为独立 slice 接受 adversarial review
- **建议**: 在后续 work unit 中对 `docs/cli_ci.md` 做独立 goal confirmation；当前不作为 blocking
- **可复现**: `git diff 3bfbd7f9..ae907b26 -- docs/cli_ci.md | wc -l` → 820+ 行

### F2（低）: `docs/host/ui-implementation-control.md` 仍引用已删除的 `--model-name`

- **证据**: 第 412、429、466 行将 `--model-name` 列为 accepted plan 中的合法参数
- **owner**: `docs/host/ui-implementation-control.md` 是 Host 层文档，不在 WU-CLI-INIT-01 的 approved scope 内
- **为何是 finding**: 虽然不在 scope 内，但这是 aggregate deep review 的跨文档一致性职责。该文档现在与 CLI parser 的 public contract 不一致
- **实际影响**: 低。Host 文档读者可能误认为 `--model-name` 仍有效；但 archive 目录下的旧文档引用是预期的历史记录
- **风险归属**: tracked by existing Host doc maintenance，不要求在本 WU 修复
- **可复现**: `grep -n "\-\-model-name" docs/host/ui-implementation-control.md` → 3 处命中

### F3（低）: PRESERVE workspace profile 文件名在 CLI adapter 中与 ConfigLoader 重复

- **证据**: `dayu/cli/commands/init.py:71` 定义 `_EXECUTION_PROFILES_FILE_NAME: Final[str] = "execution_profiles.json"`，而 `dayu/runtime/config_loader.py:943` 的 `config_file_names()` 也返回该文件名
- **历史**: S2 adjudication 将此 deferred 到 S4；S4 scope correction 窄化为 managed-tree modes 后未覆盖 ConfigLoader 重构
- **实际影响**: 极低。CLI adapter 的常量仅用于 `_workspace_execution_profile_is_regular_file` 的 no-follow shape 分类（上游 guard）。`config_file_names()` 仍是被 `_copy_missing_root_config_files` 使用的 canonical owner。两份定义指向同一字面量，漂移概率低
- **非 finding 的理由**: 这不是 semantic ownership violation——CLI adapter 使用特定文件名做特定 shape check，不是重新声明 filename ownership。若视作 finding，修复成本（统一到 ConfigLoader 常量）与收益不成比例
- **可复现**: `grep -rn "execution_profiles.json" dayu/cli/commands/init.py dayu/runtime/config_loader.py`

### F4（低）: `docs/cli_ci_oracles.json` 的 `authority_basis` 引用旧仓库路径

- **证据**: `"source": "/Users/leo/workspace/dayu-agent/README.md#13-..."` —— 仓库名为 `dayu-agent`，当前仓库为 `dayu-agent-r`
- **分析**: 该条目 `kind` 为 `reference-observation`，引用的是旧实现中的观察行为作为语义参考。从旧仓库路径引用旧实现是语义正确的——它描述的是"我们从哪里观察到的参考行为"
- **实际影响**: 无。不影响 oracle 语义。若未来有人通过路径查找旧实现，可能找不到（如果旧仓库已移动）
- **可复现**: `grep "dayu-agent" docs/cli_ci_oracles.json`

---

## 6. Scope Creep 检查

### 6.1 Approved scope vs actual changes

| 文件/目录 | Approved | Actual | 判定 |
|-----------|----------|--------|------|
| `dayu/cli/arg_parsing.py` | ✅ | 72 行变更 | ✅ |
| `dayu/cli/commands/init.py` | ✅ | 375 行变更 | ✅ |
| `dayu/cli/init_catalog.py` | ✅ | 147 行变更 | ✅ |
| `dayu/cli/init_workspace.py` | ✅ | 145 行变更 | ✅ |
| `dayu/cli/session_execution.py` | 未明确列出 | 6 行（`model_name`→`model`） | ✅ 必要跟随 S1 parser 变更 |
| `dayu/runtime/assembly.py` | ✅ | 34 行（`ModelFamilyIdentity` + helper） | ✅ |
| `dayu/service/host_assembly.py` | ✅ | 74 行变更 | ✅ |
| `dayu/config/execution_profiles.json` | ✅ | 16 行（provider family 统一） | ✅ |
| `dayu/config/prompts/manifests/conversation_compaction.json` | ✅ | 2 行（default_model_id） | ✅ |
| `tests/cli/**` | ✅ | 多个文件 | ✅ |
| `tests/runtime/**` | ✅ | 2 个文件 | ✅ |
| `tests/service/**` | ✅ | 1 个文件（341 行） | ✅ |
| `utils/smoke_cli_init_provider_matrix.py` | ✅ | 4413 行（新文件） | ✅ |
| `README.md` | ✅（触发规则） | 37 行 | ✅ |
| `dayu/config/README.md` | ✅（触发规则） | 35 行 | ✅ |
| `dayu/service/README.md` | ✅（触发规则） | 17 行（新文件） | ✅ |
| `tests/README.md` | ✅（触发规则） | 77 行 | ✅ |
| `docs/cli_ci.md` | 边界模糊 | 820 行 | ⚠️ 见 F1 |
| `docs/cli_ci_oracles.json` | ✅（oracle 修订） | 229 行 | ✅ |
| `docs/cli_init_workspace_manifest_v1.json` | ✅（oracle 修订） | 75 行（新文件） | ✅ |
| `docs/reviews/*` | ✅（Gateflow artifacts） | 多个文件 | ✅ |

### 6.2 非 scope creep 但需说明的变更

- **`dayu/cli/session_execution.py`**: 6 行变更仅将 `_MODEL_NAME_OPTION` 改为 `_MODEL_OPTION` 和 `args.model_name` 改为 `args.model`。这是 S1 parser 变更的必要消费者更新，不是独立 scope expansion
- **`docs/cli_ci.md`**: 见 Finding F1
- **`dayu/service/README.md`**: 17 行新文件。触发规则为 `dayu/service/` 修改 → 检查 `dayu/service/README.md`。该 README 之前可能不存在，新建以记录 Service assembly 的模型选择语义。在触发规则范围内 ✅

---

## 7. Stale Contract 检查

### 7.1 生产代码

| 搜索项 | 结果 | 判定 |
|--------|------|------|
| `--model-name` 在 `dayu/**/*.py` 中作为 argparse 参数 | 0 命中 | ✅ 已清理 |
| `ParsedCliArgs.model_name` | 0 命中 | ✅ 已清理 |
| `_MODEL_NAME_OPTION` 常量 | 0 命中 | ✅ 已清理 |
| `init --config` 作为合法参数 | 0 命中 | ✅ 已清理 |
| `--config` 在 init help 中 | 0 命中 | ✅ 已清理 |
| `DEEPSEEK_API_KEY` 作为 README 默认环境变量示例 | 0 命中（已改为 `MIMO_PLAN_API_KEY`） | ✅ 已更新 |
| `deepseek-v4-flash` 作为 package default（非可选 choice） | 0 命中（execution profiles 和 compactor manifest 均已改为 Mimo） | ✅ 已更新 |
| `131072` 作为 default context window | 0 命中 | ✅ 已移除 |
| "PRESERVE 只补 prompt" 旧描述 | 0 命中（README 已更新为"补齐缺失的五个根配置文件与包内 prompt 文件"） | ✅ 已更新 |

### 7.2 文档

| 文档 | `--model-name` 引用 | 判定 |
|------|---------------------|------|
| `docs/host/ui-implementation-control.md` | 3 处（作为 accepted plan 中的合法参数） | ⚠️ 见 F2 |
| `docs/host/archive/*` | 多处（历史记录） | ✅ 预期历史记录 |
| `docs/reviews/*` | 多处（review artifacts 中描述"已删除"） | ✅ review 记录 |

### 7.3 测试

- `--model-name` 仅在 `test_arg_parsing.py` 的负向测试中出现（断言 exit 2 / help absence）→ ✅ 正确
- `init --config` 仅在 `test_arg_parsing.py` 的负向测试中出现 → ✅ 正确

---

## 8. 15-Provider No-Fallback Evidence 验证

### 8.1 Retained report 摘要

- **Report**: `workspace/tmp/wu-cli-init-01/20260730T112936Z-a86f5ccdeab5/matrix-report.json`
- **SHA-256**: `b3eb7a1a83f384a7274c9ad253d221d5dfd5dbd61e763830859397d59c6786c0`
- **Rows**: 15
- **Availability breakdown**: 7 available, 3 credential_missing, 1 endpoint_unconfigured, 2 provider_rejected, 2 rate_limited
- **Internal contract**: 15/15 valid
- **No-fallback**: 15/15 valid
- **Persistence violations**: 0
- **Overall exit**: 0

### 8.2 关键验证点

| 验证项 | 状态 | 证据 |
|--------|------|------|
| No-fallback verdict 独立派生 | ✅ | `_expected_provider_identity` 从 ConfigLoader + static catalog 独立派生，不读 assembly/trace |
| Effective identity 仅来自 assembly | ✅ | `_run_matrix_row` 中 effective = `ProviderIdentity(provider=ordinary.provider, provider_model=ordinary.provider_model)` |
| 缺 identity → fail closed | ✅ | `evaluate_no_fallback` 中 expected=None → `expected_identity_missing` + `expected_identity_not_observed` → passed=False |
| Reconciliation 不用旧 verdict | ✅ | `_reconciled_no_fallback_verdict` 从 canonical evidence 完整重算 |
| Secret scan 两通道互斥 | ✅ | Host SQLite → `accepted_observation`；其它位置 → `violation`；canary 无豁免 |
| Ollama expected identity 动态 truth | ✅ | `_expected_provider_identity` 的 `workspace_config_root` 参数正确传递给 `ConfigLoader` |

### 8.3 未覆盖场景（已分类）

- `service_unreachable`（2 rows）和 `provider_rejected`（2 rows）：外部依赖不可用，not a product bug
- `credential_missing`（3 rows）：用户未提供 API key，安全失败
- `endpoint_unconfigured`（1 row）：Custom endpoint 未配置，预期行为

---

## 9. README/Oracle JSON 一致性验证

### 9.1 Oracle predicates ↔ README

| Oracle predicate | README 对应描述 | 一致？ |
|------------------|-----------------|--------|
| `init.workspace-resolution` | §2 README：`./workspace` 默认，`init` 不接受 `--config` | ✅ |
| `init.first-publication` | §2 README：FIRST 状态描述 | ✅ |
| `init.model-defaults-and-overrides` | §2 README：包内默认 Mimo Token Plan 家族；§3 README：`--model/-m` 只覆盖主 Run | ✅ |
| `init.secret-handling` | §2 README：secret 输入不回显，TTY 隐藏输入 | ✅ |
| `init.interactive-validation-and-exit` | §2 README：输入不合法重新输入；RESET 确认 exit code | ✅ |
| `init.preserve` | §2 README：PRESERVE 补齐五个根配置文件 | ✅ |
| `init.overwrite` | §2 README：OVERWRITE 完整重建 `config/` | ✅ |
| `init.reset` | §2 README：RESET 默认 No，确认后移除 `.dayu/` 和 `config/` | ✅ |
| `init.repair-and-path-safety` | §2 README：普通文件占据拒绝/修复规则 | ✅ |
| `init.real-provider-validation` | §5 README：`DAYU_CLI_INIT_PROVIDER_CHECK` 相关 | ✅ |

### 9.2 Frozen manifest ↔ Actual publication

- `docs/cli_init_workspace_manifest_v1.json`: 5 directories, 43 files, 16 model_projection_owner_paths
- S5-A 的 42 项 deterministic tests 全部独立验证通过
- `.dayu-init.lock` 是 production FIRST flow 的持久化产物（空文件），content_sha256 为空文件 SHA-256

### 9.3 四份 README 交叉一致性

| 声明 | README.md | dayu/config/README.md | dayu/service/README.md | tests/README.md |
|------|-----------|----------------------|----------------------|-----------------|
| `init` 不接受 `--config` | ✅ §2 | — | — | ✅ |
| `--model/-m` 替代 `--model-name` | ✅ §3 | — | — | ✅ |
| 包内默认 Mimo Token Plan family | ✅ §2 | ✅ | ✅ | — |
| Compactor 同 family | ✅ §2, §3 | ✅ | ✅ | ✅ |
| PRESERVE 补齐五个根配置文件 | ✅ §2 | ✅ | — | ✅ |
| 单次 `--model/-m` 不改变 compactor | ✅ §3 | — | ✅ | ✅ |
| 跨 family ordinary override 合法 | ✅ §3 | — | ✅ | ✅ |
| 普通文件占据 repair | ✅ §2 | ✅ | — | ✅ |

**无交叉不一致** ✅

---

## 10. Transaction/Rollback 验证

Goal confirmation 明确说明"FIRST/PRESERVE/OVERWRITE/RESET transaction 已有较强 whole-tree 与 rollback 基础"。本 WU 未新增 transaction/rollback 机制。

### 10.1 既有机制保持完整

- `backup_records` 保持 3-tuple 不变
- `_rollback_or_raise(...)` 零净 diff
- `publish_workspace_transaction(...)` 的 staging → validate → atomic replace → rollback 流程未修改
- `_require_snapshot_unchanged(...)` 新增 `repair_mode` 参数传递但内部逻辑不变

### 10.2 新增的 managed root 处理

- `snapshot_managed_roots` 新增 ordinary-file managed root 的 digest 计算和 repair_mode 校验
- `_cleanup_private_path` 新增 ordinary-file 的 `os.unlink` 路径
- 这些是既有 cleanup owner 的扩展，不是新 transaction 机制

**无 regression** ✅

---

## 11. 测试与验证

### 11.1 最终测试状态

- Focused suite: 740 passed, 5 skipped, 3 warnings
- pyright: 0 errors, 0 warnings, 0 informations
- Ruff: All checks passed
- `git diff --check`: 通过

### 11.2 覆盖率

S6 implementation artifact 声明所有列入计划的 owner 文件达到 ≥80% 覆盖率。`utils/smoke_cli_init_provider_matrix.py` 覆盖率为 81%（utils 文件无强制覆盖率要求但已达线）。

### 11.3 测试 owner boundary

- 测试断言真实 tree、bytes、identity 和 ConfigLoader/Service 加载结果
- 不依赖 CLI 自报 mode
- 不把偶然行为固化进测试

---

## 12. 残余风险

### R1: Provider availability 为环境快照（已分类）

- 7 available / 3 credential_missing / 1 endpoint_unconfigured / 2 provider_rejected / 2 rate_limited
- 这是 S5-B 执行时的真实环境事实，未在 S6 重试
- Classification: `assigned to environment/provider owner`
- 当前 15/15 internal/no-fallback valid 证明内部正确性不依赖 provider availability

### R2: Windows junction/reparse 真实平台 smoke 未执行（已跟踪）

- 本地 Darwin 无法验证 Windows 特定行为
- Classification: `tracked by existing issue #184`

### R3: Host SQLite resolved credential 明文（已接受）

- 10 rows 中 20 exact-byte matches 正确归类为 `accepted_observation`
- 用户已明确接受此行为
- Non-Host-SQLite 位置的 credential 和所有 canary 仍由 harness fail closed

### R4: `_runtime_assembly_env()` 双 credential 模式（已降级）

- S6 DS review 的 residual risk 4：缺少"仅 DEEPSEEK key 无 MIMO key 时 assembly fail fast"的负向测试
- 风险降级：docstring 明确边界约束；frozen manifest SHA-256 提供一定检测能力
- 如需加固：补充 `test_compactor_assembly_fails_without_mimo_credential`

### R5: `docs/cli_ci.md` 方法论变更未经独立 review（见 F1）

- 820 行变更未在 plan gate 中作为独立 slice 接受 adversarial review
- 实际影响低：内容与 WU 目标一致，且 cli_ci.md 本身是操作手册而非 normative contract

### R6: `docs/host/ui-implementation-control.md` stale `--model-name`（见 F2）

- 不在本 WU scope 内，tracked by Host doc maintenance

---

## 13. 审查覆盖项确认

- ✅ Correctness（8 项目标逐条验证）
- ✅ Semantic owner（新增 contract 均有唯一清晰 owner）
- ✅ 跨 slice 组合缺陷（S1→S2→S3→S4→S5-A→S5-B→S6 全链路验证）
- ✅ Scope creep（80 个变更文件对照 approved scope）
- ✅ Stale contract（生产代码、文档、测试的旧参数/旧默认值扫描）
- ✅ 15-provider no-fallback/evidence（retained report 完整验证）
- ✅ README/oracle JSON 一致性（四份 README + oracle predicates + frozen manifest）
- ✅ Transaction/rollback（验证既有机制未被破坏，未引入新需求）
- ✅ 未将既有 transaction/rollback 当成新需求
- ✅ 未提出 filesystem race/TOCTOU 作为 finding（S2 已识别且 classified as "covered by later approved slice"）
- ✅ 只审查，未修改代码

---

## 14. Completion

- **Verdict**: **PASS**
- **Findings**: 4 项（F1 中、F2 低、F3 低、F4 低），均不 blocking
- **Residual risks**: 6 项，均已分类和归属
- **无未分类 material finding**
- **无 blocking open question**
