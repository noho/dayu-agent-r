# wu-cli-download-01 Slice 2 Implementation Evidence

## 1. Gate / HEAD / scope

- Gate：Gateflow implementation，Slice 2（DL-F07、DL-F11 summary）。
- 基线 HEAD：`c6829400a5e37892464a614590062511554f9633`。
- 未创建 commit；未运行真实 CLI；未修改 README、registry、oracle、任务书或 plan。
- 实际 production diff 严格位于 Slice 2 allowlist：
  - `dayu/fins/download_contract.py`
  - `dayu/fins/direct_events.py`
  - `dayu/fins/ingestion_runtime.py`
  - `dayu/fins/downloaders/sec_downloader.py`
  - `dayu/fins/pipelines/sec_pipeline.py`
  - `dayu/fins/pipelines/cn_pipeline.py`
  - `dayu/fins/storage/repository_protocols.py`
  - `dayu/fins/storage/fs_source_document_repository.py`
  - `dayu/fins/storage/_fs_source_document_core.py`
  - `dayu/cli/output.py`
  - `dayu/service/fins_wait_adapter.py`
- 实际 test diff 严格位于 Slice 2 allowlist：
  - `tests/fins/test_sec_downloader.py`
  - `tests/fins/test_sec_pipeline_download.py`
  - `tests/fins/test_cn_download_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `tests/cli/test_output.py`
  - `tests/service/test_fins_wait_adapter.py`

## 2. Owner 与 root-cause 证据

- SEC request policy owner 是 `SecDownloader`：原实现由构造和 `configure` 两次解析 User-Agent，未配置时仍生成匿名 fallback header，并在配置日志中写完整身份值。
- provider transport owner 是发送请求并捕获底层异常的 downloader/source adapter；runtime 原先只能根据通用异常基类猜测 provider 语义。
- source outcome owner 是 SEC/CN adapter boundary：原实现从 source-private mapping 用默认值、字符串强转和 raw summary count 生成弱摘要，row、filter 与 count 没有统一 typed 真源。
- artifact locator owner 是 source storage repository：只有该层能在 publication guard 下确认 published identity 并返回相对 workspace 的真实目录 locator。
- public terminal owner 是 Fins runtime；CLI 与 wait adapter 只应消费同一 runtime typed object，不能读取 storage、日志或 raw mapping 补算。

## 3. 实现内容

### DL-F07

- SEC User-Agent 在 downloader composition 只解析一次，保存 `CONFIGURED | UNCONFIGURED` typed state；`configure` 不再解析或重复 warning。
- 未配置时 `_build_headers` 在 rate-limit、client refresh 和 HTTP 调用之前抛 `SecUserAgentConfigurationError`；不存在 fallback header。
- 配置与请求日志只输出 configured boolean、method、status 和 closed transport category，不输出身份值、endpoint 或 raw exception。
- SEC HTTP owner 将 timeout、connection、HTTP status、protocol、unknown 映射为 `FinsDownloadProviderError`，同时给出 retryable 与固定 safe message。
- runtime 直接消费 typed provider error，构造 configuration/provider transport/storage/execution closed public failure；不读取异常文本或异常链。

### DL-F11 summary

- `download_contract` 新增 effective filters、互斥 document disposition、完整 operation-local rows、守恒 counts、missing periods 与 terminal disposition。
- SEC/CN adapter 使用单一 strict projection helper读取 source-private result；缺字段、错类型、未知 status 直接失败，raw summary counts 不作为事实真源。
- storage protocol/wrapper/core 新增 read-only `PurePosixPath` locator query；查询在 publication guard 下验证 published meta，并返回 workspace-relative source document 目录。
- runtime 从完整 typed rows 构造最多 10 行的 `FinsDownloadPublicSummary`；`omitted_count = discovered_count - public_row_count`，计数仍来自完整 rows。
- public row、summary 与 failure contract 拒绝 URL、绝对路径、raw/provider payload 标记，并校验 reason、locator、visible disposition counts 和 terminal disposition 组合。
- CLI 与 wait adapter 机械投影 `FinsResultSummary.download/failure`；download 不再使用 generic label/value details，两个消费者均不扫描文件、不读取 raw dict 或日志。
- 删除 `ingestion_runtime` 对 `FinsDownloadResultSummary` 的旧名字 re-export；生产与测试直接从 contract owner 导入。

## 4. Owner tests

- 受影响 Slice 2 集：`341 passed`。
- 扩展 coverage union（加入既有 CLI session 与 storage owner tests）：`705 passed`。
- 关键断言：
  - 未配置 SEC 身份在首个 HTTP 前 typed fail，client 调用数为 0，同一 downloader warning 恰好一次。
  - 配置日志不含身份值；请求诊断不含 endpoint 或 raw exception。
  - typed provider error 的敏感 cause 不进入 runtime public result。
  - SEC/CN row counts 从 strict typed rows 派生，忽略不可信 raw summary counts，未知 status fail closed。
  - 真实 storage locator 是非绝对 `PurePosixPath`，不含 workspace root。
  - 18 个完整 owner rows 投影 10 个 public rows，`omitted_count` 精确为 8。
  - CLI 与 wait adapter 均直接消费同一 typed public object；wait 成功结果不包含被注入的 generic details。
  - wait 失败结果以自解释 JSON 同时携带相同 nested download 与 failure object，不退化为泛化错误文本。

## 5. 静态与质量验证

- 完整 `pyright`：`0 errors, 0 warnings, 0 informations`。
- Slice 2 修改文件 `ruff check`：通过。
- Slice 2 修改文件 `ruff format --check`：17 files already formatted。
- `python -m compileall -q dayu tests`：通过。
- `git diff --check`：通过。
- allowlist 检查：除本 artifact 外，所有 changed production/test files 均属于 Slice 2 allowlist。
- compatibility stop check：旧 runtime 模块不再公开 `FinsDownloadResultSummary` 名称；adapter strict projection 区域不存在 `.get()`、`getattr`、`hasattr` 或字符串强转补偿。
- consumer static check：CLI output 与 wait result projection 不 import 私有 storage 模块，不调用 glob/rglob/file walk，不从 raw mapping 构造 download facts。
- secret/path check：production 与本 evidence 不含测试联系 canary、测试 provider endpoint或测试绝对路径；public contract owner tests同时断言这些值不会进入 result、CLI 或 wait serialized value。

仓库级 `ruff check .` 另命中 86 个既有基线问题，均位于本 Slice 未修改文件；由于 strict allowlist，未越界修改。Slice 2 changed-file Ruff 结果为全绿。

## 6. 修改 production 单文件覆盖率

扩展 coverage union 的结果：

| Production file | Coverage |
|---|---:|
| `dayu/cli/output.py` | 83% |
| `dayu/fins/direct_events.py` | 87% |
| `dayu/fins/download_contract.py` | 81% |
| `dayu/fins/downloaders/sec_downloader.py` | 91% |
| `dayu/fins/ingestion_runtime.py` | 90% |
| `dayu/fins/pipelines/cn_pipeline.py` | 80% |
| `dayu/fins/pipelines/sec_pipeline.py` | 86% |
| `dayu/fins/storage/_fs_source_document_core.py` | 84% |
| `dayu/fins/storage/fs_source_document_repository.py` | 96% |
| `dayu/fins/storage/repository_protocols.py` | 100% |
| `dayu/service/fins_wait_adapter.py` | 93% |

总覆盖率为 88%；所有修改 production file 均达到不低于 80% 的门槛。

## 7. Residual risks / deferred work

- 按 controller 明确要求，本 Slice 未运行真实 CLI 或真实 provider；真实动态网络分类与终端 screen 观察留给后续 DL-G gate。
- 仓库级 Ruff 基线仍非全绿；问题全部在 Slice 2 allowlist 外，本实现没有新增或扩散 changed-file Ruff 问题。
- Slice 3 的 conversion-completed 与 canonical cancellation、Slice 4 的并发/integrity 不属于本次实现，未提前修改。
- 当前状态等待 controller 安排 implementation review；未自行进入 review、deepreview、PR 或 commit gate。
