# Code Review

- Reviewer：Kimi 独立 re-review（UM-O11 S1，O11-CR-F1 根 README 修复复核）
- RUNTIME/PROVIDER/MODEL: claude/kimi/kimi-k3[1m]
- CANARY=kimi-e738ab52
- Review 时间：2026-09-29
- 独立性声明：本 review 只依据当前工作树 diff、owner 代码走读与本 reviewer 自行运行的验证；不以 `docs/reviews/code-review-20260929-032747.md`、`docs/reviews/code-review-20260929-092732-o11-kimi.md`、`docs/reviews/code-review-20260929-094352-o11-mimo.md` 或任何既有评审结论作为证据。MiMo 原 finding 仅作为待复核的缺陷声明输入，其真实性由本 reviewer 独立重证。

## Scope

- Mode: O11-CR-F1 修复复核（根 `README.md` 日期段），目标文件 SHA-256 预检 `c1cd17458804aa6415beccb03320dd0b2d922df89de596019f81534208775dc3`，与任务给定值逐字一致。
- Branch: `codex/upload-material-o11`；Base: HEAD `9141b5e9c65caaf52416f177a2641f8a7e1134ad`。
- Output file: `docs/reviews/code-review-o11-readme-rereview-kimi-20260929.md`
- 边界文档：`AGENTS.md`、根 `README.md` 的 `Agent更新约束【必须遵守】`（`README.md:9-16`）、accepted plan `docs/gateflow/upload-material-o11-dates-plan-20260929.md`、裁决 `docs/gateflow/upload-material-o11-s1-code-review-adjudication-20260929.md`、修复记录 `docs/gateflow/upload-material-o11-s1-readme-fix-20260929.md`。
- Included scope：根 `README.md` diff（唯一修复对象）；owner 只读走读 `dayu/cli/commands/fins.py`、`dayu/cli/arg_parsing.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/domain/filing_semantics.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`；越界核对覆盖全部 8 个 modified 文件与 untracked artifact。
- Excluded scope：产品/测试代码本身的正确性（已由 S1 双路 review 覆盖，本轮 diff SHA 核对仅验证无 drift）；`upload_filings_from`（plan R1）；O05/O16 集成（plan R3）；UM-O12 相邻问题。
- Parallel review coverage: 无（任务禁止派发子 Agent）。

## 修复要求与复核结论对照

O11-CR-F1（低）要求根 README 日期段：① 恢复 `upload_filing` 空串/纯空白日期的拒绝承诺；② 写清 `upload_material` 两日期参数的空值折叠现状；③ 不把 `--report-date ""` 等其它折叠升级为新产品承诺；④ 仅限根 README 该段。

复核：四项要求全部落实，且逐格与 owner 代码一致（证据见下）。无新 finding。

## Findings

无（零 correctness / stability / maintainability finding）。

###  informational 观察（非 finding，不要求修复）

- **O11-RR-I1（信息）**：修复记录第 30 行「六个产品/测试候选文件的 `git diff` SHA-256 均为 `3c5261...`」中「均为」措辞易被读成逐文件 SHA 相同；本 reviewer 实测该值是六文件**合并** `git diff` 的 SHA-256（逐文件并不相同），合并口径实测匹配、越界核对结论不受影响。仅登记措辞口径，不影响 gate。

## 独立证据（本 reviewer 实际执行/走读）

### 空值真值表（owner 函数级逐格实测）

直接调用 owner 函数（`source .venv/bin/activate` 后 Python 进程内调用，不写任何文件）：

| 入口 | 字段 | 省略/`null` | `""` | 纯空白 | 合法非空 | 带首尾空白非空 | 非法/非补零 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CLI `upload_filing` | 两日期 | `None`→跳过校验 | 原文直传→拒绝 | 原文直传→拒绝 | 接受 | 拒绝 | 拒绝 |
| CLI `upload_material` | 两日期 | `None`→跳过 | 折叠 `None`→接受（落 `null`） | 折叠 `None`→接受 | 原文接受 | 原文→拒绝 | 原文→拒绝 |
| tool filing/material | 两日期 | `None`→跳过 | 原文→拒绝 | 原文→拒绝 | 接受 | 拒绝 | 拒绝 |

直接证据：

- CLI filing 原文直传：`dayu/cli/commands/fins.py:695-696`（`filing_date=args.filing_date` 无 helper 介入）；日期参数无归一化：`dayu/cli/arg_parsing.py:1148-1149`。
- CLI material 折叠：`dayu/cli/commands/fins.py:736-737` 经 `_optional_material_date_text`（`fins.py:1279-1289`）；实测 `_optional_material_date_text("")/" "/"  "` → `None`，`" 2024-02-29 "` 原文返回（不 trim）。
- Fins admission：`_validate_optional_upload_iso_date`（`dayu/fins/ingestion_runtime.py:1372-1394`）仅 `None` 跳过；filing 静态准入调用点 `ingestion_runtime.py:1288-1289`，material 共享准入调用点 `ingestion_runtime.py:7713-7716`（`_normalize_upload_request` material 分支）。实测：`""`/`" "`/`" 2024-02-29 "`/`2025-02-30`/`2024-2-9`/`2024-02-30` 均 REJECT（字段 typed code），`2024-02-29`/`0001-01-01` ACCEPT，`0000-01-01` REJECT（年份下界 0001 与 README「`0001..9999`」一致）。
- 日期规则 owner：`parse_iso_calendar_date`（`dayu/fins/domain/filing_semantics.py:375-404`），ASCII fullmatch `[0-9]{4}-[0-9]{2}-[0-9]{2}`（`:57-60`）+ `datetime.date` 存在性 + isoformat 回写一致性。
- tool 原文保留：`_optional_raw_nullable_text`（`dayu/fins/tools/upload_tools.py:396-418`）实测缺失/`null` → `None`，`""`/`" "` 原文返回 → 进入 admission 拒绝；filing 与 material 两 kind 均用此 helper（`upload_tools.py:345-346, 362-363`）。
- 「保存时为 `null`」投影同源：`sec_upload_workflow.py:514-515, 555-556` 与 `cn_pipeline.py:833, 861, 1130, 1171` 以同一 raw request 值流入 `UPLOAD_STARTED` payload 与 `prepare_upload(meta=...)`；折叠后 `None` 即 JSON `null`。

### 真实 CLI 端到端（本 reviewer fresh 运行，`$TMPDIR` 隔离 base，非冻结证据）

- `upload_filing --filing-date ""` → exit `2`，stderr `dayu-cli upload_filing: 披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期`。
- `upload_filing --filing-date " "`（纯空白）→ exit `2`，同上 stderr。
- `upload_filing --filing-date " 2024-02-29 "`（带首尾空白非空）→ exit `2`，同上 stderr。

以上与修复后 README「CLI 的 `upload_filing` 两个日期参数若传入空串或纯空白，也会作为用法错误拒绝」逐字对应。

### 措辞审查（偷增承诺 / 误导性）

- 修复后段落（`README.md:386-395`）将格式承诺限定于「若提供非空日期」，空值行为按入口分述：filing CLI 拒绝、tool 拒绝、material CLI 折叠。truth table 无缺格。
- `--filing-date ""` 「保持既有支持……保存时为 `null`」是 accepted plan 第 13 行唯一接受的 CLI 例外（source meta 与 manifest 投影 `null`），README 措辞为其子集，未扩张。
- `--report-date` 与纯空白输入仅以「当前会将……视为未提供」陈述现状并引导「直接不传对应参数」，未写成稳定承诺——符合 plan R2 边界。
- 「`upload_filings_from`……不属于该直接上传日期承诺」保留 plan R1 边界。
- 无 Host/Engine/Runtime/Fins 内部术语、无未来计划、无 gate/owner 治理词，符合根 README `Agent更新约束`（`README.md:14-15`）。
- 第一段「作为用法错误在上传任务启动前拒绝」合并叙述 CLI 与 tool 入口，tool 实际投影 `invalid_argument` 失败 outcome 而非退出码 `2`；该合并叙事为旧文本既有风格（旧文本同样以「这两个入口」合并），README 未对 tool 承诺具体退出码，不构成新误导，不登记为 finding。

### 越界与完整性核对

- `git diff --check`：exit `0`。
- 根 `README.md` diff：仅日期段 `10 insertions(+), 5 deletions(-)`，无其它段落变化。
- 六个产品/测试候选文件合并 `git diff` SHA-256 实测 `3c5261daba2736581fc61848749462862c40baf8cdbbc504506e608d53284ee9`，与修复记录声称值一致——本轮修复未顺手改动产品/测试代码。
- `dayu/fins/README.md` diff（`1 insertion, 1 deletion`）为共享 admission 日期校验描述，属 S1 implementation 候选内容，非本轮引入，不越界。
- 8 个 modified 文件与 accepted plan 白名单（生产 3 + 测试 3 + 文档 2）逐项一致；untracked 修复/裁决 artifact 无行尾空白。
- 修复期间无内容 drift：目标 SHA 预检与复核结束时一致；关键 owner（`parse_iso_calendar_date`、`_validate_optional_upload_iso_date`、`_normalize_upload_request`、CLI/tool 投影）均可读，未触发停止条件。

### 测试

- `python -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/cli/test_fins_commands.py -q -p no:cacheprovider` → **714 passed**（3 条 edgartools deprecation warning，31.48s）。
- 本轮为纯文档修复复核，未重跑 pyright（无 Python 文件变化；六个产品/测试文件 diff SHA 与已验证状态一致）。

## Residual Risk

1. CLI 纯空白（如 `--filing-date " "`）折叠为 `None` 无专门 CLI 测试断言（现有测试覆盖 `""` 与非空保真）；tool 显式 `null` → `None` 仅间接覆盖。属 MiMo 已登记残余，非本轮 README 修复范围，行为侧已由本 reviewer owner 级实测覆盖。
2. `--report-date ""`/纯空白折叠是否升级为稳定产品承诺仍属 plan R2 独立裁决事项；README 当前措辞（陈述现状 + 引导省略）在该裁决前后均成立，无文档侧阻塞。
3. R1（`upload_filings_from` 元数据）、R3（O05/O16 集成优先级）、UM-O12 相邻问题均不在本 diff，维持既有登记。
4. 本 review 为单路独立证据，不替代总控双路裁决。

## 结论

**pass**。O11-CR-F1 修复正确落实：根 README 日期空值 truth table 已补齐且逐格与 owner 代码、真实 CLI 端到端行为一致；`--filing-date ""` 例外表述未超出 accepted plan；未偷增 `--report-date` 或纯空白折叠的新承诺；无越界改动、无 drift、无新 finding。唯一登记项为 informational 的修复记录措辞口径（O11-RR-I1），不影响 gate 判定。
