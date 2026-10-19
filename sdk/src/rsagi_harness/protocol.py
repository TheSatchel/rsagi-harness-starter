"""Closed request shapes and model-only low-level input validation."""
from __future__ import annotations
import math,re

API_VERSION='0.2.0'
PERCEPTION_POLICY='rsagi-human-player-view-v1'
KEYS=('forward','back','left','right','jump','sneak','sprint','attack','use','drop')
ROLES=('observer','reasoner','actor','reviewer')

class ProtocolError(ValueError):
    def __init__(self,code,status=400):
        self.code=code;self.status=status;super().__init__(code)

def require(condition,code='INVALID_REQUEST',status=400):
    if not condition:raise ProtocolError(code,status)

def shape(value,required,optional=()):
    require(type(value) is dict and set(required)<=set(value)<=set(required)|set(optional))

def integer(value,low=0,high=2**53-1):
    require(type(value) is int and low<=value<=high)

def identifier(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value) is not None)

def validate_model_decision(value):
    """Organizer-side only. A participant may submit a receipt, never this object."""
    shape(value,['action','explanation'],['harness_update'])
    action=value['action'];require(type(action) is dict)
    kind=action.get('type')
    if kind=='WAIT':shape(action,['type'])
    elif kind=='INPUT':
        shape(action,['type','keys','look_delta'],['hotbar'])
        require(type(action['keys']) is list and len(action['keys'])<=len(KEYS))
        require(all(type(k) is str and k in KEYS for k in action['keys']))
        require(len(set(action['keys']))==len(action['keys']))
        shape(action['look_delta'],['yaw','pitch'])
        for key,limit in [('yaw',180),('pitch',90)]:
            n=action['look_delta'][key]
            require(type(n) in (int,float) and math.isfinite(n) and -limit<=n<=limit)
        if 'hotbar' in action:integer(action['hotbar'],0,8)
    elif kind=='GUI_CLICK':
        shape(action,['type','x','y','button','shift'])
        integer(action['x'],0,1279);integer(action['y'],0,719)
        require(action['button'] in ('left','right') and type(action['shift']) is bool)
    elif kind=='KEY_PRESS':
        shape(action,['type','key']);require(action['key'] in ('f3','inventory','escape'))
    elif kind=='CHAT':
        shape(action,['type','text']);text=action['text']
        require(type(text) is str and 0<len(text)<=256 and not text.lstrip().startswith('/') and '\n' not in text and '\r' not in text)
    else:raise ProtocolError('UNSUPPORTED_ACTION')
    explanation=value['explanation'];shape(explanation,['evidence','reason','expected'])
    require(all(type(s) is str and s.strip() and len(s)<=1000 for s in explanation.values()),'INVALID_EXPLANATION')
    update=value.get('harness_update')
    if update is not None:
        shape(update,['roles','next_call_credits'])
        roles=update['roles'];require(type(roles) is list and 1<=len(roles)<=4)
        require(all(type(role) is str and role in ROLES for role in roles))
        require(len(set(roles))==len(roles))
        integer(update['next_call_credits'],1,16)
    return value

def action_schema():
    def obj(properties,required=None):
        return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False}
    explanation=obj({name:{'type':'string','minLength':1,'maxLength':1000,'pattern':r'\S'} for name in ['evidence','reason','expected']})
    inputs=obj({'type':{'const':'INPUT'},'keys':{'type':'array','maxItems':len(KEYS),'uniqueItems':True,'items':{'enum':list(KEYS)}},
      'look_delta':obj({'yaw':{'type':'number','minimum':-180,'maximum':180},'pitch':{'type':'number','minimum':-90,'maximum':90}}),
      'hotbar':{'type':'integer','minimum':0,'maximum':8}},['type','keys','look_delta'])
    actions=[obj({'type':{'const':'WAIT'}}),inputs,
      obj({'type':{'const':'GUI_CLICK'},'x':{'type':'integer','minimum':0,'maximum':1279},'y':{'type':'integer','minimum':0,'maximum':719},'button':{'enum':['left','right']},'shift':{'type':'boolean'}}),
      obj({'type':{'const':'KEY_PRESS'},'key':{'enum':['f3','inventory','escape']}}),
      obj({'type':{'const':'CHAT'},'text':{'type':'string','minLength':1,'maxLength':256,'pattern':r'^(?!\s*/)[^\r\n]+$'}})]
    update=obj({'roles':{'type':'array','minItems':1,'maxItems':4,'uniqueItems':True,'items':{'enum':list(ROLES)}},'next_call_credits':{'type':'integer','minimum':1,'maximum':16}})
    return obj({'action':{'oneOf':actions},'explanation':explanation,'harness_update':{'anyOf':[update,{'type':'null'}]}},['action','explanation'])
