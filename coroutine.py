import types
import uuid
import socket
import select
import time
import Queue
import signal
import logging
#logging.basicConfig(level=logging.DEBUG)
#import traceback

class States:
    READABLE = select.EPOLLIN
    WRITABLE = select.EPOLLOUT

class ScheduleTask:
    def __init__(self, coroutine):
        self.coroutine = coroutine

class Scheduler:
    def __init__(self, timeout=0.1):
        self.timeout = timeout

        self.descriptors = 0
        self.new_descriptors = Queue.Queue()
        self.coroutines = Queue.Queue()
        self.poll = select.epoll()

        # Return values for each coroutine.
        self.coroutine_map = {}
        # Coroutines that ran early might have a buffered return value.
        self.buffered_returns = {}
        # Mappings of coroutine -> parent
        self.parents = {}
        # Coroutines waiting for another coroutine.
        self.awaiting = set()

        signal.signal(signal.SIGALRM, self.alarm_handler)

    def add_coroutine(self, coroutine):
        logging.debug('adding coroutine: %s' % coroutine)
#        traceback.print_stack()
        self.coroutines.put(coroutine)

    def alarm_handler(self, signo, stack):
        self.iterate()

        self.poll_descriptors()
        signal.setitimer(signal.ITIMER_REAL, self.timeout)

    def iterate(self):
        previous = set()

        while not self.coroutines.empty():
            try:
                coroutine = self.coroutines.get(block=False)

                # Loop detection!
#                if coroutine in previous:
#                    logging.debug('loop detected, rescheduling %s' % coroutine)
#                    self.add_coroutine(coroutine)
#                    break

                self.run_coroutine(coroutine)
                previous.add(coroutine)
            except Queue.Empty:
                break

        self.poll_descriptors()

    def run_coroutine(self, coroutine):
        if coroutine in self.awaiting:
            logging.debug('%s is waiting, adding back to queue.' % (coroutine))
            self.add_coroutine(coroutine)
            return

        signal.setitimer(signal.ITIMER_REAL, self.timeout)

        # Run the coroutine.
        try:
            args = self.coroutine_map.get(coroutine)
            # We need to remove the return value so it doesn't get reused.
            if args:
                self.coroutine_map[coroutine] = args[1:]
                if not self.coroutine_map:
                    del self.coroutine_map[coroutine]
                args = args[0]

            logging.debug('calling %s with %s' % (coroutine, args))
            result = coroutine.send(args)
            logging.debug('got %s from %s' % (result, coroutine))
            self.handle_result(coroutine, result)
        except StopIteration:
            signal.setitimer(signal.ITIMER_REAL, 0)
            # The coroutine completed, so schedule the parent, if any.
            parent = self.get_parent(coroutine)
            if parent:
                self.add_coroutine(parent)

        signal.setitimer(signal.ITIMER_REAL, 0)

    def handle_result(self, coroutine, result):
        new_descriptor = None

        # Inherits from NonBlocking, schedule the descriptor and add a mapping.
        if isinstance(result, tuple) and len(result) == 2 and hasattr(result[0], 'fileno'):
            self.parents[result[0].fileno()] = coroutine
            self.new_descriptors.put(result)
        # It's a ScheduleTask object, schedule the task and the parent (don't
        # associate the task with the parent - "threads")
        elif isinstance(result, ScheduleTask):
            self.add_coroutine(result.coroutine)
            self.add_coroutine(coroutine)
        # Schedule the new generator and map it to the parent.
        elif isinstance(result, types.GeneratorType):
            if result in self.buffered_returns:
                self.add_result(coroutine, self.buffered_returns[result])
                del self.buffered_returns[result]
                self.add_coroutine(result)
                self.add_coroutine(coroutine)
            else:
                self.add_coroutine(result)
                self.parents[result] = coroutine
                self.awaiting.add(coroutine)
        # Otherwise call the coroutine again so that it completes and then
        # store the result.
        else:
            parent = self.get_parent(coroutine)
            if parent:
                self.add_result(parent, result)
                self.add_coroutine(coroutine)
                self.add_coroutine(parent)
            else:
                self.buffered_returns[coroutine] = result

    def add_result(self, parent, result):
        if parent not in self.coroutine_map:
            self.coroutine_map[parent] = []
            
        self.coroutine_map[parent].append(result)

    def poll_descriptors(self):
        logging.debug('Adding descriptors')

        while not self.new_descriptors.empty():
            try:
                fd, mask = self.new_descriptors.get(block=False)
            except Queue.Empty:
                break

            if isinstance(mask, tuple):
                mask = reduce(lambda x, y: x | y, mask)
            self.poll.register(fd, mask)
            self.descriptors += 1

        if not self.descriptors:
            return

        for fd, events in self.poll.poll(0 if self.coroutines else 100):
            logging.debug('%s is active! scheduling %s' % (fd, self.parents[fd]))
            self.add_coroutine(self.parents[fd])
            del self.parents[fd]
            self.poll.unregister(fd)
            self.descriptors -= 1

    def get_parent(self, coroutine):
        parent = self.parents.get(coroutine)

        if not parent:
            return
            
        del self.parents[coroutine]

        if parent in self.awaiting:
            self.awaiting.remove(parent)

        return parent

    def run_until_complete(self):
        while not self.coroutines.empty() or self.descriptors:
            self.iterate()

class Socket(socket.socket):
    def __init__(self, *args, **kwargs):
        super(Socket, self).__init__(*args, **kwargs)
        self.setblocking(0)

        self.send = self._send
        self.recv = self._recv

    def accept(self):
        yield self, States.READABLE
        client, addr = super(Socket, self).accept()
        yield addr, Socket(_sock=client)

    def connect(self, host):
        yield self, States.WRITABLE

        try:
            yield super(Socket, self).connect(host)
        except socket.error:
            pass

    def _send(self, data):
        sent_bytes = 0
        while sent_bytes < len(data):
            yield self, States.WRITABLE
            sent_bytes += self._sock.send(data[sent_bytes:])

    def _recv(self, num_bytes):
        yield self, States.READABLE
        yield self._sock.recv(num_bytes)
