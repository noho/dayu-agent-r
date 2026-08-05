# PR 190 F11/F12 S5 registry/docs implementation（2026-08-06）

## Gate metadata

- Work unit：PR 190 F11/F12 interactive memory closure。
- Slice：S5 registry/docs implementation。
- Baseline HEAD：`1a79ff1859117027340910152c0ce208a7f37b5d`。
- Gate result：`PASS`。
- Implementation：`PASS`。
- Real observation：`complete`。
- Formal Oracle：`pending`。
- Current gate / next entry point：总控双路 code review。
- Stop boundary：本 artifact 后不调用 reviewer，不运行 frozen formal scenarios，不修改 PR body，不 stage/commit/push。
- Artifact path：`docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md`。

## Goal、动机与 owner 判断

直接 registry 数据证明问题真实存在：旧 `cli.interactive.core-execution@1` 的稳定 predicate 29/30 仍要求模型产生
represented/explicit-drop ledger、四类 reason 与 `policy_limit`；旧 `drop-superseded@1`、`drop-policy-limit@1` 仍把这些
已删除语义作为可执行 required evidence，`tool-trace-formal@1` 仍对应 F11 旧 public projection。S4 已从 public Host Tool
Trace、canonical terminal、compact artifact、Memory、RunInput 与 reconnect 完整观察 fresh contract，因此若不做 lifecycle
replacement，current verdict 会继续执行不可满足的旧 contract。

语义 owner 分别为：oracle registry 拥有 current accepted predicate contract；scenario registry 拥有版本化 observation
obligation、evidence identity 与 adjudication lifecycle；`docs/cli_ci.md` 只说明 current-resolution/usage 规则；readiness artifact
只追加 implementation/observation/oracle 三态。没有在 consumer、fixture、renderer 或兼容分支重算/补偿语义。

## Scope 与 changed files

本 slice 只修改用户授权的五个文件：

1. `docs/cli_ci_oracles.json`
2. `docs/cli_ci_scenarios.json`
3. `docs/cli_ci.md`
4. `docs/reviews/wu-interactive-memory-postfix-readiness.md`
5. `docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md`

未修改 schema、production code、tests、README、PR body 或其它 artifact；未运行 frozen formal scenarios。

## Registry implementation decision

### Oracle lifecycle

- `cli.interactive.core-execution@1` 只把 `status` 改为 `superseded`，并设置
  `superseded_by=cli.interactive.core-execution@2`；其它字段归一化摘要与基线完全一致。
- append `cli.interactive.core-execution@2`：`status=accepted`、
  `supersedes=cli.interactive.core-execution@1`。
- 30 个稳定 `predicate_id` 全部保留；只替换
  `interactive.29-compactor-output-accept-repair-fallback` 与
  `interactive.30-compaction-semantic-memory-closure` 的 contract，使模型只拥有五类业务语义及必要 provenance，Host 拥有
  represented/omitted exact complement、真实 caps、usage audit、bounded repair/fallback、accepted truth 与 public/canonical
  Tool Trace 同源投影。
- authority 明确记录用户于 `2026-08-05` 确认 F11/F12 replacement contract。该 design authority 使 core@2 accepted，
  不会把三条 replacement scenario 的真实 observation 自动裁决为 accepted。

### Scenario lifecycle

- `tool-trace-formal@1`、`drop-superseded@1`、`drop-policy-limit@1` 只修改 `status` 与 `superseded_by`；旧 invocation、
  required/observed evidence、coverage claims、user adjudication 与 frozen oracle refs 均不变。
- append `tool-trace-formal@2`，required evidence 只要求 public Host Tool Trace resolver/analysis response identity、canonical
  terminal equality 与 secret scan。
- append `rolling-correction-replacement@1`，required evidence 固定为 retained current replacement provenance、Host-derived
  omitted old labels、artifact/Memory/post-compact RunInput 无旧结论，以及 reconnect 无旧结论；不要求主观 reason。
- append `cap-constrained-memory-replacement@1`，required evidence 固定为 initial input 的真实 caps、Host cap/usage audit、
  accepted provenance/omitted exact complement、same-boundary bounded repair 与 budget-exhausted fallback，以及
  artifact/Memory/RunInput/reconnect 同源；不要求 `policy_limit` reason。
- 三条 fresh scenario 的 S4 evidence 均为 `sufficient`，但 `status` 均保持 `unadjudicated`，
  `user_adjudication_identity=pending-oracle-controller-adjudication`。
- 两个 registry 顶层 `registry_status` 均继续为 `calibration`。

## Immutable S4 evidence

- Root：`/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`。
- Human-readable report：`observed-report.md`。
- Report SHA-256：`bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411`。
- Root manifest：`digest.json`。
- Manifest SHA-256：`38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`。
- S4 observation：`docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md`。
- S4 acceptance：`docs/reviews/pr-190-f11-f12-s4-evidence-acceptance-20260806.md`。
- Secret scan：2 个 credential sources，exact-value 与 Authorization/Bearer/API-key pattern 均 0 finding；S5 没有重新运行
  provider 或 formal scenario。

## Preservation proof

摘要算法为：对基线/当前旧 record 删除唯一允许变化的 `status`、`superseded_by`，再对 canonical sorted JSON 计算
SHA-256。四条记录的 base/current 摘要逐条相等：

| 旧 record | base/current SHA-256 |
| --- | --- |
| `cli.interactive.core-execution@1` | `d28bec703838dcd57ed827a39b1a976c8bc39c3c5f733b1417f928677cfe92d4` |
| `interactive.interactive.g06.tool-trace-formal@1` | `462355690e5ba61925231c7da23e732ad667bb4a1a13853eb45f4c6fe5724318` |
| `interactive.interactive.g06.drop-superseded@1` | `55d6dd21c4339c3e16ae4cecf18e1c2bf68ba8125daeb873d9469972ce005a01` |
| `interactive.interactive.g06.drop-policy-limit@1` | `ab05fc91b8dcc238055aba4c8a27593eb3434516ef45daf054c4f2512183d000` |

基线的其它 2 条 oracle 与 1053 条 scenario 均逐对象 exact equal；1056 条既有 scenario 的
`accepted_oracle_refs` 全部 exact equal，未批量改写 611 条历史引用。

## Validation

在 `source .venv/bin/activate` 后执行：

| Validation | Result |
| --- | --- |
| `python -m json.tool docs/cli_ci_oracles.json` | PASS |
| `python -m json.tool docs/cli_ci_scenarios.json` | PASS |
| read-only typed loader | PASS；4 oracle records、1059 scenario records，identity/version/status/lifecycle、predicate 与关键 refs 类型有效 |
| inventory uniqueness | PASS；4 oracle keys、1059 scenario keys，无 duplicate identity |
| supersedes graph | PASS；0 dangling、0 cycle、0 asymmetric edge |
| old-entry preservation | PASS；上述四条 lifecycle-normalized digest 相等，unrelated old records 0 变化 |
| frozen accepted refs | PASS；1056 条既有 scenario 的 `accepted_oracle_refs` 0 变化 |
| historical referenced subset | PASS；基线 `1a79ff1859117027340910152c0ce208a7f37b5d` 中至少引用一个 `interactive.*` predicate 的 611 records 共 768 refs、29 个 referenced predicate ids；ref owner 分布为 766 → `cli.interactive.core-execution@2`、2 → `cli.prompt.core-execution@1`，referenced id owner 分布为 28 → `cli.interactive.core-execution@2`、1 → `cli.prompt.core-execution@1` |
| current `command=interactive` inventory | PASS；当前 612 records 共 768 refs、28 个 referenced predicate ids；768 refs 与 28 ids 全部解析到 `cli.interactive.core-execution@2` |
| current full registry inventory | PASS；当前 1059 records 共 1614 refs、64 个 referenced predicate ids；ref owner 分布为 770 → `cli.interactive.core-execution@2`、728 → `cli.prompt.core-execution@1`、116 → `cli.init.workspace-initialization@1`，referenced id owner 分布为 28 → interactive@2、26 → prompt@1、10 → init@1 |
| accepted owner schema inventory / stable resolution | PASS；current accepted owners 共定义 66 个 stable predicates，owner 分布为 30 → `cli.interactive.core-execution@2`、26 → `cli.prompt.core-execution@1`、10 → `cli.init.workspace-initialization@1`；全部 1614 refs 均唯一解析，0 dangling、0 duplicate current owner |
| removed-ledger full registry scan | PASS；scenario 命中仅两个 superseded old records；oracle 命中仅 core@1 predicate 29/30；计划外依赖 0 |
| immutable S4 root/report/digest | PASS；路径存在且 report/manifest SHA-256 exact |
| documentation links | PASS |
| `git diff --check` | PASS |

验证过程中两次 fail-closed 定位并修正了 validator/文档假设，不是 registry contract failure：第一次把 authority 文本要求成
精确 `F11/F12` identity，随后将 authority 写得更明确；第二次错误假设 768 refs 全归 interactive core，direct inventory
证明其中 2 个是合法的跨入口 prompt predicate，因此 validator 与 handbook 改为“每个 stable predicate 恰好一个 current
accepted owner”。最终完整 validation matrix 已通过。

未运行 pytest、coverage 或 pyright：本 slice 没有修改 Python、schema、production code 或 tests，accepted S5 matrix 只要求
registry/docs validation；不以该省略替代任何代码 gate。README trigger 未命中，未修改 README。

当前 registry 文件摘要：

- `docs/cli_ci_oracles.json`：`3404e241dbd71c6244da24b0dbb080022d4c57b36f040ac3456e7a18dbc97acf`
- `docs/cli_ci_scenarios.json`：`f4363fc5e7026ad075f4b7f855342cae493a4852d21bd72ef6e53b3f2d588e37`

## Docs decision

`docs/cli_ci.md` 只新增 oracle lifecycle/current stable-predicate resolution、历史 `accepted_oracle_refs` 保留规则，以及
superseded/unadjudicated replacement scenario 的使用边界。Readiness artifact 只在冻结 finding 原文之后追加最终
implementation PASS、real observation complete、Oracle pending、S4 refs/digests、F11/F12 状态与 next owner；未标 ready。

## Findings、residual risks 与 uncovered areas

- Implementation finding：0。
- `assigned to later work unit`：三条 replacement scenarios 的 Formal Oracle 仍 pending，owner 为 Oracle controller；其后续
  accept/reject 不回写本 slice 已验证的 implementation/evidence 事实。
- `assigned to later work unit`：reconnect 回答可在“已失效历史值”语境引用 raw history；后续 Oracle 裁决必须继续区分 raw
  audit history 与 active semantic Memory/RunInput，owner 为 Oracle controller。
- `assigned to later work unit`：immutable evidence root 的持续保留由 CLI CI evidence-retention owner 负责；registry 已固定
  root/report/manifest identity 与 digest，当前不存在 integrity gap。
- `covered by later approved slice`：S5 双路 code review、finding 裁决/fix/re-review 与 accepted slice checkpoint 尚未执行；
  本轮按用户 stop boundary 停在该 gate 前。

没有未分类 residual risk、blocking open question 或 needs-more-evidence 项。

## Completion status

S5 registry/docs implementation：**PASS**。Real observation：**complete**。Formal Oracle：**pending**。Registry：
**calibration**。下一未完成 Gateflow entry 是总控双路 code review；本轮到此停止。
