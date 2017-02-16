#!/usr/bin/python3
import threading
from threading import Thread
import multiprocessing
from multiprocessing import Process
import time
import requests
import logging
logging.basicConfig(level=logging.WARNING, format='[%(process)s] [%(threadName)s] [%(filename)s:%(lineno)s] [%(levelname)s] %(message)s')
import queue
import string
import random
import faulthandler
import signal
import code, traceback, signal

# http://stackoverflow.com/a/133384
def debug(sig, frame):
    """Interrupt running process, and provide a python prompt for
    interactive debugging."""
    d={'_frame':frame}         # Allow access to frame object.
    d.update(frame.f_globals)  # Unless shadowed by global
    d.update(frame.f_locals)

    i = code.InteractiveConsole(d)
    message  = "Signal received : entering python shell.\nTraceback:\n"
    message += ''.join(traceback.format_stack(frame))
    i.interact(message)

class ThreadPool:
    def __init__(self, workers=10):
        logging.info('Creating thread pool with %d workers.' % workers)
        self.work_queue = queue.Queue()
        self.results_queue = queue.Queue()
        self.workers = threading.BoundedSemaphore(workers)
        self.thread_class = threading.Thread
        self.start()

    def start(self):
        self.__master = self.thread_class(target=self.master)
        self.__master.start()

    def master(self):
        workers = list()

        while True:
            workers = self.filter_workers(workers)

            logging.debug('Acquiring worker lock.')
            self.workers.acquire()
            logging.debug('Worker lock acquired.')

            logging.debug('Retrieving work from queue.')
            work = self.work_queue.get()
            if work is None:
                logging.debug('STOP received, exiting master.')
                break

            logging.debug('Launching %s' % (work, ))
            worker = self.thread_class(target=self.run, args=work)
            worker.start()

            workers.append(worker)

        self.filter_workers(workers, block=True)
        logging.debug('Terminating master.')

    def run(self, target, *args):
        logging.debug('Launching %s with %s' % (target, args))

        try:
            self.results_queue.put({ "result": target(*args) })
            logging.debug('Worker successful.')
        except Exception as e:
            logging.debug('Got error %s' % e)
            self.results_queue.put({ "error": e })

        self.workers.release()
        logging.debug('Released worker.')

    def filter_workers(self, workers, block=False):
        logging.debug('Filtering living workers.')
        return list(filter(lambda w: w.join(block or 0) or w.is_alive(), workers))

    def results(self):
        while self.__master.is_alive():
            logging.debug('Fetching from result queue.')

            try:
                yield self.results_queue.get(block=False)
            except queue.Empty:
                logging.debug('Queue empty.')
                time.sleep(1)

        logging.debug('Workers and master exited and queue is empty, exiting.')

    def add_work(self, func, *args):
        # logging.debug('Adding %s to queue with args %s' % (func, args))
        self.work_queue.put((func,) + args)

    def close(self):
        logging.debug('Sending STOP signal to master.')
        self.work_queue.put(None)

class ProcessPool(ThreadPool):
    def __init__(self, workers=10):
        logging.info('Creating process pool with %d workers.' % workers)
        self.work_queue = multiprocessing.Queue()
        self.results_queue = multiprocessing.Queue()
        self.workers = multiprocessing.BoundedSemaphore(workers)
        self.thread_class = multiprocessing.Process
        self.start()

def runner(func, times, *args):
    logging.info('entering runner')

    for _ in range(times):
        try:
            func(*args)
        except Exception as e:
            logging.error('Error in thread: %s' % e)

    logging.info('leaving runner')

def bench(func, times, workers, bench_type, *args):
    logging.warning('%s:' % bench_type)

    threads = []
    each = int(times / workers)

    thread_type = Thread
    if bench_type == 'multiprocessing':
        thread_type = Process

    start_time = time.time()

    for _ in range(workers):
        if bench_type == 'single threaded':
            runner(*((func, each,) + args))
        else:
            t = thread_type(target=runner, args=(func, each,) + args)
            t.start()
            threads.append(t)

    if bench_type != 'single threaded':
        for thread in threads:
            thread.join()

    logging.warning('Completed in %d seconds.' % (time.time() - start_time))

def multibench(func, times, workers, *args):
    logging.warning('Running %s %d times with %d workers.' % (func, times, workers))
    bench(func, times, workers, 'multiprocessing', *args)
    bench(func, times, workers, 'threading', *args)
    bench(func, times, workers, 'single threaded', *args)

def poolbench(func, pool_type, times, workers, *args):
    logging.warning('Running with pool type: %s' % pool_type)

    start_time = time.time()

    if pool_type:
        pool = pool_type(workers)

        for _ in range(times):
            pool.add_work(count_to_1000)

        pool.close()

        for result in pool.results():
            logging.info(result)
    else:
        logging.info(runner(func, times, *args))

    logging.warning('Completed in %d seconds.' % (time.time() - start_time))

def multipoolbench(func, times, workers, *args):
    logging.warning('Running %s %d times with %d workers.' % (func, times, workers))
    poolbench(func, ProcessPool, times, workers, *args)
    poolbench(func, ThreadPool, times, workers, *args)
    poolbench(func, None, times, workers, *args)

def acquire_mutex(lock):
    lock.acquire()
    lock.release()

def get_page():
    requests.get('http://127.0.0.1').content

def read_1000000_bytes():
    open('/dev/urandom', 'rb').read(1000000)

def count_to_1000():
    a = 1
    for _ in range(1000):
        a *= 2

def do_queue(q):
    action = random.choice(['get', 'put'])
    q.cancel_join_thread()

    if action == 'get':
        logging.info('getting from queue size: %s' % (q.qsize()))
        try:
            q.get(block=False)
        except queue.Empty:
            pass
    else:
        logging.info('inserting into queue size: %s' % (q.qsize()))
        q.put(random.choice(string.ascii_letters), block=False)

    logging.info('operations completed!')
    return True

if __name__ == '__main__':
    faulthandler.register(signal.SIGUSR1)
    signal.signal(signal.SIGUSR2, debug)

    lock = multiprocessing.Lock()
    multipoolbench(acquire_mutex, 5000, 100, lock)

    multipoolbench(read_1000000_bytes, 4000, 100)
    multipoolbench(count_to_1000, 100000, 100)
    multipoolbench(get_page, 4000, 100)

    q = multiprocessing.Queue()
    multibench(do_queue, 500000, 100, q)

    lock = multiprocessing.Lock()
    multibench(acquire_mutex, 5000000, 100, lock)

    multibench(count_to_1000, 100000, 100)
    multibench(get_page, 4000, 100)
