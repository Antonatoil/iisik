"""Noncritical Auth login metric over Kafka; Auth never receives SQL credentials."""
from datetime import datetime, timezone
from app.events.domain import build
import json
import os
from confluent_kafka import Producer


def emit_auth_event(user):
    event=build('UserAuthenticated','A',user['id'],1,user['id'],
       {'user_id':user['id'],'role':user['role'],
        'authenticated_at':datetime.now(timezone.utc).isoformat()})
    p=Producer({'bootstrap.servers':os.getenv('KAFKA_BOOTSTRAP','kafka:9092'),
               'acks':'all','enable.idempotence':True,'delivery.timeout.ms':8000})
    outcomes=[]
    p.produce('tutor.events.v1',json.dumps(event,ensure_ascii=False).encode(),
              key=user['id'].encode(),on_delivery=lambda err,msg:outcomes.append(err))
    if p.flush(6) or outcomes != [None]:
        raise RuntimeError('Kafka did not acknowledge UserAuthenticated')
