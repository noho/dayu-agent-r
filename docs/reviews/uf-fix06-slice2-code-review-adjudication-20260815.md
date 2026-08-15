# UF-FIX06 Slice 2 code review adjudication

## Gate 结论

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：2
- 日期：2026-08-15
- 输入：AgentMiMo 与 AgentDS 两路独立 code review
- 结论：`FIX REQUIRED`
- 下一入口：AgentCodex code review fix

## 双审结果

- AgentMiMo：`pass`，0 blocking findings；artifact：
  `docs/reviews/code-review-slice2-mimo-20260815.md`。
- AgentDS：`pass-with-risks`，0 blocking findings；artifact：
  `docs/reviews/code-review-slice2-ds-20260815.md`。
- Controller 不接受 MiMo 对“所有格式错误消息均不超过 240 字符”的证明：现有测试只覆盖短
  basename；AgentDS 已用 230 字符 basename 复现 246 字符 usage message。

## Accepted findings

### A1：LLM-facing files 要求不自足

- 来源：AgentDS F1。
- 状态：`accepted / must-fix`。
- 修复要求：同源 projection 必须显式说明 filing 与 material 的 auto/create/update 均至少提供一个
  文件、delete 不得提供文件；CLI filing help 与 tool schema 继续消费同一 projection。

### A2：usage failure 的 240 字符 owner invariant 可被格式路径绕过

- 来源：AgentDS F2、Controller 复核。
- 状态：`accepted / must-fix`。
- 修复要求：格式 owner 必须在保留 canonical `file_label` 的同时产生不超过 240 字符的 path-free
  message；usage public fact 自身必须 fail-fast 校验其 closed code union 与 240 字符 message invariant。
  不得让合法的超长安全 basename 转成 unexpected/runtime error，不得截断或伪造 `file_label`。
- 测试要求：覆盖刚好处于长 basename 窗口的 primary/material error 及 usage projection，断言
  `file_label` 保持 canonical、message 不超过 240、绝对父路径不出现。

### A3：material CLI 调用方 docstring 漏报新异常

- 来源：AgentDS F3。
- 状态：`accepted / must-fix`。
- 修复要求：`_upload_material_stream` 的中文 docstring 补齐 `FinsUploadFormatError`。

### A4：`.json` candidate 限定缺失

- 来源：Controller 对 accepted plan §5.1 的直接复核。
- 状态：`accepted / must-fix`。
- 修复要求：help/schema 同源 projection 必须明说 `.json` 仅表示 Docling JSON candidate，不承诺任意
  JSON 内容可转换；测试同时覆盖 CLI help 与 tool schema。

### A5：无关格式化 churn

- 来源：Controller diff 审计。
- 状态：`accepted / must-fix where safely separable`。
- 修复要求：恢复 `upload_batch.py` 与既有测试中不承载 Slice 2 语义的纯 Black 重排，保留新增/更新的
  contract 断言；不得因此改动允许范围外文件或回退已验证行为。

## Deferred / no-action findings

- AgentDS F4（delete + files 被 validator 静默丢弃）：直接证据成立，但属于用户明确排除的其它
  `upload_filing` 修复项；本 work unit 不新增 action/files usage code，不改变该历史行为。作为 residual
  交给后续独立 work unit，Slice 3 不得声称其已解决。
- AgentDS F5（源码文本 audit 断言）：保留唯一 owner 的反漂移审计；补一行测试注释说明其 governance
  目的即可，不要求改成行为测试。
- MiMo F1/F2/F4：均为计划内过渡形态或同 owner 的重复防御，不单独修复。

## 保持条件

- 仍只允许修改 Slice 2 的 production/test 文件与 Slice 2 fix artifact。
- 不触及 Service/workflow/upload failure（Slice 3）、README（Slice 4）、UF-FIX07、registry、oracle/
  scenario、design doc 或冻结 evidence。
- 不运行 UF-PF06/UF-PF12，不 commit。

Blocking accepted finding 为 4 项，另有 1 项范围内清理；完成后必须进入双路 re-review，不能直接接受
Slice 2。
