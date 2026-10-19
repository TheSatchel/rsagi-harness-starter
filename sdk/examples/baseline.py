"""Replace scheduling hooks to build your harness. Store no semantic world notes."""
from rsagi_harness import CompetitionClient

def run(client):
    last_round=0
    while True:
        round_info=client.next_round(after=last_round)
        if round_info is None:return
        number=round_info['round_id']
        target=round_info['recommended_call_credits']
        if round_info['available_credits']<target:
            client.wait(round_info,request_id=f'wait-round-{number}')
        else:
            accepted=client.decide(round_info,target,request_id=f'decide-round-{number}')
            decision=client.await_decision(accepted['operation_id'])
            if decision['status']=='SUCCEEDED':
                revision=decision['proposed_revision_id']
                if revision is not None:
                    client.activate(round_info,decision['receipt_id'],revision,request_id=f'activate-round-{number}')
                client.ready(round_info,decision['receipt_id'],request_id=f'ready-round-{number}')
            # Failed calls are resolved by the host, with spent credits retained.
        last_round=number

if __name__=='__main__':run(CompetitionClient.from_env())
