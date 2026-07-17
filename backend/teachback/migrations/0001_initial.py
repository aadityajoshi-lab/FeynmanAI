from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="SourcePack", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("lesson_id", models.CharField(max_length=120, unique=True)), ("title", models.CharField(max_length=240)),
            ("description", models.TextField(blank=True)), ("version", models.CharField(default="1.0.0", max_length=80)),
            ("source_url", models.URLField(blank=True)), ("license_text", models.CharField(blank=True, max_length=240)),
            ("approved", models.BooleanField(default=True)), ("spans", models.JSONField(default=list)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
        ]),
        migrations.CreateModel(name="LearningSession", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("lesson_id", models.CharField(max_length=120)), ("learner_text", models.TextField(max_length=12000)),
            ("status", models.CharField(choices=[(x, x) for x in ("draft", "auditing", "ready", "needs_human_review")], default="draft", max_length=32)),
            ("provider_mode", models.CharField(default="codex_fixture", max_length=32)), ("record_version", models.PositiveIntegerField(default=0)),
            ("client_request_id", models.CharField(blank=True, max_length=160, null=True, unique=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name="AuditRun", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("provider_mode", models.CharField(max_length=32)), ("status", models.CharField(max_length=32)),
            ("schema_version", models.CharField(default="audit.v1", max_length=40)), ("errors", models.JSONField(default=list)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audits", to="teachback.learningsession")),
        ]),
        migrations.CreateModel(name="Claim", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("claim_id", models.CharField(max_length=120)), ("learner_text", models.TextField(max_length=6000)),
            ("verdict", models.CharField(choices=[(x, x) for x in ("supported", "misconception", "needs_precision", "needs_human_review")], max_length=32)),
            ("misconception_type", models.CharField(blank=True, choices=[(x, x) for x in ("source_of_matter", "causal_mechanism", "terminology")], max_length=40, null=True)),
            ("probe", models.TextField(blank=True, max_length=2000)), ("source_anchor_ids", models.JSONField(default=list)),
            ("revision_count", models.PositiveIntegerField(default=0)), ("position", models.PositiveIntegerField(default=0)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="claims", to="teachback.learningsession")),
        ]),
        migrations.CreateModel(name="Clarification", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("question", models.TextField(max_length=4000)), ("status", models.CharField(choices=[(x, x) for x in ("pending", "answered", "abstained", "needs_human_review")], max_length=32)),
            ("answer", models.TextField(blank=True)), ("source_anchor_ids", models.JSONField(default=list)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("claim", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="clarifications", to="teachback.claim")),
            ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="clarifications", to="teachback.learningsession")),
        ]),
        migrations.CreateModel(name="Revision", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("old_text", models.TextField(max_length=6000)), ("new_text", models.TextField(max_length=6000)),
            ("old_verdict", models.CharField(max_length=32)), ("new_verdict", models.CharField(max_length=32)),
            ("warning", models.CharField(blank=True, max_length=240)), ("record_version", models.PositiveIntegerField()), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("claim", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revisions", to="teachback.claim")),
            ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revisions", to="teachback.learningsession")),
        ]),
        migrations.AddConstraint(model_name="claim", constraint=models.UniqueConstraint(fields=("session", "claim_id"), name="unique_session_claim")),
    ]
