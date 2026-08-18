# UF-FIX07 aggregate deepreview acceptance

## Gate 结论

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- 日期：2026-08-15
- Base checkpoint：`64050349`
- 实施 HEAD：`6b80400139aba1ba43d950635a6e735467db4316` + frozen aggregate fix diff
- 结论：`AGGREGATE REVIEW ACCEPTED`
- 下一入口：protected aggregate commit；按用户明确要求跳过 draft PR，随后进入 final closeout

## Controller 裁决

本 work unit 的动机成立：重复规范路径原先未在 mutation 前拒绝，basename/stem 可导致 original/derived identity 碰撞，且多文件
primary 由输入顺序偶然决定，造成 storage 与 downstream 消费语义漂移。修复落在各业务事实的唯一 owner boundary，没有在下游增加
fallback、兼容 shim、loose parsing 或基于文件内容/顺序的 primary 推断。

接受后的 contract 为：

- raw request 与 validated selection 分离；最多 100 个不同规范输入文件，重复路径、组合/cardinality、primary 缺失或集合外等可静态判断
  错误均在 converter、workspace mutation 与 publication 前以有界 usage failure 拒绝；
- 单文件请求的唯一文件是 primary；多文件请求必须显式且恰好指定一个属于 `--files` 的 primary；validated request 是 CLI、Service、
  workflow、storage publication 与 downstream 共用的 primary 真源；
- 每个 original 使用规范路径派生、同 filing 内无碰撞的 asset identity，同时保留 `original_filename` 投影；derived identity 从 primary
  original identity 精确派生，禁止 basename/stem 覆盖或混淆；
- 只有 primary 执行 Docling 转换并由 `process_filing` 精确消费；companions 只按 UF-FIX06 capability/companion contract 原样保存，
  不投影为 converted/processed；
- publication 继续采用整批 prepared mutation；primary 转换或 publication 任一步失败都保持零部分发布和 stored count 为零；
- filing fingerprint 由 Service owner 编码 primary role：single-file 保持 v1 fixed vector，multi-file 使用 role-aware v2；descriptor 无法
  区分 primary 时禁止 identical-skip，并由唯一 version owner 保守递增，避免保留错误 primary；不持久化 path/order/safety；
- help、tool schema、CLI 错误与 README 对上述规则给出用户/LLM 可理解的自足说明。

## Finding closed set

| Finding | 最终状态 | 接受依据 |
| --- | --- | --- |
| primary role 未进入 filing fingerprint，primary flip 可能 identical-skip | 已修复 | role-aware typed fingerprint、safe/unsafe skip contract、primary flip/ambiguous/recovery/old-v1/move owner tests |
| Fins README 把 role order 错写为 input order | 已修复 | primary-first、companions 保持请求相对顺序的职责文档 |
| 四个 fingerprint fail-closed guards 缺 direct owner coverage | 已修复 | 四条独立精确消息 `pytest.raises` tests，guard 行均被覆盖 |
| 全仓 9 failures 被过度记录为全部 base 稳定复现 | 已修复 | 保留实际全仓总数；定向隔离精确记录 8/9 base 复现、1/9 unrelated host flaky |
| 8/1 定向隔离结论缺来源回引及 closed-set 状态不一致 | 已修复 | fix artifact 显式回引产生证据的 review，且引言、五行状态表、结语、completion、Decision/next 一致 |

最终双路 closed-set review：

- AgentMiMo：`docs/reviews/code-review-20260815-230205.md`，`AGGREGATE RE-REVIEW PASS`；
- AgentDS：`docs/reviews/code-review-20260815-230207.md`，`PASS（closed set）`、无 findings。

完整 aggregate review/fix 证据链保存在 `docs/reviews/code-review-20260815-222906.md` 至
`docs/reviews/code-review-20260815-230207.md` 的本 work unit timestamped artifacts，以及
`docs/gateflow/uf-fix07-aggregate-review-fix-20260815.md`。所有已接受 finding 均为 `已修复`，没有 `部分修复`、`未修复`、
`证据失效`、blocking open question 或未分类 residual risk。

## 验证接受

- fingerprint owner focused suite：80 passed；
- 13-file affected suite：1366 passed，1 skipped，3 warnings；
- 全仓 `python -m pyright dayu/ tests/ utils/`：0 errors，0 warnings，0 informations；
- 六个修改生产文件 branch coverage：88% / 89% / 99% / 81% / 92% / 87%，均达到单文件 80% 门槛；
- `git diff --check`：PASS；
- registry/oracle exact-file diff：为空。

Reviewer 的一次全仓 run 结果为 `7704 passed, 9 failed, 10 skipped, 6 deselected`。对 9 个 failure IDs 的 base
`64050349` 定向复跑为 `8 failed, 1 passed`：8 个稳定复现于 base，另一个 host watchdog 用例在 base 与移除当前 working diff 的
HEAD 均通过，属于 unrelated flaky。失败路径均不在本 aggregate diff 中，因此不归当前 work unit 修复，也不改变 affected gate 结论。

## Residual risk 与 scope

- descriptor 完全相同的 primary/companion 无法在禁止 path/order identifier 的前提下区分；当前选择 fail-closed 禁止 identical-skip，
  代价是 ambiguous replay version churn，作为保守边界接受；
- 旧无角色 multi-file digest 首次按 v2 upsert 会更新版本；不增加 dual-read 或 compatibility shim；
- UF-FIX08 existing-source auto repair、UF-FIX10 concurrency、UF-FIX11 company meta warning 继续由后续 work unit 负责；
- optional real Docling、UF-PF07/UF-PF12 真实 CLI evidence 未执行；registry、oracle/scenario 与 frozen evidence 未修改；
- 用户明确要求当前分支提交且不创建 PR，因此 draft PR gate 以显式授权跳过，不 push、不创建 PR。

Controller 接受 aggregate diff，可执行 protected aggregate commit。
