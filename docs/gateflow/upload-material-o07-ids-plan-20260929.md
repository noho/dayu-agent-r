# UM-O07-F01/F02 + UM-O08：material 身份公开输入 plan

- Gate：plan；work unit：`UM-O07-F01/F02 + UM-O08`；依据：`upload-material-o07-ids-goal-20260929.md`（goal confirmation pass）、UM-O07 与 UM-O08 用户裁决。
- 基线：分支 `codex/upload-material-ids`；本计划仅新增本文件。下一入口是 plan review；本文件不表示实施或验证完成。

## 目标、判断和边界

目标是把 material `internal_document_id` 从全部公开输入链移除，只保留身份 owner 生成并持久化/输出的同名字段；公开 `document_id` 是稳定身份的一致性断言。省略时生成、匹配时通过，不匹配或显式空值在身份 owner 或直接上游输入边界给出字段级 typed usage；完整 seed 的显式空值和 mismatch 均须在 `upload.started` 前拒绝，且不创建上传 job/observation 或发布业务数据。成功时事件、result、meta、manifest 的 ID 同源。CLI 空值保留 O08 已接受的 exit 2 和 `--document-id must not contain empty item`。

动机成立：`build_material_ids` 在 `dayu/fins/pipelines/docling_upload_service.py:1820-1856` 返回两个相同 ID；同文件 `validate_material_upload_ids:1860-1889` 仍接受两个外部断言，并用 `document_id or ""` 把空值折叠为未提供。`dayu/fins/ingestion_runtime.py:4714-4746` 的 material 启动校验只调用 `_normalize_upload_request`；`_produce_direct_upload:4521-4532` 和 `_run_upload_job:5005-5015` 都先发 `upload.started`，后调用 runner。SEC/CN workflow 虽在自己的 started 事件前调用身份函数（`sec_upload_workflow.py:475-502`、`cn_pipeline.py:1091-1118`），却晚于 runtime started。CLI、Service、request、tool schema 仍有公开内部 ID（见下表）。这解释了错误分类与时序，不以冻结 CLI 观察代替当前代码根因。

停止条件检查：**完整 seed 时可在 started 前验证，但 O05 是实施硬依赖**。`ingestion_runtime.py:121-127` 已从 `docling_upload_service` 导入 filing 身份函数，增加 material 身份函数不会产生新的反向依赖；`FinsIngestionRuntime.upload`、`prepare_observed_upload`、`start_upload` 分别在事件流、observation、job 创建前调用 `_validate_runtime_upload_request`（`3672`、`3869`、`4686`）。让该入口调用同一个 material 身份 owner 即可前移一致性断言。实施入口必须先核对 UM-O05-F01 的 `form_type`/`material_name` 前置 typed 必填校验已合入、三种启动模式均在 started 前拒绝缺失或空白值；未满足即不进入 O07 实施，也不加入临时 `is not None`/非空 seed 门控。O05 owner 先裁定缺 seed 与空 `document_id` 同时存在时的错误优先级；O07 只对 O05 放行的完整 seed 无条件调用身份 owner，显式空 ID 与 mismatch 由同一 owner/直接上游在 started 前判定。此处不发明 O05 的错误规则。

不改变 SHA-1 种子与 ID 格式、不引入外部来源 ID、不改变 filing 身份或仓储 schema、不删除结果/事件/meta/manifest 中的 `internal_document_id`，不顺手实现 O05/O06/O09/O10/O17 的字段规则。没有旧参数 alias、wrapper、读取兼容或下游错误文本解析。

## Owner、契约与精确修改范围

| 文件 | owner 与计划改动 |
| --- | --- |
| `dayu/fins/pipelines/docling_upload_service.py` | material 身份真源。保留 `build_material_ids` 的摘要规则；将 `validate_material_upload_ids` 改为只接受可选公开 `document_id` 和 owner 生成的稳定 ID 对，不再接受公开内部 ID。以 `None` 区分省略与显式空/纯空白；定义 `MaterialDocumentIdValidationError(ValueError)`，携带 closed `MaterialDocumentIdErrorReason.EMPTY` / `MISMATCH`，不以文案判断原因；返回稳定 `(document_id, internal_document_id)`。SEC/CN/runtime 只调用该函数，不各自重新判断匹配。 |
| `dayu/fins/ingestion_runtime.py` | 在 O05 已合入的 material 前置必填校验之后，`_validate_runtime_upload_request` 无条件调用 `build_material_ids` 和上述断言；将 owner 原因精确投影为 `FinsUploadUsageError` 的 `FinsUploadUsageCode.MATERIAL_DOCUMENT_ID_EMPTY` / `MATERIAL_DOCUMENT_ID_MISMATCH` 及通道中立有界消息（分别为 `document_id 不能为空`、`document_id 与材料稳定文档 ID 不一致；请省略或填写系统生成的 ID`）。经验证的 request 用 `replace(..., document_id=stable_id)` 向 event/job/runner 传同一身份；`_upload_request_document_id` 和 request summary 读取该规范请求。删除 material request 的公开 `internal_document_id` 字段及 request summary 中该输入字段，不动 result summary 的该字段。 |
| `dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/fins/pipelines/sec_pipeline.py` | 移除 material `upload_material` / `upload_material_stream` / workflow 的内部 ID 输入形参和透传；SEC/CN 仍由相同 builder/validator 生成两 ID，并将 owner 的稳定内部 ID 投影到事件、结果、仓储调用。filing 路径不改。 |
| `dayu/fins/service_runtime.py`、`dayu/service/fins_direct.py` | material runner 与 Service request 构造不再接收或转发内部 ID；保留 `result.internal_document_id` 到最终摘要的映射。 |
| `dayu/fins/tools/upload_tools.py` | 删除 LLM schema 的 `internal_document_id` property 和 material request 解析分支；把 `document_id` 描述改成“可选稳定材料文档 ID，一致性核对，不覆盖系统生成 ID”，并说明留空省略、显式空非法。schema 仍 `additional_properties=False`；工具参数解析以同一 schema property 集拒绝未知顶层字段，使旧内部 ID 不能绕过 schema 静默进入 callable。 |
| `dayu/cli/arg_parsing.py`、`dayu/cli/commands/fins.py` | 删除 material `--internal-document-id` 注册、`ParsedCliArgs`/namespace 中仅供此命令的字段及 Service 透传；保留现有 `_single_document_id` 显式空值拒绝。旧参数空/非空由 argparse 当未知参数处理。 |

不改 `dayu/fins/domain/document_models.py`、`dayu/fins/storage/`、read tools、filing request/result 字段。上表之外若发现生产输入链的同名 material 入口，先证明它是公开输入而非持久化/输出，再在本分片中同步移除；若 owner 不明则停止，不做局部 shim。

typed 错误与时序：owner 的空值/不匹配异常只表达身份原因，不依赖 CLI 文本。runtime 的 closed usage code/message 是跨通道公开错误投影真源，使用 `document_id` 字段名而非 CLI flag；CLI 已有 `FinsUploadUsageError -> exit 2` 路径（`dayu/cli/commands/fins.py:198-200`），tool 的 `ValueError` 分支投影 invalid argument。CLI argv 显式空串仍由 CLI owner 保留既有 `--document-id must not contain empty item` 文案。未提供、匹配请求在 admission 时获得稳定 ID；完整 seed + 显式空/纯空白或 mismatch 在 `upload`/`prepare_observed_upload`/`start_upload` 返回前失败：无 `upload.preparing`、`upload.started`、pipeline `UPLOAD_STARTED`、observation/job record 或仓储 batch/publication。缺 seed + 空 ID 先由 O05 owner 的前置必填校验判定，断言 typed 错误与同样的无 started/副作用；不得在 O07 重新定义其优先级。成功请求仍由相同 owner 在 SEC/CN 执行入口复核，并用该 owner 输出的内部 ID 做持久化与事件投影；重复调用是同一纯函数的边界保护，不复制判定规则。

## 一个可验证实施分片

**S1：material 身份断言前置且公开内部 ID 完全退场。** 以上生产文件与下述测试文件是唯一允许的实施范围；按 owner 函数与 typed cause → runtime admission/规范 request → SEC/CN handoff → Service/CLI/tool 公开输入退场 → 相关测试的顺序修改，同一次 implementation pass 完成。分两次 gate review 会使中间状态仍接受冗余内部 ID，不能独立满足本 work unit 的公开契约，因此不机械按层拆片。

验收断言：owner 对省略/匹配返回相同的两 ID；完整 seed + 显式空/纯空白、不匹配产生各自 typed reason，未覆盖稳定 ID。三种启动模式的同一拒绝都早于 started，runner 调用数为零，job/observation 与 source 仓储状态无变化；缺 form/name + 空 ID 的集成请求由 O05 typed 必填 owner 决定优先级，同样早于 started。tool outcome 和 Service 错误文案不含 CLI `--document-id`，CLI mismatch 提示仍可行动。SEC 与 CN/HK 正常上传的 started、result、meta、manifest 身份相等，且跨命令 `process_material` 能按生成的 `document_id` 消费。CLI help 与 parser 均没有旧参数；旧参数带空串或非空值都 exit 2、stdout 为空、零副作用。Tool schema 不含旧字段，直接调用 callable 携带旧字段也返回 invalid argument；Service/request/pipeline 的公开签名不含该字段。所有测试替身中任意拼出的 material ID 应改为 owner 生成的期望值，不能反向要求生产代码保留旧任意 ID。

## 测试、真实 CLI 与质量门槛（实施 gate 执行）

更新 `tests/fins/test_docling_upload_service.py` 断言 owner 级 ID、空值和不匹配；`tests/fins/test_fins_ingestion_runtime.py` 覆盖 direct/observation/job 的无 started、无 runner/job、usage code、规范请求摘要，包含完整 seed + 空/纯空白 ID、完整 seed + mismatch、缺 form/name + 空 ID 的 O05 优先级集成断言；`tests/fins/test_fins_service_runtime.py`、`tests/service/test_fins_direct.py` 对 material handoff 做签名与生成 ID 断言，并确认 Service 文案无 CLI flag。更新 `tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py`、`tests/fins/test_docling_upload_service_integration.py` 核对两市场成功事件/结果/meta/manifest 及失败无发布；`tests/fins/test_fins_ingestion_tools.py` 核对 schema、未知字段拒绝及 tool outcome 文案无 CLI flag；`tests/cli/test_arg_parsing.py`、`tests/cli/test_fins_commands.py` 核对 help、旧参数两种值、O08 空 `document_id`、CLI mismatch 文案及真实 Service handoff。移除旧 fake 接受内部 ID 的断言，不改 filing 预期。

实施后先 `source .venv/bin/activate`，执行下列受影响测试与类型检查；要求无新增/扩散类型错误，若修改触及既有错误，同范围修复：

```bash
python -m pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q
pyright
```

再用 `python -m pytest tests -q --cov=dayu.cli.arg_parsing --cov=dayu.cli.commands.fins --cov=dayu.service.fins_direct --cov=dayu.fins.tools.upload_tools --cov=dayu.fins.ingestion_runtime --cov=dayu.fins.service_runtime --cov=dayu.fins.pipelines.sec_pipeline --cov=dayu.fins.pipelines.sec_upload_workflow --cov=dayu.fins.pipelines.cn_pipeline --cov=dayu.fins.pipelines.docling_upload_service` 收集完整相关覆盖率；对**上表每个修改的生产 `.py` 文件分别**执行 `python -m coverage report --include=<该文件路径> --fail-under=80`，不以总体百分比代替，未达标只补能验证 owner contract 的测试。

真实 CLI 配方（实施 gate，在 O05/O17/O09/O10 合入后执行）：从仓库根目录进入锁定 Python 3.11 venv；若尚未建环境，依 `requirements.txt` 使用 `python3.11 -m venv .venv` 与 `python -m pip install -e '.[test,dev,browser]' -c constraints/lock-macos-arm64-py311.txt`（仅 macOS arm64；其他平台选对应 lock）。此处选仓库现存的 `tests/fins/fixtures/sec_earnings_repair_v1/data/raw/msft-ex99_1.htm`，是非空 `.htm`，后缀在 material converter eligible 集中；CLI 真转换成功与否仍须现场判定，不能凭后缀/测试 fake 宣称通过。以固定种子 `MATERIAL_OTHER`、`O07 Fixture`、无财年/期间调用**合入后的** `build_material_ids` 计算 `DOC_ID`，不得复制旧基线摘要字面值：

```bash
REPO="$(pwd)"
RUN="$(mktemp -d /tmp/o07-cli-20260929.XXXXXX)"
FIXTURE="$REPO/tests/fins/fixtures/sec_earnings_repair_v1/data/raw/msft-ex99_1.htm"
source .venv/bin/activate
test -s "$FIXTURE"
mkdir -p "$RUN/workspaces" "$RUN/evidence"
DOC_ID="$(python -c 'from dayu.fins.pipelines.docling_upload_service import build_material_ids; print(build_material_ids(form_type="MATERIAL_OTHER", material_name="O07 Fixture", fiscal_year=None, fiscal_period=None)[0])')"
test -n "$DOC_ID"
```

下表每行是一条 **exact argv 模板**：`$RUN`、`$FIXTURE`、`$DOC_ID` 展开后，将 argv 数组和展开值写进该场景的 `command.json`；`dayu-cli` 是 venv 安装的真实入口。所有 case 使用各自新建的 `$RUN/workspaces/<case>`，唯 `sec-process` 复用成功的 `sec-omit` workspace。命令之间不得把一个 case 的发布状态带入另一个 case。`--base`、`--forms`、`--material-name`、`--files`、`--company-name`、`--document-id` 与 `process_material --document-id` 均已按 `dayu/cli/arg_parsing.py` 核对。`--company-name` 为 fresh company 的上传提供显式名称；CN/HK ticker 沿用仓库测试的 `600519`/`0700`。

| case | exact argv（变量按上段展开） | 预期 |
| --- | --- | --- |
| `help` | `dayu-cli upload_material --help` | exit 0；help 无 `--internal-document-id`。 |
| `old-empty` | `dayu-cli upload_material --base "$RUN/workspaces/old-empty" --ticker MSFT --forms MATERIAL_OTHER --material-name 'O07 Fixture' --files "$FIXTURE" --internal-document-id ''` | exit 2、stdout 空、未知参数、无发布。 |
| `old-value` | `dayu-cli upload_material --base "$RUN/workspaces/old-value" --ticker MSFT --forms MATERIAL_OTHER --material-name 'O07 Fixture' --files "$FIXTURE" --internal-document-id legacy` | 同上。 |
| `id-empty` | `dayu-cli upload_material --base "$RUN/workspaces/id-empty" --ticker MSFT --forms MATERIAL_OTHER --material-name 'O07 Fixture' --files "$FIXTURE" --document-id ''` | exit 2、CLI owner 的 O08 空串文案、无发布。 |
| `id-mismatch` | `dayu-cli upload_material --base "$RUN/workspaces/id-mismatch" --ticker MSFT --forms MATERIAL_OTHER --material-name 'O07 Fixture' --files "$FIXTURE" --document-id mat_mismatch` | exit 2、字段级 mismatch、无 started/job/publication。 |
| `sec-omit` | `dayu-cli upload_material --base "$RUN/workspaces/sec-omit" --ticker MSFT --action create --forms MATERIAL_OTHER --material-name 'O07 Fixture' --files "$FIXTURE" --company-name Microsoft` | exit 0；事件/result/meta/manifest 的两 ID 等于 owner 值。 |
| `sec-match` | `dayu-cli upload_material --base "$RUN/workspaces/sec-match" --ticker MSFT --action create --forms MATERIAL_OTHER --material-name 'O07 Fixture' --files "$FIXTURE" --company-name Microsoft --document-id "$DOC_ID"` | exit 0；与省略 case 的稳定 ID 相等。 |
| `cn-omit` | `dayu-cli upload_material --base "$RUN/workspaces/cn-omit" --ticker 600519 --action create --forms MATERIAL_OTHER --material-name 'O07 Fixture' --files "$FIXTURE" --company-name 贵州茅台` | exit 0；CN 事件/result/meta/manifest 同源。 |
| `hk-omit` | `dayu-cli upload_material --base "$RUN/workspaces/hk-omit" --ticker 0700 --action create --forms MATERIAL_OTHER --material-name 'O07 Fixture' --files "$FIXTURE" --company-name 腾讯控股` | exit 0；HK 事件/result/meta/manifest 同源。 |
| `sec-process` | `dayu-cli process_material --base "$RUN/workspaces/sec-omit" --ticker MSFT --document-id "$DOC_ID"` | 跨命令读取同一 material；记录真实 exit/result，不把处理器失败写成身份失败。 |

每个 case 在 `$RUN/evidence/<case>/` 保存 `command.json`（JSON argv 数组、cwd、workspace、fixture 路径及 SHA-256、owner 生成的 ID、执行时环境/HEAD）、`exit-code.txt`、`stdout.txt`、`stderr.txt`、`events.txt`（从真实 CLI 输出按原顺序摘录事件及终态，保留原文定位）和 `filesystem-before.json`/`filesystem-after.json`/`filesystem-diff.json`（workspace 全文件相对路径、大小、SHA-256；不得只比较目录数）。`command.json` 以下面的 `sec-omit` 对象为模板，执行时用展开后的真实值替换尖括号占位：

```json
{"argv":["dayu-cli","upload_material","--base","<RUN/workspaces/sec-omit>","--ticker","MSFT","--action","create","--forms","MATERIAL_OTHER","--material-name","O07 Fixture","--files","<FIXTURE>","--company-name","Microsoft"],"cwd":"<REPO>","workspace":"<RUN/workspaces/sec-omit>","fixture":{"path":"<FIXTURE>","sha256":"<digest>"},"owner_document_id":"<DOC_ID>","head":"<git HEAD>","python":"<venv Python version>"}
```

三个 `filesystem-*.json` 以相对路径为键，before/after 值为 `{"size":123,"sha256":"<digest>"}`，diff 明列 added/removed/changed，不能只给布尔值。另保存找到的 `materials/material_manifest.json`、材料 `meta.json` 和 source 文件的原样副本或明确 `absent` 记录，并记录 job sidecar `*.events.jsonl` 是否存在；实际路径由新 workspace 文件树发现，不臆造固定 ticker 目录。失败 case 必须比较前后树并确认无材料发布、job/observation；成功 case 从原始事件、result、manifest/meta 逐字段核对 `document_id` 与 `internal_document_id`。如 `.htm` 实际转换失败，保留该失败证据，改选仓库中**经真实转换验证**的 fixture 后重新运行全部成功 case 并记录 fixture 变更，不能以假成功代替。真实 CLI 不是 fake CLI 测试的替代品。当前 checkout 未见 `.venv`；本 plan 只静态核对，环境未准备前不得宣称 CLI、测试或 pyright 通过。

## README、集成与残余

实施涉及 `dayu/fins/` 与 `tests/`，须先按已读的目标文档更新约束检查 `dayu/fins/README.md`、`tests/README.md`；CLI 用户参数/错误变化须检查根 `README.md` 并只写当前可用操作。Service/CLI/tool 的透传删除不改变分层或装配，`dayu/README.md` 只有核对后确认跨层稳定边界确有变化才更新；不触发 Engine/Host/Config README。此 plan gate 不修改任何 README。

O05 前置必填、O17 form canonical、O09 的 1800–2100 财年域、O10 的 `FY/H1/Q1/Q2/Q3/Q4` 与空转 `None` 均属独立 work unit，不进入本分片。O05 是本项实施硬依赖；实施入口重新核对它及 O17/O09/O10 的实际合入状态。总控 repair-sequence 是跨项义务 owner：在 O05/O17/O09/O10 合入后由集成关卡重算 O07 owner 单测、三种入口时序和上述真实 CLI 证据，不能沿用旧摘要字面值；本 plan 登记义务，不修改其它 artifact。若并行分支碰到相同 owner 函数，串行裁决合并，保证 runtime admission 与 SEC/CN 使用同一函数。不把 O17 尚无本 checkout 裁决文件的具体规则猜进本计划。seed 变化可能令已有 workspace 中已发布 material 的旧 ID 与新 ID 并存；其新起算或迁移处置属于独立 WU `fins-material-legacy-identity-seed-disposition`，由依赖 WU goal 阶段裁决；本项不实施迁移，也不宣称旧 workspace 身份兼容性已解决。

残余风险：O05 的合入状态与缺 seed + 空 ID 优先级须在实施入口从 owner contract 重核；未合入即停止 O07 实施。tool callable 目前直接解析参数，schema 的 `additional_properties=False` 不足以证明它拒绝未知键，本分片必须完成表中同源拒绝与测试；fixture 后缀合格不保证真实 Docling 转换成功，真实 CLI、覆盖率与 pyright 尚未运行；旧已发布身份处置留给独立 WU。若实施中发现 owner 无法在完整身份种子时于 started 前校验，停止并提交直接代码证据与最小替代设计，不在下游补偿。

## 完成报告格式

实施 gate 报告应列：修改文件和 owner 变化、各入口错误码及事件时序、受影响测试/逐文件覆盖率/pyright、真实 CLI 的隔离证据路径与前后状态、README 裁决、O17/O09/O10 集成基线和未覆盖风险；各 gate 状态不得用本 plan 的预测替代实测。
