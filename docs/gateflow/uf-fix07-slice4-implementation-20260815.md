# UF-FIX07 Slice 4 Implementation Artifact

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`implementation`
- Slice：`Slice 4 — README、全量验证与 gate closeout evidence`
- 日期：2026-08-15
- 基线：`892be915`
- Decision：`IMPLEMENTATION PASS / CODE REVIEW PENDING`
- Blocking open question：无
- 下一入口：`code review`
- Artifact path：`docs/gateflow/uf-fix07-slice4-implementation-20260815.md`

## Scope 与 changed files

实际修改严格位于 Slice 4 allowed files：

- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/gateflow/uf-fix07-slice4-implementation-20260815.md`

本 slice 未修改生产代码、测试代码、accepted plan、goal、registry、oracle、scenario 或 frozen evidence。

## Docs decision 与已同步事实

1. 根 README 只同步最终用户可见的当前行为：
   - `upload_filing` 示例与 help 入口包含 `--primary`；单文件可省略，多文件必须恰好指定一次且 selector 必须属于 files。
   - 重复规范路径、多个 selector、集合外 selector、超过 100 个文件以及 delete 携带 files/primary 都是上传任务启动前的 usage failure。
   - companions 只原样保存，只有 authoritative primary 进入 Docling 与后续处理；相同 basename/stem 输入不再互相覆盖。
   - 任一读取、primary 转换或 publication 失败保持整批原子失败与 `stored files=0`。
   - 未暴露内部 asset digest 或 storage schema。
2. Fins README 按 owner boundary 同步：
   - raw request 保留 selector cardinality，统一 static validator 在 workspace read 前产生 explicit validated selection。
   - `FinsUploadFilingFiles` 持有 authoritative primary 与保序 companions，不从 index、basename 或 stem 推断角色。
   - filing asset identity 与 `original_filename` 分责，derived identity、`derived_from`、storage `primary_document` 与 snapshot primary 同源。
   - `process_filing` 与 read runtime 只消费 snapshot `get_primary_source()` 返回的 exact primary derived path。
   - filing fingerprint 排除 path-derived identity；同 basename/同内容移动目录保持 identical-skip，basename 改名或内容改变触发 update。
   - material 的 name、derived name、fingerprint、metadata、事件与 failure 行为保持不变。
   - 已删除所有“首项决定 filing primary”的旧事实。
3. tests README 增加计划列出的 13 文件 focused command，并按现有测试更新 admission、CLI/tool、asset collision、fingerprint、atomicity、storage primary 与 processor/read consistency 覆盖面；没有把真实 scenario 写成已执行或已通过。

## Affected tests

执行命令：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_processor_read_consistency.py -q
```

- Exit code：0
- Result：`1358 passed, 1 skipped, 3 warnings in 48.39s`
- Skip：现有 optional real Docling integration env gate 未启用。
- Warnings：3 条第三方 `edgar` deprecation warning，不属于当前回归。

## Full pyright

执行命令：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

- Exit code：0
- Result：`0 errors, 0 warnings, 0 informations`
- 另有 pyright 新版本可用提示，不影响检查结果。

## Branch coverage

先清理 coverage 数据，再对同一 13 文件 affected suite 运行 branch coverage：

```bash
source .venv/bin/activate
python -m coverage erase
python -m coverage run --branch -m pytest <13 affected test files> -q
```

- Exit code：0
- Result：`1358 passed, 1 skipped, 3 warnings in 39.40s`

六个修改生产文件均单独通过 `--fail-under=80`：

| 文件 | Branch coverage | Gate |
| --- | ---: | --- |
| `dayu/fins/ingestion_runtime.py` | 88% | PASS |
| `dayu/fins/upload_format_contract.py` | 89% | PASS |
| `dayu/cli/arg_parsing.py` | 99% | PASS |
| `dayu/cli/commands/fins.py` | 81% | PASS |
| `dayu/fins/tools/upload_tools.py` | 92% | PASS |
| `dayu/fins/pipelines/docling_upload_service.py` | 85% | PASS |

## Scope、whitespace 与 forbidden checks

- `git diff --check`：exit 0，无输出。
- scope：最终 workspace changes 仅包含三个 allowed README 与当前 Slice 4 implementation artifact。
- forbidden files：registry、oracle、scenario、frozen evidence、accepted plan、goal、Host/Engine design 均无修改。
- 文档残留检查：三个 README 不再包含“首项/首个 primary”旧事实；当前 Slice 4 修改没有预写未实现能力。

## Findings 与 residual risks / uncovered areas

- Implementation self-check finding：`tests/README.md` 的既有 upload focused 说明仍残留“首项建模为 primary”；已在当前 slice 改为 raw selector 与 explicit validated selection，同文件复查无旧事实残留。分类：`fixed in current slice`。
- optional real Docling integration 未启用。分类：`assigned to later explicitly authorized evidence gate`；当前 deterministic affected suite 已通过。
- UF-PF07、UF-PF12 未执行。分类：`assigned to later explicitly authorized evidence gate`；这是本 slice 的明确禁止边界，不将其写成通过。
- material basename/stem collision 行为不在本 work unit 修复范围；本轮只记录并验证 material 既有行为不变。分类：`accepted scope boundary`。
- 3 条第三方 `edgar` deprecation warning。分类：`accepted external non-blocking warning`。

所有当前 residual risks 与 uncovered areas 已分类；无 validation failure、unclassified residual risk 或 blocking open question。

## 禁止动作确认与 completion status

- 未执行 UF-PF07、UF-PF12 或其它真实 mandatory scenario/evidence run。
- 未修改 registry、oracle、scenario 或 frozen evidence。
- 未 commit、push、创建 PR 或推进 PR。
- 当前 completion status：`IMPLEMENTATION PASS / CODE REVIEW PENDING`。
- Gate Order 下一个未完成 entry point：`code review`；按用户授权停在当前 implementation gate，不进入 review、commit 或 PR。
