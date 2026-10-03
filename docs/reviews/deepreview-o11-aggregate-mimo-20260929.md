RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-017e6e77

# Code Review（UM-O11-F01 aggregate deepreview）

## Scope

- Mode: current changes（aggregate，任务指定审查 accepted plan 基线到 accepted slice 的 committed diff；文件名由任务指定，覆盖 deepreview 默认 timestamp 命名）
- Branch: `codex/upload-material-o11`
- Base: `9141b5e9c65caaf52416f177a2641f8a7e1134ad`（`gateflow: accept UM-O11 strict dates plan`，accepted plan commit）
- Range: `9141b5e9..cea46f5f`，恰为单提交 `cea46f5f`（`fix: validate material upload dates before launch`）。HEAD `cea46f5fd761f2d39c6e332c26c3caa8df425f06` 与 accepted slice 一致，review 前后 `git status --short` 均为空，停止条件「HEAD/range 不符」未触发。
- Output file: `docs/reviews/deepreview-o11-aggregate-mimo-20260929.md`
- Included scope（16 个 committed 文件）:
  - 生产：`dayu/fins/ingestion_runtime.py`、`dayu/cli/commands/fins.py`、`dayu/fins/tools/upload_tools.py`
  - 测试：`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/cli/test_fins_commands.py`
  - 文档：`README.md`、`dayu/fins/README.md`
  - 流程产物（只读核对）：`docs/gateflow/upload-material-o11-s1-implementation-20260929.md`、`upload-material-o11-s1-readme-fix-20260929.md`、`upload-material-o11-s1-code-review-adjudication-20260929.md`
  - 双路 code review 与 rereview（只读核对）：`docs/reviews/code-review-20260929-032747.md`（MiMo 第一路）、`code-review-20260929-092732-o11-kimi.md`（Kimi）、`code-review-20260929-094352-o11-mimo.md`（MiMo，产出 O11-CR-F1）、`code-review-o11-readme-rereview-kimi-20260929.md`、`code-review-o11-readme-rereview-mimo-20260929.md`
  - 边界真源（只读）：基线 commit 内 `docs/gateflow/upload-material-o11-dates-goal-20260929.md`、`upload-material-o11-dates-plan-20260929.md`、`upload-material-o11-plan-review-adjudication-20260929.md`、`AGENTS.md`/`CLAUDE.md`
  - owner 依赖走读（只读）：`dayu/fins/domain/filing_semantics.py`（`parse_iso_calendar_date`）、`dayu/service/fins_direct.py`、`dayu/fins/service_runtime.py`、`dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/upload_batch.py`、`dayu/cli/arg_parsing.py`、`dayu/fins/tools/_ingestion_tool_helpers.py`
- Excluded scope:
  - `upload_filings_from` 扫描/脚本生成元数据路径（plan 残余 R1，README 明示排除）
  - O05/O16 共享 admission 并发变更（plan 残余 R3，未进入本 HEAD）
  - UM-O12 公司名称状态条件准入的相邻问题（既有登记，与本 slice 日期 diff 无关；本 review 不把该缺口计为 O11 日期 finding）
  - 未覆盖 CN/HK 真实网络发布（本地 US 仓储发布已实测，CN/HK 由 `tests/fins/test_cn_pipeline.py` 回归覆盖）
- Parallel review coverage: 无（任务明确禁止派发子 Agent；全部走读与验证由本 reviewer 单路完成）

## Findings

未发现实质性问题。

停止条件评估（逐项独立判定）：

1. **HEAD/range 与 accepted slice 不符：未触发。** `git rev-parse HEAD` = `cea46f5f`，`git log 9141b5e9..cea46f5f` 恰一条提交，diff 16 文件 = 计划允许的 8 个产品/测试/README 文件 + 8 个 gateflow/review 流程产物，无越界产品改动。
2. **实质 correctness finding：未触发。** 对任务指定攻击面（四启动入口 side effect 前拒绝、raw 日期与 CLI 折叠边界、tool schema 自足、material action/状态影响、真实 CLI 与仓储读回、README 空值事实精度、测试 coverage/pyright、跨模块 drift）逐项攻击，未找到能沿同一逻辑/数据路径证明的错误行为；详见下方攻击面走读与验证记录。

攻击面逐项结论（每项均由代码同源走读 + 本 reviewer 实测支撑）：

- **四启动入口 side effect 前拒绝：成立。** `upload`（`ingestion_runtime.py:3672`）、`prepare_observed_upload`（:3869）、`start_observed_upload`（:3841→前者）、`start_upload`（:4686）全部先经 `_validate_runtime_upload_request`（:4714）→ material 落 `_normalize_upload_request`（:7694，:7714-7715 两日期 typed 校验）才创建 direct producer、observation、durable job 或提交 runner；material 准入全程无 state read（测试以 `_ForbiddenFilingUploadStateRepository`/`_ForbiddenUploadRunner` 越界即炸 + SHA-256 workspace 树快照断言零副作用，覆盖 4 入口 × US/CN/HK × 10 类非法值）。本 reviewer 以真实 CLI 复证：三种非法日期场景（含本 slice 收紧的 padded 原文）exit 2、stdout 空、fresh base 文件树 0→0，连 base 目录都无条目（`DefaultFinsRuntime.create` 以 `create_directories=False` 装配，构造期只读），证明拒绝发生在一切 workspace 改动之前。`_run_upload_job`（:4962）只消费启动时已验证的 request 对象，无从磁盘摘要重建 request 的恢复路径。
- **raw 日期与 CLI 折叠边界：成立且与 README 逐格吻合。** CLI material 走 `_optional_material_date_text`（`fins.py:1279-1289`）：仅 `None`/空串/纯空白折叠 `None`，非空原文逐字保留（padded 不 trim）；CLI filing 原文直传（`fins.py:695-696`）；tool 两 kind 均走 `_optional_raw_nullable_text`（`upload_tools.py:396-418`）：缺失/JSON null → `None`，字符串原样。本 reviewer 逐格实测：CLI `upload_filing --filing-date ''`/`' '` → exit 2 + 字段文案（filing 空值拒绝承诺成立）；CLI `upload_material --filing-date ' 2024-02-29 '` → exit 2（本 slice 收紧行为）；`--filing-date ''` → exit 0 且 meta/manifest 双 `null`；`--report-date ' '` → exit 0 且双 `null`（R2 折叠现状与 README「当前会将……视为未提供」一致）；tool 参数层 `''`/`'  '`/padded 原样透传、显式 `null` → `None`，端到端 probe 中空串/空白/padded/不存在日期全部 `invalid_argument` + owner 字段文案，显式 `null` 得 `ToolAwaitingOutcome`（与 schema「省略或填 null 表示未提供」一致）。
- **tool schema 自足：成立。** 两字段描述（`upload_tools.py:283/287`）各自包含业务含义、filing/material 同适用、省略或 `null` 未提供、实际存在公历日 `YYYY-MM-DD`、示例 `2024-02-29`、空串/纯空白/首尾空白非法且不能用于清空日期；无内部 parser/type 名。错误投影同源：`FinsUploadUsageError`（`ValueError` 子类，`str(exc) == failure.message`，`ingestion_runtime.py:743-762`）被工具 `except ValueError` 投影为既有 `invalid_argument`，文案出自 `_USAGE_MESSAGES`（:1045-1046）唯一真源；prompt 目录无日期文案残留。
- **material action/状态影响：成立。** 准入顺序确定（ticker → action → source_kind → filing_date → report_date）；非法日期在 `delete` 动作同样于任何 mutation 前拒绝（真实 CLI `--action delete --filing-date 2025-02-30` → exit 2）；合法值不重写（`replace(request, action=action)` 保留日期原值），经 `_upload_request_summary`（:7784）、`UPLOAD_STARTED` payload、`prepare_upload(meta=...)`（`sec_upload_workflow.py:549-557`，CN/HK 同构）流入 source meta 与 `MaterialManifestItem`，同一字符串贯通。update 语义实测：内容相同的 update 为 `skipped/stored_files=0` 不写 meta（日期保持）；真实写入的 update 用空日期会把既有日期落为 `null`（meta/manifest 同步），即 README「保存时为 `null`」在 create 与真实 update 上均成立，省略参数与显式空折叠等价。
- **README 对 filing/material 空值的事实精度：成立。** `README.md:382-395` 全部可验证陈述逐格核对：非空日期严格公历 + 月日补零 + 无首尾空白（探针 `0001-01-01`/`9999-12-31` 接受、`0000-01-01`/`2024-2-29`/换行 padded 拒绝，与「年份允许 `0001..9999`」一致）；`upload_filing` 空串/纯白拒绝（实测 exit 2）；tool 空串/纯白拒绝（实测 `invalid_argument`）；material CLI 空值折叠现状 + 仅 `--filing-date ""` 标注既有支持（实测保存 `null`）；`upload_filings_from` 排除句保留 R1 边界。与 `dayu/fins/README.md` admission 段表述一致。
- **跨模块 drift：未发现新 drift。** production 中 `FinsUploadMaterialRequest` 仅两个构造点（`fins_direct.py:341` Service、`upload_tools.py:351` tool），均经四入口共享 admission；runner 下游 `service_runtime.py:240-262` 日期原样透传 US/CN/HK pipeline，无二次清洗；`upload_batch.py:543-544` 的 strip 属 R1 已登记范围；filing 静态准入（`ingestion_runtime.py:1288-1289`）与 material 共享准入（:7714-7715）复用同一 `_validate_optional_upload_iso_date` → `parse_iso_calendar_date`（`filing_semantics.py:375-404`，ASCII fullmatch + `datetime.date` 存在性 + isoformat 回写），无第二套规则。

### 信息性观察（非 finding，不要求修复）

- **O11-AGG-I1（信息）**：`_bounded_text`（`ingestion_runtime.py:7460-7482`）docstring 写「返回原文本」，实际返回 `value.strip()`；`_optional_bounded_text`（:7485-7507）因此对带空白文本会裁剪。对本 slice 日期投影无可观测后果——admission 保证非 `None` 日期是无空白的 `YYYY-MM-DD`，strip 为恒等，job summary/meta/manifest 的日期一致性由 admission 前置保证而非 helper 保真保证。Kimi review 所述「helper 不 trim」的机制表述不精确，结论仍成立。属既有代码的 docstring 措辞问题，本 diff 未触及该 helper，不登记为 finding。
- **O11-AGG-I2（信息）**：`_INVALID_ARGUMENT_HINT`（`upload_tools.py:58-60`）枚举「ticker、upload_kind、action、files、primary、会计期间和材料字段」，未列日期字段；日期失败时 message 本身字段精确（「披露日期（filing_date）必须是……」），hint 为既有通用文案（filing 日期失败此前同样附带），本 diff 未修改也不应为日期增补特例。

## Open Questions

无。

## Residual Risk

1. **R1（plan 登记，独立确认仍在）**：`upload_filings_from` 批量路径仍以 `_optional_stripped_text`（`fins.py:348-349`）与 `upload_batch.py` 的 `_optional_text`（:543-544）预折叠/裁剪日期，脚本生成 argv 经 `fins.py:439-442` 传给 direct 命令；准入契约不被绕过，但扫描层对非空带空白日期的静默修正在该入口保留。属后续独立 work unit。
2. **R2（plan 登记，需用户独立裁决）**：CLI material 对空串/纯空白两字段的折叠仍是现状而非承诺，仅 `--filing-date ""` 例外被 README 记录；与 raw request/tool 的 typed 拒绝存在入口级不对称。本 reviewer 实测 `--report-date ' '` 折叠为 `null` 与 README 陈述一致，文案未偷增承诺。
3. **R3（plan 登记，O05/O16 集成 owner）**：共享 admission 内多错误字段优先级（material 为 ticker → action → source_kind → filing_date → report_date；filing 静态准入顺序不同）及与 O05/O16 的冲突须由后集成者基于实际 HEAD 串行复核；两日期同时非法时 filing_date 优先未被测试固定。
4. **小测试缺口（既有登记）**：CLI 层 `--report-date ""`/纯空白折叠未被 `tests/cli/test_fins_commands.py` 断言（本 reviewer 真实 CLI 已行为侧证实）；tool 显式 `null` → `None` 仅由 schema 断言间接覆盖（本 reviewer 端到端 probe 证实）。
5. **潜在 hazard（既有，MiMo 复审已登记）**：`_normalize_upload_request` 的 filing 分支（:7711-7712）不校验日期（filing 日期 owner 在 `_validate_fins_upload_filing_static:1288-1289`）；当前唯一调用方 `_validate_runtime_upload_request` 不会把 filing 送入该分支，未来新增调用方必须走 filing 静态准入。
6. **验证边界**：CN/HK 真实网络发布未在本 review 重放（US 本地仓储发布 + meta/manifest 读回已实测；CN/HK 由 focused 测试组回归）；`upload_filings_from`（R1）与 O05/O16 集成（R3）在既有残余范围；UM-O12 公司名称相邻问题不在本 slice，不据此判 O11。

## 只读核对（goal / plan / 双路 code review / 总控裁决）

- goal（`upload-material-o11-dates-goal-20260929.md`）：目标「material 非空两日期仅接受严格实际存在公历日、字段明确 typed failure、校验早于 upload lifecycle 与持久化、CLI 显式空 `--filing-date ""` 例外保持」与实现逐项吻合；非目标（不动 parser/fiscal/form/name/schema、不建第二套校验、不承诺空 `report_date`）均未被违反。
- plan（`upload-material-o11-dates-plan-20260929.md`，accepted）：S1 步骤①material 分支复用 `_validate_optional_upload_iso_date`、②CLI 窄投影保空值折叠不 trim 非空、③tool 改 raw nullable + schema 自足，均已实现；允许文件清单（生产 3 / 测试 3 / 文档 2）100% 遵守；验证设计 6 项均已由实施/双路/本轮复跑落实。
- plan 裁决（`upload-material-o11-plan-review-adjudication-20260929.md`）：F1–F5（raw 空白日期拒、schema 自足、README 变更口径、覆盖率诚实登记、测试不固化 monkeypatch）在实现中全部兑现。
- 双路 code review 与 rereview：MiMo 032747（pass，无产品 finding）、Kimi 092732（pass）、MiMo 094352（O11-CR-F1 README 空值 truth table 缺口，低）、Kimi/MiMo readme-rereview（O11-CR-F1 修复验证 pass）。总控裁决 `upload-material-o11-s1-code-review-adjudication-20260929.md` 的对 owner 陈述（`parse_iso_calendar_date` 为日期真源、`_normalize_upload_request` 为四入口共同直接上游、CLI 显式空 filing_date 保持 `None` 非空不 trim、schema 自足）经本 reviewer 逐条复核属实；O11-CR-F1 修复后 README 逐格真值表与 owner 代码、真实 CLI 一致（本轮独立复证）。裁决第 3 条登记的省略 `--company-name` 落 `unexpected_runtime` 属 UM-O12-F01，本 review 按任务边界不将其计为本 slice 日期问题。
- drift 核对：diff 文件集与 implementation artifact 候选清单逐项一致；验证数字（714 passed、86/91/93%、pyright 0）与各 artifact 声明逐数字复现一致。

## 验证记录（本 reviewer 实际执行，2026-09-29）

- **测试**：`source .venv/bin/activate && python -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/cli/test_fins_commands.py -q` → **714 passed**（3 条 edgartools deprecation warning）。
- **覆盖率**（3 文件组 667 passed 后 `coverage report --include`，coverage 数据文件重定向 `$TMPDIR`）：`dayu/cli/commands/fins.py` **86%**（457/66）、`dayu/fins/ingestion_runtime.py` **91%**（2373/208）、`dayu/fins/tools/upload_tools.py` **93%**（115/8），各 ≥80%。
- **pyright**：`python -m pyright dayu/ tests/ utils/` → **0 errors, 0 warnings, 0 informations**。`git diff --check` 通过；验证全程未污染工作树（`git status --short` 为空，HEAD 保持 `cea46f5f`）。
- **真实 CLI 隔离场景**（`$TMPDIR/um-o11-aggr-cli/`，每场景 fresh `--base`，同一输入 `input/material.md`，argv：`upload_material --ticker AAPL --action create --forms MATERIAL_OTHER --material-name Deck --company-name 'Apple Inc.' --files …` + 各日期参数）：
  - `--filing-date 2025-02-30` → exit 2，stderr `披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期`，stdout 空，base 文件树 0→0；
  - `--report-date not-a-date` → exit 2，`报告期日期（report_date）……`，0→0；
  - `--filing-date ' 2024-02-29 '` → exit 2，字段文案，0→0（本 slice 收紧行为）；
  - 双 `2024-02-29` → exit 0，source meta 与 material manifest 两字段均 `2024-02-29`（同一 `document_id`）；
  - `--filing-date ''` → exit 0，meta/manifest 双 `null`；
  - `--report-date ' '` → exit 0，meta/manifest 双 `null`（R2 折叠现状）；
  - `--action delete --filing-date 2025-02-30` → exit 2（delete 同样先拒）；
  - update 语义：内容相同 update → `skipped/stored_files=0` 且 meta 不变；变更内容后 `update --filing-date ''` → `ok/stored_files=1`，meta/manifest 双 `null`（「保存时为 null」在真实 update 成立）；
  - `upload_filing --filing-date ''` 与 `' '` → 均 exit 2 + `披露日期（filing_date）……`，base 0 条目。
- **仓储读回**（非冻结证据）：`DefaultFinsRuntime.create(...).source_repository.list_source_document_ids/get_source_meta`（`SourceKind.MATERIAL`）与 `portfolio/AAPL/materials/material_manifest.json` 原文解析交叉核对，成功场景 meta/manifest 日期同源一致（合法双日期、空 filing、空白 report、update 覆盖四组均核对）。
- **tool 端到端 probe**（真实 `FinsIngestionRuntime` + `FinsUploadToolCallable`）：`''`/`'  '`/`' 2024-02-29 '`/`2025-02-30` → `ToolFailedOutcome(invalid_argument)` + owner 字段文案逐字一致；显式 `null` → `ToolAwaitingOutcome`。参数层（`_upload_request_from_arguments`）实测：省略/`null` → `None`、`''`/空白/padded 原样保留。
- **owner 探针**：`parse_iso_calendar_date` 对 `0001-01-01`/`9999-12-31` 接受，`0000-01-01`/`2024-2-29`/`2024-00-10`/`2024-01-00`/换行 padded 全拒（README「`0001..9999`」「月日补零」「无首尾空白」逐格成立）。
- **走读覆盖面**：四启动入口、`_validate_runtime_upload_request`、`_normalize_upload_request`、`_validate_optional_upload_iso_date`、`parse_iso_calendar_date`、CLI 三个投影点（filing 原文/material 折叠/batch 预折叠）、tool 两 helper 与 schema、Service 透传、runner 市场分发、meta/manifest 投影链（`sec_upload_workflow.py`/`cn_pipeline.py`/`docling_upload_service.py`/`document_models.py`）均已沿真实调用链逐行走读。

## 结论

**pass**。UM-O11-F01 accepted slice（`9141b5e9..cea46f5f`）与 accepted plan 的 S1 实现切片逐项吻合：material 两日期在四启动入口共享 admission 以字段明确 typed failure 于一切副作用（state 读、producer、observation、durable job、runner、公司/source/meta/manifest 发布）之前拒绝；raw 日期与 CLI 折叠边界、tool schema 自足、错误与文案同源、meta/manifest 同源投影经真实 CLI 与仓储读回独立证实；README 对 filing/material 空值的事实陈述逐格为真；测试为 owner 级、714 passed、三文件覆盖率 86/91/93%、pyright 0。未发现 correctness/stability/maintainability 实质性 finding；残余 R1/R2/R3 与小测试缺口均已被 plan/裁决显式登记并有明确 owner，未见新跨模块 drift。
