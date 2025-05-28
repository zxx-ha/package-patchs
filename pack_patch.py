#!/usr/bin/python
########################################################################
#zxx 2017/9/7
# help:
#     python pack_patch.py commit-id patch-number [name] [--debug]
#sample:
#     python pack_patch.py 1d17982938f5808205debf052cab10381f6e5282 -1
#     python pack_patch.py 1d17982938f5808205debf052cab10381f6e5282 -1 test
#     python pack_patch.py 1d17982938f5808205debf052cab10381f6e5282 -1 test --debug
#
#used like git format-patch 
########################################################################
import os
import sys
import string
import time
import shutil
import subprocess

# Script version
VERSION = "1.0.6"

# Debug flag
DEBUG = False

def debug_print(*args, **kwargs):
    """Print debug messages only if debug mode is enabled"""
    if DEBUG:
        print(*args, **kwargs)

def copy_file_with_git(commit, file_path, dst):
    """Copy file using git show to get the correct version"""
    try:
        # Ensure target directory exists
        dst_dir = os.path.dirname(dst)
        try:
            os.makedirs(dst_dir)
        except OSError:
            if not os.path.isdir(dst_dir):
                raise
        
        # Get file content using git show
        cmd = "git show %s:%s" % (commit, file_path)
        debug_print("\nStep 3.1 - Executing command: %s" % cmd)
        try:
            content = subprocess.check_output(cmd, shell=True)
            with open(dst, 'wb') as f:
                f.write(content)
            debug_print("Step 3.2 - Copied: %s -> %s" % (file_path, dst))
            return True
        except subprocess.CalledProcessError as e:
            print("Error getting file content: %s" % str(e))
            return False
    except Exception as e:
        print("Error copying file %s: %s" % (file_path, str(e)))
        return False

def get_modified_files(commit, num):
    """Get list of modified files from git log"""
    temp_file = 'git_log_temp'
    # Get file changes using git log for committed changes
    cmd = "git log %s %s --name-status --pretty=format: > %s" % (commit, num, temp_file)
    debug_print("\nStep 3.1 - Executing command: %s" % cmd)
    os.system(cmd)
    
    modified_files = []
    with open(temp_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            # Skip deleted files
            if line.startswith('D\t'):
                continue
                
            # Handle all other cases (A=Added, M=Modified, R=Renamed)
            if '\t' in line:
                status, file_path = line.split('\t', 1)
                if file_path:
                    # For renamed files, take the new name
                    if status == 'R' and ' -> ' in file_path:
                        file_path = file_path.split(' -> ')[1]
                    # If path contains space, use the path after the space
                    if ' ' in file_path:
                        file_path = file_path.split(' ')[-1]
                    modified_files.append(file_path)
                    debug_print("Step 3.2 - Found %s file: %s" % (status, file_path))
    
    os.remove(temp_file)
    return modified_files

# Parse command line arguments
args = sys.argv[1:]
if len(args) < 2:
    print("Usage: python pack_patch.py commit-id patch-number [name] [--debug]")
    print("Example: python pack_patch.py 1d17982938f5808205debf052cab10381f6e5282 -1")
    print("         python pack_patch.py 1d17982938f5808205debf052cab10381f6e5282 -1 test")
    sys.exit(1)

# Check for debug flag
if '--debug' in args:
    DEBUG = True
    args.remove('--debug')

commit = args[0]
num = args[1]
name = args[2] if len(args) > 2 else "patch"

debug_print("\nStep 0 - Script Information:")
debug_print("  0.1 - Script Version: %s" % VERSION)
debug_print("  0.2 - Last Update: %s" % time.strftime('%Y-%m-%d %H:%M:%S'))

# Create package directories
now = time.strftime('%Y%m%d', time.localtime(time.time()))
packagename = '%s-patch-%s' % (name, now)
SRC = os.path.join(packagename, 'src')
PATCHS = os.path.join(packagename, 'patchs')

debug_print("\nStep 1 - Package information:")
debug_print("  1.1 - Package name: %s" % packagename)
debug_print("  1.2 - Source directory: %s" % SRC)
debug_print("  1.3 - Patches directory: %s" % PATCHS)

# Create directories
try:
    os.makedirs(SRC)
except OSError:
    if not os.path.isdir(SRC):
        raise

try:
    os.makedirs(PATCHS)
except OSError:
    if not os.path.isdir(PATCHS):
        raise

# 1. Generate patch files
debug_print("\nStep 2 - Generating patches...")
os.system("git format-patch %s %s -o %s" % (commit, num, PATCHS))

# 2. Copy modified files
debug_print("\nStep 3 - Copying modified files...")
modified_files = get_modified_files(commit, num)
for file_path in modified_files:
    # Clean up the file path
    file_path = file_path.strip()
    if not file_path:
        continue
        
    # For ELF files that have old.elf and new.elf format, we only want the new.elf
    # So we split the string and take the last part
    file_path = file_path.split()[-1]
    debug_print("========result:", file_path)
    
    # Preserve the original directory structure
    dest_path = os.path.join(SRC, file_path)
    debug_print("\nStep 3.3 - Processing file:")
    debug_print("  3.3.1 - Original path: %s" % file_path)
    debug_print("  3.3.2 - Destination path: %s" % dest_path)
    
    if not copy_file_with_git(commit, file_path, dest_path):
        print("Failed to copy file: %s" % file_path)

# 3. Create zip package
debug_print("\nStep 4 - Creating zip package...")
os.system("zip -r %s.zip %s" % (packagename, packagename))

# Print final information
print("\nPackage created: %s.zip" % packagename)
print("Script Version: %s" % VERSION)

