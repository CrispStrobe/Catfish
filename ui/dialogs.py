# ui/dialogs.py

"""Various dialog windows."""

import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import messagebox, ttk

from core.catalog_creation import create_catalog
from core.config import Config


def _create_catalog_worker(folder, output, use_hash, hash_algo, cancel_event, messages):
    """Worker messages contain plain data; every Tk call stays on the UI thread."""
    try:
        create_catalog(
            folder,
            output,
            use_hash,
            hash_algo,
            progress_callback=lambda text: messages.put(("progress", text)),
            cancel_event=cancel_event,
        )
        messages.put(("success", None))
    except InterruptedError:
        messages.put(("cancelled", None))
    except Exception as error:
        messages.put(("error", str(error)))


class IndexCreationDialog:
    """Dialog for creating new index files."""

    def __init__(self, parent, folder_path: Path, config: Config):
        self.parent = parent
        self.folder_path = folder_path
        self.config = config
        self.result = False
        self.cancel_event = Event()
        self._messages = Queue()
        self._running = False
        self._closed = False
        self._poll_id = None
        self._active_output = None

        self.root = tk.Toplevel(parent)
        self.root.title("Create New Index")
        self.root.geometry("520x440")
        self.root.minsize(420, 400)
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)

        # Make modal
        self.root.transient(parent)
        self.root.grab_set()

        self.setup_ui()

    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Folder info
        ttk.Label(main_frame, text="Create index for:", font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(main_frame, text=str(self.folder_path), foreground="blue").pack(anchor=tk.W, pady=(0, 20))

        # Hash options
        hash_frame = ttk.LabelFrame(main_frame, text="Hash Algorithm", padding=10)
        hash_frame.pack(fill=tk.X, pady=(0, 10))

        self.use_hash_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            hash_frame, text="Calculate file hashes", variable=self.use_hash_var, command=self.on_hash_toggle
        ).pack(anchor=tk.W)

        self.hash_algo_var = tk.StringVar(value=self.config.get("default_hash_algo", "md5"))
        self.hash_combo = ttk.Combobox(
            hash_frame, textvariable=self.hash_algo_var, values=["md5", "sha1", "sha256"], width=10, state="readonly"
        )
        self.hash_combo.pack(anchor=tk.W, pady=(5, 0))
        ttk.Label(
            hash_frame,
            text="CAF stores names, sizes and dates. File hashes are calculated for this scan only.",
            wraplength=430,
        ).pack(anchor=tk.W, pady=(6, 0))

        # Output file
        output_frame = ttk.LabelFrame(main_frame, text="Output File", padding=10)
        output_frame.pack(fill=tk.X, pady=(0, 10))

        self.output_var = tk.StringVar()
        self.update_output_filename()

        ttk.Entry(output_frame, textvariable=self.output_var, width=50).pack(fill=tk.X)

        # Progress
        self.progress_var = tk.StringVar(value="Ready to create index")
        ttk.Label(main_frame, textvariable=self.progress_var).pack(anchor=tk.W, pady=(10, 0))

        self.progress = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=(5, 20))

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        self.create_button = ttk.Button(button_frame, text="Create Index", command=self.create_index)
        self.create_button.pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)

    def on_hash_toggle(self):
        """Handle hash toggle."""
        if self.use_hash_var.get():
            self.hash_combo.config(state="readonly")
        else:
            self.hash_combo.config(state="disabled")
        self.update_output_filename()

    def update_output_filename(self):
        """Update output filename based on settings."""
        hash_suffix = f"_{self.hash_algo_var.get()}" if self.use_hash_var.get() else ""

        filename = f"{self.folder_path.name}_index{hash_suffix}.caf"
        output_path = self.folder_path.parent / filename
        self.output_var.set(str(output_path))

    def create_index(self):
        """Capture options on the UI thread and start one cancellable scan."""
        if self._running or self._closed:
            return
        output = self.output_var.get().strip()
        if not output:
            self.creation_error("Choose an output filename.")
            return
        output_path = Path(output)
        if output_path.is_dir():
            self.creation_error("The output path is a folder; choose a .caf filename.")
            return
        if output_path.exists() and not messagebox.askyesno(
            "File Exists", f"Index file already exists:\n{output_path.name}\n\nOverwrite?", parent=self.root
        ):
            return

        # Tk variables may only be read on this thread. A worker receives plain
        # immutable settings, its own cancellation event, and a message queue.
        use_hash = self.use_hash_var.get()
        hash_algo = self.hash_algo_var.get()
        self.cancel_event = Event()
        self._messages = Queue()
        self._active_output = output_path
        self._running = True
        self.create_button.configure(state="disabled")
        self.progress.start()
        self.progress_var.set("Scanning files…")
        Thread(
            target=_create_catalog_worker,
            args=(self.folder_path, output_path, use_hash, hash_algo, self.cancel_event, self._messages),
            daemon=True,
        ).start()
        self._poll_id = self.root.after(50, self._poll_creation)

    def _poll_creation(self):
        self._poll_id = None
        if self._closed:
            return
        while True:
            try:
                kind, message = self._messages.get_nowait()
            except Empty:
                break
            if kind == "progress":
                self.progress_var.set(message)
            elif kind == "success":
                self.creation_success()
                return
            elif kind == "error":
                self.creation_error(message)
                return
            elif kind == "cancelled":
                self._running = False
                self.progress.stop()
                self.progress_var.set("Creation cancelled")
                self.create_button.configure(state="normal")
                return
        if self._running:
            self._poll_id = self.root.after(50, self._poll_creation)

    def creation_success(self):
        """Handle successful index creation on the UI thread."""
        self._running = False
        self.progress.stop()
        self.progress_var.set("Index created successfully!")
        messagebox.showinfo("Success", f"Index file created:\n{self._active_output}", parent=self.root)
        self.result = True
        self._close()

    def creation_error(self, error_msg):
        """Keep the dialog open so its options can be corrected and retried."""
        self._running = False
        self.progress.stop()
        self.create_button.configure(state="normal")
        self.progress_var.set("Creation failed")
        messagebox.showerror("Error", f"Failed to create index:\n{error_msg}", parent=self.root)

    def _close(self):
        if self._closed:
            return
        self._closed = True
        if self._poll_id is not None:
            self.root.after_cancel(self._poll_id)
            self._poll_id = None
        self.root.destroy()

    def cancel(self):
        """Stop scanning/hashing/saving and ignore any late worker messages."""
        self.cancel_event.set()
        self._close()

    def run(self):
        """Run the dialog."""
        self.root.wait_window()
