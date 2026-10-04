"""审计动作增加客户资料导出，不变更既有日志。"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """同步模型选择值，数据列结构与历史日志保持兼容。"""

    dependencies = [("audit", "0004_alter_auditlog_content_type")]
    operations = [migrations.AlterField(model_name="auditlog", name="action",
        field=models.CharField(max_length=20, verbose_name="动作", choices=[
            ("create", "创建"), ("update", "更新"), ("delete", "删除"), ("confirm", "确认"),
            ("login", "登录"), ("logout", "登出"), ("export", "导出")]))]
