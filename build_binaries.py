# build_binaries.py - Automated build script for multiple platforms
# =================================================================

#!/usr/bin/env python3
"""
Cross-platform binary builder for Universal File Search Tool
Builds executables for Windows, macOS, and creates installable packages
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

class BinaryBuilder:
    def __init__(self):
        self.root_dir = Path(__file__).parent
        self.script_name = "main.py"
        self.app_name = "Universal File Search"
        self.version = "1.0.0"
        self.build_dir = self.root_dir / "build"
        self.dist_dir = self.root_dir / "dist"
        self.icons_dir = self.root_dir / "icons"

    def clean_build(self):
        """Clean previous build artifacts."""
        print("Cleaning previous builds...")
        for dir_path in [self.build_dir, self.dist_dir]:
            if dir_path.exists():
                shutil.rmtree(dir_path)

        for spec_file in self.root_dir.glob("*.spec"):
            spec_file.unlink()

    def install_dependencies(self):
        """Install required dependencies."""
        print("Installing build dependencies...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", "--upgrade",
            "pyinstaller", "setuptools", "wheel", "Pillow"
        ], check=True)

    def setup_icons_dir(self):
        """Ensures the icons directory exists."""
        self.icons_dir.mkdir(exist_ok=True)
        
    def build_windows_exe(self):
        """Build Windows executable."""
        if platform.system() != "Windows":
            print("Skipping Windows build - not on Windows platform")
            return

        print("Building Windows executable...")
        self.setup_icons_dir()
        icon_path = self.icons_dir / "app_icon.ico"

        cmd = [
            "pyinstaller", "--onefile", "--windowed",
            "--name", self.app_name.replace(" ", ""),
            "--paths", str(self.root_dir),
            "--hidden-import", "tkinter", "--hidden-import", "tkinter.ttk",
            "--hidden-import", "tkinter.filedialog", "--hidden-import", "tkinter.messagebox",
            "--clean", self.script_name
        ]
        
        if icon_path.exists() and icon_path.stat().st_size > 0:
            cmd.extend(["--icon", str(icon_path)])
        else:
            print("Windows icon not found, using default.")

        subprocess.run(cmd, check=True)
        self.create_windows_installer()

    def build_macos_app(self):
        """Build macOS application bundle."""
        if platform.system() != "Darwin":
            print("Skipping macOS build - not on macOS platform")
            return

        print("Building macOS application...")
        self.setup_icons_dir()
        icon_path = self.icons_dir / "app_icon.icns"

        cmd = [
            "pyinstaller", "--onedir", "--windowed",
            "--name", self.app_name,
            "--paths", str(self.root_dir),
            "--osx-bundle-identifier", "com.yourcompany.universalsearch",
            "--clean", self.script_name
        ]
        
        if icon_path.exists() and icon_path.stat().st_size > 0:
            print(f"Using icon: {icon_path}")
            cmd.extend(["--icon", str(icon_path)])
        else:
            print("macOS icon not found or is empty, using default.")

        subprocess.run(cmd, check=True)
        self.create_macos_dmg()

    def build_linux_appimage(self):
        """Build Linux AppImage."""
        if platform.system() != "Linux":
            print("Skipping Linux build - not on Linux platform")
            return

        print("Building Linux executable...")
        self.setup_icons_dir()
        icon_path = self.icons_dir / "app_icon.png"

        cmd = [
            "pyinstaller", "--onefile",
            "--name", self.app_name.replace(" ", ""),
            "--paths", str(self.root_dir),
            "--clean", self.script_name
        ]

        if icon_path.exists() and icon_path.stat().st_size > 0:
            cmd.extend(["--icon", str(icon_path)])
        else:
            print("Linux icon not found, using default.")

        subprocess.run(cmd, check=True)
        self.create_linux_appimage()
    
    # --- Installer Creation Methods (Restored) ---

    def create_macos_dmg(self):
        """Create macOS DMG installer from the .app bundle."""
        print("Creating macOS DMG installer...")
        try:
            dmg_name = f"{self.app_name.replace(' ', '')}-{self.version}.dmg"
            app_path = self.dist_dir / f"{self.app_name}.app"
            
            if app_path.exists():
                subprocess.run([
                    "hdiutil", "create", "-volname", self.app_name,
                    "-srcfolder", str(app_path),
                    "-ov", "-format", "UDZO",
                    str(self.dist_dir / dmg_name)
                ], check=True)
                print(f"macOS DMG created: {dmg_name}")
            else:
                print("App bundle not found - DMG not created")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Failed to create DMG: {e}")

    def create_linux_appimage(self):
        """Placeholder for creating a Linux AppImage."""
        print("\nSkipping AppImage creation.")
        print("To create a Linux AppImage, you need external tools like 'appimagetool'.")

    def create_windows_installer(self):
        """Placeholder for creating a Windows installer."""
        print("\nSkipping Windows installer creation.")
        print("To create a Windows installer, you need external tools like NSIS.")

    def build_all(self):
        self.clean_build()
        self.install_dependencies()
        system = platform.system()
        print(f"\nBuilding for {system}...")
        if system == "Windows": self.build_windows_exe()
        elif system == "Darwin": self.build_macos_app()
        elif system == "Linux": self.build_linux_appimage()
        else: print(f"Unsupported platform: {system}"); return
        print(f"\nBuild completed! Check the 'dist' directory for your application.")
        self.print_distribution_info()

    def print_distribution_info(self):
        """Prints final information about the created files."""
        print("\n" + "="*50)
        print("DISTRIBUTION INFORMATION")
        print("="*50)
        
        system = platform.system()
        if system == "Windows":
            print("Windows Distribution:")
            print(f"- Executable: dist/{self.app_name.replace(' ', '')}.exe")
        elif system == "Darwin":
            print("macOS Distribution:")
            print(f"- App Bundle: dist/{self.app_name}.app")
            print(f"- DMG Installer: dist/{self.app_name.replace(' ', '')}-{self.version}.dmg")
        elif system == "Linux":
            print("Linux Distribution:")
            print(f"- Executable: dist/{self.app_name.replace(' ', '')}")

if __name__ == "__main__":
    builder = BinaryBuilder()
    builder.build_all()