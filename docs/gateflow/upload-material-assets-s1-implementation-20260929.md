RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-c8c8a0f6

# UM-O04-F01 + UM-O23-F01 实施记录

基线：`1453a659a79d4c9a93838412dfdecfa7feeddf98`，分支 `codex/upload-material-assets`。本次只实施 accepted plan 的单一切片；未提交、推送、创建 PR、合并或进入代码审查 gate。实施前工作区干净，实施后修改均为 plan 指定生产/测试触点、按职责触发的 README 和本记录。

## 动机与 owner 裁决

直接代码证据与 accepted plan 一致：旧 material 原件以完整 basename 保存，Docling 名却以 stem 加 `_docling.json` 派生，同 stem 不同后缀在转换后才冲突；101 个 material 文件曾依赖通用 runtime 摘要上限报裸错误。根因是转换前没有唯一的整批资产身份规划。修复放在新的 `dayu/fins/upload_asset_plan.py`，其只从 storage 纯文件名契约取得 document 控制名与保守碰撞键；格式角色仍归 `upload_format_contract.py`。file existence/regular-file 的跨入口 typed 统一、O25 选主与 O34 公司事实不属于本切片。

## 精确改动

- 新增 `dayu/fins/storage/asset_filename_contract.py`：从 storage 原常量生成唯一 `DOCUMENT_SOURCE_CONTROL_FILENAMES`，提供原样单组件校验、NFC/casefold/NFC 比较与控制名碰撞判定。`storage/__init__.py` 导出该集合；`_fs_source_integrity.py` 两个 walker 和 `_fs_maintenance_core.py` maintenance walker 消费同一 exact 集合，未改变各自拒绝/跳过规则。
- 新增 `dayu/fins/upload_asset_plan.py`：material 1..100、规范路径、重复原件/派生名及控制名、UTF-8 255 字节上限的转换前规划；完整 basename 追加 `_docling.json`；filing 的 `fins-upload-asset-v1` + NUL + 规范路径 SHA-256 原件身份原样迁入，并由同一函数派生 Docling 名。计划保序持有原件、转换项和 filing primary 名。
- 新增 `dayu/fins/upload_usage_contract.py`：迁入原 usage enum、typed fact、error、唯一文案工厂；planner reason 统一投影为 usage code/message/hint。`upload_failure.py` 使用同一文案和封闭 public code；既有 `create/update` 文案保持逐字一致，public 文本校验仅接受该固定动作枚举消息中的斜杠。
- `ingestion_runtime.py` 新增 `ValidatedFinsUploadMaterialRequest` 与唯一 admission；CLI、Service、tool、observation/runtime、真实 `ProductionFinsUploadRunner`、SEC/CN/HK 的 raw façade 与 validated 执行入口传递同一 handoff。material 101 在 job/observation/首事件之前拒绝，摘要只读取已验证数量；filing 路径规范与 exact 身份复用资产 owner helper，filing 上限及选择规则不变。
- `docling_upload_service.py` 的原件、转换结果、primary 和指纹沿同一 `UploadAssetPlan` 消费；material 同 stem 不同后缀拥有不同派生名。未更改 storage 发布/完整性契约、Docling converter、O25 primary 选择、O12/O13/O14/O15/O18 状态或 O34 company meta 时序。
- CLI 保留逐路径 `exists()`/`is_file()` 预检的英文模板和完整解析路径，并在 Service factory 之前建立 material handoff。tool schema 的 `files.maxItems` 从 material 规划常量派生。
- 新增三个 owner 测试文件，并迁移实际调用处的测试；补充 SEC/CN/HK 101 首事件前拒绝、storage 三 walker、受控 100 次 converter 调度、真实 CLI 缺失文件/目录预检测试。按 README 职责更新根 `README.md`、`dayu/fins/README.md`、`dayu/service/README.md`、`tests/README.md`；检查了 `dayu/README.md`，跨包架构关系未变，未修改。

变更清单：`git diff --numstat` 的 tracked 路径为 `README.md`、`dayu/cli/commands/fins.py`、`dayu/fins/README.md`、`dayu/fins/ingestion/observation_handle.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/{_filing_upload_fresh_validation,cn_pipeline,docling_upload_service,filing_upload_publication,sec_pipeline,sec_upload_workflow}.py`、`dayu/fins/service_runtime.py`、`dayu/fins/storage/{__init__,_fs_maintenance_core,_fs_source_integrity}.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/upload_failure.py`、`dayu/service/{README,fins_direct}.py`、`tests/README.md`、`tests/cli/test_fins_commands.py`、`tests/fins/{test_cn_pipeline,test_docling_upload_service,test_docling_upload_service_integration,test_fins_ingestion_runtime,test_fins_ingestion_tools,test_fins_service_runtime,test_fins_storage_atomicity,test_sec_pipeline_upload_filing_stream,test_sec_pipeline_upload_material_stream}.py`、`tests/service/{test_fins_direct,test_fins_wait_adapter}.py`。tracked diff：32 文件，958 行新增、1294 行删除。另有 6 个未跟踪新文件：上述三个生产 owner 和 `tests/fins/{test_storage_asset_filename_contract,test_upload_asset_plan,test_upload_usage_contract}.py`，分别 53/294/239/50/211/202 行。本记录为第 7 个新文件。`git diff --check` exit 0；未 stage。

实施结束时 tracked `git diff --numstat` 原样如下；新文件尚未 stage，故不出现在此命令中：

```text
2	0	README.md
75	41	dayu/cli/commands/fins.py
2	2	dayu/fins/README.md
3	3	dayu/fins/ingestion/observation_handle.py
119	248	dayu/fins/ingestion_runtime.py
1	1	dayu/fins/pipelines/_filing_upload_fresh_validation.py
89	92	dayu/fins/pipelines/cn_pipeline.py
61	121	dayu/fins/pipelines/docling_upload_service.py
1	2	dayu/fins/pipelines/filing_upload_publication.py
71	104	dayu/fins/pipelines/sec_pipeline.py
24	40	dayu/fins/pipelines/sec_upload_workflow.py
19	73	dayu/fins/service_runtime.py
2	0	dayu/fins/storage/__init__.py
2	5	dayu/fins/storage/_fs_maintenance_core.py
3	3	dayu/fins/storage/_fs_source_integrity.py
5	1	dayu/fins/tools/upload_tools.py
33	2	dayu/fins/upload_failure.py
1	1	dayu/service/README.md
14	57	dayu/service/fins_direct.py
2	0	tests/README.md
89	51	tests/cli/test_fins_commands.py
53	77	tests/fins/test_cn_pipeline.py
121	63	tests/fins/test_docling_upload_service.py
3	1	tests/fins/test_docling_upload_service_integration.py
26	156	tests/fins/test_fins_ingestion_runtime.py
14	23	tests/fins/test_fins_ingestion_tools.py
7	5	tests/fins/test_fins_service_runtime.py
53	0	tests/fins/test_fins_storage_atomicity.py
6	6	tests/fins/test_sec_pipeline_upload_filing_stream.py
47	93	tests/fins/test_sec_pipeline_upload_material_stream.py
7	20	tests/service/test_fins_direct.py
3	3	tests/service/test_fins_wait_adapter.py
```

## 验证命令与结果

以下命令均在仓库根目录运行，先 `source .venv/bin/activate`：

| 命令 | exit | 结果 |
| --- | ---: | --- |
| accepted plan 中的 17 文件 `python -m pytest ... --cov=dayu.fins --cov=dayu.service.fins_direct --cov=dayu.cli.commands.fins --cov-report=term-missing` | 0 | 1188 passed，1 skipped；原始输出 `/private/tmp/dayu-upload-full-pytest.log`。 |
| `python -m pytest tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py --cov=dayu.fins.pipelines.sec_pipeline --cov=dayu.fins.pipelines.cn_pipeline --cov-append --cov-report=` | 0 | 242 passed；补足修改过的两支大 pipeline 文件的全文件覆盖率。 |
| accepted plan 的 17 文件加上述 4 文件的最终 `python -m pytest ... --cov=dayu.fins --cov=dayu.service.fins_direct --cov=dayu.cli.commands.fins --cov-report=term-missing` | 0 | **1433 passed，1 skipped**；原始输出 `/private/tmp/dayu-upload-final-pytest.log`。 |
| `python -m pyright` | 0 | 0 errors、0 warnings、0 informations；`/private/tmp/dayu-upload-final-pyright.log`。 |
| `python -c 'from dayu.fins.storage import DOCUMENT_SOURCE_CONTROL_FILENAMES; import dayu.fins.storage._fs_source_integrity; import dayu.fins.storage._fs_maintenance_core; import dayu.fins.upload_usage_contract; import dayu.fins.ingestion_runtime; import dayu.fins.upload_failure; import dayu.fins.pipelines.sec_pipeline; import dayu.fins.pipelines.cn_pipeline; import dayu.cli.commands.fins; assert DOCUMENT_SOURCE_CONTROL_FILENAMES == frozenset({"meta.json", ".identity.json"})'` | 0 | 真实 Python 导入，无模块环。 |
| `git diff --check` | 0 | 无空白错误。 |

最终 19 个改动生产文件逐文件执行 `python -m coverage report --include="$file" --fail-under=80`，全部 exit 0，原始逐项输出 `/private/tmp/dayu-upload-final-file-coverage.log`：

| 文件 | 覆盖率 | 文件 | 覆盖率 |
| --- | ---: | --- | ---: |
| `dayu/fins/upload_asset_plan.py` | 91% | `dayu/fins/upload_usage_contract.py` | 94% |
| `dayu/fins/storage/asset_filename_contract.py` | 100% | `dayu/fins/storage/__init__.py` | 100% |
| `dayu/fins/storage/_fs_source_integrity.py` | 86% | `dayu/fins/storage/_fs_maintenance_core.py` | 91% |
| `dayu/fins/ingestion_runtime.py` | 91% | `dayu/fins/ingestion/observation_handle.py` | 94% |
| `dayu/fins/upload_failure.py` | 96% | `dayu/fins/tools/upload_tools.py` | 93% |
| `dayu/cli/commands/fins.py` | 86% | `dayu/service/fins_direct.py` | 90% |
| `dayu/fins/service_runtime.py` | 92% | `dayu/fins/pipelines/docling_upload_service.py` | 90% |
| `dayu/fins/pipelines/sec_pipeline.py` | 86% | `dayu/fins/pipelines/sec_upload_workflow.py` | 94% |
| `dayu/fins/pipelines/cn_pipeline.py` | 93% | `dayu/fins/pipelines/_filing_upload_fresh_validation.py` | 100% |
| `dayu/fins/pipelines/filing_upload_publication.py` | 87% |  |  |

### 失败命令与恢复（原样披露）

- 制作中 `python -m pyright > /private/tmp/dayu-upload-pyright.log 2>&1` exit 1，203 errors；第二次 `python -m pyright > /private/tmp/dayu-upload-pyright-2.log 2>&1` exit 1，49 errors；签名与测试迁移完成后 `python -m pyright > /private/tmp/dayu-upload-pyright-3.log 2>&1` exit 0，最终又运行上述 pyright exit 0。前两份原始输出保留。
- 制作中的 pytest 矩阵 `/private/tmp/dayu-upload-pytest-1.log` 为 20 failed/805 passed/1 skipped，`/private/tmp/dayu-upload-pytest-2.log` 为 4 failed/674 passed；当时仍有旧 scalar 调用与 fixture 断言。迁移后同组 `/private/tmp/dayu-upload-pytest-3.log` 为 678 passed。前两次完整 shell argv 未在日志中保存，不能伪称可逐字复原；失败原始输出未覆盖。
- `python -m pytest tests/fins/test_upload_usage_contract.py tests/cli/test_fins_commands.py -q` exit 1，1 failed/158 passed：既有 `create/update` usage 文案进入 public failure 时被路径字符校验拒绝。保留既有精确文案并将唯一固定枚举消息列为安全例外后，`python -m pytest tests/fins/test_upload_usage_contract.py tests/fins/test_upload_failure.py tests/cli/test_fins_commands.py -q` exit 0，175 passed。
- 新 CLI 小样本第一次未带 `--forms`，exit 1，`material 上传必须提供 form_type 与 material_name`；第二次带 `--forms 10-K` 但未带 `--company-name`，exit 1、`unexpected_runtime`，尚未启动 converter。第一次的证据 JSON 被第二次同路径执行覆盖，保留的 `/private/tmp/dayu-upload-real-cli-20260929/small/evidence.json` 是第二次完整 argv 与输出。随后用原样命令 `python -m dayu.cli upload_material --base /private/tmp/dayu-upload-real-cli-20260929/small_debug/workspace --debug --log-file /private/tmp/dayu-upload-real-cli-20260929/small_debug/cli.log --ticker AAPL --action create --forms 10-K --material-name 'Investor Day' --files /private/tmp/dayu-upload-real-cli-20260929/small_debug/input/deck.txt /private/tmp/dayu-upload-real-cli-20260929/small_debug/input/deck.md` 重现第二次 exit 1。补齐现有业务必填信息并在全新隔离根重试成功；没有改变 O34 公司事实规则。
- 首次真实 CLI 100 侧的 inline Python `subprocess.run(argv, timeout=180)` 超时，harness 记 exit 124、180.01 秒；`/private/tmp/dayu-upload-real-cli-20260929/hundred/evidence.json` 保存精确展开 argv、stdout/stderr、前后文件树。它仅证明通过数量准入及进入上传流程，不用作 converter 启动或 100 次真实调用的证据。随后另起隔离根，加 `--debug --log-file`，在真实 Docling `child_started` 日志出现后发送 SIGINT，CLI exit 130，子进程 `terminate_completed`、`handle_close_completed`、`temp_cleanup_completed`；证据见 `/private/tmp/dayu-upload-real-cli-20260929/hundred_observe/evidence.json` 和 `cli.log`。
- 探索性 `rg -n '_validate_upload_file_count|FinsUploadMaterialFiles|upload_context_request_progress_payload' dayu/fins/ingestion_runtime.py dayu/fins/docling_upload_service.py dayu/fins/pipelines/sec_pipeline.py dayu/fins/pipelines/cn_pipeline.py dayu/service/fins_direct.py` exit 2，原因是 `docling_upload_service.py` 实际位于 `dayu/fins/pipelines/`；随后按真实路径检查。探索性 `python -c 'from dayu.fins.upload_format_contract import FINS_UPLOAD_FORMAT_CAPABILITY; print(sorted(FINS_UPLOAD_FORMAT_CAPABILITY.converter_capability.supported_extensions))'` exit 1，属性不存在；改用 `accepts_primary()` 确认 `.txt`/`.md` 可转换。`ps -ww -o pid,ppid,etime,comm -ax | rg 'dayu.cli|python -|docling'` 因 sandbox 的 `operation not permitted` 未取得全局进程清单。

## 真实隔离 CLI、仓储与环境身份

真实命令经本 checkout 的 `.venv/bin/python -m dayu.cli` 调用；每次 `argv` 全量、cwd、stdout、stderr、exit、耗时、前后树分别保存在以下 JSON，不用受控 converter 冒充真实 converter：

- `/private/tmp/dayu-upload-real-cli-20260929/hundred_one/evidence.json`：101 个存在的普通 `.txt`，exit 2，stderr 精确为 `dayu-cli upload_material: --files 数量不能超过 100 个`，stdout 空，前后 workspace 树均空，真实 converter 启动 0、source 发布 0。
- `/private/tmp/dayu-upload-real-cli-20260929/hundred_observe/evidence.json`：100 个存在的普通 `.txt`，通过数量准入并记录 **1 次真实 Docling child_started**；主动 SIGINT 后 exit 130，source original/derived/meta/manifest 均未发布。`cli.log` 给出同一 child 的 terminate、close、temp cleanup；PID 53404 后续 `os.kill(pid, 0)` 返回 `ProcessLookupError`。受控测试 `test_material_hundred_inputs_schedule_hundred_controlled_converter_calls` 精确记录 100 个不同 basename 的 100 次调度；不宣称真实 CLI 完成 100 次 converter 调用。
- `/private/tmp/dayu-upload-real-cli-20260929/small_final/evidence.json`：真实 `.txt` + `.md` 同 stem，exit 0，6.903 秒，真实日志 `child_started` 2 次，终态 `requested_files=2`、`stored_files=2`。仓储中发布 `deck.txt`、`deck.md`、`deck.txt_docling.json`、`deck.md_docling.json`，document meta 和 material manifest 同指一个 fingerprint；仓储协议 `get_primary_source()` 读回 970 字节，`primary_document=deck.txt_docling.json`。隔离 workspace 无 SQLite 文件，CLI 未创建 legacy job DB。
- `/private/tmp/dayu-upload-real-cli-20260929/missing/evidence.json`：不存在路径与目录两例均 exit 2，stdout 空，分别保持原 CLI 英文模板与解析后完整路径，前后 workspace 树均空。

Python 为本 checkout `.venv/bin/python` 3.11.15，`dayu.__file__` 为本 checkout `dayu/__init__.py`。第三方依赖并非独立安装：本 checkout `.venv/lib/python3.11/site-packages/dayu_shared_dependencies.pth` 指向 `/Users/leo/workspace/dayu-agent-r/.venv/lib/python3.11/site-packages`。该环境身份偏差不影响上述本 checkout 代码导入事实，但不能据此宣称独立依赖安装已验证。

## 残余边界

保守 NFC/casefold/NFC 键可能多拒，不能证明覆盖所有平台 alias；255 字节是本卷当前 `NAME_MAX` 边界。admission 后外部改名仍由 storage 完整性防线处理。material 指纹只由原件的 `name`、`sha256`、`size`、`source` 描述符计算（`docling_upload_service.py` 的 `_build_upload_source_fingerprint` material 分支），派生名不参与；同内容同原件名重传仍按相同指纹走既有 identical-skip。规范化路径或末组件 symlink resolve 若改变原件名，才可能改变指纹。filing identity/指纹保持。当前 material 首项作为 primary 的既有规则没有提升为新承诺，O25 将另行裁决。跨入口单文件不存在/非普通文件的 typed 统一留给独立 work unit。material company meta 早于 source batch 的 O34 事实未改：100 侧主动取消后可见 company meta，但无 material source。首次 100 侧硬 timeout 在系统临时目录留下 `dayu-docling-5_0qp019` 临时目录，其中 `input.bin` 内容是本次生成的 `Investor day part 84.`；未将其当作发布结果，也未清理其它历史同前缀目录。全局残留进程清单因 sandbox 禁止 `ps` 未取得，已对可定位的补验 child PID 核验退出。
