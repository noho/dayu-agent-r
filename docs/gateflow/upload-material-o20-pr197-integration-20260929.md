# UM-O20-F01 接入现有 draft PR #197

- 用户要求所有闭环代码放入 PR #197，用户自行 merge。live 查询（2026-09-29）：PR #197 `OPEN`、`isDraft=true`、base `main`、head `codex/upload-material-oracle`，远端 head `45444785a60d26737cfbd27762946cd08b2e66d1`。本集成 worktree `/private/tmp/dayu-upload-pr197-integration` 原 HEAD 同该远端，工作树干净。
- 隔离 O20 worktree 的三个 accepted 提交：计划 `8c9e1d34`、S1 代码 `7870e84a`、aggregate deepreview `18a53f18`。按序 cherry-pick 到集成分支后为 `871d8919`、`814ba696`、`9d9a9d92`；无冲突，`git status --short` 干净，range `45444785..9d9a9d92` 只含 O20-F01 授权文件与 gate artifacts。
- 集成 worktree 独立 `.venv`：受影响七文件 `779 passed`、3 条 edgartools 第三方 deprecation warning；同七文件 coverage run 后 `dayu/fins/upload_format_contract.py` 165 statements / 12 miss / **93%**，`--fail-under=80` exit0；`python -m pyright dayu/ tests/ utils/` **0 errors/0 warnings/0 informations**；真实 `python -m dayu.cli upload_material --help` exit0，固定两句可见，filing help 未因 cherry-pick 触碰；`git diff --check 45444785..HEAD` exit0。
- 语义范围：只把 material 格式文案在唯一 Fins owner 生成并投影到 CLI/tool；`UM-O20-F02` XBRL 运行能力与 `UM-O20-E01` 正样本补证仍是独立未解决项，不因本次集成而宣称成功。PR 保持 draft，不请求 reviewers、不 mark ready、不 merge。

下一 Gateflow entry：提交本集成验证记录后 push 现有 PR head，进行 PR 级双路 `$deepreview`、总控裁决、必要修复/复审与 final push；完成前不计 F01 final closeout pass。
