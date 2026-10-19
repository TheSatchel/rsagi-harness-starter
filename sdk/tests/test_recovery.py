import json,sys,threading,time,unittest,urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'sdk/src'))
from rsagi_harness import APIError,CompetitionClient,TransportUncertain,complete_round,run_harness
from rsagi_harness.mock import MockArena,MockServer,fixture_model,opaque

class LostReply:
    def __init__(self,opener,path,*,drops=1,after=True):
        self.opener=opener;self.path=path;self.drops=drops;self.after=after;self.requests=[]
    def open(self,request,**kwargs):
        if request.full_url.endswith(self.path) and request.method=='POST':
            headers={k.lower():v for k,v in request.header_items()}
            self.requests.append((request.data,headers.get('idempotency-key'),headers.get('x-rsagi-match')))
            if self.drops:
                self.drops-=1
                if self.after:
                    with self.opener.open(request,**kwargs) as response:response.read()
                raise urllib.error.URLError('simulated lost API reply')
        return self.opener.open(request,**kwargs)

class RecoveryTests(unittest.TestCase):
    def make(self,arena,server):
        return CompetitionClient(server.url,arena.tokens['alpha'],allow_mock=True,expected_match_id=arena.match_id)
    def decided(self,client):
        r=client.round();op=client.decide(r,1,request_id='first-decision-key')
        return r,client.await_decision(op['operation_id'])
    def assert_error(self,code,callback):
        with self.assertRaises(APIError) as error:callback()
        self.assertEqual(error.exception.code,code)

    def test_lost_wait_reply_does_not_advance_twice(self):
        arena=MockArena(teams=('alpha',),rounds=2)
        with MockServer(arena) as server:
            c=self.make(arena,server);r=c.round();lost=LostReply(c._opener,'/v1/wait');c._opener=lost
            ack=c.wait(r,request_id='stable-wait-key')
            self.assertEqual(ack['accepted_round'],1)
            self.assertEqual((len(arena.steps),arena.logical_tick,c.round()['available_credits']),(1,5,2))
            self.assertEqual(len(lost.requests),2);self.assertEqual(lost.requests[0],lost.requests[1])

    def test_lost_decision_reply_replays_same_key_and_body(self):
        arena=MockArena(teams=('alpha',),rounds=1)
        with MockServer(arena) as server:
            c=self.make(arena,server);r=c.round();lost=LostReply(c._opener,'/v1/decisions');c._opener=lost
            op=c.decide(r,1,request_id='stable-decision-key');c.await_decision(op['operation_id'])
            self.assertEqual((arena.provider_calls,len(arena.operations),c.round()['available_credits']),(1,1,0))
            self.assertEqual(lost.requests[0],lost.requests[1])

    def test_lost_ready_reply_cannot_execute_action_again(self):
        arena=MockArena(teams=('alpha',),rounds=1)
        with MockServer(arena) as server:
            c=self.make(arena,server);r,value=self.decided(c)
            lost=LostReply(c._opener,'/v1/ready');c._opener=lost
            c.ready(r,value['receipt_id'],request_id='stable-ready-key')
            self.assertTrue(arena.finished);self.assertEqual((len(arena.steps),arena.provider_calls),(1,1))
            self.assertEqual(lost.requests[0],lost.requests[1])

    def test_lost_activation_reply_has_one_applied_revision(self):
        arena=MockArena(teams=('alpha',),rounds=1)
        with MockServer(arena) as server:
            c=self.make(arena,server);r,value=self.decided(c)
            lost=LostReply(c._opener,'/v1/harness/activate');c._opener=lost
            c.activate(r,value['receipt_id'],value['proposed_revision_id'],request_id='stable-activation-key')
            self.assertEqual(sum(e['type']=='HARNESS_POLICY_ACTIVATED' for e in arena.audit),1)
            self.assertEqual(lost.requests[0],lost.requests[1])

    def test_exhausted_reply_retries_leave_recoverable_operation(self):
        arena=MockArena(teams=('alpha',),rounds=1)
        with MockServer(arena) as server:
            c=self.make(arena,server);r=c.round();lost=LostReply(c._opener,'/v1/decisions',drops=10);c._opener=lost
            with self.assertRaises(TransportUncertain) as error:c.decide(r,1,request_id='stable-exhausted-key')
            self.assertEqual(error.exception.request_id,'stable-exhausted-key')
            self.assertEqual(len(lost.requests),3);self.assertTrue(all(x==lost.requests[0] for x in lost.requests))
            run_harness(self.make(arena,server))
            self.assertEqual((arena.provider_calls,len(arena.steps)),(1,1))

    def test_new_controller_recovers_pending_instead_of_calling_again(self):
        release=threading.Event();entered=threading.Event()
        def model(*args):entered.set();release.wait(3);return fixture_model(*args)
        arena=MockArena(teams=('alpha',),rounds=1,model=model)
        with MockServer(arena) as server:
            c=self.make(arena,server);r=c.round();op=c.decide(r,1,request_id='pending-controller-key')
            self.assertTrue(entered.wait(1))
            recovery=self.make(arena,server);pending=recovery.round()
            self.assertEqual((pending['disposition'],pending['active_operation_id']),('PENDING',op['operation_id']))
            with ThreadPoolExecutor(max_workers=1) as pool:
                job=pool.submit(run_harness,recovery)
                try:time.sleep(.03);self.assertEqual(arena.provider_calls,1)
                finally:release.set()
                job.result(timeout=5)
            self.assertEqual((arena.provider_calls,len(arena.steps)),(1,1))

    def test_controller_recovers_between_activation_and_ready(self):
        arena=MockArena(teams=('alpha',),rounds=1)
        with MockServer(arena) as server:
            c=self.make(arena,server);r,value=self.decided(c)
            c.activate(r,value['receipt_id'],value['proposed_revision_id'],request_id='activation-before-restart')
            run_harness(self.make(arena,server))
            self.assertEqual(sum(e['type']=='HARNESS_POLICY_ACTIVATED' for e in arena.audit),1)
            self.assertEqual((arena.provider_calls,len(arena.steps)),(1,1))

    def test_already_ready_controller_does_not_submit_again(self):
        arena=MockArena(rounds=2)
        with MockServer(arena) as server:
            c=self.make(arena,server);c.wait(c.round(),request_id='ready-before-restart')
            recovery=self.make(arena,server);complete_round(recovery,recovery.round())
            self.assertEqual((len(arena.idempotency),arena.provider_calls,arena.logical_tick),(1,0,0))

    def test_same_credential_cannot_mix_cached_controller_into_new_match(self):
        arena=MockArena(teams=('alpha',),rounds=1)
        with MockServer(arena) as server:
            c=self.make(arena,server);r=c.round();original=arena.match_id
            arena.match_id=opaque('newmatch')
            self.assert_error('MATCH_MISMATCH',lambda:c.wait(r,request_id='old-match-wait-key'))
            self.assert_error('MATCH_MISMATCH',c.round)
            pinned=CompetitionClient(server.url,arena.tokens['alpha'],allow_mock=True,expected_match_id=original)
            self.assert_error('MATCH_MISMATCH',pinned.session)
            self.assertEqual((arena.logical_tick,len(arena.idempotency)),(0,0))

    def test_non_mock_requires_pinned_match_and_ready_services(self):
        arena=MockArena(teams=('alpha',),rounds=1)
        with MockServer(arena) as server:
            value=self.make(arena,server).session();value={**value,'mode':'native_training'}
            c=CompetitionClient(server.url,arena.tokens['alpha'])
            with patch.object(c,'_request',return_value=value):self.assert_error('MATCH_PIN_REQUIRED',c.session)
            pinned=CompetitionClient(server.url,arena.tokens['alpha'],expected_match_id=arena.match_id)
            with patch.object(pinned,'_request',return_value=value):self.assert_error('SERVICE_CAPABILITY_NOT_READY',pinned.session)
            self.assertEqual(arena.provider_calls,0)

    def test_environment_requires_match_id_before_connecting(self):
        environment={'RSAGI_API_URL':'http://127.0.0.1:12345','RSAGI_TEAM_TOKEN':'fixture-only-token'}
        with patch.dict('os.environ',environment,clear=True):
            with self.assertRaises(ValueError) as error:CompetitionClient.from_env()
        self.assertIn('RSAGI_MATCH_ID',str(error.exception))
        self.assertNotIn(environment['RSAGI_TEAM_TOKEN'],str(error.exception))

    def test_single_harness_template_finishes_without_other_teams(self):
        arena=MockArena(teams=('alpha',),rounds=12)
        with MockServer(arena) as server:
            run_harness(self.make(arena,server))
            self.assertEqual((len(arena.steps),arena.logical_tick,arena.provider_calls),(12,60,5))
            self.assertTrue(arena.finished)

    def test_late_reply_after_host_abort_cannot_publish_success(self):
        release=threading.Event();entered=threading.Event()
        def model(team,*args):
            if team=='alpha':entered.set();release.wait(3);return fixture_model(team,*args)
            raise RuntimeError('host fault')
        arena=MockArena(rounds=1,model=model)
        with MockServer(arena) as server:
            alpha=self.make(arena,server);beta=CompetitionClient(server.url,arena.tokens['beta'],allow_mock=True)
            ao=alpha.decide(alpha.round(),1,request_id='late-alpha-decision')
            self.assertTrue(entered.wait(1))
            bo=beta.decide(beta.round(),1,request_id='fault-beta-decision')
            try:self.assertEqual(beta.await_decision(bo['operation_id'])['error'],'HOST_FIXTURE_FAULT')
            finally:release.set()
            for worker in arena.workers:worker.join(1)
            result=alpha.decision(ao['operation_id'])
            self.assertEqual((result['status'],result['error'],result['receipt_id']),('FAILED','MATCH_ABORTED',None))
            self.assertEqual(arena.logical_tick,0)

if __name__=='__main__':unittest.main()
