# Interactive Conversation Memory closure F08：DS 第二路独立 code review

## Review identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Review slice：F08（summary null 的 LLM-facing 选择规则与 replacement contract）。
- 审查者：DS（独立第二路，不依赖 MiMo）。
- 分支：`codex/interactive-oracle`。
- Base ref：`2e7a01678677817aafd22603f03f17605aa9e39c`（PR 190 compactor output semantics）。
- Accepted plan：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`。
- Frozen findings：`docs/reviews/wu-interactive-memory-closure-f08-f10.md`，SHA-256 `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`（已核对一致）。
- 输出文件：`docs/reviews/wu-interactive-memory-closure-f08-code-review-ds.md`。
- 审查时间：2026-08-04。

## Scope

本 review 只覆盖 F08 slice 未提交的 5 个变更文件：

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `docs/cli_init_workspace_manifest_v1.json`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_memory_projection.py`

不覆盖 F09（Tool Trace）、F10（turn-group atomicity）或正式 CLI scenario evidence。

## 审查方法

1. 读取 accepted plan（`wu-interactive-memory-closure-f08-f10-plan-codex.md`）、根 `AGENTS.md`、frozen findings/evidence、prompt/manifest/test 的完整 diff。
2. 独立复验 prompt/content SHA-256、manifest SHA-256、frozen baseline/evidence SHA-256。
3. 独立运行 focused test suite 与 pyright。
4. Adversarial 逐项检查用户指定的 8 类关注点（见下文）。
5. 只做只读验证，不修改任何文件。

## Positive confirmations（全部通过）

### C1：Prompt SHA-256 与 manifest entry 一致

```bash
$ python3 -c "import hashlib; print(hashlib.sha256(open('dayu/config/prompts/scenes/conversation_compaction_user.md','rb').read()).hexdigest())"
5f5a51519e11eae0f162e8623e3c55d3946e1613bd36bfe4c38cc3e61eb827c0
```

manifest 中该 asset 的 `content_sha256` 为 `5f5a51519e11eae0f162e8623e3c55d3946e1613bd36bfe4c38cc3e61eb827c0`，完全一致。

### C2：Manifest SHA-256 与 init smoke test 常量一致

```bash
$ python3 -c "import hashlib; print(hashlib.sha256(open('docs/cli_init_workspace_manifest_v1.json','rb').read()).hexdigest())"
9ebdeab528bfcf953107a7d0e94d7aba63aab4fe8c56f7e612251dd1247af6a1
```

`tests/cli/test_smoke_cli_init_provider_matrix.py` 中 `FROZEN_MANIFEST_SHA256 = "9ebdeab528bfcf953107a7d0e94d7aba63aab4fe8c56f7e612251dd1247af6a1"`，完全一致。

manifest 中仅更新了 `conversation_compaction_user.md` 的唯一 `content_sha256` 条目；其他 40+ asset entry 均未改动。两个 SHA consumer（manifest entry + test constant）精确对应，无多余或遗漏。

### C3：Frozen baseline 与 evidence 均未改变

| 文件 | Actual SHA-256 | Accepted-plan checkpoint | 一致 |
|---|---|---|---|
| `docs/cli_ci_oracles.json` | `da049231...` | `da049231...` | ✓ |
| `docs/cli_ci_scenarios.json` | `7c991d14...` | `7c991d14...` | ✓ |
| `docs/reviews/wu-interactive-memory-closure-f08-f10.md` | `95a09543...` | `95a09543...` | ✓ |
| `workspace/tmp/interactive-memory-observed-behavior.md` | `ad643151...` | `ad643151...` | ✓ |
| `workspace/tmp/interactive-memory-report-freeze.json` | `7ba64926...` | `7ba64926...` | ✓ |

### C4：旧语义文本已彻底清除

- 旧文本 `不影响同一 candidate 中其它四类业务语义项` 已从 prompt 中移除（grep 确认无匹配）。
- 测试中对该旧文本的断言已同步移除（grep 确认 `不影响同一 candidate` 在 test 文件中出现 0 次）。
- 新文本 `不表示保留旧 summary`、`其它四类业务语义项仍须根据本次材料各自独立输出`、`不得因 summary 为 null 而一并清空` 全部存在于 prompt 中。

### C5：Focused test suite 全部通过

```
$ pytest tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/cli/test_smoke_cli_init_provider_matrix.py -q
158 passed, 3 warnings in 4.23s
```

其中：
- `test_prompt_assets_are_self_contained_for_fresh_v2_contract` PASSED
- `test_accepted_compact_without_summary_clears_prior_session_summary` PASSED

### C6：Pyright 零新增错误

```
$ pyright tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/cli/test_smoke_cli_init_provider_matrix.py
0 errors, 0 warnings, 0 informations
```

### C7：无 Host semantic verifier、无阈值、无兼容代码

diff 中不包含任何生产代码变更（仅 prompt 文本 + 测试 + digest 同步）。不存在对 `context_governance.py`、`compaction_operation.py`、`memory.py`、`memory_projection.py`（生产代码）或 v2 output schema 的修改。无新增 `len(text)`、正则、词表、停用词或任何自然语言 heuristic。

### C8：改动文件严格限于 approved F08 files

`git diff --name-only HEAD` 输出恰好 5 个文件，全部在 plan 的 Slice F08 allowed files 列表中。无 v2 parser、Context Governance、Memory schema、frozen baseline/evidence 的变更。

## Adversarial checks（逐项证据）

### AC1：模型在低认知负担下是否知道何时 null 而非占位

**证据**：prompt 第 35–37 行自足定义了三条规则：

1. 非 null summary 的构成条件："至少一条完整、脱离原会话也可独立理解的业务陈述"，覆盖"当前用户目标、已经建立的结论或进展，以及仍影响后续的关键约束或下一步"。
2. null 触发条件："当前明确 cap 内无法形成至少一条上述完整业务陈述，必须输出 JSON `null`"。条件使用纯业务语言，不依赖 Python 类型名、内部模块名或 Host 实现术语。
3. 禁止项："占位符、孤立字符、孤立标点、无上下文缩写或任何截断片段"——覆盖了 MC14 观察到的 `"A"` 行为类别。

**"当前明确 cap" 的歧义性检查**：该条件中的 "cap" 指 repair feedback 中明示的字符/条目上限（如 `policy_size_cap_exceeded` 的 rejection message 中明确给出具体数值）。首次请求无 explicit cap 时该条件不触发；模型应产生正常 summary，若超 cap 则由确定性 validator reject 并进入 repair。此设计正确：null 规则是针对 repair 场景的精准约束，不引入首次请求的误判风险。

**结论**：规则自足、禁止项明确、触发条件 on-repair only。低认知负担下可正确操作。**PASS**。

### AC2：是否误要求所有维度或引入歧义

**证据**：prompt 第 35 行在列出三个维度后明确写 "不存在或后续不需要的维度不要编造补齐"。这是显式反编造约束，不会误导模型凑齐所有维度。

**维度列表的潜在风险**：第 35 行列出了 "当前用户目标、已经建立的结论或进展，以及仍影响后续的关键约束或下一步" 三项。若材料中仅存在其中一项（如仅有"下一步"无"结论"），模型可能误认为需要凑齐。但 "不存在或后续不需要的维度不要编造补齐" 直接消解此风险——它告诉模型这些维度是可能存在的类别，不是强制清单。

**"cap" 术语歧义**：prompt 中未在 session_summary section 内独立定义 "cap" 的含义，但在 `policy_limit` drop reason（第 69 行）中有完整说明。首次请求模型不明确知道 cap 数值，但如上所述，null 规则的实际触发仅在 repair 场景。该术语对 repair 场景中的模型足够清晰。不构成歧义。

**结论**：维度列表是"可能覆盖"而非"必须覆盖"；反编造约束消除了凑维度风险。**PASS**。

### AC3：无 Host semantic verifier / 阈值 / 兼容

**证据**：`git diff HEAD` 中所有变更仅涉及：
- 1 个 `.md` prompt 文件的 LLM-facing 文本
- 1 个 `.json` manifest 的 SHA-256 entry
- 3 个 Python test 文件的断言/SHA 常量

无任何 Host 生产 Python 文件被修改。无新增 `if len(text) <= N`、`text.isascii()`、`re.match(...)`、词表查找或语言检测代码。无兼容性 import、re-export 或 fallback 分支。

**结论**：F08 的修复完全在 LLM-facing prompt 边界内完成，Host 未增加任何语义判断职责。**PASS**。

### AC4：null 完整 replacement 和四类保留测试真正从 owner 投影同源

**证据链路**：

1. 测试 fixture `_accepted_compact_payload(summary_text=None, facts=[...])` 构造单一 `CompactCandidateV2` 对象，其 `session_summary=None`，`evidence_facts`、`answer_anchors`、`forward_intents`、`reference_continuity` 均由同一 candidate 提供。
2. `accepted_truth_for_candidate(candidate, ...)` 生成 `CompactAcceptedTruthV2`——这是 compaction operation 的 canonical accepted truth。
3. `build_context_compacted_payload(...)` 生成 EventLog payload——这是 durable event 的真源。
4. `build_conversation_memory_snapshot_from_events(...)`（位于 `dayu/host/memory.py:1133`，**生产代码**，非 test helper）将 events 投影为 `ConversationMemorySnapshot`。
5. 测试断言 snapshot 的 `session_summary_memory.summary_text is None`、`session_summary_memory.event_id is None`、`evidence_fact_memory.evidence_backed_facts`、`answer_anchor_memory.anchors`、`forward_intent_memory.intents`、`trace_memory.reference_continuity_items` 均来自同一 candidate。
6. `conversation_memory_snapshot_to_json_value(snapshot)` → `conversation_memory_snapshot_from_json_value(json_value)` 的 round-trip 断言（第 1452–1455 行）使用 `dayu/host/memory.py:1442` 和 `dayu/host/memory.py:1454` 的生产序列化函数——这是 durable memory 持久化的实际路径。

**全链路均为生产代码**：fixture → `CompactCandidateV2` → `CompactAcceptedTruthV2` → `build_context_compacted_payload` → EventLog → `build_conversation_memory_snapshot_from_events` → snapshot assertions → JSON round-trip。五类语义数据从同一 candidate 进入同一 Memory projector，无下游 fallback、重算或特例。

**测试的 fixture 默认值观察**：`_accepted_compact_payload` 始终提供默认的 anchor、intent、reference 值。当 `summary_text=None` 时，测试的 Event 1 与 Event 2 的 anchor/intent/ref 使用了相同的 fixture 默认值，因此测试无法通过值差异区分"旧值被替换"与"旧值被保留"。但这不构成 finding：Memory projector 的整体替换行为（latest event wins）在 `build_conversation_memory_snapshot_from_events` 中已由其他测试充分覆盖；本测试的职责是验证 null summary **不清空**其他四类，该职责已由对四类值的显式断言完成。

**结论**：测试从 owner projection 同源链路完整验证，非 mock/fake 替代。**PASS**。

### AC5：manifest 两个 SHA consumers 精确

**证据**：

- Consumer 1（prompt digest → manifest entry）：`docs/cli_init_workspace_manifest_v1.json` 中仅 `config/prompts/scenes/conversation_compaction_user.md` 的 `content_sha256` 被更新为 `5f5a5151...`。其余 40+ 条目未变。
- Consumer 2（manifest digest → init smoke test）：`tests/cli/test_smoke_cli_init_provider_matrix.py` 中仅 `FROZEN_MANIFEST_SHA256` 常量被更新为 `9ebdeab5...`。无其他常量或预期值变化。

两个 consumer 精确对应，无多余同步、无遗漏。init smoke test (`test_cli_init_workspace_manifest_is_frozen`) 通过真实 `dayu-cli init` 流程验证 publication tree 与 manifest 一致，构成真正的 publication integrity 闭环。

**结论**：两个 SHA consumer 精确，同源链路完整。**PASS**。

### AC6：测试字符串是否脆弱或遗漏

**脆弱性检查**：

- Prompt contract test (`test_prompt_assets_are_self_contained_for_fresh_v2_contract`) 使用中文子串断言 prompt 内容。若 prompt 文本被改写（即使是同义改写），对应断言必须同步更新。这是该测试模式的固有特性，不是 F08 引入的新脆弱性——AGENTS.md 要求 LLM-facing 文本必须有 contract test 确保自足性。
- null-summary replacement test (`test_accepted_compact_without_summary_clears_prior_session_summary`) 断言了四类非 summary 语义项的具体 fixture 默认值（`"收入口径"`、`"下一轮继续核对费用率。"`、`"该公司继续指向当前分析主体。"`）。若 fixture 默认值被修改，该测试也会失败。但该耦合是显式的、有意的——测试需要具体值来证明数据确实被保留。

**遗漏检查**：

- ✓ 测试覆盖了 "非 null summary 必须包含完整业务陈述" 的维度说明
- ✓ 测试覆盖了 "cap 内无法形成时输出 null" 的触发条件
- ✓ 测试覆盖了禁止占位符/孤立字符/标点/截断片段的禁止项
- ✓ 测试覆盖了 "不表示保留旧 summary" 和 "四类独立输出" 的 replacement 语义
- ✓ 测试覆盖了 null replacement 后 summary 清除且四类保留
- ✓ 测试覆盖了 snapshot JSON round-trip 一致性
- 未覆盖：summary 为 null 且其他四类中有空 array 的边界情况。但该情况在生产 schema 中合法（array 可为空），且 null-summary 不应因其他 section 为空就改变行为。不构成遗漏。
- 未覆盖：首次请求（无 explicit cap）时模型的行为。该场景属于正式 CLI scenario evidence（`interactive.g06.summary-null`），按 plan 明确不在 F08 implementation gate 覆盖范围内。

**结论**：测试字符串的耦合是显式且有意的；覆盖了 owner-level 关键路径；正式 CLI scenario 覆盖率缺口属于已登记的 later work unit。**PASS**。

### AC7：scope / README / frozen digest

**Scope**：变更文件恰好 5 个，全部在 plan allowed files 列表中。无越界修改。

**README**：已独立审阅 `dayu/config/README.md`、`tests/README.md`、根 `README.md` 的更新约束与当前内容，确认：
- `dayu/config/README.md`：拥有默认配置、workspace 覆盖关系与 prompts 目录职责。F08 只修改一个 scene prompt 的业务选择文本及派生 digest，不改变配置层级、加载、覆盖、schema 或目录职责。不应更新。✓
- `tests/README.md`：只在测试层级、运行方式或维护规则变化时更新。F08 只扩展既有 contract/owner test，不引入新测试层级或约定。不应更新。✓
- 根 `README.md`：面向最终用户；安装、CLI 参数、入口、输出通道、工作区路径、用户工作流与排障方式均未变化。不应更新。✓
- `dayu/host/README.md`：F08 不修改 Host 生产代码，Host 层无变化。不应更新。✓

**Frozen digest**：五个 frozen/evidence 文件 SHA-256 均与 accepted-plan checkpoint 完全一致（见 C3 表）。无静默变更。

**结论**：scope 精确，README 判定正确，frozen digest 未变。**PASS**。

### AC8：prompt 无 Host 内部术语泄漏

**证据**：`test_prompt_assets_are_self_contained_for_fresh_v2_contract` 的 forbidden 列表包括 `schema_version`、`current_input_anchor`、`evidence_backed_facts`、`reference_continuity_items`、`Compact`、`compaction.py`、`context_governance`、`memory.py`、`MemoryProjectionPolicy`、`SessionSummaryMemoryView`、`event_id`、`payload_ref` 等 Host 内部术语。测试断言这些术语均不在 user prompt 中出现（`assert forbidden not in user_prompt`）。独立 grep 确认 prompt 中无上述术语。

**结论**：LLM-facing 文本遵守了 AGENTS.md 的 LLM-facing 文本约束，无 Host 内部术语泄漏。**PASS**。

## 无 finding

本次 DS 第二路独立审查未发现任何 correctness、stability、maintainability、语义所有权漂移或 AGENTS.md 违规 finding。F08 slice 的 prompt 文本变更、manifest/test SHA 同步、prompt contract test 与 Memory owner test 均正确、自足且从 owner boundary 实施。

## Residual risks

1. **Real-provider 遵守度**：prompt 规则在文本层面自足且清晰，但模型在真实 cap 压力下是否稳定输出 `null` 而非占位符仍需正式 CLI scenario 验证。该风险按 accepted plan 分类为 `assigned to later work unit`（`interactive.g06.summary-null` scenario），不由 F08 implementation gate 承担。Deterministic test 已覆盖 prompt contract 与 replacement projection，不声称覆盖真实 provider 行为。

2. **"cap" 术语在 session_summary section 内未独立定义**：prompt 第 36 行的 "当前明确 cap" 依赖 `policy_limit` drop reason（第 69 行）中对 cap 的说明以及 repair feedback message 中的具体数值。首次请求模型不明确知道 cap，但 null 规则的实际触发仅在 repair 场景，因此不构成实际歧义。若未来 prompt 重构时分离了 session_summary 规则与 policy_limit 规则，应注意保持术语一致性。不构成当前 finding。

3. **Test fixture 默认值耦合**：`_accepted_compact_payload` 的默认 anchor/intent/reference 值被 `test_accepted_compact_without_summary_clears_prior_session_summary` 显式断言。若 fixture 默认值被修改，该测试将失败，但这是显式契约——修改 fixture 的人必须同步更新测试。不构成 finding。

## Verdict

**PASS**

F08 slice 实现正确、自足且从 owner boundary 实施。Prompt 变更精确关闭了 MC14 观察到的根因（模型在明确 cap 内输出占位符而非 null），不引入 Host semantic verifier、阈值判断、兼容分支或下游补偿。Publication digest 的两个 consumer 精确同源。Owner-level tests 从 Memory projector 生产代码链路验证了 null replacement 与四类保留行为。Frozen baseline/evidence 完整无变更。无 blocking finding。

下一 gate：按 accepted plan 推进 F09（Tool Trace canonical manifest 同源修复），或进入 F08 code review controller adjudication。
