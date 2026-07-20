# WU-SEMANTIC-OWNERSHIP-01 / R08 coverage-statement drift implementation Controller authorization

## 1. Gate authorization

`AUTHORIZED_FOR_AGENTCODEX_IMPLEMENTATION`。

这是既有 umbrella WU 内部 R08 的 implementation continuation，不是新 WU。Accepted plan commit：

`261df95f54dbb8cece3919b898dc26ebe1582141` (`docs: accept R08 coverage drift plan`)

Final plan：

- path：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`
- SHA-256：`115a6429653e4011cf68fc9f3f7e9d7d08431696e0c1a80269c56d2de71dc401`

Plan review final ledger：0 accepted current finding、2 rejected reviewer candidates、0 blocker。无需 re-review。

## 2. Re-entry locks

AgentCodex 开始任何 proof 或 test mutation 前必须逐项匹配：

| Lock | Required value |
|---|---|
| stopped `dayu/fins + tests` binary diff | `3d9df8fefc485d0d19421fe6d2a3fe0402bf6f27d3b821d51125e039fa52ddf0` |
| `read_runtime_helpers.py` after deletion | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `read_runtime.py` actual owner | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards entry | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| staged tree | empty |

任一不匹配必须停回 Controller；不得在未知 drift 上实施。

## 3. Exact implementation delta

保留 stopped tree 中正确完成的 dead-helper deletion，不授权任何新的 production delta。

只允许修改：

`tests/fins/test_read_runtime_semantic_ownership_guards.py`

且 delta 精确限制为：

1. 在既有 `dayu.fins.tools.read_runtime_helpers` import block 中只新增 `resolve_document_type_for_source`；
2. 只新增 exact node `test_document_type_resolver_projects_material_other_and_cn_categories`；
3. node 提供完整中文 docstring，并直接调用无下划线 public owner，精确断言：
   - `UNLISTED_MATERIAL + SourceKind.MATERIAL.value -> material`；
   - `None + SourceKind.FILING.value -> other`；
   - `FY + SourceKind.FILING.value -> annual_report`。

禁止 direct `_resolve_document_type`、mapping constant、fake repository、monkeypatch、compatibility input、参数化 omnibus、empty execution、skip/xfail、coverage pragma/omit、其它 test/product/README/artifact delta。

## 4. Mandatory sequence

1. 匹配全部 re-entry locks，并执行 retained deletion / actual typed-sorted owner source/AST proof；
2. candidate 6 尚不存在时 fresh `coverage erase`，按计划 §6.6 exact 8-file命令运行 prefix-five；必须精确 `387/485=79.79381443%<80`；
3. 只有 prefix-five 精确匹配后才实施 exact candidate 6/import；
4. 再次 fresh `coverage erase`，运行相同 8-file集合 prefix-six；必须精确 `390/485=80.41237113%>=80`；
5. 过线后停止新增测试，再次 erase coverage，从零完整执行 §6.6/§6.7 全部测试、smokes、15-file exact-key coverage、full pyright、scoped Ruff、diff/source/propagation/README/security/scope scans；
6. 产出 `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-implementation-codex.md`，记录所有命令、exact results、proof JSON path/hash、final guards hash、cumulative diff hash、no-touch locks 与 residual risks；
7. 不 stage、不 commit、不 push、不建 PR，停回 Controller validation。

任一 exact numerator、denominator、threshold、fixture、test、scan、pyright、Ruff、no-touch 或 hash drift 都 fail closed 回 Controller；不得降低门槛、跳过、兼容或继续试探。

## 5. Scope boundary

R09-R12、Issues 142/151/175/177/178、统一 tool authorization、Topic 8-9 code、其它 Fins cleanup、Web/CLI/Host/Engine work 均未授权。Security containment、typed provenance/citation/read errors、revision/snapshot storage ownership 与其它既有安全机制保持不变。
