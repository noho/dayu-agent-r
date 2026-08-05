# PR 190 F11/F12 S4 Real-Provider Observation Evidence — MiMo Review

## Scope

- Mode: Evidence gate review (read-only, no production/oracle/scenario/evidence root modification)
- PR: 190 (`noho/dayu-agent-r`, branch `codex/interactive-oracle`)
- Base HEAD: `d9f044f944dd44e0d369f9d93e0533d2b725e413`
- Repo artifact: `docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md`
- Immutable evidence root: `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`
- Expected digest.json SHA-256: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`
- Review date: 2026-08-06
- Parallel review coverage: 8 subagents (digest integrity, command/screen/report consistency, secret scan, Mimo capability, DeepSeek json_object, F11/F12 identity, prompt-injection boundary, repo artifact cross-check)

## Findings

### 01-未修复-低-repo artifact exhausted fallback 量化计数过度宣称

- **入口/函数**: `docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md` Observation verdicts 表 "Mimo bounded exhaustion / single failure / fallback" 行
- **文件(行号)**: `docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md:30`
- **输入场景**: 读取 repo artifact 中 Mimo exhausted fallback 和 DeepSeek exhausted fallback 的 verdict 描述
- **实际分支**: artifact 声称 `selected=9, dropped=2`
- **预期行为**: verdict 中的量化数值应与 evidence root 中 memory.json 的实际数据一致
- **实际行为**: 两个 exhausted fallback evidence 的 `memory.json` 中 `snapshot.trace_memory.selected_recent_window` 实际为 8 个元素，且 `dropped_recent_window` key 不存在（不是 2）
- **直接证据**:
  - `evidence/03-mimo-exhausted-fallback/memory.json`: `snapshot.trace_memory.selected_recent_window` = 8 items, 无 `dropped_recent_window` key
  - `evidence/08-deepseek-exhausted-fallback/memory.json`: `snapshot.trace_memory.selected_recent_window` = 8 items, 无 `dropped_recent_window` key
  - repo artifact 行 30: `selected=9、dropped=2`
- **影响**: 定性结论（deterministic fallback 执行、无 Memory/artifact 污染）正确，但量化数值与证据不符。不影响 gate 裁决，但 artifact 中的精确数字应可被下游验证。
- **建议改法和验证点**: 将 `selected=9、dropped=2` 改为 `selected=8、dropped=0`；验证 `memory.json` 中 `snapshot.trace_memory.selected_recent_window` 长度和 `dropped_recent_window` key 存在性。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-repo artifact DeepSeek repair source material digest 值不匹配

- **入口/函数**: `docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md` "Provider request 与 attempt binding 摘要" 章节
- **文件(行号)**: `docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md:51`
- **输入场景**: 读取 repo artifact 中 DeepSeek repair 的 source material digest 值
- **实际分支**: artifact 声称 `0f9c284b921545f4b72c46c9681be90658f477836a7cc810697c7776a29fb875`
- **预期行为**: digest 值应能在 evidence root 中被找到
- **实际行为**: 该 digest 在 `evidence/06-deepseek-bounded-repair/compact-eventlog.json` 中未找到。eventlog 中实际出现的 material digest 为 `b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee`（frozen_material_list_digest）。两个 attempt 的 operation_id 和 source_boundary 引用一致，repair 的 same-boundary 语义正确。
- **直接证据**:
  - `evidence/06-deepseek-bounded-repair/compact-eventlog.json` 全文搜索 `0f9c284b`：未命中
  - `evidence/06-deepseek-bounded-repair/compact-eventlog.json` 全文搜索 `b798e8e5`：命中，出现在 frozen_material_list_digest 字段
  - repo artifact 行 51: `source material digest 两次一致：0f9c284b...`
- **影响**: 定性结论（same-boundary repair 的 source material 一致性）正确，但引用的具体 digest 值与证据文件中的实际值不匹配。不影响 gate 裁决，但 artifact 中的 digest 应可被下游直接 grep 验证。
- **建议改法和验证点**: 将 `0f9c284b921545f4b72c46c9681be90658f477836a7cc810697c7776a29fb875` 改为 `b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee`；或确认是否有其他 evidence 文件包含该 digest。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 各核验维度 PASS 汇总

| 维度 | 结论 | 覆盖 evidence | 关键验证点 |
|------|------|---------------|------------|
| 证据树 digest 与只读状态 | **PASS** | root digest.json | 159 entries, SHA-256 匹配, 160 文件, 目录 `dr-x------` |
| command/screen/report 一致性 | **PASS** | metadata/command-inventory.json, screen/00-09, observed-report.md | 10 screen 与 10 inventory 条目一一对应; 8 evidence 目录与 report 引用一致 |
| Secret scan | **PASS** | metadata/secret-scan.json | 0 findings, 2 credential sources, 4 private SQLite 已 quarantine |
| Mimo capability=none initial/fallback | **PASS** | evidence/01, 02, 03 | provider=mimo, model=mimo-v2.5-pro, capability=none, response_format=null, request-id unavailable |
| DeepSeek json_object outbound | **PASS** | evidence/04, 05, 06, 07, 08 | provider=deepseek, model=deepseek-v4-flash, capability=json_object, outbound request 含 json_object |
| DeepSeek first-pass | **PASS** | evidence/04 | 首 attempt accepted, request-id=6d77593a... |
| DeepSeek session_summary:null | **PASS** | evidence/05 | candidate 含 session_summary:null, Memory owner 清除 summary |
| DeepSeek cap replacement | **PASS** | evidence/05 | 旧标签 omitted, 当前 21.7% 进入活动 projection |
| DeepSeek same-boundary repair | **PASS** | evidence/06 | 同 operation_id, attempt 1 rejected (cap exceeded), attempt 2 accepted |
| DeepSeek rolling correction | **PASS** | evidence/05, 06, 07 | 旧标签 omitted, reconnect 不恢复旧结论 |
| DeepSeek reconnect | **PASS** | evidence/07 | 同 session, 旧结论不恢复, 当前事实保留 |
| Failed compact 单 terminal / fallback | **PASS** | evidence/03, 08 | 2 rejected + 1 failed terminal, deterministic_recent_window, 无 compact artifact |
| Failed compact 无 Memory/artifact 污染 | **PASS** | evidence/03, 08 | latest_compaction_ref=null, semantic memory 全空 |
| Prompt-injection material/instruction boundary | **PASS** | evidence/01-08 compact artifacts | delimiter 分隔, system prompt digest 一致, 业务 marker 仅在 material 区 |
| F11 successful identity | **PASS** | evidence/01, 04, 05 | provider/model/request-id/manifest/terminal 完整 |
| F11 successful-response-then-rejected identity | **PASS** | evidence/03, 06, 08 | response identity 保留, rejected terminal 正确绑定 |
| actual provider/model/request-id availability/value | **PASS** | evidence/01-08 tool trace | Mimo: unavailable/null; DeepSeek: present/具体值 |
| public/canonical equality | **PASS** | evidence/01-08 public-canonical-equality.json | 全部 finding_count=0, exact match |
| private SQLite 误用 | **PASS** | evidence/01-08, metadata/workspace-private-db-exclusion.json | 公开树仅含 runtime_lanes.sqlite3, 无 dayu_host.sqlite3 残留 |
| implementation PASS | **PASS** | git log HEAD | HEAD=d9f044f9... 匹配 |
| real observation PASS | **PASS** | evidence/01-08 | 全部 provider 可用, 无 timeout/API rejection |
| oracle PENDING | **PASS** | git status | 无 oracle/scenario/registry 修改 |
| repo artifact validation 路径一致性 | **PASS** | metadata/command-inventory.json vs screen/ | inventory 条目与 screen 文件内容一致 |

## Open Questions

无。

## Residual Risk

1. **screen/09-pyright.txt 格式不统一**: 其余 9 个 screen 文件以 `COMMAND_EXIT_STATUS=0` 结尾，pyright 文件缺少此行。不影响正确性，仅格式约定不一致。
2. **Formal oracle 仍为 PENDING**: 按 S4 边界未运行 frozen formal CLI scenarios，不得把 observation PASS 投影成 oracle PASS。后续 gate 必须独立执行。
3. **reconnect 中旧数值的 raw history preservation vs semantic reintroduction**: 旧数值以"已失效历史值"出现在回答中，未成为活动 Memory/RunInput 结论。双路 review 应区分两种保留模式。
4. **02-mimo-boundary 无 compactor attempts**: boundary 测试未触发 compaction（session 未达阈值），compactor-attempts.json 为空数组。这符合预期但不提供 capability=none 的 compaction 级证据。
