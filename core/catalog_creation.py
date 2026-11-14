"""Shared, headless catalog creation used by the Create Index dialog."""

from pathlib import Path

from core.file_index import FileIndex


def create_catalog(
    root: Path,
    destination: Path,
    use_hash: bool = False,
    hash_algo: str = "md5",
    *,
    progress_callback=None,
    cancel_event=None,
) -> FileIndex:
    """Scan once and save only a complete, uncancelled catalog.

    Progress uses the count already indexed; there is no preliminary count walk.
    Callbacks execute on the caller's thread and must not directly touch Tk when
    this function runs in a background worker.
    """

    def progress(count, path):
        progress_callback(f"Indexed {count:,} files · {path.name}")

    index = FileIndex.scan_directory(
        root,
        use_hash,
        hash_algo,
        progress_callback=progress if progress_callback is not None else None,
        cancel_event=cancel_event,
    )
    if index.cancelled:
        raise InterruptedError("Catalog creation cancelled")
    if index.scan_error_count:
        examples = "\n".join(f"{error.path}: {error.message}" for error in index.scan_errors[:3])
        raise OSError(
            f"{index.scan_error_count} entries or folders could not be indexed. "
            f"The previous catalog has been kept.\n{examples}"
        )
    if progress_callback is not None:
        progress_callback("Saving index file…")
    index.save_to_caf(destination, cancel_event=cancel_event)
    return index
