"""HTTPS gateway: read-only /state and explicitly selected simulation /control."""
import json
import argparse
from pathlib import Path
import ssl
import threading
import time
from http import HTTPStatus
from websockets.sync.server import serve
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed

ROOT=Path(__file__).resolve().parent
UPSTREAM_PORT=9740


def request(connection,req):
    if req.headers.get('Upgrade','').lower()=='websocket':
        if req.path not in ('/state','/control'):return connection.respond(HTTPStatus.NOT_FOUND,'Unknown stream')
        return None
    path=req.path.split('?',1)[0]
    if path=='/health':
        return connection.respond(HTTPStatus.OK,'Genesis PICO simulation gateway ready\n')
    files={'/':('index.html','text/html; charset=utf-8'),'/viewer.js':('viewer.js','text/javascript; charset=utf-8')}
    if path not in files:return connection.respond(HTTPStatus.NOT_FOUND,'Not found')
    name,mime=files[path];response=connection.respond(HTTPStatus.OK,(ROOT/name).read_text())
    response.headers['Content-Type']=mime;response.headers['Cache-Control']='no-store'
    response.headers['Permissions-Policy']='xr-spatial-tracking=(self)'
    return response


def handler(client):
    stop=threading.Event()
    can_control=client.request.path=='/control'
    receiver=None
    try:
        # Native X5 visual meshes produce a measured 48 MB initial geometry packet.
        # Keep the upstream bounded; inbound controller messages remain 4096 bytes.
        with connect(f'ws://127.0.0.1:{UPSTREAM_PORT}'+('/control' if can_control else '/state'),max_size=64*1024*1024,max_queue=1,
                     compression=None,open_timeout=8,close_timeout=2) as upstream:
            def receive():
                try:
                    while not stop.is_set():
                        data=client.recv()
                        if not can_control:
                            client.close(1008,'Read-only viewer: no client messages accepted');return
                        if not isinstance(data,str) or len(data)>4096:
                            client.close(1008,'Invalid control message size');return
                        try:
                            decoded=json.loads(data)
                            if not isinstance(decoded,dict) or decoded.get('type') not in ('xr','hold','reset'):
                                raise ValueError('Unknown simulation control message')
                        except (ValueError,TypeError) as e:
                            client.close(1008,str(e));return
                        upstream.send(data)
                except ConnectionClosed:pass
                finally:stop.set()
            receiver=threading.Thread(target=receive,daemon=True);receiver.start()
            while not stop.is_set():
                try:packet=upstream.recv(timeout=2)
                except TimeoutError:continue
                client.send(packet)
    except ConnectionClosed:
        pass
    except (OSError,TimeoutError) as e:
        print(json.dumps(dict(event='upstream_unavailable',error=str(e))),flush=True)
        client.close(1011,'Genesis state unavailable; check server/tunnel')
    finally:
        stop.set();client.close()
        if receiver:receiver.join(timeout=2)


def main():
    global UPSTREAM_PORT
    parser=argparse.ArgumentParser();parser.add_argument('--robot',choices=['franka','x5'],default='franka')
    parser.add_argument('--host',default='127.0.0.1',help='Use your LAN IP for PICO access')
    parser.add_argument('--port',type=int)
    parser.add_argument('--upstream-port',type=int)
    parser.add_argument('--cert',type=Path,required=True)
    parser.add_argument('--key',type=Path,required=True)
    args=parser.parse_args()
    port=args.port or (8445 if args.robot=='x5' else 8444)
    UPSTREAM_PORT=args.upstream_port or (9742 if args.robot=='x5' else 9740)
    if not all(0<p<65536 for p in (port,UPSTREAM_PORT)):parser.error('Ports must be 1..65535')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.cert,args.key)
    with serve(handler,args.host,port,ssl=context,process_request=request,
               compression='deflate',max_size=4096,max_queue=1,close_timeout=2) as server:
        print(json.dumps(dict(event='gateway_ready',robot=args.robot,url=f'https://{args.host}:{port}/',time=time.time())),flush=True)
        server.serve_forever()


if __name__=='__main__':main()
