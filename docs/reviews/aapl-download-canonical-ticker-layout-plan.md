# AAPL SEC 下载与 canonical ticker 目录修复计划

## Gate

- gate：plan
- work unit：修复 AAPL `SCHEDULE 13G` 下载失败，并恢复 `portfolio/<canonical ticker>` 目录
- base：`2040e9ce`
- branch：`codex/prompt-oracle-adjudication`
- unrelated dirty files：`docs/cli_ci.md`、`docs/cli_ci_oracles.json`；本 work unit 不读取其内容作为真源、不修改、不暂存
- completion status：待 plan review

## 目标、动机与成功信号

目标包含两个已由用户确认的行为：

1. SEC submissions 的 `primaryDocument` 即使带展示转换路径，也必须在进入 `FilingRecord` 时成为可持久化的归档文件名，不能把路径分隔符传给 blob 仓储。
2. ticker 已由 `dayu.fins.ticker_normalization` 产生 canonical 业务值，文件系统 ticker target 必须是 `portfolio/<canonical ticker>`；document ID 继续使用 storage-private identity mapping。

直接成功信号：

- accession `0002100119-26-000139` 的
  `xslSCHEDULE_13G_X02/primary_doc.xml` 被收集为 `primary_doc.xml`，后续下载、主文件判断和 source upsert 使用同一个名称。
- fresh workspace 中 AAPL 的 published target、staging、backup 与 lock locator 以 canonical `AAPL` 为 ticker 组件，正式数据位于 `portfolio/AAPL`。
- filing/material/processed/rejected document ID 的私有目录映射、descriptor、snapshot、revision 与 publication 原子性不变。
- `list_documents` 与其它八个 read Fins tools 在 fresh `portfolio/AAPL` 布局上全部成功；consumer 不直接读取 `portfolio/`、`.identity.json` 或物理 locator。

## 第一性原理判断与直接证据

### SEC 下载失败

- SEC submissions 对 accession `0002100119-26-000139` 返回
  `form=SCHEDULE 13G`、`primaryDocument=xslSCHEDULE_13G_X02/primary_doc.xml`。
- SEC archive `index.json` 的业务文件名是 `primary_doc.xml`；带转换前缀和直接文件名的 URL 均返回 HTTP 200。
- `collect_filings_from_table(...)` 当前把 `primaryDocument` 原样写入
  `FilingRecord.primary_document`。
- `SecDownloader.list_filing_files(...)` 把该字段原样写入
  `RemoteFileDescriptor.name`，`download_files_stream(...)` 再把它作为 `filename`
  交给 blob 仓储。
- storage 的 `_normalize_filename(...)` 正确拒绝 `/`。因此错误 owner 在 SEC
  submissions 到 `FilingRecord` 的输入投影，不在 storage validator 或 CLI。

### ticker 目录

- `dayu.fins.ticker_normalization.normalize_ticker(...)` 已唯一拥有 canonical ticker
  语义，并保证当前 US/HK/CN canonical grammar 是单一安全路径组件。
- 2026-07-17 的 R07 实现提交 `64dbfbaf` 把 ticker 与 document ID 一并提升为
  arbitrary opaque external identity；`_derive_storage_key("ticker", "AAPL")`
  因而产生用户观察到的
  `id-3a993c8eb1f57f75f174ef72583041d182ed90c89ec9a6bcb87f9810c9fb4473`。
- R07 前的实现明确使用 `portfolio/<normalized ticker>`。R07 对 document ID 的
  所有权判断成立，但对已经 canonicalized 的 ticker 属于范围泛化。
- read runtime 先通过 `try_normalize_ticker(...)` 和 company repository 得到
  canonical ticker，随后只调用 repository protocol；`dayu/fins/tools`、
  processors 与 service runtime 均不直接引用 `portfolio`、private key 或
  identity descriptor。因此物理 ticker locator 的 owner-level 修改不应进入
  read tool 业务投影。

## 非目标与 scope boundary

- 不放宽 filename、primary filename、object key、URI、containment 或 symlink 校验。
- 不把任意外部 ticker、公司名或路径样式字符串作为物理目录；storage ticker
  identity 只接受 ticker normalization owner 能产生的 canonical 值。
- 不改变 document ID 的 opaque round-trip 与 private locator。
- 不读取、迁移、兼容或双写 R07 的旧 `portfolio/id-*` ticker 布局；按项目约束以
  fresh schema 验证。旧目录不会被本 work unit 删除。
- 不改变 read tool schema、LLM-facing 文本、document selection、processor cache、
  source snapshot 或 revision contract。
- 不修改 CLI CI oracle 文档，不顺带修复其它 SEC form 或 storage 重构机会。

## 设计决定

### 1. SEC primary document owner

在 `dayu/fins/pipelines/sec_filing_collection.py` 增加模块级私有 helper，把 SEC
submissions `primaryDocument` 投影为归档文件名：

- trim 后必须非空；
- 拒绝反斜杠、以 `/` 开头或结尾的值；
- 把 SEC 返回的 POSIX 相对路径按 `/` 分段；每个 segment 必须非空且不得为
  `.` / `..`，因此 double separator、dot traversal 与 trailing separator 全部
  fail closed；
- 取最后一个已验证 segment 作为归档文件名，并再次按单文件名 contract 校验；
- 不保留原路径作为 fallback，不在 downloader、workflow 或 storage 重算。

`collect_filings_from_table(...)` 只把 helper 的结果写入
`FilingRecord.primary_document`。因此 `RemoteFileDescriptor.name`、下载回调、
主文件比较和 source meta 的 `primary_document` 从同一真源派生。

### 2. ticker locator owner

在 `dayu/fins/storage/_fs_identity.py` 保持一个 identity owner，但按 namespace
区分 locator：

- ticker namespace：校验输入已经等于 `normalize_ticker(value).canonical`，storage
  key 直接返回 canonical ticker；
- filing/material/processed/rejected document namespace：继续使用现有
  namespace-separated SHA-256 private key；
- ticker descriptor 继续存在，用于 publication、backup、recovery 和 corruption
  双向校验；其 `external_identity` 必须是 canonical ticker；
- 不在 storage 内把非 canonical ticker 静默改写为另一个业务 identity。

`resolve_existing_ticker(...)` 是公司 alias 查询入口：

- 每个 candidate 先用 `try_normalize_ticker(...)` 判断是否真是 ticker；
- 只有识别成功时才以其 canonical 值执行 direct locator lookup；
- 识别失败的公司名/普通 alias 不进入 ticker locator，继续交给现有 company alias
  index；alias index 仍复用 `_canonicalize_ticker_alias(...)`；
- 其它 repository mutation/read API 继续要求调用方传 canonical ticker。

该选择保留 R06/R07 的 transaction、descriptor 与 snapshot 机制，只纠正 ticker
locator，不拆除对 document ID 仍有价值的 private mapping。

## Contract、schema、状态机与公共接口

- filesystem fresh schema 变更：ticker target 从 private hashed key 变为 canonical
  ticker；旧布局不兼容。
- repository Python 方法签名不变。
- `BatchToken.ticker`、source/company meta、manifest、tool result 中的 ticker 继续是
  canonical 业务值。
- transaction 状态机不变；writer lock、publication lock、staging、backup 与 journal
  使用同一个 canonical ticker locator/descriptor 规则。
- SEC `FilingRecord.primary_document` 的内部 contract 从“上游原始字符串”收紧为
  “归档单文件名”；无公共 schema 或 LLM-facing schema 变更。

## Implementation slices

### Slice 1：SEC transformed primary document

- objective：阻止 SEC 展示转换路径进入文件名 channel。
- allowed production file：
  `dayu/fins/pipelines/sec_filing_collection.py`
- allowed tests：
  `tests/fins/test_sec_pipeline_download.py`
- exact changes：
  - 新增单一模块级 normalization helper；
  - `collect_filings_from_table(...)` 在构造 `FilingRecord` 前调用；
  - 增加真实形态
    `xslSCHEDULE_13G_X02/primary_doc.xml -> primary_doc.xml` contract test；
  - 增加普通单组件不变，以及空值、absolute、backslash、dot/dotdot segment、
    double separator、trailing separator 的 fail-closed 测试。
- expected outcome：下游所有 primary document consumer 只看到同一个安全文件名。
- stop condition：如果 SEC archive 真实存在必须保留的嵌套业务文件，而不是展示转换
  路径，则停止并重新确认 contract。

### Slice 2：canonical ticker locator 与 read tools 回归

- objective：fresh storage 使用 `portfolio/<canonical ticker>`，保持 document ID
  private mapping和全部 read tools 行为。
- allowed production files：
  - `dayu/fins/storage/_fs_identity.py`
  - `dayu/fins/storage/_fs_company_meta_core.py`
- allowed tests：
  - `tests/fins/test_fins_storage_provider.py`
  - `tests/fins/test_fins_storage_atomicity.py`
- exact changes：
  - ticker namespace key 直接使用经过严格验证的 canonical ticker；
  - document namespace key 派生不变；
  - alias lookup 只把 `try_normalize_ticker(...)` 成功的 candidate 送入 direct
    locator；公司名/普通 alias 只走 alias index；
  - 把旧“opaque ticker”测试迁移为“canonical ticker + opaque document ID” owner
    contract；
  - recovery/backup 测试使用 canonical ticker，并新增非 canonical/路径样式 ticker
    fail-closed 断言；
  - fresh workspace 精确断言 `portfolio/AAPL`；
  - 现有九个 read tool success/failure/cancelled 综合测试移除“canonical ticker 是
    private secret”的旧断言，继续禁止 document private key、revision、URI 和 temp
    path 泄漏，并显式断言九个 success outcome。
- expected outcome：目录可读、读写 API 与工具结果仍以 canonical ticker 为真源。
- stop condition：若任一 read consumer 直接依赖旧 hashed ticker grammar，先把它迁回
  repository protocol；不得在 consumer 增加新路径分支。

## 验证

每个 slice 后先运行 focused tests；全部实现后运行累计验证：

```bash
source .venv/bin/activate
pytest tests/fins/test_sec_pipeline_download.py -q
pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_storage_atomicity.py -q
pytest tests/fins/test_fins_read_runtime.py tests/fins/test_processor_read_consistency.py -q
python -m pyright dayu/ tests/ utils/
```

额外 contract assertions：

- `portfolio/AAPL` 存在且 ticker target name 精确为 `AAPL`；
- document directory name 不等于 raw document ID，descriptor round-trip 仍成立；
- `list_documents` 对 `AAPL` 与可规范化 alias 返回相同 canonical company ticker；
- company repository 对 `AAPL`、`aapl.us` 与 `apple` 都解析为 `AAPL`，未知 alias
  返回 `None`；
- 九个 read tools 在 fresh canonical layout 上均为 completed；
- SEC 测试证明 downloader/store callback 未收到带 separator 的 primary filename。

按单文件覆盖率目标，对四个修改的 production files运行 coverage；每个文件要求
`>=80%`。若完整 storage tests 成本过高，可先 focused node 定位，但 gate acceptance
必须包含上述累计测试。

## 文档决定

- 更新 `dayu/fins/README.md` 的 storage identity 稳定说明：ticker 使用 canonical
  目录，document ID 使用 private mapping；保留 snapshot/publication contract。
- 检查 `tests/README.md`。只有其现有 Fins storage 测试职责描述包含“opaque ticker”
  时才更新为新的 canonical ticker / opaque document ID 边界，不机械追加测试清单。
- 根 README、`dayu/README.md`、CLI README 不更新：命令参数、用户工作流和分层关系
  均未变化。

## 风险与 residual risks

- 旧 `portfolio/id-*` ticker workspace 与新 fresh schema 不兼容：owner 为部署/用户
  fresh workspace 操作，本 work unit 不迁移、不删除、不兼容读取。
- ticker descriptor 仍存在，物理目录可读性恢复但目录仍受 descriptor 一致性校验；
  这是保留 transaction/recovery integrity 的有意选择。
- SEC basename 投影依赖 EDGAR filing archive 文件平铺语义；已用目标 accession 的
  submissions、index 与 HTTP 结果验证。其它新型 SEC 路径若不满足该 contract，应由
  SEC collection owner 扩展并补直接证据，不由 storage fallback。

## Goal alignment 与不过度设计说明

- Slice 1 只对应“下载报错必须修复”。
- Slice 2 只对应“目录必须是 canonical ticker”以及用户要求的 read tools 影响验证。
- 保留现有 descriptor、transaction、document mapping 和 repository API，避免为目录名
  要求重写 storage。
- 不加入迁移器、双布局探测、compat shim、全局 identity catalog 或 read tool 路径
  fallback；这些都不属于已确认目标。

## Completion report

最终报告必须明确：

- 修改了 SEC primary document 的哪个 owner，以及 ticker/document identity 如何分离；
- 验证了哪些 focused tests、九个 read tools、coverage 与 pyright；
- README 是否更新；
- review findings 最终状态；
- 旧 `id-*` workspace 不兼容这一剩余风险及处理方式；
- draft PR URL 与下一步。
