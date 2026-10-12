import socket, ssl, base64, os, struct, uuid
for host,port,tls in [('127.0.0.1',18080,False),('home.kachitoritai.run',9999,True)]:
 print('Endpoint:',host,port,flush=True)
 s=None
 try:
  s=socket.create_connection((host,port),timeout=5)
  if tls:s=ssl.create_default_context().wrap_socket(s,server_hostname=host)
  s.settimeout(5)
  key=base64.b64encode(os.urandom(16)).decode()
  req=(f'RDG_OUT_DATA /remoteDesktopGateway/ HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\nRdg-Connection-Id: {{{uuid.uuid4()}}}\r\nContent-Length: 0\r\n\r\n')
  s.sendall(req.encode());r=s.makefile('rb')
  status=r.readline().decode().strip();print('Upgrade response:',status,flush=True)
  while r.readline() not in (b'\r\n',b''):pass
  if ' 101 ' not in status:continue
  packet=struct.pack('<HHIBBHH',1,0,14,0,0,0,2);mask=os.urandom(4)
  s.sendall(bytes([0x82,0x80|len(packet)])+mask+bytes(b^mask[i%4] for i,b in enumerate(packet)))
  header=r.read(2);length=header[1]&127
  data=r.read(length)
  print('Binary RDG handshake:', 'PASS' if header[0]&15==2 and data[:2]==b'\x02\x00' else 'FAIL',flush=True)
 except Exception as e:print(type(e).__name__,str(e),flush=True)
 finally:
  if s:s.close()
