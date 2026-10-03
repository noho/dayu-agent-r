# Code Re-review（UM-O04/O23 S1 最终修复候选）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]

CANARY=mimo-112adb9b

## Scope

- Mode: current changes（`$deepreview 当前改动`，对 F1–F7 修复后候选的独立 re-review）
- Branch or PR: `codex/upload-material-assets`（UM-O04-F01 + UM-O23-F01 单一实施切片 + 两轮 review fix，未提交）
- Base: 基线 HEAD `1453a659a79d4c9a93838412dfdecfa7feeddf98`（`git rev-parse` 复核）；tracked `git diff --binary` SHA-256 `07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666`（`shasum -a 256` 复核与任务锁定一致）
- Output file: `docs/reviews/code-rereview-assets-s1-mimo-20260929.md`
- Included scope: `git status --short` 全量实读（不只按 tracked SHA 判断）——33 个 tracked 修改文件（16 个生产文件 + 4 个 README + 13 个测试文件）与 11 个未跟踪候选文件：3 个新 owner 模块（`dayu/fins/upload_asset_plan.py`、`upload_usage_contract.py`、`storage/asset_filename_contract.py`）、3 个新 owner 测试、4 个 gateflow artifact（implementation / adjudication / fix / fix2）、1 个首轮 review `docs/reviews/code-review-20260929-114318.md`。
  - 文档链实读：`AGENTS.md`、accepted goal、accepted plan、首轮 review、总控裁决、fix、fix2、implementation 记录（含指纹措辞纠正段）、4 个 README diff。
  - 生产走读：三个新 owner 模块全文；`ingestion_runtime.py`（handoff/`__post_init__`/admission/`_normalize_upload_request`/`_validate_runtime_upload_request`/`_upload_request_summary`/`_run_upload_job`/path helper 迁移）、`docling_upload_service.py` diff 全读（plan 消费、filing identity 迁移、指纹公式）、`upload_failure.py` diff 全读（planner 分类、分组互斥完备、斜杠豁免）、`sec_upload_workflow.py` 全文、`sec_pipeline.py`/`cn_pipeline.py`/`service_runtime.py`/`fins_direct.py`/`cli/commands/fins.py`/`tools/upload_tools.py`/`observation_handle.py` diff 全读、storage 三 walker diff 全读、`_filing_upload_fresh_validation.py`/`filing_upload_publication.py` import 迁移核对。
  - 测试面：`test_upload_asset_plan.py` 全文、`test_upload_usage_contract.py` 关键用例全文、`test_storage_asset_filename_contract.py` 全文、handoff/admission/身份/斜杠豁免/长标签/真实 CLI 子进程用例全文、`test_fins_storage_atomicity.py`/`test_fins_ingestion_tools.py` diff 结构级核对。
  - 真实 CLI 证据实读：`/private/tmp/dayu-upload-real-cli-20260929/{hundred_one,hundred_observe,hundred,small_final,missing}` 的 `evidence.json`（含 `small_final` after_tree/read_snapshot/manifest、`missing` 两例逐字 stderr）。
- Excluded scope: 无（本切片未触碰 `dayu/render/`、`utils/`）。O25 primary 选主、O34 公司 meta 时序、O16 delete+files 动作规则、`fins-material-file-existence-admission` 为 goal/plan/裁决明确非目标。
- Parallel review coverage: 无 subagent（任务明确禁止派发子 Agent）；全部走读、探针与验证由本 reviewer 独立完成。

## 独立验证（本 reviewer 复跑，非引用修复记录）

| 项 | 命令/证据 | 结果 |
| --- | --- | --- |
| 完整受影响矩阵（fix2 同款 21 文件） | `python -m pytest … --cov=dayu.fins --cov=dayu.service.fins_direct --cov=dayu.cli.commands.fins -q` | **1448 passed, 1 skipped, 3 warnings, exit 0**，与 fix2 记录逐字一致 |
| pyright | `python -m pyright` | 0 errors / 0 warnings / 0 informations |
| import smoke / 无环 / 控制名集合 | plan 指定两条 `python -c`，含 `DOCUMENT_SOURCE_CONTROL_FILENAMES == frozenset({"meta.json", ".identity.json"})` | exit 0 |
| 19 个改动生产文件逐文件 coverage | `python -m coverage report --include=<file> --fail-under=80` 逐一执行 | 19/19 ≥80%，最低 86%（`_fs_source_integrity.py`、`cli/commands/fins.py`、`sec_pipeline.py`）；新 owner 91/94/100% |
| `git diff --check` | | exit 0 |
| 旧符号对账 | `rg`：`_build_filing_(original|derived)_asset_identity`、`_fins_upload_path_identity`、`_normalize_fins_upload_path`、`FinsUploadMaterialFiles`（两 workflow）、`files=list(request.files)` 展开 | 全部零命中；usage 类型无经 `ingestion_runtime` 的导入（AST 扫描），`ingestion_runtime.__all__` 无 usage re-export |

**聚焦反例（本 reviewer 在本 checkout 直接探针，全 typed、无裸 ValueError、消息 ≤240、无路径泄漏）**：

1. 长 UTF-8 basename（`"名"*230+".txt"` 双目录重复）→ `duplicate_original_basename`，消息恰 240 字符，首尾片段+省略号，`.txt` 尾部可见。
2. canonical 隐藏标签（控制字符 basename `deck\x01.pdf`）→ 消息嵌 `输入文件（文件名已隐藏）`，28 字符。
3. >240 字符 basename（`"b"*241+".txt"`）→ 同上隐藏标签安全退化，不裸抛。
4. 恰 240 字符 label（`"c"*236+".txt"`）→ 裁剪后完整消息恰 240。
5. 分类顺序无关性：`[a.txt, a.txt_docling.json, META.JSON]` 与逆序均为 `reserved_control_name`（两遍式分类生效）。
6. UTF-8 字节超限（`"名"*85+".txt"`）→ `invalid_asset_name` 带完整标签，110 字符。
7. F7：不同 tuple 对象、值相等构造成功；逆序值不等拒绝（"material converter plan 必须与原件计划同源"）。
8. 100 全量入计划（converter_pairs 恰 100、保序）；101 → typed `TOO_MANY_FILES`。
9. 同源：planner error 的 usage message/hint/label 与 `fins_upload_failure_from_exception` 产物逐字段相等，kind=USAGE。
10. O16 边界：delete 携 3 个 files 被 handoff 接受（raw files 保留、selection/plan 为空）——F1 修复未偷渡 O16。

## F1–F7 修复复核结论（真实根因/修法逐项）

- **F1（handoff 跨字段不变量）**：根因属实——原 `ValidatedFinsUploadMaterialRequest` 三字段无 `__post_init__`。修法在 owner 类型边界补齐：类型/source kind/无 filing primary/`converter_pairs` 保序值相等/upsert 路径三方保序一致/original+derived 身份与 planner 函数一致/delete ⇔ 空 selection+空 plan（`ingestion_runtime.py:1412-1456`）。**未偷改 O16**：delete 分支注释与实现均不检查 raw `files`，探针 10 证实 delete+files 原样通过；owner 测试 `test_validated_material_handoff_rejects_cross_field_drift` 显式断言 `deleted.request.files == paths`。与裁决“不能借此片偷偷引入 delete+files 业务拒绝”一致。
- **F2（canonical 标签进入 usage 投影）**：根因属实——四个新 planner code 原文案无文件标签、工厂禁止传 label。修法在唯一文案 owner `_USAGE_MESSAGES` 模板嵌 `{file_name}` 并由 `_FILE_USAGE_CODES`（`upload_usage_contract.py:114-123,133-136`）携带 `error.file_label`；三个复用 code 与旧 CLI 缺失文件模板逐字未动。
- **F6（240 消息预算）**：根因属实——label 上限 240 与消息上限 240 同值，模板前后文未扣预算。修法 `_bounded_file_usage_message`（`upload_usage_contract.py:163-195`）按模板前后文计算标签预算、超长保首尾+省略号、隐藏标签天然适配；`FinsUploadUsageFailure.__post_init__` 的 240 不变量兜底。四个新 code 均经同一 helper，CLI/tool 下游零兜底。探针 1–4 证实长 UTF-8、隐藏标签、恰 240 边界全部有界闭合；**与 public failure 同源**由 `upload_failure.py:246-256` 消费 `fins_upload_asset_plan_usage_failure` 同一 message/hint/label 保证，探针 9 逐字段相等。
- **F3（指纹/skip 文档事实）**：根因属实——material 指纹 payload 仅原件 `name/sha256/size/source`（`docling_upload_service.py:1663-1674`），派生名不入式。实施记录 :111 与 `dayu/fins/README.md` 已改为“派生名不参与、同内容同原件名重传仍 identical-skip”，并保留 symlink/规范化原件名漂移披露；README 不再误述“原件名改用完整 basename”（改为“仍使用”）。
- **F4（死导入）**：`rg` 证实两 workflow 的 `FinsUploadMaterialFiles` 导入与旧 scalar 构造全部消失。
- **F5（admission 单次/对象身份）**：SEC/CN `admits_once` monkeypatch 计数（`test_sec_pipeline_upload_material_stream.py:583-660`、`test_cn_pipeline.py:2687-2760`）、runner `is` 身份（`test_fins_service_runtime.py:700-722`）、Service `is` 身份（`test_fins_direct.py:769-772`）均落地；斜杠豁免负例（`test_upload_failure.py:30-65`）钉住仅 MISSING_FILES 固定文案放行；陈旧测试名已改为实际行为。
- **F7（tuple 身份 → 保序值等价）**：修法 `plan.converter_pairs != plan.ordered_pairs`（`ingestion_runtime.py:1437`）为保序值比较；测试覆盖“不同 tuple 对象值相等成功 + 逆序拒绝”，探针 7 复证。
- **filing 双输入校验**：`plan_upload_assets` filing 分支显式拒绝 `files != filing_selection.ordered_files`（`upload_asset_plan.py:227-228`）；合法输入的 digest 身份算法逐字迁移（namespace/`b"\0"`/完整 SHA-256/小写 suffix），`test_filing_identity_and_derived_mapping_keep_existing_bytes` 钉住字节级公式与 primary/converter 对应；四个测试文件导入已改向新 owner，旧函数零残留。

## Findings

### 001-未修复-低-混合批次 reason 分类的顺序无关性缺少回归锚
- **入口/函数**: `plan_upload_assets` material 命名分类（`dayu/fins/upload_asset_plan.py:266-293`）；测试面 `tests/fins/test_upload_asset_plan.py:112-149`
- **文件(行号)**: `dayu/fins/upload_asset_plan.py:286-293`（两遍式分类注释与实现）；对照 `tests/fins/test_upload_asset_plan.py:112-122`（parametrize 均为单原因、固定输入序）
- **输入场景**: 同一请求同时携带业务资产碰撞与控制名（如 `a.txt` + `a.txt_docling.json` + `META.JSON`）并以两种输入顺序提交。
- **实际分支**: 第一遍逐文件控制名分类（遇控制名即抛 `RESERVED_CONTROL_NAME`），第二遍才做保守键碰撞（`ASSET_NAME_COLLISION`）；实现注释明言“整批先完成控制名分类，再判断业务资产互撞，避免输入顺序改变原因”。
- **预期行为**: plan 验证矩阵（`upload-material-assets-plan-20260929.md:68`）把“分类不随遍历顺序变化”列为 owner 级断言项，应有混合批次正逆序同 reason 的回归锚。
- **实际行为**: 行为正确——本 reviewer 探针 5 证实两种顺序均得 `reserved_control_name`；但现有测试只钉单原因用例与成功路径的正逆序（`test_material_full_basename_mapping_and_order`），无混合批次反序断言，未来把两遍分类改回单遍循环不会被测试拦截。
- **直接证据**: `rg` 全测试目录无同时含 `META.JSON` 与交叉碰撞名的用例；parametrize 最大输入为 2 文件且原因单一（`test_upload_asset_plan.py:115-121`）。
- **影响**: 仅回归防护缺口（无现行错误行为）；分类顺序漂移会改变 LLM/CLI 可见 closed reason，属用户可观察语义。
- **建议改法和验证点**: 在 `test_material_rejects_name_conflicts_before_conversion` 增补一组 3 文件混合批次正逆序参数，双向断言 `RESERVED_CONTROL_NAME`；验证点：新用例 + 全矩阵回归。
- **修复风险（低/中/高）**: 低（纯测试增量）。
- **严重程度（低/中/高/严重）**: 低。

### 002-未修复-低-长标签 usage 预算测试仅覆盖 ASCII，长 UTF-8 与 canonical 隐藏标签路径无专测
- **入口/函数**: `_bounded_file_usage_message`（`dayu/fins/upload_usage_contract.py:163-195`）与 `fins_upload_asset_plan_usage_failure`（`:259-281`）；测试面 `tests/fins/test_upload_usage_contract.py:253-306`
- **文件(行号)**: `upload_usage_contract.py:180-195`（按 `len()` 码点计预算）；`tests/fins/test_upload_usage_contract.py:282`（唯一长标签样本 `basename = "a" * 222 + ".txt"` 为 ASCII）
- **输入场景**: 多字节 basename（如 `"名"*230+".txt"`）触发裁剪；或 basename 命中 canonical 隐藏规则（Cc/Cf 或 >240 字符）投影固定隐藏标签。
- **实际分支**: 预算与上限均按 Python 码点计数，裁剪为纯函数；隐藏标签 11 字符直接放行。
- **预期行为**: F6 的风险面恰是“240 是字节还是码点”的单位错配；plan 要求标签“有界、路径安全、用户可修正”，裁剪/隐藏须由同一 helper 稳定完成——多字节与隐藏标签是该 helper 的边界输入，应有专测钉住单位语义与隐藏标签可读性。
- **实际行为**: 行为正确——探针 1–4 证实长 UTF-8 消息恰 240 码点、隐藏标签文案完整、无裸 `ValueError`；但 4 个长标签参数化用例与真实 CLI 子进程用例全部只用 ASCII 标签，隐藏标签（`_HIDDEN_PUBLIC_FILE_LABEL`）进入 usage 文案的组合无任何测试。
- **直接证据**: `rg '文件名已隐藏|名" \*' tests/fins/test_upload_usage_contract.py tests/cli/test_fins_commands.py` 零命中；`test_long_planner_file_label_preserves_closed_bounded_usage` 的 basename 常量为 `"a"*222+".txt"`（`:282`）。
- **影响**: 仅回归防护缺口（无现行错误行为）；单位语义或隐藏标签路径被改动时无测试拦截，可能重现 F6 类裸抛或超界文案。
- **建议改法和验证点**: 在 `test_upload_usage_contract.py` 增加多字节长标签（断言 `len(message) == 240` 且含省略号/尾缀）与 Cc basename（断言消息含 `输入文件（文件名已隐藏）`、≤240、路径安全）两组用例；验证点：新用例 + usage owner 测试回归。
- **修复风险（低/中/高）**: 低（纯测试增量）。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

- `fins_upload_failure_from_exception` 与 `fins_upload_asset_plan_usage_failure` 的调用方固定传 `max_files=MAX_MATERIAL_UPLOAD_FILES`（`upload_failure.py:246-250`、`ingestion_runtime.py:1489-1491`），隐含“`FinsUploadAssetPlanError` 只可能来自 material”这一前提。当前 planner 仅 material 分支抛该错误，前提成立；若未来 filing 分支扩展出数量类 planner error，`TOO_MANY_FILES` 文案会静默使用 material 上限。是否把上限作为 planner error 的携带参数或在 reason 上标注来源，留待 owner 裁决，不计本片 finding。

## Residual Risk

- **既有登记残余（accepted plan/裁决范围，未变化）**：保守 `NFC+casefold+NFC` 键可能多拒且不证明所有平台 alias；目标卷 `NAME_MAX<255` 时可能触仓储最终错误；admission 后 TOCTOU 由 storage 完整性防线兜底；O25 primary 选主（当前首转换文件为 primary 仅为现状）、O34 公司 meta 早于 source batch、O16 delete+files 动作规则、`fins-material-file-existence-admission` 跨入口存在性 typed 统一、filing/material 上限未来分离时共用 schema/文案重审。
- **delete+files 跨事件计数语义**（首轮 review OQ，裁决 O16 deferred）：material delete 携 files 时 raw `request.files` 仍进入 `_upload_request_summary`/progress 的 `file_count`（`ingestion_runtime.py:7721`、`:8110`），而 workflow `UPLOAD_STARTED` 用 selection 计 0（`sec_upload_workflow.py:460`）。本片 F1 修复按裁决未改动作合同；两口径差异留待 O16 一并澄清。
- **真实 CLI 证据界限**：101 侧（exit 2 / converter 0 / 零发布）、100 侧（1 次真实 converter 启动后 SIGINT 取消）、小 N 同 stem（2+2 完整发布、primary=`deck.txt_docling.json`、970 字节读回）均为首轮实施候选的证据；F1–F7 修复未改数量模板/指纹/发布路径（三个复用 usage 文案逐字未动），fix2 在当前候选补跑了长同名 basename 真实 CLI 子进程（exit 2、零发布、无 traceback）。100 次真实转换/完整发布由受控 converter 测试（`test_material_hundred_inputs_schedule_hundred_controlled_converter_calls`）承担，符合 plan 分级验收，不可升格解读；`hundred` 目录为 timeout（exit 124）不可作转换证据。修复后未重跑 101/小 N 真实 CLI，若要求当前候选自带全部真实 CLI 证据，需补跑。
- **环境偏差**（修复记录已披露）：`.venv` 经 `dayu_shared_dependencies.pth` 复用主仓 site-packages，不代表独立依赖安装验证；pyright v1.1.409（提示可升 v1.1.414）。
- **测试走读深度**：`test_fins_commands.py`、`test_cn_pipeline.py`、`test_docling_upload_service.py`、`test_sec_pipeline_upload_material_stream.py` 为关键用例全文 + diff 结构级核对，未逐行覆盖全部测试 diff；以本 reviewer 独立复跑 1448 绿作为行为回归兜底。
- **斜杠豁免耦合**（首轮 residual）：`_validate_failure_reason_text` 的 MISSING_FILES 例外以 `field_name == "failure.message"` 字符串与动态同源文案比对为前提（`upload_failure.py:557-565`），字段名漂移会使旧文案被拒；现有负例已钉住双向边界，耦合本身保留。

## 验证范围与结论

- F1–F7 全部为真实根因、修法落在 owner 边界，未发现语义所有权漂移或下游 fallback；O16/O25/O34 未被偷渡；filing 合法身份未漂移。
- 独立复跑 1448 passed/1 skipped、pyright 0、19/19 生产文件 ≥80%、import/无环 smoke、`git diff --check` 全绿；聚焦反例 10 组全部符合 closed/有界/路径安全/同源契约。
- 新发现 2 项均为低严重度测试回归锚缺口（行为实测正确），不阻断候选；建议在下一 gate 前顺手补测或由 controller 裁决 defer。
- 本 re-review 只对 tracked SHA `07281b59…` 与所列未跟踪文件内容这一候选版有效；Kimi 第二路同版 re-review 尚未完成，不构成 code gate pass。
