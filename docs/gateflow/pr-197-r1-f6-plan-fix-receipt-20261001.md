# PR197 F6 A1–A4 计划修订核收

本记录只接受计划修订交付证据，不接受计划、不实施产品。下一门禁为同版完整 plan re-review；原 A1–A4 保持 accepted，最终修复状态由复审和总控回写。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - actual model unknown; runner 未提供模型元数据
  - apply_patch 上下文失败已按实际整行恢复
  - 前缀 diff1 和新报告 no-index whitespace1 是预期差异，双流留存
  - session 定位复合读取未单独记录搜索退出；该步骤不承担必要证据
evidence_gaps: []
retry_class: none
```

- runtime/provider/label：codex/gpt-6-sol/`pr197-f6-plan-review-fix-sol-20261001-01`。托管 40525 已返回 outer0，81 行合法 JSONL，以 turn.completed 结束。完整 command/file-change 事件、stderr、last-message 已核查。
- 原流目录：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.vfHnDP`，独立 jsonl/stderr/last，实际 item_33 cat0 与 expected/正式报告/last token 匹配；token 不用来推断模型。
- 正式交付：`docs/gateflow/pr-197-r1-f6-plan-review-fix-20261001.md`，SHA256 `6f4d7d967e0c9f10ec1264baa098807409d1a109dce954fa66759d34a404676f`。
- 当前计划 SHA256 `57ab49b7648444629db3290b7d8ba54b397b63f1495fe70fd0e0d18c71d7f1b1`。root 独立重算 60 originals、59 readonly，全匹配；历史尾 45,467 字节逐字相等。command-ledger 的全部双流路径和实际退出文件与登记数值一致。首末 HEAD8328699a/mainfac32ecb 不变。
- root 实读当前设计及差异：A1 显式 normal cancelled/ok、abort ok；计数 builder 不承载完成日志。A2 postrepair 封闭三类型 catch，mid-filing 保真实两类型。A3 四 SEC 抛点沿既定 pair catch/恰一 failed 行，6-K/Phase B 迁移保零新发布。A4 CN Phase B reason 迁移保完整 cause/确认前缀/rollback；私有文字保持已裁边界。一个行为 slice、原 8 prod/10 tests 集合、job/wait owner 和已有上传裁决未扩。
- item_20 前一次 apply_patch 未匹配整行，stderr 保留原错；后续三个 file-change completed、最终计划真实内容及 SHA 恢复。item_24 diff1、item_37 no-index1 均预期，cmp/hash 实际0。不把外层0代替内层状态。产品 tests/type/coverage 本轮未执行，旧 probe 不当作产品验收。
- root 初次 canary 检查误遍历 item.started（其无 aggregated_output）触发 AssertionError；随后改为 item.completed 重查真实读回/token/终态，全部匹配。此总控脚本误判已恢复，未改原件，不作为 provider 缺陷或修复证据。

Residual：动态取消、真实 postrepair/SEC Phase B/CN Phase B 验收属于后续已批准 F6-S1；完整 durable reason、publication indeterminate、早期取消空行计数和 rejected helper 统一保持各自既有 owner/destination。F5 Q1 待用户，不代选；最终全部修复后的完整真实 CLI CI 尚未执行。此次核收不关闭上述工作。
