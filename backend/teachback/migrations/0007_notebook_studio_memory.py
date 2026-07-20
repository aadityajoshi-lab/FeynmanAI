from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("teachback", "0006_notebook_workspace")]

    operations = [
        migrations.CreateModel(
            name="NotebookChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("role", models.CharField(max_length=16)),
                ("content", models.TextField()),
                ("source_ids", models.JSONField(blank=True, default=list)),
                ("source_anchor_ids", models.JSONField(blank=True, default=list)),
                ("grounded_in", models.CharField(blank=True, max_length=32)),
                ("status", models.CharField(default="ready", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("notebook", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_messages", to="teachback.notebook")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="NotebookNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("note_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("title", models.CharField(max_length=240)),
                ("content", models.TextField(max_length=12000)),
                ("source_ids", models.JSONField(blank=True, default=list)),
                ("source_anchor_ids", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("notebook", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notes", to="teachback.notebook")),
            ],
            options={"ordering": ["-updated_at", "-id"]},
        ),
    ]
