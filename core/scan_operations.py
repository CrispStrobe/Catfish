# core/scan_operations.py

"""Scan operations with progress tracking."""

import queue
from threading import Thread

from core.data_structures import DuplicateMatch, ScanConfig
from core.search_logic import build_destination_index, find_duplicates_with_locations


def run_scan_with_progress(config: ScanConfig, parent, translator_get_func) -> list[DuplicateMatch]:
    """Run the complete scan with progress window."""
    from ui.progress_window import ProgressWindow

    progress_window = ProgressWindow(parent, translator_get_func("finding_duplicates"))
    duplicates: list[DuplicateMatch] = []

    progress_queue: queue.Queue[tuple[str, str, str]] = queue.Queue()

    def update_progress_from_queue():
        """Safely updates GUI from main thread by checking the queue."""
        try:
            while True:
                message_type, operation, details = progress_queue.get_nowait()
                if message_type == "progress":
                    progress_window.update_operation(operation)
                    progress_window.update_details(details)
                elif message_type == "error":
                    from tkinter import messagebox

                    messagebox.showerror(translator_get_func("error"), translator_get_func("scan_failed", details))
                elif message_type == "complete":
                    progress_window.root.quit()
                    return
        except queue.Empty:
            pass

        if scan_thread_obj.is_alive():
            progress_window.root.after(100, update_progress_from_queue)

    def progress_callback(operation, details):
        progress_queue.put(("progress", operation, details))

    def scan_thread():
        nonlocal duplicates
        try:
            dest_index = build_destination_index(
                config, progress_callback, progress_window.cancelled, translator_get_func
            )

            if not progress_window.cancelled.is_set() and dest_index:
                duplicates = find_duplicates_with_locations(
                    config.source_path, dest_index, progress_callback, progress_window.cancelled
                )
        except Exception as e:
            progress_queue.put(("error", "Error", str(e)))
        finally:
            progress_queue.put(("complete", "", ""))

    scan_thread_obj = Thread(target=scan_thread)
    scan_thread_obj.daemon = True
    scan_thread_obj.start()

    progress_window.root.after(100, update_progress_from_queue)
    progress_window.root.mainloop()
    progress_window.root.destroy()

    scan_thread_obj.join(timeout=1.0)
    return duplicates if not progress_window.cancelled.is_set() else []


# Keep as alias for backward compatibility with UI code
run_scan_with_progress_enhanced = run_scan_with_progress
