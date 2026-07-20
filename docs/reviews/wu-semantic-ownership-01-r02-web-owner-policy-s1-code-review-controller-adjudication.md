# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 Code Review Controller Adjudication

## 1. Gate identity and verdict

- Umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Internal remediation slice：`R02-S1` Web config owner 与 typed policy split；不是新 WU、feature、issue 或独立 sub-WU。
- Implementation base：`70ffc917..working tree`。
- Review artifacts：
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-ds.md`
- Verdict：**FIX REQUIRED — RETURN ALL ACCEPTED FINDINGS TO AGENTCODEX IN THE SAME R02-S1 SLICE**。

两路 review 均确认 config/child-budget owner 方向、retained Web security 与 S1/S2/S3 时序基本正确，但 reviewer 的 `PASS-WITH-RISKS` 或 `non-blocking` 标签不拥有 disposition。项目硬约束和 diagnostics v2 的既有可观察语义要求当前关闭下列三项；全部修复并经 Controller 验证、双路 re-review 前不得 commit 或进入 R02-S2。

## 2. Finding disposition

### R02-S1-CR-F01 — ACCEPTED / LOW — Web provider 顶层未知字段未 fail fast

来源：MiMo Finding 01，接受并修正其证据表述。

直接证据：`provider._parse_config` 是 final provider record 的唯一 raw JSON parser owner，但当前只读取已知字段；例如 `allow_prvate_network_url=false` 会被静默忽略，并回到 packaged/typed `allow_private_network_url=true`。MiMo artifact 把 default 写成 `False` 不准确，不影响根因：operator 的显式安全配置拼写错误会静默失效。Accepted plan §8.2 要求 present values exact validate、unknown/invalid precise fail fast；在 owner boundary 拒绝顶层未知字段比下游补偿更符合该 contract。

Required fix：

- 在 `provider.py` 的唯一 raw parser boundary 定义 Web provider config 已知字段闭集，进入任何字段解析前拒绝 unknown top-level key，错误消息包含精确 `web provider config.<field>` 路径。
- 已知闭集必须包含本 provider 现有全部字段与 S1 新字段；不得误改 ConfigLoader record-replace contract、不得引入兼容 alias、loose ignore 或第二 parser。
- 增加 typo/unknown direct test，并证明合法 partial final record 仍按 field/group local defaults 工作。

### R02-S1-CR-F02 — ACCEPTED / LOW — 新增测试函数与方法未完整满足中文 docstring 硬约束

来源：DS Finding 01，接受并扩大到本 slice 新增定义的完整闭集。

直接证据：DS 列出的 `unexpected_non_html`、`unexpected_html`、`convert_pdf`、`missing_optional_module`、`fake_build_requests_profile` 等只有摘要式 docstring；Controller 继续核对发现本次新增 test doubles 的 `__init__`、`read`、`close`、`stream_reader`、`ZstdDecompressor`、部分 nested fakes 以及新增 `test_*` 函数也只有单行说明。`AGENTS.md` 没有为测试代码豁免“函数必须提供完整中文 docstring，至少包含参数、返回值、异常”。只补 DS 举例的七处不能关闭根因。

Required fix：

- 以 `git diff -U0 70ffc917` 的 added definitions 为闭集，审计本 slice 新增的每个 function、method、nested fake 与 test function；全部补足中文参数、返回值、异常说明。
- 无状态且不依赖 closure 的新增 nested helper 应优先移为模块级私有 helper；确实需要捕获测试状态的 nested fake 可保留，但签名必须精确、docstring 必须完整。不得为追求机械统一引入 god fixture/builder 或 loose `**kwargs`。
- 不要求顺带修复 baseline 已存在的 docstring/lambda 债务；不得扩大到非本 slice 代码。

### R02-S1-CR-F03 — ACCEPTED / LOW — 极小 positive diagnostic cap 静默丢失截断可观察性

来源：DS Finding 02；MiMo Finding 03 的“无需修改”结论被拒绝。

直接证据：`_ERROR_TRUNCATION_SUFFIX = "...<truncated>"` 长度为 14；当前 `project_error_message` 在 `max_chars <= 14` 时把 suffix 设为空。这样虽不再违反 positive cap 并能保持长度有界，但超限消息与恰好完整的短消息不可区分，改变了 diagnostics v2 既有的显式 truncation signal。DS artifact 写成 `<=15`、MiMo 写成 `1-13` 都有 off-by-one；正确边界是 full suffix 只有在 `max_chars > 14` 时可交给当前 runtime primitive。

Required fix：

- 修复落在 `web_diagnostics.project_error_message` owner boundary；任意正整数 cap 都必须可执行且不超限，发生截断时必须仍有明确可观察标记。
- `max_chars > 14` 时保留既有完整 `...<truncated>` suffix；极小 cap 使用能装入 cap 的最小明确标记，`max_chars=1` 也必须有确定行为。不得提高配置最小值、绕过脱敏、修改 diagnostics schema/revision/payload，或修改层中立 runtime primitive 的公共 contract。
- 添加 `max_chars=1`、`14`、`15` 与未超限短文本 direct tests，锁定长度、标记、旧完整 suffix 与无误报行为。

## 3. Rejected findings and accepted observations

- MiMo Finding 02：**design confirmation / no fix**。S1 utility 将现有 private/local flag 同时投影给 custom-port 是 Controller validation F02 的精确 retained-behavior 修复；S3 才改为两个 typed facts，不得在本 fix 提前实施。
- MiMo Finding 03：其 positive-cap 不抛错结论被保留，但“无 suffix 也正确”的 disposition 被 R02-S1-CR-F03 覆盖。
- DS/MiMo 关于 coverage 位于 80% 门槛、S2/S3 增量风险、S1 utility 暂时不能独立配置 custom-port、测试队列顺序和 synthetic Playwright doubles 规模：**accepted observations / no current product fix**。当前 owner paths 有 direct tests；后续 slice 每次仍须重跑逐文件 coverage 并由 reviewers 重新检查测试耦合。
- Provider 顶层 unknown finding 不授权 schema DSL、通用 config validator 或跨 provider framework；只修当前 Web provider raw parser owner。

## 4. Fix validation and stop boundary

AgentCodex 必须在同一 R02-S1 code-review fix task：

1. 修复 `R02-S1-CR-F01..F03` 并更新固定 fix artifact `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-fix-codex.md`。
2. 重跑受影响 direct tests、完整允许三文件 suite、九个 changed production files 的逐文件 `>=80%` coverage、完整 pyright、`git diff --check`。
3. 重跑 top-level unknown、added-definition docstring、loose callable、legacy owner、S1/S2/S3/deferred/security source scans。
4. 只按 README 触发规则更新必要文字；若产品 contract 未变化，记录 no-update evidence。
5. 停止等待 Controller validation；不得 commit、push、进入 re-review、R02-S2/S3、Issue 178、R03 或统一 authorization。
