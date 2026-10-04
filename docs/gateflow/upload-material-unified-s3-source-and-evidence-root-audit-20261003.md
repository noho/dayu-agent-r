# S3 首轮源码与证据总控核查

## 当前 gate 与身份

implementation S3集中收尾；不是正式PR review或slice accepted。首轮outer0/503events/219actual commands/turn.completed、实际canary一致。62票据SHA/实际wait/exit、173 METADATA字节/SHA、25source与收尾入口freeze逐项相同；auxiliary/report哈希相同，11769保护文件与两份各618file资源无漂移。stderr为空；model=unknown，实际事件不暴露，不从provider/token猜型号。

root直接走读 Documents loader/规范workspace外路径/同fd常规文件size/hash/nlink/权限→完整目录与ZIP成员→onlymanifestcopy→worker复验；Fins唯一factory→Process必传config/capability路由→canonical区域→bootstrap→worker chdir/applyOS/复验→第三方单次转换/export/实际backend finally卸载→公共runtime wait/close→父descriptor/size/hash；runtime仅stdlib、无反业务import、实际解释器/库/alias目录只读，不wholeworkspace/network许可。不新资源闭包parser/namespacegraph/抽取质量门禁或下游fallback。

root独立公共 FsMaterialUploadStateRepository/FsSourceDocumentRepository/LocalFileStore读回：afterC01正例complete/v1/primary mlac-20251231.xml_docling.json/amended=false；原件SHA04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1；DoclingJSON1950364bytes/SHA03cff17b63d3a532de6a8e33778b39bf0317e9ae682a8c119098ddf6ba4a1f33；manifest SHA0606c3089f09cbb0a1af487d50453c7d09ff4108e63e747d0f6412fa54b9d0ef，metadata与采集读回逐值一致。不从私有布局推业务事实。

root核8cases CLI/workerPID/公开BaseProcess.close实际exit/公开handle原wait-interrupt-close：正常CLI0/原close回收worker-9，取消CLI130/worker-15，分开保真；模型成功实际unload call/return各1、closed=true，取消未观察不造closed。positive同PID56287精确privatefile/network kernel deny；fileURI同PID53073实际loader请求/目标streamfalse＋请求窗口精确path kernel再拒。FTP实请求缺指定OS拒证unknown；runtime XSD实际streamtrue属用户允许例外；ENTITY/XInclude/PI指定请求未观察not-attempted。P0-R04 strongerclosure按用户边界驳回，不与公司竞争R04混淆。

最终独占afterC01回归668pass/1旧opt-in PDFskip、9修改生产Python各>=80、CN93.68；全pyright0实际wait/exit。fresh完整安装/pipcheck/offline验证/PathStream原双流已核，主.venv未升级。macOS先验、Linux/Windows延期，不冒跨平台通过。

## 每条非零命令

完整command/output保存在complete-command-trace.json，原失败及恢复票据全保。

| event / line / exit | 原失败 | 恢复与影响 |
| --- | --- | --- |
| item_48 / 99 / 1 | output_path未绑定；US3-T01成立 | owner requirednullable初始化/成功路径assert；最终全仓0；已解释warning。 |
| item_59 / 116 / 1 | stderr首因与fixture必传字段失败 | owner和fixture修；owner-tests02=95pass/最终668pass；已解释warning。 |
| item_69 / 135 / 1 | 真实CLI因/var与/private不一致construction失败 | allocator canonical resolve；native02和最终afterC01正例；已解释warning。 |
| item_72 / 143 / 1 | 同canonical路径失败 | 同item_69恢复，旧失败保留；已解释warning。 |
| item_74 / 145 / 1 | 外层工具沙箱内sandbox_init EPERM | 正常require_escalated审批真实native02/后续kernel绑定，不绕权限；已解释warning。 |
| item_77 / 150 / 2 | argv管理员目录错误，CLI2未转换 | 读取admin-input-v2实目录，native02 CLI0；已解释warning。 |
| item_80 / 158 / 1 | JsonValue fixture不变性类型失败 | typed literal修；最终全仓0；已解释warning。 |
| item_94 / 183 / 1 | collector函数名误命中ZipExtFile.read | 精确ZipFile.read代码对象；final05/afterC01成功；已解释warning。 |
| item_97 / 190 / 1 | helper签名/公共仓储API/Json类型与pythonPath配置不合格 | typed接口/nonemptyinclude/config-clean与最终helper0；已解释warning。 |
| item_98 / 192 / 1 | 真实CLI成功后collector不能序列化SourceDocumentRevision | 公共revision.token投影；final05/公共仓储读回；已解释warning。 |
| item_113 / 222 / 1 | helper类型仍未全合格 | typed修；最终helper0；已解释warning。 |
| item_116 / 226 / 1 | root-requests已存在，mkdir阻止拟请求生成 | 后原生审批精确kernel采集；既有rootfinding收据保，不冒请求已提交；已解释warning。 |
| item_129 / 252 / 1 | fixture比较旧/var与产品canonical/private | 按实际canonical记录修fixture；fixture-recovery04/最终668pass；已解释warning。 |
| item_154 / 299 / 1 | summary.json猜不存在 | 实际逐case receipts/root核8cases，不冒缺summary；已解释warning。 |
| item_172 / 332 / 1 | 误要求锁中optional均安装，altair缺metadata | 逐已装pin相等/未装null；root核173METADATA原字节；已解释warning。 |
| item_188 / 366 / 1 | collector错写stored files:0展示文本断言 | 实际stored_files字段；5cases CLI1/publicmissing；已解释warning。 |
| item_200 / 385 / 1 | 提前猜未产生full-pyright-final-command目录 | 后目录实际产生/afterC01全仓0，旧compound非零保；已解释warning。 |
| item_211 / 409 / 1 | LocalFileStore list_objects空prefix非法探索调用 | 公共locator→精确manifest key；root自己公共读回；已解释warning。 |
| item_212 / 411 / 1 | allowed-final.json路径猜不存在 | 读实际分组allowed-files-final；保护哈希/25source绑定核；已解释warning。 |
| item_216 / 419 / 1 | kernel消息漏Sandbox前缀使断言失败 | 真实前缀/PID/path/window绑定；root independently raw核；已解释warning。 |
| item_224 / 435 / 1 | METADATA候选多于1使collector停 | 实际dist-info根精确定位；173原字节核；已解释warning。 |
| item_238 / 460 / 1 | metadata.locate_file抽象路径类型不合格 | filesystem Path断言；helper-after-recovery/config-clean/report0；已解释warning。 |

零退出compound内部缺读亦核：item_51错误provenance位置后实际admin-v2沿冻结原provenance恢复；item_137提前读未产生recovery04receipt后真实生成/核；item_240漏positive子目录后精确逐case及root公共读回。其余FAILED/Traceback为读取旧失败，不新执行失败。原kernel UTC start本地解析空数组后local窗口+UTC输出真实事件恢复，旧空数组不当未拒绝。总控生成失败索引首次把item_113/item_116错位，assert停止、未写错误artifact；按实际22条event身份纠正后才生成本文件，不产品失败或provider重试。

## Findings / residual / next

US3-T01类型、US3-V02门槛、US3-E01 childexit、UP-RR-T01 actualURI已实证恢复，待最终同版slice review；US3-C01坏容器/CRC修、method99尚部分修，集中收尾中，不能pass。原finding/supplement/旧报告与失败不覆。

分类：成立修复fixed in current S3（待核审）；Linux/Windows实装隔离assigned to later platform work（用户明确延期）；Docling #4437抽取准确性tracked by existing upstream issue；FTP未知与取消模型未观察为技术uncovered limits、当前scope不增加伪证明或资源闭包；22历史residual现有owner/destination不入scope。README根/Fins/tests/dayu职责按实际变更核；aggregate/PR为后续gate，完整upload CLI CI/registry为修复WU后独立阶段。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: partial
canary_status: match
result_status: partial
warnings: [逐条解释的历史工具非零与恢复, 首轮collector偏差重新取证, actual_model_unknown]
evidence_gaps: [US3-C01不支持压缩方法未闭合]
retry_class: none
```

outer0来自托管session44901实际返回，不再poll。独立output/stderr/last根 /private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.Ee2xTj；root核证根 workspace/tmp/upload-material-unified-repair-20261002/s3-inflight-root-audit-20261003。当前同slice集中收尾不是provider重试、无新slice/微WU，不commit/push/改main。
