# WU-SEMANTIC-OWNERSHIP-01 / R08 plan review Controller adjudication

## 1. Gate verdict

| 项 | 值 |
|---|---|
| reviewed plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| reviewed plan SHA-256 | `9ddc11b6dbfc9559561ae619f47e2d237a7e999b88798eb861eae7483b0e2385` |
| AgentMiMo review | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-review-mimo.md` / SHA-256 `0cd0c88e01d456e18d2e504a0f465da076fdae25ecc58cec61684f1b1537af89` |
| AgentDS review | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-review-ds.md` / SHA-256 `169fa79ba971547bbd4bf1585c9fcea299e947332f4a836e0022fa20306d2c9b` |
| verdict | **FIX REQUIRED / 7 accepted plan-fix groups / 0 product blocker** |

R08 仍是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 internal remediation sub-WU。当前只授权 AgentCodex 修改既有 plan 和生成一个 plan-fix artifact；不授权 implementation、stage/commit、R09-R12、deferred Issues、统一 authorization、push 或 PR。

## 2. Evidence corrections before adjudication

Controller 没有把 reviewer 初稿直接当作事实：

1. AgentMiMo 初稿把 `_resolve_processed_fiscal_fields(..., financials_payload, ...)` 的参数误读为 `_build_financials_payload(...)` 调用。全仓引用证明 `_build_financials_payload` 只有定义和三个 test caller，无 production caller。MiMo 已撤回 `R08-MIMO-F01` 并修正 artifact；AgentDS 独立得到相同结论。
2. 两路初稿都把 `dayu.fins.domain.tool_models.Citation` 误称 TypedDict。它实际是 frozen dataclass，`to_dict()` 当前返回 `dict[str, Any]`。两路均已纠正，不再建议把 dataclass直接当 public JSON TypedDict。
3. AgentDS 初稿 severity/count 不一致已修成 `4 medium + 3 low`；MiMo 将 `FinancialScale` 修正为 Literal TypeAlias。
4. 两路都通过代码真源确认 plan 示例中的 `source_type: "sec_filing"` 不存在；当前 SEC citation 值是 `SourceType.SEC_EDGAR.value == "SEC_EDGAR"`。

因此 final adjudication只基于修正后的 review artifacts与 Controller 直接代码核对。

## 3. Accepted plan-fix groups

### `R08-PF-01` — S1 internal checkpoint exact propagation evidence

**来源**：`R08-MIMO-F03`、`R08-PR-DS-01`，并合并 Controller direct finding `R08-PR-C01`。

接受范围：

- S1 仍是未提交的破坏性 contract checkpoint，不能用 compatibility field、cast、ignore、shim 或临时 adapter伪造 full pyright green；也不增加 S1 commit。
- S1 implementation完成后、双路 review前，Controller validation必须固定受保护 tree/diff hash、运行 full pyright，并产出逐条 propagation ledger：文件、symbol、已删除 producer field/type、对应 S2 owner/action。只允许落在四个预声明 S2 production paths；其它任何错误使 S1失败。
- 两路 reviewer必须独立核对同一 ledger和同一 immutable tree，不能凭“将在 S2 修”放过未登记错误。
- `tests/fins/test_fins_read_runtime.py` 直接拥有 `_extract_fiscal_from_xbrl_query` 的 XBRL producer-contract fixture，必须加入 S1 test diff allowlist；S1 只允许迁移该 fiscal consumer/fixture相关 nodes，S2 再迁移同文件的 read normalize/dedup tests。计划需写清共享文件的逐 slice symbol boundary与 focused commands。

此处是固定两-slice/no-compat约束下的明确 review checkpoint，不是 accepted product state；S2/full pyright最终必须零。

### `R08-PF-02` — financial reason 的 LLM-safe next-action projection

**来源**：窄化接受 `R08-PR-DS-02`。

接受范围：

- 七值闭集保持不变；不得删除 `unsupported_statement_type`。它不仅服务 LLM schema invalid input，也表达某个 actual processor无法服务一个全局合法 statement type 的业务结果，属于已裁决的 `unsupported` 值。
- `result_types.py` 同源 description metadata/helper必须为每个 reason给出简洁业务含义与安全下一动作，且不得暴露 processor method/fallback branch。
- 动作至少覆盖：不要重复同一 unsupported/not-found请求；选择其它合法 statement type或 document；XBRL unavailable时使用可用 extraction/其它 filing并谨慎核验；low confidence需交叉验证；scale/period不可靠时禁止相应数量级/跨期比较。

拒绝 reviewer 提出的“未来扩展占位”解释；当前没有为未来保留 dead value的授权。

### `R08-PF-03` — exact citation JSON typing strategy

**来源**：`R08-MIMO-F02`、`R08-PR-DS-03`。

最终裁决：

- 不修改 `Citation` dataclass、R07 snapshot/citation生成或字段语义；`dayu/fins/domain/tool_models.py` 不扩入 R08 allowlist。
- 新 financial/XBRL public builders 接收 `Mapping[str, JsonValue]`，立即复制为独立 `dict[str, JsonValue]`；两个 public result 的 `citation` 字段也使用 `dict[str, JsonValue]`。
- 不建立第二个 citation字段真源、不重新枚举/校验/推断 citation keys、不 cast、不 alias旧 `dict[str, Any]`；R07 `_build_citation` 的既有语义保持 no-touch。
- tests断言输出是独立 mapping、内容逐项等于同一 borrowed snapshot citation、无 revision/private key/path，并由 pyright证明新 signatures无 `Any`。

拒绝把 `Citation` dataclass直接标成 JSON TypedDict，也拒绝为 R08 新建重复 `PublicCitation`字段 schema。

### `R08-PF-04` — citation example uses current SourceType truth

**来源**：`R08-MIMO-F06`、`R08-PR-DS-07`。

Plan最小示例把 `citation.source_type` 从不存在的 `sec_filing` 改为 `SEC_EDGAR`，保留同一示例中的 `document_id`、`ticker`、`source_provider`。S2 tool description/example测试必须从当前 owner metadata/helper消费并断言不存在 `sec_filing`；不得为示例另建 source mapping。

### `R08-PF-05` — fiscal_period input schema and typed query params share one enum

**来源**：接受 `R08-PR-DS-05`。

`query_xbrl_facts` input schema 的 `fiscal_period` 必须使用现有 `FiscalPeriod` 真源值 `FY|H1|Q1|Q2|Q3|Q4`，而非只在 description举例。S1 producer query-param validator与S2 tool schema/tests必须消费同一值集；无字段时继续省略，不补 `None`。不得新建第二份 enum literal owner。

### `R08-PF-06` — bool is rejected at the XBRL producer query-param validator

**来源**：接受 `R08-PR-DS-06`并精确化 `R08-PE-F02`。

S1 `xbrl_result_contract.py` 的 `min_value/max_value` validator必须在接受 `int | float` 前显式拒绝 `bool`，并以 owner tests覆盖 true/false、int、float、missing。S2 JSON schema `type=number` 保持标准行为并增加 callable/schema test；不得依赖 Python `bool` 是 `int` 的偶然继承关系。

### `R08-PF-07` — public result names are explicit and have no compatibility aliases

**来源**：接受 `R08-PR-DS-Q01`。

S2 将 tools projection types明确命名为 `PublicFinancialStatementResult` 与 `PublicXbrlQueryResult`，与 domain producer `FinancialStatementResult` / `XbrlFactsResult` 分离。更新 direct imports、return annotations与 tests；删除旧 tools public type名，不做 compatibility re-export/alias/wrapper。Domain producer type不重命名。

## 4. Rejected, withdrawn and no-fix opinions

| Reviewer item | disposition | 理由 |
|---|---|---|
| `R08-MIMO-F01` | withdrawn / closed | 修正后的全仓调用图证明 plan 的 dead alternate owner删除正确 |
| `R08-MIMO-F04` | rejected as duplicate | plan §4.1 failure table、§5.2 step 3、§5.3 tests已逐字覆盖 method absent/None/empty→`statement_not_found` |
| `R08-MIMO-F05` | rejected as duplicate | plan §4.2、§5.2 step 2与 tests已要求 producer flat keys、删除 `filters_applied`、read不重拼 |
| `R08-PR-DS-02` 删除/未来占位分支 | rejected | user/umbrella已裁决保留 actionable `unsupported`；actual processor对全局合法type仍可能 unsupported |
| `R08-PR-DS-04` | rejected | 一个最小 complete示例加自足文本中的 optional/partial规则已满足最低认知负担；第二示例不是必要契约 |
| `R08-PR-DS-Q02` | superseded by `R08-PF-04` | current code已给出唯一答案，不是 open question |
| S1 separate worktree alternative | rejected | 不减少 S1 tree自身的传播错误，也增加非必要 orchestration；protected hash/ledger足够 |

## 5. Final ledger

| 类别 | 数量 |
|---|---:|
| accepted plan-fix groups | 7 |
| withdrawn reviewer finding | 1 |
| rejected / duplicate / superseded opinions | 7 |
| deferred finding | 0 |
| product blocker | 0 |
| open question requiring user | 0 |

所有 accepted group必须由 AgentCodex 在同一 plan artifact中修复并生成 `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-codex.md`。Controller随后完整验证 `R08-PF-01..07`；只有验证通过才进入同一 fixed-plan hash的双路 complete re-review。不得把任何 accepted group留为 implementation阶段临时判断或后续优化。

## 6. Next gate

下一 gate 是 AgentCodex plan-only fix。唯一允许修改/新增：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-codex.md
```

不允许修改 control、design、product、tests、README、旧 review/controller artifacts，不允许 stage/commit/push/PR。
