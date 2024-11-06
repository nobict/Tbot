import os
import re
import time
import shutil
import zipfile
import rarfile
import gc
from colorama import init, Fore
from datetime import datetime

# Initialize colorama for cross-platform color support
init()

def print_color(color, text):
    """Helper function to print colored text"""
    print(f"{color}{text}{Fore.RESET}")

def main():
    print("\033[H\033[2J")  # Clear screen
    print_color(Fore.CYAN, "\nStarting the EXTRACTOR...\n")

    input_directory = "files/all"
    output_directory = "files/pass"

    process_archives_in_dir(input_directory, output_directory)

def read_passwords_from_file(password_file):
    passwords_list = [""]

    if not os.path.exists(password_file):
        print_color(Fore.RED, f"🚫 Password 📂 file {password_file} does not exist.")
        print_color(Fore.YELLOW, "⚠️ Trying to extract without a password!")
        return passwords_list

    try:
        with open(password_file, 'r') as file:
            for line in file:
                password = line.strip()
                if password:
                    passwords_list.append(password)
    except Exception as err:
        print_color(Fore.RED, f"🛠 An error occurred while 🔄 reading the password file: {err}")

    return passwords_list

def extract_inner_archive(inner_file_path, destination_path, passwords):
    """Extract password files from an inner archive"""
    success = False
    inner_success = False
    if inner_file_path.endswith('.zip'):
        inner_success = extract_zip_files(inner_file_path, destination_path, passwords)
    elif inner_file_path.endswith('.rar'):
        inner_success = extract_rar_files(inner_file_path, destination_path, passwords)
    
    if inner_success:
        force_delete_file(inner_file_path)
        success = True  # Mark as successful if inner archive was processed
    return success

def extract_zip_files(archive_path, destination_path, passwords):
    try:
        with zipfile.ZipFile(archive_path) as z:
            # First check if there are any password files before proceeding
            password_files = [f for f in z.namelist() if re.match(r'.*asswor.*\.txt', f)]
            
            if not password_files:
                print_color(Fore.YELLOW, "💡 No password-protected files found in the ZIP archive")
                return False

            print_color(Fore.YELLOW, f"💡 Found {len(password_files)} 🔑 Password-protected files")
            
            has_inner_archives = False
            inner_success = False
            extraction_error = False
            
            # First check for inner archives and extract them
            for file_info in z.filelist:
                if file_info.filename.endswith(('.zip', '.rar')):
                    has_inner_archives = True
                    try:
                        temp_path = os.path.join(destination_path, file_info.filename)
                        z.extract(file_info, destination_path)
                        if extract_inner_archive(temp_path, destination_path, passwords):
                            inner_success = True
                    except Exception as err:
                        print_color(Fore.RED, f"🛠️ Error processing inner archive: {err}")
                        extraction_error = True
                        continue

            if extraction_error:
                return False

            # If we only had inner archives and they were processed successfully, return True
            if has_inner_archives and inner_success:
                return True

            # Process password files
            password_protected_files = sum(1 for f in z.namelist() if re.match(r'.*asswor.*\.txt', f))
            if password_protected_files > 0:
                print_color(Fore.YELLOW, f"💡 Found {password_protected_files} 🔑 Password-protected files\n")
            else:
                print_color(Fore.YELLOW, "💡 No password-protected files found in the ZIP archive\n")
                return False

            extracted_files = 0
            for file_info in z.filelist:
                if not re.match(r'.*asswor.*\.txt', file_info.filename):
                    continue

                # Try passwords from pass.txt first
                file_extracted = False
                try:
                    with open('pass.txt', 'r') as f:
                        for line in f:
                            password = line.strip()
                            try:
                                password_bytes = password.encode() if password else None
                                with z.open(file_info, pwd=password_bytes) as source:
                                    timestamp = int(time.time() * 1_000_000)
                                    new_filename = f"password_{extracted_files}_{timestamp}.txt"
                                    new_filepath = os.path.join(destination_path, new_filename)

                                    with open(new_filepath, 'wb') as target:
                                        shutil.copyfileobj(source, target)

                                    print_color(Fore.GREEN, f"✅ File saved: {new_filepath}")
                                    extracted_files += 1
                                    file_extracted = True
                                    break
                            except Exception:
                                continue
                except Exception as err:
                    print_color(Fore.RED, f"🛠️ Error reading pass.txt: {err}")

                if not file_extracted:
                    print_color(Fore.RED, f"🛠️ Could not extract file: {file_info.filename}")
                    continue

            return extracted_files > 0
    except Exception as err:
        print_color(Fore.RED, f"🛠️ Error opening ZIP file: {err}")
        return False

def extract_rar_files(archive_path, destination_path, passwords):
    try:
        # Configure rarfile to use UnRAR.exe
        rarfile.UNRAR_TOOL = "UnRAR.exe"
        
        with rarfile.RarFile(archive_path) as rf:
            # First check if there are any password files before proceeding
            password_files = [f for f in rf.namelist() if re.match(r'.*asswor.*\.txt', f)]
            
            if not password_files:
                print_color(Fore.YELLOW, "💡 No password-protected files found in the RAR archive")
                return False

            print_color(Fore.YELLOW, f"💡 Found {len(password_files)} 🔑 Password-protected files")
            
            has_inner_archives = False
            inner_success = False
            extraction_error = False
            
            # First check for inner archives and extract them
            for file_info in rf.infolist():
                if file_info.filename.endswith(('.zip', '.rar')):
                    has_inner_archives = True
                    try:
                        temp_path = os.path.join(destination_path, file_info.filename)
                        rf.extract(file_info, destination_path)
                        if extract_inner_archive(temp_path, destination_path, passwords):
                            inner_success = True
                    except Exception as err:
                        print_color(Fore.RED, f"🛠️ Error processing inner archive: {err}")
                        extraction_error = True
                        continue

            if extraction_error:
                return False

            # If we only had inner archives and they were processed successfully, return True
            if has_inner_archives and inner_success:
                return True

            # Process password files
            password_protected_files = 0
            extracted_files = 0

            for file_info in rf.infolist():
                if not re.match(r'.*asswor.*\.txt', file_info.filename):
                    continue

                password_protected_files += 1
                file_extracted = False

                # Try passwords from pass.txt
                try:
                    with open('pass.txt', 'r') as f:
                        for line in f:
                            password = line.strip()
                            try:
                                # Create a temporary directory for this extraction attempt
                                temp_dir = os.path.join(destination_path, "temp_extract")
                                os.makedirs(temp_dir, exist_ok=True)
                                
                                # Try to extract with current password
                                rf.extractall(temp_dir, pwd=password.encode() if password else None)
                                
                                # If extraction successful, move password files to destination
                                for root, _, files in os.walk(temp_dir):
                                    for file in files:
                                        if re.match(r'.*asswor.*\.txt', file, re.IGNORECASE):
                                            timestamp = int(time.time() * 1_000_000)
                                            new_filename = f"password_{extracted_files}_{timestamp}.txt"
                                            source_path = os.path.join(root, file)
                                            new_filepath = os.path.join(destination_path, new_filename)
                                            
                                            shutil.move(source_path, new_filepath)
                                            print_color(Fore.GREEN, f"✅ File saved: {new_filepath}")
                                            extracted_files += 1
                                            file_extracted = True
                                
                                # Clean up temp directory
                                shutil.rmtree(temp_dir, ignore_errors=True)
                                
                                if file_extracted:
                                    break
                                    
                            except Exception:
                                # Clean up temp directory on failure
                                shutil.rmtree(temp_dir, ignore_errors=True)
                                continue
                except Exception as err:
                    print_color(Fore.RED, f"🛠️ Error reading pass.txt: {err}")

                if not file_extracted:
                    print_color(Fore.RED, f"🛠️ Could not extract file: {file_info.filename}")
                    continue

            if password_protected_files > 0:
                print_color(Fore.YELLOW, f"💡 Found {password_protected_files} 🔑 Password-protected files\n")
            else:
                print_color(Fore.YELLOW, "💡 No password-protected files found in the RAR archive\n")
                return False

            return extracted_files > 0
            
    except Exception as err:
        print_color(Fore.RED, f"🛠️ Error opening RAR file: {err}")
        return False

def force_delete_file(file_path):
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            os.remove(file_path)
            return None
        except Exception as err:
            print_color(Fore.YELLOW, f"Attempt {attempt + 1} to delete file failed: {err}")
            gc.collect()  # Force garbage collection
            time.sleep(1)  # Wait a bit before next attempt

    return f"Failed to delete file after {max_attempts} attempts"

def find_first_volume(file_path):
    """Find the first volume of a multi-part archive"""
    if not any(x in file_path.lower() for x in ['.part', '.r00', '.001']):
        return file_path

    directory = os.path.dirname(file_path)
    base_name = re.sub(r'\.part\d+\.rar$|\.r\d+$|\.\d+$', '', file_path, flags=re.IGNORECASE)
    
    # Check for different multi-part formats
    potential_first_volumes = [
        f"{base_name}.rar",  # Standard RAR
        f"{base_name}.part1.rar",  # part1.rar format
        f"{base_name}.part01.rar",  # part01.rar format
        f"{base_name}.r00",  # r00 format
        f"{base_name}.001"  # 001 format
    ]
    
    for volume in potential_first_volumes:
        if os.path.exists(volume):
            return volume
            
    return None

def delete_all_volumes(first_volume_path):
    """Delete all volumes of a multi-part archive"""
    directory = os.path.dirname(first_volume_path)
    base_name = re.sub(r'\.part\d+\.rar$|\.r\d+$|\.\d+$', '', first_volume_path, flags=re.IGNORECASE)
    base_name = os.path.basename(base_name)
    
    for file in os.listdir(directory):
        if file.startswith(base_name) and any(x in file.lower() for x in ['.rar', '.r', '.']):
            file_path = os.path.join(directory, file)
            error = force_delete_file(file_path)
            if error:
                print_color(Fore.RED, f"🛠️ Error deleting volume {file}: {error}")
            else:
                print_color(Fore.GREEN, f"🗑️ Deleted volume: {file}")

def process_archives_in_dir(input_dir, output_dir):
    if not os.path.exists(input_dir):
        print_color(Fore.RED, f"🚫 Input directory {input_dir} does not exist.")
        return

    # Create output and error directories
    error_dir = "files/all_errors"
    for directory in [output_dir, error_dir]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print_color(Fore.YELLOW, f"⚠️ Directory {directory} created.")

    start = time.time()
    passwords = read_passwords_from_file("./pass.txt")

    while True:
        files = os.listdir(input_dir)
        supported_files = sum(1 for f in files if f.endswith(('.zip', '.rar')))

        if supported_files == 0:
            break

        print_color(Fore.CYAN, f"📂 Processing {supported_files} supported files in {input_dir}")
        processed_files = 0
        processed_paths = set()  # Track which archives we've already processed
        error_files = set()  # Track files that failed extraction

        for filename in files:
            file_path = os.path.join(input_dir, filename)
            
            # Skip if we've already processed this archive set
            if file_path in processed_paths:
                continue
                
            success = False

            if filename.endswith('.zip'):
                print_color(Fore.BLUE, f"\n📦 Found ZIP archive: {file_path}")
                success = extract_zip_files(file_path, output_dir, passwords)
                if success:
                    error = force_delete_file(file_path)
                    if not error:
                        processed_files += 1
                else:
                    error_files.add(file_path)
            elif filename.endswith('.rar'):
                # Handle RAR archives (including multi-part)
                first_volume = find_first_volume(file_path)
                if not first_volume:
                    print_color(Fore.YELLOW, f"⚠️ Skipping {filename} - first volume not found")
                    continue
                    
                # Add all related volumes to processed paths
                base_name = re.sub(r'\.part\d+\.rar$|\.r\d+$|\.\d+$', '', first_volume, flags=re.IGNORECASE)
                for f in files:
                    if f.startswith(os.path.basename(base_name)):
                        processed_paths.add(os.path.join(input_dir, f))
                
                print_color(Fore.BLUE, f"\n📦 Found RAR archive: {first_volume}")
                success = extract_rar_files(first_volume, output_dir, passwords)
                
                if success:
                    delete_all_volumes(first_volume)
                    processed_files += 1
                else:
                    # Move all volumes to error directory
                    for f in files:
                        if f.startswith(os.path.basename(base_name)):
                            error_files.add(os.path.join(input_dir, f))
            else:
                continue

        # Move error files to error directory
        for error_file in error_files:
            try:
                error_path = os.path.join(error_dir, os.path.basename(error_file))
                shutil.move(error_file, error_path)
                print_color(Fore.YELLOW, f"⚠️ Moved failed file to errors: {error_file}")
            except Exception as err:
                print_color(Fore.RED, f"🛠️ Error moving file to errors folder: {err}")

        print_color(Fore.YELLOW, f"Processed {processed_files} out of {supported_files} supported files")

    elapsed = time.time() - start
    print_color(Fore.GREEN, f"Total Extraction Time: {elapsed:.2f}s")

if __name__ == "__main__":
    main()