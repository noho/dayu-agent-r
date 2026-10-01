# PR197 F3-S1 双路代码审查总控裁决

## 结论与下一入口

当前门禁 **code review 不通过**：`F3-CR1-A1` 低 / accepted / 未修复，下一入口为 Sol 在原批准五个 utils 内修复输入路径解析，再对同版进行 MiMo/Kimi re-review。没有新的业务 WU，也没有放行源码提交。

审查报告：`docs/reviews/code-review-20261001-102054.md`（Kimi），`docs/reviews/code-review-20261001-103522.md`（MiMo）。真实范围为初始 S1 `60307c15947e2f89457e03126b1251aeb4264c53` 到当前五文件完整增量；冻结文件 `workspace/tmp/pr197-f3-s1-code-review-20261001/freeze.json`。审查期间只有其它 WU 与文档 checkpoint 提交，F3 五文件字节不变。

## Finding 裁决

- **F3-CR1-A1 accepted / 未修复**。具体 owner、合同、四条真实 CLI 反例、最小修复及验证边界已登记 `pr-197-r1-f3-input-loop-review-adjudication-20261001.md`。MiMo 的“环被包装”只检查 `analysis_targets_alias`，没有覆盖 loader 的 root/manifest/PDF 及 main 的 out.resolve；其无 finding 结论不能否定 root 四入口实际反例。禁止用宽 RuntimeError catch 将执行期分析错误改为输入错误。
- **Unicode 尚不存在别名**：保留既有 accepted plan 的 `requiring new issue or explicit user decision`，owner 为分析产物命名/文件系统身份规则，destination 为独立 goal。MiMo 的 fresh `_manifeſt` 路径用无转换 stub 调真实 digest main，阶段 A exit0、numbers 消失，阶段 B exit2；root已读取探针源码、实际日志及先前本卷 samefile 证据，确认这是既有明确排除的风险。没有创建外部 issue、没有扩大为 Unicode 禁令、没有称其已修复。
- 其余已批准 C01/C02、输入/产物 owner、缓存与算法不变的审查意见由 root 对照真实五源码、前次完整交付核收及 909 断言/263 命令证据采纳；不把无 finding 票数作为放行依据。

## 输入及取证复核

root 重算 **35 当前 + 35 review 原件 + 4 真正初始源码原件 + 5 fix 前原件 = 79** 项身份，全部相符。MiMo 报告的“38”“44/44”计数不准确，以上实际冻结数为准，不改写原报告。模型依据各完整 JSON 的 `modelUsage`：MiMo `mimo-v2.6-pro[1m]`，Kimi `kimi-k3[1m]`。

MiMo outer 托管句柄 65815 已返回 exit0；完整 JSON subtype success、is_error=false、61 turns、result 非空，随机读取凭据逐字匹配。stderr 只有精确 `[claude-code:unrecognized_model]` warning。JSON 的 permission_denials 有一次 Bash diff 汇总命令安全分类器超时；报告记录已改用可读 diff 恢复，root independently 核对冻结原件/五源码增量，因此不靠该失败命令证明走读。

root 实读 MiMo 的三脚本与 `probe-cli-run.log` / `probe-fs-run.log` / `probe-loop-run.log`。其中 CLI 是同步 executor/固定 digest worker 下的真实 main 路径，**不是真实 Docling CI**。报告记录首次错误相对 symlink、探针非幂等及 executor sysconf 权限失败后的夹具恢复；最终真实链接环及 fresh/重跑分阶段日志可核。脚本里残留 `object` 注解不作为严格类型验证通过证据，也不扩成产品修复项。没有重复执行 263 子命令或真实 OCR。

Kimi outer 87199 已返回 exit0。报告自身临时目录无可核日志且自述错误 symlink 夹具导致合成内容转换尝试；这部分保持 partial，不认证未取得逐轨迹的 OCR/网络外围断言。root 的独立四 CLI + 源码 + 已接受合同足以采纳其 A1 finding，不能把其自报测试算 root 已核实。

## 派发结果固定块

### MiMo

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - precise unrecognized_model diagnostic
  - permission-denied diff command recovered by readable source and root comparison
  - temporary fixture and executor setup failures recovered with final evidence
  - report identity counts corrected by root actual 79 checks
evidence_gaps: []
retry_class: none
```

runtime/provider/label 为 claude/mimo/pr197-f3-s1-code-review-mimo-20261001-01。完整 output/stderr 在本轮 `sub-agents.6qAUPL` 目录（完整绝对路径由 active-runners.json 保留）；Claude 没有逐调用轨迹，accepted 限于上述 independently verified 审查证据，**不采纳“所有输入环合同都正确”的泛化结论**。未重派、未切 provider。

### Kimi

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: partial
canary_status: match
result_status: partial
warnings:
  - precise unrecognized_model diagnostic
evidence_gaps:
  - claimed temporary probes have no independently verifiable logs
  - erroneous symlink fixture triggered conversion attempt without per-tool trace
retry_class: task
```

runtime/provider/label 为 claude/kimi/pr197-f3-s1-code-review-kimi-20261001-01；完整 output/stderr 在 `sub-agents.oR7abw`（完整路径同 manifest）。A1 已由 root 独立证据接受，不需要重派以抹去此任务取证偏差。

## 残余与整体目标

缓存鉴权、外部换链接事务、历史公开 locator、真实 OCR/性能等维持批准计划的独立 goal 分类；F4/F5/F6/F7 属其它队列。utils 按 AGENTS 无永久 pytest/coverage 要求；修后仍须实际临时验证及非空 pyright。

全部授权修复完成后，必须重跑真实 CLI CI，以用户既有裁决确定 upload_material oracle/scenarios。现有两个 registry 的完成范围仅 download/upload。本次审查及任何单元测试都不构成整体 CI/registry closeout。
