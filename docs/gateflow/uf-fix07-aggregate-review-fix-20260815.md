# UF-FIX07 aggregate deepreview fix artifact

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`aggregate deepreview -> fix`
- 日期：2026-08-15
- 实施基线 HEAD：`6b80400139aba1ba43d950635a6e735467db4316`
- Authoritative amendment：`docs/gateflow/uf-fix07-aggregate-review-plan-amendment-20260815.md`
- Aggregate re-review inputs：`docs/reviews/code-review-20260815-224341.md`、
  `docs/reviews/code-review-20260815-225405.md`（只读）
- Scope：amendment §7 单一 aggregate fix slice
- Artifact path：`docs/gateflow/uf-fix07-aggregate-review-fix-20260815.md`
- Decision：`AGGREGATE FIX COMPLETE / RE-REVIEW PASS`
- 下一入口：controller aggregate acceptance

本 gate 修复 authoritative amendment 接受的两个 aggregate findings，以及 aggregate re-review 接受并闭环的三项 LOW findings
（owner coverage、证据精度、来源回引）。未修改原 plan、goal confirmation、review inputs、registry、oracle、scenario 或 frozen evidence；
未运行 UF-PF07/UF-PF12；未 commit、push 或创建 PR。

## Finding 状态

| Finding | 裁决 | Fix 状态 | 直接证据 |
| --- | --- | --- | --- |
| Finding 1：filing fingerprint 未编码 authoritative primary，auto skip 会保留旧 downstream primary | `accepted` | `已修复` | Service fingerprint owner 新增 typed digest/safety result；single-file 保持 v1 公式，multi-file 使用 role-aware v2；不可区分 primary 等价类禁止 identical-skip，existing source 无条件 version + 1；publication 只持久化 digest `.value` |
| Finding 2：README 把 role order 错写为 input order | `accepted` | `已修复` | Fins README 已改为 primary-first、companions 保持原请求相对顺序，并记录 role-aware fingerprint 与 conservative ambiguity contract |
| Re-review Finding 1（LOW）：四个新增 fail-closed guard 缺少 direct owner coverage | `accepted` | `已修复` | 四条独立 `pytest.raises(ValueError)` 精确覆盖 filing 空 assets、缺 primary、primary identity 未 exact 命中一次、material 非法携带 filing primary；均匹配固定有界消息，production/README 未修改 |
| Re-review Finding 2（LOW）：把 9 个全仓 failures 全部写成 base 稳定复现 | `accepted` | `已修复` | Validation 与 residual risk 均改为 8/9 在 base 稳定复现、1/9 为 unrelated host flaky failure，保留全仓 run 的实际 9 failures 总数 |
| Re-review Finding 3（LOW）：8/1 定向隔离结论缺少来源回引 | `accepted` | `已修复` | Aggregate re-review inputs 与 Validation 显式回引产生定向隔离证据的 `code-review-20260815-225405.md` |

两个原 aggregate findings 与三项 re-review LOW 均为 `已修复`；没有 `部分修复`、`未修复` 或 `证据失效` finding。

## 实际实现

### Production owner

`dayu/fins/pipelines/docling_upload_service.py` 完成以下最小变更：

1. 增加 frozen/slotted `_UploadSourceFingerprint(value, identical_skip_safe)`；safety 只属于当前 preparation，不新增 durable 字段。
2. `_UploadSelectionPreparation.filing_primary` 直接承接 validated filing selection 的 authoritative primary；delete/material 为
   `None`，不从 `ordered_files[0]`、converter input、旧 meta 或 downstream 反推。
3. single-file filing 保持 amendment 前 descriptor-list 公式；multi-file 使用
   `filing-primary-role-v2` envelope，primary 独立投影，companions 按 descriptor 稳定排序。
4. role-to-asset 关联只在内存中用现有 path-private asset identity exact 命中；path identity、绝对路径、请求位置与输入顺序不进入
   fingerprint payload。
5. primary descriptor 与任一 companion descriptor 完全相同时，digest 仍忠实描述角色集合，但
   `identical_skip_safe=False`；没有 path hash、index、nonce 或其它伪可区分字段。
6. `_can_skip_upload()` 只拥有 skip 决策：overwrite、无 previous、deleted 或 unsafe 均不 skip；safe 且 previous digest 非空相等才 skip。
7. `_resolve_document_version()` 只拥有继续发布后的版本决策：无 previous 为 `v1`；existing + unsafe 无条件从 canonical previous
   version 增长一次；existing + safe 只在非空 previous digest 改变时增长。
8. `prepare_upload()` 把同一个 typed fingerprint 依次交给 skip/version owner；upsert meta 与 prepared mutation 只保存 `.value`。
   typed result、primary path、role order 与 safety bool 均未持久化。
9. material 继续使用现有 name-sorted payload，fixed digest 与 safe skip/version contract 未改变。

### Owner tests

`tests/fins/test_docling_upload_service.py` 新增或强化以下 contract tests：

- 可区分 A/B/C 集合 primary flip：create `v1`，flip 后 update `v2`，repository `primary_document`、derived
  `derived_from` 与 snapshot `get_primary_source()` 全部切换到 B；同角色但 companions 重排后 identical-skip，保持 `v2` 且 converter
  call count 不增长。
- 两个不同规范路径具有相同 basename/bytes 的 ambiguous case：两种 primary 的 v2 digest 相同且 unsafe；create/replay/flip 精确为
  `v1 -> v2 -> v3`，flip 后 path-private primary/derived identity 指向新 primary；改变 companion descriptor 后 update 到 `v4`，再次
  replay safe skip 并保持 `v4`。
- primary 唯一而两个 companions descriptor 相同的反例保持 safe，conservative policy 未扩大到 companions-only duplicate。
- 可区分 multi-file 整组跨目录 move：两组 storage identities 全部变化，但 typed v2 digest 相同且 safe；auto skip、版本保持 `v1`、
  converter 不重跑，repository 继续保留旧已发布 tree。
- 独立 old-v1 fixture 不调用 production builder，直接按旧 descriptor-list 公式 seed previous meta；相同 multi-file 首次转 v2 时 update 到
  `v2`，再以 v2 digest replay skip；同 fixture 同时证明 single-file old/current digest 相等。
- single-file move/rename/content 继续固定为 skip `v1`、update `v2`、update `v3`，并冻结 digest
  `e7d70a19bec88c733e519eace405aea9e0a357db2f7a53cdc9450d545c430848`。
- material fixed digest 继续为
  `099dc9636e306c75f1d5d64dd0210123956ba73888e968088c7279baab1d7fdd` 且 safe；既有 identical-skip 与
  rename/content replacement tests 继续通过。
- 直接 owner 断言 existing unsafe 在 previous fingerprint 缺失时仍从 `v7` 增长到 `v8`，unsafe equal digest 也不能 skip。
- 四个新增 fail-closed guard 分别使用 direct owner test 冻结：filing 空 assets、`filing_primary=None`、primary identity 在
  original assets 中未 exact 命中一次、material 非法携带 filing primary。每条均精确断言 `ValueError` 与固定安全有界消息，不构造
  compatibility、fallback 或 loose parsing 路径。

### README decision

已先读取并遵守 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`。README 只更新当前已实现的 upload contract：originals
按 primary-first role order 读取；single/multi-file fingerprint 边界、primary flip update、ambiguity conservative update、ordinary
single-file move/rename/content 与 material 不变。未写测试命令、gate 状态、旧迁移兼容或未来计划。

## Validation

### Focused owner validation

- `python -m pytest tests/fins/test_docling_upload_service.py -q`：`80 passed in 1.26s`。
- `python -m pyright dayu/fins/pipelines/docling_upload_service.py tests/fins/test_docling_upload_service.py`：
  `0 errors, 0 warnings, 0 informations`。

### Amendment §8 affected gate

- 13-file affected suite：`1366 passed, 1 skipped, 3 warnings in 35.19s`。
- 三项 warning 均来自 `.venv` 中 edgar deprecated import，不是本次 diff 产生的 failure。
- full pyright `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 同一 13-file branch coverage run：`1366 passed, 1 skipped, 3 warnings in 39.11s`。
- `coverage report --show-missing` 不再列出 production guard 行 `1267`、`1269`、`1273`、`1318`，确认四条新增 owner tests
  分别命中对应 fail-closed branch。

逐文件 branch coverage `--fail-under=80`：

| Production file | Coverage | Gate |
| --- | ---: | --- |
| `dayu/fins/ingestion_runtime.py` | 88% | PASS |
| `dayu/fins/upload_format_contract.py` | 89% | PASS |
| `dayu/cli/arg_parsing.py` | 99% | PASS |
| `dayu/cli/commands/fins.py` | 81% | PASS |
| `dayu/fins/tools/upload_tools.py` | 92% | PASS |
| `dayu/fins/pipelines/docling_upload_service.py` | 87% | PASS |

### 全仓 pytest 隔离结论（只读 reviewer evidence）

本 fix gate 没有再次运行全仓 tests。只读 review artifact `docs/reviews/code-review-20260815-224341.md` 记录的全仓结果为
`7704 passed, 9 failed, 10 skipped, 6 deselected`。定向隔离证据见只读 review artifact
`docs/reviews/code-review-20260815-225405.md`：对同一组 9 个 failure test IDs 的 base `64050349` 临时 worktree 定向复跑结果为
`8 failed, 1 passed`：8 个失败稳定复现于 base；`test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` 在 base 与移除当前
working diff 的 HEAD 均通过，属于全仓运行中的 flaky failure。相关用例位于 `tests/host/*`、`tests/service/test_import_boundary.py`、
`tests/cli/test_init_workspace.py` 与 `tests/cli/test_upload_filings_from_command.py`；这些路径不属于 base..HEAD 或当前 aggregate fix diff。
因此 9 个全仓 failures 均分类为 `pre-existing unrelated`，但只有 8 个可声明为 base 稳定复现；它们不影响本 work unit 的 13-file
affected gate，当前 scope 不修改生产、fixture 或测试来掩盖这些问题。

### Diff / scope / forbidden checks

- `git diff --check`：PASS。
- 实施期间 HEAD 保持 `6b80400139aba1ba43d950635a6e735467db4316`。
- tracked implementation diff 与本 artifact 合计只包含 amendment §7 四个 allowed paths。
- 四份 code/plan review inputs、原 plan 与 goal confirmation 的 `git diff` 为空。
- production diff 没有 `hasattr/getattr`、loose parsing、legacy helper、fallback、dual-read、compatibility branch 或新 public/storage/schema 字段。
- 既有 `path_digest` 只属于 amendment 明确保留的 filing storage asset identity owner；fingerprint payload 不包含 path identity、绝对路径、
  input order/index、inode、mtime 或 nonce。
- source meta 与 prepared mutation 只持久化 fingerprint `.value` 字符串，不持久化 typed result、primary path、role order 或
  `identical_skip_safe`。
- 未运行 UF-PF07/PF12，未修改 registry/oracle/scenario/frozen evidence，未提交或创建 PR。

## Residual risks / uncovered areas

| 风险或未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| primary 与 companion descriptor 完全相同时无法在不引入 path/order identifier 下区分；ambiguous replay 会持续 version churn | accepted conservative boundary | 当前 owner 明确禁止 identical-skip；existing source 每次 unsafe upsert 无条件 update/version increment；descriptor 恢复可区分后可再次 safe skip |
| 当前已持久化的旧无角色 multi-file digest 首次按 v2 upsert 会 update/version increment | fixed in current aggregate fix | 独立 old-v1 seed test 固定 fail-safe transition；不做 dual-read 或 compatibility shim |
| 旧 basename-based source schema 的兼容、首次重传或自动修复 | assigned to later work unit | `UF-FIX08` |
| 同 request/同 document 并发 writer | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| optional real Docling 与 UF-PF07/UF-PF12 未执行 | assigned to later evidence work | 等待独立授权；本 fix 只完成 deterministic owner/aggregate validation |
| registry/oracle/frozen evidence 仍记录修复前观察 | assigned to later evidence work | 当前 gate 明令只读，等待后续 evidence work |
| 全仓 pytest 的 9 个 failures | pre-existing unrelated | 8/9 在 base `64050349` 稳定复现；1/9 为与当前 diff 无关的 host flaky failure；归 host/service/CLI 对应 owner，当前 13-file affected gate 不受影响 |

所有 residual risks 已分类；没有 blocking open question，也没有未分类 residual risk。

## Completion status

- Changed files：`dayu/fins/pipelines/docling_upload_service.py`、`tests/fins/test_docling_upload_service.py`、
  `dayu/fins/README.md`、`docs/gateflow/uf-fix07-aggregate-review-fix-20260815.md`。
- Aggregate findings：原 Finding 1、Finding 2、guard owner tests LOW、全仓失败证据精度 LOW 与证据回引 LOW 均 `已修复`。
- Validation：focused tests、13-file affected suite、full pyright、branch coverage 六文件 gate、diff/scope/forbidden checks 均 PASS。
- Decision：`AGGREGATE FIX COMPLETE / RE-REVIEW PASS`。
- Next entry point：controller aggregate acceptance。
- 不 push、不创建 PR；真实 UF-PF evidence 与 registry/oracle/scenario/frozen evidence 保持只读。
