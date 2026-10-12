import socket,ssl,uuid,http.client,struct,time

def probe(host,port,tls):
    socks=[]
    def connect():
        s=socket.create_connection((host,port),timeout=5)
        if tls: s=ssl.create_default_context().wrap_socket(s,server_hostname=host)
        s.settimeout(5); socks.append(s); return s
    ident='{'+str(uuid.uuid4()).upper()+'}'
    def headers(method,length):
        return (f'{method} /remoteDesktopGateway/ HTTP/1.1\r\nHost: {host}:{port}\r\nRdg-Connection-Id: {ident}\r\nContent-Length: {length}\r\nConnection: Keep-Alive\r\n\r\n').encode()
    try:
        out=connect(); out.sendall(headers('RDG_OUT_DATA',0))
        response=http.client.HTTPResponse(out); response.begin()
        print('OUT status:',response.status,'framing:',response.getheader('Transfer-Encoding'),flush=True)
        seed=response.read(10); print('OUT initial bytes:',len(seed),flush=True)
        incoming=connect(); incoming.sendall(headers('RDG_IN_DATA',1))
        accepted=http.client.HTTPResponse(incoming); accepted.begin()
        print('IN status:',accepted.status,flush=True)
        incoming.sendall(b'\x00'); time.sleep(.2)
        packet=struct.pack('<HHIBBHH',1,0,14,0,0,0,2)
        incoming.sendall(b'E\r\n'+packet+b'\r\n')
        data=response.read(18)
        print('Handshake response:',data.hex(),'PASS' if len(data)==18 and data[:2]==b'\x02\x00' else 'FAIL',flush=True)
    except Exception as e: print(type(e).__name__+':',str(e),flush=True)
    finally:
        for s in socks: s.close()
for endpoint in [('127.0.0.1',18080,False),('home.kachitoritai.run',9999,True)]:
    print('TEST',endpoint,flush=True); probe(*endpoint)
