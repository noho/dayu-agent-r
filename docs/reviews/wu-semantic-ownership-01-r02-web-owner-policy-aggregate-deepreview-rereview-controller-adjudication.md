# WU-SEMANTIC-OWNERSHIP-01 / R02 aggregate deepreview final re-review Controller adjudication

## 1. Gate 结论

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`；本轮是同一R02 aggregate final re-review，不是新WU。
- AgentDS：`PASS / findings=0`。
- AgentMiMo：六项既有finding全部闭合；提出4个non-blocking建议。
- Controller：接受 `R02-AGG-RV-F01`、`R02-AGG-RV-F03`；拒绝 `R02-AGG-RV-F02`、`R02-AGG-RV-F04`。
- 下一gate：AgentCodex窄fix；fix、Controller validation和双路完整final re-review前，R02不得accepted、completion或进入R03。

两路均确认retained Web security完整、Issue 178/R03/统一authorization零偷带、约1,200行typed fake没有复制production policy/state machine。MiMo artifact在closure清单中同时列出已被重命名的旧test name `test_get_playwright_browser_owner_does_not_publish_failed_state`；当前代码只有新的cleanup-aware test，该artifact文字误差不影响其实际审查结论，Controller在此纠正。

## 2. Finding disposition

### `R02-AGG-RV-F01` — accepted with diagnostic boundary

直接代码证明：launch失败后的局部runtime cleanup在`pw.stop()`异常时使用裸`pass`；此时原launch失败虽有warning，但cleanup失败这一独立error reason没有任何owner-level诊断，若runtime无法停止则无法区分“launch失败且清理成功”与“launch失败且可能残留资源”。动机成立，owner仍是 `_get_playwright_browser` 异常边界。

修复要求：

1. 保持best-effort stop、原launch warning和返回`None` contract；
2. stop异常时记录debug诊断，但只记录稳定stage与异常类型，不记录异常正文、URL、headers、credential或storage path；
3. direct parameterized test必须断言stop成功无cleanup-failure诊断、stop异常恰好有一个脱敏诊断；
4. 不新增通用diagnostic framework、downstream fallback或Issue 178 lifecycle。

### `R02-AGG-RV-F02` — rejected

AGENTS.md要求函数有完整中文`Args/Returns/Raises`，复杂逻辑补中文行内注释；当前函数满足两项。局部runtime为什么必须在当前owner回收，已经由异常分支紧邻的中文行内注释表达。把每个内部时序不变量重复写入public/private函数概览docstring会造成文档漂移，并非contract缺口。

### `R02-AGG-RV-F03` — accepted with narrowed assertion

F01 direct test的目标是singleton create/reuse/re-key/cleanup与channel/headless key contract。当前exact dict还把`--disable-blink-features=AutomationControlled` stealth flag固化为本finding的生命周期contract；该参数不是Controller F01 closure要求，也不是R02设计真源中的稳定public contract。接受去耦，但不能弱化channel/headless验证。

修复要求：

1. 每次launch仍精确断言`headless`和normalized `channel`；
2. 不再把`args`内容或其它可变browser launch tuning作为lifecycle finding的断言；
3. 不修改production launch参数；这只是test owner边界修复。

### `R02-AGG-RV-F04` — rejected

AGENTS.md对类的要求是中文概览docstring；`Args/Returns/Raises`是函数完整docstring要求。新增fake classes均有中文职责概览，构造器与方法也有完整中文函数docstring。要求类级docstring重复构造器参数既不符合硬约束，也会制造冗余。

## 3. AgentDS residual disposition

- OS级线程调度与真实process信号：接受为stdlib/real-smoke test boundary，不是当前finding。
- `abort_resource_types`局部集合：当前无共享owner需要，保持局部；DS所述“新增类型会让现有参数化case失败”并不成立，因为新增集合成员不会自动生成case，但这不构成当前缺陷，未来行为变更应同步owner test。
- `_PW_LOCK`在cleanup stop期间持有：这是owner串行publication/cleanup所需边界，且旧实例cleanup已有同类行为；当前无阻塞证据，不接受为finding。

## 4. Fix与验证边界

允许修改：

- `dayu/tools/web/web_playwright_backend.py`；
- `tests/tools/web/test_web_tools_provider.py`；
- 相关README仅按职责触发；预计`no-update-with-evidence`；
- 新fix artifact。

禁止修改其它production/test/config/utils/control/既有artifacts；禁止Issue 178、R03、统一authorization、通用日志框架或新的browser policy。

验证至少包括：accepted F01/F03 direct nodes、全部21-case owner matrix、provider/aggregate、exact coverage、full pyright、`git diff --check`、脱敏日志断言、allowed-path/docstring/deferred-scope scans和新目录real Playwright smoke。
