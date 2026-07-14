# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 plan drift re-review（MiMo）

## 1. Review target 与 scope

**reviewed target**：`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`（S2 plan-drift fix revision）。

**scope**：对既有 `WU-SEMANTIC-OWNERSHIP-01 / R02-S2` final plan-drift target 的第一路完整 adversarial re-review。不是新 WU，不修改 plan/产品/测试/README/control。

**输入 artifacts**：
- `AGENTS.md` / `CLAUDE.md`
- `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-controller-validation.md`
- 当前 source code（caller/fake/provider parser）

**timestamp**：`20260715-022150`

## 2. Assumptions tested

1. `R02-S2-DR-01` 是否按 owner 最小前移
2. provider parser typed snapshot 传播是否避免第二 default/parser
3. test/smoke/pyright/coverage/scan 命令是否实际可执行且无假 blocker
4. Controller validation F01 是否真正关闭
5. added/signature-touched 中文 docstring gate 是否足够
6. S3 lifecycle/CLI/default/writer、Issue 178、R03、proxy credentials、统一 authorization 是否零泄漏
7. 现有未提交 implementation diff 保持且恢复时序正确

## 3. Check matrix

| 检查项 | 预期 | 实际 | 结果 |
|---|---|---|---|
| R02-S2-DR-01 owner 最小前移 | 只前移 `utils/diagnose_web_access.py` 和 `tests/tools/web/test_diagnose_web_access.py` 的 mandatory transport 传播 | plan §4.3/§6.1-6.3/§6.6/§9.4-§9.7 精确只迁移 raw requests direct caller 的 mandatory typed transport 传播；S3 lifecycle/CLI/TTL/owner filename/publish/reconcile、`_DEFAULT_DIAGNOSTIC_ERROR_CHARS`、`--max-network default=80`、`DiagnosticResourceBudget`、ordinary writer/profile schema 不前移 | PASS |
| transport source 唯一性 | transport 值只来自既有 provider `_parse_config` owner 产生的 typed snapshot | plan §4.3/§9.4 冻结 `_provider_config -> provider._parse_config -> WebToolsConfig.transport_policy -> _build_requests_profile -> _request_with_safe_redirects`；utility 不得构造 policy、复制字段/default、解析 environment 或增加 wrapper/`getattr` | PASS |
| 禁止第二 default/parser/environment inference | utility 没有第二 constructor、raw bool parser、environment 读取/推断、`getattr` | source scan `rg -n 'WebHttpTransportPolicy\s*\(|dns_peer_proof_enabled|allow_environment_proxy|getattr|os\.environ|os\.getenv|getenv\(|environ\[' utils/diagnose_web_access.py`：零命中 | PASS |
| browser Protocol 合法 variadic 归属 | `_BrowserTypeProtocol.launch(**kwargs)` 和 `_BrowserProtocol.new_context(**kwargs)` 精确命中并归属为非 transport seam | source scan `rg -n 'def (launch|new_context)\(self, \*\*kwargs: JsonValue\)' utils/diagnose_web_access.py`：精确两处命中（689、718） | PASS |
| pyright 可执行 | `python -m pyright` 可运行 | `pyright 1.1.409` 可用 | PASS |
| S1 test filter 可执行 | `pytest ... -k 'config or resource_budget or egress_policy or provider' -q --co` 可运行 | 175 tests collected | PASS |
| S2 test filter 可执行 | `pytest ... -k 'private or custom_port or proxy or peer or redirect or browser or challenge' -q --co` 可运行 | 70/175 tests collected (105 deselected) | PASS |
| transport-specific scan 可执行且零命中 | `rg -n 'WebHttpTransportPolicy\s*\(|dns_peer_proof_enabled|allow_environment_proxy|getattr|os\.environ|os\.getenv|getenv\(|environ\[' utils/diagnose_web_access.py` 零命中 | 零命中 | PASS |
| AST audit 可执行 | target-specific AST audit 可运行 | 可运行；当前 `_build_requests_profile` 和 `fake_request_with_safe_redirects` 均无 `transport_policy`（implementation 尚未执行，符合预期） | PASS |
| Controller validation F01 关闭 | `R02-S2-DR-CV-F01` 标记为 `accepted / fixed` | controller-validation §4 明确标记 `accepted / fixed`；transport scan 已收窄为只检查 transport-specific 内容 | PASS |
| added/signature-touched 中文 docstring gate | plan 要求逐 qualified name 审计，function/method 完整 Args/Returns/Raises，class 完整职责/fields/call contract | plan §9.6/§9.7 和 completion item 10 明确要求；不允许一行摘要 | PASS |
| S3 lifecycle 零泄漏 | `storage_state_out`/TTL/`_StorageStateLifecycle`/owner_final_name/reconcile 不在 S2 production scope | S2 production files 无这些符号；它们只在 `utils/diagnose_web_access.py`（S3 目标）和 `tests/tools/web/test_diagnose_web_access.py`（S3 目标）中存在 | PASS |
| Issue 178 零泄漏 | 无 Issue 178 lifecycle 代码进入 S2 | production code 无 credential refresh/retention/publish/cleanup | PASS |
| R03 零泄漏 | 无 R03 相关代码进入 S2 | source scan `rg -n 'R03' dayu tests README.md`：零命中 | PASS |
| proxy credentials 零泄漏 | 无 proxy credential 解析/存储 | `rg -n 'proxy.*credential|credential.*proxy' dayu/tools/web`：只命中一处 docstring 说明"不包含 credential" | PASS |
| 统一 authorization 零泄漏 | 无 authorization framework/policy DSL/capability token | `rg -n 'authorization framework|policy DSL|capability token' dayu tests README.md`：零命中（只在 plan 非目标说明中） | PASS |
| 现有未提交 diff 保持 | 6 个 production/test 文件的 diff 保持不变 | `git diff --stat c7b01d82` 显示 6 files changed, 1980 insertions(+), 470 deletions(-)；与 S2 implementation artifact 记录一致 | PASS |
| plan fix 只修改 plan 文档 | plan fix 不触碰 implementation 代码 | `git diff --stat c7b01d82 -- docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`：1 file changed, 162 insertions(+), 52 deletions(-)；与 fix-codex §6 记录一致 | PASS |
| control doc 更新 | gate 状态更新为 `R02-S2 plan-drift re-review` | `git diff c7b01d82 -- docs/host/issues-implementation-control.md`：gate 从 `R02-S1 accepted local commit` 更新为 `R02-S2 plan-drift re-review` | PASS |
| `utils/diagnose_web_access.py` 无 diff | 该文件尚未被修改（implementation 尚未恢复） | `git diff --stat c7b01d82 -- utils/diagnose_web_access.py`：无输出 | PASS |
| `tests/tools/web/test_diagnose_web_access.py` 无 diff | 该文件尚未被修改（implementation 尚未恢复） | `git diff --stat c7b01d82 -- tests/tools/web/test_diagnose_web_access.py`：无输出 | PASS |
| smoke 脚本零 diff | `utils/smoke_web_ci.py` 和 `utils/diag_web_batch.sh` 不在 S2 diff 中 | `git diff --stat c7b01d82 -- utils/smoke_web_ci.py utils/diag_web_batch.sh`：无输出 | PASS |
| challenge detector 零 diff | `web_challenge_detection.py` 不在 S2 diff 中 | `git diff --exit-code -- dayu/tools/web/web_challenge_detection.py`：exit 0 | PASS |
| README diff 符合预期 | `dayu/config/README.md` 和 `tests/README.md` 有 diff | `git diff --stat c7b01d82 -- dayu/config/README.md tests/README.md`：2 files changed, 4 insertions(+), 2 deletions(-) | PASS |

## 4. Findings

无 material findings。

## 5. Open questions

无。

## 6. Residual risks

| residual | 当前处理 | owner / destination |
|---|---|---|
| `utils/diagnose_web_access.py` 和 `tests/tools/web/test_diagnose_web_access.py` 的 mandatory transport 传播尚未执行 | plan fix 已明确授权前移；等待 Controller validation 后恢复 implementation | R02-S2 implementation |
| storage lifecycle/CLI/TTL/owner filename/publish/reconcile 仍在 utility 中 | plan 明确保留在 S3 删除 | R02-S3 |
| `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 和 `--max-network default=80` 仍在 utility 中 | plan 明确保留在 S3 由 typed diagnostic config 删除 | R02-S3 |
| S2 deterministic local smoke 三个 raw diagnostic cases 仍会失败 | plan 要求恢复 implementation 后重跑到 exit 0 | R02-S2 implementation |
| S2 `web_tools.py` coverage 79.9%（差一个 statement） | plan 要求逐 changed production file >=80%；恢复 implementation 后应通过新增 browser capability test 闭合 | R02-S2 implementation |

## 7. Conclusion

**verdict**：`PASS`

`R02-S2-DR-01` plan fix 已正确闭合 Controller 要求的所有项目：owner 最小前移、transport source 唯一性、禁止第二 default/parser/environment inference、假 blocker 移除、精确签名证明、中文 docstring gate、diagnostic direct/full test、deterministic local smoke closure、现有 diff 保持且恢复时序正确。S3/deferred scope 未泄漏。Controller validation F01 已修复关闭。无 material findings。

现有未提交 implementation diff 保持不变；plan fix 只修改了 plan 文档和 control doc。下一 gate 是 AgentDS 对同一 immutable final plan target 的第二路完整 re-review，然后是 Controller adjudication，最后才能恢复 S2 implementation。
