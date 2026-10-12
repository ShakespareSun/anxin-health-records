import json,time
import pytest,httpx,jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
import chatgpt_connection as connection
import ai_service
from tests_fixture import clinical_report

def test_callback_state_expiry_and_client_binding(monkeypatch):
    monkeypatch.setattr(connection,'validate_identity',lambda *a:pytest.fail('must not process invalid callback'))
    p={'expires':time.time()+60,'state':'expected','client_id':'saved'}
    for q in [{'state':'wrong'}, {'state':'expected','client_id':'other','code':'x'}]:
        with pytest.raises(connection.ConnectionError):connection.exchange_callback(q,p)
    p['expires']=0
    with pytest.raises(connection.ConnectionError):connection.exchange_callback({'state':'expected'},p)

def test_jwt_checks_signature_issuer_audience_expiry_nonce(monkeypatch):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));jwk['kid']='test-key'
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,*args,**kwargs):return httpx.Response(200,json={'keys':[jwk]},request=httpx.Request('GET','https://auth.openai.com/keys'))
    monkeypatch.setattr(connection.httpx,'Client',Client)
    claims={'sub':'account','iss':connection.ISSUER,'aud':'client','exp':time.time()+60,'iat':time.time(),'nonce':'nonce'}
    def token(c,k=key):return jwt.encode(c,k,algorithm='RS256',headers={'kid':'test-key'})
    assert connection.validate_identity(token(claims),'client','nonce','https://auth.openai.com/keys')['sub']=='account'
    for changed in [{'iss':'https://other.example'},{'aud':'other'},{'exp':1},{'nonce':'bad'}]:
        with pytest.raises((connection.ConnectionError,jwt.PyJWTError)):connection.validate_identity(token({**claims,**changed}),'client','nonce','https://auth.openai.com/keys')
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    with pytest.raises(jwt.PyJWTError):connection.validate_identity(token(claims,other),'client','nonce','https://auth.openai.com/keys')

def test_cloud_gate_stale_context_and_invalid_citations(monkeypatch):
    rs=[clinical_report()];monkeypatch.setattr(ai_service,'reports',lambda:rs)
    called=[]
    monkeypatch.setattr(connection,'request_completion',lambda *a:called.append(a) or {'text':'来源 [R999]','usage':{},'model':'test'})
    body={'question':'这个数值是什么','model':'test','fingerprint':ai_service.fingerprint(rs)}
    with pytest.raises(HTTPException) as e:ai_service.complete(body)
    assert e.value.status_code==400 and not called
    with pytest.raises(HTTPException) as e:ai_service.complete({**body,'allow_cloud':True,'fingerprint':'old'})
    assert e.value.status_code==409 and not called
    with pytest.raises(HTTPException) as e:ai_service.complete({**body,'allow_cloud':True})
    assert e.value.status_code==502

def test_stream_must_complete_and_uses_subscription_parameters(monkeypatch):
    monkeypatch.setattr(connection,'access_token',lambda:('synthetic-token','test-client'))
    monkeypatch.setattr(connection,'CATALOG',{'test-client':[{'id':'test-model'}]})
    seen=[];events=[{'type':'response.output_text.delta','delta':'回答 [R1]'}]
    class Stream:
        is_success=True
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_lines(self):return iter('data: '+json.dumps(e) for e in events)
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self,*args,**kwargs):seen.append(kwargs['json']);return Stream()
    monkeypatch.setattr(connection.httpx,'Client',Client)
    with pytest.raises(connection.ConnectionError):connection.request_completion('test-model','instructions',[{'role':'user','content':'question'}])
    assert seen[-1]['store'] is False and seen[-1]['stream'] is True and 'max_output_tokens' not in seen[-1]
    events.append({'type':'response.completed','response':{'usage':{'total_tokens':100}}})
    assert connection.request_completion('test-model','instructions',[])['usage']['total_tokens']==100

def test_windows_credential_encryption_round_trip():
    import os
    if os.name!='nt':pytest.skip('Windows DPAPI')
    from win_secret import protect_bytes
    raw=b'synthetic secret'
    cipher=protect_bytes(raw)
    assert raw not in cipher and protect_bytes(cipher,decrypt=True)==raw

def test_completed_chat_and_analysis_persist_with_source_version(monkeypatch):
    rs=[clinical_report()];monkeypatch.setattr(ai_service,'reports',lambda:rs)
    captured=[]
    monkeypatch.setattr(connection,'request_completion',lambda *args:captured.append(args) or {'text':'CA125 为 10.10，需结合参考区间。 [R1]','usage':{'total_tokens':100},'model':'test'})
    body={'question':'解释这个指标','model':'test','allow_cloud':True,'fingerprint':ai_service.fingerprint(rs)}
    result=ai_service.complete(body)
    assert result['messages'][-1]['sources']==[1] and result['messages'][-1]['usage']['total_tokens']==100
    result=ai_service.complete(body,analysis=True)
    assert not result['stale'] and result['sources']==[1]
    rs[0]['observations'][0]['value']='10'
    assert ai_service.saved_analysis()['stale']
