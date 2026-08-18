# UF-FIX04 S2 re-review（AgentDS，F1 关闭复核）

- 审查类型：current changes（针对 controller adjudication 接受的 F1 修复的定向 re-review）
- 审查时间：2026-08-14T15:33:04+0800
- Branch：`codex/upload-filing-oracle`
- Base：`e5d4394a`
- 审查输入：`AGENTS.md`、AgentDS S2 deepreview（F1）、AgentMiMo S2 deepreview、controller adjudication、AgentCodex review-fix artifact、当前相对 base 的完整 diff
- 审查问题：F1 是否真正关闭（同一请求非法 filing/report date + 确定缺失文件时，日期 typed usage error 必须优先；测试必须能在生产顺序回归时失败；fix 只触及允许的 runtime test）；fix 是否引入新 regression；冻结文件是否未变；UF-PF04 是否未执行
- 审查动作：只读。未修改生产代码或测试，未 stage、未 commit
- 并行审查覆盖：无

## 结论

**Pass，F1 已关闭，无 remaining findings。**

新增两例优先级测试与生产校验顺序形成直接可判别竞争，证据链完整；fix 只触及 `tests/fins/test_fins_ingestion_runtime.py` 一个文件；复跑验证全部与 review-fix artifact 声明一致；无新 regression、冻结文件未变、UF-PF04 无执行迹象。

## F1 关闭证明（直接证据链）

### 1. 新增可判别反例确实存在且形态正确

`test_validate_fins_upload_filing_request_preserves_validation_priority`（`tests/fins/test_fins_ingestion_runtime.py:1488-1560`）矩阵现为 8 例，新增两例：

- `tests/fins/test_fins_ingestion_runtime.py:1505-1514`：`fiscal_year=2024`、`fiscal_period="FY"`、`filing_date="2024-13-01"`、`files=(Path("missing.pdf"),)`，断言 `INVALID_FILING_DATE`；
- `tests/fins/test_fins_ingestion_runtime.py:1515-1524`：同前提，`report_date="2024-13-01"`，断言 `INVALID_REPORT_DATE`。

两例的 year/period 均为合法值，保证请求中唯一相互竞争的错误就是「日期非法」与「文件缺失」；测试体（1550-1553）把 `files[0]` 替换为 `tmp_path / "missing.pdf"` 并 `assert not missing_file.exists()`，文件缺失是确定性事实而非依赖仓库当前目录状态。既有第 8 例（1525-1528，无 files → `MISSING_FILES`）继续锁定 files 检查的终态位置。

### 2. 生产顺序与测试断言构成真判别

`_validate_fins_upload_filing_static`（`dayu/fins/ingestion_runtime.py:855-941`）当前顺序：

`ticker → action → files 数量 → aliases → fiscal_year（parse_calendar_year，895-898）→ fiscal_period → filing_date / report_date（_validate_optional_upload_iso_date，911-912）→ company_name → MISSING_FILES → file existence probes（exists → FILE_NOT_FOUND，919-921）`

- 若生产顺序回归为「file probes 先于日期」：两例请求的 `tmp_path/missing.pdf` 确定不存在，会先命中 `FILE_NOT_FOUND`；测试断言 `exc_info.value.failure.code is expected_code`（1560）期望 `INVALID_FILING_DATE` / `INVALID_REPORT_DATE`，必然 AssertionError 失败。判别成立，非巧合通过。
- 测试入口 `validate_fins_upload_filing_request`（`ingestion_runtime.py:1015`）首行即调用 `_validate_fins_upload_filing_static`（1035），静态 admission 在消费 `published_state` 之前完成，两例传入的 `published_state=...` 不会干扰判别。
- mutation 验证未执行（review-only 约束下不改生产代码），以上为代码走读的逻辑证明；两例的失败条件是结构性的，不依赖运行时偶然状态。

### 3. 修复只触及允许文件

- mtime 证据：`tests/fins/test_fins_ingestion_runtime.py` 为 15:22（S2 deepreview 15:18:52 之后、fix artifact 15:23 之前）；三个生产文件（14:58）与 CLI/tool 测试文件（15:02 / 15:04）均早于 S2 deepreview，fix 窗口内未被写。
- `find -newermt "2026-08-14 15:17:00"` 全仓（排除 .git/.venv/cache）仅命中：runtime 测试文件、5 个 review artifacts（含 MiMo re-review artifact）、1 个 workspace 锁文件（见 Residual Risk）。
- 相对 base 的 numstat：runtime 测试文件由 S2 deepreview 时 +387/-6 变为 +408/-8，增量与「2 例 + docstring 改写 + files 替换块」一致；生产三文件与 CLI/tool 测试文件 numstat 与 S2 deepreview 记录内容一致（S2 artifact 中记录的 +44/-5 等行数为当时误计，内容走读与 S2 完全一致）。

### 4. 复跑验证（本机独立执行）

| 声明 | 复核命令 | 复核结果 | 与 fix artifact 一致 |
| --- | --- | --- | --- |
| 优先级测试 | `pytest tests/fins/test_fins_ingestion_runtime.py::test_validate_fins_upload_filing_request_preserves_validation_priority -q` | `8 passed, 3 warnings` | ✅ |
| runtime 完整文件 | `pytest tests/fins/test_fins_ingestion_runtime.py -q` | `258 passed, 3 warnings`（S2 时 256 + 新增 2） | ✅ |
| 定向 pyright（6 文件） | `python -m pyright dayu/fins/ingestion_runtime.py dayu/cli/commands/fins.py dayu/fins/tools/upload_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py` | `0 errors, 0 warnings, 0 informations` | ✅ |
| diff integrity | `git diff --check` | exit 0，无输出 | ✅ |
| 未 stage | `git diff --cached --name-status` | 无输出 | ✅ |
| 冻结文件 | `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` | 无输出，未改 | ✅ |

三条 pytest warning 均为 `.venv` 中 `edgar` deprecated imports，与本 fix 无关。

## Findings

未发现实质性问题。

- F1 关闭：见上节证据链，新增两例与生产顺序的判别是结构性的，生产顺序回归必失败。
- 无新 regression：fix 只增加测试，未触碰生产代码、其它测试与冻结 evidence；runtime 完整文件 258 全绿；CLI/tool 测试文件自 S2 deepreview 起未变（mtime + numstat），S2 双路已验证的状态不因本 fix 变化。
- 冻结文件未变：`docs/cli_ci_oracles.json` / `docs/cli_ci_scenarios.json` 无任何修改。
- UF-PF04 未执行：fix 窗口（15:19-15:23）内无任何真实 CLI evidence / artifact / workspace 数据产出；唯一 workspace 变化（publication lock）早于 fix（见 Residual Risk）。

## Open Questions

无。

## Residual Risk

- `workspace/.dayu/batch_locks/AAPL.publication.lock`（0 字节、gitignored、不在 git status）：mtime 15:18:01，**早于本 fix**（runtime 测试文件 15:22、fix artifact 15:23），落在 S2 双路 deepreview 的验证运行窗口内；与本次只改 runtime 优先级测试无因果证据（该测试用 `tmp_path` 与自身 fixtures，不可能在仓库真实 workspace 获取 batch publication 锁；workspace 下无任何 14:30 之后的新数据/artifact 产出，无 published 内容落地）。按 pre-existing test-run artifact 记录，不进 finding、不扩大裁决范围；owner 不明，建议 controller 知悉即可，无需本 work unit 处理。
- 其余 residual risks 与 S2 deepreview 一致：`UF-PF04` 真实 CLI evidence（later work unit）、`upload_filings_from` metadata strip parity（later work unit）、tool 完整文件唯一 baseline failure（UF-FIX01 follow-up）、S3 download shared-owner consumer 与 README（later slice）。

## Handoff

S2 可 accepted（待 controller 合并双路 re-review 后裁决）；不进入 S3，不创建 checkpoint commit。
