# WU-SEMANTIC-OWNERSHIP-01 R06 plan fix Controller 验证

## 1. 身份与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- internal remediation sub-WU：R06
- gate：remediation plan review fix validation
- pre-fix plan SHA-256：`f147079bd9870f14402feb0782a3568109ccb710fa67d3bfe97add120f2336cd`
- fixed plan SHA-256：`ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43`
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-fix-codex.md`
- Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-controller-adjudication.md`

Verdict：`PASS / READY_FOR_DUAL_COMPLETE_PLAN_REREVIEW`。

本验证只确认 fixed plan 已完整落实 `R06-PF-01..08`、证据与 scope 一致。plan 仍未 accepted；implementation、stage/commit、R07-R12、deferred Issues、统一 tool authorization、push 与 PR 均未授权。

## 2. Controller 独立全文与范围核验

Controller 完整读取了 fixed plan 585 行和 AgentCodex fix artifact 182 行，并重新计算：

| artifact | line count | SHA-256 |
| --- | ---: | --- |
| fixed R06 plan | 585 | `ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43` |
| AgentCodex plan-fix artifact | 182 | `3c40e7baf191a5eab8cc2a55541da2123b43c96561c5988eabbd6bf2176d09b6` |

AgentCodex 声明的只读输入 digest 与 Controller 当前结果一致：AGENTS、control、Fins design、MiMo/DS reviews、Controller adjudication 与 entry validation 均未被 plan-fix gate 修改。工作区没有 product/test/README/design 新 diff；AgentCodex 只改了目标 untracked plan 并新增指定 fix artifact。Controller 自身已有 control/adjudication变更不归于 AgentCodex。

`git diff --check` 通过；两个 untracked write targets 分别以 `git diff --no-index --check /dev/null <file>` 验证无 whitespace diagnostic。由于本 gate 没有 Python/product/test 修改，未重复运行 tests、coverage、pyright 或 Ruff；entry validation 的 full pyright 零错误与 Ruff 162 baseline 未被代码变化影响，implementation gate 仍须按 plan 全量重测。

## 3. Accepted fix closure matrix

| ID | Controller 验证 | 状态 |
| --- | --- | --- |
| R06-PF-01 | §4.2 固定 per-ticker 跨进程 `batch_locks/<ticker>.publication.lock`，与 writer lock 分离；outer public guarded read + private unguarded helper、无 ambient marker、唯一锁序、`Source.open()` stable-fd 边界和跨进程 barrier tests 均自足。 | closed |
| R06-PF-02 | §4.2/§11 明确 R06 只保证一次 `Source.open()`；裸 `materialize()` 延迟/多次读取归 R07，不新增 wrapper/copy/lease/revision contract。 | closed |
| R06-PF-03 | §6 固定 `(filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta`，允许 partial 绑定非 authority 输入，batch 只能 invocation-time required keyword 传入。 | closed |
| R06-PF-04 | §3.2/§5.2 固定完整 staged ticker tree validation，不维护 touched set；source↔manifest 双向闭包是新的 storage commit invariant，primary 不 fallback，files 非空是有意 contract。 | closed |
| R06-PF-05 | §7.1 在 S1 删除 auto-batch、ContextVar、task/thread owner 与全部 ambient helpers；private manifest helpers 消费显式 state/batch/path，S3 仅 propagation。 | closed |
| R06-PF-06 | §6 把 CN company meta 和每个 Docling document 分成 caller-owned 短 transactions；Docling service 只消费 caller batch，不做跨 transaction rollback。 | closed |
| R06-PF-07 | §3.5/§7.3 明确 `FsBatchingRepository` 是四个真实 composition root 的新 production wiring，并与所有 wrappers 共享同一 repository set/core。 | closed |
| R06-PF-08 | §7.0 固定 S1/S2/S3 cumulative reviewability gates；每轮 accepted findings 必须 fix/re-review，无 magic 行数、中间 green、accepted commit 或兼容版本；S3 后仍统一 review 完整 R06 diff。 | closed |

未发现 accepted finding 被降格为 residual、测试 TODO 或“实现时再决定”。内容扫描未发现 validator 两策略、CN/Docling review 再裁决、implicit authority 延迟到 S3、slice review 未决定等 stale wording。

## 4. `materialize()` 调用图独立复核

Controller 运行 `rg -n '\.materialize\(' dayu --glob '*.py'`，结果精确为 8 个 production 文件、9 个调用点：

- documents processors：`bs_processor.py` 1、`docling_processor.py` 2、`markdown_processor.py` 1；
- Fins processors：`sec_processor.py`、`bs_report_form_common.py`、`bs_six_k_processor.py`、`source_text.py` 各 1；
- Fins pipeline：`sec_fiscal_fields.py` 1。

Controller 又直接读取 `dayu/documents/processors/source_snapshot.py`：其 `__enter__` 用 upstream `Source.open()` 读到 EOF并复制到自有 spool，随后 `materialize()` 只物化该 spool。因此 AgentCodex 拒绝把它列作 upstream bare-path consumer 是正确的证据纠正，不是规避 R07 residual。

## 5. 设计边界与 re-review 挑战点

Fixed plan 没有偷带 R07-R11、Issue 142/151/175/177/178 或统一 authorization，也没有删除 containment、symlink、atomic write、writer fencing、journal recovery 等安全机制。

双路 re-review 仍须 adversarial 验证：

1. exclusive file lock 把 published readers 彼此也短时串行化是否仍是当前基础设施下的最小正确实现，且不会让 long I/O 扩大成新的产品 bottleneck；不得以此改回进程内锁或引入新 lock framework。
2. typed delayed opener 是否保持 `LocalFileSource` 的窄 storage-owned dependency，未成为 callback framework、snapshot facade 或 ambient guard seam。
3. 全 staged-tree validator 是否只验证 canonical owner facts，不把 reader fallback/producer推断写回 storage。
4. cumulative slice reviewability 是否可执行且没有与最终 complete-diff acceptance 混淆。

这些是 re-review 必须验证的实现可生成性问题，不是当前未裁决的产品问题。

## 6. Next gate

唯一 next gate 是 AgentMiMo / AgentDS 对 SHA `ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43` 的 fixed complete plan 做并发独立 re-review。任何 accepted finding 必须再次由 AgentCodex 全部修复并 re-review。只有双路收敛且 Controller accepted-plan decision 后，才可做 exact-scope plan local commit；implementation 仍不得提前开始。
