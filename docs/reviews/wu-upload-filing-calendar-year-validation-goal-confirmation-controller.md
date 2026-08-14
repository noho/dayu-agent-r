# UF-FIX04 shared calendar/year validation goal confirmation

## Gate

- Gate: goal confirmation
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Completion status: pass
- Next entry point: plan
- Artifact path: `docs/reviews/wu-upload-filing-calendar-year-validation-goal-confirmation-controller.md`

## Preflight

- Branch: `codex/upload-filing-oracle`，不是 protected trunk。
- Workspace: clean。
- Merge state: 不存在 `MERGE_HEAD`、`REBASE_HEAD` 或 `CHERRY_PICK_HEAD`。
- Remote refresh: 已成功执行 `git fetch github main`。
- Main fast-forward state: `main == github/main`，当前分支包含 `github/main`，相对它 ahead 32、behind 0。
- Scope ownership: 当前 work unit 只涉及 UF-FIX04；既有 branch commits 与工作树边界清楚。

## Confirmed goal and motivation

建立由 `upload_filing` 与 `download` 共同消费的唯一 Fins domain calendar/year 校验 owner：

- 可选 `filing_date` / `report_date` 必须是严格 `YYYY-MM-DD` 且为实际存在的公历日期。
- required upload filing `fiscal_year` 必须是非 bool 的 `1000..9999` 整数。
- upload 的静态 usage rejection 必须发生在 workspace state read、operation、converter 与 storage mutation 前。
- download 的完整日期与 year 合法性消费同一公共真源。
- download wrapper 继续独有 year、year-month、full-date 形态识别、部分日期 inclusive bound 展开与 start/end ordering。

## First-principles judgment and direct evidence

问题成立，但原始现状描述有一处需要校正：当前 upload validator 已拒绝负数和 bool，并非两者都会进入后续流程。

同一纯 validator 调用链 `_filing_upload_request_identity -> _validate_fins_upload_filing_static` 的复现结果：

- `0`、`999`、`10000` 被错误接受。
- `-1`、`True` 已被 `FinsUploadUsageError` 拒绝。
- `2023-02-29`、`2024-13-01`、`2024-2-9` 被错误接受。
- 合法闰日 `2024-02-29` 被接受。

代码根因与触发输入位于同一逻辑路径：

- `dayu.fins.ingestion_runtime._validate_fins_upload_filing_static` 只用 `< 0` 校验 year，并只对两个日期执行文本长度校验。
- `dayu.fins.download_contract._parse_date_bound` 独立解析 year、year-month 与 full-date。
- `dayu.fins.domain.filing_semantics.normalize_fiscal_year` 另有正整数规则，但没有 `1000..9999` 边界。
- 因此 calendar/year 规则存在多个实现且 upload owner contract 不完整。

## Design alignment and semantic owner

- `docs/host/design.md` 明确 Host 不承载财报业务语义。
- `docs/engine/design.md` 明确 Engine 不负责财报业务语义或工具参数校验。
- 正确 owner boundary 是 `dayu.fins.domain`；CLI、Service、Host、Engine、converter 与 storage 都不得重复解析或下游补偿。
- 最小方向是复用或收紧现有 Fins domain semantics，不引入 runtime-wide abstraction、adapter fallback、compatibility shim 或新状态机。

## Success signals

- shared owner 对严格 calendar date、闰年与 `1000..9999` year 有 owner-level contract tests。
- upload filing 对合法日期、合法闰日和边界内 fiscal year 有正向覆盖。
- 非法日期、bool、0、负数、少于四位与超过四位 year 均产生 typed usage error。
- 非法输入不触发 workspace state read、operation、converter、source meta、manifest 或其它 durable mutation。
- download 的合法 year/year-month/full-date、inclusive expansion 与显式 start/end 行为保持成立。
- download 与 upload 的完整 date/year 校验均可由直接代码证据证明调用同一个 owner。

## Non-goals and scope boundary

- 不执行 UF-PF04 真实 CLI evidence。
- 不刷新 `docs/cli_ci_oracles.json` 或 `docs/cli_ci_scenarios.json`。
- 不修改既有冻结 evidence。
- 不处理其它 upload_filing finding。
- 不扩展到 `upload_material`。
- 不创建 PR、不 push；在当前分支创建 Gateflow 本地提交。
- 不兼容旧非法 durable state，不增加 storage/CLI fallback。

## Docs decision

plan gate 必须按 README 触发规则核对 `dayu/fins/README.md`、`tests/README.md` 与根 `README.md` 的写作边界；只有当前稳定 contract 属于其职责时才更新。

## Residual risks and uncovered areas

- 当前尚未裁定 shared helper 的精确 public API 与调用点集合；由 plan gate基于全部 consumer 证据收敛，分类为 covered by next gate。
- 当前尚未执行产品修改后的 tests、coverage 或 pyright；由 implementation/validation gate覆盖。
- UF-PF04 真实 CLI evidence 明确由用户排除，分类为 assigned to later work unit。

## User decision

用户已明确确认以上 goal、边界与成功信号，可以进入 plan。
