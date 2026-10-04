# 转换诊断 S1：运行前提恢复

Gate：同一 S1 implementation，尚未通过验收或进入 code review。checkpoint8009ba4e100081fd1b56f64ddf5bc0c42a06e808，唯一codex/upload-material-oracle，不改main。

当前workspace缺既有锁包导致真实XBRL ImportError，已登记S1-XBRL-RUNTIME-MISSING-ARELLE。总控最初列4项漏了pyparsing；完整dryrun证实5项均缺失且属于既有Arelle核心依赖及common锁。actor续行02在四项校验失败后误安装了五项并使用禁止的ps进程查询，root驳回这轮任务结果；actor停止并回滚本轮5新增包。失败、回滚、原完整工具轨迹已双私有归档，root terminal audit/retention文件可定位，不冒S1通过或模型服务失败。

总控按当前批准的依赖恢复边界，用fail-fast顺序脚本补齐arelle-release2.45.3/bottle0.13.4/isodate0.7.2/jaconv0.5.0/pyparsing3.3.3。dry-run完整预计集只上述五缺项，actualwait exit0；校验通过后才install，actualwait exit0。所有原包的版本/METADATA或PKG-INFO SHA逐项不变，Arelle核心15项Requires-Dist逐项满足。无依赖/锁/pyproject/生产源码变更；旧CI venv/source/admin/workspace全部只读。五项包只恢复当前venv，不复制源码/shim或混用旧解释器。

169原始metadata条目含cwd editable egg-info和site-packages dist-info两条同名但独立位置，归一化unique包168；加入5包后174metadata条目/173unique包。总控首次直接按script的168条metadata发现与python-读取的169条位置不同而停止，随后一次诊断断言及重复验证也exit1；均在pip开始前，不是包丢失。直接核cwd PKG-INFO原SHA保留，修正为显式枚举workspace项目metadata及runtime metadata，按绝对位置去重且分别保两个owner，实现原169条逐项一致。详情initial-source-discovery-failures.json保全。

实际恢复证据：workspace/tmp/upload-material-converter-diagnostics-20261003/root-env-restoration-03/，含before/after、dry/install report、argv/stdout/stderr/actualwait、原始失败说明、最终result；最终resultSHA 09d6885442c59075f25cd3c9ec1fb2e7c4c6c6d4ecc7f9f800eef9ec1fd871bb。root此前两轮runner audit及private retention receipts在同WU tmp，第二轮按task执行错误分类，后续一次同provider新label corrective retry，保原失败不覆盖。

下一入口：gpt-6-sol在同一S1一次集中收尾全部剩余实现/tests/cov/fullpyright/README/真实PDF4路及SIGINT/受控XBRLkernel验证；产品完整后mimo+ds-flash双code审，保完整Gateflow顺序。原802已完成冻结，后续oracle/scenario登记仍独立WU，不改原证据或业务成功语义。平台延期沿既有用户裁决。
