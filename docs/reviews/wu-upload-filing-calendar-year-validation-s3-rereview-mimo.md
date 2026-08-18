# UF-FIX04 S3 re-review（AgentMiMo）

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `67c34c0f`
- Output file: `docs/reviews/wu-upload-filing-calendar-year-validation-s3-rereview-mimo.md`
- 审查范围：controller amendment 完整性与 Unicode digit baseline 核对
- 审查输入：MiMo S3 deepreview、AgentDS S3 deepreview、controller adjudication artifact、git baseline/diff
- 排除范围：不重跑全套测试、不修改生产/测试/文档

## 结论

**Pass**。controller 对 coverage set 的正式 amendment 完整可追溯，Unicode digit 确为 baseline 既有且不应在本 slice 收紧。

## 验证项 1：controller coverage amendment 完整性与可追溯性

### 验证内容

controller adjudication artifact 的 `AgentDS F1：接受并由本 artifact 关闭` 一节声称对 accepted plan §12 做了正式 amendment。需要验证：

1. amendment 内容是否完整覆盖了 DS F1 finding 的所有要点
2. 替换集合是否与本机独立复现一致
3. 是否有可追溯的 plan 引用与约束声明

### 逐项核对

| 检查点 | controller amendment 内容 | 本机 git 复核 | 一致 |
| --- | --- | --- | --- |
| plan 引用 | 明确引用 `accepted plan §12`，声明原文绑定 CLI-only 单文件集合不可达 | DS deepreview F1 引用同一页码（`plan-codex.md:453-458`） | ✅ |
| 不可达证据 | 声称 CLI-only 集合 `63%` | DS 复核 `63%`（`122/330` missed），MiMo deepreview 验证复核表第 3 行一致 | ✅ |
| 撤销非目标测试 | 声称"撤销所有仅为提高该数字而短暂新增的非 calendar/year 测试；最终 diff 中零残留" | DS 复核 grep 零残留，MiMo deepreview 验证复核表第 11 行一致 | ✅ |
| 替换集合（5 个文件） | `tests/cli/test_fins_commands.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/service/test_fins_direct.py`、`tests/service/test_fins_wait_adapter.py`、`tests/cli/test_output.py` | `git diff 67c34c0f --name-only` 精确为 4 个 allowed tracked 文件，5 个测试文件中仅 `test_fins_commands.py` 有 diff，其余 4 个零改动 | ✅ |
| 联合集合实测结果 | `458 passed`，`88%`，`--fail-under=80` | DS 复核 `458 passed, 3 warnings`、`330 statements, 38 missed, 88%`，MiMo deepreview 验证复核表第 4 行一致 | ✅ |
| 不修改约束 | "上述五个测试文件除本 slice 允许修改的 `tests/cli/test_fins_commands.py` 外均不得为 coverage 修改；本次其余四个文件相对 base 零改动" | `git diff 67c34c0f -- tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/cli/test_output.py` 全部无输出 | ✅ |
| CLI 生产文件 coverage | `dayu/cli/commands/fins.py` 仍由 CLI 单文件集合验证 `86%` | DS 记录 `469 statements, 68 missed, 86%`，S3 未改该文件 | ✅ |
| 正式真源声明 | "本 controller amendment 是后续 gate 对 §12 不可达测试集合的唯一正式替代真源" | 无歧义，amendment 指向自身为唯一真源 | ✅ |

### 可追溯性结论

controller amendment 完整且可追溯：

- 引用了被修正的 plan 章节（§12）
- 记录了不可达的直接证据（63% 本机复现）
- 明确列出了替换集合（5 个文件）
- 声明了不得修改约束（除 `test_fins_commands.py` 外零改动）
- 记录了实测结果（458 passed, 88%）
- 声明了自身为唯一正式替代真源
- 三路独立复核（DS、MiMo、本 re-review）全部一致

## 验证项 2：Unicode digit 确为 baseline 既有

### 验证内容

MiMo S3 deepreview finding 001 与 DS residual risk 均指出 download wrapper 的 `\d` 匹配 Unicode 数字。controller 将其分类为"baseline 既有，不作为本 slice finding"。需要验证：

1. baseline（`67c34c0f`）的 regex 是否确实使用无 `re.ASCII` 的 `\d`
2. baseline 的代码路径是否同样接受 Unicode 数字
3. S3 diff 是否修改了 regex 或扩大了接受面

### 逐项核对

| 检查点 | baseline 证据 | S3 diff 证据 | 结论 |
| --- | --- | --- | --- |
| `_YEAR_PATTERN` | `git show 67c34c0f:dayu/fins/download_contract.py` 第 43 行：`re.compile(r"^\d{4}$")`，无 `re.ASCII` | diff 未触碰第 43 行 | baseline 既有，S3 未改 |
| `_YEAR_MONTH_PATTERN` | 第 44 行：`re.compile(r"^\d{4}-\d{1,2}$")`，无 `re.ASCII` | diff 未触碰第 44 行 | baseline 既有，S3 未改 |
| `_FULL_DATE_PATTERN` | 第 45 行：`re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")`，无 `re.ASCII` | diff 未触碰第 45 行 | baseline 既有，S3 未改 |
| Python `\d` Unicode 行为 | `re.compile(r'^\d{4}$').fullmatch('０００１')` → True（fullwidth）、`'٢٠٢٤'` → True（Arabic-Indic）、`'१२३०'` → True（Devanagari） | — | Python 默认 Unicode-aware |
| `int()` Unicode 接受 | `int('０００１')` = 1、`int('٢٠٢٤')` = 2024、`int('१२३०')` = 1230 | — | Python `int()` 接受 Unicode 十进制数字 |
| baseline full-date 路径 | `67c34c0f` 的 `dt.date(int(year_text), int(month_text), int(day_text))` | S3 改为 `f"{int(year_text):04d}-..."` + `parse_iso_calendar_date` | 新旧路径都经过 `int()`，接受集相同 |
| domain owner 对比 | `filing_semantics.py:56-57` 使用 `[0-9]{2}` + `re.ASCII` | — | domain owner 已收紧，但 download wrapper 从未收紧 |

### Unicode digit 结论

确认 Unicode digit 为 baseline 既有行为：

1. baseline 的三个 regex 均使用无 `re.ASCII` 的 `\d`，S3 diff 未触碰
2. baseline 的 `dt.date(int(...), ...)` 路径同样通过 Python `int()` 接受 Unicode 数字
3. S3 的补零 canonicalization `f"{int(...):04d}-..."` 与 baseline 使用相同的 `int()` 接受面，不新增接受
4. domain owner 已使用 `[0-9]` + `re.ASCII` 收紧，但 download wrapper 的 regex 形状是独立的 pre-existing pattern
5. accepted plan 明确要求保持 download 现有合法 shape/行为

controller 将其分类为"不作为本 slice finding，分类为后续 residual"是正确的。收紧 download wrapper regex 应作为独立 work unit（controller 建议为 `download date ASCII-shape admission`），不得混入 UF-FIX04。

## Re-review 要求核对

controller 在 re-review 要求一节列出四项检查，逐项确认：

| 要求 | 验证结果 |
| --- | --- |
| 本 artifact 已形成可追溯的 controller coverage amendment | ✅ 见验证项 1，amendment 完整引用 plan §12、记录不可达证据、列出替换集合与约束、声明唯一真源 |
| 替换集合与实测证据一致，且没有用非目标测试凑 coverage | ✅ 5 个文件全部为既有消费者测试，非目标测试已撤销（grep 零残留），三路复核 458 passed / 88% |
| Unicode digit 分类基于 baseline 直接对比，没有掩盖本 S3 新回归 | ✅ 见验证项 2，baseline regex 和 int() 路径均接受 Unicode 数字，S3 未修改 regex、未新增接受面 |
| 无需修改生产代码、测试、README 或历史 accepted plan artifact | ✅ re-review 只读，未修改任何文件 |

## Conclusion

**Pass**。

S3 re-review 验证通过。controller coverage amendment 完整可追溯，Unicode digit 确为 baseline 既有且不应在本 slice 收紧。无 remaining findings。S3 可进入 accepted 状态。
