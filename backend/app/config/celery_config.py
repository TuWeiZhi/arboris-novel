# AIMETA P=Celery配置_异步任务队列设置|R=Celery应用_任务路由_序列化_重试_异常钩子|NR=不含任务定义|E=celery_app|X=job|A=Celery实例|D=celery,redis|S=net|RD=./README.ai
import logging
import os
import signal

from celery import Celery, signals
from kombu import Exchange, Queue
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

app = Celery(
    'arboris',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1'),
)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # 任务执行
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_max_retries=3,

    # 工作进程
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=500,
    worker_send_task_events=True,

    # 结果
    result_expires=3600,
    result_extended=True,
)

app.conf.task_queues = (
    Queue('emotion_analysis', Exchange('emotion_analysis'), routing_key='emotion_analysis'),
    Queue('default', Exchange('default'), routing_key='default'),
)

app.conf.task_routes = {
    'app.tasks.emotion_tasks.analyze_emotion_async': {'queue': 'emotion_analysis'},
}

app.conf.beat_schedule = {}

# ── 全局异常钩子 ──


@signals.task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, **_):
    logger.error(
        "Celery 任务失败: task=%s id=%s error=%s args=%s",
        sender, task_id, exception, args,
    )


@signals.task_prerun.connect
def on_task_prerun(task_id=None, task=None, **_):
    logger.debug("Celery 任务开始: %s id=%s", task.name if task else '?', task_id)


@signals.worker_process_init.connect
def on_worker_init(**_):
    signal.signal(signal.SIGTERM, lambda sig, frame: logger.info("Celery worker 收到 SIGTERM，优雅退出"))


if __name__ == '__main__':
    app.start()
