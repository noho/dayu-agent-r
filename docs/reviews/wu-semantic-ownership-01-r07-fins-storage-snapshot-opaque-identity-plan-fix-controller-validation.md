# WU-SEMANTIC-OWNERSHIP-01 / R07 Plan Fix Controller Validation

## 1. 验证对象与结果

- reviewed plan SHA-256：`ae8d74f8a9a7fd677face4211cb7402bdc5e56eb6c80bfe8cb1791a4e46a7bc7`
- fixed plan：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`
- fixed plan SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`
- AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-fix-codex.md`
- fix artifact SHA-256：`8f5bdd503902a5bd0c32fb7db4e964c616b10b87473ab0a31c71dcc5c647a659`
- Controller adjudication SHA-256：`c7e67d2a10d6211cd87bfc8914b4fe3aa6c983826493a5b525d2881f238052e6`

Controller 已完整重读 fixed plan 789 行与 fix artifact 87 行，并对照两路原 review、Controller adjudication、`docs/fins/design.md` 和 Topic 6.3 / 6.7 逐项复核。结论：**PASS / R07-PF-01..12 CLOSED IN PLAN / READY_FOR_DUAL_COMPLETE_REREVIEW**。这不是 accepted-plan 裁决，也不授权 implementation、stage 或 commit。

## 2. Finding closure 复核

| finding | Controller 验证 |
|---|---|
| `R07-PF-01` | §8.1 保留 branch collection，但逐文件 line gate 已改为 `covered_lines / num_statements`；不再把 composite `percent_covered` 标成 line coverage。 |
| `R07-PF-02` | S3 只点名删除 `QueryDiagnosis` 与 `SEARCH_MODE_AUTO`，没有扩散 legacy Ruff cleanup。 |
| `R07-PF-03` | S2 明确 breaking `digest -> token`、non-empty opaque equality、同 slice 删除 SHA grammar/hash builder；无 alias/property/双字段/兼容值，S3 删除临时 revision method。 |
| `R07-PF-04` | lock stem 只发现 candidate key；business ticker 只从 target/backup descriptor 恢复，lock-only 无 descriptor 不投影 key 或新增状态名；targeted test 已列。 |
| `R07-PF-05` | maintenance cleanup 明确 descriptor external id 后再做既有 `fil_` 与 valid-id 业务判断；targeted test 已列。 |
| `R07-PF-06` | revision/descriptor 未变时 fd/inode/EOF/fstat/declared-content 异常直接按 corruption/validation fail closed；只有真实 publication change 才 retry，真实 smoke 已列。 |
| `R07-PF-07` | SEC fiscal 只把 path owner 切到单一 full snapshot，保留 existing lowercase filename map、排序、suffix 与 XML fallback exclusion；明确禁止 `has_xbrl_instance` 新分类/schema。 |
| `R07-PF-08` | 同 document creation lock 内 double-check；losing snapshot close、唯一 processor build/publish 与 initial miss concurrency test 均已写清。 |
| `R07-PF-09` | 9 个 read tools 的 completed/failed/cancelled/citation 运行时 JSON 全 nested key/value recursive test 已与 §3.7 对齐；不只源码 grep。 |
| `R07-PF-10` | S2 storage-owner test 明确 delete/reset 后 source/token/resource 同时 absent 并抛 `FileNotFoundError`；S3 cache retirement 测试保持独立。 |
| `R07-PF-11` | list-only 固定复用 filing/material 两个 typed list projections，不做 N+1 或新 batch API；single-document optional kind 仍由 storage 做 typed 0/1/2 判定。 |
| `R07-PF-12` | S3 cumulative review 是 R07 唯一 complete-tree code review；删除等价 R07-only duplicate deepreview，保留所有 remediation sub-WU 后的 umbrella aggregate deepreview。 |

## 3. Owner、scope 与非采纳项复核

- `source_kind=None` 保持 storage-owned typed 0/1/2 resolution；没有恢复 read-runtime filing-first guess。
- 没有 `list_source_snapshots`、batch snapshot/list API、第二 mapping owner、reverse registry 或 migration/compat path。
- revision token grammar/生成算法、identity key grammar、retry budget 与 private resource type 均未变成 business/README/tool/LLM contract。
- cross-document diagnosis 仍只校验 cached candidate；没有为未缓存文档新增 processor build。
- R08—R12、Issue 142/151/175/177/178、统一 tool authorization、Host/Engine/CLI scope均未进入 plan。
- containment、symlink、filename/local URI、atomic write/fsync、writer/publication locks、recovery、typed provenance/citation/read errors均明确保留。

## 4. Scope、hash 与 whitespace 验证

Controller 独立执行并确认：

- `shasum -a 256` 与上述 fixed plan/fix/adjudication hash 完全一致；
- fixed plan 全文状态为 `PLAN_FIX_COMPLETE / READY_FOR_CONTROLLER_VALIDATION`，没有 implementation 授权；
- `git diff --check` PASS；
- plan、fix、两路 review、Controller review/entry artifacts 的 `git diff --no-index --check` 均无 whitespace diagnostic；
- 工作树没有 product、tests、README、design 或 `workspace/tmp` 新变化；当前变化仍只属于 R07 plan gate 的 control/plan/review artifacts。

Controller 在验证时只从自己的 adjudication artifact 删除了一个 EOF 多余空行；AgentCodex随后只刷新 fix artifact 中对应保护性 SHA。fixed plan 内容和 SHA 在该窄修正前后均未变化。

tests / pyright 未运行：本 gate 只有 Markdown plan/review/control artifacts，没有 implementation。R07 implementation 后仍必须逐 slice 执行 plan §8 的完整测试、逐文件 line coverage、pyright、Ruff、diff、source/AST/LLM scans 与真实 filesystem smoke。

## 5. Re-review immutable target

AgentMiMo / AgentDS 下一 gate 必须各自完整 review 同一 immutable fixed plan SHA `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`，并验证：

1. `R07-PF-01..12` 是否真实关闭，fix 是否引入新矛盾；
2. source kind、opaque token、identity descriptor、snapshot failure/concurrency、SEC fiscal、cache/list/citation owner 是否仍唯一；
3. S1/S2/S3 allowlist、targeted tests、coverage/scans/smoke 与 fresh-schema stop conditions 是否闭合；
4. R07 final code review 与 umbrella aggregate deepreview gate 是否既不重复也不遗漏；
5. security retained/modified 与 deferred owner 是否保持。

只有两路 complete re-review 均通过、所有 finding 有最终 disposition 且无新 accepted fix，Controller 才可做 accepted-plan adjudication 与 exact-scope local commit。
