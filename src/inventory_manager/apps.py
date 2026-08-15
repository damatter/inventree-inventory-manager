"""Django application configuration for Inventory Manager."""

from django.apps import AppConfig


class InventoryManagerConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "inventory_manager"
    verbose_name = "Inventory Manager"
