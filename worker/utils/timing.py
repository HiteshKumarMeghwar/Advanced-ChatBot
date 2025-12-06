# worker/utils/timing.py
import time

class Timer:
    def __enter__(self):
        self.start = time.time()

    def __exit__(self, *args):
        print("Time:", time.time() - self.start)
