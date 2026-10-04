# 统一修复计划 preparation：总控核收

## 裁决

计划任务 `upload-material-unified-plan-sol-20261002-01`：报告与必要源码取证可采纳为 preparation；整体计划尚不可生成，**plan gate 不通过，不开始 implementation**。3 个行为 slices 符合用户合并修复项的方向；正式 planreview 还未执行。XBRL 保留在 WU，CLI CI/正式 registry 在 WU 后。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: partial
required_evidence: complete
canary_status: match
result_status: partial
warnings:
  - 两个实际 command 非零是 locator 搜索，已由真实模块读取恢复。
  - stderr 有一次文档 apply_patch verification failed；无对应失败 JSONL item，已按后续成功修改和最终内容独立核实恢复，不忽略。
  - fullPR diff-check 的既有 Raw EOF 空行仍 exit2；no-index 差异 exit1、未追踪目标 git show exit128 不表示测试通过或产品失败。
  - 总控初次 collector 未处理显式 absent 条目而失败；已修 collector 分支并完成核收，不计 provider 重试。
evidence_gaps: []
retry_class: none
```

上述 required evidence 指本次 preparation/阻塞报告的取证；不表示 code-generation-ready 或 S3 支持验收已齐。result partial 明确区分候选与 accepted plan。

## 实际核收

- runtime Codex、provider gpt-6-sol；模型事件未暴露，unknown。托管 `write_stdin 51471` 外层 exit0、199 个 LF JSONL events、turn.completed、80 个 command results、13 个成功 file changes。终态消息与实际本轮校验读取匹配。
- item_66 exit1 搜索 asset-plan 中不存在的 filing descriptor 常量，后续 item_67 等读 repository_protocols/storage exports；item_88 exit2 引用不存在 direct_types.py，后续 item_89 与实际 direct_events/upload_material_events 定位恢复。其它 reader 管道 stderr ENOENT/内嵌子命令退出按报告与完整记录逐项解释，不能仅看外层0。
- stderr 的文档补丁失败不属豁免 warning；后续成功 file_change 与最终内容失败 contract 被总控实读确认，产品无修改。工具轨迹缺该失败 item，故记 partial；最终文本/全部交付哈希独立复核补足必要证据。
- source index 142 条：141 实存源文件及快照逐件哈希无漂移，1 条 runtime/subprocess.py 明确 absent 且现场仍不存在；实际真源 interruptible_process.py 已读。805 个原有源码/依赖/测试代码/README 总控逐件匹配作者首末哈希，207 件 delivery manifest 全部匹配。
- 总控直接读 material handoff/身份 builder/SEC workflow、资产 primary/内容错误分支、Docling XBRL 依赖/options/source、仓储与 domain 导入边界、计划 S1/S2 精确契约及 S3 blocker。最终候选已明确 storage projection helper 向 domain 模型传严格事实，模型不反向 import storage；不拿较早草案当现版 finding。
- 完整事件/工具输出和原 stderr 保留在忽略的 `workspace/tmp/upload-material-unified-repair-20261002/`；公开有界 receipt 在 `evidence/upload-material-unified-repair-20261002/plan-sol-root-receipt.json`，保工具身份/退出/摘要/哈希。公开资料读取没有对外写。

## 已成立缺口与下一入口

候选 B-X1～B-X5 仍未修：macOS 标准依赖实装/锁、可信完整 taxonomy/真实 positive、强制边界、同次证据采集、上游 typed 维度风险。具体 owner/destination 见计划 §8；Docling #4437 仍 open，不新建重复 issue。

用户已将 Linux/Windows 验证正式延期，它们不再阻塞当前 WU；不能借此略过 macOS 验收。总控补充 `/usr/bin/true` OS sandbox 启动探针 exit0，只是机制可启动，不是完整边界/转换支持证明。

current gate / next entry：**plan completion**（属于既有 plan gate，非新 gate/slice）：gpt-6-sol 在不修改产品代码的前提下集中完成 macOS 必要原型/安装/公开输入取证并冻结 S3 接口/配置/文件/命令；然后正式同版 MiMo/ds-flash planreview。无法补足时给直接根因和具体缺口，不假通过、不重开业务裁决、不为字段/nit 开微循环。

此 preparation 没有 pytest/pyright/CLI campaign/registry 实施，不能称已修任何标签。所有源码仍在原 HEAD，main 不变。正式 accepted checkpoint、slice/aggregate/PR/finalcloseout 门禁均待执行。
