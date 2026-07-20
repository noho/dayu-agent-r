# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Fresh Windows Plan Correction — AgentCodex

## Review entry

- Timestamp：`2026-07-20T09:06:28+0800`（本机系统时钟）。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4 real-Windows remediation`；不是新 WU。
- Gate：fresh Windows evidence后的 plan-only correction。
- Reviewed target：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`。
- Baseline plan：`1084` lines；SHA-256
  `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`。
- Corrected plan：`1124` lines；SHA-256
  `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2`。
- Finding status：`WIN4-RW-RF01 = ACCEPTED / PLAN-CORRECTED / IMPLEMENTATION-OPEN`。
- Review conclusion：`PASS / CODE-GENERATION-READY / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW /
  IMPLEMENTATION_NOT_AUTHORIZED`。

用户指定了本 artifact 的 exact filename，因此本次使用该路径；未创建 timestamp filename 的第二份 review。

## Scope and immutable boundary

本 gate 只允许：

1. 修正上述 plan；
2. 新增本 review artifact。

本 gate 不允许且未执行：product、test、README、design、workflow、control修改；新增 helper/schema/public contract/
oracle字段；stage、commit、push、workflow dispatch、PR或外部 comment。

未来 implementation allowlist也已收敛为唯一位置：
`tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage`
的现有 snapshot assertion block。同文件 imports/constants/helpers/fixtures/其它 nodes/oracle JSON block必须零 diff。

## Root cause and owner judgment

### Direct evidence

1. fresh R11 `29709987970` 为 `3/4 passed`；fresh R12 `29709993229` init为 `9/9 passed`、embedded R11为
   `1/2 passed`。R12 same-run canary gate为 PASS，完整 logs/artifacts `19` files零命中。
2. 两个 run的唯一共同失败都发生在真实 upload process exit `0`、company/source public facts成立之后：target test把
   Fins primary与原始 source basename强制成同一个 descriptor。
3. `DoclingUploadService` 先把原始 HTML与生成的 Docling JSON都放入 pending/stored entries，再由
   `_pick_primary_docling_file()` 选择 Docling JSON并发布为 `primary_document`。
4. `SourceSnapshotProtocol.primary_filename` 的 public contract只承诺精确命中 `files`；
   `SourceSnapshotFileDescriptor` 公开 exact `name` 与可选 `sha256`。public snapshot已经足以分别证明 primary选择与
   raw-source publication，不需要 raw meta/private path。

### Root cause

amended plan §13.2.1 错误合并了两个不同 owner的事实：

- Fins production/storage owner选择并发布哪个 descriptor为 primary；
- CLI real-Windows test证明本次原始 source bytes已经发布。

因此这是 high-severity remote release-gate test-oracle plan finding，不是 production Fins、Docling、storage或 upload defect。
正确修复边界是 target test consumer；修改 Fins contract、把 raw source改成 primary，或硬编码 Docling filename为新 expected
primary都会制造新的语义所有权错误。

## Exact plan diff

1. §0/§1：把当前 gate改为 fresh success-oracle correction，记录 accepted finding、两个 fresh run、R12 `9/9`与
   canary zero-match、R11/embedded R11唯一共同失败。
2. §13.0/§13.1.1：冻结既有 WIN4-RW-S1/S2 accepted aggregate为 immutable base；加入 RF01直接证据、Fins
   `primary_document` owner与 public snapshot contract。
3. §13.2.1：删除 primary与 source basename同一性要求；改为两个独立 public assertions：
   - `snapshot.primary_filename` 按 exact name在 descriptors中恰好命中一次；
   - exact `source_path.name` 在 descriptors中恰好命中一次，且其 public `sha256` 精确等于
     `hashlib.sha256(fixture).hexdigest()`。
4. §13.2.1同时禁止把当前 Docling filename/suffix固化为 expected primary，禁止 raw meta/private path/materialized file，
   并冻结现有 oracle字段集合。
5. §13.3/§13.4：未来 diff只允许 target test node现有 snapshot assertion block；禁止任何 product/Fins/storage、其它 test、
   README/design/workflow/control、helper/schema/oracle变更；stop condition覆盖所有越界路径。
6. §13.5：owner-test/negative matrix分别覆盖 primary零/多命中、raw basename零/多命中、public SHA为空/不匹配，以及
   “primary合法指向非原始 descriptor、raw descriptor独立合法”这一真实反例。
7. §13.6/§13.7：validation只面向 one-test correction与既有 public repository owner nodes；coverage不新增分母；加入
   exact diff、旧错误措辞、hardcoded Docling primary、raw meta/private path、helper/schema/oracle字段扫描；README冻结零 diff。
8. §13.8/§13.9：fresh R11/R12 closure必须同时证明两个独立 descriptor事实；任一失败进入 diagnostic-first stop；completion
   wording明确 one-test scope、零 Fins contract变化、零 README/oracle/helper/schema变化。

## Assumptions tested

| Assumption | Direct check | Result |
| --- | --- | --- |
| raw source必须是primary才能证明上传成功 | public descriptor已公开 exact name/hash，且真实snapshot含raw HTML与Docling JSON | REJECTED |
| 应把 `_docling.json` 设为新expected primary | 当前选择只是Fins owner事实，public contract没有冻结具体filename | REJECTED |
| 需要读取raw meta/private tree验证raw source | `SourceSnapshotFileDescriptor.name/sha256`已提供充分public evidence | REJECTED |
| 需要修改Fins production/storage contract | 当前production exit 0且public facts合法，缺陷只在test oracle | REJECTED |
| 需要helper/schema/oracle字段承载新事实 | target node已有fixture bytes、hashlib、source path与descriptors | REJECTED |
| one-test correction足够 | 两个run唯一共同失败同源于同一assertion，且其它positive facts/canary已通过 | ACCEPTED |

## Adversarial review lenses

- Architecture boundary：primary仍由 Fins产生/持久化/投影；CLI test只消费 public snapshot，没有反向依赖或 private-path读取。
- Best practice：raw publication使用 exact public name/hash，避免 display、物理 tree、偶然 filename选择或 meta实现细节。
- Optimal solution：删除错误等式并增加一个现有字段断言即可；无需 product fix、contract扩张或 test seam。
- Overengineering：明确禁止 helper、wrapper、schema、oracle字段、README与 workflow扩张。
- Overcoupling：primary membership与 raw-source publication分别断言；未来 Fins更换合法 primary时不会迫使 CLI test同步改名。

没有发现新的 material plan finding。`WIN4-RW-RF01` 已在 plan层关闭错误规格，但在 one-test implementation、双路 review、
fresh remote rerun与 clean aggregate closure完成前，finding仍是 implementation-open，AR-F07仍是 release blocker。

## Old-wording and forbidden-path scans

- 旧错误 requirement scan：零命中。扫描覆盖 primary filename与 source basename同一性措辞及对应 equality expression。
- hardcoded Docling expected-primary要求：零命中；plan只把当前 Docling选择记录为 owner evidence，并明确禁止固化。
- `AMENDED_PLAN_BASE`、旧 `exact 2 slices`未来授权措辞：零命中；当前统一使用 `CORRECTED_PLAN_BASE`和唯一 RF01 slice。
- future allowlist：只有 target test node；README/product/Fins/storage/workflow/control均明确零 diff。

## Immutable product/test/workflow/control state

以下 SHA-256在 plan修改前后保持不变：

| Path | SHA-256 |
| --- | --- |
| `docs/host/issues-implementation-control.md` | `e3aa6699f83096682bac9e6134e2788318a678fced4aec53c4477123daab2023` |
| Controller fresh-evidence artifact | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` |
| `docs/fins/design.md` | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| `dayu/fins/pipelines/docling_upload_service.py` | `aad45665a3a41c39dd228bf323a6ed4bac8ca97488b6917448ba37d2ec656580` |
| `dayu/fins/storage/repository_protocols.py` | `428c7a27faed9abf46a79343f0aeb2cd891c86408ba679a12ab998e11cc83b35` |
| `tests/cli/test_upload_filings_from_command.py` | `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` |
| `.github/workflows/r11-upload-script-windows.yml` | `4c915a9c79efa5ee0166eb6fae44513ecc077b974217ca1e855e8b7ec4507f43` |
| `.github/workflows/r12-init-windows.yml` | `ba99b5a40c6d3116e1d83b05cd97139dcc62699722269b0aa6fc1a8d5ebea7b8` |

Controller control diff的 binary diff SHA-256在本 gate前后保持
`bb3ead9c2aea745688530ead769b4d984298e93c4fdb447763b1211d09797234`；没有覆盖或格式化 Controller文件。
staged tree为空。

## Validation

- Corrected plan source scan：`PASS / zero old-error matches`。
- Scope/immutable hash comparison：`PASS`。
- `git diff --check`：`PASS`。
- Full pyright：`PASS / 0 errors, 0 warnings, 0 informations`。
- Tests：未运行；本 gate没有 product/test代码变化，真实 Windows closure必须等待后续授权的 one-test implementation与fresh rerun。
