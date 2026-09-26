import gzip
import logging
import shutil
from pathlib import Path
from typing import List, Optional, Union
from zipfile import ZipFile

logger = logging.getLogger(__file__)


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


def consume_archive(
    file: Path,
    folder: Path,
    extract_files: Optional[List[str]] = None,
) -> Path:
    """Extract a ``.zip`` or ``.gz`` archive and delete the original file.

    For ``.zip`` files:
        - If ``extract_files`` is provided, all listed members are extracted, and
          the path to the **last** member in the list is returned.
        - Otherwise, the first member in the archive's name list is extracted and
          its path returned.

    For ``.gz`` files: the decompressed contents are written to a sibling file
    whose name is the archive's stem (``foo.csv.gz`` → ``foo.csv``). Only
    single-stream ``.gz`` files are supported; ``.tar.gz`` archives are
    decompressed to a ``.tar`` file rather than extracted.

    :param file: Path to the archive to extract.
    :type file: Path
    :param folder: Directory into which contents are extracted.
    :type folder: Path
    :param extract_files: Optional list of member names to extract from a zip
        archive. If ``None``, the first member is extracted. Must be non-empty
        if provided. Defaults to ``None``.
    :type extract_files: Optional[List[str]]
    :return: Path to the extracted (or decompressed) file.
    :rtype: Path

    :raises ValueError: If ``file`` has a suffix other than ``.zip`` or ``.gz``,
        or if ``extract_files`` is provided as an empty list.
    :raises KeyError: If a name in ``extract_files`` is not present in the zip
        archive.
    :raises zipfile.BadZipFile: If the file is not a valid zip archive.
    :raises OSError: If file I/O fails during extraction or decompression.

    .. note::
       The original archive at ``file`` is deleted after a successful
       extraction. If deletion fails — for example due to a permission error
       or, on Windows, because the file is still held open by another process —
       the failure is logged and the extracted file is still returned. A
       ``FileNotFoundError`` (the archive was already removed) is silently
       ignored.

    .. note::
       If extraction fails partway through, files already written to ``folder``
       are **not** rolled back, and the original archive is left in place.

    .. note::
       This is a static method.
    """
    if extract_files is not None and len(extract_files) == 0:
        raise ValueError("extract_files must be non-empty")

    suffix = file.suffix.lower()

    if suffix == ".zip":
        with ZipFile(file) as zip:
            if extract_files is not None:
                zip.extractall(path=folder, members=extract_files)

                # return the last filepath
                filepath = folder / extract_files[-1]
            else:
                filepath = Path(zip.extract(member=zip.namelist()[0], path=folder))
    elif suffix == ".gz":
        filepath = folder / file.stem

        with gzip.open(file, "rb") as f_in, open(filepath, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    else:
        raise ValueError("Unknown file format")

    try:
        file.unlink(missing_ok=True)
    except OSError:
        logger.exception(f"Extracted to {filepath} but could not delete {file}")

    return filepath
