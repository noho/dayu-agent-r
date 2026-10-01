# 最终真实 CLI CI：旧证据位置待定位

当前只读准备，不是CI执行或readiness结论。原交接文件指定根目录 `/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`，validation commit `fac32ecbff9bfe792b63ee9667c8697826b631f4`。

root实际检查该根的 observed-behavior.md/json 与 evidence-manifest.json，三者均不存在；尝试读取json返回FileNotFoundError/exit1。因此交接中的三个冻结SHA仅是历史引用，**本轮尚未重新核验**，不写“原Raw仍在/已完整保全”。这不证明文件被删除，也不是代码丢失的证据。

定位范围：当前 `workspace/tmp` 使用rg --files --hidden --no-ignore，返回0，未发现指定报告/manifest/matrix文件；workspace及仓库父级顶层无cli-ci/calibration候选目录。`/private/tmp` 同名文件搜索无命中，但rg exit2因codex-daemon-501权限拒绝，不能声称该根穷尽无证据。三份当前handoff/总控文件对旧根关键字扫描无匹配exit1是搜索无结果，不能替代证据。

已异步询问用户新的根路径或备份位置。只要旧Raw可定位，重新逐字hash、核输入与场景inventory，保全并为新run明确supersede lineage；不得静默伪造旧证据、重写原报告或用旧160执行计数宣称当前CI通过。若不能恢复，必须显式记录旧证据可用性gap，并依据用户裁决、当前冻结parser/branch inventory与授权inputs建立完整新mandatory矩阵，所缺输入/coverage不得默认齐备。

用户裁决的正式UM-O01–O36 artifacts仍在仓库且为语义权威，不因旧Raw位置未知重开用户已裁决行为。产品修复和可独立审查继续，最终真实CI仍须实际完成、oracle/scenarios正式登记并核scope readiness；两个现有registry尚无以upload_material为command的正式条目。

## 用户答复与当前处理（取代上面的待定位状态）

用户明确答复 **旧目录已删除**。因此不再等待新路径，不再将旧Raw保全或三个历史SHA的本轮重新核验写成已完成。历史160执行及其摘要仅是仓库记录的历史陈述，不能充作当前场景执行证据。

当前处理沿用户已授权的大目标：

1. 保留仓库内正式UM-O01–O36用户裁决、已登记修复、后续具体选择以及旧根/旧commit/历史digest引用；不重开裁决，不由当前代码重新决定oracle。
2. 修复完成后以最终不可变commit冻结当前parser/交互分支/状态/选项/输入/组合/跨命令全部mandatory obligations，从正式裁决及可用spec重建完整upload_material场景矩阵；旧160不是覆盖上限，也不能机械重放缺失Raw。
3. 输入重新采集或在授权CI-owned根生成有效真实输入，记录来源/版本/hash。任何无法补齐的必要输入或coverage均显式gap，不默认为齐备；依赖和真实转换不以mock补齐。
4. 新run完整真实CLI执行与取证，全部通过/失败均保留command/双流/exit/screen/文件系统/manifest/durable/log/DB/Trace/process证据及适用性证明。不同输入/版本明确记录，不能冒称复现同一旧输入。
5. 新manifest声明旧证据已删除、旧报告字节不可复核；历史引用字段与本次实证分开，登记new-run/supersede lineage，不伪造旧Raw、不声称旧SHA本轮已验证。oracle/scenarios/readiness只以本次充分证据及用户裁决正式收口。

若用户另提供旧备份，可只读恢复核验作为历史追溯材料；**本轮完整新真实CI仍必须执行**，不因恢复备份跳过。当前不要求用户寻找备份、不停止其它获授权修复。
