import signal
import sys
import socket
import select

def error(info, msg):
    print(f'{info}: ', msg)
    sys.exit(1)

def http_response():
    body = ('hello world!\r\n').encode()
    headers = (
        'Server: hello-epoll\r\n'
        'Content-type: text/plain; charset=utf-8\r\n'
        f'Content-length: {len(body)}\r\n\r\n'
        ).encode()
    start_line = ('HTTP/1.1 200 OK\r\n').encode()
    return b''.join([start_line, headers, body])

addr_info = None
try:
    addr_info = socket.getaddrinfo(
        None,
        8080,
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        socket.AI_PASSIVE
        )
except OSError as err_msg:
    error('could not get socket address information', err_msg)
    print()

af, socktype, proto, canonname, sa = addr_info[0]
sock_listen = None
try:
    sock_listen = socket.socket(af, socktype, proto)
except OSError as err_msg:
    error('socket could not be created', err_msg)

try:
    sock_listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
except OSError as err_msg:
    error('socket options could not be set', err_msg)

try:
    sock_listen.bind(sa)
except OSError as err_msg:
    error('socket could not be bound', err_msg)

try:
    sock_listen.listen(128)
except OSError as err_msg:
    error('server unable to accept connections', err_msg)
print(f'listening on: {sa[0]}:{sa[1]}')

def sig_handler(sig, frame):
    print('exiting...')
    sock_listen.close()
    sys.exit(0)

signal.signal(signal.SIGINT, sig_handler)

try:
    epoll_instance = select.epoll()
except OSError as err_msg:
    error('could not create epoll instance', err_msg)

try:
    epoll_instance.register(sock_listen, select.EPOLLIN)
except OSError as err_msg:
    error('could not register sock_listen in epoll instance', err_msg)

clients = {}
while True:
    ready_list = None
    try:
        ready_list = epoll_instance.poll()
    except OSError as err_msg:
        error('epoll_instance cound not poll', err_msg)
    for item in ready_list:
        fd, event = item
        if fd == sock_listen.fileno():
            try:
                sock_client, client_addr = sock_listen.accept()
                epoll_instance.register(sock_client, select.EPOLLIN)
                clients[sock_client.fileno()] = sock_client
                client_host, client_port = socket.getnameinfo(client_addr,
                    socket.NI_NUMERICHOST)
                print(f'new connection open: {client_host}:{client_port}')
            except OSError as err_msg:
                print('could not open a new connection: ', err_msg)
        else:
            sock_client = clients[fd]
            data = None
            try:
                data = sock_client.recv(4096)
            except OSError as err_msg:
                del clients[fd]
                epoll_instance.unregister(fd)
                print(f'(RST received) could not read data: ', err_msg)
                continue
            if not data:
                try:
                    client_host, client_port = sock_client.getpeername()
                    sock_client.shutdown(socket.SHUT_WR)
                    print(f'connection closed: {client_host}:{client_port}')
                except OSError as err_msg:
                    print('connection is already closed.', err_msg)
                del clients[fd]
                epoll_instance.unregister(fd)
                continue
            request = data.decode('utf-8').split('\r\n')
            if 'Connection: close' in request:
                client_host, client_port = sock_client.getpeername()
                sock_client.shutdown(socket.SHUT_WR)
                print(f'connection closed: {client_host}:{client_port}')
                del clients[fd]
                epoll_instance.unregister(fd)
                continue
            else:
                sock_client.sendall(http_response())

