# worker/job_queue.py
from rq import Queue
from redis import Redis

class JobQueue:
    def __init__(self, redis_url="redis://localhost:6379/0"):
        self.redis = Redis.from_url(redis_url)
        self.queue = Queue("ingestion_queue", connection=self.redis)

    def enqueue(self, task, *args, **kwargs):
        return self.queue.enqueue(task, *args, **kwargs)

    def get_queue(self):
        return self.queue
