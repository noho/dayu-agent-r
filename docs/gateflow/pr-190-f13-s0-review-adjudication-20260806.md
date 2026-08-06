# PR 190 F13 S0 Review 裁决

## Gate metadata

- Gate：S0 review adjudication
- Base：`2d914beefb7bdee3e762df06f5f1ef0d115da143`
- 被审实现：`docs/host/design.md`、`docs/gateflow/pr-190-f13-s0-design-implementation-20260806.md`
- MiMo review：`docs/reviews/code-review-20260806-145045.md`
- DeepSeek review：`docs/reviews/code-review-20260806-145052.md`
- Controller：AgentController

## 裁决原则

只接受能消除 owner / contract 歧义或补齐可复核证据的 finding；不因排版偏好把同一语义复制到多个位置。所有接受项必须在原设计 owner 或 Gateflow evidence artifact 中修复，不进入下游 consumer 补偿。

## MiMo findings

| ID | 裁决 | 处理 |
|---|---|---|
| M1 `CompactAcceptedTruthV4`字段不完整 | ACCEPT / FIXED | §24.3新增完整typed shape：proposal、replacement、boundary、coverage、audit、current input与private permit，并明确frozen/slots、无默认值和validator边界。 |
| M2 reactive multi-pass聚合不精确 | ACCEPT / FIXED | §25冻结pass-local full accept、audit proposal与replacement的不同聚合、retained-first/new-second顺序、atom不可拆分、root final binding/caps/coverage/union重验及single terminal。 |
| M3 implementation artifact缺goal逐项映射 | ACCEPT / FIXED | S0 implementation artifact新增8项Confirmed goal映射表。 |
| M4 boundary字段约束位置分散 | REJECT WITH REASON | 字段shape与紧随其后的同一§24.3约束已经形成一个连续contract，且完整覆盖source refs、evidence refs、kind与empty规则。复制约束到伪类型内部会形成第二份易漂移规范；这只是排版偏好，不构成语义缺口。 |

## DeepSeek findings

| ID | 裁决 | 处理 |
|---|---|---|
| D1 空evidence refs检测点不明确 | ACCEPT / FIXED | §24.3固定material-pack/source-boundary构造为canonical detection point；在任何runner-call/manifest前non-repairable fail，不消耗attempt、不写attempt-rejected、不进LLM repair；durable validator只做defense-in-depth。 |
| D2 `PromptLocalProvenanceEntry`缺完整shape | ACCEPT / FIXED | §24.3新增完整字段、tuple provenance clean replacement、frozen/slots/无默认值与按source kind的empty/non-empty约束。 |
| D3 scan声称缺方法和计数 | ACCEPT / FIXED | S0 implementation artifact记录全文扫描范围、patterns、命中计数和两处legacy negative-only命中解释。 |
| D4 descriptor v2与body v4版本易混淆 | ACCEPT / FIXED | §24.4明确descriptor schema与body schema是独立显式契约；reader必须验证body `schema`，不得从descriptor名字猜版本。 |
| D5 all-clear语义未裁决 | ACCEPT / FIXED | §24.3固定非空boundary下五类全空为`EMPTY_SEMANTIC_OUTPUT` typed reject；section清空与retain-only仍合法，空boundary不调用compactor。 |

## Controller verification

- `git diff --check`：通过。
- active v3 type/schema/function全文扫描：0命中。
- required v4 selector、accepted atom/replacement/truth、per-fact refs与schema-5均有直接命中。
- 两处`accepted_candidate`与两处`schema-4`只在fresh reader拒绝旧shape及negative owner tests出现。
- Engine design全文truth check确认owner未变化，无文件diff。

## Gate status

所有accepted findings已在owner文档或evidence artifact修复；M4以避免重复真源为由拒绝。等待两位原reviewer对同一finding IDs执行re-review，Controller在收到结果前不接受S0。
