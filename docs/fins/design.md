# Fins Design

本文是 Fins 财报领域的稳定设计真源。Host / Engine / Tool 的设计分别归
`docs/host/design.md`、`docs/engine/design.md` 与 `docs/tool/design.md`；Fins
拥有财报来源、仓储事务、文档发布、读取一致性、财务/XBRL 结果和 provider
discovery 完整性语义。Host / Service / CLI 只能消费 Fins 的 typed contract，
不得从路径、文件名、文档 ID、消息文本或偶然状态重算财报事实。

## 1. Storage Transaction Ownership

一个 filesystem batch 只能有一个显式 transaction owner。begin 返回的 transaction
handle，或由该 handle 明确创建的 transaction-scoped repository，是后续 mutation、
commit 与 rollback authority 的唯一真源。

Storage 不得同时使用显式 token 和隐式 `ContextVar`、当前 asyncio task、thread id
或调用栈身份决定同一写权限。跨进程/跨实例 ticker lock 只负责互斥，不成为第二个
业务 transaction owner。

Crash-recovery journal 只保存恢复 commit state machine 所需的 transaction identity、
ticker、phase 与 staging/target/backup locator。进程内 task/thread owner token、随机
ambient authority、PID 或 hostname 只有被恢复算法直接消费时才允许持久化。

## 2. Source Publication And Blob Ownership

正式 source repository 只发布完整 source 业务事实。临时 meta、blob 与 processed
mutation 必须留在 storage transaction 的 staging area；commit 一次性发布 final source、
其 blobs 与关联状态。失败、取消或 pre-commit crash 不得让 read path 看见半文档。

`ingest_complete=false` 不作为正式 source meta 的 staging acknowledgement 子状态，
blob repository 也不得要求 producer 先发布该业务记录才能写入 transaction staging。
如果未来需要跨进程恢复未完成 ingestion，必须新增独立 ingestion-state contract，明确
owner、resume、cleanup 与 terminal 规则；不得复用 source business meta 充当事务 marker。

## 3. Provenance And Citation

Source repository 拥有 source kind、ingest method、source provider 与完成态 provenance。
当前 provider 至少覆盖 SEC EDGAR、CNInfo、HKEXnews 与 user upload。新增 provider 必须
扩展同一 typed domain contract。

Read projection 从 repository provenance 派生业务可读 citation。不得根据
`document_id` 前缀、路径、文件名、ingest method fallback 或测试 fixture 猜 provider / source
type。所有 read/search/section/table/page/financial/XBRL 路径复用同一 citation owner。

## 4. Source Revision And Read Consistency

Storage owner 必须提供同源的 source snapshot 与 revision/version。Revision 只表达会改变
processor/read 结果的 source 版本，不由 read runtime 或其它消费者各自挑 meta 字段重算。

Read cache 以 storage-owned revision 失效。并发更新期间，read boundary 可以做有界内部
重试以取得稳定 snapshot；只有无法取得稳定版本时才返回 typed
`source_changed_during_read`。消费者不得用 revision-before/revision-after 的重复读取和
字段 hash 另建第二套版本真源。

Decode、search-index、XBRL-query、source-change 等失败使用 typed business error；下游不得
解析异常消息恢复错误分类。错误值只能表达调用方或模型可理解的业务失败，不暴露
processor method name、cache branch 或 storage 实现细节。

## 5. Financial Statement Result

LLM-facing financial statement 的最小业务 contract 包含：ticker、document identity、source
citation、statement type、periods、rows、currency、units、scale、data quality 与可选的业务
reason。这些字段必须由 processor/domain producer 产生并由 read projection逐字段消费；read
runtime 不补写、猜测或重算期间、倍率、质量或原因。

`data_quality` 区分结构化 XBRL、文档抽取与 partial。`reason` 只保留会改变模型判断或恢复
动作的业务原因；processor method missing、fallback branch、cache state 等实现原因不得进入
公共结果。`statement_locator`、raw labels 汇总或其它 producer diagnostics 默认保持内部；没有
独立业务消费者和设计补充时不得作为必填 LLM-facing schema 冻结。

## 6. XBRL Facts Result

LLM-facing XBRL 结果包含：ticker、document identity、source citation、query parameters、已
去重 facts、一个表示实际返回 facts 数量的 `fact_count`、data quality 与可选业务 reason。

Processor raw `total` 可以用于 producer contract 校验，read-side dedupe count 可以用于内部
diagnostic，但不得把“去重前 total”和“去重后 count”同时暴露给 LLM。公共 count 必须与
实际返回的 `facts` 同源。Read runtime 可以清洗和去重 facts，但不得覆盖 processor-owned raw
事实后再把重算值冒充 producer contract。

## 7. Direct Stream Terminal Contract

一次 Fins direct download/preprocess/upload stream 必须恰好产生一个 terminal `RESULT`。
该不变量由一个 Fins-owned stream validator / typed terminal boundary 判定一次。Service 与 CLI
只消费同一个 terminal 或 typed protocol error，不得再次扫描并独立判断 missing/duplicate
terminal。

## 8. HKEXnews Discovery Completeness

HKEXnews title search 使用官方 cumulative `rowRange` continuation：初次请求100条；
`hasNextRow=true` 时，用相同查询与排序条件请求更大的 cumulative range，直到 provider
明确返回完整结果。每次响应都是从第一条开始的累计 snapshot，consumer 只使用最后一次
完整响应，不拼接重叠前缀。

只有同时满足以下条件，discovery 才能声明 complete：

- `hasNextRow=false`。
- `loadedRecord == recordCnt`。
- `loadedRecord == len(result rows)`。

总数在续取期间变化时，使用最新 provider facts 继续请求。字段矛盾、扩大 range 后无进展，
或 provider 持续声明存在下一条却拒绝返回时，返回 typed provider-protocol failure；不得把首
100条当完整结果。没有 provider hard-cap 直接证据时，不额外设计日期递归拆分或本地固定总量
上限。

## 9. Filesystem Identity And Containment

Filesystem repository 必须阻止 absolute path、`.`、`..`、separator、drive/UNC 或 symlink
resolution 逃出 owned storage root。Containment 是 storage correctness 与局部安全边界，不能
因 repository-wide tool security 尚未设计而删除。

外部 ticker/document id 是领域 identity，不天然等于 filesystem path component。Storage 应在
唯一 owner 中把 opaque identity 映射/编码为内部 key，并保证 round-trip；不得把底层文件系统
命名限制扩展成外部 ID 的业务 grammar。该边界属于本 WU 涉及的安全相关行为，最终 closeout
必须单独说明。

## 10. Upload Batch Plan

Fins 拥有 `upload_filings_from` 的 typed batch plan：扫描候选文件，识别 filing/material，派生
财期与 material metadata，按同一领域规则去重/过滤，并返回 recognized/material/skipped 事实。
CLI 只消费该 plan 生成平台脚本和用户可读摘要，不得再次从文件名或 plan raw fields 重算分类。

Batch plan 是进程内领域 contract，不包含 `dayu-cli` executable、flag 顺序、shell quoting 或
versioned argv envelope。CLI grammar 与跨平台可执行脚本的 owner 在 `docs/ui/design.md`。
