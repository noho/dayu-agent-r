# UF-FIX01 F1 双路复核裁决

## Gate 范围

- Work unit：`UF-FIX01 validation-atomic-boundary`
- Review base：`7ea01244ddd234ca6bbc9593168b6f320bb890c8`
- Review target：`b3304eb4d6040938527584010b92dd92a45b75bd`
- MiMo artifact：`docs/reviews/code-review-20260813-134144.md`
- DS fallback artifact：`docs/reviews/code-review-20260813-135000.md`

DS 原 review turn 在完成探索后未于合理时间内收口。Controller 按 Gateflow agent fallback 中止该 turn，重新 discovery/clear，并以同一冻结范围派发禁止子 agent、禁止扩散检索的独立 `/deepreview`。第二路 artifact 已实际落盘，不以 MiMo 结论替代。

## 双路结论

MiMo 与 DS 均给出 `PASS`，共同确认：

1. FD2 隔离覆盖真实 Docling 调用，恢复与关闭路径不存在已识别的描述符泄漏；
2. UF-FIX09 的共享 converter、可中断轮询、terminate/kill/close 与 attempt chain 均未回退；
3. closed failure descriptor 与用户可见 exit 1 分类保持不变；
4. 新增 CLI 测试走真实 subprocess/Docling child 路径，不是 fake。

两路还独立识别出相同的三个低严重度问题：

- logger 测试的 `propagate=False` 使其没有真正经过 stdlib `lastResort`；
- 隔离区退出时 `flush()` 的二次异常可能遮蔽转换阶段的原始异常类型；
- CLI integration test 硬编码本机 calibration 绝对路径，不可移植。

## Controller 裁决

F1 的生产修复方向与 owner boundary **通过**。上述问题不推翻 FD2 隔离的正确性，但都能在不改变目标、owner 或架构的情况下做最小修补；为避免最终 gate 固化失真的测试覆盖与机器绑定，Controller 将其列为进入 UF-PF01 最终 focused-real rerun 前必须完成的限界 follow-up：

1. 让 owner test 确实触发无 handler 的 `lastResort` stderr 路径；
2. 清理阶段不得用 flush 次生异常覆盖转换原始异常，同时仍必须恢复/关闭 FD；
3. CLI integration test 使用测试自身创建的不可解析 PDF，保留真实 CLI/真实 converter 路径，不依赖外部 calibration root。

这不是 goal/owner 变化，不扩大到格式 allow-list、date/year、并发或其他 UF work unit。完成修补、测试与完整 pyright 后，直接进入 UF-PF01 focused-real evidence gate。

## Gate 状态

- F1 implementation review：`PASS_WITH_BOUNDED_FOLLOWUP`
- 第二路独立 review：已满足
- 下一状态：AgentCodex 限界 fix；随后测试、完整 pyright、UF-PF01 focused-real rerun
