"""In-app notifications owned by DB-N. Not delivered over Kafka in lab 4."""
from app.core.db import engine
from app.core.commands import new_id, fetch, execute, check_receipt, save_receipt, business_condition
from app.core.validation import valid_id


def mark_notification_read(actor,arg):
    uid=valid_id(arg['notificationId'])
    with engine('n').begin() as conn:
        cached=check_receipt(conn,arg['operationId'],actor['id'],'markNotificationRead',arg)
        if cached:return cached
        obj=fetch(conn,'SELECT user_id::text,read_at FROM notifications WHERE id=CAST(:id AS uuid) FOR UPDATE',id=uid)
        business_condition(obj is not None and obj['user_id']==actor['id'],'NOT_FOUND','Notification not found')
        execute(conn,'UPDATE notifications SET read_at=coalesce(read_at,now()) WHERE id=CAST(:id AS uuid)',id=uid)
        return save_receipt(conn,arg['operationId'],actor['id'],'markNotificationRead',arg,_read(conn,uid))


def _read(conn,uid):
    r=fetch(conn,'SELECT id::text,kind,text,object_id::text AS \"objectId\",created_at AS \"createdAt\",read_at AS \"readAt\" FROM notifications WHERE id=CAST(:id AS uuid)',id=uid)
    return r


def notify(user_id,kind,object_id,message,marker):
    # Stable generated event id ensures replay of the same operation doesn't duplicate notification.
    from uuid import uuid5, NAMESPACE_URL
    event_id=str(uuid5(NAMESPACE_URL,'lab4:'+marker+':'+kind))
    with engine('n').begin() as conn:
        execute(conn,"""INSERT INTO notifications(id,user_id,event_id,kind,text,object_id,created_at)
           VALUES(CAST(:id AS uuid),CAST(:user AS uuid),CAST(:event AS uuid),:kind,:body,CAST(:obj AS uuid),now())
           ON CONFLICT(event_id,user_id) DO NOTHING""",
           id=new_id(),user=user_id,event=event_id,kind=kind,body=message,obj=object_id)
