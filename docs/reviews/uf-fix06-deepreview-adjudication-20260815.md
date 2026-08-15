# UF-FIX06 aggregate deepreview adjudication

## 审查范围

- Work unit：UF-FIX06 `converter-capability-owner`
- 实现基线：`a3d584fc`
- 审查提交：`c1db7b49`、`affa665b`、`8033a56e`、`f61ddb95`
- 独立审查：
  - `docs/reviews/deepreview-uf-fix06-mimo-20260815.md`
  - `docs/reviews/deepreview-uf-fix06-ds-20260815.md`

## 总裁决

**CODE FIX REQUIRED**。

两路审查均确认 converter capability、Fins role overlay、Service/workflow admission、typed bounded
failure、原子发布与取消语义主体成立；但 AgentDS 给出的两项低严重度 finding 有直接代码证据，且都位于
格式 contract 的投影边界。为避免在 closeout 时保留新的 semantic-owner drift，接受两项并要求最小修复。

## Findings 裁决

### DS-F1：companion-only 文案硬编码 `.xsd`

- 裁决：**ACCEPTED**。
- 理由：`companion_only_suffixes` 已是 typed contract 字段，投影文案仍写死 `.xsd` 会形成第二真源；
  即使当前值一致，也违反本 work unit 的唯一 owner 目标。
- 修复要求：`project_fins_upload_format_text()` 必须从 capability 机械生成 companion-only 文案，测试应断言
  投影随 contract 输入变化，而不是仅快照当前字面量。

### DS-F2：`upload_material --files` help 未消费 contract

- 裁决：**ACCEPTED**。
- 理由：本 work unit 已把 material 定义为 converter-required role；CLI 仍使用“待上传文件路径”旧文案，
  与 tool schema 和 runtime contract 的信息完备度不一致。该修复只触及同源投影，不扩大 admission 行为。
- 修复要求：新增或复用 material 专用投影字段，明确每个文件必须真实转换成功以及 create/update/delete 的
  文件空状态；CLI help 必须直接消费该字段，并增加入口测试。

### MiMo-F1：`FinsUploadUsageFailure.code` 联合类型

- 裁决：**DEFERRED / NON-BLOCKING**。
- 理由：当前 closed enum、序列化与 kind/code 自校验均成立；进一步重塑 usage code 属于 failure contract
  演进，不是 UF-FIX06 格式准入的必要修复。

### MiMo-F2：batch discovery 不发现 companion-only 文件

- 裁决：**REJECTED AS FINDING**。
- 理由：batch discovery 没有显式 primary/companion 角色信息，只发现 converter-capable primary 是当前正确
  边界；自动归组与显式 primary 属于 UF-FIX07 非目标。

### MiMo-F3：material CLI 与 runtime 双重校验

- 裁决：**REJECTED AS FINDING**。
- 理由：CLI 和 runtime 都调用同一 typed owner；前者提供入口反馈，后者保护绕过 CLI 的 Service/workflow，
  不构成 allow-list 或语义重复。

## 非本 work unit 风险

- UF-FIX07：显式 primary、重复路径、basename/stem collision，继续 deferred。
- delete 携带 files、material 空 upsert 的 failure 分类精化，不在 UF-FIX06 范围内。
- UF-PF06、UF-PF12 与真实 CLI evidence 按用户要求不执行。

下一入口：AgentCodex 完成两项 accepted finding 的 owner-boundary code fix；随后由 AgentMiMo 与 AgentDS
双路 re-review，通过后才能进入 final closeout。
