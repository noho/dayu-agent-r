# UM-O09/O10 第二轮 plan review 总控裁决

MiMo `docs/reviews/plan-review-20260929-031057.md`：exit 0、结构化 success、canary `mimo-d74c95ee` 匹配、stderr 仅白名单提示；`pass-with-risks`，两个低 finding。Kimi 403 无有效第二路，plan gate 未通过。总控核对 O10 裁决限定真实 CLI 空值保持 `null`、`_optional_nullable_text` 在 tool 参数层拒绝空文本、filing period owner 对直接输入空值规范为 `None`；这些是不同入口的真实边界，不应为表面一致改共享 tool helper。

1. **F1 accepted，采用参数层拒绝**：material tool schema 逐字说明省略或 `null` 代表未提供，空串/纯空白在参数层 `invalid_argument`、不进 Fins admission、零 awaiting handle；补测试。CLI `--fiscal-period ""` 与 owner 直接调用仍规范为 `None`，按用户 O10 裁决保持。O11 日期同 helper 的相似 shape 在其 WU 验收中单独核对。
2. **F2 accepted**：本隔离工作区先建锁定 Python 3.11 `.venv`，记录解释器、`dayu.__file__` 与 checkout 一致；随后按 AGENTS.md 跑受影响测试、逐文件 coverage 和 pyright。不能借主工作区的 editable venv，也不能把未安装依赖的收集失败算产品错误或测试通过。

既有 `fins-material-legacy-invalid-fiscal-identity-recovery` 保留；与 `fins-material-legacy-identity-seed-disposition` 的关系由总控在集成前核对，避免两个 owner 分叉。下一步 Sol 仅修 plan，Kimi/MiMo 有效双路复审后才实施。

## MiMo 第三次 plan re-review 裁决

`docs/reviews/plan-review-20260929-035228.md`：exit 0、结构化 success、canary `mimo-02cb0ad5` 匹配、stderr 仅白名单模型提示；原 F1/F2 在计划层闭合，年 1800..2100、六个 period、seed/manifest 同源、集成顺序与 legacy 残余未见反例。新增两项低 finding，均 **accepted**：

1. tool 的 `fiscal_period` 是 filing/material 共用参数，schema 必须分别说清 filing 必填与 material 可省略/`null`，空串/纯空白均参数层拒绝；不能把“省略/null 未提供”写成对 filing 也可用的全局句。测试同时断言两段准确文案。
2. 计划点名迁移 `tests/fins/test_fins_ingestion_tools.py:1718-1723` 的 schema 描述逐字旧断言到新文案，不为保旧测试回退 LLM-facing 规则；断言覆盖 material 的 null/空串/纯空白及 filing 必填。

reviewer 复证现有 `UNSUPPORTED_FISCAL_PERIOD` 文案含 CLI flag，tool 可能直接投给 LLM。该通道中立性问题已在 O07 同类 finding 显露，**新增独立修复项 `fins-upload-usage-message-channel-neutral`**，审计所有会进入 tool 的 upload usage message 的入口术语并在各语义 owner 改写；本 O09/O10 不把纯文案全局清理偷入财年/期间域变更。日期 schema shape 的独立核对归 O11。Kimi 403 第二路仍缺；Sol 仅修 plan，再有效双路 review，产品未实施。

## Sol 第三次 plan fix 候选

`fiscal-plan-fix3-sol-20260929-01` 在显式 `/private/tmp/dayu-upload-fiscal`、独立 output/stderr、预检 ok 下退出 0；JSONL 有 `turn.completed`、28 条完成的命令，其中 `git diff --no-index` 对新计划文件返回 1，按 sub-agents 严格协议记 `agent_status=failed`；stderr 空、canary `gpt-6-sol-457c11d4` 匹配。总控直接核对计划 SHA-256 `5c3bbee5cd65d86cf92f90d5d977250264eabfbaf07a51a9d86b94c9c68e81a5`：共用 fiscal_period schema 已按 filing 必填、material 可省略/null 分句，空串/纯空白的参数层拒绝适用于两者；点名迁移旧测试 1718–1723 行的精确文案断言。该结果仅是修订候选，未形成双路 plan review pass，产品未实施；下一 gate 为有效 Kimi/MiMo 并行 plan re-review。

## MiMo 第四轮同版复审与新增修复项

MiMo label `fiscal-plan-rereview4-mimo-20260929-01`、显式绝对 fiscal workspace，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、canary `mimo-823d05db` 匹配、stderr 仅白名单 model 提示；`setup_status=ok, agent_status=completed, tool_evidence=yes, canary_status=match, retry_class=none`。review `docs/reviews/plan-review-fiscal-rereview4-mimo-20260929.md` 已实读，对 SHA `5c3bbee5...` 判 pass-with-risks。总控采纳其共用 tool `fiscal_period` 三分句与旧逐字测试迁移已闭合的直接代码证据；新增两项须先修计划：

1. **Fiscal-PR4-F1 中 accepted**：O09/O10 与 O07-F02 的 material identity builder/validator 是用户原裁决明定的同一 owner，O07-F01 将删同一 request/schema 的 `internal_document_id` 输入。计划的集成边补 O07-F01/F02：fiscal typed 准入与 ID 一致性检查的先后和错误优先级、`validate_material_upload_ids` 与共同前置链收敛、`replace(request,...)`/workflow/tool schema 在字段删除后的合并核对。O07 依赖 O05/O17/O09/O10 的稳定 seed，不允许本项预造临时 ID 兼容分支。
2. **Fiscal-PR4-F2 低 accepted**：本 WU 新增的 `INVALID_MATERIAL_FISCAL_YEAR` 文案须明确为业务中立，字段名及 1800..2100 码值可读，不带 `--flag`/CLI 术语；owner 测试与 tool 断言精确文本及 `"--" not in message`。既有其它 usage 文案通道中立清理仍归 `fins-upload-usage-message-channel-neutral`，不因此扩本 WU。

MiMo OQ：O06 的 240 Unicode 码点规则虽由独立 WU 负责，仍与本项 `build_material_ids` 和 common admission 接壤；**接受补 O06 合流登记**，阈值与 strip 规则只引用 O06 确认合同，不复制常量或实现。Kimi 有效第二路尚缺，当前 gate 为 `plan review -> fix`；Sol 仅修这三处计划文本再同版双路复审，产品未实施。

## Sol 第四次计划修订核验

label `fiscal-plan-fix-pr4-sol-20260929-01`：预检 ok、显式绝对 `/private/tmp/dayu-upload-fiscal`、独立 JSONL/stderr/last-message/canary；进程 exit0，JSONL 108 events、47 条完成命令均 exit0、无 error/failed event、`turn.completed`、stderr 空、canary `gpt-6-sol-20312390` 匹配。严格 `setup_status=ok, agent_status=completed, tool_evidence=yes, canary_status=match, warnings=[], retry_class=none`。总控实读修订记录 `docs/gateflow/upload-material-fiscal-plan-fix-pr4-20260929.md` 与新计划 SHA-256 `7c95474d37a986500664321efc589df3b6d8f28d3da14e2622eb23e36593a18a`。

总控采纳**计划候选**：O07-F01/F02 与 O09/O10 在同一 identity/admission owner 的后续串行合流、fiscal 先于 ID 一致性检查的错误优先级、字段移除核对均明确；O06 去首尾空白后 240 Unicode 码点规则只作依赖登记；新增 `INVALID_MATERIAL_FISCAL_YEAR` 的业务中立精确文案与 owner/tool 断言已列。产品、测试、README 均未改；须在同 SHA 获有效 Kimi/MiMo plan review 后才进入实施。

## MiMo 第五轮同版 plan re-review

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

MiMo label `fiscal-plan-rereview5-mimo-20260929-01`，显式绝对 fiscal workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、53 turns、canary `mimo-f83351c0` 匹配。artifact `docs/reviews/plan-review-20260929-124741.md` 已实读；计划 SHA-256 `7c95474d37a986500664321efc589df3b6d8f28d3da14e2622eb23e36593a18a` 与任务锁定一致。reviewer 独立核对 fiscal→ID 顺序、O07 字段移除交界、O06 240 码点引用、新文案、共享 tool schema、真实 CLI 配方与覆盖率门，结论 pass-with-risks、**无新 finding**。总控采纳本版已闭合 PR4-F1/F2 的计划层证据；legacy、其它 usage 通道中立、process 投影与集成顺序仍按既有独立残余追踪。Kimi 对**同 SHA** 的有效第二路尚缺，plan gate 仍未通过，产品未实施。
