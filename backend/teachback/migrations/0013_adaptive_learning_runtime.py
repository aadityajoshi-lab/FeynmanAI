from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [("teachback", "0012_notebookchatmessage_provider_provenance")]

    operations = [
        migrations.AlterField(
            model_name="learningactivity",
            name="activity_type",
            field=models.CharField(
                choices=[(item, item) for item in ("predict", "explain", "derive", "debug", "simulate", "apply", "build", "transfer", "remediate")],
                default="explain",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="learningactivity",
            name="configuration",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="learningactivity",
            name="difficulty",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="learningactivity",
            name="remediation_target",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="learningactivity",
            name="transfer_target",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="evidencerecord",
            name="transition_reason",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.CreateModel(
            name="ActivityAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("attempt_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("written_explanation", models.TextField(blank=True, max_length=12000)),
                ("learner_conclusion", models.TextField(blank=True, max_length=4000)),
                ("confidence", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("prediction", models.JSONField(blank=True, default=dict)),
                ("interaction_state", models.JSONField(blank=True, default=dict)),
                ("selected_options", models.JSONField(blank=True, default=list)),
                ("calculations", models.JSONField(blank=True, default=dict)),
                ("trace", models.JSONField(blank=True, default=list)),
                ("source_ids", models.JSONField(blank=True, default=list)),
                ("source_anchor_ids", models.JSONField(blank=True, default=list)),
                ("evaluation", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("activity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activity_attempts", to="teachback.learningactivity")),
                ("goal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activity_attempts", to="teachback.learninggoal")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activity_attempts", to="teachback.learnerprofile")),
            ],
        ),
        migrations.CreateModel(
            name="CapabilityState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("capability", models.CharField(max_length=240)),
                ("status", models.CharField(default="emerging", max_length=40)),
                ("confidence", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("misconceptions", models.JSONField(blank=True, default=list)),
                ("completed_attempt_ids", models.JSONField(blank=True, default=list)),
                ("retry_history", models.JSONField(blank=True, default=list)),
                ("current_route_position", models.PositiveIntegerField(default=1)),
                ("next_action", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("goal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="capability_states", to="teachback.learninggoal")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="capability_states", to="teachback.learnerprofile")),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("profile", "goal", "capability"), name="unique_goal_capability_state")],
            },
        ),
    ]
