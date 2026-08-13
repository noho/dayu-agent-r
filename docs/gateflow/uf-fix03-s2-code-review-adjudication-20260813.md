# UF-FIX03 S2 code review 裁决

## 输入

- implementation：`docs/gateflow/uf-fix03-s2-implementation-20260813.md`
- AgentMiMo：`docs/reviews/code-review-20260813-223608.md`（PASS）
- AgentDS：`docs/reviews/code-review-20260813-224126.md`（正文含一个未修复中等级 finding）

## Verdict 归一化

AgentDS artifact 同时写了 “PASS” 与“未修复中等级 finding”，两者冲突。Gateflow 按 finding 的可执行证据裁决：S2 当前为 **FAIL，进入 review-fix**，不得进入 accepted slice commit。

## F1：POSIX 反斜杠 basename 导致 known content failure 降级

**接受 finding。** 在 POSIX 上 `a\\b.pdf` 是可存在的单个文件名；现有 static upload validation 只检查存在性、regular file 与 suffix，会放行。empty/conversion owner 随后调用 canonicalizer；canonicalizer 按 accepted plan 正确拒绝包含 `\\` 的 pathful 输入，但该 `ValueError` 会越过 `FinsUploadFailureError` typed owner，最终落到 workflow generic runtime mapper。

### Owner 裁决

选择 reviewer 建议的方案 (a)：在 filing static request validation 边界前移拒绝，而不是在 producer 捕获后隐藏，也不改写 plan 例外。

- `direct_events.canonicalize_fins_public_file_label(...)` 继续唯一拥有 basename shape/fragment/control/length 规则；static validator 调用该 owner，只把 shape rejection 转成新的 closed usage fact，不复制 `\\`、`/` 等字符规则。
- 在 `FinsUploadUsageCode` 新增专用非文件标签 code（建议 `INVALID_FILE_BASENAME`）与固定、有界、不含 raw basename 的 actionable message；不得复用要求安全 `file_name` 的 `_FILE_USAGE_CODES`，避免再次把 raw pathful basename带入 public reason。
- static validation 在 exists/is_file/suffix 检查前完成 basename contract admission。fragment、普通 Unicode、`Cc/Cf`、超长但 filesystem 合法 basename 仍可上传；它们只在 failure label projection 时 canonicalize/隐藏，不得被 usage validation 误拒绝。只有 canonicalizer 的 shape rejection（empty/dot/pathful；现实 Path.name 主要是反斜杠）成为 typed usage failure。
- 不在 `_build_original_assets` / `_build_pending_assets` 加 fallback，不改变 content failure mapper。

### 必须测试

1. static validation 对实际 POSIX `a\\b.pdf` 文件产生 exact typed usage code/message，且在 workspace read/publication 前拒绝；Windows 不可创建该 fixture 时用平台安全的 owner unit test覆盖，但不得 skip S2 的 cross-platform contract。
2. 普通 basename、普通中文非 fragment、fragment、`Cc/Cf`、合法超长 basename 不被 static validation 拒绝；它们仍由 failure label canonicalizer按原契约投影。
3. producer/workflow regression 证明 pathful 不再可达 empty/conversion content producer，因此不可能降级为 runtime；原 empty/corrupt/mixed tests保持通过。

## 其它裁决

- empty/corrupt/mixed 原子失败、五字段 schema、label owner、typed consumer、operator/public 边界、material/no-touch：接受两路 review 的通过结论。
- 首次 focused 单测噪声在随后多次整组复跑均未复现，且测试不在 S2 diff；不立 finding。
- 全 `tests/fins` 的 upload-tool fixture failure 在 base 已存在且不在本 slice 调用链；记录为 classified residual，不在 S2 修复。

## Re-review entry

修复后必须复跑 S2 focused、S1 regression、完整 pyright、changed-file coverage、`git diff --check` 与 frozen SHA，并由 AgentMiMo/AgentDS 双路 re-review。不得进入 S3、README、UF-PF03 或 commit。

