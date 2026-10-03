# Issue #198 S2 隔离真实 CLI 复验：已发布来源克隆

- Gate：S2 implementation validation；候选代码 HEAD `7234d42dbaea603112c6fed52776281228d261a7` + 11 文件未提交 diff SHA-256 `d53e67f29e26c6d835c42ea81ce43aef34a27cf831959ee685c1802b42df14c5`。
- 执行目录：`/private/tmp/dayu-issue198-s2`；Python 3.11.15，`dayu.__file__` 指向该检出。
- 本次隔离 case：`/private/tmp/issue198-cli-replay-e23865b8`。来源为先前真实 CNInfo→Docling 成功发布、已有 S1 readback 完整性证据的 `/private/tmp/issue198-cli-narrow3-20260929/portfolio`；只复制该 `portfolio` 到新 case，没有复制旧 `.dayu` 锁或其它日志。该来源的原始 PDF SHA-256 为 `b17a9b9b84bca1d2a4e4a3cadc5dd5ba5c85e3f1fd2d758acd3315b5b040ecd9`，Docling JSON 为 `bf98154fb967ea145a9b644dd2c05037f9f40fe10f54e25f65bed0aad452dc5d`，与来源 meta 中登记的 SHA-256 一致。

## 三次相同真实 CLI 请求

每次均调用 `.venv` 中的 `dayu-cli --base <case> download --ticker 000333 --forms FY --start 2025-03-27 --end 2025-03-29 --log-file <case>/<阶段>.log`；除日志名外，命令参数相同，provider discovery 和 Fins storage/CLI 均为生产代码。

1. **基线 readback**：未注入外来文件，退出码 0；`discovered=1 downloaded=0 skipped=1`，目标 `fil_cn_95d26c810c326725ece2cc478a6a4c012fe1c9ce` 为 `integrity_complete`。`baseline.stderr` 为空。它证明新 case 中克隆的真实已发布来源完整且本次 provider 仍能发现同一候选，没有以本轮重新转换为前提。
2. **typed storage 失败**：仅在 `portfolio/000333/filings/` 根新增非点号普通文件 `issue198-unassignable-root.txt`，内容为固定受控标记；同请求退出码 1。stdout 只有 preparing/started，无成功行；stderr 先 `Fins failure` 与零候选摘要，再显示 `classification="storage"`、`reason_code="unsafe_publication"`、`retry_hint="请检查并修复工作区来源状态后重试；重复下载不会自行修复。"`。该公开失败文本与 S1 已审合同一致；本轮 S2 的 `typed.log` 没有 `fins.download.unexpected_failure`。五份已发布来源文件（manifest、identity、PDF、Docling JSON、meta）在注入前后逐文件 SHA-256 完全相同。
3. **清除唯一 mutation 后恢复**：只删除上述受控文件（先断言路径为普通文件且内容逐字匹配），再次同请求退出码 0，`discovered=1 downloaded=0 skipped=1`、同一目标 `integrity_complete`；`recovery.stderr` 为空，`recovery.stdout` 与基线 stdout 的 SHA-256 完全相同。已发布来源文件未被本次失败/恢复改写。

## 原始流身份与泄漏核对

| 流 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `baseline.stdout` | 862 | `cc02b78fa6ca3016842fd012f180010a8678e9ed5186ac85bce33f217565c7a3` |
| `baseline.stderr` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `typed.stdout` | 208 | `0804026d929cc3d8184a56a6de719c3a184292b7d4744da316a83067b7b96f46` |
| `typed.stderr` | 508 | `5349d09510905c154dd7f7ed84ff9d5e6383b6c2dced80d99ace039f3b0847e2` |
| `typed.log` | 168 | `c83123c08be8ffe58688dd5a362150501442b93d951f173be701ea68603f96e2` |
| `recovery.stdout` | 862 | `cc02b78fa6ca3016842fd012f180010a8678e9ed5186ac85bce33f217565c7a3` |
| `recovery.stderr` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

分别检查 `typed.stdout`、`typed.stderr` 和 `typed.log`：没有受控外来 basename、`Traceback` 或 `fins.download.unexpected_failure`；该 typed 案例本来就不应产生 unknown 诊断。普通 INFO 日志没有被误当失败投影。

## 方法边界与未覆盖项

- Accepted plan 原配方要求本次 fresh case 首次从 provider 下载并经 Docling 转换后发布。当前精确 2025-03-28 与中国本地 2025-03-29 两个单日查询均 0 候选；较宽 2025-03-27..31 找到目标，但 fresh 转换 180 秒超时，另一次较长受控运行尚在途。因此本次采用**历史真实发布的已验证来源克隆 + 本次真实 provider 发现/跳过 + 受控 root mutation**，不是 fresh Docling 转换成功证据。#198 的 storage public failure/CLI projection、S2 typed 不误记 unknown 与清理恢复在本次真实 CLI 链上已验证；Docling 转换能力并非本 WU 的产品目标。
- 未在真实 CLI 稳定制造带秘密的未知异常；其安全类型/调用栈、helper 故障和 ERROR 记录由 S2 owner/CLI 测试验证。审查 gate 应核定上述方法替代是否足以满足目标，而不能把它改写为原配方逐字通过。
