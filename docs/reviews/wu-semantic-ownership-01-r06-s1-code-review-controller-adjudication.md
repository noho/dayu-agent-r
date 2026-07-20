# WU-SEMANTIC-OWNERSHIP-01 R06-S1 双路累计 Code Review Controller 裁决

## 1. 身份与边界

- work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R06-S1 cumulative checkpoint；不是新 WU。
- review baseline：`d048adf7ec1135aaf575384432ebf1137f8a34f2` 到当前未暂存 working tree。
- 第一路：`docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-mimo.md`，verdict `PASS`，material finding `0`，observation `9`。
- 第二路：`docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-ds.md`，verdict `PASS-WITH-FINDINGS`，报告 finding `3`。
- 真源优先级：`AGENTS.md`、overdesign controller discussion、`docs/fins/design.md`、accepted R06 plan、plan re-review Controller 裁决、当前直接代码证据。
- 本裁决只授权 R06-S1 accepted finding fix、对应测试与证据；不授权 S2/S3、R07、Issue 175/177、README、统一 authorization framework、stage/commit/push/PR。

## 2. 动机与 semantic owner 判断

S1 的核心产品动机成立：storage transaction authority、published-tree publication guard、recovery 与 read graph 必须由 Fins storage owner 同源实现。两路 reviewer 均确认 opaque `BatchToken`、registry-only mutation authority、writer/publication lock 分离、minimal journal、recovery fail-closed continuation、VF-01..04 与安全边界成立。

当前剩余问题不是新增产品能力，而是本轮已修改 owner boundary 内的三处 contract 精确性缺口：

1. accepted plan §4.2 对每个 public published read 的 outer guarded/private unguarded graph 是全称结构约束；不能因单个方法暂时没有 public-to-public 组合就把例外固化为局部设计。
2. processed meta 文件名与读取策略由 Fins storage owner 唯一承诺；docstring 不能虚构不存在的 fallback。
3. `ProcessedDocumentRepositoryProtocol` 是公开返回 contract owner；shared core 不能继续产生无人消费、且与 public contract 不一致的 `bool` 语义。

因此需要在各自 owner boundary 做最小、严格、无兼容分支的修复。

## 3. Finding 裁决

### R06-S1-CR-F01 — maintenance public read 未使用 private unguarded helper

- 来源：MiMo O-01。
- reviewer 原判：非 material observation。
- Controller 裁决：**accepted / LOW**。
- 直接证据：accepted plan §4.2 明确要求“每一个 public published repository meta/list/read entry”在最外层获取一次 guard，且只调用显式 private unguarded helper；`dayu/fins/storage/_fs_maintenance_core.py::read_rejected_filing_file_bytes` 当前在 public entry 的 guard 内直接执行路径解析、存在性检查和 `read_bytes()`。
- root cause：实现只验证了当前无嵌套、自死锁风险，却把 accepted universal read-graph invariant 降格为“只有组合读才需要 helper”的局部最小实现。
- semantic owner：`_FsFilingMaintenanceMixin` 的 published read graph。
- required fix：抽取 typed private unguarded helper；public entry 只负责 normalize、acquire、delegate、release。不得引入 ambient held-marker、重入锁或 public compatibility 参数。
- required verification：覆盖成功读取、missing、directory/error 分支中的 owner behavior，并保留 public read self-call / guard scan 与 scoped typing。

### R06-S1-CR-F02 — processed meta docstring 虚构双文件 fallback

- 来源：DS F-01 与 F-03。
- Controller 裁决：**accepted as one deduplicated finding / LOW**。F-03 是 F-01 的同一 root cause 和同一修复面，不单独计数。
- 直接证据：`_FsProcessedMixin.get_processed_meta` 的 docstring 声称优先 `meta.json`、再回退 `tool_snapshot_meta.json`，并声称“两种元数据文件均不存在”；实际 `_processed_meta_path_for_read` 只从 `_PROCESSED_META_FILENAME = "tool_snapshot_meta.json"` 派生一个路径，`_get_processed_meta_unguarded` 也只读取该路径。
- root cause：本轮扩展 touched contract docstring 时保留了已与 storage layout 真源脱节的历史描述，结构完整但内容不真实。
- semantic owner：Fins storage processed meta path/read contract。
- required fix：删除虚构 fallback，只准确承诺 published `tool_snapshot_meta.json` 的唯一读取行为，并同步准确的返回值/异常说明；不得实现新 fallback 或旧布局兼容。
- required verification：确认全仓当前调用者与测试不依赖该虚构语义；补 owner-level contract assertion 或等价 source/behavior verification。

### R06-S1-CR-F03 — shared core reprocess marker 返回语义漂移

- 来源：DS F-02。
- Controller 裁决：**accepted / LOW**。
- 直接证据：`ProcessedDocumentRepositoryProtocol.mark_processed_reprocess_required` 与 `FsProcessedDocumentRepository` 均声明 `-> None`，wrapper 丢弃 core 返回值；`_FsProcessedMixin.mark_processed_reprocess_required` 和其 private impl 却返回 `bool`。当前调用点无消费该值，S1 owner test 也只检查副作用。
- root cause：S1 把 explicit `batch` 与 `required` 传播到 shared core 时保留了旧 core 的内部 success flag，没有以 public repository contract 为唯一真源收敛返回语义。
- semantic owner：`ProcessedDocumentRepositoryProtocol` 的 mutation contract；shared core 是其直接实现边界。
- required fix：shared core/public wrapper/protocol 统一为 `None`；`required=False` 或目标不存在时保持现有 no-op 业务行为，但不得产生另一套 success 语义。private impl 也应删除死 `bool` 返回，除非直接代码证据证明 owner 内存在真实消费者。
- required verification：owner-level tests 明确覆盖 `required=False`、存在目标、缺失目标均返回 `None` 且副作用正确；全仓调用扫描不得出现对返回值的依赖。

## 4. Observation 与 residual 裁决

- MiMo O-02：S2 intentional residual；保留 `stage_source_document`、`ingest_complete=False` 与 staging ack，S1 不修。
- MiMo O-03/O-04：owner failure-injection tests 从 storage-owned `_ActiveBatchState` 取得布局，不从 public token 推导；接受为当前测试策略，不新增 public observation API。
- MiMo O-05/O-06：现有 failure injection 与 Event barrier 辅助 polling 有直接验证目的，不形成当前产品 finding。
- MiMo O-07/O-08：既有内部 owner/AST guard 测试维护成本，不授权新增 framework 或本轮重构。
- MiMo O-09：没有证明当前 guard release 行为错误；现有并发与 release failure tests 已覆盖本轮 contract，不新增 speculative test。
- DS residual 1/2：分别由 R06-S2 与 R06-S3 accepted sequencing 承接，不能作为 S1 compatibility 理由。
- DS residual 3：`previous_primary: Any` 是既有且未触及的 JSON 边界；无当前授权。
- R07 snapshot/revision/opaque mapping、Issue 175/177 与统一 tool authorization framework 继续严格不实施。

## 5. 最终 ledger 与下一 gate

| 类别 | 数量 | 状态 |
|---|---:|---|
| accepted finding groups | 3 | `R06-S1-CR-F01..03`，必须由 AgentCodex 全部修复 |
| duplicate reviewer findings | 1 | DS F-03 合并到 `R06-S1-CR-F02` |
| no-fix observations | 8 | 明确无当前动作 |
| blocking question | 0 | 无 |

当前 verdict：**FIX REQUIRED**。

下一 gate 是 AgentCodex R06-S1 code-review fix。完成后 Controller 独立验证，并由 AgentMiMo / AgentDS 对完整累计 S1 tree 并发 re-review；两路关闭 `R06-S1-CR-F01..03` 前不得进入 S2，也不得创建中间 accepted commit。
