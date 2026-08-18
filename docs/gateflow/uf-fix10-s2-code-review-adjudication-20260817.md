# UF-FIX10 S2 code review adjudication

## Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- slice：`S2 — atomic filing activation & terminal closure`
- gate：`code-review fix adjudication`
- 日期：2026-08-17
- reviewed artifacts：
  - `docs/reviews/code-review-20260817-024912.md`（AgentMiMo）
  - `docs/reviews/code-review-20260817-024321.md`（AgentDS）
- accepted baseline：`7e0941828c09d890ad04e3ff8f2c1cf5e28441ca`
- scope：只允许既有 S2 allowlist、review/fix gate artifacts 与 accepted plan gate sync；禁止
  oracle/scenario/registry/frozen evidence、UF-PF10/UF-PF12、material 与其它 work unit

## 结论

两路 review 均确认 production 主链路的 per-ticker linearization、batch 内 fresh validation、
prepared/durable exact identity、SEC/CN/HK shared owner 接线、stable explicit update、auto
changed convergence、typed conflict、双取消 checkpoint、rollback-first 与 single terminal 方向
正确。当前不能接受 S2：异常映射仍有三个 owner-contract 缺口，且 accepted plan 冻结的并发/终态
证据存在多处未闭合。全部报告的可复现缺口予以修复；另将 DS 的 cancelled outcome open
question 升格为 Controller finding，消除取消时机导致的 action 投影漂移。

## Production findings 裁决

### M-F1 — rollback helper 捕获 `BaseException`

- 裁决：`accepted-low`。
- 根因：新 helper 把 `KeyboardInterrupt` / `SystemExit` 也重写为 `STORAGE_IO`，超出仓储
  rollback failure contract；既有 primary/secondary helper 的捕获策略不授权新路径吞信号。
- 修复边界：只捕获仓储协议可声明的普通异常；信号异常原样传播。增加直接 owner 测试。

### M-F2 — batch acquire / fresh read 的 `RuntimeError` 未映射

- 裁决：`accepted-blocker`。
- 根因：协议明确允许 reservation/lock 或 batch inspector 以 `RuntimeError` fail closed；裸异常会
  落入 workflow generic terminal，违反 path-free typed `STORAGE_IO` owner contract。
- 修复边界：在 acquire/read 两个窄边界分别映射为既有 typed storage failure，并断言 rollback
  与终态 code；不得扩大为通用 `except Exception`。

### M-F3 — fresh validator 的 corruption `ValueError` 未封闭

- 裁决：`accepted-blocker`。
- 根因：同一 validator 的 storage producer identity/state invariant failure 属于 typed
  prevalidation corruption，不是 caller programming error；裸 `ValueError` 会被 generic terminal
  错投影。
- 修复边界：只在 fresh validator 调用边界把其声明的 `ValueError` 映射到既有 corruption
  failure；arbitration/rebase/programming invariant 的 `ValueError` 继续 rollback 后走既有
  unexpected contract，不做全函数兜底。

### C-F1 — checkpoint2 cancelled outcome 使用 fresh request

- 裁决：`accepted-blocker`（Controller 补充）。
- 根因：取消不是 publish/skip/conflict 裁决；若 `MISSING -> COMPLETE` 后在 checkpoint2 取消，
  fresh request 会把 raw `auto` 的 cancelled terminal 偶然投影成 `update`，使同一请求的取消
  action 依赖竞争时机。
- 修复边界：两个 publication-owner 取消 checkpoint 均返回 initial authoritative request；
  fresh request 只供 publish/skip success outcome 使用，typed failure 继续由 workflow 使用 initial
  request。增加 changed-observation checkpoint2 直接断言。

## Test / documentation findings 裁决

### M-F4 — repair transition conflict grid 缺两行

- 裁决：`accepted-low`。
- 修复边界：显式增加 `REPAIR_REQUIRED -> MISSING` 与
  `REPAIR_REQUIRED -> COMPLETE`，均断言 `SOURCE_REVISION_STALE`。

### M-F5/M-F6 — runtime terminal 使用 sleep polling，README 与事实不一致

- 裁决：`accepted-blocker`。
- 根因：用户与 accepted plan 明确禁止测试用 sleep/retry/polling 证明竞争；README 又声称全部
  使用确定性同步。
- 修复边界：删除新增 `_wait_terminal` 的 `time.sleep` / deadline polling，复用 runtime owner
  已有的确定性完成等待或以 Event/queue/future 有界通知建立 happens-before；README 保持
  “无 sleep/polling”仅在实现真的满足后成立，不得降级文档来容纳违规测试。

### D-F1 — different-ticker test 未证明 batch 段并行

- 裁决：`accepted-blocker`。
- 根因：converter barrier 只证明 preparation 并发；即便新增 global publication lock，现有测试
  仍会全绿，不能固定成功信号 7。
- 修复边界：在两个不同 ticker 都取得各自 batch、进入 fresh read 后以 Event/Barrier 做确定性
  会合，再释放并断言两者 ok；禁止生产 hook、sleep 或时间窗口断言。

### D-F2(a) — runtime durable conflict terminal 缺失

- 裁决：`accepted`。
- 修复边界：增加并发 conflict 经 runtime durable failure summary 的 exact code/message、action
  与 stored=0 断言；同步仍必须确定且有界。

### D-F2(b) — explicit create conflict terminal 字段不完整

- 裁决：`accepted-low`。
- 修复边界：补 `requested_action/resolved_action/filing_action == create`、stored=0、非 skip、
  非 unexpected 的精确断言。

### D-F2(c) — same-ticker union 未证明 aliases union

- 裁决：`accepted`。
- 修复边界：同 ticker 不同 filing 的两个 request 携带不同 alias requirement，最终 canonical
  company meta 必须为 stable exact union；不改 company owner 生产逻辑。

## 未接受为当前缺陷的项目

- DS Q2：batch read 的 `ValueError` 现由与既有 prevalidation 相同的 corruption owner 映射；
  token/document 输入均由当前 typed caller 保证，不新增 storage exception taxonomy。
- MiMo residual 的 source-observation helper 命名歧义：无行为错误，不在当前 concurrency goal
  内做 rename。
- CN/HK same-ticker union、跨进程 explicit create/cancel 等更大矩阵：accepted plan 只要求其
  exact-auto route 与 SEC/owner 级其余矩阵，维持 non-blocking residual。

## 修复后验证要求

- 所有新增/受影响的 owner、SEC、CN/HK、runtime focused tests；
- accepted 两组 focused suite；
- 完整 `pytest tests/fins -q`；
- modified production files coverage 均不低于 80%；
- 全仓 `python -m pyright dayu/ tests/ utils/`；
- `git diff --check` 与 allowlist scope check；
- 两路独立 re-review 均无 blocker 后才可进入 S2 acceptance commit。

禁止运行 UF-PF10/UF-PF12；禁止修改 oracle/scenario/registry/frozen evidence；不得新增
sleep/retry/polling、global lock、generic exception fallback 或 material 行为。
