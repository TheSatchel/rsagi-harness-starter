"""Direct, unmetered local training connection to the launcher-installed mod.

This interface does not provide competition tickets or server synchronization.
It never starts Minecraft, reads launcher accounts or queries world state.
"""
import hashlib,json,os,re
from dataclasses import dataclass
from urllib import request,parse,error
from .control import native_fields

class ModConnectionError(RuntimeError):pass

class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

@dataclass(frozen=True)
class ModObservation:
    receipt:dict
    png:bytes

class ModClient:
    def __init__(self,url,token):
        value=parse.urlsplit(url)
        if value.scheme not in ('http','https') or not value.hostname or value.username or value.password or value.query or value.fragment:
            raise ValueError('Use a plain HTTP(S) mod endpoint')
        if not re.fullmatch(r'[0-9a-f]{64}',token):raise ValueError('Expected the mod pairing token')
        self.url=url.rstrip('/');self._token=token
        self._http=request.build_opener(request.ProxyHandler({}),_NoRedirect())

    @classmethod
    def from_env(cls):
        return cls(os.environ.get('RSAGI_MOD_URL','http://127.0.0.1:25672'),os.environ['RSAGI_MOD_TOKEN'])

    def _request(self,path,fields=None):
        body=None if fields is None else parse.urlencode(fields).encode()
        message=request.Request(self.url+path,data=body,headers={'Authorization':'Bearer '+self._token,'Content-Type':'application/x-www-form-urlencoded'})
        try:
            with self._http.open(message,timeout=20) as response:return response.read(16*1024*1024)
        except error.HTTPError as exc:
            try:reason=json.loads(exc.read(8192)).get('error','MOD_REQUEST_FAILED')
            except (ValueError,AttributeError):reason='MOD_REQUEST_FAILED'
            raise ModConnectionError(str(reason)) from None
        except (error.URLError,TimeoutError):raise ModConnectionError('MOD_NOT_REACHABLE: start Minecraft with the mod first') from None

    def _control(self,op,**fields):return json.loads(self._request('/control',{'op':op,**fields}))['result']
    def status(self):return self._control('status')
    def attach(self):return self._control('attach')
    def detach(self):return self._control('detach')
    def release(self):return self._control('release')

    def step(self,action,why,*,ticks=5):
        if type(why) is not str or not why.strip() or len(why)>300:raise ValueError('Give a brief why of at most 300 characters')
        if type(ticks) is not int or not 1<=ticks<=5:raise ValueError('One local step is 1..5 client ticks')
        self._control('input',**native_fields(action),why=why)
        return self._control('tick',count=ticks)

    def wait(self):return self._control('tick',count=5)

    def capture(self):
        receipt=self._control('capture');frame=receipt.get('frame_id','')
        if not re.fullmatch(r'frame-[0-9]{8}',frame):raise ModConnectionError('INVALID_FRAME_ID')
        png=self._request('/frames/'+frame+'.png')
        if not png.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(png).hexdigest()!=receipt.get('sha256'):
            raise ModConnectionError('FRAME_CHECKSUM_MISMATCH')
        return ModObservation(receipt,png)
