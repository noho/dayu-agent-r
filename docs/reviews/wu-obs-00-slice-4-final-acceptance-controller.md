# WU-OBS-00 Slice 4 Final Acceptance

status=complete

work_unit=WU-OBS-00

slice=S4

gate=implementation-review

decision=pass

accepted_base=179520e08e8c6b59cdf49aefc59bc4463c9698c2

implementation_artifact=docs/reviews/wu-obs-00-slice-4-implementation-codex.md

implementation_adjudication=docs/reviews/wu-obs-00-slice-4-implementation-controller-adjudication.md

review_artifacts=

- docs/reviews/code-review-20260724-162056.md
- docs/reviews/code-review-20260724-163232.md

## 双路 review 结论

AgentDS 与 AgentMiMo 均独立给出 `PASS`，两路均为 `0 actionable findings`。
共同确认：

- Service 对 workspace、`.dayu`、tool-trace directory 与 cold JSONL 四种显式 input
  mode 做唯一发现；零候选、多候选与 unsupported path fail closed；
- Host public source contract 与 input loader 再次复核路径布局，Service/CLI 不绕过 Host；
- CLI 只依赖 Service public module，Service 只依赖 `dayu.host` public surface；
- JSON/Markdown 由同一个 frozen structured report 投影；
- 临时文件位于最终目录，使用 strict UTF-8，按 JSON 后 Markdown 固定顺序
  `os.replace`；
- 第一次/第二次 replace、有无旧 Markdown 与 cleanup secondary failure 的
  `published_paths`、`failed_path`、primary failure、cleanup failure 和
  `temporary_paths_cleaned` 均保持稳定；
- mkdir/write/analysis/publication failure 不主动删除既有报告；
- CLI 的 `except Exception` 不捕获 `KeyboardInterrupt` 或 `SystemExit`；
- parser/help/required args/unknown action/subprocess/module entry 与五份 README 均和
  当前代码一致；
- 未发现过度耦合或 semantic ownership drift。

## Residual risk 裁决

以下 reviewer 记录不进入 fix gate：

1. symlink input/output、TOCTOU 与真实磁盘满/权限故障未逐项建名测试，但 Service discovery、
   Host source contract 与 Host loader 形成重复 fail-closed revalidation；temp/write/replace
   的 owner helper 与等价 OSError 路径已覆盖，changed production branch coverage 为
   `91%~100%`。没有直接行为错误证据。
2. Service 与 Host 同时持有布局常量是 discovery hint 与 authoritative validation 的分工；
   常量漂移会被 Host 拒绝，不会静默接受错误 source。当前不应引入向下层泄漏的 query/profile
   接口来消除少量字面重复。
3. `ToolTraceAnalysisInputError` 由 Host analyzer 抛出并作为普通 analysis failure 穿透
   Service，CLI 返回 1；本 Slice 不需要按该内部异常类型分流，因此不扩大 Host public API。
4. 双文件不能构成跨文件原子事务是 accepted plan 的显式边界；typed partial-publication
   truth 已准确表达，不能通过删除新 JSON 或覆盖旧 Markdown 伪造全成全败。

上述事项不新增 active residual-risk tracking item。

## 最终验证

- AgentCodex focused：`93 passed`
- AgentCodex full affected matrix：`232 passed`
- AgentCodex full pyright：`0 errors`
- AgentCodex changed production branch coverage：`91%~100%`
- AgentDS focused：`93 passed`；pyright：`0 errors`
- AgentMiMo focused：`93 passed`；pyright：`0 errors`
- Controller 在 reviewer artifacts 落盘后复跑：
  - focused：`93 passed`
  - targeted pyright：`0 errors, 0 warnings, 0 informations`
- 相对 accepted Slice 3，frozen contracts/rules/input/producer/schema 无 diff。
- `git diff --check` 通过。

## 真实 CLI acceptance

用户定义的硬停止条件未触发：

- 已授权的 `workspace/.dayu` 被精确删除并由真实 `dayu-cli prompt` fresh bootstrap；
  未运行 init，未用 fixture/helper/direct-write/alternate producer；
- Host 生成 current-schema hot/cold/payload descriptor=`9/9/7`，SQLite schema object
  count=`24`；
- 真实 directory 与 cold-file analyzer mode 均返回 0，并发布非空 JSON/Markdown；
- 双格式 counts 同源，directory mode 无虚假 digest mismatch，cold-file mode 明确
  hot/payload limitation；
- analyzer 读取前后 SQLite/cold/artifact hashes、counts 与 schema 不变；
- fresh smoke 数据仅保留在 Git 忽略的 `workspace/.dayu`。

## Acceptance

Slice 4 accepted。无需 implementation review fix/re-review。下一步创建 Slice 4
protected commit；四个 implementation slices 全部 accepted 后，进入 whole-WU aggregate
deepreview，不直接创建 PR。

blocker=none

next_entry_point=create accepted Slice 4 protected commit; never self-advance
