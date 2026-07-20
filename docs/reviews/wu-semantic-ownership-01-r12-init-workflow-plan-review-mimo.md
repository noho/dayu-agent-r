# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan — AgentMiMo complete plan review

## 1. Review identity 与 scope

- **Review target**：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`
- **Immutable metrics**：483 lines / 41,413 bytes / SHA-256 `6470ec0aafc8214e4fb3f0df88539e4ec97525b992e359bc4abbc75f06b2f5d0`
- **Review scope**：完整独立审阅全部 483 行，覆盖 §0–§12 所有章节
- **Authority order**：Controller discussion > `docs/ui/design.md` > umbrella remediation plan §19 > 当前代码 > OLD evidence
- **Review posture**：adversarial — 默认假设 plan 至少有一个重要问题，直到证据证明它足够可靠

## 2. Evidence baseline

### 2.1 当前代码 facts

| 证据 | 来源 | 关键事实 |
|---|---|---|
| 当前 init.py | `dayu/cli/commands/init.py` 470 行 | 非交互 copier；`_ensure_workspace_root` 用 `mkdir(parents=True, exist_ok=True)` 创建 workspace root |
| 当前 arg_parsing.py | `dayu/cli/arg_parsing.py` | `--reset`/`--overwrite` 两个 flag |
| models.json | `dayu/config/models.json` 27 models | `ollama` 存在（template 有效）；`custom-openai` **不存在** |
| ConfigLoader | `dayu/runtime/config_loader.py` 2754 行 | 5 个 config 文件；`ModelsConfig` 做 overlay + extends 解析 + 强类型校验 |
| filelock | `dayu/runtime/filelock.py` 335 行 | 层中立同步 file lock；默认 timeout `-1.0`（infinite wait） |
| Ruff baseline | `python -m ruff check dayu/ tests/ utils/` | **144 errors**：66 E402 + 65 F401 + 9 F841 + 3 F541 + 1 F821；`dayu/cli/` 1 error，`tests/cli/` 2 errors |
| prepare_entrypoint_runtime | `entrypoint_runtime.py:494` | **async**；返回 frozen dataclass；无 close/cleanup |
| prepare_host_admin | `host_admin.py:73` | sync；返回 frozen dataclass；无 close/cleanup |
| build_fins_processor_registry | `registry.py:40` | sync；返回 mutable `ProcessorRegistry`（纯内存 class metadata）；无 close/cleanup |
| prepare_scene | `scene_prepare.py:523` | sync；返回 frozen dataclass；无 close/cleanup |

### 2.2 Plan assumptions tested

| Assumption | 验证结果 |
|---|---|
| 15 项静态目录在 package `ModelsConfig` 中 fail closed | **部分成立**：14 项有 package record；`custom-openai` 不存在于 package |
| Prewarm public seams 不分配需 close 的资源 | **成立**：四个 prepare 函数全返回 frozen dataclass / 纯内存对象 |
| Ruff 全量零错误可验证 | **不成立**：immutable base 有 144 pre-existing errors |
| Workspace root 存在性假设 | **部分成立**：FIRST init 需要先创建 workspace，plan 未指定 |
| Staging 在同父目录创建 | **与当前代码矛盾**：当前用 `tempfile.mkdtemp`（系统 temp） |

## 3. Findings

### FINDING-001-未修复-中-Ruff 全量验证命令在 immutable base 不可行

- **位置**: §8 S1/S2/S3 验证、§9.2 Final validation profile
- **问题类型**: 不可直接实施
- **当前写法**: 每个 slice 验证都要求 `python -m ruff check dayu/ tests/ utils/`；§9.2 要求"pyright 与 Ruff 全量零错误"
- **反例/失败场景**: Implementation agent 在 immutable base 运行该命令，立即得到 144 errors，exit code 非零。agent 无法判断这是 R12 引入的还是 pre-existing 的，且 plan 禁止"擅自扩大 R12 修复范围"，形成死锁。
- **为什么有问题**: Controller 在 validation artifact 中已确认 "ran that exact command at the immutable base and reproduced exactly 144 errors"。Plan 的验证命令作为 gate 条件写入，但没有提供 baseline 差分方案。
- **直接证据**:
  - Plan §8 S1 验证：`python -m ruff check dayu/ tests/ utils/`
  - Plan §9.2："要求 pyright 与 Ruff 全量零错误；不得用 ignore、配置排除、`type: ignore`、`noqa` 或缩小命令掩盖 R12 问题"
  - Plan §10.2："起始 hashes/工作树 scope 漂移，或 full pyright/Ruff 暴露必须越界处理的问题" → stop condition
  - Controller validation §4："the plan says full `python -m ruff check dayu/ tests/ utils/` must be zero, but Controller ran that exact command at the immutable base and reproduced exactly 144 errors"
  - 实际 Ruff 输出：144 errors（66 E402 + 65 F401 + 9 F841 + 3 F541 + 1 F821）；`dayu/cli/` 1 error，`tests/cli/` 2 errors
- **影响**: Implementation agent 遇到 stop condition，无法继续；或者 agent 自行扩大修复范围清理 144 errors，违反 plan scope
- **建议改法和验证点**:
  - 方案 A（推荐）：将 Ruff 验证命令改为 `python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py dayu/cli/init_workspace.py dayu/cli/commands/init.py dayu/cli/arg_parsing.py tests/cli/test_init_catalog.py tests/cli/test_init_environment.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/cli/test_init_smoke.py`，仅检查 R12 新增/修改文件；同时保留全量命令作为 informational baseline，在 implementation artifact 中记录 pre-existing 144 errors 并交 Controller 裁决
  - 方案 B：在 S3 最终验证前，由 implementation agent 修复 `dayu/cli/` 和 `tests/cli/` 中仅有的 3 个 pre-existing Ruff errors（均为 fixable F401 unused import），然后全量命令通过（剩余 141 errors 在 R12 scope 外的 `dayu/engine/`、`dayu/host/` 等目录）
  - 两个方案都需在 §10.2 stop conditions 中明确：pre-existing Ruff errors 不构成 R12 stop condition
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### FINDING-002-未修复-中-FIRST init 新 workspace root 创建时序未指定

- **位置**: §6.3 Lock/containment/symlink、§8 S2 实现第 3 点
- **问题类型**: 契约缺失
- **当前写法**: §6.3 要求"workspace 必须解析为既有普通目录"；§8 S2 编排顺序从"解析 workspace/flags"开始，然后获取锁
- **反例/失败场景**: 用户在全新路径上运行 `dayu-cli init --base /new/workspace`。workspace 目录不存在，但 plan 要求它"解析为既有普通目录"。`file_lock` 尝试在 `<workspace>/.dayu-init.lock` 获取锁，但 `<workspace>/` 目录不存在，`mkdir` 或 `open` 失败。
- **为什么有问题**: 当前 `init.py` 的 `_ensure_workspace_root` 用 `mkdir(parents=True, exist_ok=True)` 创建 workspace root。R12 plan 删除该函数后，没有指定在哪个步骤、以什么语义创建 workspace root。FIRST init 的核心场景就是在新路径上初始化。
- **直接证据**:
  - 当前代码 `init.py:129`：`workspace_root.mkdir(parents=True, exist_ok=True)`
  - Plan §6.3："workspace 必须解析为既有普通目录"
  - Plan §8 S2："解析 workspace/flags → reset snapshot/默认 No 确认（仅 RESET）→ 获取锁并复核"
  - `docs/ui/design.md` §3："Init 把当前 package config 与 prompt assets 安装到 `<workspace_root>/config`"
- **影响**: FIRST init 在新路径上无法获取锁，实现 agent 必须自行决定创建逻辑，可能引入不安全的 pre-lock mutation
- **建议改法和验证点**:
  - 在 §8 S2 编排顺序中，在"解析 workspace/flags"之后、"获取锁"之前，增加显式步骤："若 workspace root 不存在，`mkdir(parents=True, exist_ok=True)` 创建；若已存在则校验为普通目录（非 symlink、非文件）"
  - workspace root 创建在锁外是有意的：锁文件在 workspace 内，创建前无法获取锁；创建后立即获取锁覆盖所有后续 mutation
  - 验证点：测试 FIRST init 在新路径上的完整流程；验证 workspace root 创建失败（权限、ENOSPC）时的错误处理
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### FINDING-003-未修复-低-staging 目录位置与 plan 同父目录要求矛盾

- **位置**: §6.3 "所有 staging/backup 在目标同父目录创建"
- **问题类型**: 与当前代码矛盾
- **当前写法**: §6.3 要求 staging/backup 在"目标同父目录"创建，显式核验 `st_dev` 相同
- **反例/失败场景**: Implementation agent 参考当前代码使用 `tempfile.mkdtemp`（系统 `/tmp`），生成的 staging 与 workspace 不在同一 filesystem，`os.replace` 无法 atomic rename。
- **为什么有问题**: 当前 `init.py:163` 使用 `tempfile.mkdtemp(prefix=_STAGING_DIR_PREFIX, dir=workspace_root)`，实际上 staging 已经在 workspace root 内。但 plan 的措辞"目标同父目录"可能被理解为 config 目标的父目录（即 workspace root），而当前代码的 `dir=workspace_root` 已经满足。这是一个措辞精确性问题。
- **直接证据**:
  - Plan §6.3："所有 staging/backup 在目标同父目录创建，显式核验 `st_dev` 相同"
  - 当前代码 `init.py:163`：`staging_dir = Path(tempfile.mkdtemp(prefix=_STAGING_DIR_PREFIX, dir=workspace_root))`
  - 当前代码 `init.py:335`：`backup_dir = workspace_root / (f"{_BACKUP_DIR_PREFIX}{uuid.uuid4().hex}-{workspace_config_dir.name}")`
- **影响**: 低。当前代码已在 workspace root 内创建 staging，但 plan 应明确指定路径生成方式，避免实现 agent 偏离
- **建议改法和验证点**:
  - 在 §6.4 或 §8 S2 中明确：staging 路径为 `<workspace>/.dayu-init-stage-<uuid>`，backup 路径为 `<workspace>/.dayu-init-backup-<uuid>-<target_name>`，均在 workspace root 内创建
  - 验证点：断言 staging/backup 的 `st_dev` 与 workspace root 相同
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### FINDING-004-未修复-中-静态/动态 catalog 校验对 custom-openai 的边界未收敛

- **位置**: §4.1 "静态目录加载后必须对 package `ModelsConfig` fail closed：两个 ID 都存在"
- **问题类型**: 契约缺失
- **当前写法**: §4.1 要求加载后对 package `ModelsConfig` fail closed："两个 ID 都存在，record 的 `provider` 与 `api_key_ref` 符合该选择；不补默认、不接受别名"。§4.2 说 custom-openai 的 record 由交互输入产生。
- **反例/失败场景**: Implementation agent 在 S1 中实现静态校验，遍历 15 个 catalog entry 检查两个 model ID 是否存在于 `ModelsConfig`。`custom-openai` 不存在于 package models.json，校验立即 fail closed。S1 测试无法通过。
- **为什么有问题**: `custom-openai` 按设计不存在于 package defaults（plan §4.2 明确说"以 package `models.ollama` 的完整当前-schema record 为模板"仅适用于 Ollama；custom 从零构建）。但 §4.1 的 "fail closed" 语句对全部 15 项一视同仁，没有区分静态（14 项有 package record）和动态（custom-openai 无 package record）。
- **直接证据**:
  - Plan §4.1："静态目录加载后必须对 package `ModelsConfig` fail closed：两个 ID 都存在"
  - Plan §4.2："Custom：要求完整 endpoint URL、非空 model 名...生成完整 `openai_compatible` 当前-schema record `custom-openai`"
  - `dayu/config/models.json`：27 models，`custom-openai` **不存在**
  - Plan §1："Ollama 与 custom 只在 staging 配置中产生完整当前-schema model record"
- **影响**: Implementation agent 可能在 S1 静态校验中对 custom-openai 触发 fail closed，阻塞整个 slice
- **建议改法和验证点**:
  - 将 §4.1 的静态校验明确分为两层：
    1. **Package-default 校验**（14 项）：加载后立即对 package `ModelsConfig` fail closed；两个 ID 都存在，provider 与 api_key_ref 符合
    2. **Dynamic record 校验**（custom-openai）：不参与 package-default 校验；在用户输入完成后生成 record，写入 staging `models.json` 后由真实 `ConfigLoader` 重新加载校验
  - 验证点：S1 测试分别断言 14 项 package-default 校验通过、custom-openai 不触发 fail closed
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### FINDING-005-未修复-低-锁 timeout 值未指定

- **位置**: §6.3 "lock timeout/interrupt 通过 `dayu.runtime.filelock` 的 typed 异常与释放语义处理"
- **问题类型**: 契约缺失
- **当前写法**: §6.3 引用 `dayu.runtime.filelock` 的异常语义，但未指定 timeout 值
- **反例/失败场景**: Implementation agent 使用默认 timeout（`-1.0`，infinite wait）。用户在交互选择阶段（选择 provider/model、输入 API key、确认 persistence plan）长时间停留，另一个 init 进程无限等待锁。
- **为什么有问题**: 交互式 init 的锁持有时间可能很长（用户输入 API key、确认等步骤），不同于快速文件操作。Plan 应明确 timeout 策略：是 infinite wait（用户 Ctrl+C 退出）还是 finite timeout（自动释放并报错）。
- **直接证据**:
  - Plan §6.3："lock timeout/interrupt 通过 `dayu.runtime.filelock` 的 typed 异常与释放语义处理"
  - `filelock.py`：默认 timeout `-1.0`（infinite wait per `filelock.FileLock` convention）
  - Plan §6.3："交互期间持锁是有意串行化"
- **影响**: 低。实现 agent 大概率使用默认 infinite wait，这是合理的（用户应 Ctrl+C 退出），但 plan 应显式确认
- **建议改法和验证点**:
  - 在 §6.3 中明确：lock timeout 使用 infinite wait（默认值），用户通过 Ctrl+C 退出时由 `filelock` 的 interrupt 语义释放锁
  - 或者指定一个合理的 finite timeout（如 1800 秒 = 30 分钟），超过后自动释放并报错
  - 验证点：测试 lock wait 期间 SIGINT 释放锁且不 publish
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 4. Controller 五个 mandatory challenges 裁决

### Challenge 1: Ruff baseline feasibility

**裁决**：Finding FINDING-001。Plan 的全量 Ruff 验证命令在 immutable base 不可行。Controller 已确认 144 pre-existing errors。R12 scope 内（`dayu/cli/` + `tests/cli/`）仅 3 个 pre-existing fixable errors。Plan 需要提供 baseline 差分方案或改为 per-file 验证。

### Challenge 2: Nonexistent workspace root

**裁决**：Finding FINDING-002。Plan 未指定 FIRST init 在新路径上创建 workspace root 的时序。当前代码的 `mkdir(parents=True, exist_ok=True)` 在 R12 中被删除后，没有替代逻辑。需要在锁获取前增加显式创建步骤。

### Challenge 3: Prewarm resource lifecycle

**裁决**：**无 finding**。四个 prewarm public seams 全部返回 frozen dataclass 或纯内存对象，无 I/O handle、无 connection、无 close/cleanup/context manager。`prepare_entrypoint_runtime` 是 async 函数，implementation agent 需在 async context 中调用，但这是实现细节，不是 plan 缺陷。Prewarm 不分配需要生命周期管理的资源。

### Challenge 4: Post-publish cleanup failure

**裁决**：**无 finding，但建议 plan 补充显式语句**。Backup 清理发生在 swap 成功之后（§6.4 第 7 点："成功后才 no-follow 删除 transaction backups"）。此时 config 已成功发布，backup 是旧树的可恢复副本。Backup 删除失败不应触发回滚（回滚会丢失已成功发布的新配置）。Plan §6.4 的 rollback 逻辑覆盖 "rename、fsync、validation、interrupt 故障"，不包括 post-publish cleanup。这是正确的隐式语义，但建议在 §6.4 中显式补充："publish 成功后 backup 删除失败仅警告，不触发回滚；保留 backup 供手动恢复。"

### Challenge 5: Static/dynamic catalog split

**裁决**：Finding FINDING-004。`custom-openai` 按设计不存在于 package defaults。Plan §4.1 的 "fail closed" 语句对全部 15 项一视同仁，未区分 package-default 校验和 dynamic record 校验。需要明确分层：14 项做 package-default 校验，custom-openai 做 dynamic record 校验。

## 5. 其它 adversarial 检查项（无 finding）

### 5.1 Semantic owner 一致性

Plan §3 定义的 7 个唯一 semantic owner 与 Controller entry §2 和 `docs/ui/design.md` §3 一致。`init_catalog.py`、`init_environment.py`、`init_workspace.py` 三个新模块各自承载不可互换的 owner 职责。Orchestrator `commands/init.py` 只编排，不形成 God function。

### 5.2 四态状态机

FIRST/PRESERVE/OVERWRITE/RESET 的定义（§6.2）与 `docs/ui/design.md` §3 和 umbrella remediation plan §19.3 一致。状态判定优先级 `RESET > OVERWRITE > (config exists ? PRESERVE : FIRST)` 正确。`--reset --overwrite` 由 reset 支配，不新增第五种状态。

### 5.3 TOCTOU 防护

§6.2 明确：RESET 确认后获取锁并重取 snapshot；若 identity/type/symlink 状态与展示时不同，释放锁并要求用户重跑。这是正确的 TOCTOU 防护。

### 5.4 Secret persistence

§5 的 POSIX/Windows secret persistence contract 与 `docs/ui/design.md` §3 一致。Secret value 不进入 JSON/log/artifact/prompt/trace。POSIX 单 profile 原子替换、Windows `setx` 部分成功报告。§5.3 明确 Windows `setx` 不具事务性。

### 5.5 Managed-root manifest

§6.1 的 manifest 只含 `.dayu`（whole-tree）和 `config`（whole-tree），与 design.md §3 一致。`assets/`、`portfolio/` 不在 manifest。Package 没有 product-owned `assets`，init 不创建/删除。

### 5.6 Prewarm 零网络

§7 明确禁止联网行为，测试以 socket/network seam fail-fast 证明零网络。与 design.md §3 的 "prewarm 失败只能形成明确 warning" 一致。

### 5.7 Issue/Topic scope

Plan §1.3 正确排除 Issue 142/151/175/177/178、Topic 8/9、Web/WeChat/render。与 Controller entry §5 一致。

### 5.8 Windows setx 与 R11 真实节点

§5.3 的 `subprocess.run(("setx", name, value), shell=False)` 是 argument-safe 的。§8 S3 第 5 点正确集成 R11 两个真实 `.cmd` 节点测试。`setx` 1024 字符截断是已知 Windows 限制，API key 通常不会超过。

### 5.9 Manifest role projection

§4.3 的 16 个 known manifest 分为 8 ordinary + 8 thinking，与 umbrella remediation plan §19.2 一致。Ollama/custom 的两个角色都引用同一动态 model record，正确反映了这些 provider 没有独立 thinking variant。

### 5.10 过度设计检查

三个新模块各自承载已存在且不可互换的 owner 职责。没有引入通用配置 migration framework、通用 transaction engine、provider plugin registry 或新公共 runtime abstraction。`filelock`、ConfigLoader、scene/Service/Fins 全部复用现有 owner。

## 6. Open questions

### OQ-001: prewarm scene_id 值

Plan §7 说 "prepare_entrypoint_runtime(EntrypointRuntimeRequest) 分别覆盖 prompt 与 interactive scene/tool discovery"，但未指定 `scene_id` 的具体值。Implementation agent 需要从 `config/prompts/scenes/` 目录推断（`prompt` 和 `interactive`）。建议在 §7 中显式列出。

### OQ-002: `prepare_entrypoint_runtime` 是 async

该函数是 `async def`（`entrypoint_runtime.py:494`），prewarm 逻辑需要在 async context 中调用。Plan §7 未提及 async 要求。Implementation agent 需在 `commands/init.py` 中使用 `asyncio.run()` 或等价机制。建议在 §7 中明确。

## 7. Residual risks

| 风险 | Owner | 跟踪方式 |
|---|---|---|
| Windows `setx` 多变量写入不具跨调用事务性 | R12/CLI owner | §5.3 已明确 contract；closeout 披露 |
| 两个 managed roots 不能跨 root 单 syscall 原子替换 | R12/CLI owner | §10.1 已明确；rollback 测试覆盖 |
| prewarm 可能触发既有本地目录初始化（如 portfolio/） | R12/CLI owner | §10.1 已明确；测试证明 assets/portfolio 不被 reset 接管 |
| shell profile 可能包含损坏 marker | R12/CLI owner | §5.2 fail closed；让用户显式修复 |
| Ruff 144 pre-existing errors | Repository owner | Controller 裁决是否在 R12 scope 外统一修复 |

## 8. Plan review conclusion

**`pass-with-risks`**

Plan 在架构设计、semantic owner 分离、四态状态机、secret persistence、managed-root transaction、prewarm 零网络和 Issue/Topic scope 控制方面均正确且完整。三个 cumulative slices 的划分合理，每个 slice 的 allowed path、tests、coverage 和 review gate 清晰。

5 个 findings 中：
- **FINDING-001（Ruff baseline）** 和 **FINDING-004（custom-openai 校验）** 是中等严重程度的实施阻塞，需要 plan 修改后才能安全交给 implementation agent
- **FINDING-002（workspace root 创建）** 是中等严重程度的契约缺失，有明确修复路径
- **FINDING-003（staging 目录）** 和 **FINDING-005（lock timeout）** 是低严重程度的精确性问题

Controller 五个 mandatory challenges 中：Challenge 3（prewarm resource lifecycle）和 Challenge 4（post-publish cleanup）经证据验证无 finding；Challenges 1/2/5 对应 FINDING-001/002/004。

建议 AgentCodex 修复 5 个 findings 后，由 AgentMiMo 和 AgentDS 并发 complete re-review。
