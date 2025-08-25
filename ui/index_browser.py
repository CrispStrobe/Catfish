# ui/index_browser.py

"""Index browser for offline content viewing."""
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import List
from datetime import datetime as dt

from core.file_index import FileIndex
from core.data_structures import FileEntry
from utils.i18n import translator as t
from utils.platform_utils import get_screen_geometry, calculate_window_geometry, open_file_or_folder
from utils.file_utils import format_size, get_display_path, path_is_native_and_exists
from utils.platform_utils import open_file_or_folder, FileOperationError

class IndexBrowserWindow:
    """Window for browsing index contents without requiring mounted volumes."""
    
    def __init__(self, parent, caf_path: Path):
        self.parent = parent
        self.caf_path = caf_path
        self.file_entries = []
        
        self.root = tk.Toplevel(parent)
        self.root.title(f"Browse Index: {caf_path.name}")
        
        # Responsive geometry
        screen_width, screen_height = get_screen_geometry()
        geometry = calculate_window_geometry(screen_width, screen_height)
        self.root.geometry(geometry)
        
        self.setup_ui()
        self.load_index_contents()
        
        # Make modal
        self.root.transient(parent)
        self.root.grab_set()
    
    def setup_ui(self):
        """Setup the browser UI."""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Info frame
        info_frame = ttk.LabelFrame(main_frame, text="Index Information", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.info_var = tk.StringVar()
        self.info_var.set("Loading index...")
        ttk.Label(info_frame, textvariable=self.info_var).pack(anchor=tk.W)
        
        # Search frame
        search_frame = ttk.LabelFrame(main_frame, text="Search in Index", padding=10)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        search_inner = ttk.Frame(search_frame)
        search_inner.pack(fill=tk.X)
        
        ttk.Label(search_inner, text="Filter:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_inner, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))
        self.search_entry.bind('<KeyRelease>', self.on_search_change)
        
        ttk.Button(search_inner, text="Clear", command=self.clear_search).pack(side=tk.RIGHT)
        
        # Files tree
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('Size', 'Modified', 'Path', 'Status')
        self.files_tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings')
        self.files_tree.heading('#0', text='Filename')
        self.files_tree.heading('Size', text='Size')
        self.files_tree.heading('Modified', text='Modified')
        self.files_tree.heading('Path', text='Full Path')
        self.files_tree.heading('Status', text='Exists')
        
        # Column widths
        self.files_tree.column('#0', width=200, minwidth=150)
        self.files_tree.column('Size', width=80, minwidth=60)
        self.files_tree.column('Modified', width=120, minwidth=100)
        self.files_tree.column('Path', width=350, minwidth=250)
        self.files_tree.column('Status', width=60, minwidth=50)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.files_tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.files_tree.xview)
        self.files_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.files_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind events
        self.files_tree.bind('<Double-Button-1>', self.on_file_double_click)
        self.files_tree.bind('<Button-3>', self.on_file_right_click)
        
        # Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(action_frame, text="Export List", command=self.export_file_list).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="Copy Path", command=self.copy_selected_path).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text="Close", command=self.close).pack(side=tk.RIGHT)
        
        # Status bar
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def load_index_contents(self):
        """Load and display index contents."""
        try:
            # Load index using existing FileIndex method
            file_index = FileIndex.load_from_caf(self.caf_path, False, 'md5')  # Hash doesn't matter for browsing
            
            if not file_index:
                self.info_var.set("Failed to load index")
                return
            
            # Extract all file entries
            self.file_entries = []
            for size, entries in file_index.size_index.items():
                self.file_entries.extend(entries)
            
            # Update info
            total_files = len(self.file_entries)
            total_size = sum(entry.size for entry in self.file_entries)
            existing_files = sum(1 for entry in self.file_entries if path_is_native_and_exists(entry.path))
            
            info_text = f"Total files: {total_files:,} | Total size: {format_size(total_size)} | "
            info_text += f"Existing: {existing_files:,} ({existing_files/total_files*100:.1f}%)"
            self.info_var.set(info_text)
            
            # Populate tree
            self.populate_files_tree()
            self.status_var.set(f"Loaded {total_files:,} files from index")
            
        except Exception as e:
            self.info_var.set(f"Error loading index: {e}")
            self.status_var.set("Failed to load index")
    
    def populate_files_tree(self, filter_text=None):
        """Populate the files tree with optional filtering."""
        # Clear existing items
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        
        # Apply filter
        entries_to_show = self.file_entries
        if filter_text:
            try:
                pattern = re.compile(filter_text, re.IGNORECASE)
                entries_to_show = [entry for entry in self.file_entries 
                                if pattern.search(entry.path.name) or pattern.search(str(entry.path))]
            except re.error:
                entries_to_show = [entry for entry in self.file_entries 
                                if filter_text.lower() in entry.path.name.lower() or 
                                    filter_text.lower() in str(entry.path).lower()]
        
        # Sort by path
        entries_to_show.sort(key=lambda x: str(x.path))
        
        # Populate tree
        for entry in entries_to_show:
            filename = entry.path.name
            size_str = format_size(entry.size)
            modified_str = dt.fromtimestamp(entry.mtime).strftime('%Y-%m-%d %H:%M')
            
            # Clean up path display - show relative path from home
            try:
                home_path = Path.home()
                if entry.path.is_relative_to(home_path):
                    display_path = "~" / entry.path.relative_to(home_path)
                else:
                    display_path = entry.path
            except (ValueError, OSError):
                display_path = entry.path
                
            path_str = get_display_path(entry.path)
            exists_str = "Yes" if entry.path.exists() else "No"
            
            # Color coding for existing vs non-existing files
            exists = path_is_native_and_exists(entry.path)
            exists_str = "Yes" if exists else "No"
            tags = ('exists',) if exists else ('missing',)
            
            self.files_tree.insert('', 'end',
                                text=filename,
                                values=(size_str, modified_str, path_str, exists_str),
                                tags=tags)
        
        # Configure tag colors - FIX VISIBILITY ISSUE
        self.files_tree.tag_configure('missing', foreground='gray')
        self.files_tree.tag_configure('exists', foreground='white')
        
        self.status_var.set(f"Showing {len(entries_to_show):,} of {len(self.file_entries):,} files")

    def on_search_change(self, event):
        """Handle search text changes."""
        filter_text = self.search_var.get().strip()
        self.populate_files_tree(filter_text if filter_text else None)
    
    def clear_search(self):
        """Clear search filter."""
        self.search_var.set("")
        self.populate_files_tree()
    
    def on_file_double_click(self, event):
        """Handle double-click on file with error handling."""
        selection = self.files_tree.selection()
        if selection:
            item = selection[0]
            path_str = self.files_tree.item(item, 'values')[2]
            path = Path(path_str)
            
            try:
                open_file_or_folder(path, open_folder=False)
            except FileNotFoundError:
                messagebox.showinfo("File Not Available", 
                                f"File is not currently accessible:\n{path}\n\n"
                                "This may be because the volume is not mounted or the file has been moved.")
            except FileOperationError as e:
                messagebox.showerror(t.get('error'), str(e))
                
    def on_file_right_click(self, event):
        """Handle right-click context menu."""
        selection = self.files_tree.selection()
        if selection:
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="Copy Path", command=self.copy_selected_path)
            menu.add_command(label="Copy Filename", command=self.copy_selected_filename)
            menu.add_command(label="Show in Folder", command=self.show_in_folder)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
    
    def copy_selected_path(self):
        """Copy selected file path to clipboard."""
        selection = self.files_tree.selection()
        if selection:
            item = selection[0]
            path_str = self.files_tree.item(item, 'values')[2]
            self.root.clipboard_clear()
            self.root.clipboard_append(path_str)
            self.status_var.set("Path copied to clipboard")
    
    def copy_selected_filename(self):
        """Copy selected filename to clipboard."""
        selection = self.files_tree.selection()
        if selection:
            item = selection[0]
            filename = self.files_tree.item(item, 'text')
            self.root.clipboard_clear()
            self.root.clipboard_append(filename)
            self.status_var.set("Filename copied to clipboard")
    
    def show_in_folder(self):
        """Show selected file in folder if it exists with error handling."""
        selection = self.files_tree.selection()
        if selection:
            item = selection[0]
            path_str = self.files_tree.item(item, 'values')[2]
            path = Path(path_str)
            
            try:
                open_file_or_folder(path, open_folder=True)
            except FileNotFoundError:
                messagebox.showinfo("File Not Available", "File is not currently accessible.")
            except FileOperationError as e:
                messagebox.showerror(t.get('error'), str(e))

    def export_file_list(self):
        """Export file list to CSV."""
        filename = filedialog.asksaveasfilename(
            title="Export File List",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("Filename,Size,Size (bytes),Modified,Full Path,Exists\n")
                    
                    for item in self.files_tree.get_children():
                        text = self.files_tree.item(item, 'text').replace('"', '""')
                        values = [str(v).replace('"', '""') for v in self.files_tree.item(item, 'values')]
                        size_bytes = next((entry.size for entry in self.file_entries 
                                         if str(entry.path) == values[2]), 0)
                        
                        f.write(f'"{text}","{values[0]}",{size_bytes},"{values[1]}","{values[2]}","{values[3]}"\n')
                
                messagebox.showinfo("Success", f"File list exported to:\n{filename}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export file list:\n{e}")
    
    def close(self):
        """Close the browser window."""
        self.root.destroy()
    
    def run(self):
        """Run the browser window."""
        self.root.wait_window()