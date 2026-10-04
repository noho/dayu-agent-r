# 转换诊断 WU：accepted plan

2026-10-03T12:00:32.822115+00:00

## Decision

**plan review / fix / re-review pass，允许 accepted plan commit；下一个未完成 gate 是一个完整 S1 implementation。** 本记录为当前状态真源。计划正文保留历史候选/待复审措辞以保持实际已审字节，不回写旧审查对象。唯一分支 codex/upload-material-oracle，开始/计划内容 source parent 79977b3a52f8566672e3b462f786f1004dfd3f89，main fac32ecbff9bfe792b63ee9667c8697826b631f4 不动。

接受计划 docs/gateflow/upload-material-converter-diagnostics-plan-20261003.md SHA cbd771224d4fc88bcafa6a03c8e786d4e1cef6dc22e15937ed38d7dc73461709；只一个 S1，不按文件或 owner 切分。三生产/五测试/三README allowlist 保持。

## Finding closure（仅计划级，不是产品已修）

DN-R1..DN-R6、DN-D0与控制流补充已由原同版 MiMo/DS 复审验证，报告 plan-review-20261003-185739.md / plan-review-20261003-190419.md。当前父投递delta（DN-R7）及五处措辞收敛由 plan-review-20261003-195231.md / plan-review-20261003-194600.md 验证；必要受影响合同已审，零变化部分以相同 SHA、精确 diff 与前审证据继承，不冒全部重复审读。四路真实 managed exits 0、完整实际工具轨迹/错误恢复/来源/报告/canary 均root核验并双份私有保全，receipts在本WU temp。所有 accepted findings 当前**已修复（计划级）且 re-review verified**，无未修复/部分/证据失效阻塞，无 open question。

DN-R7 在日志 owner 专用方法内捕获普通诊断投递故障，保原准入/目的地/格式和普通日志行为，禁止 std emit/handleError 公共stderr逃逸、global raiseExceptions、monkeypatch、fallback。不存在已验证businesssuccess因为sidecar坏而变失败的新门槛。四类控制流保持传播、cleanup后原对象，原manifest publication语义不变。

## Residual classification / S1 conditions

DS-R1及MiMo真实装配/锁释放/未覆盖控制流阶段：**fixed in current slice（待S1实际实施验证）**。在S1真实 configure helper owner测试加入未配置/缺失/非唯一marker时不触root/lastResort/公开双流，失败bool按已审分支；跨线程锁释放及 format/flush/release 的控制流原对象；普通RecursionError是Exception，按计划False，不误列为四种控制流。

生产三个完整文件>=80、真实spawn collector原数据及合并、fullpyright0、真实91页PDF default/quiet/logfile/error、SIGINT130、macOS controlledXBRL正例及private/workspace/network禁止：均是当前S1未来必要验证，**尚未执行/未宣pass**。产品所有代码完成后再做双code review，保既有完整gate顺序，不再微切slice。

Windows/Linux 用户已明确延期，owner 为后续平台验收；Docling抽取质量上游，不纳当前目标；raw unknown INFO路由/无三路全局序/收口后投影为已审最小机制，更强保证需要未来明确决定；quota/daemon/独立Logger框架均outsidegoal无授权laterWU。独立正式registry WU继续等待本修复闭环和新的真实measurement/source identity，不改旧registry与frozen802。

## Scope / docs / next

实核 tracked product diff empty、受保护源码/两个registry哈希与实施前基线一致。计划gate仅文档与独占机制proof，未跑产品pytest/fullpyright或真实CLI，不需要为文档机械跑测试。README实施后按已读职责更新，不提前写未实现事实。

下一入口 accepted plan commit → gpt-6-sol集中S1implementation → code review/fix/re-review/accepted slice commit → aggregate deepreview → 更新既有draftPR197并正式PRreview → finalpush/draftpass/finalcloseout。用户最终merge，禁止main/newbranch/worktree/新PR/ready/approve/issue/comment/merge。所有修改成果进入既有PR197，独立registry partial计划不并入本plancommit。
