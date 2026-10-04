# upload_material registry S1 集中 fix 恢复记录

Task：`upload-material-registry-code-fix-sol-20261004-02`。当前 gate：`fix`；状态：四项已修，交总控安排同版独立 re-review。本记录不宣称 S1、code review 或整个 WU 通过，也不进入提交、推送或 PR gate。

## 身份与依据

- 唯一 workspace `/Users/leo/workspace/dayu-agent-r`，分支 `codex/upload-material-oracle`，HEAD `d054c0fece08d3fb5b3ed71207b3dbb8ec7f5d8c`。`main` 未动。冻结十四候选在修改前逐 bytes/SHA 与 `code-review-freeze-01/manifest.json` 一致；manifest SHA `4870a6891c9fe4c23cc9ef6acc312442dc6913a6923c80401a3166ef7d0b2317`。
- Accepted plan SHA `896762824e3de6ba7538fc710fc13fb8a5f33838788dd84335b7efea7f3ddad0`；root 最终四项裁决 SHA `c6803d5a1ef21b8ca93652358e7d102d216fd3d13ac5e1d799a1383dbbd2f333`。MiMo 与 DS 原报告及 root 反例为定位输入；本轮未改原报告或裁决。
- 请求路由 codex/gpt-6-sol，后台实际模型 metadata 未暴露，记录 `unknown`，不作阻塞。CANARY 由本轮指定文件实际读取：`gpt-6-sol-fea9275e`。

## 四项修复与 owner

| Finding | 状态 | 登记 owner 修复 | owner 合同证据 |
|---|---|---|---|
| REG-C01 focused 终态 | 已修复，待 re-review | validator 将每个 focused row 的 `required_evidence` 与冻结 `focused-source.measurements` 精确对齐，从 PDF `result.json.actual_wait/exit` 或 XBRL `actual-exit.json.actual_wait/actual_exit` 读取终态；同时核 measurement、assignment、scenario 的 wait/exit/outcome 与 `result_ref`。130 仅对应现有 SIGINT cancel，0 对应 success；未知结果拒绝。 | `test_focused_terminal_is_bound_to_original_result` 逐字段反例；当前六原件经完整 producer 正例。 |
| REG-C02 六维覆盖 | 已修复，待 re-review | old 802 从冻结 matrix/parser/pairwise 得 mandatory；focused 六测量从原 command argv、冻结 parser canonical option、批准的六 case 输入分类/状态取得独立 expected claims。row claims 为 covered 来源，逐 row 精确比较，再逐维求集合差；九 no-credit 保排除。 | `test_focused_six_dimensions_reject_fabricated_or_missing_credit` 六维正反、`test_coverage_cannot_trade_missing_state_for_extra_command`。当前正式六维为 35/61/0/166/217/50，均零 gap。 |
| REG-C03 必填、类型、血缘及 source | 已修复，待 re-review | oracle 已有必填字段、authority basis 与十九批准关系、裁决 identity/结果、allowed variants；new scenario 已有二十字段、关键枚举、precondition、invocation、observed 八字段逐项校验。scenario/source ID、cwd/stdin/input_class/state、run bundle/report ID/SHA/relative ref 均与原 command、assignment 两 source 及 frozen focused source 绑定。缺 row 字段先校并带 `assignment.rows.N.ID.field` 定位。 | `test_material_oracle_rejects_each_missing_contract_field`、`test_new_oracle_rejects_wrong_authority_and_adjudication_shape`、`test_new_scenario_required_shape_and_enums`、`test_new_scenario_rejects_each_missing_observed_field`、`test_scenario_report_identity_is_bound_to_its_source`、`test_scenario_invocation_tracks_original_command`、`test_missing_assignment_field_keeps_row_locator`、`test_source_bundle_identity_cannot_be_relabelled_with_scenarios`。 |
| REG-C04 crash 分类 | 已修复，待 re-review | 两条旧 source 的 `process_outcome.signal=9`、`actual_wait_returncode=-9`、`harness_deadline_kill=false` 决定 `path_kind=crash`；保 `execution_outcome=error`。只改两个新 scenario 的 `path_kind`，不按 case ID 前缀或添加 outcome。 | `test_real_sigkill_result_requires_crash_class_without_rewriting_outcome` 从两份原 result 直接核；完整 producer 正例。 |

同一 producer `validate_upload_material_registration` 产生一个 report、两份 proof；两个 registry 仅投影此结果。原 6 oracle、1328 scenario 与各自 opaque 历史 proof 全值保持；唯一新 oracle 和十九 predicate 的 expected/forbidden 连同全部其它新 oracle 字段也与原冻结候选全值相同。799 个新 scenario 仅两条 `path_kind` 从 `negative` 改为 `crash`。原 execution outcome、Raw、case facts 与 assignment 不变。

## 当前验证与重投影

- `.venv` 下 `python -m pytest tests/cli/test_cli_ci_upload_material_registry.py tests/cli/test_cli_ci_run_observation.py -q`：actual exit 0，166 passed。`python -m pyright`：actual exit 0，0 errors/0 warnings/0 informations。最终同源码版本重跑，双流各自保在独占 `code-fix-sol-02/`。
- 原成功 strict CLI argv 仅将 `--output` 改为独占 fresh path；四 public roots、source root、target `22eca6c313005e3c5185340f2d6b535ab2583056` 与 `--check` 不变。actual exit 0。producer、strict 输出与两 registry 内嵌 proof 逐值相同，proof SHA `196d933a99a8503a5cf6ae9550114fdcc0dd3d5b41d8cf4f32a9c435595ad532`。
- 新计数：原 source 802，focused source 6，正式 799，排除 9，一个 oracle，十九 predicate；PAIR66 仍 66/66。focused 已冻结 40 个 public 文件双副本 SHA 全同原 manifest；五个实测产品模块 live SHA 同原 source。没有重新导出、scan 或运行 PDF、XBRL、native、原 802。
- 当前审查目标为 `docs/gateflow/evidence/upload-material-registry-20261003/review-target.json`（SHA `ad334bcbcb336a395ebf31c1b224c060233346d1f86a063be1f6705428f87260`）及独占 `code-fix-sol-02/code-review-target.json`（SHA `05c068f9b724ce6bca54e49ce05696c9412eefb51a23d9545d67092a499428d3`）；当前 bounded validation/proof 已刷新。旧 code-review freeze manifest 与旧失败日志不覆盖。

## 文档决策和剩余风险

现有 `docs/cli_ci.md` §4.6/5.1 已写同一 producer、独立六维、source/ref 和人工语义核边界；`tests/README.md` 已有本测试文件定位。此次内部 validator contract 收严未改变最终用户工作流，不改二者或根 README。测试、源码、两 registry 与三份当前 bounded evidence 是本轮改动；root 自有 control/handoff dirty 维持原 owner。

Gateflow residual 分类：四项机器登记缺口为 **fixed in current slice**，仍须独立 re-review；Win/Linux XBRL、历史 Raw 与既有 22 residual 为 **assigned to later work unit**；Docling 抽取质量为 **tracked by existing issue #4437**；**covered by later approved slice** 与 **requiring new issue or explicit user decision** 当前均无新项。机器 `ready` 只说明登记闭合，不代替原十九条业务语义的人工审查或整个 WU pass。

完整实际 argv/exit/双流 SHA、失败恢复、before/fullvalue/audit、当前 bytes/SHA、五类 residual 与禁止操作见 `workspace/tmp/upload-material-registry-20261003/code-fix-sol-02/result.json`。本轮未派发子 Agent、未 stage/commit/push、未作网络写。
