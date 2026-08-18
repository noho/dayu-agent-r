# upload-filing-ticker-alias-contract plan re-review controller adjudication

## Gate metadata

| 字段 | 值 |
| --- | --- |
| Gate | `plan re-review adjudication` |
| Work unit | `upload-filing-ticker-alias-contract` |
| Adjudicator | `AgentController` |
| Timestamp | `2026-08-14 22:36:24 +0800` |
| Reviewed plan | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-codex.md` |
| Reviewer artifacts | `docs/reviews/plan-rereview-20260814-222224-mimo.md`; `docs/reviews/plan-rereview-20260814-222224-ds.md` |
| Decision | `fail` |
| Next gate | `plan fix` |

## Controller conclusion

AgentMiMo 的 `pass` 证明 A1–A8、R1/R2、commit-time authoritative merge、锁序与 typed failure 的主体设计已经闭合；AgentDS 的 `fail` 提供了更强的直接反例，因此本 gate 以 `fail` 裁决。唯一 blocker 不是锁或 merge 架构，而是修订计划把 `meta.json` 缺失误定义为 workspace corruption。

直接代码与数据流证据表明，`FilingUploadPublishedState.company_meta=None` 是公开建模的合法状态，material upload 不产生 CompanyMeta，既有公开 batch API 也能发布只含 descriptor/文档而无 `meta.json` 的 corpus。故“published corpus 存在但 CompanyMeta 尚未到达”是合法 durable state，不是损坏。若按当前计划实现，任一 material-first corpus 会阻断整个 workspace 的 alias read 和任何后续 meta commit，并使该 corpus 无法通过正常上传补齐 CompanyMeta；这与现有生产数据流和本 work unit 的 alias 目标均冲突。

## Accepted findings and required fixes

### P1 — accepted/blocker：meta-less corpus 是 canonical-only identity，不是 corruption

Plan fix 必须同时修订 §5.5、§5.6、§7.4、§11.3 及所有关联表述，冻结以下语义：

1. `missing_meta` 从 `CompanyTickerIdentityCorruptionKind` 删除。合法 published ticker directory 由 ticker identity descriptor 拥有 canonical corpus identity；缺少 `meta.json` 时，该 corpus 只贡献 descriptor canonical lookup，不贡献任何 alias。
2. authoritative published scan 必须枚举并严格校验每个实际 `portfolio/` ticker directory 的 identity descriptor。每个合法 descriptor canonical 都进入唯一 index；只有存在且严格解析成功的 CompanyMeta 才额外贡献 `ticker_identity.accepted_aliases`。
3. `meta.json` 存在但 JSON/schema/grammar 非法仍是 `invalid_meta` corruption；CompanyMeta canonical/market 与 directory descriptor 不一致仍是 `identity_mismatch`；任一 lookup key（包括 meta-less corpus 的 canonical）被另一 corpus 的 canonical 或 alias 占用仍是 `duplicate_owner` / incoming conflict。不得因 meta 缺失而跳过 canonical 所有权。
4. `resolve_company_ticker` 必须复用同一 unique index。因此 meta-less corpus 的 canonical query 保持可读并路由自身 corpus；它没有 accepted alias，alias query不会凭空命中。健康 corpus 的 canonical/alias read 不得被无关 meta-less corpus阻断。
5. incoming canonical target 已存在且 descriptor 合法但 `meta.json` 缺失时，commit authoritative current 为 `None`，允许 `refresh_if_stale` 的 create transition 给 material-first corpus首次补齐 CompanyMeta；该 corpus descriptor canonical仍参与冲突验证。
6. prevalidation 观察到 CompanyMeta、commit-time CompanyMeta却缺失的状态不是 durable corruption；它表示 optimistic precondition失效，必须投影为 `CompanyMetaConcurrentUpdateError` 并在任何 backup/swap 前 fail closed。
7. 测试必须覆盖：material-only/meta-less corpus canonical `list_documents`；它与健康 alias corpus共存时双方正常查询；给 meta-less corpus补 CompanyMeta成功；另一 corpus alias撞其 canonical时原子拒绝；invalid meta、identity mismatch、duplicate owner仍 fail closed；prevalidation 后 meta 消失走 concurrent-update typed failure。

该裁决保持 CompanyMeta 为 alias 声明真源，同时承认 storage ticker descriptor 是 corpus canonical identity 的既有 durable owner；两者不是重复 grammar。descriptor 只持久化 owner 已产生的 exact canonical，不解析或推断 alias。

### P2 — accepted/non-blocker：补齐机械迁移 consumer/test 清单

将以下旧 `FmpCompanyInfo` 构造 consumer 加入 §9.3、S1 allowed tests、focused/regression validation与 residue 说明：

- `tests/cli/test_prompt_command.py`
- `tests/service/test_entrypoint_runtime.py`

新 fixture 必须以 `CompanyTickerIdentity` 表达 canonical 与 accepted aliases；canonical-equivalent 值不得继续作为 accepted alias 固化。

### P3 — accepted/non-blocker：修正 6-K repair 验证表述

现有 module-level regression 没有直接执行 `_resolve_target_tickers` 的被改分支。Plan fix 应把“既有 repair regression 已覆盖”修正为“新增或扩展 public-path regression 精确触达 `_resolve_target_tickers` 的 CompanyMeta ticker projection，并由逐文件 coverage gate兜底”，不得声称未发生的直接覆盖。

## Findings kept closed

以下内容经两路 reviewer 与 controller 复核后保持 closed，不在下一轮重开：

- A1：same-canonical prevalidation snapshot lost-update；authoritative current + stable alias union设计保留。
- A2：6-K production consumer已纳入；只修正测试精度表述。
- A3：S1 `alias -> list[canonical]` 临时契约与 S2 原子切换。
- A4：incoming conflict 与 durable corruption分型；仅从 corruption kinds移除`missing_meta`。
- A5：`UploadCompanyNameRequiredError` 收窄 catch owner。
- A6：invalid meta / identity mismatch / duplicate owner 在 published mutation前 fail closed；仅纠正合法 meta-less state。
- A7：recovery/read barrier及 identity guard acquire/release failure测试。
- A8：S1 只是不可部署 checkpoint，S2强制连续完成。
- R1：recovery不得用 `meta.json` 是否存在猜 transaction-local mutation。
- R2：`_STORAGE_FAILURE_CODES` 是计划新增项，不是当前遗漏。

## Rejected or deferred observations

- AgentDS 提到 resolver version producer 不一致：属于既有行为且本 WU 不恶化，`assigned to later work unit`。
- workspace scan性能、recovery全量 guard等待、旧 schema/migration、UF-PF05、oracle/scenario/frozen evidence：保持既有 later-work / explicit exclusion 分类。
- meta-less corpus canonical read 选择 `NOT_FOUND`：rejected-with-reason。直接 canonical probe 是现有合法行为，material-first corpus含真实文档，改为 NOT_FOUND 会扩大用户可见回归且与 storage descriptor 的 canonical ownership冲突；本 WU保留 canonical可读。

## Exit criteria for next re-review

下一轮只复核 P1–P3 是否精确落入 plan 与 test matrix，并确认已关闭的 A1–A8、R1/R2未被回退。若通过，创建 accepted plan local commit并自动进入 S1 implementation；不得创建 PR、不得 push。
