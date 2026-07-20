from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("teachback", "0010_learningactivity_apply")]

    operations = [
        migrations.AddField(
            model_name="notebooksource",
            name="grounding_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
