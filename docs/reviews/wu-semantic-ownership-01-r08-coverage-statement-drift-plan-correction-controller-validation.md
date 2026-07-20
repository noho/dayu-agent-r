# WU-SEMANTIC-OWNERSHIP-01 / R08 coverage-statement drift plan correction Controller validation

## 1. 结论

`PASS / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW`。

这是既有 umbrella WU 内部 R08 的 plan-correction validation，不是新 WU，也不授权实现、测试变更、code review、aggregate deepreview、commit、push 或 PR。

唯一最终计划：

`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`

最终 SHA-256：

`115a6429653e4011cf68fc9f3f7e9d7d08431696e0c1a80269c56d2de71dc401`

AgentCodex correction artifact：

`docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-codex.md`

SHA-256：

`1a082e37024e3e4cfbbfd1d4a196591d0c6ef488d1c93a44c117d416a14db683`

## 2. Controller validation finding 与关闭

Controller 首次读取中间计划 SHA `81b4eb985412513df96051dcfa9dc3e830611b5f127d19f5162eee3afc8a34d6` 时发现一项阻塞性计划缺陷：fresh prefix-five 命令仍排除了原 candidate 5 `test_search_next_section_projection_ranks_business_evidence_per_query`，因此命令实际只形成 prefix four，不能产生文字和 checker 锁定的 `387/485`。

该中间版本未被接受。AgentCodex 在同一任务 follow-up 中删除残留 `--deselect` 和前一 test path 的续行符，并将集合不变量写回完整计划。Controller 再次读取最终 §6.6，确认：

- prefix-five 与 prefix-six 命令各包含相同 8 个 test paths；
- 两段命令均无 `--deselect`；
- 当前 guards 中精确存在原五个候选节点，candidate 6 尚不存在；
- 计划顺序先在 entry guards 上运行 prefix-five，再只新增 candidate 6 exact node/import，最后运行 prefix-six；
- 因此 prefix-five 收集原五项，prefix-six 收集原五项加 candidate 6，共六项。

Controller validation finding 已关闭，未产生新的 accepted plan finding。

## 3. Accepted finding `R08-CR-PCF03` 覆盖

最终计划已完整保留并单指令化以下裁决：

- 保留正确 dead-helper deletion、old-helper zero proof 与 actual typed/sorted owner；
- coverage.py 根证据为 1 个 covered definition statement + 8 个 missing body statements，共 9 statements；
- Controller all-five `387/485=79.79381443%<80` 仅作 plan evidence，不冒充 implementation acceptance；
- 旧 `382/482`、`388/482` 与 candidate-4/5 first-prefix 预测明确 superseded；
- guards path 只授权 candidate 6 `test_document_type_resolver_projects_material_other_and_cn_categories` 与唯一 `resolve_document_type_for_source` import；
- 三条 direct public-owner assertions 精确覆盖 material fallback、missing filing form `other`、CN/HK `FY -> annual_report`；
- private `_resolve_document_type`、mapping constants、fake repository、monkeypatch、compatibility input、参数化 omnibus、empty execution、其它 test/product/README delta全部禁止；
- fresh prefix-five 必须精确 `387/485=79.79381443%<80`，fresh prefix-six 必须精确 `390/485=80.41237113%>=80`；任一 drift fail closed；
- 达标后停止新增测试，再次 erase coverage，从零执行完整 §6.6/§6.7；
- R09-R12、Issues 142/151/175/177/178、统一 authorization 与 Topic 8-9 code 继续 out-of-scope。

## 4. Protected tree locks

| Lock | Controller result |
|---|---|
| stopped `dayu/fins + tests` binary diff | `3d9df8fefc485d0d19421fe6d2a3fe0402bf6f27d3b821d51125e039fa52ddf0` |
| `read_runtime_helpers.py` after deletion | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `read_runtime.py` actual owner | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards entry | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| staged tree | empty |

`git diff --check`：PASS。

本 plan-only validation 未修改或运行 product code、tests、README、coverage acceptance、pyright 或 implementation。

## 5. Next gate

只允许 AgentMiMo 与 AgentDS 并发执行完整 corrected-plan review。Reviewer 必须审完整最终计划与 accepted finding，而不是只审最后的 `--deselect` 删除。Reviewer verdict 不独立授权实现；若有 accepted finding，必须回 AgentCodex 修复并双路完整 re-review。
