from pathlib import Path
import logging

# Configure logging for better visibility of actions
logging.basicConfig(level=logging.INFO, format='[%(asctime)s]: %(message)s')

# List of files required for the VOC-to-YOLO annotation converter and chatbot project
list_of_files = [
    "src/__init__.py",                        # Initialization file for the source package
    "src/convert_voc_to_yolo.py",             # Main conversion script from VOC to YOLO format
    "src/utils.py",                           # Utility functions (e.g., logging setup, file handling utilities)
    "data/labels/.gitkeep",                   # Keeps the data/labels folder in Git (VOC XML annotation files location)
    "tests/test_convert_voc_to_yolo.py",      # Test case for the VOC to YOLO conversion logic
    "tests/test_utils.py",                    # Test case for utility functions
    "config/config.json",                     # Configuration file for the chatbot
    ".env",                                   # Environment file for storing sensitive data like API keys
    "setup.py",                               # Setup file for packaging the project
    "pyproject.toml",                         # Configuration file for Python project dependencies and settings
    "Dockerfile",                             # Dockerfile for containerizing the application
    ".gitignore",                             # File to ignore unnecessary files in Git
    ".dockerignore",                          # File to ignore unnecessary files in Docker builds
    "notebooks/experiments.ipynb",            # Jupyter notebook for experiments with the chatbot and retrieval system
    "data/.gitkeep",                          # Keeps the data folder in Git (for general data files)
    "app.py",                                 # Entry point for the chatbot application
    "static/.gitkeep",                        # Keeps the static folder in Git (for CSS, JS)
    "templates/index.html",                   # HTML template for the web interface
    "README.md",                              # README file for project documentation
    ".github/workflows/cicd-main.yml",        # GitHub Actions workflow for CI/CD automation
]

# Loop over the list of files and create the necessary directories and files
for filepath in list_of_files:
    filepath = Path(filepath)
    filedir = filepath.parent

    # Create directories if they don't exist
    if filedir != Path("."):  # Only create directory if it's not the current directory
        if not filedir.exists():
            filedir.mkdir(parents=True, exist_ok=True)
            logging.info(f"Created directory: {filedir}")

    # Create the file if it doesn't exist or is empty
    if not filepath.exists() or filepath.stat().st_size == 0:
        filepath.touch()  # This creates an empty file
        logging.info(f"Created empty file: {filepath}")
    else:
        logging.info(f"File {filepath} already exists and is not empty")
