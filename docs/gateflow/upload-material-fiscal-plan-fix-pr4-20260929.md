# UM-O09/O10 第四轮 MiMo plan review 修订记录

- Gate：`plan review → fix`；对象：`docs/gateflow/upload-material-fiscal-plan-20260929.md`；复审基线 SHA-256：`5c3bbee5cd65d86cf92f90d5d977250264eabfbaf07a51a9d86b94c9c68e81a5`。
- 来源：`docs/reviews/plan-review-fiscal-rereview4-mimo-20260929.md` 两项 finding；`docs/gateflow/upload-material-fiscal-plan-review-adjudication-20260929.md` 的第四轮总控裁决及 O06 合流登记要求。
- 状态：仅计划修订候选；本记录不是 Kimi/MiMo 双路 plan review pass、实施授权或产品验证结果。

## 动机、裁决及修订

两项 finding 均有同源代码证据，修订必要。O09/O10 用户裁决将 fiscal 与 O07-F02 归于同一 material identity builder/validator；当前 `FinsUploadMaterialRequest`、`validate_material_upload_ids`、US/CN/HK workflow 及 tool schema 与 O07-F01 的公开 `internal_document_id` 移除有实际重叠。新 material 年份 usage message 会进入 tool 输出，缺少精确业务中立文案的测试约束会让新债务通过 review。O06 的早期裁决未定阈值，但 2026-09-29 用户后续明确采用去首尾空白后 240 个 Unicode 码点，隔离 goal 已据此通过；按后续裁决登记，不沿用第四轮 review 中“阈值未决”的旧状态。

| 项 | 对计划的修订与验收边界 |
| --- | --- |
| Fiscal-PR4-F1（中） | owner 段点明 O07-F02 与 fiscal 共用 identity builder/validator；residual 表和汇入实施检查登记 O07-F01/F02 的串行合并。canonical fiscal、form、name 先于稳定 ID；fiscal 与显式 `document_id` 同时非法时先报 fiscal typed usage，合法后才执行 `validate_material_upload_ids` 的一致性检查，O07-F02 保持字段级错误与零发布。逐处核对 `internal_document_id` 公开字段移除对 `FinsUploadMaterialRequest`、`replace(request, ...)`、CLI/Service、US/CN/HK workflow、ID validator 和 tool schema 同块改动的影响；不留第二套 admission 或兼容分支。本 WU 不实施 O07。 |
| Fiscal-PR4-F2（低） | 新 `INVALID_MATERIAL_FISCAL_YEAR` 文案定为“材料财年（fiscal_year）必须是 1800..2100 的整数”。owner usage 与 tool 错误投影测试逐字断言此句及 `"--" not in message`；filing 原文不变，其它既有 usage 文案仍归独立通道中立修复项。 |
| O06 合流登记 | 引用后续已确认的 `len(name.strip()) <= 240` Unicode 码点规则；同一名称 owner 在身份、source meta、LLM 投影前校验，O05 必填与 O06 长度同 admission 串行合并。本 WU 不复制 O06 实现、常量或独立测试。 |

共用 tool `fiscal_period` schema 的 filing 必填、material 可省略/`null`、两者空串/纯白参数层拒绝三分句保持；旧逐字 schema 测试迁移、O09/O10 值域、legacy residual、隔离 venv 与逐文件覆盖率计划均未改变。O16 action/files 已有优先级仍须在汇入时复核；计划只确定身份计算所需偏序，不替其它 work unit 宣称完整错误优先级。

## 核对与后续状态

修订前计划 SHA 与指定基线相符；HEAD 为 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。本轮仅修改本记录及目标计划，未运行实现测试、pyright、真实 CLI 或覆盖率：没有产品代码变更，计划中的这些命令属于后续 implementation gate。以修订后计划同一 SHA 进行有效 Kimi/MiMo 双路复审，并由总控裁决；本轮到此停止，不进入下一 gate。风险是 O05/O06/O07/O16/O17 的最终集成顺序与具体字段级 code 仍须在各自计划及集成 HEAD 上验证，旧非法 fiscal 身份的独立处置也未获裁决。

## 本轮命令与退出码

以下每行是一条实际执行的 shell 命令，重复读取也保留；**全部 exit 0**。两次 `apply_patch` 及本记录的补充 patch 均成功，属于文件编辑工具调用，没有 shell 退出码。所有命令工作目录均为 `/private/tmp/dayu-upload-fiscal`。

```text
01 pwd
02 cat AGENTS.md
03 cat /private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.hzYy0K/canary.txt
04 rg -n 'UM-O09|UM-O10|O07|O06|fiscal|upload.material' /Users/leo/.codex/memories/MEMORY.md
05 git status --short
06 shasum -a 256 docs/gateflow/upload-material-fiscal-plan-20260929.md
07 cat docs/reviews/plan-review-fiscal-rereview4-mimo-20260929.md
08 cat docs/gateflow/upload-material-fiscal-plan-review-adjudication-20260929.md
09 cat docs/gateflow/upload-material-fiscal-plan-20260929.md
10 rg -n 'O07|O06|material_name|fiscal|upload.material' docs/gateflow --glob '*.md'
11 cat docs/gateflow/upload-material-fiscal-plan-20260929.md
12 cat docs/gateflow/upload-material-fiscal-plan-review-adjudication-20260929.md
13 cat docs/gateflow/upload-material-fiscal-goal-20260929.md
14 rg --files /Users/leo/workspace/dayu-agent-r/docs/reviews | rg 'upload-material-um-o(01-o06|07|09|10)-oracle-adjudication\.md$'
15 cat /Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o07-oracle-adjudication.md
16 cat /Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md
17 cat /Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o09-oracle-adjudication.md
18 cat /Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o10-oracle-adjudication.md
19 sed -n '140,225p' docs/reviews/plan-review-fiscal-rereview4-mimo-20260929.md
20 git branch --show-current
21 git rev-parse HEAD
22 rg -n 'UM-O06|240 Unicode|Unicode 码点|去空白后|strip.*240|240.*strip' /Users/leo/workspace/dayu-agent-r/docs/gateflow /Users/leo/workspace/dayu-agent-r/docs/reviews --glob '*.md' -m 4
23 rg -n '^(### 02|## (结论|建议|Residual)|- \*\*位置\*\*|fins-upload-usage-message-channel-neutral|O06)' docs/reviews/plan-review-fiscal-rereview4-mimo-20260929.md
24 rg -n 'FinsUploadMaterialRequest|INVALID_FISCAL_YEAR|_USAGE_MESSAGES|_normalize_upload_request|admit_fins|_validate_runtime_upload_request|replace\(request|internal_document_id' dayu/fins/ingestion_runtime.py
25 rg -n 'build_material_ids|validate_material_upload_ids|_normalize_optional_upload_fiscal_period|material_name|internal_document_id' dayu/fins/pipelines/docling_upload_service.py
26 rg -n 'internal_document_id|fiscal_year|fiscal_period|FinsUploadMaterialRequest|_optional_nullable_text|_required_text' dayu/fins/tools/upload_tools.py dayu/fins/tools/_ingestion_tool_helpers.py
27 sed -n '250,265p' /Users/leo/workspace/dayu-agent-r/docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md
28 cat /private/tmp/dayu-upload-o06/docs/gateflow/upload-material-o06-name-length-goal-20260929.md
29 sed -n '74,105p' docs/reviews/plan-review-fiscal-rereview4-mimo-20260929.md
30 sed -n '680,705p;1020,1050p;1540,1580p;7690,7720p' dayu/fins/ingestion_runtime.py
31 sed -n '1820,1892p' dayu/fins/pipelines/docling_upload_service.py
32 sed -n '225,285p;328,365p' dayu/fins/tools/upload_tools.py
33 rg -n -C 5 'build_material_ids|validate_material_upload_ids|fiscal_year|fiscal_period|internal_document_id' dayu/fins/pipelines/sec_upload_workflow.py dayu/fins/pipelines/cn_pipeline.py
34 sed -n '4705,4765p;7694,7718p' dayu/fins/ingestion_runtime.py
35 sed -n '455,495p' dayu/fins/pipelines/sec_upload_workflow.py
36 sed -n '1080,1110p' dayu/fins/pipelines/cn_pipeline.py
37 sed -n '1027,1056p' dayu/fins/ingestion_runtime.py
38 sed -n '1705,1745p' tests/fins/test_fins_ingestion_tools.py
39 shasum -a 256 docs/gateflow/upload-material-fiscal-plan-20260929.md docs/gateflow/upload-material-fiscal-plan-fix-pr4-20260929.md
40 git status --short
41 rg -n '第四轮|唯一语义 owner|INVALID_MATERIAL_FISCAL_YEAR|fiscal_period.*schema|S1 测试契约|UM-O06-F01|UM-O07-F01/F02|Residual：|venv|覆盖率' docs/gateflow/upload-material-fiscal-plan-20260929.md
42 cat docs/gateflow/upload-material-fiscal-plan-fix-pr4-20260929.md
43 python3 -c 'from pathlib import Path; p=Path("docs/gateflow/upload-material-fiscal-plan-20260929.md"); q=Path("docs/gateflow/upload-material-fiscal-plan-fix-pr4-20260929.md"); a=p.read_text(); b=q.read_text(); assert a.count("材料财年（fiscal_year）必须是 1800..2100 的整数") == 2; assert "\"--\" not in message" in a; assert "UM-O07-F01/F02" in a and "UM-O06-F01" in a; assert "filing 分句明确财期必填" in a and "material 分句明确财期可省略或传 `null`" in a and "空字符串或纯空白在 tool 参数层均以 `invalid_argument` 拒绝" in a; assert all(not line.rstrip(" \t").endswith(" ") for line in a.splitlines()+b.splitlines()); print("static plan assertions: pass")'
44 sed -n '302,321p' /Users/leo/.codex/memories/MEMORY.md
45 wc -l docs/gateflow/upload-material-fiscal-plan-20260929.md docs/gateflow/upload-material-fiscal-plan-fix-pr4-20260929.md
```
