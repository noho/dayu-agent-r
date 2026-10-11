# SEC HTML 图片资产 S1 实施记录

- Work unit：`sec-html-image-assets`；gate：`implementation`；slice：唯一 approved S1。
- Branch：`fix/sec-html-image-assets`；accepted plan：`771299b8244e5cb25ce8f943ab41671d8e59e16c`；原生产基线：`297bfbbc67b7d7468e3dfb6669a3385c4dd10d18`。
- Binding scope：已确认 goal 与 approved plan。沿实际入口和既定 owner 实施，没有重开设计、扩大 schema 或资产地址契约。
- Completion：**S1 实施和必要验证完成，交总控进入双路 code review 裁决**。本记录不表示 review/final closeout pass；没有 stage、commit、push、PR、其它 Agent 或 control/review 修改。
- Artifact：`docs/plans/sec-html-image-assets-s1-implementation.md`。
- Durable validation：`docs/validation/sec-html-image-assets-implementation.json`。下载文件、完整原始日志、临时 hook/脚本仅在 `workspace/tmp/`，不提交 Git。

## 实际 changed files / scope

生产文件仅四个：

- `dayu/fins/downloaders/sec_downloader.py`：有限直接图片解析、首 base、共享 URL/name/collision owner、严格解码、typed 发现错误、新增图片 listing 与 typed 文件失败日志。
- `dayu/fins/pipelines/sec_download_filing_workflow.py`：从实际待发布预取字节发现依赖；完整描述符集合/指纹；Phase A/B 当前下载契约资格；发现失败与取消；同 batch 原子发布。
- `dayu/fins/pipelines/sec_pipeline.py`：SEC 下载契约升为 `sec_pipeline_download_v1.3.0`，删除本地 rebuild 授予版本的参数。
- `dayu/fins/pipelines/sec_rebuild_workflow.py`：删除当前下载版本参数与写入，沿仓储 metadata update merge 保留最近正式下载版本或缺席状态。

测试文件：`tests/fins/test_sec_pipeline_download.py`、`tests/fins/test_sec_earnings_repair.py`、新增 `tests/fins/test_sec_html_image_assets.py` 和 `tests/fins/test_sec_html_image_assets_real_cli.py`。既有 downloader/stream 测试直接回归，未为它们新增生产兼容逻辑。

文档：根 `README.md`、`dayu/fins/README.md`、`tests/README.md`；另写本 artifact 与 validation JSON。总控原有 `docs/plans/sec-html-image-assets-control.md` dirty 修改保持原样，不属于本 worker changes。

## Decisions / 实际行为

1. **发现 owner 在 downloader。** 标准库 HTMLParser 收集 img/src、img/srcset、picture 内 source/srcset；属性间与跨 HTML 候选共同去重，不按尺寸、media、用途、扩展名选择图片。非 picture 的 source 不进入图片集合。srcset 按位置完整解析，支持 approved 有限 w/x/data 语法，Decimal 精确比较，歧义或非法列表整体 typed fail。
2. **首 base 与地址真源。** 全文第一个带 href 的 base 包括空 href，与标签位置无关；标准 URL 解析后检查完整 origin/申报路径组件。绝对候选独立于不安全 base，相对候选不能回退到归档根。显式绝对 base 的点段也先归一化再授权；编码分隔、遍历、多次编码、控制字符（含 Unicode C1）失败关闭。同申报子目录明确失败，不做 basename flatten。NFC/casefold 与控制名复用 storage public owner；基础文件与图片使用同一身份判断。
3. **字节与完整集合同源。** 接受分支先正式 unconditional 预取基础文件，只解析同一次 `_PrefetchedFile.content`；不使用 precheck 或旧 HTML，不为发现再次 GET HTML。发现成功后 base ∪ 新增图片成为指纹、集合比较及 upsert 的完整输入。基础 GET/发现失败先于晚期等价 skip；optional HEAD 不改变必要 GET 契约。
4. **版本与事务资格。** 删除 Phase A 的无版本 `integrity_complete` fallback；Phase B identity 相同也只按当前版本/非空指纹的既有快跳资格裁决。旧/缺版本 COMPLETE 普通下载补齐。竞争 writer 发布当前版本后重试快跳，发布旧版本后仍升级。所有网络在 batch 外，同一 token 内 materialize/reset/upsert/commit；失败和取消保留旧 publication，fresh 失败仍 MISSING。
5. **认证与持久化 owner 保持原边界。** 原 `build_source_fingerprint` 算法、source upsert、document version、首入库时间、processed 重处理与 storage URI/hash/manifest/revision 不另造替代真源。rebuild 不写 download_version；正式成功下载才认证当前契约。包版本保持 `0.1.4`。
6. **失败说明同源。** 图片 GET 失败沿原 FILE_FAILED → filing `file_download_failed` → adapter/CLI diagnostics 链；materializer 从 typed failure 投影安全文件名、reason_code、reason_message 到 operator log。发现错误在 begin 前给出所属 HTML 与封闭原因，不泄漏正文/不安全原地址/UA。

与 plan 的实际差异仅验证实现细节：coverage 的点号 source 模块探测会导入父包，并在模块回收后触发 NumPy C 扩展重复加载；改用 downloader/pipelines **目录测量同一测试集合**，逐文件验收四个 owner，无 omit/ignore/断言降级。2025 的正式 submissions primary 是封面 `tsm-20250717x6k.htm`，演示样例为正式选择的附件；修正了验证器“样例 HTML 必须为 primary”的错误假设，正式文件选择与生产筛选未改。

收尾强化 Unicode 控制字符规则并补 owner 断言后，以最终代码重跑完整受影响 focused 集合并追加 coverage；四文件行映射保持一致。真实 TSM 直接候选均为 ASCII，真实矩阵不承担 Unicode/base/srcset 的能力证明；这些边界由最终合成 owner 测试实际覆盖。

## Actual validation

全部命令先 `source .venv/bin/activate`。准确命令、exit、counts、完整 CLI argv/cwd、日志路径与 SHA256 见 validation JSON。

| 实际验证 | Exit / 结果 |
| --- | --- |
| `pytest -q tests/fins tests/cli/test_fins_commands.py --cov=dayu/fins/downloaders --cov=dayu/fins/pipelines --cov-report=term-missing --cov-report=json:workspace/tmp/sec-html-image-assets-coverage.json` | 0；3554 passed、9 skipped、3 个既有第三方 deprecation warnings；430.77s |
| `pytest -q tests/fins/test_sec_html_image_assets.py tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_sec_earnings_repair.py --cov=dayu/fins/downloaders --cov=dayu/fins/pipelines --cov-append --cov-report=term-missing --cov-report=json:workspace/tmp/sec-html-image-assets-coverage.json` | 0；366 passed、3 warnings；95.92s；最终代码受影响完整集合 |
| 最终 HTML 图片 + earnings focused | 0；148 passed；随后新增的收尾 owner 用例及 Unicode 规则由下一两项和最终 366 集合覆盖 |
| 最终 HTML 图片 + downloader focused | 0；179 passed、3 warnings；31.68s |
| discovery 零 begin、图片单独补齐 processed、两版本并发 winner focused | 0；4 passed、120 deselected；3.44s |
| `pyright`（最后代码/测试修改后，全仓） | 0；0 errors、0 warnings、0 informations |
| 真实 opt-in CLI 最终矩阵 | 0；2 passed、0 skipped、3 warnings；139.61s |
| `git diff --check` | 0 |

全仓 9 个 skip 包括默认未启用的两项 real CLI；它们**另用显式 opt-in 实际通过**，不把 broad skip 当网络通过。其它外部资源 opt-in 不属于本次 SEC 图片范围，未扩展为本任务证明。

四个实际修改生产文件的最终单文件覆盖率：

| Owner 文件 | Coverage |
| --- | --- |
| `sec_downloader.py` | 95.03% |
| `sec_download_filing_workflow.py` | 89.86% |
| `sec_pipeline.py` | 89.54% |
| `sec_rebuild_workflow.py` | 89.92% |

曾遇到的测试供数/构造误用、coverage collection failure 与被主动中止的旧测量均记录在 validation JSON；不能将这些尝试当 pass。旧 SC13 mock 的 descriptor 与返回文件名不一致已在对应测试明确修正，没有生产 fallback。META 原真实 HTML/历史 manifest 未修改，三张 logo 使用显式 SYNTHETIC 测试图片 mock；按完整集合核验 snapshot/meta/hash/size/fp，必要 logo 失败保留旧 publication 与 processed。

### 两例真实 CLI 证据

最终运行根：`workspace/tmp/sec-html-image-assets-SQyN9Y/`；此前完整通过的矩阵在 `workspace/tmp/sec-html-image-assets-GX3RAy/`。最终两例各 12 次正式 CLI 子进程，合计 **24 次**；所有 argv/log/stdout/stderr/exit/transport/descriptor 观测单独保存并在 validation JSON 逐项引用、附 hash。

| 样例 | 正式披露日期 | 引用/去重图片 | 发布集合 | 普通升级 |
| --- | --- | --- | --- | --- |
| `0001193125-19-110066` / `d733154d6k.htm` | 2019-04-18 | 17 / 15 | 16 个文件 | v1.2.0 → v1.3.0；document v1 → v2 |
| `0001046179-25-000082` / `a2q25presentatione_6kxwm.htm` | 2025-07-17 | 12 / 12 | 16 个文件（含正式选择的其它 HTML） | v1.2.0 → v1.3.0；document v1 → v2 |

- 日期来自生产 SecDownloader submissions/history 与 `collect_filings_from_table`；没有按猜测或文件名确定日期。
- 新入口固定为本仓库 `.venv/bin/dayu-cli`；installed dist-info 确认 editable root 为本仓库、package 0.1.4；每次子进程独立记录 dayu/sec_pipeline import origin 与 download_version。
- 旧状态由原 commit `git archive` 的生产 `python -m dayu.cli.__main__` 正式建立，baseline cwd/import root 正确；没有手工补文件、改 meta 或改新常量装旧版本。
- fresh 与正式旧版 ordinary upgrade 均成功；27 张去重图片全部正式 GET，snapshot、files[]、仓储 open、URI、size、SHA256、完整 descriptor fingerprint 与版本同源一致。两 HTML 与预检 hash 相同，五张预检抽查图片 hash 也一致。
- 两种成功 base 及故障解除后的 base 再次普通执行，目标 skipped，目标归档 transport 为零；revision/meta/files/hash/首入库/版本及 meta/manifest 字节 hash 保持。
- 每例 exact 图片 GET 注入 404 的 fresh/upgrade 均真实命中；target 在 failed_documents，reason_category=`file_download_failed`，operator log 给出实际图片名及 `provider_http_status`；四次故障命令均 exit 1。fresh 未发布，upgrade 的旧 COMPLETE meta/files/hash/revision/manifest/version 原样保留；解除 fault 后普通 retry 成功并再次幂等。
- hook 只观察原指纹与 transport，fault 只改 exact GET 远端响应；无生产 seam/producer/contract/result 改写。SEC_USER_AGENT 仅在内存复用既有 literal，证据只记布尔值，并实际检查所有最终证据未含该值。
- 原业务 workspace 和原证据目录未读写，未 clear 会话。真实 bases 未执行 processor/LLM，不宣称图片 OCR 或财务数值解析通过。

## Docs decision

已按各 README 职责核对并更新三份：

- Fins README：稳定依赖集合/首 base/地址边界、版本资格、空指纹前置、原子保留与 rebuild 认证边界。
- Tests README：真实 owner/mock 证明范围、META SYNTHETIC 明确供数、opt-in 独立 baseline/transport fault 验证入口及非证明范围。
- 根 README：普通增量补齐、正式日期示例、当前缓存快跳与可选 overwrite、必要图片失败诊断、子目录限制及 rebuild 不能补远端资源。

没有 UI/Service/Host/Engine 分层或装配变化，不改 `dayu/README.md`、其它层 README 或包版本。

## Finding / risk 裁决交接

| 项目 | 本实施证据 / 状态 |
| --- | --- |
| SECIMG-A1 | 完整 META mock/F/hash/size/fp 与 logo 失败保留实际通过；已实施验证，待总控独立 code review |
| SECIMG-A2 | 当前版本空 fp 的基础 GET/发现/HEAD 前置、等价 skip 和失败优先实际通过；已实施验证，待总控独立 code review |
| SECIMG-001 | 三种直接候选、有限 srcset、无 src 发布/补齐/必要失败实际通过；已实施验证，待总控独立 code review |
| SECIMG-002 | 首 base 全矩阵、统一规范 URL、边界/点段/编码/碰撞/子目录失败实际通过；已实施验证，待总控独立 code review |
| SECIMG-003 | 沿总控既有 rejected-with-reason；没有扩展子目录映射 |

| Risk | 分类 / 状态 | Owner / destination |
| --- | --- | --- |
| R1 全部27图及真实补齐/故障验证 | approved S1 实际关闭 | S1 worker/总控；本 JSON 的两真实矩阵与逐图证据 |
| R2 parser/版本门/rebuild/事务/取消/并发/测试迁移 | approved S1 实际关闭，独立 review 尚待总控 | SEC downloader/workflow/rebuild/tests；owner tests、coverage、pyright、validation JSON、双路 code review |
| R3 HEAD 策略/validators/当前快跳不检查远端变化 | assigned to later work unit | SEC transport/workflow 维护者；独立远端重校验/指纹策略需求 |
| R4 子目录、更宽 srcset、CSS/JS/browser、legacy非UTF8能力 | assigned to later work unit | SEC downloader/Fins storage 维护者；有真实样本的独立目录资产地址契约/其它资源解析需求。当前有限契约的安全失败已实测 |
| R5 外站/跨申报/OCR/数值提取 | assigned to later work unit | 后续需求提出方；独立能力需求 |
| R6 200非空响应类型/HEAD与GET之间内容变化 | assigned to later work unit | SEC transport 维护者；独立响应内容校验/validator同响应身份需求 |
| R7 真实 processor/LLM/OCR/processed重算 | assigned to later work unit | Fins processor/分析能力维护者；独立图片读取/OCR验收。processed 重处理标记已由真实 Fs owner 测试覆盖 |

未覆盖项就是 R3–R7 对应的已批准非目标/后续能力；没有新增未分类风险或 scope/owner 阻塞。总控仍需完成双路 code review、裁决和后续 checkpoint/gates；本 worker 不代替总控作 review 或 final closeout 判断。
