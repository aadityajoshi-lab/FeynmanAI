from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _configure_sqlite_connection(sender, connection, **_kwargs) -> None:
    """Use bounded waits for the concurrent local workspace read pattern."""
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")


class TeachbackConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "teachback"

    def ready(self) -> None:
        connection_created.connect(_configure_sqlite_connection, dispatch_uid="teachback.sqlite_connection_tuning")
