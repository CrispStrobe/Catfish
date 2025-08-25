# core/scan_operations.py:

"""Scan operations with progress tracking."""
import queue
from pathlib import Path
from typing import List, Optional
from threading import Thread

from core.data_structures import ScanConfig, DuplicateMatch
from core.file_index import FileIndex
from core.search_logic import build_destination_index, find_duplicates_with_locations
from utils.file_utils import filter_overlapping_paths, get_caf_path

def run_scan_with_progress(config: ScanConfig, parent, translator_get_func) -> List[DuplicateMatch]:
    """Run the complete scan with progress window"""
    from ui.progress_window import ProgressWindow
    
    progress_window = ProgressWindow(parent, translator_get_func('finding_duplicates'))
    duplicates = []
    
    # Thread-safe communication queue
    progress_queue = queue.Queue()
    
    def update_progress_from_queue():
        """Safely updates GUI from main thread by checking the queue"""
        try:
            while True:
                message_type, operation, details = progress_queue.get_nowait()
                if message_type == "progress":
                    progress_window.update_operation(operation)
                    progress_window.update_details(details)
                elif message_type == "error":
                    from tkinter import messagebox
                    messagebox.showerror(translator_get_func('error'), translator_get_func('scan_failed', details))
                elif message_type == "complete":
                    progress_window.root.quit()
                    return
        except queue.Empty:
            pass
        
        # Reschedule this check if thread is still running
        if scan_thread_obj.is_alive():
            progress_window.root.after(100, update_progress_from_queue)
    
    def progress_callback(operation, details):
        """Thread-safe progress callback"""
        progress_queue.put(("progress", operation, details))
    
    def scan_thread():
        nonlocal duplicates
        try:
            # Build destination index
            dest_index = build_destination_index(config, progress_callback, progress_window.cancelled)
            
            if not progress_window.cancelled.is_set() and dest_index:
                # Find duplicates
                duplicates = find_duplicates_with_locations(config.source_path, dest_index, 
                                                          progress_callback, progress_window.cancelled)
            
        except Exception as e:
            progress_queue.put(("error", "Error", str(e)))
        finally:
            progress_queue.put(("complete", "", ""))
    
    # Start scan in background thread
    scan_thread_obj = Thread(target=scan_thread)
    scan_thread_obj.daemon = True
    scan_thread_obj.start()
    
    # Start queue polling from main thread
    progress_window.root.after(100, update_progress_from_queue)
    
    # Run progress GUI
    progress_window.root.mainloop()
    progress_window.root.destroy()
    
    # Wait for thread to complete
    scan_thread_obj.join(timeout=1.0)
    
    return duplicates if not progress_window.cancelled.is_set() else []

def run_scan_with_progress_enhanced(config: ScanConfig, parent, translator_get_func) -> List[DuplicateMatch]:
    """Enhanced scan with selective index recreation."""
    from ui.progress_window import ProgressWindow
    
    progress_window = ProgressWindow(parent, translator_get_func('finding_duplicates'))
    duplicates = []
    
    # Thread-safe communication queue
    progress_queue = queue.Queue()
    
    def update_progress_from_queue():
        try:
            while True:
                message_type, operation, details = progress_queue.get_nowait()
                if message_type == "progress":
                    progress_window.update_operation(operation)
                    progress_window.update_details(details)
                elif message_type == "error":
                    from tkinter import messagebox
                    messagebox.showerror(translator_get_func('error'), translator_get_func('scan_failed', details))
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
            # Build destination index with selective recreation
            dest_index = build_destination_index_selective(config, progress_callback, progress_window.cancelled, translator_get_func)
            
            if not progress_window.cancelled.is_set() and dest_index:
                duplicates = find_duplicates_with_locations(config.source_path, dest_index, 
                                                          progress_callback, progress_window.cancelled)
            
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

def build_destination_index_selective(config: ScanConfig, progress_callback=None, cancel_event=None, translator_get_func=None) -> Optional[FileIndex]:
    """Build destination index with selective recreation of specific indices."""
    filtered_paths = filter_overlapping_paths(config.dest_paths)
    
    if progress_callback:
        progress_callback(translator_get_func('building_index') if translator_get_func else "Building index", 
                         f"Processing {len(filtered_paths)} destination folders")
    
    dummy_root = Path('.') 
    combined_index = FileIndex(dummy_root, config.use_hash, config.hash_algo)
    
    for i, dest_path in enumerate(filtered_paths):
        if cancel_event and cancel_event.is_set(): 
            break
        if not dest_path.is_dir(): 
            continue

        caf_path = get_caf_path(dest_path, config.hash_algo)
        dest_index = None

        if progress_callback:
            progress_callback(f"Processing folder {i+1}/{len(filtered_paths)}", f"Folder: {dest_path.name}")
        
        # Check if this specific path needs recreation
        force_recreate = (hasattr(config, 'selective_recreation_paths') and 
                         dest_path in config.selective_recreation_paths)
        
        # Try to load existing index (unless forced recreation)
        if config.reuse_indices and not force_recreate and caf_path.exists():
            if progress_callback: 
                progress_callback(f"Loading index for {dest_path.name}", "Please wait...")
            dest_index = FileIndex.load_from_caf(caf_path, config.use_hash, config.hash_algo)
        
        # Build new index if needed
        if not dest_index:
            if progress_callback: 
                scanning_text = translator_get_func('scanning_files') if translator_get_func else "Scanning files..."
                progress_callback(f"Creating new index for {dest_path.name}", scanning_text)
            dest_index = FileIndex(dest_path, config.use_hash, config.hash_algo)
            
            import os
            for root, _, files in os.walk(dest_path):
                if cancel_event and cancel_event.is_set(): 
                    break
                root_path = Path(root)
                for j, filename in enumerate(files):
                    if cancel_event and cancel_event.is_set(): 
                        break
                    if progress_callback and j % 200 == 0:
                        progress_callback(f"Indexing {dest_path.name}", f"File: {filename}")
                    dest_index.add_file(root_path / filename)
            
            if cancel_event and cancel_event.is_set(): 
                break

            # Save the newly created index
            if config.reuse_indices:
                if progress_callback: 
                    progress_callback(f"Saving index for {dest_path.name}", f"Path: {caf_path.name}")
                dest_index.save_to_caf(caf_path)
        
        if not dest_index: 
            continue

        # Merge into combined index
        for size, entries in dest_index.size_index.items():
            combined_index.size_index[size].extend(entries)
        if config.use_hash:
            for key, entries in dest_index.hash_index.items():
                combined_index.hash_index[key].extend(entries)
        combined_index.total_files += dest_index.total_files
        
    return combined_index