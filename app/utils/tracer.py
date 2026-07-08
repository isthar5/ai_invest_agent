import time

class Tracer:
    def __init__(self):
        self.logs = {}

    def start(self, name):
        self.logs[name] = time.time()

    def end(self, name):
        self.logs[name] = time.time() - self.logs[name]

    def report(self):
        return self.logs