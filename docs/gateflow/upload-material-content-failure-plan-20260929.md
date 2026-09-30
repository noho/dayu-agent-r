RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

# UM-O21-F01 + UM-O22-F01：material 内容失败同源传播实施计划

- Gate：plan review → fix；work unit：`UM-O21-F01 + UM-O22-F01`；状态：按第二次 MiMo F1/F2 与控制器最新裁决修订候选 plan，待有效 Kimi/MiMo 双路 re-review，未实施。
- 工作区：`/private/tmp/dayu-upload-content`；分支：`codex/upload-material-content`；核对 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。本计划以已确认的 `docs/gateflow/upload-material-content-failure-goal-20260929.md` 为绑定范围；只写相对仓库路径，主工作区裁决只读。

## 目标、动机和成功信号

1. `UM-O22-F01`：filing 和 material 的原件字节恰为 `b""` 时，在共同的原始字节准入处、Docling 启动前，产生同一个 `FinsUploadFailureError`，其 reason 是现有 `content/empty_input_file`、当前原件的 canonical safe `file_label`、固定文案“文件为空，无法上传”和提示“请提供非空文件后重试”。单文件和多文件都指向实际空文件，material `stored_file_count=0` 且没有 material 文档部分发布。
2. `UM-O21-F01`：material 每个原件转换触发 `DoclingConversionError(CONVERTER_EXECUTION)` 时，在知道 `file_path` 的逐文件边界产生 `content/docling_converter_execution` 与当前原件的 canonical safe `file_label`；保留原异常为 `__cause__` 供 operator 诊断。PDF、DOCX 单文件及“有效文件在前、损坏文件在后”均指向损坏文件；已有 filing 行为保持。
3. SEC 与 CN/HK market workflow 的 failed result、upload failed event、runtime typed summary、direct RESULT、CLI 及 tool 的 awaiting→observation 失败终态只消费同一个 reason；普通/debug 公开输出和 observation 的 kind/code、label、文案、提示与 requested/stored 一致。tool 不创建 durable job，不能要求其 `result_summary.failure` 或 `failure_summary`。仅单独走 `start_upload` 的 durable job 路径验证这两处摘要来自同一个 reason。不得从输入序号、异常字符串、绝对路径、日志或显示层重建标签。

严重性只涉及失败分类、可行动提示和出错文件定位。主工作区只读裁决 `docs/reviews/upload-material-um-o21-oracle-adjudication.md` 记录 F17/F18/F19 已为 content 失败，F19 requested=2/stored=0，却缺 file label；`docs/reviews/upload-material-um-o22-oracle-adjudication.md` 记录 F16/S18 的真实 0 字节 material 被误归 `runtime/unexpected_runtime`。这些是旧 validation commit 的冻结观察，不当作本 HEAD 的测试结果，也不证明公司 meta 零副作用或任意 commit 故障原子性。本 HEAD 直接代码证据如下。

| 边界 | 当前直接事实 | 修复判断 |
| --- | --- | --- |
| `dayu/fins/pipelines/docling_upload_service.py::_build_original_assets` | `read_bytes()` 之后仅在 `source_kind is FILING and raw_data == b""` 构造现有 typed empty failure；material 继续前进 | 去掉 filing 限定，共同读取 owner 对相同字节事实分类一次；保留当前 basename canonicalizer。 |
| `dayu/fins/pipelines/docling_process_converter.py::_validate_conversion_request` | material 空字节会触发 `ValueError("input_bytes must not be empty")` | 这是转换器参数防线，不是上传业务 failure owner；无需改转换器或解析英文异常。 |
| `dayu/fins/pipelines/docling_upload_service.py::_build_pending_assets` | `except DoclingConversionError` 中 material 直接 `raise`，filing 用当前 `file_path.name`、共享 canonicalizer 和 resolver 包装 typed reason | 同一个 catch 对两类 source 都在当前位置构造一次 typed reason；不改变取消路径、转换策略或派生资产名。 |
| `dayu/fins/upload_failure.py::fins_upload_failure_from_exception` | 已有 closed content codes、空文件 factory 与 reason 校验；resolver 未识别 `FinsUploadFailureError`，未识别的异常落 `runtime/unexpected_runtime` | 在任何重新分类之前，遇到 typed error **直接返回 `error.failure` 对象本身**，不复制、不覆盖 label；其它异常映射保持原样。 |
| SEC `run_upload_material_stream`；CN/HK `CnPipeline.upload_material_stream` | 两处 `except Exception` 均调用 resolver，显式传 `file_label=None`，再以返回 reason 的 `message`/`to_json()` 造 failed result 和 event | 当前 catch 确实会吞掉新 typed error 的标签；共享 resolver 增加优先透传后，这两处 catch 无需修改，`None` 仅供尚未归属文件的普通异常使用。用入口测试证明透传，不添加市场特例 catch。filing 独立 typed catch 保持现状。 |
| `dayu/fins/tools/upload_tools.py::_resolve_upload_file_path` | `is_file()` 后用 `stat().st_size <= 0` 把 0 字节文件提前映为无标签的英文 `invalid_argument`；observation 尚未创建，Docling owner 不可达 | 删除文件大小业务重判并修正 docstring；保留 resolve 与存在/普通文件路径结构检查。空文件进入既有 awaiting→observation 失败终态链，由 Docling 读取实际字节并给出同一 typed `content/empty_input_file` reason；tool 不建 job。 |

同源闭环在现有契约内有直接代码支撑，实施时仍须用终态证据核验：`FinsUploadFailureError.failure -> fins_upload_failure_from_exception` 身份透传 `-> failure.to_json()`；`FinsUploadPipelineResult.from_pipeline_json` 用 strict `upload_failure_reason_from_json` 读回；`FinsUploadResultSummary.failure_reason` 持有同一 typed 值；direct `_upload_result_details` 从该值产生 kind/code/file/message/hint 和 requested/stored，失败 `error_message` 来自同一文案。tool 只调用 `prepare_observed_upload`，其 execution context 的 `job_record=None`；返回 `ToolAwaitingOutcome` 后激活并 `poll_observation`，验收 observation 的 FAILED 终态 `result.details`/`error_message`，不读取不存在的 job 摘要；`FinsResultSummary.failure` 当前恒为 `None`，不得冒充 typed reason。另经 `start_upload` 创建的 durable job，`result_summary.failure` 与 `failure_summary` 才从 `failure_reason.to_json()` 双写。`dayu/service/fins_direct.py` 与 CLI direct stream 只接入共享 runtime；tool 删除原有 `st_size` 截胡后仅校验路径结构，不在 tool adapter 复制或重判内容事实。当前 `DoclingUploadService.prepare_upload` 的 `_validate_source_files` 只检验 Path、存在和普通文件，随后 `_build_original_assets` 读取字节；因此去掉 tool 大小检查后，合法 0 字节普通文件可达共同 owner。`dayu/fins/storage` 的 source/blob 仓储只负责材料文档发布，不拥有上传失败文案或文件标签；Docling prepare 的读取、转换完成前不进入 material source 发布 batch。SEC/CN material 在 prepare 前另有 company meta batch，不能称为工作区零写入。

## 契约与实现决定

- **唯一语义 owner**：`DoclingUploadService` 负责“当前原件字节为空”和“当前文件转换失败”的事实与文件身份；`dayu.fins.direct_events.canonicalize_fins_public_file_label` 唯一负责公开安全标签；`dayu.fins.upload_failure` 唯一负责 closed reason、固定文案和 typed 异常解析。市场 workflow 只投影，不重新计算。
- `upload_tools.py` 的 `_resolve_upload_file_path` 仅保留路径解析、存在与普通文件检查，删除 `candidate.stat().st_size <= 0` 及对应英文错误；该处既不读取内容也不产生 typed content reason。文件在结构检查与 owner 读取之间消失或变更时，按实际读取/存储错误处理，不以旧 stat 结果猜测内容。
- `_build_original_assets` 在 `raw_data == b""` 时，无论 source kind，记录 operator 诊断、canonicalize `file_path.name`、抛现有 `FinsUploadFailureError(fins_upload_empty_input_failure(file_label))`。把共享 catch 的 `Filing upload empty input rejected before publication` 改成 filing/material 中立的上传描述，保留必要的 basename 诊断，不把原始本地路径投影到公开文本。同步修正函数和空文件 factory 的中文 docstring，使其描述 filing/material；不改 `read_bytes` 的 I/O 错误类别。
- `_build_pending_assets` 的 `except DoclingConversionError as exc` 不再对 material 原样重抛：取得当前 `file_path.name`，用同一 canonicalizer 得 label，以既有 `fins_upload_failure_from_exception(exc, file_label=label)` 构造 reason，`raise FinsUploadFailureError(reason) from exc`。把共享 catch 的 `Filing upload conversion rejected before publication` 改成 filing/material 中立的上传描述，保留已知文件名的 operator 诊断与原始 cause；公开 reason 不包含路径或原异常文本。同步修正该函数 Raises docstring；不另建日志或 failure owner。
- resolver 首分支识别 `FinsUploadFailureError` 并直接返回 `error.failure`；不增加 code、kind、JSON 字段或兼容读取，不改 `DoclingConversionError` 原有 closed kind 映射。`file_label=None` 不能覆盖 typed reason 自带 label。对普通异常，原有 resolver 行为保持。
- 不修改 `docling_process_converter.py`、market workflow、runtime、Service、CLI、storage 或事件生产代码；tool 产品改动仅限上述路径检查与 docstring。若入口测试发现某处实际丢失 reason，先复查真实 call path；仅允许在其语义 owner 边界修正，不能通过展示 fallback、tool 局部 typed 伪造、loose parsing 或扩展公开 schema 绕过停止条件。

## 实施文件白名单与行为切片

以下为后续 implementation 的**可编辑白名单**，不是本轮改动。测试跟随行为边界，不能用旧“material 原样抛 DoclingConversionError”断言迫使生产代码保留分支。

| 切片 | 允许的产品文件 | 允许的测试文件 | 完成信号 |
| --- | --- | --- | --- |
| S1：共享 owner 产出并穿过 catch | `dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/upload_failure.py` | `tests/fins/test_docling_upload_service.py`、`tests/fins/test_upload_failure.py`、`tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py`；必要的 filing 回归在 `tests/fins/test_sec_pipeline_upload_filing_stream.py` | 空 material 在 converter 和 material source batch 之前失败；第二份空文件指向第二份；material 损坏文件 typed reason 的 code/label/cause 正确且无 source 发布；两处共享 operator log 改为中立上传描述；SEC/CN/HK 各入口 failed event/result exact reason，stored=0；filing 已有 empty/converter 回归通过。 |
| S2：公开、持久结果与真实入口验收 | `dayu/fins/tools/upload_tools.py`（仅删 `st_size` 内容重判、修 docstring） | `tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/cli/test_fins_commands.py`；仅在确有新稳定文档事实时检查下述 README | tool 对空 filing/material 保留路径结构检查后返回 `ToolAwaitingOutcome`，激活后 `poll_observation` 得 FAILED，`result.details`/`error_message` 与同字节 direct/CLI typed reason 对齐且无 durable job；另由 `start_upload` 的真实 job 路径断言 `result_summary.failure` 与 `failure_summary` 双写同一 JSON；真实 CLI 普通/debug 与 tool 新隔离 lineage 通过。 |

S1 和 S2 按可观察行为而非模块分割；若 S1 入口断言已覆盖 S2 所需投影，可合并一次实现和一次 review，不为固定切片数制造重复测试。两项修复共享两个 owner 与相同传播路径，所以不按 O21/O22 再拆两个实现。S2 不授权改下游产品代码。若集成证明下游真有丢失，先停止并更新 plan/review 裁决。

## 测试、验证和证据

本隔离工作区预检时 `.venv` 不存在。实施验证前须在此工作区 provision Python 3.11 `.venv`，记录 provision 命令和依赖锁定来源；不可借主工作区可执行文件或依赖。激活后先断言 `sys.version_info[:2] == (3, 11)`、`Path(sys.prefix).resolve() == Path.cwd().joinpath('.venv').resolve()`、`Path(dayu.__file__).resolve() == Path.cwd().joinpath('dayu/__init__.py').resolve()`，记录 `sys.executable`、`dayu.__file__`、pytest/pyright/pytest-cov 版本与 `command -v dayu-cli`，并确认 CLI 是本 `.venv/bin/dayu-cli`。身份或依赖不符先停止验证并修环境，不借其它 worktree 的结果充数。

owner tests 必须断言 `FinsUploadFailureError.failure` exact kind/code/message/retry_hint/file_label，resolver 对 typed error 返回**对象身份相同**的 reason，直接构造的非法 label 仍被拒绝；material converter 错误的 `__cause__` 是原始 `DoclingConversionError`，其它 closed Docling kind 与 generic error 不漂移。安全文件名用超长或需隐藏 basename 验证固定隐藏标签、长度上界与无绝对路径。更新 `test_prepare_material_nth_conversion_failure_discards_partial_work` 的旧原样抛异常断言；点名迁移 `test_sec_pipeline_upload_material_stream.py::test_upload_material_nth_conversion_failure_is_content_terminal_without_source_publication` 中 `file_label: None` 旧断言为当前损坏原件的 safe label。多文件空字节前置读取时应断言无 converter 调用、无 material source batch/manifest/blob，且不误称 company meta 未写入。SEC/CN/HK 测试对 market event `payload.result.failure`、`payload.error`、`stored_file_count` 与 source 仓储状态断言；至少一个测试禁止 generic mapper 对 typed error 重分类或直接检查 resolver 身份透传。两处共享 Docling catch 的 operator log 可加 caplog 断言，确认 material/filing 诊断均不误称 Filing，且公开 reason 不含原始路径；不要固化旧日志文字。迁移 `test_upload_tool_empty_file_returns_failed_outcome_before_observation_start`：覆盖 filing/material 空文件，断言 tool 先给 `ToolAwaitingOutcome`，激活并 `poll_observation` 后快照为 FAILED；从 `result.details` 读取 failure kind/code/file/failure message/retry hint、requested/stored，并核对 `result.error_message` 为同一文案。以同字节 direct/CLI 失败 reason 的 `to_json()` 五字段逐字段对照，不从 observation 的 `FinsResultSummary.failure` 推断 typed reason；保持现有无 job record 断言，不要求 tool 的 `result_summary.failure`/`failure_summary`。不得保留旧 `ToolFailedOutcome/invalid_argument` 断言。缺失文件与目录仍在 observation 前按路径结构失败。另在 `tests/fins/test_fins_ingestion_runtime.py` 用 `start_upload` 加真实 production runner 的空文件/转换失败 job 用例，读取 durable record，断言 `result_summary.failure` 与 `failure_summary` 都等于 owner 的 exact `to_json()`；不得把这一双写要求搬到 tool 路径。

受影响测试建议命令（实施后执行，失败必须解释和修复）：

```bash
source .venv/bin/activate
python -c 'import pathlib, sys, dayu; root=pathlib.Path.cwd().resolve(); assert sys.version_info[:2] == (3, 11); assert pathlib.Path(sys.prefix).resolve() == (root / ".venv").resolve(); assert pathlib.Path(dayu.__file__).resolve() == root / "dayu/__init__.py"; print(sys.executable, dayu.__file__)'
python -m pytest --version
python -m pyright --version
python -m pip show pytest-cov
command -v dayu-cli
test "$(command -v dayu-cli)" = "$PWD/.venv/bin/dayu-cli"
python -m pytest tests/fins/test_upload_failure.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py -q
python -m pyright dayu/ tests/ utils/
```

单文件 coverage 分别取报告，不以合并覆盖率掩盖目标文件；每条在同一虚拟环境、对应完整行为测试集合下执行，目标为各修改产品文件至少 80%，不足时补 owner 级有意义断言、再测，不降低门槛：

```bash
python -m pytest tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py -q --cov=dayu.fins.pipelines.docling_upload_service --cov-report=term-missing
python -m pytest tests/fins/test_upload_failure.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q --cov=dayu.fins.upload_failure --cov-report=term-missing
python -m pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q --cov=dayu.fins.tools.upload_tools --cov-report=term-missing
```

真实 CLI 证据使用新、独立、fresh 的 run_dir 和每个 case 独立 `--base`；用 Python `subprocess.run` 以 argv 数组启动本工作区 `.venv/bin/dayu-cli`，cwd 为本 HEAD 仓库，stdin 为 `DEVNULL`，设置有界 timeout，记录实际 argv、输入字节 SHA-256、HEAD、venv/`dayu.__file__` 身份、环境差异、stdout/stderr、exit/timeout、进程检查、工作区前后文件清单及关键 source/meta/manifest JSON。证据脚本若需新增只能放 `utils/`（分析辅助）或 `workspace/tmp/`（临时）；不写入冻结 oracle 根目录。以 `upload_material --ticker AAPL --action create --forms MATERIAL_OTHER --material-name Deck --files ... --company-name 'Apple Inc.' --base <fresh>` 为基线，分别跑 0 字节 `empty.txt`、有效文件+空文件、9 字节损坏 PDF、18 字节损坏 DOCX、有效 `probe.txt`+损坏 `corrupt.docx`；每 case 普通和 `--debug --log-file <case-log>` 各一份 fresh workspace。有效对照必须先在同版本单文件验证可转换；保留输入 exact bytes，不以假 converter 冒充真实 CLI。核对 exit=1、无超时/残留子进程、requested=1 或 2/stored=0、screen/RESULT 的相同 safe label、kind/code/文案/提示，debug 公开文本不泄露路径或异常，operator log 有必要诊断且对 material 不误称 Filing；检查 material original、Docling JSON、source meta、material manifest 均未发布，同时如实记录可能已提交的 company identity/meta。查询 CLI lineage 的 durable/job/SQLite/EventLog/Trace/Memory：存在则核对同一 failure；不存在明确标为 queried-but-absent，不把 CLI 查询结果冒充 `start_upload` 双写验收。

另以同一锁定 venv 和 production tool 装配做真实 tool 入口验证：fresh workspace 中分别给 0 字节 material、有效文件+空文件及损坏文件，记录原始 tool args/输入 SHA-256、`ToolAwaitingOutcome`、observation 激活与 `poll_observation` FAILED 终态；从终态 `result.details`/`error_message` 核对 kind/code/safe file label/文案/提示及 requested/stored，按 owner `to_json()` 五字段与对应同字节 direct/CLI reason 对照；filing 空文件另抽一例验证共享空字节 owner。工具只启动 awaiting，不能把初始 outcome 当 terminal 失败；确认 tool 无 durable job record，查询其它 durable/job/SQLite/EventLog/Trace/Memory 时逐项记 queried-but-absent，不要求 `result_summary.failure`/`failure_summary`。若等待超时、异常逃逸或终态缺 typed reason，记录真实路径并按停止条件处理。tool 测试不得用 fake runner 替代这条入口证据。另在独立 fresh workspace 以 `start_upload` 的 production runner 验证真实 durable job 失败，读取 job record 两处摘要与同一 owner reason 的 exact JSON；不将其归入 tool/CLI lineage。新 CLI/tool/start_upload lineage 与冻结 F16–F19/S18 并列，不能覆盖旧证据。CN/HK 用市场入口测试确保复用 owner，若有真实 CLI 市场基线则补独立抽样。

## README 决定、依赖、残余风险与停止条件

- 本计划只改此 plan，不改 README。实施后因 `dayu/fins/` 与 `tests/` 变化，检查 `dayu/fins/README.md` 的 developer public failure contract 章节及 `tests/README.md` 的现有测试层级/命令；仅当稳定已实现边界或测试层级实际变化才更新。用户可见错误定位变化需检查根 `README.md` 的用户排障职责，适合时补充用户可行动提示；不写内部 code 流水账。`dayu/README.md` 的跨包架构未变化，预计无需改；若证据显示边界变化则按其 Agent 更新约束再决定。编辑任何 README 前重新读目标文件约束。
- O04/O23 同时计划修改 `DoclingUploadService` 的 material selection/原件与派生资产身份规划。集成到 PR #197 前串行比较同文件最终 diff：本项失败标签只能从当前 `file_path.name` 的 canonicalizer 得到，不得把 planned storage asset name、stem、派生名或列表位置替代原件身份；空字节检查仍在统一 original bytes 准入处，且 O04/O23 的预转换身份校验和本项 content failure 的优先顺序要按已接受 goal 核对。对共享文件的合并、冲突与回归做单独复审，不在本项设计资产命名。
- 残余：公司 meta 提前持久化属 UM-O34；Docling 抽取质量、格式 capability、material 资产名规划属其它 work unit；任意 storage commit 中途故障不由 F16–F19/S18 证明。当前无新增 schema、分类或 public interface。
- **停止**：本轮完成候选 plan 后停止，等待有效 Kimi/MiMo 双路 re-review。实施阶段若 HEAD 不再为 `8d8d494fbbce0052372fb1b42097c9f7222cfa28` 且未经明确 rebase/集成裁决、目标 plan 与已有 artifact 冲突、去掉 tool `st_size` 后存在合法空文件仍无法到达 Docling 原件字节 owner 的直接代码/测试反例、typed reason 无法沿实际 market catch 或 tool awaiting→observation FAILED 终态的 `result.details`/`error_message` 保持同源，或必须改公开 schema/既有 content 分类，立即记录直接证据并停止；不得给 tool 建 job、在 tool 局部伪造 typed reason、从 `FinsResultSummary.failure` 反推失败或加下游 fallback。`start_upload` 的 durable 双写单独验收，不以 tool 无 job 误触停止条件。

## 后续完成报告格式

逐项报告 O21/O22 的 owner 改动、文件清单、受影响测试、pyright、每个产品文件单文件 coverage 数值、普通/debug 真实 CLI 新 run_dir 与 canary、tool observation 终态同源对照、独立 `start_upload` durable 双写、README 决定、残余风险和 O04/O23 集成状态。下一 gate 是 Kimi/MiMo 有效双路独立 plan re-review；本计划不实施、不提交、不发 PR 或外部评论。
