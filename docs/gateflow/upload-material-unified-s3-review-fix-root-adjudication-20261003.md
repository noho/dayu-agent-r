# S3 集中 review fix：总控核收及原生 CLI 恢复

## Scope 与裁决

Gate：fix S3 → re-review S3。唯一 workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`，HEAD `a514dea14c0ce66722da034502f3af54a54c3238`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。此次只修首轮已成立 US3-R01/R02/D01 六个白名单文件，不改目标、不新 slice。

总控实际阅读六项增量 `repair-only.patch` 及相关真实调用/票据，独立校验全部146个JSONL事件、62次命令完成、5次成功file change和12份receipt的command/stdout/stderr/receipt SHA、真实wait及绑定源清单。24项最终源码逐项匹配；12122保护输入零漂移。源清单SHA `6aae2616a06581a2439bd3b396ce8da8c17b1c1884fddc6d72715f3b9528333f`。

| finding | 实施核收 | 后续 |
| --- | --- | --- |
| US3-R01 | 已修复：Documents owner先valid再访问backend；真实缺属性坏输入不掩盖execution | 同版双路复审确认后回写最终状态 |
| US3-R02 | 已修复：worker五种状态合同、PDF零调用、分类及finally单次释放；另真实Docling坏内容回归 | 同版双路复审 |
| US3-D01 | 已修复：根README明确管理员taxonomy源目录、程序快照及用户原件副本 | 同版双路复审 |

这不是S3 accepted pass或WU closeout。保留原子Agent报告 `upload-material-unified-s3-review-fix-report-20261003.md`（SHA `1cd61860db260e2d7ff01f157945e6976a86686eded67c144a8fddfd50694d20`）中的原始blocked状态，不能覆写其历史证据。

## 原生 CLI 恢复（总控执行）

子Agent的首轮cli-r01-01 actual1为sandbox_init拒绝，只到construction。总控另用托管外层原生执行、相同最终源及既有standard-venv，新的独占base和raw目录，未关闭/更改生产sandbox策略。session68251已取得actualouter1；坏内容预期失败，不把退出1冒成功或平台拒绝。receipt实际wait=true/exit1。

新票据在 `workspace/tmp/upload-material-unified-repair-20261002/s3-review-fix-01/root-audit/cli-native-r01-01/`。真实stderr `failure_code=docling_converter_execution`、stored_files=0；没有sandbox_init拒绝。`public-native-r01.json`为总控以FsMaterialUploadStateRepository/FsSourceDocumentRepository/FsCompanyMetaRepository公共API真实读回：material missing、publication absent、material_ids=[]、公司Mountain Lake Acquisition Corp.独立存在。未以私有文件存在代替业务成功。此补证关闭原报告R01 execution取证gap，不伪称子Agent已完成该步骤。

## 验证及证据边界

- tests-final-v2 actual0/waittrue：82 passed、5明确deselected、11.08s；后五项原外部positive及内核负例没有计为pass。
- full pyright-final-v2 actual0/waittrue：0 errors、0 warnings。owner覆盖214/235=91.06%，未新增覆盖排除。
- 六个临时工具type实际0；final integrity/readonly reverse patch check实际0。
- 18未变源SHA与冻结基线相同，可继承原读取与原执行范围；Documents生命周期helper已改，旧整链正例仍为历史事实，不能宣称本次最终源新实跑正例。受控真实正例在后续aggregate最终源验证中统一核收。

## 全部失败/恢复裁决

- JSONL行97 item_49：CLI construction拒绝，原双流保留；总控新native票据恢复required execution，不能改旧结论。
- 行103 item_48：新测试私有导入pyright失败，随后公开定义路径修正，源v2和最终tests/type实际0；旧v1清单保留。
- 行125 item_64：逆变换末换行SHA不等而停止，无错patch或sourcewrite；后build_diff_v2逐六项冻结原字节SHA成立，incremental-diff-v2-command及patch-check实际0。
- stderr一次apply_patch预期typing导入行不匹配，工具原子拒绝；后实际读导入再修。不是provider故障。
- 行59 item_29：compound外0内不存在fs_company_repository.py及failclosed-managed03票据；后实际仓储/旧集中收尾票据定位恢复。行102 item_52：compound外0内两个假定state模块不存在；行110–112实际fs_material_upload_state_repository.py及repository_protocols.py恢复，readback-01和root native公共回读真实0。不把compound外0当内全部成功。
- 其余error-like命中为读取代码/历史原failed日志，不是新增工具失败；完整67项tool trace及error-like原输出在root-audit，62command/5file-change可核。没有turn.failed、无未恢复required gap。
- 子Agent实际model未被event暴露，self-report不替代实际model；记unknown warning。外层0/turn.completed/实际canary读取匹配仅证明生命周期/指定读取，不单独证明业务核收。

```yaml
setup_status: ok
agent_status: blocked
canary_status: match
tool_evidence: yes
tool_trace: complete
required_evidence: complete
result_status: partial
warnings: [model-unknown, recovered-tool-failures]
evidence_gaps: []
retry_class: none
```

agent_status保留子任务blocked历史，按sub-agents不能把blocked自报改accepted。总控独立恢复后的组合fix证据可进入re-review；不需provider重派。所有JSONL/stderr/last/prompt/canary已复制到workspace/evidence及output/evidence-backup双独占副本并逐字节SHA核验，原TMP不删。

## Docs 与 residual

根README职责内修管理员资源说明；tests README区分合成控制流、真实坏内容及真实正例/内核证据。Linux/Windows/非3.11 assigned to later platform work，按用户明确延期；抽取质量tracked by upstream Docling #4437；FTP unknown、runtime-XSD allowed、ENTITY/XInclude/PI未观察请求、取消模型未观察保留原有界技术证据/后续owner。22独立residual不加入。aggregate/full PR review为后续已批gate；完整CLI CI/正式registry是WU完成后独立阶段。

下一入口：re-review S3，MiMo/ds-flash并行、只审六项修复增量及必要主链路，旧18项精确SHA继承，不能重复全安装/全OS矩阵/旧全slice走读。
