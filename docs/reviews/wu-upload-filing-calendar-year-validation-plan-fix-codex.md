# UF-FIX04 plan review fix artifact

## Gate record

- Gate: `plan review fix`
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Branch: `codex/upload-filing-oracle`
- Fixed target: `docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md`
- Review inputs:
  - `docs/reviews/plan-review-20260814-134334.md`
  - `docs/reviews/plan-review-20260814-135603.md`
  - `docs/reviews/wu-upload-filing-calendar-year-validation-plan-review-controller-adjudication.md`
- Scope: 只落实 controller 已裁决的 plan fixes；不进入 implementation、plan re-review 或后续 gate。
- Changed files:
  - `docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md`
  - `docs/reviews/wu-upload-filing-calendar-year-validation-plan-fix-codex.md`
- Explicitly unchanged: 产品代码、测试、README、冻结文件。
- Completion status: `plan fix complete`
- Current gate / next entry point: `plan re-review`
- Artifact path: `docs/reviews/wu-upload-filing-calendar-year-validation-plan-fix-codex.md`

## Controller decisions applied

1. required `parse_calendar_year` 收窄为 `int -> int`，仍显式拒绝 bool；`normalize_fiscal_year(JsonValue | None)` 在同一 owner 先完成 bool/非 int拒绝与 `JsonValue -> int` narrowing，再委托 required parser。
2. fiscal year、download year-only/year-month 共用 `1000..9999` year owner；strict full calendar date独立接受实际 Gregorian `0001..9999`，不调用 year owner。
3. download保留 strip、三种 raw shape、partial expansion与ordering；full-date先补零 canonicalize，再委托full-date owner。
4. CLI直接 `upload_filing` 与 `start_fins_upload` filing branch都保留两个日期raw文本，不strip、不把空白折叠为`None`；material/company及共享旧helper保持不变。
5. 三个year/date usage code各自只有一份业务中立、自解释中文message，CLI与LLM tool outcome共同消费，文本不含`--flag`语法。
6. read-runtime direct consumer回归的精确allowed test file为`tests/fins/test_read_runtime_semantic_ownership_guards.py`。
7. 每个修改生产文件均绑定真实可达测试集合、逐slice coverage命令和不掩盖exit code的判定方式。
8. tool完整文件的唯一预存失败归`UF-FIX01 follow-up`；不修fixture，新增/受影响cases必须全绿，完整文件只允许同一failure node集合且不得新增/扩散。
9. `upload_filings_from` raw metadata strict parity deferred到later `upload_filings_from metadata strictness parity` work unit；README只承诺direct `upload_filing` / filing tool admission，不泛化batch入口。

## Finding disposition

### AgentMiMo 01 — `parse_calendar_year(JsonValue)` API过宽

- Adjudication: `accepted`
- Fix status: `已修复`
- Changed sections: plan §5 Exact APIs、`normalize_fiscal_year` delegation；§10 S1 exact changes/tests；§11 owner matrix。
- Evidence: required API签名已收窄为`int`；raw JSON narrowing只留在同owner optional normalizer。

### AgentMiMo 02 — `1000..9999`缺少直接裁决

- Adjudication: `rejected-with-reason`
- Fix status: 不适用；保持驳回，不假装修复。
- Preserved reason: 用户原始目标已经逐字给出fiscal-year闭区间`1000..9999`，goal confirmation也已确认，不需要再次询问或把该范围描述为推断。
- Plan note: §4仅补充直接来源，未把finding写成已修复。

### AgentMiMo 03 — download full-date canonicalize规格不足

- Adjudication: `rejected-with-reason`
- Fix status: 不适用；保持驳回，不假装修复。
- Preserved reason: 原plan已经明确`f"{year:04d}-{month:02d}-{day:02d}"`后委托owner，并已有`2024-2-9`回归要求；没有欠规格证据。
- Plan note: 仅随controller的date/year解耦补充`0999`语义，没有把该finding算作修复。

### AgentMiMo 04 — CLI test file跨S2/S3

- Adjudication: `rejected-with-reason`
- Fix status: 不适用；保持驳回，不假装修复。
- Preserved reason: S3明确依赖accepted S2，Gateflow顺序实施；同一test file是有序追加，不存在并行ownership冲突。

### AgentMiMo 05 — read runtime direct consumer回归缺口

- Adjudication: `accepted`
- Fix status: `已修复`
- Changed sections: plan §3/§4 consumer证据；§7 planned tests；§10 S1 allowed files/exact tests；§11 regression；§12 coverage集合与命令。
- Evidence: 指定`tests/fins/test_read_runtime_semantic_ownership_guards.py`，要求`_parse_source_document_meta`合法年份不变、非法历史year明确fail closed。

### AgentMiMo 06 — `service_runtime.py`定位不足

- Adjudication: `rejected-with-reason`
- Fix status: 不适用；保持驳回，不假装修复。
- Preserved reason: plan §4已经提供完整path/function，且implementation不修改`service_runtime.py`；不得把导航文件伪列入allowed production files。

### AgentDS 1 — tool path strip破坏strict admission

- Adjudication: `accepted`
- Fix status: `已修复`
- Changed sections: plan §6 upload raw input；§7 production/test scope与call chain；§9 tool assertions；§10 S2 allowed changes/invariants/tests。
- Evidence: filing-only raw nullable reader原样保留empty/blank/padded string到domain admission；material/company继续使用旧helper；tool tests覆盖zero observation/job/executor side effects。

### AgentDS 2 — full date与fiscal-year范围过度耦合

- Adjudication: `accepted`
- Fix status: `已修复`
- Changed sections: plan §1、§5、§6、§8、§10 S1/S3、§11矩阵、§13 README、§14 risks。
- Evidence: `parse_iso_calendar_date(str)`不调用`parse_calendar_year`，actual Gregorian full date接受`0001..9999`；download year-only/year-month仍调用`1000..9999` year owner。

### AgentDS 3 — coverage集合对修改文件不可达

- Adjudication: `accepted`
- Fix status: `已修复`
- Changed sections: plan §10每slice validation/completion；§12逐生产文件测试集合与命令。
- Evidence: 五个修改生产文件分别绑定真实直接测试集合；`filing_semantics.py`额外组合覆盖既有SEC/fiscal函数的tests；每个coverage命令保留pytest与coverage自身exit code。

### AgentDS 4 — affected tool test file存在预存失败

- Adjudication: `accepted`（事实）；fixture顺手修复明确不接受。
- Fix status: `已修复`
- Changed sections: plan §10 S2 non-goals/tests/completion/stop；§12 S2命令与expected；§14 residual risk。
- Evidence: 精确记录baseline node `tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`，owner=`UF-FIX01 follow-up`。focused新增/受影响cases必须exit 0；完整文件保留真实非零exit并精确比较failure node集合；coverage才允许deselect该node。

### AgentDS 5 — tool outcome暴露CLI双横线文案

- Adjudication: `accepted`
- Fix status: `已修复`
- Changed sections: plan §8 typed usage/schema；§9 tool assertions；§10 S2 tests；§11 upload matrix。
- Evidence: fiscal/date code使用单一业务中立message，CLI/tool共用，不含`--`，closed mapping/schema/outcome tests同步断言。

### AgentDS 6 — `upload_filings_from`仍strip metadata dates

- Adjudication: `deferred-with-owner`
- Fix status: 不适用；保持deferred，不假装修复。
- Owner/destination: later `upload_filings_from metadata strictness parity` work unit；不创建/修改issue。
- Changed sections: plan §2 non-goals；§10 S2/S3 boundaries；§11 regressions；§13 README scope；§14 residual risk。
- Evidence: plan明确该入口不变，README不得把direct admission规则泛化为batch parity。

### AgentDS 7 — `normalize_fiscal_year` consumer证据不准确

- Adjudication: `accepted`
- Fix status: `已修复`
- Changed sections: plan §3 repository architecture；§4 direct evidence；§7 planned tests；§11 regression。
- Evidence: 唯一生产direct consumer更正为`dayu/fins/tools/read_runtime.py::_parse_source_document_meta`；processor/pipeline只描述为facts producer或其它domain语义consumer。

## Changed sections summary

- Gate state：改为`plan fix complete`，next entry point=`plan re-review`。
- §1–§6：解耦full-date/fiscal year合法域，收窄API，定义same-owner narrowing与CLI/tool raw input规则。
- §7–§9：补direct consumer test、tool raw reader、单一LLM/CLI message、zero-side-effect断言与精确README边界。
- §10–§12：更新三slice allowed changes、read-runtime精确allowed test file、真实可达per-file coverage集合、每slice命令与UF-FIX01 baseline处理。
- §13–§14：README scope不泛化；补全deferred/baseline residual risk owner。

## Validation

- 完整读取两份plan review、controller adjudication与待修订plan。
- 只读核对`normalize_fiscal_year`全仓库直接consumer、`_parse_source_document_meta`现有tests、tool日期strip链路、download/upload测试入口和各生产文件可达测试集合。
- 未运行任何产品测试、coverage、pyright或`UF-PF04`；这些属于后续implementation slices，不能在plan fix gate伪报。
- 内容一致性搜索通过：required窄签名、same-owner narrowing、full-date/year解耦、read-runtime精确测试文件、UF-FIX01 baseline、deferred owner与gate state均存在；旧`parse_calendar_year(JsonValue)`、date委托year owner、CLI双横线usage message和“所有命令exit 0”等冲突表述均不存在。
- `git diff --check` exit `0`。因两个目标artifacts均为untracked，另分别执行`git diff --no-index --check /dev/null <artifact>`；两条命令无whitespace-error输出，exit `1`仅表示目标文件相对`/dev/null`存在内容差异。
- `git status --short`确认本轮没有产品代码、测试、README或冻结文件变化；未stage、未commit。
- 未stage、未commit。

## Docs decision

- 本gate只改review artifacts，不修改README。
- implementation阶段按触发规则更新根`README.md`与`dayu/fins/README.md`，但只描述download及direct `upload_filing` / `start_fins_upload` filing admission；不承诺`upload_filings_from` strict metadata parity。
- `tests/README.md`、`dayu/README.md`、Host/Engine README不更新，理由保持plan §13所述。

## Residual risks

1. `UF-PF04`真实CLI evidence：`assigned to later work unit`，owner=`UF-PF04`。
2. 其它upload findings：`assigned to later work unit`，owner=`UF-FIX01/02/03/05...`。
3. `upload_filings_from` raw-date parity：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`。
4. tool预存fixture failure：`assigned to later work unit`，owner=`UF-FIX01 follow-up`；当前work unit只允许同一baseline且不得新增/扩散。
5. 历史非法fiscal year read fail-closed：`fixed in current slice`，由owner contract与read-runtime direct consumer回归锁定，不做compatibility读取。

没有`unclassified residual risk`，没有需要新issue或当前用户裁决的事项。

## Completion

- Completion status: `plan fix complete`
- Accepted findings: 全部已在plan中修复。
- Rejected findings: 原理由完整保留，未伪装为修复。
- Deferred finding: 保留明确later owner与README范围限制。
- Validation status: 内容一致性与git diff whitespace check通过；未执行且不声称完成implementation测试、coverage、pyright或`UF-PF04`。
- Current gate / next entry point: `plan re-review`
- Artifact path: `docs/reviews/wu-upload-filing-calendar-year-validation-plan-fix-codex.md`
