"""Export the participant HTTP contract; no running service is created."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sdk/src'))
from rsagi_harness.protocol import API_VERSION,action_schema

def obj(properties,required=None):
    return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False}
def ref(name):return {'$ref':'#/components/schemas/'+name}
def response(name,description):return {'description':description,'content':{'application/json':{'schema':ref(name)}}}

def build():
    identifier={'type':'string','pattern':'^[A-Za-z0-9_-]{1,128}$'}
    nullable_id={'anyOf':[identifier,{'type':'null'}]}
    integer={'type':'integer','minimum':0,'maximum':2**53-1}
    mode={'enum':['protocol_mock','native_training','strict_competition']}
    schemas={
      'Error':obj({'error':obj({'code':{'type':'string'}})}),
      'Capabilities':obj({key:{'type':'boolean'} for key in ['human_view_capture','native_game_execution','real_model','self_organization_config','arbitrary_code_hot_update','strict_certified']}),
      'Session':obj({'api_version':{'const':API_VERSION},'mode':mode,'match_id':identifier,'team_id':identifier,
        'perception_policy':{'const':'rsagi-human-player-view-v1'},'ticks_per_round':{'const':5},'rounds_per_logical_second':{'const':4},
        'credit_cap':{'const':16},'tokens_per_credit':{'const':512},'seconds_per_credit':{'const':10},'max_model_calls_per_round':{'const':1},
        'f3_allowed':{'const':True},'screen':obj({'width':{'const':1280},'height':{'const':720}}),'capabilities':ref('Capabilities')}),
      'Round':obj({'mode':mode,'phase':{'enum':['COLLECTING','FINISHED','ABORTED']},'round_id':{'type':'integer','minimum':1},'logical_tick':integer,
        'available_credits':{'type':'integer','minimum':0,'maximum':16},'observation_ref':nullable_id,'harness_revision':identifier,
        'recommended_call_credits':{'type':'integer','minimum':1,'maximum':16},'disposition':{'enum':['OPEN','PENDING','DECIDED','READY']},'finished':{'type':'boolean'}}),
      'DecideRequest':obj({'round_id':{'type':'integer','minimum':1},'observation_ref':identifier,'credits':{'type':'integer','minimum':1,'maximum':16},'harness_revision':identifier}),
      'RoundRequest':obj({'round_id':{'type':'integer','minimum':1}}),
      'ReadyRequest':obj({'round_id':{'type':'integer','minimum':1},'receipt_id':identifier}),
      'ActivateRequest':obj({'round_id':{'type':'integer','minimum':1},'receipt_id':identifier,'revision_id':identifier}),
      'Accepted':obj({'mode':mode,'operation_id':identifier,'status':{'const':'PENDING'}}),
      'Usage':obj({'kind':{'enum':['synthetic_mock','provider_reported']},'input_tokens':integer,'output_tokens':integer,'reasoning_tokens':integer}),
      'Decision':obj({'mode':mode,'operation_id':identifier,'round_id':{'type':'integer','minimum':1},'status':{'enum':['PENDING','SUCCEEDED','FAILED']},
        'receipt_id':nullable_id,'proposed_revision_id':nullable_id,'usage':{'anyOf':[ref('Usage'),{'type':'null'}]},'error':{'type':['string','null']}}),
      'Acknowledgement':obj({'mode':mode,'accepted_round':{'type':'integer','minimum':1},'disposition':{'enum':['READY','REVISION_ACTIVATED']}}),
      'ModelDecision':action_schema()
    }
    errors={str(code):response('Error',description) for code,description in [(400,'Invalid fields, values or idempotency key'),(401,'Invalid team credential'),(404,'Unknown or non-owned object'),(409,'Round, quota, receipt, revision or idempotency conflict'),(413,'Request body too large'),(415,'JSON required'),(500,'Host error; formal runtime must stop safely')]}
    def operation(name,description,result,request=None,status='200',parameters=None):
        value={'operationId':name,'description':description,'responses':{status:response(result,'Success'),**errors}}
        if request:
            value['requestBody']={'required':True,'content':{'application/json':{'schema':ref(request)}}}
            value['parameters']=[{'$ref':'#/components/parameters/IdempotencyKey'}]
        if parameters:value.setdefault('parameters',[]).extend(parameters)
        return value
    paths={
      '/v1/session':{'get':operation('getSession','Own team binding and public protocol settings; capability booleans are not certification.','Session')},
      '/v1/round':{'get':operation('getRound','Own released boundary only; repeated reads never produce more world information. No other teams or world state.','Round')},
      '/v1/decisions':{'post':operation('createDecision','Atomically pre-charge one call. Host supplies bound perception and original context; request cannot contain prompts, images, history or actions.','Accepted','DecideRequest','202')},
      '/v1/decisions/{operation_id}':{'get':operation('getDecision','Poll an owned operation. Receipt and mechanical usage only; no world-semantic output returned to the controller.','Decision',parameters=[{'in':'path','name':'operation_id','required':True,'schema':identifier}])},
      '/v1/wait':{'post':operation('waitAndBank','Zero-call, neutral-input ready; preserve quota. Global step occurs only after all teams resolve.','Acknowledgement','RoundRequest')},
      '/v1/ready':{'post':operation('commitDecision','Commit exactly the host-held model action using an owned round-bound receipt. No client-authored action payload.','Acknowledgement','ReadyRequest')},
      '/v1/harness/activate':{'post':operation('activateModelProposedPolicy','Activate only a configuration revision produced by that model operation. No arbitrary source upload or world notes.','Acknowledgement','ActivateRequest')}
    }
    spec={'openapi':'3.1.1','info':{'title':'RSAGI participant Harness API','version':API_VERSION,
      'description':'PROTOCOL MOCK ONLY today. No live competition endpoint, native perception/execution or inference is connected. 512 tokens/10 seconds, 1280x720 are starter parameters, not frozen match rules.'},
      'servers':[{'url':'http://127.0.0.1:{port}','description':'Local protocol mock; use its allocated loopback port. No production endpoint advertised.','variables':{'port':{'default':'8000'}}}],
      'security':[{'TeamBearer':[]}],'paths':paths,
      'components':{'securitySchemes':{'TeamBearer':{'type':'http','scheme':'bearer','description':'One opaque credential bound to one match and team, not a Minecraft or model-provider credential.'}},
        'parameters':{'IdempotencyKey':{'in':'header','name':'Idempotency-Key','required':True,'schema':{'type':'string','pattern':'^[A-Za-z0-9_-]{8,128}$'},'description':'Reuse exactly the same key and body after uncertain transport. A changed body conflicts. Successful records remain for the match.'}},'schemas':schemas},
      'x-runtime-status':'protocol_mock_only_not_competition_ready'}
    out=ROOT/'api/openapi.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
    decision={'$schema':'https://json-schema.org/draft/2020-12/schema',**action_schema()}
    (ROOT/'api/model-decision.schema.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2)+'\n')
    return spec

if __name__=='__main__':
    spec=build();print(json.dumps({'openapi':spec['openapi'],'api_version':API_VERSION,'paths':len(spec['paths']),'runtime':spec['x-runtime-status']}))
