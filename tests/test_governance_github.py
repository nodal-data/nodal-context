"""Offline trust-boundary tests for protected GitHub authority, no credentials."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import governance_github as g


def reject(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('unsafe evidence accepted')


def run():
    protection={'required_pull_request_reviews':{'required_approving_review_count':1,'dismiss_stale_reviews':True,
        'require_code_owner_reviews':True}, 'required_status_checks':{'strict':True,'contexts':['validate','approval-policy']},
        'enforce_admins':{'enabled':True}}
    with patch.object(g,'api',return_value=protection):
        g.protection('org/repo','main')
    for edit in (lambda p:p['required_pull_request_reviews'].update(dismiss_stale_reviews=False),
                 lambda p:p['enforce_admins'].update(enabled=False),
                 lambda p:p['required_status_checks'].update(contexts=['validate']),
                 lambda p:p.update(allow_force_pushes={'enabled':True})):
        invalid=deepcopy(protection);edit(invalid)
        with patch.object(g,'api',return_value=invalid):reject(lambda:g.protection('org/repo','main'))
    state={'restrictions':{'users':[{'login':'authority'}],'apps':[],'teams':[]},'enforce_admins':{'enabled':True}}
    with patch.dict(os.environ,{'ACF_GOVERNANCE_WRITER':'authority'}),patch.object(g,'api',return_value=state):
        g.state_protection('org/repo')
        state['restrictions']['users'].append({'login':'author'})
        reject(lambda:g.state_protection('org/repo'))
    now=datetime.now(timezone.utc)
    fresh={'revision':'repair','content_digest':'content','checked_at':now.isoformat(),
           'expires_at':(now+timedelta(hours=1)).isoformat(),
           'sources':{'dbt':{'status':'checked','revision':'source','digest':'hash'}}}
    block={'recorded_at':(now-timedelta(hours=1)).isoformat()}
    check={'head_sha':'repair','status':'completed','conclusion':'success','updated_at':now.isoformat(),'name':'behavior'}
    url='https://github.com/org/repo/actions/runs/12'
    with patch.object(g,'api',return_value=check):
        assert g.repair_checks('org/repo',[url],'repair',block,fresh,'content',['dbt'])
        reject(lambda:g.repair_checks('org/repo',[url],'repair',block,fresh,'content',['missing']))
        reject(lambda:g.repair_checks('org/repo',['https://example.com/pass'],'repair',block,fresh,'content',['dbt']))
        check['head_sha']='unrelated'
        reject(lambda:g.repair_checks('org/repo',[url],'repair',block,fresh,'content',['dbt']))
    # Compare-and-swap protects a concurrently published block from lost writes.
    with patch.object(g,'api',return_value={}) as api:
        g.write_store('org/repo',{'events':[]},'expected-blob')
        assert api.call_args.kwargs['data']['sha']=='expected-blob'
    print('test_governance_github: OK')


if __name__=='__main__':run()
