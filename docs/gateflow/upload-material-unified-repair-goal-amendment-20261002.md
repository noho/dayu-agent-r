# 统一修复 WU：XBRL 平台验收范围修订

用户明确答复（2026-10-02）：

1. 当前没有 Linux/Windows 执行环境。问题引用：`call_HyomfTDZNhBRx3GNfVquK2Bk`。
2. 选择“macOS 先验收，跨平台验证延期（建议）”。问题引用：`call_bsk2T12TDnnGiXAiF9rWU6at`。

这是 Gateflow binding goal 的明确修订：当前统一修复 WU 保留 O20F02，以本机 macOS arm64 / Python 3.11 的真实受控 XBRL 支持验收。Linux/Windows 的 fresh 实装、依赖锁回读、强制文件/网络隔离及进程继承验证移至后续平台验证项；owner 为平台部署/依赖与 Documents runtime，总控负责排程。不得宣称这两个平台已验证或把 macOS 结果外推。

本轮 macOS 的受控依赖组合、可信 taxonomy 输入/边界、有效真实 instance 经 Docling 并 manifest 提交成功、失败/取消和可审计证据要求保留；抽取准确性归 Docling 上游。旧计划中“三平台均通过才本 WU pass”的条款被本次具体授权覆盖，其它既定业务裁决不变。必要同次证据不能以重放/标题文档/fake 代替。

当前候选计划是基于修订前合同生成，仍非 accepted plan。计划作者收齐终态后，应集中补齐本机必要设计证据、修正 S3 精确契约与白名单、按此修订重绑计划，再由 MiMo/ds-flash 同版双路 planreview 和总控裁决。剩余真正设计/证据缺口仍需解决，不能只把 platform 字样改成 macOS 就宣称 generation-ready。

17 个上传修复标签与 O20F02 仍合为一个 WU；PR review 在全部 slices/aggregate 后。完整 upload_material CLI CI 与 oracle/scenario 登记保持在修复 WU 完成后的独立阶段。
