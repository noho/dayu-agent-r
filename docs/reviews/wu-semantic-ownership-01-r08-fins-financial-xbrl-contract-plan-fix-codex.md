# WU-SEMANTIC-OWNERSHIP-01 / R08 plan review fix — AgentCodex

## 1. Gate identity

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 umbrella |
| internal sub-WU | `R08` Financial/XBRL contract；不是新 WU |
| gate | plan review fix |
| timestamp | `2026-07-17 03:50:35 +0800` |
| source plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| reviewed plan SHA-256 | `9ddc11b6dbfc9559561ae619f47e2d237a7e999b88798eb861eae7483b0e2385` |
| fixed plan SHA-256 | `07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5` |
| Controller adjudication | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-review-controller-adjudication.md` |
| status | **FIX COMPLETE / READY FOR CONTROLLER VALIDATION** |

本 gate 只消费 Controller 的 `R08-PF-01..07` 七组裁决。两路 final corrected review 用于核对直接证据，不另行扩张 fix 清单。问题动机成立：七组均是 code-generation-ready 精度或 LLM-facing 安全契约缺口，不需要重新设计 owner boundary，也没有 product blocker。

## 2. Accepted fixes ledger

下表的“修复前”位置以 reviewed plan SHA `9ddc11b6...e2385` 为准；“修复后”位置以 fixed plan SHA `07268a12...ecde5` 为准。

| ID | 修复前 plan 位置 | 修复后 plan 位置 | 落实结果 |
|---|---|---|---|
| `R08-PF-01` | §3.4 line 158 把 `test_fins_read_runtime.py` 全归 S2；§5.1 lines 339-347 的 S1 test allowlist 不含该文件；§5.4 line 391 只有概括 propagation evidence；§5.6 lines 422-426 未锁定 exact ledger/hash | §3.4 line 158；§5.1 lines 360-374；§5.3 lines 394-405；§5.4 lines 422-431；§5.6 line 464 | S1 test allowlist 加入共享文件；固定 S1 fiscal fixture/node 与 S2 normalize/dedup nodes 的 symbol 边界和 focused commands。Controller 在 review 前锁定 base/status/changed paths、逐 path 内容 SHA-256 与完整 binary diff SHA-256，产出含文件、symbol、rule/message、已删 field/type、S2 owner/action 的 full-pyright exact ledger；诊断只允许四个预声明 S2 production paths，两路 reviewer 独立核对同一 immutable hash/ledger。 |
| `R08-PF-02` | §3.1 lines 89-101 只固定七值；§4.4 lines 284-292 未要求 reason 安全下一动作 | §4.4 lines 287-311；§6.2 line 514；§6.5 line 557 | 保留七值与 `unsupported_statement_type`，明确它表达 actual processor 无法服务全局合法 statement type，不是未来占位。`result_types.py` 同源 metadata/helper 拥有七值的业务含义和 LLM-safe 下一动作：不重复 unsupported/not-found，XBRL unavailable 改用可用抽取/其它 filing 并谨慎核验，low confidence 交叉验证，scale/period 不可靠时禁止相应数量级/跨期比较；文本不暴露 method/fallback branch。 |
| `R08-PF-03` | §4.3 line 273 仅给出条件性“若边界只暴露 mapping”，未固定输出类型与独立性 | §4.3 lines 255-280；§6.5 line 551 | 两个 builder 精确接受 `Mapping[str, JsonValue]`，立即复制为独立 `dict[str, JsonValue]`；两个 public result 的 `citation` 字段使用该 dict。测试必须证明不 alias、内容逐项等于同一 borrowed snapshot citation、无 revision/private key/path、新 signatures 无 `Any`。不改 `Citation` dataclass、不重枚举 keys、不改 R07。 |
| `R08-PF-04` | §4.4 line 300 错误使用 `source_type: "sec_filing"` | §4.4 lines 313-333；§6.5 line 557；§6.7.B lines 625-640 | 唯一最小示例改为 `SEC_EDGAR`，保留 `document_id` / `ticker` / `source_provider`。Description/example tests 消费当前 owner metadata/helper 并断言 LLM-facing 文本不存在 `sec_filing`；不新建 source mapping。 |
| `R08-PF-05` | §4.2 lines 212-238 只在 typed query params 使用 `FiscalPeriod`；§4.4 line 289 只要求列出允许值，未固定 tool input enum 同源 | §4.2 lines 217, 230-232；§4.4 line 311；§5.3 line 395；§6.2 line 517；§6.5 line 553 | S1 validator 与 S2 schema/tests 共享 `dayu.fins.domain.filing_semantics.FiscalPeriod` / `FISCAL_PERIODS`，值集精确为 `FY|H1|Q1|Q2|Q3|Q4`。`query_xbrl_facts.fiscal_period.enum` 从该 owner 派生，不建第二 literal owner；字段缺席时不补 `None`。 |
| `R08-PF-06` | §4.2 line 231 只概括要求 validator 拒绝 bool，未固定先后顺序与完整 test matrix | §4.2 line 232；§4.4 line 311；§5.3 line 396；§6.2 line 517；§6.5 line 553 | S1 `xbrl_result_contract.py` 在接受 `int | float` 前显式拒绝 `bool`；owner tests 覆盖 `True`、`False`、`int`、`float`、missing。S2 JSON Schema 保持 `type: number`，callable/schema test 证明 boolean 拒绝和 number 接受。 |
| `R08-PF-07` | §3.4 line 146 与§4.3 lines 241-280 未明确删除 tools 旧类型名；§6.2 line 473 只写“两个 typed public result” | §3.4 line 146；§4.3 lines 244-280；§6.2 line 513；§6.5 line 550 | Tools public types 精确命名为 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`，更新 direct imports、return annotations 与 tests；删除旧 tools `FinancialStatementResult` / `XbrlQueryResult`，不保留 re-export/alias/wrapper。Domain producer `FinancialStatementResult` / `XbrlFactsResult` 不重命名。 |

## 3. Rejected paths absence

| Controller 拒绝路径 | 缺席证据 |
|---|---|
| 把 dead `_build_financials_payload` 重构成 production path | Fixed plan §3.4 line 150、§5.2 line 382 继续只删除无 production caller 的 alternate owner 与其测试；未新增 production caller/owner。 |
| 增加第二个 complete/partial 示例 | Fixed plan §4.4 lines 313-330 仍只有一个最小 complete XBRL 示例；optional/partial 规则由自足文本表达。 |
| 重复扩写 method absent/empty 迁移 | Fixed plan 沿用§4.1 failure table 和§5.2 step 3 的既有 owner-terminal 归一；本 fix 未新增第二套分支或下游补偿。 |
| 重复扩写 flat query migration | Fixed plan 沿用§4.2 与§5.2 step 2 的既有 producer flat params 裁决；本 fix 只补共享 fiscal enum/bool 验证，未引入新 adapter 或 read-side 重拼。 |
| 修改 `Citation` dataclass 或建重复 `PublicCitation` | Fixed plan §4.3 line 276 显式保持 dataclass/`to_dict()`/R07 no-touch，只复制 borrowed mapping；没有第二 citation schema。 |
| compatibility alias/re-export/wrapper/shim | Fixed plan §2.3、§4.3 line 255、§6.2 line 513 明确禁止；旧 tools public type 名必须删除。 |
| 修改 Host、R07 citation/snapshot owner | Fixed plan §2.2、§6.4、§6.7.D 保留 Host governance 独立边界与 R07 no-touch；本 gate 未修改 code。 |
| 偷带 R09-R12、deferred Issues、统一 authorization | Fixed plan §2.3、§7、§8 继续列为 out-of-scope/后续；本 fix 未扩 allowlist。 |

## 4. Scope and validation evidence

### 4.1 Final status

- Final plan SHA-256: `07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5`.
- Plan status: `FIX COMPLETE / READY FOR CONTROLLER VALIDATION`.
- `R08-PF-01..07`: `7/7 closed in fixed plan`.
- Product blocker: `0`.
- Deferred accepted finding: `0`.
- 未执行 implementation、tests、pyright 或 README 更新；本 gate 为 docs-only plan fix，没有产品代码可验证。

### 4.2 Worktree status boundary

本 gate 开始时已存在用户 worktree 状态：`docs/host/issues-implementation-control.md` 为 modified，R08 plan、两路 review、Controller adjudication 和 plan-entry validation 为 untracked。本 gate 不触碰这些既有 control/old artifacts。Final `git status --short --untracked-files=all` 只在该基线上新增本 fix artifact；本次内容 delta 仅为：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-codex.md
```

未修改 control/design/code/tests/README/old artifacts，未stage/commit/push/PR。

### 4.3 No-index diff check

| 对象 | 命令 | 结果 |
|---|---|---|
| fixed plan | `git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` | `PASS`：零 whitespace/error diagnostic；exit `1` 只表示 untracked 文件与 `/dev/null` 存在预期内容 diff |
| fix artifact | `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-codex.md` | `PASS`：零 whitespace/error diagnostic；exit `1` 只表示 untracked 文件与 `/dev/null` 存在预期内容 diff |

## 5. Handoff

本 fix 停在 Controller validation。只有 Controller 完整验证 `R08-PF-01..07` 且锁定同一 fixed-plan hash 后，才可进入双路 complete plan re-review。当前不授权 implementation、commit、R09-R12、deferred Issues、统一 authorization、push 或 PR。
