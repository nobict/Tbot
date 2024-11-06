import sys
import os
import re
import shutil
import chardet
from tqdm import tqdm
import pyfiglet
from termcolor import colored
from config import PASS_FILES_DIR, ERROR_DIR, OUTPUT_FILE

def print_header():
    os.system('cls')
    title = pyfiglet.figlet_format("LOG FORMATER", font="slant")
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


# Removed command-line argument check
# as this script is now called from main.py


output_file = sys.argv[-1]
error_folder = 'files/errors'

def process_file(input_file, output_file, error_folder):
    credentials = []
    found_strings = False
    search_strings = ("")
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Detect the encoding of the input file
    with open(input_file, 'rb') as f:
        rawdata = f.read()
        encoding = chardet.detect(rawdata)['encoding']

    try:
        # Convert the input file to UTF-8 if needed
        if encoding != 'utf-8':
            with open(input_file, encoding=encoding, errors="ignore") as f:
                data = f.read()
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write(data)
            encoding = 'utf-8'

        with open(input_file, encoding=encoding, errors="ignore") as f:
            total_lines = sum(1 for line in f)
            f.seek(0)

            username = ""
            password = ""
            url = ""

            for line_number, line in enumerate(tqdm(f, total=total_lines, desc=f"Processing {os.path.basename(input_file)}")):
                line = line.strip()
                if not line or line.startswith("="):
                    continue

                # Extract credentials
                if "Username" in line or "USER" in line or "LOGIN" in line or "USR" in line:
                    username = re.split("[:=]", line)[-1].strip()
                elif "Password" in line or "PASS" in line:
                    password = re.split("[:=]", line)[-1].strip()
                elif "URL" in line or "Host" in line:
                    url = line.split(":", 1)[-1].split("=", 1)[-1].strip().lstrip("://")

                # Save credentials when we have all parts
                if username and password and url:
                    if "://t.me/" not in url:
                        credential = f"{url}:{username}:{password}"
                        credentials.append(credential)
                        
                        # Write to output file immediately
                        with open(output_file, "a", encoding="utf-8") as out_f:
                            out_f.write(credential + "\n")
                            
                    username = ""
                    password = ""
                    url = ""

        # Handle empty files and cleanup
        if os.stat(input_file).st_size == 0:
            print(f"Deleting empty file: {input_file}")
            os.remove(input_file)
        elif not credentials:
            print(f"No credentials found in: {input_file}")
            with open("lconv_error_log.txt", "a") as log_f:
                log_f.write(f"No credentials found in {input_file}\n")
        else:
            print(f"✅ Processed {len(credentials)} credentials from {os.path.basename(input_file)}")

        return len(credentials) > 0

    except Exception as e:
        print(f"❌ Error processing {input_file}: {str(e)}")
        # Move file to error directory
        error_path = os.path.join(error_folder, os.path.basename(input_file))
        os.makedirs(error_folder, exist_ok=True)
        shutil.move(input_file, error_path)
        
        with open("lconv_error_log.txt", "a") as log_f:
            log_f.write(f"Error processing {input_file}: {str(e)}\n")
        
        return False

def process_files(input_dir, output_file, error_dir):
    """Process all files with progress tracking"""
    try:
        # Get list of files
        files = [f for f in os.listdir(input_dir) if f.endswith('.txt')]
        total_files = len(files)
        
        if not files:
            print("📂 No files found to process")
            return
            
        print(f"\n🔄 Processing {total_files} files...")
        
        processed = 0
        successful = 0
        failed = 0
        
        with tqdm(total=total_files, desc="Processing files") as pbar:
            for filename in files:
                try:
                    input_file = os.path.join(input_dir, filename)
                    success = process_file(input_file, output_file, error_dir)
                    
                    if success:
                        successful += 1
                    else:
                        failed += 1
                        
                    processed += 1
                    pbar.update(1)
                    
                except Exception as e:
                    print(f"\n❌ Error processing {filename}: {e}")
                    failed += 1
                    pbar.update(1)
                    continue
                    
        print(f"\n✅ Processing complete:")
        print(f"   • Processed: {processed}/{total_files}")
        print(f"   • Successful: {successful}")
        print(f"   • Failed: {failed}")
        
    except Exception as e:
        print(f"\n❌ Error in process_files: {e}")

# Check if the user wants to process all files in a folder
if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "-f":
        folder_path = PASS_FILES_DIR
        if not os.path.isdir(folder_path):
            print("Error: Folder not found")
            sys.exit(1)
        
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                process_file(file_path, OUTPUT_FILE, ERROR_DIR)