# UF-FIX07 Slice 4 acceptance

## Gate 结论

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Slice：4（README / full affected validation）
- 日期：2026-08-15
- 结论：`SLICE ACCEPTED`
- Base checkpoint：`892be915`
- 下一入口：aggregate review

## 接受依据

- AgentCodex 已按三个 README 的职责边界同步当前实现：根 README 面向最终用户，Fins README 面向架构与契约维护者，
  tests README 只记录现有测试事实和执行方式。
- 双路 code review：
  - `docs/reviews/code-review-20260815-211626.md`：AgentDS `PASS`；
  - `docs/reviews/code-review-20260815-211702.md`：AgentMiMo `PASS`。
- 两路均把文档声明回溯到 Slice 1–3 的生产代码与 owner-level tests，确认无首项 primary 残留、未来能力预写、内部
  identity 算法泄漏或虚假 UF-PF evidence，且无 finding、blocker 或未分类风险。

## Accepted documentation contract

- 根 README 自足说明 `--primary`：单文件可省、多文件恰好一个且必须属于 `--files`；重复规范路径、多个 selector、
  集合外 selector、超过 100 个文件以及 delete 携带 files/primary 都在启动前作为 usage failure 拒绝。
- 根 README 说明只有 explicit primary 执行 Docling 与 downstream process，companions 仅原样保存；同 basename/stem
  文件可共存，失败时整批零发布且 stored files 为零。
- Fins README 准确记录 raw request 与 validated selection 的 owner 分工、collision-free asset identity 与
  `original_filename`/`derived_from` 投影、storage primary 和 downstream exact consumption，以及 filing fingerprint
  的 move identical-skip / rename update 语义；material contract 保持不变。
- tests README 记录当前 deterministic coverage、13 文件 focused command 与 owner-level assertions，未声称真实
  UF-PF07/UF-PF12 已执行或通过。

## 验证

- 13-file affected suite：1358 passed，1 skipped，3 warnings。
- 全仓 `python -m pyright dayu/ tests/ utils/`：0 errors，0 warnings，0 informations。
- 六个修改生产文件 branch coverage：88% / 89% / 99% / 81% / 92% / 85%，均通过 80% 单文件门槛。
- `git diff --check`：通过。
- 未执行 UF-PF07/UF-PF12；未修改 registry、oracle/scenario 或冻结 evidence。

Slice 4 blocking finding 为 0，允许进入 aggregate review。optional real Docling integration skip 与第三方 `edgar`
deprecation warnings 已分类为非阻塞项；真实 evidence 仍需另行授权。
