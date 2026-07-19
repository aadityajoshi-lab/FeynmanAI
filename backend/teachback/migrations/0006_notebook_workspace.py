from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("teachback", "0005_studysource")]

    operations = [
        migrations.CreateModel(
            name="Notebook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notebook_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("title", models.CharField(max_length=240)),
                ("subject", models.CharField(blank=True, max_length=240)),
                ("description", models.TextField(blank=True)),
                ("learning_goal", models.CharField(default="understand", max_length=40)),
                ("status", models.CharField(default="draft", max_length=32)),
                ("ocr_provider", models.CharField(default="local_fallback", max_length=80)),
                ("knowledge_pack", models.JSONField(blank=True, default=dict)),
                ("knowledge_pack_markdown", models.TextField(blank=True)),
                ("stats", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="NotebookSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_id", models.CharField(max_length=160, unique=True)),
                ("title", models.CharField(max_length=240)),
                ("source_kind", models.CharField(default="reference", max_length=40)),
                ("filename", models.CharField(blank=True, max_length=255)),
                ("mime_type", models.CharField(blank=True, max_length=120)),
                ("size_bytes", models.PositiveBigIntegerField(default=0)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                ("status", models.CharField(default="queued", max_length=32)),
                ("extraction_method", models.CharField(default="local", max_length=80)),
                ("extraction", models.JSONField(blank=True, default=dict)),
                ("blocks", models.JSONField(blank=True, default=list)),
                ("assets", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("notebook", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notebook_sources", to="teachback.notebook")),
            ],
        ),
        migrations.CreateModel(
            name="NotebookArtifact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("artifact_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("artifact_type", models.CharField(max_length=40)),
                ("title", models.CharField(max_length=240)),
                ("status", models.CharField(default="ready", max_length=32)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("source_ids", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("notebook", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="artifacts", to="teachback.notebook")),
            ],
        ),
    ]
