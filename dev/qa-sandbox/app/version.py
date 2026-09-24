"""
version.py — Versionado centralizado de la aplicacion DLAB CRM.
Formato: MAJOR.MINOR.PATCH (Semantic Versioning)
"""

__version__ = "1.0.0"
__build__ = "20260826"
__codename__ = "Seguridad"


def get_version() -> str:
    return __version__


def get_build() -> str:
    return __build__


def get_full_version() -> str:
    return f"{__version__} (build {__build__})"


def get_version_dict() -> dict:
    return {
        "version": __version__,
        "build": __build__,
        "codename": __codename__,
        "full": get_full_version(),
    }
