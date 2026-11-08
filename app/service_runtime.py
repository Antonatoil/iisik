"""Service entry point: real gRPC + Kafka workers + HTTP readiness in ONE container."""
import logging
import os
import signal
from threading import Thread, Event
import uvicorn
from app.grpc.server import start
from app.events.consumer import CONSUMERS, consumer_loop
from app.events.publisher import outbox_loop

logging.basicConfig(level=logging.INFO)

def main():
    owner=os.environ['SERVICE_OWNER']
    stop=Event()
    grpc_server=start(owner)
    workers=[]
    if owner in ('l','p','r','x'):
        workers.append(Thread(target=outbox_loop,args=(owner,stop),daemon=True,name=owner+'-outbox'))
    if owner in CONSUMERS:
        workers.append(Thread(target=consumer_loop,args=(owner,stop),daemon=True,name=owner+'-consumer'))
    for worker in workers:worker.start()
    try:
        uvicorn.run('app.service_api:app',host='0.0.0.0',port=8100,log_level='info')
    finally:
        stop.set()
        grpc_server.stop(grace=5).wait(6)
        for worker in workers:worker.join(timeout=3)

if __name__=='__main__':main()
