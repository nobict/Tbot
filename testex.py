import os
import random
import rarfile
import py7zr
import pyzipper
import re
from tqdm import tqdm
from glob import glob
import pyfiglet
from termcolor import colored
import shutil
import platform
import subprocess
import importlib.util
from config import ALL_FILES_DIR, PASS_FILES_DIR, ERROR_DIR
import logging
import asyncio

# Add logger configuration at the top of the file
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# I added this function to run an external executable as a fallback in case of an error.
def run_fallback():
    """Run fallback ext.py on error with user confirmation."""
    try:
        # Get the current directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        ext_path = os.path.join(current_dir, "ext.py")
        
        if os.path.exists(ext_path):
            # Ask for confirmation
            response = input("\n❓ Extraction failed. Would you like to try the fallback method? (y/n): ")
            
            if response.lower() == 'y':
                print("\n🔄 Running fallback ext.py...")
                # Import and run ext.py
                spec = importlib.util.spec_from_file_location("ext", ext_path)
                ext_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ext_module)
                
                # Call the main function from ext.py
                if hasattr(ext_module, 'main'):
                    ext_module.main()
                else:
                    print("❌ Error: main() function not found in ext.py")
            else:
                print("\n⏭️ Skipping fallback method...")
        else:
            print(f"\n❌ Error: Could not find ext.py at {ext_path}")
    except Exception as e:
        print(f"\n❌ Error running fallback ext.py: {e}")
        

def print_header():
    os.system('cls')
    title = pyfiglet.figlet_format("EXTRACTER", font="big")
    title = colored(title, 'red')
    subtitle = colored("by @redscorpionlogs", 'green')

    print('''
==================================
{}   {}
==================================
'''.format(title, subtitle))
print_header()
print('''
LOADING FILES PLEASE WAIT .....
''')

def read_file_from_rar(rar_file, info, pwd):
    content = bytearray()
    try:
        with rar_file.open(info, pwd=pwd) as part_file:
            content.extend(part_file.read())
    except RuntimeError as e:
        print(f'Error: {e}')
        print('Incorrect password. Please try again.')
    except Exception as e:
        print(f'Error: {e}')
    return content

def extract_passwords_from_rar(rar_path, destination_dir, progress_callback=None):
    """Extract from RAR with progress tracking"""
    try:
        print(f"\n📂 Processing RAR file: {os.path.basename(rar_path)}")
        with rarfile.RarFile(rar_path, 'r') as rar_file:
            # Count password files
            password_files = [f for f in rar_file.infolist() 
                            if re.compile(r'.*ass.*\.txt', re.IGNORECASE).match(f.filename)]
            total_files = len(password_files)
            processed = 0
            
            print(f"📑 Found {total_files} password files")
            
            if progress_callback:
                progress_callback({
                    'status': 'extracting',
                    'total_files': total_files,
                    'current': 0,
                    'file_name': os.path.basename(rar_path)
                })
            
            passwords = read_passwords_from_file('pass.txt')
            print(f"🔑 Trying {len(passwords)} passwords...")
            
            for pwd in passwords:
                try:
                    print(f"🔍 Attempting extraction with password...")
                    rar_file.extractall(path=destination_dir, pwd=pwd.encode())
                    processed = total_files
                    if progress_callback:
                        progress_callback({
                            'status': 'extracting',
                            'total_files': total_files,
                            'current': processed,
                            'file_name': os.path.basename(rar_path)
                        })
                    print("✅ Extraction successful!")
                    return True
                except rarfile.BadRarFile:
                    continue
                    
            print("❌ No valid password found")
            return False
            
    except Exception as e:
        print(f"❌ Error extracting RAR {rar_path}: {e}")
        return False

def extract_passwords_from_7z(archive_path, destination_dir, progress_callback=None):
    """Extract from 7z with progress tracking"""
    try:
        # Try passwords from pass.txt
        with open('pass.txt', 'r') as f:
            passwords = [line.strip() for line in f if line.strip()]
        
        for pwd in passwords:
            try:
                # Open archive with password
                with py7zr.SevenZipFile(archive_path, mode='r', password=pwd) as archive:
                    # Get list of files
                    file_list = archive.getnames()
                    password_file_regex = re.compile(r'.*\.ass.*\.txt', re.IGNORECASE)
                    matching_files = [f for f in file_list if password_file_regex.match(f)]
                    total_files = len(matching_files)
                    
                    if total_files == 0:
                        continue
                    
                    if progress_callback:
                        progress_callback({
                            'status': 'extracting',
                            'total_files': total_files,
                            'current': 0,
                            'file_name': os.path.basename(archive_path)
                        })
                    
                    # Extract matching files
                    counter = 1
                    with tqdm(total=total_files, desc="Extracting files", unit="file") as pbar:
                        for file_name in matching_files:
                            try:
                                # Extract to temporary directory first
                                temp_dir = os.path.join(destination_dir, 'temp')
                                os.makedirs(temp_dir, exist_ok=True)
                                
                                # Extract file
                                archive.extract(temp_dir, [file_name])
                                
                                # Move file with random prefix
                                temp_path = os.path.join(temp_dir, file_name)
                                if os.path.exists(temp_path):
                                    prefix = str(random.randint(1000000000, 9999999999))
                                    new_name = f"{prefix}_password_{counter}.txt"
                                    new_path = os.path.join(destination_dir, new_name)
                                    
                                    shutil.move(temp_path, new_path)
                                    counter += 1
                                    
                                    if progress_callback:
                                        progress_callback({
                                            'status': 'extracting',
                                            'total_files': total_files,
                                            'current': counter - 1,
                                            'file_name': os.path.basename(archive_path)
                                        })
                                    
                                    pbar.update(1)
                                
                            except Exception as e:
                                print(f"Error extracting {file_name}: {e}")
                                continue
                                
                        # Cleanup temp directory
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        
                    # Add explicit success message
                    print(f"✅ Successfully extracted files from: {os.path.basename(archive_path)}")
                    return True  # Return True if we got this far with the correct password
                    
            except py7zr.Bad7zFile:
                continue  # Try next password
                
        # If we get here, no password worked
        print(f"\n❌ No valid password found for {archive_path}")
        return False
        
    except Exception as e:
        print(f'\n❌ Error processing 7z archive {archive_path}: {e}')
        if progress_callback:
            progress_callback({
                'status': 'error',
                'message': str(e),
                'file_name': os.path.basename(archive_path)
            })
        
        # Ask for fallback
        response = input("\n❓ Would you like to try the fallback method? (y/n): ")
        if response.lower() == 'y':
            run_fallback()
            
        return False

def read_file_from_zip(zip_file, info, pwd):
    content = bytearray()
    try:
        with zip_file.open(info, pwd=pwd) as part_file:
            content.extend(part_file.read())
    except RuntimeError as e:
        print(f'Error: {e}')
        print('Incorrect password. Please try again.')
    except Exception as e:
       print(f'Error: {e}')
    return content

def extract_passwords_from_zip(zip_path, destination_dir, progress_callback=None):
    # Check if zip_path is a multi-part ZIP file
    zip_parts = sorted(glob(zip_path + '.*'))
    if zip_parts:
        # Open the first part of the multi-part ZIP file
        with pyzipper.AESZipFile(zip_parts[0], 'r') as zip_file:
            counter = 1
            password_file_regex = re.compile(r'.*pas.*\.txt', re.IGNORECASE)
            with tqdm(desc="Extracting password files from ZIP archive", unit="file", leave=False) as pbar:
                pwd = None
                for info in zip_file.infolist():
                    if password_file_regex.match(info.filename):
                        # Read the contents of the file from the multi-part ZIP file
                        content = bytearray()
                        for part in zip_parts:
                            with pyzipper.AESZipFile(part, 'r') as part_zip_file:
                                while True:
                                    # Try passwords from pass.txt if archive is encrypted and password is not set
                                    if part_zip_file.getinfo(info.filename).flag_bits & 0x1 and pwd is None:
                                        with open('pass.txt', 'r') as f:
                                            for line in f:
                                                pwd = line.strip().encode('utf-8')
                                                try:
                                                    with part_zip_file.open(info, pwd=pwd) as part_file:
                                                        content.extend(part_file.read())
                                                    break
                                                except RuntimeError as e:
                                                    pass
                                    # Prompt user for password if archive is encrypted and password is not set
                                    if part_zip_file.getinfo(info.filename).flag_bits & 0x1 and pwd is None:
                                        pwd = input(f'Enter password for {zip_path} (press Enter to skip): ')
                                        if not pwd:
                                            break
                                        pwd = pwd.encode('utf-8')
                                    with part_zip_file.open(info, pwd=pwd) as part_file:
                                        content.extend(part_file.read())
                                    break
                        if not content:
                            continue
                        prefix = str(random.randint(1000000000, 9999999999))
                        filename = prefix + 'password' + str(counter) + '.txt'
                        file_path = os.path.join(destination_dir, filename)
                        with open(file_path, 'wb') as f:
                            f.write(content)
                        pbar.update(1)
                        counter += 1
    else:
        # Handle single-part ZIP file
        with pyzipper.AESZipFile(zip_path, 'r') as zip_file:
            counter = 1
            password_file_regex = re.compile(r'.*pas.*\.txt', re.IGNORECASE)
            total_files = len([info for info in zip_file.infolist() if password_file_regex.match(info.filename)])
            with tqdm(total=total_files, desc="Extracting password files from ZIP archive", unit="file", leave=False) as pbar:
                pwd = None
                for info in zip_file.infolist():
                    if password_file_regex.match(info.filename):
                        while True:
                            # Try passwords from pass.txt if archive is encrypted and password is not set
                            if zip_file.getinfo(info.filename).flag_bits & 0x1 and pwd is None:
                                with open('pass.txt', 'r') as f:
                                    for line in f:
                                        pwd = line.strip().encode('utf-8')
                                        try:
                                            content = zip_file.read(info.filename, pwd=pwd)
                                            break
                                        except RuntimeError as e:
                                            pass
                            # Prompt user for password if archive is encrypted and password is not set
                            if zip_file.getinfo(info.filename).flag_bits & 0x1 and pwd is None:
                                pwd = input(f'Enter password for {zip_path} (press Enter to skip): ')
                                if not pwd:
                                    break
                                pwd = pwd.encode('utf-8')
                            content = zip_file.read(info.filename, pwd=pwd)
                            break
                        if not content:
                            continue
                        prefix = str(random.randint(1000000000, 9999999999))
                        filename = prefix + 'password' + str(counter) + '.txt'
                        file_path = os.path.join(destination_dir, filename)
                        with open(file_path, 'wb') as f:
                            f.write(content)
                        pbar.update(1)
                        counter += 1

def extract_passwords_from_archive(archive_path, destination_dir, progress_callback=None):
    """Extract passwords with progress tracking"""
    try:
        total_size = os.path.getsize(archive_path)
        file_name = os.path.basename(archive_path)
        success = False  # Initialize success flag
        
        if progress_callback:
            progress_callback({
                'status': 'start',
                'file_name': file_name,
                'total_size': total_size,
                'archive_type': 'RAR' if rarfile.is_rarfile(archive_path) else '7Z' if archive_path.endswith('.7z') else 'ZIP'
            })
        
        # Determine archive type and extract
        if rarfile.is_rarfile(archive_path):
            success = extract_passwords_from_rar(archive_path, destination_dir, progress_callback)
        elif archive_path.endswith('.7z'):
            success = extract_passwords_from_7z(archive_path, destination_dir, progress_callback)
        elif pyzipper.is_zipfile(archive_path):
            success = extract_passwords_from_zip(archive_path, destination_dir, progress_callback)
            success = True  # ZIP extraction doesn't return success status, assume success
        else:
            print(f"❌ Unsupported archive format: {archive_path}")
            return False
            
        # Update progress and return result
        if success:
            print(f"✅ Successfully extracted: {os.path.basename(archive_path)}")
            if progress_callback:
                progress_callback({
                    'status': 'complete',
                    'file_name': file_name,
                    'success': True
                })
            return True
        else:
            print(f"❌ Failed to extract: {os.path.basename(archive_path)}")
            if progress_callback:
                progress_callback({
                    'status': 'error',
                    'file_name': file_name,
                    'success': False
                })
            return False
            
    except Exception as e:
        print(f"❌ Error in extract_passwords_from_archive: {str(e)}")
        if progress_callback:
            progress_callback({
                'status': 'error',
                'message': str(e),
                'file_name': os.path.basename(archive_path)
            })
        return False

def extract_and_delete_archive(archive_path, destination_dir, progress_callback=None):
    """Extract archive and handle cleanup"""
    try:
        # Skip temporary files
        if archive_path.lower().endswith('.temp'):
            print(f'Skipping temporary file: {archive_path}')
            return False

        # Extract the archive
        success = extract_passwords_from_archive(archive_path, destination_dir, progress_callback)
        
        if success:
            try:
                # Only delete if extraction was successful
                if os.path.exists(archive_path):
                    os.remove(archive_path)
                    print(f'✅ Successfully extracted and deleted: {os.path.basename(archive_path)}')
                return True
            except PermissionError:
                print(f'⚠️ Could not delete {archive_path}: File is in use')
                return True  # Still return True as extraction was successful
            except Exception as e:
                print(f'⚠️ Error deleting {archive_path}: {str(e)}')
                return True  # Still return True as extraction was successful
        
        # If extraction failed, don't move to error directory, just return false
        print(f"❌ Failed to extract: {os.path.basename(archive_path)}")
        return False

    except Exception as e:
        print(f'❌ Error processing archive {archive_path}: {str(e)}')
        return False

def process_archives_in_dir(input_dir, output_dir, progress_callback=None):
    """Process all archives with progress tracking"""
    try:
        # Get list of all archives
        archives = []
        for ext in ['*.rar', '*.7z', '*.zip']:
            archives.extend(glob(os.path.join(input_dir, '**/' + ext), recursive=True))
        
        # Filter out temporary files
        archives = [a for a in archives if not a.lower().endswith('.temp')]
        
        total_archives = len(archives)
        processed = 0
        successful = 0
        failed = 0
        
        if progress_callback:
            asyncio.run(progress_callback({
                'status': 'start',
                'total_archives': total_archives,
                'current': 0
            }))
        
        print(f"\n📦 Found {total_archives} archives to process")
        
        # Process all files
        for archive in archives:
            try:
                if progress_callback:
                    asyncio.run(progress_callback({
                        'status': 'processing',
                        'total_archives': total_archives,
                        'current': processed,
                        'successful': successful,
                        'failed': failed,
                        'current_file': os.path.basename(archive)
                    }))
                
                success = extract_and_delete_archive(archive, output_dir)
                processed += 1
                
                if success:
                    successful += 1
                else:
                    failed += 1
                    print(f"⚠️ Initial extraction failed for: {os.path.basename(archive)}")
                    
            except Exception as e:
                print(f"❌ Error processing {archive}: {str(e)}")
                failed += 1
        
        # Add fallback prompt if any failures occurred
        if failed > 0:
            print(f"\n⚠️ {failed} archives failed to extract.")
            run_fallback()
        
        # Final status update
        if progress_callback:
            asyncio.run(progress_callback({
                'status': 'complete',
                'total_archives': total_archives,
                'processed': processed,
                'successful': successful,
                'failed': failed
            }))
                
        print(f"\n✅ Processing complete:")
        print(f"   • Processed: {processed}/{total_archives}")
        print(f"   • Successful: {successful}")
        print(f"   • Failed: {failed}")
        
        return successful > 0

    except Exception as e:
        print(f"❌ Error in process_archives_in_dir: {str(e)}")
        if progress_callback:
            asyncio.run(progress_callback({
                'status': 'error',
                'message': str(e)
            }))
        return False

def read_passwords_from_file(filename):
    """Read passwords from a file and return them as a list."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Error reading passwords file: {e}")
        return []

if __name__ == "__main__":
    process_archives_in_dir(ALL_FILES_DIR, PASS_FILES_DIR)
