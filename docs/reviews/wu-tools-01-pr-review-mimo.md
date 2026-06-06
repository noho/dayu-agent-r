# WU-TOOLS-01 Draft PR Review — AgentMiMo

## Verdict

**pass-with-findings**

## Scope Reviewed

- PR #123 diff（`docs/host/issues-implementation-control.md`、`docs/reviews/wu-tools-01-final-closeout-controller.md`、控制文档新增 WU-TOOLS-01-F01~F09 与 WU-CM-01-F03/F04 段落、README 变更、代码文件清单）
- Phaseflow gate order 正确性
- Residual Risk 表完整性
- WU-TOOLS-01 F01/F04/F06/F09 裁决一致性
- 总控文档对 review artifact 的引用正确性
- 文档自相矛盾检查

## Findings

### F1 — PR 描述与实际变更严重不符（中）

- **文件**：PR #123 description
- **问题**：PR 描述声明 "Docs-only change; pytest and pyright were not run"，但实际变更包含 216 个文件、145 个代码/配置文件（`.py` / `.json`）、20 个测试文件，净增 ~41,000 行。新增了完整的 `dayu/documents/` 包（processors、docling_runtime、search_utils 等）、`dayu/fins/` 大量新模块（service_runtime、domain、storage 新实现）、`dayu/tools/` 新 provider（doc_tools、web tools）、以及 20 个测试文件。这不是 docs-only change。
- **为什么影响 PR gate**：PR 描述是 reviewer 和后续 merge 的第一入口。描述与实际 diff 不符会导致 reviewer 假设低风险而跳过代码审查；pytest / pyright 未运行意味着新增的 ~41,000 行代码没有经过任何自动化验证。
- **建议修复**：更新 PR description 为准确描述变更范围（shared document foundations、Fins service/runtime、tools provider、storage、processors、tests）；补充 pytest / pyright 验证结果或明确标注为何本次不运行。

### F2 — 总控文档未显式引用 closeout controller artifact（低）

- **文件**：`docs/host/issues-implementation-control.md`，WU-TOOLS-01 行（约 L218）
- **问题**：closeout controller artifact `docs/reviews/wu-tools-01-final-closeout-controller.md` 存在于 PR 中，但总控文档的 WU-TOOLS-01 work unit 行没有显式引用它。旧模式（如 WU-CM-01 chain）在 status 表中有 `| final closeout artifacts |` 行；新规则虽把 artifact 引用从 status 表移出，但 work unit 行本身应提供 closeout artifact 的可发现入口。
- **为什么影响 PR gate**：后续 reviewer 或 phaseflow agent 需要从总控文档找到 closeout controller 以确认 residual risk 和 gate 状态；当前只能通过搜索 `docs/reviews/` 目录发现该文件。
- **建议修复**：在 WU-TOOLS-01 行的 description 列或新增一行中加入 closeout controller artifact 路径引用。

## Residual / Follow-up Risk

| ID | 状态 | Owner / Destination | 说明 |
|---|---|---|---|
| WU-TOOLS-01-S4-R1 | deferred-with-owner | WU-TOOLS-01-F01 | 共享 Fins ingestion service/runtime |
| WU-TOOLS-01-S5-R2 | deferred-with-owner | WU-TOOLS-01-F02/F03 / #120 | Web CI pipeline + smoke |
| WU-TOOLS-01-S1-R1 | deferred-with-owner | WU-TOOLS-01-F04~F07 / #121/#122 | SEC/Fins + CN/HK Docling CI + smoke |
| WU-TOOLS-01-S1-R2 | deferred-with-owner | WU-TOOLS-01-F08 | documents processor registry naming |
| WU-TOOLS-01-S6-R1 | deferred-with-owner | WU-CM-01-F04 | proactive compaction test seam |
| WU-ENG-02-S3-R1 | transferred-to-issue | WU-OBS-00B / #119 | usage observation correlation boundary |

所有 residual 均有 owner / destination，无 open 项遗留。closeout controller 与总控文档 residual risk 表一致。

## 裁决一致性验证

- **Shared Fins service/runtime**：F01 段落明确要求 CLI download 与 tool download 同源调用 shared Fins service/runtime。closeout controller 和总控文档一致。
- **CLI/tool 同源**：F01 目标中 "CLI download 和 tool download 必须走同一套代码、同一套逻辑" 与 closeout controller 的 F01 描述一致。
- **Upload 单独 F09**：F01 非目标明确 "不迁移 upload；OLD upload 是 CLI-facing command runtime，不是 upload tool，迁移与 upload ingestion tool 由 WU-TOOLS-01-F09 追踪"。F09 段落完整定义了 upload 迁移原则。一致。
- **Ticker / market normalization 唯一真源**：closeout controller 和 F01/F04/F06/F09 段落均声明 `dayu/fins/ticker_normalization.py` 为唯一真源，禁止在 service/runtime、tool adapter、CI runner 或 pipeline selector 中复制逻辑。一致。

## 总控文档 review artifact 引用检查

- 旧 WU-CM-01 系列 review artifact 已从 status 表中移除，符合新规则 "artifact、commit、review 与历史验证记录写入对应 work unit、review artifact 或 closeout artifact，不在'当前状态'表中累积流水账"。
- WU-TOOLS-01 review artifacts（S1-S6、external blocker reconciliation、plan review 等）未出现在 status 表中，符合新规则。
- 新增的 WU-CM-01-F03/F04 段落和 WU-OBS-00B 段落无 stale 引用。

## Validation

- `docs/host/issues-implementation-control.md` diff 验证：gate 状态、residual risk 表、work unit 表、follow-up WU 段落均与 closeout controller 一致。
- `docs/reviews/wu-tools-01-final-closeout-controller.md` diff 验证：结论、residual risk 表、follow-up WU、ticker normalization 约束、next entry point 均正确。
- PR 文件清单验证：216 文件变更，145 代码/配置文件，20 测试文件，71 docs/reviews 文件。
- 未运行 pytest / pyright（文档-only review scope；但 F1 指出 PR 实际包含大量代码变更）。
