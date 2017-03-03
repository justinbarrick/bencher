#!/usr/bin/python2
import coroutine
import socket

def test_coroutine(arg=None):
    print 'in coroutine: %s' % arg
    yield arg
    print 'end coroutine'

def test(arg=None):
    print 'in test: %s' % arg

    result = yield test_coroutine(arg)

    yield result
    print 'end test: %s' % result
    print 'expected: %s, actual: %s' % (arg, result)
    assert result == arg

def a_long_test():
    print 'in a_long_test'
    result = yield test_coroutine()
    print result
    assert result == None

    print 'second part of a long test'
    result = yield test('hello')
    assert result == 'hello'

    print 'third part of a long test'
    result = yield test_coroutine()
    assert result == None

    print 'fourth part of a long test'
    result = yield test('hello')
    assert result == 'hello'

def network_test(google):
    sock = coroutine.Socket()

    yield sock.connect((google, 80))
    print 'Connected to google!'
    yield sock.send('GET / HTTP/1.1\r\nHost: google.com\r\n\r\n')
    print 'Send data to google!'

    data = yield sock.recv(4096)
    print 'Received data from google: %s' % data.split('\r\n')[0]

    yield sock.close()
    print 'Closed connection to google.'

def test_client(port, data):
    client = coroutine.Socket()

    print 'Connecting to test server at %d' % port
    yield client.connect(('127.0.0.1', port))

    print 'Sending "%s" to test server at port %d' % (data, port)
    yield client.send(data)

    print 'Receiving from test server %d' % port
    received = yield client.recv(4096)

    print 'Received "%s" from %d (expected: "%s")' % (received, port, data)
    assert received == data

    yield client.close()

def test_handle_client(client, addr):
    print 'Handling client from %s:%d' % addr
    received = yield client.recv(4096)

    print 'Echoing "%s" back to client.' % received
    yield client.send(received)
    yield client.close()

def launch_clients(port, num_clients):
    for index in range(num_clients):
        print 'Launching to client to say "hello %d"' % index
        yield coroutine.ScheduleTask(test_client(port, 'hello %d' % index))

def accept_clients(server, num_clients):
    print 'Accepting clients.'
    for _ in range(num_clients):
        addr, client = yield server.accept()
        yield coroutine.ScheduleTask(test_handle_client(client, addr))

    yield server.close()

def test_server():
    server = coroutine.Socket()

    server.bind(('127.0.0.1', 0))
    server.listen(5)

    addr, port = server.getsockname()

    print 'Bound to port %d, launching clients.' % port
    yield coroutine.ScheduleTask(launch_clients(port, 15))
    yield coroutine.ScheduleTask(accept_clients(server, 15))

generator2_exited = False

def generator2(iterations):
    for i in range(iterations):
        print 'generator2 yielding %d' % i
        yield i

    print 'generator2 exiting'
    global generator2_exited
    generator2_exited = True

def generator1(iterations):
    print 'creating generator2'
    gen = generator2(iterations)

    print 'iterating'
    for i in range(iterations):
        value = yield gen
        print value, i
        assert value == i

    value = yield test(4)
    assert 4 == value
    assert generator2_exited == True

if __name__ == '__main__':
    google = socket.gethostbyname('google.com')

    coroutines = coroutine.Scheduler()
    coroutines.add_coroutine(test())
    coroutines.add_coroutine(a_long_test())
    coroutines.add_coroutine(test())
    coroutines.add_coroutine(test('helloooo'))

    for _ in range(3000):
        coroutines.add_coroutine(network_test(google))

    coroutines.add_coroutine(test())
    coroutines.add_coroutine(test())
    coroutines.add_coroutine(test_server())
    coroutines.add_coroutine(generator1(100))
    coroutines.run_until_complete()
