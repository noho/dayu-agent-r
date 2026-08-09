# PR 190 F17 Goal Confirmation

- 确认时间：2026-08-07 14:22:09 +0800
- 分支：`codex/interactive-oracle`
- 基线 HEAD：`e1217811ad57e48c90e3763994930e53378ba060`
- 设计入口：`docs/cli_ci.md`
- 目标 PR：draft PR 190（复用，不新建、不改变 readiness）

## Preflight

- 工作树 clean，无 unresolved merge entry 或进行中的 merge。
- 当前分支为 `codex/interactive-oracle`，上游同名；本地 `main` 与 `github/main` 均为
  `113ea34d47b95812d79aa31705949bbb46bc6061`，可 fast-forward 且没有 rebase 需求。
- PR 190 为 `OPEN`、`DRAFT`、`CLEAN`，base 为 `main`，head 与上述基线 HEAD 一致；没有
  review request 或已提交 review。

## 动机与直接证据

问题成立。通过 production `InitMode.FIRST`、production file lock、workspace transaction
owner 在 fresh 临时 workspace 发布完整树，再由严格 `validate_publication_tree` 独立枚举，得到：

- manifest inventory：5 directories / 43 files / 16 model pointers；
- actual inventory：5 directories / 43 files / 16 model pointers；
- 完整差异仅为
  `file_digest_mismatch:config/prompts/scenes/conversation_compaction_user.md`；
- actual prompt SHA-256：
  `22e7bc5015cb369ff228a754b557493594b8313c99877944b5a7c08da0dc1c88`；
- manifest 中旧值：
  `59b50e13ea636c434fcabe26adf6d9ed22665dfcba03533ebcf5e9b524b87b76`；
- manifest 当前 raw SHA-256：
  `d95de68e69b0aacc712ec6bf468c8604a91460a17f3e2497f397182517a6a9f8`。

因此 F17 不是 pytest 偶发失败，也不是可忽略的历史债务，而是 prompt bytes 已变更后冻结
publication 派生链未同步的确定性错误。

## 语义 owner 与唯一派生链

1. `dayu/config/prompts/scenes/conversation_compaction_user.md` 的原始 bytes 是当前
   LLM-facing 业务内容真源；F17 不修改它。
2. `dayu.cli.init_workspace` 的 production transaction 是 workspace publication 行为 owner；
   它原样发布当前 package asset，并没有行为错误。
3. `docs/cli_init_workspace_manifest_v1.json` 是用户已冻结的 publication truth consumer，精确
   承诺当前 5/43/16 tree 及每个 asset digest。
4. `FROZEN_MANIFEST_SHA256` 只钉住 manifest 原始 bytes；它是 manifest 的二级派生 consumer，
   不是另一套 publication 真源。

正确修复边界是只同步 manifest 中该 asset entry，再从保存后的 manifest 原始 bytes 计算并同步
测试常量。不得倒改 prompt、动态生成 expected、放宽 validator 或添加兼容分支。

## Goal

- 使 prompt raw digest、manifest asset entry、manifest raw digest 与测试 digest pin 严格闭合。
- 保持 production publication inventory 精确为 5 directories / 43 files / 16 model pointers。
- 使 `tests/cli/test_smoke_cli_init_provider_matrix.py` 全部 71 个 owner tests 通过。
- 证明 fresh production tree 不存在第二个 path、digest 或 model-pointer mismatch。

## 非目标

- 不修改 prompt 内容、init/prompt/interactive 产品行为或 validation 逻辑。
- 不修改目录、文件名、model projection owner、Host/Engine schema 或 public contract。
- 不修改 accepted Oracle、formal scenario registry 或 readiness adjudication；三条 replacement
  scenarios 继续为 `unadjudicated`。
- 不创建新 PR，不 merge、不 mark ready、不 approve/request reviewers，不 rebase/force-push，
  不删除分支。

## 验收与风险边界

- strict fresh production publication validation：无 issues，counts 为 5/43/16；
- prompt digest 等于 manifest entry；manifest raw digest 等于测试常量；
- owner suite 71 passed；JSON parse、必要 pyright/Ruff/compileall、`git diff --check` 通过；
- changed product consumers 仅为 manifest 的一个 entry 与测试 digest pin；其余文件仅允许
  Gateflow plan/review/closeout evidence。

没有 owner 不清楚、scope 冲突或 public contract 扩张。用户已给出完整 Goal Definition 并授权
自动推进，因此 Goal Confirmation 为 `pass`。
