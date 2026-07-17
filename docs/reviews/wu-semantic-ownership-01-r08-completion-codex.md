# WU-SEMANTIC-OWNERSHIP-01 / R08 Completion Evidence（AgentCodex）

## 1. 结论与门禁边界

- **completion evidence 结论：PASS。** R08 的 accepted implementation、修复、复验、code rereview 与 aggregate deepreview 已形成闭环；R08 actual accepted residual 为 **0**，没有 open finding、blocker 或 deferred reviewer candidate。
- **本报告不是新 WU，也不是新 implementation。** 它只证明既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内 remediation sub-WU R08 的完成事实。
- **umbrella 仍为 active。** 本报告不能关闭 umbrella，也不授权进入 R09。
- **本报告之后唯一合法 gate：** Controller 对本 completion report 做完整 validation，随后形成包含本报告且 scope 精确的 completion commit；只有该 commit 被 Controller 接受后，才可开始 R09 plan。
- **本次写入边界：** 只新增本文件；不修改产品代码、tests、README、control、design 或 prior artifacts，不 stage、不 commit、不 push。

上述结论以 Git object、accepted plan/checkpoint、Controller adjudication、最终 validation 与 aggregate deepreview 的直接证据为准；较早的中间结果只作为时序历史，不覆盖最终事实。

## 2. Git lineage、tree 与 34-path exact scope

### 2.1 accepted implementation commit 对象事实

对 `2f701e9db3311cd1e1fc87a01fe95611b7cd90b9` 执行 `git cat-file -p`、`git rev-list --parents -n 1`、`git diff-tree --no-commit-id --name-status -r` 和 parent/tree blob 查询，得到：

| 项目 | 精确值 | 判定 |
|---|---|---|
| accepted implementation commit | `2f701e9db3311cd1e1fc87a01fe95611b7cd90b9` | R08 唯一 accepted implementation commit |
| parent | `2f013c5b36eebd55958c24d38d7acce90026b999` | 单 parent；不是 merge commit |
| tree | `96fc654b8aa77997a09791e68d33114d2d685755` | accepted tree |
| exact changed paths | 34 | 与 commit tree diff 一致 |
| scope 分类 | 23 product/test/README + 10 evidence + 1 control | 合计 34，无未分类路径 |
| 排序后 34-path manifest SHA-256 | `492da139f19b9461e6d4367a6910660bb6de2d9e7e2229d0f27a42900ea584ad` | 防止路径集合被口头概括替代 |
| commit diff stat | 34 files, 5379 insertions, 955 deletions | 仅作对象规模交叉核对 |

commit 内的 control blob 是 accepted implementation 提交前同步的 R08 gate 状态；commit 不可能在自身 blob 内引用尚未形成的自身 SHA。accepted commit SHA 及 completion-evidence next gate 由其后的 control transition 记录。本报告不修改该 control transition。

### 2.2 23 个 product/test/README paths 与 blob

下表中的 old blob 来自 parent tree，new blob 来自 accepted tree；全部为 mode-preserving modification。

| # | path | parent blob | accepted blob |
|---:|---|---|---|
| 1 | `dayu/fins/README.md` | `2466ca15feebecb1a90cefeba9c3b07f1229d9b9` | `713a8cf86b494ee9dd07816c498cbc96c3543af3` |
| 2 | `dayu/fins/domain/financial_result_contract.py` | `e52b548895eed42c794f5b782c1dec38cf2b23bb` | `6a18ce202d40f0a6c9a16af66a3726d1b167c3e5` |
| 3 | `dayu/fins/domain/xbrl_result_contract.py` | `2c0a960c6e5c57ba354918afdb8d839b0554368e` | `74cb634131303c8536058adfd0ad0ac5ca546f99` |
| 4 | `dayu/fins/pipelines/sec_fiscal_fields.py` | `a4f6f24476a9e0ead58182981a58500efa514c8d` | `70e2c82db9251b8e5bb5cfca2782348b098bb81d` |
| 5 | `dayu/fins/processors/bs_report_form_common.py` | `d2a6dcbd118b3975ca21cae685fe6de9d15ba545` | `867095671dc14ec252f9c55dd49e0c36822449b9` |
| 6 | `dayu/fins/processors/bs_six_k_processor.py` | `8bb45095a6cd8a6a46490d2a6727195f6f5c75a5` | `fa4c25dfda124ec0332ed47050a1d2d6a71f7a86` |
| 7 | `dayu/fins/processors/financial_base.py` | `1597383d52bd8a7b54f67b515c02ca5943933e79` | `77e863dd7a039dc4ce6010d5e6308bc0567043ea` |
| 8 | `dayu/fins/processors/html_financial_statement_common.py` | `5880cfaaed1cb179ed5910735ab299a164567ba9` | `483b672f735f49b9fb4b06cd895ca5dbab9dcf1d` |
| 9 | `dayu/fins/processors/report_form_financial_statement_common.py` | `1aab678ac38e91ed8083dff311423b8a608f4385` | `0c63d15fadc01ea2ca3bd3e9e4799112b60f313b` |
| 10 | `dayu/fins/processors/sec_processor.py` | `a7e317b0f3e7d93b0af6b7db32f5608819f01128` | `e74ec36aa740e426e90ddde54d74cb31eeac3c84` |
| 11 | `dayu/fins/processors/sec_xbrl_query.py` | `85138f24d1e8ff8df4b37e1e80c8e7a681248412` | `4690da853b6b6eaa2e27f0521cebda764a2875e6` |
| 12 | `dayu/fins/processors/six_k_form_common.py` | `9119dfef9a2112b12ef0c2e9431a4343f1839e66` | `8bbb33b76fd280caae1a3d57e7bd9febff9e1e86` |
| 13 | `dayu/fins/tools/fins_tools.py` | `20de7c74d46d247a2f770994bde287854e7dc4df` | `7436a8f3c52a7963425c3add8334d86267d08857` |
| 14 | `dayu/fins/tools/read_runtime.py` | `42785051ec0ec599e3cc0aa32b2b68b3bcb4bf3c` | `5f1f42c77c4980a05b12838632d4e3729785a516` |
| 15 | `dayu/fins/tools/read_runtime_helpers.py` | `dde761b6ccca2307df163f5b0d007b4b86fdb4a7` | `624f89034ff5fc4a5e00faf6a3492cf4d8b92de6` |
| 16 | `dayu/fins/tools/result_types.py` | `075828a05f68c8c555879e185f478c3566a7e5a0` | `ad61adf4f52540e776f00f0ae30caee53dc1c7d1` |
| 17 | `tests/README.md` | `f439e2109521a1cd3d0dd8209ef1f4d9ccd44bb3` | `89273b2fd29321a8430e1679bbb551ec1a5951a6` |
| 18 | `tests/fins/test_financial_read_contracts.py` | `df6986194b7f98b860aaaf6a7a11aa119210afda` | `63895afe396ef8c0d58f1650290d22a4fba5b0f2` |
| 19 | `tests/fins/test_fins_read_runtime.py` | `499769d0ee2005a4ade2b0bc9248a4ed90e56556` | `c1105b8906803fa6441adb0f4a71009806b98cfe` |
| 20 | `tests/fins/test_fins_storage_provider.py` | `860e9239da758f4140b13d8e36d64556141db217` | `cd2afa221b45a1cf6b4fc4d4170b26dbac3a58e7` |
| 21 | `tests/fins/test_processor_read_consistency.py` | `8fa5064968541327a9c62af103753cf24f5e3339` | `5a65f98ceee1316928a195df230d303f11c31180` |
| 22 | `tests/fins/test_read_runtime_semantic_ownership_guards.py` | `6f8e38910e27e3c28a7fde3d83b397d2281278bf` | `3030a9b1285462eb4ac68e04253c12723e0008bc` |
| 23 | `tests/fins/test_sec_pipeline_download.py` | `ea008eb1666ef91be5918b9e0c1d85de4bbef109` | `36b74e93b5b41410b17ebd9d19b64b3ed4378ab3` |

精确分类为：`dayu/fins/` 下 15 个 Python 文件 + 1 个 Fins README，`tests/fins/` 下 6 个 Python 文件 + 1 个 tests README，共 23。

### 2.3 10 个 evidence paths 与 blob

这 10 个路径在 parent tree 不存在，均由 accepted commit 新增；`∅` 表示无 parent blob。

| # | path | parent blob | accepted blob |
|---:|---|---|---|
| 1 | `docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-controller-adjudication.md` | `∅` | `65d8781c45cd8ee228e61cd0344d8fbfbf896628` |
| 2 | `docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-ds.md` | `∅` | `90ba2078d53b4fd57fb9d94e41c869012695e2ae` |
| 3 | `docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-mimo.md` | `∅` | `ed5ade127b6b451c7d56e553de0d631f2661eccb` |
| 4 | `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-controller-adjudication.md` | `∅` | `2ac5ae14c1d88bc2746802d75c483406287c2ff6` |
| 5 | `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-ds.md` | `∅` | `d878a5835a3485656a2358d7eb90b6e31db7a873` |
| 6 | `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-mimo.md` | `∅` | `daa4a40070abbc6ddc3192808d6bc139844de5e6` |
| 7 | `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-fix-codex.md` | `∅` | `2faf0fe9ef286c13417c0abc802caafa3af1f34e` |
| 8 | `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-fix-controller-validation.md` | `∅` | `ffd9439e5b726edab722c6923947ece778e2b004` |
| 9 | `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md` | `∅` | `a10354db15b58b25e4ee1104a3d00e0395a1d54e` |
| 10 | `docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md` | `∅` | `5a530510ee6686dd796867746133230a524ccf8d` |

### 2.4 1 个 control path 与 blob

| path | parent blob | accepted blob |
|---|---|---|
| `docs/host/issues-implementation-control.md` | `c191d4e7b6f26b211ab049ac7be38fb417aee14c` | `691adf5fe081e4a705ae9dc97df202a37a3b7e5f` |

23 + 10 + 1 = 34；不存在第 35 个路径，也不存在产品、测试、README、evidence、control 之外的偷带路径。

## 3. accepted plan、slice、correction、review、validation 与 deepreview chain

### 3.1 accepted plan checkpoint lineage

Git 历史显示 R08 在实现前和修复过程中有多个只承载 plan/control/evidence 的 accepted plan checkpoint；它们不是 implementation commit：

| checkpoint | 作用 | exact scope |
|---|---|---:|
| `19cbe8a054784297a593cfd6ea823bac40109b99` | 初始 R08 accepted plan + entry/review/fix/final rereview chain | 16 paths |
| `1eb896...` | S1 drift 后 cumulative validation plan correction | 13 paths |
| `0dc856...` | `R08-CR-PCF01` 计划修正及复核 | 7 paths |
| `65fd8...` | candidate exhaustion / `R08-CR-PCF02` 计划修正及复核 | 7 paths |
| `261df...` | coverage statement drift / `R08-CR-PCF03` 计划修正及复核 | 7 paths |
| `c723de...` | prefix-six exact drift / `R08-CR-PCF04` 计划修正及复核 | 12 paths |

这些 checkpoint 的 exact path 均只位于 plan、control、review/fix/validation evidence；未包含产品代码、tests 或 README。`git log --` 对 S1/S2 implementation artifact 的结果则只指向 `2f701e9...`，从对象历史上证明 S1、S2 没有独立 accepted implementation commit。

### 3.2 初始 accepted plan chain

初始计划的 source of truth 为：

- `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`
- `docs/reviews/wu-semantic-ownership-01-r08-plan-entry-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-final-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-final-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-final-rereview-controller-adjudication.md`

entry validation、双 reviewer、Controller adjudication、两轮 fix/validation/rereview 均齐全；最终 plan rereview 结论为 9/9 closed、0 deferred、0 blocker。

### 3.3 S1 blocked intermediate 与 S2 cumulative chain

- `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md` 的身份始终是 `implementation-self-check-blocked`。它只留下 S1 producer-side 中间证据：focused 98/50、147 diagnostic、modified-scope pyright 0，但完整 pyright 暴露 5 个需要 S2 public projection 才能闭合的传播错误。它从未被独立 accepted、stage 或 commit。
- `docs/reviews/wu-semantic-ownership-01-r08-s1-validation-plan-drift-controller-adjudication.md` 接受 `R08-S1-VAL-PD-F01..02`：S1 exact collection 不可独立完成，且 S1 固定覆盖率不能替代最终 cumulative 15-file exact-key 门禁。
- S2 不是第二个独立实现，而是 S1+S2 cumulative closure；`docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md` 明确记录 cumulative tree。
- 因此合法时序是 `S1 blocked intermediate -> plan correction -> S2 cumulative -> cumulative validation/review/fix/rereview/deepreview -> one accepted implementation commit`，不存在“两次 accepted implementation”。

cumulative validation plan correction chain 完整存在：

- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-controller-validation.md`

### 3.4 code review、correction 与再验证链

初始 cumulative code review：

- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-review-fix-codex.md`

`R08-CR-PCF01` plan correction 与双复核：

- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-rereview-controller-adjudication.md`

test-only continuation、candidate exhaustion、coverage drift、prefix-six exact drift 与 pyright stop/fix 的链依次完整存在：

- `docs/reviews/wu-semantic-ownership-01-r08-test-only-code-review-fix-controller-authorization.md`
- `docs/reviews/wu-semantic-ownership-01-r08-test-only-code-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-correction-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-correction-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-implementation-controller-authorization.md`
- `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-implementation-controller-authorization.md`
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-correction-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-correction-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-implementation-controller-authorization.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-implementation-continuation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-stop-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-fix-controller-validation.md`

最终 rereview 与 aggregate deepreview chain：

- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-controller-adjudication.md`

因此 accepted plan、slice、correction、implementation evidence、validation、code review/fix/rereview、aggregate deepreview 没有断链。

## 4. accepted findings 的最终 closure

### 4.1 plan 与 cumulative-plan findings

| findings | accepted 原因 | 最终 disposition |
|---|---|---|
| entry `R08-PE-F01..05` | 入口 scope、owner、验证与 gate 表述需闭合 | 全部在初始 plan fix/rereview 中 closed |
| initial plan `R08-PF01..07` | S1/shared fiscal evidence、reason action、citation/R07、SEC_EDGAR、fiscal enum、bool rejection、public type 命名 | 全部进入 plan 并由 final rereview closed |
| plan rereview `R08-RR-PF01..02` | shared node selection 必须精确；真实 ToolRuntime forced truncation 必须覆盖 | 全部 closed |
| `R08-S1-VAL-PD-F01..02` | S1 exact collection 不成立；S1 coverage 不能代替 cumulative 门禁 | cumulative plan correction 后 closed |
| cumulative correction `R08-CVPF01..03` | exact-key coverage manifest、真实 changed-Python Ruff manifest、aggregate fix 后全量复验 | 全部实现并 closed |

initial final plan rereview 的最终计数为 9/9 closed；以上 findings 没有 deferred 或 blocker。

### 4.2 code review、correction 与 validation findings

| finding | root cause / correction | 最终 disposition |
|---|---|---|
| `R08-CR-CF01` | shared test 中 4 个 generic/compat node 和 9 个 import 违反新 symbol boundary | 节点与 import 被删除；最终 code rereview closed |
| `R08-CR-PCF01` | 删除 compat node 后 coverage 必须通过 stable owner 的最小测试闭合，不能恢复兼容节点 | plan corrected，owner-level guards 执行；closed |
| `R08-CR-PCPR-F01`（PCF01 review 阶段） | typed fixture 的 `KeyError` 必须投影为 public `FinsReadArgumentError` | plan 与实现均修正；closed |
| `R08-CR-PCF02` | 5 个 test-only candidates 后仍不足 80%；需删除零调用 dead helper，而非堆测试 | `_collect_available_document_types` 删除，真实 typed/sorted owner 保留；closed |
| `R08-CR-PCF03` | 删除 dead helper 后 exact denominator 改变，需补一个 public resolver owner test | material/other/CN FY owner 分支由单一 public resolver 测试覆盖；closed |
| `R08-CR-PCF04` | candidate 6 实际新增覆盖行与计划算术不一致，必须 fail-close 修正 exact arithmetic | 计划与 prefix-six exact evidence 修正；closed |
| prefix-six `R08-CR-PCPR-F01..05` | 6 个陈旧 test 名、prefix 与 15-file 门禁混淆、时态、历史 baseline provenance、helper hash label | 全部修正并经双 reviewer/Controller rereview closed |
| `R08-VAL-PY-F01` | optional membership 未先窄化 | owner 边界显式窄化；full pyright 0，closed |
| `R08-VAL-PY-F02` | test fixture constructor 与 protocol 不一致 | fixture 改为 protocol-compatible typed constructor；closed |
| `R08-VAL-PY-F03` | XBRL union 未用 TypeGuard 完成严格窄化 | owner-side TypeGuard 修正；full pyright 0，closed |

这里有两个历史阶段都使用 `R08-CR-PCPR-F01` 字样：一个属于 PCF01 review，一个属于 prefix-six review。它们由 artifact 路径和阶段上下文唯一识别，二者都已 closed，不应把 ID 碰撞误判成遗漏。

最终 cumulative code rereview 的结论是 PASS：上述 accepted findings 全部闭合，MiMo 提出的旧 contract locator/raw-total/旧 reason 候选因前提已失效而 rejected-with-reason，DS 的问题均得到证据化分类；没有 open、deferred 或 blocker。

### 4.3 aggregate deepreview DS candidates O1..O5 / A1..A9

aggregate Controller 对 DS 的 14 个 candidates 逐项给出最终 disposition；全部是 **rejected-with-reason**，不是 deferred：

| ID | final disposition | 直接理由摘要 |
|---|---|---|
| O1 | rejected-with-reason | SEC fiscal fallback 仍由既定 pipeline owner 产生，不构成 R08 owner defect |
| O2 | rejected-with-reason | CN fiscal mapping 是 accepted owner 行为，没有第二真源 |
| O3 | rejected-with-reason | 所指兼容行为为 pre-existing 且与 R08 exact diff 无关 |
| O4 | rejected-with-reason | 所指 alias 不构成本 contract defect |
| O5 | rejected-with-reason | local helper 的边界职责不同，不是重复业务真源 |
| A1 | rejected-with-reason | blank concepts 合法进入既定 default query semantics |
| A2 | rejected-with-reason | accepted contract 已自足，不需要新增产品规则 |
| A3 | rejected-with-reason | typed input 与 public projection boundary 已成立 |
| A4 | rejected-with-reason | 与 O2 同一 CN owner 前提，未发现独立 defect |
| A5 | rejected-with-reason | 所指 normalizer 为 pre-existing owner，不是 R08 drift |
| A6 | rejected-with-reason | 不可达 defensive no-op 不改变 public semantics |
| A7 | rejected-with-reason | 分支是严格类型窄化 guard，不是业务 fallback |
| A8 | rejected-with-reason | copy 分别发生在不同 owner boundary，服务于 raw immutability 与 public isolation |
| A9 | rejected-with-reason | 所指文本是 internal message，不是 public/LLM-facing contract |

aggregate ledger 精确为：accepted 0、rejected-with-reason 14、deferred 0、blocker 0。MiMo aggregate deepreview 结论 PASS、zero finding；DS aggregate deepreview 的所有 candidates 都已被 Controller 最终裁决，故不存在“reviewer candidate 尚未 disposition”的尾项。

## 5. Topic 6 的实际闭合范围与语义 owner

`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` 对 Topic 6 的最终 adjudication 将 owner 问题拆为独立 sub-WU。R08 只实现其中的 **minimal financial/XBRL producer + single public projection**：

1. financial producer contract 产生最小 statement fields、coverage state 与七值 actionable reason；processor/pipeline 只提供 owner 输入，不在 tool/UI 下游重算。
2. XBRL producer contract 接收 typed query params，复制 raw facts 后 normalize/deduplicate，产生返回事实集合。
3. `dayu/fins/tools/result_types.py` 承担唯一 public projection schema；`read_runtime.py` / `read_runtime_helpers.py` 通过唯一 builder/projection path 暴露该语义，不另建第二套 public contract。
4. `fact_count` 唯一定义为 `len(returned deduplicated facts)`；raw provider count 只允许作为内部处理事实，不能冒充 public count。

R08 的边界不应被扩大：

- **R06/R07：** 只做 no-regression；没有把 R06/R07 再实现为 R08。
- **R09：** direct-stream 仍是 planned next sub-WU。
- **R10：** HKEX 仍为 planned sub-WU。
- **R11：** upload batch 仍为 planned sub-WU。
- **R12：** init/initialization 仍为 planned sub-WU。

这些 planned sub-WU 既不是 R08 residual，也不是 R08 已实现内容。将它们列入 R08 残余会错误地把正确 scope boundary 解释为 defect；将它们标为已完成则会伪造 umbrella 进度。

## 6. 最终 temporal truth 与验证锁

### 6.1 immutable locks

accepted tree 的重新计算与最终 artifacts 一致：

| lock | 最终值 | 重新核验方式 |
|---|---|---|
| product diff lock | `01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d` | parent 到 accepted commit 对 `dayu/fins`、`tests` 的 binary diff 做 SHA-256 |
| guards blob lock | `44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a` | accepted commit 中 guards 文件 blob 内容做 SHA-256 |

这两个锁是最终 code rereview 与 aggregate deepreview 的共同输入。任何后续产品/test 变化都会改变锁值并使本 completion evidence 失效。

### 6.2 最终验证事实

最终时序有效结果为：

| 验证 | 最终结果 |
|---|---|
| guards | 24 passed |
| prefix-six exact rerun | 392 passed；helper 391/485 = 80.61855670% |
| focused financial/XBRL groups | 119 passed + 50 passed |
| fiscal owner test | 1 passed |
| public projection group | 334 passed |
| forced truncation | 1 passed |
| smokes | 3 passed |
| aggregate affected suite | **392 passed** |
| full Fins | **859 passed, 1 skipped** |
| exact-key per-file coverage | **15/15，逐文件均 >= 80%** |
| full pyright | **0 errors** |
| changed Python Ruff | **21/21，0 error** |
| source/contract scans | A-G 全部通过 |
| diff check | accepted commit parent diff 通过 |

full Fins 的 1 个 skip 是既有 Docling 环境 gate，不是 R08 新增失败、finding 或 residual。最终 artifacts 还记录并区分了非失败 warnings；它们不改变上述 gate 结论。

S2 较早的 **390 passed / 857 passed + 1 existing environment skip** 只是当时 cumulative tree 的历史快照。后续 correction、candidate 6 和 pyright fix 改变了验证树；因此 completion truth 必须使用最终的 **392 / 859 / 15-of-15 / pyright zero / Ruff zero**，不得回退引用 390/857 作为最终结果。

本 completion gate 按用户约束没有重复运行大测试矩阵；它验证 accepted Git objects、锁值、source scans、smoke/validation artifacts 和最终时序一致性，避免用新的未受控工作树结果替换 accepted evidence。

## 7. contract 完整性与 no-regression 证据

### 7.1 README trigger

- `dayu/fins/` 和 `tests/` 被修改，故触发 `dayu/fins/README.md` 与 `tests/README.md`；accepted commit 确实只更新这两个责任范围内 README。
- Fins README 只同步 minimal financial current contract、XBRL typed params、copy/deduplicate 与唯一 returned count；tests README 只同步对应 contract tests。
- 根 README 的用户安装/入口/工作流未变化，`dayu/README.md` 的分层/装配边界未变化，`dayu/config/README.md` 的配置职责未变化；因此它们未被机械修改是正确的。

### 7.2 LLM-facing self-contained contract

accepted source scan 与 plan contract 对齐：public tool descriptions 自足说明字段含义、类型、必填性、允许值、reason 的下一步动作以及最小示例；没有要求模型理解 Python 类型名、内部 schema 名、历史迁移名或 Host 内部治理术语。内部引用标识没有被伪装成财报事实。

七个且仅七个 actionable financial reasons 为：

1. `unsupported_statement_type`
2. `xbrl_not_available`
3. `statement_not_found`
4. `low_confidence_extraction`
5. `scale_unavailable`
6. `period_semantics_unavailable`
7. `scale_and_period_semantics_unavailable`

每个 reason 在 LLM-facing description 中带业务可读含义与行动提示；没有旧 reason alias 或 loose parsing 分支。

### 7.3 raw facts、typed query 与唯一 count

- XBRL query params 由 typed contract 解析；optional 缺失与显式 `null` 不混同，布尔值不会被当作整数接受。
- provider raw facts 在 normalize/deduplicate 前复制，后续 projection 再隔离复制；这两次 copy 分属不同 owner boundary，不会反向修改 provider raw data。
- accepted tree 对 `fact_count` 的 source scan 只发现 public field/description/example、README/test 说明和唯一 builder assignment；生产赋值唯一为 returned facts copy 的长度。
- public contract 中不存在 raw/provider total 的第二 count，也没有 consumer 从 raw fields、日志、顺序或历史行为反推返回数量。

所以唯一业务事实是：`fact_count = len(returned deduplicated facts)`。

### 7.4 R07 snapshot/citation/opaque identity no-regression

- 34-path exact scope 未包含 R07 storage identity、snapshot 或 citation owner 模块；没有引入兼容 locator、path-like fallback 或 identity 重算。
- public citation 由既定 citation mapping 投影为隔离后的 plain mapping，不篡改 snapshot semantics。
- final AST/source scans 对 R07 相关 21 个函数做了 no-change 核验；final code rereview 与 aggregate deepreview 均未发现 opaque identity、snapshot/citation 的 regression。
- Host cursor/fetch-more envelope 与 Fins pre-Host result count 保持分层：Host 截断/游标不是第二个 Fins `fact_count` owner。

## 8. security、no-code 与 deferred-scope 证明

### 8.1 Topic 8 / Topic 9

- Topic 8 保持既有 **240 字符**通用异常 redaction/truncation；R08 没有为此新增代码、schema 或公共错误框架。
- Topic 9 的结论仍是**不建立统一 authorization framework**；R08 没有借 financial/XBRL contract 偷带统一权限抽象。

### 8.2 安全性质未弱化

accepted 34-path scope、source scans、code rereview 与 aggregate deepreview 共同证明下列既有安全 owner 未被弱化：

- workspace containment；
- symlink policy；
- DNS pinning / peer verification；
- resource budget；
- atomic publication；
- process fencing。

R08 没有把这些安全事实复制到 Fins public projection，也没有用下游 fallback 绕开 owner。

### 8.3 未偷带的 issues 与 trackers

`Issue 142`、`Issue 151`、`Issue 175`、`Issue 177`、`Issue 178` 均未进入 R08 accepted scope；Web、WeChat、render trackers 同样未进入。34-path manifest 中不存在相关 Host/UI/Service/Web/WeChat/render 路径，review/deepreview 也没有把它们标作 R08 已实现或 R08 residual。

R09 direct-stream、R10 HKEX、R11 upload、R12 init 继续留在 umbrella 的 planned next sub-WU 队列；这是一种明确的 scope ownership，不是 deferred reviewer finding。

## 9. 最终 residual ledger 与 completion gate 判定

| 项目 | 最终状态 |
|---|---|
| accepted plan findings | 全部 closed |
| accepted plan-correction findings | 全部 closed |
| `R08-CR-CF01` | closed |
| `R08-CR-PCF02..04` | closed |
| `R08-VAL-PY-F01..03` | closed |
| 其余 accepted correction/review findings | 全部 closed |
| aggregate DS `O1..O5/A1..A9` | 14/14 rejected-with-reason，0 deferred |
| MiMo aggregate findings | 0 |
| open findings | 0 |
| blockers | 0 |
| R08 actual accepted residual | **0** |

**AgentCodex completion evidence verdict：PASS。** `2f701e9db3311cd1e1fc87a01fe95611b7cd90b9` 是 parent `2f013c5b36eebd55958c24d38d7acce90026b999`、tree `96fc654b8aa77997a09791e68d33114d2d685755`、34-path exact scope 的唯一 R08 accepted implementation commit；最终锁、验证、review 与 deepreview 均指向同一 accepted tree。

**状态约束：** R08 可以进入 Controller completion validation，但 `WU-SEMANTIC-OWNERSHIP-01` umbrella 仍 active。下一步只能是 Controller 完整验证本报告并形成 exact completion commit；在该 commit 被接受前不得进入 R09 plan，更不得声称 R09/R10/R11/R12 已实现。
