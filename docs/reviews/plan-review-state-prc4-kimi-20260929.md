# UM-O14/O15 state plan 独立 plan review（Kimi，PR-C4 最终候选同版复审）

- RUNTIME/PROVIDER/MODEL: codex/kimi/kimi（canary `kimi-74886b45` 与派发标识一致；具体模型版本号无法从运行时内自证，如实披露，不猜写）
- CANARY=kimi-74886b45
- Review target：`/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md`
- Target SHA-256：`1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`（本机 `shasum -a 256` 实测，与任务锁定值一致）
- Review mode：只读 adversarial `$planreview`。唯一新增本 artifact；不实施 state/O12，不修改 plan/goal/旧 review/裁决/产品/测试/README，不 commit/push/PR/merge，不派发子 Agent，未调用 Goal tool 与进程列表。
- Scope：重点反证 PR-C4-F1（format owner 对角色/public 文案、hint、canonical label 的唯一事实；统一 usage producer 装箱、hint 全 code 必填/校验、`upload_failure.py` 唯一映射、tool `invalid_argument` 与 direct/可达 awaited 同源）与 PR-C4-F2（alias/public reason 测试白名单与 focused 命令）；兼审 O12/O34/UM-A09/F8–F11、三态目标动作表、公司与材料原子 guard、O16/O05 等实施依赖是否回退。
- 本机时钟戳：2026-09-29 17:59 +0800（artifact 文件名按任务指定固定，未用自动生成时间戳）。

## 预检与版本锁定（均为一手证据，检查命令自身 exit 0）

| 检查项 | 一手结果 |
| --- | --- |
| canary | 工具读取 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.V9TsYK/canary.txt`，逐字内容 `kimi-74886b45` |
| state plan SHA-256 | `1fe2f546…78b6`，与锁定一致 |
| O12 accepted checkpoint | `git cat-file -t b201d9f3` 为 `commit`，全量 `b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c`，subject `docs: accept O12 material company plan` |
| checkpoint 内 O12 plan SHA-256 | `git show b201d9f3:docs/gateflow/upload-material-o12-company-plan-20260929.md` 实测 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`，与锁定一致 |
| checkpoint 拓扑披露 | `git merge-base --is-ancestor b201d9f3 HEAD` 判 `NOT_ANCESTOR`：该 checkpoint 不在本 checkout HEAD（`8d8d494f`）历史中，属相邻分支快照；对象与 blob SHA 均已核，锁定效力不受拓扑影响，与 plan「相邻只读 checkpoint」表述一致 |
| MiMo 上轮 review | `docs/reviews/plan-review-20260929-164438.md` SHA-256 `c195066975ff055f787e5067815fbf300264ac643ade2ab3e6ab29aedd3eacd9`，与 Sol PR-C4 fix 记录一致 |
| 工作树状态 | 本 checkout HEAD `8d8d494f`；goal/plan/三份 fix/裁决/review 均为未跟踪文档，与 plan 自述一致 |
| O12 未实施证据 | `rg "MaterialUploadPublishedState|upload_usage_contract" dayu/ tests/` 无匹配（预期无匹配，按任务约定记录于此）：accepted plan 类型在本 checkout 不存在，plan 的「待实施」定性准确 |

已读文档：workspace `AGENTS.md`（与 `CLAUDE.md` 逐字节相同）、binding goal `upload-material-state-goal-20260929.md`、总控裁决 `upload-material-state-plan-review-adjudication-20260929.md` 全文（C1/C2/C3、F1–F11、O34、OQ1–OQ3、PR-C3-F1、PR-C4-F1/F2 各节）、Sol `upload-material-state-plan-prc4-fix-20260929.md`、MiMo 上轮 `plan-review-20260929-164438.md` 及 C3 后同版 `plan-review-20260929-150200.md`、O12 accepted plan（commit 内 blob）全文。

## Assumptions Tested（逐条反证结果）

1. **PR-C4-F1 的现状反例真实、plan 无虚称既有 API。** 成立。`ingestion_runtime.py:673-700` 的 `FinsUploadUsageCode` 已含 `CREATE_TARGET_EXISTS`/`UPDATE_TARGET_MISSING` 两码；`FinsUploadUsageFailure`（:708-741）仅 `code/message`，`code` 接受 `FinsUploadUsageCode | FinsUploadFormatFailureKind`；producer `fins_upload_usage_failure`（:1062-1097）只查 `_USAGE_MESSAGES`（仅普通 code）；`_raise_upload_format_usage`（:1121-1132）直接构造 fact，绕过 producer——MiMo 反例与 plan §5「现状反例」段逐句吻合。plan 明确 fact 的 `hint/public_message/file_label` 与新 producer 均为待实施，无虚称。
2. **format owner 的唯一事实成立。** `upload_format_contract.py:41-58` 三个 role-specific kind、:26-28 角色模板、:61-82 有界文案、:85-111 `FinsUploadFormatError` 自带经 `validate_fins_public_file_label` 校验的 canonical `file_label`；canonicalizer 唯一 owner 在 `direct_events.py:1080/1100`。format 的 public 通用文案「文件格式不受支持，请选择支持的文件后重试」与 retry hint「请查看上传帮助中的支持格式后重试」当前确实写在 `upload_failure.py:226-233` 的分类分支里——plan 让 format owner 接管这两个文案的生产、producer 原样装箱、mapper 原样消费，消除了真实的第二文案源，方向正确且由真实 API 支撑。
3. **`upload_failure.py` 唯一 public 构造/映射可成立。** 全 `dayu/` 15 处 `FinsUploadFailureReason(` 构造均在该文件（rg 实测）；`FinsUploadFailureCode`（:37-54）当前无 target 码、USAGE 组仅 `UNSUPPORTED_UPLOAD_FORMAT`（:163-165），新增三 target 码「全部且仅归 USAGE」是对封闭分组的合法扩展；`retry_hint`/`file_label` 已是既有字段，JSON exact-key round-trip 由 `upload_failure_reason_from_json`（:436-475）承载。无第二种构造路径需求。
4. **path-free 校验与 filing 文案冲突是真实风险，plan 处理正确。** `_validate_failure_reason_text`（:523-536）对 public reason 的 `message/retry_hint` 禁止 `/`、`\` 与控制字符；既有 `_USAGE_MESSAGES` 中 `MISSING_FILES` 含字面 `create/update`、日期文案含 `YYYY-MM-DD`。plan 把 path-free 校验限定在「映入 public reason 的 target/format `public_message`」，fact 层只做 1..240+无控制字符，避免误伤 filing 既有文案——与代码约束精确对齐。
5. **tool `invalid_argument` 与 direct/可达 awaited 同源可达。** `upload_tools.py:50,58-60,117-124` 当前无 typed 分支，`FinsUploadUsageError`（ValueError 子类，:743-760，`str(exc)` 即 fact.message）落通用 `invalid_argument`+通用 hint；plan 要求在普通 `ValueError` 前捕获 typed usage、只取 fact.message/hint、不增 Fins code/file_label 字段，与 F11 裁决及现有协议形状一致。CLI 既有 `except FinsUploadUsageError → 渲染 exc.failure.message → EXIT_USAGE_ERROR`（`dayu/cli/commands/fins.py:198-200`），Service 透传 typed（`service_runtime.py:77`）。runtime admission 先于 producer/job/observation（`ingestion_runtime.py:4714-4747`），稳定拒绝不建 job/observation，「不造任务测不可达 awaited 分支」与结构一致。
6. **`FinsUploadFailureError.failure` 直通是必要且待实施的。** 当前 `fins_upload_failure_from_exception`（:214-292）无该直通分支；SEC/CN filing workflow 先 `except FinsUploadFailureError` 用 `exc.failure`（`sec_upload_workflow.py:311-318`、`cn_pipeline.py:942-949`），而 SEC material stream 仅通用 `except Exception`（`sec_upload_workflow.py:599-603`）。O12 集成后材料 guard 抛 typed conflict 时必须经分类器直通才能在 material 路径投影为 `source_publication_conflict`，否则退化为 `unexpected_runtime`。该直通同时是 O12 accepted plan 的 O12-PR4-F1 已接受实施项（「先取 `FinsUploadFailureError.failure`」），plan §5 与之逐句一致，非本 WU 私造。
7. **PR-C4-F2 修复属实。** `tests/fins/test_company_identity_storage_contract.py:636-670` 真实断言 alias conflict→`TICKER_ALIAS_CONFLICT`、corruption→`STORAGE_IO`、精确文案、`file_label is None` 与 `upload_failure_reason_from_json(conflict.to_json()) == conflict`；plan S1/S2 测试白名单与 §验证命令的两条 focused pytest（含 `--cov` 版本）均已纳入该文件。
8. **O12 依赖成立且为 accepted-plan 锚定。** commit 内 O12 accepted plan 逐项规定：同版 `MaterialUploadPublishedState`（含 COMPLETE tombstone 完整可信 meta/revision、strict 完整性分离）、typed admission/公司决策、独立 company batch commit outcome、材料自身 batch/skip guard（expected source + post-company meta、单一 `MaterialUploadPublishedStateConflictError`、material 语境投影 `source_publication_conflict`）、alias 唯一性在 company commit 最终检查、upload job 原子 typed 终态（O12-PR4-F3）；其集成顺序节明确「静态字段/文件组合 → target 状态 → 公司缺名 → 启动/发布」，与本 plan §3 admission 顺序一致。产品未实施与本 checkout 无符号的实测一致。
9. **O34/UM-A09/F8–F11/三态表/原子 guard 无回退。** `_resolve_document_version`（`docling_upload_service.py:1745-1770`）同指纹保留旧版本、异指纹递增，与 F10 两格矩阵一致；filing tombstone create 现行即 `CREATE_TARGET_EXISTS`（`_fs_filing_upload_state_core.py:113-131` COMPLETE 含 tombstone meta），plan「保持现行」准确；material tombstone create 无 overwrite 现行经 `_upsert_source_document` 的 `FileExistsError`（`_fs_source_document_core.py`）拒绝，plan 记录为既有拒绝而非新 typed 规则，与 F1 裁决一致；filing 侧漂移→`source_publication_conflict` 已有 `_STATE_DEPENDENT_USAGE_CODES` 先例（`filing_upload_publication.py:71-78,747-750`）；`commit_prepared_upload_batch`（`docling_upload_service.py:1382-1433`）仍是唯一 publication 生命周期 owner，plan 未引入第二套编排。
10. **O16/O05 等依赖接缝真实且 plan 未猜未实施 API。** `FinsUploadMaterialFiles.from_upsert_paths/for_delete`（`upload_format_contract.py:486/506`）当前被 SEC workflow:493、CN pipeline:1109、CLI:1147 三处各自构造——「typed 静态裁决覆盖所有入口并先于目标读取」确为待 O16 集成确认的硬核对，plan 表述为定位点而非 API 承诺；`build_material_ids`/`validate_material_upload_ids`/`_normalize_optional_upload_fiscal_period`（`docling_upload_service.py:1820/1859/2027`）均在。

## Findings

无新增 material finding。对 PR-C4-F1/F2 两处修复目标，本 review 以一手代码与 O12 accepted plan 逐项反证，未能构造出推翻「计划内容候选已修」的反例；停止条件（SHA 漂移、format/usage/public 同源无法由真实 API 支持、O12 依赖不成立）均未触发。O12/O34/UM-A09/F8–F11、三态动作表、公司与材料原子 guard、O16/O05 依赖亦无新反例。

## Open Questions

- OQ-K1（低）：plan §5 要求「material 三码分别说明 create 目标材料已存在…」且「filing 既有 create/update 文案逐字保持」，而 `CREATE_TARGET_EXISTS`/`UPDATE_TARGET_MISSING` 是 filing/material 共享 code、现行 `_USAGE_MESSAGES` 每码一条文案。唯一自洽读法是 producer 按 source kind 产出文案（总控 PR-C3-F1 裁决的「kind-aware」表述支持此读法），但 plan §5 的 producer 合同段未显式写出 kind 入参。实施者若改共享文案会破 filing 逐字保持，若保留纯通用文案则不满足「说明目标材料」的字面要求；plan 自身的 owner 测试要求（filing 文案不漂移 + material 动作明确文案）足以拦截两种错误，故不升级为 finding。建议实施或下一 plan 修订时在 producer 合同处点名 kind 维度，消除措辞歧义。

## Residual Risks And Tracking

- O12 产品未实施/未集成；实际 `MaterialUploadPublishedState`、typed admission、公司独立 commit outcome、材料 guard、active-only 终态 API 可能与 accepted plan 漂移。跟踪去向：O12 implementation gate + 本 plan §停止条件（漂移即回 O12 owner/本 plan gate，plan 已钉死）。
- `FinsUploadFailureError.failure` 分类器直通是 O12-PR4-F1 的待实施项；S2 的 material conflict 投影依赖它随 O12 集成落地。跟踪去向：O12 implementation gate；本 plan S2 白名单已含 `upload_failure.py` 确需触及。
- 冻结 A04 不覆盖「已有不同内容 create」真实 CLI 证据；修复可用性在补跑前不可声称。跟踪去向：state implementation gate 的真实 CLI 矩阵（plan 已列为必交新证据）。
- material tombstone create 无 overwrite 维持现有 storage 拒绝（当前 `FileExistsError`→`storage_io` 投影）、`REPAIR_REQUIRED`/`UNSAFE` repair 授权未裁决、O13 时间幂等/O18/O33 各自 WU。跟踪去向：对应 work unit/goal。
- O12 checkpoint `b201d9f3` 非本 checkout HEAD 祖先（相邻分支快照）；锁定依赖对象/blob SHA 已核。跟踪去向：总控登记，无需动作。
- 本轮只读核验未运行 pytest/pyright；它们属未来 implementation gate，本 review 不授权实施。

## Execution Notes（合规与偏差披露）

- 全部检查命令自身 exit 0；两处预期无匹配的 `rg`（`MaterialUploadPublishedState|upload_usage_contract` 等）以 `|| true` 归一退出码，并按任务约定将「无匹配」作为 O12 产品未实施的正向证据记录于预检表，不作失败、不作结论外推断。
- 未使用 zsh `====` 链式输出、Goal tool、进程列表；未派发子 Agent；未 commit/push/PR/merge；唯一新增文件为本 artifact。
- 探索中一次 `ls docs/reviews/ | rg plan-review` 输出被截断（目录存量大），随后改用精确路径读取目标文件，未从截断输出得出任何结论。

## Final Plan Review Conclusion

`pass-with-risks`

PR-C4-F1/F2 的计划修复经一手核证成立：format owner 对角色/public 双文案、hint、canonical label 的唯一事实可由 `upload_format_contract.py` 真实承载；统一 usage producer 装箱 + hint 全 code 必填校验 + `upload_failure.py` 唯一 public 映射 + tool `invalid_argument`/direct/可达 awaited 同源，均与现行代码结构相容且未虚称既有 API；alias/public reason 合同测试已入白名单与两条 focused 命令。O12 依赖锚定 accepted plan（checkpoint `b201d9f3`/plan SHA `48e0598b…` 实核），O34/UM-A09/F8–F11 与三态/原子 guard 无回退。残余风险集中于 O12 未集成的实现漂移与 §5 producer 的 kind 维度措辞歧义（OQ-K1），均已被 plan 停止条件或测试要求覆盖。本 review 不授权实施：O12 accepted+integrated 仍是 S1/S2 的硬门槛，实施前须按 plan §停止条件实读 O12 最终 API 复核。
