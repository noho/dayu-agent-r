# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix Slice 1 third stop Controller adjudication

## 1. 裁决

- 时间：`2026-07-18 17:47:08 +0800`。
- Gate：同一 Slice 1 implementation continuation；不是新 WU、不是新 slice，三测试文件 allowlist 不变。
- AgentCodex third stop：`VALID / CORRECTLY STOPPED`。parent拓扑修复后的functional/canonical/coverage均满足当前slice条件；full pyright暴露授权Web harness中的唯一新增类型错误后，AgentCodex按stop rule未继续签署后续门禁。
- Controller verdict：`TEST SNAPSHOT TYPE OWNER DEFECT / SAME-FILE FIX AUTHORIZED / NOT_PRODUCTION_DEFECT`。

## 2. Root cause 与 owner

`logging.Logger.filters`的public运行时语义允许三类filter：`logging.Filter`、接收`LogRecord`并返回bool的callable、以及实现`filter(LogRecord) -> bool`的对象。当前`_LoggerState.filters`窄写为`tuple[logging.Filter, ...]`，不能无损承载stdlib声明的filter集合；`_logger_state()`因此产生唯一pyright错误。

这个缺陷属于`tests/tools/web/test_smoke_web_ci.py`的typed snapshot contract。不能用cast、type-ignore、`Any`、`object`或private `logging._FilterType`掩盖；不能修改production或缩窄真实Logger filter语义。

## 3. 补充精确授权

AgentCodex在同一任务follow-up中获准且必须：

1. 仅在已授权的`tests/tools/web/test_smoke_web_ci.py`定义最小module-level typed filter contract：用public `logging.LogRecord`、`collections.abc.Callable`和结构化`Protocol`表达callable filter与拥有`filter(record) -> bool`方法的对象；让`_LoggerState.filters`无损接受stdlib `Logger.filters`实际元素。
2. 不得导入/复制private typeshed或`logging._FilterType`，不得使用cast/ignore/Any/object/loose类型；不得改变filter identity/order的snapshot/restore行为。
3. 先fresh运行Web topology contract、Web focused、指定order-sensitive联跑和full pyright；然后在最终tree上重新运行canonical、exact-exclusion coverage/219-path ledger、real smokes及原先尚未完成的Ruff/build/scans/security/secret/deferred/no-code/scope门禁。最终artifact不得以第三次stop前的canonical/coverage替代最终tree证据。
4. 更新同一implementation artifact；任何额外pyright错误、测试失败或额外path需求都必须再次停止。

## 4. 不变边界与next entry

- 所有Controller artifacts/control doc均protected；AgentCodex不得修改。
- Slice 2/3、review、commit、push、PR、aggregate deepreview与closeout仍未授权。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；`AR-F07 = PENDING_RELEASE_BLOCKER`；Topic 8/9与deferred Issue owners不变。
- Next entry：AgentCodex same-task implementation follow-up；全部fresh gates完成后停在Controller validation。
