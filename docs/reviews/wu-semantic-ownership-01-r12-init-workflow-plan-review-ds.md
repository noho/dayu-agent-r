# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan — AgentDS Independent Complete Plan Review

## 0. Review Identity

- **Reviewer**: AgentDS (second independent path, adversarial complete plan review)
- **Date**: 2026-07-18
- **Immutable target**: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`
  - 483 lines / 41,413 bytes / SHA-256 `6470ec0aafc8214e4fb3f0df88539e4ec97525b992e359bc4abbc75f06b2f5d0`
- **Controller validation**: `PASS_WITH_MANDATORY_CHALLENGES` — five specific challenges must be independently adjudicated
- **Entry controller artifact**: `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-entry-controller-validation.md`
  - 118 lines / SHA-256 `678a1e424c325d8c170dee3d0375e2387149c3c3ff4c4e0440416dafa3a7a489`
- **Scope**: Full 483-line adversarial review; semantic owner, catalog/static-dynamic boundary, secret persistence, FIRST/PRESERVE/OVERWRITE/RESET, new workspace creation, lock/TOCTOU/containment/symlink, multi-root rollback/cleanup, prewarm resource close & zero network, Windows setx and R11 real nodes, test/coverage/pyright/Ruff baseline, README/scans, Issues 142/151/175/177/178, Topic 8/9 no-scope, and all five controller challenges
- **Posture**: Adversarial — search for strongest evidence-based reasons this plan should not yet be handed to an implementation agent

---

## 1. Evidence Baseline Verified

| Item | Expected | Actual | Match |
|---|---|---|---|
| Plan SHA-256 | `6470ec0aafc8214e4fb3f0df88539e4ec97525b992e359bc4abbc75f06b2f5d0` | same | ✓ |
| Plan lines | 483 | 483 | ✓ |
| Plan bytes | 41,413 | 41,413 | ✓ |
| Git commit | `5d4deef8` | same (HEAD) | ✓ |
| Current init.py SHA | `c33db731...` | same | ✓ |
| Current arg_parsing.py SHA | `d8442bc6...` | same | ✓ |
| Current filelock.py SHA | `269f30e4...` | same | ✓ |
| Current models.json SHA | `d817a171...` | same | ✓ |
| Current init tests | 82 passed | 82 passed | ✓ |
| Ruff baseline | 144 errors | 144 errors | ✓ |
| `custom-openai` in models.json | absent | absent | ✓ |
| `ollama` in models.json | present | present | ✓ |
| `qwen-plus` in models.json | present | present (2 entries: base + thinking via extends) | ✓ |
| R11 Windows workflow | `r11-upload-script-windows.yml` | exists | ✓ |
| R11 Windows test nodes | 2 real `.cmd` tests | `test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd` + `test_windows_generated_script_runs_real_cli_into_temp_storage` | ✓ |
| `prepare_entrypoint_runtime` seam | `dayu/service/entrypoint_runtime.py` | exists | ✓ |
| `prepare_host_admin` seam | `dayu/service/host_admin.py` | exists | ✓ |
| `build_fins_processor_registry` seam | `dayu/fins/processors/registry.py` | exists | ✓ |
| `prepare_scene` seam | `dayu/runtime/scene_prepare.py` | exists | ✓ |
| Umbrella plan §19 | `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §19 | R12 plan at lines 971-1078 | ✓ |
| Controller discussion Topic 7 | `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` §7.3 | init workflow decisions recorded | ✓ |

All 16 package known manifest hashes are accepted as anchored by the controller validation.

---

## 2. Controller Challenge Adjudication

### Challenge 1 — Ruff Baseline Feasibility

**Controller statement**: Plan requires full `python -m ruff check dayu/ tests/ utils/` zero, but immutable baseline has exactly 144 errors across unrelated historical paths.

**Direct evidence**:
- Plan §8 S1/S2/S3 验证节全部写 `python -m ruff check dayu/ tests/ utils/`（全量零错误）
- Plan §9.2 明确 "Ruff 全量零错误；不得用 ignore、配置排除、type: ignore、noqa 或缩小命令掩盖 R12 问题"
- Plan §10.2 停止条件包括 "full Ruff 暴露必须越界处理的问题"
- 当前基线：`Found 144 errors`（其中 69 fixable, 8 hidden fixable），分布在 `dayu/cli/commands/`、`dayu/fins/`、`dayu/host/`、`dayu/engine/`、`tests/` 等非 R12 路径

**裁决**: **这是个真实阻断性问题。** 计划要求全量 Ruff 零错误，但基线 144 个错误分布在 R12 无权修改的模块中（Host、Engine、Fins、已有 CLI 命令）。Plan 的"不得缩小命令"规则与"不得越界处理"停止条件形成矛盾：两个要求无法同时满足。

**严重程度**: **高** — 实现 Agent 无法通过此 gate，会触发 §10.2 停止条件。

**建议修改**: 将 Ruff 验证拆为两层：
1. **R12 changed paths 零错误**：`python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py dayu/cli/init_workspace.py dayu/cli/commands/init.py dayu/cli/arg_parsing.py tests/cli/test_init_*.py` — 这条必须为零。
2. **全量 Ruff 不扩散**：`python -m ruff check dayu/ tests/ utils/` 的错误数相对于基线 144 不得增加；新增错误必须归零。
3. 若 changed-path Ruff 零但全量因无关路径报错，不算 R12 失败。

---

### Challenge 2 — Nonexistent Workspace Root

**Controller statement**: Current init creates fresh workspace root; plan §6.3 requires existing ordinary directory without explicitly assigning creation.

**Direct evidence**:
- 当前代码 `_ensure_workspace_root()` 调用 `workspace_root.mkdir(parents=True, exist_ok=True)`（line 129）
- Plan §6.3："workspace 必须解析为既有普通目录" — 没有对应的创建步骤
- Plan §6.2 编排顺序以 lock 获取开头，lock path 是 `<workspace>/.dayu-init.lock` — 若 workspace 不存在，lock file parent 也不存在
- Plan 的 `filelock` 配置 `create_parent_dirs=True`，但 `file_lock` 只创建 lock file 的 parent directory，不会创建整个 workspace 根

**裁决**: **真实 gap。** 首次用户在新路径执行 `dayu-cli init --base ./new_workspace` 时，`./new_workspace` 不存在，lock path `./new_workspace/.dayu-init.lock` 的 parent 也不存在。`RuntimeFileLock` 的 `_prepare_parent_directory` 会创建 lock parent，但 plan §6.3 随后要求 workspace "必须解析为既有普通目录"，而它刚刚才被 lock helper 隐式创建。这里有两个问题：(a) workspace 创建 owner 不明确（是 lock helper 隐式副作用还是显式步骤）；(b) workspace 被 lock helper 创建时没有 containment/symlink 校验。

**严重程度**: **高** — 首次安装路径不可 code-generate。

**建议修改**:
1. 在 lock 获取前增加显式 workspace root resolution/creation 步骤：若不存在则 `mkdir`（仅创建目录，不做 containment 检查因为此时还没有 workspace 内容）；若已存在且不是目录则 fail。
2. 将 workspace root 的 symlink 检查加入该步骤。
3. 明确：workspace root 创建不是 managed root mutation，不受 lock 保护范围约束。

---

### Challenge 3 — Prewarm Resource Lifecycle

**Controller statement**: Listed Service/Fins public preparation seams may allocate local resources; review must verify construction/close/no-network/no-business-data.

**Direct evidence**:
- Plan §7 列出三个 public seam：`prepare_entrypoint_runtime(EntrypointRuntimeRequest)`、`prepare_host_admin(ServiceHostAdminRequest)`、`build_fins_processor_registry()`
- `prepare_entrypoint_runtime` 是 `async def`，内部可能创建 scene/tool discovery 对象
- `prepare_host_admin` 是同步函数，接收 `ServiceHostAdminRequest`，可能分配 Host opener 相关资源
- `build_fins_processor_registry` 创建 `ProcessorRegistry`，可能初始化 Fins processor 实例
- Plan 没有指定这些对象的 close/cleanup 生命周期
- Plan §7 只说 "prewarm 失败只输出 warning"，但没有说成功 prewarm 后如何释放资源

**裁决**: **真实 gap，但严重性低于前两个 challenge。** Prewarm 在一个一次性 CLI 进程中运行，进程退出时 OS 回收资源。但在 prewarm 后到进程退出之间，可能有打开的文件句柄、已初始化的 processor 对象等残留。对本 CLI 场景不是 production 风险，但测试若在同一个进程中反复调用 prewarm（如 smoke test），资源泄漏可能导致 flaky tests。

**严重程度**: **中** — 不影响 production 正确性，但 smoke test 稳定性可能受影响。

**建议修改**:
1. Plan 明确 prewarm helper 的作用域：每次 prewarm 调用后，显式释放/清理可关闭资源（close any opened files, clear caches）。
2. 测试中 prewarm spy/mock 要验证：prewarm 完成后没有遗留未关闭的文件描述符或网络连接。
3. 或明确声明 "prewarm 资源在进程退出时由 OS 回收，不要求显式 close"，并记录为可接受 residual。

---

### Challenge 4 — Post-Publish Cleanup Failure Classification

**Controller statement**: Must verify whether backup cleanup/fsync failure is a rollback-triggering publication failure or a recoverable diagnostic.

**Direct evidence**:
- Plan §6.4 step 6：rollback 故障处理描述清晰——保留 backup、打印路径、返回失败
- Plan §6.4 step 7："每个父目录在 publish/restore 后 fsync；成功后才 no-follow 删除 transaction backups"
- 但没有说父目录 fsync 失败或 backup 删除失败时，已发布的 config 是否仍然有效、init 返回成功还是失败

**裁决**: **半步 gap。** Publish 后的 backup 删除是 cleanup 而非 publish correctness。若 swap 已成功（`os.replace` 完成 + 父目录 fsync 成功），backup 删除的 fsync 失败只意味着 backup 可能未完全刷盘——这不影响已发布的 config 的正确性。Plan 应明确：swap 成功的判定点是 `os.replace` + 父目录 fsync 成功；之后 backup cleanup 失败是 warning/diagnostic，不影响 init 返回成功。

**严重程度**: **中** — 当前文本可能让实现 Agent 把 harmless cleanup 失败当作 publication 失败处理。

**建议修改**:
1. 明确 publish success boundary：`os.replace(staging, config/)` 成功 + 父目录 `fsync` 成功 = 发布成功。
2. 之后的 backup cleanup（no-follow delete + 父目录 fsync）失败只产生 warning，不改变 init exit code，不声称发布失败。
3. Plan §6.4 step 7 的 "成功后才 no-follow 删除" 改为 "swap 成功后才 no-follow 删除 transaction backups；cleanup 失败不改变发布结果"。

---

### Challenge 5 — Static/Dynamic Catalog Split

**Controller statement**: `custom-openai` absent from package defaults by design. Static validation must not require it before it's built.

**Direct evidence**:
- `custom-openai` 在 `dayu/config/models.json` 中不存在（grep 验证零命中）
- Plan §4.1："静态目录加载后必须对 package ModelsConfig fail closed：两个 ID 都存在，record 的 provider 与 api_key_ref 符合该选择"
- 这意味着 catalog 中的 `custom-openai` / `runtime custom-openai` 两个 ID 都需要在 package models.json 中存在——但它们不存在
- Plan §4.1 后文承认："Ollama/custom 的显示项存在于同一目录，但其 record 由显式交互输入产生"——但 fail-closed 规则文本没有显式排除 Ollama/Custom

**裁决**: **真实 gap。** Fail-closed 验证的文本覆盖了所有 15 项目录项，但 Ollama（其 ordinary model ID 存在于 package）和 Custom（其 ordinary model ID 不存在）需要不同的验证路径。Plan 意图正确但规则文本有歧义，实现 Agent 可能按字面意思对 Custom 执行 fail-closed 检查而失败。

**严重程度**: **中** — 意图正确但文本不精确，可能在实现时触发假阳性 stop condition。

**建议修改**:
1. 将 §4.1 的 fail-closed 规则改为："对 13 个静态 provider 条目，两个 model ID 都必须存在于 package `ModelsConfig` 中。Ollama 的 `ollama` ID 必须在 package models 中存在。Custom 的 `custom-openai` ID 在 package models 中不存在是预期行为——其 record 在交互输入后动态生成；静态验证不得要求它预先存在。"
2. S1 测试必须分别覆盖：13 静态条目缺 ID 即 fail，Custom 缺 ID 不 fail。

---

## 3. Additional Findings

### F-06 — PRESERVE Missing-Prompt Scope Ambiguity

- **位置**: Plan §6.2 PRESERVE 定义
- **问题类型**: 契约缺失
- **当前写法**: "prompt assets" 仅指 package `config/prompts/` 下相对路径缺失的文件/目录
- **反例/失败场景**: Package `config/prompts/` 下包含子目录（如 `manifests/`、`fragments/`），且用户可能删除了整个子目录。Plan 说 "缺失的文件/目录" 暗示也复制缺失的目录本身（空目录）。但当前 package prompt tree 中没有有意义的空目录——所有目录都包含文件。若未来 package 增加空目录标记（如占位目录），init 的行为未定义。
- **为什么有问题**: "文件/目录" 的措辞过于宽泛。Umbrella plan §19.2-19.3 使用 "packaged prompt assets" 和 "missing packaged prompt assets"，语义上指文件。当前 package `config/prompts/` 下没有空目录，所以此歧义当前无害，但措辞不精确。
- **直接证据**: Plan §6.2: "prompt assets 仅指 package config/prompts/ 下相对路径缺失的文件/目录"
- **影响**: 实施 Agent 可能实现目录级复制（`copytree` with `dirs_exist_ok`），与文件级 copy 语义不同
- **建议改法和验证点**: 改为 "缺失的文件（不包含空目录）"；或明确 "当前 package 不包含有意义的空目录，按文件粒度复制缺失项"
- **修复风险**: 低
- **严重程度**: 低

---

### F-07 — RESET `.dayu/` Deletion Edge Case: Active SQLite WAL/SHM

- **位置**: Plan §6.2 RESET 定义, §6.4 step 5
- **问题类型**: 状态机漏洞
- **当前写法**: RESET 删除整个 `.dayu/` tree via no-follow rmtree
- **反例/失败场景**: 前一个 Host 运行崩溃后，`.dayu/` 内可能残留 SQLite WAL (`-wal`) 和 SHM (`-shm`) 文件。这些文件是普通文件，no-follow rmtree 可以删除它们，不会导致错误。但如果另一个 Host 进程仍在运行（违反了 lock 保护前提），删除会引发 Host 错误。由于 lock 保护了并发 init+Host，这个场景只可能在 lock 被外部绕过时发生。
- **为什么有问题**: 不是 R12 的 bug——lock 已经防止了并发。但 residual risk 应该更明确地记录：lock 保护 init↔init 和 init↔Host 互斥的前提是 Host 也遵守同一 lock 或 init 在 Host 停止后运行。
- **直接证据**: Plan §6.3: lock 覆盖范围包括交互、staging、swap；lock path 在 managed roots 外
- **影响**: 低 — 当前 lock 设计已覆盖此场景
- **建议改法和验证点**: 在 §10.1 残余风险中增加一条："若 Host 或其他进程绕过 `.dayu-init.lock` 直接写入 managed roots，RESET 删除可能与活跃写入竞争。正确前提是 init 在 Host 停止后运行。"
- **修复风险**: 低
- **严重程度**: 低

---

### F-08 — Custom-OpenAI `runtime_hints` Hardcoded Values Lack Derivation

- **位置**: Plan §4.2 Dynamic model record — Custom 段
- **问题类型**: 契约缺失
- **当前写法**: Custom 的 `runtime_hints.runner_option_hints` 硬编码 8 个 hint 值，如 `write (0.6,1.0,true)`、`overview (0.1,1.0,true)` 等
- **反例/失败场景**: 若用户使用的 custom-openai provider 对某些 scene 需要不同的 temperature/top_p（例如 `write` scene 在 Mimo 用 0.8 而 Custom 硬编码为 0.6），用户无法在 init 阶段调整。当前 plan 没有提供覆盖机制。
- **为什么有问题**: 与 Ollama 不同——Ollama 的 runtime_hints 来自 package `ollama` record 模板。Custom 的 runtime_hints 是凭空硬编码的，没有 package 模板可继承。Plan 应说明这些值的来源：是 OLD init 的历史值，还是产品决策，还是任意安全默认值。
- **直接证据**:
  - Plan §4.2: Custom record `runtime_hints.runner_option_hints` 的具体 tuple 值
  - Package `models.json`: 无 `custom-openai` record 可继承
  - Ollama record hints: write `(0.6,1.0,true)` — Custom 恰好匹配 Ollama 的 write 值
- **影响**: 中 — Custom provider 用户可能得到不理想的默认 hint；但不影响 correctness，因为 execution profiles 会进一步覆盖
- **建议改法和验证点**: 在 plan 中注明 Custom runtime_hints 的来源（如 "使用与 Ollama 相同的保守默认值" 或 "这些值来自 OLD init custom provider 历史"），并提供未来调整的明确 owner（catalog module）
- **修复风险**: 低
- **严重程度**: 低

---

### F-09 — POSIX Profile Shell Detection Underspecified

- **位置**: Plan §5.2 POSIX owner 行为
- **问题类型**: 契约缺失
- **当前写法**: "根据已检测 shell 在 ~/.zshrc 或 ~/.bashrc 中选择一个 profile"
- **反例/失败场景**:
  1. 用户的 `SHELL` 环境变量指向 `/bin/fish` 或 `/bin/sh`（非 bash/zsh）——plan 说 "shell 不受支持时 fail closed"，正确
  2. 用户同时有 `~/.bashrc` 和 `~/.zshrc`，但 `SHELL=/bin/bash`——只写 `~/.bashrc`，正确
  3. 用户使用 macOS，`SHELL=/bin/zsh` 但 macOS 的 zsh 实际读取 `~/.zshrc`（非 `~/.zprofile`），正确
  4. 但 plan 没有说明：若 `SHELL` 检测为 bash/zsh 但对应 rc 文件不存在，是创建新文件还是 fail？
- **为什么有问题**: 边界条件未覆盖。新用户可能没有 `~/.bashrc`——创建是合理的（首次安装场景）。
- **直接证据**: Plan §5.2: "profile 若是 symlink（包括 dangling symlink）拒绝；保留既有文件 mode，首次创建用 0600" — "首次创建用 0600" 暗示会创建，但没有显式说明不存在时创建
- **影响**: 低 — "首次创建用 0600" 暗示了创建意图；实现 Agent 大概率做对
- **建议改法和验证点**: 显式说明："profile 不存在时创建新文件，mode 0600"；对应测试覆盖
- **修复风险**: 低
- **严重程度**: 低

---

### F-10 — PRESERVE `.dayu/` Handling Ambiguity

- **位置**: Plan §6.2 PRESERVE 状态, §6.4 step 5
- **问题类型**: 契约缺失
- **当前写法**: PRESERVE 状态下 "`.dayu/` 原样不动"
- **反例/失败场景**: PRESERVE 状态下 config/ 被 swap 更新（补 missing prompts + model projection），但 `.dayu/` 保持不变。如果用户之前用旧版 init 创建了 `.dayu/` 内有过时结构，新版 Host 是否能正确读取？Plan 正确地将此责任归于 Host（Host 在首次启动时初始化 `.dayu/` 内部结构），但 plan 未显式声明这一前提。
- **为什么有问题**: 缺少语义 owner 声明：`.dayu/` 的内部结构 owner 是 Host，不是 init。Init 只负责整个 `.dayu/` 作为 managed root 的 reset 删除，不负责其内部初始化。
- **直接证据**: Plan §6.1: "`.dayu` 内部目录不能单独列出"；§6.4 step 5: "FIRST 不凭空创建 `.dayu/`"
- **影响**: 低 — 语义边界已在 managed-root manifest 中隐含，只是没有显式写出来
- **建议改法和验证点**: 在 §3 或 §6.1 增加一行："`.dayu/` 内部结构与初始化归 Host 所有；init 只拥有 managed-root 级别的 create/delete/replace"
- **修复风险**: 低
- **严重程度**: 低

---

## 4. Open Questions

### OQ-01: Prewarm 是否应该在 staging validate 阶段而非 publish 后执行？

Plan 当前设计：prewarm 在 publish 成功后执行，失败只 warning。替代方案：将 prewarm 的一部分（ConfigLoader + scene assembly validation）移动到 pre-publish validate（§6.4 step 3 已有 ConfigLoader 读取 staging），prewarm 只保留 processor registry 与 host admin assembly（更接近真实 runtime 预热）。这可以更早发现配置问题（publish 前而非 publish 后），但 processor registry 构建可能依赖 `.dayu/` 内部路径，而 FIRST init 时 `.dayu/` 不存在。当前设计（post-publish warning-only）是安全的，但 plan 没有解释为什么不把 prewarm validation 前置。

**建议**: 不需要修改 plan。在 implementation 时若发现 processor registry 可以在 staging config 基础上构建（不需要 `.dayu/`），可考虑前置。当前 post-publish 设计是安全的。

### OQ-02: Custom OpenAI endpoint 是否需要 `/chat/completions` 后缀的自动补全？

Plan §4.2: "endpoint 必须按用户输入原样校验和写入，不猜 `/chat/completions` 后缀"。这与 OLD init 行为一致（OLD 也要求完整 URL）。正确决定。不修改。

---

## 5. Architecture Boundary Review

逐层审查 plan 的 owner 分配与架构约束：

| 语义 | Plan owner | 正确性 | 证据 |
|---|---|---|---|
| 交互顺序、状态机、prewarm | `commands/init.py` | ✓ | 不泄露给 argparse/catalog |
| 静态 catalog + dynamic record | `init_catalog.py` | ✓ | 单一 typed source |
| OS secret persistence + redaction | `init_environment.py` | ✓ | workspace 不接触值 |
| Managed-root manifest + transaction | `init_workspace.py` | ✓ | 唯一 manifest 常量 |
| File lock | `dayu/runtime/filelock.py` | ✓ | 复用，不增加第二种 lock |
| Config 校验 | `dayu/runtime/config_loader.py` | ✓ | 当前 schema 唯一 owner |
| Package defaults | `dayu/config/**` | ✓ | init 只读不写 |
| argparse 参数 | `dayu/cli/arg_parsing.py` | ✓ | 只解析 flags，不反推业务语义 |

**结论**: 无架构边界违规。三模块拆分（catalog / environment / workspace）对应三类不可互换的 owner，orchestrator 只编排不形成 God function。无反向依赖。无 `dayu.runtime` 对上层模块的 import。

---

## 6. Best-Practice Review

对照项目指令（AGENTS.md、CLAUDE.md）检查：

| 约束 | 计划合规性 | 说明 |
|---|---|---|
| 语义所有权 | ✓ | 每类语义有唯一 owner，见 §3 |
| 禁止兼容代码 | ✓ | §1.3 明确禁止 fallback/shim/旧名 re-export |
| 严格类型 | ✓ | §3 末尾明确要求 |
| LLM-facing 文本约束 | ✓ | init 不产生 LLM-facing 内容；无相关违规 |
| 分层架构 | ✓ | CLI → Service（prewarm），不绕过 Service |
| 测试覆盖率 ≥80% | ✓ | §9.1 单文件覆盖率要求 |
| 禁止 God object | ✓ | 三模块拆分，orchestrator 只编排 |
| 不保留旧测试兼容 | ✓ | §8 S2 明确 "迁移到新 owner contract，不为旧偶然行为保兼容" |

**结论**: 无最佳实践违规。

---

## 7. Optimal-Solution Review

对照 umbrella plan §19 的"三 slice"结构和 OLD init 的已知工作流：

- **Plan 的三 slice 切分是合理的**: S1（contract only）→ S2（filesystem mutation）→ S3（integration smoke + docs）按风险递增。S1 不与文件系统交互，最容易 review；S2 引入 lock/transaction，风险最高；S3 是验证层。
- **三模块拆分 vs 单文件**: Plan 的三个新模块 (`init_catalog.py`, `init_environment.py`, `init_workspace.py`) 对应三类不可互换的 owner。若合并为单文件，会形成 God module。拆分是正确的。
- **动态 model record 方案**: 对 Ollama/Custom 使用当前-schema record 模板是合理的最小方案。不需要引入通用 "model builder framework" 或 plugin registry。

**结论**: 方案是最优实践路径，无 credible simpler alternative。

---

## 8. Overengineering Review

| 可能的过度设计 | Plan 实际做法 | 判定 |
|---|---|---|
| 通用配置迁移框架 | §1.3 明确排除 Issue 142 | 正确拒绝 |
| 通用 transaction engine | `init_workspace.py` 只实现 init 需要的 swap/rollback | 正确范围 |
| Provider plugin registry | 静态 tuple，不引入 plugin 机制 | 正确范围 |
| 统一 tool authorization | §1.3 明确排除 Topic 9 | 正确拒绝 |
| 新 runtime abstraction | 全部复用现有 `filelock`/`ConfigLoader`/Service seams | 正确复用 |

**结论**: 无过度设计。

---

## 9. Overcoupling Review

| 潜在耦合 | Plan 实际做法 | 判定 |
|---|---|---|
| argparse 与业务语义 | §3: "argparse 只解析显式 flags；不得在测试/README 重建状态机" | 正确解耦 |
| workspace transaction 与 secret persistence | §5.1: secret 在 workspace mutation 前完成；§6.4 step 4 明确顺序 | 正确解耦 |
| catalog 与 manifest 内容 | §4.1: catalog 引用 model ID，不解析 manifest 内容 | 正确解耦 |
| 多个消费者各自写路径白名单 | §6.1: 唯一 `ManagedRootManifest` 常量，禁止另写路径 tuple | 正确集中 |

**结论**: 无过度耦合。

---

## 10. Residual Risks

Plan §10.1 已披露的残余风险均准确。补充以下：

| 新增 Residual | 说明 | Owner | 跟踪 |
|---|---|---|---|
| Prewarm 资源泄漏 | prewarm 调用 public seams 后未显式 close；进程退出时 OS 回收 | R12 CLI | 见 F-03 (Challenge 3) |
| Host 绕过 lock 并发 | 若 Host 在 init lock 外运行，RESET 可能与活跃 Host 冲突 | R12 CLI / Host | 见 F-07 |
| Custom runtime_hints 无模板继承 | 硬编码值缺乏来源说明，未来可能需调整 | R12 CLI | 见 F-08 |

---

## 11. Final Review Conclusion

**结论: `PASS_WITH_FINDINGS`**

Plan 在架构边界、语义所有权、状态机设计、secret 安全、no-scope 约束等方面均正确且具体。三个 cumulative slices 合理切分，每个 slice 有明确的允许路径、测试、覆盖率、pyright/Ruff/diff 验证和 review gate。

十项 findings（Controller Challenge 1-5 对应 F-01—F-05，Additional F-06—F-10）中：两项严重程度为 HIGH（F-01 Ruff baseline infeasibility, F-02 workspace creation gap），必须在 plan 中修复后才能交给 implementation agent；三项 MEDIUM（F-03—F-05，即 Controller challenges 3-5）应在 plan fix 中一并处理；五项 LOW（F-06—F-10）建议修复但不阻断 plan acceptance。

Controller 的五个 challenge 均已独立裁决并给出具体修复建议。无新发现的 stop condition。所有 Issue（142/151/175/177/178）和 Topic（8/9）的 no-scope 边界均被正确遵守。

**Plan acceptance 前提**:
1. F-01 和 F-02 必须在 plan 中修复（Ruff scope 明确化为 changed-path 零 + 全量不扩散；workspace creation 显式分配给 init pre-lock 步骤）
2. F-03—F-05（Controller challenges 3-5）应在 plan 中修复
3. F-06—F-10 建议修复但不阻断

---

## 12. Artifact Metadata

- **Review file**: `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-review-ds.md`
- **Reviewer**: AgentDS
- **Timestamp**: 20260718-063634
- **Lines/bytes/SHA of this artifact**: 见 Controller handoff 机械度量
- **Immutable target unchanged**: ✓ (no modification to target, control, entry, production, tests, README)
- **No stage/commit**: ✓
