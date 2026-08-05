# PR 190 F11/F12 S4 Evidence Re-Review — MiMo 独立复核（2026-08-06）

## Scope

- **Mode**: Evidence gate re-review（只读审查 immutable evidence root + repo artifact，不修改 production/oracle/scenario/evidence）
- **PR**: 190（https://github.com/noho/dayu-agent-r/pull/190），head branch `codex/interactive-oracle`
- **Baseline HEAD**: `d9f044f944dd44e0d369f9d93e0533d2b725e413`
- **Repo artifact**: `docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md`
- **Immutable evidence root**: `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`
- **Expected digest SHA-256**: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`
- **Review inputs**:
  - MiMo 初审：`docs/reviews/pr-190-f11-f12-s4-evidence-mimo-review-20260805.md`
  - DS 初审：`docs/reviews/pr-190-f11-f12-s4-evidence-ds-review-20260806.md`
  - 总控裁决：`docs/reviews/pr-190-f11-f12-s4-evidence-review-adjudication-20260806.md`
  - Fix artifact：`docs/reviews/pr-190-f11-f12-s4-evidence-fix-20260806.md`
  - 修正后 observation：`docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md`
- **Excluded scope**: 未读取私有 SQLite quarantine 内容；未运行 provider；未 commit/push
- **Output file**: `docs/reviews/pr-190-f11-f12-s4-evidence-mimo-rereview-20260806.md`

## 结论

**PASS**。修正后 observation artifact 的所有关键声明均与 immutable evidence root 中的 machine-readable canonical data 一致。总控对 MiMo-01、DS-01/02/03 的拒绝裁决有直接证据支撑。未发现实质性问题。

---

## 逐项核验

### 1. Digest identity

- **预期**: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`
- **实测**: `shasum -a 256 digest.json` → `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d` ✅ **exact match**
- 文件数：159 covered entries + 1 self-excluded = 160 total ✅

### 2. Read-only enforcement

- evidence root 权限：`dr-x------` ✅
- evidence 子目录：`dr-xr-xr-x` ✅
- 所有文件：`-r--r--r--` ✅

### 3. MiMo-02 已改为 canonical operation/frozen_material_list_digest

**裁决：已正确修复 ✅**

- 修正后 observation（行 51）引用：
  - operation: `event-context-compact-requested-7aea6b1297414d9fb79656dd80b254ff`
  - `payload.frozen_material_list_digest`: `sha256:b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee`
- 直接 evidence 核验：
  - `evidence/06-deepseek-bounded-repair/compact-eventlog.json` seq 318 `CONTEXT_COMPACTION_REQUESTED`：`event_id=event-context-compact-requested-7aea6b1297414d9fb79656dd80b254ff`，`frozen_material_list_digest=sha256:b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee` ✅
  - seq 321 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`（attempt 1，`failure_category=quality_check_rejected`）绑定同一 `operation_id` ✅
  - seq 322 `CONTEXT_COMPACTED`（`accepted_attempt_number=2`）绑定同一 `operation_id` ✅
- 旧不可定位 digest `0f9c284b...` 已从 observation 中移除 ✅

### 4. Fallback terminal 9/2 与 post-dispatch Memory 8 不再混淆

**裁决：边界已正确区分 ✅**

- `evidence/03-mimo-exhausted-fallback/compact-eventlog.json`：`CONTEXT_COMPACTION_FAILED.payload.fallback_input_window` 中 `selected_block_ids` count=9、`dropped_block_ids` count=2 ✅
- `evidence/03-mimo-exhausted-fallback/memory.json`：`snapshot.trace_memory.selected_recent_window` count=8，`dropped_recent_window` key 不存在 ✅
- 修正后 observation（行 30）明确区分：
  - "canonical `CONTEXT_COMPACTION_FAILED.payload.fallback_input_window`（失败 terminal 的 input boundary）记录 fallback=`deterministic_recent_window`、selected=9、dropped=2"
  - "dispatch 完成后的 `memory.json.snapshot.trace_memory.selected_recent_window` 为 8 items，是另一投影，不是该 selection ledger，也不拥有 `dropped_block_ids`"
- 两个投影的 owner 边界描述准确 ✅

### 5. Selector 与 actual identity 边界正确

**裁决：边界已正确区分 ✅**

- `screen/04-deepseek-baseline.txt` 行 9：`SMOKE ASSEMBLY compactor_model_id=mimo-v2.5-pro-plan`（配置 selector id）
- `evidence/04-deepseek-baseline/compactor-attempts.json` attempt 1：`provider=deepseek`、`model=deepseek-v4-flash`（actual identity）
- 修正后 observation（行 52）明确说明：
  - "`SMOKE ASSEMBLY compactor_model_id=mimo-v2.5-pro-plan` 是 assembly 配置 selector；DeepSeek workspace 的 `config/models.json` 令该 selector `extends=deepseek-v4-flash`"
  - "actual provider/model truth 由 `provider-identity.json`、`compactor-attempts.json`、public Tool Trace 与 canonical terminal 共同给出"
  - "不能从 selector 字符串反推真实调用身份"
- Mimo baseline：`provider=mimo`、`model=mimo-v2.5-pro`、`structured_output_capability=none`、`structured_output_request=None`、`outbound_response_format_type=None` ✅
- DeepSeek baseline：`provider=deepseek`、`model=deepseek-v4-flash`、`structured_output_request=json_object` ✅

### 6. 36 字符公式同 owner

**裁决：公式已正确说明 ✅**

- `evidence/06-deepseek-bounded-repair/compactor-attempts.json` attempt 1：
  - `answer_anchors[0].title` = "当前毛利率口径"（7 chars）
  - `answer_anchors[0].detail` = "当前唯一有效毛利率为21.7%，旧口径18.2%已失效。"（28 chars）
  - owner 公式：`title + "\n" + detail` = 7 + 1 + 28 = **36 chars**
- 修正后 observation（行 37）已明确公式："answer anchor 按 owner 规则计为 title 7 + newline 1 + detail 28 = 36 chars，因 `36 > 30` 而 rejected"
- EventLog seq 321 记录 `failure_category=quality_check_rejected`，与 cap rejection 一致 ✅

### 7. 总控对 MiMo-01 的拒绝有直接证据

**裁决：拒绝理由成立 ✅**

- MiMo-01 要求将 `selected=9、dropped=2` 改为 `selected=8、dropped=0`
- 直接 evidence：`CONTEXT_COMPACTION_FAILED.payload.fallback_input_window` 中 `selected_block_ids` count=9、`dropped_block_ids` count=2
- `memory.json.snapshot.trace_memory.selected_recent_window` count=8 是 dispatch 后 Memory 投影，不是 terminal input boundary
- 总控裁决正确：混淆了 fallback input boundary 与 dispatch 完成后的 Memory snapshot ✅

### 8. 总控对 DS-01 的拒绝有直接证据

**裁决：拒绝理由成立 ✅**

- DS-01 要求 screen ASSEMBLY 诊断显示 DeepSeek model
- 直接 evidence：`compactor_model_id=mimo-v2.5-pro-plan` 是 assembly 配置 selector，`compactor-attempts.json` 中 actual `provider=deepseek`、`model=deepseek-v4-flash`
- F11/F12 从未把 assembly selector id 当 actual identity ✅

### 9. 总控对 DS-02 的拒绝有直接证据

**裁决：拒绝理由成立 ✅**

- DS-02 声称 baseline Memory summary 也为 null
- 直接 evidence：
  - `evidence/04-deepseek-baseline/memory.json`：`session_summary_memory.summary_text` 非空（约 280 字符中文摘要）✅
  - `evidence/05-deepseek-replacement-constrained/memory.json`：`session_summary_memory.summary_text` = null ✅
- 这正是 `session_summary:null` clear 的 before/after evidence ✅

### 10. 总控对 DS-03 的拒绝有直接证据

**裁决：拒绝理由成立 ✅**

- DS-03 声称 36 chars 与 detail 28 不一致
- 直接 evidence：owner 规则按 `title + "\n" + detail` 计量 = 7 + 1 + 28 = 36
- EventLog audit 记录 `answer_anchor_char_actual=36`，repair feedback 明示 `36 > 30` ✅
- reviewer 只统计 detail 或漏掉换行，finding 不成立 ✅

### 11. 三层 PASS/PENDING 诚实性

| 层 | 声明 | 证据 | 判定 |
|---|---|---|---|
| Implementation | PASS | 观察基线为已 push HEAD `d9f044f9`；本轮未修改生产代码 | ✅ 诚实 |
| Real-provider observation | PASS | 8 个 evidence 目录全部完成，所有 screen exit_status=0，无 provider unavailable/timeout | ✅ 诚实 |
| Formal oracle | PENDING | 明确声明未运行 frozen formal CLI scenarios，未修改 oracle/scenario/registry | ✅ 诚实 |

### 12. F11 public/canonical

- 所有 8 个 evidence 的 `public-canonical-equality.json` 均 `finding_count=0` ✅
- public Tool Trace 来自 public resolver，未读取 private SQLite ✅
- F11 两类 identity（successful compact / successful-response-then-rejected）均有 evidence 支撑 ✅

### 13. F12 transport/repair/fallback/Memory/reconnect

- **Transport**: Mimo `capability=none` / `null`；DeepSeek `json_object` ✅
- **Repair**: DeepSeek repair attempt 1 rejected（`quality_check_rejected`），attempt 2 accepted，同一 operation boundary ✅
- **Fallback**: Mimo 与 DeepSeek exhausted fallback 均为 2 rejected + 1 failed terminal，0 artifact，`latest_compaction_ref=null` ✅
- **Memory**: replacement `session_summary:null` 清除旧 summary；failed compact 不污染 Memory/artifact ✅
- **Reconnect**: `screen/07-deepseek-reconnect.txt` 复用同一 session，未恢复旧结论，当前 21.7% 事实保留 ✅

### 14. Secret scan / digest 不变

- `metadata/secret-scan.json`：0 exact_value_findings，2 credential sources（仅环境变量名）✅
- 发布树包含 4 个 `runtime_lanes.sqlite3`（runtime lane DB，不含 credential snapshot），无 `dayu_host.sqlite3` ✅
- 4 个含 credential snapshot 的 private Host DB（`dayu_host.sqlite3`）已 quarantine 至独立目录，quarantine 不在 root digest 内 ✅

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

## Residual Risk

1. **Formal oracle 仍为 PENDING**：按 S4 边界未运行 frozen formal CLI scenarios。后续 gate 必须独立执行，不得将 observation PASS 投影为 oracle PASS。
2. **screen/09-pyright.txt 缺少 `COMMAND_EXIT_STATUS=0` 行**：其余 9 个 screen 文件以此行结尾，pyright 文件缺少。不影响正确性，仅格式不一致。
3. **MiMo capability=none 的 compaction 级证据**：`02-mimo-boundary` 的 compactor-attempts.json 为空数组（session 未达阈值），不提供 capability=none 在 compaction 级的直接 transport 证据。`01-mimo-baseline` 和 `03-mimo-exhausted-fallback` 已覆盖该能力。
