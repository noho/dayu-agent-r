# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan — AgentDS Independent Complete Re-Review

## 0. Review Identity

- **Reviewer**: AgentDS (independent adversarial complete re-review of fixed plan)
- **Timestamp**: 20260718-071147
- **Immutable re-review target**: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`
  - 558 lines / 56,459 bytes / SHA-256 `37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b`
- **Re-review scope**: 完整独立审阅 fixed plan 全部 558 行；逐项验证 R12-PF-01..12 closure；审查三 cumulative slices、owner 边界、事务/回滚、secret、prewarm、POSIX/Windows smoke、coverage/pyright/Ruff、security retention、Issue 142/151/175/177/178 与 Web/WeChat/render/no-code Topic 8-9 边界
- **Posture**: Adversarial — 默认假设 fixed plan 仍至少有一个重要问题，直到证据证明它足够可靠交给 implementation agent

## 1. Complete read scope and evidence baseline

### 1.1 Required documents (全部完整读取)

| Artifact | Lines | SHA-256 (verified) |
|---|---|---|
| Fixed plan (immutable target) | 558 | `37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b` |
| Controller adjudication | 142 | `73445f3d09c145e34f38dbf9311bd75e534f0f9318df702e127996453a33bc46` |
| AgentCodex plan-fix | 137 | `27c1083159181ce5c5bb9b685bd25a282bff02b9e84df10e3a753eabf6fea824` |
| Controller plan-fix validation | 114 | `0f4296b7254ce59d9c5f922ce89837e49ee357efa9343168c3a4620c2b2f22dd` |
| AGENTS.md (project constraints) | 128 | 直接读取 |
| `docs/ui/design.md` (design truth) | 111 | 直接读取 |
| AgentMiMo original review | 236 | `88714fc66d964ec54d587ae651210d4a79c62bd099de50830d9fcb0b169fdeec` |
| AgentDS original review | 365 | `f83fc2d7058be2941637cd9c43f17ef863940fd055712ee848145b56c1699ff2` |

### 1.2 Direct code evidence (全部完整读取)

| Evidence | Path | Key facts verified |
|---|---|---|
| Current init.py | `dayu/cli/commands/init.py` 470 行 | 非交互 copier；`_ensure_workspace_root` 使用 `mkdir(parents=True, exist_ok=True)`；staging 用 `tempfile.mkdtemp(dir=workspace_root)` |
| Current arg_parsing.py | `dayu/cli/arg_parsing.py` 950 行 | `--reset`/`--overwrite` 两个 flag |
| filelock.py | `dayu/runtime/filelock.py` 335 行 | `file_lock(lock_path, timeout_seconds=None, create_parent_dirs=True)`；`None` → 第三方 `-1.0` 无限等待 |
| models.json | `dayu/config/models.json` 1041 行 | SHA `d817a17135a01e1e7d89ada9e6b93b107d29fa9715105340c7ff44d505cf8b68`；26 条 record；`ollama` 在（provider=ollama, api_key_ref=null）；`custom-openai` 不存在 |
| entrypoint_runtime.py | L260–309, L494–543 | `EntrypointRuntimeRequest` 7 字段含 `context_slot_values: Mapping[str, JsonValue]`、`env: Mapping[str, str]`；`prepare_entrypoint_runtime` async；返回 frozen `EntrypointRuntimeResult` |
| host_admin.py | L19–98 | `ServiceHostAdminRequest` 4 字段含 `config_overlay_dir: Path \| None`；`prepare_host_admin` sync；返回 frozen `ServiceHostAdminResult` |
| scene_prepare.py | L107–131, L189–203, L1201–1227 | `SceneToolCatalog(tools: tuple[SceneToolInfo, ...])` 可空 tuple；`ScenePrepareRequest` 5 字段含 `available_tools: SceneToolCatalog`（必填无默认）；`_select_tools` 对 `tool_names` 做 catalog 存在性校验 |
| 16 known manifests | `dayu/config/prompts/manifests/*.json` | 精确 16 个文件存在 |
| Ruff baseline | raw stdout JSON | `ruff 0.15.11`，144 errors，raw stdout SHA `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` 已验证匹配 |

### 1.3 Git baseline

- HEAD commit: `5d4deef8d37fb75b496d33fef9e2da11111a76d6` — matches plan §2
- `git diff --name-only HEAD -- dayu/ tests/ utils/` → 空输出（无 tracked production/test modification since HEAD）
- Plan §2 所有起始 SHA-256 已验证可复现（`models.json`、`filelock.py`、`arg_parsing.py`、`commands/init.py`）

## 2. R12-PF-01..12 closure verification (逐项)

### R12-PF-01 — Ruff gate executable without scope expansion

| Aspect | Plan location | Evidence |
|---|---|---|
| Immutable baseline fingerprint | §2 lines 88–92 | Ruff `0.15.11`，144 errors，raw stdout SHA `051bd6cc...` — verified matching |
| Changed-path zero | §8 S1/S2/S3 验证块 | 每个 slice 的累积 allowlist scoped Ruff 命令 |
| Full fingerprint no-delta | §9.2 lines 423–466 | baseline/current count+SHA+`cmp` 逐字节零差异 |
| No 144 cleanup | §10.2 line 506 | "不清理或重分类历史基线" |
| Full pyright zero retained | §9.2 line 466 | `python -m pyright dayu/ tests/ utils/` exit 0 零诊断 |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-02 — fresh workspace root has explicit pre-lock owner

| Aspect | Plan location | Evidence |
|---|---|---|
| Bootstrap owner | §3 owner table row 1 | `commands/init.py` 是 "fresh workspace pre-lock bootstrap" owner |
| Path resolution + rejection | §6.3 lines 259–261 | `lstat`/resolved identity；拒绝 symlink、dangling、普通文件、非目录 |
| RESET No before creation | §6.3 line 261 | "RESET 的 unlocked snapshot... 先于创建，因此取消 RESET 不会留下新目录" |
| `mkdir(parents=True, exist_ok=True)` | §6.3 lines 261–262 | 锁前显式创建；并发后重做 identity 复核 |
| Permission/ENOSPC/type-race | §6.3 line 262 | fail closed |
| No root deletion on cancel | §6.3 line 262 | "init 不拥有 workspace root 删除语义" |
| Tests | §8 S2 lines 348–349 | fresh path FIRST、并发 identity、permission/ENOSPC、file/symlink races |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-03 — prewarm invocation exact, no lifecycle invention

| Aspect | Plan location | Evidence |
|---|---|---|
| Exact scene IDs | §7 line 284 | `scene_id="prompt"` / `scene_id="interactive"` |
| Async boundary | §7 line 285 | 一次 `asyncio.run(...)` 进入私有 async helper，顺序 await |
| Empty context slots | §7 line 284 | `fins_default_subject`/`current_time` 空字符串，不伪装业务事实 |
| No close contract | §7 lines 286–288 | `EntrypointRuntimeResult`、`ServiceHostAdminResult`、`ProcessorRegistry` 均无 close/aclose/context-manager |
| Contract drift → stop | §7 line 288 | "若实现前 CURRENT seam 真正出现 owned closable resource，这是停止并交 Controller 的 contract drift" |
| Zero network | §7 line 287 | "测试以 socket/network seam fail-fast 证明零网络" |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-04 — publication success and cleanup failure distinct

| Aspect | Plan location | Evidence |
|---|---|---|
| Success boundary | §6.4 line 276 | 全部 required `os.replace` + parent durability `fsync` |
| Pre-boundary → rollback | §6.4 lines 276–277 | 逆序恢复全部 backup；FIRST 移除已 rename 的 config |
| Post-boundary → warning | §6.4 lines 277–278 | typed warning/recoverable diagnostic，保留精确 backup path，"不 rollback、不把已发布 config 报告为失败、不改变 init 成功 exit status" |
| Deletion durability unconfirmed | §6.4 line 278 | "deletion durability unconfirmed" 单独报告 |
| Tests | §8 S2 lines 352–353 | pre/post boundary fault injection；backup delete fail + post-delete fsync fail |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-05 — static and dynamic catalog validation disjoint

| Aspect | Plan location | Evidence |
|---|---|---|
| 13 non-dynamic pairs | §4.1 lines 156–157 | fail closed：两个 ID 都存在，provider/api_key_ref 精确匹配 |
| Package `ollama` | §4.1 lines 157–158 | 单独校验：`ollama` template 存在，provider=ollama，api_key_ref=null |
| `custom-openai` absence | §4.1 lines 159–160 | "在 package `models.json` 中不存在是预期事实"；package-default 不得对它做 ID 存在性校验 |
| Dynamic validation | §4.2 lines 180–181 | staging 构建后由真实 `ConfigLoader` 重载校验 |
| Tests | §8 S1 lines 310–311 | static mismatch fail-closed + custom absence non-error |

**Verdict: FIXED / CLOSED.** ✓ — 另见 R12-RR-01。

### R12-PF-06 — private staging precise but not public protocol

| Aspect | Plan location | Evidence |
|---|---|---|
| Unique/private | §6.3 lines 267–268 | workspace root 内不可预测、唯一、仅本 transaction 持有 |
| Same filesystem | §6.3 line 267 | 显式核验 `st_dev` 相同 |
| Not public/LLM-facing | §6.3 line 268 | "临时名/prefix 是内部实现细节，不是 public、README 或 LLM-facing protocol" |
| Tests | §8 S2 line 351 | 测试不固定临时名称 |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-07 — lock wait explicit and interruptible

| Aspect | Plan location | Evidence |
|---|---|---|
| Explicit `timeout_seconds=None` | §6.3 line 263 | `file_lock(<workspace>/.dayu-init.lock, timeout_seconds=None, create_parent_dirs=False)` |
| Interruptible | §6.3 line 263 | "等待中 SIGINT 必须零 publish" |
| No finite magic timeout | §10.3 line 522 | "不造 magic timeout" |
| Lock visibility | §6.3 line 263 | "CLI 可显示正在等待的 workspace 与 lock path，不得显示 secret" |
| Tests | §8 S2 lines 342, 351 | 编排覆盖；竞争测试 |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-08 — PRESERVE copies missing prompt files only

| Aspect | Plan location | Evidence |
|---|---|---|
| File granularity | §6.2 line 252 | "prompt assets 仅指 package `config/prompts/` 下相对路径缺失的普通文件" |
| Parent-only dir creation | §6.2 line 252 | "只在复制某个 missing file 时创建它的 missing parent directories" |
| No empty-dir protocol | §6.2 line 252 | "不复制 package 空目录，不定义空目录协议，也不做目录级 merge" |
| Tests | §8 S2 line 347 | owner-level 测试 |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-09 — init lock does not claim active Host exclusion

| Aspect | Plan location | Evidence |
|---|---|---|
| Init-to-init only | §6.3 line 265 | "该锁只证明 init-to-init serialization；Host 当前不消费它" |
| RESET warning | §6.2 line 255 | 确认前显示"请先停止当前 workspace 的 active Dayu 进程" |
| No Host lock/process kill | §6.2 line 255 | "R12 不做 Host lock、process discovery、kill 或统一治理" |
| External writer residual | §10.1 line 504 | "若 active Host 或其它 Dayu 进程继续写 managed roots，RESET 仍可与外部 writer 竞争" |
| Tests | §8 S2 line 349 | 断言未调用 Host lock/process discovery/kill |
| README | §8 S3 line 389 | 将此用户边界写入根 README |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-10 — custom runtime hints have direct OLD source

| Aspect | Plan location | Evidence |
|---|---|---|
| OLD evidence reference | §4.2 line 166 | `_CUSTOM_OPENAI_TEMPERATURE_PROFILES` 精确八个 temperature：`1.0/1.0/0.8/1.0/1.0/1.0/0.5/0.4` |
| Current-schema projection | §4.2 lines 167–178 | 逐 hint 投影 `top_p=1.0`；普通 stream `true`；compaction stream `false` |
| Ollama values removed | §4.2 line 166 | "Custom runtime hints 不复制 Ollama 或任意当前 provider record" |
| Not generic default | §4.2 line 179 | "catalog owner 只做下表这一次明示的 OLD-workflow → current-schema 投影，不将它宣称为通用 provider 默认" |
| Contract drift → stop | §4.2 line 179 | "如实现时上述 OLD 证据或 current-schema 精确字段契约已漂移，必须停止并交 Controller" |
| Tests | §8 S1 line 311 | 逐值等于投影 |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-11 — absent POSIX profile atomic creation 0600

| Aspect | Plan location | Evidence |
|---|---|---|
| Confirmation first | §5.2 line 210 | "只有在用户已显式确认 persistence plan 后才允许触及选中 profile" |
| Atomic creation | §5.2 lines 211–212 | same-parent exclusive private temp → 显式 `0600` → write/fsync → `os.replace` |
| Not pre-create empty file | §5.2 line 212 | "不先创建空 public profile，不受 umask 偶然行为决定最终 mode" |
| Existing mode preserved | §5.2 line 211 | "已存在普通文件保留原 mode" |
| Symlink/dangling fail closed | §5.2 line 211 | retained |
| Tests | §8 S1 line 312 | supported shell profile 不存在 → 确认后原子创建 mode=0600 |

**Verdict: FIXED / CLOSED.** ✓

### R12-PF-12 — `.dayu` internal state remains Host/runtime-owned

| Aspect | Plan location | Evidence |
|---|---|---|
| Owner table | §3 row 6 | "`.dayu/` 内部名称、创建与生命周期 | 现有 Host/runtime/CLI/artifact 各自的 typed owner" |
| Init scope | §6.1 line 235 | "Init 只在已确认 RESET 的 whole-root transaction 层面把 `.dayu/` 移出 public path" |
| FIRST/PRESERVE/OVERWRITE | §6.1 line 235 | "均不创建、迁移、枚举、修补或重解释 `.dayu/` 内部状态" |
| Internal owners retained | §6.1 line 235 | "现有 Host/runtime/CLI/artifact 边界各自所有：它们决定内部名称、创建、校验与生命周期" |

**Verdict: FIXED / CLOSED.** ✓

### Closure summary

All 12 accepted plan-fix groups are genuinely closed in the fixed plan. The Controller's 5 rejected/no-fix items remain absent: no unrelated Ruff cleanup, no frozen temp protocol, no finite magic timeout, no Host lock/process kill, no speculative close framework. No accepted finding was weakened or bypassed.

## 3. New adversarial findings

### R12-RR-01 — 未修复 — 中 — pre-publish `ScenePrepareRequest` validation 缺少 `SceneToolCatalog` 构造规范

- **位置**: Plan §6.4 step 3 (line 274)
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: "pre-publish validate：用真实 `ConfigLoader` 读取 staging 当前五配置文件；再对精确 16 个 known manifest 逐一调用 `dayu.runtime.scene_prepare.prepare_scene(ScenePrepareRequest)`，校验 current manifest/scene/model/tool contract 能装配。"
- **反例/失败场景**: `ScenePrepareRequest` 的 `available_tools: SceneToolCatalog` 字段是必填且无默认值（`scene_prepare.py:203`）。若 implementation agent 传入空 `SceneToolCatalog(tools=())`，则任何在 manifest 中显式声明 `tool_names` 或 `tool_tags_any` 且 `allow_empty=False`（默认）的 scene 会触发 `ScenePrepareError`（`_select_tools` at L1219–1226）。Plan 没有说明在 staging-only 上下文中如何构造有效的 `SceneToolCatalog`。
- **为什么有问题**: plan §6.4 step 3 是 pre-publish validation 的一部分，必须在 mutation 前完成。若 validation 因 tool catalog 不完整而失败，用户无法完成 init。Implementation agent 面临三个都不理想的选项：(a) 从 package tool definition 构造完整 tool catalog（需要理解 tool discovery 流程且可能拉入 Service 层依赖），(b) 使用空 catalog 并接受某些 scene 验证失败，(c) 跳过 `prepare_scene` 中的 tool selection 阶段（破坏 contract）。
- **直接证据**:
  - `ScenePrepareRequest` dataclass（`dayu/runtime/scene_prepare.py:189–203`）：`available_tools: SceneToolCatalog` 无默认值
  - `SceneToolCatalog`（L130–131）：`tools: tuple[SceneToolInfo, ...]`，可接受空 tuple
  - `_select_tools`（L1212–1227）：`SceneToolSelectionMode.NONE` 不查 catalog；`ALL` 不查 catalog；但显式 `tool_names` 或 `tool_tags_any` 要求 catalog 中存在匹配项，否则 `ScenePrepareError`
  - Plan 未在任何位置说明如何构造 `SceneToolCatalog`
- **影响**: 实施 Agent 在 S2 中遇到此 gap 时可能选择错误路径，导致 pre-publish validation 过松（隐藏 manifest 问题）或过严（阻止合法 init）
- **建议改法和验证点**:
  1. 在 §6.4 step 3 中明确：使用 `SceneToolCatalog(tools=())`（空目录），并确认全部 16 个 known manifest 的 `tool_selection.mode` 均为 `ALL` 或 `NONE`（不依赖具体 tool name / tag）；若任一 manifest 使用显式名称/tag 选择，则需从 package tool definition 构造最小 catalog。
  2. 或者：在 S2 验证步骤中显式说明 "pre-publish `prepare_scene` 调用只需验证 scene/manifest/model 字段的 schema 一致性；tool contract 验证推迟到 S3 prewarm 阶段"，并在 §6.4 step 3 中将 `prepare_scene` 替换为更轻量的 manifest parser 校验。
  3. 验证点：S2 测试必须证明任一 manifest 的显式 tool 选择不会导致 pre-publish validation 假阳性失败。
- **修复风险**: 低
- **严重程度**: 中

### R12-RR-02 — 未修复 — 中 — S3 跨进程竞争 smoke test 缺少进程协调机制

- **位置**: Plan §8 S3 line 383
- **问题类型**: 不可直接实施 / 测试缺口
- **当前写法**: "竞争 smoke：父进程持有真实 `.dayu-init.lock`，子进程不发布；释放后成功。两个真实 CLI publisher 最终只能串行，终态可由 `ConfigLoader` 读取。"
- **反例/失败场景**: 两个真实 subprocess CLI 调用需要协调：(a) 父进程获取锁，(b) 子进程启动并阻塞，(c) 父进程释放锁，(d) 子进程获取锁并完成。没有任何进程间协调协议（信号、超时、轮询、pipe），直接交给 implementation agent 设计会使测试依赖 timing luck（子进程必须在父进程释放前启动并进入等待），极易变成 flaky test。
- **为什么有问题**: 跨进程并发测试是最难做可靠的测试类别之一。Plan 只说"父进程持有锁，子进程不发布；释放后成功"但没有指定：(a) 父进程如何通知测试 harness "我已获取锁"，(b) 测试 harness 如何在父进程持锁期间启动子进程，(c) 子进程如何向测试 harness 报告 "我正在等待锁"（区别于"我因其他原因卡住"），(d) 超时策略。
- **直接证据**:
  - Plan §8 S3 line 383：仅 3 行描述整个并发测试
  - 当前 `filelock.py` 使用第三方 `FileLock.acquire(timeout=-1.0)` — 无限等待，没有内置进度报告
  - Plan §1.3 排除 "Host lock/process kill"，因此测试不能用 Host 信号机制
- **影响**: 实施 Agent 可能：(a) 实现一个 flaky test 在 CI 中随机失败，(b) 过度设计进程协调框架，(c) 把测试降级为单进程 mock 从而失去并发验证价值
- **建议改法和验证点**:
  1. 在 plan 中指定最小协调协议：父进程获取锁后向 stdout 写一个 sentinel line；测试 harness 用 `subprocess.Popen` + 轮询 stdout 检测 sentinel，然后启动子进程。子进程设置 finite timeout（如 30s）等待锁；父进程在测试 harness 确认子进程已启动后释放锁（通过 stdin 或 signal）。
  2. 或明确此测试是 best-effort smoke，允许在 CI 中用 `pytest.mark.flaky` 标记，不阻断 gate。
  3. 验证点：测试在循环运行 ≥20 次中至少 19 次通过。
- **修复风险**: 低
- **严重程度**: 中

### R12-RR-03 — 未修复 — 低 — prewarm `env` allowlist 收集路径未指定

- **位置**: Plan §7 line 285
- **问题类型**: 契约缺失
- **当前写法**: "`env` 只投影本次已选 model/tool config 所需的 allowlisted env names"
- **反例/失败场景**: Implementation agent 需要知道：哪些 env names 是 "allowlisted"？从 catalog 的 `required env` 列收集？还是从 `models.json` 的 `api_key_ref` 动态派生？`prepare_entrypoint_runtime` 的 `env` 参数是所有环境变量的完整映射还是仅 filtered subset？若 agent 传空 mapping，`compose_open_host_options` 可能因缺少必需 env 而失败，prewarm 产生虚假 warning。
- **为什么有问题**: plan 未指定 `env` mapping 的构造路径，使 prewarm 行为依赖于实现 agent 的解读。若 agent 传空 `env` → prewarm 失败（假阳性 warning）。若 agent 传完整 `os.environ` → 泄漏非 allowlisted env（违反 least privilege）。
- **直接证据**:
  - Plan §7 line 285："`env` 只投影本次已选 model/tool config 所需的 allowlisted env names"
  - `EntrypointRuntimeRequest.env: Mapping[str, str]`（`entrypoint_runtime.py:279`）— 无默认值
  - Plan catalog §4.1 table 中每行有 `required env` 列
  - Plan 可选集成 §5.1 line 204 列出 `TAVILY_API_KEY` 等五个可选 env
- **影响**: 低 — implementation agent 大概率做对（从 catalog selection 收集 required env + 可选 env names，从 `os.environ` 取值），但 plan 应显式说明
- **建议改法和验证点**: 在 §7 中增加一句："allowlisted env names 由 catalog entry 的 `required env` 与用户已提供的可选集成 env name 的并集决定；值从当前 `os.environ` 读取（secret persistence 已将它们注入进程环境），不在 prewarm 中直接访问 secret typed entry。"
- **修复风险**: 低
- **严重程度**: 低

### R12-RR-04 — 未修复 — 低 — `dayu/config/README.md` 更新触发与 R12 scope 的连接未说明

- **位置**: Plan §8 S3 allowed paths (line 376)
- **问题类型**: 范围漂移
- **当前写法**: S3 将 `dayu/config/README.md` 纳入修改范围，line 389 要求写 "当前配置 owner、PRESERVE/OVERWRITE/RESET 与 manifest projection"
- **反例/失败场景**: R12 不修改 `dayu/config/` 下的任何 production 文件（plan §3 line 125："R12 不改 package models/manifests"）。AGENTS.md 的 README 触发规则是 "`dayu/config/` 修改 -> 检查并按需更新 `dayu/config/README.md`"。由于 `dayu/config/` 未被修改，严格意义上触发条件未满足。Plan 没有解释为何该 README 仍在 R12 scope 内。
- **为什么有问题**: 项目约束要求 README 更新由代码变更触发，不是任意文档改进都自动进入 scope。`dayu/config/README.md` 更新可能有合理动机（init 是用户与 config 的主要交互面），但 plan 应说明理由而非隐含纳入。
- **直接证据**:
  - AGENTS.md line 110："`dayu/config/` 修改 -> 检查并按需更新 `dayu/config/README.md`"
  - Plan §3 line 125："R12 不改 package models/manifests"
  - Plan §8 S3 line 376：`dayu/config/README.md` 在 allowed paths
- **影响**: 低 — 不影响 implementation correctness；若 Controller 裁决无需更新，可从此 slice 移除
- **建议改法和验证点**: 在 plan §1.1 或 §8 S3 中增加一句："`dayu/config/README.md` 更新是因为 PRESERVE/OVERWRITE/RESET 改变了用户对 config 生命周期的认知，属于用户可见 config 行为变化，不依赖 `dayu/config/` 文件修改触发。"
- **修复风险**: 低
- **严重程度**: 低

### R12-RR-05 — 未修复 — 低 — `commands/init.py` 单文件 ≥80% 覆盖率在 orchestrator 上的实现挑战

- **位置**: Plan §9.1 line 417
- **问题类型**: 测试缺口（风险提示，非阻断）
- **当前写法**: `pytest tests/cli/test_init_command.py tests/cli/test_init_smoke.py --cov=dayu.cli.commands.init --cov-report=term-missing --cov-fail-under=80 -q`
- **反例/失败场景**: `commands/init.py` 是 orchestrator 模块，包含交互式选择（需要 stdin mock）、secret 收集（需要隐藏输入 mock）、四态分支、prewarm async boundary、SIGINT handling、lock acquire/release 编排——这些路径中多个依赖真实 I/O。S2 重写后，旧的 `test_init_command.py`（82 tests）测试的是 copier 行为，必须全部迁移。实现 agent 可能发现某些 orchestrator 路径（如 KeyboardInterrupt 在交互选择中、concurrent lock race 恢复）无法在纯单元测试中达到 80%，需要依赖 S3 smoke test 补覆盖率，但 S3 在覆盖率计算时已进入。
- **为什么有问题**: plan 要求 S2 结束时 `commands/init.py` 单文件覆盖率 ≥80%（§9.1 line 417 同时引用 `test_init_command.py` 和 `test_init_smoke.py`），但 `test_init_smoke.py` 在 S3 才引入。S2 仅允许 `test_init_command.py`（修改）和 `test_init_workspace.py`（新增）。若 S2 结束时覆盖率不达标，S2 review gate 过不去；但 S2 没有 smoke test 来覆盖真实 I/O 路径。这是一个 slice 边界处的覆盖率可达性风险。
- **直接证据**:
  - Plan §9.1 line 417：单文件覆盖率命令同时包含 `test_init_command.py` 和 `test_init_smoke.py`
  - Plan §8 S2 line 335：`test_init_smoke.py` 不在 S2 allowed paths
  - Plan §8 S3 line 373：`test_init_smoke.py` 在 S3 才引入
  - Plan §9.1 line 417 出现在 §9 "Coverage、全量验证与机械 scans"（跨 slice 通用要求），但 §8 S2 review gate 引用 §9 时并未单独降低覆盖率要求
- **影响**: 低 — 这不是结构性缺陷。S2 可通过 mock-heavy 单元测试达到 80%；S3 smoke test 提供额外防御。但 plan 应澄清 S2 review gate 的覆盖率预期是基于 `test_init_command.py + test_init_workspace.py`，还是允许 S2 以 <80% 通过、S3 再补足。
- **建议改法和验证点**: 在 §8 S2 review gate 中明确："S2 覆盖率命令使用 `pytest tests/cli/test_init_command.py tests/cli/test_init_workspace.py --cov=dayu.cli.commands.init --cov-report=term-missing`（S3 smoke 引入前），目标仍为 ≥80%；若纯单元测试无法达到则可在 S2 记录 gap 并在 S3 smoke 补齐后重新验证。"
- **修复风险**: 低
- **严重程度**: 低

## 4. Architecture boundary review

逐层审查 fixed plan 的 owner 分配（对照 `AGENTS.md` 分层架构硬约束和 semantic ownership 约束）：

| 语义 | Plan owner | 判定 | 证据 |
|---|---|---|---|
| init 生命周期、提示顺序、pre-lock bootstrap、四态决策、prewarm | `commands/init.py` | ✓ | 不泄露给 argparse/catalog |
| 静态 catalog + dynamic record + manifest projection | `init_catalog.py` | ✓ | 单一 typed source |
| OS secret persistence + redaction | `init_environment.py` | ✓ | workspace 不接触值 |
| Managed-root manifest + transaction | `init_workspace.py` | ✓ | 唯一 `ManagedRootManifest` 常量 |
| File lock | `dayu/runtime/filelock.py` | ✓ | 复用，不增加第二种锁 |
| Config/schema 校验 | `dayu/runtime/config_loader.py` | ✓ | 当前 schema 唯一 owner |
| Package defaults | `dayu/config/**` | ✓ | init 只读不写 |
| argparse | `dayu/cli/arg_parsing.py` | ✓ | 只解析 flags，不反推业务语义 |
| `.dayu/` 内部结构 | Host/runtime/CLI/artifact 各自 typed owner | ✓ | init 不创建/迁移/枚举/重解释 |

**结论**: 无架构边界违规。三模块拆分（catalog / environment / workspace）对应三类不可互换的 owner。无反向依赖。无 `dayu.runtime` 对上层模块的 import。无 God function/object/dataclass。

## 5. Overcoupling review

- argparse 与业务语义解耦：argparse 只解析 `--reset`/`--overwrite` flags，不反推状态机 ✓
- workspace transaction 与 secret persistence 解耦：secret 在 workspace mutation 前完成 ✓
- catalog 与 manifest 内容解耦：catalog 引用 model ID，不解析 manifest ✓
- 多消费者共源：唯一 `ManagedRootManifest` 常量驱动 snapshot、reset 展示、containment、backup、publish、rollback、cleanup ✓
- staging 名称不是 public contract：不进入 README/LLM-facing protocol ✓

**结论**: 无过度耦合。

## 6. Overengineering review

对照 rejected items 验证 fixed plan 未引入：

- 无通用配置迁移框架 ✓
- 无通用 transaction engine ✓
- 无 provider plugin registry ✓
- 无统一 tool authorization ✓
- 无新 runtime abstraction ✓
- 无 resource close/cache/FD framework ✓
- 无 Host lock/process discovery/kill ✓
- 无 finite magic timeout ✓
- 无 frozen public temp protocol ✓

三个新模块是三类不可互换 owner 的最小表达。三个 slices 按"纯 contract → 文件系统发布 → 集成验证"累积，隔离了最高风险 seam。

**结论**: 无过度设计。

## 7. Security retention review

| 安全边界 | Plan contract | Evidence |
|---|---|---|
| Secret value 不进 workspace/log/error | §5.1 lines 205–206 | `repr=False` typed entry；异常 message 不含值 |
| POSIX profile atomic 0600 | §5.2 lines 211–213 | same-parent private temp → fsync → `os.replace` |
| POSIX symlink/dangling 拒绝 | §5.2 line 211 | fail closed |
| Windows `setx` argument-safe | §5.3 lines 217–218 | `shell=False`，不构造 command string，不记录 stdout/stderr |
| Windows CI sentinel only | §5.3 line 220 + §8 S3 line 384 | 唯一非 secret sentinel；生产 key 只在 mock/隔离输入 |
| CI artifact 不含 env value | §8 S3 line 386 | 只允许测试报告、版本、文件 hash 与 env names |
| Containment + symlink no-follow | §6.3 lines 266–267 | lexical + resolved containment；所有 walk no-follow |
| Lock path 不是 managed root | §6.1 line 234 | `.dayu-init.lock` 在 manifest 外 |
| Network scan source guard | §9 source scans line 483 | `requests\.\|httpx\.\|urllib\|socket\|huggingface\|download\|web_search\|open_host\|run\(` 在 init 模块零命中 |

**结论**: 安全保留边界完整。无新增攻击面。

## 8. Issue/Topic boundary verification

| Issue/Topic | Plan §1.3 explicit exclusion | Boundary intact |
|---|---|---|
| Issue 142 (workspace migration) | "不设计或调用 workspace migration" | ✓ |
| Issue 151 (Write/assets owner) | "不实现 Write/assets owner" | ✓ |
| Issue 175 (Docling isolation) | "不改变 Docling 进程隔离" | ✓ |
| Issue 177 (document truncation) | "不改变文档截断" | ✓ |
| Issue 178 (storage state lifecycle) | "不改变 storage state lifecycle" | ✓ |
| Web, WeChat, render | "不改变入口、服务装配或渲染行为" | ✓ |
| Topic 8 (exception truncation) | "不修改 240 字 exception truncation 决议" | ✓ |
| Topic 9 (tool authorization) | "不设计统一 tool authorization" | ✓ |

`wechat` 的 exact manifest basename 是 §4.3 的唯一允许 production 命中（thinking role）。无新实现分支。

**结论**: 所有 Issue/Topic 边界完整，无 scope creep。

## 9. Three cumulative slices review

### S1 — Typed catalog, manifest projection, OS environment owner

- **Allowed paths**: 4 个文件（2 新 production + 2 新 test）
- **实现**: catalog 静态校验、dynamic record builder、POSIX/Windows writer；不改变 public CLI
- **Test contract**: 直接针对 owner contract，无需 orchestrator
- **Gate**: S1 review 对照 §4/§5

**判定**: 范围正确。唯一风险是 R12-RR-01（`SceneToolCatalog`）会在 S2 才暴露——S1 不调用 `prepare_scene`，但 `init_catalog.py` 的 manifest projection helper 只做 model ID 替换，不涉及 tool catalog。

### S2 — Single-manifest workspace transaction + four-state orchestration

- **Allowed paths**: S1 全部 + 6 个文件（1 新 production + 2 修改 production + 1 新 test + 2 修改 test）
- **实现**: workspace transaction、四态编排、argparse 更新、删除旧 copier
- **Risk**: 旧 `test_init_command.py` (82 tests) 全部迁移；R12-RR-01（`SceneToolCatalog`）在此 slice 暴露
- **Gate**: Reviewer 必须逐状态和逐 fault point 审核

**判定**: 范围正确。R12-RR-01 应在 S2 开始前由 Controller 裁决。R12-RR-05（覆盖率可达性）应在 S2 review gate 明确。

### S3 — Non-network prewarm, real POSIX/Windows smoke, README, closeout

- **Allowed paths**: S1/S2 全部 + 5 个文件（1 新 test + 1 新 CI workflow + 3 README）
- **实现**: prewarm、真实 smoke、Windows CI、README、source scans
- **Risk**: R12-RR-02（竞争测试协调）、R12-RR-03（env allowlist）、R12-RR-04（config README trigger）
- **Gate**: Reviewer 同时检查 smoke、coverage、docs/scans 和 Windows workflow

**判定**: 范围正确。三个 finding 均为低-中严重度，不阻断 plan acceptance。

## 10. Rejected items remain absent

Fixed plan 和所有 review/control artifacts 均不含以下被 Controller 明确拒绝的内容：

- ❌ 清理 144 个历史 Ruff 诊断
- ❌ 固定 staging/backup 名称或 prefix 为 public protocol
- ❌ Finite magic lock timeout
- ❌ Host lock、process discovery、kill 或统一进程治理
- ❌ 为纯 typed/in-memory preparation result 发明 resource close/cache/FD framework
- ❌ 把 prewarm 前移到 staging 阶段
- ❌ 把 custom endpoint 自动补全 `/chat/completions` 后缀
- ❌ 兼容性 fallback/shim/旧名 re-export/loose parsing/`hasattr`/`getattr`

## 11. Residual risks

Plan §10.1 已披露的 risks 均准确。新增以下（已在 findings 中详述）：

| 新增 Residual | 严重度 | Owner | 跟踪 |
|---|---|---|---|
| Pre-publish `SceneToolCatalog` 构造未定 | 中 | R12 CLI | R12-RR-01 |
| S3 竞争 smoke 协调机制缺失 | 中 | R12 CLI | R12-RR-02 |
| Prewarm `env` allowlist 路径未指定 | 低 | R12 CLI | R12-RR-03 |
| `config/README.md` 更新 trigger 连接缺失 | 低 | R12 CLI | R12-RR-04 |
| S2 orchestrator 覆盖率在 smoke 前可达性 | 低 | R12 CLI | R12-RR-05 |

## 12. Finding ledger

| ID | Severity | Type | Status |
|---|---|---|---|
| R12-PF-01 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-02 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-03 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-04 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-05 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-06 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-07 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-08 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-09 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-10 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-11 | — | Controller-accepted fix | CLOSED ✓ |
| R12-PF-12 | — | Controller-accepted fix | CLOSED ✓ |
| R12-RR-01 | 中 | 契约缺失 | OPEN — pre-publish `SceneToolCatalog` |
| R12-RR-02 | 中 | 测试缺口 | OPEN — 竞争 smoke 协调 |
| R12-RR-03 | 低 | 契约缺失 | OPEN — prewarm env allowlist |
| R12-RR-04 | 低 | 范围漂移 | OPEN — config README trigger |
| R12-RR-05 | 低 | 测试缺口 | OPEN — S2 coverage reachability |

无严重 (CRITICAL/HIGH) 新 finding。无 design contradiction。无 blocking question。

## 13. Final re-review conclusion

**`PASS_WITH_FINDINGS`**

Fixed plan 在全部 12 个 Controller-accepted plan-fix groups 上实现了真正的 closure。架构边界、语义所有权、四态状态机、secret persistence、managed-root transaction/rollback、prewarm 零网络、Issue/Topic no-scope 边界均正确且具体。Rejected items 均未出现。三个 cumulative slices 的划分和 sequencing 合理，每个 slice 有明确的 allowed paths、tests、coverage、pyright/Ruff/diff 验证和 review gate。Ruff baseline fingerprint 机制可在 immutable base 上精确执行。

5 个新 finding 中：2 个中等严重度（R12-RR-01 `SceneToolCatalog` 构造规范缺失；R12-RR-02 竞争 smoke 协调机制缺失），应在 plan 中修复后才能安全交给 implementation agent；3 个低严重度（R12-RR-03 prewarm env、R12-RR-04 config README trigger、R12-RR-05 coverage reachability）建议修复但不阻断 plan acceptance。

Plan acceptance 前提：
1. R12-RR-01 和 R12-RR-02 应在 plan 中修复或由 Controller 明确裁决为 deferred implementation decision
2. R12-RR-03..05 建议修复

---

## 14. Artifact metadata

- **Review file**: `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-rereview-ds.md`
- **Reviewer**: AgentDS
- **Timestamp**: 20260718-071147
- **Immutable target unchanged**: ✓ (no modification to target, control, entry, production, tests, README)
- **No stage/commit**: ✓
- **Lines/bytes/SHA of this artifact**: 见机械度量（下附）
