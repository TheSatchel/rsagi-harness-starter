"""Compact model controls, mechanically expanded by the organizer's client.

No positions, world queries, target IDs, routes or task-completion conditions.
vel is local input strength, not permission to set an entity's world velocity.
"""
from __future__ import annotations
import math

CONTROL_FIELDS=('vel','look','do','ticks','slot','mode','jump')
INTERACTIONS=('none','mine','attack','use','hold_use')
MODES=('walk','sprint','sneak')

def control_settings():
    return {'profile':'compact_vel3_v1','auto_jump':True,'turn_degrees_per_logical_second':180,
      'default_action_ticks':5,'max_action_ticks':80,'hotbar_first_slot':1}

def vector(value,name,limits):
    if type(value) is not list or len(value)!=len(limits):raise ValueError('INVALID_'+name)
    if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>limit for v,limit in zip(value,limits)):
        raise ValueError('INVALID_'+name)
    return value

def validate_control(action):
    if type(action) is not dict or not set(action)<=set(CONTROL_FIELDS):raise ValueError('INVALID_CONTROL_FIELDS')
    if 'vel' in action:vector(action['vel'],'VEL',(1,1,1))
    if 'look' in action:vector(action['look'],'LOOK',(180,90))
    if 'do' in action and (type(action['do']) is not str or action['do'] not in INTERACTIONS):raise ValueError('INVALID_INTERACTION')
    if 'ticks' in action and (type(action['ticks']) is not int or not 1<=action['ticks']<=80):raise ValueError('INVALID_TICKS')
    if 'slot' in action and (type(action['slot']) is not int or not 1<=action['slot']<=9):raise ValueError('INVALID_SLOT')
    if 'mode' in action and (type(action['mode']) is not str or action['mode'] not in MODES):raise ValueError('INVALID_MODE')
    if 'jump' in action and type(action['jump']) is not bool:raise ValueError('INVALID_JUMP')
    return action

def native_fields(action):
    """Trusted executor codec only; participants still submit model receipts.

    Defaults replace prior controls. Only explicit WAIT preserves an unexpired
    lease; {} is an explicit stop of the previous movement/interaction.
    """
    validate_control(action)
    forward,right,turn=action.get('vel',[0,0,0]);length=math.hypot(forward,right)
    if length>1:forward,right=forward/length,right/length
    yaw,pitch=action.get('look',[0,0])
    result={'type':'ACT','forward':str(forward),'right':str(right),'turn':str(turn),'yaw':str(yaw),'pitch':str(pitch),
      'interaction':action.get('do','none'),'hold_ticks':str(action.get('ticks',5)),
      'mode':action.get('mode','walk'),'jump':str(action.get('jump',False)).lower()}
    if 'slot' in action:result['hotbar']=str(action['slot']-1)
    return result

def view_quaternion(yaw,pitch):
    """Optional math helper, [w,x,y,z], no roll, MC axes: +yaw right, +pitch down.

    Uses the q/-q hemisphere convention w>=0 (lexicographic sign at w==0).
    Models use two degree angles; they never need to generate or normalize q.
    This is orientation arithmetic, not a world observation or target selection.
    """
    for angle in (yaw,pitch):
        if type(angle) not in (int,float) or not math.isfinite(angle):raise ValueError('INVALID_VIEW_ANGLE')
    if abs(pitch)>90:raise ValueError('INVALID_PITCH')
    a=math.radians(yaw)/2;b=math.radians(pitch)/2
    q=[math.cos(a)*math.cos(b),math.cos(a)*math.sin(b),-math.sin(a)*math.cos(b),math.sin(a)*math.sin(b)]
    first=next((n for n in q if abs(n)>1e-15),0)
    return [-n for n in q] if first<0 else q

def control_schema():
    def vector_schema(limits,description):
        return {'type':'array','minItems':len(limits),'maxItems':len(limits),
          'prefixItems':[{'type':'number','minimum':-n,'maximum':n} for n in limits],
          'items':False,'description':description}
    return {'type':'object','properties':{
      'vel':{**vector_schema((1,1,1),'[forward, right, turn] local input strengths. Positive=forward/right/clockwise. Translation clamped to unit length. turn=1 means +180 degrees per logical second, applied at +9 degrees per native tick.'),'default':[0,0,0]},
      'look':{**vector_schema((180,90),'Relative degrees [yaw, pitch], +right/+down. Applied once before continuous vel turning. Native pitch clamps to [-90,90].'),'default':[0,0]},
      'do':{'enum':list(INTERACTIONS),'default':'none','description':'At the current crosshair: hold mine, tap attack/use, or hold use. No target selection.'},
      'ticks':{'type':'integer','minimum':1,'maximum':80,'default':5,'description':'Logical client ticks only; zero wall-clock progress during inference.'},
      'slot':{'type':'integer','minimum':1,'maximum':9,'description':'Visible hotbar key 1..9.'},
      'mode':{'enum':list(MODES),'default':'walk'},
      'jump':{'type':'boolean','default':False,'description':'Optional explicit jump/swim input; vanilla auto-jump is enabled uniformly.'}},
      'additionalProperties':False,
      'description':'Compact character control; missing fields reset to defaults, {} stops prior input. Not a world velocity setter or planner.'}
