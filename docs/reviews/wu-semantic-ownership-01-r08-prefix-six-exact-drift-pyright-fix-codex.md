# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift pyright fix — Codex

## 1. Gate、授权与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- remediation sub-WU：`R08`；本轮是同一 R08 validation-fix gate，不是新 WU 或新 slice
- accepted plan：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`
- STOP artifact：`docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-implementation-continuation-codex.md`
- 唯一 Controller 裁决/授权：`docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-stop-controller-adjudication.md`
- accepted findings：`R08-VAL-PY-F01..F03`
- branch / HEAD：`phaseflow/host-issues-control` / `2f013c5b36eebd55958c24d38d7acce90026b999`
- Python / pyright / Ruff / pytest / coverage：`3.11.15` / `1.1.409` / `0.15.11` / `9.0.3` / `7.13.5`
- 最终状态：**PASS / THREE_FINDINGS_FIXED / FULL_REVALIDATION_GREEN / STOP BACK TO CONTROLLER**

第一性原理判断：12 个 pyright diagnostics 全部来自 R08 新增测试 owner 对正确 public contract / protocol 的类型消费方式，
不是 production contract 错误。正确修复边界是单一 guards 测试文件：先证明 optional key presence、让测试 processor
接受全部 protocol-valid constructor calls、用成功 public shape 的正向必有业务字段收窄 union。修改 production schema、
protocol、registry annotation，或使用 `.get()` 默认值、cast、ignore、弱类型与 compatibility facade，都会把测试消费错误
扩散到正确 owner，因此均未采用。

本 gate 已在修复后的新 tree 上从 entry locks、§6.7.G source/AST proof 开始，保留 prefix-five predecessor 且不回退、
不重跑 prefix-five，fresh 完成 prefix-six exact proof，并从零完整执行 §6.6/§6.7。全部门槛通过；未 stage、commit、push、
创建 PR、执行 code review、aggregate deepreview 或进入下一 gate。

## 2. Findings closure 与精确修改

唯一修改的测试文件：

```text
tests/fins/test_read_runtime_semantic_ownership_guards.py
```

| Finding | 状态 | Test-owner fix | 禁止路径核验 |
|---|---|---|---|
| `R08-VAL-PY-F01` | 已修复 | 在索引 `suggestion`、`caption`、`page_no` 前分别增加精确 `"..." in result` assertion | 未使用 `.get()`、默认值、cast、ignore；未改 schema |
| `R08-VAL-PY-F02` | 已修复 | `_DefaultConceptsXbrlProcessor` 的 test-only `taxonomy` keyword 改为业务合理默认值 `"US-GAAP"`；显式 `US-GAAP 2024`、custom taxonomy 与 failure test 能力全部保留 | 未改 production protocol、registry annotation；未用 cast/compat facade |
| `R08-VAL-PY-F03` | 已修复 | 新增 test-local `_is_xbrl_query_result(...) -> TypeGuard[PublicXbrlQueryResult]`，只用成功 contract 正向必有字段 `facts`；两个成功结果在访问 `query_params/facts/fact_count` 前显式 assert | 未使用 `Any`、cast、loose parsing、provider/internal-state 推断或 production fallback |

精确结构不变量：

- candidate 6 test、唯一 `resolve_document_type_for_source` import 与三条 material / other / FY assertion 均未修改；
- 原五个 stable-owner tests 均保留，六节点 cardinality 各为 1 且仍构成连续完整前缀；
- target file 仍收集 `24` 个 test nodes；八文件 aggregate / prefix-six 仍精确收集 `392` 个 nodes；
- 没有新增、删除、重命名、skip、xfail 或参数化任何 test node；
- production、其它 tests、README、design、control、plan、prior/controller/S1/S2 artifacts 均 no-touch；
- README trigger 已检查：本轮仅修测试类型证明，不改变用户可见 contract、测试职责、入口或分层关系，因此 README no-touch 正确。

内容锁变化：

```text
guards before: cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274
guards after:  44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a
binary diff before: e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f
binary diff after:  01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d
```

## 3. Focused validation

修复后首先执行：

| Command | Exit | Exact result |
|---|---:|---|
| `pyright tests/fins/test_read_runtime_semantic_ownership_guards.py` | `0` | `0 errors, 0 warnings, 0 informations` |
| `pytest tests/fins/test_read_runtime_semantic_ownership_guards.py` | `0` | `24 passed, 3 warnings in 1.45s` |

F01-F03 AST proof 进一步确认：XBRL TypeGuard 返回 `TypeGuard[PublicXbrlQueryResult]`，predicate 精确为
`"facts" in result`；taxonomy 是 optional keyword default；文件没有 cast/type-ignore/pyright-ignore。Focused pyright 与运行时
assertions共同证明 optional membership、protocol-valid constructor 和 union narrowing 均在 test owner 闭合。

## 4. Entry locks 与 §6.7.G pre-prefix proof

新 tree entry evidence：

| Lock | Result |
|---|---|
| tracked changed-path manifest | 精确 23 paths |
| tracked NUL manifest SHA-256 | `d04a659725063c42ea549e49b46f371b99d766f3a02a308e60efd24be78c092f` |
| cumulative binary diff SHA-256 | `01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d` |
| guards content | `44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a` |
| `read_runtime_helpers.py` content | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b`，no-touch |
| actual-owner `read_runtime.py` content | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657`，no-touch |
| shared runtime test content | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`，no-touch |
| S1 / S2 artifacts | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` / `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648`，no-touch |
| prefix-five predecessor JSON | `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb`，保留且未重跑 |
| staged tree | empty |

§6.7.G 在 prefix-six 前执行并通过：

```text
PASS old helper source matches=0
PASS old helper definition/caller/import=0; actual typed/sorted owner definition/caller=1
```

Guards AST proof：原五/candidate-six cardinality 均为 1、连续前缀、resolver import 精确 1；candidate 6 docstring、
三条精确 assertion 均存在，无 skip/xfail/coverage bypass。

## 5. Prefix-five predecessor 与 fresh prefix-six exact proof

Prefix-five predecessor 保持原 evidence，不回退 candidate 6、不 deselect、不重跑、不重写：

```text
391 passed
PREFIX_FIVE_PROOF dayu/fins/tools/read_runtime_helpers.py: 387/485 = 79.79381443%
workspace/tmp/r08-prefix-five-proof-coverage.json
SHA-256 43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb
```

Fresh prefix-six 使用 accepted plan 相同八文件、零 deselect：

```text
392 passed, 3 warnings in 22.27s
PREFIX_SIX_PROOF dayu/fins/tools/read_runtime_helpers.py: 391/485 = 80.61855670%
NEWLY_COVERED_LINES [344, 346, 348, 442]
PASS prefix-five/prefix-six direct comparison
```

Fresh prefix-six JSON：`workspace/tmp/r08-prefix-six-proof-coverage.json`，SHA-256
`d4ec8822a8df6443d6749cc1e8fcc719621440dd98815c38138a396231c7c7df`。因此 prefix-six exact truth、
first/shortest threshold-crossing 结论与 candidate 6 产品断言均未漂移；达到阈值后没有增加第七项测试。

## 6. 从零 §6.6 validation ledger

所有命令都从 repository root、激活 `.venv` 后在同一未提交 tree 上执行。

| Gate / command | Exit | Exact result |
|---|---:|---|
| S1 focused owner matrix | `0` | `119 passed, 50 deselected, 3 warnings in 4.07s` |
| S1 fiscal exact node | `0` | `1 passed, 3 warnings in 0.70s` |
| S2 focused/public six-file matrix | `0` | `334 passed, 3 warnings in 17.53s` |
| forced pre-Host → Host envelope → public `fetch_more` node | `0` | `1 passed, 3 warnings in 3.24s` |
| AAPL XBRL / HTML financial / no-statement 三节点 smoke | `0` | `3 passed, 3 warnings in 4.16s` |
| R08 aggregate eight-file matrix | `0` | `392 passed, 3 warnings in 17.86s` |
| full `pytest tests/fins -q` accepted rerun | `0` | `859 passed, 1 skipped, 3 warnings in 39.44s` |
| fresh cumulative eight-file coverage run | `0` | `392 passed, 3 warnings in 22.18s` |
| exact-key 15-file checker | `0` | 15/15 PASS，见下表 |
| full `pyright` | `0` | `0 errors, 0 warnings, 0 informations` |
| NUL-safe actual-changed Python scoped Ruff | `0` | `All checks passed!` |
| `git diff --check` | `0` | PASS |

第一次 full Fins 命令的工具会话在进程继续运行时只返回到 `66%`，没有提供 exit / final summary；该不完整捕获没有被当作
绿色证据。未修改 tree 后立即完整重跑并持续轮询到明确 `EXIT 0` 与上表 `859 passed, 1 skipped` summary。

真实 smoke evidence 保持：AAPL XBRL fixture 是
`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123`；HTML financial 与 no-statement 仍由
`tests/fins/test_fins_storage_provider.py` 中真实 filesystem repository 构造。唯一 skip 仍是未修改的真实 Docling upload
integration，需要 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`；本轮没有新增或修改 skip/xfail。三条 warnings 均为已安装
`edgar` 包的既有 deprecated-module warnings。

### 6.1 15-file exact-key whole-file coverage

Fresh cumulative JSON：`workspace/tmp/r08-cumulative-coverage.json`，SHA-256
`a0947bea291a3df685e9b907dcdb8ec8bff1f25965cfd042a00f01824eb9374c`。Production NUL manifest SHA-256
`1c74512a4b60eed7b7aa79d9fe77d1658f5be90f9c8f59328276fc2a13f87748`。

| Exact repo-relative JSON key | Covered/statements | Percent | Result |
|---|---:|---:|---|
| `dayu/fins/domain/financial_result_contract.py` | `178/201` | `88.55721393%` | PASS |
| `dayu/fins/domain/xbrl_result_contract.py` | `167/187` | `89.30481283%` | PASS |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | `254/278` | `91.36690647%` | PASS |
| `dayu/fins/processors/bs_report_form_common.py` | `139/166` | `83.73493976%` | PASS |
| `dayu/fins/processors/bs_six_k_processor.py` | `279/348` | `80.17241379%` | PASS |
| `dayu/fins/processors/financial_base.py` | `14/14` | `100.00000000%` | PASS |
| `dayu/fins/processors/html_financial_statement_common.py` | `572/712` | `80.33707865%` | PASS |
| `dayu/fins/processors/report_form_financial_statement_common.py` | `81/91` | `89.01098901%` | PASS |
| `dayu/fins/processors/sec_processor.py` | `247/290` | `85.17241379%` | PASS |
| `dayu/fins/processors/sec_xbrl_query.py` | `234/283` | `82.68551237%` | PASS |
| `dayu/fins/processors/six_k_form_common.py` | `421/514` | `81.90661479%` | PASS |
| `dayu/fins/tools/fins_tools.py` | `301/348` | `86.49425287%` | PASS |
| `dayu/fins/tools/read_runtime.py` | `840/975` | `86.15384615%` | PASS |
| `dayu/fins/tools/read_runtime_helpers.py` | `391/485` | `80.61855670%` | PASS |
| `dayu/fins/tools/result_types.py` | `138/138` | `100.00000000%` | PASS |

## 7. §6.7 source / AST / LLM / README / security / no-touch scans

| Scan | Result |
|---|---|
| §6.7.A internal raw/provider/reported total inventory | 0 matches，PASS |
| §5.5 financial/internal locator、method/empty、alternate reason inventory | 0 matches，PASS |
| §6.7.B public/tool/schema/serializer/LLM forbidden inventory | 0 matches，PASS |
| §6.7.C `fact_count` inventory | 仅 public typed field、owner description/example、唯一 `len(returned_facts_copy)` builder assignment、两份 current README；PASS |
| Public projection AST | 新 public types 存在、旧 tools types 不存在、`fact_count` production assignment owner 精确 1、builder annotations 无 `Any`；PASS |
| R07 no-touch AST | 名称 inventory 共 23 个相关函数；只允许两个 financial/XBRL projection owner 变化，其余 snapshot/borrow/release/revision/citation/source-changed 21 个函数与 HEAD AST 相同；PASS |
| Exact allowlist/security scan | tracked paths 精确 23；storage/Host/Engine/Service/UI/prompts/containment/symlink/atomic/security roots无 diff；PASS |
| Shared test correction scan | 四个已删 nodes、九个专用 imports/符号零命中；shared file content hash保持 `01db...6692`；PASS |
| Guards compatibility/private-helper scan | availability/capability、private helpers、旧 collector 零命中；PASS |
| README current-contract scan | 新增内容无 R08/slice/gate/review/future/未来计划文本；README no-touch；PASS |
| Topic 8–9 / deferred scan | Topic 8 no-code、Topic 9 安全机制 no-touch；R09-R12、Issues 142/151/175/177/178、统一 authorization 无实现；PASS |
| §6.7.G post-validation proof | old helper definition/caller/import 全零；actual typed/sorted owner definition/caller 各一；PASS |
| Staged / whitespace | staged empty；`git diff --check` PASS |

22 个非 guards tracked paths 的 content hash 与 STOP artifact manifest逐项一致，直接证明本 fix 没有触碰 production、其它 tests
或 README。完整测试、smoke、AST 与 source proof则重新证明该 no-touch tree 的产品行为仍满足 accepted contract，未把历史绿色
机械复用为新 tree acceptance。

## 8. Final 23-path tracked content manifest

| Path | SHA-256 |
|---|---|
| `dayu/fins/README.md` | `50c07ae625188c470c2818405d445772d073bc67496dcb58f57362720479dd4f` |
| `dayu/fins/domain/financial_result_contract.py` | `55a87fadce62b1c8d58ac206038d3f5144eaaaf30d4ef9ec82323c5240d7a34b` |
| `dayu/fins/domain/xbrl_result_contract.py` | `81844c4b08cae67f185e862ec69eafcb14ef848eec247bdbf127511a625fc2db` |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | `f99725e34f3ccbf52a2b8f152d403e3bddfc62f811597130e0df1d19752e0191` |
| `dayu/fins/processors/bs_report_form_common.py` | `78a6503405196022ed9a20936ea17707b36d5bb8940371388319f58fd0266506` |
| `dayu/fins/processors/bs_six_k_processor.py` | `745727883a2a35af717295506b9b57c6d8c130d976db5be2ee309602b177ede5` |
| `dayu/fins/processors/financial_base.py` | `c591e7538f68dc9cf25f50dbea0a061d7e658a4348bc30b5f4e0fd9769c9a374` |
| `dayu/fins/processors/html_financial_statement_common.py` | `c9a4795fedb7db0454e0ade0513289c68053ef78f535b1483df8dac433379628` |
| `dayu/fins/processors/report_form_financial_statement_common.py` | `c5cbe60cf34a2b623658656c925d4afe81874793822c2fe978f6c77467948fcd` |
| `dayu/fins/processors/sec_processor.py` | `f56fd3a35164eefc99d9e2d0f732f09f5823ad53287b96cd6107e107194e4f7b` |
| `dayu/fins/processors/sec_xbrl_query.py` | `3e787b8a08a5486474b1f72e71c8f4fd93c1bf01aafbc11bf32d9512a1a223f8` |
| `dayu/fins/processors/six_k_form_common.py` | `6fb5758cdc26dae6811f64e5ca0df8008c2030698bcb8fa1187aa368edc9c139` |
| `dayu/fins/tools/fins_tools.py` | `ab096833a249868b50dc25dde23a6a9c512bfe5fe757c7520df791dc077f7a4e` |
| `dayu/fins/tools/read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| `dayu/fins/tools/read_runtime_helpers.py` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `dayu/fins/tools/result_types.py` | `f7ee9d1c31e2e9e62c87bb717da229d0f3182e91af15ea9ac45121da76bd1d83` |
| `tests/README.md` | `6c0614afd2b4a6c1a78988cc4512e2b4d0e21528f8e5cc5af69959de8dfe0454` |
| `tests/fins/test_financial_read_contracts.py` | `75f6e7f6fee615eca9c1c26bc5af768ffc527677c66d9cf5b76cbaac5879c0a4` |
| `tests/fins/test_fins_read_runtime.py` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| `tests/fins/test_fins_storage_provider.py` | `a2885ce6fd62909a2760d900a46181984ea83e7351037905e28581eb5f27b872` |
| `tests/fins/test_processor_read_consistency.py` | `da55b5eb32a18eeef425a264fe9a172d888f9c2608dad9d9a0a098e4fe955459` |
| `tests/fins/test_read_runtime_semantic_ownership_guards.py` | `44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a` |
| `tests/fins/test_sec_pipeline_download.py` | `f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |

Additional evidence hashes：

```text
workspace/tmp/r08-tracked-changed-paths.nul   d04a659725063c42ea549e49b46f371b99d766f3a02a308e60efd24be78c092f
workspace/tmp/r08-changed-production-python.nul 1c74512a4b60eed7b7aa79d9fe77d1658f5be90f9c8f59328276fc2a13f87748
workspace/tmp/r08-changed-fins-python.nul     14afb51f3ee5748ebe93c6d04aead95e69027498fc10f09eaffcfb982c41bab1
workspace/tmp/r08-prefix-five-proof-coverage.json 43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb
workspace/tmp/r08-prefix-six-proof-coverage.json  d4ec8822a8df6443d6749cc1e8fcc719621440dd98815c38138a396231c7c7df
workspace/tmp/r08-cumulative-coverage.json    a0947bea291a3df685e9b907dcdb8ec8bff1f25965cfd042a00f01824eb9374c
```

本 artifact 自身无法在自身内容中嵌入稳定的递归 content hash；写完后由外部命令重算并在 handoff 报告。

## 9. Changed files、residual risks 与 stop

本 validation-fix gate 的 authored delta 精确为：

```text
tests/fins/test_read_runtime_semantic_ownership_guards.py
docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-fix-codex.md
```

Residual risks / uncovered areas：

1. **Environment-gated existing coverage:** 真实 Docling upload integration 仍由既有环境变量 gate 排除；该文件不在 R08 diff，
   本轮没有改变其 owner 或 skip。该项不是当前 finding，也不授权扩 scope。
2. **Existing dependency warnings:** 三条 `edgar` deprecated-module warnings 是环境既有状态，不影响 exit 或 R08 contract；本轮未修改依赖。
3. **Deferred boundaries preserved:** Topic 8 no-code、Topic 9 既有安全机制、R07 owners、R09-R12 与 Issues
   142/151/175/177/178 均保持原 owner/destination；没有新增 unclassified residual risk。

Completion decision：`R08-VAL-PY-F01..F03` 全部已修复，full revalidation 全绿；本 gate 到此停止回 Controller。
未 stage、commit、push、创建 PR、执行 code review、aggregate deepreview 或下一 gate。
