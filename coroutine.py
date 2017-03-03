import types
import uuid
import socket
import select
import time
import logging
#logging.basicConfig(level=logging.DEBUG)

class States:
    READABLE = select.EPOLLIN
    WRITABLE = select.EPOLLOUT

class ScheduleTask:
    def __init__(self, coroutine):
        self.coroutine = coroutine

class Scheduler:
    def __init__(self):
        self.coroutines = []
        self.coroutine_map = {}
        self.buffered_returns = {}
        self.parents = {}
        self.poll = select.epoll()
        self.descriptors = 0

    def add_coroutine(self, coroutine):
        self.coroutines.append(coroutine)

    def iterate(self):
        scheduled_coroutines = []
        new_descriptors = []

        logging.debug('invoking self.coroutines: %s' % self.coroutines)

        for coroutine in self.coroutines:
            # Run the coroutine.
            try:
                args = self.coroutine_map.get(coroutine)
                # We need to remove the return value so it doesn't get reused.
                if coroutine in self.coroutine_map:
                    del self.coroutine_map[coroutine]

                logging.debug('calling %s with %s' % (coroutine, args))
                result = coroutine.send(args)
            except StopIteration:
                # The coroutine completed, so schedule the parent, if any.
                parent = self.get_parent(coroutine)
                if parent:
                    scheduled_coroutines.append(parent)
                continue

            logging.debug('got %s from %s' % (result, coroutine))

            # Inherits from NonBlocking, schedule the descriptor and add a mapping.
            if isinstance(result, tuple) and len(result) == 2 and hasattr(result[0], 'fileno'):
                self.parents[result[0].fileno()] = coroutine
                new_descriptors.append(result)
            # It's a ScheduleTask object, schedule the task and the parent (don't
            # associate the task with the parent - "threads")
            elif isinstance(result, ScheduleTask):
                scheduled_coroutines.append(result.coroutine)
                scheduled_coroutines.append(coroutine)
            # Schedule the new generator and map it to the parent.
            elif isinstance(result, types.GeneratorType):
                if result in self.buffered_returns:
                    self.coroutine_map[coroutine] = self.buffered_returns[result]
                    del self.buffered_returns[result]
                    scheduled_coroutines.append(result)
                    scheduled_coroutines.append(coroutine)
                else:
                    scheduled_coroutines.append(result)
                    self.parents[result] = coroutine
            # Otherwise call the coroutine again so that it completes and then
            # store the result.
            else:
                parent = self.get_parent(coroutine)
                if parent:
                    self.coroutine_map[parent] = result
                    scheduled_coroutines.append(coroutine)
                    scheduled_coroutines.append(parent)
                else:
                    self.buffered_returns[coroutine] = result

        self.coroutines = scheduled_coroutines
        self.poll_descriptors(new_descriptors)

    def poll_descriptors(self, new_descriptors):
        logging.debug('Adding descriptors: %s' % new_descriptors)

        for fd, mask in new_descriptors:
            if isinstance(mask, tuple):
                mask = reduce(lambda x, y: x | y, mask)
            self.poll.register(fd, mask)
            self.descriptors += 1

        if not self.descriptors:
            return

        for fd, events in self.poll.poll(0 if self.coroutines else 100):
            logging.debug('%s is active! scheduling %s' % (fd, self.parents[fd]))
            self.coroutines.append(self.parents[fd])
            del self.parents[fd]
            self.poll.unregister(fd)
            self.descriptors -= 1

    def get_parent(self, coroutine):
        parent = self.parents.get(coroutine)

        if not parent:
            return
            
        del self.parents[coroutine]
        return parent

    def run_until_complete(self):
        while self.coroutines or self.descriptors:
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
