try:
    from app.core.version import __version__
except ImportError:
    __version__ = "dev"
