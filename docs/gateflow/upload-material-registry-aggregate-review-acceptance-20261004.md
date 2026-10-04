# upload_material registry aggregate deepreview 总控验收

## 结论与目标

aggregate deepreview / fix / 必要差异双 re-review 循环通过。唯一完整行为 S1 已在238b2898 accepted checkpoint；本轮只集中闭合登记校验器同一 crash 事实合同的 focused source 漏调用，不新增 slice、业务裁决、schema 或产品修复。唯一工作树 /Users/leo/workspace/dayu-agent-r，唯一分支 codex/upload-material-oracle，main fac32ecbf 未动。

## Findings 最终状态

REG-C01/C02/C03/C04/R01/R02/R03/AG01 全部 accepted、已修复。AG01 先 durable 登记再 fix；root 原单标签反例成立，现六 focused 伪 crash 在 owner 首消费处逐例拒绝、有定位、不生成 proof。C04/R01 原两真实 SIGKILL/crash/error 与非 kill 反向拒绝保持，合同覆盖两 source。无新实质 finding / blocking question。根因和最终裁决见 aggregate-adjudication。

## 审查与验证

MiMo58181与ds-flash95625实际退出0、structured success；7584/40901 events、44/54 tools 全配对。root核完整轨迹、每个失败/compound掩码/报告覆盖偏差及恢复、指令全文实际Read、CANARY、精确源/输入、两新delta和真实调用链；私档双保完成。不是两票代裁，不冒全仓穷尽审查。

最终同版186项受影响测试通过、full pyright零错误、批准的 -m strict CLI actual0；合法 whole proof129672字节/SHA196d933a99a8503a5cf6ae9550114fdcc0dd3d5b41d8cf4f32a9c435595ad532不变。原180/166证据是不同源码版本历史，字节保留。新增1 oracle/19 predicates/799 formal scenarios，原6/1328/105及历史证据全值保。原802实际产品执行与新focused6来源分别固定，不重标当前HEAD重跑。完整精确证据、实际argv/exit/日志、源码SHA、双审标准裁决块、失败解释和归档receipt见 evidence/upload-material-registry-20261003/aggregate-review-proof.json。

## 文档与残余风险

docs/cli_ci.md 与 tests/README.md 已按职责更新，产品/rootREADME本登记WU未触发新变化。fixed in current slice=全部8项；covered by later approved slice=无；assigned to later work unit=用户延期Linux/Windows XBRL、历史CNInfo迁移、旧Raw缺口及既有22residual（原owner/destination保持）；tracked by existing issue=Docling抽取准确性#4437；requiring new issue or explicit user decision=无。

## 当前gate/下一入口

accepted deepreview commit，之后立即 ready-to-open-draft-PR / push / 核既有draft PR197 / 正式PR review。当前尚不宣 PR gate 或登记 WU final closeout pass；用户手工merge。
