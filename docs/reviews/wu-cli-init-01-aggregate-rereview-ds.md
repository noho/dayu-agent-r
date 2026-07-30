# WU-CLI-INIT-01 Aggregate Deepreview Fix Re-Review — DS

## Re-review metadata

- **Work unit**: `WU-CLI-INIT-01`
- **Gate**: `aggregate deepreview fix re-review`
- **Reviewer**: AgentDS（Claude Code / DeepSeek）
- **日期**: 2026-07-30
- **输入**:
  - `docs/reviews/wu-cli-init-01-aggregate-deepreview-ds.md`（DS 原始 aggregate review，4 findings）
  - `docs/reviews/wu-cli-init-01-aggregate-deepreview-mimo.md`（MiMo 独立 aggregate review，3 informational findings）
  - `docs/reviews/wu-cli-init-01-aggregate-fix-codex.md`（Codex fix artifact，Controller 裁决 + 变更）
  - `docs/host/ui-implementation-control.md`（uncommitted fix diff）
- **审查聚焦**:
  1. Controller 对 F1/F3/F4 的 reject 是否有直接证据
  2. F2 accept 是否在正确 owner 以最小方式关闭
  3. 历史 gate 是否被改写
  4. current contract 是否清晰
  5. 无 scope 扩散

## Verdict

**PASS** — Controller 四项裁决均有直接、可复现证据。F2 fix 在正确 owner、最小方式、保留历史 gate。两份 aggregate review 的 PASS 判定一致且无冲突。无 scope 扩散。无新 finding。

---

## 1. Controller 裁决逐项验证

### 1.1 F1：`docs/cli_ci.md` 方法论变更 scope boundary 模糊 → **reject**

**Controller 理由**: `933908a8` 是用户明确要求在 Gateflow 前提交的独立 commit（`docs: record CLI calibration workflow and init oracle`），只修改 `docs/cli_ci.md` 与 `docs/cli_ci_oracles.json`；WU 本身的 cli_ci.md 变更仅限于对该 handbook 的 oracle 相关增补。

**直接证据复核**:

| 检查项 | 结果 | 命令/证据 |
|--------|------|-----------|
| `933908a8` commit 存在且独立 | ✅ | `git show 933908a8 --stat`: `docs: record CLI calibration workflow and init oracle`，`docs/cli_ci.md`（791+ 行），`docs/cli_ci_oracles.json`（217+ 行） |
| `3bfbd7f9` 是 merge base（不是 `933908a8` 的后代） | ✅ | `git merge-base 3bfbd7f9 933908a8` → `3bfbd7f9`；`3bfbd7f9` 是 `feat: add Tool Trace analyzer (#186)`，独立于本 WU 分支 |
| Goal Confirmation Preflight 记录独立提交 | ✅ | Goal Confirmation §Preflight: "修复前 handbook 与 init oracle 已由用户明确要求提交为 933908a8" |
| WU-only `docs/cli_ci.md` 变更量 | ✅ | `git diff 933908a8..ae907b26 -- docs/cli_ci.md` → 仅 31 insertions（仅新增 15-choice smoke 命令用法段落） |
| 原始 DS review 的 820 行统计误因 | ✅ 已定位 | `git diff 3bfbd7f9..ae907b26` 包含了 `933908a8` 的 791+ 行独立变更（因为 `3bfbd7f9` 是 merge base，在 `933908a8` 之前） |

**复核结论**: Controller reject 有完整直接证据。原始 DS F1 的 820 行统计基于对 diff range 的错误解读——`3bfbd7f9` 是 merge base，不在 WU 分支的祖先链中，因此 diff 包含了独立 commit `933908a8` 的 handbook 变更。WU 实际只贡献了 31 行 oracle smoke 命令文档。

### 1.2 F2：`docs/host/ui-implementation-control.md` 仍引用 `--model-name` → **accept**

**Controller 裁决**: 在控制文档"真源层级"后新增当前 CLI 契约提示，不重写历史 gate。

**Fix 复核**:

| 检查项 | 结果 | 证据 |
|--------|------|------|
| Owner 正确 | ✅ | 新增提示位于 `docs/host/ui-implementation-control.md` 第 47 行，紧接"真源层级"框图之后、"本文档不得引入新的架构边界"声明之前——这是该文档的当前契约区域，owner 正确 |
| 最小方式 | ✅ | 仅 1 个 blockquote（2 句）："当前 CLI 契约：公开模型覆盖参数已冻结为 `--model/-m`，旧参数 `--model-name` 不存在；下文历史 gate 中的 `--model-name` 仅是当时记录，不代表当前公开参数。" |
| 历史 gate 保留 | ✅ | 3 处原始 `--model-name` 引用（第 414、431、468 行）完整保留，均位于 WU-CLI-01 各 gate 描述段落中（S1 implementation、S1 review 通过项、S4 review 通过项） |
| Current contract 清晰 | ✅ | 提示同时声明：当前参数（`--model/-m`）、旧参数不存在、历史 gate 仅为记录 |
| 不引入新机制 | ✅ | 不修改文档结构、gate 记录、术语或架构边界 |
| 不扩散 | ✅ | 仅 1 个文件、2 行新增；无生产代码、测试、README、oracle 或 review artifact 修改 |

**复核结论**: F2 fix 在正确 owner、最小方式、保留全部历史 gate。current contract 清晰无歧义。

### 1.3 F3：CLI 常量与 ConfigLoader 文件名重复 → **reject**

**Controller 理由**: `_EXECUTION_PROFILES_FILE_NAME` 只定位单个 workspace 文件做 no-follow shape guard；publication 路径仍调用 `config_file_names()` 枚举完整配置目录。上游单文件 shape guard 没有接管 publication catalog ownership。

**直接证据复核**:

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `_EXECUTION_PROFILES_FILE_NAME` 仅用于 shape guard | ✅ | `init.py:74` 定义，仅在 `init.py:478` `_workspace_execution_profile_is_regular_file` 中使用——该函数用 `os.stat(follow_symlinks=False)` 做单文件 no-follow 分类 |
| Publication 路径使用 canonical owner | ✅ | `init_workspace.py:904,938` 两处调用 `config_file_names()`（import 自 `dayu.runtime.config_loader`）枚举完整 managed root 配置 |
| 两个常量服务不同语义 | ✅ | shape guard：单文件存在性/类型判定；publication catalog：完整受管文件枚举。未发生 ownership 冲突 |
| S2 adjudication 已将此 deferred | ✅ | S2 code review adjudication: "重复配置文件名 residual：covered by later approved slice（S4）"；S4 scope correction 窄化为 managed-tree modes 后未覆盖 ConfigLoader 重构，但两处用法路径已自然分离 |

**复核结论**: Controller reject 有直接代码证据。`_EXECUTION_PROFILES_FILE_NAME` 与 `config_file_names()` 服务不同语义目的，不存在 ownership takeover 或漂移风险。

### 1.4 F4：`authority_basis` 指向旧仓库路径 → **reject**

**Controller 理由**: `docs/cli_ci_oracles.json` 将该条目明确标为 `reference-observation`，说明旧版 overwrite/reset 行为仅作为目录迁移后语义参考；指向用户指定的旧仓库路径符合字段语义。

**直接证据复核**:

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 条目 kind 为 `reference-observation` | ✅ | `cli_ci_oracles.json:192`: `"kind": "reference-observation"` |
| Summary 明确说明语义 | ✅ | `cli_ci_oracles.json:193-194`: "旧版 overwrite/reset 的业务行为作为目录迁移后的语义参考" |
| 旧路径是语义正确的引用 | ✅ | `reference-observation` 的语义是"我们从哪里观察到的参考行为"——指向旧仓库（`dayu-agent`）作为观察源是该字段类型的正确用法 |
| 不是 binding normative reference | ✅ | 该条目的 `kind` 为 `reference-observation`（非 `user-decision`），不构成 normative contract |

**复核结论**: Controller reject 有直接证据。`reference-observation` 条目指向旧仓库作为语义参考源是字段语义的正确使用。

---

## 2. 两份 Aggregate Review 交叉验证

| 维度 | DS review | MiMo review | 一致性 |
|------|-----------|-------------|--------|
| Correctness（8 项目标） | ✅ PASS | ✅ PASS | ✅ 一致 |
| Semantic owner | ✅ PASS | ✅ PASS | ✅ 一致 |
| Cross-slice combination | ✅ PASS | ✅ PASS | ✅ 一致 |
| Scope creep | ✅ PASS（含 F1 已被 reject） | ✅ PASS | ✅ Controller 裁决后一致 |
| Stale contract | ✅ PASS（含 F2 已 fix） | ✅ PASS（F-01/F-02 informational） | ✅ 一致 |
| 15-provider no-fallback | ✅ PASS | ✅ PASS | ✅ 一致 |
| README/oracle JSON | ✅ PASS | ✅ PASS | ✅ 一致 |
| pyright/test | ✅ PASS | ✅ PASS | ✅ 一致 |
| 最终 verdict | PASS | PASS | ✅ 一致 |

**MiMo 的 3 项 informational findings**（F-01: compactor scene_model_hints 描述过时、F-02: Custom context window 描述过时、F-03: `_confirm` 空输入语义 nuance）均为 Goal Confirmation 历史快照与当前代码的非功能性差异，MiMo 已明确建议"无需修改"，Controller 在 fix artifact 中确认"本 gate 同样不回写这些历史记录"。与 DS 的 F1/F3/F4 reject 逻辑一致。

---

## 3. 历史 Gate 完整性验证

| 检查项 | 结果 |
|--------|------|
| `docs/host/ui-implementation-control.md` 中 WU-CLI-01 gate 章节完整 | ✅ 第 286-357 行保留 CLI-01-S1 到 CLI-01-S7 的所有 implementation/review/fix/re-review gate 记录 |
| 3 处 `--model-name` 引用原样保留 | ✅ 第 414 行（S1 implementation gate）、第 431 行（S1 review 通过项）、第 468 行（S4 review 通过项）——均为历史 gate 中的 accepted plan 描述 |
| 新增提示不改写历史 | ✅ 提示文字明确："下文历史 gate 中的 `--model-name` 仅是当时记录，不代表当前公开参数" |
| 无 gate 记录被删除、修改或重排 | ✅ `git diff` 仅显示第 47 行新增 blockquote；全文其它行无变更 |

---

## 4. Scope 扩散检查

| 检查项 | 结果 |
|--------|------|
| Fix 变更文件数 | ✅ 1 个：`docs/host/ui-implementation-control.md` |
| Fix 变更行数 | ✅ 2 行（1 个 blockquote） |
| 生产代码变更 | ✅ 0 |
| 测试变更 | ✅ 0 |
| README/oracle 变更 | ✅ 0 |
| Review artifact 变更 | ✅ 仅新增 `wu-cli-init-01-aggregate-fix-codex.md`（Gateflow artifact） |
| 未触及 approved scope 外的文件 | ✅ `docs/host/ui-implementation-control.md` 的 current contract 区域是该文档的当前契约声明位置，owner 正确 |

---

## 5. 残余 Findings

**无新 finding。** 原 DS review 的 4 项 findings 处置如下：

| Finding | 严重度 | 处置 | 状态 |
|---------|--------|------|------|
| F1: cli_ci.md scope boundary | 中 | Controller reject（独立 commit + WU 仅 31 行） | ✅ 已关闭 |
| F2: stale --model-name | 低 | Controller accept → Codex fix（当前契约提示） | ✅ 已修复 |
| F3: 常量重复 | 低 | Controller reject（不同语义目的） | ✅ 已关闭 |
| F4: 旧仓库路径 | 低 | Controller reject（reference-observation 字段语义） | ✅ 已关闭 |

原 MiMo review 的 3 项 informational findings 无需修改，不在 fix scope 内。

---

## 6. Completion

- **Re-review verdict**: **PASS**
- **Controller 裁决验证**: 4/4 项均有直接可复现证据
- **F2 fix 验证**: owner 正确、最小方式、历史 gate 完整、current contract 清晰
- **两份 aggregate review 一致性**: 无冲突，均 PASS
- **Scope 扩散**: 无
- **新 finding**: 0
- **未关闭 finding**: 0
