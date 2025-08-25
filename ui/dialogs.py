# ui/dialogs.py

"""Various dialog windows."""
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from threading import Thread
from typing import Optional, List, Dict

from core.config import Config
from core.file_index import FileIndex
from utils.i18n import translator as t

class IndexCreationDialog:
    """Dialog for creating new index files."""
    
    def __init__(self, parent, folder_path: Path, config: Config):
        self.parent = parent
        self.folder_path = folder_path
        self.config = config
        self.result = False
        
        self.root = tk.Toplevel(parent)
        self.root.title("Create New Index")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # Make modal
        self.root.transient(parent)
        self.root.grab_set()
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Folder info
        ttk.Label(main_frame, text="Create index for:", font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W)
        ttk.Label(main_frame, text=str(self.folder_path), foreground='blue').pack(anchor=tk.W, pady=(0, 20))
        
        # Hash options
        hash_frame = ttk.LabelFrame(main_frame, text="Hash Algorithm", padding=10)
        hash_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.use_hash_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(hash_frame, text="Include file hashes", 
                       variable=self.use_hash_var, command=self.on_hash_toggle).pack(anchor=tk.W)
        
        self.hash_algo_var = tk.StringVar(value=self.config.get('default_hash_algo', 'md5'))
        self.hash_combo = ttk.Combobox(hash_frame, textvariable=self.hash_algo_var,
                                      values=['md5', 'sha1', 'sha256'], width=10, state='readonly')
        self.hash_combo.pack(anchor=tk.W, pady=(5, 0))
        
        # Output file
        output_frame = ttk.LabelFrame(main_frame, text="Output File", padding=10)
        output_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.output_var = tk.StringVar()
        self.update_output_filename()
        
        ttk.Entry(output_frame, textvariable=self.output_var, width=50).pack(fill=tk.X)
        
        # Progress
        self.progress_var = tk.StringVar(value="Ready to create index")
        ttk.Label(main_frame, textvariable=self.progress_var).pack(anchor=tk.W, pady=(10, 0))
        
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(5, 20))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Create Index", command=self.create_index).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
    
    def on_hash_toggle(self):
        """Handle hash toggle."""
        if self.use_hash_var.get():
            self.hash_combo.config(state='readonly')
        else:
            self.hash_combo.config(state='disabled')
        self.update_output_filename()
    
    def update_output_filename(self):
        """Update output filename based on settings."""
        if self.use_hash_var.get():
            hash_suffix = f"_{self.hash_algo_var.get()}"
        else:
            hash_suffix = ""
        
        filename = f"{self.folder_path.name}_index{hash_suffix}.caf"
        output_path = self.folder_path.parent / filename
        self.output_var.set(str(output_path))
    
    def create_index(self):
        """Create the index file."""
        output_path = Path(self.output_var.get())
        
        # Check if file already exists
        if output_path.exists():
            if not messagebox.askyesno("File Exists", 
                                     f"Index file already exists:\n{output_path.name}\n\nOverwrite?"):
                return
        
        # Start creation in thread
        self.progress.start()
        self.progress_var.set("Creating index...")
        
        def create_thread():
            try:
                index = FileIndex(self.folder_path, self.use_hash_var.get(), self.hash_algo_var.get())
                
                # Count total files first
                total_files = sum(1 for _ in self.folder_path.rglob('*') if _.is_file())
                processed = 0
                
                # Add files to index
                for file_path in self.folder_path.rglob('*'):
                    if file_path.is_file():
                        index.add_file(file_path)
                        processed += 1
                        
                        if processed % 100 == 0:
                            self.root.after(0, lambda: self.progress_var.set(
                                f"Processing files... {processed}/{total_files}"))
                
                # Save index
                self.root.after(0, lambda: self.progress_var.set("Saving index file..."))
                index.save_to_caf(output_path)
                
                # Success
                self.root.after(0, self.creation_success)
                
            except Exception as e:
                self.root.after(0, lambda: self.creation_error(str(e)))
        
        thread = Thread(target=create_thread)
        thread.daemon = True
        thread.start()
    
    def creation_success(self):
        """Handle successful index creation."""
        self.progress.stop()
        self.progress_var.set("Index created successfully!")
        messagebox.showinfo("Success", f"Index file created:\n{self.output_var.get()}")
        self.result = True
        self.root.destroy()
    
    def creation_error(self, error_msg):
        """Handle index creation error."""
        self.progress.stop()
        self.progress_var.set("Creation failed")
        messagebox.showerror("Error", f"Failed to create index:\n{error_msg}")
    
    def cancel(self):
        """Cancel the dialog."""
        self.root.destroy()
    
    def run(self):
        """Run the dialog."""
        self.root.wait_window()