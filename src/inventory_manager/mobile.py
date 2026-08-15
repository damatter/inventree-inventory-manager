"""Shared contract for exposing authenticated features to the mobile app."""


class MobileAppMixin:
    """Advertise native renderers through InvenTree plugin UI features."""

    MOBILE_APP_SCHEMA_VERSION = 1
    MOBILE_APP_FEATURES: tuple[dict, ...] = ()

    @classmethod
    def mobile_app_options(cls, renderer: str, endpoint: str) -> dict:
        """Return the versioned feature options understood by the mobile app."""

        return {
            "mobile": {
                "schema_version": cls.MOBILE_APP_SCHEMA_VERSION,
                "renderer": renderer,
                "endpoint": endpoint,
            }
        }

    @classmethod
    def mobile_app_manifest(cls) -> dict:
        """Return a machine-readable description of every mobile integration."""

        return {
            "schema_version": cls.MOBILE_APP_SCHEMA_VERSION,
            "features": list(cls.MOBILE_APP_FEATURES),
        }
