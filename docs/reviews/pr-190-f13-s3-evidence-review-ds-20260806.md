# PR 190 F13 S3 Evidence Authenticity Review (DeepSeek)

**Reviewer:** F13 S3 DeepSeek adversarial reviewer
**Date:** 2026-08-06
**Design doc:** `docs/gateflow/pr-190-f13-s3-validation-and-real-observation-20260806.md`
**Evidence root:** `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX`
**Target commit:** `e4c290c88e5ce853251e236e4422023889f6884a`
**Verdict:** ACCEPTED（附记录级修正建议）

## 审查范围与方法

本审查仅针对 evidence authenticity，不评判业务正确性（那是 Oracle 职责）。逐项交叉验证：run-manifest → execution-index → 8 个 PTY segment 的 command/terminal/tool-trace → harness-source → 3 个 artifact → SQLite memory snapshot → 最终 public Tool Trace。所有字段名、值和时序均从 immutable evidence root 直接提取。

## 逐项验证结果

### 1. 真实 CLI / provider / tool / corpus 可核实性：通过

- CLI SHA-256 `ab7d7ba9f7...` 与 manifest 一致。
- harness-source.py（SHA-256 `ce659ce2...`）证实调用 production `dayu-cli interactive` PTY，无 mock/fake。
- 所有 8 个 segment 的 `command.json` 均记录 `--model mimo-v2.5-pro-plan`；public trace 记录 `effective_provider=mimo`、`effective_model=mimo-v2.5-pro`。
- 真实 tool 调用可追溯：EventLog sequence 60 的 `TOOL_RESULT_ACCEPTED` 对应 `read_section`，其 ref `evidence:event-tool-result-accepted-2527bd9c...` 出现在所有 durable 投影中。
- corpus 路径 `/Users/leo/workspace/.dayu-cli-ci/prompt-financial-20260731TqJFtTp/workspace/portfolio` 在 harness 与 manifest 中一致。
- `mock_fake_provider_or_tool: false` 声明可核验：无任何 segment 使用 fake/mock provider 或 tool。

### 2. 场景名与实际 artifact 时序区分：通过（设计文档自身已区分）

- F13O02 场景名为 `first-compact` 但未生成 compaction artifact（terminal 显示为普通助手回复，无 `CONTEXT_COMPACTED` 事件，filesystem diff 无 `compaction/sha256/` 新条目）。
- 首个 accepted artifact `d064f72a...` 实际由 F13O04 生成（filesystem diff 确认 `created: [.dayu/artifacts/compaction/sha256/d0/...]`）。
- 第二个 artifact `d7ff3e7f...` 由 F13O06 生成（cap-constrained）。
- 第三个 artifact `5fd4c26f...` 由 F13O07 生成（诊断变体）。
- 设计文档第 89-103 行已正确区分场景名与真实时序。

### 3. 21.7% 是否进入 compact boundary：通过

- 首个 artifact 的 `source_boundary`（7 个 atom 的列表）经 JSON 全文搜索确认不含 "21.7" 或 "18.2"。
- 所有 3 个 artifact 的 `accepted_replacement.evidence_facts` 中，5 个 claim 均不含 "21.7" 或 "18.2"。
- SQLite `host_memory_snapshots`（最终 checkpoint sequence 209）的 `evidence_fact_memory.evidence_backed_facts`（5 条）均不含 "21.7" 或 "18.2"。
- 21.7% 仅出现在 snapshot 的 user_window 区域（标记为"用户文本输入，无工具证据"），未进入 durable formal EvidenceFact。
- 设计文档第 159-164 行的限制声明准确：首个 artifact 的 source_boundary 未选入该修正，因此不能将本 observation 扩大解释为"Host typed reject 已验证"。

### 4. cap 是否真的 repair：通过（设计文档已诚实说明）

- F13O06 setup 确认 `session_summary_char_cap: 1`（`NULL_SUMMARY_CAP = 1`）。
- F13O06 terminal 显示正常 accepted compaction（`CONTEXT_COMPACTED` 而非 `CONTEXT_COMPACTION_FAILED`）。
- 第二个 artifact `d7ff3e7f...` 的 `accepted_proposal` 中模型直接输出合法 retain proposal（`evidence_facts: []`，5 个旧 claim 通过 Host 原子保留）。
- 设计文档第 195-197 行正确说明："provider 在 attempt 1 直接输出 session_summary=null，Host 接受；没有 repair feedback 或第二次 attempt"。
- **结论：** 这不是 repair observation，而是 cap=1 时模型直接合规的 observation。设计文档未 overclaim。

### 5. 故意无效 prompt 是否真的 exhaustion：部分 gap（execution-index 标签过宽）

- F13O07 setup 将 `conversation_compaction.md` 替换为 `只输出纯文本 F13_INTENTIONAL_INVALID，禁止输出 JSON。`。
- F13O07 tool-trace 显示：compaction **成功**（`CONTEXT_COMPACTED` at seq 183, attempt 1），**无** `CONTEXT_COMPACTION_FAILED`。
- F13O07 terminal 显示正常助手回复："F13_FAILURE_PROBE = 海鸥 → 状态：探针/测试输入"，无 compact 失败迹象。
- EventLog 全量：`CONTEXT_COMPACTION_REQUESTED` 3 次，`CONTEXT_COMPACTED` 3 次，`CONTEXT_COMPACTION_FAILED` 0 次。
- **问题点：** execution-index.json 中 F13O07 的 coverage 标签包含 `real-provider-invalid-output`、`bounded-repair-exhaustion`、`fallback-and-memory-non-pollution`——这三个标签均未在真实 observation 中实现。provider 未输出 invalid output；未触发 repair exhaustion；未进入 fallback 路径。
- **缓解：** 设计文档第 197-201 行已明确声明："不能声称 repair exhaustion/fallback/non-pollution 已由真实 CLI 证明"。design doc 本体未 overclaim，但 execution-index 的 coverage 标签与实际行为不一致。
- **建议修正：** 更新 execution-index 中 F13O07 的 coverage 标签为 `prompt-variant-attempt-1-accepted`、`compaction-survived-diagnostic-prompt`、`no-compaction-failure-triggered`。

### 6. formal scenarios 是否仍 unadjudicated：通过

- run-manifest: `formal_scenario_status: "unadjudicated"`、`evidence_rule: "observation only; no PASS/accepted adjudication"`。
- execution-index: `formal_scenario_status: "unadjudicated"`。
- harness-source 第 517 行：`"formal_scenario_status": "unadjudicated"`。
- 设计文档第 212-225 行明确列出 Oracle 仍需独立补跑的三条 replacement scenarios。
- 无任何文件声称 observation = formal adjudication。

### 7. 三路 durable/public 投影是否同源：通过

三路投影的 5 个 evidence fact 的 canonical ref 完全一致：

| 投影路径 | 字段名 | 值（所有 5 个 fact 相同） |
|---|---|---|
| Artifact（`d064f72a...`） | `accepted_replacement.evidence_facts[*].canonical_evidence_refs` | `["evidence:event-tool-result-accepted-2527bd9c..."]` |
| Memory（snapshot seq=209） | `evidence_fact_memory.evidence_backed_facts[*].evidence_refs` | `["evidence:event-tool-result-accepted-2527bd9c..."]` |
| Public Tool Trace | `compactor_responses[*].accepted_evidence_facts[*].canonical_evidence_refs` | `["evidence:event-tool-result-accepted-2527bd9c..."]` |

- EventLog 直接关联：sequence 60 = `TOOL_RESULT_ACCEPTED`，tool=`read_section`。
- 第三个 artifact 的 `terminal_event_id` = `event-context-compacted-742dcbd1fbde416f868b274ceec9ba50`，与 public trace 一致。
- claim 文本三路一致（5 条 claim 相同）。
- **微小记录差异：** Memory 使用字段名 `evidence_refs`；artifact 和 public trace 使用 `canonical_evidence_refs`。值一致，不影响语义同源性，但建议未来统一字段名以降低审计成本。

### 8. 其他交叉验证

| 设计文档声明 | 证据验证 | 结果 |
|---|---|---|
| run-manifest SHA-256 匹配 | 直接计算确认 | ✅ |
| CLI SHA-256 匹配 | 直接计算确认 | ✅ |
| harness SHA-256 匹配 | 直接计算确认 | ✅ |
| 8 个 segment exit_code=0 | 全部 confirmed | ✅ |
| harness_invalid_count=0 | 全部 confirmed | ✅ |
| git_status_porcelain 为空 | manifest 记录 `""` | ✅ |
| 2493 tests passed | test output 不在 evidence root（属于 CI） | ⚠️ 未直接验证 |
| pyright 0 errors | pyright output 不在 evidence root | ⚠️ 未直接验证 |
| public Tool Trace SHA-256 `5c63586e...` | 需外部验证 | ⚠️ 未直接验证 |
| SQLite backup SHA-256 `d52c10a9...` | 需外部验证 | ⚠️ 未直接验证 |
| schema_version=5 | 所有 3 个 artifact confirmed | ✅ |
| EventLog 3 个 CONTEXT_COMPACTED（133/165/183） | SQLite + tool trace confirmed | ✅ |
| 最终 Memory checkpoint 209 | SQLite snapshot confirmed | ✅ |
| 5 个 EvidenceFact，0 个 empty evidence_refs | SQLite + public trace confirmed | ✅ |

### 9. 未直接验证的声明（不构成 gap，但需注明）

- tests、pyright、ruff、compileall：这些是 CI 运行时验证，不在 immutable evidence root 中。存在合理性（设计文档记录了命令和结果），但不能从 evidence root 直接核实。
- 设计文档行首 artifact SHA-256、public Tool Trace SHA-256、SQLite SHA-256：这些是设计文档写入时的文件快照指纹。evidence root 中的文件可能与文档记录一致（设计文档引用时它们已存在），但审查未独立计算这些 hash。

## 总评

设计文档对自身局限性的诚实程度高于典型水平：它明确区分 observation vs formal adjudication、明确指出 repair/cap exhaustion/failed compaction 未被真实观察到、明确将 21.7% boundary 限制在普通窗口而非 durable memory。所有可从 evidence root 直接验证的核心声明均成立。

**唯一实质性问题：** execution-index.json 中 F13O07 的 coverage 标签（`bounded-repair-exhaustion`、`fallback-and-memory-non-pollution`）与真实 observation 行为不一致——compactor 在 attempt 1 成功 accepted，未触发 repair 或 fallback。设计文档正文已正确说明此点，但 execution-index 的 coverage 字段仍保留过宽标签。

## Resolution（rereview 追加）

Controller 裁决不修改 immutable original execution-index（SHA256 `2c890d19dba720e316d0dca385dec57415c01130d294560083b7d4c1185ce003`），已新增旁路 errata：

- **Errata 文件：** `evidence/execution-index-f13-postfix.errata.json`
- **Errata SHA256：** `9de85cc34c6dba8a929841178848369f370a457e6378b3a77462a23caf3f336c`
- **Schema：** `dayu.observation.execution_index_errata.v1`
- **`original_record_mutated`：** `false`

Errata 逐项更正 F13O07 三个 intent coverage 标签：

| 原始 intent 标签（保留不删） | 更正为 observed 标签 |
|---|---|
| `real-provider-invalid-output` | `real-provider-compactor-attempt` |
| `bounded-repair-exhaustion` | `attempt-1-accepted` |
| `fallback-and-memory-non-pollution` | `diagnostic-did-not-trigger-repair-or-fallback` |

Errata 同时记录了 `observed_terminal_event`（`event-context-compacted-742dcbd1...`）、`observed_terminal_sequence`（183）、`observed_compaction_attempt_number`（1）、`observed_artifact`（`5fd4c26f...`），均与本审查独立验证一致。Reason 字段准确声明"provider returned a valid proposal on attempt 1. No repair, exhaustion, fallback, failed terminal, or non-pollution failure-path behavior was observed."

**Errata 方案满足原裁决条件：** 原始 immutable index 未被修改；overclaim 标签通过旁路 errata 精确更正；更正值与不可变证据一致。

## Final Verdict

**ACCEPTED** — 条件已满足。原始 execution-index 保持不可变（SHA256 `2c890d19...`），errata（SHA256 `9de85cc...`）提供 F13O07 的 observed 标签更正，不与任何 immutable evidence 冲突。
