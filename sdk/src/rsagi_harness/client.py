"""Small HTTP SDK. Idempotency keys survive uncertain transport outcomes."""
from __future__ import annotations
import json,os,time,urllib.error,urllib.parse,urllib.request,uuid
from .protocol import API_VERSION

class APIError(RuntimeError):
    def __init__(self,status,code):
        self.status=status;self.code=code;super().__init__(f'API {status}: {code}')

class TransportUncertain(RuntimeError):
    """Retry the same operation with the same request_id, never a new decision."""
    def __init__(self,request_id):
        self.request_id=request_id;super().__init__('Transport outcome uncertain; reuse request_id='+str(request_id))

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class CompetitionClient:
    def __init__(self,base_url,team_token,*,allow_mock=False,timeout=5):
        parsed=urllib.parse.urlsplit(base_url)
        local=parsed.hostname in ('127.0.0.1','localhost','::1')
        if parsed.scheme not in ('http','https') or (parsed.scheme=='http' and not local) or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
            raise ValueError('Use an HTTPS API origin; HTTP is only allowed on loopback')
        if not isinstance(team_token,str) or not team_token or any(c in team_token for c in '\r\n'):
            raise ValueError('Missing or invalid team credential')
        self.base_url=base_url.rstrip('/');self._token=team_token;self.allow_mock=allow_mock;self.timeout=timeout
        self._opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect());self._session=None

    @classmethod
    def from_env(cls):
        return cls(os.environ['RSAGI_API_URL'],os.environ['RSAGI_TEAM_TOKEN'],allow_mock=os.environ.get('RSAGI_ALLOW_PROTOCOL_MOCK')=='1')

    def _request(self,method,path,body=None,request_id=None):
        if not path.startswith('/v1/') or '?' in path or '#' in path:raise ValueError('Invalid protocol path')
        headers={'Authorization':'Bearer '+self._token,'Accept':'application/json'}
        data=None
        if method=='POST':
            request_id=request_id or uuid.uuid4().hex
            headers.update({'Content-Type':'application/json','Idempotency-Key':request_id})
            data=json.dumps(body,separators=(',',':'),allow_nan=False).encode()
        req=urllib.request.Request(self.base_url+path,data=data,headers=headers,method=method)
        try:
            with self._opener.open(req,timeout=self.timeout) as response:
                raw=response.read(65537)
                if len(raw)>65536:raise APIError(502,'RESPONSE_TOO_LARGE')
                value=json.loads(raw)
                if type(value) is not dict:raise APIError(502,'INVALID_RESPONSE')
                return value
        except urllib.error.HTTPError as ex:
            if 300<=ex.code<400:raise APIError(ex.code,'REDIRECT_FORBIDDEN') from None
            try:code=json.loads(ex.read(4096))['error']['code']
            except (ValueError,KeyError,TypeError):code='INVALID_ERROR_RESPONSE'
            raise APIError(ex.code,code) from None
        except (urllib.error.URLError,TimeoutError,OSError):
            raise TransportUncertain(request_id) from None

    def session(self):
        if self._session is None:
            value=self._request('GET','/v1/session')
            if value.get('api_version')!=API_VERSION:raise APIError(409,'UNSUPPORTED_API_VERSION')
            if value.get('mode')=='protocol_mock' and not self.allow_mock:raise APIError(409,'MOCK_REQUIRES_EXPLICIT_OPT_IN')
            if value.get('mode') not in ('protocol_mock','native_training','strict_competition'):raise APIError(409,'UNKNOWN_SERVER_MODE')
            self._session=value
        return self._session

    def round(self):
        self.session();return self._request('GET','/v1/round')

    def next_round(self,after=0,*,timeout=180):
        deadline=time.monotonic()+timeout
        delay=.02
        while True:
            value=self.round()
            if value['phase']=='ABORTED':raise APIError(503,'MATCH_ABORTED')
            if value['finished']:return None
            if value['round_id']>after:return value
            if time.monotonic()>=deadline:raise TimeoutError('Waiting for global round boundary; no model retry was made')
            time.sleep(delay);delay=min(.25,delay*2)

    def decide(self,round_info,credits,*,request_id=None):
        self.session()
        return self._request('POST','/v1/decisions',{'round_id':round_info['round_id'],'observation_ref':round_info['observation_ref'],
          'credits':credits,'harness_revision':round_info['harness_revision']},request_id)

    def decision(self,operation_id):
        self.session()
        if not isinstance(operation_id,str) or not operation_id.replace('_','').isalnum():raise ValueError('Invalid operation ID')
        return self._request('GET','/v1/decisions/'+operation_id)

    def await_decision(self,operation_id,*,timeout=180):
        deadline=time.monotonic()+timeout
        delay=.02
        while True:
            value=self.decision(operation_id)
            if value['status'] in ('SUCCEEDED','FAILED'):return value
            if time.monotonic()>=deadline:raise TimeoutError('Request still pending; poll the existing operation, do not start another call')
            time.sleep(delay);delay=min(.25,delay*2)

    def wait(self,round_info,*,request_id=None):
        self.session();return self._request('POST','/v1/wait',{'round_id':round_info['round_id']},request_id)

    def ready(self,round_info,receipt_id,*,request_id=None):
        self.session();return self._request('POST','/v1/ready',{'round_id':round_info['round_id'],'receipt_id':receipt_id},request_id)

    def activate(self,round_info,receipt_id,revision_id,*,request_id=None):
        self.session();return self._request('POST','/v1/harness/activate',{'round_id':round_info['round_id'],'receipt_id':receipt_id,'revision_id':revision_id},request_id)
