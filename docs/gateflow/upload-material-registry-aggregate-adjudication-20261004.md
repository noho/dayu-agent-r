# upload_material registry aggregate 总控修复登记

## REG-AG01 初始登记 / accepted / 未修复 / 低

- 真源：与REG-C04/R01同一个crash必须有真实SIGKILL事实的validator owner合同，非新业务分类或新slice。
- 触发：将真实focused成功NATIVE-DEFAULT-04（actual exit0、success）的正式scenario.path_kind从positive改成crash，其它事实、assignment、来源及十九规则不改。
- 根因：_assignment_guard仅在cli802 source分支调用_crash_path_kind；focused source分支只核actual_wait=True，首次消费scenario.path_kind未按已核0/130真实focused终态拒绝不可能crash。因此API仍产生pass/proof。
- 直接证据：当前helper SHA153fe8f1a81f39c837b3b847ac583ed74969113cad89816274c24b9646e3cf2c，formal消费约855–863；MiMo own probe-focused-false-crash，root独立同输入单变更重现 actual0/errors[]/proof产生，见workspace/tmp/upload-material-registry-20261003/root-aggregate-counterexample-01.json。
- 影响：validator仍可给无强杀事实的新focused样本虚假crash分类以ready信用。当前六合法原记录本身正确，修validator拒绝路径，不改Raw/登记记录/用户裁决。
- 修法范围：在相同owner formal首消费处，对focused已批准终态拒绝crash；复用已有真实终态事实，禁止合成process_outcome/raw信号、泛化其它path_kind分类、引入新public字段/通用框架或consumer补偿。测试实际六focused合法与虚假crash逐项拒绝；保持两cli802真实crash/error和原反向拒绝。
- 合并一次aggregate fix，gpt-6-sol实施，必要差异双复审；当前先登记不实施，待MiMo真实终态/所有aggregate findings集中裁完。

## 当前gate

aggregate deepreview在途/出现成立finding，禁止aggregate pass/checkpoint/push。原S1 code acceptance与其checkpoint是历史门禁证据，当前新finding由aggregate owner负责集中修复；不重做原802、不新slice或新用户裁决。main不动，既有PR197边界保持。无新scope openquestion。风险fixed in current slice（待fix），其它原分类保持。

## 双aggregate终態总裁决

MiMo2978 actual0/report145032 SHA69eaaada6287858d052fa4d62d90d4a1a3f12c38a2000bea8b32c979b553b76a；DS91004 actual0/report144310 SHAa0fe2876395c3ab570e83952a5ecf289aa10ca6036f47388db6647dd45fb4595。完整46/52tool与必要证据/CANARY/root补核/双保已完成，DS未发现该反例不抵消直接事实。peer REG-A01归并root REG-AG01 accepted未修复；原REG-C04/R01当前整体**部分修复**，其余五项已修。当前gate=aggregate fix，仅这一成立剩项一次gpt-6-sol集中收尾，不新slice；之后必要新差异双re-review核实AG01和C04/R01整体，避免重审已冻结范围。各报告原覆盖/指令读遗漏/探索失败/peer交叉读时序如实在审计，不能两票代独裁。

## aggregate集中fix候选终态

66642实际exit0/turn.completed，141events59commands；root完整核与独立source/六负例走读。helper23cb69c240815114cd4475ee6a0b104dd2bf7587d4fc7823ae51b54a5e17b348、tests1fc88191841ec6419b8fb58d43d60f38842e727ffbe6fe9f8f73a916cf1c2aec；186tests/type0/批准-m strict0及samewholeproof；首次pytest路径误写actual4与两探索rg1恢复原件保，必需证据无缺口。AG01 candidate已修，C04/R01整体仍待双差异复审最终确认。currentgate=aggregate re-review，不宣aggregatepass。

## 最新双复审总控终裁 / 全部已修复

MiMo58181、DS95625 actual0/structured success，完整44/54工具与全部必要证据/root实际源和双保核收；报告153132/152419无新实质finding。REG-AG01 accepted已修复，REG-C04/R01整体已修复，其余五项精确继承已修。186 tests/type0/原批准-m strict0绑定final两source；六伪crash逐项拒绝，合法wholeproof字节不变。上文初始状态/在途描述为历史，冻结rootqueue仍保原字节；最新状态以本段和aggregate-review-acceptance/proof为准。currentgate=accepted deepreview commit；next=既有PR197正式review链，尚不宣PR或final closeout pass。
