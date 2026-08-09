# WU-CLI-CONFORMANCE-F01-F07 Plan Review（DeepSeek）

## Review 元数据

- **Reviewed target**: `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
- **Plan Gate 状态**: `COMPLETE — code-generation-ready`
- **Review 类型**: Adversarial plan review（planreview skill）
- **Review 方**: DeepSeek（独立，不替代后续 MiMo review gate）
- **编制日期**: 2026-08-02T17:45:53+08:00（Asia/Shanghai）
- **冻结真源**: `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` readiness_proof、`docs/cli_ci.md`、`docs/host/design.md`、`docs/engine/design.md`、两份 immutable evidence report
- **Review 边界**: 只读 plan + 真源 + 代码事实；不编辑 plan、生产代码、测试、registry、PR 190

---

## 0. Assumptions Tested

| # | Plan assumption | Verified against | Result |
|---|---|---|---|
| A1 | `--config` grammar 只在 CLI 层拥有，删除后下游不补偿 | `arg_parsing.py:163,530-536`、`agent_entrypoint.py:25,201`、`entrypoint_runtime.py:439,449` | **成立** — 删除 owner + 输入校验层即可闭环 |
| A2 | `context_compaction_completed` 是 stale trigger identifier，无外部冻结 consumer | `run_input.py:338`、`_runner_call_manifest.py:157`、`engine/` 零命中 | **成立** — Engine 不消费该值 |
| A3 | prompt_toolkit 公共 `Vt100Parser` 可用于 prompt one-shot ESC 序列分类 | `run_keys.py` 当前使用 `os.read(fd, 1)` + 线程模型 | **部分成立** — Vt100Parser 可用但现有架构不兼容，见 Finding B1 |
| A4 | `_ActiveTurnCloseout` 接口足以支撑 S4 attachment/pending mutation 协调 | `session_execution.py:145,170` 现有 `_PromptAcceptedRunState`/`_InteractiveAcceptedRunState` | **未验证** — plan 未枚举 S4 所需的 barrier 接口 |
| A5 | interactive manifest tag 删除即完成 effective tool set 变更，下游不补偿 | `interactive.json` `tool_tags_any` 含 `fins-preprocess` | **成立** — manifest 是 scene 工具集唯一 owner |
| A6 | S7 fresh schema 可与现有 Memory policy 共用同一 `MemoryProjectionPolicy` instance | `docs/host/design.md:99` 定义 policy 字段 | **成立** — policy 已存在 typed instance |
| A7 | 两个 dirty registry 在 Plan Gate 的 SHA-256 基线在全部 S1-S8 保持字节不变 | plan §0.1 + §13.1-13.2 staging 规则 | **可验证但未解决最终提交** — 见 Finding B2 |
| A8 | `host_assembly.py` 不受 S1 `explicit_config_dir` 删除影响 | `host_assembly.py` 不从 `entrypoint_runtime.py`/`host_admin.py` import | **成立** — 无直接 import 依赖 |

---

## 1. Findings

### B1-未修复-严重-S3 prompt one-shot Vt100Parser 与现有线程模型不兼容

- **位置**: §5.2 "prompt one-shot raw input 使用 prompt_toolkit 公共 Vt100Parser 做增量分类"
- **问题类型**: 不可直接实施
- **当前写法**:
  > "以 chunk 读取、增量 UTF-8 decode，feed parser；仅当 parser 产出的 KeyPress 同时满足 key is Keys.Escape 且原始 data == '\x1b' 时发 CANCEL。ESC 后在短暂 ambiguity window 内有后续字节则继续解析；只有 timeout 后 flush() 得到 standalone Escape。"
- **反例/失败场景**:
  当前 `dayu/cli/run_keys.py` 使用后台线程 `os.read(fd, 1)` + `asyncio.Queue` 投递单字节动作（见 `run_keys.py:218-244`）。`Vt100Parser` 是 prompt_toolkit 内部异步增量 parser，设计用于 async feed 模式。plan 没有说明如何桥接这两种模型：
  - 线程内 feed parser：`Vt100Parser` 的 `feed()` 和 `flush()` 方法不是线程安全的；
  - 异步 feed parser：需要把 `os.read` 移入 event loop，与现有 `TtyRunningKeyMonitor` 的线程架构冲突；
  - timeout 机制：plan 说“timeout 使用命名常量”，但 `Vt100Parser` 的 ambiguity timeout 由 prompt_toolkit 内部控制，Dayu 侧不能独立设置。
- **为什么有问题**: plan 描述的方案在现有 `run_keys.py` 架构下无法直接落地，implementation agent 会被迫在两种架构之间重新设计，plan 不再是 code-generation-ready。
- **直接证据**:
  - `dayu/cli/run_keys.py:218-244` — `_read_loop` 在 daemon 线程中 `os.read(fd, 1)` 逐字节读取
  - `dayu/cli/run_keys.py:261-273` — `running_key_action_from_bytes` 把任何 `b'\x1b'` 映射为 `CANCEL_RUN`
  - plan §5.2 没有提及 `run_keys.py` 现有线程架构如何迁移到 Vt100Parser 模型
  - `Vt100Parser` 可用性确认（`python -c "from prompt_toolkit.input.vt100 import Vt100Parser"` 成功），但其设计目标是 async input processor，不是 threaded key monitor
- **影响**: 实施 Agent 必须重新设计 prompt one-shot 的输入架构，且可能发现 Vt100Parser 不适合非 prompt_toolkit 上下文，导致 S3 返工或引入新的竞态条件。S3 的 `_PromptControlKey`、`_ActiveTurnCloseout` 等 typed state 设计依赖正确的输入分类；若 parser bridge 不可靠，所有 cancel/escape 不变量都无法成立。
- **建议改法和验证点**:
  1. plan 必须明确回答：是用 threading + Vt100Parser（需验证线程安全性），还是用 async `os.read` + Vt100Parser（需重构 `TtyRunningKeyMonitor`），还是用其它 parser？
  2. 或者：承认 Vt100Parser 不适合 prompt one-shot 路径，改用更简单的 byte-level state machine（例如检测 `\x1b` 后 N ms 内是否有后续字节，有则继续累积），这可以用现有线程模型实现。
  3. 无论哪种方案，必须在 plan 中写清 parser bridge 的 typed interface、超时常量、flush 语义和与 `_ActiveTurnCloseout` 的对接方式。
- **修复风险**: 中 — 需要重新审视架构选择，但 typed state 设计（`_LocalCancelIntent`、`_ActiveTurnCloseout`）不依赖 parser 实现细节
- **严重程度**: 严重（blocking — plan 在此点不满足 code-generation-ready 条件）

---

### B2-未修复-严重-两个 dirty registry 的最终 PR 190 纳入方案缺失

- **位置**: §0.1、§13.1、§13.2
- **问题类型**: open question 未收敛
- **当前写法**:
  > "任何后续 slice 都不得编辑、reset、overwrite、rebuild 或 stage 它们"
  > "两个 dirty registry始终保留在worktree，既不stash/reset也不stage"
  > "每次stage前后运行 `git diff --cached --name-only`；若出现 `docs/cli_ci_oracles.json` 或 `docs/cli_ci_scenarios.json`，立即停止"
- **反例/失败场景**:
  用户明确要求 review "eventual required inclusion of the two pre-existing dirty registry baselines in PR 190"。这两个 registry 是 WU-CLI-CONFORMANCE-F01-F07 的 frozen oracle/scenario 真源，PR 190 作为 interactive conformance 的修复 PR，最终必须包含这些 registry 才能被下游 CI 消费。但 plan 的 §13.1-13.2 禁止在 S1-S8 中 stage 它们，并且没有说明它们在 PR 190 中的最终 disposition：
  - 是否在 S8 closeout commit 中单独 stage？
  - 是否作为独立 commit 在 S8 之后追加？
  - 是否留在 worktree dirty 由后续 PR 处理？
  - 若不能 stage，PR 190 的 closeout 标准是什么？
- **为什么有问题**: plan 把两个 registry 定义为"不可变的 frozen baseline"，却没有定义它们从 worktree dirty 状态进入 committed PR 的合法路径。S1-S8 的显式 allowlist staging 规则阻止任何 slice 误 stage 它们，这是正确的保护措施；但保护措施不能替代 disposition 决策。
- **直接证据**:
  - plan §0.1 表格定义 SHA-256 基线并标记"字节不可变"
  - plan §13.1: "两个 dirty registry始终保留在worktree，既不stash/reset也不stage"
  - plan §13.2: staged set 中出现 registry 文件时"立即停止"
  - 用户 prompt 明确要求 review "eventual required inclusion of the two pre-existing dirty registry baselines in PR 190"
  - `git status` 确认两个 registry 文件处于 modified 状态（见会话初始 git status）
- **影响**: 若 implementation agent 在 S8 closeout 时不知如何处理这两个文件，可能导致：(a) PR 190 合入后缺少必要的 CI oracle/scenario registry；(b) 错误地在某个 slice 中 stage 它们；(c) 永久保留为 dirty worktree 状态导致后续 work unit 的基线不明确。
- **建议改法和验证点**:
  1. plan 增加明确的 registry disposition 决策：在 S8 closeout commit 中，作为独立 staged set（不混入任何 S1-S7 生产代码变更）commit 两个 registry，并记录其 Plan Gate 基线 SHA-256 与 commit 时的 SHA-256 相同。
  2. 或者：若 registry 应留在后续 work unit 处理，明确写出 PR 190 可以 closeout without them 的理由。
  3. 验证：S8 closeout 前 `shasum -a 256 docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` 与 §0.1 基线一致。
- **修复风险**: 低 — 这是一个流程/commit 边界决策，不改变任何 slice 的实现语义
- **严重程度**: 严重（blocking — 影响 PR 190 的 closeout 判定和 CI 消费能力）

---

### B3-未修复-高-S2 prompt_toolkit adapter seam 规格不足以指导实现

- **位置**: §4.2 特别是 `_PromptToolkitExternalEditorAdapter.open(buffer, explicit_command)`
- **问题类型**: 不可直接实施
- **当前写法**:
  > "若当前 prompt_toolkit public seam 不能表达'保留其 tempfile lifecycle 且显式只启动一次'，实现必须使用一个局部、版本锁定并有 contract test 的 adapter seam"
- **反例/失败场景**:
  plan 没有指定：
  - 当前 prompt_toolkit 的锁定版本是什么（`pip freeze` 中 `prompt_toolkit` 的具体版本）
  - `Buffer.open_in_editor(validate_and_handle=False)` 的 public seam 是否已经满足"保留 tempfile lifecycle 且显式只启动一次"——如果满足，不需要 adapter seam；如果不满足，plan 应该明确 seam 是什么
  - contract test 的最小断言集：应该覆盖 tempfile 创建/回填/清理、explicit command 单次启动、非零返回、进程异常
  - adapter 需要访问 prompt_toolkit 的哪些内部 API（`Buffer._editing_buffer`? `run_in_terminal`? `create_tempfile`?）
- **为什么有问题**: plan 在关键实现决策点使用"如果...则..."条件句，把 seam 可行性判断推给 implementation agent。但 plan 声称是 code-generation-ready，应该在 Plan Gate 完成这个判断。
- **直接证据**:
  - plan §4.2: "若当前 prompt_toolkit public seam 不能表达...实现必须使用一个局部、版本锁定并有 contract test 的 adapter seam"
  - plan §4.5: Residual risk MEDIUM，"原因是第三方 editor lifecycle 的 async/seam 行为"
  - plan §14.2: "当前锁定prompt_toolkit seam若不能同时满足...S2停止并提交dependency证据"
  - 没有找到 plan 中对当前 prompt_toolkit 版本的记录或 seam 分析
- **影响**: implementation agent 可能花费大量时间在 adapter seam 发现上，甚至发现无法实现而触发 S2 stop——但 plan 本应在 Plan Gate 完成 seam 可行性分析。中等概率导致 S2 返工或 scope 扩大。
- **建议改法和验证点**:
  1. plan 补充当前 prompt_toolkit 版本号（从 `requirements.txt` 或 `pip freeze` 获取）。
  2. plan 补充对 `Buffer.open_in_editor` 的 seam 分析：能否在保持其 tempfile 生命周期不变的前提下，替换 editor command 选择逻辑？
  3. 若 seam 成立，写出 adapter 的 typed contract（输入 `_ExplicitEditorCommand | None`、输出 `_ExternalEditorTask`）及与 prompt_toolkit `run_in_terminal` 的对接方式。
  4. 若 seam 不成立，plan 应降级 S2 范围或给出替代方案（例如接受 prompt_toolkit 的系统 fallback 行为但增加配置错误前置检查），而不是让 implementation agent 在 gate 中触发 stop。
- **修复风险**: 中 — 需要阅读 prompt_toolkit 源码确认 seam
- **严重程度**: 高

---

### B4-未修复-中-S3 替换 `_PromptAcceptedRunState`/`_InteractiveAcceptedRunState` 的现有消费者未枚举

- **位置**: §5.2 "替换 `_PromptAcceptedRunState`/`_InteractiveAcceptedRunState` 中分裂的 barrier 行为"
- **问题类型**: 切片过粗 / open question 未收敛
- **当前写法**:
  > "旧类型可以被统一类型完全替代，不保留 wrapper"
- **反例/失败场景**:
  `session_execution.py:916` 创建 `_PromptAcceptedRunState()` 并在 `_cancel_prompt_turn_after_local_request` 中使用（见 `session_execution.py:1019`）。`session_execution.py:1657,1707` 创建 `_InteractiveAcceptedRunState()` 并在多个位置使用（见 `session_execution.py:1736`）。plan 没有枚举这些现有消费者的完整列表和它们对 barrier 的依赖方式。
- **为什么有问题**: 若 `_ActiveTurnCloseout` 的接口与现有消费者的使用模式不完全匹配，implementation agent 可能需要扩大 S3 的修改范围（超出 allowlist）或引入兼容 shim。plan 应该先枚举现有消费者，再证明 `_ActiveTurnCloseout` 的接口可以覆盖所有现有用法。
- **直接证据**:
  - `dayu/cli/session_execution.py:145-168` — `_PromptAcceptedRunState` 定义
  - `dayu/cli/session_execution.py:170-233` — `_InteractiveAcceptedRunState` 定义
  - `dayu/cli/session_execution.py:916,1019,1657,1707,1736` — 创建和使用点
  - plan §5.2 只声明替换，未枚举消费者
- **影响**: 中等概率导致 S3 实现时发现需要修改 allowlist 外的调用方，或 `_ActiveTurnCloseout` 接口需要多次调整
- **建议改法和验证点**:
  1. plan 增加现有消费者枚举表：位置、使用的 barrier 字段/方法、替换后如何映射到 `_ActiveTurnCloseout`
  2. 验证 `_ActiveTurnCloseout` 的 `request_cancel`、`on_run_accepted`、`wait_closeout` 三个方法覆盖现有所有 cancel/submit/barrier 交互
- **修复风险**: 低 — 只是文档补充，不影响 typed contract 设计
- **严重程度**: 中

---

### B5-未修复-中-S7 32 文件原子 commit 缺乏实现阶段风险缓解策略

- **位置**: §9.1 "S7 可以按 9.2–9.8 的内部顺序编码，但不得拆成可合并的 outer slice"
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**:
  > "只有全部 owner tests 和投影一致性通过后，S7 才整体完成"
- **反例/失败场景**:
  S7 的 allowed files 包含 16 个生产文件 + 16 个测试文件 = 32 个文件，预计变更量在 2000-4000 行。一次原子 commit 意味着：
  - 任何一个文件的 pyright 错误阻塞整个 S7
  - 任何一个测试失败阻塞整个 S7
  - 不能在 commit 之间做增量验证
  - review surface 过大，MiMo/DS review gate 难以逐项判断

  虽然 plan 正确识别了"不得提交中间 schema"的不变量，但没有提供实施阶段的缓解策略。
- **为什么有问题**: plan 的 residual risk 标记为 HIGH 是诚实的，但没有把识别到的风险转化为 implementation 指导。对于声称 code-generation-ready 的 plan，应该给出如何在一个工作会话中安全完成 32 文件原子变更的策略。
- **直接证据**:
  - plan §9.1 允许修改 16 个生产文件 + 16 个测试文件
  - plan §9.1: "不得拆成可合并的 outer slice、不得提交中间 schema、不得让下游先兼容旧/新两套 contract"
  - plan §14.1: "F07 fresh schema影响面大 | HIGH"
- **影响**: implementation agent 可能在 S7 中途被大量失败阻塞，需要多次回到 plan 重新设计。但不改变 S7 的原子性需求。
- **建议改法和验证点**:
  1. plan 增加实施顺序建议：例如先完成 §9.2-9.3（fresh schema types），在独立分支上验证类型定义自洽；再完成 §9.4（strict JSON boundary）；再完成 §9.5（validation issues）；最后完成 §9.6-9.7（attempt/accept/terminal/projection）。
  2. 建议在原子 commit 前使用 `git stash` + focused test 做增量验证，但不形成中间 commit。
  3. 明确 S7 implementation 的预计 wall-clock 时间和建议的 checkpoint 策略（例如每完成一个子节就运行 focused tests）。
- **修复风险**: 低 — 只是增加 implementation guidance
- **严重程度**: 中

---

### B6-未修复-低-`dayu/service/` 文件修改未触发 service README 更新

- **位置**: §10.1 "`dayu/service/README.md`：**不更新**，其稳定 Service assembly/entrypoint owner说明未改变；CLI 字段删除不构成新的 Service职责"
- **问题类型**: 契约缺失
- **当前写法**: plan 认为 S1 从 `EntrypointRuntimeRequest` 删除 `explicit_config_dir`、从 `ServiceHostAdminRequest` 删除 `config_overlay_dir` "不构成新的 Service 职责"，因此不更新 `dayu/service/README.md`。
- **反例/失败场景**:
  虽然 `AGENTS.md` 的 README 触发列表中没有 `dayu/service/` 条目，但 S1 确实修改了 Service 层的 public typed request dataclass。如果 `dayu/service/README.md` 记录了 `EntrypointRuntimeRequest` 或 `ServiceHostAdminRequest` 的字段，删除 `explicit_config_dir`/`config_overlay_dir` 应该触发更新。
- **为什么有问题**: plan 依赖 `AGENTS.md` 的 README 触发规则做机械判定，但没有先检查 `dayu/service/README.md` 的实际内容是否记录了被修改的 request 类型。
- **直接证据**:
  - plan §3.2 明确删除 `EntrypointRuntimeRequest.explicit_config_dir` 和 `ServiceHostAdminRequest.config_overlay_dir`
  - plan §10.1 判定 `dayu/service/README.md` 不更新
  - `AGENTS.md:110-116` README 触发列表没有 `dayu/service/` 条目
- **影响**: 低 — 即使 service README 未同步，也不影响代码正确性
- **建议改法和验证点**: plan 补充一句："已确认 `dayu/service/README.md` 未记录 `EntrypointRuntimeRequest` 或 `ServiceHostAdminRequest` 的具体字段，因此删除字段不触发更新。" 或改为有条件更新。
- **修复风险**: 低
- **严重程度**: 低

---

### B7-未修复-低-plan 声称 code-generation-ready 但 §14.2 保留了三个 implementation-time stop check

- **位置**: §14.2 "开放问题"
- **问题类型**: open question 未收敛
- **当前写法**:
  > "当前没有阻塞产品语义的开放问题。以下只是 implementation-time stop checks"
- **反例/失败场景**:
  三个 stop check 中：
  1. prompt_toolkit seam 可行性——如果在 S2 实现时触发 stop，意味着 plan 在 Plan Gate 应该已经判断 seam 是否可用。这与 code-generation-ready 的声称有矛盾。
  2. provider credentials 不可用——这是 operational risk，合理。
  3. Memory policy cap 真源不一致——如果触发，意味着 plan 的假设（"caps 直接接收现有 MemoryProjectionPolicy typed instance"）可能不成立。
- **为什么有问题**: 第 1 和第 3 个 stop check 应该在 Plan Gate 通过代码阅读解决，而不是留给 implementation agent 在 gate 中触发 stop。
- **直接证据**: plan §14.2 三条 stop check
- **影响**: 低 — S2 的 seam 问题已由 B3 覆盖
- **建议改法和验证点**: 将第 1 条 stop check 提升为 B3 的修复项；将第 3 条改为"S7 实现开始前先运行现有 memory policy tests 确认 cap 真源一致性"，而不是运行时 stop。
- **修复风险**: 低
- **严重程度**: 低

---

## 2. Architecture Boundary 审查

逐层验证语义 owner（§2.3 表格）：

| 语义 | 计划 owner | 真源验证 | 结论 |
|---|---|---|---|
| CLI option/action/help | `dayu.cli.arg_parsing` | `arg_parsing.py:530-536` 注册 `--config`，`arg_parsing.py:290-314` 二次拒绝 | **正确** — 删除 owner 即可闭环 |
| workspace config location | `dayu.runtime` location contract → Service assembly | `entrypoint_runtime.py:893-894` 用 `ConfigLoader` 解析 | **正确** — CLI 不再提供覆盖 |
| editor selection/error | CLI composer | `composer.py` 拥有 Ctrl+X Ctrl+E binding | **正确** — Host/Service 不参与 |
| key sequence 分类 | prompt: `run_keys` / interactive: `composer` prompt_toolkit binding | `run_keys.py:261-273` 逐字节映射；`composer.py:429` 用 prompt_toolkit `escape` binding | **正确** — 但 prompt 侧 parser 方案需修复（B1） |
| Run acceptance/cancel | Host public API → CLI acceptance barrier 观察 | `session_execution.py:145,170` 现有 barrier 类型 | **正确** — CLI 只观察，不推断 |
| attachment access mode | Host attachment contract | `docs/host/design.md:13` 单写者约束 | **正确** — CLI fresh attach 不提升 mode |
| scene effective tool set | config scene manifest + Service assembly | `interactive.json` `tool_tags_any` | **正确** — manifest 是唯一配置 owner |
| compaction trigger | Host typed RunInput/manifest | `run_input.py:338`、`_runner_call_manifest.py:157` | **正确** — Engine 不消费 |
| compact candidate validity | Host Context Governance accept barrier | `docs/host/design.md:3688-3695` 定义 semantic retry/repair 归 Host | **正确** — parser/operation/artifact/Memory 不复算 |
| compact terminal | Host terminal commit guard | `docs/host/design.md:3771-3790` 每 operation 一个 canonical terminal | **正确** — late attempt 只形成 diagnostic |

**Architecture boundary 结论**: 没有发现语义 owner 漂移或跨层穿透。plan 的 owner 分配与代码事实、设计真源一致。

---

## 3. Overcoupling 审查

| 潜在耦合 | 审查结论 |
|---|---|
| S1 同时修改 CLI arg_parsing + Service request | **合理** — `explicit_config_dir` 从 request 删除是删除 `--config` 的直接下游，属于同一语义闭环 |
| S3 `_ActiveTurnCloseout` 同时服务 prompt + interactive | **正确** — plan 明确要求二者共用同一 barrier，消除当前 `_PromptAcceptedRunState`/`_InteractiveAcceptedRunState` 的分裂 |
| S4 依赖 S3 的 `_ActiveTurnCloseout` | **正确** — plan §2.4 明确"不得在 S4 再建第二套 submit state machine" |
| S7 的 accepted truth 派生到 Memory/RunInput/artifact/trace | **正确** — 这是单一真源派生多投影，不是耦合；plan 明确各投影从同一 `CompactAcceptedTruthV2` 读取 |
| S6 先于 S7 | **正确** — S7 的 trigger 依赖 S6 的新值，是正常依赖顺序 |

**Overcoupling 结论**: 未发现过度耦合。

---

## 4. Goal Drift / Scope Creep 审查

逐 slice 验证 in-scope（§2.1）vs 实际变更范围：

| Slice | 声称 scope | 实际变更是否超出？ | 结论 |
|---|---|---|---|
| S1 | 删除 `--config` grammar/action/help/parsing/forwarding | 删除 `EntrypointRuntimeRequest.explicit_config_dir` 和 `ServiceHostAdminRequest.config_overlay_dir` — 这是 `--config` 的下游消费者 | **范围内** |
| S2 | 显式 editor 失败处理与 unset fallback | 仅 CLI composer owner | **范围内** |
| S3 | Escape/Ctrl+C 跨 acceptance barrier | 增加 `Vt100Parser` 用于 prompt one-shot — 这是实现手段，不是新目标 | **范围内** |
| S4 | READ_ONLY 保留 REPL + fresh attach | 仅 CLI coordinator + Host owner test | **范围内** |
| S5 | 从 interactive effective tool set 移除 preprocess | 仅 manifest tag 删除 | **范围内** |
| S6 | typed trigger 重命名 | 精确 rename + design doc 同步 | **范围内** |
| S7 | Host Context Governance 原子 closure | v2 schema/governance/projection — 在 F07 evidence 确定的修复范围内 | **范围内** |
| S8 | integration/evidence/docs | 仅 README + repo 外 evidence | **范围内** |

**Goal drift 结论**: 未发现目标漂移。plan 没有将 implementation 中发现的潜在风险升级为新目标或架构强化。

---

## 5. Non-goals 遵守审查

逐项验证 §2.2 非目标：

| 非目标 | S1-S8 是否违反？ | 证据 |
|---|---|---|
| 不修改冻结 oracle/scenario/`docs/cli_ci.md` | **遵守** — 所有 slice 的 registry check 都验证 SHA-256 | §11.1 每 slice 共通检查 |
| 不迁移旧 compact schema/DB | **遵守** — S7 明确"v1 parser/alias/compat branch 全部删除" | §9.2 |
| 不把 Host 取消/attachment/compact 下放到 CLI/Service/Engine | **遵守** — owner 表格正确分配 | §2.3 |
| 不改变 ordinary Agent/Engine terminal outcome 枚举 | **遵守** — §9.6 复用既有 terminal commit guard | §9.6 |
| 不重写 prompt_toolkit 通用编辑器/终端 parser/History | **遵守** — S2 只做 adapter | §4.2 |
| 不改变 Fins preprocess 独立命令/工具实现/存储协议 | **遵守** — S5 明确不修改 `dayu/fins/tools/preprocess_tools.py` | §7.1 |
| 不用 LLM 做自然语言事实真伪证明 | **遵守** — §9.4 明确 contradiction 只判 schema 可证明冲突 | §9.4 |
| 不顺手清理归档/无关 README/无关 pyright debt | **遵守** — 仅在 S8 更新被触发的 README | §10.1 |

**Non-goals 结论**: 未发现违反非目标。

---

## 6. 测试覆盖审查

| Slice | 测试策略 | 覆盖 worst-case / 反例？ | 结论 |
|---|---|---|---|
| S1 | parser inventory + unknown option + Service request 构造 | 覆盖了 root/command/action 三种 parser + 前后位置参数化 `--config` | **充分** |
| S2 | 参数化 VISUAL/EDITOR/unset、nonexistent/nonexec/launch fail、teardown | 覆盖了 invalid/launch/nonzero/unset 四类路径 | **充分** |
| S3 | raw byte→typed key 表、pre-accept/double Ctrl+C 三阶段、同 batch 竞态 | 覆盖了 CSI/Home/Delete/Alt/bracketed paste 反例 | **充分** |
| S4 | 双 attachment owner test + CLI 状态测试 | 覆盖了 READ_ONLY 拒绝→fresh attach→accepted→closeout 全路径 | **充分** |
| S5 | 真实 manifest + Service assembly | 覆盖了 interactive effective set 不含 preprocess + 独立 preprocess 仍可用 | **充分** |
| S6 | success/fallback RunInput + manifest parse/round-trip + terminal identity 对照 | 覆盖了旧值拒绝 | **充分** |
| S7 | strict JSON/coverage/caps/repair/materialization/exhaust/rolling/public smoke 九类 | 覆盖了全空/diagnostics-only/all-drop/超 cap/duplicate key/repair success/exhaust fallback | **充分** |
| S8 | 真实 CLI integration + cross-layer evidence | 按 F01-F07 逐一真实断言 | **充分** |

**测试覆盖结论**: 每个 slice 的 owner-level tests 覆盖了反例和关键竞态，符合 planreview 对测试的要求。

---

## 7. Open Questions

| # | 问题 | 严重性 | 建议处置 |
|---|---|---|---|
| Q1 | prompt_toolkit 当前版本是什么？`Buffer.open_in_editor` 的 seam 是否支持替换 editor command？ | 高 | 与 B3 一并解决 |
| Q2 | `_ActiveTurnCloseout` 的三个方法（`request_cancel`、`on_run_accepted`、`wait_closeout`）是否覆盖 `_PromptAcceptedRunState` 和 `_InteractiveAcceptedRunState` 的所有现有消费者？ | 中 | 与 B4 一并解决 |
| Q3 | `MemoryProjectionPolicy` 的 typed instance 在 S7 开始前是否已经只有一个 cap 真源（没有两个不一致的估算器）？ | 中 | S7 实现前运行现有 memory policy tests 确认 |
| Q4 | 若 Mimo 在 S8 真实 evidence 阶段持续无法产出合法 v2 candidate（如 compaction audit 报告的连续 5 次 label 错误），在 Mimo-first 规则下，是用 DeepSeek fallback 完成 evidence，还是将 Mimo failure 本身作为 valid evidence？ | 低 | plan §12.2 已有规则（Mimo 失败原样保留，DeepSeek 作为新 bundle），但需要确认 S8 时间预算是否允许两个 provider 的完整 evidence |

---

## 8. Residual Risks

| 风险 | 等级 | plan 已有收敛 | review 补充 |
|---|---|---|---|
| prompt_toolkit 显式 editor seam | MEDIUM | 版本锁定 adapter contract + 真实 PTY 测试 | B3 建议在 Plan Gate 完成 seam 分析 |
| ESC ambiguity + SIGINT/terminal 同 batch 竞态 | MEDIUM | Vt100Parser chunk matrix + 确定性 scheduler + PTY evidence | B1 指出 parser bridge 未解决 |
| READ_ONLY 后 writer 退出时 fresh attach 竞争 | MEDIUM | Host public typed mode + close-before-open + stable pending identity | 收敛充分 |
| F07 fresh schema 影响面大 | HIGH | S7 原子边界 + strict parser + shared policy + projection identity | B5 建议增加实施顺序和 checkpoint 策略 |
| LLM 自然语言低质量但形式合法 | MEDIUM/ACCEPTED | deterministic 最低信息+coverage | 收敛充分 |
| Mimo/DeepSeek/网络环境不可用 | MEDIUM/OPERATIONAL | Mimo-first + 明确 fallback + 新 bundle | 收敛充分 |
| dirty registry 误 stage/覆盖 | HIGH/CONTROLLED | 固定 digest + 显式 allowlist staging + 每步检查 | B2 指出最终 disposition 未解决 |

---

## 9. 补充验证

### 9.1 F01-F07 Oracle 对齐

逐 F 验证 plan 是否覆盖了 frozen oracle 的 predicate：

- **F01** (`interactive.01`): plan S1 删除全局 `--config` grammar → 满足 `forbidden: "为 prompt/interactive --config 建立 accepted scenario"`
- **F02** (`interactive.09`): plan S2 invalid editor 报错回 composer → 满足 `forbidden: "显式无效的EDITOR/VISUAL被静默忽略并回退到另一系统editor"`
- **F03** (`prompt.17` + `interactive.11/12/18`): plan S3 Escape/Ctrl+C 序列分类 + acceptance barrier → 满足 `expected: "只有standalone Escape表达取消"` 和 `forbidden: "看到ESC prefix立即取消Run"`
- **F04** (`interactive.15`): plan S4 READ_ONLY 保留 REPL + fresh attach → 满足 `expected: "READ_ONLY 客户端提交时显示明确只读失败但保留REPL"` 和 `forbidden: "将第二个并发客户端授予mutation权限"`
- **F05** (`interactive.28`): plan S5 从 interactive manifest 删除 `fins-preprocess` tag → 满足 `expected: "effective tool set不向Host注册start_fins_preprocess"`
- **F06** (`interactive.26`): plan S6 trigger 重命名为 `context_governance_resolved` → 满足 evidence report 中用户裁决"trigger 只说明 governance 已终结"
- **F07** (`interactive.29`): plan S7 accept barrier + coverage + repair + terminal → 满足 `expected: "全空/diagnostics-only/无法证明semantic coverage的candidate不得被接受"`

**Oracle 对齐结论**: 所有 F01-F07 的 plan 变更都直接对应 frozen oracle 的 expected/forbidden predicate，没有发现 oracle 覆盖缺口。

### 9.2 真实 Evidence 对齐

Plan S8 的 evidence 要求与 `docs/cli_ci.md` 第 11 节通用材料清单一致：
- `manifest.json`、`command.txt`、`before.json`、`input.txt`、`screen.txt`
- `host-public.json`、`event-log.jsonl`、`tool-trace.jsonl`、`memory.json`、`run-input.json`、`artifacts.json`
- `after.json`、`verdict.json`

Plan 额外要求 F02/F03/F04 的 PTY timing 和 F07 的 per-attempt validation code，这些是合理的场景特定证据。

---

## 10. Final Plan Review Conclusion

**Verdict: `fail`**（存在 blocking findings，plan 不满足 code-generation-ready 条件）

**Blocking findings（必须在 Plan Gate 修复后才能进入 implementation）**:
- **B1**: S3 prompt one-shot Vt100Parser 与现有 `run_keys.py` 线程模型不兼容，plan 没有指定 parser bridge 方案
- **B2**: 两个 dirty registry 的最终 PR 190 纳入方案缺失

**High-severity findings（强烈建议在 Plan Gate 修复）**:
- **B3**: S2 prompt_toolkit adapter seam 规格不足以指导实现

**Medium-severity findings（可在 implementation 前或期间解决）**:
- **B4**: S3 替换类型的现有消费者未枚举
- **B5**: S7 32 文件原子 commit 缺乏实施阶段缓解策略

**Low-severity findings（非阻塞）**:
- **B6**: `dayu/service/README.md` 更新判定需确认
- **B7**: §14.2 部分 stop check 应在 Plan Gate 解决

**Architecture、overcoupling、goal drift、non-goals、测试覆盖**: 全部通过，未发现 plan 在这些维度上的结构性缺陷。

**下一步**: plan author 应修复 B1 和 B2，并考虑 B3 的修复。修复后 plan 可重新提交 Plan Review Gate。

---

*Review 方: DeepSeek | 日期: 2026-08-02 | 后续合法入口: 修复后的 Plan Review Gate（同 plan 文件或续写）*
