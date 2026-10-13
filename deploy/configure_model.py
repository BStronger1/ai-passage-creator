#!/usr/bin/env python3
"""Import an existing private Chat Completions configuration without printing keys."""
import argparse
import json
from pathlib import Path
from dotenv import dotenv_values

parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path)
args=parser.parse_args()
source=json.loads(args.source.read_text())
root=Path(__file__).resolve().parents[2]
target=root/'app/python-backend/.env'
if not target.exists():
    raise SystemExit('Run service.py setup first')
values=dict(dotenv_values(target))
for dest,key in [('DASHSCOPE_API_KEY','LLM_API_KEY'),('DASHSCOPE_MODEL','LLM_MODEL'),('DASHSCOPE_BASE_URL','LLM_BASE_URL')]:
    value=source.get(key)
    if not isinstance(value,str) or not value.strip():
        raise SystemExit('Missing field '+key)
    values[dest]=value
# JSON quoting is compatible with the dotenv values used here.
target.write_text(''.join(f'{key}={json.dumps(value or "", ensure_ascii=False)}\n' for key,value in values.items()),encoding='utf-8')
target.chmod(0o600)
print('Configured model: '+values['DASHSCOPE_MODEL'])
