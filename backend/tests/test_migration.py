"""Проверка перехода с предыдущей схемы без удаления данных."""
from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from customer_orders.start import migrate


def test_upgrade_preserves_previous_application_and_metrics(engine):
    app_id=uuid4()
    with engine.begin() as connection:
        config=Config('alembic.ini');config.attributes['connection']=connection
        command.downgrade(config,'0001_orders')
        connection.execute(text("INSERT INTO services (id,slug,title,description,budget_min,budget_max,currency,is_active) VALUES (1,'old-service','Existing service','Existing description',30000,120000,'RUB',true)"))
        connection.execute(text("INSERT INTO applications (id,idempotency_key,payload_hash,service_id,service_title,name,email,task_description,status,preferred_contact) VALUES (:id,:key,:hash,1,'Existing service','Existing customer','existing@example.com','Нужна интеграция CRM','new','email')"),{'id':app_id,'key':uuid4(),'hash':'a'*64})
        connection.execute(text("INSERT INTO behavior_metrics VALUES (:id,12345,1,false)"),{'id':app_id})
    migrate()
    with engine.connect() as connection:
        row=connection.execute(text("SELECT a.name,m.elapsed_ms,a.priority_evaluation FROM applications a JOIN behavior_metrics m ON m.application_id=a.id WHERE a.id=:id"),{'id':app_id}).one()
        assert row[0]=='Existing customer' and row[1]==12345
        assert row[2]['level']=='low'
        assert connection.execute(text('SELECT count(*) FROM services')).scalar()==1
