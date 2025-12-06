# worker/base_worker.py
from abc import ABC, abstractmethod

class BaseWorker(ABC):
    @abstractmethod
    def run(self, *args, **kwargs):
        pass

    def log(self, message):
        print(f"[Worker] {message}")
