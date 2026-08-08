# PR 190 F20 Storage-owned Material Audit

## Status and authority

- Work unit：F20。
- Verdict：`PASS` for the narrow material identity / parent / exact-content-duplication predicates recorded below；它不证明
  context trigger、compaction、provider behavior 或 B2。
- 唯一文档读取路径：
  1. `ProcessedDocumentRepositoryProtocol.list_processed_documents`；
  2. `ProcessedDocumentRepositoryProtocol.get_processed_handle`；
  3. `DocumentBlobRepositoryProtocol.list_entries`；
  4. `DocumentBlobRepositoryProtocol.read_file_bytes(handle, "sections.json")`。
- concrete production implementation：`FsProcessedDocumentRepository` + `FsDocumentBlobRepository`，通过同一个
  `build_fs_repository_set(..., create_directories=False)` 装配。
- 审计目标：immutable F19 failed observation 使用的 AAPL 2025 10-K corpus；只读 owner projection，不复制或复用 F19
  Session、EventLog、SQLite、Memory、RunInput、artifact 或 execution state。
- public document identity：ticker `AAPL`、document id `fil_0000320193-25-000079`、form `10-K`、fiscal year `2025`。
- repository 返回的 `sections.json` bytes SHA-256：
  `dcc1aaf01df6ed5abfcf17bbc58a8ee6a32ff84a741f68058efc62e5dfee85b5`。
- path-redacted audit stdout SHA-256：
  `827ba9bdebb81609830f5c374dfe520a1a00f7cc63b3fe0d8166500400d062e5`。
- audit helper SHA-256：
  `97cbd37687d3f70077aacafc43a291820b8a01a7af2466132be048d6daf3111e`。
- helper validation：`ruff check` PASS、targeted `pyright` `0 errors`、`compileall` PASS；同一 owner read 重跑得到相同
  path-redacted stdout SHA-256。

此前 Controller 曾用 `jq` 直接读取 private `sections.json`。该动作不符合项目财报文档存取 owner 约束，输出已明确作废，
不构成本 artifact、plan、fix、review 或 formal observation 的输入，也不得用于 PASS。下面所有值均由上述 repository API
重新读取的 bytes 独立计算。

## Predicates

本窄审计只使用 storage owner 实际公开的数据：`ref`、`summary.parent_ref` 与 `content`。当前 published section contract不提供
源文档 `[start,end)` offset，因此本 artifact 不发明 range。材料 no-padding 判定冻结为：

1. 同一 recipe 不同时选择 ancestor 与 descendant；
2. content SHA-256 两两不同；
3. 任意两个 selected content 均不存在双向全文包含。

这组 predicate 精确排除本轮 review 发现的“选择 parent section 后又重复选择其完整 child chunks”问题；它不声称不同财报 section
之间没有共享普通词语或短句。

## R1 isolated risk material

| ref | title | parent_ref | chars | content SHA-256 | six target strings |
| --- | --- | --- | ---: | --- | --- |
| `s_0003_c04` | Business Risks | `s_0003` | 25,719 | `c724dd5827dbabbd7840d2d5a34b9bf1d1b7194914c0227593283a71bc952732` | all absent |
| `s_0003_c05` | Legal and Regulatory Compliance Risks | `s_0003` | 17,986 | `6ee85666a8387447245d6016292a60bf0f437937bee9470db58e37ab6de69190` | all absent |
| `s_0003_c06` | Financial Risks | `s_0003` | 8,183 | `6771dcc939b91d848e582c49911c52889c589f79d51455e9be3e70715355a5de` | all absent |

“six target strings”按固定顺序表示 `416,161`、`133,050`、`391,035`、`123,216`、`21.7`、`18.2`。三项为同一
parent的 sibling refs；三组无序 pair 均为 `same_digest=false`、`left_contains_right=false`、
`right_contains_left=false`。

## R2 non-overlapping new material

| ref | title | parent_ref | chars | content SHA-256 | target strings present |
| --- | --- | --- | ---: | --- | --- |
| `s_0011` | Part II - Item 7 | `null` | 18,013 | `289421017191a49a9736e222fde7e92922d841d06c03b3744af772f8efbef047` | `416,161`, `391,035` |
| `s_0012` | Part II - Item 7A | `null` | 3,015 | `e797fb36bdc9bc41e182b23c626e44d992211bec933e17ff92b574812a194702` | none |
| `s_0013` | Part II - Item 8 | `null` | 61,252 | `d1a11c06db1a08e644946e6869cc152aa55353c5437214c1c2b85a1e62065607` | `416,161`, `133,050`, `391,035`, `123,216` |
| `s_0015` | Part II - Item 9A | `null` | 4,494 | `05e6c7a0f102a286d4cc57f427647b9715c6ff05d98b75cd49bae57382bfc15d` | none |
| `s_0023` | Part IV - Item 15 | `null` | 10,586 | `84520d108258939e8a01814fe9d6bcebbf0b01cc088ccc4cc0460071563c4294` | none |

五项均为 top-level sibling refs，未选择任何 child chunk。10 组无序 pair 均为 `same_digest=false`、
`left_contains_right=false`、`right_contains_left=false`。`21.7` 与 `18.2` 在五项中全部 absent。

## Execution gate

F20 Slice 1 必须从完全 fresh seed 通过同一 `dayu.fins.storage` repository API 重算本 artifact 的 document identity、blob SHA、
section ref/parent/content SHA/char count/target-presence 与全部 pairwise predicates。只有 exact match 才能进入 production
renderer/estimator trigger proof；任一偏差都必须 seal 为 `setup-blocked`，禁止直接读取仓储文件、添加 padding、重复 parent/chunk、
降低 threshold、修改产品或调用 provider。
