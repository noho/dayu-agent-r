# PR 190 F19 goal confirmation（2026-08-08）

## Preflight

- branch：`codex/interactive-oracle`；F19 entry HEAD：`6f328307d77b734d9eb3c64ff9baf135ae60417b`；
- worktree：仅有ownership不明且明确排除的 `docs/reviews/plan-review-20260808-095346.md`；
- merge/rebase state：不存在；
- main fast-forward：`github/main...HEAD = 0/110`，main是HEAD祖先；
- PR：PR 190，OPEN/DRAFT，head=`codex/interactive-oracle`，base=`main`，merge state CLEAN；继续非强推送到同一PR。

## Confirmed goal

用户已明确授权在F18 immutable failed closeout后立即开启独立F19 observation work unit。F19目标是：

1. 使用全新run root、fresh workspace与新的1800秒monotonic deadline，运行真实production CLI、POSIX PTY、真实AAPL
   corpus与真实MiMo plan；禁止DeepSeek、fake/mock、output injection及F18/Trial durable state复用。
2. 采用已由MiMo/DS双路PASS的owner-legal material chain：R1 typed grounding后读取`s_0003`形成business-risk previous
   EvidenceFact；R2 baseline accepted后typed grounding并读取`s_0013`形成FY2025 financial EvidenceFact；R3 no-tool target观察
   cap=1下replacement/keep-omit/provenance/complement；accepted后R4 fresh reconnect。
3. 最多三条fresh有效候选链，自适应观察replacement/reconnect、same-boundary bounded repair与budget-exhausted fallback；自然
   未触发必须如实needs-more，不追加prompt/tool padding、不重跑同链、不伪造模型输出。
4. 首次provider前修正并provider-free验证wrapper的prompt-file→argv边界：非空prompt必须以单个`--prompt`参数传给冻结
   harness；empty prompt fail closed；验证产物必须记录prompt bytes/SHA、argv presence与provider未启动。
5. F19 publication必须修复F18 findings：public summary包含per-chain budget/count/terminal refs；每条attempted chain发布
   path-redacted Host resolver/Tool Trace analysis JSON/Markdown；发布`execution-index.json`；所有cross-file digest字段明确
   domain并从最终artifact owner bytes复算；最后writer重新执行secret/path scan。
6. 完成B2逐项human-readable observed behavior report，分别给出product/setup implementation、real observation、publication、
   Oracle与overall readiness verdict。B2在用户裁决前保持unadjudicated，Agent不得替用户接受。

## Non-goals and frozen residuals

- 不修改产品、scene、profile、Engine/Host/Fins、CLI adapter、analyzer或测试来迁就observation setup；若owner direct evidence证明
  产品缺陷，停止provider并开启独立实现gate，不在F19观察脚本中fallback。
- 不修改F18 public/private tree，不覆盖或重标F18两条non-covering与一条provider-not-started记录。
- 不调查旧Trial2 sequence 327不可恢复cause，不扩展B1 cold analyzer，不修改issue 192 INFO，不处理Fins schema优化。
- 不读取、修改、暂存或提交 `docs/reviews/plan-review-20260808-095346.md`。

## Gate decision

Goal已由用户当前指令确认。next gate是AgentCodex最小F19 execution/publication plan与wrapper实现，随后MiMo/DS双路独立
plan+wrapper review；两路均PASS前不得冻结新deadline或调用provider。
