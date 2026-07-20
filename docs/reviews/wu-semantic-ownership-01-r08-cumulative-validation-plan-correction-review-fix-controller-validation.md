# WU-SEMANTIC-OWNERSHIP-01 / R08 累积验证计划修正 Review Fix — Controller Validation

## 结论

- umbrella work unit 仍为 `WU-SEMANTIC-OWNERSHIP-01`；本 gate 是 R08 内部 remediation continuation，不是新 WU。
- AgentCodex 仅修改 R08 plan 并新增 review-fix artifact，未修改受保护的 S1 product/test tree，未进入 S2。
- Controller 接受 `R08-CVPF-01..03` 的修复进入双路完整 plan re-review；reviewer 结论不能独立授权 S2。
- final plan SHA-256：`87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`。
- protected S1 14-path binary diff SHA-256：`0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57`。

## Accepted finding closure validation

### R08-CVPF-01

§6.6 现在由 Git top-level glob pathspec 直接生成 repo-relative、NUL-separated、实际 changed production Python manifest；可执行 checker 对 coverage JSON `files[path]` 做 exact-key lookup，逐文件输出 ledger，并在空 manifest、缺 key 或 `<80.00%` 时失败。文档明确禁止 basename、suffix、absolute-path、路径规范化或其它 loose fallback。

### R08-CVPF-02

§6.6 现在由 Git top-level glob pathspec 直接生成 `dayu/fins/**/*.py` 与 `tests/fins/**/*.py` 的 NUL-separated actual-changed manifest，并机械传给同一 Python 环境的 Ruff；空 manifest 在 Ruff 前失败，不再保留人工占位符或手抄 allowlist。

### R08-CVPF-03

§7 现在明确：任一 aggregate deepreview accepted finding 修复只要改变 reviewed tree，旧 validation、content manifest、binary diff hash 与双路 aggregate review 全部失效；必须在新 hash 上完整重跑 §6.6/§6.7 并完成双路完整 re-review 与 Controller closure。

## Rejected finding absence

- DS F4 未实施：§6.4 继续保留 Host/Fins public contract 的 exact key-set proof。
- MiMo F2 未实施：§6.7 仍是 §6.6 纳入 scans 的具体展开，不是第二验证真源。
- MiMo F3 未实施：没有新增并发、行号或兼容 seam；S1→S2 仍由同一 Agent 在同一 cumulative tree 顺序实施。

## Controller checks

- 完整读取 final plan 的 §6.6、§6.7、§7、stop conditions 与 handoff checklist，以及 AgentCodex review-fix artifact。
- 独立重算 plan SHA-256：`87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`。
- 独立重算 protected 14-path binary diff SHA-256：`0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57`。
- `git diff --check`：通过。
- `git diff --cached --name-only`：为空。
- 未发现 product/test/README/design 或 S2 越界修改；未 stage、commit、push 或创建 PR。

## 下一入口

AgentMiMo 与 AgentDS 必须在同一 final plan SHA 和 protected S1 hash 上并发执行完整 `$planreview` 等价复审，验证 `R08-CVPF-01..03`、拒绝项缺席、完整 plan 的代码生成可执行性与累计 gate 状态机。若任一路产生 accepted finding，必须由 AgentCodex 修复并再次双路完整 re-review；双路 closure 前不得进入 S2。
