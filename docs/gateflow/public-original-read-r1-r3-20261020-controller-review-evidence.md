# 主控代码审核取证

冻结 HEAD `cd37d5759b1152eb1571fd410ff6275c30c83e25`，生产源码未改；这份记录只收集具体反例，不代替双路完整审核。

## C1 XML 模式与媒体类型不一致（待总控最终裁决）

- 真实入口：DefaultFinsRuntime/create/read runtime 的 list_document_assets → read_original_structure；通过真实 Fs 原子发布一个 sample.xhtml，媒体类型 application/xhtml+xml。最小原文 `<html xmlns="http://www.w3.org/1999/xhtml"><body><P>A</p></body></html>`。
- 直接根因：original_content.original_capabilities 按 suffix/media 声明结构可用；read_runtime.py:3303 却只按 filename.endswith(".xml") 选择 XML 模式。XHTML 和无 .xml 后缀的 XML 媒体会进入 HTML 的大小写折叠/可省略闭合逻辑。
- 实际返回：parse_status=complete、diagnostics=[]、P 的 closure=explicit 且 closing 指向小写 </p>。XML 大小写不匹配被伪装为完整闭合，违反 XML 保大小写与不伪造完整性的已批准契约。
- 完整命令、真实响应/身份及返回 SHA 见 `workspace/tmp/public-original-read-r1-r3-20261020/controller-xml-probe/{receipt,response}.json`；临时脚本同根 controller-xml-probe.py。首次测试 helper 导入因未给开发树 PYTHONPATH 失败，保留事实，修正仅开发树路径后实际退出 0。未运行 live、未改调用方原件或生产代码。
- 修复方向：把媒体/后缀的格式判定统一在原文 processor 的格式能力 owner，再将正确语法模式传入索引；不得在单个工具下游特判。补真实 runtime 的 XHTML/XML media、大小写与 HTML 可省略结束边界。严重度中，修复风险低；收齐双路后同轮裁决。

## 已排除的 target 假设（不是 finding）

主控以真实 Fs/public runtime 验证 HTML `<a target="_blank">` 包裹默认 target 的 ix:nonNumeric：返回 complete、implicit_default、context resolved。完整 target() 代码仅接受 inline namespace 的特定元素，普通 HTML target 不参与；负面假设未成立，不要求修复。输入、完整响应、命令/退出见 `workspace/tmp/public-original-read-r1-r3-20261020/controller-target-probe/`。
