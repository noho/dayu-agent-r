# upload-filing-ticker-alias-contract plan review controller adjudication

## Gate state

- Gate: `plan review`
- Work unit: `upload-filing-ticker-alias-contract`
- Reviewed plan: `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-codex.md`
- Reviewer artifacts:
  - `docs/reviews/plan-review-20260814-215912.md`（AgentMiMo，`pass-with-risks`）
  - `docs/reviews/plan-review-20260814-220204.md`（AgentDS，`fail`）
- Controller decision: `fail; plan fix required`
- Completion status: `plan review complete`
- Current gate / next entry point: `plan fix`
- Artifact path: `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-review-controller-adjudication.md`

## Evidence and decision rule

Controller 完整读取两份 review artifact、plan、goal confirmation 与 reviewer 指向的直接代码路径。裁决以 confirmed business contract、实际 prevalidation/batch/commit/read 数据流和项目 semantic-owner 约束为准；reviewer 结论本身不是事实。

## Accepted findings

### A1 — 同 canonical 并发 lost update（DS F1）

- Decision: `accepted`
- Severity: `高`
- Evidence: `validate_fins_upload_filing_request` 在 writer lock 之前用 published snapshot 生成 `company_meta_decision`；SEC/CN workflow 在 `begin_batch` 后直接 stage 该旧决策。plan 的 commit validation 又排除 incoming canonical 旧 meta且不 re-merge。
- Failure: P1 prevalidate v1 后暂停，P2 提交 alias Y，P1 再用 v1-based staged meta commit，会静默覆盖 Y。
- Required fix: plan 必须把 authoritative merge 移到 writer/recovery/identity 保护的 commit-time owner；在 identity guard 内重读 incoming canonical current published meta，与 staged declared/accepted aliases稳定 union，再校验冲突并投影最终 staged CompanyMeta。prevalidation decision 只能表达拟议 alias intent和非并发前置条件，不能成为 commit-time merge base。
- Required validation: barrier-controlled same-canonical cross-process test，覆盖两个提交均保留 aliases，或 stale writer以明确 typed failure失败且 published tree不变；不得静默丢失。

### A2 — 受影响文件漏项（DS F2）

- Decision: `accepted`
- Severity: `中`
- Evidence: `dayu/fins/pipelines/sec_6k_primary_document_repair.py` 消费 `entry.company_meta.ticker`，而 plan 移除该字段却未把文件纳入 S1 allowed files。
- Required fix: 将该文件加入 affected/allowed file scope，机械迁移到唯一 identity projection；补对应 residue/pyright validation，若无专门测试则记录由相关 storage/repair regression覆盖。

### A3 — S1 storage 中间契约未冻结（DS F3）

- Decision: `accepted`
- Severity: `中`
- Evidence: S1 计划删除 `_canonicalize_ticker_alias` / `_normalize_company_ticker_aliases`，但保留的 `resolve_existing_ticker` 与 alias index helper 当前直接依赖两者。
- Required fix: 明确 S1 将内部 route/index 改为只消费 `ticker_identity.lookup_tickers()`；在 S1 中仍保留 `alias -> list[canonical]` 与 duplicate-owner late `ValueError` 行为，直到 S2 原子 route 一次切换；列清 residue scan 的临时允许项和 S2 删除点。

### A4 — read-side durable conflict/corruption failure 未定义（DS F4；合并 MiMo F2）

- Decision: `accepted`
- Severity: `中`
- Evidence: plan 让 read route 抛带 incoming ticker 字段的 upload-conflict exception，但 read 场景没有 incoming canonical；当前 `fins_tools` generic exception 只会投影 `execution_error`。
- Required fix: 区分 incoming commit conflict 与 published identity corruption。storage public route应对 durable duplicate/invalid identity使用适合 read/write scan 的 typed corruption error；read runtime必须映射为 path-free、有界、可行动的 `FinsReadBusinessError`，upload commit conflict继续映射为 terminal `ticker_alias_conflict`。补 identity guard获取失败、durable duplicate/invalid state的 read owner/tool projection tests。

### A5 — builder ValueError 被误报 company-name-required（DS F5）

- Decision: `accepted`
- Severity: `低`
- Evidence: ingestion prevalidation 当前把 `resolve_upload_company_meta_decision` 的任意 `ValueError` 映射为 `COMPANY_NAME_REQUIRED`；identity builder新增 alias grammar `ValueError` 后，错误原因 owner会扩大。
- Required fix: plan 必须用 typed company-meta requirement error或前置显式判定收窄 missing-company-name reason；invalid alias继续唯一映射 `INVALID_TICKER_ALIAS`，不能依赖偶然调用顺序兜底。

### A6 — commit scan 遇到 invalid published meta 的行为缺失（DS F6）

- Decision: `accepted`
- Severity: `低`
- Evidence: storage inventory已有 `invalid_meta` 状态；commit uniqueness scan若跳过损坏项，会允许新 corpus 抢占损坏 meta可能声明的 alias，而 read又 fail closed。
- Required fix: commit-time identity scan遇到 missing/invalid/corrupt CompanyMeta必须在任何 backup/swap前 fail closed；不能跳过、默认空 aliases或猜测。补 published invalid meta阻断 meta commit且 tree hash不变的测试。

### A7 — recovery/read 并发测试缺口（MiMo F4）

- Decision: `accepted`
- Severity: `低`
- Evidence: plan只覆盖 meta commit与 recovery crash interleaving，没有证明 alias read在 recovery physical restore期间被正确串行化。
- Required fix: 增加 barrier-controlled recovery + alias read测试，断言 read不观察中间 tree，恢复后返回正确 route；增加 recovery identity guard获取失败时无 physical restore的 fail-closed测试。

### A8 — S1 完成语义需要澄清（MiMo F3）

- Decision: `accepted`
- Severity: `低`
- Evidence: S1 是 Gateflow checkpoint，不是可部署/可关闭 work unit；原 plan 的“可独立验证增量”容易被误读为满足全部 success signals。
- Required fix: 明确 S1 仅是 reviewed checkpoint，仍保留 late-conflict既有行为，不得部署/close；S2 是达成 goal confirmation 的强制后续。plan 顶部错误声称“用户要求 plan complete 后停止”也必须删除，恢复 Gateflow 自动推进语义。

## Rejected findings

### R1 — recovery 只对含 meta.json orphan 取得 identity guard（MiMo F1）

- Decision: `rejected-with-reason`
- Reason: 当前 batch staging会复制既有 ticker tree，`meta.json` 存在不能证明本 batch 修改过 CompanyMeta；crash 后 transaction-local `company_meta_staged` 不可恢复。用文件存在推断 mutation违反 semantic-owner约束并重新打开 crash窗口。当前没有 measured latency 证据支撑弱化 correctness guard。
- Residual classification: 无；若未来 profiling 证明 recovery contention，由独立性能 work unit在不削弱恢复正确性的前提下处理。

### R2 — `_STORAGE_FAILURE_CODES` 当前不存在（MiMo F5）

- Decision: `rejected-with-reason`
- Reason: plan §5.6 明确写的是“新增 `_STORAGE_FAILURE_CODES`”，并明确在 generic/OSError 前识别 typed conflict；这不是 implementation 遗漏。所需 mapper unit test已经列出。

## Residual risks

- 旧 workspace 歧义 aliases / 旧 CompanyMeta schema：`assigned to later work unit`，用户明确要求 fresh schema、不做兼容迁移。
- UF-PF05 真实 CLI evidence：`assigned to later work unit`，用户明确排除。
- oracle/scenario registry、冻结 evidence与其它 finding：`assigned to later work unit`，用户明确排除。
- CompanyMeta全 workspace scan性能：`assigned to later work unit` only if measured；当前不新增 durable index/cache。
- 本 review loop没有 unclassified residual risk。

## Validation

- 两份 reviewer artifact均符合 planreview timestamp路径要求并提供代码证据。
- AgentDS 只读验证现有 storage suites：256 passed；coverage基线表明关键 storage文件的80%目标可达。
- Controller执行 `git diff --check` 通过；工作树只有本 work unit artifacts。

## Completion status

Plan review gate 已完成并判定 fail。所有 accepted findings均有明确 plan fix要求；没有 blocking user question。next entry point 为 `plan fix`，由 AgentCodex修订 plan并产出 fix artifact，随后进入两路 `plan re-review`。
