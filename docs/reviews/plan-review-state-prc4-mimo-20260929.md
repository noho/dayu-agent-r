# UM-O14/O15 state plan PR-C4 独立 plan review

- RUNTIME/PROVIDER/MODEL: codex/mimo/gpt-5
- CANARY=mimo-40234d2e
- Review target：`/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md`
- Target SHA-256：`1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`，与任务锁定值一致。
- Review mode：只读 adversarial `$planreview`。唯一新增本 artifact；不实施 state/O12，不修改 plan/goal/旧 review/裁决/产品/测试/README，不 commit/push/PR/merge，不派发子 Agent，不调用 Goal tool。
- Scope：重点反证 PR-C4-F1 的 format/usage/public failure 唯一 owner 与同源投影、全 code 必填 hint、tool `invalid_argument`、direct/可达 awaited 一致性，以及 PR-C4-F2 的 alias/public reason 测试白名单和 focused 命令；兼审 O12/O34/UM-A09/F8-F11、三态目标动作、公司/材料原子 guard、O16/O05 等实施依赖。

## Reviewed Target And Scope

binding goal 为 `docs/gateflow/upload-material-state-goal-20260929.md`。本次实读 AGENTS.md、goal、总控 `docs/gateflow/upload-material-state-plan-review-adjudication-20260929.md`、Sol `docs/gateflow/upload-material-state-plan-prc4-fix-20260929.md`、上轮 `docs/reviews/plan-review-20260929-164438.md`，以及当前 `dayu/fins/upload_format_contract.py`、`ingestion_runtime.py`、`upload_failure.py`、`tools/upload_tools.py`、`direct_events.py`、`pipelines/docling_upload_service.py`、SEC/CN material workflow 和相关 owner/入口测试。

O12 依赖基线来自只读 checkpoint `/private/tmp/dayu-upload-o12`：

| 项目 | 一手结果 |
| --- | --- |
| checkpoint | `b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c`，`git rev-parse <commit>^{commit}` 完整匹配 |
| accepted plan | `docs/gateflow/upload-material-o12-company-plan-20260929.md` 在该 commit 内的 SHA-256 为 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`，与任务指定一致 |
| accepted adjudication | 实读 checkpoint 内 `upload-material-o12-plan-review-adjudication-20260929.md`；第五修订版双路均为 pass-with-risks，加入 O12-PR5-F1/F2/F3 实施硬条件后判 plan gate pass，产品未实施 |
| current product state | 精确检查未找到 `MaterialUploadPublishedState`、`_material_upload_admission`、`fs_material_upload_state_repository`；预期无匹配记录已明确打印，符合“accepted plan、产品未实施/集成” |

state plan SHA、O12 checkpoint/plan SHA 均满足停止条件前置，不存在 hash 漂移。

## Assumptions Tested

1. **PR-C4-F1 已把 format/usage fact 的 owner 和装箱边界钉死。** 成立。plan §5 明列当前 `_raise_upload_format_usage` 的第二构造反例，并规划 `upload_usage_contract.py` 唯一 producer：普通 usage 文案/hint 由 usage owner 产生，format 角色 message/public message/hint/file_label 由 format owner 提供，producer 只装箱；`upload_failure.py` 只做 closed code 到 public reason 的唯一映射。
2. **hint 对全 code 必填且在 owner 构造时校验。** 成立。plan 覆盖全部既有 usage code、三个 target code 和三个 format kind，要求 `hint: str` 为 1..240、非空、无控制字符/路径分隔符，并禁止 tool fallback 或第二张 code-to-hint 表。
3. **tool、direct、可达 awaited 的 message/hint/file_label 同源。** 成立。tool 只在普通 `ValueError` 前捕获 typed usage，保持 `invalid_argument`，取同一 fact 的 message/hint；direct 与实际可达 awaited 经 `upload_failure.py` 的同一 mapper 取 public_message/hint/file_label。稳定 target admission 不创建 job/observation，plan 不伪造不可达 awaited 证据。
4. **canonical label 不会在下游重新推导。** 成立。`upload_format_contract.py` 通过唯一 public-label helper 产生并验证 `FinsUploadFormatError.file_label`，plan 要求该值原样进入 usage fact 和 public reason，tool 不重新拼 label。实现时必须保持“公共 label helper 算法唯一、format error 携带值唯一”，不得在 format/usage/public mapper 复制 canonicalization 规则。
5. **PR-C4-F2 的 owner 测试缺口已补入计划。** 成立。S1、S2 和两条 focused pytest 命令均列入 `tests/fins/test_company_identity_storage_contract.py`，并要求 alias conflict、identity corruption、`retry_hint`、`file_label`、strict JSON round-trip 与 alias/漂移优先级。
6. **O12 是硬依赖而非当前 API。** 成立。plan 反复要求 accepted+integrated 后实读实际状态协议、公司 decision、独立 company commit、材料 writer-owned guard 和 active-only job 终态 API；当前产品缺少这些符号时禁止进入 S1。
7. **O34、UM-A09、F8-F11 与三态表没有回退。** 成立。公司合法独立提交后材料失败/取消保留公司事实；同指纹 tombstone 恢复保留旧版本、异指纹按现行 owner 递增；COMPLETE tombstone 保留完整可信 meta；material active-create 与 missing-update/delete 才升级 typed，tombstone create 维持既有 storage 拒绝。
8. **O16/O05 等前置依赖和原子 guard 边界足够明确。** 成立。计划固定静态字段/文件组合、稳定身份、exact 目标状态、O12 公司决策、lifecycle 的顺序，并把并发最终复验留在 O12 材料 writer-owned publication guard，不在市场 workflow、tool 或 CLI 复制状态机。

## Findings

无 material finding。

PR-C4-F1 的一手反例已被计划准确承认为待实施缺口，而不是被虚称既有行为；唯一 producer、format owner 四类事实、必填 hint、唯一 public mapper、tool/direct/可达 awaited 的投影和测试断言形成闭合实施边界。PR-C4-F2 的测试文件与 focused 命令也已补齐。

## Open Questions

- 当前 canonicalizer/validator 的算法 owner 是 `dayu/fins/direct_events.py`，format owner 负责把同一 canonical 值装入 `FinsUploadFormatError`。实施时应保持这一单一算法真源及逐值透传；若总控要求字面上的“format owner 独占 canonicalization 算法”，应先裁决是否迁移全部调用点，不能通过 re-export 或复制实现表面满足。
- raw `FinsUploadFormatError` 在 CLI 的 material file selection 边界仍可先于 runtime producer 出现；S1 的 CLI typed fact 断言必须覆盖该实际入口并消费同一 message/hint，不能只测 runtime `_raise_upload_format_usage`。

## Residual Risks And Tracking

- O12 accepted plan 尚未实施/集成，实际 `MaterialUploadPublishedState`、typed admission、公司独立提交、材料 guard、alias 优先级和 active-only terminal API 可能漂移。跟踪去向：O12 implementation gate + state plan §停止条件；漂移回 O12 owner/本 plan gate。
- O16/O05/O07/O09/O10/O17 的实际 owner/API 必须按计划顺序集成；state WU 不得临时 normalization 或补洞。跟踪去向：实施前 dependency checkpoint。
- O13 时间幂等、O18 amended、O33 auto 并发 skip、tombstoned create 新语义和 repair 授权仍在各自 work unit。跟踪去向：对应 goal/WU。
- 本轮为 plan review，不运行 pytest/pyright，也不授权实施；未来 implementation gate 仍须激活 `.venv`，执行 focused pytest、pyright、逐修改生产文件 coverage 和真实 CLI 状态矩阵。

## Execution Deviations

以下探索命令未满足“所有检查命令自身 exit 0”，均未作为结论证据依赖，并如实披露：

1. 一条 `rg` 符号/异常类型探索返回 exit 1（无匹配）；随后使用已存在的具体文件和行号读取，不以该无匹配结果作判断。
2. `rg` 查询同内容/overwrite 时误写不存在的 `docs/reviews/upload-material-um-o14-oracle-adjudication.md` 和 `docs/reviews/upload-material-um-o15-oracle-adjudication.md`，命令 exit 2；未从该探测得出结论，改读 goal、总控裁决、state plan 与真实代码/测试。
3. `rg` 查询 F8-F11 时重复使用上述不存在路径，命令 exit 2；随后只读取存在的总控裁决和 state plan，相关结论均有一手文本。
4. `rg --files docs | rg "upload-material-um-o..."` 无匹配返回 exit 1；该路径盘点不参与结论。

最终 hash 复核、O12 commit/plan SHA 复核、预期无 O12 产品符号检查、目标输出路径可用性检查和只读状态检查均 exit 0。没有产品改动、依赖安装、commit/push/PR/merge、Goal tool 或子 Agent 派发。

## Final Plan Review Conclusion

`pass-with-risks`

PR-C4-F1/F2 已形成可直接实施的唯一 owner 与测试边界；O12/O34/UM-A09/F8-F11、三态目标动作、公司/材料原子 guard 和 O16/O05 等依赖未发现 material 反例。风险来自 O12 产品尚未集成、canonical label 的底层算法 owner/格式事实 owner 需在实现时保持清晰分工，以及 raw CLI format 入口必须纳入 typed fact 测试。该结论仅表示计划内容可进入后续有效 gate；本轮存在披露的探索命令非零，严格执行协议不能记为全命令 exit 0 的有效 MiMo gate，也不授权 state/O12 实施。
