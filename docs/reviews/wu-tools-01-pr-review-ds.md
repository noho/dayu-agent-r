# WU-TOOLS-01 Draft PR Review — AgentDS

## Verdict

**pass-with-findings**

该 PR 的 control document 与 closeout artifact 状态正确、自洽、无阻断性问题；可以通过 draft PR review gate，进入 final closeout 等待 PR review / merge gate。

## Scope Reviewed

- `docs/host/issues-implementation-control.md`（PR diff 全文，约 71KB）
- `docs/reviews/wu-tools-01-final-closeout-controller.md`（PR 新增文件，77 行）
- `docs/host/design.md`（设计真源，验证架构边界引用自洽性）
- `docs/engine/design.md`（设计真源，验证架构边界引用自洽性）
- `dayu/fins/ticker_normalization.py`（验证公开 API 形态与文档声明一致）
- PR #123 metadata（`gh pr view` 获取的 title、body、commits、draft 状态）
- git log 验证 commit 顺序（plan → slice acceptances → closeout）

未审查 PR 中 216 个文件的实现代码（各 slice 已在独立的 code review gate 中完成审查），本 review 聚焦 control document correctness、流程状态、owner/destination 与文档自洽性。

## Findings

### F1 — PR body 声明 "Docs-only change" 与 PR 实际内容不一致（Low）

**位置**: PR #123 body / GitHub metadata

**问题**: PR body 写 `## Validation: Docs-only change; pytest and pyright were not run.`，但 PR diff 包含 216 个文件（72,560 行新增），其中包括大量 `dayu/fins/`、`dayu/tools/`、`dayu/documents/` 生产代码与 `tests/` 测试代码。PR title 为 "phaseflow: close out WU-TOOLS follow-ups"，PR body summary 描述的是 closeout 阶段的 control doc 清理工作。这些声明对于阅读 PR body 的人会产生误导——会以为整个 PR 只包含文档变更。

**为什么影响 PR gate**: 不阻断。draft PR review gate 的审查对象是 control doc 和 closeout artifact 的正确性，而非 PR body 的描述准确性。PR 是 draft 状态，body 可以在 mark ready 前修正。

**建议修复**: 将 PR body 修改为准确描述 PR 内容——这是一个包含 S1-S6 实现代码 + closeout control doc 更新的综合 PR，或者将 "Docs-only change" 限定为 "Closeout-phase changes are docs-only"。

### F2 — Residual Risk 表格式变更后 `来源 work unit` 不再有独立列（Low）

**位置**: `docs/host/issues-implementation-control.md` 第 195-202 行

**问题**: 旧 residual risk 表有 `来源` 列（例如 "WU-ENG-02 Slice 3 code review"），新表格式为 `| ID | 状态 | Owner / Destination | 下一步 |`，去掉了 `来源` 与 `类型` 列。追踪规则（第 181 行）要求 "每条 tracking item 必须有稳定 id、来源 work unit、状态、owner / destination 和下一步动作"。当前通过 ID 命名约定（如 `WU-TOOLS-01-S4-R1` 中的 `S4` 暗示来源为 Slice 4）隐式承载来源信息，但命名约定不等同于显式字段。

**为什么影响 PR gate**: 不阻断。来源信息在 ID 约定中可追溯，所有 residual 都能通过 ID 前缀定位到来源 slice。但若后续引入不遵循此约定的 residual，可能丢失来源可追溯性。

**建议修复**: 可保持现状（convention-based approach 在本项目中一致应用），也可在表头注释中说明 ID 命名约定如何编码来源 work unit。无需新增列。

### F3 — closeout controller 未显式引用 migration plan 文档路径（Informational）

**位置**: `docs/reviews/wu-tools-01-final-closeout-controller.md` 第 25 行

**问题**: closeout controller 记录 "Accepted plan commit: f6658fb4"，但未提及 plan 文档路径 `docs/host/wu-tools-01-migration-plan.md`。control doc 的 WU-TOOLS-01 行同样只引用 commit 而非文档路径。对于后续开发者，定位 migration plan 需要先通过 commit hash 查找。

**为什么影响 PR gate**: 不阻断。commit hash 是充分引用，且 `docs/host/wu-tools-01-migration-plan.md` 在仓库中可直接发现。

**建议修复**: 可选在 closeout controller 的 Accepted Local Delivery 节中补充 plan 文档路径；非必须。

## Correctness Verification

以下检查项全部通过，无阻断性发现：

### Phaseflow Gate Order

- control doc 第 143 行: `gate | draft PR opened / final closeout pending PR gate` — 正确，draft PR 已打开，final closeout 等待 PR review/merge gate。
- closeout controller 第 5-7 行: "按流程，final closeout 不在 draft PR 之前完成。本 artifact 只记录 PR gate opened 与 final closeout 前置条件，不声明 GitHub PR review / merge gate 已通过" — 与 control doc 一致。
- control doc 第 218 行: WU-TOOLS-01 状态 `draft-pr-open-final-closeout-pending` — 与 gate 字段一致。
- PR #123 `isDraft: true` — 确认是 draft PR，gate order 正确。

### Residual Risk Table

- control doc 第 195-202 行 residual risk 表共 6 条记录，closeout controller 第 38-45 行同样 6 条。
- 两条文档中的 ID、closeout decision/状态、owner/destination 一一对应，无差异。
- 全部 6 条均为 `transferred-to-issue` 或 `deferred-with-owner`，无 `open` 状态且无 owner 的项。
- ID → owner 映射:
  - `WU-ENG-02-S3-R1` → WU-OBS-00B / GitHub Issue #119
  - `WU-TOOLS-01-S4-R1` → WU-TOOLS-01-F01
  - `WU-TOOLS-01-S5-R2` → WU-TOOLS-01-F02 → F03 / GitHub Issue #120
  - `WU-TOOLS-01-S1-R1` → WU-TOOLS-01-F04/F05 + F06/F07 / GitHub Issues #121, #122
  - `WU-TOOLS-01-S1-R2` → WU-TOOLS-01-F08
  - `WU-TOOLS-01-S6-R1` → WU-CM-01-F04

### WU-TOOLS-01-F01/F04/F06/F09 裁决清晰性

- **F01** (control doc 第 720-768 行): shared Fins service/runtime 底座 ✓; CLI/tool 同源 ✓ ("CLI download 和 tool download 必须走同一套代码、同一套逻辑"); upload 排除给 F09 ✓ ("Upload 不纳入本条，转入 WU-TOOLS-01-F09 单独追踪"); ticker_normalization 真源 ✓
- **F04** (control doc 第 839 行起): 继承 F01 同源裁决 ✓ ("本条继承 F01 的同源裁决"); ticker_normalization 真源 ✓ ("CI runner 不得为了批处理便利复制 ticker / market 归一化规则")
- **F06** (control doc 第 905 行起): 继承 F01 同源裁决 ✓; ticker_normalization 真源 ✓ ("不得在 CI runner、scorer 或 Docling adapter 中复制 CN/HK market 判断")
- **F09** (control doc 第 1002 行起): upload 独立追踪 ✓ ("OLD upload 是 CLI-facing command runtime，不是 upload tool"); 继承 runtime 底座 ✓ ("必须与 read、download、preprocess/process 一样落到 shared Fins service/runtime 底座"); ticker_normalization 真源 ✓ ("Upload 迁移同样继承 ticker / market 归一化唯一真源裁决")
- closeout controller 第 63 行: "For all Fins ingestion follow-ups, ticker / market normalization must call `dayu/fins/ticker_normalization.py` as the only source of truth." — 与各 F0x 条目一致。

### ticker_normalization 真源存在性

- `dayu/fins/ticker_normalization.py` 存在，公开 API 包含 `normalize_ticker(...)` / `try_normalize_ticker(...)` / `ticker_to_company_id(...)` / `NormalizedTicker`，与文档声明一致。

### 无 Stale Review Artifact 引用

- control doc 中已无旧 WU-CM-01 closeout chain 的 artifact 引用（`wu-dur-obs-cm-closeout-pr-review`、`wu-cm-01-pr-review`、`wu-cm-01-aggregate-deepreview` 等全部清理）。
- 旧 "current inspection note"（约 40 行流水账）已移除，符合新规则（第 173 行）"不在当前状态表中累积流水账"。
- 旧 `plan artifacts`、`implementation commits`、`review artifacts` 等冗长字段已全部从当前状态表清理。

### 文档间自洽性

- control doc 和 closeout controller 在以下方面全部一致:
  - gate 状态
  - active work unit (WU-TOOLS-01)
  - default next work unit (WU-TOOLS-01-F01)
  - next entry point (PR review gate → F01, or WU-CM-01-F04 first)
  - residual risk ID / owner / destination
  - follow-up work unit 列表 (F01-F09, WU-CM-01-F04, WU-OBS-00B)
  - ticker_normalization 真源声明
  - GitHub issue status comments (#82, #97, #98)
  - design source (docs/host/design.md, docs/engine/design.md)

### 新增 Work Unit 合理性

- `WU-CM-01-F03` (Assistant final answer continuity fidelity): 属于 WU-CM-01 final closeout follow-up，不是 WU-TOOLS-01 范围，未出现在 closeout controller 的 follow-up 列表中 —— 正确。
- `WU-OBS-00B` (Usage observation correlation boundary): 是 WU-ENG-02-S3-R1 的 owner，同时出现在 control doc work unit 表和 closeout controller follow-up 列表中 —— 一致。

## Residual / Follow-up Risk

以下为 PR merge 后的 residual risk 概览（已在 control doc 中追踪，此处仅复述不新增）:

| ID | Owner | 风险 |
|---|---|---|
| WU-TOOLS-01-S4-R1 | WU-TOOLS-01-F01 | Fins ingestion shared runtime 尚未建立 |
| WU-TOOLS-01-S5-R2 | WU-TOOLS-01-F02/F03 | Web CI diagnostics + smoke 尚未迁移 |
| WU-TOOLS-01-S1-R1 | WU-TOOLS-01-F04-F07 | SEC/Fins + CN/HK Docling CI pipeline + smoke 尚未迁移 |
| WU-TOOLS-01-S1-R2 | WU-TOOLS-01-F08 | processor registry `engine` 命名尚未清理 |
| WU-TOOLS-01-S6-R1 | WU-CM-01-F04 | broad Host validation 因 proactive compaction test seam 尚未恢复 |
| WU-ENG-02-S3-R1 | WU-OBS-00B | usage observation correlation 需求待 analyzer 确认 |

新增风险: 无。所有风险均有明确 owner/destination，已在 control doc 中追踪。

## Validation

本 review 为文档-only review，验证方法:
- `gh pr view 123` 获取 PR metadata
- `git diff main...phaseflow/wu-tools-01 --stat` 获取变更规模
- `git diff main...phaseflow/wu-tools-01 -- docs/host/issues-implementation-control.md` 全文审阅 control doc diff
- `git diff main...phaseflow/wu-tools-01 -- docs/reviews/wu-tools-01-final-closeout-controller.md` 全文审阅 closeout artifact
- `rg` / `grep` 验证无 stale artifact 引用
- `head` 验证 `dayu/fins/ticker_normalization.py` 公开 API 形态
- `git log` 验证 commit 顺序

未运行 pytest / pyright（本次 gate review 范围限定为文档正确性）。
