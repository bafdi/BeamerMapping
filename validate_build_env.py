#!/usr/bin/env python3
"""
Build Environment Validation Script
Checks if all requirements for building are met
"""

import sys
import subprocess
import platform
from pathlib import Path

def check_python_version():
    """Check if Python version is adequate"""
    print("Checking Python version...", end=" ")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"✗ Python {version.major}.{version.minor}.{version.micro} (need 3.8+)")
        return False

def check_pip():
    """Check if pip is available"""
    print("Checking pip...", end=" ")
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "--version"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✓")
            return True
        else:
            print("✗")
            return False
    except Exception as e:
        print(f"✗ {e}")
        return False

def check_dependencies():
    """Check if runtime dependencies are installed"""
    print("\nChecking runtime dependencies:")
    deps = ['PyQt6', 'cv2', 'numpy', 'mss']
    all_ok = True
    
    for dep in deps:
        module_name = 'opencv-python' if dep == 'cv2' else dep
        print(f"  {module_name}...", end=" ")
        try:
            __import__(dep)
            print("✓")
        except ImportError:
            print("✗ Not installed")
            all_ok = False
    
    return all_ok

def check_build_dependencies():
    """Check if build dependencies are installed"""
    print("\nChecking build dependencies:")
    print("  pyinstaller...", end=" ")
    try:
        import PyInstaller
        print(f"✓ {PyInstaller.__version__}")
        return True
    except ImportError:
        print("✗ Not installed (run: pip install -r requirements-build.txt)")
        return False

def check_data_directories():
    """Check if required data directories exist"""
    print("\nChecking data directories:")
    dirs = ['presets', 'docs', 'src']
    all_ok = True
    
    for dir_name in dirs:
        print(f"  {dir_name}/...", end=" ")
        if Path(dir_name).exists():
            print("✓")
        else:
            print("✗ Missing")
            all_ok = False
    
    return all_ok

def check_platform_specific():
    """Check platform-specific requirements"""
    os_name = platform.system()
    print(f"\nPlatform-specific checks ({os_name}):")
    
    if os_name == "Darwin":  # macOS
        print("  Homebrew...", end=" ")
        try:
            result = subprocess.run(["brew", "--version"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("✓")
            else:
                print("✗ Not installed (needed for create-dmg)")
        except FileNotFoundError:
            print("✗ Not installed (install from https://brew.sh)")
        
        print("  create-dmg...", end=" ")
        try:
            result = subprocess.run(["create-dmg", "--version"], 
                                  capture_output=True, text=True)
            if result.returncode == 0 or "create-dmg" in result.stderr.lower():
                print("✓")
            else:
                print("✗ Not installed (run: brew install create-dmg)")
        except FileNotFoundError:
            print("✗ Not installed (run: brew install create-dmg)")
    
    elif os_name == "Windows":
        print("  Windows detected - ready for .exe build ✓")
    
    else:
        print(f"  {os_name} detected - platform support may vary")

def main():
    """Main validation function"""
    print("=" * 60)
    print("BeamerMapper Build Environment Validation")
    print("=" * 60)
    print()
    
    results = []
    results.append(check_python_version())
    results.append(check_pip())
    results.append(check_dependencies())
    results.append(check_build_dependencies())
    results.append(check_data_directories())
    
    check_platform_specific()
    
    print("\n" + "=" * 60)
    if all(results):
        print("✓ All checks passed! Ready to build.")
        print("\nNext steps:")
        print("  macOS:   ./build_macos.sh")
        print("  Windows: build_windows.bat")
        return 0
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        print("\nTo install missing dependencies:")
        print("  Runtime: pip install -r requirements.txt")
        print("  Build:   pip install -r requirements-build.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())
