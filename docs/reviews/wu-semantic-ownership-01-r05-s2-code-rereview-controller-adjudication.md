# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Code Re-Review Controller Adjudication

## 1. Gate 与 final verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- AgentMiMo artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-rereview-mimo.md`。
- AgentDS artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-rereview-ds.md`。
- Controller final verdict：`PASS / ACCEPTED_LOCAL_COMMIT_AUTHORIZED`。

两路都以 transition HEAD `e077c708` 后的完整未提交 working-tree transaction 为 target，审查 implementation、initial dual review、Controller adjudication、AgentCodex fix、fix Controller validation 与整个 product/test/README diff。两路均确认三项 accepted findings 关闭，四项 no-fix observations 未被偷带，没有新 material finding、blocker 或 ownerless residual。

## 2. Evidence integrity

- protected tracked transaction digest：`95f24a4e21e258e47d33bb1bafbe9d8fb25bcc3c2985941df6ed8f1bca123fc6`；两路匹配。
- new owner-test Git blob：`1c9c21a0df334709ba8dcb8188c48c5e7fdaa2fc`；两路匹配。
- AgentDS 初次把 Git blob 当文件 SHA-256、把全量 working-tree diff 当 protected tracked scope；Controller 在同一任务 follow-up 中纠正算法和路径范围。DS 随后用 `git hash-object` 与九路径精确命令复算匹配，最终 artifact 没有保留 drift 误判。
- AgentMiMo 初次查看 `main...HEAD` 历史 diff；Controller 在同一任务 follow-up 中纠正为 `git diff HEAD` + untracked owner test。MiMo 最终完整读取当前 product/test files、校验 owner-test blob，并以 Controller 冻结 transaction 为 evidence baseline。

上述过程性纠正没有修改 product/test target，也没有削弱 reviewer 独立结论。

## 3. Final finding ledger

| Finding / observation | Final disposition |
|---|---|
| MiMo-001 / DS-02：durable construction projection 重复 | `CLOSED`。`dayu.host.durable.options` 的 typed helper 成为唯一 nested policy construction owner；旧 command private helper 与 smoke duplicate 删除。 |
| MiMo-002 / DS-01：smoke private `_wait_poller` / runner diagnostics penetration | `CLOSED`。private Protocol/cast/counter 删除；第二轮 blocked observation 的 public Run/outbox + durable Wait/claim facts 提供 owner-level证据。 |
| DS-05：fake adapter 无界 wait | `CLOSED`。三个 gate 有界、具名、fail-fast，finally abort 释放全部 gate。 |
| MiMo-003：单文件规模 | `NO_CURRENT_DEFECT / CLOSED`。无结构拆分。 |
| MiMo-004：single-attempt smoke 的 backoff cap relation | `NO_CURRENT_DEFECT / CLOSED`。未修改。 |
| DS-03：Engine fake 同 event loop | `NO_CURRENT_DEFECT / CLOSED`。未线程化。 |
| DS-04：理论极慢 CI margin | `NO_CURRENT_DEFECT / CLOSED`。无数据支持调参。 |

Final count：accepted current finding `3/3 CLOSED`；rejected-as-current-defect observation `4/4 CLOSED`；new material finding `0`；blocker `0`。

## 4. Controller acceptance reasoning

1. `HostDurableStoreOptionsSource` 仅声明九个内聚 storage construction 字段，用 structural typing 避免 durable 下层 import 上层 opener 类型；它不查 profile/default、不持久化、不解释上层字段，也没有 callback/factory/query 行为。当前多 typed opener 输入使该 dependency inversion 有充分理由，不是 god bag 或 speculative abstraction。
2. `project_host_durable_store_options(...)` 是唯一 `PayloadStoragePolicy`、`HostSQLiteStoragePolicy` 与 `HostDurableStoreOptions` nested construction source；所有 production construction paths 与当前 diagnostic smoke durable read 复用它。旧 helper 完全删除，无 wrapper/re-export。
3. late publication 的 happens-before 成立：首轮 Ready 已返回；第二轮真实 durable claim 已提交；第二轮 adapter 在返回 Ready 前由唯一 release gate 阻塞；此时 public Run/durable Wait 仍 WAITING、首轮 timeout diagnostic 保持、terminal outbox 为空。若首轮获得发布权，该组合不能成立。
4. 新 direct owner test 用可区分输入断言全部映射字段，并覆盖现有 durable options validation；Controller 与两路验证 100% module branch coverage，不以 coverage 代替行为断言。
5. Engine production no diff；accepted awaiting regression 证明 handshake timer 不拥有已接受长事务。S1 wait owner、scheduler residual、retained safety 与 deferred scope 均保持。

`options.py` 预存没有 `__all__`，DS 将其记录为 minor inconsistency 而非 finding。当前 helper 只由精确模块 import 使用，没有 package re-export 或稳定 top-level API 承诺；机械新增 `__all__` 反而扩张本修复范围，Controller 接受 `NO_CURRENT_FIX`。Protocol property docstring 的通用 `:raises Exception:` 也是接口级允许实现说明，不构成错误 contract。

## 5. Validation acceptance

Controller 独立验证已记录于 `docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-fix-controller-validation.md`：fresh public smoke PASS、aggregate `360 passed`、focused `11 passed`、durable owner `100%` branch coverage、full pyright `0`、changed Ruff green、full Ruff `165→162` 精确只删除三条 touched F401、`git diff --check`、source/no-diff/security scans 与 scheduler residual probe全部通过。

AgentMiMo 与 AgentDS 又分别复核上述证据、完整 owner boundaries、README trigger、cleanup、retained safety 与 deferred scope。无需第二个 fix gate。

## 6. Residuals 与安全边界

| Residual | Owner / destination | R05-S2 disposition |
|---|---|---|
| scheduler close / terminal promotion coordination | independent Host scheduler/lifecycle owner；需要显式后续裁决 | retained，未修、未 waive、未归 Issue 175 |
| cancelled abandon 持续 timeout 时长期 capped retry | future Host durable evidence policy | retained；不得从 timeout 猜 LOST |
| Issue 175 process isolation | existing Issue 175 | 未实施 |
| callback / unified authorization / R06+ | later work | 未实施 |

现有 token invalidation、late-publication fence、claim CAS、backoff、typed LOST、cancellation、capacity、close-drain、durable storage/path/SQLite safety 均保持。R05-S2 没有设计统一 tool authorization framework，也没有删除任何现有安全 owner。

## 7. Authorized next action

只授权把完整 R05-S2 product/test/README transaction、完整 review/fix/validation/adjudication chain 与 Controller control state 做一个 accepted local commit。

不得包含 `workspace/tmp`、scheduler fix、Issue 175、callback、统一 authorization、R06+、push 或 PR。commit 后进入 R05 aggregate validation/deepreview；R05-S2 完成不等于 R05 或 umbrella 完成。
