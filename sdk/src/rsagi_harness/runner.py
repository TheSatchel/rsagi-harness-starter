"""Mechanical round recovery only; no game-state memory or planning."""
from .client import APIError

def complete_round(client,round_info,*,choose_credits=None):
    """Continue OPEN/PENDING/DECIDED/READY using host-owned operation handles.

    Restart the controller with the same match credential to recover. Restarting
    Minecraft or moving to a different match is deliberately not supported.
    """
    number=round_info['round_id'];state=round_info['disposition']
    if state=='READY':return
    if state=='OPEN':
        credits=(choose_credits or (lambda r:r['recommended_call_credits']))(round_info)
        if type(credits) is not int or not 1<=credits<=16:raise ValueError('Call target must be an integer from 1 to 16')
        if round_info['available_credits']<credits:
            client.wait(round_info,request_id=f'wait-round-{number}');return
        accepted=client.decide(round_info,credits,request_id=f'decide-round-{number}')
        operation=accepted['operation_id']
    elif state in ('PENDING','DECIDED'):
        operation=round_info.get('active_operation_id')
        if not operation:raise APIError(502,'MISSING_ACTIVE_OPERATION')
    else:raise APIError(502,'UNKNOWN_ROUND_DISPOSITION')
    decision=client.await_decision(operation)
    if decision['round_id']!=number:raise APIError(409,'DECISION_ROUND_MISMATCH')
    if decision['status']=='FAILED':
        if decision['error'] not in ('MODEL_DEADLINE_EXCEEDED','MODEL_OUTPUT_REJECTED'):
            raise APIError(503,'MATCH_ABORTED')
        return  # Host resolved the spent call; never issue another decision.
    revision=decision['proposed_revision_id']
    if revision is not None and revision!=round_info['harness_revision']:
        client.activate(round_info,decision['receipt_id'],revision,request_id=f'activate-round-{number}')
    client.ready(round_info,decision['receipt_id'],request_id=f'ready-round-{number}')

def run_harness(client,*,choose_credits=None):
    last_round=0
    while True:
        round_info=client.next_round(after=last_round)
        if round_info is None:return
        complete_round(client,round_info,choose_credits=choose_credits)
        last_round=round_info['round_id']
