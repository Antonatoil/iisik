"""Kafka producer + per-owner transactional outbox relay (at-least-once)."""
import json
import logging
import os
import time
from datetime import datetime, timezone
from threading import Event
from uuid import uuid4

from confluent_kafka import Producer, KafkaException
from sqlalchemy import text
from app.core.db import engine
from app.events.domain import build

LOG = logging.getLogger(__name__)


def producer():
    return Producer({'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP','kafka:9092'),
                     'acks':'all', 'enable.idempotence':True, 'retries':10,
                     'delivery.timeout.ms':15000, 'client.id':'tutoring-lab6-producer'})


def send(p, event, topic='tutor.events.v1'):
    delivered=[]
    def ack(error, message):
        delivered.append(error)
    p.produce(topic, value=json.dumps(event,ensure_ascii=False,separators=(',',':')).encode(),
              key=event['aggregate_id'].encode(), on_delivery=ack)
    remaining=p.flush(12)
    if remaining or delivered != [None]:
        raise RuntimeError('Kafka did not acknowledge event')


def emit_auth_event(user):
    payload={'user_id':user['id'],'role':user['role'],
             'authenticated_at':datetime.now(timezone.utc).isoformat()}
    event=build('UserAuthenticated','A',user['id'],1,user['id'],payload)
    send(producer(),event)


def outbox_loop(owner, stop:Event):
    p=producer()
    while not stop.is_set():
        try:
            # Acknowledgement occurs before marking the outbox row published.
            # On process crash the same event can be replayed; inbox deduplicates.
            with engine(owner).begin() as conn:
                row=conn.execute(text("""SELECT event_id::text,topic,partition_key,envelope
                    FROM event_outbox WHERE published_at IS NULL
                    ORDER BY created_at,event_id FOR UPDATE SKIP LOCKED LIMIT 1""")).mappings().first()
                if row:
                    event=row['envelope']
                    if isinstance(event,str):event=json.loads(event)
                    send(p,event,topic=row['topic'])
                    conn.execute(text('UPDATE event_outbox SET published_at=now() WHERE event_id=CAST(:id AS uuid)'),
                                 {'id':row['event_id']})
            if not row:
                stop.wait(.3)
        except Exception:
            LOG.exception('Outbox relay failed for %s; retrying without losing the event',owner)
            stop.wait(2)
