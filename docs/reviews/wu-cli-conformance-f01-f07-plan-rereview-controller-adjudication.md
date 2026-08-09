# WU-CLI-CONFORMANCE-F01-F07 Plan Re-review 总控裁决

## 0. Gate 元数据

- Gate：`plan re-review -> fix`
- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Reviewed plan：`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
- Plan-fix artifact：`docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`
- Re-review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-ds.md`
- 既有 PR：`190`
- 第一轮裁决结论：`FAIL — 原 18 项 accepted findings 已修复，但 2 个新 finding 必须先修计划`
- 第二轮终态：`PASS — 见 §6；允许创建 accepted plan commit`
- 当前允许动作：仅按 §6.4 的十条精确路径创建 accepted plan commit；不得混入 implementation、README 或其它文件，不得 push 或操作 PR。

## 1. 原 accepted findings 的逐项裁决

总控不以两路 reviewer 的 PASS 结论代替证据。对照首轮总控裁决、修订计划、直接代码和冻结设计后，状态如下：

| 来源 | Finding | 状态 | 总控证据摘要 |
|---|---|---|---|
| MiMo | M-F1 | `已修复` | S1 已使用真实 `tests/cli/test_session_command.py`，并补全 typed construction-site inventory。 |
| MiMo | M-F2 | `已修复` | S4 owner test 已固定为 `tests/host/test_session_attachment_registry.py`。 |
| MiMo | M-F3 | `已修复` | S6/S7 已提供 old active symbol/literal 到 fresh contract 的机械映射、传播闭包和零残留扫描。 |
| MiMo | M-F4 | `已修复` | S7 保持一个 outer slice/commit，并增加 schema、accept、repair、projection/multi-pass 四个内部 checkpoint。 |
| MiMo | M-F7 | `已修复` | S2 已固定 public prompt_toolkit seam、explicit CLI-owned tempfile round trip 和四分 outcome。 |
| MiMo | M-O1 | `已修复` | provider 不可用时 S8 保持 `BLOCKED-ON-REAL-EVIDENCE`，恢复后使用新 run id。 |
| MiMo | M-O2 | `已修复` | `MemoryProjectionPolicy` 与 `estimate_memory_size_units()` owner 已固定为 `dayu/host/memory.py`。 |
| DeepSeek | DS-B1 | `已修复` | parser 只在 reader thread 创建/调用；同线程 feed/deadline/flush；callback 只经 `loop.call_soon_threadsafe` 投递 typed action。 |
| DeepSeek | DS-B2 | `已修复` | accepted plan commit 明确纳入两个 frozen registry 原字节，并在 S1–S8 前清理 dirty baseline。文件名错配属于本轮新增 finding，不使原 disposition 失效。 |
| DeepSeek | DS-B3 | `已修复` | unset 与 explicit editor 路径、public API、exact argv、nonzero/OSError/readback outcome 已收口。 |
| DeepSeek | DS-B4 | `已修复` | prompt/interactive accepted state、cancel sites 和 shared coordinator 已逐点映射。 |
| DeepSeek | DS-B5 | `已修复` | S7 内部 checkpoint 已列 focused tests/pyright，且明确禁止 stash、新分支、中间 stage/commit。 |
| DeepSeek | DS-B7 | `已修复` | editor、Memory policy owner 已收口；provider 仅保留 operational stop。 |
| Controller | C1 | `已修复` | §9.6 保留 `CompactPipelinePassQueuePlan`/`build_reactive_pass_queue_plan`；每 pass whole-candidate repair，全部 pass 后 root coverage/duplicate/caps/budget 重验；中间 truth 不 durable。 |
| Controller | C2 | `已修复` | F02 已区分 missing/nonexec/spawn `OSError`、nonzero silent cancel、zero update、unset fallback。 |
| Controller | C3 | `已修复` | S1 已补全 controller 指定的 CLI/Service tests 与 typed construction sites。 |
| Controller | C4 | `已修复` | accepted truth 先由 terminal owner 提交 artifact/event；Memory 只消费 committed `CONTEXT_COMPACTED` strict semantic projection。 |
| Controller | C5 | `已修复` | stale Phase A/B 与提前 code-generation-ready 声明已删除；fix 后入口已改为 re-review。 |

被首轮总控拒绝的 M-F5、M-F6、DS-B6 未被复活；fresh schema/no compatibility、最小 shared closeout owner、service README 不更新的裁决保持不变。

## 2. Re-review 新 findings 裁决

### R1-accepted-低：prompt_toolkit 版本事实写错且影响 stop contract

MiMo NEW-1/NF1 与 DeepSeek NEW-1 指向同一直接事实：

- `pyproject.toml` 声明 `prompt_toolkit>=3.0.0`；当前 `.venv` 恰好安装 `3.0.52`。
- Plan §4.2 却写“当前锁定依赖是 `prompt_toolkit==3.0.52`”，§4.2、§4.5、§14.1 又以“锁定依赖/锁定版本/锁定 3.0.52”定义 readback、stop signal 和风险收敛。

裁决为 `accepted`。这不是要求 pin 依赖，也不能无证据宣称全部未来 `>=3.0.0` 版本行为完全相同。Plan fix 必须：

1. 精确区分“当前验证环境安装 3.0.52”和“项目声明范围 `>=3.0.0`”。
2. 方案只依赖 prompt_toolkit 的 public import/API，不依赖 3.0.52 私有实现或精确版本锁。
3. 把“按锁定依赖去除末尾换行”改为 frozen editor success behavior 的 CLI owner 规则；不要把产品语义归给偶然依赖版本。
4. stop signal 改为：若当前 resolved dependency 的 public seam 与已核验证据不符，停止回到 plan；不得 private fallback、monkey patch 或擅自 pin。
5. 不修改 `pyproject.toml`，不新增 dependency compatibility layer。

### R2-accepted-高：accepted-plan staged set 引用了错误的 re-review artifact 名称

Plan §13.2 与 plan-fix artifact 使用：

- `...-plan-re-review-mimo.md`
- `...-plan-re-review-ds.md`
- `...-plan-re-review-controller-adjudication.md`

本 Gate 实际 durable artifact 与总控 artifact 使用：

- `...-plan-rereview-mimo.md`
- `...-plan-rereview-ds.md`
- `...-plan-rereview-controller-adjudication.md`

因此当前“十条显式路径”及 `git add -- ...` 命令会引用不存在文件，无法满足 DS-B2 的 completion signal。裁决为 `accepted`。Plan 与 plan-fix artifact 必须统一改为本 Gate 已实际生成的三个 `plan-rereview-*` 路径，并重新验证：

- 十条路径全部存在；
- staged-set 计数仍为 10；
- 两个 registry working-tree/index digest 保持固定值；
- 当前 fix/re-review 阶段仍不 stage。

## 3. Review artifact 自洽性校正

两路 reviewer 已在同一 re-review gate 内修正 durable artifact：

- MiMo 将错误的 `12/12` 修为 `18/18`，并把 NEW-1/NF1 统一标为“未修复、低、非 blocking、待总控裁决”。
- DeepSeek 将“无 new finding”与 NEW-1 的矛盾改为“原 18 项已修复；NEW-1 未修复、低、非 blocking、待总控裁决”。
- 两路下一入口均已改为 controller adjudication，不再越过 plan-fix 决策。

这些是 review artifact 的事实一致性校正，不改变原 18 项 finding 的 `已修复` 状态。

## 4. Required second plan-fix completion signal

1. 只修改 `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md` 与 `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`。
2. 修复 R1 的全部四处版本/owner/stop-risk措辞；不 pin、不改 dependency。
3. 修复 R2 的三条 artifact 路径及完整 `git add --` 示例；十条 staged paths 全部真实存在。
4. plan-fix artifact 追加本轮 R1/R2 的修复记录和直接校验结果，不覆盖首轮记录。
5. 两个 frozen registry SHA-256 保持：
   - `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
   - `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
6. `git diff --check`、两个 `json.tool`、十路径存在性检查通过，index 为空。
7. 完成后停在第二轮独立 plan re-review；不得实施、stage、commit、push 或操作 PR。

## 5. Residual risk disposition

- prompt_toolkit public terminal/editor behavior：`covered by S2 owner tests + S8 real PTY evidence`。
- reactive multi-pass aggregate closure：`covered by S7 checkpoints + aggregate-root tests`。
- provider availability：`operational; S8 remains open until full-real evidence succeeds`。
- 当前没有未分类的产品 blocker；R1/R2 都是计划事实/流程闭环问题，修复不改变 frozen oracle 或设计语义。

## 6. 第二轮独立 Plan Re-review 终态裁决

### 6.1 第二次 fix 与 re-review 输入

- AgentCodex 只修改了：
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`
- MiMo 与 DeepSeek 分别在原 durable artifact 末尾追加“第二轮 Re-review”结论，没有新建替代 artifact。
- 两路都逐项验证 R1/R2，并对原 18 项 finding 做 regression scan；两路结论均为 PASS，但总控仍逐项回到直接文件证据裁决。

### 6.2 R1/R2 最终状态

| Finding | 最终状态 | 总控直接证据 |
|---|---|---|
| R1 prompt_toolkit 版本事实/owner/stop contract | `已修复` | Plan §4.2 已区分当前环境 `3.0.52` 与 `pyproject.toml` 声明 `>=3.0.0`；方案只依赖 public API，不把环境版本当 pin；成功 readback 的末尾换行规则归 CLI frozen behavior；§4.5/§14.1 已删除“锁定版本”并规定 public seam 不符即回 plan，禁止 private fallback、monkey patch、兼容层或擅自 pin。 |
| R2 re-review artifact 路径与 exact staged set | `已修复` | Plan §13.2、完整 `git add --` 示例及 plan-fix artifact 已统一为实际存在的三条 `plan-rereview-*` 路径；显式集合与命令均为 10 条，逐条存在。 |

### 6.3 回归与新 finding 裁决

- 原 18 项 `accepted` / `accepted-in-part` finding 保持 `已修复`，第二次 fix 只改变 R1/R2 涉及的事实措辞和 artifact 路径，没有退化 owner contract、slice allowlist、multi-pass、Memory 投影或 registry disposition。
- M-F5、M-F6、DS-B6 保持 `rejected-with-reason`，未被复活。
- MiMo/DeepSeek 第二轮均报告无新 finding；总控对 dependency、editor、parser、registry staged set、S7 multi-pass/Memory 链和 gate metadata做定向复核后，也未发现新 finding。
- R1/R2 均已收口；当前没有未分类 blocker。

### 6.4 Accepted Plan Gate completion signal

Plan Re-review Gate 最终裁决为 `PASS`。下一步只允许创建一个 accepted plan commit，精确包含以下 10 条路径：

1. `docs/cli_ci_oracles.json`
2. `docs/cli_ci_scenarios.json`
3. `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
4. `docs/reviews/wu-cli-conformance-f01-f07-plan-review-mimo.md`
5. `docs/reviews/wu-cli-conformance-f01-f07-plan-review-ds.md`
6. `docs/reviews/wu-cli-conformance-f01-f07-plan-review-controller-adjudication.md`
7. `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`
8. `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-mimo.md`
9. `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-ds.md`
10. `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md`

提交前后必须满足：

- 两个 registry working-tree 与 index blob SHA-256 分别为冻结值；
- `git diff --cached --name-only` 与上述集合完全一致；
- `git diff --cached --check`、两个 `json.tool` 通过；
- 不包含生产代码、tests、README、design 或其它文件；
- commit message：`gateflow: accept plan for WU-CLI-CONFORMANCE-F01-F07`；
- 本 gate 只创建 local commit，不 push；commit 完成后才可进入 S1 implementation gate。
