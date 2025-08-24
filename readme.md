# Enhanced Duplicate File Finder with Interactive GUI

A high-performance Python application that finds duplicate files between source and destination folders, featuring a complete interactive GUI workflow, efficient CAF index persistence, and thread-safe operation.

Status: work in progress

## Features

- 🖥️ **Complete Interactive GUI** - Full workflow from path selection to duplicate management
- 📱 **Responsive Design** - Adapts to screen sizes from laptops to large monitors  
- ⚡ **CAF Index Persistence** - Dramatically faster subsequent scans using Cathy-inspired indices
- 🧵 **Thread-Safe Operation** - Background processing with real-time progress updates
- 🎯 **Smart Path Management** - Automatic subdirectory exclusion to prevent double-indexing
- 🔍 **Advanced Filtering** - Regex-based duplicate selection with mass operations
- 📋 **Path Integration** - Copy file paths to clipboard with Ctrl+C or double-click
- 🛡️ **Safe Deletion** - Interactive selection with size calculations and confirmations
- 📊 **Multiple Hash Algorithms** - MD5, SHA1, or SHA256 with filename+size fallback
- 🔄 **Seamless Workflow** - From setup through results with cancellation support

## Quick Start

### 1. Install Python (if not already installed)

```powershell
# Install Python using winget (Windows Package Manager)  
winget install Python.Python.3.12

# Alternative: Install from Microsoft Store
winget install 9NCVDN91XZQP

# Alternative: Download from python.org
# Visit https://www.python.org/downloads/ and download Python 3.8+
```

### 2. Install Dependencies

```powershell
# Install required packages
pip install tqdm

# Or using requirements.txt
pip install -r requirements.txt
```

**requirements.txt**
```
tqdm>=4.64.0
```

### 3. Launch Interactive Mode

```powershell
# Complete GUI workflow - no paths needed!
python duplicate_finder.py --gui

# GUI with hash mode pre-selected  
python duplicate_finder.py --gui --hash md5
```

## GUI Workflow

### Setup Phase
- **Browse for Source Folder** - Select the folder to scan for duplicates
- **Add Destination Folders** - Multiple destinations supported with add/remove
- **Configure Options** - Choose hash algorithm, enable index persistence
- **Path Validation** - Real-time validation with helpful error messages

### Scanning Phase  
- **Background Processing** - Thread-safe operation with progress updates
- **Cancellation Support** - Stop scanning at any time
- **Index Management** - Automatic CAF file creation and reuse
- **Smart Filtering** - Excludes subdirectories to prevent double-indexing

### Results Phase
- **Interactive Selection** - Checkboxes and spacebar for file selection
- **Regex Filtering** - `.*\.jpg$` to select only JPG files, etc.
- **Mass Operations** - "Select All Filtered" for bulk selection
- **Size Calculations** - Real-time totals for selected files
- **Safe Deletion** - Confirmation dialogs with detailed information

## Index Persistence (Major Performance Feature)

The application saves file indices as CAF files (Cathy-inspired format) for dramatic performance improvements:

### First Scan
- Builds complete file indices for all destination folders
- Saves indices as `.caf` files next to each folder
- Normal scanning speed

### Subsequent Scans  
- Loads existing indices in seconds instead of minutes/hours
- Automatically detects changed files (by size/date)
- 10-100x faster for unchanged large directories

### Index Management
- **Automatic Creation** - Indices saved when `--reuse-indices` enabled
- **Smart Invalidation** - Rebuilt when files change
- **Manual Control** - Force recreation with `--recreate-indices`

## Usage Examples

### Interactive GUI Mode (Recommended)
```powershell
# Complete interactive experience
python duplicate_finder.py --gui

# With hash comparison preset
python duplicate_finder.py --gui --hash md5

# Force index recreation
python duplicate_finder.py --gui --recreate-indices
```

### Command Line Mode
```powershell
# Basic comparison with index persistence
python duplicate_finder.py "C:\Downloads" "D:\Archive" --reuse-indices

# Hash comparison with multiple destinations  
python duplicate_finder.py "C:\Downloads" "D:\Photos" "E:\Backup" --hash md5 --reuse-indices

# Force rebuild all indices
python duplicate_finder.py "C:\Downloads" "D:\Archive" --hash sha256 --recreate-indices
```

## Advanced Features

### Regex Filtering Examples
- `.*\.(jpg|jpeg|png)$` - Select only image files
- `IMG_\d{4}` - Select files like IMG_1234.jpg  
- `.*[Dd]uplicate.*` - Select files with "duplicate" in name
- `.*\.mp4$` - Select only MP4 video files

### Path Copy Integration
- **Ctrl+C** - Copy selected file path to clipboard
- **Double-click** - Copy file path to clipboard  
- **Status Feedback** - Shows what was copied

### When to Use Hash Comparison
- **Filename+Size (Default)** - Fastest, good for basic duplicate detection
- **MD5 Hash** - Balanced speed/accuracy, detects renamed files
- **SHA256 Hash** - Slowest but most secure, for critical data

## System Requirements

- **Operating System** - Windows 10/11, macOS, or Linux
- **Python** - Version 3.8 or higher
- **Memory** - Minimum 2GB RAM (4GB+ recommended for large folders)
- **Storage** - Space for .caf index files (typically 1-5MB per indexed folder)
- **Permissions** - Read access to all folders being scanned

## Troubleshooting

### GUI Won't Start
```powershell
# Check Python/tkinter installation
python -m tkinter

# Install tkinter if missing (Linux)
sudo apt-get install python3-tk
```

### Index Files Not Working
- Check folder permissions for .caf file creation
- Verify sufficient disk space for indices  
- Use `--recreate-indices` to rebuild corrupted indices

### Performance Issues
- Enable `--reuse-indices` for large folders
- Use filename+size mode for fastest scanning
- Process folders in smaller batches if needed

### Path Issues
- Ensure no files are locked by other applications
- Check read permissions on all source/destination folders
- Use GUI path browser to avoid typing errors

## Technical Architecture

### CAF File Format
- Binary format inspired by Cathy disk cataloger
- Stores file metadata, directory structure, and optional hashes
- Efficient loading/saving with proper endianness handling
- Extended comment field for hash storage

### Thread Model
- Main GUI thread handles all UI updates
- Background worker threads for file processing  
- Queue-based communication for thread safety
- Proper cleanup and cancellation support

## File Structure
```
your-project-folder/
├── duplicate_finder.py          # Main application
├── requirements.txt             # Python dependencies  
├── README.md                   # This documentation
└── [generated files]
    ├── FolderName_index.caf    # Index files (auto-generated)
    ├── delete_duplicates.bat   # Batch file (if generated)
    └── delete_duplicates_report.txt # Report file (if requested)
```

## Command Line Reference

### Arguments
| Argument | Description | Options | Default |
|----------|-------------|---------|---------|
| `--gui` | Launch interactive GUI | Flag | False |
| `source_folder` | Source folder (CLI mode) | Path | Required for CLI |
| `dest_folders` | Destination folders (CLI mode) | Paths | Required for CLI |
| `--hash` | Hash algorithm | `md5`, `sha1`, `sha256` | None |
| `--reuse-indices` | Enable CAF index persistence | Flag | False |
| `--recreate-indices` | Force rebuild indices | Flag | False |

### Examples
```powershell  
# GUI with all features
python duplicate_finder.py --gui

# CLI with indices  
python duplicate_finder.py "C:\Downloads" "D:\Archive" --reuse-indices

# Hash mode with index rebuild
python duplicate_finder.py "C:\Downloads" "D:\Archive" --hash md5 --recreate-indices
```

## License

MIT License - Use at your own risk. Always backup important data before running file deletion operations.