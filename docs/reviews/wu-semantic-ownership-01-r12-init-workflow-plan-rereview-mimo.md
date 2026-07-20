# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan — AgentMiMo complete fixed-plan re-review

## 0. Review identity 与结论

- **Reviewer**：AgentMiMo（独立 adversarial re-review，第二轮）
- **Review target**：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`
- **Immutable metrics**：558 行 / 56,459 字节 / SHA-256 `37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b`
- **Review scope**：完整独立审阅全部 558 行，覆盖 §0–§12 所有章节；逐项验证 R12-PF-01..12 修复关闭状态
- **Authority order**：Controller discussion > `docs/ui/design.md` > umbrella remediation plan §19 > 当前代码 > OLD evidence
- **Review posture**：adversarial — 默认假设 fixed plan 至少有一个重要问题，直到证据证明它足够可靠
- **结论**：`PASS_WITH_OBSERVATIONS` — 12 个 PF 组全部有效关闭，无 blocking finding，1 个低严重度观察项

## 1. 完整读取范围与证据基线

### 1.1 读取文档

| 文档 | 行数 | SHA-256 | 用途 |
|---|---|---|---|
| fixed plan（target） | 558 | `37b00dfa...` | 唯一被审对象 |
| Controller adjudication | 142 | `73445f3d...` | PF 接受/拒绝裁决来源 |
| AgentCodex plan-fix | 137 | `27c10831...` | PF 修复证据 |
| Controller plan-fix validation | 114 | `0f4296b7...` | scope/content 基线 |
| Controller plan-entry validation | 118 | `678a1e42...` | authority order 基线 |
| AgentMiMo original review | 236 | `88714fc6...` | 第一轮 findings 对照 |
| AgentDS original review | 365 | `f83fc2d7...` | 第一轮 findings 对照 |
| `docs/ui/design.md` | 112 | — | UI/CLI design authority |
| `AGENTS.md` | 129 | — | 编码/架构约束 |
| `dayu/cli/commands/init.py` | 470 | `c33db731...` | 当前 init 实现 |
| `dayu/cli/arg_parsing.py` | 950 | `d8442bc6...` | 当前 argparse |
| `dayu/runtime/filelock.py` | 335 | `269f30e4...` | 锁实现 |
| `dayu/runtime/config_loader.py` | 2754 | `a5b5b05d...` | ConfigLoader |
| `dayu/config/models.json` | — | `d817a171...` | package model catalog |
| OLD init | — | `f23c4183...` | OLD evidence |

### 1.2 机械验证结果

| 验证项 | 预期 | 实际 | 匹配 |
|---|---|---|---|
| Fixed plan SHA-256 | `37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b` | same | ✓ |
| Fixed plan lines | 558 | 558 | ✓ |
| Fixed plan bytes | 56,459 | 56,459 | ✓ |
| Git commit | `5d4deef8` | same (HEAD) | ✓ |
| Ruff 版本（`.venv`） | `0.15.11` | `.venv` 中 `0.15.11` | ✓ |
| Ruff full JSON 诊断数 | 144 | 144 | ✓ |
| Ruff full JSON SHA-256 | `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` | same | ✓ |
| R12 existing candidate paths scoped Ruff | 0 diagnostics | 0 diagnostics (exit 0) | ✓ |
| R12 absent paths | E902 expected | E902 (3 errors) | ✓ |
| 16 known manifest hashes | plan §2 table | all 16 match | ✓ |
| `custom-openai` in models.json | absent | absent | ✓ |
| `ollama` in models.json | present, provider=ollama, api_key_ref=None | same | ✓ |
| 13 paired ordinary model IDs | present with correct provider/api_key_ref | all match | ✓ |
| 13 paired thinking model IDs | present via extends chain | all resolve correctly | ✓ |
| `config_file_names()` returns 5 files | same | same | ✓ |
| `file_lock` signature | `timeout_seconds: float | None = None, create_parent_dirs: bool = True` | same | ✓ |
| `prepare_entrypoint_runtime` | async, returns frozen dataclass, no close | same | ✓ |
| R11 Windows workflow | exists | exists | ✓ |
| `git diff --check` | exit 0 | exit 0 | ✓ |

## 2. Findings ledger

| # | 类别 | 严重度 | PF 组 | 状态 |
|---|---|---|---|---|
| FINDING-01 | §4.1 thinking model extends resolution 措辞 | 低 | PF-05 | open |
| 其余所有检查项 | 无 finding | — | — | closed |

**结论**：0 个 blocking finding，0 个 medium+ finding。1 个低严重度观察项不影响 implementation。

## 3. R12-PF-01..12 逐项验证

### R12-PF-01 — Ruff gate 可执行且不扩 scope

- **Fixed plan 对应文本**：§2 lines 88–92 锁定 Ruff 版本（`0.15.11`）、144 项、full JSON SHA、candidate-path-zero；§8 每个 slice 有 changed-path 零诊断命令；§9.2 lines 423–466 要求 baseline/current JSON count+SHA+`cmp` 逐字节零差异
- **验证**（`.venv` 激活）：`python -m ruff --version` 输出 `0.15.11`，与 plan 声称一致；Ruff full JSON 确认为 144 项 / SHA `051bd6cc...`；R12 四个已有 candidate path 的 scoped Ruff 为零（exit 0）；absent 新文件产生预期 E902 错误
- **Status**：`FIXED`

### R12-PF-02 — fresh workspace root 有显式 pre-lock owner

- **Fixed plan 对应文本**：§3 owner table 将 bootstrap 交给 `commands/init.py`；§6.3 lines 259–264 定义路径解析、existing symlink/non-directory 拒绝、RESET No 先于创建、`mkdir(parents=True, exist_ok=True)`、并发 identity 复核、permission/ENOSPC/type-race 失败和"init 不删 workspace root"
- **验证**：当前代码 `_ensure_workspace_root` 用 `mkdir(parents=True, exist_ok=True)`；fixed plan 正确地将此职责显式分配给 `commands/init.py` 作为 pre-lock owner；`file_lock` 的 `create_parent_dirs=False` 确保锁不会隐式创建 workspace root
- **代码证据**：`filelock.py:280-281` — `create_parent_dirs=False` 时 parent 不存在直接 raise `RuntimeFileLockError`
- **Status**：`FIXED`

### R12-PF-03 — prewarm invocation 精确且不发明 lifecycle

- **Fixed plan 对应文本**：§7 lines 281–288 精确 `scene_id="prompt"`/`"interactive"`，一次 `asyncio.run` 进入私有 async helper 后顺序 await，typed request 空字符串 slots，当前三类 result 无 close/aclose/context-manager contract；S3 line 381 固定接入点
- **验证**：`prepare_entrypoint_runtime` 确认为 async，返回 frozen dataclass，无 close；`prepare_host_admin` 和 `build_fins_processor_registry` 同样返回无 close contract 的 typed 结果
- **代码证据**：`entrypoint_runtime.py:494` — async def；frozen dataclass return；无 `__del__`/`close`/`__exit__`
- **Status**：`FIXED`

### R12-PF-04 — publication success 与 cleanup warning 分界

- **Fixed plan 对应文本**：§6.4 lines 270–278 把 success boundary 定义为全部 required `os.replace` + parent durability `fsync`；边界前失败 rollback，边界后 no-follow delete/fsync 失败仅 typed warning
- **验证**：plan 正确定义了 publication success boundary、pre-boundary rollback 和 post-boundary warning-only 语义；测试要求覆盖两侧故障注入
- **Status**：`FIXED`

### R12-PF-05 — static/dynamic catalog validation 分离

- **Fixed plan 对应文本**：§4.1 lines 154–162 分成 13 个非 dynamic pair、package `ollama` template 和 dynamic `custom-openai` 三条互斥校验路径
- **验证**：models.json 确认 `custom-openai` absent；13 个 paired choices 的 ordinary ID 均有正确的 provider/api_key_ref；thinking IDs 通过 extends chain 正确解析；`ollama` 确认为 provider=ollama, api_key_ref=None 的 template
- **代码证据**：`models.json` — thinking models 使用 `extends` 字段继承 base model 的 provider/api_key_ref，ConfigLoader 负责解析 extends chain
- **观察**：§4.1 表述"两个 record 的 `provider` 和 `api_key_ref` 都精确匹配"对 thinking model 需理解为 resolved values（通过 extends），而非 raw record 直接字段。ConfigLoader 作为"加载 package `ModelsConfig` 后"的语义已隐含 resolved view。措辞可更精确但不阻塞 implementation（见 FINDING-01）
- **Status**：`FIXED`

### R12-PF-06 — private staging 精确但不成为 public protocol

- **Fixed plan 对应文本**：§6.3 lines 267–268 要求 workspace-root 内不可预测 unique private staging/backup，与 managed target 同 filesystem 且验证 `st_dev`
- **验证**：当前代码已在 workspace root 内创建 staging（`tempfile.mkdtemp(prefix=_STAGING_DIR_PREFIX, dir=workspace_root)`）；plan 不冻结临时名/prefix 为 public contract
- **Status**：`FIXED`

### R12-PF-07 — lock wait 显式无限且可中断

- **Fixed plan 对应文本**：§6.3 line 263 精确 `file_lock(..., timeout_seconds=None, create_parent_dirs=False)`
- **验证**：`file_lock` 签名确认 `timeout_seconds: float | None = None`；`None` 经 `_effective_timeout_seconds` 传递给第三方 `FileLock`，映射为无限等待（`-1.0` convention）；`KeyboardInterrupt` 在等待期间自然传播
- **代码证据**：`filelock.py:220-242` — `file_lock` 函数签名；`filelock.py:150-182` — `acquire` 方法中 `Timeout` 异常处理和 `KeyboardInterrupt` 传播路径
- **Status**：`FIXED`

### R12-PF-08 — PRESERVE 只复制 missing files

- **Fixed plan 对应文本**：§6.2 line 252 只允许 package prompt 普通 missing file，只为它创建 missing parents，不复制空目录且不做目录级 merge
- **验证**：plan 明确 file-granularity 语义，排除 directory-level merge；package `config/prompts/` 下无有意义空目录
- **Status**：`FIXED`

### R12-PF-09 — init lock 不声称 active Host exclusion

- **Fixed plan 对应文本**：§6.2 line 255 RESET 确认前警告停止 active Dayu；§6.3 line 265 明确只是 init-to-init serialization；§10.1 把 external writer 竞争作为 residual
- **验证**：当前 Host 不消费 `.dayu-init.lock`（grep 验证）；plan 正确地将 Host 互斥排除为非目标，RESET 前警告用户停止 active Dayu
- **Status**：`FIXED`

### R12-PF-10 — custom runtime hints 逐值有直接来源

- **Fixed plan 对应文本**：§4.2 lines 166–182 逐 hint 引用 OLD custom temperatures，再按当前 schema 投影
- **验证**：OLD init SHA `f23c4183...` 确认 `_CUSTOM_OPENAI_TEMPERATURE_PROFILES` 存在且值为 write=1.0, overview=1.0, audit=0.8, decision=1.0, interactive=1.0, prompt=1.0, infer=0.5, conversation_compaction=0.4。Plan 表精确匹配 OLD 证据
- **代码证据**：OLD `init.py` — `_CUSTOM_OPENAI_TEMPERATURE_PROFILES` dict 逐值验证一致
- **Status**：`FIXED`

### R12-PF-11 — absent POSIX profile 原子创建 0600

- **Fixed plan 对应文本**：§5.2 lines 210–213 要求确认 persistence 后才触及 profile，same-parent exclusive private temp 强制 `0600`、write/fsync/原子 `os.replace`
- **验证**：plan 正确覆盖了 supported shell 的 profile 不存在时的创建路径、mode 设定、atomic replace 和 symlink/dangling 仍 fail closed
- **Status**：`FIXED`

### R12-PF-12 — `.dayu` 内部状态仍由 Host/runtime 等 owner 所有

- **Fixed plan 对应文本**：§3 owner table 与 §6.1 line 235 把内部名称、创建、校验、生命周期留给现有 Host/runtime/CLI/artifact typed owners
- **验证**：init 只拥有已确认 RESET 的 whole-root transaction；FIRST/PRESERVE/OVERWRITE 不创建、迁移、枚举、修补或重解释 `.dayu/`
- **Status**：`FIXED`

## 4. Detailed findings

### FINDING-01 — §4.1 thinking model extends resolution 措辞（低严重度）

- **位置**：§4.1 — "两个 record 的 `provider` 和 `api_key_ref` 都精确匹配表中承诺"
- **问题**：thinking model records 通过 `extends` 字段继承 base model 的 `provider`/`api_key_ref`，自身不直接拥有这些字段。例如 `mimo-v2.5-pro-thinking-plan` 的 raw record 只有 `extends: mimo-v2.5-pro-plan`，无 `provider`/`api_key_ref`
- **直接证据**：`models.json` — 13 个 thinking model IDs 全部使用 `extends` 继承；ConfigLoader 的 `ModelsConfig` 负责解析 extends chain 输出 resolved view
- **影响**：低。Plan §4.1 后文说"加载 package `ModelsConfig` 后 fail closed"——`ModelsConfig` 是 resolved view，所以实际校验逻辑正确。措辞"两个 record"可能被误解为 raw record 直接字段检查
- **建议**：将"两个 record 的 `provider` 和 `api_key_ref` 都精确匹配"改为"两个 ID 对应的 resolved model record（thinking 通过 extends chain 解析）的 `provider` 和 `api_key_ref` 都精确匹配"
- **Owner**：plan 文档精确性（非 implementation blocking）

## 5. 架构与安全审查

### 5.1 Semantic owner 一致性

Plan §3 定义的 7 个唯一 semantic owner 与 `docs/ui/design.md` §3 和 AGENTS.md 一致：

| 语义 | Plan owner | 正确性 |
|---|---|---|
| init 生命周期/状态机/prewarm | `commands/init.py` | ✓ 不泄露给 argparse/catalog |
| 静态 catalog + dynamic record | `init_catalog.py` | ✓ 单一 typed source |
| OS secret persistence + redaction | `init_environment.py` | ✓ workspace 不接触值 |
| Managed-root manifest + transaction | `init_workspace.py` | ✓ 唯一 manifest 常量 |
| File lock | `dayu/runtime/filelock.py` | ✓ 复用，不增加第二种 lock |
| Config 校验 | `dayu/runtime/config_loader.py` | ✓ 当前 schema 唯一 owner |
| Package defaults | `dayu/config/**` | ✓ init 只读不写 |

### 5.2 四态状态机

FIRST/PRESERVE/OVERWRITE/RESET 定义（§6.2）与 `docs/ui/design.md` §3 一致。状态判定优先级 `RESET > OVERWRITE > (config exists ? PRESERVE : FIRST)` 正确。`--reset --overwrite` 由 reset 支配，不新增第五种状态。

### 5.3 TOCTOU 防护

§6.2 明确：RESET 确认后获取锁并重取 snapshot；若 identity/type/symlink 状态与展示时不同，释放锁并要求用户重跑。正确。

### 5.4 Secret persistence

§5 POSIX/Windows contract 与 design.md §3 一致。Secret value 不进入 JSON/log/artifact/prompt/trace。POSIX 单 profile 原子替换、Windows `setx` 部分成功报告。§5.3 明确 Windows `setx` 不具事务性。

### 5.5 Managed-root manifest

§6.1 的 manifest 只含 `.dayu`（whole-tree）和 `config`（whole-tree）。`assets/`、`portfolio/` 不在 manifest。Design.md §3 的 reset 范围包含 `assets/`，但以"当前产品存在时的"为条件——当前仓库无 `dayu/assets`，R12 plan 正确地按 Issue 151 非目标排除。

### 5.6 Prewarm 零网络

§7 明确禁止联网行为，测试以 socket/network seam fail-fast 证明零网络。与 design.md §3 一致。

### 5.7 Issue/Topic scope

Plan §1.3 正确排除 Issue 142/151/175/177/178、Topic 8/9、Web/WeChat/render。与 Controller entry §5 一致。`wechat` 作为 known manifest 的 thinking role 出现是 §4.3 唯一允许的 production 命中。

### 5.8 过度设计检查

三个新模块各自承载已存在且不可互换的 owner 职责。没有引入通用配置 migration framework、通用 transaction engine、provider plugin registry 或新公共 runtime abstraction。`filelock`、ConfigLoader、scene/Service/Fins 全部复用现有 owner。

## 6. 拒绝的扩展与不变量

以下内容按 Controller adjudication 明确不实现，fixed plan 中未出现：

1. 不清理 144 个历史 Ruff 诊断
2. 不固定 staging/backup 名称为 public protocol
3. 不加 finite magic timeout
4. 不加 Host lock/process discovery/kill
5. 不为无 close contract 的 typed result 发明 resource close framework
6. 不创建通用 migration、transaction、authorization framework
7. 不实现 Issue 142/151/175/177/178
8. Topic 8/9 保持 no-code 决策

## 7. 残余风险

| 风险 | Owner | 已有 contract |
|---|---|---|
| Windows `setx` 多变量不具跨调用事务性 | R12/CLI | §5.3 明确 contract；config 不发布时只报告已写 env names |
| 多 managed-root publication 不是跨 root 单 syscall atomic | R12/CLI | §6.4 定义有序 rename + rollback |
| Post-boundary backup cleanup 可 warning | R12/CLI | §6.4 明确 typed warning + retained path |
| Init lock 只串行 init，不防 active Host writer | R12/CLI | §6.2 RESET 前警告；§10.1 residual |
| Shell profile 损坏 marker | R12/CLI | §5.2 fail closed |
| Prewarm 可触发既有本地目录初始化 | R12/CLI | §7 无网络；§10.1 residual |

无 unclassified residual。Ruff 版本已用 `.venv` 复核通过（`0.15.11` / 144 项 / SHA `051bd6cc...`），不构成残余风险。

## 8. 三个 cumulative slices 审查

| Slice | 允许路径 | 测试/验证 | Review gate |
|---|---|---|---|
| S1 | init_catalog.py + init_environment.py + tests | 15 项 catalog 校验、role projection、Ollama/custom 输出、POSIX/Windows secret | owner/contract/无泄漏/当前 schema |
| S2 | S1 + init_workspace.py + init.py + arg_parsing.py + tests | 四态矩阵、fresh path、reset TOCTOU、manifest、lock/containment/symlink、rollback fault points | 逐状态+逐 fault point 审核 |
| S3 | S2 + smoke + Windows workflow + README | POSIX/Windows subprocess smoke、prewarm orchestration、coverage/pyright/Ruff/diff/scans | 真实 smoke/coverage/docs/scans |

Slices 累积正确，每个 slice 的 allowed path 集精确，review gate 隔离最高风险 seam。

## 9. Verdict

**`PASS_WITH_OBSERVATIONS`**

- 12 个 PF 组全部有效关闭，fixed plan 修复了所有 Controller adjudicated findings
- 0 个 blocking finding，0 个 medium+ severity finding
- 1 个低严重度观察项（thinking model extends resolution 措辞）不阻塞 implementation
- 架构边界、semantic owner、四态状态机、secret persistence、managed-root transaction、prewarm 零网络和 Issue/Topic scope 控制均正确且完整
- 三个 cumulative slices 划分合理，每个 slice 的 allowed path、tests、coverage 和 review gate 清晰

**可进入 implementation gate。**
