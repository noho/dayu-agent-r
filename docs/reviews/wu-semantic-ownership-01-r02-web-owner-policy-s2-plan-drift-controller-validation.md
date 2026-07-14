# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 plan drift Controller validation

## 1. Validation target

Controller 对以下同一 plan-drift target完成验证：

- `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`；
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-controller-adjudication.md`；
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-fix-codex.md`；
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md` 的直接 stop evidence；
- 当前 code/test direct caller事实。

当前仍是既有 `WU-SEMANTIC-OWNERSHIP-01 / R02-S2`；validation只决定plan是否可进入双路完整re-review，不接受代码、不恢复implementation、不创建新slice。

## 2. Root cause 与 owner validation

Controller独立确认：

- `_request_with_safe_redirects` 已在当前未提交S2 diff中新增无default必填 `transport_policy`；
- `utils/diagnose_web_access.py:_build_requests_profile` 是遗漏的直接caller；
- `tests/tools/web/test_diagnose_web_access.py` 存在同一旧签名fake；
- 三个deterministic raw diagnostic cases的稳定 `TypeError` 与该缺参同源；
- provider `_parse_config` 仍是raw config到typed `WebToolsConfig`的唯一parser owner；utility只应消费其 `transport_policy` projection，不能创建第二default/parser/environment owner。

因此 `R02-S2-DR-01` 的动机、严重性与owner边界成立。精确前移utility/direct test是mandatory contract传播，不是S3产品语义提前。

## 3. Plan fix validation

修订后plan已闭合以下要求：

1. §4.3、§6.1-6.3/6.6、§9.4-9.7精确授权 `utils/diagnose_web_access.py` 与 `tests/tools/web/test_diagnose_web_access.py` 的direct caller/fake传播；
2. raw mapping只交给既有provider parser owner；utility禁止复制bool默认、直接构造policy、解析environment或增加compatibility default/wrapper/`getattr`；
3. direct-node、完整diagnostic test、provider tests、完整pyright、逐changed production coverage与README/source/allowlist gates已写入；
4. §13要求现有smoke脚本S2零diff、exit 0、local零skip/failure，并让三个先前`artifact_missing` cases产生v2/revision2 evidence；
5. storage lifecycle/CLI/TTL/owner filename/publish/reconcile、`_DEFAULT_DIAGNOSTIC_ERROR_CHARS`、`--max-network default=80`、`DiagnosticResourceBudget`、ordinary writer/profile schema仍留在S3；
6. `utils/smoke_web_ci.py`、batch script、根README、Issue 178、R03、proxy credential schema和统一authorization均未获S2写权限；
7. state machine明确保留当前未提交S2 diff，双路re-review与Controller裁决前不得恢复implementation。

## 4. Controller validation finding

### R02-S2-DR-CV-F01 — accepted / fixed

初版plan把全文件 `**kwargs` 纳入utility transport零命中scan，但当前utility已有两个合法browser Protocol variadic methods：`_BrowserTypeProtocol.launch(**kwargs)` 与 `_BrowserProtocol.new_context(**kwargs)`。该命令会产生确定性假blocker，不能证明transport seam正确。

AgentCodex按follow-up完成窄修：

- transport零命中scan只检查第二policy constructor、raw bool解析、environment读取/推断与`getattr`；当前直接执行零命中；
- 两处既有browser Protocol `**kwargs`单独精确命中并归属为非transport seam；
- target-specific AST audit精确要求 `_build_requests_profile` 与exact fake具有无default typed keyword-only `transport_policy`且无loose kwargs；
- added/signature-touched production/test definitions必须逐qualified name完成中文docstring audit；function/method/nested helper显式包含Args/Returns/Raises，class/Protocol/TypedDict说明职责、fields/call contract，一行摘要不能通过。

复核后该finding关闭，没有改变产品contract、allowlist或implementation diff。

## 5. 验证结果

- 完整读取最终plan diff与fix artifact：通过；
- `R02-S2-DR-01`在owner、allowlist、tests、smoke、stop/completion中传播一致：通过；
- S3/deferred scope未前移：通过；
- 收窄后的utility transport scan：零命中；
- browser Protocol归属scan：精确两处；
- `git diff --check`：通过；
- AgentCodex记录的11项既有dirty/untracked内容hash前后相同：现有implementation、control、README、tests与既有artifacts未被plan-fix gate改写；
- 本gate是plan validation，未运行implementation pytest/coverage/pyright/smoke；这些仍是恢复implementation后的hard gates，不能由历史结果替代。

## 6. Verdict 与 next gate

Controller verdict：`PASS FOR DUAL FULL PLAN-DRIFT RE-REVIEW`。

`R02-S2-DR-01` plan fix已通过Controller validation；`R02-S2-DR-CV-F01`已修复关闭。下一gate是AgentMiMo与AgentDS对同一immutable final plan target并发完整re-review。reviewer不得修改plan、产品、测试、README或control，只能各写固定review artifact。双路与后续Controller adjudication闭合前，不得恢复S2 implementation。
