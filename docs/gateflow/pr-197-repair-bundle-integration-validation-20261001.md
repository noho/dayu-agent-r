# PR197 修复组合回归：PR review 入口证据

日期2026-10-01；唯一workspace `/Users/leo/workspace/dayu-agent-r` / `codex/upload-material-oracle`。HEAD4896b8d4；含F6-AG-A1待复审的一行docstring工作区候选。**本记录是组合验证证据，不是PR gate或final CI pass。**

必要性：F4/F7 accepted aggregate后的共享CN workflow、storage exports、tests及README已由获准F6改动；旧整文件SHA不同不表示丢修复，旧模块通过也不能直接替代当前组合。root对F2/F3/F4/F6/F7当前37路径首末SHA绑定，组合运行其中12个受影响测试文件，实际激活venv，独占cache/basetemp，PYTHONDONTWRITEBYTECODE=1。

托管session46516取得outer exit0；实际pytest inner exit0，stdout **1377 passed，3 warnings，58.78s**，stderr空，warnings均既有edgar弃用。37输入首末逐件SHA相同。范围含CN身份观察/终态model/下载workflow/runtime/storage原子性、SEC workflow/stream、direct、CLI、wait adapter。F3五utils未变化且不进入这组pytest，采用其既有同版分析输入/CLI/type证据；不声称本次重新执行。

双流、精确argv/cwd/env、exit、37source binding及末身份原件位于`workspace/tmp/pr197-repair-bundle-integration-validation-20261001/`，evidence-manifest实际hash/bytes可核。全量pyright采用同当前源码Sol AG-A1交付中的真实783checked/0errors/exit0，不无依据重复。各prod coverage采用已核scope的无排除数据；不宣称本次重采coverage。

F2目标函数AST保持accepted fix；F3五源码保持accepted slice SHA。F4元数据同窗观察/成功前缀/原异常/缺席allocated身份规则仍由storage及CN identity owner承诺；F7共享终态词表由CnDownloadTerminalStatus/Final唯一产生，普通结果与完整性中止入口仍按各子集消费；F6公共完整性原因/错误投影不替代F4身份事实，也不把F7私有中止快照误作公开成功。真正PR review仍须固定PR head/base比较快照和独立MiMo/Kimi复审，不以本回归证明全PR无缺陷。

残余：F6-AG-A1候选仍待同版双窄审（fixed in current slice目的地）；F3/F4/F6/F7的PRreview/closeout为later approved gates；F5Q1为explicit user decision；原upload队列、受控XBRL及完整真实CLI新matrix/oracle/scenarios/readiness为later approved work，未执行。main未动，无新分支/工作树/网络/OCR输入或业务裁决。
