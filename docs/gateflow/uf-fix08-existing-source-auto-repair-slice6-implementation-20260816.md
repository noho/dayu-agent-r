# UF-FIX08 existing-source-auto-repair：Slice 6 implementation

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`implementation`
- slice：`Slice 6：download unsafe 回归、文档与全量验证`
- 日期：2026-08-16
- baseline / current HEAD：`1e062f6cc13c22232449b4dc80ffcccb93b796d7`
- accepted plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- 前置状态：Slices 1–5 已有 accepted commits；Slice 5 HEAD 为 `1e062f6c`
- code review：`docs/reviews/code-review-20260816-183959.md`、`docs/reviews/code-review-20260816-184513.md`
- completion status：`CODE REVIEW FIXED / awaiting re-review`
- blocking questions：无
- 下一入口：Slice 6 re-review

## 第一性原理与语义 owner 裁决

动机成立。storage 的 typed integrity classification 已由前序 slices 收敛为 source publication 完整性的唯一真源；download workflow
只应在 Phase A、whole-tree preflight 与 Phase B 消费 typed fact，不能读取 raw meta、检查文件存在性、扫描目录或解释异常字符串。

当前代码直接证据表明：

1. `classify_source_integrity_preflight(...)` 已实现 whole-tree `UNSAFE_PUBLICATION`、多个
   `REPAIR_REQUIRED`、未选中与已拒绝 repair target 的 typed 拒绝；SEC/CN 顶层 workflow 已在 company、maintenance、rejection
   publication 前调用该 owner，并把唯一 `SelectedSourceRepairRequired` 排到首位，修复后再次 whole-tree recheck。
2. storage inspector 已把 whole source-kind manifest missing 投影为每个 actual source 的 shared
   `SOURCE_MANIFEST_MISSING`。因此多 actual source 自然形成多个 repair targets，非 selected actual source 由 preflight 拒绝；唯一 actual
   filing 且为 accepted selected target 时，既有 download reset + canonical upsert 能重建 manifest。
3. 实际缺口只存在于两份 single-filing workflow：Phase A 对 `UNSAFE` 仍会读取 previous meta；Phase B 会先调用 publication identity
   comparator，SEC 后续还存在“非 `MISSING` 即 reset”的分支。`UNSAFE` 因而没有在所有 mutation 前显式 typed fail closed。

因此本 slice 没有修改 storage classifier、顶层 workflow、provider/retry/registry owner，也没有复制 whole-tree 决策。production 只在四个
typed classification 消费点加入 `UNSAFE_PUBLICATION` gate。

## 实际修改

### SEC/CN download Phase A 与 Phase B

- SEC/CN Phase A 在 `classify_source_integrity(...)` 返回后、读取 previous meta 或计算复用状态前，显式把 `UNSAFE` 转为
  `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`。
- SEC/CN Phase B 在 `classify_staged_source_integrity(...)` 返回后、publication identity 比较、retry/skip/reset/blob/company/source mutation
  前执行同一 typed gate。
- `MISSING`、`COMPLETE`、`REPAIR_REQUIRED` 的既有 identity retry、complete skip、repair unconditional transport、overwrite 与 reset/upsert
  路径保持不变；未增加 retry 次数、provider policy、rejection registry 或结果收敛语义。
- 两个 public workflow docstring 补充 typed preflight/revision failure；没有新增 helper、fallback、raw meta parsing、目录扫描或异常字符串判定。

### Owner-level tests

- SEC：
  - 真实 source 加入 undeclared file 形成 storage-owned `UNSAFE`，分别从 single-filing Phase A 与顶层 whole-tree 入口断言
    `UNSAFE_PUBLICATION`；provider filing transport、batch、company meta、rejection registry 均零 mutation，旧 meta/payload/manifest/unsafe
    bytes 不变。
  - Phase A 为 `COMPLETE + overwrite=True` 时继续到真实 batch；staged classifier 返回 invariant-valid typed `UNSAFE` 后，直接断言
    `UNSAFE_PUBLICATION`、begin/rollback 各一次、零 reset/blob/commit，以及 published meta/payload/manifest bytes 与 `COMPLETE` 状态不变。
  - whole manifest missing + 两个 actual sources 返回 `MULTIPLE_REPAIR_REQUIRED`；provider filing transport、company、rejection 与 source
    bytes 不变，每个 actual source 都保持 shared manifest repair reason。
  - 非 selected source 的 whole manifest missing 返回 `UNSELECTED_REPAIR_REQUIRED`。
  - 唯一 accepted selected source 的 whole manifest missing 继续真实下载/reset/upsert，完成后 public classification 与 snapshot 均为
    `COMPLETE`，canonical manifest 已重建。
- CN：
  - Phase A 真实 `UNSAFE` 在 previous-meta reuse、PDF transport 与 batch/reset 前拒绝。
  - Phase B 注入 storage typed staged `UNSAFE`，断言唯一 begin 后 rollback、零 reset/blob/commit、source 仍 absent。
  - whole manifest missing + FY/H1 两个 actual 且同时 selected，返回 `MULTIPLE_REPAIR_REQUIRED`，company/source/batch/download mutation 为零。
  - whole manifest missing + actual target 未 selected，返回 `UNSELECTED_REPAIR_REQUIRED`。
  - 唯一 accepted selected source 的 whole manifest missing 继续 reset/download/upsert，manifest 重建且 public classification/snapshot 为
    `COMPLETE`。

### README

- 根 `README.md` 仅写最终用户事实：完整本地输入下 `auto` 可原子重建安全可修复目标；显式 action 与无法安全重建状态在发布前给出可行动失败。
- `dayu/fins/README.md` 删除只描述缺文件/size/digest 三类损坏的旧说明，记录四态、trusted revision、validator-only repair
  authorization、fresh/staged recheck、existing batch old-or-new、snapshot complete-only，以及 download whole-tree/Phase A/Phase B typed
  fail-closed。
- `tests/README.md` 增加 accepted focused owner command，并记录 storage/validator/publication/snapshot/downstream/download owner matrix。
- 未修改 `dayu/README.md`、Host/Engine/config README；分层与 assembly 无变化。

## Changed files

Production：

- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`

Tests：

- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_cn_download_workflow.py`

Docs：

- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice6-implementation-20260816.md`（本 artifact）
- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice6-code-review-fix-20260816.md`

没有修改其它 production/test/doc，尤其没有修改 oracle、scenario、design、evidence、registry 或 calibration record。

## Validation

运行环境：仓库 `.venv`，Python 3.11。

新增/修改 contract nodes：

```text
16 passed, 3 warnings in 1.37s
```

Code review fix 新增 SEC Phase B direct node：

```text
python -m pytest \
  tests/fins/test_sec_pipeline_download.py::test_sec_unsafe_phase_b_rolls_back_without_reset_blob_or_commit -q
1 passed, 3 warnings in 0.86s
```

两份直接受影响测试文件：

```text
python -m pytest tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_workflow.py -q
201 passed, 3 warnings in 2.93s
```

accepted plan §10 focused matrix：

```text
1230 passed, 3 warnings in 45.40s
```

完整 Fins suite：

```text
python -m pytest tests/fins -q
1851 passed, 1 skipped, 3 warnings in 50.10s
```

Service + CLI regression：

```text
python -m pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
188 passed, 3 warnings in 11.01s
```

focused branch coverage 采集：

```text
coverage run --branch -m pytest <accepted focused matrix>
1230 passed, 3 warnings in 51.71s

dayu/fins/pipelines/sec_download_filing_workflow.py  83% branch-aware coverage
dayu/fins/pipelines/cn_download_filing_workflow.py   83% branch-aware coverage
```

两份修改 production 均达到单文件 `>=80%`。

全仓固定类型检查：

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

三条 warning 均来自已安装 `edgar` package 的既有 deprecated imports；唯一 skip 是仓库既有环境条件 skip。

## Scope、frozen guards 与执行约束

- `git diff --check`：通过。
- HEAD 保持 `1e062f6cc13c22232449b4dc80ffcccb93b796d7`；未 commit、未 staged、未 push、未 clear、未创建 PR。
- artifact 写入前，diff 只包含 7 个用户允许修改的 production/test/README 文件；本 artifact 是用户明确允许新增的 Slice 6
  implementation artifact。
- `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/host/design.md`、`docs/engine/design.md` diff 为空。
- 未执行 `dayu-cli`、UF-PF08、UF-PF12、真实 provider evidence 或真实 converter evidence。
- 未修改 material repair、UF-FIX10 retry、UF-FIX11 company warning、旧 schema compatibility、CLI/tool schema、Service/Host/Engine。

## Residual risks 与后续 owner

| residual / 未覆盖项 | 分类与 owner |
| --- | --- |
| 一般 preparation 并发的 success/skip 收敛 | `UF-FIX10`；本 slice 只保护既有三轮 download identity retry |
| fresh company meta warning | `UF-FIX11` |
| material existing-source repair | 后续独立 work unit；本 slice 未扩大 authorization |
| 旧 schema compatibility/migration | 后续显式 migration work unit（若授权） |
| 真实 CLI/provider/converter evidence 与 registry/oracle adjudication | UF-PF08/UF-PF12 evidence work unit |

没有未分类 residual risk，没有 blocking question。当前 artifact 只表示 Slice 6 implementation pass，不表示 code review 或 UF-FIX08
aggregate deepreview 已通过。

## 下一入口

Code review fix 已完成并按用户要求停在 Slice 6 re-review gate。下一步应对当前未提交 diff、implementation artifact 与 fix artifact执行
独立 re-review；本轮不 commit、不 clear、不自动进入 deepreview 或 closeout。
