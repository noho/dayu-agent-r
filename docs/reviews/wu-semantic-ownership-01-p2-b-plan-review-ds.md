# WU-SEMANTIC-OWNERSHIP-01 P2-B Plan Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-B Host memory/test contract hardening`
- Gate: plan review（adversarial，不改代码）
- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-b-plan.md`
- Delivery artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-controller-validation.md`
- Source adjudication: `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`

## Verdict

**pass-with-findings**

Plan 的 owner boundary 判断正确、stop condition 充分、non-goals 清晰、propagation audit 完备。六个 challenge area 中有三个存在 underspecification 需要 plan 修正后才能进入 implementation；这些 gaps 不改变 plan 的整体可行性，但若不在 plan 中补齐，implementation 可能触发不必要的 stop condition 或产生新的语义所有权漂移。

---

## Findings

### F1 (High). MiMo 08: typed field 落点未指定，存在意外触发 schema migration stop condition 的风险

**证据**：

- Plan §5 S1 要求"为 memory projection / run input event view 增加显式 `assistant_final_answer_text` 或等价 typed field"，但未指定该 field 的数据结构落点。
- 当前 `_MemoryProjectionPayloadView`（`dayu/host/durable/memory.py:363`，内部 namedtuple）是 projection-internal 类型，在其上增加 field 不涉及 durable schema。
- `ConversationMemorySnapshotVNext` 的 `SelectedRecentWindowItem` 是 durable snapshot schema，在其上增加 field 等于迁移 durable schema，会触发 plan 自身的 stop condition（"实施发现消除 payload mutation 必须新增或迁移 durable EventLog schema 字段"）。
- `dayu/host/memory.py` 中的 `MemoryProjectionEvent` 是 Host public contract type；plan 将其列为"仅当需要扩展 typed 字段"的 allowed file，说明 plan 已经意识到这个 ambiguity，但没有做出 design decision。

**影响**：若 implementation 误将 typed field 落在 durable snapshot schema 上，stop condition 触发，整个 slice 被 blocked。MiMo 09 和 MiMo 12 也会被连带阻塞（参见 F4）。

**建议 plan 修正**：

1. 明确 typed field 的落点：优先落在 `_MemoryProjectionPayloadView`（projection-internal），其次落在 `MemoryProjectionEvent`（Host public contract），明确排除 `ConversationMemorySnapshotVNext` 和 `SelectedRecentWindowItem`。
2. 明确 `_memory_projection_payload_view()` 和 `_payload_with_assistant_final_answer()` 的修改范围：这两个函数还处理 `TOOL_RESULT_ACCEPTED` 分支（`memory.py:381-382`、`run_input.py:3209-3210`），plan 应明确 TOOL_RESULT_ACCEPTED 分支是否保持不变。
3. 明确 `_terminal_answer.py` 模块 docstring 的新契约表述：不应只删除旧表述，应写出 replacement text 的关键要素——resolver 输出是 typed continuity material，consumer 不通过 payload mutation 消费。

---

### F2 (Medium). MiMo 09: relative import resolution 的不可解析场景缺少错误行为规格

**证据**：

- Plan §5 S1 要求"按当前被扫描文件所属 package root 解析为绝对模块名"，但未定义 package root 的判定方式。
- 当前 `_imported_module_names()` 在 `tests/host/test_import_boundary.py:180-197`，是 pure-AST scanner，不感知文件系统路径或 package 结构。
- 可能出现的 ambiguity：
  - 文件不在任何 package root 下（如 `workspace/tmp/` 下的脚本）：`from .x import y` 无法解析。
  - 文件在 namespace package 下：`from ..x import y` 的 parent package 可能不唯一。
  - editable install (`pip install -e`)：`__init__.py` 可能不在预期位置。

**影响**：若 implementation 遇到无法确定性解析的相对 import，可能选择静默跳过（回到当前漏扫状态）、假阳性报错（误杀合法依赖）、或引入 fragile 的 custom import resolver（违反 non-goal"不需要新增通用 import linter"）。

**建议 plan 修正**：

1. 明确 package root 判定规则：从被扫描文件路径向上查找首个不含 `__init__.py` 的目录的父目录，或使用 `sys.path` 中最长匹配 prefix。
2. 明确不可解析时的行为：应报出 `pytest.fail` 或明确的 `UnableToResolveRelativeImport` 错误，不得静默跳过。
3. 测试用例应覆盖：同包相对 import（`from .durable import memory`）、父包相对 import（`from ..engine import agent`）、以及一个 intentionally unresolvable 的 case（如文件不在任何 package 下的 `from .ghost import x`），断言后者触发明确错误而非静默通过。

---

### F3 (Medium). MiMo 12: "business test body" 与 "digest invariant test" 的边界未定义

**证据**：

- Plan §5 S1 要求"保留专门测试 digest 计算时允许局部构造 `snapshot_without_digest`，但应集中在 factory 或明确的 digest invariant test"。
- Plan validation 要求 `rg -n 'snapshot_digest="pending"' tests/host/test_compact_material.py tests/host/test_run_input_builder.py` 不应再有匹配。
- 当前 `_empty_snapshot()`（`test_compact_material.py:2990`）、`_rich_memory_snapshot()`（`test_run_input_builder.py:3996`）、`_current_input_memory_snapshot()`（`:4158`）、`_reference_continuity_only_snapshot()`（`:4224`）均使用 `snapshot_digest="pending"` + `calculate_memory_snapshot_digest()` 模式构造 snapshot。

**影响**：若 shared factory 内部仍使用 `snapshot_digest="pending"` 模式（这是合理的——digest 计算需要先构造 snapshot_without_digest），`rg` 扫描会命中 factory 自身。除非 factory 以不同方式构造（如先构造不含 digest 的 dataclass instance 再通过 helper 补全），否则 source scan 要么误报、要么需要排除 factory 文件。Plan 当前的 `rg` 命令没有 exclude pattern，也没有定义"factory 内部可以使用 sentinel"和"业务测试体不得使用 sentinel"的边界。

**建议 plan 修正**：

1. 明确 shared factory 的 digest 构造方式：factory 内部使用 `snapshot_digest=SENTINEL` 或 `snapshot_digest=""` 等不与 `"pending"` 字面量冲突的占位符；或 factory 接受 `snapshot_without_digest` 参数由 caller 通过 `calculate_memory_snapshot_digest()` 补全。
2. 更新 `rg` 验证命令，排除 factory 文件或明确 factory 内部允许的例外形式。
3. 增加一个 explicit assertion：`rg -n 'ConversationMemorySnapshotVNext(' tests/host/test_compact_material.py tests/host/test_run_input_builder.py` 只应在 shared factory、专门 digest invariant test 和迁移过渡期允许的位置出现。

---

### F4 (Medium). One-slice 策略在 MiMo 08 stop condition 触发时会造成 MiMo 09/12 连带阻塞

**证据**：

- Plan §5 建议 1 个 implementation slice，理由是"三类 finding 代码量小，验证矩阵共享"。
- Plan §5 S1 第一步就是"更新 `docs/host/design.md` 中 Conversation Memory / RunInputBuilder terminal answer continuity 描述"，这是 MiMo 08 的前置 design truth sync。
- Plan stop condition："实施发现消除 payload mutation 必须新增或迁移 durable EventLog schema 字段"→ 整个 slice 停止。
- MiMo 09（import scanner）和 MiMo 12（fixture factory）不依赖 MiMo 08 的 design truth sync，也不依赖 durable schema。

**影响**：若 MiMo 08 design truth sync 发现当前 `RUN_SUCCEEDED` terminal payload contract 不足以支持 typed resolver material 方案（概率低但非零——因为 design.md 当前完全没有 terminal answer continuity 的显式描述），stop condition 触发，MiMo 09 和 MiMo 12 也被阻塞。这两项是独立的 test hardening，不需要等待 design truth 裁决。

**建议 plan 修正**：

1. 将 slice 分为两个子步骤或两个独立 slice：
   - S1a: MiMo 08 design truth sync + production projection change（可独立 stop）
   - S1b: MiMo 09 import scanner + MiMo 12 fixture factory + cross-path equivalence test（不依赖 S1a 的结果）
2. 或者：保持 one-slice 但明确 MiMo 08 stop condition 触发时，implementation agent 必须将 MiMo 09/12 作为独立的 follow-up work unit 继续，不得将整个 P2-B 标记为 blocked。
3. 无论哪种方案，cross-path equivalence test 的 placement 需要明确：它测试的是 MiMo 08 的修复效果（两条路径的 LLM-facing text 一致），应跟随 MiMo 08 的实现节奏；如果 MiMo 08 stop，equivalence test 也应 defer，不应独立实现。

---

### F5 (Low). Allowed files 列表缺少 `dayu/host/terminal_payload.py`

**证据**：

- `dayu/host/_terminal_answer.py` 依赖 `dayu/host/terminal_payload.py` 的 `assistant_final_answer_text_from_run_payload()`、`terminal_payload_content_text_from_payload()` 和 `PayloadTextReadPolicy`。
- 若 MiMo 08 修改了 `_terminal_answer.py` 的 resolver contract（如改为返回 typed material 而非 raw text），`terminal_payload.py` 中的 helper 可能也需要同步调整或新增 typed return type。
- Plan allowed files 列表中未包含 `dayu/host/terminal_payload.py`。

**影响**：低——当前 `terminal_payload.py` 中的 helper 是通用 payload 读取工具，大概率不需要修改。但若 implementation 发现需要新增 typed return type 或修改 `assistant_final_answer_text_from_run_payload` 的行为，缺少 allowed file 声明会导致 scope creep 争议。

**建议 plan 修正**：将 `dayu/host/terminal_payload.py` 加入 allowed files，标注"仅在 terminal answer continuity resolver contract 变更需要同步修改 helper 返回类型时修改"。

---

### F6 (Low). Cross-path equivalence test 对真实 terminal artifact 依赖未明确

**证据**：

- Plan §5 S1 要求"同一 `RUN_SUCCEEDED` + terminal payload descriptor source 经 durable memory projection 和 ordinary RunInputBuilder 进入 LLM-facing assistant continuity 时文本一致"。
- 当前 `test_memory_projection.py` 中的 durable projection tests 使用 `write_memory_snapshot_with_checkpoint()` 写入真实 durable store（`test_memory_projection.py:1737`）。
- 当前 `test_run_input_builder.py` 中的 RunInputBuilder tests 使用 `_rich_memory_snapshot()` 等 synthetic snapshot（`test_run_input_builder.py:3996`），不经过 durable store 的 EventLog → projection pipeline。
- Cross-path equivalence test 需要在同一 durable store 中先写入 `RUN_SUCCEEDED` event + terminal artifact，再分别经过 durable projection 和 RunInputBuilder 读取——这要求 test 同时理解两种 consumer 的 setup。Plan 没有指定 test 应该放在哪个测试文件，也没有说明是否需要真实 terminal artifact descriptor（`terminal_summary_ref` + `terminal_summary_digest`）。

**影响**：若 implementation 选择 synthetic-only test（两条路径都 mock 了 terminal answer），可能漏掉真实 terminal artifact descriptor 读取链路中的 digest 校验、transaction 边界和 `sqlite_payload_object` 错误处理。

**建议 plan 修正**：明确 cross-path equivalence test 至少包含一个真实 durable store case：写入 `RUN_SUCCEEDED` event（inline `final_answer` 为空，`terminal_summary_ref`/`terminal_summary_digest` 指向真实 terminal artifact payload），再分别通过 durable memory projection 和 RunInputBuilder 消费，断言两条路径产出的 LLM-facing assistant answer text 一致且不含 refs/digests。

---

## Accepted Plan Compliance

以下方面 plan 充分且正确，无需修改：

### Owner boundary 判断

Plan §3 的 owner boundary 表格正确识别了每个语义的首次产生、校验、持久化/真源、投影/LLM 可见和 P2-B 修复边界。与 `docs/host/design.md` 的以下约束一致：

- Projection 不能反向成为 EventLog 真源（design.md:43）→ MiMo 08 修复边界落在 projection 不修改 payload view。
- Conversation Memory 是 read model（design.md:2778-2784）→ 不把 mutated payload 当作 canonical EventLog truth。
- RunInputBuilder 不暴露 refs/digests（design.md:3140）→ cross-path equivalence test 断言不泄漏。
- Engine 不拥有 Host durable truth（engine/design.md:3-7, :483）→ 不改 Engine final_answer contract。

### Non-goals / Scope boundary

Plan §4 的 non-goals 完整覆盖了可能被误扩展的区域：
- 不重设 Conversation Memory 五类语义模型。
- 不改 compact proposal schema、compactor prompt、retention/purge。
- 不改 Engine final_answer contract。
- 不把完整 final answer 强制复制进 EventLog hot payload。
- 不做旧库兼容读取。

### Stop conditions

Plan §4 的五个 stop condition 具体、可验证、与三种 finding 的 risk 对齐。每个 stop condition 都有明确的触发条件和升级路径（design gate 或 re-scope）。

### Propagation audit

Plan §6 的 8 条 propagation audit 路径覆盖了从 Engine 产出到测试夹具的完整链路，与 CLAUDE.md "语义所有权与修复边界"的 propagation audit 要求一致。

### Validation matrix

Plan §5 S1 的 validation commands 覆盖了 import-boundary、memory projection、run input、compact material 四个测试文件，外加 pyright 和 git diff --check。optional broader validation（`pytest tests/host`）合理。

### README trigger judgment

Plan §7 正确判断当前 planning gate 不需要 README 更新；implementation 触发规则与 CLAUDE.md README 更新触发条件一致。

### One-slice justification

Plan §5 的 one-slice 理由（代码量小、验证矩阵共享、拆多 slices 增加 gate 成本但不减少 schema/design 风险）基本合理。唯一风险是 F4 指出的 MiMo 08 stop condition 连带阻塞——这是一个 sequencing risk，不是 slice count 错误。

---

## Residual Risks

以下风险在 plan 修正后仍然存在，implementation 和 review gate 需要持续关注：

### R1. `_terminal_answer.py` 与 `docs/host/design.md` 对齐后仍可能发现 terminal answer continuity 的 design truth gap

**风险**：当前 design.md 没有显式描述 `RUN_SUCCEEDED` hot payload、terminal payload descriptor 和 assistant final-answer continuity resolver 三者的关系。若 design truth sync 发现需要引入新的 terminal fact 字段或新的 public contract，P2-B 的"最小 hardening"scope 可能不够。

**缓解**：plan 已有 stop condition。implementation agent 必须在第一步 design truth sync 后立即判断是否触发 stop condition，不能先写 production code 再回头补 design。

**Owner**：implementation agent + gate review。

### R2. Relative import scanner 可能与现有 import-boundary test 的 `_matches_prefix()` 逻辑产生交互

**风险**：`_matches_prefix()` 使用 prefix tuple 匹配绝对模块名。相对 import 解析为绝对模块名后，同一个禁止前缀逻辑自然适用——但若解析出的绝对模块名与手动编写的绝对 import 形式不一致（如 `from dayu.host.durable import memory` vs 从 `dayu/host/durable/memory.py` 的相对 import 解析为 `dayu.host.durable.memory`），已有 test 的 expected allowed/forbidden 列表可能需要更新。

**缓解**：implementation 后必须运行完整 `tests/host/test_import_boundary.py`，任何 expected list 变更必须在 implementation report 中解释。

**Owner**：implementation agent。

### R3. Shared memory snapshot factory 可能被后续修改绕过

**风险**：新增的 shared factory 只在当前 tests 中 enforce。若后续开发者在 `test_compact_material.py` 或 `test_run_input_builder.py` 中新增测试时手写 `ConversationMemorySnapshotVNext(...)` 而不使用 factory，source scan 会被动发现（通过 CI 中的 `rg` assertion），但没有编译期或类型期 enforce。

**缓解**：plan 中的 source scan assertion（`rg` 命令）作为 CI gate 可捕获回归。如果项目后续引入 pre-commit hook 或 lint rule，可以升级 enforce 方式。当前 P2 级别的 test hardening 不需要编译期 enforce。

**Owner**：后续 gate review + CI maintainer。

### R4. Cross-path equivalence test 可能暴露未知的 semantic conflict

**风险**：plan stop condition 已列出"cross-path equivalence test 暴露现有 RunInputBuilder 与 memory projection 对 LLM-facing final answer 的真实语义冲突"。当前代码的两个路径使用相同的 `assistant_final_answer_continuity_text()` resolver，理论上应产出相同文本——但 RunInputBuilder 可能对 text 做额外的截断、wrapper 或 role mapping，而 memory projection 可能做不同的 selected recent window policy 过滤。若暴露冲突超出 P2-B 范围，stop condition 触发。

**缓解**：plan stop condition 覆盖了此风险。implementation 应优先写 equivalence test（在 production change 之前），以尽早发现冲突。

**Owner**：implementation agent。

---

## Review Artifact

- 本 artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-review-ds.md`
- 产出日期: 2026-07-09
- Reviewer: AgentDS (Claude Code Agent)
- 未修改任何生产代码、测试或 README。
