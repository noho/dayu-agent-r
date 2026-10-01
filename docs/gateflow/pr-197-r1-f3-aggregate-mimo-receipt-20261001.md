# F3 完整 aggregate：MiMo 交付核收

MiMo50118 外层 exit0、JSON success/is_error=false、75 turns、无 permission denial，actual modelUsage mimo-v2.6-pro[1m]；canary与本轮预检匹配，stderr只有精确unrecognized_model warning。报告 `docs/reviews/code-review-20261001-140211.md` SHA `9c66da57004402b692e735651e4eca3569ba4e8f7637e874735831e2a2dfe15e` 已全文读取，五源码累积增量及既有finding意见可以作为证据，尚未单独构成aggregate通过。

原首核1117 current/originals匹配，末核恰一README变更、1117originals保持；报告称root文档checkpoint不准确，实为F6获准README新增一行。root生产冻结清单的冲突已在F3-AG-PV01登记并用同accepted03的pinned README纠正，原失败不改写。MiMo53684仅窄复审纠正后的输入身份和旧完整意见适用性，待终态；不是重新业务裁决或再审全五源码。

root读完新增 `probe_identity.py`/`verify_freeze.py` 和关键 CLI 原件。原报告8-file strict配置实包含五产品和三只读依赖，不含这两临时脚本；16严格提示不作为项目新门禁，不能当临时脚本绿灯。root独立显式新include/exclude=[]、项目同口径实际检查两临时脚本：2files/0errors/exit0，配置及双流/exit在 `workspace/tmp/pr197-controller-collection-20261001/f3-aggregate-mimo-receipt/`。没有修改旧脚本或仓库类型配置，也没有将0-file pass采信。

原探针stdout可见22项结果，CLI原件有双流但没有独立exit文件；不据Claude summary声明中间命令均成功。root在独占新目录复制合成fixture，并运行真实main：六CLI实际2/0/2/0/2/2；保留名负例无out、重复ID负例已有报告字节不变、cached digest待生成0、selected-only仅aa/bb、未选缓存字节不变。root还实际运行既有离线探针，exit0且22结果与原件完全一致。新argv/stdout/stderr/真实exit及断言结果在 `workspace/tmp/pr197-controller-collection-20261001/f3-aggregate-mimo-cli-receipt/`；原取证目录与脚本未修改。原CLI exit自报缺口由新同源码实证补齐，不编造旧exit。

原报告列出的临时环构造/相对路径对照/长s物理别名预期/type include错误已从最终脚本与root实际22pass确认恢复；freeze末漂移单独归owner配置修复，未以“scope外”直接放行。原报告strict8files/16提示和默认five5files0分别保留；产品同版type证据不混淆。root此前猜 `cli-fixtures` 路径失败、只读命令exit1，经rg定位真实cli目录恢复，未作为证据。

无新产品finding。已有Unicode尚未建立的物理别名、跨运行缓存/执行后回滚/私有闭合谓词治理/历史locator/真实OCR与跨平台语料均保持原独立goal或既有plan边界；没有升为本gate新目标。下一入口为MiMo53684窄复审核收→root两路整项裁决→accepted deepreview commit；最终精确PR head审查/closeout、全部修复后的真实CLI CI仍未完成。
