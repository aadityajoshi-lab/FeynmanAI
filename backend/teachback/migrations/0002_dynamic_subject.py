from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("teachback", "0001_initial")]
    operations = [
        migrations.CreateModel(name="SubjectPack", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("subject_id", models.SlugField(max_length=100, unique=True)), ("title", models.CharField(max_length=240)),
            ("summary", models.TextField(blank=True)), ("version", models.PositiveIntegerField(default=1)),
            ("active", models.BooleanField(default=True)), ("metadata", models.JSONField(blank=True, default=dict)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name="LearnerProfile", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("profile_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)), ("anonymous_key", models.CharField(max_length=128, unique=True)),
            ("display_name", models.CharField(blank=True, max_length=120)), ("preferences", models.JSONField(blank=True, default=dict)),
            ("memory_enabled", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name="Module", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("module_id", models.SlugField(max_length=120)), ("title", models.CharField(max_length=240)), ("summary", models.TextField(blank=True)),
            ("position", models.PositiveIntegerField(default=0)), ("version", models.PositiveIntegerField(default=1)), ("metadata", models.JSONField(blank=True, default=dict)),
            ("subject_pack", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="modules", to="teachback.subjectpack")),
        ]),
        migrations.CreateModel(name="Concept", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("concept_id", models.SlugField(max_length=160)), ("title", models.CharField(max_length=240)), ("prompt", models.TextField()),
            ("learning_goal", models.TextField(blank=True)), ("learning_mode", models.CharField(default="guided", max_length=40)),
            ("skill_ids", models.JSONField(blank=True, default=list)), ("version", models.PositiveIntegerField(default=1)), ("metadata", models.JSONField(blank=True, default=dict)),
            ("module", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="concepts", to="teachback.module")),
            ("source_pack", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="concepts", to="teachback.sourcepack")),
        ]),
        migrations.CreateModel(name="SkillEvidence", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("subject_id", models.SlugField(max_length=100)),
            ("skill_id", models.SlugField(max_length=160)), ("status", models.CharField(default="emerging", max_length=32)), ("mastery_score", models.FloatField(default=0.0)),
            ("evidence_count", models.PositiveIntegerField(default=0)), ("recent_signal", models.CharField(blank=True, max_length=80)), ("last_seen_at", models.DateTimeField(auto_now=True)), ("metadata", models.JSONField(blank=True, default=dict)),
            ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="skills", to="teachback.learnerprofile")),
        ]),
        migrations.CreateModel(name="LearnerMemory", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("key", models.SlugField(max_length=160)), ("kind", models.CharField(default="preference", max_length=40)),
            ("content", models.TextField(max_length=4000)), ("enabled", models.BooleanField(default=True)), ("consented", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memory_items", to="teachback.learnerprofile")),
        ]),
        migrations.AddConstraint(model_name="module", constraint=models.UniqueConstraint(fields=("subject_pack", "module_id"), name="unique_subject_module")),
        migrations.AddConstraint(model_name="concept", constraint=models.UniqueConstraint(fields=("module", "concept_id"), name="unique_module_concept")),
        migrations.AddConstraint(model_name="skillevidence", constraint=models.UniqueConstraint(fields=("profile", "subject_id", "skill_id"), name="unique_profile_skill")),
        migrations.AddConstraint(model_name="learnermemory", constraint=models.UniqueConstraint(fields=("profile", "key"), name="unique_profile_memory_key")),
    ]
