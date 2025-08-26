# ui/duplicate_results.py

"""Duplicate results management window."""
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import List, Set
from datetime import datetime as dt

from core.data_structures import DuplicateMatch
from utils.i18n import translator as t
from utils.platform_utils import get_screen_geometry, calculate_window_geometry, open_file_or_folder
from utils.file_utils import format_size, get_platform_info, get_default_script_name, escape_script_path
from utils.platform_utils import open_file_or_folder, FileOperationError, make_script_executable

class DuplicateResultsWindow:
    """Window for displaying and managing duplicate results."""
    
    def __init__(self, parent, duplicates: List[DuplicateMatch], method: str):
        self.parent = parent
        self.duplicates = duplicates
        self.method = method
        self.selected_for_deletion = set()
        self.action = None
        
        self.root = tk.Toplevel(parent.root)
        self.root.title(t.get('duplicate_manager'))
        
        # Responsive geometry
        screen_width, screen_height = get_screen_geometry()
        geometry = calculate_window_geometry(screen_width, screen_height)
        self.root.geometry(geometry)
        
        self.setup_ui()
        self.populate_tree()
        
        # Make modal
        self.root.transient(parent.root)
        self.root.grab_set()

    def show_in_folder(self):
        """Show selected file in folder if it exists with error handling."""
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            path_str = self.tree.item(item, 'values')[1]
            path = Path(path_str)
            try:
                open_file_or_folder(path, open_folder=True)
            except FileNotFoundError:
                messagebox.showinfo("File Not Available", "File is not currently accessible.")
            except FileOperationError as e:
                messagebox.showerror(t.get('error'), str(e))

    def setup_ui(self):
        """Setup the GUI components with enhanced duplicate selection"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Info frame
        info_frame = ttk.LabelFrame(main_frame, text=t.get('information'), padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        try:
            total_size_bytes = sum(d.source_file.stat().st_size for d in self.duplicates if d.source_file.exists())
        except:
            total_size_bytes = 0
            
        info_text = f"{t.get('method')}: {self.method} | {t.get('found')} {len(self.duplicates)} {t.get('files_with_duplicates')} | {t.get('total_size')}: {format_size(total_size_bytes)}"
        ttk.Label(info_frame, text=info_text).pack(anchor=tk.W)
        
        # Selection mode frame
        mode_frame = ttk.Frame(info_frame)
        mode_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.selection_mode_var = tk.StringVar(value="source")
        ttk.Radiobutton(mode_frame, text=t.get('source_duplicates'), variable=self.selection_mode_var, 
                    value="source", command=self.on_selection_mode_change).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text=t.get('destination_duplicates'), variable=self.selection_mode_var, 
                    value="destination", command=self.on_selection_mode_change).pack(side=tk.LEFT, padx=(20, 0))
        
        # Filter frame
        filter_frame = ttk.LabelFrame(main_frame, text=t.get('filter'), padding=10)
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        filter_inner = ttk.Frame(filter_frame)
        filter_inner.pack(fill=tk.X)
        
        ttk.Label(filter_inner, text=t.get('regex_filter')).pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(filter_inner, textvariable=self.filter_var)
        self.filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))
        self.filter_entry.bind('<KeyRelease>', self.on_filter_change)
        
        ttk.Button(filter_inner, text=t.get('select_all_filtered'), command=self.select_all_filtered).pack(side=tk.RIGHT, padx=(0, 5))
        ttk.Button(filter_inner, text=t.get('deselect_all'), command=self.deselect_all).pack(side=tk.RIGHT, padx=(0, 5))
        
        # Tree frame
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('Size', 'Path')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings')
        self.tree.heading('#0', text='File')
        self.tree.heading('Size', text='Size')
        self.tree.heading('Path', text='Path')
        
        # Column widths
        self.tree.column('#0', width=300, minwidth=200)
        self.tree.column('Size', width=120, minwidth=100)
        self.tree.column('Path', width=500, minwidth=400)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind events
        self.tree.bind('<Button-1>', self.on_tree_click)
        self.tree.bind('<space>', self.on_space_key)
        self.tree.bind('<Control-c>', self.copy_path_to_clipboard)
        self.tree.bind('<Double-Button-1>', self.on_double_click)
        
        # Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(action_frame, text=t.get('delete_selected'), command=self.delete_selected_files).pack(side=tk.LEFT)
        ttk.Button(action_frame, text=t.get('generate_script'), command=self.generate_script).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('new_scan'), command=self.new_scan).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('close_button'), command=self.close).pack(side=tk.RIGHT)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set(t.get('no_selection_status'))
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))

    def populate_tree(self):
        """Populate the tree view with duplicates - enhanced for both source and destination selection"""
        for i, duplicate in enumerate(self.duplicates):
            try:
                source_size = duplicate.source_file.stat().st_size
                source_id = self.tree.insert('', 'end', 
                                        text=f"☐ {duplicate.source_file.name}",
                                        values=(f"{source_size:,} bytes", str(duplicate.source_file)),
                                        tags=('source', f'dup_{i}'))
                
                for j, dest in enumerate(duplicate.destinations):
                    dest_id = self.tree.insert(source_id, 'end',
                                text=f"☐ → {dest.path.name}",
                                values=(f"{dest.size:,} bytes", str(dest.path)),
                                tags=('destination', f'dup_{i}_{j}'))
            except OSError:
                continue

    def on_selection_mode_change(self):
        """Handle selection mode change between source and destination"""
        # Clear all selections when mode changes
        self.deselect_all()

    def on_tree_click(self, event):
        """Handle tree item clicks for selection - enhanced for mode awareness"""
        item = self.tree.identify_row(event.y)
        if item:
            tags = self.tree.item(item, 'tags')
            mode = self.selection_mode_var.get()
            
            if mode == "source" and 'source' in tags and 'hidden' not in tags:
                self.toggle_selection(item)
            elif mode == "destination" and 'destination' in tags and 'hidden' not in tags:
                self.toggle_selection(item)

    def update_status(self):
        """Update status bar with selection count"""
        count = len(self.selected_for_deletion)
        if count > 0:
            try:
                total_size = sum(Path(self.tree.item(item, 'values')[1]).stat().st_size 
                            for item in self.selected_for_deletion)
                self.status_var.set(f"{t.get('selected')}: {count} files ({total_size/1024/1024:.1f} MB)")
            except:
                self.status_var.set(f"{t.get('selected')}: {count} files")
        else:
            self.status_var.set(t.get('no_selection_status'))
    
    def on_filter_change(self, event):
        """Handle filter text changes and correctly un-hide items."""
        filter_text = self.filter_var.get()
        
        try:
            # Compile pattern only if filter_text is not empty
            pattern = re.compile(filter_text, re.IGNORECASE) if filter_text else None
            
            # Iterate through all items and their children
            for item in self.tree.get_children(''):
                # Process the parent item
                self._filter_item(item, pattern)
                # Process child items
                for child_item in self.tree.get_children(item):
                    self._filter_item(child_item, pattern)

        except re.error:
            # If regex is invalid, do nothing
            pass

    def _filter_item(self, item, pattern):
        """Helper to show/hide a single tree item based on a regex pattern."""
        tags = list(self.tree.item(item, 'tags'))
        item_path = self.tree.item(item, 'values')[1]
        
        # Determine if the item should be visible
        is_visible = not pattern or pattern.search(item_path)

        if is_visible:
            # If it should be visible, REMOVE the 'hidden' tag
            if 'hidden' in tags:
                tags.remove('hidden')
                self.tree.item(item, tags=tuple(tags))
            # Detach and re-attach to force redraw in correct position
            parent = self.tree.parent(item)
            index = self.tree.index(item)
            self.tree.detach(item)
            self.tree.move(item, parent, index)
        else:
            # If it should be hidden, ADD the 'hidden' tag
            if 'hidden' not in tags:
                tags.append('hidden')
                self.tree.item(item, tags=tuple(tags))
            # Detach to hide
            self.tree.detach(item)
    
    def on_space_key(self, event):
        """Handle space key for selection"""
        item = self.tree.focus()
        if item:
            tags = self.tree.item(item, 'tags')
            if 'source' in tags and 'hidden' not in tags:
                self.toggle_selection(item)
    
    def on_double_click(self, event):
        """Handle double-click to open file with error handling."""
        item = self.tree.identify_row(event.y)
        if item and 'hidden' not in self.tree.item(item, 'tags'):
            path_str = self.tree.item(item, 'values')[1]
            path = Path(path_str)
            try:
                open_file_or_folder(path)
            except FileNotFoundError:
                messagebox.showerror(t.get('error'), t.get('file_not_found', path))
            except FileOperationError as e:
                messagebox.showerror(t.get('error'), str(e))
    
    def toggle_selection(self, item):
        """Toggle selection state of an item"""
        current_text = self.tree.item(item, 'text')
        if item in self.selected_for_deletion:
            self.selected_for_deletion.remove(item)
            new_text = current_text.replace('☑', '☐')
        else:
            self.selected_for_deletion.add(item)
            new_text = current_text.replace('☐', '☑')
        
        self.tree.item(item, text=new_text)
        self.update_status()
    
    def select_all_filtered(self):
        """Select all visible (filtered) items"""
        for item in self.tree.get_children():
            tags = self.tree.item(item, 'tags')
            if 'source' in tags and 'hidden' not in tags and item not in self.selected_for_deletion:
                self.toggle_selection(item)
    
    def deselect_all(self):
        """Deselect all items"""
        for item in list(self.selected_for_deletion):
            self.toggle_selection(item)
    
    def delete_selected_files(self):
        """Delete selected files directly"""
        if not self.selected_for_deletion:
            messagebox.showwarning("Warning", t.get('no_selection'))
            return

        count = len(self.selected_for_deletion)
        try:
            total_size = sum(Path(self.tree.item(item, 'values')[1]).stat().st_size for item in self.selected_for_deletion)
        except (OSError, IndexError):
            messagebox.showerror("Error", "Could not calculate size of selected files.")
            return

        # Safety confirmation dialog
        if not messagebox.askyesno("Confirm Deletion",
                                   f"Are you sure you want to permanently delete {count} files ({format_size(total_size)})?\n\nThis action CANNOT be undone."):
            return

        deleted_count = 0
        failed_deletions = []
        
        # Iterate over a copy because we're modifying the set and tree
        for item in list(self.selected_for_deletion):
            file_path_str = self.tree.item(item, 'values')[1]
            file_path = Path(file_path_str)
            try:
                file_path.unlink()
                deleted_count += 1
                self.tree.delete(item)
                self.selected_for_deletion.remove(item)
            except OSError as e:
                failed_deletions.append(f"{file_path.name}: {e}")
        
        # Final report message
        message = f"Successfully deleted {deleted_count} of {count} selected files."
        if failed_deletions:
            message += f"\n\nFailed to delete {len(failed_deletions)} files:\n"
            message += "\n".join(failed_deletions[:5]) # Show first 5 errors
            if len(failed_deletions) > 5:
                message += f"\n... and {len(failed_deletions) - 5} more."
                
        messagebox.showinfo("Deletion Complete", message)
        self.update_status()
    
    def generate_script(self):
        """Generate a script file to delete the selected items"""
        if not self.selected_for_deletion:
            messagebox.showwarning("Warning", t.get('no_selection'))
            return
            
        platform_info = get_platform_info()
        default_name = get_default_script_name()
        
        file_types = [
            (f"{platform_info['name']} scripts", f"*{platform_info['script_ext']}"),
            ("All files", "*.*")
        ]
        
        filename = filedialog.asksaveasfilename(
            title=f"Save {platform_info['name']} Deletion Script",
            defaultextension=platform_info['script_ext'],
            filetypes=file_types,
            initialfile=default_name
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(platform_info['script_header'])
                    comment = "REM" if platform_info['name'] == 'Windows' else "#"
                    f.write(f"{comment} Deletion script generated on {dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    
                    for item in self.selected_for_deletion:
                        file_path = Path(self.tree.item(item, 'values')[1])
                        quoted_path = escape_script_path(file_path)
                        f.write(f"{platform_info['delete_cmd']} {quoted_path}\n")
                    
                    f.write(f"\n{platform_info['echo_cmd']} \"Script finished.\"\n{platform_info['pause_cmd']}\n")
                
                make_script_executable(Path(filename))
                messagebox.showinfo("Success", f"Deletion script was successfully saved to:\n{filename}")

            except OSError as e:
                messagebox.showerror("Error", str(e))
    
    def copy_path_to_clipboard(self, event):
        """Copy selected file path to clipboard"""
        item = self.tree.focus()
        if item:
            path_value = self.tree.item(item, 'values')
            if path_value and len(path_value) > 1:
                self.root.clipboard_clear()
                self.root.clipboard_append(path_value[1])
                self.status_var.set(f"Copied path to clipboard: {Path(path_value[1]).name}")
                self.root.after(2000, self.update_status)
    
    def new_scan(self):
        """Signal that a new scan should be started"""
        self.action = 'new_scan'
        self.close()
    
    def close(self):
        """Close the window"""
        self.root.destroy()