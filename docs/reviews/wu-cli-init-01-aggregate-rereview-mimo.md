# WU-CLI-INIT-01 Aggregate Deepreview Re-Review — MiMo

## 审查范围

- **Gate**：aggregate deepreview re-review
- **输入文档**：
  - `docs/reviews/wu-cli-init-01-aggregate-deepreview-mimo.md`（MiMo aggregate review）
  - `docs/reviews/wu-cli-init-01-aggregate-deepreview-ds.md`（DS aggregate review）
  - `docs/reviews/wu-cli-init-01-aggregate-fix-codex.md`（Controller fix 裁决 + Codex 修复）
  - `docs/host/ui-implementation-control.md`（实施总控文档，已含当前契约提示）
  - `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`（Goal Confirmation）
- **审查者**：AgentMiMo（Claude Code / MiMo）
- **审查日期**：2026-07-30

## 审查任务

1. 验证 Controller 对 DS F1/F3/F4 reject 的证据
2. 验证 DS F2 accept 的 owner 修复
3. 确认历史 gate 未被改写
4. 确认 current contract 清晰
5. 确认无 scope 扩散
6. 核对 MiMo 与 DS 两份 aggregate review 的一致性

---

## 1. Controller 裁决验证

### DS F1：`docs/cli_ci.md` 方法论变更 scope boundary 模糊 — **reject ✅**

| 验证项 | 直接证据 | 判定 |
|---|---|---|
| `933908a8` 提交范围 | `git show --stat 933908a8` → 只修改 `docs/cli_ci.md`（+791）和 `docs/cli_ci_oracles.json`（+217） | ✅ |
| Goal Confirmation Preflight 声明 | 第 18-19 行："修复前 handbook 与 init oracle 已由用户明确要求提交为 `933908a8`" | ✅ |
| 独立提交性质 | commit message: `docs: record CLI calibration workflow and init oracle`，不涉及 WU-CLI-INIT-01 代码 | ✅ |

**结论**：该 handbook 提交是用户在 WU-CLI-INIT-01 启动前明确要求的独立任务，不是本 work unit 的 scope creep。Controller reject 理由充分。

### DS F2：控制文档仍出现 `--model-name` — **accept + owner 修复 ✅**

| 验证项 | 直接证据 | 判定 |
|---|---|---|
| 代码真源 | `arg_parsing.py:715` 只注册 `--model, -m`；无 `--model-name` | ✅ |
| 负向测试 | `tests/cli/test_arg_parsing.py` 验证 help 不含 `--model-name` 且 parser 拒绝 | ✅ |
| 历史 gate 命中位置 | `ui-implementation-control.md` 第 414、431、468 行，均在 WU-CLI-01 S3/S4 历史 review gate 内 | ✅ |
| 当前契约提示 | 第 47 行新增 blockquote："公开模型覆盖参数已冻结为 `--model/-m`，旧参数 `--model-name` 不存在；下文历史 gate 中的 `--model-name` 仅是当时记录，不代表当前公开参数。" | ✅ |
| 历史记录未被改写 | 第 414、431、468 行文本与原始 S3/S4 gate 记录一致 | ✅ |

**结论**：Fix 正确地在"真源层级"后的显眼位置新增当前契约提示，同时保留历史 gate 原文。Owner 是控制文档的当前契约区域，不是历史 gate 记录。修复方式正确。

### DS F3：CLI 常量与 ConfigLoader 文件名重复 — **reject ✅**

| 验证项 | 直接证据 | 判定 |
|---|---|---|
| `_EXECUTION_PROFILES_FILE_NAME` 用途 | `init.py:74` 定义，`init.py:478` 用于 `_workspace_execution_profile_is_regular_file` 的 no-follow shape guard | ✅ |
| `config_file_names()` 用途 | `init_workspace.py:904,938` 用于完整 publication catalog 枚举 | ✅ |
| 职责差异 | shape guard（单文件分类）vs catalog enumeration（全量 publication）— 不同职责 | ✅ |

**结论**：shape guard 不接管 publication catalog ownership，不存在语义重复。Controller reject 理由充分。

### DS F4：`authority_basis` 指向旧仓库路径 — **reject ✅**

| 验证项 | 直接证据 | 判定 |
|---|---|---|
| 字段 kind | `cli_ci_oracles.json:192` `"kind": "reference-observation"` | ✅ |
| 字段语义 | summary: "旧版 overwrite/reset 的业务行为作为目录迁移后的语义参考" | ✅ |
| 路径指向 | `/Users/leo/workspace/dayu-agent/README.md#13-初始化工作区与配置` — 用户指定的 OLD repo | ✅ |

**结论**：`reference-observation` 类型的 `authority_basis` 指向旧仓库作为语义参考，符合字段定义。Controller reject 理由充分。

---

## 2. 历史 Gate 改写检查

| 检查项 | 结果 |
|---|---|
| `ui-implementation-control.md` 第 414 行（S3 gate） | 文本与原始 S3 review gate 一致，未被改写 ✅ |
| `ui-implementation-control.md` 第 431 行（S3 gate） | 文本与原始 S3 review gate 一致，未被改写 ✅ |
| `ui-implementation-control.md` 第 468 行（S4 gate） | 文本与原始 S4 review gate 一致，未被改写 ✅ |
| WU-CLI-01 全部 S1-S7 gate 记录 | 未被触碰 ✅ |
| Goal Confirmation 原文 | 未被改写 ✅ |
| Oracle JSON 原文 | 未被改写 ✅ |

**结论**：所有历史 gate 记录保持原样。新增的当前契约提示是 blockquote 格式，与历史记录视觉区分明显。

---

## 3. Current Contract 清晰度

`ui-implementation-control.md:47` 的当前契约提示：

> **当前 CLI 契约：**公开模型覆盖参数已冻结为 `--model/-m`，旧参数 `--model-name` 不存在；下文历史 gate 中的 `--model-name` 仅是当时记录，不代表当前公开参数。

| 清晰度检查 | 判定 |
|---|---|
| 声明了当前参数是什么 | ✅ `--model/-m` |
| 声明了旧参数不存在 | ✅ `--model-name` 不存在 |
| 解释了历史记录为何保留 | ✅ "仅是当时记录" |
| 与代码真源一致 | ✅ `arg_parsing.py:715` |
| 与 README 一致 | ✅ `README.md:200-204` |
| 与 oracle 一致 | ✅ `cli_ci_oracles.json` predicates |

**结论**：当前契约提示清晰、自足、与所有真源一致。

---

## 4. Scope 扩散检查

| 检查项 | 结果 |
|---|---|
| Fix 修改了生产代码？ | 否 ✅ |
| Fix 修改了测试？ | 否 ✅ |
| Fix 修改了 README / oracle？ | 否 ✅ |
| Fix 修改了历史 gate？ | 否 ✅ |
| Fix 修改了其它 review artifact？ | 否 ✅ |
| 变更范围 | 仅 `ui-implementation-control.md`（+1 行 blockquote）+ `aggregate-fix-codex.md`（新文件） |

**结论**：无 scope 扩散。

---

## 5. MiMo 与 DS Aggregate Review 一致性核对

| 维度 | MiMo 判定 | DS 判定 | 一致 |
|---|---|---|---|
| Correctness | PASS | PASS | ✅ |
| Semantic owner | PASS | PASS | ✅ |
| Cross-slice defects | PASS | PASS | ✅ |
| Scope creep | PASS | PASS | ✅ |
| Stale contract | PASS（3 informational） | PASS | ✅ |
| 15-provider no-fallback | PASS | PASS | ✅ |
| README/oracle consistency | PASS | PASS | ✅ |
| pyright/test/whitespace | PASS | PASS | ✅ |
| 总判定 | PASS | PASS | ✅ |

**细节差异**（non-blocking）：
- MiMo 报告 smoke test 为 4413 行；DS 报告为 4115 行。实际 `wc -l` 结果为 4413。差异不影响判定，可能是 DS 在审查时计数方式不同。
- DS 额外识别了 `_EXECUTION_PROFILES_FILE_NAME` 常量重复（F3），MiMo 未单独列出但已在 semantic owner 检查中隐式覆盖。
- DS 的 8 个目标逐条验证与 MiMo 的 oracle predicate 逐项比对是互补视角，结论一致。

**结论**：两份 aggregate review 核心判定完全一致，差异仅在非阻塞性细节层面。

---

## 6. Fix Artifact 质量检查

`docs/reviews/wu-cli-init-01-aggregate-fix-codex.md` 检查：

| 检查项 | 判定 |
|---|---|
| 四项 finding 均有裁决和直接证据 | ✅ |
| F2 的修复方式正确（新增当前契约提示，不改历史） | ✅ |
| F1/F3/F4 的 reject 理由充分 | ✅ |
| 声明未修改生产代码、测试或历史 gate | ✅ |
| 验证方法与文档-only 变更风险相称 | ✅ |
| 残余风险与停止条件明确 | ✅ |

---

## 最终判定

# **PASS**

全部审查任务通过：

1. ✅ Controller 对 DS F1/F3/F4 reject 的证据充分、直接
2. ✅ DS F2 accept 的 owner 修复正确（当前契约提示 + 历史保留）
3. ✅ 历史 gate 未被改写
4. ✅ current contract 清晰且与所有真源一致
5. ✅ 无 scope 扩散
6. ✅ MiMo 与 DS 两份 aggregate review 核心判定一致

### 残余风险

无新增残余风险。Fix 只处理 Controller 接受的 DS F2；DS F1/F3/F4 按 Controller 理由 reject。MiMo aggregate review 的 3 个 Informational findings 均为历史文档描述差异，不在本 gate 处理范围。
