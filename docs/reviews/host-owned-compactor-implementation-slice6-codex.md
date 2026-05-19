# Host-owned Compactor Slice 6 README 同步

## 范围与判断

- 设计真源：`docs/host/design.md`。
- 实施 plan：`docs/host/host-owned-compactor-plan.md`。
- 本次只做 README / 稳定文档同步，不提交、不 push，不扩大到生产代码清理。
- 问题真实存在：`dayu/host/README.md` 仍把 `CompactorExecutionBaseline` 写入包根 opener contract，并描述为显式注入 compactor；这与当前代码中 `CompactorRunnerBaseline` + `open_host()` 内部构造 `LLMContextCompactor` 不一致。

## 已检查 README

- `dayu/host/README.md`：命中 Host public opener contract、包根导出、Context Governance / compactor runner baseline、Host-owned compactor 与 current behavior，已同步。
- `README.md`：命中手工 smoke 的项目级使用说明，已同步为 `CompactorRunnerBaseline` 与 Host-owned compactor runner。
- `tests/README.md`：命中 public compact smoke 的测试分层说明，已同步为 public opener 内部构造 Host-owned compactor。
- `dayu/README.md`：已检查。当前层边界与术语中 `Host` 拥有 Context Governance，未出现本 slice 要清理的旧 public contract 术语；不修改。

## 修改内容

- `dayu/host/README.md`
  - 将包根 public contract 从 `CompactorExecutionBaseline` 改为 `CompactorRunnerBaseline`。
  - 明确普通 Service 只传 compactor runner/options/artifact root，不注入低层 compactor port、prompt、candidate builder、quality override 或 raw policy ref。
  - 明确 `ContextCompactor` 只作为 Host 内部 / 低层测试 seam，不属于普通 public opener contract。
  - 将 proactive compact 行为描述从“调用显式注入的 compactor”改为“调用 Host-owned compactor”。
- `README.md`
  - 将手工 Host public smoke 描述改为通过 `CompactorRunnerBaseline` 提供 Host-owned compactor runner 配置。
  - 删除不符合当前脚本输出的 “DeepSeek compactor 调用次数” 描述。
- `tests/README.md`
  - 将 `test_public_compact_smoke.py` 描述从“显式真实 compactor adapter”改为通过 `CompactorRunnerBaseline` 覆盖 public opener 内部构造 Host-owned compactor。

## 决定不改

- `dayu/README.md`：没有残留 `CompactorExecutionBaseline`、`compactor_baseline`、caller-owned compactor 或 Service 注入 `ContextCompactor` 的说明；保持不变，避免把总览文档写成 Host 设计草稿。
- `tests/host/public_smoke_support.py`：里面的 slice / smoke 字符串是测试 case / helper 标识，不是 README 稳定文档，也不是 public contract 说明；本 slice 不做代码命名清理。
- 生产代码：当前代码已导出 `CompactorRunnerBaseline`，`open_host()` 已内部构造 `LLMContextCompactor`；本任务目标是文档同步，未发现必须通过代码改动修复的 README 示例引用。

## 验证

- 已通过：`rg 'CompactorExecutionBaseline|compactor_baseline|caller-owned|caller owned|Service.*ContextCompactor|ContextCompactor.*Service' README.md dayu/README.md dayu/host/README.md tests/README.md`
- 已通过：`source .venv/bin/activate && python -m pyright dayu/host tests/host`
- 已通过：`git diff --check`

未运行 pytest：本次只改 README 与 review artifact，未改生产代码或测试代码。
