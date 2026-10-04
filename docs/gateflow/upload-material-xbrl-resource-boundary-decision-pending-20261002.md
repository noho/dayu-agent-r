# XBRL 运行库读取与资源边界：范围解释待用户裁决

状态：pending，尚无用户答复；当前旧binding scope不变。总控已通过异步UI询问，不能把建议当授权。

原 goal `upload-material-o20-xbrl-runtime-goal-20260929.md` 要求可信taxonomy、明确文件系统边界、实测file/穿越/远程不越承诺；未由用户逐字定义运行库是否属于该承诺的只读例外。当前候选OS策略为必要运行库读取作了例外，真实XML最小变体实际请求其中Arelle/config/disclosuresystems.xsd并获流，反例成立。资源owner/S3作者提议新增资源引用闭包validator；它的成本与覆盖性尚未证，可能扩大为第二套解析路径。必须先明确范围，不能为了通过或为了硬化静默改目标。

总控建议：允许明确列出的已安装运行库只读访问，禁用户工作区和其它私有文件，禁出站网络；taxonomy可信来源、完整清单/哈希/布局与受控复制保留，XML的读取受同一强制文件/网络边界约束；不另承诺XML绝不能访问运行库文件，不新增泛化XBRL资源解析器。财务抽取准确性仍Docling上游。备选为维持XML仅声明taxonomy的更强合同，并继续证明其可实施资源入口或明确上游缺口。

若用户采用建议，必须在正式goal amendment明确写binding新边界，再由gpt-6-sol集中删除过度资源闭包设计/当前R04阻塞，冻结必要macOS策略和精确S3计划，然后正式同版双审；不得直接root跳过作者或reviewgate。若用户坚持更强边界，继续原计划的实际owner机制取证。当前gpt-6-sol集中任务仍in-flight，父层启动策略/必要文件网络probe可独立继续；依赖边界答复的产品验收/acceptedplan保持pending。

不改变17标签现成裁决、singleWU/三行为slices、LinuxWindows延期、完整CLI与registry在WU后、唯一开发branch与PR197。P0-R04当前accepted/未修复状态保持，建议不是已延期/关闭记录。

## 已取得用户裁决

用户选择“采用上述边界（建议）”；本pending记录已结束，现行binding见 `upload-material-xbrl-runtime-boundary-goal-amendment-20261002.md`。原提问/反例保持历史，不复写为早已确认。运行库例外内读取不再列R04阻塞；必要OS边界/启动/取消仍验。
