#!/usr/bin/env python3
"""Celery worker 启动入口。

使用方式:
    python worker.py                          # 启动所有队列
    python worker.py -Q emotion_analysis      # 仅启动情感分析队列
    python worker.py --concurrency=4          # 自定义并发数
"""
import subprocess
import sys


def main():
    argv = [
        "celery",
        "-A", "app.config.celery_config.app",
        "worker",
        "--loglevel=info",
    ]
    argv.extend(sys.argv[1:])

    try:
        subprocess.run(argv, check=True)
    except KeyboardInterrupt:
        print("\nCelery worker 已停止")


if __name__ == "__main__":
    main()
