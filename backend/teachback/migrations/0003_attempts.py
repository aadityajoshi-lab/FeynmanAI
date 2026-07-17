from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("teachback", "0002_dynamic_subject")]
    operations = [
        migrations.CreateModel(name="LearningAttempt", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("attempt_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ("learner_text", models.TextField(blank=True, max_length=12000)), ("learning_mode", models.CharField(default="guided", max_length=40)), ("state", models.CharField(default="draft", max_length=40)), ("record_version", models.PositiveIntegerField(default=1)), ("record", models.JSONField(blank=True, default=dict)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("concept", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="attempts", to="teachback.concept")), ("module", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attempts", to="teachback.module")), ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="teachback.learnerprofile")),
        ]),
        migrations.CreateModel(name="AttemptCheckpoint", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("checkpoint_id", models.SlugField(max_length=120)), ("kind", models.CharField(default="teach_back", max_length=40)), ("state", models.CharField(default="pending", max_length=40)), ("payload", models.JSONField(blank=True, default=dict)), ("response", models.JSONField(blank=True, default=dict)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("attempt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="checkpoints", to="teachback.learningattempt")),
        ]),
        migrations.AddConstraint(model_name="attemptcheckpoint", constraint=models.UniqueConstraint(fields=("attempt", "checkpoint_id"), name="unique_attempt_checkpoint")),
    ]
