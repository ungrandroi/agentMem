"""One-operation tool contracts for relative and absolute movement."""
DIRECTIONS=('up','down','left','right')
MOVE='Walls and closed doors block movement. Keys do not block movement and are not picked up automatically.'
PICKUP='Pick up the key on your CURRENT tile into inventory. You may hold multiple keys.'
TOGGLE='Unlock and open, or open/close, the adjacent door. Unlocking consumes a matching ordinary key; if unavailable, a held master key opens the door without being consumed. A master key stays in inventory and can unlock any number of doors. Unlocked doors never relock; reopening or closing costs no key.'
LEGACY_TOGGLE='Unlock and open, or open/close, the adjacent door. Unlocking consumes a matching ordinary key; if unavailable, it consumes one master key. A master key unlocks any ONE door. Unlocked doors never relock; reopening or closing costs no key.'
COST=' Each call costs one step, including ineffective actions. The environment ends the task at G or when the budget is exhausted.'
RELATIVE=('left','right','forward','pickup','toggle')
ABSOLUTE=(*DIRECTIONS,'pickup',*(f'toggle_{d}' for d in DIRECTIONS))
def tool(name,description,props):
 return {'type':'function','function':{'name':name,'description':description+COST,'parameters':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}}
def tools_for(mode,reusable_master=True,six_tools=True):
 toggle=TOGGLE if reusable_master else LEGACY_TOGGLE
 if mode=='relative':
  return [tool('step','left/right turn 90 degrees in place; forward moves one tile in the facing direction. '+MOVE+' pickup: '+PICKUP+' toggle: '+toggle+' In this mode the door must be directly ahead.',{'action':{'type':'string','enum':list(RELATIVE)}})]
 if mode!='absolute':raise ValueError('Unknown action mode')
 direction={'type':'string','enum':list(DIRECTIONS)}
 if six_tools:
  return [*(tool(d,'Move one tile '+d+' on the map. '+MOVE,{}) for d in DIRECTIONS),tool('pickup',PICKUP,{}),tool('use',toggle+' Specify the adjacent map direction.',{'direction':direction})]
 return [tool('move','Move one tile in the specified map direction, regardless of prior movement. '+MOVE,{'direction':direction}),tool('pickup',PICKUP,{}),tool('toggle',toggle+' Specify the adjacent map direction.',{'direction':direction})]
def encode_action(mode,action,*,six_tools=True):
 if mode=='relative':return 'step',{'action':action}
 if action=='pickup':return 'pickup',{}
 if action.startswith('toggle_'):return ('use' if six_tools else 'toggle'),{'direction':action[7:]}
 return (action,{}) if six_tools else ('move',{'direction':action})
def decode_action(mode,name,args,*,six_tools=True):
 from experiments.action_protocol import parse_action
 import json
 parse_action(json.dumps({'name':name,'args':args}),tools_for(mode,six_tools=six_tools))
 if mode=='relative':return args['action']
 if six_tools:return 'toggle_'+args['direction'] if name=='use' else name
 return 'pickup' if name=='pickup' else 'toggle_'+args['direction'] if name=='toggle' else args['direction']
