# UF-FIX11 plan review fix artifact

## 1. Gate 元数据

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- Gate：`plan review -> fix -> re-review`
- Fix 状态：`fix-complete-awaiting-re-review`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 修订目标：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- 当前 gate：`re-review`
- 下一入口：`re-review`
- Artifact path：`docs/gateflow/uf-fix11-plan-review-fix-20260817.md`
- Blocker：无

本次只完成 plan-review fix，不进入 re-review/implementation，不修改生产代码或测试，不运行真实 CLI evidence，不创建 PR。

## 2. 输入证据

已完整读取并以 controller 裁决为唯一 fix 决策源：

- `AGENTS.md`
- `/Users/leo/.agents/skills/gateflow/SKILL.md`
- `docs/reviews/plan-review-20260817-090453.md`
- `docs/reviews/plan-review-20260817-091441.md`
- `docs/gateflow/uf-fix11-plan-review-adjudication-20260817.md`
- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`

两份 review 均为 `pass-with-risks`；controller decision 为 `fix-required-before-re-review`。controller 明确确认架构方向成立，所需修复仅是 code-generation-ready 规格与验收边界收敛。

## 3. Scope 与 changed files

### 3.1 Changed files

- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- `docs/gateflow/uf-fix11-plan-review-fix-20260817.md`（新增）

### 3.2 未修改

- 生产代码：无
- 测试代码：无
- Host/Engine：无
- material：无
- `docs/cli_ci_oracles.json`：无
- scenario/oracle/evidence runner：无
- frozen evidence/真实 CLI evidence：无
- README：无；用户可见行为尚未实施，README 更新仍保留在 approved implementation Slice 3
- PR/commit/push：无

## 4. 第一性原理 fix 判断

此次 review 没有推翻 root cause：ignored-name fact 仍必须由 company-meta commit owner 基于 publication-lock final `CompanyMeta` 产生；合法 alias 在 source skip 时仍必须通过既有 batch/identity guard/alias uniqueness 原子持久化。

A1/A2 的建议会把 warning 改回 commit 前 snapshot 推断，或让合法 alias 在 skip 时继续丢失，均违背已确认 goal 和唯一 semantic owner。因此保留 `rejected-with-reason`。A3-A10 则揭示了真实的实施/验收缺口，全部按 controller 要求写死在 plan 中。

## 5. A1-A10 finding 状态

### A1 — name-only commit 刷新 updated_at / 属不必要 mutation

- Controller decision：`rejected-with-reason`
- Fix/re-review 状态：`证据失效`（原 finding 反例不成立；等待 re-review 确认）
- 保留理由：等价名称在 plan 中本来就是 `keep + rollback`；不等价名称才进入 commit owner。`_company_meta_from_published` 在 identity 不变时保留原 `updated_at`，final meta 逐字段相同。
- 未采纳内容：不得按 review 建议在 commit 前比较 snapshot 并生成 warning。
- Plan 修订：§8.3、§13.1、§13.3 明确 final company meta 字段/序列化 bytes、`updated_at` 与 source tree hash 不变；锁/physical swap 成本独立列为 later-work-unit residual。
- 验收证据要求：name-only metadata commit 测试断言 final meta bytes/字段和 source tree exact unchanged，但 warning 仍来自 commit outcome。

### A2 — SKIP+preserve 与 UF-FIX10 no-mutation 冲突

- Controller decision：`rejected-with-reason`
- Fix/re-review 状态：`证据失效`（原 finding 把 source skip 与 company identity mutation 混为同一 contract；等待 re-review 确认）
- 保留理由：UF-FIX10 的 no-mutation 约束针对 filing/source assets、version、meta、manifest；用户已明确授权 source skipped 时合法 company alias 仍需原子持久化。
- 未采纳内容：不得取消 SKIP+preserve metadata commit，也无需重新询问用户。
- Plan 修订：§8.3、Slice 2 tests、§13.1 明确 company identity metadata 是唯一例外；source stage token 必须为空，source tree/content hash、version、assets/meta/manifest exact unchanged。
- 验收证据要求：alias durable，source publication zero mutation；collision/failure 无 partial mutation。

### A3 — `commit_batch` 返回类型 / fake 收敛验证盲区

- Controller decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan 修订：
  - §6.4 明确 pyright 因 `-> None` 协变不能单独强制收敛。
  - §9.2 增加 dayu 3 个定义（1 个 Protocol + 2 个 implementation）、test 7 文件/9 定义的完整 `def commit_batch` 清单；标明 `test_docling_upload_service.py` 有 3 个定义。
  - Slice 1 allowed files 覆盖全部 7 个 fake 文件，并区分 outcome success 与 no-intent download `None`。
  - §12.5 增加 `rg -n "def commit_batch" dayu tests`，要求输出与清单 exact 对应并逐项检查行为断言。
- Residual：fake 漏改风险为 `fixed in current slice`（由实施时清单、rg、exact outcome tests 和 pyright 共同关闭）。

### A4 — `warnings` 缺失 / `null` schema 行为

- Controller decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan 修订：
  - §6.6 与 Slice 3 明确 filing 所有 terminal payload 必须显式输出 `warnings`，空为 `[]`；failed/cancelled/delete 只能为空。
  - `FinsUploadPipelineResult.from_pipeline_json(result, *, source_kind: SourceKind)` 新增无默认值显式参数；filing/material callsite 分别传 `SourceKind.FILING`/`SourceKind.MATERIAL`，不得从 payload 猜类型。
  - 字段缺失只允许显式 `SourceKind.MATERIAL` 的 out-of-scope material payload，并映射空 tuple；明确不是旧 schema compatibility。
  - `null`、错误类型、未知 kind/message、重复或超限对象全部 fail closed。
  - 测试矩阵分别命名 filing missing/null 与 material-only missing。
- Residual：schema ambiguity 为 `fixed in current slice`；material warning 本身仍 `assigned to later work unit`。

### A5 — warning 文案未直说“提交未生效 / 现有被保留”

- Controller decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan 修订：固定唯一文案逐字改为：

  `本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。`

  §6.3、Slice 3 CLI tests 与 §12.5 都要求 exact match；仍不回显 raw names，不含路径或内部术语。
- Residual：文案漂移风险为 `fixed in current slice`，由单一常量/closed codec/exact projection tests 关闭。

### A6 — `UploadOperationResult` semantic drift / 双载体消费歧义

- Controller decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan 修订：
  - 保留 `UploadOperationResult.company_meta_commit_outcome` 作为 `commit_prepared_upload_batch` 到 shared filing publication 的最小内部载体；不另建扩散 material caller 的 wrapper。
  - shared filing publication 是内部 outcome 的唯一业务消费者，也是 `FilingUploadPublicationOutcome.warnings` 的唯一生产者。
  - SEC/CN 主分支只读 shared outcome warnings，禁止读取内部 outcome；early cancelled/delete 显式 `warnings=()`。
  - 增加 `outcome.warnings == projection(outcome.result.company_meta_commit_outcome)` owner invariant 与早退/delete 无 warning tests。
- Residual：双源消费风险为 `fixed in current slice`；内部字段不进入 JSON、不越过 shared owner。

### A7 — SKIP+preserve 继承 whole-tree COMPLETE 校验

- Controller decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan 修订：§8.3、状态表、Slice 2 allowed files/tests/stop condition 明确 metadata-only commit 继续服从 `_validate_complete_source_tree`。同 ticker 存在无关 `REPAIR_REQUIRED`/非 `COMPLETE` source 时必须 typed failure、无 warning、无 alias/company/source partial mutation，不新增 bypass。
- Residual：degraded-tree 行为的不确定性为 `fixed in current slice`（通过明确 fail-closed contract 与 owner/workflow tests 关闭）；fail-closed 本身是接受的当前权衡。

### A8 — SKIP 分支可能误复用 filing publish helper

- Controller decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan 修订：§8.3 与 Slice 2 写死：

  `stage_upload_company_meta_decision(...) -> batching_repository.commit_batch(batch) -> build_prepared_filing_skip_result(...) -> dataclasses.replace(...)`

  并禁止 `publish_prepared_upload(...)`、`commit_prepared_upload_batch(...)` 与任何 filing/source asset staging。
- 验收：source stage token 空、published tree hash exact unchanged；对应 stop condition 已加入。
- Residual：误 publish 风险为 `fixed in current slice`。

### A9 — durable job `result_summary` 未规格化 warnings

- Controller decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan 修订：§6.6、§7.2、Slice 3 与 §12.5 明确 `FinsUploadResultSummary.to_json_summary()` 必须写 `warnings`，空为 `[]`；saved job `result_summary`、direct/CLI/tool 使用同一 typed tuple。既有 re-read 只读 `status`/`document_id`，不得重算 warning。
- 验收：durable record exact warning tests 与 re-read regression。
- Residual：durable/UI/tool drift 为 `fixed in current slice`。

### A10 — 并发 final-truth 测试未落名

- Controller decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan 修订：Slice 2 增加两个明确的 barrier/event-controlled tests：
  1. 同 ticker publish 完成后，stale-prepared 请求 fresh-recheck 为 skip+alias/name；断言 warning/outcome 与 final durable meta 一致且 source tree 不变。
  2. 跨 ticker 竞争同一 alias；断言唯一 winner，loser typed collision failure、无 warning/partial mutation，最终 alias owner 与 returned outcome 一致。
- 约束：使用 `threading.Barrier`/`threading.Event`；禁止 `sleep`/polling。
- Residual：并发验收缺口为 `fixed in current slice`。

## 6. Residual risks 与 uncovered areas

| Residual | Classification | Owner/destination | 本轮处理 |
| --- | --- | --- | --- |
| name-only metadata batch 的 writer lock/physical swap 成本 | `assigned to later work unit` | 后续性能/存储 work unit | 本轮以 publication-final correctness 优先；若测试暴露 correctness/stability 回归则不得 defer |
| degraded unrelated source 使 metadata-only commit fail closed | `fixed in current slice` | UF-FIX11 implementation/review | 已冻结 contract 并要求 owner/workflow tests；禁止 bypass |
| material company-name warning | `assigned to later work unit` | 独立 material work unit | 本轮只允许 shared parser 的 material-only missing warnings 规则，不改 material schema/flow |
| 真实 CLI evidence、oracle/scenario/frozen evidence | `assigned to later work unit` | evidence work unit | 用户明确排除，本轮不运行、不修改 |
| durable 后 guard-release/cleanup 报错时不发 warning | `assigned to later work unit` | storage operations work unit | 沿用既有 failure contract，不补发或猜测 success |

没有 `covered by later approved slice`、`tracked by existing issue` 或 `requiring new issue or explicit user decision` 项；没有未分类 residual risk。

## 7. Validation

本 fix gate 仅修改 Markdown plan/artifact，因此没有运行 pytest、coverage 或 pyright，也没有运行真实 CLI evidence。实施 gate 的测试、coverage、pyright 与 static commands 已在 plan §12 固化。

本 gate 的静态验证要求：

- plan/fix artifact 均存在且无 trailing whitespace；
- plan current gate 与 next entry 均为 `re-review`；
- A1/A2 明确保留 `rejected-with-reason`，未落入 implementation changes；
- A3-A10 全部在 plan 与本 artifact 标记 `已修复`；
- plan 包含 fake 全集/`rg`、material-only missing/null、精确文案、唯一 shared outcome 消费、whole-tree fail-closed、direct SKIP metadata commit、durable summary、barrier/event tests、source zero-mutation；
- `git status --short` 除 UF-FIX11 goal/plan/review/adjudication/fix artifacts 外无新改动；
- 生产代码、测试、README、Host/Engine/material/oracle/scenario/frozen evidence 无 diff。

实际执行结果：

| 检查 | 结果 |
| --- | --- |
| `rg -n "def commit_batch" dayu tests` | 通过；实际为 dayu 3 个定义（Protocol 1 + implementation 2）、test 7 文件/9 定义，与修订后清单一致 |
| A1-A10 heading/status 扫描 | 通过；A1/A2 为 `rejected-with-reason`/`证据失效`，A3-A10 均为 `accepted`/`已修复` |
| 关键 contract 扫描 | 通过；fake rg、显式 `SourceKind`、material-only missing、`null` fail-closed、精确文案、唯一 shared consumer、whole-tree fail-closed、direct SKIP commit、durable summary、Barrier/Event、source zero-mutation 均存在 |
| trailing whitespace 扫描 | 通过；两份 changed artifact 无匹配 |
| `git diff --name-only` | 为空；没有 tracked 生产/测试/README 改动 |
| `git status --short` | 仅 UF-FIX11 goal/plan/review/adjudication/fix artifacts 为 untracked，无范围外文件 |

## 8. Docs decision

本 gate 的文档职责就是修订 plan 并新增 fix artifact。README 记录稳定已实现行为，当前尚未进入 implementation，因此本 gate 不更新 README；plan Slice 3 保留实施后的 README 触发决策。

## 9. Completion status

- Accepted findings A3-A10：`已修复`，等待 re-review 验证。
- Rejected findings A1/A2：保留 `rejected-with-reason`；原反例证据在 controller 裁决下失效，不得误实施。
- Blocking open question：无。
- Unclassified residual risk：无。
- 当前 gate：`re-review`。
- 下一入口：`re-review`。
- Implementation：未进入。
- PR：未创建。
