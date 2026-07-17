# WU-SEMANTIC-OWNERSHIP-01 / R11-S1 implementation evidence（AgentCodex）

## 1. Gate、scope 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- remediation sub-WU：R11；slice：`R11-S1 — Fins OLD batch classification owner`。
- 当前 Agent：AgentCodex；授权只覆盖 S1 implementation 与本 evidence。
- verdict：`STOPPED_BEFORE_IMPLEMENTATION`。
- stop owner：Controller；需要重新裁决 S1/S2 slice boundary 或 S1 checkpoint 的 full-pyright 要求。

第一性原理判断：R11-S1 的业务动机成立，正确 semantic owner 是
`dayu.fins.upload_batch`。但 accepted S1 producer contract 与仍在只读 S2 consumer 中的旧公共类型/字段形成直接、
可复现的 transition conflict。若仅在 S1 allowlist 内实现 accepted contract，必然破坏当前 CLI 静态类型与运行期 import；
若保留旧类型/字段来维持当前 CLI，则会违反 accepted plan 明令禁止的 generic contract、compatibility alias/seam 和
“entry type 是唯一 command discriminator”约束。因此没有一个同时满足 exact allowlist、owner contract、no-compat 与
full pyright 零新增 error 的实现路径。

根据 authorization §7 的 `coverage/type/lint/test 失败或 diff 超出 exact allowlist` stop gate，本 Agent 未修改
product/test，未进入 S2/S3，也未用下游 adapter、fallback 或兼容 shim 补偿。

## 2. Before locks

| Lock | 实测值 | Verdict |
|---|---|---|
| branch | `phaseflow/host-issues-control` | PASS，非 protected trunk |
| HEAD / accepted-plan commit | `f7b452f992b4797b32fea7c6f7212b5ec4345ec1` | PASS |
| accepted plan SHA-256 | `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025` | PASS |
| `AGENTS.md` SHA-256 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | PASS |
| `dayu/fins/upload_batch.py` | 376 lines / 12,000 bytes / `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` | PASS |
| `tests/fins/test_upload_batch.py` | 187 lines / 5,914 bytes / `7668bf268eab97f250684cee2ea3cacbca31e6e5a7a02c9605ab90b2b7ea6a69` | PASS |
| current read-only CLI consumer | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` | 与 accepted plan §2.2 lock 一致 |
| Ruff version | `ruff 0.15.11` | PASS，逐字匹配 oracle |
| Ruff baseline file | 144 findings / `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` | PASS |
| staged tree | empty | PASS |

开始时 workspace 只有 Controller-owned 状态：

```text
 M docs/host/issues-implementation-control.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-s1-controller-authorization.md
```

开始时 Controller-owned 文件实测 SHA-256：

- `docs/host/issues-implementation-control.md`：
  `225d87a5c1e77afd1c331c78628988e3275a4e873187610c5e47382e04a89b9b`
- `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-s1-controller-authorization.md`：
  `339422269ec49476e98afe0978520cdc6b440492d938d0b8ece1fe1a33cc95ce`

本 Agent 未覆盖、删除、stage 或修改这两个 Controller-owned 路径。

## 3. Direct stop evidence 与 root cause

### 3.1 Accepted S1 owner contract

Accepted plan §5.1 / §5.3 与 authorization §4 同时要求：

- 用 `UploadBatchFilingEntry` / `UploadBatchMaterialEntry` / `UploadBatchSkippedEntry` / `UploadBatchPlan`
  替换 generic entry/result；
- plan 只承诺 `recognized_entries`、`material_entries`、`skipped_entries`；
- 不保留 generic `command_name`；单一文件字段是 `file`；
- entry 的具体类型是 S2 唯一 command discriminator；
- 禁止 compatibility alias、adapter、fallback、loose parsing 或下游重算。

### 3.2 Current read-only S2 consumer

`dayu/cli/commands/fins.py` 当前仍直接消费被 S1 contract 删除的旧 surface：

```text
54:from dayu.fins.upload_batch import (
58:    UploadBatchPlanEntry,
307:    serialized_plan = _render_upload_batch_plan(plan.entries)
316:def _render_upload_batch_plan(entries: tuple[UploadBatchPlanEntry, ...]) -> str:
332:def _upload_batch_command_argv(entry: UploadBatchPlanEntry) -> tuple[str, ...]:
339:        entry.command_name,
344:    if entry.command_name == COMMAND_UPLOAD_MATERIAL:
350:    parts.extend(str(path) for path in entry.files)
```

它还把旧 generic plan 投影成 JSON argv；该 consumer 计划到 S2 才能被合法修改。当前 S1 exact write allowlist 不含
`dayu/cli/commands/fins.py`。

### 3.3 Validation contradiction

修改前执行 authorization 指定的 full pyright baseline：

```text
$ source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

所以删除旧 import target/字段会形成新增 type errors；这不是可接受的 existing baseline。保留
`UploadBatchPlanEntry` / `UploadBatchPlanResult`、`entries`、`command_name`、`files` 或 material fields on filing 仅为
现有 CLI 继续工作，则与 accepted contract 和 no-compat 明文冲突。通过 `__getattr__`、dead legacy dataclass、property、
union alias、overload 或 test-only seam 隐藏该问题仍是下游/兼容补偿，未采用。

这是同一 producer-consumer contract 的直接逻辑证据，不是从日志、fixture 或间接报错推断 root cause。

## 4. Exact product/test diff manifest 与 final locks

由于 stop 发生在首次 `apply_patch` product/test 修改前，两个授权 product/test 路径的 diff 精确为空：

```text
$ git diff --name-only f7b452f992b4797b32fea7c6f7212b5ec4345ec1 -- \
    dayu/fins/upload_batch.py tests/fins/test_upload_batch.py
<empty>
```

| Path | Final SHA-256 | Diff |
|---|---|---|
| `dayu/fins/upload_batch.py` | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` | none |
| `tests/fins/test_upload_batch.py` | `7668bf268eab97f250684cee2ea3cacbca31e6e5a7a02c9605ab90b2b7ea6a69` | none |

Agent-owned diff 只有本 evidence 路径；没有额外 product/test/README/design/workflow diff。

## 5. Field / enum / optional consumer checklist

Checkpoint 状态：`NOT_FROZEN — implementation stopped`。以下 accepted contract 已读取并用于确认 blocker，但没有伪报为
已实现：

| Typed fact | Accepted lock | Implementation status |
|---|---|---|
| filing/material entry type | 唯一 command discriminator | NOT IMPLEMENTED |
| ticker / aliases | canonical + ordered tuple；empty aliases 为 `()` | NOT IMPLEMENTED |
| action | `auto|create|update`，default `auto` | NOT IMPLEMENTED |
| file | 每 entry 精确一个 `Path` | NOT IMPLEMENTED |
| filing fiscal fields | `year` 与 `FY|H1|Q1|Q2|Q3|Q4` 均非 optional | NOT IMPLEMENTED |
| material fiscal fields | year/period 分别可为 `None` | NOT IMPLEMENTED |
| amended | `bool`，absent `False` | NOT IMPLEMENTED |
| filing/report dates、company | `str | None`，absent `None` | NOT IMPLEMENTED |
| overwrite | `bool`，absent `False`；只表示 storage overwrite | NOT IMPLEMENTED |
| material form/name | 三个 normalized form enum + required name；material-only | NOT IMPLEMENTED |
| skipped | `path + typed reason code + readable reason` | NOT IMPLEMENTED |

## 6. Tests、smoke、coverage、pyright 与 Ruff

| Gate | Result |
|---|---|
| focused owner tests | NOT RUN；stop 发生在 product/test 修改前 |
| real filesystem smoke | NOT RUN；没有可验证的新 owner implementation |
| coverage JSON / `upload_batch.py >=80%` | NOT RUN；changed production file 集合为空 |
| full pyright baseline | PASS；`0 errors, 0 warnings, 0 informations` |
| target Ruff | NOT RUN；没有 implementation diff |
| full Ruff current JSON / current-only delta | NOT RUN；stop 发生在 implementation 前；未重锁或修改 baseline |
| diff check | product/test diff 为空；evidence 完成后单独执行并记录 final workspace 状态 |

Ruff version 与 baseline file lock 已验证；没有使用 `noqa`、exclusion、baseline 更新或版本重锁。

## 7. README trigger、owner/security/deferred scans

- 已读取 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`：它只记录当前已实现的 package capability，S1
  原计划不修改 README，最终同步属于 R11-S3。
- 已读取 `tests/README.md` 的更新约束；本次没有测试实现变化，因此无 README diff。
- reverse dependency blocker：当前依赖方向是 CLI -> Fins，合法；问题是 S1 producer contract 原子替换无法与只读旧
  consumer 同一 checkpoint 保持可运行/可类型检查。没有引入 Fins -> CLI/Service/Host/Engine/UI 反向 import。
- security：没有修改 discovery、containment 或 symlink 代码，因此不能声明 accepted security contract 已实现或通过；
  没有放宽 lexical/resolved boundary，也没有新增 renderer/argv/output/JSON protocol。
- deferred：Service/runtime/storage/FMP resolver/ticker normalization/design/constraints、Issue 142/151/175/177/178、
  R12、Topic 8/9、统一 authorization、S2/S3 production diff 均未进入本 Agent scope。
- 没有执行 post-implementation owner/security/deferred scan matrix，因为没有 implementation；以“未运行”而非 pass 记录。

## 8. Workspace / staged state 与 stop verdict

- Controller-owned dirty/untracked paths保持原样，SHA 未被本 Agent 改写。
- `git diff --cached --name-only`：empty。
- 未 stage、commit、push、创建 PR 或进入 S2/S3。
- stop condition：`TRIGGERED`。
- blocker 分类：accepted producer contract 与 exact slice allowlist/full-pyright checkpoint 互不相容，需要 Controller
  调整授权边界或 validation sequencing；Agent 无权自行扩域。
- residual risk：未分类 residual 为 0；这是 implementation blocker，不转 residual，也不伪报 S1 pass。

READY_FOR_CONTROLLER_S1_CHECKPOINT_VALIDATION
