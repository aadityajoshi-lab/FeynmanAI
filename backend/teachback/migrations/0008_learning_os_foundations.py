# Generated manually to keep the learning OS data model explicit and reviewable.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def create_personal_workspaces(apps, schema_editor):
    Organization = apps.get_model("teachback", "Organization")
    Membership = apps.get_model("teachback", "Membership")
    LearnerProfile = apps.get_model("teachback", "LearnerProfile")
    for profile in LearnerProfile.objects.filter(workspace__isnull=True).iterator():
        workspace = Organization.objects.create(
            name=(profile.display_name or "Personal workspace")[:180],
            kind="personal",
            owner=profile.account,
            settings={"legacyProfile": profile.anonymous_key},
        )
        profile.workspace_id = workspace.id
        profile.save(update_fields=["workspace"])
        if profile.account_id:
            Membership.objects.get_or_create(
                organization=workspace,
                user_id=profile.account_id,
                defaults={"role": "owner", "status": "active"},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("teachback", "0007_notebook_studio_memory"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LearningActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activity_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("activity_type", models.CharField(choices=[("predict", "predict"), ("explain", "explain"), ("derive", "derive"), ("debug", "debug"), ("simulate", "simulate"), ("build", "build"), ("transfer", "transfer")], default="explain", max_length=32)),
                ("title", models.CharField(max_length=240)),
                ("prompt", models.TextField()),
                ("position", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(default="ready", max_length=32)),
                ("prerequisites", models.JSONField(blank=True, default=list)),
                ("source_ids", models.JSONField(blank=True, default=list)),
                ("evaluator", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["position", "id"]},
        ),
        migrations.AddField(
            model_name="learnerprofile",
            name="account",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="feynman_profile", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="notebook",
            name="owner_profile",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notebooks", to="teachback.learnerprofile"),
        ),
        migrations.CreateModel(
            name="Course",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("course_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("title", models.CharField(max_length=240)),
                ("description", models.TextField(blank=True)),
                ("join_code", models.CharField(blank=True, max_length=24, unique=True)),
                ("status", models.CharField(default="draft", max_length=32)),
                ("route", models.JSONField(blank=True, default=dict)),
                ("source_policy", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("instructor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="feynman_courses", to=settings.AUTH_USER_MODEL)),
                ("source_packs", models.ManyToManyField(blank=True, related_name="courses", to="teachback.sourcepack")),
            ],
        ),
        migrations.AddField(
            model_name="notebook",
            name="course",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notebooks", to="teachback.course"),
        ),
        migrations.AddField(
            model_name="learningattempt",
            name="activity",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="attempts", to="teachback.learningactivity"),
        ),
        migrations.CreateModel(
            name="LearningGoal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("goal_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("title", models.CharField(max_length=240)),
                ("description", models.TextField(blank=True)),
                ("domain", models.CharField(default="general", max_length=80)),
                ("outcome", models.CharField(blank=True, max_length=500)),
                ("current_level", models.CharField(default="beginner", max_length=40)),
                ("time_budget", models.CharField(blank=True, max_length=80)),
                ("source_mode", models.CharField(default="optional", max_length=40)),
                ("safety_mode", models.CharField(default="guided", max_length=40)),
                ("verification_mode", models.CharField(default="guided", max_length=40)),
                ("status", models.CharField(default="draft", max_length=32)),
                ("contract", models.JSONField(blank=True, default=dict)),
                ("route", models.JSONField(blank=True, default=dict)),
                ("next_action", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("course", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="goals", to="teachback.course")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="goals", to="teachback.learnerprofile")),
            ],
        ),
        migrations.AddField(
            model_name="learningactivity",
            name="goal",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="teachback.learninggoal"),
        ),
        migrations.CreateModel(
            name="EvidenceRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("evidence_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("capability", models.CharField(max_length=240)),
                ("evidence_type", models.CharField(default="explanation", max_length=40)),
                ("status", models.CharField(choices=[("observed", "observed"), ("verified", "verified"), ("needs_review", "needs_review"), ("rejected", "rejected")], default="observed", max_length=32)),
                ("score", models.FloatField(blank=True, null=True)),
                ("summary", models.TextField()),
                ("rubric", models.JSONField(blank=True, default=dict)),
                ("source_anchor_ids", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evidence_records", to="teachback.learnerprofile")),
                ("activity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="evidence_records", to="teachback.learningactivity")),
                ("goal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evidence_records", to="teachback.learninggoal")),
            ],
        ),
        migrations.AddField(
            model_name="learningattempt",
            name="goal",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="attempts", to="teachback.learninggoal"),
        ),
        migrations.AddField(
            model_name="notebook",
            name="goal",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notebooks", to="teachback.learninggoal"),
        ),
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("organization_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("name", models.CharField(max_length=180)),
                ("kind", models.CharField(default="institution", max_length=32)),
                ("settings", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="owned_feynman_organizations", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name="learninggoal",
            name="workspace",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="goals", to="teachback.organization"),
        ),
        migrations.AddField(
            model_name="course",
            name="organization",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="courses", to="teachback.organization"),
        ),
        migrations.AddField(
            model_name="learnerprofile",
            name="workspace",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="learner_profiles", to="teachback.organization"),
        ),
        migrations.AddField(
            model_name="notebook",
            name="workspace",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notebooks", to="teachback.organization"),
        ),
        migrations.CreateModel(
            name="ShareGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("share_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("evidence_ids", models.JSONField(blank=True, default=list)),
                ("scope", models.CharField(default="selected_evidence", max_length=80)),
                ("active", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="share_grants", to="teachback.course")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="share_grants", to="teachback.learnerprofile")),
            ],
        ),
        migrations.CreateModel(
            name="Enrollment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enrollment_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[("active", "active"), ("invited", "invited"), ("withdrawn", "withdrawn")], default="active", max_length=24)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="teachback.course")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="teachback.learnerprofile")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("course", "profile"), name="unique_course_enrollment")]},
        ),
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("membership_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("role", models.CharField(choices=[("owner", "owner"), ("institution_admin", "institution_admin"), ("instructor", "instructor"), ("learner", "learner")], default="learner", max_length=32)),
                ("status", models.CharField(choices=[("active", "active"), ("invited", "invited"), ("suspended", "suspended")], default="active", max_length=24)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feynman_memberships", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="teachback.organization")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("organization", "user"), name="unique_organization_member")]},
        ),
        migrations.RunPython(create_personal_workspaces, migrations.RunPython.noop),
    ]
