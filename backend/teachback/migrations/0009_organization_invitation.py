import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("teachback", "0008_learning_os_foundations")]

    operations = [
        migrations.CreateModel(
            name="OrganizationInvitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("invitation_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("email", models.EmailField(max_length=254)),
                ("role", models.CharField(choices=[("owner", "owner"), ("institution_admin", "institution_admin"), ("instructor", "instructor"), ("learner", "learner")], default="learner", max_length=32)),
                ("token", models.CharField(default=uuid.uuid4, editable=False, max_length=64, unique=True)),
                ("status", models.CharField(default="pending", max_length=24)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invitations", to="teachback.organization")),
            ],
        ),
    ]
