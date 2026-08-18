# UF-FIX04 S3 re-review（AgentDS）

- 审查类型：current changes 双路 S3 re-review（裁决后复审）
- 审查时间：2026-08-14T16:04:23+0800
- Branch：`codex/upload-filing-oracle`
- Base：`67c34c0f44bf72ddeea9f1e732808f06245d8044`（S2 accept 提交）
- 审查输入：`docs/reviews/wu-upload-filing-calendar-year-validation-s3-review-controller-adjudication.md`（本轮复审对象）、`docs/reviews/wu-upload-filing-calendar-year-validation-s3-deepreview-ds.md`（本人 S3 F1）、`docs/reviews/wu-upload-filing-calendar-year-validation-s3-deepreview-mimo.md`（MiMo S3 review）、`docs/reviews/wu-upload-filing-calendar-year-validation-s3-implementation-codex.md`、accepted plan（`wu-upload-filing-calendar-year-validation-plan-codex.md`）
- 审查动作：只读复审。未修改生产代码、测试、README、历史 plan artifact，未 stage、未 commit。按用户要求未重跑全套 pytest/coverage/pyright（本人 S3 首轮已本机独立复现 63%/88%/458 passed/pyright 0 errors，本轮只核对状态一致性与裁决 artifact 的可追溯性）
- 并行审查覆盖：无

## 结论

**Pass，无 remaining findings。**

controller adjudication artifact 已正式关闭本人 S3 F1（coverage plan 偏离）。五项关闭要件全部有直接证据支撑：原不可达命令明确、替换五文件集合完整、88%/458 passed 与实测一致、禁止修改非目标 consumers 成立且已独立验证零改动、历史 plan 不回写而由 amendment supersede 成立。MiMo 001 的 Unicode digit 分类经 baseline 直接对比核对无误（pre-existing、非 S3 引入、独立 work unit）。

## 逐项关闭判定

### 1. 明确原不可达命令 ✅

- 裁决 artifact 第 26 行明确：accepted plan §12 把 `download_contract.py >=80%` 绑定为只运行 `tests/cli/test_fins_commands.py`，实现期直接证据证明该集合只能达到 `63%`，missing lines 主要属于 result summary、provider failure 与其它非 UF-FIX04 public contract。
- plan 原文直接证据：`plan-codex.md:572`（§12 "S3 and aggregate commands" 的 completion 命令）`coverage report --include='dayu/fins/download_contract.py' --fail-under=80` 与 `plan-codex.md:455/508`（§11 字面命令与 coverage 映射表）均绑定 CLI 单文件。
- 本人 S3 首轮本机复现该字面命令：`330` statements、`122` missed、`63%`，`--fail-under=80` 必然 exit 非零——原命令按字面不可达为直接证据，裁决对该错误的描述与事实一致。

### 2. 替换五文件集合 ✅

- 裁决 artifact 第 30-35 行完整列出替换集合：`tests/cli/test_fins_commands.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/service/test_fins_direct.py`、`tests/service/test_fins_wait_adapter.py`、`tests/cli/test_output.py`，与 implementation artifact §Control-side coverage-set correction 第 51-56 行逐项一致。
- 集合性质复核：五个文件均为仓库既有、真实到达 `download_contract.py` 的消费者测试文件（CLI、runtime、Service direct/wait、public projection），不存在为凑门槛新增的非目标测试。

### 3. 88%/458 passed ✅

- 裁决 artifact 第 37 行：联合集合实测 `458 passed`，`download_contract.py` 为 `88%`，继续执行原 `--fail-under=80` 门槛。
- 与本人 S3 首轮本机独立复现一致（`458 passed, 3 warnings`；`330` statements、`38` missed、`88%`，exit 0）；`dayu/cli/commands/fins.py` 单文件集合 `86%`（`469`/`68`）也与 implementation artifact §Validation.2 及 S2 deepreview 记录一致。

### 4. 禁止修改非目标 consumers ✅

- 裁决 artifact 第 36 行明确：五个测试文件除本 slice 允许修改的 `tests/cli/test_fins_commands.py` 外均不得为 coverage 修改；第 28 行明确撤销所有仅为提高数字而短暂新增的非 calendar/year 测试，最终 diff 零残留。
- 本轮独立验证：
  - `git diff 67c34c0f --stat -- tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/cli/test_output.py` 输出为空——四个非 CLI 文件相对 base 零改动 ✅
  - `grep -rn "test_download_result_contract_derives_counts\|test_download_provider_errors_preserve" dayu/ tests/` 无匹配——两个撤销测试零残留 ✅

### 5. 历史 plan 不回写而由 amendment supersede ✅

- 裁决 artifact 第 39 行明确：历史 accepted plan artifact 保持不可变，不回写已接受记录；本 controller amendment 是后续 gate 对 §12 不可达测试集合的唯一正式替代真源；S3 completion signal 以本节集合为准，其余 plan 要求不变。
- 本轮独立验证：`git diff 67c34c0f --stat -- docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md` 输出为空——plan 自 base 以来零改动（该文件于 `f609a4d8` 提交）；plan 文件未出现在本次任何改动中 ✅

### 6. Unicode digit baseline 对比分类核对 ✅

- 裁决 artifact 第 41-43 行对 MiMo 001 的分类：该接受集在 `67c34c0f` baseline 已存在；S3 未修改 regex，也未新增该接受面；不收紧为 ASCII-only，作为独立 `download date ASCII-shape admission` work unit 处理。
- baseline 直接对比核对（`git show 67c34c0f:dayu/fins/download_contract.py`）：
  - baseline 44-46 行：`_YEAR_PATTERN`/`_YEAR_MONTH_PATTERN`/`_FULL_DATE_PATTERN` 均为无 `re.ASCII` 的 `\d` 正则——与当前 `download_contract.py:46-48` 相同 ✅
  - baseline 808 行：旧 full-date 路径 `dt.date(int(year_text), int(month_text), int(day_text))`，Python `int()` 接受 Unicode 十进制数字——接受集与 S3 后等价，裁决引述与 baseline 原文一致 ✅
  - 本轮 `git diff 67c34c0f -- dayu/fins/download_contract.py | grep "^[+-].*PATTERN"` 输出为空——S3 diff 未触碰任何 regex 行，未新增接受面 ✅
- 数据流核对：裁决所述「partial year 仍把数值交给 year owner，full-date 仍把 canonical ASCII 文本交给 date owner」准确——Unicode 数字由 wrapper 的 `int()` 补零规范化为 ASCII canonical 文本后才交给 `parse_iso_calendar_date`，不存在 shared owner 绕过。分类无误：pre-existing、非 S3 回归、不掩盖任何本 S3 新问题。

### 7. Re-review 四要求逐条核对 ✅

| 裁决 artifact 要求 | 核对结果 |
| --- | --- |
| 已形成可追溯的 controller coverage amendment | ✅ 文件存在于 `docs/reviews/`，内容引用 plan §12、列出替换集合、说明 supersede 关系 |
| 替换集合与实测证据一致，无凑 coverage | ✅ 集合为既有真实消费者文件；非 CLI 四文件零改动；撤销测试零残留 |
| Unicode digit 分类基于 baseline 直接对比，无掩盖 S3 新回归 | ✅ 见第 6 项；S3 diff 未触碰 regex |
| 无需修改生产代码、测试、README 或历史 accepted plan artifact | ✅ 本轮零修改；workspace 状态与首轮审查一致 |

## Workspace 状态一致性复核

- `git diff --name-only 67c34c0f --` 精确为 4 个 allowed tracked 文件（`README.md`、`dayu/fins/README.md`、`dayu/fins/download_contract.py`、`tests/cli/test_fins_commands.py`）
- `git diff --cached --name-status` 无输出——无 staged changes
- `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` 无输出——冻结 registry 未改
- 新增 untracked 文件仅 4 个 review artifacts（ds/mimo/implementation/adjudication），无其它非预期改动

## Findings

未发现实质性问题。

（备注级观察，不构成 finding：裁决 artifact 引用「accepted plan §12」节号而非 F1 建议验证点中的精确行号 453-458。§12 "Validation commands" 在 plan 中唯一，且 §12 内 572 行的 S3 aggregate command 正是 completion signal 所在，节号引用足以唯一定位绑定错误，不构成可追溯性缺口。）

## Open Questions

- 无。F1 已由 controller artifact 正式关闭，各项关闭要件均有直接证据。

## Residual Risk

- **Unicode digit wrapper regex 宽松**：pre-existing，接受集与 baseline 相同，S3 未触碰。已由裁决分类为独立 `download date ASCII-shape admission` work unit，owner 为后续 slice，非本 S3 残留。
- **`_parse_date_bound` 空/过长分支未覆盖**：pre-existing 测试缺口，S3 diff 未触碰，文件级 88% ≥ 80% gate 已达成，不影响本 slice 结论。
- **UF-PF04 真实 CLI evidence**：未执行（按用户要求），owner=`UF-PF04` later work unit。
- **S2 遗留项**：`upload_filings_from` metadata strip parity、tool 完整文件 UF-FIX01 baseline failure——owner 已记录于 S2/S3 各 artifact，不重复报告。
