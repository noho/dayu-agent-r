# UM-O06-F01 material_name 长度计划 adversarial plan review（MiMo 路）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro

CANARY=mimo-31c0eb33

- 审查对象：`docs/gateflow/upload-material-o06-name-length-plan-20260929.md`
- 审查 SHA-256：`fd95ede94a6746da266630661b8802c564c556357c8aa882d8dbd1fe9fc24400`（实测一致，见下方复核记录）
- 审查日期：2026-09-29；workspace `/private/tmp/dayu-upload-o06`，branch `codex/upload-material-o06`
- 证据基线：goal confirmation `upload-material-o06-name-length-goal-20260929.md`（240 Unicode 码点为用户 2026-09-29 明确裁决，本次审查不重议阈值）、裁决登记 `upload-material-o06-plan-review-adjudication-20260929.md`、总控队列 `upload-material-issue-198-repair-sequence-20260928.md`、`AGENTS.md`、当前 HEAD 代码与测试
- 范围：只做 plan review；不实施、不改 plan/代码/测试/README/goal/裁决
- 结论：**pass-with-risks**（2 项中级、3 项低级 finding，均为可在 plan 文本内收敛的规格缺口，无结构性不安全；详见文末）

## SHA 复核记录

```
fd95ede94a6746da266630661b8802c564c556357c8aa882d8dbd1fe9fc24400  docs/gateflow/upload-material-o06-name-length-plan-20260929.md
```

与裁决登记中记载的 SHA 一致；文件存在；plan 已自declare"唯一业务 owner 是 Fins material request admission"，owner 可判定，满足继续审查的停止条件。

## Goal Confirmation 绑定范围

- 目标（binding）：`material_name` 按 `len(name.strip())` 最多 240 个 Unicode 码点，超限在 `upload.started`、ID 生成、业务持久化之前统一 typed 拒绝；不截断、不做 NFC/NFD 归一化；`None`/空串/纯空白的必填语义归 O05，O05/O06 同一共享 admission owner 合流；真实 CLI 独立 workroot 验证 239/240/241、emoji、组合字符、前后空白。
- 非目标（binding）：O05 缺失、O17 form canonical、O16 文件动作、O04/O23 文件名、O07 稳定 ID 对外契约各守原 work unit；不从 job 摘要 240 或 241 样本倒推阈值。
- goal 停止条件：若 direct/job/material ID 使用不同规范化结果，plan 必须明确唯一 canonical 名称 owner，不得下游补截断/兼容逻辑。
- 裁决登记（binding）：O05 必填与 O17 form canonical 是前置依赖；240 计数口径已裁决不再重问。

## 已测试的 assumptions（含验证结果）

| # | plan 声称 | 验证结果 |
| --- | --- | --- |
| A1 | `FinsUploadMaterialRequest.material_name: str | None`，`_normalize_upload_request()` 只处理 ticker/action/source kind，material 分支无名称长度校验 | **成立**：`ingestion_runtime.py:7694-7714` 只做 `_admit_fins_upload_ticker_identity`/`_normalize_upload_action`/`_validate_upload_source_kind`，material 分支仅 `replace(request, action=action)` |
| A2 | `upload()`/`prepare_observed_upload()`/`start_upload()` 都经 `_validate_runtime_upload_request()`，且在其之前无业务写入 | **成立**：三处调用点 `ingestion_runtime.py:3672/3869/4686`，均在 producer/handle/queued record 之前；`start_upload` 的 `_upload_request_summary()`（4693）先于 `_create_queued_record_with_start_lock`（4696） |
| A3 | US/CN/HK workflow 可直接进入 `build_material_ids()`，共两个实际 ID 前入口 | **成立**：仅 `sec_upload_workflow.py:475` 与 `cn_pipeline.py:1091` 两处调用；定义在 `docling_upload_service.py:1820`，seed 用 `material_name.strip()`、空值抛 `ValueError("material_name 不能为空")`（1843-1848） |
| A4 | workflow 把原名称写入 `upload.started`、result、`prepare_upload(meta=...)`，仓储从同一 meta 投影 | **成立**：`sec_upload_workflow.py:510/552/583/611` 全部写 raw `material_name`；`_fs_processed_core.py:575` 从 `merged_meta` 透传 |
| A5 | job 摘要 `_optional_bounded_text()` 通用 `_MAX_TEXT_CHARS=240` 仅约束摘要 | **成立**：`ingestion_runtime.py:166/7840-7844`；`_bounded_text` 按 strip 后长度校验并**返回 strip 后文本**（7475-7482），仅 `_upload_request_summary` 调用，direct/pipeline 路径不经过 |
| A6 | CLI/tool 已有去首尾空白投影，direct 保留 raw | **成立**：CLI `fins.py:730` `_optional_stripped_text(args.material_name)`；tool `_ingestion_tool_helpers.py:95-112` `_required_text` 返回 `value.strip()`；Service `fins_direct.py:341-358` 原样构造 request |
| A7 | workflow `try` 的泛异常收口会把非 typed 异常映射为 `unexpected_runtime` | **成立**：`sec_upload_workflow.py:602-603`、`cn_pipeline.py:1218-1219` 的 `except Exception` → `fins_upload_failure_from_exception`，后者对未识别异常一律 `UNEXPECTED_RUNTIME`（`upload_failure.py:280-286`）；`build_material_ids` 与 validator 计划插入点在 `try`（sec 489 / cn 1105）之前，typed 错误可自然逃逸 |
| A8 | tool 协议按现有 `invalid_argument` 映射，CLI usage 错误 exit 2 | **成立**：tool `upload_tools.py:117-124` 捕获 `ValueError` → `invalid_argument`（`FinsUploadUsageError` 为 `ValueError` 子类，`ingestion_runtime.py:743`）；CLI `fins.py:198-200` 捕获 `FinsUploadUsageError` → `EXIT_USAGE_ERROR=2`（`exit_codes.py:10`） |
| A9 | `service_runtime.py` 晚期 None guard、`docling_upload_service.py` 身份算法不在白名单 | **成立**：`service_runtime.py:223-226` 晚期 guard 存在；plan 明确排除且禁止用作缺口补偿 |
| A10 | 白名单测试文件与 `MATERIAL_OTHER`、`--base`、`--forms`、`--material-name` 等 CLI 矩阵元素存在 | **成立**：7 个测试文件均在；`arg_parsing.py:396/888/958-959` 存在对应参数；tool schema 示例含 `MATERIAL_OTHER`（`upload_tools.py:262`） |
| A11 | 引入 pipelines→`ingestion_runtime` 的 validator 调用不新增架构边 | **成立**：`sec_upload_workflow.py:19`、`cn_pipeline.py:39-46` 已从 `ingestion_runtime` 导入类型；`docling_upload_service` 不反向依赖 `ingestion_runtime`，无新增环 |
| A12 | "证明无业务写入"可用既有测试手法达成 | **成立**：`test_sec_pipeline_upload_material_stream.py:385-487` 已有 monkeypatch 拒绝读写 + 目录断言的先例 |
| A13 | O17→O05→O16→O06 为真实代码依赖 | **部分成立**：O05→O06（同 owner 合流、空值归属、error 优先级）与 O17→O05（form 先 canonical 再判必填）为设计依赖且裁决登记确认 O05/O17 前置；**O16→O06 无功能依赖证据**，见 F03 |

## Findings

### F01-未修复-[中]-workflow 直调入口的空值/纯空白名称行为未定义，长度校验函数前置条件在该调用点可被破坏

- **位置**: plan《目标、边界与唯一 owner》第 14 段（"该函数只在 O05 已将名称收窄为非空 `str` 后调用"、"独立 US/CN/HK pipeline 的两个实际 ID 前入口调用**同一个** owner 函数"）；白名单第 2 行（"在各 material ID 前调用同一 validator"）；《owner 测试与验收矩阵》第 40 行（workflow 只测 241/240，无空值行）
- **问题类型**: 契约缺失 / 测试缺口 / 语义所有权
- **当前写法**: 长度校验函数契约是"只在 O05 已收窄为非空 str 后调用"，只执行 `len(name.strip()) > 240`；两个 workflow 入口"调用同一 validator"；矩阵对 workflow 入口只断言 241 抛同码、240 走原路径。
- **反例/失败场景**: `run_upload_material_stream(..., material_name="   ")` 或 `""` 直调（不过 runtime admission，无 O05 收窄）。若实现按字面只在 workflow 装长度叶子函数：`len("".strip())=0 ≤ 240` 通过，随后落到 `build_material_ids` 的 raw `ValueError("material_name 不能为空")`（`docling_upload_service.py:1848`）——同一"名称缺失"业务事实，runtime 入口报 O05 typed code，workflow 入口报 builder raw ValueError，形成两套必填错误语义。若实现让长度函数对空值 assert/前置校验，则 workflow 调用点违反该函数自身 docstring 契约，行为（AssertionError/错误 code）不可预测。
- **为什么有问题**: goal 明确"O05/O06 应在同一共享 admission owner 中合流，不形成两套长度/必填判断"；AGENTS.md 语义所有权要求同一业务事实唯一 owner、多消费者复用同一真源。plan 的 workflow 插入点规格（"同一 validator"字面指长度叶子）+ 矩阵缺空值行，使 implementation agent 有两条都"符合 plan"的实现路径，其中一条产出禁止的语义分叉。
- **直接证据**: `docling_upload_service.py:1843-1848`；`sec_upload_workflow.py:475`（`build_material_ids` 在 `try` 489 之前，raw ValueError 直接向外传播）；plan 第 14/31/40 行；goal 第 12 段。
- **影响**: 实施 Agent 生成错误/不一致错误语义；LLM 在 workflow 路径看到不可行动的 raw ValueError；后续 review 无法验收"同一 owner"承诺；与修复序列"同源规范化及校验"要求冲突。
- **建议改法和验证点**:
  1. plan 明确 workflow 两入口调用的是 O05+O06 合流后的完整 admission 校验（或共享 owner 函数定义空值→O05 code），并写明空值/纯空白在 workflow 入口的期望 code；
  2. 矩阵补 workflow 入口的 `None`/`""`/纯空白行，断言与 runtime 入口同一 code；
  3. 验证点：直调两 workflow 传空名，断言 typed O05 code（而非 `ValueError("material_name 不能为空")`）。
- **修复风险（低/中/高）**: 低（plan 文本 2-3 句 + 矩阵 1 行）
- **严重程度（低/中/高/严重）**: 中

### F02-未修复-[中]-名称超长与 O16 action/files（及 O17 form 之外情形）同时非法时的错误优先级未定义、未测试

- **位置**: plan《目标、边界与唯一 owner》第 16 段（只定义"名称和 form 同时非法时延续 O05 已确定的 form 优先级"）；矩阵第 38 行（"文件与目标条件用合法夹具隔离，避免 O16/状态错误混淆"）；《集成前提》第 22 段（O16 前置顺序）
- **问题类型**: 契约缺失 / 测试缺口 / 状态机漏洞（错误顺序契约）
- **当前写法**: plan 只规定 form-vs-name 优先级（form 先），对 name-vs-action/files 保持沉默，并在矩阵中刻意用合法夹具隔离，使 joint-invalid 情形从未被定义也从未被测试。O16 前置顺序默默决定了检查顺序，但没有形成任何可验收契约。
- **反例/失败场景**: `action=delete` 且 files 非法且 `material_name` 241 码点的请求进入 admission：O16 的 action/files 检查与 O06 的长度检查在同一流程内的相对位置决定 LLM 先收到哪个错误。实现顺序即事实契约；O16 或 O06 任一后续重排时无回归测试兜底，LLM 先修 files 再撞名称错误，多轮返工。
- **为什么有问题**: repair-sequence 对同类问题有显式优先级传统（"UM-O16-F01 的 action/files 错误应早于 O14/O15 的状态错误"），O06 与 O16 的错误先后却无任何文档；AGENTS.md LLM-facing 约束要求错误在最低认知负担下稳定做对下一步——错误顺序漂移直接损害该目标。plan 声称"所有 action 使用同一规则"并有完整矩阵，但对最容易真实出现的组合脏输入恰好无覆盖。
- **直接证据**: plan 第 16/38 行；`upload-material-issue-198-repair-sequence-20260928.md` 第 25 行（仅规定 O16 早于 O14/O15）；`_normalize_upload_action` 等现有检查在 `_normalize_upload_request` 前段（7707-7709），O05/O06 插入 material 分支，O16 落点未定。
- **影响**: 错误行为不可验收；LLM-facing 错误顺序不稳定；后续返工。
- **建议改法和验证点**:
  1. plan 显式声明 name-too-long 与 action/files 非法的优先级（建议沿 repair-sequence 惯例规定请求字段错误的固定顺序，并与 O16 work unit 对齐）；
  2. 矩阵补一行 joint-invalid 用例（241 名称 + 非法 files 或非法 action），断言稳定先报哪一个 code；
  3. 验证点：同一 joint-invalid 请求在 O06/O16 先后两种集成顺序下产生同一错误 code（由契约钉死后可测）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F03-未修复-[低]-O16→O06 硬前置超出裁决登记的前置清单，缺乏代码级依赖支撑，拖延已知缺口闭环

- **位置**: plan《集成前提与一个行为切片》第 22 段（"实施次序固定为：O17→O05→O16→O06…O05/O17/O16 任一尚未集成时，O06 计划可审但不得实施"）
- **问题类型**: 切片过粗（sequencing）/ 过度耦合
- **当前写法**: 把 O16（action/files）设为 O06 实施硬前置；但同段又写"O16 若已先行集成，后两项逐次重读实际…"并以条件句处理"若实施 HEAD 已通过 O16 建立统一 pipeline 准入调用点，复用该点"——两种顺序都被预料到，却仍固定 O16 先行。
- **反例/失败场景**: O16 无 plan、无排期（repair-sequence 2026-09-28 状态："其它 work unit 未开始"）→ 即便 O05/O17 已集成，已证实的 241 直通缺口仍被无限期阻塞。O06 的校验（`len(name.strip())`）与 action/files 无功能依赖；plan 自述的条件句证明 O16 未集成时在既定插入点落子、O16 后续复用/挪动即可，并不需要 O16 先行。
- **为什么有问题**: 裁决登记第 3 行只写"O05 必填与 O17 form canonical 是前置依赖"；repair-sequence 把 O05/O06/O07/…/O17 并列为"请求与身份真源"组，唯一硬顺序是 O16 先于 O14/O15。plan 单方面加码前置，属于以实现中预见的协调风险升级为硬 gate，又未给出"O16 不先行则何处必然坏"的具体反例。
- **直接证据**: plan 第 22 段；`upload-material-o06-plan-review-adjudication-20260929.md` 第 3 行；`upload-material-issue-198-repair-sequence-20260928.md` 第 12/25 行。
- **影响**: 风险闭环后移（241 入口缺口继续敞口）；O06 进度被正交 work unit 绑架。
- **建议改法和验证点**: 把 O16 前置改为条件性——仅当 O16 裁决确认将建立统一 pipeline 准入调用点时串行等待，否则 O06 在 O05+O17 集成 HEAD 上实施并在 O16 后续集成时复核；或补充"O16 必须先行"的具体失败反例。验证点：无。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F04-未修复-[低]-usage message 文案内容未被验收矩阵钉住，LLM-facing 自足性可能不达标

- **位置**: plan 第 14 段（"同源中文 usage message"）；矩阵第 38/40/43 行（只断言"同一中文 message"）
- **问题类型**: 测试缺口 / LLM-facing 语义
- **当前写法**: plan 要求封闭 code `MATERIAL_NAME_TOO_LONG` 与"同源中文 usage message"，矩阵断言各入口 message 一致，但从未规定 message 必须包含的语义内容。
- **反例/失败场景**: 实现写"材料名称过长"也能通过全部矩阵断言，但 message 未说明 240 上限、strip 后计数口径与修复动作；tool schema 更新了规则描述，但 LLM 真正读到修复依据的是出错时的 message——不自足则 LLM 猜测口径（按字节/按字形），行为不稳定。
- **为什么有问题**: AGENTS.md LLM-facing 约束要求关键规则写在当前 LLM-facing 输入中、可行动、自足；错误 message 是 LLM 纠错路径上的唯一规则载体时尤甚。plan 对 schema 描述内容钉得精确（"去首尾空白后最多 240 个 Unicode 码点"），对 message 却只钉"同源"。
- **直接证据**: plan 第 14/38/42 行；`FinsUploadUsageFailure` 仅约束 message 非空且 ≤240 字符（`ingestion_runtime.py:719-740`），不约束内容；tool 失败路径回传 `str(exc)`=message（`upload_tools.py:117-124`）。
- **影响**: LLM-facing 语义弱化；后续补文案需再开测试变更。
- **建议改法和验证点**: 矩阵增加 message 内容断言（含"240"、strip/码点计数口径、可行动指引三要素），或 plan 直接给出封闭文案作为验收基线。验证点：断言 message 匹配约定要素。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F05-未修复-[低]-`upload_filings_from` 批量入口的文件名派生名称与新上限的交互未纳入评估

- **位置**: plan 第 6 段入口盘点（只列 `fins.py`/`fins_direct.py`/`upload_tools.py` 与两个 workflow）；白名单与矩阵未提 `dayu/fins/upload_batch.py`
- **问题类型**: 范围漂移（盘点不完整）/ open question 未收敛
- **当前写法**: plan 声称入口盘点完整（"入口在 dayu/cli/commands/fins.py、dayu/service/fins_direct.py、dayu/fins/tools/upload_tools.py"），并以"各入口的既有投影不由 O06 重定义"覆盖输入投影；但未提及批量命令的名称派生投影。
- **反例/失败场景**: `upload_filings_from` 用 `_derive_material_name()`（`upload_batch.py:590-609`，`f"{prefix} {rest}"` 会加 prefix+空格，长于文件名词干）从文件名派生名称，写入生成脚本的 `--material-name`（`fins.py:415`）。APFS 文件名可达 255 UTF-8 字节，纯 ASCII 词干即可派生 >240 码点名称 → 批量脚本生成成功、执行时逐条在 admission 报 `MATERIAL_NAME_TOO_LONG`。这不是绕过（admission 仍统一拒绝），但"生成成功、执行失败"的用户可见行为变化未在残余风险或 README 决策中登记。
- **为什么有问题**: goal 要求"对 direct/job/tool 等公开入口统一拒绝超限输入"并核对真实 CLI 工作流；批量生成脚本是最终用户工作流的一部分（根 README 触发条件含"最终用户工作流"）。plan 对该交互零表述，实现后 README"当前真实 CLI 限制"可能漏写，或后续有人在 batch 侧加截断（下游补偿）来"修"它。
- **直接证据**: `upload_batch.py:573-609`；`fins.py:355-358/400-418`（entry→argv 机械投影含 `--material-name`）；plan 第 6/12/48 段。
- **影响**: 用户可见行为变化未登记；未来错误修复方向（下游截断）风险。
- **建议改法和验证点**: 在 plan 残余风险登记该交互并把跟踪去向指向文件名/`UM-O04/O23` owner（名称派生是其语义域），同时在 README 决策行注明批量脚本限制口径；不改 `upload_batch.py`（保持白名单纪律）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- **Q1（goal 停止条件的形式满足）**: goal 停止条件要求"direct/job/material ID 使用不同规范化结果"被证实时"plan 明确唯一 canonical 名称 owner"。代码事实确有多套结果：ID seed 用 strip（`docling_upload_service.py:1843`）、job 摘要用 strip（`_bounded_text` 返回 strip 文本）、事件/meta/manifest 保留 raw（`sec_upload_workflow.py:510/552`）、CLI/tool 入口先 strip。plan 已逐点声明这些既有语义维持原样（第 12/43 段）并把身份契约留给 O07，行为本身是钉死的、可测的；但"唯一 canonical 名称 owner"这句对**名称值**的 owner 点名（应在 `build_material_ids` seed 归一化 / O07 契约）是隐式的。建议 plan 或 O07 goal confirmation 补一句显式声明，避免实施/review 在措辞上争议。不构成独立 finding 的原因：矩阵已把 raw 保留、摘要一致、无归一化全部钉为可验收断言，实现跑偏空间已被封死。
- **Q2**: 若裁决选择"workflow 只装长度叶子"（F01 的路径 A），则 workflow 空名错误语义归 O05 还是保持 `build_material_ids` 现状，需要 O05 goal confirmation 显式回答；O05 当前无任何 plan/goal artifact。
- **Q3**: `"  "+"A"*240+"  "` 与 `"A"*240"` 同 seed 同 ID、但 raw meta 不同——既有身份语义（strip seed）下的既存现象，plan 未在矩阵显式断言"padded 与 unpadded 同 ID"。建议 O07 身份裁决覆盖，或矩阵补一行把该现状钉为已知契约。
- **Q4**: `_MAX_TEXT_CHARS`（摘要通用界）与 `_MAX_MATERIAL_NAME_CODEPOINTS`（业务界）双常量并存，plan 明确不复用（正确，避免 job 摘要常量冒充业务规则）；代价是两处 240 未来可漂移。由于 admission 先行、摘要界对名称不可达，风险为零级；若未来调业务上限，摘要界将对直达 `_upload_request_summary` 的路径失配。建议在摘要 owner 处留一行注释/测试提示即可，无需本次动作。

## Residual Risks 与跟踪去向

| # | 残余风险 | 跟踪去向 |
| --- | --- | --- |
| R1 | O05/O17/O16 均未开始（repair-sequence 2026-09-28 状态），O06 实施被多重前置阻塞，241 直通缺口持续敞口 | 总控 repair-sequence 队列；O06 gate 顺序裁决（与 F03 一并裁决） |
| R2 | 真实 CLI 转换依赖（Docling 等）不可用时，成功读回验证降级为环境失败记录 | plan 已定处置（记录原命令/退出码/未验证项，不以单元测试替代）；S1 完成报告 |
| R3 | `service_runtime.py:223-226` 晚期 None guard 与 `build_material_ids` 空值 ValueError 构成重复必填判断（admission 合流后成为第二套语义） | O05 work unit（或独立清理裁决）；O06 不动（白名单纪律正确） |
| R4 | batch 文件名派生超长名交互（F05） | `UM-O04/O23` 文件名 work unit + 根 README 用户工作流说明 |
| R5 | 隔离 checkout 无 `.venv`，本审查未运行测试/pyright（非目标）；plan 命令门槛已要求实施前建真实 3.11 环境 | plan《命令门槛》已覆盖；S1 完成报告验证 |

## 结论

**pass-with-risks**。

- 动机、阈值来源（用户裁决 240 码点，非 241 样本或摘要常量倒推）、唯一 owner 选点、失败时机（三条 runtime 入口在 producer/job/handle 与一切写入前拒绝；workflow 插入点在 `try`/`build_material_ids`/任何读写之前，typed 错误可逃逸泛异常收口）、白名单纪律（禁 downstream 补偿、禁 `maxLength`、禁 wrapper）、验证设计（typed code 断言、mock 不得预拒、文件树前后快照、真实 CLI 双流与读回）均经代码直接证据核实成立，无动机夸大、无 goal drift、无过度设计。
- 2 项中级 finding（F01 workflow 空值语义分叉风险、F02 joint-invalid 错误优先级未定义）属于规格缺口而非结构错误：均可在 plan 文本内以数句规格 + 矩阵行收敛；建议在进入 implementation gate 前先修 F01/F02，F03-F05 可随裁决顺带处理。
- 在 F01/F02 收敛后，该 plan 足够 code-generation-ready 交给 implementation agent。
