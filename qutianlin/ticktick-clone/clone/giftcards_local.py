"""Local sandbox gift-card fulfillment. Codes are created only after approval."""
import hashlib,secrets,time,datetime,json,re
from fastapi import HTTPException
from collaboration_local import invite_email
SCHEMA='''CREATE TABLE IF NOT EXISTS ticktick_giftcards(code TEXT PRIMARY KEY,owner TEXT NOT NULL,order_id TEXT NOT NULL,created INTEGER NOT NULL,expires INTEGER NOT NULL,redeemed_by TEXT,redeemed_at INTEGER);'''
def validate(body,a):
 try:count=int(body.get('count',1));card_type=int(body.get('cardType',1));receiver_type=int(body.get('receiverType',1))
 except (ValueError,TypeError):raise HTTPException(400,'Invalid gift card options')
 if count<1 or count>50 or card_type not in range(1,6) or receiver_type not in [1,2]:raise HTTPException(400,'Invalid gift card options')
 email=body.get('email','') if receiver_type==2 else a['email_normalized']
 if not isinstance(email,str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(400,'Enter a valid recipient email')
 return {'count':count,'cardType':card_type,'receiverType':receiver_type,'email':email,'buyer':str(body.get('buyer','')),'receiver':str(body.get('receiver','')),'message':str(body.get('message',''))}
def fulfill(db,a,d,flow):
 gift=flow['gift'];now=int(time.time());codes=[]
 for _ in range(gift['count']):
  code='LOCAL-'+secrets.token_hex(10).upper();codes.append(code);db.execute('INSERT INTO ticktick_giftcards VALUES(?,?,?,?,?,NULL,NULL)',(code,a['account_id'],flow['flow_id'],now,now+366*86400))
 invite_email(gift['email'],'Local Premium gift card','This is a local payment simulation.\nYour gift card code(s):\n'+'\n'.join(codes)+'\nRedeem in local TickTick Settings > Redeem.')
 d.setdefault('giftOrders',{})[flow['flow_id']]={'orderId':flow['flow_id'],'createdTime':datetime.datetime.now(datetime.timezone.utc).isoformat(),'currencyCode':'USD','amount':49.99,'count':gift['count'],'giftCardRecord':gift,'isSimulation':True}
def handle(path,method,body,req,a,d,db,save,actorid):
 if not path.startswith('giftcard/'):return None
 if path=='giftcard/orders':return list(d.get('giftOrders',{}).values())
 if path.startswith('giftcard/by-order/'):
  ident=path.rsplit('/',1)[-1]
  if ident not in d.get('giftOrders',{}):raise HTTPException(404,'Order not found')
  return [{'id':r['code'],'code':r['code'],'expireTime':datetime.datetime.fromtimestamp(r['expires'],datetime.timezone.utc).isoformat(),'validatedBy':r['redeemed_by'],'validatedTime':r['redeemed_at']} for r in db.execute('SELECT * FROM ticktick_giftcards WHERE owner=? AND order_id=?',(a['account_id'],ident))]
 if path.startswith('giftcard/apply/'):
  code=path.rsplit('/',1)[-1];r=db.execute('SELECT * FROM ticktick_giftcards WHERE code=?',(code,)).fetchone();now=int(time.time())
  if not r or r['expires']<=now:raise HTTPException(400,'Invalid or expired gift card')
  if r['redeemed_by']:raise HTTPException(409,'Gift card already redeemed')
  if db.execute('UPDATE ticktick_giftcards SET redeemed_by=?,redeemed_at=? WHERE code=? AND redeemed_by IS NULL',(str(actorid(a)),now,code)).rowcount!=1:raise HTTPException(409,'Gift card already redeemed')
  old=d.get('subscription',{});d['subscription']={**old,'frequency':'Year','ends':max(now,old.get('ends',0))+366*86400,'autoRenew':old.get('autoRenew',False)};save(db,a,d);return {'success':True}
 if path.endswith('/resend'):
  ident=path.split('/')[1];order=d.get('giftOrders',{}).get(ident)
  if not order:raise HTTPException(404,'Order not found')
  if order.get('resentAt',0)>time.time()-60:raise HTTPException(429,'Please wait before resending')
  gift=validate({**order['giftCardRecord'],**body},a);codes=[r['code'] for r in db.execute('SELECT code FROM ticktick_giftcards WHERE owner=? AND order_id=?',(a['account_id'],ident))];invite_email(gift['email'],'Local Premium gift card','Local gift card codes:\n'+'\n'.join(codes));order['giftCardRecord']=gift;order['resentAt']=int(time.time());save(db,a,d);return {}
 return None
