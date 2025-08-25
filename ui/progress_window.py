# ui/progress_window.py

"""Progress window for long-running operations."""
import tkinter as tk
from tkinter import ttk
from threading import Event

from utils.i18n import translator as t

class ProgressWindow:
    """Progress window for long-running operations."""
    
    def __init__(self, parent=None, title="Progress"):
        self.root = tk.Toplevel(parent) if parent else tk.Tk()
        self.root.title(title)
        self.root.geometry("500x300")
        self.root.resizable(False, False)
        
        self.cancelled = Event()
        self.setup_ui()
        
        # Center on parent
        if parent:
            self.root.transient(parent)
            self.root.grab_set()
    
    def setup_ui(self):
        """Setup progress UI with enhanced display"""
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Current operation
        self.operation_var = tk.StringVar(value=t.get('initializing'))
        operation_label = ttk.Label(main_frame, textvariable=self.operation_var, 
                                font=('TkDefaultFont', 12, 'bold'))
        operation_label.pack(pady=(0, 15))
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate', length=400)
        self.progress.pack(fill=tk.X, pady=(0, 15))
        self.progress.start()
        
        # Details
        self.details_var = tk.StringVar(value="")
        details_label = ttk.Label(main_frame, textvariable=self.details_var, wraplength=450)
        details_label.pack(pady=(0, 20))
        
        # Statistics frame
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.stats_var = tk.StringVar(value="")
        stats_label = ttk.Label(stats_frame, textvariable=self.stats_var, foreground='gray')
        stats_label.pack()
        
        # Cancel button
        ttk.Button(main_frame, text=t.get('cancel_button'), 
                command=self.cancel).pack()
    
    def update_operation(self, text):
        """Update current operation text"""
        self.operation_var.set(text)
        self.root.update_idletasks()
    
    def update_details(self, text):
        """Update details text"""
        self.details_var.set(text)
        self.root.update_idletasks()

    def update_stats(self, text):
        """Update statistics text"""
        self.stats_var.set(text)
        self.root.update_idletasks()
    
    def cancel(self):
        """Cancel the operation"""
        self.cancelled.set()
        self.root.quit()
