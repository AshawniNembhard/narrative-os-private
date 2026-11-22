"""Explicitly billed API AI alternative for hosted Narrative OS.
No localhost ChatGPT OAuth tokens are used in cloud mode.
"""
import json
import os
import urllib.request

def configured():return bool(os.getenv('OPENAI_API_KEY','').strip())

def infer_json(system,payload):
    key=os.getenv('OPENAI_API_KEY','').strip()
    if not key:raise ValueError('Set OPENAI_API_KEY in host secrets to enable cloud AI')
    body={'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),
          'messages':[{'role':'system','content':system},
                      {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
          'response_format':{'type':'json_object'}}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',
        method='POST',data=json.dumps(body).encode(),headers={
         'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=65) as resp:answer=json.load(resp)
    return json.loads(answer['choices'][0]['message']['content'])