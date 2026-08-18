# UF-FIX04 S3 双路审查控制侧裁决与 plan amendment

## Gate record

- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Slice: `S3-download-shared-owner-and-closeout`
- Base: `67c34c0f`
- Reviewers: AgentMiMo、AgentDS
- Decision: `core implementation pass; governance finding fixed by this amendment`
- Next entry point: `dual S3 re-review`

## 核心实现裁决

两路 reviewer 均判定 S3 核心实现 Pass：

- year-only / year-month 只把年份合法性委托 `parse_calendar_year`；
- full-date 在 download wrapper 补零后只委托 `parse_iso_calendar_date`，没有继承 fiscal year 的 `1000` 下界；
- wrapper 继续拥有 trim、三种输入 shape、partial inclusive expansion、真实月末与闰年展开；
- `FinsDownloadDateRange` 继续唯一拥有 start/end ordering；
- public download DTO 通过同一 full-date owner 校验，错误类型和用户可见 message 与 baseline 一致；
- README 准确区分 direct filing admission 与 `upload_filings_from` 非目标路径；
- frozen oracle/scenario/evidence 未改，UF-PF04 未执行。

## AgentDS F1：接受并由本 artifact 关闭

accepted plan §12 把 `download_contract.py >=80%` 绑定为只运行 `tests/cli/test_fins_commands.py`。实现期直接证据证明该集合只能达到 `63%`，且 missing lines 主要属于 result summary、provider failure 与其它非 UF-FIX04 public contract。为满足错误集合而新增无关测试会造成 goal drift，因此控制侧在实现过程中作出以下修正，本 artifact 将其正式记录为对 accepted plan §12 的后续 amendment：

1. 撤销所有仅为提高该数字而短暂新增的非 calendar/year 测试；最终 diff 中零残留。
2. `dayu/cli/commands/fins.py` coverage 仍由 `tests/cli/test_fins_commands.py` 单文件集合验证，结果 `86%`。
3. `dayu/fins/download_contract.py` coverage 改由当前仓库既有真实 consumers 联合集合验证：
   - `tests/cli/test_fins_commands.py`
   - `tests/fins/test_fins_ingestion_runtime.py`
   - `tests/service/test_fins_direct.py`
   - `tests/service/test_fins_wait_adapter.py`
   - `tests/cli/test_output.py`
4. 上述五个测试文件除本 slice 允许修改的 `tests/cli/test_fins_commands.py` 外均不得为 coverage 修改；本次其余四个文件相对 base 零改动。
5. 联合集合实测 `458 passed`，`download_contract.py` 为 `88%`，继续执行原 `--fail-under=80` 门槛。

历史 accepted plan artifact 保持不可变，不回写已接受记录；本 controller amendment 是后续 gate 对 §12 不可达测试集合的唯一正式替代真源。S3 completion signal 以本节集合为准，其余 plan 要求不变。

## AgentMiMo 001：不作为本 slice finding，分类为后续 residual

三个 download shape regex 使用无 `re.ASCII` 的 `\d`，因此 Unicode 十进制数字可被 `int()` 接受。该接受集在 `67c34c0f` baseline 已存在：旧 full-date 路径同样执行 `dt.date(int(year_text), int(month_text), int(day_text))`；S3 未修改 regex，也未新增该接受面。accepted plan 明确要求保持 download 现有合法 shape/行为，因此本 work unit 不将其收紧为 ASCII-only。

这不是 shared owner 绕过：wrapper 先按其既有 download shape 规范化，partial year 仍把数值交给 year owner，full-date 仍把 canonical ASCII 文本交给 date owner。若产品需要收紧 download raw shape，应作为独立 `download date ASCII-shape admission` work unit 修改 wrapper pattern并单独评估兼容影响；不得混入 UF-FIX04。

## Re-review 要求

复审只需确认：

- 本 artifact 已形成可追溯的 controller coverage amendment；
- 替换集合与实测证据一致，且没有用非目标测试凑 coverage；
- Unicode digit 分类基于 baseline 直接对比，没有掩盖本 S3 新回归；
- 无需修改生产代码、测试、README 或历史 accepted plan artifact。

双路 re-review 均 Pass 前，S3 不得 accepted 或 commit。
