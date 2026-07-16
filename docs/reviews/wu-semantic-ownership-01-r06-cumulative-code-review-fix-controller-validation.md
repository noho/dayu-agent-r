# WU-SEMANTIC-OWNERSHIP-01 R06 cumulative code-review fix Controller validation

## Gate identity

- Umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`。
- Remediation sub-WU：R06 Fins 显式 batch authority 与完整 source publication。
- Gate：累计 S1+S2+S3 code-review accepted-findings fix 的 Controller 独立验证。
- 基线 / 当前 HEAD：`d048adf7ec1135aaf575384432ebf1137f8a34f2`。
- Branch：`phaseflow/host-issues-control`。
- Agent fix artifact：`docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-fix-codex.md`。
- Finding 真源：`docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-controller-adjudication.md`。
- 结论：**PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_REREVIEW**。

本验证不接受 Agent 自报结论作为通过依据。Controller 逐项读取实现与 owner tests，独立重跑 direct、aggregate、coverage、type、lint、source scan、workspace 与 README trigger 检查后作出结论。

## Accepted finding closure

### R06-CR-F01：malformed journal per-entry isolation

`dayu/fins/storage/_fs_storage_infra.py::_recover_single_batch_dir()` 只在 `_read_json_object()` 边界捕获 `ValueError`，把截断 JSON、空文件和非-object 根归类为当前 transaction 的 `unparseable_journal`，保留目录和原始 evidence 后返回。`OSError` 没有被捕获，外层排序循环仍会继续恢复后续合法 orphan。

参数化 owner test 同时构造 malformed entry 与排序更后的合法 orphan，三种输入均证明 malformed evidence 保留、合法 orphan 同轮恢复且 published old 完整。finding 已关闭。

### R06-CR-F02：SEC rebuild cancellation / rollback dual failure

`rebuild_single_local_filing()` 只在 `begin_batch()` 后、`commit_batch()` 调用前的 mutation 区间捕获 `BaseException`：

- rollback 成功时，普通 `Exception` 保持既有 failed result；
- rollback 成功时，`KeyboardInterrupt` / `SystemExit` 原 identity 继续传播；
- rollback 也失败时，operation/cancellation 保持主异常 identity，rollback 成为 `__cause__`，并附带稳定 recovery-evidence note；
- `commit_batch()` 仍在该 catch 外，commit-start 后 caller 不二次 rollback。

取消两 case、普通失败回归与 operation/rollback 双失败 owner tests 均直接断言 identity、cause、note 与 exactly-once rollback。finding 已关闭。

### R06-CR-F03：ingestion rollback primary-error preservation

`dayu/fins/ingestion_runtime.py` 新增模块级私有 `_rollback_batch_before_commit()`，由三条 caller-owned pre-commit transaction path 复用。helper 用当前正在处理的 operation/cancellation 作为主异常；rollback 失败不会替换主异常，且不会建立跨模块 callback、facade 或 framework。

rejected artifact 与 preprocess 两条此前缺失路径的 owner tests 均证明 operation identity、rollback cause、稳定 note 和单次 rollback。已有 downloaded path 同时收敛到同一 helper。finding 已关闭。

### R06-CR-F04：deterministic publication-lock synchronization

独立 reader child 显式创建并注入同一个 `_FsRepositorySet`，在真实 public reader 调用 `_acquire_publication_guard()` 的 seam 发出 `publication_acquire_entered`，随后立即进入原 blocking acquire。parent 收到该信号后，用同一 publication lock 的真实 non-blocking acquire 证明 writer 正持有 guard，再释放 rename barrier；测试不再依赖 `poll(0.25)` 或进程启动 `ready` 推断。

测试没有反射 concrete repository 私有属性，没有 production debug flag、sleep、fake policy 或 force-release。两个 rename barrier owner cases 均通过。finding 已关闭。

## Controller independent validation

所有 Python 命令均在 `source .venv/bin/activate` 后运行。

| 验证 | 结果 |
| --- | --- |
| 四组 direct owner tests | `11 passed, 3 warnings` |
| Aggregate affected：`tests/fins` + combined tools acceptance | `732 passed, 1 skipped, 3 warnings` |
| Aggregate branch coverage JSON | 成功生成 `workspace/tmp/r06-controller-fix-coverage.json` |
| 本 gate 三个 production owner line coverage | storage infra `733/817 = 89.71%`；SEC rebuild `125/138 = 90.57%`；ingestion runtime `1535/1693 = 90.66%` |
| 其余 S3 production coverage | 继承并复核已接受 S3 22-file matrix；本 gate 未修改其余 19 个文件，既有最低 `80.40%`，全部 `>=80%` |
| Full pyright | `0 errors, 0 warnings, 0 informations` |
| Cumulative changed Python scoped Ruff | `All checks passed!` |
| Full Ruff fingerprint | base `162`、current `152`、`current-only=0`、`base-only=10`；current SHA-256 `5671e8ec...ed23` 与 Agent 证据一致 |
| Mutation AST | production `54`、tests `129`、missing explicit batch `0` |
| Ambient authority scan | `0` |
| Ack / false-completion scan | production `0`；仅两个 storage negative owner tests 命中 `ingest_complete=False` |
| Optional/default batch scan | `0` |
| Journal process facts scan | `owner_pid` / `hostname` 为 `0` |
| F04 obsolete synchronization scan | `poll(0.25)` / old `ready` / concrete repository private-set reflection 为 `0` |
| Deferred scope scan | revision/snapshot/bounded retry/unified authorization/force-release 为 `0` |
| `git diff --check` | 通过 |
| staged paths | `0` |

唯一 skip 是既有可选 Docling integration 环境门控；三条 warning 是既有 `edgar` deprecation warning，不是本 gate 新增或扩散。

## Owner、scope 与安全边界复核

- `BatchToken(transaction_id, ticker)`、journal 三字段闭集与 `SWAPPED_TARGET` pre-commit recovery 语义未改。
- processed/company/maintenance validator、四个 shared-core composition root 与 public read contract 未改。
- containment、ticker normalization、symlink 拒绝、atomic write/fsync、writer/recovery/publication lock order 均未放宽。
- 没有实现 publication-lock force-release；对应 retained operational residual 继续由 `dayu.runtime.filelock` 与 process termination 安全恢复承担。
- 没有进入 R07 revision/snapshot/opaque-id/retry/cache contract。
- 没有进入 Issue 142、151、175、177、178，也没有引入统一 tool authorization framework。
- Agent fix gate 只改三个 production owner、三个对应 test files，并新增自身 artifact；其余 dirty/untracked paths 均为已接受的累计 R06 checkpoint，未被清理、覆盖或回滚。

## README trigger audit

Controller 复读 `dayu/fins/README.md` 与 `tests/README.md` 的更新约束。两份 README 已陈述 batching-only lifecycle、commit 前失败/取消 rollback、publication guard/recovery 与相应测试职责。本 gate 修复的是同一 current contract 的错误分支和证明 seam，没有新增稳定 public capability、schema、用户工作流、分层或装配边界，因此无需追加 README/design 修改。根 README 与 `dayu/README.md` trigger 也未命中。

## Residual 与 next gate

- `R06-CR-F01..F04` correctness residual：`0`。
- accepted finding：`0 open / 4 closed`。
- blocking question：`0`。
- retained operational residual：publication lock release syscall 失败仍由 `dayu.runtime.filelock` / process termination owner 承担，禁止 unsafe force-release。
- R07 与既有 deferred Issues 保持原 owner，不进入本 gate。

下一 gate 仅授权 AgentMiMo 与 AgentDS 并发对完整累计 S1+S2+S3 final tree 做 complete re-review，重点核验四项 accepted finding closure、此前 S1/S2 finding closure、全部 rejected/deferred boundary 与组合行为。任何新 accepted finding 必须返回 AgentCodex 修复并再次完成 Controller validation 与双路 re-review。当前仍不创建 intermediate commit。

## READY_FOR_DUAL_COMPLETE_CUMULATIVE_REREVIEW
