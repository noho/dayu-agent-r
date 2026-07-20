# WU-SEMANTIC-OWNERSHIP-01 / R09 completion Controller validation

## 1. Gate 与 verdict

- 当前仍是同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 remediation sub-WU R09 的 completion
  validation，不是新 WU、issue 或 feature。
- AgentCodex completion artifact：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-completion-codex.md`，
  283 lines，SHA-256
  `3139d04d8c0a6747e7213a3bb9f9f347951de58b402baef4ec484f082eaa0320`。
- Controller verdict：`PASS / R09 COMPLETE / ZERO ACCEPTED OR OPEN FINDING`。
- R09 actual accepted residual risk：0；blocker：0。
- umbrella 仍 active；R10 在本 validation 内未授权。

## 2. Accepted implementation commit object validation

| Field | Expected / actual | Result |
|---|---|---|
| commit | `8e0f2c5588c395cc8ee459a35f36db1de737b450` | match |
| parent | `9d36a115400fb59fd95475189810b43a09fda31b` | match；single parent |
| tree | `f2bc9ecee14da46dc95e004922262a3ab521fe24` | match |
| message | `fins: accept R09 direct stream validator remediation` | match |
| changed paths | 32 | exact |
| sorted 32-path manifest SHA-256 | `7e6171f4645d46ec37c9085082c46c6f3fc4d7d62355efbb3f6ceaa18e4911b2` | match |
| commit-range `git diff --check` | zero output | pass |

Controller 独立读取了 commit tree 中 32 个路径的 blob OID，并逐个确认 completion artifact 分组清单
包含同一 OID：12 个 product/test/README、19 个 implementation/review evidence、1 个 commit 内 control
blob，missing = 0。commit 内 control blob 是
`516eb80d8da43bb30c36548c21ed5831b64a2ce6`。

AgentCodex 写入期间的 Controller-owned worktree control blob 始终为
`d581bf1602872bac931420f534fdce4950bab239`；Agent 没有修改、stage 或覆盖它。当前 staged tree 仍 empty。

## 3. Product/test immutable validation

Controller 逐项复核 completion artifact 的 12 个 product/test/README Git blob OID 与最终 content
SHA-256，全部匹配 accepted commit 和 R09 final locks。Authority 的 canonical cumulative diff 按原三段
算法独立复算：

1. 10 个 tracked-at-entry paths 的 commit-range binary diff；
2. 追加 `dayu/fins/direct_stream.py` 的 commit-range binary diff；
3. 追加 `tests/fins/test_fins_direct_stream.py` 的 commit-range binary diff。

最终 SHA-256 精确为：
`60f52a7ebbd1608b11d28dd0206bf4176eac59e5dfc4a03fa87393c9457caf3e`。

单次把 12 paths 交给 Git 产生的 `3b804117...abda` 只是另一种 path ordering，不是 authority
algorithm、drift 或 finding；completion artifact 已正确区分。

## 4. Finding 与 validation ledger

- `R09-PR-F01..F06`：closed。
- `R09-CR-F01..F04`：closed / fixed。
- F01 self-cause/context follow-up：closed under `R09-CR-F01`，不是新 finding。
- `R09-RR-F01`：closed / fixed。
- final code re-review new finding：0。
- aggregate new accepted/material finding：0。
- AgentMiMo initial R1-R4 residual candidates：4 个 rejected-with-reason evidence-invalid candidates，
  不创建 speculative owner/WU。
- AgentDS daemon-thread / 50ms observations：2 个 non-actionable existing design observations。
- Issue 175：Fins Docling process isolation 的 existing deferred owner record，不是 R09 accepted finding。

Final ledger：accepted/open 0；blocker 0；R09 actual accepted residual 0。

最终 locked validation truth：

| Validation | Result |
|---|---|
| affected aggregate | `161 passed, 3 existing warnings` |
| R06 regression | `242 passed, 3 existing warnings` |
| R08 regression | `180 passed, 3 existing warnings` |
| full Fins | `873 passed, 1 existing skip, 3 existing warnings` |
| retained security | `16 passed, 3 existing warnings` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed Python Ruff | `All checks passed!` |
| coverage | `92.21% / 97.78% / 90.44% / 90.16% / 88.56%`，全部 `>=80%` |
| fresh real smokes | SEC download、Docling process、upload_filing/Docling 均 exit 0 |
| diff/source/propagation/stale/compat/deferred/no-touch scans | pass；零未分类命中 |

Completion artifact 自身 283 lines / SHA 与外部命令一致，不内嵌自引用值；其 no-index diff-check
无 whitespace error。

## 5. Security、deferred 与 completion decision

R09 保留 direct-event safe-text/leakage guards、path/job-id/raw-payload rejection、operation-scoped
cooperative cancellation、queue backpressure、late-publication fence、filesystem containment、symlink/atomic
publication、R06 transaction authority 和既有 security/resource/process fencing。CLI 没有直接导入 Fins
storage，也没有投影 raw typed reason。

R09 没有实现 Issue 142、151、175、177、178，Web/WeChat/render tracker，Topic 8/9 或统一 tool
authorization framework；Topic 8/9 no-code decisions 未改变。Issue 175 只保留既有 owner/destination。

因此 R09 满足 completion success signal：unique validator owner、mechanical downstream consumption、
全部 accepted findings关闭、验证完整、actual accepted residual 0。R09 status 可记为 `COMPLETE`；
umbrella `WU-SEMANTIC-OWNERSHIP-01` 必须继续。

## 6. Exact completion commit authorization

只授权一个 exact 3-path local completion commit：

1. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-completion-codex.md`
2. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-completion-controller-validation.md`
3. `docs/host/issues-implementation-control.md`

commit message：`docs: complete R09 direct stream validator remediation`。

提交前必须 staged count = 3、exact names match、无其它 unstaged/untracked、staged `git diff --check`
pass。该 commit 关闭 R09 内部 sub-WU，不关闭 umbrella；R10 只能在 completion commit 成功并由
Controller 更新 next entry 后进入独立 plan gate。
