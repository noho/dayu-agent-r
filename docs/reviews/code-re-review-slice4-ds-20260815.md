# Code Re-review

## Scope

- Mode: current changes（第二路独立 code re-review，AgentDS）
- Branch: `codex/upload-filing-oracle`
- Base: `8033a56eb0f44ae5664c510b84ebe448050888eb`
- Work unit: `UF-FIX06 converter-capability-owner` Slice 4 code review fix（裁决 `docs/reviews/uf-fix06-slice4-code-review-adjudication-20260815.md`：A1 blocking + A2-A4 low，A5 rejected as fix requirement）
- Review 输入:
  - 裁决：`docs/reviews/uf-fix06-slice4-code-review-adjudication-20260815.md`
  - Fix artifact：`docs/gateflow/uf-fix06-slice4-code-fix-20260815.md`
  - Fix 后的 implementation artifact：`docs/gateflow/uf-fix06-slice4-implementation-20260815.md`
- Included scope（相对基线的完整 diff，8 个文件）:
  - `dayu/fins/upload_format_contract.py`（+2/-1，A1 owner 文案修复）
  - `tests/fins/test_upload_format_contract.py`（+20，exact projection 锁定）
  - `tests/cli/test_arg_parsing.py`（+3/-1，help 同源断言）
  - `tests/fins/test_fins_ingestion_tools.py`（+2，tool schema 同源断言）
  - `README.md`（+9/-1，A1 投影 + A2 + A3）
  - `dayu/fins/README.md`（+16/-6，capability/role/batch/data flow + A4）
  - `tests/README.md`（implementation 轮 +35，fix 轮未改，声明一致）
  - 两个 gateflow artifact（implementation fix 同步 + code-fix 新增）
- Excluded scope: 未重跑 14 文件 focused 矩阵与全量 pyright；未运行 UF-PF06/UF-PF12/真实 CLI evidence；冻结 evidence 位于 workspace 外未复核；其它生产/测试文件不在 fix scope（`git diff --name-only` 与裁决 Fix scope 逐项对照无越界）。
- Parallel review coverage: 无（本路独立完成）。

## 逐项核验（A1-A4）

### A1 — accepted / blocking — 已正确修复

- **owner 文案**：`dayu/fins/upload_format_contract.py:565` 改为"主文件后缀通过只表示具备转换资格，不保证文件内容转换成功。随附文件只校验可随批保存的后缀，不执行转换。"
  - 核验：`.xsd` companion 准入不再被描述为转换资格；"主文件"限定与 `accepts_primary`（仅 converter capability）/`accepts_companion`（∪{`.xsd`}）的角色语义一致；"随附文件只校验可随批保存的后缀" 与 `require_filing_path(COMPANION)` 的校验行为一致；"不执行转换" 与 `_prepare_upload_selection` 中 filing converter_inputs 仅 `require_primary()` 一致。
- **机械同源**：CLI help（`dayu/cli/arg_parsing.py:924`）与 LLM-facing tool schema（`dayu/fins/tools/upload_tools.py:238`）生产文件本轮零改动，继续消费 `FINS_UPLOAD_FORMAT_TEXT`；test 侧将两个消费点与 owner 文本的断言收紧为含新限定句的 fragment 断言。
- **根 README 投影**：`README.md:319-321` 为等价用户语义（"主文件后缀通过只表示具备转换资格…；随附文件（含 `.xsd`）只按可随批保存的后缀准入，不做转换"），未维护独立后缀清单，格式清单继续以 `--help` 即时输出为准。
- **独立复跑**：`tests/fins/test_upload_format_contract.py` 19 passed；`test_upload_filing_files_help_consumes_self_contained_format_projection` 与 `test_upload_tool_calendar_year_schema_and_usage_messages_are_business_neutral` 2 passed（本路独立执行，非 fix 自报告）。

### A2 — accepted / low — 已正确修复

- 根 README 增加"`.json` 只是 Docling JSON candidate"，与 owner 的"`.json` 仅是 Docling JSON 候选，不代表任意 JSON 内容可转换"等价；未复制后缀清单。

### A3 — accepted / low — 已正确修复

- 根 README 失败触发改为"空文件、任一原始文件读取失败，或 filing primary / material 任一需要转换的文件内容无法成功转换时，整批上传失败且 `stored files` 为 `0`"；"filing 失败时也不会回退为只保存原文件或 companions"单独说明。
- 核验：触发清单同时覆盖两种 source kind；"material 任一需要转换的文件"未泄漏 `converter-required` 内部术语；与代码一致（material 转换失败在 `docling_upload_service.py:790-791` 重抛、零发布；空文件对 material 经转换失败路径同样整批失败）。

### A4 — accepted / low — 已正确修复

- Fins README 新增段落："material workflow 在 prepare 前以独立 company batch 提交 company meta；后续转换或存储失败不会回滚已提交的 company meta，但 source/blob 仍由后续单一 publication batch 保持零部分发布。filing 的 company meta 则与 source/blob 保持同一 publication batch 的原子边界。"
- 代码对照：
  - SEC material：company batch 先 begin→stage→commit（`sec_upload_workflow.py:492-505`），再 prepare（:506），source/blob 走独立 publication batch（:530-536）；
  - CN material：company batch 先 commit（`cn_pipeline.py:1107-1120`），再 prepare（:1121），source/blob 独立 batch（:1145-1148）；
  - filing 同 batch：SEC filing（`sec_upload_workflow.py:227-247`）与 CN filing（`cn_pipeline.py:856-876`）都在同一 `publication_batch` 内 stage company decision 并发布 source/blob。
  - "后续失败不回滚已提交 company meta"由 commit 时序保证；"source/blob 零部分发布"由 prepare 先于 batch 与 batch rollback 保证。表述准确。

### A5 — rejected as fix requirement

- 无需核验修改；fix artifact 按裁决重跑了要求的验证（owner/help/schema 568 passed、14 文件矩阵 1235 passed、pyright 0 errors、三面对照 PASS），本路独立复跑了 owner 与 help/schema 三个测试节点确认。

## Findings

未发现实质性问题。

- 无新增语义错误：owner 文案逐句重读，不再存在把 companion 准入（含 `.xsd`）描述为转换资格的措辞；help/schema 机械同源未被破坏。
- 无行为回退：selection 类型、converter inputs 收窄、原子发布、requested/stored 计数、取消线性化点、production behavior/schema 均无代码变更（本轮唯一生产文件改动是 owner 文案两行字符串）。
- 无越界修改：diff 文件集合与裁决 Fix scope 允许清单一致；review artifacts、design、registry、oracle/scenario 无 diff；`git diff --check` 通过；冻结 evidence 未被读取或写入。
- 测试未固化错误语义：exact projection 测试的期望文本与生产逐字一致且包含新限定句，是 owner-level contract 锁而非兼容分支。

## Open Questions

- 无。

## Residual Risk

- 本路未独立重跑 14 文件 focused 矩阵与全量 pyright（fix 自报告 1235 passed / 0 errors；本路独立证据为 21 个相关测试节点通过）。
- UF-PF06 全格式 fixture 矩阵与 UF-PF12 全量 CLI scenario 未运行（按用户指令，归属对应 PF work unit）。
- 冻结 evidence bundle 位于 workspace 外，本路未复核其 SHA-256。
- owner 文案被 exact 全文断言锁定：未来文案演进必须同步更新测试期望文本，属有意的漂移防护，维护成本记录在案。

## 结论

**PASS**

A1-A4 全部正确修复且有直接代码/测试证据支撑，A5 按裁决无需修改。owner 文案不再将 `.xsd` companion 准入表述为转换资格，CLI help / tool schema 机械同源保持，根 README 的 `.xml`/`.json`/legacy/primary-companion/material failure 文案准确且用户可读，Fins README 的 material company batch 与 source/blob 边界与代码一致。production behavior/schema/atomic/count/cancel/protected scope 均无回退。无 blocking finding，无新问题。
