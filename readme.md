# CatFiSh - Catalog File Search

A high-performance, cross-platform desktop application for indexing drives or folders, searching for files instantly, and finding duplicates. Built with Python and Tkinter, this tool is designed to be fast, efficient, and user-friendly, with both a complete GUI and a flexible command-line interface.    

It creates and uses catalog files (`.caf`) that are backwards-compatible with the classic [Cathy](http://www.mtg.sk/rva/cathy/cathy.html) cataloging tool, while extending its functionality with modern hashing algorithms and features.

-----

## Key Features

  - 🖥️ **Dual Interface:** Choose between a complete interactive GUI for visual workflow or a powerful CLI for scripting and automation.
  - ⚡ **Fast File Indexing (CAF Persistence):** Scans are dramatically faster on subsequent runs by creating and reusing `.caf` index files.
  - 👯 **Advanced Duplicate Finder:**
      - Compare a source folder against multiple destination folders.
      - Use MD5, SHA1, or SHA256 hashes for byte-perfect comparison.
  - 🔍 **Powerful Search:** Instantly search indexed files using filters for filename (with regex), file size, and modification date.
  - 💻 **Cross-Platform:** A single Python codebase that runs and builds for Windows, macOS, and Linux.
  - 🌐 **Offline Index Browsing:** Browse the contents of an index file even if the original drive is disconnected—perfect for checking archived drives.
  - 🌍 **Multi-Lingual Support:** Interface available in English and German, with auto-detection of system language.
  - 🛡️ **Safe Deletion Workflow:** Interactively select duplicates, generate safe and reviewable deletion scripts (`.bat` or `.sh`), or delete directly.
  - 📜 **Scriptable JSON Output:** Both search and duplicate-finding CLI commands can output structured JSON for easy integration with other tools.

-----

## Getting Started

### For Users (Recommended)

Download a pre-built executable for your operating system from the project's **[Releases Page](https://www.google.com/search?q=https://github.com/CrispStrobe/duplicate-finder/releases)**. No installation is required.

### For Developers (Running from Source)

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/CrispStrobe/Catfish.git
    cd Catfish
    ```

2.  **Create and activate a virtual environment (recommended):**

    ```bash
    # macOS / Linux
    python3 -m venv venv
    source venv/bin/activate

    # Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install Pillow
    ```

4.  **Run the application:**

    ```bash
    # To run the GUI (default behavior)
    python main.py

    # To see help for the Command-Line Interface (CLI)
    python main.py --help
    ```

-----

## Usage Guide: GUI Mode

Run the application without any arguments to launch the graphical interface, which is organized into four tabs.

### 1\. Search Files

The main search interface. Filter indexed files by **name (regex)**, **size**, and **modification date**. Results can be opened, located in the file explorer, or have their paths copied.

### 2\. Manage Indices

Manage your `.caf` index files. **Create** new indexes from folders, **Refresh** the list of available indexes, and **Delete** old ones. Use the **Active** checkbox to control which indexes are included in searches.

### 3\. Find Duplicates

Find duplicate files between a source and one or more destinations. Enable **file hashes** for accuracy and **reuse existing indices** for maximum speed.

### 4\. Settings

Configure the application's behavior, including **language**, default **hash algorithm**, and **index search locations**.

-----

## Usage Guide: CLI Mode

The command-line interface is perfect for scripting and automation. Use subcommands `search` or `find-dupes` to perform actions.

### Command: `search`

Searches for files across all active indexes based on the specified criteria.

**Examples:**

```bash
# Find all JPG files larger than 1MB
python main.py search "*.jpg" --size-min 1MB

# Find all video files and output the results as JSON
python main.py search "\.(mp4|mov)$" --output json > videos.json
```

### Command: `find-dupes`

Compares a source directory against one or more destination directories to find duplicate files.

**Examples:**

```bash
# Find duplicates of files from "C:\Photos" inside "D:\Backup"
# Use existing indexes for speed.
python main.py find-dupes "C:\Photos" "D:\Backup" --reuse-indices --hash md5

# Check a download folder against multiple archives and output a JSON report
python main.py find-dupes ./Downloads ./Archive1 ./Archive2 --output json
```

-----

## Building the Application

A build script is included to create distributable executables using PyInstaller. To build for your current OS, run:

```bash
python build_binaries.py
```

The final application will be placed in the `dist/` directory.

-----

## Command-Line Reference

### Global Arguments

| Argument | Description | Options |
| :--- | :--- | :--- |
| `command` | The action to perform. | `search`, `find-dupes` |
| `--lang` | Set language for CLI output messages. | `en`, `de` |

### `search` Arguments

| Argument | Description | Example |
| :--- | :--- | :--- |
| `pattern` | **Required.** Search pattern (regex supported). | `"vacation_.*\.jpg"` |
| `--size-min`| Minimum file size. | `--size-min 500KB` |
| `--size-max`| Maximum file size. | `--size-max 2GB` |
| `--date-min`| Minimum modification date. | `--date-min "2025-01-01"` |
| `--date-max`| Maximum modification date. | `--date-max "yesterday"` |
| `--output` | Output format. | `--output json` |

### Duplicates finding `find-dupes` Arguments

| Argument | Description |
| :--- | :--- |
| `source` | **Required.** The source folder to check for duplicates. |
| `destinations`| **Required.** One or more destination folders to search within. |
| `--hash` | Use a hash algorithm for accuracy. If omitted, uses name+size. |
| `--reuse-indices`| Use existing `.caf` indexes to speed up scans. |
| `--recreate-indices`| Force recreation of all destination indexes. |
| `--output` | Output format (`text` or `json`). |

-----

## Project Structure

```
duplicate-finder/
├── core/                  # Core logic (indexing, search, data structures)
├── ui/                    # GUI components (windows, dialogs)
├── utils/                 # Helper modules (file I/O, i18n, platform)
├── main.py                # Main application entry point (GUI and CLI)
├── build_binaries.py      # Script to build executables
└── README.md              # This documentation
```

-----

## Acknowledgments
Many thank to Robert Vašíček for the [awesome Cathy tool](http://rva.mtg.sk/) and to binsento42 for [the python recreation](https://github.com/binsento42/Cathy), which was very useful in building this.

## License

This project is licensed under the **MIT License**. Use at your own risk. **Always back up important data** before performing file deletion operations.
