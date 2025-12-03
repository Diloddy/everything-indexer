#!/usr/bin/env python3
"""
Everything‑like Indexer for Linux – Clean Working Version.
Matrix Style: 80% transparent black with green accents.
"""
import os
import re
import csv
import json
import sqlite3
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Menu, Listbox, Scrollbar, simpledialog
from datetime import datetime
from threading import Thread
import shutil


# ==================== PLATFORM-INDEPENDENT PATHS ====================
def get_app_data_dir():
    """Get the correct application data directory for any OS"""
    home = os.path.expanduser("~")
    
    if sys.platform == "win32":
        base = os.path.join(os.environ.get("APPDATA", home), "EverythingIndexer")
    elif sys.platform == "darwin":  # macOS
        base = os.path.join(home, "Library", "Application Support", "EverythingIndexer")
    else:  # Linux and other Unix-like
        base = os.path.join(home, ".local", "share", "everything-indexer")
    
    os.makedirs(base, exist_ok=True)
    return base

def get_config_dir():
    """Get the correct config directory for any OS"""
    home = os.path.expanduser("~")
    
    if sys.platform == "win32":
        base = os.path.join(os.environ.get("APPDATA", home), "EverythingIndexer")
    elif sys.platform == "darwin":  # macOS
        base = os.path.join(home, "Library", "Preferences", "EverythingIndexer")
    else:  # Linux and other Unix-like
        base = os.path.join(home, ".config", "everything-indexer")
    
    os.makedirs(base, exist_ok=True)
    return base

# Database and settings paths
APP_DATA_DIR = get_app_data_dir()
CONFIG_DIR = get_config_dir()
DB_PATH = os.path.join(APP_DATA_DIR, "everything_index.db")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

def extract_drive_letter(path):
    """Extract drive letter from path like /media/user/M/..."""
    if not path or not isinstance(path, str):
        return "Unknown"
    
    # Clean the path
    path = path.strip()
    
    # Case 1: Windows path with drive letter (C:, D:, M:, etc.)
    windows_match = re.match(r'^([A-Za-z]):', path)
    if windows_match:
        return windows_match.group(1).upper()
    
    # Case 2: Linux path format: /media/username/M/...
    if path.startswith('/media/'):
        parts = path.split('/')
        if len(parts) >= 4:
            # Look for single letter after /media/username/
            for part in parts[3:]:
                if len(part) == 1 and part.isalpha():
                    return part.upper()
            return parts[3].upper()
    
    # Case 3: Linux path format: /mnt/M/...
    if path.startswith('/mnt/'):
        parts = path.split('/')
        if len(parts) >= 3:
            drive = parts[2]
            if len(drive) == 1 and drive.isalpha():
                return drive.upper()
    
    # Case 4: Look for single letter directory
    match = re.search(r'/([A-Za-z])/', path)
    if match:
        return match.group(1).upper()
    
    return "Unknown"

# ==================== DATABASE ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            excluded TEXT DEFAULT ''
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            folder_id INTEGER,
            path TEXT UNIQUE,
            name TEXT,
            size INTEGER,
            modified REAL,
            type TEXT,
            indexed_date REAL,
            FOREIGN KEY (folder_id) REFERENCES folders (id)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_name ON files (name COLLATE NOCASE)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_type ON files (type COLLATE NOCASE)')
    conn.commit()
    conn.close()

def get_or_create_folder(folder_path):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO folders (path) VALUES (?)", (folder_path,))
    c.execute("SELECT id FROM folders WHERE path = ?", (folder_path,))
    folder_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return folder_id

def get_excluded_patterns(folder_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT excluded FROM folders WHERE id = ?", (folder_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return [p.strip() for p in row[0].split(';') if p.strip()]
    return []

def update_excluded(folder_path, exclude_pattern):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT excluded FROM folders WHERE path = ?", (folder_path,))
    row = c.fetchone()
    current = row[0] if row and row[0] else ''
    new_excluded = current + ';' + exclude_pattern if current else exclude_pattern
    c.execute("UPDATE folders SET excluded = ? WHERE path = ?", (new_excluded, folder_path))
    conn.commit()
    conn.close()

def get_excluded_folders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT path FROM folders WHERE excluded = 'EXCLUDED'")
    excluded_paths = {row[0] for row in c.fetchall()}
    conn.close()
    return excluded_paths

def index_folder(folder_path, cleanup=False, progress_callback=None):
    if not os.path.isdir(folder_path):
        return False, "Invalid folder path."
    
    folder_id = get_or_create_folder(folder_path)
    excluded_patterns = get_excluded_patterns(folder_id)
    excluded_folders = get_excluded_folders()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    file_count = 0
    
    if cleanup:
        c.execute("SELECT path FROM files WHERE folder_id = ?", (folder_id,))
        existing_paths = {row[0] for row in c.fetchall()}
    else:
        existing_paths = set()
    
    seen_paths = set()
    
    if folder_path in excluded_folders:
        conn.close()
        return True, f"Folder '{os.path.basename(folder_path)}' is excluded (skipped)."
    
    for root, dirs, files in os.walk(folder_path):
        skip_entirely = False
        for excluded_path in excluded_folders:
            if root.startswith(excluded_path):
                skip_entirely = True
                break
        
        if skip_entirely:
            dirs[:] = []
            continue
        
        rel_root = os.path.relpath(root, folder_path)
        skip_this = False
        if rel_root != '.':
            for pattern in excluded_patterns:
                if pattern and (rel_root == pattern or rel_root.startswith(pattern + '/')):
                    skip_this = True
                    break
        
        if skip_this:
            dirs[:] = []
            continue
        
        for f in files:
            full = os.path.join(root, f)
            try:
                stat = os.stat(full)
                _, ext = os.path.splitext(f)
                c.execute('''INSERT OR REPLACE INTO files
                            (folder_id, path, name, size, modified, type, indexed_date)
                            VALUES (?,?,?,?,?,?,?)''',
                          (folder_id, full, f, stat.st_size, stat.st_mtime,
                           ext.lower(), datetime.now().timestamp()))
                file_count += 1
                seen_paths.add(full)
                if progress_callback and file_count % 100 == 0:
                    progress_callback(file_count)
            except:
                pass
    
    if cleanup:
        missing = existing_paths - seen_paths
        for path in missing:
            c.execute("DELETE FROM files WHERE path = ?", (path,))
        removed_count = len(missing)
    else:
        removed_count = 0
    
    conn.commit()
    conn.close()
    
    msg = f"Indexed {file_count} files from {os.path.basename(folder_path)}"
    if cleanup and removed_count > 0:
        msg += f", removed {removed_count} missing files."
    
    return True, msg

def rescan_drive(drive_path, cleanup=False):
    if not os.path.isdir(drive_path):
        return False, "Invalid drive path."
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT path FROM folders WHERE path LIKE ? AND excluded != 'EXCLUDED'", 
              (drive_path + '%',))
    folders = [row[0] for row in c.fetchall()]
    conn.close()
    
    if not folders:
        return False, f"No indexed folders found under {drive_path}"
    
    total_files = 0
    total_removed = 0
    
    for folder in folders:
        success, msg = index_folder(folder, cleanup=cleanup)
        if "Indexed" in msg:
            parts = msg.split(" ")
            for i, part in enumerate(parts):
                if part == "Indexed":
                    total_files += int(parts[i+1])
                    break
        if "removed" in msg:
            parts = msg.split(" ")
            for i, part in enumerate(parts):
                if part == "removed":
                    total_removed += int(parts[i+1])
                    break
    
    msg = f"Rescanned {len(folders)} folders on {os.path.basename(drive_path)}: "
    msg += f"{total_files} files processed"
    if total_removed > 0:
        msg += f", {total_removed} removed"
    
    return True, msg

def search_files(search_term, limit=1000000):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if not search_term:
        query = '''SELECT f.name, f.size, f.type, f.path
                   FROM files f JOIN folders fo ON f.folder_id = fo.id
                   ORDER BY f.indexed_date DESC LIMIT ?'''
        params = (limit,)
    else:
        terms = [t.strip() for t in search_term.split('|')]
        queries = []
        params = []
        for term in terms:
            if '!' in term:
                include, exclude = term.split('!', 1)
                include = include.strip()
                exclude = exclude.strip()
                if include:
                    queries.append("(name LIKE ? AND name NOT LIKE ?)")
                    params.append('%' + include + '%')
                    params.append('%' + exclude + '%')
                else:
                    queries.append("(name NOT LIKE ?)")
                    params.append('%' + exclude + '%')
            elif '*' in term or '?' in term:
                pattern = term.replace('*', '%').replace('?', '_')
                queries.append("(name LIKE ?)")
                params.append(pattern)
            else:
                queries.append("(name LIKE ?)")
                params.append('%' + term + '%')
        where = ' OR '.join(queries)
        query = f'''SELECT f.name, f.size, f.type, f.path
                    FROM files f JOIN folders fo ON f.folder_id = fo.id
                    WHERE {where} COLLATE NOCASE
                    ORDER BY f.name LIMIT ?'''
        params.append(limit)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

# ==================== GUI ====================
class EverythingApp:
    def __init__(self, root):
        self.root = root
        
        # Try to load icon from same directory as script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "icon.png")
        try:
            self.icon = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, self.icon)
        except Exception as e:
            # If icon not found in script dir, try system paths
            try:
                # Try common icon locations
                possible_icon_paths = [
                    "/usr/share/icons/everything-indexer.png",
                    "/usr/local/share/icons/everything-indexer.png",
                    os.path.expanduser("~/.local/share/icons/everything-indexer.png"),
                ]
                for path in possible_icon_paths:
                    if os.path.exists(path):
                        self.icon = tk.PhotoImage(file=path)
                        root.iconphoto(True, self.icon)
                        break
            except:
                print(f"Icon error (ignored): {e}")
                pass
        
        self.root.title("Everything Indexer")
        self.root.geometry("1500x850")
        
        # Matrix theme: transparent black window
        self.root.configure(bg='#0A0A0A')
        # Try to set opacity (may not work on all window managers)
        try:
            self.root.attributes('-alpha', 0.95)  # 95% opacity
        except:
            pass
        
        self.sort_column = 'name'
        self.sort_reverse = False
        self.font_size = 14
        self.tree_font_size = 14

        self.style = ttk.Style()
        
        # Matrix theme: Black with green text, semi-transparent
        self.style.theme_use('default')
        
        # Configure all widgets with Matrix theme
        bg_color = '#0A0A0A'  # Pure black
        fg_color = '#00FF00'  # Bright green
        hover_bg = '#003300'  # Dark green for hover
        field_bg = '#001100'  # Slightly lighter black for fields
        
        # Frame styling
        self.style.configure('TFrame', background=bg_color)
        
        # Label styling
        self.style.configure('TLabel', 
                            background=bg_color,
                            foreground=fg_color,
                            font=('Monospace', self.font_size))
        
        # Button styling - Matrix theme
        button_config = {
            'foreground': fg_color,
            'background': bg_color,
            'font': ('Monospace', self.font_size),
            'borderwidth': 2,
            'relief': 'raised',
            'padding': (10, 5),
            'focuscolor': '#00FF00'  # Green focus ring
        }
        
        self.style.configure('Green.TButton', **button_config)
        self.style.configure('Red.TButton', **button_config)
        self.style.configure('Blue.TButton', **button_config)
        self.style.configure('Orange.TButton', **button_config)
        self.style.configure('Purple.TButton', **button_config)
        
        # Button hover effects
        self.style.map('Green.TButton',
                      background=[('active', hover_bg)],
                      foreground=[('active', fg_color)])
        self.style.map('Red.TButton',
                      background=[('active', hover_bg)],
                      foreground=[('active', fg_color)])
        self.style.map('Blue.TButton',
                      background=[('active', hover_bg)],
                      foreground=[('active', fg_color)])
        self.style.map('Orange.TButton',
                      background=[('active', hover_bg)],
                      foreground=[('active', fg_color)])
        self.style.map('Purple.TButton',
                      background=[('active', hover_bg)],
                      foreground=[('active', fg_color)])
        
        # Scrollbar styling
        self.style.configure("Vertical.TScrollbar",
                            background='#00AA00',
                            troughcolor='#003300',
                            bordercolor='#00AA00',
                            arrowcolor='#00FF00',
                            width=20)
        
        self.style.map("Vertical.TScrollbar",
                      background=[('active', '#00FF00')],
                      foreground=[('active', '#00FF00')])

        # Entry field styling
        self.style.configure('TEntry',
                            fieldbackground=field_bg,
                            background=field_bg,
                            foreground=fg_color,
                            insertcolor=fg_color,
                            borderwidth=2,
                            relief='sunken')

        # Entry focus effect
        self.style.map('TEntry',
                      fieldbackground=[('focus', '#002200')],
                      background=[('focus', '#002200')])
        
        # Treeview styling (matches existing)
        self.style.configure('Treeview', 
                            font=('Monospace', self.tree_font_size),
                            background=bg_color,
                            foreground=fg_color,
                            fieldbackground=bg_color,
                            rowheight=self.tree_font_size + 10)
        
        self.style.configure('Treeview.Heading', 
                            font=('Monospace', self.tree_font_size),
                            background='#003300',
                            foreground=fg_color)
        
        self.style.map('Treeview',
                      background=[('selected', '#004400')],
                      foreground=[('selected', fg_color)])

        frame_search = ttk.Frame(root, padding="15")
        frame_search.grid(row=0, column=0, sticky=(tk.W, tk.E))
        frame_search.configure(style='TFrame')
        
        ttk.Label(frame_search, text="Search:", font=('Monospace', self.font_size)).grid(row=0, column=0, sticky=tk.W)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(frame_search, textvariable=self.search_var,
                                      width=45, font=('Monospace', self.font_size))
        self.search_entry.grid(row=0, column=1, padx=10)
        self.search_var.trace('w', self.on_search_change)
        self.search_entry.focus_set()

        btn_frame = ttk.Frame(frame_search)
        btn_frame.grid(row=0, column=2, padx=15)
        ttk.Button(btn_frame, text="Index Drive", style='Green.TButton',
                   command=self.index_drive).pack(side=tk.LEFT, padx=3, pady=2)
        ttk.Button(btn_frame, text="Exclude Folder", style='Red.TButton',
                   command=self.exclude_folder).pack(side=tk.LEFT, padx=3, pady=2)
        ttk.Button(btn_frame, text="Manage Exclusions", style='Blue.TButton',
                   command=self.manage_exclusions).pack(side=tk.LEFT, padx=3, pady=2)
        ttk.Button(btn_frame, text="Export CSV", style='Orange.TButton',
                   command=self.export_csv).pack(side=tk.LEFT, padx=3, pady=2)
        ttk.Button(btn_frame, text="Clear All", style='Purple.TButton',
                   command=self.clear_all_indexes).pack(side=tk.LEFT, padx=3, pady=2)

        frame_results = ttk.Frame(root, padding="15")
        frame_results.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))

        self.columns = ('Name', 'Size', 'Type', 'Drive', 'Path')
        self.tree = ttk.Treeview(frame_results, columns=self.columns,
                                 show='headings', height=28)
        
        self.tree.heading('Name', text='Name', anchor=tk.W, command=lambda: self.sort_by_column('Name'))
        self.tree.heading('Size', text='Size', anchor=tk.W, command=lambda: self.sort_by_column('Size'))
        self.tree.heading('Type', text='Type', anchor=tk.W, command=lambda: self.sort_by_column('Type'))
        self.tree.heading('Drive', text='Drive', anchor=tk.W, command=lambda: self.sort_by_column('Drive'))
        self.tree.heading('Path', text='Path', anchor=tk.W, command=lambda: self.sort_by_column('Path'))
        
        self.tree.column('Name', width=300)
        self.tree.column('Size', width=80)
        self.tree.column('Type', width=80)
        self.tree.column('Drive', width=80)
        self.tree.column('Path', width=500)
        
        # Load saved column widths
        self.load_column_widths()
        
        scrollbar = ttk.Scrollbar(frame_results, orient=tk.VERTICAL,
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Bind keyboard shortcuts for file operations
        self.tree.bind('<F2>', self.rename_selected_file)
        self.tree.bind('<Delete>', self.delete_selected_file)
        self.tree.bind('<Control-d>', self.delete_selected_file)  # Ctrl+D alternative
        self.tree.bind('<Double-Button-1>', self.on_double_click)
        self.tree.bind('<Return>', self.on_double_click)
        self.tree.bind('<Button-3>', self.show_context_menu)
        
        # Add context menu items for rename and delete
        self.tree.bind('<Button-3>', self.show_context_menu)

        self.status_var = tk.StringVar()
        self.status_var.set("Ready. Type to search. F2=rename, Del=delete")
        status = ttk.Label(root, textvariable=self.status_var,
                           relief=tk.SUNKEN, anchor=tk.W, 
                           font=('Monospace', self.font_size-2))
        status.grid(row=2, column=0, sticky=(tk.W, tk.E))

        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        frame_results.columnconfigure(0, weight=1)
        frame_results.rowconfigure(0, weight=1)

        # Save settings when app closes
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Keyboard shortcuts
        self.root.bind('<Control-f>', lambda e: self.search_entry.focus())
        self.root.bind('<Control-F>', lambda e: self.search_entry.focus())
        self.root.bind('<Escape>', self.clear_search)
        self.root.bind('<F5>', lambda e: self.refresh_all())
        self.root.bind('<Control-q>', lambda e: self.root.destroy())
        self.root.bind('<Control-Q>', lambda e: self.root.destroy())
        self.root.bind('<Control-r>', lambda e: self.rename_selected_file())  # Ctrl+R for rename
        self.root.bind('<Control-R>', lambda e: self.rename_selected_file())
        
        init_db()
        self.refresh_all()

    def sort_by_column(self, col):
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False
        self.refresh_list(self.search_var.get().strip())

    def on_search_change(self, *args):
        # Cancel previous delayed search if any
        if hasattr(self, '_search_job'):
            self.root.after_cancel(self._search_job)
        
        # Schedule new search after 300ms delay
        self._search_job = self.root.after(300, self.perform_search)

    def perform_search(self):
        term = self.search_var.get().strip()
        self.refresh_list(term)

    def refresh_list(self, term=''):
        for row in self.tree.get_children():
            self.tree.delete(row)
        results = search_files(term, limit=1000000)
        col_index = {'Name':0, 'Size':1, 'Type':2, 'Drive':3, 'Path':4}
        idx = col_index.get(self.sort_column, 0)
        results.sort(key=lambda x: x[idx], reverse=self.sort_reverse)
        for name, size, ftype, full_path in results:
            # Extract drive letter properly using the function
            drive_letter = extract_drive_letter(full_path)
                
            self.tree.insert('', tk.END, values=(
                name,
                self.format_size(size),
                ftype,
                drive_letter,
                full_path
            ))

        # Bind selection to show path
        self.tree.bind('<<TreeviewSelect>>', self.show_selected_path)

        self.status_var.set(f"Found {len(results)} files. Indexed folders: {self.get_folder_count()}")

    def show_selected_path(self, event=None):
        sel = self.tree.selection()
        if sel:
            full_path = self.tree.item(sel[0])['values'][4]
            self.status_var.set(f"Selected: {full_path}")

    def clear_search(self, event=None):
        self.search_var.set("")
        self.search_entry.focus()
        return "break"

    # ==================== FILE OPERATIONS ====================
    def rename_selected_file(self, event=None):
        """Rename selected file with F2 key"""
        sel = self.tree.selection()
        if not sel:
            return
        
        item = self.tree.item(sel[0])
        old_path = item['values'][4]
        old_name = item['values'][0]
        
        if not os.path.exists(old_path):
            messagebox.showerror("Error", f"File not found:\n{old_path}")
            return
        
        # Ask for new name
        new_name = simpledialog.askstring("Rename File", 
                                         f"Rename '{old_name}' to:",
                                         initialvalue=old_name,
                                         parent=self.root)
        
        if not new_name or new_name == old_name:
            return
        
        # Validate filename
        if not self.is_valid_filename(new_name):
            messagebox.showerror("Invalid Filename", 
                               "Filename contains invalid characters or is empty.")
            return
        
        # Create new path
        directory = os.path.dirname(old_path)
        new_path = os.path.join(directory, new_name)
        
        # Check if new name already exists
        if os.path.exists(new_path):
            response = messagebox.askyesno("File Exists", 
                                         f"A file named '{new_name}' already exists.\n"
                                         f"Overwrite?")
            if not response:
                return
        
        try:
            # Rename file
            os.rename(old_path, new_path)
            
            # Update database
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # Get file stats for update
            stat = os.stat(new_path)
            _, ext = os.path.splitext(new_name)
            
            # Update the file record
            c.execute('''UPDATE files 
                        SET path = ?, name = ?, size = ?, modified = ?, type = ?, indexed_date = ?
                        WHERE path = ?''',
                     (new_path, new_name, stat.st_size, stat.st_mtime, 
                      ext.lower(), datetime.now().timestamp(), old_path))
            
            conn.commit()
            conn.close()
            
            # Refresh display
            self.refresh_list(self.search_var.get().strip())
            
            # Select the renamed file in the list
            self.status_var.set(f"Renamed: {old_name} → {new_name}")
            
        except PermissionError:
            messagebox.showerror("Permission Error", 
                               f"Permission denied. Make sure you have write access to:\n{directory}")
        except OSError as e:
            messagebox.showerror("Rename Error", f"Could not rename file:\n{str(e)}")
        except Exception as e:
            messagebox.showerror("Rename Error", f"Unexpected error:\n{str(e)}")

    def delete_selected_file(self, event=None):
        """Delete selected file with Delete key (permanently)"""
        sel = self.tree.selection()
        if not sel:
            return
        
        item = self.tree.item(sel[0])
        file_path = item['values'][4]
        file_name = item['values'][0]
        
        if not os.path.exists(file_path):
            messagebox.showerror("Error", f"File not found:\n{file_path}")
            return
        
        # Confirm deletion with more options
        response = self.show_delete_confirmation(file_name, file_path)
        
        if response == "cancel":
            return
        
        try:
            if response == "permanent":
                # Delete file permanently
                os.remove(file_path)
                action = "Permanently deleted"
            elif response == "trash":
                # Try to move to trash (Linux)
                try:
                    # Try using gio trash command (GNOME)
                    import subprocess
                    subprocess.run(['gio', 'trash', file_path], check=True)
                    action = "Moved to trash"
                except:
                    # Fallback to rename to .trash folder
                    trash_dir = os.path.expanduser('~/.local/share/Trash/files')
                    os.makedirs(trash_dir, exist_ok=True)
                    trash_path = os.path.join(trash_dir, os.path.basename(file_path))
                    counter = 1
                    while os.path.exists(trash_path):
                        name, ext = os.path.splitext(os.path.basename(file_path))
                        trash_path = os.path.join(trash_dir, f"{name} ({counter}){ext}")
                        counter += 1
                    shutil.move(file_path, trash_path)
                    action = "Moved to trash"
            
            # Update database - remove the file entry
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM files WHERE path = ?", (file_path,))
            
            # Also check if we need to update the folder's indexed_date
            folder = os.path.dirname(file_path)
            c.execute('''UPDATE folders SET excluded = excluded 
                        WHERE path = ?''', (folder,))
            
            conn.commit()
            conn.close()
            
            # Remove from treeview and refresh
            self.tree.delete(sel[0])
            self.status_var.set(f"{action}: {file_name}")
            
        except PermissionError:
            messagebox.showerror("Permission Error", 
                               f"Permission denied. Make sure you have write access to the file.")
        except OSError as e:
            messagebox.showerror("Delete Error", f"Could not delete file:\n{str(e)}")
        except Exception as e:
            messagebox.showerror("Delete Error", f"Unexpected error:\n{str(e)}")

    def show_delete_confirmation(self, filename, filepath):
        """Show enhanced delete confirmation dialog with options"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Confirm Delete")
        dialog.geometry("500x250")
        dialog.configure(bg='#0A0A0A')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Try to set opacity
        try:
            dialog.attributes('-alpha', 0.97)
        except:
            pass
        
        result = {"choice": "cancel"}
        
        def set_choice(choice):
            result["choice"] = choice
            dialog.destroy()
        
        # Title
        tk.Label(dialog, text=f"Delete '{filename}'?", 
                font=('Monospace', self.font_size, 'bold'),
                bg='#0A0A0A', fg='#FF5555').pack(pady=(20, 10))
        
        # File path
        path_label = tk.Label(dialog, text=f"Path: {filepath}", 
                             font=('Monospace', self.font_size-2),
                             bg='#0A0A0A', fg='#AAAAAA',
                             wraplength=450, justify='left')
        path_label.pack(pady=(0, 20))
        
        # Warning
        tk.Label(dialog, text="This action cannot be undone!", 
                font=('Monospace', self.font_size-2),
                bg='#0A0A0A', fg='#FFAA00').pack(pady=(0, 20))
        
        # Button frame
        btn_frame = tk.Frame(dialog, bg='#0A0A0A')
        btn_frame.pack(pady=10)
        
        # Buttons
        tk.Button(btn_frame, text="Move to Trash", 
                 command=lambda: set_choice("trash"),
                 font=('Monospace', self.font_size-2),
                 bg='#0A0A0A', fg='#00FF00',
                 activebackground='#003300', activeforeground='#00FF00',
                 width=15).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Delete Permanently", 
                 command=lambda: set_choice("permanent"),
                 font=('Monospace', self.font_size-2),
                 bg='#0A0A0A', fg='#FF5555',
                 activebackground='#330000', activeforeground='#FF5555',
                 width=15).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Cancel", 
                 command=lambda: set_choice("cancel"),
                 font=('Monospace', self.font_size-2),
                 bg='#0A0A0A', fg='#AAAAAA',
                 activebackground='#003300', activeforeground='#AAAAAA',
                 width=10).pack(side=tk.LEFT, padx=5)
        
        # Center dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        self.root.wait_window(dialog)
        return result["choice"]

    def is_valid_filename(self, filename):
        """Check if filename is valid"""
        if not filename or not filename.strip():
            return False
        
        # Check for invalid characters (basic check)
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in invalid_chars:
            if char in filename:
                return False
        
        # Check for reserved names
        reserved_names = ['CON', 'PRN', 'AUX', 'NUL', 
                         'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
                         'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']
        if filename.upper() in reserved_names:
            return False
        
        return True
    
    def load_column_widths(self):
        """Load saved column widths and sort settings"""
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    widths = json.load(f)
                    for col, width in widths.items():
                        if col in self.columns:
                            self.tree.column(col, width=width)
                    # Load sort settings
                    self.sort_column = widths.get('sort_column', 'name')
                    self.sort_reverse = widths.get('sort_reverse', False)
        except:
            pass  # Use defaults if load fails
    
    def save_column_widths(self):
        """Save current column widths and sort settings"""
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            widths = {col: self.tree.column(col, 'width') for col in self.columns}
            # Add sort settings
            widths['sort_column'] = self.sort_column
            widths['sort_reverse'] = self.sort_reverse
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(widths, f)
        except:
            pass  # Don't crash if save fails
    
    def on_closing(self):
        """Save settings when app closes"""
        self.save_column_widths()
        self.root.destroy()

    def index_drive(self):
        initial_dir = '/media' if os.path.exists('/media') else '/'
        folder = filedialog.askdirectory(
            title="Select a drive/folder to index",
            initialdir=initial_dir
        )
        if folder:
            def do_index():
                self.status_var.set("Indexing...")
                success, msg = index_folder(folder, cleanup=False)
                self.status_var.set(msg)
                self.refresh_list(self.search_var.get().strip())
            Thread(target=do_index, daemon=True).start()

    def exclude_folder(self):
        initial_dir = '/media' if os.path.exists('/media') else '/'
        folder = filedialog.askdirectory(
            title="Select folder to exclude (and all its subfolders)",
            initialdir=initial_dir
        )
        if folder:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id FROM folders WHERE path = ?", (folder,))
            row = c.fetchone()
            
            if row:
                c.execute("UPDATE folders SET excluded = 'EXCLUDED' WHERE id = ?", (row[0],))
                c.execute("DELETE FROM files WHERE folder_id = ?", (row[0],))
            else:
                c.execute("INSERT INTO folders (path, excluded) VALUES (?, 'EXCLUDED')", (folder,))
            
            conn.commit()
            conn.close()
            
            self.status_var.set(f"Excluded folder: {os.path.basename(folder)}")
            self.refresh_list(self.search_var.get().strip())

    def manage_exclusions(self):
        win = tk.Toplevel(self.root)
        win.title("Manage Excluded Folders")
        win.geometry("700x450")
        win.configure(bg='#0A0A0A')
        try:
            win.attributes('-alpha', 0.95)
        except:
            pass
        
        tk.Label(win, text="Excluded folders (will not be indexed):", 
                font=('Monospace', self.font_size),
                bg='#0A0A0A', fg='#00FF00').pack(pady=15)
        
        list_frame = tk.Frame(win, bg='#0A0A0A')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        lb = Listbox(list_frame, selectmode=tk.SINGLE, yscrollcommand=scrollbar.set,
                     font=('Monospace', self.tree_font_size), 
                     bg='#0A0A0A', fg='#00FF00',
                     selectbackground='#004400', selectforeground='#00FF00')
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=lb.yview)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT path FROM folders WHERE excluded = 'EXCLUDED'")
        rows = c.fetchall()
        conn.close()
        
        for row in rows:
            lb.insert(tk.END, row[0])
        if not rows:
            lb.insert(tk.END, "(No excluded folders)")
        
        def remove_exclusion():
            sel = lb.curselection()
            if sel:
                folder = lb.get(sel[0])
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE folders SET excluded = '' WHERE path = ?", (folder,))
                conn.commit()
                conn.close()
                lb.delete(sel[0])
                self.status_var.set(f"Removed exclusion: {os.path.basename(folder)}")
                self.refresh_list(self.search_var.get().strip())
        
        btn_frame = tk.Frame(win, bg='#0A0A0A')
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="Remove Exclusion", command=remove_exclusion,
                  font=('Monospace', self.font_size-2),
                  bg='#0A0A0A', fg='#00FF00',
                  activebackground='#003300', activeforeground='#00FF00').pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Close", command=win.destroy,
                  font=('Monospace', self.font_size-2),
                  bg='#0A0A0A', fg='#00FF00',
                  activebackground='#003300', activeforeground='#00FF00').pack(side=tk.LEFT, padx=5)

    def export_csv(self):
        term = self.search_var.get().strip()
        results = search_files(term, limit=None)
        if not results:
            messagebox.showwarning("No Data", "Nothing to export.")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".csv",
                                                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Name', 'Size (bytes)', 'Type', 'Drive', 'Path'])
                    for row in results:
                        name, size, ftype, full_path = row
                        drive_letter = extract_drive_letter(full_path)
                        writer.writerow([name, size, ftype, drive_letter, full_path])
                messagebox.showinfo("Export Successful", f"Exported {len(results)} rows to\n{filename}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))

    def clear_all_indexes(self):
        if messagebox.askyesno("Clear All Indexes",
                               "This will delete ALL indexed files and folders.\n"
                               "This action cannot be undone.\n\nProceed?"):
            try:
                # Delete database and settings
                if os.path.exists(DB_PATH):
                    os.remove(DB_PATH)
                if os.path.exists(SETTINGS_FILE):
                    os.remove(SETTINGS_FILE)
                
                # Reinitialize
                init_db()
                self.refresh_all()
                messagebox.showinfo("Cleared", "All indexes have been removed.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not clear database:\n{e}")

    def refresh_all(self):
        self.refresh_list(self.search_var.get().strip())

    def on_double_click(self, event=None):
        self.open_selected()

    def open_selected(self):
        sel = self.tree.selection()
        if sel:
            full_path = self.tree.item(sel[0])['values'][4]
            if full_path and os.path.exists(full_path):
                os.system(f'xdg-open "{full_path}"')
            else:
                messagebox.showinfo("File Not Found",
                                    f"File not found: {full_path}")

    def show_context_menu(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        
        menu = Menu(self.root, tearoff=0, 
                   font=('Monospace', self.font_size-2),
                   bg='#0A0A0A', fg='#00FF00',
                   activebackground='#003300', activeforeground='#00FF00')
        
        menu.add_command(label="Open", command=self.open_selected)
        menu.add_separator()
        
        # Add Rename and Delete to context menu
        menu.add_command(label="Rename (F2)", command=lambda: self.rename_selected_file())
        menu.add_command(label="Delete (Del)", command=lambda: self.delete_selected_file())
        menu.add_separator()
        
        menu.add_command(label="Rescan This Folder", command=self.rescan_folder)
        menu.add_command(label="Rescan This Folder with Cleanup", command=self.rescan_cleanup)
        menu.add_command(label="Rescan Entire Drive", command=self.rescan_entire_drive)
        menu.add_command(label="Rescan Entire Drive with Cleanup", command=self.rescan_entire_drive_cleanup)
        menu.add_separator()
        menu.add_command(label="Exclude This Folder", command=self.exclude_this_folder)
        menu.add_command(label="Exclude Subfolder...", command=self.exclude_subfolder)
        menu.tk_popup(event.x_root, event.y_root)

    def rescan_folder(self):
        sel = self.tree.selection()
        if sel:
            full_path = self.tree.item(sel[0])['values'][4]
            if full_path:
                folder = os.path.dirname(full_path)
                def do_rescan():
                    self.status_var.set(f"Rescanning {folder}...")
                    success, msg = index_folder(folder, cleanup=False)
                    self.status_var.set(msg)
                    self.refresh_list(self.search_var.get().strip())
                Thread(target=do_rescan, daemon=True).start()

    def rescan_cleanup(self):
        sel = self.tree.selection()
        if sel:
            full_path = self.tree.item(sel[0])['values'][4]
            if full_path:
                folder = os.path.dirname(full_path)
                def do_rescan():
                    self.status_var.set(f"Rescanning (cleanup) {folder}...")
                    success, msg = index_folder(folder, cleanup=True)
                    self.status_var.set(msg)
                    self.refresh_list(self.search_var.get().strip())
                Thread(target=do_rescan, daemon=True).start()

    def rescan_entire_drive(self):
        sel = self.tree.selection()
        if sel:
            full_path = self.tree.item(sel[0])['values'][4]
            if full_path:
                if '/media/' in full_path:
                    parts = full_path.split('/')
                    if len(parts) >= 4:
                        drive_root = '/'.join(parts[:4])
                    else:
                        drive_root = full_path
                else:
                    drive_root = '/' + full_path.split('/')[1] if '/' in full_path else full_path
                
                def do_rescan():
                    self.status_var.set(f"Rescanning entire drive {os.path.basename(drive_root)}...")
                    success, msg = rescan_drive(drive_root, cleanup=False)
                    self.status_var.set(msg)
                    self.refresh_list(self.search_var.get().strip())
                Thread(target=do_rescan, daemon=True).start()

    def rescan_entire_drive_cleanup(self):
        sel = self.tree.selection()
        if sel:
            full_path = self.tree.item(sel[0])['values'][4]
            if full_path:
                if '/media/' in full_path:
                    parts = full_path.split('/')
                    if len(parts) >= 4:
                        drive_root = '/'.join(parts[:4])
                    else:
                        drive_root = full_path
                else:
                    drive_root = '/' + full_path.split('/')[1] if '/' in full_path else full_path
                
                def do_rescan():
                    self.status_var.set(f"Rescanning entire drive {os.path.basename(drive_root)} (cleanup)...")
                    success, msg = rescan_drive(drive_root, cleanup=True)
                    self.status_var.set(msg)
                    self.refresh_list(self.search_var.get().strip())
                Thread(target=do_rescan, daemon=True).start()

    def exclude_subfolder(self):
        sel = self.tree.selection()
        if sel:
            full_path = self.tree.item(sel[0])['values'][4]
            if full_path:
                folder = os.path.dirname(full_path)
                sub = filedialog.askdirectory(title="Select subfolder to exclude", initialdir=folder)
                if sub:
                    rel = os.path.relpath(sub, folder)
                    update_excluded(folder, rel)
                    self.status_var.set(f"Excluded subfolder: {rel}")
                    self.refresh_list(self.search_var.get().strip())

    def exclude_this_folder(self):
        sel = self.tree.selection()
        if sel:
            full_path = self.tree.item(sel[0])['values'][4]
            if full_path:
                folder = os.path.dirname(full_path)
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT id FROM folders WHERE path = ?", (folder,))
                folder_row = c.fetchone()
                if folder_row:
                    folder_id = folder_row[0]
                    c.execute("UPDATE folders SET excluded = 'EXCLUDED' WHERE id = ?", (folder_id,))
                    c.execute("DELETE FROM files WHERE folder_id = ?", (folder_id,))
                    conn.commit()
                
                conn.close()
                self.status_var.set(f"Excluded folder: {os.path.basename(folder)}")
                self.refresh_list(self.search_var.get().strip())

    def get_folder_count(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM folders WHERE excluded != 'EXCLUDED'")
        count = c.fetchone()[0]
        conn.close()
        return count

    @staticmethod
    def format_size(size):
        if size == 0:
            return "0 B"
        
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        for unit in units:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    @staticmethod
    def parse_size(size_str):
        size_str = size_str.strip()
        
        units = {
            'B': 1,
            'KB': 1024,
            'MB': 1024**2,
            'GB': 1024**3,
            'TB': 1024**4,
            'PB': 1024**5
        }
        
        for unit, multiplier in units.items():
            if size_str.upper().endswith(unit):
                num_part = size_str[:-len(unit)].strip()
                try:
                    num = float(num_part)
                    return int(num * multiplier)
                except ValueError:
                    try:
                        return int(float(size_str))
                    except:
                        return 0
        
        try:
            return int(float(size_str))
        except:
            return 0

def main():
    """Main entry point for the application"""
    root = tk.Tk()
    app = EverythingApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
