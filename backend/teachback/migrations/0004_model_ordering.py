from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("teachback", "0003_attempts")]
    operations = [
        migrations.AlterModelOptions(name="module", options={"ordering": ["position", "id"]}),
        migrations.AlterModelOptions(name="concept", options={"ordering": ["id"]}),
        migrations.AlterModelOptions(name="claim", options={"ordering": ["position", "id"]}),
    ]
