# WU-SEMANTIC-OWNERSHIP-01 / R11 independent plan adversarial review — AgentDS

## Review metadata

- **reviewer**: AgentDS (second independent plan review)
- **immutable target**: `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- **target lock**: 711 lines / SHA-256 `c2c5700561cf8ad48f774aba79d792e775d7419de821efda4162f3d7411038d5`
- **review posture**: constructively adversarial; default to skepticism
- **authority order**: AGENTS.md > design truth docs > Controller discussion Topic 7 > umbrella plan > umbrella optimization control > CURRENT code evidence
- **timestamp**: 2026-07-17T21:37:32+08:00
- **baseline**: `phaseflow/host-issues-control` HEAD `2b14b2fbc89654267e3d33daa2ae410ceff45e68`, staged tree empty

## Scope of this review

This review covers all 10 sections of the R11 plan artifact: motivation (§1), authority/source locks (§2), goal/success/non-goals (§3), semantic owner map (§4), three slices (§5–§7), cumulative validation (§8), review state machine (§9), and plan acceptance checklist (§10).

Each finding is classified as **material finding** (must fix before implementation), **question** (needs Controller clarification), or **rejected/no-action observation** (raised, examined, found insufficient evidence).

## Documents consulted

| Document | Lines | Role |
|---|---|---|
| Target plan | 711 | Immutable review target |
| AGENTS.md | 128 | Authority #1 |
| Controller control doc (R11 sections) | 2244 | Current gate state |
| Umbrella optimization control | 302 | Slice/review constraints |
| Controller discussion Topic 7 | §7.1–7.3 | Adjudicated product decisions |
| Fins design §10 | 123 | Upload batch plan owner |
| UI design §1–2 | 111 | Entrypoint lifecycle + upload_filings_from |
| CURRENT `dayu/fins/upload_batch.py` | 376 | Direct code evidence |
| CURRENT `dayu/cli/commands/fins.py` | 1057 | Direct code evidence |
| CURRENT `dayu/cli/arg_parsing.py` | 932 | Direct code evidence |
| CURRENT `pyproject.toml` | 152 | Placeholder surface evidence |
| CURRENT `requirements.txt` | 12 | Placeholder dependency evidence |
| CURRENT `dayu/fins/ticker_normalization.py` | ~133 | Ticker normalization owner |
| CURRENT `dayu/fins/resolver/fmp_company_info.py` | ~98 | FMP resolver contract |
| CURRENT placeholder package files (6 files) | ~30 each | Deletion target evidence |
| CURRENT `tests/cli/test_public_package_entrypoints.py` | 217 | Placeholder test surface |
| R11 plan entry Controller validation | 58 | Authorized scope |
| R11 plan Controller validation | 116 | Pre-review PASS verdict |

## Assumptions tested

1. Fins typed plan interface is complete enough for CLI renderer consumption without retroactive S1 changes.
2. A single batch file escape strategy can cover all of `%`, `!`, `&`, `|`, `^`, `(`, `)`, quotes, backslashes, Unicode, empty args, and appended args simultaneously.
3. `%*` or an owner algorithm can correctly pass through caller-appended args in real `cmd.exe`.
4. Three strict-sequential slices with no backward feedback are safe given the Fins→CLI interface is fully specified.
5. "One FMP resolve call" unambiguously bounds total FMP API access.
6. Workspace root symlink rejection at every ancestor level is universally safe.
7. `python -m pip wheel --no-build-isolation` works with `.venv`'s current state.
8. The Ruff baseline delta approach survives Ruff version changes between plan-lock and implementation.
9. OLD classification rules are fully and unambiguously specifiable in §5.2.
10. placeholder deletion scope correctly distinguishes `dayu.web` (placeholder package) from `dayu.tools.web` (real web-browsing tools).

---

## Material Findings

### DS-F01-未修复-高-Windows renderer 未达到 code-generation-ready 状态

- **位置**: §6.5 "Windows outcome、invariants 与 evidence-driven algorithm gate"
- **问题类型**: 不可直接实施
- **当前写法**: Plan 明确声明 "具体 quote/escape 算法不在无 Windows evidence 的 plan 中臆定"，要求 S2 实现顺序为 "先把上述 adversarial matrix 写成 renderer unit + real-recorder oracle；再在唯一 renderer 内实现一个候选算法；任何反例即修改同一算法并重跑，直到真实 cmd.exe 通过后才锁定。"
- **反例/失败场景**: Implementation Agent 在没有具体算法指导的情况下，可能：
  1. 选择 `^`-escape 所有 metacharacters 的 naive 方案，然后发现 `^` 在引号内外的行为不一致；
  2. 先实现 `%*` 方案，发现 appended args 中的 `%` 在 cmd-level 已被展开，无法恢复；
  3. 在 `%%`（percent doubling）与 `%*` 之间产生交互失败——`%%` 在 batch 文件中变成 `%`，但如果 appended arg 也有 `%`，`%*` 展开后的字符可能被二次解析；
  4. 尝试用 `%1 %2 %3 ... %9` 代替 `%*` 但遇到超过 9 个 args 的退化场景。
- **为什么有问题**: Plan 对这一高风险点的态度正确（不臆定算法、要求真实 evidence），但其交付物边界不满足 "code-generation-ready" 的最低要求：Implementation Agent 需要自行完成算法设计、对抗测试、反例驱动迭代——这本质上是 plan-level work 被推迟到了 implementation phase。根据 umbrella optimization control，production-high 风险的变更必须完成 plan review 后才能进入 implementation；而 Windows quoting 是整个 S2 的核心交付物，其算法仍在 plan 中被标记为 TBD。
- **直接证据**:
  - Plan §6.5: "具体 quote/escape 算法不在无 Windows evidence 的 plan 中臆定"
  - Plan §6.5: "S2 实现顺序必须是：先把上述 adversarial matrix 写成 renderer unit + real-recorder oracle；再在唯一 renderer 内实现一个候选算法"
  - Umbrella optimization control "High Risk" 要求: "plan → plan review → fix/re-review → per-slice implementation"——plan 必须在 implementation 前完成设计
  - cmd.exe 批处理已知约束：`%` 在 batch body 中必须双写 `%%`；`%*` 是内置参数展开语法；这两者在同一条命令中的交互取决于 cmd.exe 解析器实现细节，不同 Windows 版本行为可能不同
- **影响**: Implementation Agent 可能花费大量 token/time 在算法发现上；若选错初始方案，需要多轮反例迭代才收敛；最坏情况下，agent 可能接受 "看起来通过" 的算法但漏掉边缘 cmd.exe 版本差异
- **建议改法和验证点**:
  1. Plan 至少应给出一个 **候选算法家族**（如 "使用 `%%` doubling + `^` escaping + 逐参数 `%1..%N` explicit referencing" vs "使用 `%*` + 延迟展开关闭 + 引号包裹"）并说明各自的已知失效模式；
  2. 明确 S2 implementation 的前 N 步是算法发现而非直接编码，并给出算法发现的收敛判据（如"所有 adversarial matrix case 连续三次 run 无新增反例"）；
  3. 在 plan 中注明：若 implementation agent 在 N 次迭代后仍未找到收敛算法，应 stop 并回到 Controller 裁决，而不是继续尝试变体算法。
- **修复风险**: 低——只需补充指导性内容，不改变 plan 的 owner boundary、allowlist 或 success signals
- **严重程度**: 高——若算法不可行，整个 S2 Windows 交付物不存在；且这是硬 release blocker

### DS-F02-未修复-高-严格顺序 slice 禁止 S2→S1 反馈回路

- **位置**: §9.1 "Slice state machine"
- **问题类型**: 切片过粗 / 架构边界
- **当前写法**: "严格顺序最多三个 slices：R11-S1 -> R11-S2 -> R11-S3。... 任一 source drift、stop condition、checkpoint failure 或 blocker 均禁止下一 slice。"§5.1 定义的 typed models 是 S1 产出，§6.2 定义的 argv builder 是 S2 消费者。
- **反例/失败场景**: S2 的 `upload_script.py` renderer 作为 S1 typed plan 的第一个真实消费者，在消费 `UploadBatchFilingEntry` / `UploadBatchMaterialEntry` / `UploadBatchSkippedEntry` 时，可能发现：
  1. S1 的 `UploadBatchSkippedEntry` 缺少 CLI summary 渲染需要的 path display format（绝对/相对路径）；
  2. S1 的 `UploadBatchMaterialEntry.form_type` 枚举值与 `--forms` flag 的 argparse `choices` 不完全匹配（如 OLD 表中的 `EARNINGS_CALL` vs `EARNINGS CALL` 空格差异）；
  3. S1 的 `fiscal_period` 值（如中文"一季度"）在 argv 中需要额外 quoting 而 S2 renderer 未预期。
  这些 interface gaps 发现时 S1 已经 "checkpoint passed"，Plan §9.1 不允许回溯修改 S1。
- **为什么有问题**: 按照 umbrella optimization control 的 slice 切分约束，"是否有不同 semantic owner?" 和 "是否有不同 failure blast radius?" 都成立，拆分是正确的。但 plan 缺少 S1 contract 的 **freeze-before-S2 验证步骤**——S1 checkpoint pass 只能证明 S1 自身逻辑正确，不能证明其 typed contract 对 S2 consumer 是完备的。在 "先设计 contract 再实现两个 owner" 的正常开发流程中，contract 是在两者之前冻结的；但 plan 的 S1→S2 顺序等同于 "先实现 producer，再让 consumer 发现 contract gap"。
- **直接证据**:
  - Plan §9.1: "任一 source drift、stop condition、checkpoint failure 或 blocker 均禁止下一 slice"
  - Plan §5.1: typed models 定义在 S1；§6.2: argv builder 在 S2 消费这些 models
  - CURRENT code evidence: `UploadBatchPlanEntry` 是单一 flat type，而 plan 将其拆为 `UploadBatchFilingEntry`/`UploadBatchMaterialEntry`/`UploadBatchSkippedEntry` 三个独立类型——这是首次消费方验证此拆分的正确性
- **影响**: 若 interface gap 在 S2 被发现，必须要么 (a) 在 S2 中做 adapter/fallback 补救（违反 semantic ownership），要么 (b) Controller 破例允许回到 S1（违反 plan state machine），要么 (c) stop 整个 R11（过度反应）。三种结果都不理想
- **建议改法和验证点**:
  1. 在 S1 checkpoint 和 S2 开始之间插入一个轻量 contract-validation gate：CLI reviewer（或 Controller）用 S1 的 typed models 手工验证能否无歧义地构造 S2 所有 argv variant；
  2. 或在 S2 的 stop conditions 中加入明确条款："若 S2 发现 S1 contract 不足以无歧义生成 argv，S2 可以以 typed finding 形式要求 S1 contract fix，Controller 裁决后允许 S1 targeted fix 并重跑 S1+S2 cumulative validation"；
  3. 至少应在 S1 §5.1 typed models 定义之后，附加一段 "S2 consumer contract validation checklist" 列出每个 typed field 到 `--flag` 的映射，供 S1 checkpoint 时预验证。
- **修复风险**: 低——增加一个 contract 验证步骤，不改变 slice allowlist 或 owner boundary
- **严重程度**: 高——可能导致 S2 实现偏轨或被迫引入语义所有权违规的补救代码

### DS-F03-未修复-中-"one FMP resolve call" 语义歧义

- **位置**: §6.2 item 4
- **问题类型**: 契约缺失
- **当前写法**: "传入时 CLI 从 `FMP_API_KEY` 显式读取，缺失立即失败；创建当前 `FmpCompanyInfoResolver` 并只调用一次 `resolve_company_info(canonical)`。这里"一次解析"是一次 resolver 调用，不臆测其内部 HTTP hop 数。"
- **反例/失败场景**: `FmpCompanyInfoResolver.resolve_company_info()` 内部可能发起多次 HTTP 请求（如重试、分页、多 endpoint 聚合），但 plan 将其计为 "一次调用"。若 `--infer` 的用户期望是 "一次 FMP API 访问"，而实际触发了 5 次 HTTP round-trip（重试 + search + profile endpoints），则 plan 声称的 "zero/once FMP access" 约束在 HTTP/计费层面被违反。
- **为什么有问题**: Plan 在 §3.2 success signal 5 承诺 "`--infer` 最多调用一次当前 FMP resolver"，但定义 "一次" 的边界是 Python 方法调用次数而非网络访问次数。这是一个 contract 歧义：若当前 `FmpCompanyInfoResolver` 恰好只发一次 HTTP 请求，plan 就碰巧正确；若未来 resolver 内部增加额外 endpoint 调用，plan 声称的不变量静默失效。按照语义所有权原则，CLI 不拥有 FMP resolver 的内部实现，因此 CLI-level plan 只能约束它可见的边界（Python call count 或 FMP API key exposure），不能约束 resolver 内部行为。
- **直接证据**:
  - Plan §6.2 item 4: "这里'一次解析'是一次 resolver 调用，不臆测其内部 HTTP hop 数"
  - Plan §3.2 success signal 5: "`--infer` 最多调用一次当前 FMP resolver"
  - CURRENT `FmpCompanyInfoResolver`: 是一个类，`resolve_company_info` 是其方法；其 HTTP 行为不在 plan 控制范围内
- **影响**: 若 resolver 未来增加 HTTP 调用，用户可能观察到意外的 API 使用量；但这不是 plan 层面的 bug——plan 已经诚实地声明了约束边界。风险在于：Controller/aggregate review 可能将此 "once" 理解为网络层面约束，导致后续 gate 误判
- **建议改法和验证点**:
  1. 将 success signal 5 的措辞从 "最多调用一次当前 FMP resolver" 改为 "最多创建并使用一个 `FmpCompanyInfoResolver` 实例，且只调用其 `resolve_company_info(canonical)` 一次；对 HTTP/网络调用次数不做 guarantee"；
  2. 在 §6.2 item 4 末尾补充："本 plan 不约束 resolver 内部的 HTTP hop 数、重试策略或多 endpoint 聚合；这些由其自身 owner 控制。"
- **修复风险**: 极低——措辞澄清
- **严重程度**: 中——不修复不会导致实现偏轨，但可能在 aggregate review 中引起无谓争论

### DS-F04-未修复-中-工作区根路径 symlink 拒绝过于宽泛

- **位置**: §6.3 "workspace/output 任一级 symlink 均拒绝"
- **问题类型**: 过度设计 / 最佳实践偏离
- **当前写法**: "output directory 必须 resolved contained in workspace root；workspace/output 任一级 symlink 均拒绝。"
- **反例/失败场景**: macOS 上 `/tmp` 是 `/private/tmp` 的 symlink。若用户的工作区根为 `/tmp/dayu-workspace`（通过 `--base /tmp/dayu-workspace`），publisher 的 containment check 会发现 `/tmp` 自身是 symlink，于是拒绝写入，即使 `/tmp/dayu-workspace/output/` 在工作区内部且安全。类似场景在 Linux 上也存在（某些挂载点在 `/run` symlink 下）。
- **为什么有问题**: Plan 的 symlink 拒绝策略是正确的安全措施，但 "任一级" 过于宽泛——用户工作区路径中任何祖先目录的 symlink 都会触发拒绝。这会把 OS 级别的合法文件系统布局变成用户可见的失败，且用户无法修复（不能改变 `/tmp -> /private/tmp` 的 OS 设计）。按照 AGENTS.md 的最佳实践优先原则，"优先选择可维护、可测试、可演进的方案"——这里应该只拒绝工作区自身是 symlink 或工作区内部路径含 symlink，而非拒绝工作区解析路径上的所有祖先 symlink。
- **直接证据**:
  - Plan §6.3: "workspace/output 任一级 symlink 均拒绝"
  - macOS 事实：`/tmp` → `/private/tmp`（系统级 symlink）
  - AGENTS.md: "最佳实践优先：优先选择可维护、可测试、可演进的方案，不走捷径，不做表面修复"
- **影响**: macOS 用户使用 `/tmp` 作为工作区时无法生成上传脚本；错误消息可能令人困惑（"workspace root is a symlink" 但实际上用户并未创建任何 symlink）
- **建议改法和验证点**:
  1. 将 "任一级 symlink 均拒绝" 细化为："workspace root 自身为 symlink 时拒绝；output directory 在 workspace root 内部的任何路径组件为 symlink 时拒绝；但 workspace root 的祖先目录可以是 OS 级合法 symlink（如 `/tmp -> /private/tmp`），只要 resolved workspace root 在 resolved contain 范围内"；
  2. 或至少将祖先 symlink 拒绝的检测范围限定为 "workspace root 不是 symlink 且 output directory 的路径组件中不包含 symlink"；
  3. 测试必须覆盖祖先 symlink 的合法通过场景与工作区内部 symlink 的正确拒绝场景。
- **修复风险**: 低——缩小拒绝范围至 workspace boundary 以下，不影响安全语义
- **严重程度**: 中——不修复会导致 macOS `/tmp` 用户无法使用，属于可避免的可用性退化

### DS-F05-未修复-中-`--overwrite` 语义在 batch 生成与逐文件上传间未区分

- **位置**: §5.2 item 11 + §6.2 item 6
- **问题类型**: 契约缺失
- **当前写法**: §5.2.11: "explicit ... overwrite 原样传播到每个真实拥有这些 current upload 字段的 entry"。§6.2.6: "upload_filings_from grammar 必须显式加入 --overwrite"。
- **反例/失败场景**: 当前 `upload_filings_from` 命令（arg_parsing.py line 781-805）没有 `--overwrite` flag。Plan 要求新增它。但这里存在两种不同的 `--overwrite` 语义：
  1. **batch-level overwrite**（生成时）：是否覆盖已存在的输出脚本文件；
  2. **per-file overwrite**（执行时）：每条 `upload_filing`/`upload_material` 命令的 `--overwrite` flag，控制是否覆盖已有 source document。
  Plan §5.2.11 明确说的是后者（传播到每个 entry），但 §6.2.6 只说 "加入 --overwrite" 而未区分这两种语义。在当前的 `_upload_batch_command_argv` 实现中没有 `--overwrite` flag 的处理逻辑，需要新增。
- **为什么有问题**: 如果 implementation agent 把唯一的 `--overwrite` 实现为 publisher 的 overwrite（覆盖输出脚本），则不会传播到每个 entry 的 upload command；如果实现为 entry 的 `--overwrite` 传播，则缺少 publisher 的 overwrite 控制。两个语义需要两个独立的 flag 或一个 flag 的双重语义清晰说明。
- **直接证据**:
  - CURRENT `arg_parsing.py:781-805`: `_register_upload_filings_from_command` 没有 `--overwrite`
  - CURRENT `commands/fins.py:275-313`: `_run_upload_filings_from` 没有 overwrite 参数传入 `UploadBatchPlanRequest`
  - CURRENT `UploadBatchPlanRequest` (upload_batch.py:58-86): 没有 `overwrite` 字段
  - Plan §5.2.11: "overwrite 原样传播到每个...entry"
  - Plan §6.2.6: "upload_filings_from grammar 必须显式加入 --overwrite"
- **影响**: Implementation agent 可能漏实现其中一种语义；若两种语义被混淆，生成的脚本可能静默覆盖用户已有文件或漏传 overwrite 到逐条命令
- **建议改法和验证点**:
  1. 在 §6.2.6 明确说明 `--overwrite` 的双重语义：(a) 作为 batch request 字段传播到每个 entry 的 `--overwrite` flag；(b) 不与 publisher 的输出文件 overwrite 行为混淆（publisher 始终使用 atomic replace，不依赖用户 flag）；
  2. 或拆分为两个独立参数：`--overwrite`（传播到逐条命令）和 `--force-output`（覆盖已有脚本文件），若 plan 认为 publisher atomic replace 已经天然处理了输出覆盖则明确说明；
  3. 在 S1 typed model 中确认 `UploadBatchPlanRequest.overwrite` 字段存在且正确传播。
- **修复风险**: 低——语义澄清
- **严重程度**: 中——可能导致实现遗漏或语义混淆

### DS-F06-未修复-中-wheel scan 未覆盖 RECORD、top_level.txt 与间接依赖残留

- **位置**: §7.3
- **问题类型**: 测试缺口
- **当前写法**: wheel scan 使用 `rg` 检查 `METADATA`（`Provides-Extra: web` / Streamlit requirement）和 `entry_points.txt`（placeholder entrypoints），并验证 archive 中零 `dayu/web`、`dayu/wechat`、`dayu/render`。
- **反例/失败场景**:
  1. wheel 的 `RECORD` 文件列出所有安装文件。如果 placeholder 的 `__pycache__` 残留、`.pyc` 编译产物或 package 目录意外进入 wheel（例如 setuptools 的 `package-data` 配置没有被完全清理），`RECORD` 中会出现 `dayu/web/__pycache__/` 或类似路径，而 plan 的 scan 不会检测到。
  2. `top_level.txt` 记录包的顶层模块名。如果删除 placeholder packages 后但 `top_level.txt` 仍包含 `dayu`（这本身是合法的——`dayu` 仍是 top-level），这不是问题；但如果 setuptools 为每个 package 生成了独立的 top-level 条目，清理不完整可能残留。
  3. wheel 的 `METADATA` scan 只检查 `Provides-Extra: web` 和 `Requires-Dist: Streamlit`，但若 web extra 被删除后某个被保留的 extra（如 `browser`）间接依赖了 Streamlit（通过 transitive dependency），Streamlit 仍可能出现在 `Requires-Dist` 中——这不是 placeholder 残留而是合法依赖。
- **为什么有问题**: Plan 的 wheel 验证在 `METADATA` 和 `entry_points.txt` 层面是正确的，但 `RECORD` 提供了逐文件粒度的事实，是更精确的 "wheel 内容" 真源。只在 archive 层面 `find` 可以覆盖，但 plan 漏掉了显式 `RECORD` 断言。`top_level.txt` 同理。
- **直接证据**:
  - Plan §7.3: `rg` commands 只覆盖 `METADATA` 和 `entry_points.txt`
  - Plan §7.3: "archive 中必须零 dayu/web、dayu/wechat、dayu/render"——这个 scan 使用 `python -m zipfile -e` 提取后做文件系统 find，是更全面的
  - 实际上 plan 的 archive-level find 已经覆盖了 RECORD 等价物——但未显式断言 RECORD 与 archive 内容的一致性
- **影响**: 低——archive-level find 已提供等价保护；但缺少显式 RECORD 断言意味着 metadata 层面的残留可能不被发现
- **建议改法和验证点**:
  1. 在 §7.3 wheel scan 中加入：`rg -n 'dayu/(web|wechat|render)/' workspace/tmp/r11-wheel-extract/*.dist-info/RECORD`（期望 exit 1）；
  2. 或在已有 archive find 的基础上增加一条：若 RECORD 中存在但 archive 中缺失的文件被检测到，单独报告；
  3. 最低限度：在 scan 说明中注明 "archive-level find 等效覆盖 RECORD，不单独做 RECORD 逐行 diff"。
- **修复风险**: 极低——增加一条 rg 命令
- **严重程度**: 中——虽 archive find 已提供大部分保护，但显式 RECORD check 是 defense-in-depth

---

## Questions for Controller

### DS-Q01-未修复-无严重程度-跨平台脚本生成未定义

- **位置**: §6.3 "POSIX UTF-8/LF；Windows UTF-8/CRLF"
- **当前写法**: Plan 始终以 "当前平台" 视角描述脚本生成（POSIX `.sh` 或 Windows `.cmd`，由 "实际 OS 决定"）。
- **问题**: 未定义的情景：macOS 用户能否生成为 Windows 部署的 `.cmd` 脚本？或反之？Plan §6.3 说 "平台内容、编码与换行由实际 OS 决定"——这是指生成脚本的平台还是目标执行平台？如果是生成平台，则跨平台生成不被支持（macOS 只能生成 `.sh`，不能生成 `.cmd`）。如果是目标平台，则需要一个 `--platform` 参数。
- **影响**: 若用户需要在 macOS 上为远程 Windows 服务器生成脚本，当前 plan 不支持。但这不是 OLD 行为的一部分（OLD 也在本地生成对应平台脚本），且 plan 的 scope 中没有提及跨平台生成需求。
- **建议**: Controller 确认 R11 scope 是否仅限 "本地生成、本地执行"，还是需要跨平台生成能力。若仅限本地，可在 plan 中明确：`## 6.2.x 跨平台生成：脚本格式由生成平台决定，不支持为其他平台交叉生成。`

### DS-Q02-未修复-无严重程度-Material routing 零 filings 时 call cap = 0 是否正确

- **位置**: §5.2 item 10
- **当前写法**: "`EARNINGS_CALL` cap 等于过滤后的 recognized filing 数量"
- **问题**: 若某源目录只包含 material 文件（如 Earnings Call transcript + Presentation）但没有任何 filing 文件，则 recognized filing 数量为 0，call cap = 0，意味着所有 Earnings Call material entry 都被裁剪。这是 OLD 的预期行为吗？还是应该至少保留 1-2 个 call entries？当前 plan 缺少对这种边缘情况的处理说明。
- **影响**: 如果 OLD 在实际使用中不会遇到 pure-material 目录（因为通常用户会同时放入 filing 和 material），这可能不是实际问题；但 plan 应记录这个设计决策。
- **建议**: 确认 OLD 对此场景的行为，或在 plan 中记录 "当 recognized filing 为零时，Earnings Call material cap=0，所有 call entries 进入 skipped"。

### DS-Q03-未修复-无严重程度-Ruff baseline 跨版本一致性

- **位置**: §8.1
- **当前写法**: "Controller 在 accepted-plan parent 上预先锁定的 `workspace/tmp/r11-ruff-baseline.json`"
- **问题**: 如果 Controller 在 plan acceptance 时锁定的 Ruff 版本与 implementation agent 运行时的 Ruff 版本不同，baseline 中的规则集合可能不匹配（新增规则、规则重命名、规则移除）。Plan 的 set difference 逻辑可能在版本不一致时产生假阳性。
- **影响**: 如果 `.venv` 中的 Ruff 版本在 plan acceptance 到 implementation 之间未变化，则无问题。Plan 可加一条预检：`python -m ruff --version` 输出与 baseline 锁定时一致。
- **建议**: 在 baseline lock 时同时记录 `ruff --version` 输出，在 implementation validation 的第一步做版本一致性检查。

---

## Rejected / No-Action Observations

### DS-R01-rejected-已检无问题-`FmpCompanyInfoResolver` 不在 CLI 的 import surface

- **检查内容**: Plan §4 语义 owner map 将 "FMP response parse/normalize" owner 放在既有 `FmpCompanyInfoResolver`，CLI 只调用一次。验证当前 CLI commands 是否已经 import 了 resolver。
- **直接证据**: `grep -n "FmpCompanyInfo\|FMP.*Resolver\|fmp_company_info" dayu/cli/commands/fins.py` → 零命中。CLI 当前不 import resolver。
- **结论**: Plan 引入 `FmpCompanyInfoResolver` 依赖到 CLI 是新增的，但这是 plan 明确授权的（§4 closed allowlist 允许修改 `dayu/cli/commands/fins.py`，§6.2 item 4 明确授权创建 resolver）。不属于 scope creep。**No action.**

### DS-R02-rejected-已检无问题-`normalize_ticker` 返回 market/exchange 字段但不被 batch 使用

- **检查内容**: Plan §5.1 的 `UploadBatchPlanRequest` 只有 `canonical` ticker 和 `aliases`，没有 market/exchange 字段。而 `normalize_ticker` 返回的 `NormalizedTicker` 包含 `canonical`、`market`、`exchange`。验证 plan 是否缺失了 market 信息的传播。
- **直接证据**: CURRENT `upload_filing` Service 的 `ticker` 参数只接受 canonical ticker 字符串；market/exchange 由 Fins domain 内部自行推导。Plan 的 batch request 不需要传播 market/exchange 因为它们不是 upload command 的公共参数。
- **结论**: Plan 正确。Market/exchange 是 Fins domain 内部事实，不是 CLI grammar 的一部分。**No action.**

### DS-R03-rejected-已检无问题-plan 对 `--document-id`/`--internal-document-id` 的处理

- **检查内容**: Plan §6.2 item 1 说 "batch entry 没有后两项 [document-id/internal-document-id]，生成脚本不得臆造"。验证 batch material entries 是否确实不需要这些 ID。
- **直接证据**: CURRENT `_upload_material_stream` (commands/fins.py:490-524) 接受 `document_id` 和 `internal_document_id`，但它们都是 Optional。Material 上传可以没有这些 ID（新上传时）。Plan 的 batch material entry 是首次上传，不应携带已有 document ID。
- **结论**: Plan 正确。Batch 生成的是新上传命令，不应有 document ID。**No action.**

### DS-R04-rejected-已检无问题-两个 `"dayu.web"` sentinel 保留

- **检查内容**: Plan §4 和 §8.3 保留 `tests/tools/web/test_web_tools_provider.py` 和 `tests/tools/web/test_diagnose_web_access.py` 中的 `"dayu.web"` import 负向 sentinel。验证这些是真实 Web tools 测试还是 placeholder 残留。
- **直接证据**: `tests/tools/web/` 测试的是 `dayu.tools.web`（Doc 的 web browsing 工具），不是被删除的 `dayu.web`（Web UI placeholder）。这些测试中的 `"dayu.web"` 字符串是用来断言 "旧 import 路径不再可用"，是负向 boundary 测试。
- **结论**: Plan 正确保留了这些 sentinels。但需注意 implementation agent 可能混淆 `dayu.web`（placeholder）和 `dayu.tools.web`（真实工具）。Plan 的 scan 已经区分了这两者（§8.3 的 placeholder scan 使用精确路径限定）。**No action.**

### DS-R05-rejected-已检无问题-`constraints/lock` 的 Streamlit/watchdog pin 保留

- **检查内容**: Plan §2.4 说 "constraints 只限制'若 dependency graph 选择该依赖时的版本'，不会自行安装，也不发布 script/package。" 验证保留 inert pins 是否安全。
- **直接证据**: `constraints/` 目录中的 lock 文件只在 `pip install -c` 时生效。删除 `pyproject.toml` 的 `web` extra 与 `requirements.txt` 的 `[web]` 后，Streamlit 不会进入 dependency graph，因此其 pin 成为 inert——不会触发安装，也不会影响 wheel metadata。保留 pin 是安全的（它只是声明 "如果将来有人重新引入 Streamlit，用这个版本"）。
- **结论**: Plan 正确。No-touch 是正确策略——删除 inert pin 会引入不必要的变更。**No action.**

### DS-R06-rejected-已检无问题-plan 不依赖 push/PR、统一 auth 或 deferred issues

- **检查内容**: 验证 plan 是否偷偷依赖 push/PR（通过 GitHub Actions workflow 的 PR trigger）、统一 authorization framework、或 deferred issues (142/151/175/177/178) 的实现。
- **直接证据**:
  - Workflow §7.2 使用 `workflow_dispatch` + `pull_request.paths` triggers。这些 trigger 在 workflow 文件入库时即可被 GitHub 识别，不需要额外 auth。Workflow 在 PR 到 `main` 时触发是标准 GitHub Actions 行为。Plan 明确说 "本地 branch 未发布前无法得到 GitHub-hosted run"——Windows gate 可以在缺少 GitHub run 时标记为 `PENDING_RELEASE_BLOCKER`。这不等于依赖 push/PR。
  - Plan §3.3 明确 deferred list：Issue 142/151/175/177/178、R12、真实 Web/WeChat/render、Topic 8/9、统一 auth。
  - Plan §8.3 deferred diff scan 验证这些 deferred 范围的 production diff 为零。
  - Plan §5.2 的 OLD 分类规则是自足的，不依赖 FMP resolver（FMP 只在 CLI 的 `--infer` 阶段用于 ticker→company 查找，不参与文件分类）。
- **结论**: Plan 的依赖边界清晰。Windows workflow 的 PR trigger 是在已有 PR 流程中的标准行为，不构成 hidden dependency。**No action.**

### DS-R07-rejected-已检无问题-`python -m pip wheel` 在 `.venv` 中的可行性

- **检查内容**: Plan §7.3 使用 `python -m pip wheel --no-deps --no-build-isolation` 构建 wheel。验证这个命令在项目的 setuptools 配置下是否需要额外的 build frontend。
- **直接证据**: `pyproject.toml` 的 `[build-system]` 声明 `requires = ["setuptools>=68", "wheel"]`。`python -m pip wheel --no-build-isolation` 使用当前环境中已安装的 setuptools 和 wheel 来构建，不创建隔离环境。如果 `.venv` 中没有 `setuptools>=68` 和 `wheel`，命令会失败。
- **结论**: Plan 需要确保 `.venv` 中已有 build 依赖。这在标准开发环境中通常满足（`pip install -e .[test,dev]` 会安装 setuptools）。但如果 `.venv` 是最小安装，需要先确认。不属于 plan 缺陷，但值得在 implementation 前做一次 build dependency check。**No action.**

---

## Residual risks

| Risk | Severity | Destination |
|---|---|---|
| Windows cmd.exe quoting algorithm 可能不存在同时满足所有 adversarial matrix 的单一代数方案 | 高 | R11-S2 implementation phase；若 agent 无法收敛则 escalate 到 Controller |
| S1/S2 contract gap 发现后的修复流程未定义 | 中 | R11-S1 checkpoint 或 Controller contract-validation gate |
| FMP API 访问次数定义歧义 | 低 | §6.2 item 4 措辞澄清即可解决 |
| macOS `/tmp` symlink 可用性问题 | 中 | §6.3 containment 规则细化 |
| `--overwrite` 双重语义混淆 | 中 | §5.2/§6.2 措辞澄清 |
| Wheel RECORD 残留检测缺失 | 低 | §7.3 scan 补充 |
| Ruff 版本漂移导致 baseline delta 假阳性 | 低 | Baseline 锁定同时记录 Ruff version |
| 跨平台脚本生成需求 | 低 | Controller 确认 scope 边界 |

---

## Final plan review conclusion

**Verdict: PASS-WITH-FINDINGS**

本 plan 的 owner boundary 划分正确、三 slice 依赖顺序合理、安全边界（containment/symlink/atomic/secret）完整、deferred no-touch 边界清晰、validation/scans/coverage gates 详尽可执行。六个 material findings 中：

- **DS-F01**（Windows renderer 非 code-generation-ready）是唯一可能上升为 blocker 的 finding：若 cmd.exe 下不存在同时满足所有 adversarial matrix 约束的单一代数方案，S2 的核心交付物无法完成。Plan 的证据驱动算法发现策略是正确的，但需要更具体的失败处理预案。
- **DS-F02**（S2→S1 feedback 缺失）是高概率在实际实现中会遇到的结构性问题，建议在 S1 checkpoint 处增加 contract validation gate。
- **DS-F03–F06** 是中等风险的 contract 歧义、可用性边界和 scan 覆盖问题，均可通过措辞澄清或增加 scan 命令解决，不改变 plan 核心设计。
- **DS-Q01–Q03** 是三个待 Controller 确认的边界问题。它们不阻止 plan 推进，但答案会影响 implementation 细节。
- **DS-R01–R07** 是已检查并排除的怀疑点，无 action required。

本 review 不授权 implementation。Plan 修复后需要 Controller adjudication 和（若 Controller 要求）双路 re-review。

## Controller adjudication entrypoint

- **当前 gate**: R11 plan review — AgentDS complete
- **next gate**: AgentMiMo plan review 完成后，Controller 对两份 review 的 findings 做 adjudication
- **accepted findings 数量**: 0（adjudication 前）
- **blocker**: 0（DS-F01 是高严重度 but 不是 blocker——plan 的算法发现策略是合理路径，但需要更具体指导）
- **README 更新**: 不适用（plan review artifact 不触发 README 更新）
- **修改文件**: 仅本 artifact，不改 plan/control/code/tests/README/design/CI
- **staged tree**: 不适用（无 stage 操作）

READY_FOR_CONTROLLER_ADJUDICATION
