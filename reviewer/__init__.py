import pathlib, sys

# Ensure the src directory is on the import path for test imports
_src_dir = pathlib.Path(__file__).resolve().parent.parent / "src"
if _src_dir.is_dir():
    sys.path.insert(0, str(_src_dir))

# Extend the package __path__ so that submodules are resolved from src/reviewer
_impl_dir = pathlib.Path(__file__).resolve().parent.parent / "src" / "reviewer"
if _impl_dir.is_dir():
    __path__.append(str(_impl_dir))
