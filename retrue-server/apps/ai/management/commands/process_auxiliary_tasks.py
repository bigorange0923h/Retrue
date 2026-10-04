"""消费持久化辅助任务；可按分钟定时执行，异常不会丢失任务。"""

from django.core.management.base import BaseCommand
from apps.ai.orchestration.auxiliary import process_pending_memory


class Command(BaseCommand):
    """在同一 Django 部署中处理有限条记忆评估任务。"""

    help = "处理已排队的辅助记忆评估（只生成候选，不确认正式记忆）"

    def add_arguments(self, parser):
        """单次上限避免一个定时运行长时间占用模型。"""
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        """输出计数，不输出客户内容、候选原文或模型错误。"""
        count = process_pending_memory(options["limit"])
        self.stdout.write(f"辅助任务成功处理 {count} 项")
