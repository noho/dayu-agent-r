# WU-SEMANTIC-OWNERSHIP-01 / R08 cumulative code re-review Controller adjudication

## 1. 结论

`PASS / ALL_ACCEPTED_CODE_AND_VALIDATION_FINDINGS_CLOSED / ZERO_NEW_ACCEPTED_FINDING / READY_FOR_AGGREGATE_DEEPREVIEW`。

Immutable review target：

- cumulative `git diff --binary -- dayu/fins tests` SHA-256：`01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d`
- 23 tracked paths；guards `44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a`；staged empty
- AgentMiMo final artifact：`docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-mimo.md`，SHA-256 `972b5505a063df16d5da76103bc89a7a3c1c8ff6ab8c90ca21fb9e3a300c4a7c`，verdict `PASS / no material finding`
- AgentDS artifact：`docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-ds.md`，final whitespace-normalized SHA-256 `d9e27c9f3703b65b812b70b03b3765e9ac61978abbf0e0cdddf243c63963c064`，verdict `APPROVE / no blocking finding`。Only three Markdown line-ending spaces changed after review；semantic content and verdict are byte-for-byte otherwise unchanged。

两路均完整 review 当前 uncommitted working tree 的 23-path cumulative diff，而非只审 pyright patch；均独立匹配 locks，并重新挑战 Topic 6、semantic ownership、LLM-facing、R07/security/no-code/deferred boundaries。

## 2. Accepted finding closure

| Finding | Final status | Evidence |
|---|---|---|
| `R08-CR-CF01` | `已修复` | shared runtime test 四个 generic/compat nodes 与九 imports/symbols 零命中；shared hash `01db5538...6692` |
| `R08-CR-PCF02` | `已修复` | dead `_collect_available_document_types` definition/caller/import 全零；actual typed/sorted owner definition/caller 各一 |
| `R08-CR-PCF03` | `已修复` | candidate 6 public resolver test/import/三断言精确保留，无 bypass/padding |
| `R08-CR-PCF04` | `已修复` | prefix-five `387/485`、fresh prefix-six `391/485` 与 `[344,346,348,442]` direct evidence一致 |
| `R08-VAL-PY-F01` | `已修复` | optional public keys 先做 membership proof |
| `R08-VAL-PY-F02` | `已修复` | test processor constructor 对 protocol-valid calls 可调用 |
| `R08-VAL-PY-F03` | `已修复` | test-local XBRL success TypeGuard 只按必有 public field 收窄 |

此前 plan-review findings `R08-CR-PCPR-F01..F05` 也已由 accepted plan loop 关闭；两路 code re-review 未发现 regression。

## 3. MiMo 同任务证据纠正留痕

AgentMiMo 首次完成稿曾报告三个 README/code mismatch candidates：mandatory `statement_locator`、producer raw XBRL `total`、九值 reason。Controller 直接核对当前 working tree 与权威裁决后，判定三项均把 controller discussion §463 的旧 contract 问题描述误当成当前真源，并且使用了不含 uncommitted R08 tree 的旧 commit-range 内容：

| Candidate | Final decision |
|---|---|
| initial `R08-REVIEW-F01` mandatory `statement_locator` | `证据失效 / rejected-with-reason`：current README、design §5 与 controller discussion §514 均要求该 diagnostic 不进入 required contract；current source/README 零命中 |
| initial `R08-REVIEW-F02` producer raw `total` | `证据失效 / rejected-with-reason`：current README/design 明确 producer contract 为 query_params/facts/quality，可选 reason；公共唯一 `fact_count=len(returned facts)` |
| initial `R08-REVIEW-F03` `statement_method_missing` / `statement_empty` | `证据失效 / rejected-with-reason`：两项已裁决删除并统一为 `statement_not_found`，不得恢复内部诊断 |

同一任务 follow-up 后，MiMo 重新读取当前 filesystem 与 `git diff HEAD`、修正所有 finding ledger、重跑 focused tests/pyright，并重写 final artifact。Final artifact 不再包含上述伪 findings，结论 PASS。三项不实施、不 defer，也不创建 issue。

## 4. DS questions 与 residual adjudication

| Reviewer item | Controller decision |
|---|---|
| Q1 prefix proof 未由 reviewer 独立重跑 | 非 finding；AgentCodex 在最终 immutable tree fresh 运行，JSON hashes 已锁；Controller 独立读取 JSON 确认 `387/485 -> 391/485` 与四行差集 |
| Q2 15-file checker 未由 reviewer独立重跑 | 非 finding；AgentCodex fresh exact-key checker 15/15 PASS，完整 ledger 与 cumulative JSON hash已锁；aggregate reviewers继续核验 evidence chain，不要求重复测试作为 review entry condition |
| Q3 forced-truncation fixture 对 facts 数量敏感 | `rejected-with-reason` as finding；test 通过 public callable 产生真实 pre-Host value并显式断言大于 truncate limit，fixture drift 会 fail closed；owner 为该现有 test maintenance |
| exact-key path normalization portability | 已由 repo-relative NUL manifest + exact JSON key lookup fail closed；不新增路径 fallback或coverage compatibility |
| future Host truncation contract change | 非当前 defect；当前三段组合 smoke通过。未来 contract change 必须由其 owner同步测试；Issue 177 仍只承担既有 truncation follow-up，不在 R08 偷带 |
| helper remaining 94 statements | 非 finding；whole-file `80.61855670%` 达到强门槛，禁止为追求100%新增padding |
| Docling integration skip | tracked by Issue 175；非 R08 scope |
| `edgar` warnings | existing dependency warnings；非 R08 finding |

没有 blocking open question、unclassified residual risk 或需要当前 fix 的 finding。

## 5. Security / no-code / deferred decision

- Topic 8 继续保留 Engine generic exception 240 字符硬编码、脱敏与截断后缀；R08 无 Engine delta。
- Topic 9 未实现统一 tool authorization framework；当前未设计 permission schema、policy DSL、role/capability 或 sandbox。
- Containment、symlink、DNS/peer、resource budget、atomic write/publication、process fencing 与 Host truncation owner 均未删除或弱化。
- R07 snapshot/citation lifecycle no-touch；R09-R12 与 Issues 142/151/175/177/178 未偷带。

## 6. Next gate

AgentMiMo 与 AgentDS 必须使用 `/deepreview` 对相同 immutable R08 cumulative tree做并发、独立、完整 aggregate deepreview，覆盖 S1+S2/corrections/candidate/deletion/pyright-fix 的组合行为、全部 finding closure 与设计一致性。Reviewer verdict 不授权 accepted commit；任何 aggregate accepted finding 仍须 AgentCodex fix、完整 §6.6/§6.7 revalidation 与双路 aggregate re-review。只有 aggregate loop 关闭后，Controller 才能创建一个 exact-scope R08 accepted local implementation commit。
