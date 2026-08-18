# UF-FIX07 Slice 2 Implementation

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Slice：`Slice 2：CLI 与 LLM-facing primary 投影`
- Gate：`review fix`
- 日期：2026-08-15
- Prerequisite accepted commit：`9d0a2f8ab2068acc667752cb277e74bbe0a536c1`
- Artifact path：`docs/gateflow/uf-fix07-slice2-implementation-20260815.md`
- Completion status：`REVIEW FIX COMPLETE / RE-REVIEW PENDING`
- Blocking open question：无
- Next entry point：`re-review`

## Scope 与 changed files

实际修改仅限于 Slice 2 获准的生产、测试与 artifact 文件：

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/fins.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/upload_format_contract.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_upload_format_contract.py`
- `docs/gateflow/uf-fix07-slice2-implementation-20260815.md`
- `docs/gateflow/uf-fix07-slice2-review-fix-20260815.md`

未新建误派路径 `tests/fins/test_ingestion_tools.py`；未修改 Slice 1 owner、Service、Host、Engine、
runtime、storage、processor、Docling、renderer、README、registry、oracle 或 frozen evidence。

## 第一性原理与 owner 裁决

问题成立：如果 CLI 使用 last-wins 收集重复 selector，Fins owner 将无法看到真实 cardinality；如果
CLI/tool 自行判定 membership、单/多文件或角色格式，会与 Slice 1 static admission owner 形成双真源。

本 slice 保持以下唯一所有权：

- CLI 只收集全部 `--primary` occurrence，并与 `--files` 一样执行机械 path resolve。
- tool adapter 只把 optional string `primary` 投影为 0/1 raw selector；material 携带 primary 在请求
  union discrimination boundary fail closed。
- membership、selector cardinality、单/多文件要求、delete 组合与 primary/companion 格式继续只由
  `dayu.fins.ingestion_runtime` 的 static validator 产生与拒绝；CLI/tool 没有新增第二套业务校验。
- CLI/LLM-facing 文案继续由 `project_fins_upload_format_text()` 拥有；两个 primary 投影由同一个
  模块级规则 helper 生成，入口只机械消费。

## 实现与数据流

1. `upload_filing` 新增单值、`action="append"` 的 `--primary PATH`；`ParsedCliArgs.primary` 保留空状态或
   每次 occurrence。`upload_material` 与 `upload_filings_from` 不注册该参数。
2. CLI prevalidation 把全部 occurrence 投影到 `FinsUploadFilingRequest.primary_selectors`，重复、缺失、
   非 membership 和 duplicate files 都由 Fins owner 在 Service factory/workspace mutation 前返回 typed usage failure。
3. `FinsUploadFormatTextProjection` 新增 `filing_primary`、`upload_tool_primary` 与
   `upload_tool_material_primary_failure`；同源文案自足说明单文件
   可省略、多文件恰好一个、membership、顺序不决定角色、delete 禁止 files/primary；tool 文案
   另明确 material 不使用 primary，且不允许根据质量、重要性或转换结果推断角色。schema description
   与 material-primary failure 机械复用同一 typed 字段，adapter 不再硬编码第二份业务文本。
4. `start_fins_upload` 只新增 optional string `primary`；`files` 原生 schema 新增 `maxItems: 100`，
   未加入顶层 `required`，未修改 `ToolParametersSchema` 或 Host/Engine contract。
5. tool filing 路径的 primary 省略/提供分别生成空 tuple/单元素 resolved `Path` tuple；valid multi-file
   非首位 primary 可登记 observation，invalid selector 在 state read、observation registration/activation 与 job submit 前失败。

## Tests 与 validation

### Affected tests

```bash
source .venv/bin/activate
python -m pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py tests/fins/test_upload_format_contract.py -q
```

- Exit code：0
- Result：`721 passed, 3 warnings in 16.40s`
- 三条 warning 均为现有 `edgar` 依赖的 deprecation warning，与本 slice 无关。
- 首轮的 3 个 failure 均来自同一个旧 CLI renderer 测试夹具：它构造两文件 filing 却未显式声明
  primary。已按 Slice 1 owner contract 修正 fixture，未在生产代码加入兼容分支。

关键断言覆盖：CLI occurrence 全保留、非首位 primary 的 raw/validated 投影、四类 zero-side-effect CLI
usage failure、其它两个 upload 命令不接受 primary、两个文本字段 exact projection、tool optional string schema、
`files.maxItems=100`、0/1 selector、valid observation 登记、invalid selector/material/delete 的 fail-closed 边界，以及
material-primary `ToolFailedOutcome` 的 owner 同源中文 message、包含 primary 的精确 hint 与 workspace/state/job
零副作用。

### Targeted pyright

```bash
source .venv/bin/activate
python -m pyright dayu/cli/arg_parsing.py dayu/cli/commands/fins.py \
  dayu/fins/tools/upload_tools.py dayu/fins/upload_format_contract.py \
  tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py tests/fins/test_upload_format_contract.py
```

- Exit code：0
- Result：`0 errors, 0 warnings, 0 informations`
- pyright 另提示有新版本可用，不是类型检查失败。

### 单生产文件 coverage

使用同一组 affected tests 执行 `coverage run --branch`，然后对每个修改生产文件独立
`coverage report --include=... --fail-under=80`：

| 文件 | Branch coverage | 结果 |
| --- | ---: | --- |
| `dayu/cli/arg_parsing.py` | 99% | pass |
| `dayu/cli/commands/fins.py` | 81% | pass |
| `dayu/fins/tools/upload_tools.py` | 92% | pass |
| `dayu/fins/upload_format_contract.py` | 89% | pass |

### Diff / scope

- `git diff --check`：exit 0，无输出。
- 产品文本不再包含“首文件是主文件”。
- `ToolParametersSchema` 的现有声明期、runtime 校验和 Host JSON 投影已直接支持 `maxItems`，
  未触发 stop condition。

## Docs decision

本 slice 不修改 README。用户可见 CLI/schema 文档同步已由 accepted plan 明确归属后续 Slice 4；本轮不预写
尚未完成的 Slice 3 asset/storage 行为。

## Findings 与 residual risks

- MiMo review `docs/reviews/code-review-20260815-200314.md`：pass，无 finding。
- DS review `docs/reviews/code-review-20260815-201037.md` Finding 1：`accepted`，当前 fix 状态为`已修复`；
  material-primary failure 已改为 projection owner 中文文本，ValueError hint 已包含 primary，并有 exact outcome 与零副作用测试。
- Implementation 内发现的旧多文件 test fixture：`fixed in current slice`；已改为显式 selector 并通过回归。
- 既有 delete+files adapter 英文消息：`assigned to later work unit`；该路径在 Slice 2 前已存在，本轮按主控边界
  不处理，后续由 LLM-facing 文案收敛 work unit / registry-evidence owner 裁决。
- schema `files.maxItems=100` 与 ingestion limit 分属两个边界：`assigned to later work unit`；当前形态是
  accepted plan 明确边界，本 review fix 不改 owner design。
- filing deterministic asset identity、derived association、storage primary 与 process consumption：
  `covered by later approved slice`，owner/destination 为 Slice 3。
- README 同步与全量 closeout validation：`covered by later approved slice`，owner/destination 为 Slice 4。
- existing-source 旧 schema、concurrency、company warning、registry/evidence 更新和真实 scenario run：
  `assigned to later work unit`，owner/destination 沿用 accepted plan §12 的 UF-FIX08/10/11 与后续 registry/evidence gate。
- 未分类 residual risk：无。

## 禁止边界确认

- 未修改 `ingestion_runtime`、Docling、storage、README、registry、oracle 或 frozen evidence。
- 未执行 UF-PF07、UF-PF12 或其它真实 evidence scenario。
- 未 commit、push、创建/推进 PR 或对外 comment。
- 两份 review artifact 仅作为输入读取，未修改；本 fix 未执行 re-review。

## Gate decision

Slice 2 accepted review Finding 1 已修复，affected tests、targeted pyright、单文件 coverage 与 diff check 已通过。
没有 blocking open question 或未分类 residual risk。Completion status 为
`REVIEW FIX COMPLETE / RE-REVIEW PENDING`；按用户明确指令停在 Gate Order 的下一个未完成入口：`re-review`。
