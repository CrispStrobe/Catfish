# Enhanced Duplicate File Finder

A high-performance Python script that finds duplicate files between a source folder and multiple destination folders, with detailed location tracking and efficient indexing inspired by disk cataloging tools.

## Features

- 🔍 **Complete duplicate tracking** - Shows exactly WHERE each duplicate was found
- ⚡ **High-performance indexing** - Uses lazy hashing and hierarchical file organization  
- 📊 **Multiple comparison modes** - filename+size, MD5, SHA1, or SHA256 hash+size
- 🛡️ **Safe batch file generation** - Confirmation prompts and detailed comments
- 📝 **Detailed reporting** - Optional text reports with complete duplicate analysis
- 🏗️ **Efficient data structures** - Inspired by Cathy disk cataloging architecture
- 📈 **Progress indicators** - Real-time feedback during scanning
- 🪟 **Windows-optimized output** - Proper Unicode handling and path escaping

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

### 2. Verify Python Installation

```powershell
# Check Python version (should be 3.8 or higher)
python --version

# If 'python' doesn't work, try:
python3 --version

# Or:
py --version
```

### 3. Download the Script Files

Create a new folder and save these files:

**requirements.txt**
```
tqdm>=4.64.0
```

**duplicate_finder.py** (use the Python script provided earlier)

### 4. Navigate to Script Directory

```powershell
# Open Command Prompt or PowerShell
# Navigate to the folder containing your script
cd "C:\path\to\your\script"
```

### 5. Run the Script

```powershell
# Basic usage - compare by filename and size (fastest)
python duplicate_finder.py "C:\Downloads" "C:\Sorted\Photos" "C:\Sorted\Documents"

# MD5 hash comparison with detailed duplicate tracking
python duplicate_finder.py "C:\Downloads" "C:\Archive\Photos" --hash md5

# SHA256 comparison with custom output and detailed report
python duplicate_finder.py "C:\Downloads" "C:\Archive" --hash sha256 --output "cleanup.bat" --report

# Multiple destination folders with complete location tracking
python duplicate_finder.py "C:\Temp" "C:\Backup1" "C:\Backup2" --hash md5 --report
```

## Usage Examples

### Example 1: Basic Duplicate Detection
```powershell
python duplicate_finder.py "C:\Downloads" "C:\Sorted\Photos"
```
- Compares files in `C:\Downloads` against `C:\Sorted\Photos`
- Uses filename + file size for comparison
- Creates `delete_duplicates.bat`

### Example 2: Multiple Destination Folders
```powershell
python duplicate_finder.py "C:\Downloads" "C:\Photos" "C:\Documents" "C:\Videos"
```
- Compares `C:\Downloads` against three destination folders
- Finds files that exist in ANY of the destination folders

### Example 3: Hash-Based Comparison (Recommended)
```powershell
python duplicate_finder.py "C:\Downloads" "C:\Archive" --hash md5
```
- Uses MD5 hash + file size (detects renamed files)
- More accurate but slower
- Perfect for finding true duplicates regardless of filename

### Example 4: Maximum Security (SHA256)
```powershell
python duplicate_finder.py "C:\Downloads" "C:\Archive" --hash sha256
```
- Uses SHA256 hash + file size (most secure)
- Slowest but most accurate method
- Ideal for critical data verification

## Command Line Arguments

| Argument | Description | Options | Required |
|----------|-------------|---------|----------|
| `source_folder` | Folder to scan for duplicates | Any valid path | Yes |
| `dest_folders` | One or more destination folders | Any valid paths | Yes |
| `--hash` | Use hash + size comparison | `md5`, `sha1`, `sha256` | No |
| `--output` / `-o` | Custom batch file name | Any filename | No |
| `--report` | Generate detailed text report | Flag | No |

## Output Files

### Generated Batch File
The script creates a Windows batch file (default: `delete_duplicates.bat`) containing:
- UTF-8 encoding with BOM for proper Unicode support
- Safety confirmation prompt
- DEL commands for each duplicate file
- **Complete location details** showing exactly where each duplicate was found

**Example enhanced batch file content:**
```batch
@echo off
chcp 65001 > nul

REM Enhanced batch file to delete duplicate files from source folder.
REM Comparison method: MD5 hash + size
REM This file shows exactly WHERE each duplicate was found.
REM WARNING: This will permanently delete the files listed below!

REM Deleting source file: C:\Downloads\photo1.jpg
REM Found 2 duplicate(s) at:
REM   -> D:\Photos\Vacation\photo1.jpg (2,547,891 bytes)
REM   -> E:\Archive\2023\photo1.jpg (2,547,891 bytes)
del "C:\Downloads\photo1.jpg"

REM Deleting source file: C:\Downloads\document.pdf
REM Found 1 duplicate(s) at:
REM   -> D:\Archive\docs\document.pdf (451,203 bytes)
del "C:\Downloads\document.pdf"
```

### Optional Detailed Report
With the `--report` flag, generates an additional text file with comprehensive duplicate analysis:
- Summary statistics
- Complete file paths and sizes
- Organized listing of all duplicate locations

## Safety Features

⚠️ **IMPORTANT SAFETY NOTES:**

1. **Always review the batch file** before running it
2. **Test with a small folder first** to verify behavior
3. **Backup important data** before running batch deletions
4. The batch file includes a confirmation prompt
5. All file paths are properly quoted and escaped

## Troubleshooting

### Python Not Found
If you get "python is not recognized":
```powershell
# Try these alternatives:
python3 duplicate_finder.py ...
py duplicate_finder.py ...

# Or add Python to PATH manually
```

### Permission Errors
If you get permission errors:
```powershell
# Run Command Prompt as Administrator
# Right-click Command Prompt -> "Run as administrator"
```

### File Access Errors
- Ensure no files are open in other programs
- Check that you have read access to all folders
- Some system folders may be protected

### Large Folders Take Long Time
- Use `--md5` only when necessary (it's slower but more accurate)
- The script shows progress indicators every 100 files
- Consider processing smaller batches for very large folders

## Technical Details

### Comparison Methods

**Filename + Size (Default)**
- Fastest method - no hash calculation required
- May miss renamed files with identical content
- Suitable for basic duplicate detection

**MD5 Hash + Size (--hash md5)**
- Moderate speed with high accuracy
- Detects renamed duplicates based on content
- Balanced approach for most use cases

**SHA1 Hash + Size (--hash sha1)**
- Similar to MD5 but uses SHA1 algorithm
- Good alternative to MD5 for content verification

**SHA256 Hash + Size (--hash sha256)**
- Slowest but most cryptographically secure
- Maximum accuracy for critical data verification
- Recommended for sensitive or important files

### System Requirements
- Windows 10/11
- Python 3.8 or higher
- `tqdm` package (for progress bars)
- Read access to all folders being scanned

## File Structure
```
your-project-folder/
├── duplicate_finder.py          # Optimized main script
├── requirements.txt             # Dependencies (tqdm)
├── README.md                   # This file
└── delete_duplicates.bat       # Generated batch file (after running)
```

## License

MIT.

Keep in mind that this script is provided as-is for personal use. Use at your own risk and always backup important data before running file deletion operations.