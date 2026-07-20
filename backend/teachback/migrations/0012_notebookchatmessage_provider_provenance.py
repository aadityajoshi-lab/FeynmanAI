from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("teachback", "0011_notebooksource_grounding_enabled")]

    operations = [
        migrations.AddField(
            model_name="notebookchatmessage",
            name="provider_name",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="notebookchatmessage",
            name="provider_model",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="notebookchatmessage",
            name="provider_error_category",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
