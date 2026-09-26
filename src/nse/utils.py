from pathlib import Path
from typing import Union


def prepare_path(path: Union[str, Path], isFolder: bool = False):
    """Resolve and validate a filesystem path.

    Expands ``~``, converts to an absolute path, and — if ``isFolder`` is
    ``True`` — ensures the path is a directory, creating it (including parents)
    if it does not exist.

    :param path: The path to resolve. Strings are converted to :class:`Path`.
    :type path: Union[str, Path]
    :param isFolder: Default ``False``. If ``True``, treat ``path`` as a
        directory and enforce/create it.
    :type isFolder: bool
    :return: The resolved absolute path.
    :rtype: Path

    :raises NotADirectoryError: If ``isFolder`` is ``True`` and ``path`` exists
        but does not point to a directory. This includes symlinks whose target
        is a regular file.

    .. note::
       When ``isFolder`` is ``False``, the path is resolved but neither validated
       nor created.

    .. note::
       If ``isFolder`` is ``True`` and ``path`` does not exist, it is created
       with ``mkdir(parents=True, exist_ok=True)``. Concurrent callers racing to
       create the same directory will not raise.

    .. note::
       ``path`` is resolved with :meth:`Path.resolve` before any checks, so
       symlinks are fully followed. A broken symlink is therefore indistinguishable
       from a non-existent path, and its target directory will be created when
       ``isFolder`` is ``True``.

    .. note::
       This is a static method.
    """
    path = path if isinstance(path, Path) else Path(path)
    path = path.expanduser().resolve()

    if isFolder:
        if path.exists() and not path.is_dir():
            raise NotADirectoryError(f"{path}: must be a folder")

        path.mkdir(parents=True, exist_ok=True)

    return path
