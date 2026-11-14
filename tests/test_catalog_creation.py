"""Single-pass creation, cancellation, and UI-thread message handling."""

import os
from pathlib import Path
from queue import Queue
from threading import Event, get_ident
from types import SimpleNamespace

import pytest

from core.catalog_creation import create_catalog
from core.file_index import FileIndex
from ui.dialogs import IndexCreationDialog, _create_catalog_worker


def test_create_catalog_walks_each_folder_once_and_keeps_hashes_in_memory(tmp_path, monkeypatch):
    root = tmp_path / "source"
    (root / "a/b").mkdir(parents=True)
    (root / "empty").mkdir()
    (root / "a/b/data").write_bytes(b"all the bytes")
    (root / "zero").touch()
    counts = {}
    original = os.scandir

    def scandir(path):
        counts[Path(path)] = counts.get(Path(path), 0) + 1
        return original(path)

    monkeypatch.setattr(os, "scandir", scandir)
    progress = []
    catalog = tmp_path / "new.caf"
    index = create_catalog(root, catalog, True, "sha256", progress_callback=progress.append)
    assert counts == {root: 1, root / "a": 1, root / "a/b": 1, root / "empty": 1}
    assert index.total_files == 2
    assert all(len(entry.hash) == 64 for entry in index.all_files)
    assert progress[-1] == "Saving index file…"
    loaded = FileIndex.load_from_caf(catalog, False, "md5")
    assert loaded.total_files == 2
    assert sorted(entry.size for entry in loaded.all_files) == [0, 13]


def test_create_catalog_refuses_partial_scan_and_preserves_old_output(tmp_path, monkeypatch):
    catalog = tmp_path / "old.caf"
    catalog.write_bytes(b"previous")
    index = FileIndex(tmp_path)
    index._record_scan_error(tmp_path / "denied", "permission denied")
    monkeypatch.setattr(FileIndex, "scan_directory", lambda *args, **kwargs: index)
    with pytest.raises(OSError, match="1 entries or folders"):
        create_catalog(tmp_path, catalog)
    assert catalog.read_bytes() == b"previous"


def test_create_catalog_precancel_does_not_save(tmp_path):
    event = Event()
    event.set()
    output = tmp_path / "cancelled.caf"
    with pytest.raises(InterruptedError):
        create_catalog(tmp_path, output, cancel_event=event)
    assert not output.exists()


@pytest.mark.parametrize(
    "failure,expected", [(None, "success"), (InterruptedError(), "cancelled"), (OSError("denied"), "error")]
)
def test_worker_only_emits_plain_queue_messages(tmp_path, monkeypatch, failure, expected):
    def work(*args, progress_callback, **kwargs):
        progress_callback("Indexed 10 files")
        if failure is not None:
            raise failure

    monkeypatch.setattr("ui.dialogs.create_catalog", work)
    messages = Queue()
    _create_catalog_worker(tmp_path, tmp_path / "new.caf", False, "md5", Event(), messages)
    assert messages.get_nowait() == ("progress", "Indexed 10 files")
    kind, payload = messages.get_nowait()
    assert kind == expected
    assert payload == ("denied" if expected == "error" else None)
    assert messages.empty()


class _Value:
    def __init__(self, value):
        self.value = value
        self.thread = get_ident()

    def get(self):
        assert get_ident() == self.thread
        return self.value

    def set(self, value):
        assert get_ident() == self.thread
        self.value = value


class _Widget:
    def __init__(self):
        self.state = "normal"
        self.started = False

    def configure(self, **kwargs):
        self.state = kwargs.get("state", self.state)

    def start(self):
        self.started = True

    def stop(self):
        self.started = False


class _Root:
    def __init__(self):
        self.calls = {}
        self.destroyed = False
        self.thread = get_ident()

    def after(self, delay, callback):
        assert get_ident() == self.thread
        key = len(self.calls) + 1
        self.calls[key] = callback
        return key

    def after_cancel(self, key):
        assert get_ident() == self.thread
        self.calls.pop(key, None)

    def destroy(self):
        assert get_ident() == self.thread
        self.destroyed = True

    def mainloop(self):
        while self.calls:
            key = next(iter(self.calls))
            self.calls.pop(key)()

    def quit(self):
        self.calls.clear()


def _dialog(tmp_path):
    dialog = IndexCreationDialog.__new__(IndexCreationDialog)
    dialog.root = _Root()
    dialog.folder_path = tmp_path / "source"
    dialog.output_var = _Value(str(tmp_path / "new.caf"))
    dialog.use_hash_var = _Value(True)
    dialog.hash_algo_var = _Value("sha256")
    dialog.progress_var = _Value("Ready")
    dialog.progress = _Widget()
    dialog.create_button = _Widget()
    dialog.cancel_event = Event()
    dialog._messages = Queue()
    dialog._running = False
    dialog._closed = False
    dialog._poll_id = None
    dialog._active_output = None
    dialog.result = False
    return dialog


def test_dialog_captures_settings_and_prevents_concurrent_creation(tmp_path, monkeypatch):
    threads = []

    class PendingThread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args

        def start(self):
            threads.append(self)

    monkeypatch.setattr("ui.dialogs.Thread", PendingThread)
    dialog = _dialog(tmp_path)
    dialog.create_index()
    assert dialog._running
    assert dialog.create_button.state == "disabled"
    assert dialog.progress.started
    dialog.output_var.set(str(tmp_path / "different.caf"))
    dialog.use_hash_var.set(False)
    dialog.hash_algo_var.set("md5")
    dialog.create_index()
    assert len(threads) == 1
    assert threads[0].args[:4] == (tmp_path / "source", tmp_path / "new.caf", True, "sha256")


def test_cancel_stops_worker_and_ignores_late_success(tmp_path, monkeypatch):
    dialog = _dialog(tmp_path)
    dialog._running = True
    dialog._poll_id = dialog.root.after(50, dialog._poll_creation)
    shown = []
    monkeypatch.setattr("ui.dialogs.messagebox.showinfo", lambda *args, **kwargs: shown.append(args))
    dialog.cancel()
    assert dialog.cancel_event.is_set()
    assert dialog.root.destroyed
    assert not dialog.root.calls
    dialog._messages.put(("success", None))
    dialog._poll_creation()
    assert not shown
    assert not dialog.result


def test_poll_handles_progress_and_error_then_allows_retry(tmp_path, monkeypatch):
    dialog = _dialog(tmp_path)
    dialog._running = True
    dialog.progress.start()
    shown = []
    monkeypatch.setattr("ui.dialogs.messagebox.showerror", lambda *args, **kwargs: shown.append(args))
    dialog._messages.put(("progress", "Indexed 200 files"))
    dialog._messages.put(("error", "A folder was unreadable"))
    dialog._poll_creation()
    assert not dialog._running
    assert not dialog.progress.started
    assert dialog.create_button.state == "normal"
    assert dialog.progress_var.value == "Creation failed"
    assert "A folder was unreadable" in shown[0][1]
    assert not dialog.root.calls


def test_duplicate_scan_shows_one_persistent_warning_after_partial_results(tmp_path, monkeypatch):
    from core.data_structures import ScanConfig
    from core.scan_operations import run_scan_with_progress

    class ImmediateThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            self.target()

        def is_alive(self):
            return False

        def join(self, timeout):
            pass

    window = SimpleNamespace(
        root=_Root(), cancelled=Event(), update_operation=lambda text: None, update_details=lambda text: None
    )
    shown = []

    def build(config, progress, cancel, translate):
        progress("Scan warnings", "A selected folder was unreadable.")
        progress("Scan warnings", "A selected folder was unreadable.")
        return FileIndex(tmp_path)

    monkeypatch.setattr("ui.progress_window.ProgressWindow", lambda *args: window)
    monkeypatch.setattr("core.scan_operations.Thread", ImmediateThread)
    monkeypatch.setattr("core.scan_operations.build_destination_index", build)
    monkeypatch.setattr("core.scan_operations.find_duplicates_with_locations", lambda *args: [])
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *args, **kwargs: shown.append(args))
    result = run_scan_with_progress(ScanConfig(tmp_path, [tmp_path], False, "md5", False, False), None, lambda key: key)
    assert result == []
    assert len(shown) == 1
    assert shown[0][1] == "A selected folder was unreadable."
    assert window.root.destroyed
