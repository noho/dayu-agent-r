# upload_material 修复后 CLI CI：总控双路裁决

状态：frozen observation 已核对；两路 lifecycle completed/outer exit0；审查结论部分采纳；新 predicate 等待用户裁决。产品修复 WU 已关闭，本文件不重开它，也不改源冻结事实。

## 身份与证据

- branch codex/upload-material-oracle；target79977b3a52f8566672e3b462f786f1004dfd3f89。
- observed-behavior.md SHA256 f35d33f5ff62b1e45d6f6ecf7ae1bcf7db4139f33c5b2af714e59ea0680ef53c；20518公开文件双副本SHA全核对；802实际执行、全部actual wait。
- MiMo116 tool calls/results，DS130 calls/results；完整原JSONL/stderr/private输入/最终workspaces均双份保全。详root-*-terminal-audit.json和root-*-retention.json。
- 31历史裁决及后续用户选择优先；原Raw已被用户删除，旧来源不可重新核验，新run是superseding lineage，不宣称恢复旧Raw。

## MiMo逐项裁决

|建议|总控处理|依据/限制|
|---|---|---|
|S1|部分采纳既决验证|O06+用户240码点；长度合规是admission条件，不保证任意动作发布，delete不产生content|
|S2|驳回漏格，采纳矩阵验证|PAIRWISE-04同fingerprint、amended false→true、overwrite，v1→v1、stored1；root-overwrite-amended-coverage-check.json|
|S3|采纳既决验证|O07/O25，唯一显式primary；shared owner|
|S4|采纳既决验证|O05/O12/O15，条件必填、独立财政可选|
|S5|采纳既决验证|O19/O20与macOS范围；13formats+真实91页PDF；不判断抽取准确性|
|S6|采纳既决验证|O21/O22 typed conversion/empty failure；不把pre-admission循环链接扩入converter失败|
|S7|采纳既决验证|O28 direct无Host/Agent，查询不存在不等未查询|
|S8|采纳已覆盖部分|O29，256冲突+32primary+append；quiet不抑业务；未测PDFquiet不推断|
|S9|needs-more-evidence / unadjudicated|原生PDF129行MatchingPostProcessor WARNING直写stdout，stderr0；第三方诊断通道新窄predicate待用户，非Docling质量|
|S10|采纳限定观察|O30/O31，130优雅终态；SIGKILL仅已见PID最终采样absent，不声称parentdeath500ms保证|
|S11|驳回重复数值提问|原owner100+accepted plan前置且保数量规则，99/100/101实测；不是凭旧101推上限、不新增alias100cap|
|S12|采纳否定提醒|AL000先syntax拒绝，不证明aliascount|
|S13|采纳观察/拒绝公开别名推断|--file有效缩写是当前parser事实；internal-id移除已裁；不新增缩写永久规范|
|S14|采纳限定wiring|首错保全无positivecredit；BATCH2script和BATCH3显式IDs真实成功；不宣其它完整campaignready|
|S15|采纳回归观察，不升oracle|O14限定+approvedplan240，tombstonecreate拒绝/保持状态；不固化storage_io不自动恢复|
|S16|驳回需重新定义verdict|cli_ci2.7既定owner/枚举；executor unadjudicated占位无效，root独立裁决|
|S17|采纳14leaf分类，纠正展示范围|1primary+5cross+8out；实际完整commandpath来自argv；top标签不扩campaign|
|S18|部分驳回|O19E01后续lexicalsymlink真实补证+CONTENT10已成功；断链/循环/越界未新增契约，不制造拒绝合法symlink目标|
|S19|记录观察、不判新bug|approvedplan112保files原OSError、primary typedselector出口；不同错误阶段不以物理输入相同强求文案相同；不固化措辞|
|S20|驳回新裁决请求|O02 Accepted已明确重复scalar last-wins；nativePDF后Microsoft生效符合该裁决|
|S21|采纳协调/业务分离|52 readbacks仅锁mtime，root-current-readback-lock-delta.json；不回填过去|
|S22|采纳collector归因|v1datetime故障非产品失败，不计credit；v2fresh35终态32失败/3HTML成功，不造质量oracle|

## DS建议裁决

S01–S11既决验证按对应O01–O36与后续有效设计逐项核验采纳，保留root-ds-suggestions-preliminary-reconciliation.json中的字段修正：native stdout19741字节、log-file32格仅6非空/10高等级空、leaf5cross/8out。不同意其summary绝对全部with-log非空，也不同意只有历史O19前节。

|新建议|总控处理|
|---|---|
|N01|与MiMoS9合并：第三方诊断通道候选待用户，不自动accept|
|N02|驳回aliascount上限：无契约且样本未触数量owner|
|N03|合法symlink补证有效；循环/断链强typed新方向不自动实施，保currentdesign观察|
|N04|驳回bad HTML必须转换失败：用户已明确抽取准确性上游，本项目只转换/发布/失败处理|
|N05|既有O04/O23唯一资产映射contract，不硬码具体编码名称新oracle|
|N06|UNSAFE/REPAIR_REQUIRED按acceptedS2设计failclosed，非新用户问题|
|N07|wiring范围保留，不扩其它命令campaign|
|N08|root既有2.7verdictowner，无需用户定义枚举|

## 待用户窄predicate UM-CI-N01（发现登记，不是已授权修复）

输入：原生91页MSFT2024PDF，SHA96de32a720641251b44c3e27e25ce2aa7ab035a15182b6260ef0ef06aa041dc0。FORMAT-PDF-NATIVE-FULL真实exit0、Docling+manifest成功；stdout19741字节，其中129行第三方WARNING，stderr0；未测nativePDFquiet/log-file组合。

建议predicate：第三方转换器诊断也须遵循CLI诊断日志通道，不能混入业务stdout；quiet抑制诊断而保业务进度/summary。有--log-file时符合等级的诊断进该文件；无log-file时遵循CLI既定诊断去向。该建议与抽取准确性无关。允许依赖运行库正常产生诊断；禁止把它当业务事实。另一选项：明确第三方原样输出不受当前CLI日志contract约束，保持事实记录、登记scope例外。

authority不足：O29只接受实测产品Print/logoperator行为，不能由两审同意自动扩大。依cli_ci4.7提交用户选具体predicate；若接受，则冻结新oracle，从后续run生效，判断是否需新WU补证/修复，不追溯改原run事实或把已闭产品WU重开。

## 分离状态

- Observation/evidence：complete within declared802 scope。
- 当前已裁产品语义：未发现直接违例；非零exit按场景分别归因。
- primary validation verdict：oracle-review-required（UM-CI-N01未裁；非执行器unadjudicated枚举）。
- registry：仍仅旧5command历史ready，upload_material尚未登记，不能宣materialready。
- 下一入口：用户窄predicate裁决；独立登记WU goal/plan可研究既有裁决与旧record保护，不先写新accepted。

## 用户后续裁决

用户明确接受UM-CI-N01：第三方诊断也遵守CLI日志规则。新oracle后续run生效，原frozenfacts与原run裁决不追溯改pass/fail。登记新修复UM-CI-N01-F01：converter第三方直写stdout绕过CLI诊断边界。新单slice修复WU完成并真实补验后，才最后登记/closeout；原产品repairWU保持已关闭。

## 发布与保全位置

本文件仅发布bounded总控裁决，不将20MB冻结观察报告、97MB公开证据或私有输入/工作树归档放入Git。公开源`workspace/evidence/upload-material-cli-20261003-79977b3a-01/public`，独立长期副本`output/evidence-backup/upload-material-cli-20261003-79977b3a-01/public`，每字节SHA已校验。private四份归档包括input-runtime-harness-source、actual-final-ci-workspaces、review-ds-flash-original-run、review-mimo-original-run，均双份600访问。原报告freeze后不改；所有root proof/完整失败恢复/双review原结果在workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation，与private归档互证。

用户后续acceptance以oracle-candidates.json记录为准；本版发布日期之后，新的日志predicate用于后续run。原802runprimary=oracle-review-required为历史新predicate未裁时结论，不逆写为pass或fail；新修复/新run另有target/identity。唯一branch本地/远端/PR197目前79977b3a，mainfac32ecb，没有新分支。
