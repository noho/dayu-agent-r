# `WU-CLI-DOWNLOAD-02` Slice 2 Code Review Adjudication

## Gate state

- Work unit: `WU-CLI-DOWNLOAD-02-DL-F12-F14`
- Slice: Slice 2 — DL-F14 market form policy
- Input HEAD: `401edda723750d1cb18ad6f6572cda79d948679d`
- Implementation artifact: `docs/gateflow/wu-cli-download-02-slice2-implementation-20260810.md`
- Review artifacts:
  - `docs/reviews/wu-cli-download-02-slice2-code-review-mimo-20260810.md`
  - `docs/reviews/wu-cli-download-02-slice2-code-review-ds-20260810.md`
- Adjudication: **fix required / no blocking contract question**

## Review convergence

AgentMiMo 结论为 PASS、无 finding。AgentDS 结论为 PASS with two low-severity findings。两者均确认：market-specific 三集合 owner、CN/HK bare 语义、显式 Q2/Q4 不回归、rebuild local-only、Slice 3 边界和现有 owner tests 均未发现 correctness 级失败。

总控不把 reviewer 的 PASS 自动视为 accepted gate；以下逐项按直接代码证据裁决。

## Finding adjudication

### S2-CR-01 — `filters.start_dates` value 在 download/rebuild 间不同源

- Source: AgentDS finding 1
- Severity: low
- Decision: **accepted / fix in Slice 2**
- Direct evidence:
  - `run_cn_download_stream_impl(...)` 已由 `resolve_period_windows(...)` 生成逐财期实际 business window，并在候选选择中按该 tuple 过滤。
  - download 结果却用全局 `resolve_window(...)` 的同一个 `window.start_date` 填充全部 discovery keys。
  - rebuild 结果使用 `PeriodDownloadWindow.start_date`，因此 FY 与 interim/quarter 默认窗口分别为五年与两年。
- Root-cause judgement: `start_dates` 是 workflow/rebuild 对“实际采用窗口”的投影；它的 value owner 已经是 `resolve_period_windows(...)`。download 从另一个全局窗口重算 value，形成双真源并在 bare default、未显式 start 时产生可观察差异。
- Required fix: download 的 `filters.start_dates` 直接从既有 `period_windows` tuple 投影 `{item.fiscal_period: item.start_date}`；不得新增 helper、fallback 或下游兼容。补 owner test 精确断言未显式 start 时 FY 与 Q1/H1 的值不同且等于 policy window 结果，同时保留 key 集断言。
- Scope judgement: 属于 Slice 2 三路 policy/window projection 的直接 owner boundary，不是 Slice 3、CLI 或通用基础设施扩张。

### S2-CR-02 — `CN_FISCAL_PERIOD_ORDER` 未纳入模块 `__all__`

- Source: AgentDS finding 2
- Severity: low
- Decision: **accepted / fix in Slice 2**
- Direct evidence: `cn_download_models.py` 已用 `__all__` 显式管理该模块公共 contract，并导出同级公共常量与类型；新增非私有 `CN_FISCAL_PERIOD_ORDER` 被 `cn_form_utils.py` 跨模块直接消费，但未进入清单。
- Root-cause judgement: canonical 顺序被计划和实现定位为 CN/HK 下载链路唯一 source of truth；遗漏导出清单会使模块声明的公共表面与实际跨模块 contract 不一致。
- Required fix: 仅在现有 `__all__` 中加入 `"CN_FISCAL_PERIOD_ORDER"`，并在 owner test 断言导出清单；不得新增 re-export 或兼容路径。
- Scope judgement: 单一 owner 模块的 contract 完整性修复，无行为或架构扩张。

## Rejected / deferred items

- AgentDS residual risk 中的 `_PERIOD_SORT_KEY` 复用属于已批准 Slice 3 classification work，本 gate 不提前修改。
- `_optional_period` 的未来扩展风险不是当前冻结语义缺陷，不处理。
- HKEX `13600`、multi-period projection 与真实 CLI evidence 分别属于 Slice 3 和后续 aggregate/evidence gate，不提前处理。
- `cn_report_selection.py` 的 formatter-only diff 已由两名 reviewer 核验无 token、顺序、分类或控制流变化；不要求额外 churn。

## Fix and re-review gate

AgentCodex 只允许修改：

- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_download_models.py`
- `tests/fins/test_cn_download_workflow.py`
- 本 slice implementation artifact（仅同步最终验证/修复记录）

修复后必须重新运行受影响测试、accepted focused union、八个 production 文件逐文件 coverage、changed-files Ruff/format、compileall、全量 pyright、`git diff --check` 与 Slice 2 guards。不得 commit、不得进入 Slice 3、不得运行真实 CLI。随后由原 MiMo/DS reviewers 对两个 accepted finding 做独立 re-review。

## Re-review adjudication

- Re-review artifacts:
  - `docs/reviews/wu-cli-download-02-slice2-rereview-mimo-20260810.md`
  - `docs/reviews/wu-cli-download-02-slice2-rereview-ds-20260810.md`
- AgentMiMo verdict: **PASS**
- AgentDS verdict: **PASS**

总控完整读取两份 re-review，并复核最终代码与 tests diff：

- S2-CR-01 已关闭：download 与 rebuild 均直接从 `period_windows` 投影逐财期 `start_dates`；owner test 在未显式起点时精确证明 FY 五年窗口和 H1/Q1/Q3 两年窗口。
- S2-CR-02 已关闭：canonical order 仅加入 owner 模块现有 `__all__`，没有包级 re-export、wrapper 或兼容路径。
- 两名 reviewer 均回扫完整 Slice 2 diff，未发现新 finding；旧 contract、Slice 3 absence、HKEX `13600` unchanged 与 Python allowlist guards 均通过。
- AgentCodex 最终验证为 focused union `1031 passed`，八个 production 文件逐文件覆盖率 `84%–100%`，Ruff check/format、compileall、全量 pyright 与 `git diff --check` 均通过。

Final adjudication: **Slice 2 code-review-pass / accepted for protected commit**。Residual risks 仅为已批准 Slice 3 与后续真实 evidence gate 的工作，不存在 unclassified risk 或 blocking question。
