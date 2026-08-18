# UF-FIX01 UF-PF01 focused-real finding

## Gate context

- Probe HEAD：`452258eb00e9e0d330603ee6099dfd0beda9322a`
- Evidence root：`/Users/leo/workspace/.dayu-cli-ci/uf-pf01-focused-real-20260813-Cxy3YR/controller-probe`
- Probe bundle digest：`8146a4017655d7b93e83eeba0c670ffb132806acb59540312c8c91ffc1ba6f41`
- Cases：`UF-003`、`UF-I11`、`UF-ATOMIC-FRESH`、`UF-ATOMIC-EXISTING`
- Result：`1/4 PASS`，UF-PF01 **BLOCKED**

## 真实事实

- `UF-003`：exit `2`，stdout empty，stderr exact actionable one line，fresh workspace before/after 均为空，真正零新增。
- `UF-I11`：exit `1`，fresh workspace before/after 均为空；未留下 company/source/job/batch durable state。
- `UF-ATOMIC-FRESH`：exit `1`，fresh workspace before/after 均为空；未留下孤立 company meta 或半成品 source。
- `UF-ATOMIC-EXISTING`：真实 `probe.txt` create seed 成功；随后真实 `corrupt.pdf` update exit `1`，company meta、identity、source meta、manifest、original 与 Docling asset 的 before/after facts 和逐文件 SHA-256 完全一致。
- 三个 content failure 的 typed terminal stdout 均含 closed reason：`文件无法解析或已损坏，请检查文件后重试`。

## Blocking finding F1

三个真实 content failure 的 stderr 在 typed terminal result 前直接输出 Docling 内部 traceback、repo `.venv` 绝对路径、第三方异常 repr 与 Dayu retry warning，单 case stderr 约 5.5k 字符。根因位于独立 Docling conversion child：`_DoclingProcessTarget` 运行第三方 converter 时继承调用方 stderr；child 未装配 Dayu parent 的 log sink，stdlib `lastResort`/第三方 logger 因而直接写公开 CLI stderr。

这违反已确认的 error-classification/public projection contract：content failure 虽正确 exit `1` 且 durable atomic，但 public stderr 必须无 traceback/绝对路径并保持 bounded。不得在 CLI 层过滤字符串，也不得改变 typed failure 分类或靠失败后清理伪造结果。

## Fix boundary

唯一 owner 是 `dayu.fins.pipelines.docling_process_converter` 的 child process adapter boundary。最小修复应在 child 调用第三方 conversion 的范围内隔离 inherited public stderr；failure 仍由既有 closed descriptor 返回父进程，父进程继续投影 typed content reason并在 Dayu operator log 记录 typed cause。禁止改变共享 converter instance、cancellation/terminate/kill/close、async prepare、attempt chain、format allow-list 或 publication transaction。

必须补：child owner test 固定 failing conversion 不向 inherited stderr 写 traceback；真实 CLI integration test 使用 corrupt input 固定 exit `1`、typed reason、stderr 无 traceback/绝对路径且 fresh workspace 零 mutation；随后运行受影响 tests、完整 pyright、双路 `$deepreview`，再重新生成全新的 30-case final bundle。
