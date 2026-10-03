# 总控新增 DN-R7：父日志投递故障可直接泄漏公共 stderr

2026-10-03T11:11:31.521041+00:00

当前计划 SHA `33c00f8543a42c438e315f3294e8f8399cee972722b49ab55bde2bb041d6a141`。状态 **accepted / 未修复**；同一个 S1 内补足，不新建 WU，不改变已决材料成功及取消语义。

现有 `dayu.runtime.log._build_marker_handler` 创建 `logging.StreamHandler`。标准 `emit` 内部捕获普通格式化、write、flush 错误并调用 `handleError`；默认 `logging.raiseExceptions=True` 时直接打印公共 stderr。计划的新 helper 外层捕获不到已由 handler 消化的异常。真实 configure owner +真实失败目的流 +原源 WARNING LogRecord 复现公共 stderr 878 bytes。根探针最初漏传必填 debug_stream 参数，已如实记录并更正后取得有效证据。

需在 runtime 日志投递 owner 明确不走公共 stderr 的普通故障处理，仍复用同一准入、目的地和格式，保持控制流传播及业务原终态；禁止临时修改全局 raiseExceptions 或 monkeypatch。不要顺带修改范围外普通日志的行为。补真实失败 stream/formatter 合同负例。依据为本 WU 已绑定日志通道及 DN-R1/DN-R5，未新增业务目标。证据和 hash 见 `workspace/tmp/upload-material-converter-diagnostics-20261003/root-parent-handler-finding.json`。
