"""MIKE URBAN Classic MDB import, inspection export, and INP translation."""

__all__ = ["MikeUrbanImportError", "import_mike_urban_mdb", "mdb_to_inp"]


def __getattr__(name):
    if name in {"MikeUrbanImportError", "import_mike_urban_mdb"}:
        from .importer import MikeUrbanImportError, import_mike_urban_mdb
        return {"MikeUrbanImportError": MikeUrbanImportError, "import_mike_urban_mdb": import_mike_urban_mdb}[name]
    if name == "mdb_to_inp":
        from .inp import mdb_to_inp
        return mdb_to_inp
    raise AttributeError(name)
