# WU-SEMANTIC-OWNERSHIP-01 Remediation Plan Review — AgentMiMo

## 审查身份

- **角色**：第一路独立 plan review（AgentMiMo）
- **目标**：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`
- **证据范围**：`b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`；plan write HEAD `01bbf74c`
- **权威顺序**：AGENTS.md → `docs/host/issues-implementation-control.md` → `docs/phaseflow-umbrella-optimization-control.md` → `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` → `docs/host/design.md` → `docs/engine/design.md` → `docs/tool/design.md` → `docs/fins/design.md` → `docs/ui/design.md`
- **三路原始 review 定位**：仅代码证据，冲突时 controller discussion 胜出
- **输出边界**：仅本文件；不修改 plan/control/design/README/测试；不实现代码；不 commit/push/PR

## 审查方法

逐项核对 12 个审查维度；对计划中每个声明用直接代码/设计真源验证；每个 finding 包含稳定 ID、严重级别、直接证据、违反依据和最小修复。

---

## Findings

### MIMO-PF-01 — R12 reset 白名单缺少 assets 扩展性声明

- **严重级别**：HIGH（accepted-candidate）
- **位置**：plan §19.3 行 977、§4 行 95
- **证据**：
  - controller discussion Topic 7.3 明确要求："show `.dayu`, `config`, and product-present `assets` targets and require explicit confirmation, then delete those Dayu-owned/reconstructable roots"
  - 当前 `dayu/cli/commands/init.py:419-432` 的 `_reset_whitelist_paths` 返回 `(config_dir, host_dir, artifact_root, web_tools_storage_state_dir)`，无 `assets`
  - controller 同时说："The current repository has no `dayu/assets`; do not import unimplemented write/template product surface only to mimic an OLD directory. Issue #151 owns write and its required assets."
  - plan §19.3 行 977 只写 "`.dayu`与managed config"，未提及 `assets`
  - plan §4 行 95 正确标记 Issue 151 deferred，但 R12 正文未说明 reset 白名单必须在 assets 可用时扩展
- **违反依据**：controller discussion Topic 7.3 的 "product-present assets" 是 reset 语义的一部分；plan 不应静默省略
- **最小修复**：R12-S2 正文或 §19.3 补充一句：reset 白名单当前包含 `.dayu`（含 host/artifact/storage-state）和 `config`；当 Issue 151 交付 `assets` 目录后，白名单必须扩展以包含 product-present `assets`，同时 portfolio 永不删除

### MIMO-PF-02 — Windows .cmd quoting 未处理 `%VAR%` cmd.exe 展开

- **严重级别**：HIGH（accepted-candidate）
- **位置**：plan §18.2 行 873
- **证据**：
  - plan 写 "Windows：UTF-8/CRLF、`@echo off`、`chcp 65001 >nul`、使用 `subprocess.list2cmdline` 等价的cmd quoting"
  - `subprocess.list2cmdline` 遵循 MS C runtime `CommandLineToArgvW` 规则，对 `&|^()%!` 中的多数字符做双引号包裹
  - 但 cmd.exe 在双引号内仍展开 `%VAR%`：`python -c "print(subprocess.list2cmdline(['echo', '%PATH%']))"` 生成 `echo "%PATH%"`，cmd.exe 执行时 `%PATH%` 被展开
  - 若生成脚本的文件名或参数包含 `%`（如 `%20` URL encoding 或 `%TEMP%` 路径），cmd.exe 会尝试环境变量展开
  - `list2cmdline` 不做 `%` → `%%` 转义，因为它面向 `CreateProcess`/`CommandLineToArgvW`，不面向 cmd.exe 解释器
- **违反依据**：plan 承诺 "不得手写脆弱replace" 但未覆盖 cmd.exe 特有的 `%` 展开；这与 "跨平台 quoting 与 POSIX 实执行 smoke" 验收信号矛盾
- **最小修复**：R11-S2 实施说明中补充：Windows `.cmd` 脚本中，若参数包含 `%`，必须转义为 `%%`（cmd.exe 的 `%` escape 机制）；或在脚本中使用 `setlocal DisableDelayedExpansion` 并在每条命令前用 `set` 构建变量；或明确标注为已知 residual 并在 smoke 中用包含 `%` 的路径验证

### MIMO-PF-03 — R04-S2 WaitPollerRuntimePolicy 默认值来源未明确

- **严重级别**：MEDIUM（accepted-candidate）
- **位置**：plan §11.3 R04-S2 行 507-514
- **证据**：
  - plan 写 "删除 `WaitPollerRuntimePolicy()` 作为部署默认的调用点；unit tests 构造全部字段"
  - plan 写 "必须断言 packaged exact values、missing/unknown/wrong/NaN/nonpositive、disabled policy；source scan 不存在 Service/local hard-coded 30/5/8"
  - 当前 `dayu/host/wait_adapter.py:448-459` 使用模块级常量（`_POLL_CLAIM_TTL_SECONDS`、`_ADAPTER_CALL_TIMEOUT_SECONDS` 等）作为 dataclass 默认值
  - plan 未说明这些模块级常量应删除还是保留为代码级 fallback
  - 若保留常量，`WaitPollerRuntimePolicy()` 仍可构造出与 config 相同的默认值，未达成 "删除作为部署默认的调用点" 目标
  - 若删除常量，所有字段必须由 config 显式提供，dataclass 不再有无参构造
- **违反依据**：plan 的删除/保留边界不清晰；"source scan 不存在 Service/local hard-coded 30/5/8" 暗示应删除常量，但未显式说明
- **最小修复**：R04-S2 明确：删除 `WaitPollerRuntimePolicy` 的所有字段默认值，改为 `__init__` 中全部 required；或保留常量但删除无参构造 `WaitPollerRuntimePolicy()` 调用点，只允许 `WaitPollerRuntimePolicy(enabled=True, poll_interval_seconds=1, ...)` 显式构造

### MIMO-PF-04 — R03-S2 tool schema secret 参数无法迁移到 config 时的 fallback 未定义

- **严重级别**：MEDIUM（accepted-candidate）
- **位置**：plan §10.4 R03-S2 行 444-451
- **证据**：
  - plan 写 "若 source scan 找到真实 secret 参数，必须在该 tool schema/producer owner 删除或改成 config ref，而不是 Host blacklist"
  - plan 写 "若任一现有 tool schema确实要求 LLM 提交 credential 且无法在该 tool owner内迁移，立即 stop 并上报 owner"
  - 这是正确的 stop condition，但未说明 stop 后的处理路径
  - 若某个 tool schema 确实需要 LLM 提交一次性 token（如 OAuth code），且该 token 无法预置到 config，plan 应说明是：(a) 从 tool schema 删除该参数并改为 config/环境变量；(b) 保留参数但标记为 Host-sensitive 并在 projection 中脱敏；(c) 其它
  - 当前 source scan 结果（`rg -n 'api_key.*token.*secret.*password' dayu tests`）应作为 plan 的输入证据
- **违反依据**：stop condition 是正确的，但缺少 "stop 后怎么办" 的路径；implementation agent 遇到此情况时会卡住
- **最小修复**：R03-S2 补充：若 source scan 发现 tool schema 确实要求 LLM 提交 credential 且无法在该 tool owner 内迁移，stop 并上报；controller 将决定该参数是否从 tool schema 移除、改为 config ref、或作为特例保留并由 tool producer 自行脱敏

### MIMO-PF-05 — R12-S3 prewarm 对 overwrite 的行为描述含糊

- **严重级别**：LOW（accepted-candidate）
- **位置**：plan §19.4 R12-S3 行 1010
- **证据**：
  - plan 写 "unit test用spy证明无network，first/reset调用一次，ordinary/overwrite规则与design一致（overwrite不是first，不自动prewarm，除非controller design明确写入）"
  - controller discussion Topic 7.3 明确："first/reset only: non-network prewarm"
  - plan 的括号注释 "除非controller design明确写入" 引入不确定性；controller 已明确写了 "first/reset only"
  - 当前 `dayu/cli/commands/init.py` 无 prewarm 实现（只做 tree copy/swap），所以这是全新行为
- **违反依据**：controller 已裁决，plan 不应留 "除非" 余地
- **最小修复**：删除括号注释，改为明确："first/reset 成功发布后调用一次 prewarm；ordinary init 和 overwrite 不调用 prewarm"

### MIMO-PF-06 — R11-S2 POSIX smoke 用 fake dayu-cli 只测 argv roundtrip，非端到端

- **严重级别**：LOW（accepted-candidate）
- **位置**：plan §18.4 行 900-901
- **证据**：
  - plan 写 "POSIX执行生成脚本，PATH前置一个只记录argv的 fake `dayu-cli`，逐 entry与typed plan exact比对"
  - plan 的验收信号写 "smoke必须证明脚本实际argv可执行，不接受只比较字符串"
  - fake dayu-cli 只记录 argv 并返回成功，不执行真实 upload_filing/upload_material
  - 这验证了 argv quoting 和转发正确性，但不验证真实 CLI grammar 解析、Fins runtime 调用和文件上传行为
  - 真实端到端 smoke 需要实际的 `python -m dayu.cli upload_filing` 调用
- **违反依据**：plan 的验收信号说 "不接受只比较字符串"，但 fake dayu-cli 本质上是 argv 字符串比较的升级版
- **最小修复**：R11-S2 补充：fake dayu-cli smoke 是 argv quoting/forwarding 的必要验证；真实端到端 smoke（实际 `python -m dayu.cli upload_filing` 调用 Fins runtime）作为 R11 完成信号的补充，可在 aggregate smoke 中执行

### MIMO-PF-07 — R04-S2 "30/5/8" 模块常量与 config 数值的关系未明确

- **严重级别**：LOW（accepted-candidate）
- **位置**：plan §11.3 R04-S2 行 514
- **证据**：
  - plan 写 "source scan 不存在 Service/local hard-coded 30/5/8"
  - 当前 `dayu/host/wait_adapter.py` 使用模块级常量如 `_ADAPTER_CALL_TIMEOUT_SECONDS`、`_CLOSE_DRAIN_TIMEOUT_SECONDS`、`_MAX_OUTSTANDING_ADAPTER_CALLS`
  - 这些常量被 `WaitPollerRuntimePolicy` dataclass 默认值引用
  - plan 未说明这些常量是否应删除、保留为 config fallback、或保留为测试辅助
  - 若保留，source scan 会命中它们，但它们不是 "Service/local hard-coded"（它们在 Host 模块内）
- **违反依据**：plan 的 scan 命令可能产生误报；常量保留与否影响 dataclass 设计
- **最小修复**：与 MIMO-PF-03 合并处理；明确：这些常量在 config 提供显式值后删除，或保留为代码级常量但不作为部署默认

### MIMO-PF-08 — R06/R07/R08 允许文件列表已验证完整

- **严重级别**：NOTE（confirmed-correct）
- **位置**：plan §7.4
- **证据**：
  - R06 允许的 12 个 pipeline 文件全部存在
  - R07 允许的 storage 文件全部存在
  - R08 允许的 11 个 processor 文件和 5 个 tool 文件全部存在
  - R09 `direct_events.py` 存在；`direct_stream.py` 为新增文件（plan 正确标注）
  - R10 `hkexnews_downloader.py` 存在
  - R11 `upload_batch.py` 存在；`upload_script.py` 为新增
  - R12 `init_catalog.py`/`init_environment.py`/`init_workspace.py` 为新增
- **结论**：文件列表完整，无遗漏，新增文件正确标注

### MIMO-PF-09 — 安全 retained/modified 矩阵完整性验证

- **严重级别**：NOTE（confirmed-correct）
- **位置**：plan §21
- **证据**：
  - `allowed_paths`、containment/symlink → retained ✓
  - DNS/peer/resource budget → retained（peer proof default off）✓
  - atomic/process fencing → retained ✓
  - 未实现统一 authorization framework ✓
  - browser capability 独立于 private-network → modified ✓
  - storage-state lifecycle → deleted/deferred Issue 178 ✓
  - 与 controller discussion Topic 9 完全一致
- **结论**：安全矩阵完整，无误删、无越界

### MIMO-PF-10 — Topic 8/9 和 Issue 142/151/175/177/178 无越界验证

- **严重级别**：NOTE（confirmed-correct）
- **位置**：plan §3、§4
- **证据**：
  - Topic 8 "no code：保留 Engine 240 字符异常消息策略" ✓
  - Topic 9 "no code：不实现统一授权；保留现有局部权限与 I/O 防御" ✓
  - Issue 142/151 "deferred：workspace assets / 其它已跟踪迁移" ✓
  - Issue 175 "deferred：Fins 长事务进程隔离" ✓
  - Issue 177 "deferred：完整 TruncationManager 接通" ✓
  - Issue 178 "deferred：credential storage-state retention/refresh/concurrent publish/cleanup lifecycle" ✓
  - Web/WeChat/render tracker 不搬入本 WU ✓
- **结论**：无越界，deferred 标记正确

### MIMO-PF-11 — 12 个 sub-WU / 30 slices 切分合理性验证

- **严重级别**：NOTE（confirmed-correct）
- **位置**：plan §5
- **证据**：
  - 12 个 sub-WU，每个 ≤3 slices：R01(2) R02(3) R03(3) R04(3) R05(2) R06(3) R07(3) R08(2) R09(2) R10(1) R11(3) R12(3) = 30 slices
  - R03 合并 Topic 3/4 的理由成立：共享同一 accepted-evidence LLM projection 和四个 downstream consumers
  - R06 合并 batch authority 与 source publication 的理由成立：transaction commit point 必须和 complete source 可见点同时切换
  - R07 合并 revision/snapshot 与 opaque ID mapping 的理由成立：共同改变 storage path/read snapshot layout
  - 切分沿独立 durable state、public contract、真实入口或可独立回滚风险边界
- **结论**：切分合理，无过碎/过耦合/半成品

### MIMO-PF-12 — Sequencing 依赖图验证

- **严重级别**：NOTE（confirmed-correct）
- **位置**：plan §6
- **证据**：
  - config→composition→behavior：R04→R05 ✓
  - Fins transaction→complete publication→snapshot/read→domain/terminal/HKEX：R06→R07→R08/R09/R10 ✓
  - CLI upload/init：R11 依赖 R06，R12 依赖 R08/R09/R11 ✓
  - R01/R02/R03 无硬依赖，可并行 ✓
  - aggregate 在所有 sub-WU 之后 ✓
- **结论**：依赖图正确，无循环，无遗漏

### MIMO-PF-13 — R03 LLM-facing 修复回到 prompt/tool schema/producer owner 验证

- **严重级别**：NOTE（confirmed-correct）
- **位置**：plan §10
- **证据**：
  - plan 删除 `llm_safe_replay_arguments` 及字段黑名单/递归 sensitive-key taxonomy ✓
  - plan 删除 `_INTERNAL_SOURCE_REF_KINDS` 和 unknown `kind:id` rendering ✓
  - plan 不新建通用安全归一层、`BusinessSource` speculative type ✓
  - projection 优先使用显式 semantic query，否则使用 schema-owned canonical arguments ✓
  - opaque refs 仅 internal provenance，不进入 LLM material ✓
  - 与 controller discussion Topic 3/4 完全一致
- **结论**：R03 设计正确回到 owner，无新 normalization 层

### MIMO-PF-14 — 计划中新类型/常量/预算数值证据验证

- **严重级别**：NOTE（confirmed-correct）
- **位置**：plan 多处
- **证据**：
  - R02 resource budget 数值（128/256 MiB HTTP, 1 MiB/16/8 Mi browser, 8 Ki/512 diagnostics）有直接代码证据：当前 `web_resource_budget.py` 的旧默认值被显著放大，plan 明确说明是 "initial Tool-config safety ceilings"
  - R07 `_SOURCE_SNAPSHOT_MAX_ATTEMPTS = 3` 有设计依据："最小有界 concurrency retry"
  - R12 catalog 表格（15 个 provider/model pair）直接对照当前 `dayu/config/models.json` 和 OLD init
  - R12 scene manifest role 映射（non-thinking 8 个、thinking 8 个）有当前 manifest 文件直接证据
  - 无 speculative design 夹带
- **结论**：所有新类型、常量、预算数值和 catalog 条目都有设计或代码直接证据

### MIMO-PF-15 — 测试命令与验证闭合性验证

- **严重级别**：NOTE（confirmed-correct）
- **位置**：plan §7.5、各 sub-WU 正文
- **证据**：
  - 每个 slice 有精确 `pytest` 命令
  - 每个 slice 有 `coverage --include` 指向 changed production files
  - 每个 slice 有 mandatory source/propagation scan
  - 每个 slice 有 README decision
  - §22.1 aggregate regression 有完整命令集
  - §22.2 aggregate deepreview 覆盖所有维度
  - §22.3 PR gates 六项条件
  - §22.4 final closeout 验收矩阵12 个维度
- **结论**：验证闭合，无遗漏

---

## Verdict

**PASS（附 accepted-candidates）**

- 7 个 accepted-candidate findings（2 HIGH、3 MEDIUM、2 LOW）
- 8 个 confirmed-correct notes
- 0 个 blocking questions

## Findings 汇总

| ID | 级别 | 类型 | 摘要 |
| --- | --- | --- | --- |
| MIMO-PF-01 | HIGH | accepted-candidate | R12 reset 白名单缺少 assets 扩展性声明 |
| MIMO-PF-02 | HIGH | accepted-candidate | Windows .cmd quoting 未处理 `%VAR%` cmd.exe 展开 |
| MIMO-PF-03 | MEDIUM | accepted-candidate | R04-S2 WaitPollerRuntimePolicy 默认值来源未明确 |
| MIMO-PF-04 | MEDIUM | accepted-candidate | R03-S2 tool schema secret 参数 fallback 路径未定义 |
| MIMO-PF-05 | MEDIUM | accepted-candidate | R12-S3 prewarm 对 overwrite 行为描述含糊 |
| MIMO-PF-06 | LOW | accepted-candidate | R11-S2 POSIX smoke 只测 argv roundtrip 非端到端 |
| MIMO-PF-07 | LOW | accepted-candidate | R04-S2 模块常量与 config 数值关系未明确 |
| MIMO-PF-08 | NOTE | confirmed-correct | R06/R07/R08 允许文件列表完整 |
| MIMO-PF-09 | NOTE | confirmed-correct | 安全 retained/modified 矩阵完整 |
| MIMO-PF-10 | NOTE | confirmed-correct | Topic 8/9 和 Issue 无越界 |
| MIMO-PF-11 | NOTE | confirmed-correct | 12 sub-WU / 30 slices 切分合理 |
| MIMO-PF-12 | NOTE | confirmed-correct | Sequencing 依赖图正确 |
| MIMO-PF-13 | NOTE | confirmed-correct | R03 LLM-facing 修复回到 owner |
| MIMO-PF-14 | NOTE | confirmed-correct | 新类型/常量/预算数值有直接证据 |
| MIMO-PF-15 | NOTE | confirmed-correct | 测试命令与验证闭合 |

## Blocking Questions

无。所有 accepted-candidate findings 均可在 plan fix 阶段以文档补充解决，不阻塞 implementation 启动。

## 建议 Plan Fix 优先级

1. **MIMO-PF-01 + MIMO-PF-05**（R12）：一行补充 assets 扩展性 + 删除 prewarm 括号注释
2. **MIMO-PF-02**（R11）：补充 `%` escaping 或标注 residual
3. **MIMO-PF-03 + MIMO-PF-07**（R04）：明确常量删除/保留策略
4. **MIMO-PF-04**（R03）：补充 stop 后处理路径
5. **MIMO-PF-06**（R11）：补充端到端 smoke 归属

---

*Review completed by AgentMiMo. Artifact only; no code, control, design, README, or test modifications.*
