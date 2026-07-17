# WU-SEMANTIC-OWNERSHIP-01 / R11 R11-IMP-BF01 plan-boundary fix evidence（AgentCodex）

## 1. Gate、scope 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`；continuation：同一 R11 accepted plan 的 plan-only amendment。
- finding：`R11-IMP-BF01 — 原 producer/consumer checkpoint 不能形成合法中间 tree`。
- accepted-plan commit / current HEAD：`f7b452f992b4797b32fea7c6f7212b5ec4345ec1`。
- branch：`phaseflow/host-issues-control`。
- evidence timestamp：`2026-07-17 22:57:52 +0800`（由本机 `date` 生成）。
- exact write allowlist：R11 plan 与本 evidence；未授权且未修改 product、test、README、design、CI、Controller control、
  S1 authorization/stop/adjudication artifact。
- Agent verdict：Controller §5 的全部 plan-amendment requirements 已在 plan boundary 闭合，完整 amended plan 的
  adversarial review 为 `pass`，未发现新 material finding。Controller finding ledger 仍由 Controller 在完整读取与双路
  complete re-review 后正式转为 closed；本 evidence 不越权授权 implementation、stage、commit、push、PR 或 R12。

第一性原理结论：finding 的动机成立且 severity=BLOCKER 准确。它不是测试或 implementation 技巧问题，而是同一静态
producer-consumer contract 的 atomic cutover boundary 错误。正确 owner 是 R11 plan 的 slice state machine；产品 semantic
owner 仍是 Fins producer，CLI 仍是 typed consumer/argv/renderer/publisher owner，不因修订而改变。

## 2. Before / final plan locks

| Lock | Before | Final |
|---|---:|---:|
| plan lines | 773 | 848 |
| plan bytes | 61,810 | 70,036 |
| plan SHA-256 | `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025` | `9d46ecfc74ced43b6f4868405fbee426523cee754456f0f2131aa3c4dd917be0` |

其它只读 evidence locks：

- `AGENTS.md`：`cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e`。
- `dayu/fins/upload_batch.py`：376 lines / 12,000 bytes /
  `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178`。
- `dayu/cli/commands/fins.py`：1,057 lines / 37,116 bytes /
  `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6`。
- S1 stop evidence：`a01e188e5acc4eae9e75e0106014d5af7b0c2cb697ab507e42812ac503b5258c`。
- Controller adjudication：`b53f0c7546801a48d465b70c66a1fbf0f51fd3cd2cec595b449a3e56364db600`。

## 3. Direct producer-consumer root-cause evidence

CURRENT Fins producer 仍定义/导出 `UploadBatchPlanEntry` 与 `UploadBatchPlanResult`，以 `command_name`、multi-file `files`、
单一 `entries` 表达 generic plan：

```text
dayu/fins/upload_batch.py:90:class UploadBatchPlanEntry:
dayu/fins/upload_batch.py:108:    command_name: BatchUploadCommandName
dayu/fins/upload_batch.py:111:    files: tuple[Path, ...]
dayu/fins/upload_batch.py:123:class UploadBatchPlanResult:
dayu/fins/upload_batch.py:135:    entries: tuple[UploadBatchPlanEntry, ...]
```

CURRENT CLI consumer 在同一 tree 中直接 import 并读取该 surface：

```text
dayu/cli/commands/fins.py:58:    UploadBatchPlanEntry,
dayu/cli/commands/fins.py:307:    serialized_plan = _render_upload_batch_plan(plan.entries)
dayu/cli/commands/fins.py:316:def _render_upload_batch_plan(entries: tuple[UploadBatchPlanEntry, ...]) -> str:
dayu/cli/commands/fins.py:342:        entry.command_name,
dayu/cli/commands/fins.py:354:    parts.extend(str(path) for path in entry.files)
```

因此 producer-only 删除旧类型/字段会直接破坏 CLI import/attribute/type contract；保留旧 surface、property、alias、wrapper、
dead dataclass、union adapter 或 dual reader 又违反 no-compat 与唯一 typed owner。当前 full pyright baseline 是 0 errors，不能
以 transient broken tree 或放宽 full pyright 跨过中间 checkpoint。唯一最窄修复是原 producer+consumer atomic cutover。

## 4. Controller adjudication §5 requirements mapping

| Controller §5 requirement | Amended plan evidence | Verdict |
|---|---|---|
| 1. 三 slices 改为 atomic Fins+CLI → packaging 两 slices | §1 lines 7—21 固定同一 R11 plan-only continuation；§2.4 lines 97—104 映射 `R11-I1/R11-I2`；§9.1 lines 749—779 固定精确 two-slice state machine | CLOSED |
| 2. §5/§6 只作同一 slice 内 ordered work packages，中间无 checkpoint/next/stop/commit/full validation | §4 lines 196—209 合并 allowlist；§5 lines 211—346 为 WP-A；§6 lines 348—512 为 WP-B；§9.1 lines 753—769 明令无 broken-tree/stop/handoff/checkpoint/accept/commit/full validation | CLOSED |
| 3. 精确合并原 allowlists、tests/smokes/coverage/pyright/Ruff/scans且不降 gate | §4 lines 196—205 列出原 producer+consumer 八个 write paths；§5.3、§6.6 只在共同 cutover 后运行；§8 lines 631—687 固定 cumulative tests、smokes、coverage `>=80`、full pyright 0、Ruff `0.15.11` 与 baseline | CLOSED |
| 4. consumer gap 变为同一 slice Fins owner targeted correction并重跑 combined validation | §5.3 lines 335—346、§6.6 lines 508—512、§9.1 lines 770—775；只改 Fins owner 两路径，禁止 CLI fallback/compat，再跑 producer+consumer 全部 cumulative gate | CLOSED |
| 5. 全文更新 §1、§4、§5/§6、§9.1—§9.4、checklist及旧三-slice引用；packaging不扩 scope | §1、§2.4、§4—§10 均已传播；§7 lines 514—626 保留原 packaging/README/Windows 内容并明确不回改/扩张 I1 | CLOSED |
| 6. 两 slices 后只做一次 cumulative code review；无中间 commit | §9.1 lines 777—779 与 §9.2 lines 783—797；state machine 只有 `one cumulative code-review gate` | CLOSED |
| 7. 保留 Windows/Ruff/coverage/security/deferred/no-touch/no-push | Windows `PENDING_RELEASE_BLOCKER` 在 §7.2、§9.2、§9.4；Ruff `0.15.11`/baseline 在 §8.1；coverage 在 §8.2；security/deferred/no-touch 在 §3.3/§8.3；no-push 在 §1/§9.3 | CLOSED |

## 5. Complete source / propagation scans

### 5.1 Legacy three-slice/state-machine zero scan

执行：

```bash
rg -n 'R11-S[123]|R11-S1[[:space:]]*->[[:space:]]*R11-S2|S1[[:space:]]*->[[:space:]]*S2|严格顺序最多三个|三个 dependency-ordered slices|三个 slices|三 slice|S1 checkpoint|S2 checkpoint|S3 checkpoint|进入 S[123]|回到 S[123]|从 S[123]|Slice [123][[:space:]]' \
  docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md
```

结果：exit `1`，stdout empty，证明无旧 `R11-S1 -> R11-S2 -> R11-S3`、三-slice、旧 checkpoint 或旧 next-slice
state transition。

对 bare historical label 另行执行：

```bash
rg -n '\bS1\b|\bS2\b|\bS3\b' \
  docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md
```

唯一命中是 line 12 的 `S1 authorization/stop/adjudication artifacts`，它是用户要求 no-touch 的 Controller artifact 专名，
不是 implementation slice/checkpoint 语义；`S2`/`S3` 零命中。

### 5.2 Positive two-slice propagation

正向扫描命中：

```text
211:## 5. Atomic slice R11-I1 / WP-A — Fins OLD batch classification owner
348:## 6. Atomic slice R11-I1 / WP-B — Current CLI grammar、FMP 与 shell/cmd renderer
514:## 7. Slice R11-I2 — Placeholder/package/README closure 与 Windows release evidence
749:严格顺序精确两个 implementation slices：R11-I1 ... -> R11-I2 ...
762: -> one cumulative code-review gate
```

所有 `checkpoint` 命中经完整逐项人工审阅后只属于四类：

1. 明确禁止 WP-A/WP-B 中间 checkpoint/acceptance/commit/full validation；
2. WP-A+WP-B 共同 cutover并完成 combined validation 后的唯一 `R11-I1 atomic checkpoint`；
3. 第二 packaging slice 完成并重跑 final cumulative validation 后的 `R11-I2 checkpoint`；
4. acceptance checklist 对上述同一语义的复述。

不存在 producer-only checkpoint、CLI-only checkpoint、work-package acceptance、work-package commit 或第三 slice
transition。全文完整重读亦确认 §9.2—§9.4 的 aggregate/accepted commit/completion gate 顺序未被破坏。

### 5.3 Retained contract / boundary scan

- 原 cumulative product/test/README/CI allowlist逐项保留；`R11-I1` 只是八个原 producer+consumer paths 的 union，
  `R11-I2` 仍精确使用原 packaging paths。
- product decisions、Fins/CLI owner map、typed field/enum/optional mapping、POSIX/Windows真实 smoke、每个 changed production
  Python file line coverage `>=80.00`、full tests、full pyright、Ruff same-version baseline与 current-only=empty均保留。
- `PENDING_RELEASE_BLOCKER`、真实 `windows-latest/cmd.exe` 与 artifact oracle 均保留；未把 Windows pending 转 residual。
- security、deferred、no-touch、Service/storage/runtime/FMP/ticker/design/constraints/Controller no-diff、no-push/PR/R12 边界
  均保留。
- 第二 packaging slice 未增加任何路径、能力、tracker、dependency cleanup 或产品行为。

## 6. Rejected alternatives / adversarial review

以下 Controller rejected alternatives 未进入正向实施路径，只在 plan 的禁止规则中出现：

- 未保留 `UploadBatchPlanEntry/Result`、`entries/command_name/files` compatibility surface；
- 未加入 CLI loose parsing、fallback、`hasattr/getattr`、dual reader 或 downstream repair；
- 未跳过、推迟或放宽 combined full pyright/test/coverage/Ruff/scans；
- 未把 transient broken tree 定义为 checkpoint/validation/handoff state；
- 未修改 Service/storage/runtime、增加跨层 adapter、创建新 sub-WU 或扩大 packaging scope；
- 未增加 work-package/slice commit、提前 code review、stage、push 或 PR。

Architecture boundary、best-practice、optimal-solution、overengineering 与 overcoupling lenses 的复核结论：atomic cutover 是
能够同时保持唯一 semantic owner、strict typing、可验证 tree 与 no-compat 的最窄修复；没有更小的合法 checkpoint 方案，
也没有理由扩大产品或 packaging scope。Open questions：0；新 accepted-candidate finding：0；actual residual：0。

## 7. Workspace、diff 与 validation truth

开始时 workspace：

```text
 M docs/host/issues-implementation-control.md
?? docs/reviews/wu-semantic-ownership-01-r11-s1-checkpoint-stop-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-s1-controller-authorization.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-s1-implementation-codex.md
```

上述 Controller-owned dirty/untracked paths 均保持存在；本 Agent 未覆盖、删除、stage 或提交。Agent-owned write manifest 精确为：

```text
docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md
docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-boundary-fix-codex.md
```

完成后 `git status --short`：

```text
 M docs/host/issues-implementation-control.md
 M docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md
?? docs/reviews/wu-semantic-ownership-01-r11-s1-checkpoint-stop-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-boundary-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-s1-controller-authorization.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-s1-implementation-codex.md
```

完整 tracked `git diff --name-only` 仅比开始状态新增 plan；其中
`docs/host/issues-implementation-control.md` 是用户明示的既有 Controller-owned dirty diff。排除该 no-touch path 后，tracked
diff 精确只有 plan；evidence 是唯一新增 Agent-owned untracked path。三个既有 Controller/auth/stop evidence untracked paths
保持原样。Controller control 的 final SHA-256 为
`fc548a13e32744b8e190210342635d61fb7f6ecf5e38f777bfd880aae7b274b5`。

- product/test/README/design/CI diff：empty；因此按显式 plan-only 授权未运行 product tests、coverage、pyright 或 Ruff。
- staged tree：empty。
- `git diff --check`：PASS。
- 未 stage、commit、push、创建 PR 或进入 implementation/R12。
- final gate：完整 amended plan 等待 Controller complete read 与双路 complete re-review，不得只审 delta。

READY_FOR_CONTROLLER_PLAN_BOUNDARY_FIX_VALIDATION
