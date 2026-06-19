# Gateflow Plan: conversation memory smoke 诊断增强

- **Gate**: plan
- **Work unit**: conversation memory smoke 诊断增强
- **Scope**: `utils/smoke_host_public_conversation_memory_scenarios.py`、对应 runtime helper 测试、README 说明
- **Design source**: `docs/host/design.md`
- **Baseline**: 当前工作区已有 conversation memory smoke 分层与 compact audit 初稿，用户确认可作为 baseline 继续修改；本轮不 revert、不 stash、不 commit。

## Goal / Motivation / Success Signal

目标是增强 diagnostic compact smoke 的失败解释能力。当前 long25 失败显示 `CONTEXT_COMPACTION_FAILED`、`requested_proactive=6`、`compacted_proactive=4`、`failed_proactive=2`、`rejected_proactive=25`，但 smoke 输出只能给出聚合计数，无法直接定位每个 compaction operation 的 reject 分布、diagnostic refs、proposal manifest refs 或具体 offending field。

动机成立：设计真源要求 tool trace / audit 能解释 compact 保留、压缩、丢弃及失败原因；现有 Host 已在 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 中保存 `failure_category`、`diagnostic_refs`、`proposal_manifest_ref` 等信息，smoke 侧没有把这些信息结构化投影出来。

成功信号：

- `memory-compact` 失败时 stdout 包含 per-operation compact audit 摘要。
- stdout 包含 rejected attempt error histogram，可按 failure category / diagnostic suffix 聚合。
- `--log-level DEBUG` 下输出 rejected proposal 相关 `diagnostic_refs`、`proposal_manifest_ref`、attempt number 与 operation id 摘要，便于定位 offending field。
- `SMOKE` 行不再与 stderr 的 `SMOKE FAIL` 粘连。
- 不改变生产 memory / compact accept barrier / current input anchor 语义。

## Non-goals / Scope Boundary

- 不修改 `docs/host/design.md` 设计语义。
- 不放宽 compact accept barrier。
- 不把 `current_input_anchor` 变成可引用来源。
- 不实现 issue-80 全量 eval。
- 不新增 reactive / fallback certification suite。
- 不读取 memory 表或 compact material 正文；只读取本次 session 的 compact EventLog rows 与 compact artifact 文件路径。

## Direct Code Evidence

- `utils/smoke_host_public_conversation_memory_scenarios.py` 已有 `CompactAuditSummary` 与 `_compact_audit_summary_from_rows(...)`，但只输出总计数。
- `dayu/host/context_events.py` 的 `build_context_compaction_attempt_rejected_payload(...)` 已提供 `failure_category`、`diagnostic_refs`、`next_policy_decision`、`proposal_manifest_ref`、`proposal_manifest_digest`。
- long25 日志显示 offending field 已存在于 Host debug log / diagnostic refs 中，例如 `reference_continuity_items[3].source_labels contains cross-section label: E1` 与 `forward_intents[0].source_labels cites current input anchor: C1`。
- 当前日志出现 `... wuliangye_revenue=1SMOKE FAIL ...`，说明 stdout/stderr 合流存在 flush/line-buffering 粘连问题。

## Affected Files

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `README.md`
- `tests/README.md`
- `docs/reviews/*` gateflow artifacts

## Contract / Schema / State Changes

无生产 contract、schema、state machine 变更。新增内容只属于 smoke stdout diagnostic contract 与测试 helper。

## Implementation Decisions

- 新增 smoke-local typed dataclasses 表达 compact operation audit 与 rejected attempt audit，不使用 `Any` / `object` 签名。
- 从 EventLog payload JSON 中解析 operation id、attempt number、failure category、repairable、diagnostic refs、next policy decision、budget、proposal manifest refs。
- operation 归因继续使用 request event id 到 trigger source 的映射；accepted / failed / rejected 通过 `operation_id` 回指 request。
- 默认输出保持一行总览；DEBUG 输出打印 per-operation 与 rejected attempt 明细。
- 使用 stdout line buffering/write-through 与失败前 flush 修复行粘连。

## Slices

### S1: compact audit 结构化诊断

- 允许文件：smoke 脚本与对应测试。
- 变更：新增 audit details dataclass、histogram helper、打印 helper；增强 `_compact_audit_summary_from_rows` 周边解析。
- 非目标：不读取 compact artifact 内容，不改 Host。
- 验证：新增纯 helper 测试覆盖 operation 归因、histogram 与 DEBUG 明细。

### S2: stdout 粘连修复与 README 同步

- 允许文件：smoke 脚本、README、tests README。
- 变更：main 中配置 stdout line buffering / write-through，异常路径 flush stdout；README 只描述 compact audit 新增诊断。
- 验证：新增 main 级轻量测试或 helper 测试确认配置函数可调用；README 触发规则已检查。

## Tests / Validation

- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`
- `source .venv/bin/activate && pyright`

## Docs Decision

触及 `utils/`、`tests/` 与用户可见 smoke CLI 输出说明，需检查并按需更新根 README 与 `tests/README.md`。不修改 `docs/host/design.md`。

## Risks / Residuals

- 真实 compactor 输出仍可能因模型质量失败；本轮只增强诊断，不承诺修复 compactor prompt 或 accept 率。分类：assigned to later work unit。
- smoke 读取 EventLog 是 diagnostic compact suite 的例外，可能弱化 public-only 边界；本轮限定为 `memory-compact` audit 诊断，不读取 memory/material 正文。分类：fixed in current slice by scope limit。

## Completion Report Format

最终报告改动文件、验证命令、docs 更新、review artifact、剩余风险；明确未 commit、未 push、未开 PR。

