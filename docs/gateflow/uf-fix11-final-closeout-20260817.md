# UF-FIX11 local-only final closeout

## Gate 元数据

- gate：`final closeout`
- work unit：`UF-FIX11 upload_filing company metadata ignored-change warning`
- branch：`codex/upload-filing-oracle`
- accepted implementation/deepreview target：`26ec95c1`
- execution mode：`local-only-by-explicit-user-instruction`
- completed at：`2026-08-17`
- completion status：`PASS`
- artifact：`docs/gateflow/uf-fix11-final-closeout-20260817.md`

## Root cause 与唯一语义 owner

直接代码与 accepted oracle 证据确认：fresh canonical company identity 已存在时，publication
边界会保留 canonical name；旧实现只返回 company metadata 是否变更，没有把“用户提交的名称在
最终成功或 skip 后未生效”建模成 typed outcome。CLI、direct command 与 tool/LLM-facing result
因此没有可机械投影的同源事实。问题不属于 CLI 文本格式化层。

修复后的唯一语义 owner 是 publication lock 内、基于最终 authoritative company state 作出的
company metadata commit decision。该 owner 产生闭合的 `CompanyMetaCommitOutcome` 与
`CompanyNameIgnoredChange` typed contract；publication 只有在最终 `SUCCESS` 或 `SKIPPED` 后才把
warning 投影到结果。CLI、runtime summary、durable summary、direct result 与 wait/tool adapter 只
机械转发同一 warning，不读取原始参数、日志、文件状态或 disposition 重新推断。

## 修改结果

- fresh metadata 下提交不同 company name：保留已有 canonical name；最终 success 或 source-exists
  skip 均返回业务可读、可行动且有界的 ignored-change warning。
- company name 缺失，或经 NFKC、空白归一化与 casefold 后与 canonical name 等价：不产生 warning。
- alias contract 保持不变：合法新 alias 由 identity owner 合并、去重、持久化并可用于文档路由；
  canonical-equivalent/重复 alias 不误报；invalid/collision 继续 typed failure。本实现不存在成功但
  合法新 alias 未进入 accepted identity 的真实路径，未制造虚假 ignored-alias 分支。
- stale metadata 下显式名称继续与 filing source 原子刷新；缺少必需名称继续在发布前 fail closed，
  不产生 durable partial mutation。
- failed、cancelled、killed、rolled back 或未完成 publication 不产生 ignored-change warning。
- canonical SKIP 的 arbitration 与 executor 共用同一纯校验函数；非法 company decision 在 stage/
  commit 前拒绝，防止未来状态漂移先提交再失败。
- CLI stdout 与退出码契约不变；warning 写到 stderr。direct command 与 completed wait/tool/LLM
  result 保持同一语义。
- 未修改 Host、Engine、download、material、freshness/version 规则、CLI CI oracle/scenario/registry
  或 frozen evidence。

## Local Gateflow commits

| Gate | Commit |
| --- | --- |
| accepted plan | `c7f5ddb1` |
| accepted slice-boundary amendment | `0b4740fa` |
| accepted S1+S2 | `5bb122d3` |
| accepted S3 projection amendment | `f6893c29` |
| accepted S3 | `91dbf843` |
| accepted aggregate deepreview | `26ec95c1` |

本 artifact 的 local-only closeout commit 由 controller 在写入后创建，其 hash 记录在最终用户报告；
commit 内容不自引用自身 hash。

## Review 与 finding 状态

- plan、slice-boundary amendment、S1+S2、S3 projection amendment 与 S3 均经过 AgentMiMo、
  AgentDS 双路 review/re-review，accepted finding 全部闭环。
- aggregate deepreview 主 artifact：`docs/reviews/code-review-20260817-172506.md`。
- specialist review：
  `docs/reviews/uf-fix11-deepreview-state-owner-mimo-20260817.md` 与
  `docs/reviews/uf-fix11-deepreview-projection-ds-20260817.md`。
- deepreview 发现的 canonical SKIP executor 校验缺口已在 owner boundary 修复；初次修复中不理想的
  frozen-dataclass test seam 随后改为 typed validator wrapper。
- 最终 re-review：
  `docs/reviews/uf-fix11-deepreview-fix-rereview-final-mimo-20260817.md` 与
  `docs/reviews/uf-fix11-deepreview-fix-rereview-final-ds-20260817.md` 均为 `PASS`，无新 finding。
- 所有已接受 finding 均已关闭；无未分类风险、blocking question 或 requiring-user-decision finding。

## Final deterministic validation

- 受影响测试全集：`2158 passed, 1 skipped, 3 warnings`。
- owner 文件：`tests/fins/test_filing_upload_publication.py` -> `41 passed`。
- deepreview 修复最小组：`5 passed`；修复前新增回归测试以 `1 failed` 证明旧行为。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- Ruff：pass。
- `git diff --check 94182a0c...HEAD`：pass。
- 关键修改文件覆盖率：`ingestion_runtime.py` 89%、`service_runtime.py` 88%、
  `direct_events.py` 83%、`output.py` 82%、`fins_wait_adapter.py` 91%、
  `filing_upload_publication.py` branch coverage 84%。
- 测试与 pyright 均在 `source .venv/bin/activate` 后执行；没有新增、扩散或掩盖类型错误。

按明确非目标，本 work unit 未执行真实 CLI post-fix evidence、UF-PF11、UF-PF12 或其他 calibration，
也未修改 frozen evidence 与 CLI CI registry。

## README decision

- `README.md`：更新用户可见 warning 触发条件、输出通道与保留 canonical name 的行为。
- `dayu/fins/README.md`：更新 authoritative decision owner、typed warning 与投影边界。
- `tests/README.md`：更新 owner、并发、CLI/direct/tool 投影与负向 warning 覆盖。
- `dayu/README.md`：不更新；分层关系与装配方式未改变。
- Host/Engine/config 生产目录未修改，相应 README 不触发。

## Residual risks 与后续 owner

| 项目 | 分类 | Owner / 后续 |
| --- | --- | --- |
| `UploadOperationResult.file_events` 仍为可变集合 | pre-existing / later work unit | ingestion result contract owner |
| resolver version 仍依赖人工 bump 纪律 | pre-existing / maintenance | company metadata freshness owner；本轮不改 freshness 规则 |
| material upload 的同类行为 | explicit non-goal / later work unit | 独立 material work unit |
| name-only metadata 更新仍可能执行 physical swap | optimization / later work unit | company metadata publication owner |
| post-commit cleanup 可观测性 | operational / later work unit | storage publication maintenance |
| 真实 CLI/network evidence 与 frozen registry 更新 | explicitly deferred | 后续单独授权的 calibration work unit |

以上均不阻塞本 work unit；没有已知 correctness blocker。

## 外部状态与 next entry point

- push：`not-applicable-by-explicit-user-instruction`
- PR URL / draft PR / ready / reviewer / PR review：`not-applicable-by-explicit-user-instruction`
- merge / branch deletion：未执行
- external issue modification/comment：未提供 issue，未执行
- next entry point：保留当前本地分支与全部 Gateflow commits，用户可审阅或合并当前分支；真实
  calibration 与 registry 更新须在后续独立授权 work unit 中执行。当前 work unit 到达
  `local-only final closeout pass`。
