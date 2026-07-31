# WU-CLI-INIT-01 S5-A Code Review Adjudication

## Gate

- work unit：`WU-CLI-INIT-01`
- slice：`S5-A deterministic implementation`
- gate：`code review adjudication`
- controller：`AgentController`
- 日期：2026-07-30
- decision：`pass`
- next entry point：`S5-B live provider matrix implementation`

## 审查输入

- `docs/reviews/wu-cli-init-01-s5a-implementation-codex.md`
- `docs/reviews/wu-cli-init-01-s5a-code-review-mimo.md`
- `docs/reviews/wu-cli-init-01-s5a-code-review-ds.md`
- `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- `docs/reviews/wu-cli-init-01-plan-codex.md` 的 S5

两路独立 reviewer 均给出 `PASS`。Controller 复核了 frozen manifest、production
publication fixture、42 项 deterministic tests、92% utils 单文件覆盖率、full
pyright、Ruff 和 `git diff --check` 证据。

## Controller 裁决

S5-A 满足进入 S5-B 的前置条件：

1. frozen manifest 描述的是 init 完成后的 workspace publication，不是 package
   `dayu/config` source tree；
2. 第一轮原始 observed-behavior 直接列出的第 43 个文件为 workspace 根
   `.dayu-init.lock`，当前 production FIRST flow 也持久保留该空普通文件；
3. actual tree 由 production lock 与 workspace transaction owner 构造，expected
   来自 checked-in immutable manifest，正常验证路径不存在 actual-to-expected
   generator；
4. 精确 5 个目录、43 个文件、43 个 content digest 和 16 个模型投影 owner 均被
   独立比较；
5. classifier、redaction、bounded summary、secret scan 与 no-fallback verdict
   已形成严格 typed、fail-closed 的 deterministic contract；
6. live 入口仍明确拒绝执行，因此 S5-A 没有冒充 15-row real provider matrix pass。

原 plan 中“全部 package-source digests”的文字只适用于 42 个 package-owned
`config` 文件；根级 `.dayu-init.lock` 没有 package source，其冻结事实是 production
publication 的空内容摘要。把统一字段命名为 `content_sha256` 是对既定 43-file
Goal 的准确投影，不改变 Goal、oracle version 或业务行为。

## Findings 裁决

### MiMo

未提出 material finding。结论接受。

### DeepSeek

1. `validate_publication_tree` 捕获根级读取错误后继续产生二级 mismatch：
   - 严重度：低；
   - 裁决：`covered by S5-B`；
   - 理由：当前始终 fail closed，不会签发错误 pass；S5-B 接入真实 workspace
     report 时应短路为单一根因并补测试，避免 live evidence 出现诊断噪音。
2. S5-A `main()` 抛出 `NotImplementedError`，外层 `SystemExit` 当前不会构造：
   - 严重度：低；
   - 裁决：`covered by S5-B`；
   - 理由：这是 S5-A 明确拒绝 live 执行的临时边界；S5-B 实现 `main() -> int`
     后该结构自然消失，不保留兼容分支。
3. validator 只枚举根级 lock 与 `config/` 受管子树：
   - 裁决：`not a finding`；
   - 理由：portfolio、assets、`.dayu` 及其它 sibling 不属于 FIRST frozen
     publication manifest；若未来 owner 集合变化，必须升 oracle version。
4. ordinary/thinking 的真实 effective identity：
   - 裁决：`covered by S5-B`；
   - 理由：S5-B 必须对每个 row 从 production assembly 与 Host trace 读取实际身份。
5. secret regex 不覆盖未来 camelCase field：
   - 裁决：`not applicable`；
   - 理由：当前 report schema 由本模块拥有且只使用 snake_case；未来 schema
     改名时应在 owner boundary 同步更新扫描 contract。

不存在未分类 material finding、blocking open question 或 Goal Confirmation 之外的
新需求。

## Accepted validation

- `pytest tests/cli/test_smoke_cli_init_provider_matrix.py -q`：
  `42 passed`
- utils 单文件 coverage：`92%`
- `python -m pyright dayu/ tests/ utils/`：
  `0 errors, 0 warnings, 0 informations`
- scoped Ruff：`All checks passed`
- `git diff --check`：通过
- 双路 code review：`PASS / PASS`

## Completion

S5-A code review gate `pass`。允许精确提交本 slice 的三个实现文件、implementation
artifact、两路 review artifact 与本 adjudication artifact；随后进入 S5-B，不得把
本提交表述为 live provider matrix 已完成。
