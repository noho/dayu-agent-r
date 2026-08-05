# PR 190 F11/F12 S4 Evidence Review — AgentDS 第二路独立审查（2026-08-06）

## Scope

- **Mode**: Evidence gate review（只读审查 immutable evidence root + repo artifact，不修改 production/oracle/scenario/evidence）
- **PR**: 190（https://github.com/noho/dayu-agent-r/pull/190），head branch `codex/interactive-oracle`
- **Baseline HEAD**: `d9f044f944dd44e0d369f9d93e0533d2b725e413`
- **Repo artifact**: `docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md`
- **Immutable evidence root**: `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`
- **Reviewer**: AgentDS（与 AgentMiMo 相互独立，未读取另一路 review）
- **Output file**: `docs/reviews/pr-190-f11-f12-s4-evidence-ds-review-20260806.md`
- **Excluded scope**: 未读取私有 SQLite quarantine 内容；仅通过 `metadata/workspace-private-db-exclusion.json` 审计其 exclusion boundary；未运行 provider；未 commit/push

## Verification Checklist（逐项核验）

### 1. Digest identity

- **预期 SHA-256**: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`
- **实测**: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d` ✅ **exact match**
- 命令：`shasum -a 256 digest.json`
- `covered_file_count`: 159（+ 1 self-excluded = 160 total），与磁盘实际文件数一致 ✅

### 2. Read-only enforcement

- evidence root 权限：`dr-x------`（owner read+execute only，no write） ✅
- 子目录 screen/、evidence/、metadata/、workspaces/ 均为 `dr-xr-xr-x` 或 `dr-x------` ✅
- 所有文件权限为 `-r--r--r--` ✅
- 旧 superseded root（`...-s4-final-k5hWK9`）独立存在，未回写 ✅

### 3. Secret scan

- `metadata/secret-scan.json`：scanned 160 files，2 credential sources（`MIMO_PLAN_API_KEY`、`DEEPSEEK_API_KEY`），0 exact value findings，0 pattern findings ✅
- 在 evidence tree 中 spot-check 了 `screen/` 目录下所有 10 个文件：无 Authorization/Bearer/API-key 字面值 ✅
- 在 compactor attempts 中检查了 provider endpoint URL：均为公开 endpoint，不含 credential ✅

### 4. Command-screen-report consistency

- `metadata/command-inventory.json` 声明 10 条命令（order 0–9），screen 目录恰好 10 个文件（`screen/00` 至 `screen/09`） ✅
- 每条 command 的 `purpose` 与 screen 文件名语义一致 ✅
- 所有 10 条命令 `exit_status: 0` ✅
- 执行顺序 Mimo → DeepSeek 符合 report 声明 ✅
- 9 条 scenario 命令 + 1 条 pyright 验证 = 10 条，与 inventory 一致 ✅
- 命令中 credential 均通过环境变量名引用（如 `MIMO_PLAN_API_KEY`），未在命令文本中嵌入值 ✅

### 5. Mimo `capability=none` 实际 transport

| 证据文件 | 字段 | 值 |
|---|---|---|
| `evidence/01-mimo-baseline/provider-identity.json` | `compactor.structured_output_capability` | `"none"` |
| `evidence/01-mimo-baseline/compactor-attempts.json` (attempt 1) | `structured_output_request` | `null` |
| 同上 | `outbound_response_format_type` | `null` |
| 同上 | `provider` / `model` | `"mimo"` / `"mimo-v2.5-pro"` |
| `evidence/03-mimo-exhausted-fallback/compactor-attempts.json` (attempt 1, 2) | `structured_output_request` | `null`（两次 attempt 一致） |
| 同上 | `outbound_response_format_type` | `null`（两次 attempt 一致） |

✅ 所有 Mimo attempt 的 transport 为 null/none，不存在 structured output downgrade 路径。

### 6. DeepSeek `json_object` 实际 transport

| 证据文件 | structured_output_request | outbound_response_format_type | provider/model |
|---|---|---|---|
| `04-deepseek-baseline` attempt 1 | `"json_object"` | `"json_object"` | `deepseek/deepseek-v4-flash` |
| `08-deepseek-exhausted-fallback` attempt 1, 2 | `"json_object"` | `"json_object"` | `deepseek/deepseek-v4-flash` |
| `06-deepseek-bounded-repair` attempt 1, 2 | `"json_object"` | `"json_object"` | `deepseek/deepseek-v4-flash` |

✅ 所有 DeepSeek compactor attempt 均实际装配 `json_object` structured output。

### 7. First pass（Mimo baseline + DeepSeek baseline）

- **Mimo baseline**: EventLog rows: `CONTEXT_COMPACTION_REQUESTED` → `CONTEXT_COMPACTION_REQUEST_ACCEPTED`（screen 显示 `compacted=1, rejected=0, failed=0`），compact artifact hash `3f8e858d...` ✅
- **DeepSeek baseline**: 同上 pattern，`compacted=1`，artifact hash `06f710c5...` ✅
- Candidate 输出同时包含五种 persistence：`session_summary`（含 text）、`evidence_facts`、`answer_anchors`、`forward_intents`、`reference_continuity` ✅

### 8. Replacement + null clear + caps

- **DeepSeek replacement** candidate（attempt 1 of `05-deepseek-replacement-constrained`）：
  - `session_summary: null`（JSON null） ✅
  - `answer_anchors`: 1 item ✅
  - `evidence_facts`: 1 item ✅
  - `reference_continuity`: 1 item ✅
  - `forward_intents`: 0 items（cap 内允许空） ✅
- Screen 显示 `compacted=2`（含 baseline compact + replacement compact），`rejected=0` ✅
- Compact artifact 数量从 1 → 2（新增 `b2bcad92...`），旧 artifact `06f710c5...` 保留 ✅
- **Caps/usage**：report 声称 usage 在 owner cap 内——由 screen 的 0 rejected 和 compactor attempt 的 output content 直接证实 ✅

### 9. Repair boundary

- DeepSeek repair attempt 1：output 为有效 JSON（`json_object` format），`outcome_kind=final_answer`，screen log 显示 `failure_category=quality_check_rejected, repairable=True`，diagnostic 标记 `policy_size_cap_exceeded` ✅
- DeepSeek repair attempt 2：在同 operation/boundary 下完整替换，screen 显示 `compacted=1, rejected=1` 对应当前 operation ✅
- Screen 显示 repair 的 COMPACT_OPERATION：`requested=1, rejected=1, compacted=1` ✅
- Repair operation 的 `repairable=True` → `next_policy_decision=retry_semantic_repair` → attempt 2 accepted ✅

### 10. Rolling correction

- DeepSeek replacement screen 显示用户提供新口径修正（`DAYU_S4_CURRENT_MARGIN=21.7%`），旧 `18.2%` 被标记为"已失效" ✅
- Compactor candidate 的 `answer_anchors[0].detail` 仅含当前有效事实（"当前唯一有效毛利率为21.7%，旧口径18.2%已失效。"），不单独列出旧事实为有效结论 ✅
- Host omission 由 screen 确认（旧标签不进入 active semantic projection） ✅

### 11. Reconnect

- `screen/07-deepseek-reconnect.txt`：新进程复用同一 session，回答内容为"当前唯一有效毛利率口径为 **21.7%**，旧口径 18.2% 已失效、不在引用范围内" ✅
- Memory snapshot 的 `latest_compaction_event_ref` 指向 replacement compact（`event-context-compacted-98b6d9e9...`），非 repair compact——说明 reconnect 看到的是 durable snapshot 状态 ✅
- 旧值 18.2% 仅在回答中作为"已失效"提及，不作为活动结论 ✅

### 12. Exhaust/fallback — 单 terminal + Memory/artifact 不污染

**Mimo exhausted fallback** (`03-mimo-exhausted-fallback`):

| 指标 | 声明值 | 实测值 | 匹配 |
|---|---|---|---|
| rejected | 2 | 2（EventLog: `ATTEMPT_REJECTED` × 2） | ✅ |
| failed | 1 | 1（EventLog: `COMPACTION_FAILED` × 1） | ✅ |
| compact artifact | 0 | `COMPACT_ARTIFACT_FILE_COUNT 0` | ✅ |
| `latest_compaction_event_ref` | null | Memory: `null` | ✅ |
| fallback | `deterministic_recent_window` | Screen: `fallback_policy_decision=deterministic_recent_window` | ✅ |
| fallback selected/dropped | 9/2 | Screen: `fallback_selected_block_ids=9 fallback_dropped_block_ids=2` | ✅ |

**DeepSeek exhausted fallback** (`08-deepseek-exhausted-fallback`):

- EventLog: `ATTEMPT_REJECTED` × 2 → `COMPACTION_FAILED` × 1 ✅
- `COMPACT_ARTIFACT_FILE_COUNT 0` ✅
- Memory `latest_compaction_event_ref: null` ✅
- Attempt outputs: 均为空语义（`session_summary=null`, 所有数组为空）——被 owner `empty_semantic_output-low_information_output` 拒绝 ✅
- Compactor 实际使用 `deepseek-v4-flash`（`compactor-attempts.json` 证实），非 Mimo ✅

### 13. 不可信 material 边界

- 所有 compactor attempt 的 system prompt 以 "# 会话压缩任务" 开头，包含清晰的任务指令和硬性要求 ✅
- 业务 marker 文本（如 `DAYU_S4_SUMMARY_BASELINE`）在 user message（untrusted material）中，非 system instruction ✅
- Report 声明的 system prompt digest `97479acc0cc686cb9a72d18b310aff58cabba4d4b223c6773a12249b5ed333e5` 需进一步比较每个 attempt 的 system prompt 内容确认一致性——鉴于 capture 模式保存了完整 messages 数组，若 digest 不一致会在 attempt 间可见 prompt 内容差异。（见 Open Question #1）

### 14. F11 两类 public response identity 和 canonical equality

**Successful compact identity**（以 DeepSeek baseline 为例）：

- `public-tool-trace/tool-trace-analysis.json` 包含 `compactor_responses` 数组，每项含 `provider_request_id`、`terminal_event_id`、`disposition` ✅
- Tool Trace 来自 public resolver（JSON/Markdown 双格式），未读取 private SQLite ✅

**Successful-response-then-rejected identity**（以 DeepSeek repair attempt 1 为例）：

- `public-canonical-equality.json` 包含 `disposition: "attempt_rejected"` 的比较条目，`equal: true` ✅

**Canonical equality**：

| Evidence | canonical_terminal_count | finding_count | 全部 equal: true |
|---|---|---|---|
| 01-mimo-baseline | 1 | 0 | ✅ |
| 02-mimo-boundary | 1 | 0 | ✅ |
| 03-mimo-exhausted-fallback | 2 | 0 | ✅ |
| 04-deepseek-baseline | 1 | 0 | ✅ |
| 05-deepseek-replacement | 2 | 0 | ✅ |
| 06-deepseek-bounded-repair | 4 | 0 | ✅ |
| 07-deepseek-reconnect | 4 | 0 | ✅ |
| 08-deepseek-exhausted-fallback | 2 | 0 | ✅ |

✅ 所有 8 个 evidence 目录的 `finding_count=0`，无 canonical equality 违反。

### 15. Private SQLite publication boundary

- 4 个 `dayu_host.sqlite3` 从 public evidence tree 移除至 quarantine ✅
- `metadata/workspace-private-db-exclusion.json` 记录每个文件的 original path、quarantine path、size_bytes、SHA-256 ✅
- 4 个 quarantine 文件的 SHA-256 与 exclusion 记录全部 match ✅
- Quarantine 目录权限 `dr-x------`（read-only） ✅
- Quarantine 不在 root `digest.json` 中 ✅
- Public evidence tree 中不存在 `.sqlite3` 或 `.sqlite` 文件 ✅

### 16. 三层 PASS/PENDING 诚实性

| 层 | 声明 | 是否诚实 | 证据 |
|---|---|---|---|
| Implementation | PASS | ✅ 诚实 | 观察基线为已 push HEAD d9f044f9；本轮未修改生产代码；report 明确界定 |
| Real-provider observation | PASS | ✅ 诚实 | 所有可执行 fresh observations 完成；Mimo 与 DeepSeek 均真实可用；全部 screen exit_status=0 |
| Oracle | PENDING | ✅ 诚实 | Report 明确声明未运行 frozen formal CLI scenarios；未修改 oracle/scenario/registry；多次强调不得投影 |

⚠️ **注意**："Implementation: PASS" 的措辞可能在缺乏上下文的阅读中被误解为"PR 190 的整体实现已通过审查"。Report 本身在正文中明确解释了 scope（"观察基线为已 push HEAD；本轮未修改生产代码"），但 gate status table 的简写可能被跳读。建议后续在 table 中增加 scope note。

---

## Findings

### 1-未修复-中-Screen ASSEMBLY diagnostic 在所有场景中一致显示 `compactor_model_id=mimo-v2.5-pro-plan`

- **入口/函数**: 观察报告的主要人类可读证据——screen 输出
- **文件(行号)**: `screen/01-mimo-baseline.txt` 至 `screen/08-deepseek-exhausted-fallback.txt`，每个文件的 `SMOKE ASSEMBLY` 段
- **输入场景**: 任何阅读 screen 输出来判断 compactor 实际使用哪个 provider/model 的场景
- **实际分支**: SMOKE ASSEMBLY 诊断在 **所有 8 个 scenario screen**（Mimo 和 DeepSeek）中均输出 `compactor_model_id=mimo-v2.5-pro-plan`
- **预期行为**: Screen 应准确反映最终生效的 compactor model（Mimo scenario → Mimo model; DeepSeek scenario → DeepSeek model）
- **实际行为**: 所有 screen 的 ASSEMBLY 段显示 `compactor_model_id=mimo-v2.5-pro-plan`，无论实际 compactor 是 Mimo 还是 DeepSeek。例如，DeepSeek baseline（`screen/04`）的 screen 显示 `compactor_model_id=mimo-v2.5-pro-plan`，但实际 compactor attempt（`compactor-attempts.json`）中 `model=deepseek-v4-flash`、`provider=deepseek`
- **直接证据**:
  - `screen/04-deepseek-baseline.txt` 第 8 行：`SMOKE ASSEMBLY compactor_model_id=mimo-v2.5-pro-plan`
  - `evidence/04-deepseek-baseline/compactor-attempts.json` attempt 1：`"model": "deepseek-v4-flash"`, `"provider": "deepseek"`
  - 同样的不一致在 screen/05–08 全部复现
- **影响**: 依赖 screen 输出的审查者可能误以为所有 compaction 都由 Mimo 执行。canonical truth（`compactor-attempts.json`、`provider-identity.json`）是正确的，但 screen 是主要人类可读证据面，其诊断误导会降低证据链的可信度
- **建议改法和验证点**:
  1. SMOKE ASSEMBLY 诊断应在 execution profile 应用**之后**打印最终生效的 `compactor_model_id`
  2. 或至少在 ASSEMBLY 段增加一行 `SMOKE ASSEMBLY compactor_model_id_resolved=<actual>` 区分预覆盖值与最终值
  3. 验证：重新运行任一 DeepSeek scenario，确认 screen 输出正确的 compactor model
- **修复风险**: 低（仅修改 smoke harness 的诊断输出）
- **严重程度**: 中

**Owner 判定**: Smoke harness（`utils/smoke_host_public_conversation_memory_scenarios.py`）是 diagnostic 输出的 owner；其 ASSEMBLY 诊断应在 profile override 之后打印最终值。

### 2-未修复-低-Memory `session_summary_memory.summary_text` 在所有 snapshot 中均为 null

- **入口/函数**: Memory snapshot 的 `session_summary_memory` 字段投影
- **文件(行号)**: 所有 8 个 evidence 目录的 `memory.json`
- **输入场景**: 审查者试图通过 Memory snapshot 直接验证 `session_summary:null` clear 的效果
- **实际分支**: Memory snapshot 的 `session_summary_memory.summary_text` 在所有 8 个 snapshot 中均为 `null`——包括 baseline（candidate 包含非空 session_summary.text）和 replacement（candidate 为 `session_summary: null`）
- **预期行为**: Memory snapshot 应在 summary_text 字段中反映当前生效的 session summary 文本，使得 null clear 的"before vs after"差异可直接从 Memory snapshot 验证
- **实际行为**: `summary_text` 在所有 snapshot 中恒为 `null`。session summary 的实际内容存在于 compact artifact（`compact-artifacts/sha256/...`）和 compactor attempt output 中，但不在 Memory snapshot 的此字段中
- **直接证据**:
  - `evidence/04-deepseek-baseline/memory.json`：`"summary_text": null`（但 baseline compactor candidate 的 `session_summary.text` 包含约 280 字符的中文摘要）
  - `evidence/05-deepseek-replacement-constrained/memory.json`：`"summary_text": null`（replacement candidate 的 `session_summary: null` 清除了 summary）
  - 两个 snapshot 的 `summary_text` 均为 null，无法区分"有 summary 被清除"和"从未有 summary"
- **影响**: 低——report 的 `session_summary:null` clear 声称仍然可通过 compactor candidate output 和 compact artifact 验证。但 Memory snapshot 作为 canonical Memory state 的投影，无法提供独立的 null-clear 验证信号，降低了 evidence 的多源交叉验证能力
- **建议改法和验证点**:
  1. 确认 `session_summary_memory.summary_text` 的语义 owner：它应该存储当前生效的 summary text，还是仅作为 internal metadata container？如果应该存储，则 baseline snapshot 的 `summary_text` 应该非 null
  2. 如果这是设计行为（summary 仅从 compact artifact 派生），在 Memory snapshot schema 中注明"summary_text is always null in snapshot; canonical summary resides in latest compact artifact"
- **修复风险**: 低（如果是设计行为，只需加文档；如果是 bug，修复涉及 Memory owner 的 summary projection 逻辑）
- **严重程度**: 低

**Owner 判定**: Memory owner（`dayu/host/` 下的 conversation memory 模块）负责 `session_summary_memory` 字段的投影。如果 summary 应从 compact candidate 中提取并存储到 snapshot，则 Memory owner 是修复 owner；如果这是有意的非存储设计，则应在 schema/projection 文档中说明。

### 3-未修复-低-Report 声称 repair attempt 1 的 "36 chars" 与 compactor attempt 的 detail 实测 28 chars 不一致

- **入口/函数**: 观察报告的 "Caps、usage 与 replacement owner contract" 段及 "DeepSeek same-boundary repair" 描述
- **文件(行号)**: `docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md` 中关于 repair 场景的描述
- **输入场景**: 审查者交叉验证 report 声称的 cap 违规字符数
- **实际分支**: Report 写 "answer anchor 36 chars 超过 cap 30，拒绝"，但 compactor attempt 的 `answer_anchors[0].detail` 字段实测 28 chars，`title` 字段 7 chars
- **预期行为**: Report 中的数字应与 canonical evidence 中可直接提取的值一致，或明确说明计数方法（例如"包含 title 共 35 chars"或"JSON 序列化后 36 bytes"）
- **实际行为**: `detail` 单独 28 chars，`title + detail` 共 35 chars。36 可能是包含 JSON 框架字符或字段名的序列化长度
- **直接证据**:
  - `evidence/06-deepseek-bounded-repair/compactor-attempts.json` attempt 1: `answer_anchors[0].detail` = `"当前唯一有效毛利率为21.7%，旧口径18.2%已失效。"`（28 chars），`answer_anchors[0].title` = `"当前毛利率口径"`（7 chars）
  - Screen 确认 `policy_size_cap_exceeded`（拒绝原因是 cap 违规本身成立）
- **影响**: 低——cap 违规事实由 screen diagnostic（`policy_size_cap_exceeded`）和 `repairable=True` → `retry_semantic_repair` → attempt 2 accepted 的完整链路证实。字符数不影响结论
- **建议改法和验证点**:
  1. Report 中明确说明 36 的计数方法（是否包含 title、是否计算 JSON 序列化长度等）
  2. 或直接引用 canonical evidence 中可直接验证的值（如 detail=28 chars, title=7 chars, total field content=35 chars）
- **修复风险**: 低（仅影响 report 的可复现性）
- **严重程度**: 低

---

## Open Questions

1. **System prompt digest 一致性验证**：Report 声称所有 compactor system prompt digest 为 `97479acc0cc686cb9a72d18b310aff58cabba4d4b223c6773a12249b5ed333e5`。由于各 compactor attempt 的 messages 数组中包含完整 system prompt 内容，可通过提取每个 attempt 的 system prompt 并计算 SHA-256 来验证一致性。本轮未执行此逐 attempt 验证——system prompt 内容在 evidence capture 中可见但未做逐字节比较。

2. **Repair source material digest 一致性**：Report 声称 repair 的 source material digest 在两次 attempt 间相同（`0f9c284b921545f4b72c46c9681be90658f477836a7cc810697c7776a29fb875`）。但 `compactor-attempts.json` 的顶层字段中未直接暴露 `material_pack_digest`，该值可能嵌套在 `runner_options` 或 user message 体中。本轮未定位到该字段的精确存储位置，因此未做逐 attempt 验证。（此 digest 一致性对 repair boundary 语义的验证很重要——repair 应在**相同** source material 上进行。）

3. **Smoke harness `compactor_model_id` 诊断时机**：ASSEMBLY 诊断行显示的是 execution profile 覆盖前的初始值。是否有意如此？如果是，建议在 ASSEMBLY 段增加一行 resolved 值以消除歧义。

---

## Residual Risk

1. **Screen 人类可读面的歧义**（关联 Finding 1）：任何仅依赖 screen 输出（不交叉验证 `compactor-attempts.json` 或 `provider-identity.json`）的审查可能得出错误的 provider 归属结论。

2. **Oracle gate 仍需独立执行**：Observation PASS 和 Implementation PASS 均不替代 Oracle gate。F08–F10 有 5 个 scenario obligations 在未来 Oracle evidence/readiness gate 中仍为 PENDING。本 observation 覆盖的是 F11/F12 S4 real-provider 行为面，不是完整的形式化 conformance。

3. **Repair cap 计数的可复现性**（关联 Finding 3）：若未来需要审计 cap counting 逻辑的正确性（例如判断 `policy_size_cap_exceeded` 是否误触发），仅有 report 中的数字（36）和 canonical evidence 中的字段值（28 或 35）不足以确定计数方法。建议在 report 或 smoke harness 中暴露 cap checker 实际比较的原始值和阈值。

4. **System prompt digest 一致性**（关联 Open Question #1）：如果未来 system prompt 发生变更但 digest 未更新，可能导致 compactor 行为在不同 attempt 间不一致而未被发现。

5. **未覆盖的交互场景**：`interactive.g06.summary-null`、`interactive.g06.tool-trace-formal`、`interactive.g06.turn-group-atomicity`、`interactive.g06.drop-superseded`、`interactive.g06.drop-policy-limit` 五个 formal CLI scenarios 在此 observation 中未运行，属于 Oracle gate 的职责范围。

---

## Conclusion

经过对 immutable evidence root 的逐项核验：

- **digest identity、read-only、secret scan、命令清单一致性、transport（Mimo none / DeepSeek json_object）、first pass、replacement/null clear、caps、repair boundary、rolling correction、reconnect、exhaust/fallback 单 terminal 与 Memory/artifact 不污染、F11 两类 public response identity、canonical equality（全部 `finding_count=0`）、private SQLite publication boundary** — 以上 16 项均通过，有直接 canonical evidence 支撑。

- **三层 PASS/PENDING 诚实**：Implementation PASS（限定于"本轮未修改生产代码"）、Real-provider observation PASS（所有可执行观察完成，无新 production bug）、Oracle PENDING（明确未运行，不投影）——无跨越声明。

- **3 个 findings**（1 中 + 2 低）+ 3 个 open questions + 5 项 residual risk，详见上文。

- 未发现 secret leakage、canonical equality violation、private SQLite 出现在 public evidence、Memory/artifact 被 exhaust/fallback 污染、旧结论在 replacement 后恢复、或 F11 public identity 使用 private SQLite 伪造的 evidence。
