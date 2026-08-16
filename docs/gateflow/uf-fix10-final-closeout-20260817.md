# UF-FIX10 same-request-concurrency final closeout

## Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`final closeout pass`
- 日期：2026-08-17
- branch：`codex/upload-filing-oracle`
- work-unit base：`656b926c`
- accepted commits：
  - `46972e72`：accepted plan
  - `5a2f821b`：S1 scope amendment
  - `d97d233b`：S1 second amendment
  - `7e094182`：S1 publication owner contracts
  - `047691c8`：S2 same-request publication convergence
  - `dd4e50ac`：final deepreview test evidence closure
- completion status：`FINAL CLOSEOUT PASS`
- blocking open questions：无
- PR：按用户明确指示跳过；未创建 PR

## 最终结论

UF-FIX10 已从 root cause、owner contract、production lifecycle、workflow projection、deterministic
tests、README、两轮 code review 与整 work-unit final deepreview 全部闭环。

同一 exact filing `auto` 请求的两个 caller 现在都在 conversion 后进入 per-ticker writer owner：
先取得 batch 的 caller 在 fresh state 仍缺失时发布；后取得 batch 的 caller 在任何 company/source
mutation 前从 batch-protected authoritative view 重放同一 validator，并且只有在 fresh COMPLETE、
company durable facts 已满足、prepared/durable publication identity exact equal 时收敛为 canonical
skip。winner 报告实际 stored originals；loser 保留 requested count、stored=0，不新增 source version，
不重写 assets/meta/manifest，不误报 conversion events。

显式 create/update 没有被 auto/skip 吞并：create+no-overwrite 竞争为 typed
`SOURCE_PUBLICATION_CONFLICT`；create+overwrite 使用 fresh source meta rebase 后真实发布；stable
explicit update 保持既有 identical skip，changed update fail closed。repair/unsafe、取消、batch acquire/
read、commit/rollback 与 late-cancel 继续由既有 typed failure 和 atomic publication owner 承诺。

## Owner 与线性化验收

- storage owner 提供 strict path-free `FilingUploadPublicationIdentity`、staging batch fresh reader、
  durable identity projection与既有 per-ticker writer/old-or-new commit。
- Docling owner 产生 required typed initial skip disposition、prepared identity、canonical skip result 与
  create-overwrite fresh rebase；material early skip 保持不变。
- shared filing publication owner 固定 begin → cancel1 → fresh read/validator → closed arbitration →
  cancel2 → rollback skip/conflict/cancel 或 stage+commit publish 的唯一顺序。
- SEC/CN/HK 只调用 shared owner并投影 authoritative outcome，不复制 arbitration；failure/cancelled
  action 使用 initial request，publish/skip success 使用 fresh request。
- 同 ticker mutation 由 ticker writer 串行并从 staging clone fresh view 保留不同 filing/company aliases
  exact union；不同 ticker 可在各自 batch fresh-read 段同时会合，无 global/workspace lock。

## 最终 review closure

- S2 首轮两路 review：`code-review-20260817-024912.md`、`024321.md`；异常边界、取消 action、
  runtime completion、different-ticker barrier、durable conflict 与 alias union findings 全部修复。
- S2 re-review：`code-review-20260817-031615.md`、`032141.md`，均 PASS。
- 整 work-unit final deepreview：MiMo `code-review-20260817-033113.md` 为 PASS；DS
  `code-review-20260817-034314.md` 确认生产 PASS，并提出三个低严重度 test evidence gap。
- final test-only fix re-review：`code-review-20260817-035840.md`、`040335.md`，均 PASS；
  multi-file loser events/winner identity、same-ticker document/assets exact union、create-overwrite
  两次 commit fresh meta/version/revision 均有真实端到端证据。

没有未关闭 finding 或 blocking open question。

## 最终验证

- final test-only 定点：`6 passed`。
- UF-FIX10 accepted focused：`746 passed`。
- 完整 `pytest tests/fins -q`：`1916 passed, 1 skipped`。
- modified production coverage：CN `93%`、Docling `89%`、publication owner `87%`、SEC `94%`，
  合计 `90%`。
- 全仓 `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- final re-review 独立复核：SEC stream `46 passed, 3 warnings`；测试文件 pyright 0；
  `git diff --check` 通过。

既有 warning 仅为 edgar deprecation warning；无本 work unit 新 warning 或 expected red。

## README 与排除项

- 已按职责更新 `dayu/fins/README.md` 与 `tests/README.md`。
- 根 README、`dayu/README.md`、Host/Engine README 不更新：CLI、安装、用户工作流、分层或装配未变。
- 未修改 material、UF-FIX11、Host/Engine/Service/CLI production、tool schema。
- 未修改 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 或冻结 evidence。
- 未执行 UF-PF10、UF-PF12 或真实 CLI evidence。
- 未新增通用 OCC、distributed/global/workspace lock、retry、sleep/polling 竞争证明、目录扫描或
  repository-lock 人工绕过。

## 已分类 residual risks

- dynamic service-runtime monkeypatch fake 当前不进入 batch-read call path；未来触发该路径或协议再次
  扩展时由 fixture owner 同步。
- CN/HK 已覆盖 identical-auto shared route；same-ticker different-filing exact union 的完整 workflow
  证据集中在 SEC，未重复 market-specific case。
- 跨进程覆盖 exact-auto winner/skip；explicit create/cancel/rollback failure 由线程/owner 级确定性测试
  覆盖。
- converter 非确定性导致 derived identity 不等时保持 typed conflict，是已记录的 fail-closed tradeoff。
- legacy `_wait_terminal` polling 只属于本 work unit 之前的非 publication-matrix tests；本轮新增并发
  证据均使用 Barrier/Event/Queue/future 有界通知。
- manual filesystem writer、SHA-256 理论碰撞与 post-COMMITTED guard release 属于已分类 later-work-unit
  operational risk。

无未分类 residual risk。

## Closeout decision

目标已完成，验证、review、docs 与提交均闭合。按用户要求不创建 PR，本 work unit 以
`FINAL CLOSEOUT PASS` 结束。
