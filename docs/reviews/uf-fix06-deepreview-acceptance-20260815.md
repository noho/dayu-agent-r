# UF-FIX06 aggregate deepreview acceptance

## Gate result

**PASS**。

AgentMiMo 与 AgentDS 的 aggregate deepreview 均完成；Controller 接受 DS-F1、DS-F2，AgentCodex 已在
格式文本 owner 与 CLI 直接消费边界完成最小修复。两路 re-review 均确认 root cause 已消除、无新
regression、无 semantic-owner drift，follow-up docstring 精度观察也已消除。

## Accepted fix

- `project_fins_upload_format_text(capability)` 从 `companion_only_suffixes` 机械投影随附文件专属后缀，
  不再在 LLM-facing 文案中硬编码 `.xsd`。
- `FinsUploadFormatTextProjection.material_files` 成为 material CLI help 与 upload tool schema 的共同
  文案 owner；两者不再维护独立规则文本。
- owner contract 测试证明 companion-only 输入变化会同步改变文案；CLI 测试证明
  `upload_material --files` 直接消费 owner 投影并包含 converter-required、逐个转换与空状态语义。

## Review evidence

- 初审：
  - `docs/reviews/deepreview-uf-fix06-mimo-20260815.md`
  - `docs/reviews/deepreview-uf-fix06-ds-20260815.md`
- 裁决：`docs/reviews/uf-fix06-deepreview-adjudication-20260815.md`
- 修复：`docs/gateflow/uf-fix06-deepreview-code-fix-20260815.md`
- 复审：
  - `docs/reviews/deepreview-re-review-uf-fix06-mimo-20260815.md` — PASS
  - `docs/reviews/deepreview-re-review-uf-fix06-ds-20260815.md` — PASS

## Validation evidence

- Focused tests：`570 passed, 3 warnings`。
- Focused coverage：`dayu/fins/upload_format_contract.py 94%`、`dayu/cli/arg_parsing.py 99%`、
  `dayu/fins/tools/upload_tools.py 92%`，合计 `97%`。
- 全量 pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- protected registry/design 文件：未修改。
- UF-PF06、UF-PF12 与真实 CLI evidence：按用户要求未执行。

## Residual risk

- MiMo-F1 的 usage-code 联合类型维持 `DEFERRED / NON-BLOCKING`，不属于 UF-FIX06 必要修复。
- UF-FIX07 的显式 primary、重复路径与 basename/stem collision 继续 deferred。
- delete 携带 files、material 空 upsert 的 failure 分类精化属于后续 usage contract 工作。

下一入口：提交 aggregate deepreview fix 与 review artifacts，然后执行 final closeout validation。
