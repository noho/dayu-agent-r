# UF-FIX11 S1+S2 Implementation Acceptance

## Gate metadata

- work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- slice：`S1+S2 — atomic authoritative company identity commit and filing warning`
- gate：`implementation acceptance`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 基线提交：`0b4740fa1a1334d0e242f31311c6d6902ff70035`
- completion status：`PASS / ACCEPTED FOR SLICE COMMIT`
- next entry point：`S3 result projection implementation`
- blocking open questions：无

## Controller acceptance decision

S1+S2 已通过 implementation、双路 implementation review、review fix 与双路 implementation
re-review。语义 owner 位于 publication lock 内重新读取最终 authoritative company identity 后执行的
company metadata commit decision；storage 仅在最终 commit、cleanup 与 batch close 全部成功后返回 typed
outcome。publication workflow 只把该 outcome 机械投影为 filing warning，SEC/CN terminal producer 再通过
唯一 closed codec 输出同一事实。下游 summary、durable、direct、CLI 与 tool/LLM projection 仍严格留给 S3。

Controller 接受本切片进入独立 accepted commit。没有基于 preflight snapshot、原始参数、日志文本、
disposition、文件状态或入口特例重新推断 ignored change；没有新增 alias 丢弃路径、rename workflow、市场
真实性校验、通用 warning framework 或 Host/Engine 改动。

## Review adjudication

### Initial implementation reviews

- MiMo：`docs/reviews/uf-fix11-s1-s2-implementation-review-mimo-20260817.md`，PASS，0 blocking；
  两项 non-blocking observation 进入 controller 裁决。
- DS：`docs/reviews/uf-fix11-s1-s2-implementation-review-ds-20260817.md`，无 production correctness 或
  stability blocker；报告三项 owner/structure test gap。

### Accepted fixes

- DS Finding-001：补齐 material 显式空 warnings 合法、非空 filing warning fail closed 的 parser owner test。
- DS Finding-002：补齐 cancelled/outcome warning 同源不变量与 closed codec 负例的 direct owner tests。
- DS Finding-003：把四个 `SourceKind` callsite contract 改为按所属方法绑定，不依赖源码物理顺序。
- MiMo 空白输入建议：补齐 ASCII 与 Unicode 空白作为 missing/no-intent 的 pipeline-boundary test。

### Rejected with reason

- 不统一 pipeline 必填校验与 domain 防御校验的内部错误文案；二者属于不同 owner contract，下游无权匹配
  这些文本。
- 不修改 production normalization；pipeline owner 把空白视为 missing，domain 对绕过 owner 的空白 intent
  fail closed，职责不同且没有根因证据支持合并。

### Final re-reviews

- MiMo：`docs/reviews/uf-fix11-s1-s2-implementation-rereview-mimo-20260817.md`，PASS，确认全部 accepted
  findings 关闭、rejected-with-reason 合理、无新 finding。
- DS：`docs/reviews/uf-fix11-s1-s2-implementation-rereview-ds-20260817.md`，PASS，确认全部 accepted
  findings 关闭、无 blocking open question 或未分类 residual risk。

## Validation evidence

- review-fix 新增 branch tests：`13 passed, 3 warnings in 1.13s`。
- accepted plan §12.1 focused suite：`715 passed, 3 warnings in 12.57s`。
- accepted plan §12.2 combined regression：`2138 passed, 1 skipped, 3 warnings in 63.28s`。
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- `tests/fins` production coverage：`1951 passed, 1 skipped`；12 个本切片 production 文件均 `>=80%`，
  总计 `87%`。
- `git diff --check`：通过。

唯一 skip 为既有 Docling integration 条件 skip；三个 warning 均来自 `edgar` 依赖的 deprecated import，
不是本切片回归。

## Documentation and commit boundary

S1+S2 没有改变最终用户可见入口、输出通道、工作流、测试运行规则或 README 所有的架构说明，因此本切片
不触发 README 修改。accepted commit 只包含：

- S1+S2 production 与 owner-level tests；
- implementation、双路 review、review fix、双路 re-review 与本 acceptance artifact。

不包含 S3 projection、README、aggregate deepreview、final closeout，也不修改 frozen evidence、
`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 或 CLI CI registry。

## Residual risks

- `covered by later approved slice`：summary、durable、direct、CLI、tool/LLM warning projection 与 README
  触发检查，由 S3 完成。
- `assigned to later work unit`：name-only metadata batch 的 writer lock/physical swap 成本；material 若未来
  需要同类 warning 的独立 owner/schema；commit durable 后 guard-release/cleanup 异常的运维可见性。
- `rejected-with-reason`：内部错误文案统一与 production normalization 改写。
- 未分类 residual risk：无。

## Completion status

UF-FIX11 原子 S1+S2 implementation gate 已通过。Controller 接受该切片提交；提交完成后才可开始 S3。
