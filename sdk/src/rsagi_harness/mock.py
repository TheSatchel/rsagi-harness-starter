"""Organizer-side LOCAL PROTOCOL MOCK. No Minecraft, pixels, audio or real model.

This is not a security-isolated runtime. It deliberately has no bridge to kernel
control, game sockets, credentials, world files or the live model gateways.
"""
from __future__ import annotations
from copy import deepcopy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib,hmac,json,re,secrets,threading,time,urllib.parse
from .protocol import API_VERSION,PERCEPTION_POLICY,ProtocolError,identifier,integer,require,shape,validate_model_decision

def opaque(prefix):return prefix+'_'+secrets.token_hex(16)

def fixture_model(team,round_id,policy):
    # Synthetic handshake output; this is neither perception nor AI competence.
    first=policy['roles']==['actor']
    return {'action':{'type':'KEY_PRESS','key':'f3'} if first else {'type':'WAIT'},
      'explanation':{'evidence':'Protocol fixture, no world observation.','reason':'Exercise one accepted model receipt.','expected':'Protocol acknowledgement only; no native game effect.'},
      'harness_update':{'roles':['observer','actor'],'next_call_credits':2} if first else None}

class MockArena:
    def __init__(self,teams=('alpha','beta'),*,rounds=12,model=fixture_model,model_delay=.01):
        require(1<=len(teams)<=16 and len(set(teams))==len(teams))
        for team in teams:identifier(team)
        integer(rounds,1,1000)
        self.condition=threading.Condition(threading.RLock());self.total_rounds=rounds
        self.model=model;self.model_delay=model_delay;self.match_id=opaque('mock')
        self.round_id=1;self.logical_tick=0;self.finished=False;self.closed=False;self.aborted=False
        self.tokens={team:secrets.token_urlsafe(32) for team in teams}
        self.teams={};self.operations={};self.revisions={};self.idempotency={};self.steps=[];self.audit=[];self.workers=[]
        self.provider_calls=0
        for team in teams:
            revision=opaque('revision')
            self.revisions[revision]={'team':team,'roles':['actor'],'next_call_credits':4,'source':'initial_mock_policy'}
            self.teams[team]={'credits':1,'observation_ref':opaque('observation'),'revision':revision,
              'disposition':'OPEN','operation':None,'receipt':None,'committed_action':None}

    def authenticate(self,header):
        require(type(header) is str and header.startswith('Bearer '),'UNAUTHORIZED',401)
        token=header[7:]
        for team,credential in self.tokens.items():
            if hmac.compare_digest(token,credential):return team
        raise ProtocolError('UNAUTHORIZED',401)

    def _round(self,team):
        state=self.teams[team];policy=self.revisions[state['revision']]
        return {'mode':'protocol_mock','phase':'ABORTED' if self.aborted else ('FINISHED' if self.finished else 'COLLECTING'),'round_id':self.round_id,'logical_tick':self.logical_tick,
          'available_credits':state['credits'],'observation_ref':None if self.finished else state['observation_ref'],
          'harness_revision':state['revision'],'recommended_call_credits':policy['next_call_credits'],
          'active_operation_id':state['operation'],
          'disposition':state['disposition'],'finished':self.finished}

    def _operation(self,team,operation_id):
        op=self.operations.get(operation_id)
        require(op is not None and op['team']==team,'NOT_FOUND',404)
        return {key:deepcopy(op[key]) for key in ['mode','operation_id','round_id','status','receipt_id','proposed_revision_id','usage','error']}

    def _current(self,team,round_id):
        integer(round_id,1)
        require(not self.finished,'MATCH_FINISHED',409)
        require(round_id==self.round_id,'ROUND_MISMATCH',409)
        return self.teams[team]

    def _receipt(self,team,round_id,receipt_id):
        state=self._current(team,round_id);identifier(receipt_id)
        require(state['disposition']=='DECIDED' and state['receipt']==receipt_id,'INVALID_RECEIPT',409)
        op=self.operations[state['operation']]
        require(op['status']=='SUCCEEDED','INVALID_RECEIPT',409)
        return state,op

    def dispatch(self,team,method,path,body=None,request_id=None):
        with self.condition:
            require(team in self.teams,'UNAUTHORIZED',401)
            if method=='GET':
                if path=='/v1/session':
                    return 200,{'api_version':API_VERSION,'mode':'protocol_mock','match_id':self.match_id,'team_id':team,
                      'perception_policy':PERCEPTION_POLICY,'ticks_per_round':5,'rounds_per_logical_second':4,
                      'credit_cap':16,'tokens_per_credit':512,'seconds_per_credit':10,'max_model_calls_per_round':1,
                      'f3_allowed':True,'screen':{'width':1280,'height':720},
                      'capabilities':{'human_view_capture':False,'native_game_execution':False,'real_model':False,
                        'self_organization_config':True,'arbitrary_code_hot_update':False,'strict_certified':False}}
                if path=='/v1/round':return 200,self._round(team)
                if path.startswith('/v1/decisions/'):
                    return 200,self._operation(team,path[len('/v1/decisions/'):])
                raise ProtocolError('NOT_FOUND',404)
            require(method=='POST','METHOD_NOT_ALLOWED',405)
            require(path in ('/v1/decisions','/v1/ready','/v1/wait','/v1/harness/activate'),'NOT_FOUND',404)
            require(type(request_id) is str and re.fullmatch(r'[A-Za-z0-9_-]{8,128}',request_id) is not None,'IDEMPOTENCY_KEY_REQUIRED')
            fingerprint=json.dumps([method,path,body],sort_keys=True,separators=(',',':'),allow_nan=False)
            key=(team,request_id)
            if key in self.idempotency:
                prior=self.idempotency[key]
                require(prior[0]==fingerprint,'IDEMPOTENCY_CONFLICT',409)
                return deepcopy(prior[1])
            if path=='/v1/decisions':
                shape(body,['round_id','observation_ref','credits','harness_revision'])
                state=self._current(team,body['round_id'])
                require(state['disposition']=='OPEN','ROUND_ALREADY_RESERVED_OR_READY',409)
                require(body['observation_ref']==state['observation_ref'],'OBSERVATION_MISMATCH',409)
                require(body['harness_revision']==state['revision'],'HARNESS_REVISION_MISMATCH',409)
                integer(body['credits'],1,16)
                require(body['credits']<=state['credits'],'INSUFFICIENT_CREDITS',409)
                # Charge and register operation atomically, before starting computation.
                state['credits']-=body['credits'];state['disposition']='PENDING'
                operation_id=opaque('decision');state['operation']=operation_id
                self.operations[operation_id]={'mode':'protocol_mock','operation_id':operation_id,'team':team,
                  'round_id':self.round_id,'status':'PENDING','receipt_id':None,'proposed_revision_id':None,'usage':None,'error':None,
                  'credits_spent':body['credits'],'parent_revision':state['revision'],'original_fixture_result':None}
                result=(202,{'mode':'protocol_mock','operation_id':operation_id,'status':'PENDING'})
                self.idempotency[key]=(fingerprint,deepcopy(result))
                self.audit.append({'type':'RESERVED','team':team,'round':self.round_id,'credits':body['credits'],'operation':operation_id})
                worker=threading.Thread(target=self._compute,args=(operation_id,),daemon=True)
                self.workers.append(worker);worker.start()
                return deepcopy(result)
            if path=='/v1/wait':
                shape(body,['round_id']);state=self._current(team,body['round_id'])
                require(state['disposition']=='OPEN','ROUND_ALREADY_RESERVED_OR_READY',409)
                state['disposition']='READY';state['committed_action']={'type':'WAIT'}
                self.audit.append({'type':'WAIT_WITHOUT_MODEL','team':team,'round':self.round_id,'control_reason':'BANK_CREDIT_NO_MODEL_CALL'})
                result=(200,{'mode':'protocol_mock','accepted_round':self.round_id,'disposition':'READY'})
            elif path=='/v1/ready':
                shape(body,['round_id','receipt_id']);state,op=self._receipt(team,body['round_id'],body['receipt_id'])
                state['disposition']='READY';state['committed_action']=deepcopy(op['original_fixture_result']['action'])
                result=(200,{'mode':'protocol_mock','accepted_round':self.round_id,'disposition':'READY'})
            else:
                shape(body,['round_id','receipt_id','revision_id']);state,op=self._receipt(team,body['round_id'],body['receipt_id'])
                identifier(body['revision_id'])
                require(body['revision_id']==op['proposed_revision_id'] and body['revision_id'] in self.revisions,'INVALID_REVISION',409)
                require(state['revision']==op['parent_revision'],'REVISION_ALREADY_CHANGED',409)
                state['revision']=body['revision_id']
                self.audit.append({'type':'HARNESS_POLICY_ACTIVATED','team':team,'round':self.round_id,'parent':op['parent_revision'],'revision':state['revision']})
                result=(200,{'mode':'protocol_mock','accepted_round':self.round_id,'disposition':'REVISION_ACTIVATED'})
            self.idempotency[key]=(fingerprint,deepcopy(result))
            self._advance_if_complete();return deepcopy(result)

    def _compute(self,operation_id):
        with self.condition:
            op=self.operations[operation_id]
            if self.closed or self.aborted or op['status']!='PENDING':return
            team=op['team'];round_id=op['round_id'];policy=deepcopy(self.revisions[op['parent_revision']])
            self.provider_calls+=1
        try:
            time.sleep(self.model_delay)
            value=deepcopy(self.model(team,round_id,policy))
            # Preserve raw original synthetic output on the organizer side.
            with self.condition:op['original_fixture_result']=value
            validate_model_decision(value)
            failure=None
        except TimeoutError:failure='MODEL_DEADLINE_EXCEEDED'
        except ProtocolError:failure='MODEL_OUTPUT_REJECTED'
        except Exception:failure='HOST_FIXTURE_FAULT'
        with self.condition:
            if self.closed or op['status']!='PENDING':return
            state=self.teams[team]
            require(state['operation']==operation_id and self.round_id==round_id,'MOCK_INTERNAL_OPERATION_MISMATCH',500)
            op['usage']={'kind':'synthetic_mock','input_tokens':0,'output_tokens':0 if failure else 32,'reasoning_tokens':0}
            if failure:
                op['status']='FAILED';op['error']=failure
                # This is a host disposition, never a participant bypass or retry.
                state['disposition']='READY';state['committed_action']={'type':'WAIT'}
                if failure=='HOST_FIXTURE_FAULT':
                    self.finished=True;self.aborted=True
                    for pending in self.operations.values():
                        if pending['status']=='PENDING':
                            pending['status']='FAILED';pending['error']='MATCH_ABORTED'
                            self.teams[pending['team']]['disposition']='READY'
            else:
                op['status']='SUCCEEDED';op['receipt_id']=opaque('receipt')
                state['receipt']=op['receipt_id'];state['disposition']='DECIDED'
                update=value.get('harness_update')
                if update is not None:
                    revision=opaque('revision');op['proposed_revision_id']=revision
                    self.revisions[revision]={'team':team,**deepcopy(update),'source_operation':operation_id,'parent':op['parent_revision']}
            self.audit.append({'type':'DECISION_RESOLVED','team':team,'round':round_id,'operation':operation_id,'status':op['status'],'credits_spent':op['credits_spent']})
            self._advance_if_complete();self.condition.notify_all()

    def _advance_if_complete(self):
        if self.finished:return
        if not all(s['disposition']=='READY' for s in self.teams.values()):return
        # Deterministic mock ordering only; real execution must use RoundCoordinator.
        order=sorted(self.teams,key=lambda t:hashlib.sha256(f'{self.round_id}:{t}'.encode()).digest())
        self.steps.append({'round_id':self.round_id,'ticks':5,'order':order,
          'actions':{team:deepcopy(self.teams[team]['committed_action']) for team in order}})
        self.logical_tick+=5
        if self.round_id==self.total_rounds:
            self.finished=True
        else:
            self.round_id+=1
            for state in self.teams.values():
                state.update({'credits':min(16,state['credits']+1),'observation_ref':opaque('observation'),
                  'disposition':'OPEN','operation':None,'receipt':None,'committed_action':None})
        self.condition.notify_all()

class MockServer:
    def __init__(self,arena=None):
        self.arena=arena or MockArena();arena=self.arena
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.handle_request('GET')
            def do_POST(self):self.handle_request('POST')
            def handle_request(self,method):
                try:
                    team=arena.authenticate(self.headers.get('Authorization'))
                    url=urllib.parse.urlsplit(self.path);require(not url.query and not url.fragment,'INVALID_QUERY')
                    if url.path!='/v1/session':
                        require(self.headers.get('X-RSAGI-Match')==arena.match_id,'MATCH_MISMATCH',409)
                    body=None
                    if method=='POST':
                        require(self.headers.get('Content-Type','').split(';')[0].strip()=='application/json','JSON_REQUIRED',415)
                        require(self.headers.get('Transfer-Encoding') is None,'CONTENT_LENGTH_REQUIRED')
                        raw_length=self.headers.get('Content-Length','')
                        require(raw_length.isdigit(),'CONTENT_LENGTH_REQUIRED')
                        size=int(raw_length);require(0<size<=4096,'BODY_TOO_LARGE',413)
                        def unique_pairs(pairs):
                            result={}
                            for k,v in pairs:
                                require(k not in result,'DUPLICATE_JSON_FIELD');result[k]=v
                            return result
                        body=json.loads(self.rfile.read(size),object_pairs_hook=unique_pairs,parse_constant=lambda _:(_ for _ in ()).throw(ProtocolError('INVALID_JSON')))
                    status,value=arena.dispatch(team,method,url.path,body,self.headers.get('Idempotency-Key'))
                except ProtocolError as ex:status,value=ex.status,{'error':{'code':ex.code}}
                except (ValueError,UnicodeError):status,value=400,{'error':{'code':'INVALID_JSON'}}
                except Exception:status,value=500,{'error':{'code':'MOCK_INTERNAL_ERROR'}}
                raw=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
                if status==401:self.send_header('WWW-Authenticate','Bearer realm="rsagi"')
                self.end_headers()
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=None
        self.url='http://127.0.0.1:'+str(self.server.server_address[1])

    def __enter__(self):
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.02},daemon=True);self.thread.start();return self

    def __exit__(self,*args):
        with self.arena.condition:self.arena.closed=True
        self.server.shutdown();self.server.server_close()
        if self.thread:self.thread.join(timeout=2)
        for worker in self.arena.workers:worker.join(timeout=2)
