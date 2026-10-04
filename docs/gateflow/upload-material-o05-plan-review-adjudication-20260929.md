# UM-O05-F01 plan review 总控裁决

- Gate：plan review -> fix；workspace `/private/tmp/dayu-upload-o05`，branch `codex/upload-material-o05`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- MiMo 有效 review：`docs/reviews/plan-review-20260929-013658.md`；运行退出 0，Claude JSON `subtype=success`、`is_error=false`、`terminal_reason=completed`、canary `mimo-b2bfc0c7` 匹配，stderr 仅白名单模型名提示。结论 `fail`，三个可局部修的 finding。Kimi 因五小时额度 403 尚无有效本轮 plan review；双路 gate 未通过。
- Sol 初始 plan 派发虽有 `turn.completed`/canary，但四个 command execution 非零，按协议 `agent_status=failed`；plan 文件只作为候选独立审查，不把派发声明算 gate pass。

## Finding 和问题裁决

| 项 | 裁决 | 修复 owner 与验收 | 状态 |
| --- | --- | --- | --- |
| F1 中：CLI 单值空白 `--forms` 与共享逗号解析 helper 边界欠规格 | **accepted** | 只在 `_single_optional_form` 对 `values` 恰一个、原文不含逗号、`strip()==""` 的情况原样传 Fins owner；含逗号或多值仍走 `_normalized_text_tuple` 原结构校验，`_single_batch_material_form` 与共享 helper 不变。plan 固定缺值、`""`、`"  "`、`","`、`" ,"`、`"A,"`、`"A,B"` 的 owner/结构错误优先级及测试。 | 待 plan fix |
| F2 中：tool raw helper 让合法带空白值的事件/meta 漂移 | **accepted，选择保留合法值原投影** | adapter 只做原有 strip，不承担必填业务规则；由 `upload_tools.py` 模块级私有输入投影 helper 读取可空 raw text，再对非空字符串 strip，缺失/null 返回 None、空串/纯空白返回 `""`，交 Fins owner typed 拒绝；非字符串仍由 adapter 以原有类型错误拒绝。两字段共用该 helper，合法 `" 8-K "`/`" Deck "` 仍以无空白值进入 request、事件/meta；补缺失/空白/padded tool 断言。不得切换成原样 raw 投影，也不得在 adapter 自行抛业务必填错误。 | 待 plan fix |
| F3 低：runner 与 summary 测试夹具遗漏 | **accepted** | `tests/fins/test_fins_service_runtime.py` 两个旧请求补合法 form/name，保留 summary count 与 early-cancel 原断言；纳入受影响命令。测试不让非法 fixture 固化偶然的晚期行为，不修改生产 runner。 | 待 plan fix |
| Q1：owner 文案含 CLI 专用 `--forms`，同时进入 LLM tool error | **accepted（文本边界）** | 在唯一 Fins usage 文案处改为渠道中立且字段明确的中文，例如 `材料类型（form_type）不能为空`、`材料名称（material_name）不能为空`；CLI 用户可通过 command help 对应参数，tool 模型依 schema 的同名参数行动。精确 owner 文案测试按定稿断言，不给 tool 错误塞 CLI 内部用语。 | 待 plan fix |
| 总控独立发现：plan 将 O09 错标为 form canonical | **accepted（依赖标签）** | O09 原裁决是 fiscal_year 1800–2100；form canonical 是 `UM-O17-F01`。只更正 plan 的依赖/residual 标签，不改变 O05 当前行为范围。 | 待 plan fix |

残余：O16 同 admission 的 action/files 规则串行集成；O06 名称长度另案；合法 form canonical 归 O17；runner 私有晚期守卫暂留，不作公开准入证明；当前 worktree 缺 `.venv`，实施前必须验证代码身份/依赖。所有 accepted finding 修完并有 Kimi/MiMo 有效 re-review 才能提交 accepted plan，产品尚未实施。

## MiMo 修订计划复审（2026-09-29 02:05）

MiMo `docs/reviews/plan-review-20260929-020356.md` 退出 0，JSON `subtype=success`、`is_error=false`、canary `mimo-c89fb752` 匹配，stderr 仅白名单提示；结论 `pass-with-risks`、无 material finding。总控接受其对 F1–F3、Q1、O17 标签的逐项代码复核，Sol 修订候选虽有四条失败 command 仍按 `agent_status=failed`，此单路独立审查只能证明计划文本，不构成双路 gate pass。

复审 R3 发现计划覆盖率命令只核 `ingestion_runtime.py`，但 S1 也改 `upload_tools.py` 与 `dayu/cli/commands/fins.py`。**接受并登记为 implementation 验收硬项**：依 AGENTS.md 对所有被改生产单文件逐一取得真实覆盖率数字，目标各 ≥80%；若未达标，补有效边界测试或如实列残余与 gate 判断，不能用一个文件的数字替代。实施任务和 code review 必须显式核对。其余 R1 环境、R2 O16 集成、R4 runner 内部守卫、R5 CLI 多值结构文案、R6 help 可发现性保留各自归属，不能宣称由 O05 解决。Kimi 本候选仍无有效第二路；未进入产品实现。

## 总控跨项集成裁决（O17 前置）

总控复核发现本候选 plan §字段检查与 §风险仍写「合法 form 保留 raw、O17 后续再 canonical」，而总控依赖队列已裁决 O17 先建立用户指定的唯一 `normalize_material_form_type`，O05 再在该 owner 上游收紧必填。这两套预期不能同时用于同一实施 HEAD。**accepted C1**：O05 implementation 以 O17 的 accepted canonical 函数已集成为硬前提；修 plan 时在 Fins admission 中先对 None/空白给 typed usage，再让合法文本复用该函数，CLI/tool adapter 仅保留已有结构/类型投影，request/event/meta 的合法 form 与 O17 同源。迁移 padded tool 和 CLI 对照的预期，不要求 O05 复制 canonical 函数，也不把 O17 的业务变更误算为 O05 独立验收。若 O17 接口最终变化，先核实真实 owner 再复审 O05 plan。此项已登记主总控队列；Kimi/MiMo 需对修订后的同一候选有效双路复审。

Sol `o05-plan-integration-fix-sol-20260929-01` 预检 ok、显式 `/private/tmp/dayu-upload-o05`、独立 output/stderr，process exit0、JSONL `turn.completed`、canary `gpt-6-sol-33f398c6` 匹配、stderr 空；`git diff --no-index --check` 对未跟踪文件按差异返回 1，按协议 **agent_status=failed**，候选只供总控独立核对。总控核得 plan SHA `2a7fa07dce8fd626b48a96f4669b005bcede5ed97d24ee5e2ebe55dc798e52e2`，已将 O17 accepted+integrated 列硬依赖、合法 form 使用 O17 函数、padded tool 的事件/meta 预期迁移、所有拟改生产文件逐个 >=80% coverage 列门槛；没有产品/测试/README 正文改动。待同版 Kimi/MiMo 有效 plan re-review，不能用旧版 MiMo pass 充数。

## C2：独立 workflow 绕过唯一必填 owner（2026-09-29）

O06 MiMo 同版审查直接证实：`sec_upload_workflow.py` 与 `cn_pipeline.py` 的 material 独立入口在 `build_material_ids` 前没有经过 runtime admission；`build_material_ids` 对空串/纯白抛 raw `ValueError("material_name 不能为空")`。本 O05 plan 当前只改 `ingestion_runtime.py` 与 CLI/tool，不包含这两个 workflow，若照此实施则同一“material form/name 必填”事实在 runtime 报 typed usage，在独立 workflow 报 raw ValueError。该分叉违反 goal 的共同 owner 与 AGENTS.md 语义所有权，且会迫使 O06 在 workflow 重做空值分支。**接受 C2（中，未修复）**：O05 计划须让两条独立 workflow 在 ID/started/任何业务读写前调用同一 Fins material identity admission（含 form/name 必填与 O17 canonical），并以当前代码调用链证明不会产生 import cycle；白名单及 owner 测试加入对应文件。后续 O06 在同一调用点增长度规则，不能只调用“非空专用”叶子。O05/O16 同 owner 错误顺序按实际集成 HEAD 串行裁决，不从旧计划文本硬套。现候选计划 **不得**作为可实施 plan，Sol 仅修计划后重新双路审查，产品未改。

Sol C2 修订计划 SHA `ed83ceb378840c3ca47e5adbd1d4a41e6c078261a80d37315034819bd4cfaef8` 已补公开 `admit_fins_upload_material_identity`、SEC/CN/HK 独立 workflow 前置调用与 O17 同源；其 JSONL 两条非零查询命令，严格 `agent_status=failed`，只取候选。总控跨工作区检查 O04/O23 资产实施候选发现新增 `dayu/fins/upload_usage_contract.py` 并把 `FinsUploadUsageCode`、`_USAGE_MESSAGES` 从 `ingestion_runtime.py` 移至此 owner；O05 当前计划仍指令在 `ingestion_runtime.py` 扩 enum/mapping。**C3 accepted，待资产切片审查/集成后修复**：O05 在最终实施 HEAD 对准唯一 usage contract owner，准入函数可继续在 Fins runtime 作为共享调用边界，但 closed code/message 必须扩同一源，不能因旧计划在 runtime 复制第二套。该跨项依赖先登记，O05 现版不得直接实施；若资产切片最终变化，以 accepted HEAD 重核并同版复审。产品未改。
