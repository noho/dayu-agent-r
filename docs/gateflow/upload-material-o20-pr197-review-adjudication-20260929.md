# UM-O20-F01 PR #197 集成审查裁决登记

- 审查目标是 draft PR #197 已推送的 head `9735800cb55a40336469593fa2fddae43c9c69ad`；本记录不 mark ready、不 merge。
- MiMo `docs/reviews/pr-review-197-o20-mimo-20260929.md`：进程 exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`，canary `mimo-a00ccf64` 匹配，stderr 只有 `[claude-code:unrecognized_model]` 白名单提示；报告包含首次 GitHub TLS 探针和两次自写探针参数错误，均原样披露，后续同目的验证成功。MiMo 结论 pass，1 项低 finding，尚不能单路判 PR review gate pass。
- **O20-PR-F1（低，待总控双路裁决）**：同一 tool `files.description` 内 filing 旧句对 `.xml`/`.json` 的内容资格说明不如 material 新句精确，未点名独立 linkbase/`.xbrl`。直接 owner 为 `dayu/fins/upload_format_contract.py` 的唯一文本投影。O20-F01 已接受目标明确只改 material 固定句，故该旧 filing 句不能在本切片暗改。MiMo 建议 F02 收口；总控需核对 F02 goal 的文案边界，若 filing 精度不属于 F02，则登记独立 filing 文案 work unit，不能让低 finding 消失。

## 总控 owner/范围裁决（2026-09-29）

- **O20-PR-F1 accepted／deferred-with-owner，未修复**。总控直接核对 `/private/tmp/dayu-upload-o20-pr10/docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md:17,23`：F02 成功信号明确要求 CLI/tool 公开文案沿 O20-F01 唯一投影、与实际 capability/部署条件一致，且不得把普通 XML/独立 linkbase 冒称可转换 instance；非目标又禁止扩大 O20-F01 已闭环文案。故此旧 filing 句的 XBRL/独立 linkbase 资格精度归 F02 未来产品文案投影，在其 P0 与实施计划通过前不得先改 PR197 当前 F01，避免未经证明的能力声明。F02 实施/深审必须逐字核同一个 `upload_format_contract.py` owner 的 filing/material help/tool schema 与真实能力，消除此项；若 F02 最终被取消或缩范围，则另立 filing 文案 WU，不可悄然丢失。当前 PR #197 O20-F01 已推内容不回退；Kimi 同 PR head review 结果仍待核。
- Kimi 同 PR head 的独立 `$deepreview` 仍运行；收到结构化结果、核对 head/代码/测试后才作最终裁决与 checkpoint。
