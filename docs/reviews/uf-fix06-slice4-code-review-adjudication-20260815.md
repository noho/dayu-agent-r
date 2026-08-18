# UF-FIX06 Slice 4 code review adjudication

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：4（文档、全局审计与验证收口）
- Gate：code review adjudication
- 日期：2026-08-15
- 基线：`8033a56eb0f44ae5664c510b84ebe448050888eb`
- 状态：`FIX REQUIRED`
- 下一入口：Slice 4 code fix

## Review 输入

- AgentMiMo：`docs/reviews/code-review-slice4-mimo-20260815.md`，结论 `PASS`，1 个低严重度文案 finding。
- AgentDS：`docs/reviews/code-review-slice4-ds-20260815.md`，结论 `BLOCKED`，1 个 blocking finding、2 个低严重度 findings。

## Controller 裁决

### A1 — accepted / blocking

格式文案 owner 中“后缀通过只表示具备转换资格”错误涵盖 companion-only `.xsd`。companion 后缀准入只表示可随批原样保存，不会执行转换；该句进入 CLI help 与 LLM-facing tool schema，必须在 owner 修复，不能只在 README 下游补偿。

最小修复：

- 在 `dayu/fins/upload_format_contract.py` 将该句限定为“主文件后缀通过”，并自足说明随附文件只校验可随批保存的后缀、不执行转换。
- 更新 owner-level exact projection 测试；CLI help 与 tool schema 继续机械消费同一文本。
- 根 README 同步等价用户语义，不维护独立后缀清单。

虽然 Slice 4 原计划是 docs-only，本 finding 位于已提交的唯一 LLM-facing owner。按项目语义所有权硬约束，Controller 允许本 fix 最小重开该 owner 文件及其直接 contract tests；禁止用 README-only 特例掩盖。

### A2 — accepted / low

根 README 补齐 `.json` 只是 Docling JSON candidate 的限定，与 help/tool schema 保持等价。

### A3 — accepted / low

根 README 的失败触发需同时覆盖 filing primary 与 material 任一 converter-required 文件，避免把共享上传段落收窄为 filing-only 词汇；filing 的“不回退为只保存 originals/companions”继续单独说明。

### A4 — accepted / low

Fins README 补回 material 既有独立 company publication 语义：company meta 在 prepare 前以独立 batch 提交，后续转换/存储失败不回滚该已提交 company meta；source/blob 仍保持零部分发布。该项只是恢复当前代码事实，不改变行为。

### A5 — rejected as fix requirement

MiMo 关于 implementation 验证数字为自报告的观察不要求修改。Gateflow 后续 re-review、aggregate deepreview 与 Controller 最终复验会提供独立证据；UF-PF06/UF-PF12 仍按用户要求不运行。

## Fix scope

允许修改：

- `dayu/fins/upload_format_contract.py`
- `tests/fins/test_upload_format_contract.py`
- `tests/cli/test_arg_parsing.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`（仅当测试事实需同步；无必要则不改）
- `docs/gateflow/uf-fix06-slice4-implementation-20260815.md`
- 新增 `docs/gateflow/uf-fix06-slice4-code-fix-20260815.md`

禁止修改 review artifacts、design、registry、oracle/scenario、冻结 evidence 或其它生产/测试文件。

## 验证要求

- owner projection、CLI help 与 tool schema exact tests。
- README/help/tool schema 纯进程内三面对照，明确区分 primary conversion eligibility 与 companion storage admission。
- 原 14 文件 focused matrix；若重新采集整文件 coverage，继续追加两个既有 CN download tests。
- 全量 `python -m pyright dayu/ tests/ utils/`。
- 静态旧 allow-list / generated-name primary inference / protected diff audit。
- 不运行 UF-PF06、UF-PF12 或真实 CLI evidence。

## Completion signal

A1–A4 修复并通过验证后进入 MiMo / DS 双路 code re-review；未通过前不得接受 Slice 4。
