# UF-FIX01 implementation fix re-review 裁决

## Gate context

- Work unit：`UF-FIX01 validation-atomic-boundary`
- Review base：`69bc9d2af91788303c839d01ad937cf9b802eb1d`
- Reviewed target：`5a6d80c2b0e87c5810a3bbedb1ab74524a205adc`
- MiMo artifact：`docs/reviews/code-review-20260813-123814.md`
- DS fallback artifact：`docs/reviews/code-review-20260813-124100.md`
- Controller result：**BLOCKED — one minimal fix loop required**

## 已核销项

Controller 接受两路对 A1、A2、A3、A5、C1、C2、C3 主体行为的共同结论：validated request 保持 typed handoff；workflow 以 fresh published state 调同一 validator 并丢弃旧派生值；company meta 与 source publication 共用一个 storage batch；frozen CLI usage matrix、typed failure catch 顺序、material/UF-FIX09 non-goal 均已有 owner-level evidence。

## 必须修复的 finding

### R1 — prevalidation repository construction 必须处于 typed operational boundary

**裁决：接受，阻塞。** `prevalidate_fins_upload_filing_request_for_workspace` 在 `try` 外构造 `FsFilingUploadStateRepository`。构造链中的 workspace `resolve()` 可能抛出 `OSError`；该异常虽经 storage 投影后不含路径且 CLI 最终 exit 1，但绕过 `FinsUploadPrevalidationError`，也绕过专用 CLI operator log。这违反已确认的 A4：业务启动前的 storage/lock/corruption operational failure 必须由 prevalidation owner 产生 typed、bounded、path-free reason，public exit 1，同时 operator evidence 保留原始 cause。

最小修复：把 repository construction 与 state read 放入同一个 typed prevalidation `try`，沿用现有 I/O/corruption mapping；不得在 CLI generic branch 加字符串判断或 fallback。补 owner-level test，故障发生于 repository construction/resolve 阶段，断言 typed exception 的固定 reason、cause chain，并补真实 CLI boundary 断言 exit 1、exact path-free stderr、operator log 包含根因、fresh workspace 无 mutation。

### R2 — `_prevalidate_upload_filing_request` docstring 必须反映 typed contract

**裁决：接受，阻塞。** 当前 docstring 仍声明裸 `OSError`/`ValueError`，与实际 `FinsUploadUsageError` / `FinsUploadPrevalidationError` 契约不一致，违反项目 docstring 硬约束。

最小修复：只更新该函数异常说明，不改变运行语义。

## 非 finding / 不扩展项

- DS 关于 workflow fresh recheck 后的 usage error 在异步 direct producer 内如何形成 terminal exit 的备忘，不是本次新增缺口：用户在业务启动前可判断的输入已由 factory 前 prevalidation 映射为 exit 2；随后真实 published state 漂移属于业务运行期竞争，不得反向改写为 preflight usage。
- authoritative identity mismatch 是内部 invariant failure；本轮不改变其文案或分类。它仍是 exit 1，且不属于用户可预判输入错误。
- 不修改 date/year 域、suffix allow-list、material transaction、UF-FIX09 converter、frozen evidence/registry 或其它 work unit。

## 下一 gate 条件

AgentCodex 只修 R1/R2，运行直接受影响测试与完整 pyright，更新 fix artifact 并本地提交。随后 MiMo、DS 对该 delta 做第二轮独立 `$deepreview`；两路均确认 R1/R2 closed 且无新阻塞 finding 后，implementation gate 才可 PASS，并进入 UF-PF01 focused-real evidence。
