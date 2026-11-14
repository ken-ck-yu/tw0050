"""Ingest modules. Importing the package imports every submodule; failures are recorded."""

import importlib
import pkgutil

IMPORT_ERRORS: dict[str, str] = {}

for _m in pkgutil.iter_modules(__path__):
    try:
        importlib.import_module(f"{__name__}.{_m.name}")
    except Exception as _e:  # a broken module must not break every command
        IMPORT_ERRORS[_m.name] = f"{type(_e).__name__}: {_e}"
