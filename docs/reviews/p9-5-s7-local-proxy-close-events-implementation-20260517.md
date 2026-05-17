# P9.5 S7 LocalProxy Close / Events Race Implementation

## 范围

- Gate：P9.5 S7 LocalProxy Close / Events Race implementation。
- 分支：`p9.5-pre-p10-hardening`。
- 计划来源：`docs/host/p9-5-pre-p10-hardening-plan.md` 的 S7。

## 动机判断

S7 动机成立。直接证据是默认 `_DefaultLocalWorkerHandle.events()` 允许同一 handle 多次取得同一个 Engine generator，完整消费后也能再次取得已耗尽 generator；同时 `close()` 直接 `aclose()` 底层 generator，对 close 与 active `anext()` 并发的处理不够明确。LocalProxy 是 Host 到 Engine public entry 的资源边界，必须保证 single-use event stream，并在 scheduler close / terminal break / stream error 等路径不遗留 generator。

## 变更文件

- `dayu/host/local_proxy.py`
- `tests/host/test_local_proxy_engine_ingest.py`
- `tests/host/test_dispatch_scheduler.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/p9-5-s7-local-proxy-close-events-implementation-20260517.md`

## 实现内容

- 将 `_DefaultLocalWorkerHandle.events()` 收紧为 single-use：同一 handle 只能打开一次 events，close 后继续调用仍稳定抛 `RuntimeError`。
- 新增 `_DefaultLocalWorkerEventStream` 包装底层 `run_agent_messages()` async generator：
  - 防止同一 stream 并发 `anext()`；
  - `close()` 可取消活跃 `anext()` task；
  - `close()` 会调用底层 Engine generator 的 `aclose()`；
  - handle `close()` 通过 lock 保持幂等。
- 新增 LocalProxy controlled async generator 测试，覆盖重复打开 events 被拒绝、close while active consumption 会 finalize 底层 generator。
- 新增 scheduler controlled handle 测试，覆盖 scheduler close during active event consumption 后 cancel / close 一次、active registry unregister、lane token release。
- 新增 DefaultLocalProxy terminal-then-late-event 测试，证明 terminal accepted 后 scheduler 关闭 worker stream，不继续读取 late event，底层 generator finalize。
- `dispatch.py` 的 production 清理路径已有 `_consume_worker_events(... finally)` 单点负责 active registry unregister、worker handle close 与 lane release；本次通过测试锁住该行为，未改 production scheduler。
- 同步 `dayu/host/README.md` 与 `tests/README.md` 的 LocalProxy single-use events / close race 当前行为说明。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_local_proxy_engine_ingest.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py`
  - 结果：49 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过，无输出。

## 文档决策

- 已更新 `dayu/host/README.md`：明确 Default LocalProxy events 为 single-use，handle close 会关闭已打开的底层 Engine generator。
- 已更新 `tests/README.md`：测试覆盖描述加入 LocalProxy single-use events / close race。

## 残余风险

- 本次没有引入 RemoteProxy、远端 exactly-once event delivery、wire protocol、orphan recovery 或 P11 recovery 语义。
- Scheduler 对 active task 的关闭仍是 best-effort cancel + finally cleanup；这符合当前本地 worker 语义，不承诺远端 worker ack。
- 既有 clean EOF without terminal 与 stream exception 仍沿当前 EngineEventIngestor closeout 路径映射为 FAILED / LOST。

## 停止状态

S7 implementation 完成。未 commit、未 push、未创建 PR，未进入 review gate。
