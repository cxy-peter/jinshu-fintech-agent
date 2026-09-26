"""Bound request size before JSON/multipart decoding, including chunked uploads."""
from starlette.responses import JSONResponse
class BodyLimitMiddleware:
 def __init__(self,app,limit=4_000_000):self.app=app;self.limit=limit
 async def __call__(self,scope,receive,send):
  if scope['type']!='http' or scope['method'] in {'GET','HEAD','OPTIONS'}:return await self.app(scope,receive,send)
  messages=[];size=0
  while True:
   message=await receive()
   if message['type']=='http.disconnect':return
   size+=len(message.get('body',b''))
   if size>self.limit:return await JSONResponse({'detail':'请求最多4MB，请拆分后上传'},413)(scope,receive,send)
   messages.append(message)
   if not message.get('more_body'):break
  async def replay():return messages.pop(0) if messages else await receive()
  await self.app(scope,replay,send)
