# S1 fix：实际渲染 caller 白名单补充

此项是已批准 S1 batch raw form 变化引出的真实回归修复，映射既有 S1 成功信号“机械原文投影且生成有效可执行脚本”，不修改 goal/UM裁决、公开参数合法性、验收平台或3 slices。

正确 owner 为 dayu/cli/upload_script.py::_render_posix_script，原 §5.4 白名单遗漏了这条实际 caller。仅允许该 renderer 将再生成注释的每个 LF 物理行加 shell comment 前缀，普通单行输出字节完全保；原 command shlex quoting/raw argv 和 Windows 既有约束保。拒绝在 batch 或 identity 下游 trim、拒全局新增换行业务规则。技术白名单仅补 upload_script.py；owner 测试仍是已批准 tests/cli/test_upload_filings_from_command.py，无新测试模块或额外 slice。

同一集中 fix 另允许 US1-R01 准确同步 ingestion_runtime.py、upload_asset_plan.py、tools/upload_tools.py、pipelines/docling_upload_service.py、storage/_fs_source_document_core.py、cli/commands/fins.py 的相关 docstrings 与根 README.md，行为零变化。其它生产源码只读；有新必要 caller 必须先报告 root，不自行扩。

验证：renderer 合法多行原文不使注释成为命令，POSIX syntax 与参数原文 roundtrip、真实 batch CLI 首/尾LF及CRLF合法form生成0/sh-n0、普通singleline字节保；必要owner测试、一次最终受影响回归、fullpyright0与全部19修改生产文件逐文件覆盖≥80。旧证据不改，新的run独占COV/cacheoff/basetemp/命令argv/双流/actualexit。

root 基于真实路径、直接反例和现成授权裁决该最窄 owner 修复；accepted plan c99...原字节保持，不为修本轮回归另开plan或goal gate。非目标不变：不状态/amended/并发、不XBRL、不完整campaign/registry；全片后才PRreview。
