"""仅观察所 spawn bare CLI 的真实巨潮 HTTP；不改变请求、响应或业务返回。"""

from __future__ import annotations

import argparse
import atexit
from collections import Counter
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock
from typing import Callable, cast
from urllib.parse import parse_qs

import httpcore
import httpx

from dayu.contracts.json_value import JsonValue
from dayu.fins.downloaders.cninfo_downloader import _parse_raw_announcement, CNINFO_QUERY_URL, JsonValue as ProviderJsonValue

_REPO = Path(__file__).resolve().parents[1]
_RUN_ENV = 'DAYU_601225_HTTP_RUN'
_PID_ENV = 'DAYU_601225_HTTP_PID'
_HOSTS = frozenset(('www.cninfo.com.cn', 'static.cninfo.com.cn'))
_SEQ: ContextVar[int | None] = ContextVar('dayu_http_observer_seq', default=None)


@dataclass
class _Observer:
    """当前 CLI PID 的观察状态；所有可变记录在锁内更新。"""

    root: Path
    pid: int
    guard: Lock = field(default_factory=Lock)
    seq: int = 0
    errors: int = 0
    seen: set[httpx.Response] = field(default_factory=set)
    original_transport: Callable[[httpx.HTTPTransport, httpx.Request], httpx.Response] = httpx.HTTPTransport.handle_request
    original_read: Callable[[httpx.Response], bytes] = httpx.Response.read
    original_headers: Callable[[httpcore.HTTP11Connection, httpcore.Request], None] = httpcore.HTTP11Connection._send_request_headers

    def emit(self, record: dict[str, JsonValue]) -> None:
        """追加辅助证据。参数：record 为有界字段。返回：无。异常：捕获 I/O 记录为观察失败。"""
        try:
            with self.guard:
                with (self.root / 'http.jsonl').open('a') as output:
                    output.write(json.dumps({'pid': self.pid, 'utc': datetime.now(timezone.utc).isoformat(), **record}, ensure_ascii=False)+'\n')
        except OSError:
            self.errors += 1


_STATE: _Observer | None = None


def _observed_transport(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
    """透传真实 transport。参数：transport/request。返回：原 response。异常：原异常透传。"""
    assert _STATE is not None
    state = _STATE
    transport = self
    if request.url.host not in _HOSTS:
        return state.original_transport(transport, request)
    with state.guard:
        state.seq += 1
        seq = state.seq
    state.emit({'kind': 'transport_request', 'seq': seq, 'method': request.method, 'url': str(request.url)})
    token = _SEQ.set(seq)
    try:
        response = state.original_transport(transport, request)
    except BaseException as exc:
        state.emit({'kind': 'transport_error', 'seq': seq, 'error_type': type(exc).__name__})
        raise
    finally:
        _SEQ.reset(token)
    state.emit({'kind': 'transport_response', 'seq': seq, 'status': response.status_code,
                'location': response.headers.get('location'), 'http_version': cast(bytes,response.extensions.get('http_version', b'')).decode()})
    return response


def _observed_headers(self: httpcore.HTTP11Connection, request: httpcore.Request) -> None:
    """原发送成功后观察。参数：connection/request。返回：无。异常：原发送异常透传。"""
    assert _STATE is not None
    _STATE.original_headers(self, request)
    if request.url.host.decode('ascii') in _HOSTS:
        _STATE.emit({'kind': 'wire_sent', 'seq': _SEQ.get(), 'method': request.method.decode('ascii'),
                     'host': request.url.host.decode('ascii'), 'target': request.url.target.decode('ascii')})


def _observed_read(self: httpx.Response) -> bytes:
    """先调用原 read 后保存 query raw。参数：response。返回：同一 bytes。异常：原 read 异常透传。"""
    assert _STATE is not None
    state = _STATE
    response = self
    payload = state.original_read(response)
    if response.request.method == 'POST' and str(response.request.url) == CNINFO_QUERY_URL:
        with state.guard:
            if response in state.seen:
                return payload
            state.seen.add(response)
            index = len(state.seen)
        try:
            name = f'query-{index:03d}.response.bin'
            (state.root / name).write_bytes(payload)
            form: dict[str, JsonValue] = {key: [v for v in values] for key, values in parse_qs(response.request.content.decode(), keep_blank_values=True).items()}
            state.emit({'kind': 'query_body', 'filename': name, 'sha256': hashlib.sha256(payload).hexdigest(), 'form': form})
        except Exception as exc:
            state.errors += 1
            state.emit({'kind': 'observer_error', 'error_type': type(exc).__name__})
    return payload


def _finished() -> None:
    """记录正常解释器结束与 hook 完整性。参数：无。返回：无。异常：无。"""
    assert _STATE is not None
    _STATE.emit({'kind': 'observer_finished', 'seq_count': _STATE.seq, 'error_count': _STATE.errors,
                 'hooks_intact': httpx.HTTPTransport.handle_request is _observed_transport
                 and httpx.Response.read is _observed_read and httpcore.HTTP11Connection._send_request_headers is _observed_headers})


def install_observer() -> None:
    """sitecustomize 装载 scoped hook，后代 PID 不装 hook。

    参数：从专用 env 读取独立 run-dir。返回：无。异常：装载错误写 observer_error，供父进程拒绝验收。
    """
    global _STATE
    root = os.environ.get(_RUN_ENV)
    if root is None or os.environ.get(_PID_ENV) is not None:
        return
    os.environ[_PID_ENV] = str(os.getpid())
    _STATE = _Observer(Path(root), os.getpid())
    try:
        if httpx.__version__ != '0.28.1' or httpcore.__version__ != '1.0.9':
            raise ValueError('HTTP dependency pin mismatch')
        if tuple(inspect.signature(httpcore.HTTP11Connection._send_request_headers).parameters) != ('self','request'):
            raise ValueError('HTTP wire signature mismatch')
        httpx.HTTPTransport.handle_request = _observed_transport
        httpx.Response.read = _observed_read
        httpcore.HTTP11Connection._send_request_headers = _observed_headers
        _STATE.emit({'kind': 'observer_started', 'argv': [str(v) for v in sys.argv], 'httpx': httpx.__version__, 'httpcore': httpcore.__version__})
        atexit.register(_finished)
    except Exception as exc:
        _STATE.errors += 1
        _STATE.emit({'kind': 'observer_error', 'error_type': type(exc).__name__})


def _read_json(path: Path) -> JsonValue:
    """读取辅助 JSON。参数：path。返回：JSON value。异常：I/O/JSON 原异常。"""
    return cast(JsonValue, json.loads(path.read_bytes()))



def _canonical_rows(rows: list[JsonValue], keys: tuple[str, ...]) -> list[str]:
    """比较官方集合的原始稳定字段。参数：raw rows及字段名。返回：排序规范表示。异常：非object拒绝。"""
    if any(not isinstance(row,Mapping) for row in rows):
        raise ValueError('official raw row malformed')
    return sorted(json.dumps({key:row.get(key) for key in keys},sort_keys=True,ensure_ascii=False) for row in rows if isinstance(row,Mapping))

def summarize_http(run_dir: Path, pid: int) -> dict[str, JsonValue]:
    """对账 wire、transport、raw 页及精确来源 locator。

    参数：run_dir/pid 为本次 CLI 证据。返回：辅助核验结果。异常：无效证据 ValueError。
    """
    events: list[Mapping[str, JsonValue]] = []
    errors: list[JsonValue] = []
    for line in (run_dir/'http.jsonl').read_text().splitlines():
        value = cast(JsonValue, json.loads(line))
        if not isinstance(value, Mapping) or value.get('pid') != pid:
            raise ValueError('observer PID/record mismatch')
        events.append(value)
    started = [e for e in events if e.get('kind') == 'observer_started']
    finished = [e for e in events if e.get('kind') == 'observer_finished']
    if len(started)!=1 or len(finished)!=1 or finished[0].get('hooks_intact') is not True or finished[0].get('error_count') != 0:
        errors.append('observer_lifecycle_incomplete')
    requests = {e['seq']:e for e in events if e.get('kind') == 'transport_request' and isinstance(e.get('seq'), int)}
    responses = {e['seq']:e for e in events if e.get('kind') in ('transport_response','transport_error') and isinstance(e.get('seq'),int)}
    wire = [e for e in events if e.get('kind') == 'wire_sent']
    if set(requests)!=set(responses) or len(wire)!=len(requests) or {cast(int,e['seq']) for e in wire if isinstance(e.get('seq'),int)}!=set(requests):
        errors.append('transport_wire_not_closed')
    if finished and finished[0].get('seq_count')!=len(requests):
        errors.append('observer_seq_count_mismatch')
    if any(e.get('kind')=='transport_response' and e.get('http_version')!='HTTP/1.1' for e in events):
        errors.append('unsupported_http_version')
    for e in wire:
        seq=e.get('seq')
        if not isinstance(seq,int) or seq not in requests:
            errors.append('unassociated_wire');continue
        req=requests[seq];url=req.get('url')
        if not isinstance(url,str):raise ValueError('request URL missing')
        parsed=httpx.URL(url)
        if e.get('method')!=req.get('method') or e.get('host')!=parsed.host or e.get('target')!=parsed.raw_path.decode():
            errors.append('wire_request_mismatch')
    locators: dict[str,str]={};annual_rows:list[JsonValue]=[];pages:dict[str,list[tuple[int,bool,int,int]]]={}
    for e in events:
        if e.get('kind')!='query_body':continue
        filename=e.get('filename');form=e.get('form')
        if not isinstance(filename,str) or not isinstance(form,Mapping):raise ValueError('raw record malformed')
        payload=(run_dir/filename).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=e.get('sha256'):errors.append('raw_hash_mismatch')
        raw=cast(JsonValue,json.loads(payload))
        if not isinstance(raw,Mapping):raise ValueError('query not object')
        items=raw.get('announcements');category=form.get('category');page=form.get('pageNum')
        if not isinstance(category,list) or not category or not isinstance(category[0],str) or not isinstance(page,list) or not isinstance(page[0],str):raise ValueError('query form incomplete')
        rows=items if isinstance(items,list) else []
        more=raw.get('hasMore');total=raw.get('totalRecordNum')
        if not isinstance(more,bool) or not isinstance(total,int):raise ValueError('raw pagination malformed')
        pages.setdefault(category[0],[]).append((int(page[0]),more,total,len(rows)))
        for item in rows:
            # HTTP raw parser 是 provider URL 唯一真源；不从 PDF URL 截取 ID。
            parsed=_parse_raw_announcement(cast(ProviderJsonValue, item))
            if parsed is not None:
                if parsed.source_url in locators and locators[parsed.source_url]!=parsed.announcement_id:errors.append('locator_collision')
                locators[parsed.source_url]=parsed.announcement_id
            if category[0]=='category_ndbg_szsh;':annual_rows.append(item)
    if set(pages)!={'category_ndbg_szsh;','category_bndbg_szsh;','category_yjdbg_szsh;','category_sjdbg_szsh;'}:
        errors.append('bare_query_categories_incomplete')
    for category, group in pages.items():
        ordered=sorted(group)
        if [p[0] for p in ordered]!=list(range(1,len(group)+1)) or ordered[-1][1] or any(not p[1] for p in ordered[:-1]):
            errors.append('raw_pagination_incomplete:'+category)
        if len({p[2] for p in ordered})!=1 or sum(p[3] for p in ordered)!=ordered[-1][2]:
            errors.append('raw_total_count_mismatch:'+category)
    frozen=_read_json(_REPO/'workspace/tmp/601225-evidence/current-002.response.bin')
    assert isinstance(frozen,Mapping)
    frozen_rows=frozen.get('announcements');assert isinstance(frozen_rows,list)
    keys=('announcementId','announcementTitle','announcementTime','adjunctUrl','adjunctType','secCode')
    official_unchanged=_canonical_rows(annual_rows,keys)==_canonical_rows(frozen_rows,keys)
    if not official_unchanged:errors.append('official_set_changed')
    redirect_hops:list[JsonValue]=[]
    # 每 hop 仅由上一真实响应 Location 与原 raw locator 的引用链归属，不从URL猜来源。
    for seq,req in sorted(requests.items()):
        url=req.get('url');response=responses.get(seq);location=response.get('location') if response is not None else None
        if isinstance(url,str) and url in locators and isinstance(location,str) and location:
            next_url=str(httpx.URL(url).join(location))
            locators[next_url]=locators[url]
            redirect_hops.append({'seq':seq,'source_id':locators[url],'from_url':url,'location':location,'to_url':next_url})
    attempts:Counter[str]=Counter();sends:Counter[str]=Counter();unknown:list[JsonValue]=[];nonpdf:list[JsonValue]=[]
    for seq,req in requests.items():
        url=req.get('url');method=req.get('method');assert isinstance(url,str)
        if method=='GET' and url in locators:
            source_id=locators[url];attempts[source_id]+=1
            sends[source_id]+=sum(e.get('seq')==seq for e in wire)
        elif method=='GET' and httpx.URL(url).host=='static.cninfo.com.cn':unknown.append(dict(req))
        else:nonpdf.append(dict(req))
    if unknown:errors.append('unknown_pdf_url')
    if any(c>1 for c in attempts.values()) or any(c>1 for c in sends.values()):errors.append('multiple_pdf_get')
    if attempts!=sends:errors.append('pdf_attempt_wire_mismatch')
    return {'validation_status':'passed' if not errors else 'failed','errors':errors,'pid':pid,
            'started':len(started),'finished':len(finished),'transport_count':len(requests),'wire_count':len(wire),
            'pdf_get_attempt_counts':dict(attempts),'pdf_get_wire_counts':dict(sends),'unknown_pdf_urls':unknown,
            'nonpdf_requests':nonpdf,'official_unchanged':official_unchanged,'annual_raw_count':len(annual_rows),
            'locator_by_source':{sid:url for url,sid in locators.items()},'redirect_hops':redirect_hops}


def run_cli(run_dir: Path, command: list[str]) -> int:
    """运行真实 CLI 并等到实际退出，不替换入口或 origin。

    参数：新 run_dir、原 command argv。返回：原 CLI exit 或观察失败 2。异常：非法范围/已存在输出拒绝。
    """
    root=run_dir.resolve()
    root.relative_to(_REPO/'workspace/tmp')
    if root.exists():raise ValueError('run-dir 已存在，拒绝覆盖')
    if not command or Path(command[0]).resolve()!=(_REPO/'.venv/bin/dayu-cli').resolve():raise ValueError('必须真实 venv dayu-cli')
    if any(arg==option or arg.startswith(option+'=') for arg in command for option in ('--forms','--overwrite','--rebuild')):
        raise ValueError('必须 bare incremental download')
    if 'download' not in command:raise ValueError('必须公开 download')
    if '--help' not in command:
        base=Path(command[command.index('--base')+1]).resolve();base.relative_to(_REPO/'workspace/tmp')
        for flag,expected in (('--ticker','601225.SH'),('--start','2018-01-01'),('--end','2026-10-12')):
            if command[command.index(flag)+1]!=expected:raise ValueError('target argv mismatch')
    root.mkdir();bootstrap=root/'bootstrap';bootstrap.mkdir()
    (bootstrap/'sitecustomize.py').write_text('from utils.observe_601225_cli_http import install_observer\ninstall_observer()\n')
    env=os.environ.copy();env.pop(_PID_ENV,None);env[_RUN_ENV]=str(root)
    env['PYTHONPATH']=os.pathsep.join((str(bootstrap),str(_REPO),env.get('PYTHONPATH','')))
    with (root/'stdout.txt').open('wb') as stdout, (root/'stderr.txt').open('wb') as stderr:
        proc=subprocess.Popen(command,cwd=_REPO,env=env,stdout=stdout,stderr=stderr)
        (root/'run.json').write_text(json.dumps({'argv':command,'pid':proc.pid,'status':'running'},indent=2)+'\n')
        exit_code=proc.wait()
    (root/'run.json').write_text(json.dumps({'argv':command,'pid':proc.pid,'exit_code':exit_code,'status':'exited'},indent=2)+'\n')
    try:summary=summarize_http(root,proc.pid)
    except Exception as exc:summary={'validation_status':'failed','errors':[type(exc).__name__]}
    (root/'http-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    if exit_code!=0:return exit_code
    return 0 if summary['validation_status']=='passed' else 2


def main() -> int:
    """解析独立验收参数。参数：sys.argv。返回：真实 exit。异常：参数/范围错误原样。"""
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='operation',required=True).add_parser('run');sub.add_argument('--run-dir',type=Path,required=True);sub.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();command=cast(list[str],args.command)
    if command and command[0]=='--':command=command[1:]
    return run_cli(args.run_dir,command)


if __name__=='__main__':sys.exit(main())
