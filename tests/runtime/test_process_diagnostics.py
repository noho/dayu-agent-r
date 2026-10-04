"""一次性真实 spawn worker 的诊断隔离、传输与收口 owner 合同。"""
from __future__ import annotations

import asyncio
import ctypes
import io
import json
import logging
import multiprocessing
import multiprocessing.util
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import BinaryIO, Protocol, cast
from types import FunctionType
from typing_extensions import Buffer

import pytest
from dayu.runtime import process_diagnostics as diagnostics
from dayu.runtime.process_diagnostics import (
    ProcessCaptureIncident, ProcessCaptureIncidentCode, ProcessDiagnosticsError,
    ProcessDiagnosticsFailureReason, ProcessLogDiagnostic, ProcessRawDiagnostic,
    capture_process_diagnostics, read_process_diagnostics,
)


class _FaultStream(io.BytesIO):
    """可在 writer 媒体的指定阶段产生普通错误或原控制流。"""
    def __init__(self, phase: str, error: BaseException) -> None:
        """参数：阶段/原异常；返回：无；异常：初始化错误传播。"""
        super().__init__(); self.phase = phase; self.error = error

    def write(self, data: Buffer) -> int:
        """参数：行字节；返回：真实写长度；异常：指定写故障原样传播。"""
        if self.phase == 'write': raise self.error
        return super().write(data)

    def flush(self) -> None:
        """参数：无；返回：无；异常：指定 flush 故障原样传播。"""
        if self.phase == 'flush': raise self.error
        super().flush()

    def close(self) -> None:
        """参数：无；返回：关闭后无；异常：指定 close 故障原样传播。"""
        super().close()
        if self.phase == 'close': raise self.error


class _RecursiveMessage:
    """消息投影中真实发起同线程日志。"""
    def __str__(self) -> str:
        """参数：无；返回：外层消息；异常：不主动抛出。"""
        logging.getLogger('late.recursive').warning('recursive inner')
        return 'recursive outer'


class _BlockingMessage:
    """阻塞投影以建立 reservation/close 实际交错。"""
    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        """参数：进入/释放事件；返回：无；异常：不主动抛出。"""
        self.entered = entered; self.release = release

    def __str__(self) -> str:
        """参数：无；返回：在途消息；异常：实际 wait 超时断言失败。"""
        self.entered.set(); assert self.release.wait(10)
        return 'reserved healthy'


class _BrokenException(Exception):
    """真实 traceback owner 的坏异常字符串负例。"""
    def __str__(self) -> str:
        """参数：无；返回：永不返回；异常：字符串方法失败。"""
        raise RuntimeError('bad exception str')


def _native_flush() -> None:
    """参数：无；返回：真实 libc flush；异常：无。"""
    ctypes.CDLL(None).fflush(None)


def _write_raw_after_scope() -> None:
    """参数：无；返回：framework finalizer 写入；异常：真实 fd 错误传播。"""
    os.write(1, b'framework finalizer\n'); _native_flush()


def _raise_dup2(fd: int, target: int) -> None:
    """参数：fd 对；返回：永不返回；异常：模拟 fd2/fd1 setup 失败。"""
    raise OSError('dup2 failure')


def _capture_worker(directory_name: str, mode: str) -> None:
    """参数：独占目录/场景；返回：真实 worker 完成；异常：owner 断言失败使 child 非零。"""
    directory = Path(directory_name)
    patch = pytest.MonkeyPatch()
    previous = logging.getLogger().manager.loggerClass
    existing = logging.getLogger('existing.owner'); existing.setLevel(logging.DEBUG)
    existing.addHandler(logging.StreamHandler(sys.stdout)); existing.propagate = False
    if mode == 'isolation':
        patch.setattr(diagnostics.os, 'dup2', _raise_dup2)
        try:
            with capture_process_diagnostics(directory): raise AssertionError('body must not execute')
        except ProcessDiagnosticsError as exc:
            assert exc.reason is ProcessDiagnosticsFailureReason.ISOLATION_SETUP
        finally: patch.undo()
        return
    if mode == 'media':
        (directory / 'records.jsonl').write_bytes(b'')
    with capture_process_diagnostics(directory):
        if mode in ('normal', 'media'):
            existing.warning('existing warning')
            late = logging.getLogger('late.owner'); late.setLevel(logging.DEBUG)
            late.addHandler(logging.StreamHandler(sys.stdout)); late.propagate = False
            late.warning('late warning')
            logging.getLogger().warning('root warning')
            os.write(1, b'raw WARNING\xff\n'); os.write(2, b'raw error\n')
            subprocess.run([sys.executable, '-c', 'import os;os.write(1,b"descendant\\n")'], check=True)
            threads = [threading.Thread(target=late.warning, args=('thread %s', i)) for i in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            # 无 newline 的 native 缓冲跨结构化 scope，必须仍落 raw。
            libc = ctypes.CDLL(None); libc.printf(b'native buffered')
            multiprocessing.util.Finalize(None, _write_raw_after_scope, exitpriority=0)
        elif mode == 'bad':
            logger = logging.getLogger('late.bad'); logger.setLevel(logging.DEBUG)
            logger.warning('%d', 'x')
            logger.warning('\ud800')
            logger.warning(_RecursiveMessage())
            for fields in ({'name': 3}, {'levelno': True}, {'created': True}, {'created': float('nan')},
                           {'created': float('inf')}, {'created': 10 ** 500}, {'stack_info': 2}):
                record = logging.LogRecord('bad', logging.WARNING, '', 0, 'bad', (), None)
                for name, value in fields.items(): setattr(record, name, value)
                logger.handle(record)
            record = logging.LogRecord('bad', logging.WARNING, '', 0, 'bad exc', (), None)
            record.exc_info = cast(tuple[type[BaseException], BaseException, None], (ValueError, ValueError('test'), 'bad-tb'))
            logger.handle(record)
            try: raise _BrokenException()
            except _BrokenException: logger.exception('real broken exception')
        elif mode == 'writer':
            for phase in ('write', 'flush', 'close'):
                stream = _FaultStream(phase, OSError('spool failed'))
                writer = diagnostics._DiagnosticWriter(cast(BinaryIO, stream))
                assert writer.try_capture(logging.LogRecord('writer', logging.WARNING, '', 0, 'fault', (), None))
                writer.begin_closing(); writer.wait_for_reservations(); writer.close()
                assert stream.closed
            writer = diagnostics._DiagnosticWriter(None)
            assert writer.try_capture(logging.LogRecord('writer', logging.WARNING, '', 0, 'drop', (), None))
            writer.begin_closing(); writer.close()
            assert writer.try_capture(logging.LogRecord('writer', logging.WARNING, '', 0, 'late', (), None)) is False
        elif mode == 'control':
            for error in (KeyboardInterrupt(), SystemExit(7), asyncio.CancelledError(), GeneratorExit()):
                stream = _FaultStream('write', error)
                writer = diagnostics._DiagnosticWriter(cast(BinaryIO, stream))
                try: writer.try_capture(logging.LogRecord('writer', logging.WARNING, '', 0, 'control', (), None))
                except BaseException as caught: assert caught is error
                else: raise AssertionError('control swallowed')
                assert writer._active == 0 and writer._projection.depth == 0
                stream.phase = 'none'; writer.begin_closing(); writer.wait_for_reservations(); writer.close()
    assert logging.getLogger().manager.loggerClass is previous
    assert not existing.filters
    existing.warning('after scope raw')
    Path(directory_name, 'identity.json').write_text(json.dumps({'pid': os.getpid(), 'module': diagnostics.__file__}))


def _spawn(directory: Path, mode: str) -> None:
    """参数：独占目录/场景；返回：join 后无；异常：异常退出/超时失败。"""
    worker = multiprocessing.get_context('spawn').Process(target=_capture_worker, args=(str(directory), mode))
    worker.start(); worker.join(30)
    try:
        if worker.is_alive(): worker.kill(); worker.join(); raise AssertionError('worker timeout')
        assert worker.exitcode == 0, (directory / 'stderr.bin').read_bytes() if (directory / 'stderr.bin').exists() else mode
    finally: worker.close()


@pytest.mark.parametrize('mode', ['normal', 'bad', 'writer', 'control', 'media', 'isolation'])
def test_real_spawn_capture_contract(tmp_path: Path, mode: str, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：目录/场景/公开双流；返回：无；异常：隔离、等级、字段或故障合同违例失败。"""
    _spawn(tmp_path, mode)
    public = capfd.readouterr(); assert public.out == public.err == ''
    if mode in ('media', 'isolation'): return
    values = list(read_process_diagnostics(tmp_path, require_complete=True))
    records = [value for value in values if isinstance(value, ProcessLogDiagnostic)]
    if mode == 'normal':
        assert len(records) == 11 and all(record.source_level == logging.WARNING for record in records)
        raw = b''.join(value.data for value in values if isinstance(value, ProcessRawDiagnostic))
        for expected in (b'raw WARNING\xff', b'raw error', b'descendant', b'after scope raw', b'native buffered', b'framework finalizer'): assert expected in raw
    if mode == 'bad':
        incidents = [value.code for value in values if isinstance(value, ProcessCaptureIncident)]
        assert incidents.count(ProcessCaptureIncidentCode.RECORD_VALIDATION) == 7
        assert ProcessCaptureIncidentCode.RECORD_FORMAT in incidents
        assert ProcessCaptureIncidentCode.RECORD_ENCODING in incidents
        assert ProcessCaptureIncidentCode.RECURSIVE_RECORD in incidents
        assert len(records) == 2 and '<exception str() failed>' in records[-1].message
    assert json.loads((tmp_path / 'identity.json').read_text())['module'] == str(Path(diagnostics.__file__).resolve())


class _ObservedCondition(threading.Condition):
    """只观察等待入口，所有锁操作及等待仍由真实 stdlib Condition 执行。"""

    def __init__(self) -> None:
        """参数：无；返回：无；异常：真实同步设施初始化错误传播。"""
        super().__init__(threading.Lock())
        self.wait_entered = threading.Event()

    def wait(self, timeout: float | None = None) -> bool:
        """参数：超时；返回：真实等待结果；异常：stdlib 等待异常原样传播。"""
        self.wait_entered.set()
        return super().wait(timeout)


def _release_after_scope_wait(root: Path, condition: _ObservedCondition, release: threading.Event,
                              scope_done: threading.Event, failures: list[BaseException]) -> None:
    """参数：目录/真实 condition/释放/完成事件/失败列表；返回：观察后放行；异常：保失败供主线程断言。"""
    try:
        assert condition.wait_entered.wait(10), 'scope exit never entered Condition.wait'
        # scope 持有 Condition 锁进入 wait。观察线程取得此锁证明真实 wait 已释放它，
        # 而投影仍由 release barrier 阻塞；仅入口事件或线程存活都不足以证明这一点。
        with condition:
            assert not release.is_set() and not scope_done.is_set()
            before_release = (root / 'records.jsonl').read_bytes()
            assert before_release == b'', 'footer appeared before reservation completed'
            (root / 'wait-proof.json').write_text(json.dumps({
                'actual_condition_wait_released_lock': True, 'scope_done_before_release': False,
                'records_before_release': [], 'emitter_released': False,
            }))
    except BaseException as exc:
        failures.append(exc)
    finally:
        release.set()


def _concurrency_worker(directory: str) -> None:
    """参数：独占目录；返回：真实 scope 收口后无；异常：确定性等待或 record/footer 顺序错误失败。"""
    root = Path(directory); condition = _ObservedCondition()
    entered = threading.Event(); release = threading.Event(); scope_done = threading.Event()
    failures: list[BaseException] = []
    with capture_process_diagnostics(root):
        writer = diagnostics._CapturingLogger.writer; assert writer is not None
        writer._condition = condition
        logger = logging.getLogger('race'); logger.setLevel(logging.WARNING)
        emit = threading.Thread(target=logger.warning, args=(_BlockingMessage(entered, release),))
        emit.start(); assert entered.wait(10)
        observer = threading.Thread(target=_release_after_scope_wait,
                                    args=(root, condition, release, scope_done, failures))
        observer.start()
        # 不提前 release/join emitter；真实 context manager exit 必须等待其 reservation。
    scope_done.set(); observer.join(10); emit.join(10)
    assert not failures, failures
    assert not observer.is_alive() and not emit.is_alive()
    assert json.loads((root / 'wait-proof.json').read_text())['actual_condition_wait_released_lock']
    lines = [json.loads(line) for line in (root / 'records.jsonl').read_bytes().splitlines()]
    assert [line['kind'] for line in lines] == ['log', 'end']
    assert lines[0]['message'] == 'reserved healthy'


def test_reserved_emit_completes_before_footer(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：独占目录/双流；返回：无；异常：并发 healthy reservation 丢失或锁未释放失败。"""
    worker = multiprocessing.get_context('spawn').Process(target=_concurrency_worker, args=(str(tmp_path),))
    worker.start(); worker.join(30)
    try: assert worker.exitcode == 0
    finally:
        if worker.is_alive(): worker.kill(); worker.join()
        worker.close()
    public = capfd.readouterr(); assert public.out == public.err == ''


_VALID = {'schema_version': 1, 'kind': 'log', 'source_name': 'third', 'source_level': 30, 'message': 'message', 'created_at': 123.0}
_END_LINE = b'{"schema_version":1,"kind":"end"}\n'


@pytest.mark.parametrize('bad', [b'bad\n', b'{}\n', b'{"schema_version":true,"kind":"end"}\n',
                                b'{"schema_version":2,"kind":"end"}\n', b'{"schema_version":1,"kind":"capture_incident","code":"bad"}\n'])
def test_reader_invalid_schema(tmp_path: Path, bad: bytes) -> None:
    """参数：目录/非法完整行；返回：无；异常：非法 schema 被接收时失败。"""
    (tmp_path / 'records.jsonl').write_bytes(bad)
    with pytest.raises(ProcessDiagnosticsError) as error: list(read_process_diagnostics(tmp_path, require_complete=True))
    assert error.value.reason is ProcessDiagnosticsFailureReason.TRANSPORT_INVALID


@pytest.mark.parametrize('field,value', [('source_level', True), ('source_name', 2), ('message', False), ('created_at', True), ('created_at', float('nan')), ('extra', 0)])
def test_reader_strict_record_fields(tmp_path: Path, field: str, value: str | int | bool | float) -> None:
    """参数：非法字段；返回：无；异常：类型或 exact keys 校验缺失时失败。"""
    record = dict(_VALID); record[field] = value
    (tmp_path / 'records.jsonl').write_text(json.dumps(record) + '\n')
    with pytest.raises(ProcessDiagnosticsError) as error: list(read_process_diagnostics(tmp_path, require_complete=False))
    assert error.value.reason is ProcessDiagnosticsFailureReason.TRANSPORT_INVALID


@pytest.mark.parametrize('require_complete', [True, False])
@pytest.mark.parametrize('tail', [b'', b'{"partial"', _END_LINE + b'after footer\n'])
def test_read_strategy_and_incomplete_prefix(tmp_path: Path, require_complete: bool, tail: bytes) -> None:
    """参数：目录/读取策略/坏尾部；返回：无；异常：正常模式泄前缀或取消模式隐瞒缺口失败。"""
    (tmp_path / 'records.jsonl').write_bytes((json.dumps(_VALID) + '\n').encode() + tail)
    reader = read_process_diagnostics(tmp_path, require_complete=require_complete)
    if not require_complete: assert next(reader) == ProcessLogDiagnostic('third', 30, 'message', 123.0)
    with pytest.raises(ProcessDiagnosticsError) as error: next(reader)
    assert error.value.reason is (ProcessDiagnosticsFailureReason.TRANSPORT_INVALID if tail.startswith(_END_LINE) else ProcessDiagnosticsFailureReason.TRANSPORT_INCOMPLETE)


def test_read_raw_chunks_and_missing_media(tmp_path: Path) -> None:
    """参数：目录；返回：无；异常：固定块/偏移或缺媒体原因漂移失败。"""
    with pytest.raises(ProcessDiagnosticsError) as error: list(read_process_diagnostics(tmp_path, require_complete=True))
    assert error.value.reason is ProcessDiagnosticsFailureReason.TRANSPORT_READ
    (tmp_path / 'records.jsonl').write_bytes(_END_LINE)
    (tmp_path / 'stdout.bin').write_bytes(b'x' * (64 * 1024 + 1)); (tmp_path / 'stderr.bin').write_bytes(b'')
    raw = list(read_process_diagnostics(tmp_path, require_complete=True))
    assert raw == [ProcessRawDiagnostic('stdout', b'x' * (64 * 1024), 0), ProcessRawDiagnostic('stdout', b'x', 64 * 1024)]
    (tmp_path / 'stderr.bin').unlink()
    with pytest.raises(ProcessDiagnosticsError) as error: list(read_process_diagnostics(tmp_path, require_complete=True))
    assert error.value.reason is ProcessDiagnosticsFailureReason.TRANSPORT_READ


def test_independent_interpreter_native_exit_flush(tmp_path: Path) -> None:
    """参数：独占目录；返回：无；异常：正常解释器退出 native 自动 flush 外泄失败。"""
    script = 'import ctypes,sys;from pathlib import Path;from dayu.runtime.process_diagnostics import capture_process_diagnostics\nwith capture_process_diagnostics(Path(sys.argv[1])): ctypes.CDLL(None).printf(b"native normal exit")'
    completed = subprocess.run([sys.executable, '-c', script, str(tmp_path)], capture_output=True, check=False)
    assert completed.returncode == 0 and completed.stdout == completed.stderr == b''
    assert b'native normal exit' in (tmp_path / 'stdout.bin').read_bytes()


class _ControlMessage:
    """真实 getMessage 调用字符串转换时产生指定控制流。"""

    def __init__(self, error: BaseException) -> None:
        """参数：原控制流；返回：无；异常：无。"""
        self.error = error

    def __str__(self) -> str:
        """参数：无；返回：不返回；异常：传播原控制流对象。"""
        raise self.error


class _ControlRecord(logging.LogRecord):
    """直接验证 getMessage owner 的控制流。"""
    error: BaseException

    def getMessage(self) -> str:
        """参数：无；返回：不返回；异常：传播原控制流对象。"""
        raise self.error


def _control_error(kind: str) -> BaseException:
    """参数：封闭测试种类；返回：本 worker 的控制流对象；异常：未知种类 KeyError。"""
    return {'keyboard': KeyboardInterrupt(), 'exit': SystemExit(7),
            'cancel': asyncio.CancelledError(), 'generator': GeneratorExit()}[kind]


def _projection_control_worker(directory: str, kind: str, route: str) -> None:
    """参数：独占目录/种类/真实投影入口；返回：无；异常：同对象或 reservation/depth 回收错误失败。"""
    error = _control_error(kind)
    with capture_process_diagnostics(Path(directory)):
        writer = diagnostics._CapturingLogger.writer
        assert writer is not None
        logger = logging.getLogger('control.projection'); logger.setLevel(logging.WARNING)
        try:
            if route == 'str':
                logger.warning(_ControlMessage(error))
            else:
                record = _ControlRecord('control.projection', logging.WARNING, '', 0, 'ignored', (), None)
                record.error = error
                logger.handle(record)
        except BaseException as caught:
            assert caught is error
        else:
            raise AssertionError('projection control swallowed')
        assert writer._active == 0 and writer._projection.depth == 0
        logger.warning('healthy after control')
    values = list(read_process_diagnostics(Path(directory), require_complete=True))
    assert [v.message for v in values if isinstance(v, ProcessLogDiagnostic)] == ['healthy after control']
    assert not any(isinstance(v, ProcessCaptureIncident) for v in values)


@pytest.mark.parametrize('kind', ['keyboard', 'exit', 'cancel', 'generator'])
@pytest.mark.parametrize('route', ['getMessage', 'str'])
def test_capture_projection_control_identity(tmp_path: Path, kind: str, route: str, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：目录/控制流/入口/双流；返回：无；异常：真实 worker 投影吞对象或资源泄漏失败。"""
    worker = multiprocessing.get_context('spawn').Process(target=_projection_control_worker, args=(str(tmp_path), kind, route))
    worker.start(); worker.join(30)
    try:
        assert worker.exitcode == 0
    finally:
        if worker.is_alive(): worker.kill(); worker.join()
        worker.close()
    public = capfd.readouterr(); assert public.out == public.err == ''


class _CleanupStream:
    """持有真实 fd，执行实际回收后再产生指定控制流。"""

    def __init__(self, stream: BinaryIO, phase: str, error: BaseException) -> None:
        """参数：真实文件/故障阶段/原对象；返回：无；异常：无。"""
        self.stream = stream; self.phase = phase; self.error = error

    def fileno(self) -> int:
        """参数：无；返回：真实 fd；异常：关闭文件 ValueError。"""
        return self.stream.fileno()

    def write(self, data: Buffer) -> int:
        """参数：完整行；返回：真实写长度；异常：指定 footer 写控制流。"""
        if self.phase == 'write': raise self.error
        return self.stream.write(data)

    def flush(self) -> None:
        """参数：无；返回：真实 flush；异常：指定 flush 控制流。"""
        if self.phase == 'flush': raise self.error
        self.stream.flush()

    def close(self) -> None:
        """参数：无；返回：真实关闭；异常：关闭后指定控制流。"""
        self.stream.close()
        if self.phase == 'close': raise self.error


class _TestFilter(Protocol):
    """标准 logging 支持的结构化 filter 接口。"""

    def filter(self, record: logging.LogRecord, /) -> bool:
        """参数：记录；返回：允许与否；异常：实现约定。"""
        ...


class _CleanupLogger(logging.Logger):
    """撤销真实 filter 后产生控制流，允许验证其它 logger 仍撤销。"""
    removal_error: BaseException | None = None
    setup_error: BaseException | None = None

    def addFilter(self, filter: _TestFilter | FunctionType) -> None:
        """参数：真实 filter；返回：正常安装；异常：安装前指定 setup 原控制流。"""
        if self.setup_error is not None:
            raise self.setup_error
        super().addFilter(filter)

    def removeFilter(self, filter: _TestFilter | FunctionType) -> None:
        """参数：真实 filter；返回：无；异常：实际撤销后指定原对象。"""
        super().removeFilter(filter)
        if self.removal_error is not None:
            raise self.removal_error


def _scope_cleanup_worker(directory: str, kind: str, phase: str, body_kind: str) -> None:
    """参数：目录/控制流/清理阶段/body优先级；返回：无；异常：首对象或资源回收不满足失败。"""
    root = Path(directory); error = _control_error(kind); second = SystemExit(19)
    body_error = _control_error(kind) if body_kind == 'control' else ValueError('body') if body_kind == 'ordinary' else None
    patch = pytest.MonkeyPatch(); streams: list[_CleanupStream] = []
    original_open = diagnostics._open_private; original_flush = diagnostics._flush_standard_streams
    flush_calls = 0
    old_class = logging.getLogger().manager.loggerClass
    logging.getLogger().manager.setLoggerClass(_CleanupLogger)
    first = logging.getLogger('cleanup.first'); other = logging.getLogger('cleanup.other')
    assert isinstance(first, _CleanupLogger)
    if phase in ('teardown', 'incident'):
        first.removal_error = error if phase == 'teardown' else OSError('remove fault')
    if phase in ('setup_filter', 'setup_filter_cleanup'):
        first.setup_error = error
    def open_stream(path: Path) -> BinaryIO:
        """参数：scope文件；返回：真实包装句柄；异常：指定 open 控制流。"""
        if phase in ('records_open', 'records_open_cleanup') and path.name == 'records.jsonl': raise error
        fault = 'none'
        selected = error
        if path.name == 'records.jsonl' and phase.startswith('records_'):
            fault = phase.removeprefix('records_')
        if phase in ('raw_close', 'records_open_cleanup', 'setup_filter_cleanup') and path.name in ('stderr.bin', 'stdout.bin'):
            fault = 'close'; selected = error if path.name == 'stderr.bin' else second
            if phase != 'raw_close': selected = second
        wrapped = _CleanupStream(original_open(path), fault, selected); streams.append(wrapped)
        return cast(BinaryIO, wrapped)
    def flush_standard() -> None:
        """参数：无；返回：实际双流 flush；异常：退出 flush 控制流。"""
        nonlocal flush_calls
        flush_calls += 1
        original_flush()
        if phase == 'stdio' and flush_calls == 2: raise error
    def begin(writer: diagnostics._DiagnosticWriter) -> None:
        """参数：writer；返回：真实状态变更；异常：变更后指定控制流。"""
        original_begin(writer); raise error
    def wait(writer: diagnostics._DiagnosticWriter) -> None:
        """参数：writer；返回：实际 reservation 收口；异常：收口后指定控制流。"""
        original_wait(writer); raise error
    def incident(writer: diagnostics._DiagnosticWriter, code: ProcessCaptureIncidentCode) -> None:
        """参数：真实 writer/阶段；返回：无；异常：撤销故障报告中的控制流。"""
        raise error
    original_begin = diagnostics._DiagnosticWriter.begin_closing
    original_wait = diagnostics._DiagnosticWriter.wait_for_reservations
    patch.setattr(diagnostics, '_open_private', open_stream)
    patch.setattr(diagnostics, '_flush_standard_streams', flush_standard)
    if phase == 'begin': patch.setattr(diagnostics._DiagnosticWriter, 'begin_closing', begin)
    if phase == 'wait': patch.setattr(diagnostics._DiagnosticWriter, 'wait_for_reservations', wait)
    if phase == 'incident': patch.setattr(diagnostics._DiagnosticWriter, 'note_incident', incident)
    try:
        try:
            with capture_process_diagnostics(root):
                if body_error is not None: raise body_error
        except BaseException as caught:
            setup_phase = phase in ('records_open', 'records_open_cleanup', 'setup_filter', 'setup_filter_cleanup')
            assert caught is (body_error if body_kind == 'control' and not setup_phase else error)
        else:
            raise AssertionError('cleanup control swallowed')
        assert all(s.stream.closed for s in streams)
        assert diagnostics._CapturingLogger.writer is None
        assert logging.getLogger().manager.loggerClass is _CleanupLogger
        assert not first.filters and not other.filters
        (root / 'cleanup-proof.json').write_text(json.dumps({'phase': phase, 'same_object': True, 'closed': len(streams), 'filters_removed': True}))
    finally:
        patch.undo(); first.removal_error = None
        logging.getLogger().manager.loggerClass = old_class


@pytest.mark.parametrize('kind', ['keyboard', 'exit', 'cancel', 'generator'])
@pytest.mark.parametrize('phase', ['begin', 'teardown', 'wait', 'stdio', 'raw_close', 'records_write', 'records_flush', 'records_close', 'records_open', 'incident', 'setup_filter', 'records_open_cleanup', 'setup_filter_cleanup'])
@pytest.mark.parametrize('body_kind', ['none', 'ordinary', 'control'])
def test_scope_cleanup_preserves_first_control_and_reclaims(tmp_path: Path, kind: str, phase: str, body_kind: str, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：目录/阶段/body与cleanup控制流/双流；返回：无；异常：同对象或真实资源回收违例失败。"""
    worker = multiprocessing.get_context('spawn').Process(target=_scope_cleanup_worker, args=(str(tmp_path), kind, phase, body_kind))
    worker.start(); worker.join(30)
    try:
        assert worker.exitcode == 0, (tmp_path / 'stderr.bin').read_bytes() if (tmp_path / 'stderr.bin').exists() else phase
        assert json.loads((tmp_path / 'cleanup-proof.json').read_text())['same_object']
    finally:
        if worker.is_alive(): worker.kill(); worker.join()
        worker.close()
    public = capfd.readouterr(); assert public.out == public.err == ''


def _observe_private_stream(open_private: Callable[[Path], BinaryIO], streams: list[BinaryIO], path: Path) -> BinaryIO:
    """参数：真实打开函数、观察列表、文件路径；返回：原文件句柄；异常：真实打开错误原样传播。"""
    stream = open_private(path)
    streams.append(stream)
    return stream


def _ordinary_body_error_worker(directory: str) -> None:
    """参数：独占目录；返回：健康清理后无；异常：普通 body 异常身份、回收或完整传输违例失败。"""
    root = Path(directory)
    manager = logging.getLogger().manager
    previous_class = manager.loggerClass
    existing = logging.getLogger('ordinary.body')
    existing.setLevel(logging.WARNING)
    existing.propagate = False
    existing.addHandler(logging.StreamHandler(sys.stdout))
    loggers = [logging.getLogger(), *(value for value in manager.loggerDict.values()
                                     if isinstance(value, logging.Logger))]
    previous_filters = [(logger, tuple(logger.filters)) for logger in loggers]
    streams: list[BinaryIO] = []
    error = ValueError('ordinary body error')
    caught: BaseException | None = None
    patch = pytest.MonkeyPatch()
    # 仅保存真实句柄引用；不包装媒体、不替代写入或清理，也不注入故障。
    patch.setattr(diagnostics, '_open_private', partial(_observe_private_stream, diagnostics._open_private, streams))
    try:
        try:
            with capture_process_diagnostics(root):
                existing.warning('before ordinary body error')
                os.write(1, b'ordinary body stdout\n')
                os.write(2, b'ordinary body stderr\n')
                raise error
        except BaseException as exc:
            caught = exc
        assert len(streams) == 3 and all(stream.closed for stream in streams)
        assert diagnostics._CapturingLogger.writer is None
        assert manager.loggerClass is previous_class
        assert all(tuple(logger.filters) == filters for logger, filters in previous_filters)
        values = list(read_process_diagnostics(root, require_complete=True))
        assert [value for value in values if isinstance(value, ProcessCaptureIncident)] == []
        assert [value.message for value in values if isinstance(value, ProcessLogDiagnostic)] == ['before ordinary body error']
        assert [value for value in values if isinstance(value, ProcessRawDiagnostic)] == [
            ProcessRawDiagnostic('stdout', b'ordinary body stdout\n', 0),
            ProcessRawDiagnostic('stderr', b'ordinary body stderr\n', 0),
        ]
        lines = (root / 'records.jsonl').read_bytes().split(b'\n')
        assert len(lines) == 3 and lines[-1] == b''
        assert json.loads(lines[-2]) == {'schema_version': 1, 'kind': 'end'}
        with (root / 'ordinary-body-proof.json').open('x') as stream:
            json.dump({'same_object': caught is error, 'closed_streams': len(streams),
                       'logger_state_restored': True, 'footer_complete': True}, stream)
        assert caught is error, 'ordinary body ValueError must propagate as the same object'
    finally:
        patch.undo()


def test_scope_preserves_ordinary_body_error_with_healthy_cleanup(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：独占目录、父双流捕获；返回：无；异常：真实单次 spawn 的异常、回收或公开流合同违例失败。"""
    worker = multiprocessing.get_context('spawn').Process(target=_ordinary_body_error_worker, args=(str(tmp_path),))
    worker.start()
    worker.join(30)
    try:
        assert worker.exitcode == 0, (tmp_path / 'stderr.bin').read_bytes()
        assert json.loads((tmp_path / 'ordinary-body-proof.json').read_text())['same_object'] is True
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join()
        worker.close()
    public = capfd.readouterr()
    assert public.out == public.err == ''


def _outer_handled_control_worker(directory: str, kind: str) -> None:
    """参数：独占目录/外层控制流种类；返回：正常 scope 后无；异常：外层已处理对象被误抛时失败。"""
    root = Path(directory); error = _control_error(kind)
    try:
        raise error
    except BaseException as caught:
        assert caught is error
        with capture_process_diagnostics(root):
            logging.getLogger('outer.handled').warning('normal scope body')
        # 此处仍在外层 except；本 scope 没有异常，不能重抛当前线程活跃异常。
        assert sys.exception() is error
    values = list(read_process_diagnostics(root, require_complete=True))
    assert [v.message for v in values if isinstance(v, ProcessLogDiagnostic)] == ['normal scope body']
    (root / 'outer-handled-proof.json').write_text(json.dumps({'kind': kind, 'scope_raised': False, 'footer_complete': True}))


@pytest.mark.parametrize('kind', ['keyboard', 'exit', 'cancel', 'generator'])
def test_scope_ignores_outer_handled_control(tmp_path: Path, kind: str, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：目录/外层控制流/双流；返回：无；异常：独立单次 scope 误传播外层已处理对象失败。"""
    worker = multiprocessing.get_context('spawn').Process(target=_outer_handled_control_worker, args=(str(tmp_path), kind))
    worker.start(); worker.join(30)
    try:
        assert worker.exitcode == 0
        assert json.loads((tmp_path / 'outer-handled-proof.json').read_text())['scope_raised'] is False
    finally:
        if worker.is_alive(): worker.kill(); worker.join()
        worker.close()
    public = capfd.readouterr(); assert public.out == public.err == ''


def _closing_routes_worker(directory: str) -> None:
    """参数：独占目录；返回：无；异常：CLOSING stale filter/class 路由或 healthy reservation/footer 错误失败。"""
    root = Path(directory); existing = logging.getLogger('closing.existing')
    existing.setLevel(logging.WARNING); existing.propagate = False
    existing.addHandler(logging.StreamHandler(sys.stdout))
    with capture_process_diagnostics(root):
        writer = diagnostics._CapturingLogger.writer; assert writer is not None
        stale = existing.filters[-1]; assert isinstance(stale, diagnostics._ExistingLoggerCaptureFilter)
        late = logging.getLogger('closing.late'); late.setLevel(logging.WARNING)
        late.propagate = False; late.addHandler(logging.StreamHandler(sys.stderr))
        entered = threading.Event(); released = threading.Event()
        thread = threading.Thread(target=late.warning, args=(_BlockingMessage(entered, released),))
        thread.start(); assert entered.wait(10)
        writer.begin_closing()
        existing.warning('closing stale goes raw stdout')
        late.warning('closing class goes raw stderr')
        released.set(); thread.join(10); assert not thread.is_alive()
    record = logging.LogRecord('after', logging.WARNING, '', 0, 'after closed', (), None)
    assert stale.filter(record) is True
    values = list(read_process_diagnostics(root, require_complete=True))
    assert [v.message for v in values if isinstance(v, ProcessLogDiagnostic)] == ['reserved healthy']
    raw = b''.join(v.data for v in values if isinstance(v, ProcessRawDiagnostic))
    assert b'closing stale goes raw stdout' in raw and b'closing class goes raw stderr' in raw
    lines = [json.loads(line) for line in (root / 'records.jsonl').read_bytes().splitlines()]
    assert [v['kind'] for v in lines] == ['log', 'end']


def test_closing_stale_filters_and_late_class_keep_original_raw_boundary(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：独占目录/双流；返回：无；异常：真实交错的 reservation 丢失或 late 公开逃逸失败。"""
    worker = multiprocessing.get_context('spawn').Process(target=_closing_routes_worker, args=(str(tmp_path),))
    worker.start(); worker.join(30)
    try: assert worker.exitcode == 0
    finally:
        if worker.is_alive(): worker.kill(); worker.join()
        worker.close()
    public = capfd.readouterr(); assert public.out == public.err == ''
