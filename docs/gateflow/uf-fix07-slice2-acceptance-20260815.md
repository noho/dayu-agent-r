# UF-FIX07 Slice 2 acceptance

## Gate 结论

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Slice：2（CLI / tool primary projection）
- 日期：2026-08-15
- 结论：`SLICE ACCEPTED`
- Base checkpoint：`9d0a2f8a`
- 下一入口：implementation Slice 3

## 接受依据

- AgentCodex 已完成 CLI、tool schema/adapter 与共享 LLM-facing 文案投影。
- 初轮双路 review：
  - `docs/reviews/code-review-20260815-200314.md`：AgentMiMo `pass`；
  - `docs/reviews/code-review-20260815-201037.md`：AgentDS `pass-with-risks`，一个低严重度 finding。
- 主控接受 DS Finding 1：material 携 `primary` 的 tool failure 文案与恢复 hint 未同步新字段。
- AgentCodex 已在 `docs/gateflow/uf-fix07-slice2-review-fix-20260815.md` 完成修复。
- 最终双路 re-review：
  - `docs/reviews/code-review-20260815-201912.md`：AgentMiMo `pass`；
  - `docs/reviews/code-review-20260815-202058.md`：AgentDS `pass`。
- 两路均确认 Finding 1 为 `已修复`，无新 finding、blocker 或未分类风险。

## Accepted contract

- `upload_filing --primary PATH` 使用 append，保留全部 occurrence；其它 upload 命令不注册该选项。
- CLI 只把 raw selector 机械投影为 `primary_selectors`，不做 cardinality、membership、single/multi 或角色判断。
- `start_fins_upload` schema 的 `primary` 是 optional string，`files.maxItems=100`；adapter 对 filing 投影 0/1 selector，
  material 携 `primary` 在 tool union boundary fail closed。
- CLI help 与 tool schema 从 `FinsUploadFormatTextProjection` 机械消费同一组 primary 规则：单文件可省略、多文件恰好一个、
  selector 必须属于 files、顺序不决定角色、delete 禁止 files/primary、material 不使用 primary。
- material-primary failure message 由 typed projection owner 单点产生，schema 与 adapter outcome 复用；恢复 hint 明确包含
  `primary`，并保持 workspace/state/job/observation 零副作用。
- 不存在“首文件是主文件”的 CLI/tool LLM-facing 残留，也未新增 Host/Engine schema contract。

## 验证

- Affected tests：721 passed。
- Targeted pyright：0 errors。
- 单生产文件 branch coverage：99% / 81% / 92% / 89%。
- `git diff --check`：通过。
- 未执行 UF-PF07/UF-PF12 或真实 CLI evidence；未修改 README、registry、oracle/scenario 或冻结 evidence。

Slice 2 blocking finding 为 0，允许进入 Slice 3。既有 delete+files adapter 英文消息不在本 slice 新增范围；
asset/storage/process 语义仍由后续 approved Slice 3 完成。
