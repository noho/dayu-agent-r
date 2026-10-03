# Code Review — UM-O20-F01 S1（MiMo 独立审查）

- RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro
- CANARY=mimo-6c3b7e9f

## Scope

- Mode: current changes（`$deepreview 当前改动`，审查对象为已实施未提交的 S1）
- Branch or PR: `codex/upload-material-o20`
- Base: HEAD `8c9e1d3473e5fd9c8e4509a38539a1a940140070`（accepted plan checkpoint）；goal 声明基线 `8d8d494f` 仅作背景，本次 diff 以 HEAD 为对照
- Output file: `docs/reviews/code-review-20260929-o20-mimo.md`（用户指定路径，覆盖 deepreview 默认 timestamp 命名）
- Included scope:
  - 工作树未提交 diff：`README.md`、`dayu/fins/upload_format_contract.py`、`tests/fins/test_upload_format_contract.py`、`tests/cli/test_arg_parsing.py`、`tests/fins/test_fins_ingestion_tools.py`
  - 未跟踪实施记录 `docs/gateflow/upload-material-o20-s1-implementation-20260929.md`（作为自述材料，结论均以当前代码与本 reviewer 自行验证为准，不采信其成功声明）
  - owner/CLI/tool/batch 代码走读：`dayu/fins/upload_format_contract.py`、`dayu/cli/arg_parsing.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/upload_batch.py`、`dayu/documents/docling_runtime.py`、`dayu/fins/ingestion_runtime.py`、SEC/CN/Docling pipeline 消费点
  - 测试走读与实跑：plan 指定七文件；另全库检索格式文案冻结点
  - 输入文档：goal `docs/gateflow/upload-material-o20-format-help-goal-20260929.md`、accepted plan `docs/gateflow/upload-material-o20-format-help-plan-20260929.md`、裁决 `docs/gateflow/upload-material-o20-plan-review-adjudication-20260929.md`、`AGENTS.md`
- Excluded scope:
  - `docs/reviews/code-review-20260929-o20-kimi.md`（Kimi 同轮 review，全程未读，保持独立）
  - `docs/reviews/code-review-20260929-030106.md`（会话开始前已存在、归属不明的 review，未读）
  - `dayu/documents`、转换运行时、依赖装配的产品改动（F01 非目标，diff 中亦无）
  - XBRL 端到端能力补证（独立 `UM-O20-E01`/`UM-O20-F02`，不在本切片裁决）
- Parallel review coverage: 无 subagent（任务禁止派发）；全部走读与验证由本 reviewer 自行完成
- Review 结论: **pass-with-risks**（无未修复 finding；残余风险均已登记且不阻塞放行）

## Findings

未发现实质性问题。

### 对抗性检查记录（已证伪的攻击面，非 finding）

1. **固定两句逐字性**：plan/裁决指定的固定两句（`.json` 仅是 Docling 格式的 JSON 文档候选，不代表任意 JSON 内容可转换。`.xml/.xbrl` 仅是 XBRL 财报实例文档候选，不代表任意 XML 或独立 linkbase 文件可转换。）与 `upload_format_contract.py:630-631` 运行时投影逐字一致（脚本比对 `plan_quote_matches_fixed: True`、`fixed_in_material_verbatim: True`、出现次数 1、连写无额外空格、位置在「后缀通过只表示具备转换资格，不保证文件内容转换成功。」与「delete 不得提供文件。」之间）。
2. **filing/capability 不变**：以 `git show HEAD:dayu/fins/upload_format_contract.py` 动态执行对照，`filing_files`、`filing_primary`、`upload_tool_primary`、`upload_tool_material_primary_failure` 全部逐字不变；`material_rest_preserved: True`（当前 material 文案删除固定两句后与 HEAD 逐字相同）；`DOCLING_CONVERTER_CAPABILITY`（`dayu/documents/docling_runtime.py:222-234`）与 `FINS_UPLOAD_FORMAT_CAPABILITY` 在 diff 中零改动；生产 diff 仅 `material_files` 三行文本。
3. **唯一格式说明 owner**：全库检索确认格式说明唯一产生点是 `project_fins_upload_format_text`（`upload_format_contract.py:589`）；`dayu/cli/arg_parsing.py:963` 消费 `FINS_UPLOAD_FORMAT_TEXT.material_files`，`dayu/fins/tools/upload_tools.py:241` 消费 `upload_tool_files`，`upload_batch.py:418` 仅消费 `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary` 做后缀准入（skip 原因为 typed `unsupported_suffix`，非内容格式规则）；SEC/CN workflow 与 `DoclingUploadService` 只消费 `FinsUploadMaterialFiles` typed selection；`dayu/ui`、`dayu/service` 无独立 material 格式文案。三个测试文件是仅有的文案冻结点，无旧形式残留（`rg "转换成功。delete 不得提供文件"` 零命中）。
4. **真实 CLI help 可读**：本 checkout `.venv` 实跑 `python -m dayu.cli upload_material --help`，`--files` 段完整保留有序后缀清单、转换资格警示、固定两句与 delete 规则；argparse 折行只落在空格处（「。.json 仅是 / Docling 格式的…」「。.xml/.xbrl 仅是 / XBRL 财报实例文档候选…」「delete / 不得提供文件。」），拼回即 owner 逐字文本，语义连续可读。`upload_filing --help` 的 `--files` 段与 HEAD filing 文案逐字一致。
5. **tool schema 同源**：本 checkout `.venv` 以隔离临时 workspace 实跑 `DefaultFinsRuntime.create(...).get_ingestion_runtime()` + `build_fins_upload_tool(runtime)`，真实 `files.description == FINS_UPLOAD_FORMAT_TEXT.upload_tool_files` 为 `True`；`upload_kind=material 时，{material_files}` 逐字包含（一次生成、组合复用，无下游复制）；`files.type=array`、`maxItems=100`、`primary.type=string`、`primary` 不在 required——参数类型/枚举/必填性不变。
6. **F01 不承诺有效 XBRL/JSON 必成功**：固定两句为「仅是…候选，不代表任意…可转换」非承诺句式；material 段不含「必成功/一定成功/保证转换成功」类片段（脚本检查通过）；diff 未触及依赖、capability、失败分类；README 新段同为非承诺表述。E01/F02 的 XBRL 能力问题未被本次文案暗示为已解决。
7. **测试不弱化、不固化偶然行为**：owner 测试（`test_upload_format_contract.py:305-341`）对 material 全文逐字相等断言（同时钉死固定两句插入位置），filing 预期未改；CLI 测试断言 `files_action.help == FINS_UPLOAD_FORMAT_TEXT.material_files`（owner 原文逐字）并按裁决口径对真实 argparse 格式化 help 做空白归一后断言完整 material 文本与固定两句顺序可见；tool 测试从真实构造 schema 断言 `files.description` 整体等于 owner 投影且 material 子段含固定三句连续片段。`_capture_help` 走真实 `build_parser()` + argparse help 渲染，非 mock 文案。
8. **越界检查**：diff 白名单与 plan 完全一致（见下），无 F02 顺手改动（未装依赖、未删 capability、未改 failure code）、无新公共 API/schema 字段/状态机/迁移、无下游 fallback 或兼容 shim。
9. **过度耦合检查**：CLI/tool/batch 均只依赖稳定投影或 capability，无跨层穿透；文案变更一次投影即服务三入口；测试断言 owner 级 contract（投影内容与组合形式），未出现要求多处同步修改的隐性字符串协议。
10. **分支/参数生效链**：本次仅文本插入，无新分支；`suffixes` 仍由 `capability.primary_suffixes` 机械投影（`upload_format_contract.py:604`），固定两句未引入后缀清单第二真源。

### diff 白名单核对

| 文件 | plan 白名单 | 实际 | 结果 |
| --- | --- | --- | --- |
| `dayu/fins/upload_format_contract.py` | 唯一允许生产文件 | `material_files` +3 行文本 | 一致 |
| `tests/fins/test_upload_format_contract.py` | 允许 | expected_material_text 更新 | 一致 |
| `tests/cli/test_arg_parsing.py` | 允许 | help 同源/归一断言补强 | 一致 |
| `tests/fins/test_fins_ingestion_tools.py` | 允许 | schema material 子段断言 | 一致 |
| `README.md`（根） | 允许（上传章节短说明） | 4 行 material 候选/非保证段，指向即时 CLI help | 一致 |
| 其它生产/测试/README | 禁止 | 无 | 一致 |

`git status --short` 另有未跟踪文档：实施记录（切片产物）与两份 review artifact（非实施写入，未读）。`git diff --check` 退出 0。HEAD 保持 `8c9e1d34`，未提交未推送。

## 验证证据（本 reviewer 在本 checkout `.venv` 自行复跑，非采信实施自述）

- **venv 身份**：`.venv` 存在于本 checkout；`python 3.11.15`，`sys.executable=/private/tmp/dayu-upload-o20/.venv/bin/python`，`dayu.__file__=/private/tmp/dayu-upload-o20/dayu/__init__.py`；`pip check` 无破依赖；docling 2.127.0 / pyright 1.1.409 / coverage 7.13.5；约束文件 SHA-256 实测 `lock-common-py311.txt=3a68c4af…b05e3`、`lock-macos-arm64-py311.txt=c8242535…41563`，与实施记录一致。
- **定向回归**：`python -m pytest -q` 七文件（owner/CLI/tool/batch/SEC material stream/CN/Docling upload service）→ `779 passed, 3 warnings in 12.30s`，退出 0（警告为 edgartools 废弃 API，与本切片无关）。
- **单文件覆盖率**：`coverage erase` + `coverage run -m pytest -q` 同七文件 + `coverage report --include='dayu/fins/upload_format_contract.py' --fail-under=80` → 退出 0，`165 Stmts / 12 Miss / 93% Cover`，≥80%。
- **pyright**：`0 errors, 0 warnings, 0 informations`，退出 0。
- **真实入口**：`python -m dayu.cli upload_material --help` / `upload_filing --help` 均退出 0，见对抗性检查 4；真实 tool schema 见对抗性检查 5。
- **文案机器比对**：plan/裁决/实施记录三份文档引用的固定两句与 owner 运行时文本逐字一致；filing 与 HEAD 逐字一致（见对抗性检查 1-2）。

## Open Questions

- 无。

## Residual Risk

- **R-F02（已登记独立项，不阻塞 F01）**：当前标准安装下完整 XBRL instance 转换能力待 `UM-O20-F02` 裁决；filing 文案缺 `.xbrl` 限定、filing「XBRL XML 候选」与 material「XBRL 财报实例文档候选」及「Docling JSON 候选」/「Docling 格式的 JSON 文档候选」术语不一致，裁决已交 F02 对所有公开入口清算。本切片 filing 逐字未动，该不一致面是既有状态而非本次引入。
- **R-E01（证据缺口）**：Docling JSON 正样本结论属 E01 记录环境，本切片未做端到端上传/抽取准确率验证；XBRL 不得记 validated success。
- **R-help 折行（plan R5，已接受）**：argparse CJK 折行上限仍在（如 filing help 的「仅原样保存 / 、不转换」断行）；本次 material 固定两句折行落在空格处，语义连续可读，formatter 修复明确不在 F01。
- **R-token 增量（plan R4，已接受）**：`upload_tool_files` 组合描述变长，LLM token 占用略增；schema 参数类型/枚举/必填性不变。
- **R-README 摘要漂移（低）**：根 README 新段是人工摘要（措辞与 owner 略异，如「后缀符合要求不保证文件内容转换成功」），语义忠实且以 CLI help 为权威指引，符合 plan 的 README 职责取舍；但其内容非机械派生自投影，owner 文案未来变更时需人工同步。
- **R-叙述文案与 capability 手工同步（既有模式，低）**：投影中「Docling 格式的 JSON 文档候选 / XBRL 财报实例文档候选」为叙述性描述，`JSON_DOCLING`/`XML_XBRL` 内部 format id 变更时需手工同步；filing 文案同模式既有，本次未扩大该模式的结构面。
