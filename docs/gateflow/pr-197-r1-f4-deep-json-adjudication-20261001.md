# F4-CR1-A1：新批量快照拒绝既有仓储已接受的深层JSON

## 直接反例与根裁决

**中／accepted／未修复**，owner为storage批量元数据观察 `_fs_source_document_core.read_source_meta_view` 的新副本生成。根在Sol52404真实outer0/161JSONL turn.completed之后，对实际候选唯一新路径作adversarial验证；在隔离临时根通过真实Fs仓储blob/source/batch API创建并成功提交带custom_nested JSON的source，不伪造COMPLETE、不直接篡改磁盘、不改source/tests。深度8/300控制均source COMPLETE、旧public list/get成功、新view成功；深度600同样真实commit成功、旧list/get成功、真实classify COMPLETE，新view在MappingProxyType(deepcopy(meta))抛RecursionError。完整结果workspace/tmp/pr197-controller-collection-20261001/f4-deep-meta-probe.json，命令outer0是受控反例采集成功，不是产品通过。

实际路径：原get每次json.loads读取新树，_source_meta_without_revision仅去私有revision并产生业务mapping；新view额外deepcopy给原已接受JSON增加更低Python递归栈限制。600层对象可序列化且已被存储创建/读取/完整性owner接受，不是缺少来源或损坏数据。一个非HK/用户上传来源的这种合法meta也在HK身份全树观察中被复制，因此可使原可解析身份的下载提前失败；不能凭788现有测试green或“其它异常透传”来接受新拒绝。

正确修复须在同一storage owner保全已有合法JSON范围、顶层只读和独立观察数据，不能下游catch/fallback/限深/忽略该doc/把它typed UNSAFE/改manifest；不改业务/API状态与错误优先序，不让测试固化deepcopy偶然实现。可首先分析已有getter每次独立解析的生命周期，消除不必要副本，或以必要最小无递归副本实现保证同一公共独立观察契约；实际技术方案由Sol据owner直接证据确定，禁止发明通用JSON框架、下游补偿、sys.setrecursionlimit或新JSON入库拒绝。当前accepted plan明确deepcopy技术写法与目标冲突，必要修正须在fix artifact记录为何保全同一goal/publiccontract；不把该必要correctness变为新业务选择。

## 当前gate与排程

Sol作者delivery可核收，但源码不能accepted。下一同版MiMo/Kimi（quota失败用授权DS）并行Code-review，以14实际文件/完整差异/真实tests同一冻结候选为证据；本finding作为根已验证未修项一并审查。先收完整独立review及根裁决，再Sol在当前F4-S1 fix（必要技术plan句同步、无新S2）→同版re-review→root tests/types/逐filecoverage→accepted slice commit。不得在只读review在途改候选，F3仅文档两句fix可并行且不同写界。

本项立即登记独立artifact与controller/queue/handoff。分类fixed in current slice（尚待fix/re-review，不作pass）；F4-R01原跨writertarget-only局限仍requiring new issue or explicit user decision，本finding不是集合唯一性强化。F4-R02原总扫描性能等assigned to later work unit，F5/F6/原upload队列不顺带实施。原788/fullpyright0/eightfile>=80是反例修前候选的证据，不能沿用为修后最终结论。当前只探针与裁决文档，README不触发，后续source修法按实际reader职责更新。
