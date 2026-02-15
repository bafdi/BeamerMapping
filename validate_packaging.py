#!/usr/bin/env python3
"""
Validation script to check packaging setup.
Tests that all necessary files and configurations are in place.
"""

import os
import sys
from pathlib import Path

def check_file(path, description):
    """Check if a file exists."""
    if os.path.exists(path):
        print(f"✓ {description}: {path}")
        return True
    else:
        print(f"✗ {description}: {path} NOT FOUND")
        return False

def check_executable(path, description):
    """Check if a file is executable."""
    if os.path.exists(path):
        if os.access(path, os.X_OK):
            print(f"✓ {description}: {path} (executable)")
            return True
        else:
            print(f"⚠ {description}: {path} (not executable)")
            return False
    else:
        print(f"✗ {description}: {path} NOT FOUND")
        return False

def main():
    """Run validation checks."""
    print("BeamerMapper Packaging Validation")
    print("=" * 50)
    
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    all_checks = []
    
    # Check main entry point
    print("\n1. Main Application:")
    all_checks.append(check_file("run_mapper.py", "Main entry point"))
    all_checks.append(check_file("src/mapper/__init__.py", "Mapper package"))
    all_checks.append(check_file("src/mapper/main_window.py", "Main window module"))
    
    # Check packaging scripts
    print("\n2. Packaging Scripts:")
    all_checks.append(check_executable("package_mac.sh", "macOS packaging script"))
    all_checks.append(check_file("package_win.bat", "Windows packaging script"))
    all_checks.append(check_executable("create_dmg.sh", "DMG creation script"))
    
    # Check icons
    print("\n3. Application Icons:")
    all_checks.append(check_file("icon.ico", "Windows icon"))
    all_checks.append(check_file("icon.icns", "macOS icon"))
    all_checks.append(check_file("icon.png", "PNG icon"))
    
    # Check configuration files
    print("\n4. Configuration Files:")
    all_checks.append(check_file("requirements.txt", "Python requirements"))
    all_checks.append(check_file("setup.py", "Setup script (py2app)"))
    all_checks.append(check_file("BeamerMapper.spec", "PyInstaller spec"))
    
    # Check GitHub Actions
    print("\n5. CI/CD:")
    all_checks.append(check_file(".github/workflows/build.yml", "GitHub Actions workflow"))
    
    # Check documentation
    print("\n6. Documentation:")
    all_checks.append(check_file("README.md", "README"))
    all_checks.append(check_file("PACKAGING.md", "Packaging documentation"))
    
    # Check presets directory (optional)
    print("\n7. Optional Assets:")
    if os.path.exists("presets"):
        print(f"✓ Presets directory: presets/")
    else:
        print(f"⚠ Presets directory: presets/ (not found, may be empty)")
    
    # Summary
    print("\n" + "=" * 50)
    passed = sum(all_checks)
    total = len(all_checks)
    print(f"Summary: {passed}/{total} checks passed")
    
    if passed == total:
        print("✓ All packaging files are in place!")
        return 0
    else:
        print("⚠ Some files are missing or not executable")
        return 1

if __name__ == "__main__":
    sys.exit(main())
