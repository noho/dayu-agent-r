# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Corrected Aggregate Deepreview — Controller Adjudication

## Gate identity and verdict

- Timestamp：`2026-07-20T10:30:13+0800`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；本 gate是所有内部 remediation sub-WU完成后的 corrected aggregate review。
- Base：`8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`。
- Reviewed HEAD：`de68672b803c4e355d2a18b0fbc2890497053230`。
- Six-path binary/full-index diff SHA-256：`9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd`。
- `LC_ALL=C` sorted path-list SHA-256：`c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf`。
- Verdict：`PASS / ACCEPTED_AGGREGATE_FINDING=0 / NEW=0 / BACKFLOW=0 / BLOCKER=0 / ZERO_CHANGE_FIX_AND_DUAL_REREVIEW_REQUIRED`。

## Dual aggregate evidence

| Reviewer | Artifact | Lines | SHA-256 | Verdict |
| --- | --- | ---: | --- | --- |
| AgentMiMo | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-corrected-aggregate-deepreview-mimo.md` | `452` | `dec40a45edb5666bee732ba802d8137d1bad8f22c9bc592bdc35fc7d2a6ad692` | PASS / finding `0` / backflow `0` / blocker `0` / open `0` |
| AgentDS | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-corrected-aggregate-deepreview-ds.md` | `492` | `3137674c8d583ac868355e7dc724c59dafe497fc88534b027c9739a4ba8d443e` | PASS / new `0` / backflow `0` / blocker `0` / open `0` |

AgentDS第一次 path-list摘要 `e911...` 使用未冻结locale排序；same-task follow-up按 `LC_ALL=C sort`复算 exact
`c63b3b4...138cf`，不是payload mismatch或finding。Final artifact已记录冻结值。

## Aggregate finding disposition

1. 六路径组合满足 upload跨平台grammar/argv、company-name与public storage facts，RF01不再把 raw-source指定为Fins primary。
2. init的provider/model、TTY/redirected secret输入、setx/atomic/reset与README用户契约一致；Config/Host durable local state允许
   API key/header，Tool Trace/audit/public/LLM/log/review evidence仍禁止明文。
3. R11/R12 metadata、artifact integrity、same-run canary、reset/storage-state边界保持accepted plan；真实Windows仍pending。
4. Topics 1-7无回流；Topics 8-9保持no-code；deferred Issue 142/151/175/177/178与Web/WeChat/render未实施。
5. security mechanisms完整保留，没有统一 tool authorization framework、compatibility/fallback/downstream repair或LLM-facing drift。
6. 两路fresh full CLI均为 `552 passed, 7 skipped`；受影响 pyright零、Ruff通过、`init.py` coverage `92%`、diff-check通过。

## Residual candidate normalization

Controller将 reviewer residual candidates按唯一owner去重与裁决：

- Darwin不能证明真实 Windows console/cmd与RF01闭环、Windows nodes本地skip：合并为唯一 open evidence residual
  `AR-F07-WIN-REMOTE`，owner/destination为 Controller fresh R11/R12。
- fresh run出现新failure：这是 §13.9 conditional diagnostic-first stop rule，不是当前open finding或独立 residual。
- caller-owned pipe/OS memory短暂持有secret：在用户已裁决的当前 threat model之外；`NO ACTION`，不创建“独立安全设计 WU”。
- Full Ruff 142 entry baseline：已证明零新增；`PRE_EXISTING / NON_FINDING / NO ACTION`，不创建 cleanup WU。
- `init.py` coverage `92%`高于 `>=80%`门槛且关键owner tests/真实smoke已覆盖；未覆盖行不是当前finding，拒绝新 coverage WU。
- POSIX sibling assertion asymmetry与 `execution.stdout.count("Fins succeeded")`均在 aggregate base之前存在且未被本 range修改；
  用户禁止修改accepted findings无关既有代码，故为 `PRE_EXISTING / OUT_OF_SCOPE / NON_FINDING / NO ACTION`，不创建sub-WU。

因此 accepted aggregate finding为 `0`，unclassified residual为 `0`，唯一需后续证据项只有 `AR-F07-WIN-REMOTE`。

## Authorized next gate

按固定流程，只授权 AgentCodex产出 zero-change aggregate fix record与Controller validation；随后 AgentMiMo/AgentDS双路完整
aggregate re-review。不得直接commit、push、dispatch、PR review或final closeout。
