import json,sys,threading,time,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'sdk/src'))
sys.path.insert(0,str(ROOT/'sdk/examples'))
from rsagi_harness import APIError,CompetitionClient
from rsagi_harness.mock import MockArena,MockServer,fixture_model
from rsagi_harness.protocol import ProtocolError,validate_model_decision
from baseline import run

class ParticipantAPITests(unittest.TestCase):
    def setUp(self):
        self.arena=MockArena(rounds=12)
        self.server=MockServer(self.arena);self.server.__enter__()
        self.alpha=CompetitionClient(self.server.url,self.arena.tokens['alpha'],allow_mock=True)
        self.beta=CompetitionClient(self.server.url,self.arena.tokens['beta'],allow_mock=True)
    def tearDown(self):self.server.__exit__()
    def error(self,code,callback):
        with self.assertRaises(APIError) as caught:callback()
        self.assertEqual(caught.exception.code,code)
        return caught.exception.status
    def bank(self):
        for n in range(1,4):
            self.alpha.wait(self.alpha.round(),request_id=f'alpha-bank-{n}')
            self.beta.wait(self.beta.round(),request_id=f'beta-bank-{n}')
        return self.alpha.round()

    def test_polling_repeats_one_owned_boundary_without_world_state(self):
        first=self.alpha.round()
        for _ in range(10):self.assertEqual(self.alpha.round(),first)
        self.assertNotEqual(first['observation_ref'],self.beta.round()['observation_ref'])
        self.assertEqual(set(first),{'mode','phase','round_id','logical_tick','available_credits','observation_ref','harness_revision','recommended_call_credits','active_operation_id','disposition','finished'})
        self.assertEqual(self.arena.logical_tick,0)
        session=self.alpha.session();self.assertTrue(session['f3_allowed'])
        self.assertFalse(session['capabilities']['human_view_capture'])
        self.assertFalse(session['capabilities']['native_game_execution'])

    def test_only_full_barrier_advances_and_same_ack_is_replayable(self):
        a=self.alpha.round();b=self.beta.round()
        result=self.alpha.wait(a,request_id='alpha-wait-key')
        self.assertEqual(self.alpha.round()['logical_tick'],0)
        self.assertEqual(self.beta.round()['available_credits'],1)
        self.beta.wait(b,request_id='beta-wait-key')
        self.assertEqual(self.alpha.round()['logical_tick'],5)
        self.assertEqual(self.alpha.round()['available_credits'],2)
        self.assertEqual(self.alpha.wait(a,request_id='alpha-wait-key'),result)
        self.assertEqual(self.arena.logical_tick,5)

    def test_call_precharged_once_and_slow_model_cannot_advance_world(self):
        round_info=self.bank();release=threading.Event();entered=threading.Event()
        def model(*args):entered.set();release.wait(2);return fixture_model(*args)
        self.arena.model=model
        accepted=self.alpha.decide(round_info,4,request_id='unique-decision-key')
        try:
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.alpha.round()['available_credits'],0)
            self.assertEqual(self.alpha.round()['disposition'],'PENDING')
            self.assertEqual(self.alpha.decide(round_info,4,request_id='unique-decision-key'),accepted)
            self.beta.wait(self.beta.round(),request_id='beta-round-four-wait')
            time.sleep(.03);self.assertEqual(self.arena.logical_tick,15)
            self.assertEqual(self.arena.provider_calls,1)
        finally:release.set()
        result=self.alpha.await_decision(accepted['operation_id'])
        self.assertEqual(self.arena.logical_tick,15)
        ack=self.alpha.ready(round_info,result['receipt_id'],request_id='alpha-ready-four')
        self.assertEqual(self.arena.logical_tick,20)
        self.assertEqual(self.alpha.round()['available_credits'],1)
        self.assertEqual(self.alpha.decide(round_info,4,request_id='unique-decision-key'),accepted)
        self.assertEqual(self.alpha.ready(round_info,result['receipt_id'],request_id='alpha-ready-four'),ack)
        self.assertEqual(self.arena.provider_calls,1)

    def test_idempotency_key_cannot_change_body_or_operation(self):
        r=self.bank();accepted=self.alpha.decide(r,4,request_id='same-key-different-body')
        self.error('IDEMPOTENCY_CONFLICT',lambda:self.alpha.decide(r,3,request_id='same-key-different-body'))
        self.error('IDEMPOTENCY_CONFLICT',lambda:self.alpha.wait(r,request_id='same-key-different-body'))
        self.alpha.await_decision(accepted['operation_id'])
        self.error('ROUND_ALREADY_RESERVED_OR_READY',lambda:self.alpha.decide(r,1,request_id='different-key-same-round'))
        self.assertEqual(self.alpha.round()['available_credits'],0)
        self.assertEqual(self.arena.provider_calls,1)

    def test_concurrent_replays_create_only_one_operation_and_charge(self):
        r=self.alpha.round()
        def submit():
            client=CompetitionClient(self.server.url,self.arena.tokens['alpha'],allow_mock=True)
            return client.decide(r,1,request_id='concurrent-replay-key')
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:submit(),range(6)))
        self.assertTrue(all(result==results[0] for result in results))
        self.alpha.await_decision(results[0]['operation_id'])
        self.assertEqual((len(self.arena.operations),self.arena.provider_calls,self.alpha.round()['available_credits']),(1,1,0))

    def test_rejects_forged_observation_stale_round_and_excess_quota_before_charge(self):
        a=self.alpha.round();b=self.beta.round()
        attempts=[({**a,'round_id':0},1,'INVALID_REQUEST'),({**a,'round_id':2},1,'ROUND_MISMATCH'),
          ({**a,'observation_ref':b['observation_ref']},1,'OBSERVATION_MISMATCH'),
          ({**a,'harness_revision':b['harness_revision']},1,'HARNESS_REVISION_MISMATCH'),
          (a,2,'INSUFFICIENT_CREDITS'),(a,0,'INVALID_REQUEST'),(a,True,'INVALID_REQUEST')]
        for i,(r,credits,code) in enumerate(attempts):
            with self.subTest(code=code):self.error(code,lambda:self.alpha.decide(r,credits,request_id=f'invalid-request-{i}'))
        self.assertEqual((self.arena.provider_calls,self.alpha.round()['available_credits']),(0,1))

    def test_no_world_prompt_history_or_direct_action_ingress(self):
        r=self.alpha.round()
        base={'round_id':r['round_id'],'observation_ref':r['observation_ref'],'credits':1,'harness_revision':r['harness_revision']}
        for i,key in enumerate(['prompt','messages','history','image','coordinates','team_id','action','memory']):
            self.error('INVALID_REQUEST',lambda:self.alpha._request('POST','/v1/decisions',{**base,key:'forbidden'},f'unknown-field-{i}'))
        for path in ['/v1/probe','/v1/observation','/v1/world','/v1/step','/v1/console']:
            self.assertEqual(self.error('NOT_FOUND',lambda:self.alpha._request('GET',path)),404)
        self.assertEqual((self.arena.provider_calls,self.alpha.round()['available_credits']),(0,1))

    def test_operations_receipts_and_revisions_are_owned(self):
        r=self.alpha.round();accepted=self.alpha.decide(r,1,request_id='alpha-owned-decision')
        result=self.alpha.await_decision(accepted['operation_id'])
        self.assertEqual(self.error('NOT_FOUND',lambda:self.beta.decision(accepted['operation_id'])),404)
        self.assertEqual(self.error('NOT_FOUND',lambda:self.beta.decision('decision_unknown')),404)
        self.error('INVALID_RECEIPT',lambda:self.beta.ready(self.beta.round(),result['receipt_id'],request_id='beta-forged-receipt'))
        self.error('INVALID_RECEIPT',lambda:self.beta.activate(self.beta.round(),result['receipt_id'],result['proposed_revision_id'],request_id='beta-forged-revision'))
        self.assertNotIn('action',result);self.assertNotIn('explanation',result)
        self.assertNotIn('original_fixture_result',result)

    def test_model_proposed_policy_changes_at_runtime_with_provenance(self):
        r=self.bank();accepted=self.alpha.decide(r,4,request_id='policy-decision-key')
        result=self.alpha.await_decision(accepted['operation_id']);revision=result['proposed_revision_id']
        self.assertIsNotNone(revision)
        body={'round_id':r['round_id'],'receipt_id':result['receipt_id'],'revision_id':revision,'notes':'world memory'}
        self.error('INVALID_REQUEST',lambda:self.alpha._request('POST','/v1/harness/activate',body,'policy-injected-notes'))
        ack=self.alpha.activate(r,result['receipt_id'],revision,request_id='activate-policy-key')
        self.assertEqual(self.alpha.activate(r,result['receipt_id'],revision,request_id='activate-policy-key'),ack)
        self.error('REVISION_ALREADY_CHANGED',lambda:self.alpha.activate(r,result['receipt_id'],revision,request_id='activate-again-new-key'))
        self.assertEqual(self.alpha.round()['recommended_call_credits'],2)
        self.alpha.ready(r,result['receipt_id'],request_id='ready-after-policy')
        self.beta.wait(self.beta.round(),request_id='beta-after-policy-wait')
        self.assertEqual(self.alpha.round()['harness_revision'],revision)
        self.assertEqual(self.arena.revisions[revision]['roles'],['observer','actor'])
        self.assertEqual(self.arena.revisions[revision]['source_operation'],accepted['operation_id'])

    def test_timeout_retains_charge_and_host_explicitly_resolves_wait(self):
        def timeout(*args):raise TimeoutError()
        self.arena.model=timeout;r=self.bank()
        accepted=self.alpha.decide(r,4,request_id='timeout-decision-key')
        result=self.alpha.await_decision(accepted['operation_id'])
        self.assertEqual((result['status'],result['error']),('FAILED','MODEL_DEADLINE_EXCEEDED'))
        self.assertEqual(self.alpha.round()['available_credits'],0)
        self.assertEqual(self.arena.logical_tick,15)
        self.beta.wait(self.beta.round(),request_id='beta-timeout-wait')
        self.assertEqual((self.arena.logical_tick,self.alpha.round()['available_credits']),(20,1))
        self.assertEqual(self.arena.provider_calls,1)
        self.assertEqual(self.arena.steps[-1]['actions']['alpha'],{})

    def test_invalid_model_action_never_becomes_a_receipt(self):
        def invalid(*args):return {'action':{'type':'NAVIGATE_TO','x':10,'z':20},'explanation':{'evidence':'fixture','reason':'fixture','expected':'fixture'}}
        self.arena.model=invalid;r=self.alpha.round()
        accepted=self.alpha.decide(r,1,request_id='invalid-model-decision')
        result=self.alpha.await_decision(accepted['operation_id'])
        self.assertEqual((result['status'],result['error'],result['receipt_id']),('FAILED','MODEL_OUTPUT_REJECTED',None))
        self.assertEqual(self.arena.teams['alpha']['committed_action'],{})
        self.assertEqual(self.alpha.round()['available_credits'],0)
        self.assertEqual(self.arena.logical_tick,0)

    def test_host_fault_aborts_global_mock_instead_of_blame_on_one_team(self):
        def fault(*args):raise RuntimeError('host fixture failed')
        self.arena.model=fault;r=self.alpha.round()
        accepted=self.alpha.decide(r,1,request_id='host-fault-decision')
        result=self.alpha.await_decision(accepted['operation_id'])
        self.assertEqual(result['error'],'HOST_FIXTURE_FAULT')
        self.assertEqual(self.alpha.round()['phase'],'ABORTED')
        self.assertEqual(self.arena.logical_tick,0)
        self.error('MATCH_ABORTED',lambda:self.beta.next_round())
        self.error('MATCH_FINISHED',lambda:self.beta.wait(self.beta.round(),request_id='wait-after-host-fault'))

    def test_two_baselines_reach_shared_barriers_and_activate_two_policies(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[pool.submit(run,c) for c in [self.alpha,self.beta]]
            for job in jobs:job.result(timeout=10)
        self.assertTrue(self.arena.finished)
        self.assertEqual((len(self.arena.steps),self.arena.logical_tick,self.arena.provider_calls),(12,60,10))
        self.assertEqual(sum(x['type']=='HARNESS_POLICY_ACTIVATED' for x in self.arena.audit),2)
        self.assertTrue(all(step['ticks']==5 for step in self.arena.steps))

    def test_mock_requires_opt_in_and_bad_credentials_have_no_side_effect(self):
        default=CompetitionClient(self.server.url,self.arena.tokens['alpha'])
        self.error('MOCK_REQUIRES_EXPLICIT_OPT_IN',default.session)
        bad=CompetitionClient(self.server.url,'invalid-team-token',allow_mock=True)
        self.assertEqual(self.error('UNAUTHORIZED',bad.session),401)
        self.assertEqual((self.arena.provider_calls,self.arena.logical_tick),(0,0))

    def test_redirect_does_not_forward_team_credential(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        received=[]
        target_url=self.server.url
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                received.append(self.path)
                self.send_response(302);self.send_header('Location',target_url+'/v1/session');self.send_header('Content-Length','0');self.end_headers()
        redirect=ThreadingHTTPServer(('127.0.0.1',0),Redirect)
        thread=threading.Thread(target=redirect.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
        try:
            client=CompetitionClient('http://127.0.0.1:'+str(redirect.server_address[1]),self.arena.tokens['alpha'],allow_mock=True)
            # If the redirect were followed, the real mock would authenticate and
            # return a session; the SDK must reject at the redirect response.
            self.assertEqual(self.error('REDIRECT_FORBIDDEN',client.session),302)
            self.assertEqual(received,['/v1/session']);self.assertIsNone(client._session)
        finally:redirect.shutdown();redirect.server_close();thread.join(1)

    def test_http_duplicates_and_non_json_are_rejected(self):
        import urllib.request,urllib.error
        for raw,content_type,code in [(b'{"round_id":1,"round_id":2}','application/json','DUPLICATE_JSON_FIELD'),
          (b'{}','text/plain','JSON_REQUIRED'),(b'{','application/json','INVALID_JSON'),
          (b'x'*4097,'application/json','BODY_TOO_LARGE')]:
            req=urllib.request.Request(self.server.url+'/v1/wait',data=raw,headers={'Authorization':'Bearer '+self.arena.tokens['alpha'],'Content-Type':content_type,'Idempotency-Key':'invalid-http-test','X-RSAGI-Match':self.arena.match_id})
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.alpha._opener.open(req,timeout=2)
            self.assertEqual(json.loads(error.exception.read())['error']['code'],code)
        self.assertEqual(self.arena.logical_tick,0)

    def test_model_input_schema_is_low_level_and_f3_is_allowed(self):
        valid=fixture_model('alpha',1,{'roles':['actor']})
        self.assertEqual(validate_model_decision(valid)['action'],{'type':'KEY_PRESS','key':'f3'})
        for action in [{'type':'INPUT','keys':[],'look_delta':{'yaw':True,'pitch':0}},
          {'type':'INPUT','keys':[],'look_delta':{'yaw':float('nan'),'pitch':0}},
          {'type':'INPUT','keys':['pathfind'],'look_delta':{'yaw':0,'pitch':0}},
          {'type':'GUI_CLICK','x':1280,'y':0,'button':'left','shift':False},
          {'type':'CHAT','text':' /locate structure stronghold'},
          {'type':'INPUT','keys':[],'look_delta':{'yaw':0,'pitch':0},'target_block':[1,2,3]}]:
            with self.subTest(action=action),self.assertRaises(ProtocolError):
                validate_model_decision({**valid,'action':action})

if __name__=='__main__':unittest.main()
