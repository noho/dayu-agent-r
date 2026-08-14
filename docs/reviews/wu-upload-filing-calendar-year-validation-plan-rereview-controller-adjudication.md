# UF-FIX04 plan re-review controller adjudication

## Gate record

- Gate: `plan re-review`
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Branch: `codex/upload-filing-oracle`
- Reviewed plan: `docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md`
- Plan fix artifact: `docs/reviews/wu-upload-filing-calendar-year-validation-plan-fix-codex.md`
- Re-review inputs:
  - `docs/reviews/plan-review-20260814-141854.md`（AgentMiMo，`pass`）
  - `docs/reviews/plan-review-20260814-142422.md`（AgentDS，`pass-with-risks`）
- Controller conclusion: `accepted plan`
- Completion status: `plan review closed`
- Next entry point: implementation `S1-domain-calendar-year-owner`

## Accepted-finding closure

两路 reviewer 均以源码、冻结依据和本机只读验证确认，下列 controller accepted findings 全部为 `已修复`：

1. required `parse_calendar_year` API 已收窄为 `int -> int`；raw `JsonValue` narrowing 只留在同 owner 的 optional normalizer。
2. read-runtime 唯一生产 direct consumer 已识别，并纳入 S1 精确回归。
3. filing tool 日期 raw text 不再由共享 strip helper提前折叠；material/company 行为保持。
4. full calendar date `0001..9999` 与 fiscal/download partial year `1000..9999` 已解耦。
5. 五个修改生产文件均有真实可达 coverage 集合；S1 当前集合实测 `filing_semantics.py` statement coverage 为 `85%`。
6. UF-FIX01 预存失败节点已精确记录，完整文件失败集合不得新增或扩散。
7. 三个 calendar/year usage message 使用同一业务中立真源，不含 CLI `--flag` 语法。
8. `normalize_fiscal_year` blast radius 已更正为 read-runtime direct consumer，不再误列 processor/pipeline。

原 controller 驳回的四项 findings 理由仍成立；`upload_filings_from` strict metadata parity 继续按原裁决 deferred 到明确 later owner，没有伪报修复。

## Re-review residual adjudication

### AgentMiMo R1 — raw reader 非 string 文案精度

- Decision: `rejected-with-reason`
- Reason: plan §6 已明确只有 missing/null 返回 `None`、string 原样进入 admission、非 string 在 tool boundary 拒绝；§10 S2 的 `Exact allowed changes` 又明确指定非 string 抛 `ValueError`。两段是语义与实施细节的递进关系，不存在可执行歧义，也不能合理推导为把非 string 折叠成 `None`。

### AgentDS observation 1 — goal artifact 与 download year 下界的文字张力

- Decision: `rejected-with-reason`
- Reason: 用户目标和冻结 oracle 明确四位 year 为 `1000..9999`；“保持 download 现有合法行为”指已冻结的 year/year-month/full-date shape、partial inclusive expansion 与显式 start/end 语义，不授权保留 `<1000` 的 year-only/year-month。plan 已明确 full-date `0001..9999` 仍合法，未改写 goal artifact。

### AgentDS observation 2 — S1 coverage 边际

- Decision: `accepted-as-self-enforcing-risk`
- Disposition: `fixed in current slice`。S1 必须运行 owner matrix 后的真实 coverage，并以 `--fail-under=80` 和 stop condition 阻止不足门槛的实现进入 review；当前未实现状态的 `85%` 不是最终完成证据。

### AgentDS observation 3 — 其它 usage code 仍含 CLI flag

- Decision: `deferred-with-owner`
- Owner: 其它 upload finding / LLM-facing usage message consistency work unit。
- Reason: 本 work unit只改变 calendar/year 三个 code；扩大到 ticker/action/file 等其它 code 会越过用户明确范围。

## Docs decision

- implementation 必须按 plan 更新根 `README.md` 与 `dayu/fins/README.md`。
- `tests/README.md`、`dayu/README.md`、Host/Engine README 不更新，理由维持 plan §13。
- frozen oracle/scenario/evidence 保持只读；不执行 `UF-PF04`。

## Residual risks

1. `UF-PF04`：`assigned to later work unit`，owner=`UF-PF04`。
2. 其它 upload findings：`assigned to later work unit`，owner=`UF-FIX01/02/03/05...`。
3. `upload_filings_from` raw-date parity：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`。
4. tool 预存 fixture failure：`assigned to later work unit`，owner=`UF-FIX01 follow-up`；当前 work unit只允许相同 failure node 集合。
5. 历史非法 fiscal year read fail-closed、CLI date strict raw admission、download/upload格式差异：`fixed in current slice`，由 owner contract和明确 regression gates 锁定。

没有 `unclassified residual risk`，没有需要用户新增裁决的事项。

## Final decision

Plan 已达到 `accepted plan`：owner、API、分层边界、输入裁决、错误投影、测试位置、coverage gate、README 决策和 residual-risk owner 均已收敛。允许进入 implementation `S1-domain-calendar-year-owner`；不得跳过 slice review 或扩大到排除项。
