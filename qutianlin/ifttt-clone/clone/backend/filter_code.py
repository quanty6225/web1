"""Bounded JavaScript filter evaluation without host, filesystem or networking APIs."""
import json
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / 'vendor'
if str(VENDOR) not in sys.path: sys.path.insert(0, str(VENDOR))
import quickjs


def validate(code):
    context = quickjs.Context()
    context.set_memory_limit(16 * 1024 * 1024)
    context.set_time_limit(0.1)
    try: context.eval('(function(){\n' + code + '\n})')
    except quickjs.JSException as error: raise ValueError('Invalid filter code: ' + str(error).splitlines()[0][:160]) from None


def evaluate(code, definition, catalog, ingredients, query_steps, timestamp, zone='UTC'):
    context = quickjs.Context()
    context.set_memory_limit(16 * 1024 * 1024)
    context.set_max_stack_size(256 * 1024)
    context.set_time_limit(0.1)
    values = {}
    def assign(path, value):
        pieces = path.split('.')
        if not pieces or any(not re.fullmatch(r'[A-Za-z_$][\w$]*', p) or p in {'__proto__', 'prototype', 'constructor'} for p in pieces):
            return
        target = values
        for piece in pieces[:-1]: target = target.setdefault(piece, {})
        target[pieces[-1]] = value
    trigger = catalog[definition['trigger']['module']]
    for ingredient in trigger['ingredients']:
        if ingredient.get('Filter code'):
            assign(ingredient['Filter code'], ingredients.get(ingredient['Slug'], ''))
    for step in query_steps:
        module = catalog[step['module']]
        for ingredient in module['ingredients']:
            path = ingredient.get('Filter code')
            if path: assign(path.split('[0]')[0] if '[0]' in path else path, step['results'])
    source = '"use strict";\nconst __output = ' + json.dumps([{'skip': False, 'reason': '', 'fields': {}} for _ in definition['actions']]) + ';\n'
    source += 'const __values = ' + json.dumps(values) + '; for (const key of Object.keys(__values)) globalThis[key] = __values[key];\n'
    local_time = datetime.fromtimestamp(timestamp, ZoneInfo(zone))
    clock = {'hour': local_time.hour, 'minute': local_time.minute, 'day': (local_time.weekday()+1)%7, 'iso': local_time.isoformat()}
    source += 'const __clock = '+json.dumps(clock)+'; globalThis.Meta = {currentUserTime:{hour:()=>__clock.hour,minute:()=>__clock.minute,day:()=>__clock.day,format:()=>__clock.iso}};\n'
    source += 'function __parent(path){let object=globalThis;for(const key of path){if(["__proto__","prototype","constructor"].includes(key))throw Error("Invalid field path");object=object[key]||(object[key]={});}return object;}\n'
    source += 'function __method(path,callback){const key=path.pop(),object=__parent(path),previous=object[key];object[key]=(...args)=>{if(typeof previous==="function")previous(...args);callback(...args);};}\n'
    for index, action in enumerate(definition['actions']):
        module = catalog[action['module']]
        skip = module['developer_info'].get('Filter code method', '').split('(')[0]
        if skip:
            pieces = skip.split('.')
            source += '__method(' + json.dumps(pieces) + ',(reason="")=>{__output[' + str(index) + '].skip=true;__output[' + str(index) + '].reason=String(reason);});\n'
        for field in module['fields']:
            method = field.get('Filter code method', '').split('(')[0]
            if method:
                pieces = method.split('.')
                source += '__method(' + json.dumps(pieces) + ',value=>{__output[' + str(index) + '].fields[' + json.dumps(field['Slug']) + ']=String(value);});\n'
    # User code runs inside an isolated VM and cannot access Python callbacks.
    source += '(function(){\n' + code + '\n})();\nJSON.stringify(__output);'
    try:
        result = json.loads(context.eval(source))
        if not isinstance(result, list) or len(result) != len(definition['actions']): raise ValueError('Invalid filter result')
        if len(json.dumps(result)) > 16000: raise ValueError('Filter result is too large')
        for outcome, action in zip(result, definition['actions']):
            allowed = {field['Slug'] for field in catalog[action['module']]['fields']}
            if not isinstance(outcome, dict) or set(outcome) != {'skip', 'reason', 'fields'} or type(outcome['skip']) is not bool or not isinstance(outcome['reason'], str) or not isinstance(outcome['fields'], dict):
                raise ValueError('Invalid filter action result')
            if set(outcome['fields']) - allowed or any(not isinstance(value, str) or len(value)>8000 for value in outcome['fields'].values()):
                raise ValueError('Invalid filter action fields')
        return result
    except (quickjs.JSException, ValueError) as error:
        raise ValueError('Filter code failed: ' + str(error).splitlines()[0][:160]) from None
