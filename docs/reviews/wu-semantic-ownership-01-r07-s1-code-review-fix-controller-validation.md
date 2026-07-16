# WU-SEMANTIC-OWNERSHIP-01 R07-S1 code-review fix Controller validation

## 1. 结论

- work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 `R07-S1`；不是新 WU。
- 初次被验证 artifact：
  `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-fix-codex.md`，
  SHA-256 `b4d1985480e99c05a0de18a94c211ddf6ad5361787e4da971cead7b22d8083fd`。
- 初次 verdict：**FAIL / VALIDATION_FIX_REQUIRED**。
- validation-correction 后 artifact SHA-256：
  `765685b713de24e4cadcb1c462981a1ee2657faf4453406345bf812e2623437d`。
- 最终 verdict：**PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_S1_CODE_REVIEW**。
- `R07-S1-CR-F01` destructive cleanup complete preflight：当前证据未发现回归，等待修正后完整验证。
- `R07-S1-CR-F02` `begin_batch` primary-error preservation：当前证据未发现主异常被次级失败替换，
  但 path-free exception-chain contract 尚未满足，因此 finding 不能关闭。
- `R07-S1-CR-F03` storage-owner private locator removal：**未关闭**。
- gate：保持同一 `R07-S1 code-review fix` 任务，先做 validation correction；不得进入双路 re-review、
  accepted commit、S2/S3 或 R08+。

## 2. Controller 独立反例

Controller 使用真实 Unix-domain socket 作为 public blob/read helper 的 OS I/O failure，调用
`_read_file_bytes` 后同时检查顶层异常与完整异常链。结果为：

```text
top_str_leak=False
top_args_leak=False
cause_type=OSError
cause_str_leak=True
traceback_leak=True
```

这证明 `_project_filesystem_error` 只清理了顶层 `str` / `args`；当前所有
`raise projected_error from raw_error` 又把包含 absolute workspace path 与 private locator 的
原始异常置入 `__cause__`。调用方只需执行 `traceback.format_exception(exc)`，私有 locator 就会重新
离开 storage boundary。AgentCodex artifact §6.1 声称“raw cause 保留”并不能满足裁决中的“任何 raw
locator 仍可从 public storage 异常观察到都视为 fix 未完成”。

同一 producer-boundary 问题还存在于 runtime lock 路径：`RuntimeFileLockError` / timeout 可把第三方
异常作为 raw cause，第三方异常可能包含 lock path；`_acquire_lock_token` 与 `_release_lock_token`
目前没有在 storage boundary 移除该 raw cause。accepted finding 已明确覆盖 staging/backup/lock
locator，不能只保证顶层 message path-free。

## 3. R07-S1-CR-CV-F01 — public exception graph 仍泄露 private locator

- 来源：Controller fix validation。
- 裁决：`ACCEPTED / FIX REQUIRED`，归入既有 `R07-S1-CR-F03`，不是新产品 finding。
- root cause：producer projection 创建 path-free 顶层异常后仍显式 chaining 到 raw pathful
  filesystem/runtime-lock exception；因此异常对象图与格式化 traceback 仍包含 locator。
- owner-boundary 修复要求：
  1. storage public boundary 抛出的完整 exception graph（`__cause__`、`__context__`、`args`、notes
     及格式化 traceback）不得含 workspace absolute path、private storage key、staging、backup、
     lock locator；
  2. 保留有业务意义的异常 subclass、`errno` 与因果类别，但不得通过 raw pathful cause 保留诊断；
     若保留 chaining，只能链向由 producer 构造的 path-free cause；也可在明确投影点抑制 raw context；
  3. `_acquire_lock_token`、`_release_lock_token` 与 `begin_batch` 等 public storage 路径必须对
     `RuntimeFileLockError` / timeout 的 raw nested cause 做同一 owner 投影，不得修改
     `dayu.runtime.filelock` 的层中立 contract；
  4. 不得添加字段名 blacklist、regex sanitizer、下游 trace/LLM repair、兼容 shim 或修改未授权
     文件。

另外，以下 terminal cleanup note 仍直接把次级异常 `str(...)` 拼入主异常，违背同一 accepted
finding 的 path-free note contract：

- `commit_batch` publication guard release failure；
- `commit_batch` post-commit cleanup failure；
- `_close_active_batch` writer mutex release failure。

这些位置必须复用已存在的 `_append_secondary_error_note`（或等价的同 owner path-free typed note），
不能继续复制次级异常 message。

## 4. 必须补充的 owner 测试

在既有四个 S1 test-file allowlist 内补充或收紧测试：

1. 对真实 socket I/O failure 递归检查完整 exception graph，并检查
   `traceback.format_exception(exc)`；workspace root 与实际 private key 均不得出现。
2. 对 acquire/release/runtime-lock failure 的 raw nested cause 做同样检查，覆盖 lock locator。
3. 覆盖上述三个 terminal cleanup note，断言只保留 action、error type 与可用 `errno`，不含次级
   exception message/path，同时最早 authoritative 主异常保持不变。
4. 修正后重新执行 adjudication 要求的 finding-focused tests、四个 exact full test files、九个
   production file 覆盖率、full pyright、scoped/full Ruff baseline、`git diff --check` 与 locator
   propagation scan。

## 5. Scope 与下一入口

保持原 adjudication 的 production/test allowlist。AgentCodex 只可更新本次 fix 的 production/test
改动和原 fix artifact；不得修改本 Controller artifact、control、plan、design、README，亦不得
stage/commit/push。下一入口是 AgentCodex same-task validation correction，完成后由 Controller 重新
独立验证；只有通过后才进入 AgentMiMo / AgentDS complete dual re-review。

## 6. Validation correction 复验

AgentCodex 在同一 task 内完成 `R07-S1-CR-CV-F01` 修正并更新原 fix artifact。Controller 独立
读取 owner 实现与测试后确认：

- `_project_filesystem_error` 重新构造同 subclass/errno 的 path-free 顶层异常与 path-free cause；
  `_raise_path_free_error` 在明确 producer 投影点移除 Python 自动挂入的 raw context；
- storage-local runtime-lock adapter 重新投影 acquire/release failure，保留
  `RuntimeFileLockError` / timeout 类别而不暴露第三方/raw nested locator；
- publication release、post-commit cleanup、writer release 三处 note 均复用
  `_append_secondary_error_note`，只保留 action、error type 与可用 errno；
- `dayu/runtime/filelock.py` 无 diff；未添加下游 sanitizer、字段 blacklist、兼容 shim、统一
  authorization 或 deferred Issue 实现。

Controller 独立重跑真实 Unix-domain socket failure；完整异常图结果为：

```text
nodes=2
top_type=OSError
top_errno=102
cause_type=OSError
context_none=True
graph_leak=False
raw_node_reachable=False
```

Controller 独立验证矩阵：

| 检查 | 结果 |
|---|---|
| 四个 exact full test files | `363 passed, 3 warnings`，两次独立执行分别用时 `14.22s` 与 coverage run `15.05s` |
| 九个 production file 行覆盖率 | `80.00%`–`96.08%`；`_fs_identity.py` 为 `92/115 = 80.00%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed-scope Ruff | `All checks passed` |
| full Ruff baseline | 既有 `152`：`72 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`，未扩散 |
| `git diff --check` | PASS |
| raw projection / note scan | `raise projected from raw`、terminal note `str(error)` 为 0 |
| runtime owner scan | `file_lock(...).acquire()` / `token.release()` 仅存在于 storage-local adapter |
| scope/security | runtime filelock、README、design、S2/S3、R08+、deferred Issue 与统一 authorization 无新增实现 |

覆盖率逐文件为：`document_models.py 96.08%`、`_fs_identity.py 80.00%`、
`_fs_storage_utils.py 83.82%`、`_fs_storage_infra.py 86.19%`、`_fs_blob_core.py 88.06%`、
`_fs_company_meta_core.py 91.11%`、`_fs_maintenance_core.py 92.39%`、
`_fs_processed_core.py 88.83%`、`_fs_source_document_core.py 83.69%`。

因此 `R07-S1-CR-CV-F01` 在 Controller validation 层关闭，`R07-S1-CR-F01..03` 全部进入
AgentMiMo / AgentDS complete dual cumulative S1 code re-review。此 PASS 只授权 re-review；不授权
accepted commit、S2/S3、R08+、deferred Issue、统一 authorization、push 或 PR。
