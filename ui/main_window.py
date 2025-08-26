# ui/main_window.py

"""Main application window with tabbed interface."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import List, Optional, Set, Dict
import re
from datetime import datetime as dt

# Import all required modules with absolute imports
from core.config import Config
from core.index_discovery import IndexDiscovery
from core.data_structures import SearchCriteria, SearchResult, ScanConfig
from core.search_logic import search_files_in_index
from core.file_index import FileIndex
from core.scan_operations import run_scan_with_progress_enhanced, run_scan_with_progress
from utils.i18n import translator as t
from utils.platform_utils import get_screen_geometry, calculate_window_geometry, open_file_or_folder, FileOperationError
from utils.file_utils import format_size, parse_size, parse_date
from ui.progress_window import ProgressWindow
from ui.duplicate_results import DuplicateResultsWindow
from ui.index_browser import IndexBrowserWindow
from ui.dialogs import IndexCreationDialog
from utils.file_utils import format_size, parse_size, parse_date, get_display_path

class UniversalSearchApp:
    """Main application with tabbed interface."""
    
    def __init__(self):
        self.config = Config()
        
        # Apply language setting
        t.set_language(self.config.get('language', 'en'))
        
        self.root = tk.Tk()
        self.root.title(t.get('app_title'))
        
        # Set up geometry
        screen_width, screen_height = get_screen_geometry()
        saved_geometry = self.config.get('window_geometry')
        if saved_geometry:
            self.root.geometry(saved_geometry)
        else:
            geometry = calculate_window_geometry(screen_width, screen_height)
            self.root.geometry(geometry)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initialize components
        self.index_discovery = IndexDiscovery(self.config)
        self.available_indices = []
        self.search_results = []
        
        # Duplicate scan variables
        self.dup_source_path = None
        self.dup_dest_paths = []
        
        self.setup_ui()
        
        # Auto-load indices if enabled
        if self.config.get('auto_load_indices', True):
            self.refresh_indices()
    
    def setup_ui(self):
        """Setup the main tabbed interface."""
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tabs
        self.search_frame = ttk.Frame(self.notebook)
        self.manage_frame = ttk.Frame(self.notebook)
        self.duplicates_frame = ttk.Frame(self.notebook)
        self.settings_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.search_frame, text=t.get('search_tab'))
        self.notebook.add(self.manage_frame, text=t.get('manage_tab'))
        self.notebook.add(self.duplicates_frame, text=t.get('duplicates_tab'))
        self.notebook.add(self.settings_frame, text=t.get('settings_tab'))
        
        # Setup individual tabs
        self.setup_search_tab()
        self.setup_manage_tab()
        self.setup_duplicates_tab()
        self.setup_settings_tab()
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.update_status()

    def on_index_tree_click(self, event):
        """Handle clicks on the index tree to toggle active state."""
        item = self.index_tree.identify_row(event.y)
        column = self.index_tree.identify_column(event.x)
        
        if item and column == '#1':  # Active column
            self.toggle_index_active(item)

    def toggle_index_active(self, item):
        """Toggle active state of an index."""
        caf_path_str = self.index_tree.item(item, 'tags')[0]
        current_active = self.config.is_index_active(caf_path_str)
        
        # Toggle state
        self.config.set_index_active(caf_path_str, not current_active)
        self.config.save_config()
        
        # Update display
        current_values = list(self.index_tree.item(item, 'values'))
        current_values[0] = "☐" if current_active else "☑"
        self.index_tree.item(item, values=current_values)
        
        # Update tags
        new_tags = (caf_path_str, 'inactive' if current_active else 'active')
        self.index_tree.item(item, tags=new_tags)

    def activate_all_indices(self):
        """Activate all indices."""
        for item in self.index_tree.get_children():
            caf_path_str = self.index_tree.item(item, 'tags')[0]
            self.config.set_index_active(caf_path_str, True)
            
            # Update display
            current_values = list(self.index_tree.item(item, 'values'))
            current_values[0] = "☑"
            self.index_tree.item(item, values=current_values, tags=(caf_path_str, 'active'))
        
        self.config.save_config()

    def deactivate_all_indices(self):
        """Deactivate all indices."""
        for item in self.index_tree.get_children():
            caf_path_str = self.index_tree.item(item, 'tags')[0]
            self.config.set_index_active(caf_path_str, False)
            
            # Update display
            current_values = list(self.index_tree.item(item, 'values'))
            current_values[0] = "☐"
            self.index_tree.item(item, values=current_values, tags=(caf_path_str, 'inactive'))
        
        self.config.save_config()

    def get_active_indices_only(self) -> List[Path]:
        """Get only active indices for search operations."""
        return [caf_path for caf_path in self.available_indices 
                if self.config.is_index_active(str(caf_path))]

    def browse_index_contents(self):
        """Browse contents of selected index without requiring mounted volume."""
        selection = self.index_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an index to browse.")
            return
        
        item = selection[0]
        caf_path_str = self.index_tree.item(item, 'tags')[0]
        caf_path = Path(caf_path_str)
        
        # Launch index browser
        browser = IndexBrowserWindow(self.root, caf_path)
        browser.run()
    
    def setup_search_tab(self):
        """Setup the main search interface."""
        main_frame = ttk.Frame(self.search_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Search criteria frame
        criteria_frame = ttk.LabelFrame(main_frame, text=t.get('search_criteria'), padding=10)
        criteria_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Name pattern
        name_frame = ttk.Frame(criteria_frame)
        name_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(name_frame, text=t.get('name_pattern'), width=15).pack(side=tk.LEFT)
        self.search_name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=self.search_name_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(name_frame, text=t.get('name_examples'), foreground='gray').pack(side=tk.RIGHT)
        
        # Size range
        size_frame = ttk.Frame(criteria_frame)
        size_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(size_frame, text=t.get('size_range'), width=15).pack(side=tk.LEFT)
        
        size_inner = ttk.Frame(size_frame)
        size_inner.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.search_size_min_var = tk.StringVar()
        ttk.Entry(size_inner, textvariable=self.search_size_min_var, width=15).pack(side=tk.LEFT)
        ttk.Label(size_inner, text=" - ").pack(side=tk.LEFT)
        self.search_size_max_var = tk.StringVar()
        ttk.Entry(size_inner, textvariable=self.search_size_max_var, width=15).pack(side=tk.LEFT)
        ttk.Label(size_inner, text=t.get('size_examples'), foreground='gray').pack(side=tk.LEFT, padx=(5, 0))
        
        # Date range
        date_frame = ttk.Frame(criteria_frame)
        date_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(date_frame, text=t.get('date_range'), width=15).pack(side=tk.LEFT)
        
        date_inner = ttk.Frame(date_frame)
        date_inner.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.search_date_min_var = tk.StringVar()
        ttk.Entry(date_inner, textvariable=self.search_date_min_var, width=15).pack(side=tk.LEFT)
        ttk.Label(date_inner, text=" - ").pack(side=tk.LEFT)
        self.search_date_max_var = tk.StringVar()
        ttk.Entry(date_inner, textvariable=self.search_date_max_var, width=15).pack(side=tk.LEFT)
        ttk.Label(date_inner, text=t.get('date_examples'), foreground='gray').pack(side=tk.LEFT, padx=(5, 0))
        
        # Search buttons
        search_btn_frame = ttk.Frame(criteria_frame)
        search_btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(search_btn_frame, text=t.get('search_button'), command=self.perform_search).pack(side=tk.LEFT)
        ttk.Button(search_btn_frame, text=t.get('clear_button'), command=self.clear_search_criteria).pack(side=tk.LEFT, padx=(10, 0))
        
        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text=t.get('search_results'), padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        # Results tree
        tree_frame = ttk.Frame(results_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = (t.get('size_col'), t.get('modified_col'), t.get('index_col'), t.get('path_col'))  # Added index_col
        self.search_tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings')
        self.search_tree.heading('#0', text=t.get('filename_col'))
        self.search_tree.heading(t.get('size_col'), text=t.get('size_col'))
        self.search_tree.heading(t.get('modified_col'), text=t.get('modified_col'))
        self.search_tree.heading(t.get('index_col'), text=t.get('index_col'))
        self.search_tree.heading(t.get('path_col'), text=t.get('path_col'))
        
        # Column widths
        self.search_tree.column('#0', width=200, minwidth=150)
        self.search_tree.column(t.get('size_col'), width=80, minwidth=60)
        self.search_tree.column(t.get('modified_col'), width=120, minwidth=100)
        self.search_tree.column(t.get('index_col'), width=150, minwidth=120)
        self.search_tree.column(t.get('path_col'), width=300, minwidth=200)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.search_tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.search_tree.xview)
        self.search_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.search_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind events
        self.search_tree.bind('<Double-Button-1>', self.on_search_double_click)
        self.search_tree.bind('<Button-3>', self.on_search_right_click)
        
        # Action buttons
        action_frame = ttk.Frame(results_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(action_frame, text=t.get('open_file'), command=self.open_search_file).pack(side=tk.LEFT)
        ttk.Button(action_frame, text=t.get('open_folder'), command=self.open_search_folder).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('copy_path'), command=self.copy_search_path).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('export_results'), command=self.export_search_results).pack(side=tk.LEFT, padx=(10, 0))
    
    def setup_manage_tab(self):
        """Setup the index management interface with active/inactive controls."""
        main_frame = ttk.Frame(self.manage_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Index list frame
        list_frame = ttk.LabelFrame(main_frame, text=t.get('available_indices'), padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Index tree with active column
        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('Active', 'Root Path', 'Files', 'Size', 'Created', 'Hash')
        self.index_tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings')
        self.index_tree.heading('#0', text='Index File')
        self.index_tree.heading('Active', text='Active')
        self.index_tree.heading('Root Path', text='Root Path')
        self.index_tree.heading('Files', text='Files')
        self.index_tree.heading('Size', text='Size')
        self.index_tree.heading('Created', text='Created')
        self.index_tree.heading('Hash', text='Hash')
        
        # Column widths
        self.index_tree.column('#0', width=180, minwidth=150)
        self.index_tree.column('Active', width=60, minwidth=50)
        self.index_tree.column('Root Path', width=280, minwidth=200)
        self.index_tree.column('Files', width=70, minwidth=60)
        self.index_tree.column('Size', width=80, minwidth=70)
        self.index_tree.column('Created', width=100, minwidth=90)
        self.index_tree.column('Hash', width=70, minwidth=60)
        
        # Scrollbars
        v_scrollbar2 = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.index_tree.yview)
        h_scrollbar2 = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.index_tree.xview)
        self.index_tree.configure(yscrollcommand=v_scrollbar2.set, xscrollcommand=h_scrollbar2.set)
        
        self.index_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar2.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind events
        self.index_tree.bind('<<TreeviewSelect>>', self.on_index_select)
        self.index_tree.bind('<Double-Button-1>', self.on_index_double_click)
        self.index_tree.bind('<Button-1>', self.on_index_tree_click)
        
        # Action buttons
        action_frame = ttk.Frame(list_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(action_frame, text=t.get('create_index'), command=self.create_new_index).pack(side=tk.LEFT)
        ttk.Button(action_frame, text=t.get('refresh_indices'), command=self.refresh_indices).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text="Browse Contents", command=self.browse_index_contents).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('delete_index'), command=self.delete_selected_index).pack(side=tk.LEFT, padx=(10, 0))
        
        # Toggle buttons
        toggle_frame = ttk.Frame(list_frame)
        toggle_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(toggle_frame, text="Activate All", command=self.activate_all_indices).pack(side=tk.LEFT)
        ttk.Button(toggle_frame, text="Deactivate All", command=self.deactivate_all_indices).pack(side=tk.LEFT, padx=(10, 0))
        
        # Index info frame
        info_frame = ttk.LabelFrame(main_frame, text=t.get('index_info'), padding=10)
        info_frame.pack(fill=tk.X)
        
        self.index_info_var = tk.StringVar()
        self.index_info_var.set("Select an index to view details")
        ttk.Label(info_frame, textvariable=self.index_info_var, justify=tk.LEFT).pack(anchor=tk.W, fill=tk.X)
        
    def setup_duplicates_tab(self):
        """Setup the duplicate detection interface with enhanced index management."""
        main_frame = ttk.Frame(self.duplicates_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title
        ttk.Label(main_frame, text=t.get('duplicates_tab'), 
                font=('TkDefaultFont', 16, 'bold')).pack(pady=(0, 20))
        
        # Source selection
        source_frame = ttk.LabelFrame(main_frame, text=t.get('source_folder'), padding=10)
        source_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.dup_source_var = tk.StringVar()
        source_entry = ttk.Entry(source_frame, textvariable=self.dup_source_var, width=50)
        source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(source_frame, text=t.get('browse_button'), 
                command=self.select_duplicate_source).pack(side=tk.RIGHT, padx=(10, 0))
        
        # Destination selection with index info
        dest_frame = ttk.LabelFrame(main_frame, text=t.get('destination_folders'), padding=10)
        dest_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Enhanced destination tree with index information
        tree_frame = ttk.Frame(dest_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('Index File', 'Last Updated', 'Update Index')
        self.dup_dest_tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings', height=6)
        self.dup_dest_tree.heading('#0', text='Destination Folder')
        self.dup_dest_tree.heading('Index File', text=t.get('index_info'))
        self.dup_dest_tree.heading('Last Updated', text=t.get('last_updated'))
        self.dup_dest_tree.heading('Update Index', text=t.get('update_index'))
        
        self.dup_dest_tree.column('#0', width=300, minwidth=250)
        self.dup_dest_tree.column('Index File', width=200, minwidth=150)
        self.dup_dest_tree.column('Last Updated', width=120, minwidth=100)
        self.dup_dest_tree.column('Update Index', width=100, minwidth=80)
        
        scrollbar_dup = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.dup_dest_tree.yview)
        self.dup_dest_tree.configure(yscrollcommand=scrollbar_dup.set)
        
        self.dup_dest_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_dup.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind events for update checkboxes
        self.dup_dest_tree.bind('<Button-1>', self.on_dup_tree_click)
        
        # Destination buttons
        dest_buttons = ttk.Frame(dest_frame)
        dest_buttons.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(dest_buttons, text=t.get('add_folder'), 
                command=self.add_dup_dest_folder_enhanced).pack(side=tk.LEFT)
        ttk.Button(dest_buttons, text=t.get('remove_selected'), 
                command=self.remove_dup_dest_folder_enhanced).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(dest_buttons, text=t.get('clear_all'), 
                command=self.clear_dup_dest_folders_enhanced).pack(side=tk.LEFT, padx=(10, 0))
        
        # Options frame
        options_frame = ttk.LabelFrame(main_frame, text=t.get('options'), padding=10)
        options_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Hash options
        hash_frame = ttk.Frame(options_frame)
        hash_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.dup_use_hash_var = tk.BooleanVar(value=True)
        hash_check = ttk.Checkbutton(hash_frame, text=t.get('use_hash'), 
                                    variable=self.dup_use_hash_var, command=self.on_dup_hash_toggle)
        hash_check.pack(side=tk.LEFT)
        
        self.dup_hash_algo_var = tk.StringVar(value=self.config.get('default_hash_algo', 'md5'))
        self.dup_hash_combo = ttk.Combobox(hash_frame, textvariable=self.dup_hash_algo_var, 
                                        values=["md5", "sha1", "sha256"], width=10, state="readonly")
        self.dup_hash_combo.pack(side=tk.LEFT, padx=(10, 0))
        
        # Index options
        index_frame = ttk.Frame(options_frame)
        index_frame.pack(fill=tk.X)
        
        self.dup_reuse_indices_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(index_frame, text=t.get('reuse_indices'), 
                    variable=self.dup_reuse_indices_var).pack(side=tk.LEFT)
        
        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        ttk.Button(button_frame, text=t.get('start_scan'),
                command=self.start_duplicate_scan).pack(side=tk.LEFT)
        ttk.Button(button_frame, text=t.get('clear_button'),
                command=self.clear_duplicate_form_enhanced).pack(side=tk.LEFT, padx=(10, 0))
    
    def setup_settings_tab(self):
        """Setup the settings interface."""
        main_frame = ttk.Frame(self.settings_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Language settings
        lang_frame = ttk.LabelFrame(main_frame, text=t.get('language'), padding=10)
        lang_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.language_var = tk.StringVar(value=self.config.get('language', 'en'))
        lang_combo = ttk.Combobox(lang_frame, textvariable=self.language_var, 
                                 values=['en', 'de'], width=10, state='readonly')
        lang_combo.pack(side=tk.LEFT)
        
        # Hash algorithm settings
        hash_frame = ttk.LabelFrame(main_frame, text=t.get('default_hash'), padding=10)
        hash_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.hash_var = tk.StringVar(value=self.config.get('default_hash_algo', 'md5'))
        hash_combo = ttk.Combobox(hash_frame, textvariable=self.hash_var,
                                 values=['md5', 'sha1', 'sha256'], width=10, state='readonly')
        hash_combo.pack(side=tk.LEFT)
        
        # Auto-load indices
        self.auto_load_var = tk.BooleanVar(value=self.config.get('auto_load_indices', True))
        ttk.Checkbutton(main_frame, text=t.get('auto_load_indices'), 
                       variable=self.auto_load_var).pack(anchor=tk.W, pady=(0, 10))
        
        # Index search locations
        locations_frame = ttk.LabelFrame(main_frame, text=t.get('index_locations'), padding=10)
        locations_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Locations list
        list_frame_settings = ttk.Frame(locations_frame)
        list_frame_settings.pack(fill=tk.BOTH, expand=True)
        
        self.locations_listbox = tk.Listbox(list_frame_settings, height=6)
        scrollbar_settings = ttk.Scrollbar(list_frame_settings, orient=tk.VERTICAL, command=self.locations_listbox.yview)
        self.locations_listbox.configure(yscrollcommand=scrollbar_settings.set)
        
        self.locations_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_settings.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.refresh_locations_list()
        
        locations_buttons = ttk.Frame(locations_frame)
        locations_buttons.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(locations_buttons, text=t.get('add_location'), 
                  command=self.add_search_location).pack(side=tk.LEFT)
        ttk.Button(locations_buttons, text=t.get('remove_location'), 
                  command=self.remove_search_location).pack(side=tk.LEFT, padx=(10, 0))
        
        # Apply settings button
        ttk.Button(main_frame, text=t.get('apply_settings'), 
                  command=self.apply_settings).pack(pady=(20, 0))
    
    def refresh_indices(self):
        """Refresh the list of available indices."""
        self.available_indices = self.index_discovery.discover_indices()
        self.populate_index_tree()
        self.update_status()
    
    def populate_index_tree(self):
        """Populate the index management tree with active states."""
        # Clear existing items
        for item in self.index_tree.get_children():
            self.index_tree.delete(item)
        
        for caf_path in self.available_indices:
            info = self.index_discovery.get_index_info(caf_path)
            if info:
                is_active = self.config.is_index_active(str(caf_path))
                active_text = "☑" if is_active else "☐"
                
                self.index_tree.insert('', 'end',
                                    text=caf_path.name,
                                    values=(
                                        active_text,
                                        str(info.root_path),
                                        f"{info.file_count:,}",
                                        format_size(info.total_size),
                                        info.created_date.strftime('%Y-%m-%d'),
                                        info.hash_method
                                    ),
                                    tags=(str(caf_path), 'active' if is_active else 'inactive'))
                
    def add_dup_dest_folder_enhanced(self):
        """Add destination folder with index detection."""
        folder = filedialog.askdirectory(title="Select Destination Folder")
        if folder:
            folder_path = Path(folder)
            
            # Check if folder already exists
            for item in self.dup_dest_tree.get_children():
                if self.dup_dest_tree.item(item, 'text') == str(folder_path):
                    messagebox.showwarning("Warning", t.get('duplicate_folder'))
                    return
            
            # Find related indices
            related_indices = self.find_indices_for_folder(folder_path)
            
            if related_indices:
                # Multiple indices case
                if len(related_indices) > 1:
                    selected_index = self.show_index_selection_dialog(folder_path, related_indices)
                    if not selected_index:
                        return
                    index_info = selected_index
                else:
                    index_info = related_indices[0]
                
                # Add to tree with index information
                last_updated = index_info['created_date'].strftime('%Y-%m-%d')
                item_id = self.dup_dest_tree.insert('', 'end',
                                                text=str(folder_path),
                                                values=(
                                                    index_info['path'].name,
                                                    last_updated,
                                                    "☐"
                                                ),
                                                tags=('dest_folder', str(folder_path)))
            else:
                # No index found
                item_id = self.dup_dest_tree.insert('', 'end',
                                                text=str(folder_path),
                                                values=(
                                                    "No index found",
                                                    "-",
                                                    "☑"  # Will need to create index
                                                ),
                                                tags=('dest_folder', str(folder_path)))
            
            self.dup_dest_paths.append(folder_path)

    def find_indices_for_folder(self, folder_path: Path) -> List[Dict]:
        """Find all active indices that contain the given folder."""
        related_indices = []
        active_indices = self.get_active_indices_only()
        
        for caf_path in active_indices:
            info = self.index_discovery.get_index_info(caf_path)
            if info:
                # Check if folder is within the indexed root or if root is within folder
                try:
                    if (folder_path.resolve().is_relative_to(Path(info.root_path).resolve()) or 
                    Path(info.root_path).resolve().is_relative_to(folder_path.resolve())):
                        related_indices.append({
                            'path': caf_path,
                            'root_path': info.root_path,
                            'created_date': info.created_date,
                            'hash_method': info.hash_method
                        })
                except (ValueError, OSError):
                    continue
        
        return related_indices

    def show_index_selection_dialog(self, folder_path: Path, related_indices: List[Dict]) -> Optional[Dict]:
        """Show dialog to select which index to use when multiple are found."""
        dialog = tk.Toplevel(self.root)
        dialog.title(t.get('multiple_indices_found'))
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        selected_index = None
        
        ttk.Label(dialog, text=f"{t.get('select_indices_to_update')}\n{folder_path}",
                font=('TkDefaultFont', 10, 'bold')).pack(pady=10)
        
        # List of indices
        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        var = tk.StringVar()
        for i, index_info in enumerate(related_indices):
            text = f"{index_info['path'].name} -> {index_info['root_path']} ({index_info['created_date'].strftime('%Y-%m-%d')})"
            ttk.Radiobutton(frame, text=text, variable=var, value=str(i)).pack(anchor=tk.W, pady=2)
        
        def on_ok():
            nonlocal selected_index
            try:
                idx = int(var.get())
                selected_index = related_indices[idx]
                dialog.destroy()
            except (ValueError, IndexError):
                messagebox.showerror("Error", "Please select an index.")
        
        def on_cancel():
            dialog.destroy()
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)
        
        dialog.wait_window()
        return selected_index

    def on_dup_tree_click(self, event):
        """Handle clicks on the destination tree to toggle update checkboxes."""
        item = self.dup_dest_tree.identify_row(event.y)
        column = self.dup_dest_tree.identify_column(event.x)
        
        if item and column == '#3':  # Update Index column
            current_values = list(self.dup_dest_tree.item(item, 'values'))
            if len(current_values) >= 3:
                # Toggle checkbox
                current_values[2] = "☑" if current_values[2] == "☐" else "☐"
                self.dup_dest_tree.item(item, values=current_values)
                
                # If this index covers multiple folders, update them all
                self.sync_related_index_updates(item)

    def sync_related_index_updates(self, changed_item):
        """Sync update status for folders that share the same index."""
        changed_values = self.dup_dest_tree.item(changed_item, 'values')
        if len(changed_values) < 2:
            return
            
        changed_index_name = changed_values[0]
        changed_update_status = changed_values[2]
        
        # Find other items with the same index
        for item in self.dup_dest_tree.get_children():
            if item != changed_item:
                values = list(self.dup_dest_tree.item(item, 'values'))
                if len(values) >= 3 and values[0] == changed_index_name:
                    values[2] = changed_update_status
                    self.dup_dest_tree.item(item, values=values)

    def remove_dup_dest_folder_enhanced(self):
        """Remove selected destination folder from enhanced tree."""
        selection = self.dup_dest_tree.selection()
        if selection:
            for item in selection:
                folder_path = Path(self.dup_dest_tree.item(item, 'text'))
                self.dup_dest_tree.delete(item)
                if folder_path in self.dup_dest_paths:
                    self.dup_dest_paths.remove(folder_path)

    def clear_dup_dest_folders_enhanced(self):
        """Clear all destination folders from enhanced tree."""
        for item in self.dup_dest_tree.get_children():
            self.dup_dest_tree.delete(item)
        self.dup_dest_paths.clear()

    def clear_duplicate_form_enhanced(self):
        """Clear the enhanced duplicate detection form."""
        self.dup_source_var.set("")
        self.dup_source_path = None
        self.clear_dup_dest_folders_enhanced()
    
    def refresh_locations_list(self):
        """Refresh the search locations list."""
        self.locations_listbox.delete(0, tk.END)
        for location in self.config.get('index_search_locations', []):
            self.locations_listbox.insert(tk.END, location)

    def perform_search(self):
        """Perform file search across only active indices with progress window."""
        try:
            criteria = self.parse_search_criteria()
            self.search_tree.delete(*self.search_tree.get_children())
            self.search_results.clear()
            
            # Get only active indices
            active_indices = self.get_active_indices_only()
            if not active_indices:
                messagebox.showwarning("No Active Indices", "No active indices found. Please activate at least one index.")
                return
            
            # Use progress window for better user experience
            self.run_search_with_progress(criteria, active_indices)
            
        except Exception as e:
            messagebox.showerror(t.get('error'), t.get('search_error', str(e)))
            self.status_var.set("Search failed")
    
    def perform_search_old(self):
        """Perform file search across only active indices with improved display."""
        try:
            criteria = self.parse_search_criteria()
            self.search_tree.delete(*self.search_tree.get_children())
            self.search_results.clear()
            
            # Get only active indices
            active_indices = self.get_active_indices_only()
            if not active_indices:
                messagebox.showwarning("No Active Indices", "No active indices found. Please activate at least one index.")
                return
            
            self.status_var.set(t.get('searching_status'))
            self.root.update_idletasks()
            
            total_results = 0
            for caf_path in active_indices:
                if caf_path.exists():
                    # Load index and search
                    file_index = self.load_index_for_search(caf_path)
                    if file_index:
                        results = search_files_in_index(file_index, criteria)
                        total_results += len(results)
                        
                        # Extract clean index name
                        try:
                            # Get the filename without .caf extension
                            index_name = caf_path.name
                            if index_name.lower().endswith('.caf'):
                                index_name = index_name[:-4]  # Remove .caf extension
                            
                            # Clean up the name further if needed
                            if '_index' in index_name:
                                index_name = index_name.replace('_index', '')
                                
                        except (AttributeError, TypeError):
                            index_name = "Unknown"
                        
                        # Add results with clean index name
                        for result in results:
                            self.add_search_result_to_tree(result, index_name)
            
            self.status_var.set(t.get('found_status', total_results))
            
        except Exception as e:
            messagebox.showerror(t.get('error'), t.get('search_error', str(e)))
            self.status_var.set("Search failed")

    
    def parse_search_criteria(self) -> SearchCriteria:
        """Parse search criteria from UI."""
        # Name pattern
        name_pattern = self.search_name_var.get().strip()
        if not name_pattern:
            name_pattern = None
        
        # Size range  
        size_min = None
        size_max = None
        try:
            if self.search_size_min_var.get().strip():
                size_min = parse_size(self.search_size_min_var.get().strip())
            if self.search_size_max_var.get().strip():
                size_max = parse_size(self.search_size_max_var.get().strip()) 
        except ValueError as e:
            raise ValueError(t.get('invalid_size', e))
        
        # Date range
        date_min = None
        date_max = None
        try:
            if self.search_date_min_var.get().strip():
                date_min = parse_date(self.search_date_min_var.get().strip()) 
            if self.search_date_max_var.get().strip():
                date_max = parse_date(self.search_date_max_var.get().strip())  
        except ValueError as e:
            raise ValueError(t.get('invalid_date', e))
        
        return SearchCriteria(
            name_pattern=name_pattern,
            size_min=size_min,
            size_max=size_max,
            date_min=date_min,
            date_max=date_max
        )
    
    def load_index_for_search(self, caf_path: Path):
        """Load an index file for searching with verbose logging."""
        print(f"[LOAD] Loading index: {caf_path}")
        
        # Determine hash algorithm from filename
        name = caf_path.stem.lower()
        use_hash = True
        if '_sha256' in name:
            hash_algo = 'sha256'
        elif '_sha1' in name:
            hash_algo = 'sha1'
        else:
            hash_algo = 'md5'
        
        print(f"[LOAD] Using hash algorithm: {hash_algo}")
        
        file_index = FileIndex.load_from_caf(caf_path, use_hash, hash_algo)
        
        if file_index:
            print(f"[LOAD] Successfully loaded index with {file_index.total_files} files")
            print(f"[LOAD] Size index has {len(file_index.size_index)} buckets")
            
            # Log some sample data
            sample_count = 0
            for size, entries in file_index.size_index.items():
                if sample_count < 3:  # Show first 3 size buckets
                    print(f"[LOAD] Size bucket {size}: {len(entries)} files")
                    if entries and sample_count == 0:  # Show one file from first bucket
                        sample_file = entries[0]
                        print(f"[LOAD] Sample file: {sample_file.path.name} ({sample_file.size} bytes)")
                    sample_count += 1
        else:
            print(f"[LOAD] Failed to load index: {caf_path}")
        
        return file_index
    
    def add_search_result_to_tree(self, result: SearchResult, index_name: str = ""):
        """Add search result to tree with FULL ABSOLUTE path display."""
        self.search_results.append(result)
        filename = result.path.name
        size_str = format_size(result.size)
        modified_str = dt.fromtimestamp(result.mtime).strftime('%Y-%m-%d %H:%M')
        
        # Show the COMPLETE absolute path - no shortening!
        display_path = str(result.path.parent)
        
        # Ensure we have a valid index name
        if not index_name or index_name.strip() == "":
            index_name = "Unknown"
        
        self.search_tree.insert('', 'end',
                            text=filename,
                            values=(size_str, modified_str, index_name, display_path),
                            tags=(len(self.search_results) - 1,))
    
    def clear_search_criteria(self):
        """Clear all search criteria."""
        self.search_name_var.set("")
        self.search_size_min_var.set("")
        self.search_size_max_var.set("")
        self.search_date_min_var.set("")
        self.search_date_max_var.set("")
    
    def get_selected_search_result(self) -> Optional[SearchResult]:
        """Get the currently selected search result"""
        selection = self.search_tree.selection()
        if not selection:
            return None
            
        item = selection[0]
        tags = self.search_tree.item(item, 'tags')
        if tags:
            try:
                result_index = int(tags[0])
                return self.search_results[result_index]
            except (ValueError, IndexError):
                return None
        return None
    
    def on_search_double_click(self, event):
        """Handle double-click on search result."""
        result = self.get_selected_search_result()
        if result:
            try:
                # Let the robust open_file_or_folder handle existence and platform checks
                open_file_or_folder(result.path, open_folder=False)
            except (FileNotFoundError, FileOperationError) as e:
                messagebox.showerror(t.get('error'), str(e))
    
    def on_search_right_click(self, event):
        """Handle right-click on search result."""
        result = self.get_selected_search_result()
        if result:
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label=t.get('open_file'), command=self.open_search_file)
            menu.add_command(label=t.get('open_folder'), command=self.open_search_folder)
            menu.add_command(label=t.get('copy_path'), command=self.copy_search_path)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
    
    def open_search_file(self):
        """Open selected search result file with error handling."""
        result = self.get_selected_search_result()
        if result:
            try:
                open_file_or_folder(result.path, open_folder=False)
            except FileNotFoundError:
                messagebox.showerror(t.get('error'), t.get('file_not_found', result.path))
            except FileOperationError as e:
                messagebox.showerror(t.get('error'), str(e))
    
    def open_search_folder(self):
        """Open folder containing selected search result with error handling."""
        result = self.get_selected_search_result()
        if result:
            try:
                open_file_or_folder(result.path, open_folder=True)
            except FileNotFoundError:
                messagebox.showerror(t.get('error'), t.get('file_not_found', result.path))
            except FileOperationError as e:
                messagebox.showerror(t.get('error'), str(e))
    
    def copy_search_path(self):
        """Copy selected search result path to clipboard."""
        result = self.get_selected_search_result()
        if result:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(result.path))
            self.status_var.set(t.get('path_copied', result.path.name))
            self.root.after(2000, self.update_status)
    
    def export_search_results(self):
        """Export search results to CSV with index information."""
        if not self.search_results:
            messagebox.showwarning("Warning", t.get('no_results'))
            return
        
        filename = filedialog.asksaveasfilename(
            title="Export Search Results",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("Filename,Size,Size (bytes),Modified,Index,Full Path\n")
                    for i, result in enumerate(self.search_results):
                        # Get the tree item to extract index information
                        tree_children = list(self.search_tree.get_children())
                        if i < len(tree_children):
                            item = tree_children[i]
                            values = self.search_tree.item(item, 'values')
                            index_name = values[2] if len(values) > 2 else ""
                        else:
                            index_name = ""
                        
                        filename_clean = result.path.name.replace('"', '""')
                        path_clean = str(result.path).replace('"', '""')
                        size_str = format_size(result.size)
                        modified_str = dt.fromtimestamp(result.mtime).strftime('%Y-%m-%d %H:%M:%S')
                        
                        f.write(f'"{filename_clean}","{size_str}",{result.size},"{modified_str}","{index_name}","{path_clean}"\n')
                
                messagebox.showinfo("Success", t.get('export_complete', filename))
                
            except Exception as e:
                messagebox.showerror(t.get('error'), t.get('export_error', e))
    
    def on_index_select(self, event):
        """Handle index selection in management tab."""
        selection = self.index_tree.selection()
        if selection:
            item = selection[0]
            caf_path_str = self.index_tree.item(item, 'tags')[0]
            caf_path = Path(caf_path_str)
            
            info = self.index_discovery.get_index_info(caf_path)
            if info:
                info_text = f"{t.get('root_path')} {info.root_path}\n"
                info_text += f"{t.get('file_count')} {info.file_count:,}\n"
                info_text += f"{t.get('total_size')} {format_size(info.total_size)}\n"
                info_text += f"{t.get('created_date')} {info.created_date.strftime('%Y-%m-%d %H:%M')}\n"
                info_text += f"{t.get('hash_method')} {info.hash_method}"
                self.index_info_var.set(info_text)
        else:
            self.index_info_var.set("Select an index to view details")
    
    def on_index_double_click(self, event):
        """Handle double-click on index - open in file manager with error handling."""
        selection = self.index_tree.selection()
        if selection:
            item = selection[0]
            caf_path_str = self.index_tree.item(item, 'tags')[0]
            caf_path = Path(caf_path_str)
            try:
                open_file_or_folder(caf_path, open_folder=True)
            except FileNotFoundError:
                messagebox.showerror(t.get('error'), t.get('file_not_found', caf_path))
            except FileOperationError as e:
                messagebox.showerror(t.get('error'), str(e))
    
    def create_new_index(self):
        """Create a new index file."""
        folder = filedialog.askdirectory(title="Select Folder to Index")
        if folder:
            # Show options dialog
            dialog = IndexCreationDialog(self.root, Path(folder), self.config)
            dialog.run()
            if dialog.result:
                # Refresh indices after creation
                self.refresh_indices()
    
    def delete_selected_index(self):
        """Delete selected index file."""
        selection = self.index_tree.selection()
        if selection:
            item = selection[0]
            caf_path_str = self.index_tree.item(item, 'tags')[0]
            
            if messagebox.askyesno("Confirm", f"Delete index file?\n{Path(caf_path_str).name}"):
                try:
                    Path(caf_path_str).unlink()
                    self.refresh_indices()
                    messagebox.showinfo("Success", "Index file deleted successfully.")
                except Exception as e:
                    messagebox.showerror(t.get('error'), str(e))
    
    # --- Duplicate Detection Methods ---
    
    def select_duplicate_source(self):
        """Select source folder for duplicate detection."""
        folder = filedialog.askdirectory(title=t.get('source_folder'))
        if folder:
            self.dup_source_var.set(folder)
            self.dup_source_path = Path(folder)
    
    def add_dup_dest_folder(self):
        """Add destination folder for duplicate detection."""
        folder = filedialog.askdirectory(title="Select Destination Folder")
        if folder:
            folder_path = Path(folder)
            if folder_path not in self.dup_dest_paths:
                self.dup_dest_paths.append(folder_path)
                self.dup_dest_listbox.insert(tk.END, str(folder_path))
            else:
                messagebox.showwarning("Warning", t.get('duplicate_folder'))
    
    def remove_dup_dest_folder(self):
        """Remove selected destination folder."""
        selection = self.dup_dest_listbox.curselection()
        if selection:
            index = selection[0]
            self.dup_dest_listbox.delete(index)
            del self.dup_dest_paths[index]
    
    def clear_dup_dest_folders(self):
        """Clear all destination folders."""
        self.dup_dest_listbox.delete(0, tk.END)
        self.dup_dest_paths.clear()
    
    def on_dup_hash_toggle(self):
        """Enable/disable hash algorithm selection for duplicates."""
        if self.dup_use_hash_var.get():
            self.dup_hash_combo.config(state="readonly")
        else:
            self.dup_hash_combo.config(state="disabled")
    
    def clear_duplicate_form(self):
        """Clear the duplicate detection form."""
        self.dup_source_var.set("")
        self.dup_source_path = None
        self.clear_dup_dest_folders()
    
    def start_duplicate_scan(self):
        """Start duplicate scan with enhanced features."""
        # Validate input
        if not self.dup_source_path:
            messagebox.showerror(t.get('error'), t.get('select_source'))
            return
        
        if not self.dup_dest_paths:
            messagebox.showerror(t.get('error'), t.get('select_dest'))
            return
        
        # Validate paths
        if not self.dup_source_path.exists():
            messagebox.showerror(t.get('error'), f"Source folder does not exist: {self.dup_source_path}")
            return
        
        invalid_paths = [p for p in self.dup_dest_paths if not p.exists()]
        if invalid_paths:
            messagebox.showerror(t.get('error'), f"Invalid destination folders:\n" + 
                            "\n".join(str(p) for p in invalid_paths))
            return
        
        # Determine which indices need updating (if using enhanced tree)
        indices_to_recreate = []
        if hasattr(self, 'dup_dest_tree'):  # Enhanced version
            for item in self.dup_dest_tree.get_children():
                values = self.dup_dest_tree.item(item, 'values')
                if len(values) >= 3 and values[2] == "☑":
                    folder_path = Path(self.dup_dest_tree.item(item, 'text'))
                    indices_to_recreate.append(folder_path)
        
        # Create configuration
        config = ScanConfig(
            source_path=self.dup_source_path,
            dest_paths=self.dup_dest_paths,
            use_hash=self.dup_use_hash_var.get(),
            hash_algo=self.dup_hash_algo_var.get(),
            reuse_indices=self.dup_reuse_indices_var.get(),
            recreate_indices=len(indices_to_recreate) > 0 if hasattr(self, 'dup_dest_tree') else self.dup_recreate_indices_var.get()
        )
        
        # Store which specific indices to recreate (for enhanced version)
        if indices_to_recreate:
            config.selective_recreation_paths = indices_to_recreate
        
        # Run scan with enhanced features if available, otherwise basic
        if hasattr(self, 'dup_dest_tree'):
            duplicates = run_scan_with_progress_enhanced(config, self.root, t.get)
        else:
            duplicates = run_scan_with_progress(config, self.root, t.get)
        
        if not duplicates:
            if messagebox.askyesno("No Duplicates", t.get('no_duplicates')):
                return
            else:
                return
        
        # Show results
        method = f"{config.hash_algo.upper()} hash + size" if config.use_hash else "filename + size"
        if config.reuse_indices:
            method += " (with CAF indices)"
        
        results_window = DuplicateResultsWindow(self, duplicates, method)
        results_window.root.wait_window()
        
        # Check if user wants new scan
        if hasattr(results_window, 'action') and results_window.action == 'new_scan':
            if hasattr(self, 'clear_duplicate_form_enhanced'):
                self.clear_duplicate_form_enhanced()
            else:
                self.clear_duplicate_form()
    
    # --- Settings Methods ---
    
    def add_search_location(self):
        """Add new search location."""
        folder = filedialog.askdirectory(title=t.get('add_location'))
        if folder:
            locations = self.config.get('index_search_locations', [])
            if folder not in locations:
                locations.append(folder)
                self.config.set('index_search_locations', locations)
                self.refresh_locations_list()
    
    def remove_search_location(self):
        """Remove selected search location."""
        selection = self.locations_listbox.curselection()
        if selection:
            index = selection[0]
            locations = self.config.get('index_search_locations', [])
            if 0 <= index < len(locations):
                locations.pop(index)
                self.config.set('index_search_locations', locations)
                self.refresh_locations_list()
    
    def apply_settings(self):
        """Apply changed settings."""
        # Save language setting
        old_lang = self.config.get('language', 'en')
        new_lang = self.language_var.get()
        self.config.set('language', new_lang)
        
        # Save other settings
        self.config.set('default_hash_algo', self.hash_var.get())
        self.config.set('auto_load_indices', self.auto_load_var.get())
        
        # Save configuration
        self.config.save_config()
        
        # If language changed, show restart message
        if old_lang != new_lang:
            messagebox.showinfo("Language Changed", 
                              "Please restart the application to apply language changes.")
        else:
            messagebox.showinfo("Settings", "Settings applied successfully.")
        
        # Refresh indices if auto-load setting changed
        if self.config.get('auto_load_indices', True):
            self.refresh_indices()
    
    def update_status(self):
        """Update status bar."""
        count = len(self.available_indices)
        self.status_var.set(t.get('ready_status', count))
    
    def on_closing(self):
        """Handle application closing."""
        # Save window geometry
        self.config.set('window_geometry', self.root.geometry())
        self.config.save_config()
        self.root.destroy()
    
    def run_search_with_progress(self, criteria: SearchCriteria, active_indices: List[Path]):
        """Run search with enhanced progress window and error recovery."""
        
        from threading import Thread
        import queue
        
        progress_window = ProgressWindow(self.root, "Searching Files")
        search_results = []
        
        # Thread-safe communication queue
        progress_queue = queue.Queue()
        
        def update_progress_from_queue():
            """Safely updates GUI from main thread by checking the queue"""
            try:
                while True:
                    message_type, operation, details, data = progress_queue.get_nowait()
                    if message_type == "progress":
                        progress_window.update_operation(operation)
                        progress_window.update_details(details)
                    elif message_type == "result":
                        # Add search result to tree with index name
                        result, index_name = data
                        self.add_search_result_to_tree(result, index_name)
                    elif message_type == "error":
                        messagebox.showerror(t.get('error'), t.get('search_error', details))
                    elif message_type == "complete":
                        total_results = data
                        self.status_var.set(t.get('found_status', total_results))
                        progress_window.root.quit()
                        return
            except queue.Empty:
                pass
            
            # Reschedule this check if thread is still running
            if search_thread_obj.is_alive():
                progress_window.root.after(50, update_progress_from_queue)  # More frequent updates
        
        def progress_callback(operation, details):
            """Thread-safe progress callback"""
            progress_queue.put(("progress", operation, details, None))
        
        def result_callback(result, index_name):
            """Thread-safe result callback with index name"""
            progress_queue.put(("result", "", "", (result, index_name)))
        
        def search_thread():
            """Background search thread with better error handling"""
            try:
                total_results = 0
                
                progress_callback("Initializing search", f"Preparing to search {len(active_indices)} active indices")
                
                for i, caf_path in enumerate(active_indices):
                    if progress_window.cancelled.is_set():
                        break
                        
                    if not caf_path.exists():
                        progress_callback(f"Skipping index {i+1}/{len(active_indices)}", f"File not found: {caf_path.name}")
                        continue
                    
                    # Extract index name
                    try:
                        index_name = caf_path.name
                        if index_name.lower().endswith('.caf'):
                            index_name = index_name[:-4]
                        if '_index' in index_name:
                            index_name = index_name.replace('_index', '')
                    except:
                        index_name = "Unknown"
                    
                    progress_callback(f"Loading index {i+1}/{len(active_indices)}", f"Reading: {caf_path.name}")
                    
                    # Load index with timeout protection
                    file_index = self.load_index_for_search(caf_path)
                    if not file_index:
                        progress_callback(f"Skipping index {i+1}/{len(active_indices)}", f"Failed to load: {caf_path.name}")
                        continue
                    
                    progress_callback(f"Searching index {i+1}/{len(active_indices)}", f"Loaded: {caf_path.name} ({file_index.total_files:,} files)")
                    
                    # Search in this index with progress
                    results = self.search_files_in_index_with_progress(
                        file_index, criteria, progress_callback, result_callback, 
                        progress_window.cancelled, index_name
                    )
                    total_results += len(results)
                    
                    if progress_window.cancelled.is_set():
                        break
                
                # Complete
                progress_queue.put(("complete", "", "", total_results))
                
            except Exception as e:
                progress_queue.put(("error", "Error", str(e), None))
        
        # Start search in background thread
        search_thread_obj = Thread(target=search_thread)
        search_thread_obj.daemon = True
        search_thread_obj.start()
        
        # Start queue polling from main thread with higher frequency
        progress_window.root.after(50, update_progress_from_queue)
        
        # Run progress GUI
        progress_window.root.mainloop()
        progress_window.root.destroy()
        
        # Wait for thread to complete
        search_thread_obj.join(timeout=1.0)

    def search_files_in_index_with_progress(self, file_index, criteria, progress_callback, result_callback, cancel_event, index_name):
        """Search files in an index with optimized progress reporting."""
        results = []
        
        # Compile regex pattern if provided
        name_regex = None
        if criteria.name_pattern:
            try:
                name_regex = re.compile(criteria.name_pattern, re.IGNORECASE)
            except re.error as e:
                raise ValueError(t.get('invalid_regex', e))
        
        # Pre-filter size buckets for better performance
        relevant_sizes = []
        total_entries = 0
        
        for size in file_index.size_index.keys():
            # Size filtering at bucket level
            if criteria.size_min is not None and size < criteria.size_min:
                continue
            if criteria.size_max is not None and size > criteria.size_max:
                continue
            relevant_sizes.append(size)
            total_entries += len(file_index.size_index[size])
        
        if total_entries == 0:
            progress_callback("Search complete", f"No files match size criteria in {index_name}")
            return results
        
        progress_callback("Searching files", f"Scanning {total_entries:,} relevant files in {index_name}")
        
        processed = 0
        last_progress_update = 0
        
        # Search through relevant size buckets only
        for size in relevant_sizes:
            if cancel_event and cancel_event.is_set():
                break
                
            entries = file_index.size_index[size]
            
            for entry in entries:
                if cancel_event and cancel_event.is_set():
                    break
                    
                processed += 1
                
                # More frequent progress updates (every 500 files or 2% progress)
                progress_threshold = min(500, max(100, total_entries // 50))
                if processed - last_progress_update >= progress_threshold:
                    progress_percentage = (processed / total_entries) * 100
                    progress_callback(f"Searching {index_name}", 
                                f"Processed {processed:,}/{total_entries:,} files ({progress_percentage:.1f}%) - {len(results)} matches")
                    last_progress_update = processed
                
                # Name filtering
                if name_regex and not name_regex.search(entry.path.name):
                    continue
                
                # Date filtering  
                if criteria.date_min or criteria.date_max:
                    file_mtime = dt.fromtimestamp(entry.mtime)
                    
                    if criteria.date_min and file_mtime < criteria.date_min:
                        continue
                    if criteria.date_max and file_mtime > criteria.date_max:
                        continue
                
                # File passed all criteria
                result = SearchResult(
                    path=entry.path,
                    size=entry.size,
                    mtime=entry.mtime,
                    hash=entry.hash
                )
                results.append(result)
                result_callback(result, index_name)
        
        # Final progress update
        if not cancel_event or not cancel_event.is_set():
            progress_callback(f"Completed {index_name}", f"Found {len(results)} matches out of {processed:,} files scanned")
        
        return results
    
    def run(self):
        """Run the application."""
        self.root.mainloop()