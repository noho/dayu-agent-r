# WU-CLI-CONFORMANCE-F01-F07 计划审查报告

## 审查目标

- 计划文件：`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- 分支：`codex/interactive-oracle`
- 审查时间：2026-08-02T17:46:02+08:00

## 审查范围

逐项验证 F01–F07 语义 owner、S1–S8 实施决策、schema/state-machine/public interface、允许文件列表、sequencing、测试计划、staging/commit plan、dirty registry baselines 保护、README triggers、真实 evidence 要求、过度耦合、owner drift、反例与 residual risks。审查依据为 frozen truth docs、直接代码事实与两份 immutable evidence reports。

## 使用的冻结真源

| 真源 | SHA-256 / 状态 |
|---|---|
| `docs/cli_ci_oracles.json` | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` ✓ 与 §0.1 一致 |
| `docs/cli_ci_scenarios.json` | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` ✓ 与 §0.1 一致 |
| `observed-behavior-pr190-closeout.md` | `6aa8c8c7430e979b95f3bd8551f44ae34432e5e55172231c296d634932aa712f` ✓ |
| `compaction-invalid-response-audit-pr190.md` | `fed1a2ae29baf2b59b3d16d90460661c563ae18233f93530b241645ada38fb61` ✓ |
| `post_fix_conformance_refresh` 状态 | `required-on-fixed-commit-before-current-implementation-pass` ✓ |

## 测试的假设

1. 计划引用的文件全部存在且路径正确
2. 计划声称的语义 owner 与代码实际 owner 一致
3. 允许文件列表完整覆盖所需修改
4. S7 v2 schema 命名方案与现有代码可衔接
5. dirty registry 不会被意外 stage
6. 测试文件名与计划一致
7. 计划不引入 goal drift
8. 计划的 sequencing 不引入过度耦合

---

## Findings

### F1-未修复-严重-S1 测试文件名拼写错误（复数 vs 单数）

- **位置**: §3.1 允许文件列表第 10 项
- **问题类型**: 不可直接实施
- **当前写法**: 计划将 `tests/cli/test_session_commands.py`（复数）列入 S1 允许修改文件
- **反例/失败场景**: 实际文件名为 `tests/cli/test_session_command.py`（单数）。实施 agent 在验证命令 `pytest tests/cli/test_session_commands.py` 时会直接报 FileNotFoundError，导致 S1 验证步骤失败。
- **为什么有问题**: 文件名不匹配会导致 implementation agent 无法执行聚焦验证命令，也无法正确 git add 该测试文件。
- **直接证据**: `ls tests/cli/test_session*` 输出 `tests/cli/test_session_command.py`（单数），无复数形式。
- **影响**: 实施 agent 无法完成 S1 验证，阻塞后续所有 slice。
- **建议改法和验证点**: 将 `tests/cli/test_session_commands.py` 改为 `tests/cli/test_session_command.py`。同时确认聚焦验证命令中的 pytest 参数也使用正确路径。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 严重

---

### F2-未修复-严重-S4 测试文件名不存在

- **位置**: §6.1 允许文件列表第 3 项
- **问题类型**: 不可直接实施
- **当前写法**: 计划将 `tests/host/test_session_attachment.py` 列入 S4 允许修改文件，并在括号中注明"只增加 Host 已有 typed READ_ONLY owner contract 断言"。
- **反例/失败场景**: 实际文件名为 `tests/host/test_session_attachment_registry.py`。计划正文中提到"若实际 Host owner test 位于现有相邻 attachment 测试文件，则只能把该文件替换进 allowlist"，但这个条件分支并未实际执行——allowlist 中的文件名仍然是错误的。
- **为什么有问题**: 实施 agent 会尝试创建或修改一个不存在的文件路径。如果 agent 按计划字面执行，要么因文件不存在而失败，要么创建一个新文件而忽略已有的 `test_session_attachment_registry.py` 中的相关测试。
- **直接证据**: `ls tests/host/test_session*` 输出 `tests/host/test_session_attachment_registry.py` 和 `tests/host/test_session_lifecycle.py`，无 `test_session_attachment.py`。
- **影响**: S4 实施 agent 无法正确扩展 Host owner test 断言，或创建重复测试文件。
- **建议改法和验证点**: 将 `tests/host/test_session_attachment.py` 改为 `tests/host/test_session_attachment_registry.py`，并在 slice artifact 中记录实际路径。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 严重

---

### F3-未修复-中-S7 v2 schema 命名空间变更未明确说明

- **位置**: §9.2 Fresh input/source-boundary contract
- **问题类型**: 目标漂移（轻微）/ 最佳实践偏离
- **当前写法**: 计划定义 `COMPACT_INPUT_SCHEMA_V2 = "dayu.context_compaction.input.v2"` 和 `COMPACT_OUTPUT_SCHEMA_V2 = "dayu.context_compaction.output.v2"`，但未说明这是一次完整的命名空间变更。
- **反例/失败场景**: 现有代码使用 `conversation_compact_input_v1` / `conversation_compact_output_v1`（`compaction.py:29-32`），以及 `ConversationCompactOutputVNext` 类名。从 `conversation_compact_*` 到 `dayu.context_compaction.*` 是命名空间级别的变更，影响 schema version literal、class name、all references across 17+ production files 和 16 test files。
- **为什么有问题**: 实施 agent 需要理解这不仅仅是版本号从 v1 到 v2 的升级，而是整个命名空间的重构。计划只列出了新 schema 的精确 shape，但未提供从旧命名到新命名的映射指导。agent 可能只替换 version literal 而保留旧 class name，或反之。
- **直接证据**: `compaction.py:29-32` 定义 `CONVERSATION_COMPACT_INPUT_SCHEMA_VERSION_VNEXT = "conversation_compact_input_v1"` 和 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT = "conversation_compact_output_v1"`；`ConversationCompactOutputVNext` 类在 `compaction.py:1421` 定义并在 `compaction_operation.py`、`compact_pipeline.py`、`llm_compaction.py`、`context_governance.py` 中广泛引用。
- **影响**: 实施 agent 可能产生命名不一致的中间状态，或遗漏某些引用的重命名。
- **建议改法和验证点**: 在 §9.2 增加一段说明：旧 `conversation_compact_input_v1` → 新 `dayu.context_compaction.input.v2`，旧 `conversation_compact_output_v1` → 新 `dayu.context_compaction.output.v2`，旧 `ConversationCompactOutputVNext` → 新 `CompactCandidateV2`（或计划中定义的精确类名）。建议在聚焦验证命令中增加 `rg -n 'conversation_compact_input_v1|conversation_compact_output_v1|ConversationCompactOutputVNext' dayu/host tests/host` 扫描。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

---

### F4-未修复-中-S7 原子提交范围过大

- **位置**: §9.1 原子边界与 §13.2 staging plan
- **问题类型**: 切片过粗
- **当前写法**: S7 允许修改 17 个生产文件和 16 个测试文件，要求一次性原子提交，不得拆分。
- **反例/失败场景**: 如果实施 agent 在第 15 个文件修改时引入 pyright 错误或测试失败，回退成本极高——需要撤销前面 14 个文件的修改。更现实的风险是：agent 在修改过程中遇到意外的代码耦合（例如 `compact_pipeline.py` 中的 `build_reactive_pass_queue_plan` 被 `engine_ingest.py` 调用），需要同时修改调用方，但调用方可能不在允许列表中或修改会影响其它 slice 的前置条件。
- **为什么有问题**: 计划在 §0.2 声明"F07 不是 blocker"，但 S7 的实际复杂度（17 文件原子变更 + fresh schema + accept barrier + repair + terminal + Memory projection）远超任何单个 slice。计划自身将 residual risk 标为 HIGH。
- **直接证据**: `pass_queue` 参数存在于 `compaction_operation.py:676,755,767,788,1089-1113`；`build_reactive_pass_queue_plan` 在 `compact_pipeline.py:580` 定义，在 `engine_ingest.py:108,2907` 引用。删除 reactive multi-pass 需要同时修改 operation、pipeline 和 engine_ingest 三个模块。
- **影响**: 实施 agent 可能在原子边界内反复失败，消耗大量 token 和时间；或在压力下跳过某些验证步骤。
- **建议改法和验证点**: 不建议拆分原子边界（schema 一致性确实需要原子落地），但建议在 S7 内部按 9.2–9.8 的子步骤顺序编码，并在每个子步骤后运行子集测试作为中间检查点。计划已在 §9.1 允许"按 9.2–9.8 的内部顺序编码"，但应更明确地要求每个子步骤后运行 `pyright` 和该子步骤涉及的测试子集。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

---

### F5-未修复-低-S7 缺少 v1 数据兼容/迁移说明

- **位置**: §2.2 明确非目标
- **问题类型**: 契约缺失
- **当前写法**: 计划声明"不迁移旧 compact schema/旧 durable DB，不提供旧字段、旧 trigger 或 `--config` 兼容读取/alias/re-export"。
- **反例/失败场景**: 现有 Host SQLite 中可能已存储 v1 schema 的 compact artifact。S7 将 schema version literal 从 `conversation_compact_input_v1` 改为 `dayu.context_compaction.input.v2`，并删除 v1 parser。如果 `memory.py` 或 `compact_artifact.py` 尝试从 SQLite 读取旧 artifact 并用新 parser 解析，会失败。`post_fix_conformance_refresh` 要求"existing sessions with v1 compact data to function after changes"——这意味着 S8 真实 evidence 需要在已有 v1 数据的 session 上运行。
- **为什么有问题**: 计划没有说明如何处理已有的 v1 durable compact data。"不迁移"是明确的非目标，但代码需要在遇到旧数据时 fail gracefully 而不是 crash。
- **直接证据**: `compaction.py:29-32` 定义 v1 schema literal；`compact_artifact.py` 保存和读取 artifact；`memory.py` 从 artifact 恢复 compact view。`post_fix_conformance_refresh` 的 finding_count=7 且 status 为 `required-on-fixed-commit-before-current-implementation-pass`。
- **影响**: 如果 S7 的 artifact reader 不兼容旧数据，已有 session 的 memory 恢复会失败。
- **建议改法和验证点**: 在 §9.6 或 §9.7 增加一段说明：当 artifact reader 遇到非 v2 schema version 时，应走既有 fallback/fail-closed 路径（类似 attempt exhaust），不 crash、不静默忽略。这不需要"迁移"旧数据，只需要对旧 schema 做 deterministic reject。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

### F6-未修复-低-S3 统一 barrier 设计增加 prompt 路径复杂度

- **位置**: §5.2 Typed state 与 owner-level call path
- **问题类型**: 过度耦合（轻微）
- **当前写法**: 计划将 prompt one-shot 和 interactive REPL 的 acceptance/cancel barrier 统一为 `_ActiveTurnCloseout`，放在 `session_execution.py`。
- **反例/失败场景**: prompt 是一次性命令，没有 composer、没有 typeahead、没有 queued follow-up；其 cancel 语义比 interactive 简单得多。统一 barrier 意味着 prompt 路径必须携带 interactive 才需要的状态（`submit_terminal` event、`cancel_started` flag 等），增加 prompt 路径的认知负担和测试复杂度。
- **为什么有问题**: 计划 §14.3 声称"F03 共用一个 turn closeout 而不为 prompt/interactive 建两套 framework"。但 prompt 的 `run_keys.py` 已经独立处理 one-shot raw input（§5.2 提到"prompt one-shot raw input 使用 prompt_toolkit 公共 Vt100Parser"），与 interactive 的 prompt_toolkit binding 不同。统一 barrier 是否真的减少复杂度，取决于 `_ActiveTurnCloseout` 的实际接口是否对两条路径都自然。
- **直接证据**: `session_execution.py:145` 定义 `_PromptAcceptedRunState`，`session_execution.py:170` 定义 `_InteractiveAcceptedRunState`，两者已有不同的 barrier 实现。
- **影响**: 非阻塞。统一 barrier 是合理的架构方向，但实施 agent 需要注意不要让 prompt 路径承担不必要的 interactive 状态。
- **建议改法和验证点**: 无需改计划。实施时应确保 `_ActiveTurnCloseout` 的 prompt 用法不引入 interactive-only 的状态字段到 prompt 路径。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

### F7-未修复-低-S2 prompt_toolkit seam 依赖风险

- **位置**: §4.2 `_PromptToolkitExternalEditorAdapter` 与 §14.1 风险登记
- **问题类型**: 并发恢复风险（第三方依赖）
- **当前写法**: 计划要求"若当前 prompt_toolkit public seam 不能表达'保留其 tempfile lifecycle 且显式只启动一次'，实现必须使用一个局部、版本锁定并有 contract test 的 adapter seam"。
- **反例/失败场景**: prompt_toolkit 的 `Buffer.open_in_editor()` 内部管理 tempfile 和 editor 子进程生命周期。如果该方法不支持"只启动指定 executable 而不 fallback"，adapter 需要 monkey-patch 或重写部分逻辑。prompt_toolkit 版本升级可能破坏这种非公开依赖。
- **为什么有问题**: 计划已识别此风险为 MEDIUM，并设定了 stop signal。但 stop signal 的触发条件（"依赖版本变化导致 seam 失效"）只能在实施时才能验证，计划无法提前确定是否可行。
- **直接证据**: 计划 §4.2 和 §4.5 明确讨论此风险。§14.1 将其列为 MEDIUM risk。
- **影响**: S2 可能需要在实施时暂停并请求 gate 裁决。这不是计划缺陷，而是合理的 stop signal 设计。
- **建议改法和验证点**: 无需改计划。实施 agent 应在 S2 开始时先验证 prompt_toolkit seam 可行性，不可行则立即停止。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## Open Questions

### O1-S8 real evidence provider 不可用时的处理

计划 §12.2 要求 Mimo-first、DeepSeek fallback。§14.2 说"真实 provider credentials/配额若不可用，S8 标记环境 blocked 并保留 bundle"。但 `post_fix_conformance_refresh` 的 status 是 `required-on-fixed-commit-before-current-implementation-pass`——如果 S8 标记 blocked，整个 work unit 的 closeout 判定如何处理？计划 §10.3 的 stop signal 提到"目标 commit 不 clean、provider 身份/模型不可证"时停止，但没有说明 blocked 后的 next entry point。

**建议**: 在 §10.3 增加一段：若 S8 因 provider 不可用标记 blocked，closeout 状态为 `BLOCKED-ON-REAL-EVIDENCE`，next entry point 为"provider 恢复后重新执行 S8 evidence acquisition"，不退回 S1–S7。

### O2-S7 Memory policy 内部不一致的处理

计划 §14.2 提到"若 S7 owner tests 发现现有 Memory policy 内部本身有两个不一致 cap 真源，先把共享 policy owner 收敛在 S7 允许文件内"。当前代码中 `MemoryProjectionPolicy` 定义在 `dayu/host` 内，而 `estimate_memory_size_units` 的具体实现位置未在计划中确认。如果 estimator 位于 S7 允许文件外，需要申请 scope 扩展。

**建议**: 实施 agent 在 S7 开始前先确认 `estimate_memory_size_units` 的定义位置，若在允许文件外则在 slice artifact 中记录并请求 gate 裁决。

---

## Residual Risks

| 风险 | 等级 | 收敛方式 | 跟踪位置 |
|---|---|---|---|
| prompt_toolkit editor seam 随版本变化 | MEDIUM | 版本锁定 adapter contract test | S2 implementation gate |
| ESC ambiguity 与 SIGINT/terminal 同 batch 竞态 | MEDIUM | Vt100Parser chunk matrix + 确定性 scheduler tests | S3 + S8 PTY evidence |
| READ_ONLY 后 writer 退出时 fresh attach 竞争 | MEDIUM | Host public typed mode + close-before-open + stable pending identity | S4 + S8 真实并发 |
| F07 fresh schema 影响面大（17 文件原子变更） | HIGH | S7 原子边界 + strict parser + full suite | S7 implementation gate |
| LLM 自然语言低质量但形式合法 | MEDIUM/ACCEPTED | deterministic 最低信息 + coverage + 真实 provider evidence | S7 + S8 |
| Mimo/DeepSeek/网络环境不可用 | MEDIUM/OPERATIONAL | Mimo-first + 明确 fallback + 新 bundle | S8 |
| dirty registry 误 stage/覆盖 | HIGH/CONTROLLED | 固定 digest + 显式 allowlist staging + 每步 status/index 检查 | 每个 slice |

---

## 计划质量总结

### 优点

1. **语义 owner 表完整且准确**：§2.3 的 11 项 owner 表与代码实际 owner 一致，每个 finding 都有清晰的修复边界。
2. **冻结真源保护严格**：§0.1 的 SHA-256 验证、staging allowlist 和每步 digest 检查构成有效的 registry 保护机制。实际验证确认两个 registry 的 SHA-256 与 §0.1 一致。
3. **S7 原子边界设计合理**：schema、validator、repair、terminal、artifact、Memory、RunInput、trace 和 owner tests 必须同在，避免中间不一致状态。
4. **stop signal 明确**：每个 slice 都有"立即停止信号"，且条件具体可验证。
5. **真实 evidence 程序完整**：§12 定义了独立 run root、clean target commit、Mimo-first/DeepSeek fallback、immutable bundle 和 digest 验证。
6. **no-overdesign 论证充分**：§14.3 逐项说明每个设计决策的最小化理由。

### 不足

1. **测试文件名错误**（F1、F2）：两个阻塞性错误，实施 agent 会直接失败。
2. **v2 schema 命名空间变更未显式说明**（F3）：从 `conversation_compact_*` 到 `dayu.context_compaction.*` 的全面重命名需要额外指导。
3. **v1 数据兼容策略缺失**（F5）：虽然"不迁移"是正确的非目标，但对旧数据的 deterministic reject 行为需要明确。

---

## 结论

**Verdict: pass-with-risks**

计划在语义 owner、frozen truth 对齐、staging 保护和 evidence 程序方面质量很高。发现两个阻塞性测试文件名错误（F1、F2）需要在实施前修正，否则 implementation agent 会在 S1 和 S4 的验证步骤直接失败。一个中等级别的命名空间变更说明缺失（F3）和 v1 数据兼容策略缺口（F5）也需要补充。其余 finding 为非阻塞改进。

修正 F1 和 F2 后，计划可安全交给 implementation agent。F3 和 F5 可以在修正 F1/F2 时一并补充，也可以由 implementation agent 在对应 slice 开始时自行确认。
