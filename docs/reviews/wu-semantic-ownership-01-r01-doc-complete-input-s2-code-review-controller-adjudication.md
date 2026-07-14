# WU-SEMANTIC-OWNERSHIP-01 / R01-S2 Code Review Controller 裁决

## 1. Gate 身份与输入

- 当前仍是既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation slice R01-S2，不是新 WU。
- accepted plan 为 commit `54e35231` 中的 `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`。
- slice base 为 `547c926e`；输入包括完整 working-tree S2 diff、implementation artifact、controller validation，以及：
  - `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s2-code-review-ds.md`
- 两路 reviewer 均完整复核 production、tests 与 tests README，而非只读取 controller 摘要；两路均独立运行 provider、真实 threshold smoke、ToolRuntime owner、pyright 与传播扫描。

## 2. Review 裁决

| 路径 | Reviewer 结论 | Controller 裁决 |
|---|---|---|
| MiMo | PASS；无 material finding、无 open question | **接受**。完整覆盖 deterministic cancellable iterator、list heap、search partial/containment、cap 全链删除、真实 smoke、output/security/Issue 177 边界。 |
| DS | PASS；无 material finding、无 open question | **接受**。完成全文件与完整 diff 走读、adversarial failure pass、10 个定向节点、4 个 ToolRuntime owner 节点、pyright 与 14 类传播/边界扫描。 |

两路证据与 controller 独立复核一致：

- directory/source cap 的 producer、参数、result、schema、LLM-facing、tests 与 README 传播已删除；
- list 完整观察并返回精确 `total/scanned_entries`，output `limit` 只保留稳定前 N；
- search 只有 `result_limit` 能产生 partial，正文读取前 containment owner 保持；
- 目录 symlink 产出但不递归，file symlink/list、search resolve、direct read projection 三条既有 owner boundary 未被合并为权限框架；
- 真实 10,001 普通文件、>33 MiB 大文件与越界 symlink 经 discovery→callable 通过；
- `ToolTruncateSpec`、Host-owned `fetch_more`、allowed paths、取消、process fencing 与 Issue 177 边界未漂移。

## 3. Finding 与 residual 裁决

没有 accepted finding 需要修复，也没有理由制造空的 fix/re-review gate。

| Reviewer observation | Controller classification | 裁决 |
|---|---|---|
| 完整目录观察和每层确定性排序会增加极大目录的时间/内存成本 | accepted product semantic | Topic 1 已明确删除 producer cap；保留 cancellation 和 output limit。不得以此恢复 partial 或隐藏预算。 |
| search `total_matches` 是返回命中数 | accepted current search contract | 当前 tool description 已自解释。Issue 177 只追踪 Doc 与 TruncationManager 的完整接通；本裁决不替 Issue 177 推导新的 complete-result schema。 |
| list `stat()` 的 `OSError` 继续跳过单个 entry | pre-existing unchanged behavior | 无当前 failure evidence，且不属于 directory-cap root cause；不扩 scope。 |
| 真实 10,001-entry smoke 在慢 CI 可能更耗时 | required acceptance evidence | 当前约 2 秒并稳定通过。不得把 fixture 降到旧阈值以下；只有出现真实 CI failure 后才能在不削弱阈值证据的前提下处理。 |
| symlink/TOCTOU 仍由既有局部边界治理 | retained security behavior | 当前不创建或实施统一 authorization WU/schema。未来若产品授权，最终 owner 才是 Host ToolRuntime 或同级治理边界；本 slice 不指定新的实施入口。 |

MiMo 将某些未来 complete-result/symlink hardening 可能性列作 residual，DS 提到可调整 smoke fixture；这些都不是当前 accepted debt，不能扩大 Issue 177、创建新 WU 或削弱已裁决验证。

## 4. 最终验证与边界

- Controller：provider `66 passed`；ToolTruncateSpec/fetch_more `4 passed`；真实 smoke/security/cancellation `6 passed`；coverage matrix `84 passed`；`doc_tools.py` 620/770 statements、80.51948051948052%；pyright `0 errors`；ruff、`git diff --check`、删除语义和 retained-owner scans 通过。
- MiMo：provider `66 passed`；真实 smoke `1 passed`；owner nodes `4 passed`；affected matrix `84 passed`；pyright、ruff、diff/scans 通过。
- DS：provider `66 passed`；adversarial nodes `10 passed`；owner nodes `4 passed`；pyright 与传播/边界 scans 通过。
- 没有 Host/runtime/contracts/config/Engine/Service/UI/Fins product diff；control doc 只有 phaseflow gate/state 更新。
- 未实施 Issue 177、Issue 142/151/175/178、统一 tool authorization framework、Topic 8 code change或后续 remediation sub-WU。
- `tests/README.md` 只更新其 Documents/Tools owner 段落，其它 README 无触发修改。

## 5. Gate 结论

R01-S2 **accepted**，允许 controller 创建一个包含最终实现、测试、README、implementation/controller/review artifacts 与当前 control state 的本地 accepted commit。该 commit 只接受 S2；不等于 R01 aggregate deepreview 或整个 R01 完成。提交成功后 controller 必须单独更新 control doc 的 accepted hash 与下一入口，再进入 R01 aggregate validation/deepreview。
