# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix Slice 1 second stop Controller adjudication

## 1. 裁决

- 时间：`2026-07-18 17:30:59 +0800`。
- Gate：同一 Slice 1 implementation continuation；不是新 WU、不是新 slice，也不改变三文件 allowlist。
- AgentCodex second stop：`VALID / CORRECTLY STOPPED`。canonical suite除计划允许的 `AR-F02` import-boundary外，出现 SEC debug-log full-order失败；AgentCodex未把它误归为允许失败，也未继续 coverage/build等后续门禁。
- Controller verdict：`AR-F03 ROOT CAUSE CONFIRMED / TEST-HARNESS OWNER FIX AUTHORIZED / NOT_PRODUCTION_DEFECT`。

## 2. Root cause直接证据

当前 harness会恢复 root/concrete logger的level、handlers、filters、propagate、disabled并恢复registry entries，但没有快照/恢复 concrete logger的`parent` identity。Python logging在用Logger替换中间`PlaceHolder`时会自动重挂既有descendant logger；仅清空/回填`loggerDict`不会反向恢复这些parent引用。

Controller在fresh Python进程用当前harness做最小probe：

```text
old_parent = dayu
old dayu.fins registry entry = PlaceHolder
logging.getLogger("dayu.fins") 后 child.parent = 新 dayu.fins Logger
harness restore 后 dayu.fins registry entry = 原 PlaceHolder
child.parent identity仍为已从registry删除的 dayu.fins Logger
child.parent is old_parent = false
child.parent is restored registry entry = false
```

这与canonical失败同源：SEC日志动态使用`dayu.fins.FINS.SEC_DOWNLOADER`；full-order下该child在Web smoke前已存在，smoke的noisy-logger配置创建`dayu.fins`并改变parent拓扑，harness之后留下orphan parent，后续`runtime_log.configure`安装在`dayu`的handler收不到该child日志。计划指定的短联跑在Web smoke之后才首次创建SEC child，因此未覆盖这个反例。

Root cause位于`tests/tools/web/test_smoke_web_ci.py`的in-process隔离harness；standalone Web logging和Fins production logging均正确，不得修改production或SEC测试。

## 3. 补充精确授权

AgentCodex在同一任务follow-up中获准且必须：

1. 仅修改已授权的`tests/tools/web/test_smoke_web_ci.py`，让typed logger snapshot包含每个concrete logger调用前的`parent: logging.Logger | None` identity，并在registry entries恢复后恢复所有快照logger的parent identity。
2. 扩充同一harness contract test：调用前创建descendant logger并保留原parent identity，fake调用中新建其原`PlaceHolder`位置的parent logger以触发stdlib reparent；success与failure两路均断言调用后descendant parent identity精确恢复，且原有registry/logger/handler identity/order/state断言全部保留。
3. 不得硬编码`dayu.fins`、SEC logger或production suppression列表，不得修改production、`tests/fins/test_sec_downloader.py`、其它测试或任何额外path。
4. 更新同一implementation artifact，记录本裁决、修复与fresh验证；从Web focused、拓扑contract、计划指定order-sensitive联跑开始fresh重跑，再重跑real smokes、canonical suite及此前未完成的accepted plan全部门禁。
5. canonical suite只允许`AR-F02`单节点中间失败；出现任何其它失败或额外path需求必须再次停止。

## 4. 不变边界与next entry

- 原authorization、第一次stop adjudication、control doc及本artifact均为Controller-owned protected paths；AgentCodex不得修改。
- Slice 2/3、review、commit、push、PR、aggregate deepreview与closeout仍未授权。
- Topic 8/9、security no-deletion、deferred Issue owners及`AR-F06`/`AR-F07`状态不变。
- Next entry：AgentCodex same-task implementation follow-up；全部fresh gates完成后停在Controller validation。
