#
# Usage: python compile_locales.py
#
# This script compiles .po files into .mo files for use with gettext.
# It requires the 'polib' library. Install it with:
# pip install polib
#
import os
from pathlib import Path
import polib

def compile_all_po_files():
    """
    Finds all .po files in the 'locales' directory and compiles them to .mo files.
    """
    base_dir = Path(__file__).parent
    locales_dir = base_dir / 'locales'
    
    if not locales_dir.is_dir():
        print(f"Error: Directory '{locales_dir}' not found.")
        return

    print("Starting compilation of .po files...")
    
    po_files = list(locales_dir.glob('**/*.po'))
    
    if not po_files:
        print("No .po files found to compile.")
        return

    for po_path in po_files:
        mo_path = po_path.with_suffix('.mo')
        try:
            print(f"Compiling {po_path} -> {mo_path}")
            po_file = polib.pofile(str(po_path))
            po_file.save_as_mofile(str(mo_path))
        except Exception as e:
            print(f"  ERROR compiling {po_path}: {e}")
            
    print("\nCompilation finished.")

if __name__ == "__main__":
    try:
        import polib
    except ImportError:
        print("Error: 'polib' library not found.")
        print("Please install it using: pip install polib")
    else:
        compile_all_po_files()