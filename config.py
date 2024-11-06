import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALL_FILES_DIR = os.path.join(BASE_DIR, 'files', 'all')
PASS_FILES_DIR = os.path.join(BASE_DIR, 'files', 'pass')
ERROR_DIR = os.path.join(BASE_DIR, 'files', 'errors')
OUTPUT_FILE = os.path.join(BASE_DIR, 'output.txt')

# Create directories if they don't exist
for directory in [ALL_FILES_DIR, PASS_FILES_DIR, ERROR_DIR]:
    os.makedirs(directory, exist_ok=True)
    