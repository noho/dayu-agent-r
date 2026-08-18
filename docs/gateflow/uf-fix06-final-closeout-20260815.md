# UF-FIX06 final closeout

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`final closeout` 独立只读验证
- 日期：2026-08-15
- 分支：`codex/upload-filing-oracle`
- 接受计划 checkpoint：`267e90b121597c1d71247273d9450b90ffbe1c26`
- 验证提交范围：`267e90b1..060f133b`
- 验证终点 / 当前 `HEAD`：`060f133b7309b8e3257c8434b16ebc1263c8b7b4`
- Artifact：`docs/gateflow/uf-fix06-final-closeout-20260815.md`
- 最终结论：**FINAL CLOSEOUT PASS**
- 下一入口：UF-FIX06 work unit completed；后续仅按用户需要进入集成或其它 work unit

## 结论与第一性原理判断

本次指定的本地验收全部通过：14 文件受影响 pytest 矩阵、全量 pyright、提交范围与工作树
`git diff --check`、protected diff、五个 UF-FIX06 implementation/deepreview commits、双路
aggregate deepreview/fix/re-review、README 决策均可由直接证据闭环。代码与文档的本地接受状态成立。

用户已明确本次 final closeout 以本地提交范围验收为完成合同，并明确无需创建 PR。当前分支没有
upstream、没有 PR，仅作为外部状态记录，不构成本次 closeout blocker。按用户约束，本轮不 push、
不创建或修改 PR、不评论 issue、不 commit。

## 独立验证结果

所有 Python 命令均先执行 `source .venv/bin/activate`。环境为 Python `3.11.15`、pytest `9.0.3`、
pyright `1.1.409`。

### 1. 14 文件受影响 pytest 矩阵

文件清单来自 accepted plan 的验证章节，也是
`docs/gateflow/uf-fix06-slice4-acceptance-20260815.md` 所称“原 14 文件 focused matrix”的真源：

```bash
python -m pytest \
  tests/documents/test_docling_runtime.py \
  tests/fins/test_upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_upload_batch.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_upload_failure.py \
  tests/fins/test_docling_process_converter.py -q
```

- 结果：`1237 passed, 1 skipped, 3 warnings in 23.80s`
- 退出码：`0`
- Slice 4 acceptance 记录为 `1235 passed`；当前范围终点多出的两个通过项来自随后 aggregate
  deepreview fix 新增的 owner/CLI 直接回归：companion-only 文案机械投影与 material CLI help 同源消费。
- 唯一 skip 是需显式启用的真实 Docling upload integration；本轮未设置真实 integration 开关。
- 三条 warning 均来自已安装 `edgar` 包的 deprecated import，不是 UF-FIX06 新增 warning。

### 2. 全量 pyright

```bash
python -m pyright dayu/ tests/ utils/
```

- 结果：`0 errors, 0 warnings, 0 informations`
- 退出码：`0`
- 额外输出仅提示 pyright `1.1.409 -> 1.1.411` 可升级，不影响检查结论。

### 3. diff check 与工作树

- `git diff --check 267e90b1..060f133b`：PASS，零输出。
- 写入本 artifact 前的 `git diff --check`：PASS，零输出。
- 写入本 artifact 前的 `git status --short`：零输出，工作树干净。
- `git status --branch --short` 当时仅输出 `## codex/upload-filing-oracle`，没有 staged、modified
  或 untracked 项。
- 本轮预期且唯一的工作树变更是新增本 final closeout artifact；没有修改生产代码、测试、README、
  registry、oracle、scenario 或 evidence。

### 4. Protected diff

命令：

```bash
git diff --quiet 267e90b1..060f133b -- \
  docs/cli_ci_oracles.json \
  docs/cli_ci_scenarios.json \
  docs/host/design.md \
  docs/engine/design.md
```

结果为退出码 `0`，`git diff --name-status` 零输出：

| Protected file | 范围内状态 |
|---|---|
| `docs/cli_ci_oracles.json` | 无 diff |
| `docs/cli_ci_scenarios.json` | 无 diff |
| `docs/host/design.md` | 无 diff |
| `docs/engine/design.md` | 无 diff |

本轮没有运行 UF-PF06、UF-PF12 或真实 CLI evidence，也没有读取、刷新或替换冻结 evidence bundle。

## UF-FIX06 commit 核对

`267e90b1` 是 `gateflow: accept UF-FIX06 implementation plan` checkpoint，本次实现验证范围从其后开始。
`git merge-base --is-ancestor 267e90b1 060f133b` 返回 `0`；范围内恰有五个提交，父提交逐个首尾相接，
无 merge 或旁支插入，且终点等于当前 `HEAD`。

| 顺序 | Commit | Subject | Gate / scope 对账 |
|---:|---|---|---|
| 1 | `c1db7b495823f51b6fb01ad70c85044841cb80f0` | `feat(documents): centralize Docling capability contract` | Slice 1；Documents converter capability owner、直接测试、双路 review/re-review 与 acceptance artifacts |
| 2 | `affa665b0592aec54564d31b0cfeb4055dd7bd8a` | `feat(fins): define upload file role contract` | Slice 2；Fins typed filing/material role owner、CLI/batch/tool consumers、直接测试与完整 gate artifacts |
| 3 | `8033a56eb0f44ae5664c510b84ebe448050888eb` | `feat(fins): enforce typed upload workflow roles` | Slice 3；Service/workflow typed selection、failure projection、原子/取消回归、双路 review/re-review 与 acceptance artifacts |
| 4 | `f61ddb9582f542751e52a0b31ff59e2c52f8a7c9` | `docs(fins): document upload format ownership` | Slice 4；三个 README、LLM-facing owner 文案直接测试、双路 review/re-review 与 acceptance artifacts |
| 5 | `060f133b7309b8e3257c8434b16ebc1263c8b7b4` | `fix(fins): unify upload format text projections` | Aggregate deepreview accepted DS-F1/DS-F2 修复、双路 re-review、adjudication 与 aggregate acceptance artifacts |

范围文件与上述 slice owner 边界一致；protected files 未进入任何 checkpoint。

## Aggregate deepreview / re-review 核对

两路初审都给出 `PASS`，但不是“零 finding PASS”：

- AgentMiMo：`docs/reviews/deepreview-uf-fix06-mimo-20260815.md`，`PASS`，提出 MiMo-F1/F2/F3。
- AgentDS：`docs/reviews/deepreview-uf-fix06-ds-20260815.md`，`PASS`，无 blocking finding，但提出
  两项低严重度 owner 文案 finding。
- Controller：`docs/reviews/uf-fix06-deepreview-adjudication-20260815.md`，准确裁决为
  `CODE FIX REQUIRED`；接受 DS-F1/DS-F2，MiMo-F1 deferred/non-blocking，MiMo-F2/F3
  rejected-with-reason。
- Fix：`docs/gateflow/uf-fix06-deepreview-code-fix-20260815.md` 在文本 owner 与 CLI 直接消费边界
  修复 DS-F1/DS-F2，没有扩大 runtime admission、storage 或 README scope。
- AgentMiMo re-review：`docs/reviews/deepreview-re-review-uf-fix06-mimo-20260815.md`，`PASS`。
- AgentDS re-review：`docs/reviews/deepreview-re-review-uf-fix06-ds-20260815.md`，`PASS`；后续
  docstring 精度观察已消除，PASS 不变。
- Aggregate acceptance：`docs/reviews/uf-fix06-deepreview-acceptance-20260815.md`，`PASS`。

最终 finding 状态：

| Finding | 最终状态 | 分类 / owner |
|---|---|---|
| DS-F1：companion-only 文案硬编码 `.xsd` | 已修复，双路复审 PASS | 当前 aggregate fix |
| DS-F2：material CLI help 未消费同一 contract | 已修复，双路复审 PASS | 当前 aggregate fix |
| MiMo-F1：usage-code 联合类型演进 | deferred / non-blocking | assigned to later failure-contract work unit |
| MiMo-F2：batch 不发现 companion-only 文件 | rejected-with-reason | 属 UF-FIX07/后续 association 语义，不是本 work unit finding |
| MiMo-F3：CLI/runtime 双重校验 | rejected-with-reason | 两层消费同一 owner，入口反馈与 runtime correctness 职责不同 |
| DS follow-up docstring 精度观察 | 已消除 | `060f133b` 中准确描述 filing/material help 与 tool schema 消费者 |

没有未裁决 finding，没有未分类代码 residual risk；aggregate deepreview gate 本身已经通过。

## README 决策核对

实际范围只修改 `README.md`、`dayu/fins/README.md`、`tests/README.md`，没有修改 `dayu/README.md`：

- 根 README 面向最终用户。UF-FIX06 改变 `upload_filing --files` 的用户可见 primary/companion、
  candidate、转换失败与零部分发布说明，命中根 README 触发；新增文本位于上传工作流章节，不暴露
  gate 过程或内部类型，职责匹配。
- `dayu/fins/README.md` 面向 Fins 开发者。Fins capability/role owner、typed data flow 与
  material company-meta/source/blob publication 边界发生变化，命中该 README；文本描述当前实现，
  不记录未来计划或测试流水账。
- `tests/README.md` 的职责是当前测试分层、运行方式与维护约定。范围新增 owner-level regression
  文件与 focused 命令，更新测试手册成立。
- `dayu/README.md` 未改：`UI -> Service -> Host -> Engine` 分层、装配方式及公共 runtime 边界均未变化。
- Host/Engine design 未改：本 work unit 不改变 Host/Engine contract 或状态机，protected diff 也证明
  没有越界。
- Aggregate fix 不再修改 README：它只让既有 owner 文案和 material CLI help 机械消费同一投影，
  Slice 4 已记录的用户/开发者语义仍准确。

README 决策为 **PASS**。

## Docs、PR 与 issue 状态

- Docs updates：UF-FIX06 已按职责更新三个 README；本轮只新增本 final closeout artifact。
- Draft PR URL：N/A；用户明确本次无需创建 PR。当前分支无 PR、无 upstream，仅作状态记录。
- PR review status：N/A；不属于用户确认的本地 closeout contract。
- Accepted PR-review checkpoint 与 review 后 final push：N/A；本轮不 push、不创建 PR。
- Issue link/comment：范围材料没有声明 GitHub issue 编号，因此本轮无法也未执行 issue 关联或 comment；
  本次也没有 issue 外部写入要求。

## Residual risks 与未覆盖项

| Residual / uncovered area | 分类 | Owner / destination |
|---|---|---|
| 真实全格式 fixture matrix 未运行 | assigned to later work unit | UF-PF06 |
| mandatory CLI scenario / 真实 CLI evidence 未运行 | assigned to later work unit | UF-PF12 |
| 默认矩阵中的真实 Docling integration 仍 skip | assigned to later work unit | UF-PF06；本轮按约束不设置真实 integration 开关 |
| batch 不自动将同目录 `.xsd` 与 primary 关联 | assigned to later work unit | 后续 batch association / UF-FIX07 类 work unit |
| 显式 primary、重复路径、basename/stem collision | assigned to later work unit | UF-FIX07 |
| usage-code 联合类型、delete 携带 files、material 空 upsert 的 failure 分类精化 | assigned to later work unit | 后续 usage/failure-contract work unit |
| 本次 closeout 未重新采集逐文件 coverage | uncovered validation area，非代码 finding | Slice 4 accepted evidence 为 11 个目标生产文件均 `>=80%`、aggregate `92%`；本轮用户指定矩阵未要求 coverage |
没有未分类 residual risk。上述产品与真实 evidence 缺口均已分配给后续 work unit，未被误写为
UF-FIX06 已完成能力。无 PR、无 upstream 是用户明确接受的当前外部状态，不属于 residual risk。

## Completion status

**FINAL CLOSEOUT PASS**。

本地 implementation、slice review/re-review、aggregate deepreview/fix/re-review、deterministic pytest、
全量 pyright、README、protected-scope 与干净工作树验证均 PASS；五个范围提交线性完整，双路
aggregate deepreview accepted findings 已修复并双路 re-review PASS，没有 blocking finding 或未分类
residual risk。按用户确认的本地 closeout contract，UF-FIX06 work unit completed。当前无 PR、无 upstream，
用户明确无需创建 PR，因此不影响本次 PASS；后续仅按用户需要进入集成或其它 work unit。
