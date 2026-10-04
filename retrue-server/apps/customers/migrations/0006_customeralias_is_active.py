"""允许停用客户别称，历史别称默认继续启用。"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """只增加启用标记，不改已有身份归属和唯一匹配键。"""

    dependencies = [("customers", "0005_customeralias")]
    operations = [migrations.AddField(model_name="customeralias", name="is_active",
                                     field=models.BooleanField(default=True, verbose_name="是否启用"))]
