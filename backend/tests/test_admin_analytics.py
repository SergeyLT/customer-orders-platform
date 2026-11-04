from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from customer_orders.auth import COOKIE, digest, now
from customer_orders.manage import create_invite
from customer_orders.models import Admin, AdminSession, AnalyticsDaily, BehaviorEvent, SetupInvite, Visit
from customer_orders.analytics import cleanup
from customer_orders.demo import EXAMPLES, create_demo
from customer_orders.priority import evaluate

GUARD = {"X-Requested-With": "CustomerOrders"}
PASSWORD = "synthetic-password-at-least-16"


def invite(engine):
    with Session(engine) as session, session.begin():
        return create_invite(session)


def test_setup_requires_code_one_use_and_preserves_data(client, engine, service):
    # service fixture already creates admin, поэтому закрытая регистрация обязательна.
    assert client.post('/api/auth/setup', headers=GUARD, json={"code":"x"*43,"username":"intruder","password":PASSWORD}).status_code == 403


def test_setup_reissue_concurrent_and_password_hash(client, engine):
    assert client.get('/api/auth/setup/status').json() == {'setup_available': True}
    old = invite(engine)
    code = invite(engine)
    assert client.post('/api/auth/setup/check',headers=GUARD,json={"code":old}).status_code == 403
    assert client.post('/api/auth/setup/check',headers=GUARD,json={"code":code}).status_code == 200
    body={"code":code,"username":"owner","password":PASSWORD}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:client.post('/api/auth/setup',headers=GUARD,json=body),range(2)))
    assert sorted(r.status_code for r in responses)==[201,403]
    with Session(engine) as session:
        record=session.scalar(select(Admin))
        assert record.password_hash.startswith('$argon2id$') and PASSWORD not in record.password_hash
        assert session.get(SetupInvite,1) is None
    assert client.post('/api/auth/setup/check',headers=GUARD,json={"code":code}).status_code==403
    assert client.get('/api/auth/setup/status').json() == {'setup_available': False}
    client.cookies.clear()
    assert client.get('/api/auth/setup/status').json() == {'setup_available': False}
    with Session(engine) as session, session.begin():
        session.scalar(select(Admin)).is_active = False
    assert client.get('/api/auth/setup/status').json() == {'setup_available': False}


def test_expired_invite(client,engine):
    code=invite(engine)
    with Session(engine) as s,s.begin():s.get(SetupInvite,1).expires_at=now()-timedelta(seconds=1)
    assert client.post('/api/auth/setup',headers=GUARD,json={"code":code,"username":"owner","password":PASSWORD}).status_code==403


def test_csrf_cookie_logout_and_basic_disabled(client,admin):
    assert client.get('/api/auth/me').status_code==200
    assert client.post('/api/admin/services',json={}).status_code==403
    assert client.post('/api/auth/logout',headers={**admin,"Origin":"https://other.example"}).status_code==403
    token=client.cookies.get(COOKIE)
    assert client.post('/api/auth/logout',headers=admin).status_code==204
    assert client.get('/api/auth/me').status_code==401
    client.cookies.set(COOKIE,token)
    assert client.get('/api/auth/me').status_code==401
    client.cookies.clear()
    assert client.get('/api/admin/services',auth=('admin','test-admin-password-only-123')).status_code==401


def test_tampered_jwt(client,admin):
    client.cookies.clear();client.cookies.set(COOKIE,'not-a-jwt')
    assert client.get('/api/auth/me').status_code==401


def test_expired_and_wrong_audience_tokens(client,admin,engine):
    import jwt
    from customer_orders.core import get_settings
    with Session(engine) as s,s.begin():
        row=s.scalar(select(AdminSession));row.expires_at=now()-timedelta(seconds=1)
    assert client.get('/api/auth/me').status_code==401
    secret=get_settings().jwt_secret.get_secret_value()
    token=jwt.encode({'sub':str(uuid4()),'jti':str(uuid4()),'iat':now(),'exp':now()+timedelta(hours=1),'iss':'customer-orders','aud':'other-app'},secret,algorithm='HS256')
    client.cookies.clear();client.cookies.set(COOKIE,token)
    assert client.get('/api/auth/me').status_code==401


def test_production_cookie_flags(client,admin,monkeypatch):
    from customer_orders.core import get_settings
    monkeypatch.setattr(get_settings(),'cookie_secure',True)
    response=client.post('/api/auth/login',headers=GUARD,json={'username':'admin','password':'test-admin-password-only-123'})
    assert response.status_code==200
    cookie=response.headers['set-cookie']
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Path=/api' in cookie


def test_active_time_and_device_separation(client,admin,engine):
    visit=client.post('/api/analytics/visits',json={'consent':True,'device':'mobile'}).json()
    from uuid import UUID
    with Session(engine) as s,s.begin():s.get(Visit,UUID(visit['visit_id'])).last_at=now()-timedelta(seconds=15)
    body={**visit,'batch_id':str(uuid4()),'active_ms':10000,'events':[]}
    assert client.post('/api/analytics/batches',json=body).status_code==202
    assert client.post('/api/analytics/batches',json=body).json()['duplicate']
    mobile=client.get('/api/admin/analytics?device=mobile',headers=admin).json()
    assert mobile['periods'][0]['average_active_seconds']==10
    assert client.get('/api/admin/analytics?device=desktop',headers=admin).json()['periods'][0]['visits']==0


def test_login_guard_and_rate_limit(client,admin):
    client.cookies.clear()
    body={"username":"missing","password":"wrong"}
    assert client.post('/api/auth/login',json=body).status_code==403
    for _ in range(10):assert client.post('/api/auth/login',headers=GUARD,json=body).status_code==401
    assert client.post('/api/auth/login',headers=GUARD,json=body).status_code==429


def test_admin_management_last_admin_and_revocation(client,admin):
    me=client.get('/api/auth/me').json()['admin']
    assert client.patch('/api/admin/admins/'+me['id'],headers=admin,json={"is_active":False}).status_code==409
    second=client.post('/api/admin/admins',headers=admin,json={"username":"second","password":PASSWORD})
    assert second.status_code==201
    assert 'password' not in second.text
    sid=second.json()['id']
    assert client.post('/api/admin/admins',headers=admin,json={"username":"SECOND","password":PASSWORD}).status_code==409
    cookie=client.cookies.get(COOKIE)
    response=client.post('/api/auth/login',headers=GUARD,json={"username":"second","password":PASSWORD})
    second_token=client.cookies.get(COOKIE)
    client.cookies.clear();client.cookies.set(COOKIE,cookie)
    assert client.patch('/api/admin/admins/'+sid,headers=admin,json={"is_active":False}).status_code==200
    client.cookies.clear();client.cookies.set(COOKIE,second_token)
    assert client.get('/api/auth/me').status_code==401


def test_change_own_password_revokes_sessions(client,admin):
    assert client.post('/api/auth/password',headers=admin,json={"current_password":"test-admin-password-only-123","new_password":PASSWORD}).status_code==204
    assert client.get('/api/auth/me').status_code==401
    response=client.post('/api/auth/login',headers=GUARD,json={"username":"admin","password":PASSWORD})
    assert response.status_code==200 and 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']


def test_analytics_requires_consent_validates_and_deduplicates(client,admin,engine):
    assert client.post('/api/analytics/visits',json={"consent":False,"device":"desktop"}).status_code==422
    visit=client.post('/api/analytics/visits',json={"consent":True,"device":"desktop"}).json()
    body={**visit,"batch_id":str(uuid4()),"active_ms":0,"events":[{"kind":"click","target":"service","x":5000,"y":3000,"width":1200,"height":3000},{"kind":"selected","target":"service","width":1200,"height":3000}]}
    assert client.post('/api/analytics/batches',json={**body,"token":"x"*43}).status_code==403
    assert client.post('/api/analytics/batches',json=body).status_code==202
    assert client.post('/api/analytics/batches',json=body).json()['duplicate']
    assert client.post('/api/analytics/batches',json={**body,"email":"private@example.com"}).status_code==422
    report=client.get('/api/admin/analytics',headers=admin).json()
    assert report['periods'][0]['visits']==1 and report['periods'][0]['selected']==1
    assert client.get('/api/admin/analytics?kind=click',headers=admin).json()['heatmap'][0]['count']==1
    with Session(engine) as s:
        assert len(list(s.scalars(select(BehaviorEvent))))==2


def test_analytics_retention_preserves_aggregates(client,engine):
    visit=client.post('/api/analytics/visits',json={"consent":True,"device":"mobile"}).json()
    with Session(engine) as s,s.begin():
        from uuid import UUID
        s.get(Visit,UUID(visit['visit_id'])).created_at=now()-timedelta(days=31)
    with Session(engine) as s,s.begin():cleanup(s)
    with Session(engine) as s:
        assert not list(s.scalars(select(Visit)))
        assert len(list(s.scalars(select(AnalyticsDaily))))==1


def test_priority_examples_manual_override_and_search(client,admin,service,engine):
    with Session(engine) as s,s.begin():create_demo(s)
    with Session(engine) as s,s.begin():create_demo(s)
    response=client.get('/api/admin/orders',headers=admin).json()
    assert response['total']==10
    levels=[x['effective_priority'] for x in response['items']]
    assert levels==['high']*4+['medium']*3+['low']*3
    item=response['items'][-1]
    assert client.patch('/api/admin/applications/'+item['id']+'/priority',headers=admin,json={"priority":"high","comment":""}).status_code==422
    assert client.patch('/api/admin/applications/'+item['id']+'/priority',headers=admin,json={"priority":"high","comment":"Уточнён срок по телефону"}).status_code==200
    assert client.get('/api/admin/orders?priority=high',headers=admin).json()['total']==5
    assert client.get('/api/admin/orders?q=Демов',headers=admin).json()['total']==2
    assert client.get('/api/admin/orders?q=%25',headers=admin).json()['total']==0


@pytest.mark.parametrize('name,deadline,task,role,budget,expected',EXAMPLES)
def test_documented_priority_examples(name,deadline,task,role,budget,expected):
    result=evaluate({"desired_deadline":deadline,"task_description":task,"role":role,"budget":30000 if budget=='min' else 120000 if budget=='max' else None},30000,120000)
    assert result['level']==expected


def test_metrics_do_not_affect_priority():
    base={"task_description":"Нужна интеграция CRM","desired_deadline":None}
    assert evaluate(base)==evaluate({**base,"metrics":{"elapsed_ms":999999}})
