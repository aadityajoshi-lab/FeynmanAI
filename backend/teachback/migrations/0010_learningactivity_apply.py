from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("teachback", "0009_organization_invitation")]

    operations = [
        migrations.AlterField(
            model_name="learningactivity",
            name="activity_type",
            field=models.CharField(
                choices=[
                    ("predict", "predict"),
                    ("explain", "explain"),
                    ("derive", "derive"),
                    ("debug", "debug"),
                    ("simulate", "simulate"),
                    ("apply", "apply"),
                    ("build", "build"),
                    ("transfer", "transfer"),
                ],
                default="explain",
                max_length=32,
            ),
        ),
    ]
