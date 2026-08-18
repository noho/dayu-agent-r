# UF-FIX11 company metadata ignored-change warning — Goal Confirmation

## Gate 元数据

- work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- gate：`goal confirmation`
- 日期：2026-08-17
- design sources：`docs/host/design.md`、`docs/engine/design.md`
- accepted oracle：`docs/cli_ci_oracles.json` 中
  `upload_filing.company-meta-refresh`
- current gate：`plan`
- next entry point：`plan`
- completion status：`confirmed-by-user`

## Preflight

- 当前分支：`codex/upload-filing-oracle`，不是 protected trunk。
- merge / rebase：均未进行。
- 工作树：检查时 clean。
- `git fetch github main:main`：成功；`main == github/main == 256786b2`。
- `git rev-list --left-right --count main...HEAD`：`0 74`；当前分支包含最新 main，领先
  74 个提交，满足 fast-forward 基线条件。
- tmux pane discovery：AgentMiMo=`ai-0:1.1`、AgentCodex=`ai-0:1.4`、
  AgentDS=`ai-0:1.5`；三个名称均唯一，后续每个新 gate 仍须重新 discovery、clear、
  wait-idle 后派发。

## 第一性原理判断

动机成立，且不是单纯展示缺陷。用户提交的 metadata 变化只有 authoritative identity / metadata
decision 与最终 publication owner 知道是否生效；当前 owner 丢掉该事实，下游没有可靠信息可展示。
如果只在 CLI 比较参数或日志，会在并发 fresh recheck、skip、rollback、tool observation 与 durable
state 之间制造多套语义，因此必须在 company metadata 的 commit-time authoritative merge 边界产生
typed ignored-change 事实，再由 publication result、direct result、CLI 与 tool/wait adapter 机械投影。

## 直接代码与数据证据

1. `dayu/fins/pipelines/upload_company_meta.py::resolve_upload_company_meta_decision` 在 existing
   fresh metadata 下只比较 merged ticker identity：identity 未变化时返回 `keep`，有新 alias 时构造
   `preserve_published` intent；两条路径都不保留用户提交的 `company_name`。因此 fresh canonical name
   不会被改写是正确的，但“请求值未生效”事实在 owner 边界被静默丢失。
2. `dayu/fins/domain/company_meta_contract.py::merge_company_meta_for_commit` 已是 storage 在锁内重读
   `current_published` 后选择最终 CompanyMeta 的唯一 owner；它当前只返回 `CompanyMeta`，没有返回
   typed publication outcome / ignored-change 事实。
3. `dayu/fins/storage/_fs_storage_infra.py::_prepare_company_identity_commit` 在 writer、recovery、
   identity guard 下调用上述 merge，并在 publication swap 前写最终 meta；这是能把 warning 与最终
   durable company state 同源的最窄边界。
4. `dayu/fins/pipelines/filing_upload_publication.py::execute_prepared_filing_publication` 已在
   writer-owned fresh view 中重做 filing validation。但 `SKIP` 分支当前直接 rollback 并返回 skipped，
   不 stage / commit fresh company decision。这不仅导致不同 company name 静默无提示，也构成一个真实
   “成功 skip 但新合法 alias 未进入 accepted identity”的路径。
5. `tests/fins/test_sec_pipeline_upload_filing_stream.py::
   test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision` 与 CN 对应测试直接固定了
   当前现象：请求中的不同名称未写入，最终 status 为 skipped，batch rollback，且无 public warning。
6. `FinsUploadPipelineResult`、`FinsUploadResultSummary`、`FinsResultSummary` 当前只携带 status、counts、
   IDs、skip/failure 等字段，没有 typed company metadata warning；`dayu/cli/output.py` 与
   `dayu/service/fins_wait_adapter.py` 只能消费现有 result，因此在展示层无法可靠补救。
7. accepted oracle 明确要求：stale metadata 缺 company-name 时 fail closed / 显式名称原子刷新；fresh
   canonical identity 不被单次 filing upload 静默改名；忽略新名称或 alias update 时必须 warning。
8. 已提交 closeout/review 证据确认既有 owner：ticker grammar / alias dedupe 属于
   `CompanyTickerIdentity`，commit-time identity union 与 uniqueness 属于 storage；UF-FIX10 则确认
   shared publication owner 与 writer-owned fresh view 是同请求、跨请求并发的最终裁决点。

## 目标与成功信号

- fresh canonical company identity 下，不允许单次 filing upload 改写 canonical company name。
- 用户提交的非空名称经唯一 normalization 后若与最终 canonical name 不等，并且最终 filing terminal
  为 success 或 skip，则从 commit-time authoritative company outcome 产生一条有界、无路径、无内部术语、
  可行动的 typed warning。
- direct command result、CLI 屏幕与 tool/LLM-facing completed result 投影同一 warning contract；
  failure、cancel、kill、rollback 或未完成 publish 时没有 warning。
- source skip 时，合法新 alias 仍在同一原子 publication unit 中合并持久化并可由 read route 解析；
  已生效 alias 不误报 ignored。invalid / collision alias 继续 typed fail closed。
- stale metadata 的显式 refresh 与 source 原子提交、缺名称零 durable mutation 的既有 contract 不变。
- publication-lock / writer-owned fresh re-read 后的 warning、structured result 与最终 repository state
  一致；不依赖 CLI preflight snapshot。
- 受影响测试、完整相关回归、修改文件覆盖率和全仓 pyright 通过；按 README 触发规则裁决文档更新。

## Scope boundary

允许修改的语义链路限定为：Fins company metadata commit contract、Fins storage batch commit result、
shared filing publication owner、upload pipeline/runtime typed result、direct event result、CLI renderer、
Fins tool wait projection，以及相应 owner / SEC-CN shared route / CLI-Service-tool tests 和职责内 README。
SEC、CN、HK 入口不得各自判断 ignored change。

## 非目标与不过度设计说明

- 不新增 rename API、metadata 管理命令、alias 市场真实性验证或 resolver freshness/version 规则。
- 不修改 download/material/Host/Engine 行为；只有既有 direct/tool typed result 的必要机械投影可进入范围。
- 不创建通用 warning framework、event bus、全局锁、重试或兼容 shim。
- 不运行真实 CLI post-fix evidence、UF-PF11/UF-PF12，不修改 frozen evidence、oracle、scenario 或 registry。
- 不为不存在的 alias ignored 路径制造 warning；当前已发现的 skip 丢 alias 路径应修成真正持久化，
  而不是接受丢弃后仅提示。

最小正确方案是在既有 company metadata commit owner 返回窄 typed outcome，并沿既有结果链投影；
不需要 Host/Engine 协议、通用 warning 抽象或新的管理工作流。

## Blocking open questions

无。用户已明确 warning 适用终态、alias/stale/atomicity contract、并发真源、外部 evidence 排除项、
本地提交与不创建 PR 的边界，并于 2026-08-17 确认本 goal restatement。

## Residual risks / uncovered areas

- 当前尚未运行修改后验证；归类为 `covered by later approved slice`。
- material 也存在“fresh name 不覆盖”的既有行为，但用户明确列为非目标；归类为
  `assigned to later work unit`，本 work unit 不声称修复。
- 外部真实 CLI calibration、UF-PF11/UF-PF12 与 frozen evidence 刷新由用户明确排除；归类为
  `assigned to later work unit`。
