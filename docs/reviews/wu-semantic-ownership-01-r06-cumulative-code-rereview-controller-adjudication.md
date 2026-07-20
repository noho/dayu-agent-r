# WU-SEMANTIC-OWNERSHIP-01 R06 cumulative code re-review Controller adjudication

## Gate identity

- Umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`。
- Remediation sub-WU：R06 Fins 显式 batch authority 与完整 source publication。
- Gate：完整累计 S1+S2+S3 code re-review Controller adjudication。
- Base / current HEAD：`d048adf7ec1135aaf575384432ebf1137f8a34f2`。
- Branch：`phaseflow/host-issues-control`。
- AgentMiMo：`docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-rereview-mimo.md`，`PASS / 0 new material findings / 0 blockers`。
- AgentDS：`docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-rereview-ds.md`，`PASS / 0 new material findings / 0 blockers`。
- Fix validation：`docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-fix-controller-validation.md`。
- 最终裁决：**PASS / R06 FINAL TREE ACCEPTED FOR EXACT-SCOPE LOCAL COMMIT**。

Reviewer verdict 不自动授权 acceptance。Controller 已完整读取两份 re-review、修正后的 prior-finding ledger、当前 owner code/tests，并与原累计 adjudication 和 accepted plan 逐项复核后作出本裁决。

## Accepted finding final closure

| Finding | 最终状态 | Controller 证据 |
| --- | --- | --- |
| `R06-CR-F01` | CLOSED | `_recover_single_batch_dir()` 只把当前 entry 的 JSON `ValueError` 分类为 `unparseable_journal`，保留 evidence 并让外层继续；`OSError` 传播。三种 malformed journal 与 later valid orphan owner cases 通过。 |
| `R06-CR-F02` | CLOSED | SEC rebuild pre-commit 捕获 cancellation/operation，rollback exactly once；普通失败保持 failed result，取消原 identity 传播，双失败 operation 为 primary、rollback 为 cause；commit-start fence 不变。四个 owner cases 通过。 |
| `R06-CR-F03` | CLOSED | ingestion 三条 caller-owned pre-commit path 复用模块级私有 helper，rollback 失败不替换 operation/cancellation primary；rejected artifact 与 preprocess 双失败 owner cases 通过。 |
| `R06-CR-F04` | CLOSED | child 在真实 public reader publication-guard acquire seam 发信号，parent 用同一真实 lock 的 non-blocking contention 证明 writer 持锁；旧 `poll(0.25)` / startup-ready 推断和 concrete repository private-set reflection 均删除。两个 rename barrier 通过。 |

此前五个 accepted validation/review findings 也保持关闭：

- `R06-S1-CR-F01`：maintenance public guarded read 使用 private unguarded helper；
- `R06-S1-CR-F02`：processed meta contract 不再描述不存在的 fallback；
- `R06-S1-CR-F03`：shared-core mark reprocess 返回 protocol-owned `None`；
- `R06-S2-CR-F01`：explicit primary mismatch 返回 `None`，不猜 first file；
- `R06-S3-CV-F01`：preprocess selection 对缺失 `ingest_complete` fail closed。

最终 accepted ledger：`9 closed / 0 open / 0 blocker`。

## Rejected、deduplicated、deferred ledger

原累计 adjudication 中的结论全部保持：

- MiMo F01、F03、F05-F12、F14-F15 维持 rejected；F02/F04/F13/F16 已并入并由 `R06-CR-F02..F04` 关闭。
- DS F01/F02 已由 `R06-CR-F01/F03` 关闭；DS F03-F05 维持 rejected；DS F06 维持 R07-owned deferred。
- pre-commit `SWAPPED_TARGET` 仍是 rollback state，不是 committed；没有 unsafe lock force-release；`BatchToken` public shape 仍精确为 `transaction_id,ticker` 且不增加 grammar；source validator 不吸收 processed/company/maintenance；R07 revision/snapshot/opaque-id/retry/cache 未进入。

### 旧 DS first-review 晚追加 F07 的显式补充裁决

`R06-CR-DS-F07` 在旧 DS artifact 末尾晚于原 Controller 取证追加，因此原 adjudication 没有列出。本轮 AgentDS 已将其 retracted 为 non-material current finding；Controller 现在显式裁决为：

**REJECTED — hypothetical path-divergence concern, no current defect evidence.**

直接理由：

1. 默认 concrete owner 中，`LocalFileStore(root=state.staging_ticker_dir.parent)` 与 normalized key `{ticker}/{source_dir}/{document_id}/{filename}` 解析出的实际路径，精确等于 `_resolve_handle_child_path_for_state()` 校验的 `handle_dir / filename`。ticker、source kind、document ID、filename 均由同一 normalization owners 约束。
2. `LocalFileStore._resolve_normalized_key()` 自己负责 object-key 对其 root 的 containment；可注入 `FileStore` 是独立存储 collaborator contract，不应由 Fins local path resolver 反推或强制其物理路径。使用 resolved local `Path` 直接写入反而会绕过 `FileStore` owner 和数据/存储职责分离。
3. finding 只提出未来某个 private helper 若独立漂移的可能，没有当前输入能够产生路径分叉、containment bypass、published half-source 或 consumer failure 的直接证据。建议通过修改 private `_build_file_store` root 制造失败，会测试刻意破坏的 collaborator，而非 reachable production contract。
4. retained containment、symlink、object-key normalization、complete-source validator 与 atomic publication tests 均通过；不需要 assertion、fallback、重复 path authority 或新 test shim。

至此，旧 MiMo/DS 累计 review 的每个 finding 均有最终 Controller disposition；没有遗漏项。

## Independent evidence synthesis

Controller fix validation 与两路 re-review 共同复现：

| Evidence | Final result |
| --- | --- |
| direct accepted owner cases | Controller `11 passed`；DS `11 passed` |
| aggregate affected matrix | Controller/DS 均为 `732 passed, 1 skipped, 3 warnings` |
| touched production line coverage | storage infra `89.71%`；SEC rebuild `90.57%`；ingestion runtime `90.66%`；其余 accepted S3 files 继续全部 `>=80%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| cumulative scoped Ruff | `All checks passed!` |
| full Ruff fingerprint | base `162`、current `152`、`current-only=0`、`base-only=10` |
| mutation AST | production `54`、tests `129`、missing explicit batch `0` |
| ambient / optional batch / journal process facts / obsolete F04 sync | `0` |
| ack / false completion | production `0`；两个 test-only validator negatives |
| `git diff --check` / staged paths | pass / `0` before accepted commit |

唯一 skip 是既有可选 Docling integration 环境门控；三条 warning 是既有 `edgar` deprecation warning。

## Plan、owner、security 与 no-scope-creep decision

- public `BatchToken`、required keyword `batch=`、single batching lifecycle owner 与 internal registry authority 符合 accepted plan。
- blob-first + final source once、full staged-tree validator、bidirectional manifest、commit/recovery journal 与 publication guard 形成完整 publication owner boundary。
- `DefaultFinsRuntime`、`CnPipeline`、`SecPipeline`、standalone 6-K repair 四个 production roots 使用 shared core。
- reader 在长 staging/validator 期间仍读完整 old；在两次 rename 短窗通过 publication guard 阻塞，完成后只读完整 old/new。
- containment、ticker normalization、symlink 拒绝、DNS/peer、resource budgets、atomic write/fsync、process fencing 与 writer/recovery/publication lock order没有被删除或放宽。
- 没有实现统一 tool authorization framework。
- 没有实现 R07 或 Issue 142、151、175、177、178。
- README current truth 与 code 同源；本 fix/re-review gate 没有触发新的 README/design 修改。

## Residual ownership

1. publication lock release syscall 失败：retained operational residual，owner 为 `dayu.runtime.filelock` / process termination；禁止在 Fins recovery 删除 lock marker 或伪造 force-release。
2. 跨多个 repository calls / processor cache lifetime 的 snapshot/revision consistency：R07 唯一 owner；R06 只保证一次 published read/open 不进入 rename 空窗。
3. `edgar` deprecation warnings：外部依赖 residual，不是 R06 新增。
4. 可选 Docling integration skip：既有环境门控；不阻塞当前 R06 correctness acceptance。

## Final decision and next gate

- New material re-review findings：`0`。
- Open accepted findings：`0`。
- Blocking questions：`0`。
- R06 final cumulative tree：accepted。

唯一下一动作是创建一个 exact-scope local accepted commit，包含从 `d048adf7` 开始的完整 R06 production/test/README tree、全部 R06 implementation/review/fix/validation artifacts、本 adjudication与同步 control state。不得混入 R07、其它 remediation sub-WU、deferred Issues、统一 authorization、push 或 PR。

## R06_FINAL_TREE_ACCEPTED_FOR_EXACT_SCOPE_LOCAL_COMMIT
