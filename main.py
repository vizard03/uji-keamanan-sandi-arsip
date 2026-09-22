# ==============================================================================
# APLIKASI UJI PEMULIHAN PIN
# ==============================================================================

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Toplevel, scrolledtext, Menu
import os
import time
import platform
import subprocess
import shutil
import tempfile
from threading import Thread
from queue import Queue, Empty
import logging
import string
import random
import sys
from datetime import datetime
import locale
import csv
import sqlite3
from collections import Counter

# Import pustaka pihak ketiga (pastikan sudah diinstal)
try:
    from ttkthemes import ThemedTk
    import py7zr
    import zipfile
    import rarfile
    import PyPDF2
    import pyminizip

    # PERBAIKAN BUG: Set backend matplotlib ke 'Agg' untuk menghindari error threading GUI
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    from reportlab.platypus import SimpleDocTemplate, Image as ReportlabImage, Paragraph, Spacer, PageBreak, Table, TableStyle, Preformatted
    from reportlab.lib.pagesizes import letter, legal
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.lib.colors import HexColor, black
    from PIL import Image as PILImage, ImageTk
    import qrcode
    
    # Pustaka BARU untuk laporan kinerja
    import psutil
    import cpuinfo
except ImportError as e:
    messagebox.showerror("Pustaka Hilang", f"Error: Pustaka yang dibutuhkan tidak ditemukan.\n{e}\n\nSilakan instal semua dependensi yang diperlukan, contoh: 'pip install ttkthemes py7zr rarfile PyPDF2 pyminizip reportlab Pillow qrcode matplotlib psutil py-cpuinfo'.")
    sys.exit(1)

# ==============================================================================
# KONFIGURASI APLIKASI
# ==============================================================================
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
ASSET_DIR = os.path.join(BASE_DIR, "asset", "img")
DATABASE_DIR = os.path.join(BASE_DIR, "database")
DB_PATH = os.path.join(DATABASE_DIR, 'pin_dictionary.db')


# ==============================================================================
# KELAS UTAMA APLIKASI
# ==============================================================================
class App(ThemedTk):
    def __init__(self):
        super().__init__()
        self.set_theme("arc") 
        self.title("Aplikasi Uji Pemulihan PIN")
        self.geometry("1000x800")
        self.minsize(850, 650)
        
        self.user_name = tk.StringVar()
        self.cracking_in_progress = False
        self.file_counter = 0
        self.files_processed_count = 0
        self.total_files_to_process = 0
        self.results_data = []
        self.active_threads = []
        
        # Variabel untuk Laporan Kinerja
        self.system_info = {}
        self.monitoring_active = False
        self.cpu_usage_history = []
        self.memory_usage_history = []
        
        self.log_after_id = None
        self.typewriter_after_id = None
        
        self.result_queue = Queue()
        self.log_queue = Queue()

        self.setup_logging()
        self.initialize_database()
        self.create_welcome_screen()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def initialize_database(self):
        """Memastikan database dan tabel log ada, dan mengambil ID terakhir."""
        try:
            os.makedirs(DATABASE_DIR, exist_ok=True)
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS log_hasil_uji (
                    id INTEGER PRIMARY KEY,
                    nama_file TEXT,
                    tipe TEXT,
                    status TEXT,
                    pin_ditemukan TEXT,
                    timestamp TEXT
                )
            ''')
            cursor.execute("SELECT MAX(id) FROM log_hasil_uji")
            last_id = cursor.fetchone()[0]
            self.file_counter = last_id if last_id is not None else 0
            conn.commit()
            conn.close()
            self.logger.info(f"Database berhasil diinisialisasi. ID berikutnya: {self.file_counter + 1}")
        except sqlite3.Error as e:
            self.logger.error(f"Gagal inisialisasi database: {e}")
            messagebox.showerror("Error Database", f"Tidak dapat menginisialisasi database: {e}")

    def create_welcome_screen(self):
        self.welcome_frame = ttk.Frame(self, padding="20")
        self.welcome_frame.pack(expand=True, fill=tk.BOTH)
        center_frame = ttk.Frame(self.welcome_frame)
        center_frame.place(relx=0.5, rely=0.45, anchor=tk.CENTER)

        try:
            logo_path = os.path.join(ASSET_DIR, "logo.png")
            if os.path.exists(logo_path):
                img = PILImage.open(logo_path).resize((80, 80), PILImage.Resampling.LANCZOS)
                self.welcome_logo_img = ImageTk.PhotoImage(img)
                logo_label = ttk.Label(center_frame, image=self.welcome_logo_img)
                logo_label.pack(pady=(0, 20))
        except Exception as e:
            self.logger.warning(f"Gagal memuat logo untuk welcome screen: {e}")

        self.welcome_label = ttk.Label(center_frame, text="", font=("Segoe UI", 24, "bold"))
        self.welcome_label.pack(pady=10)
        
        self.name_entry = ttk.Entry(center_frame, textvariable=self.user_name, font=("Segoe UI", 12), width=30, justify='center')
        self.start_button = ttk.Button(center_frame, text="Mulai", command=self.start_application, state="disabled")
        
        self.placeholder_text = "Masukkan Nama Anda"
        self.placeholder_color = 'grey'
        self.default_fg_color = self.name_entry.cget("foreground")

        self.run_typewriter_effect("Halo, Silahkan Isi Nama Anda", self.welcome_label, self.show_name_input)

    def set_placeholder(self):
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, self.placeholder_text)
        self.name_entry.config(foreground=self.placeholder_color)

    def on_entry_focus_in(self, event):
        if self.name_entry.get() == self.placeholder_text:
            self.name_entry.delete(0, tk.END)
            self.name_entry.config(foreground=self.default_fg_color)

    def on_entry_focus_out(self, event):
        if not self.name_entry.get():
            self.set_placeholder()

    def show_name_input(self):
        self.name_entry.pack(pady=20, ipady=5)
        self.set_placeholder()
        self.name_entry.bind("<FocusIn>", self.on_entry_focus_in)
        self.name_entry.bind("<FocusOut>", self.on_entry_focus_out)
        
        self.start_button.pack(pady=20, ipady=5, ipadx=10)
        self.start_button.config(state="normal")
        self.bind('<Return>', lambda event: self.start_application())

    def start_application(self):
        user_input = self.name_entry.get().strip()
        if not user_input or user_input == self.placeholder_text:
            messagebox.showwarning("Nama Kosong", "Nama tidak boleh kosong.", parent=self.welcome_frame)
            return
        
        self.user_name.set(user_input)
        self.unbind('<Return>')
        for widget in self.welcome_frame.winfo_children():
            widget.destroy()
        
        center_frame = ttk.Frame(self.welcome_frame)
        center_frame.place(relx=0.5, rely=0.4, anchor=tk.CENTER)
        self.welcome_label = ttk.Label(center_frame, text="Memuat aplikasi...", font=("Segoe UI", 24, "bold"))
        self.welcome_label.pack(pady=10)
        
        self.update_idletasks()
        self.after(1500, self.initialize_main_app)

    def run_typewriter_effect(self, text, widget, callback=None):
        self.current_text = ""
        self.target_text = text
        self.widget_to_update = widget
        self.callback_on_done = callback
        self._typewriter_step(0)

    def _typewriter_step(self, index):
        if index < len(self.target_text):
            self.current_text += self.target_text[index]
            self.widget_to_update.config(text=self.current_text)
            self.typewriter_after_id = self.after(50, self._typewriter_step, index + 1)
        elif self.callback_on_done:
            self.callback_on_done()

    def initialize_main_app(self):
        self.run_typewriter_effect(f"Selamat datang, {self.user_name.get()}", self.welcome_label, self.transition_to_main_ui)

    def transition_to_main_ui(self):
        self.after(1000, lambda: self.welcome_frame.destroy())
        self.after(1000, self.build_main_ui)
        
    def build_main_ui(self):
        self.title(f"Aplikasi Uji Pemulihan PIN - [{self.user_name.get()}]")
        self.collect_system_info()
        self.create_menu()
        self.create_main_containers()
        self.process_ui_queue()

    def on_closing(self):
        if messagebox.askokcancel("Keluar", "Anda yakin ingin keluar dari aplikasi?"):
            self.cracking_in_progress = False
            self.monitoring_active = False # Hentikan monitoring
            time.sleep(0.2)
            if self.log_after_id: self.after_cancel(self.log_after_id)
            if self.typewriter_after_id: self.after_cancel(self.typewriter_after_id)
            self.destroy()

    def setup_logging(self):
        log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
        file_handler = logging.FileHandler('activity_log.txt', mode='a', encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setFormatter(log_formatter)
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        if self.logger.hasHandlers(): self.logger.handlers.clear()
        self.logger.addHandler(file_handler)
        self.logger.addHandler(queue_handler)

    def process_ui_queue(self):
        try:
            while True:
                message = self.result_queue.get_nowait()
                self.handle_result(message)
        except Empty:
            pass

        while not self.log_queue.empty():
            try:
                record = self.log_queue.get_nowait()
                self.log_text.config(state='normal')
                self.log_text.insert(tk.END, record)
                self.log_text.see(tk.END)
                self.log_text.config(state='disabled')
            except Empty:
                break
        
        self.log_after_id = self.after(100, self.process_ui_queue)

    def create_menu(self):
        menubar = Menu(self)
        self.config(menu=menubar)
        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Hapus Log Aktivitas", command=self.clear_log_file)
        file_menu.add_separator()
        file_menu.add_command(label="Keluar", command=self.on_closing)
        menubar.add_cascade(label="File", menu=file_menu)

    def clear_log_file(self):
        if messagebox.askyesno("Konfirmasi", "Anda yakin ingin menghapus seluruh isi file 'activity_log.txt'?"):
            try:
                with open('activity_log.txt', 'w'): pass
                self.logger.info("File activity_log.txt telah dibersihkan.")
            except Exception as e:
                messagebox.showerror("Error", f"Gagal menghapus log: {e}")

    def create_main_containers(self):
        self.main_view_frame = ttk.Frame(self, padding="10")
        self.analysis_view_frame = AnalysisView(self, self, self.user_name)
        self.frequency_view_frame = FrequencyView(self)
        self.performance_view_frame = SystemPerformanceView(self)
        
        self.create_bottom_bar()
        self.main_view_frame.pack(fill=tk.BOTH, expand=True)
        self.build_main_view_widgets(self.main_view_frame)

    def build_main_view_widgets(self, parent_frame):
        parent_frame.grid_rowconfigure(0, weight=1)
        parent_frame.grid_columnconfigure(1, weight=1)
        control_panel = ttk.LabelFrame(parent_frame, text="Kontrol & Opsi", padding="10")
        control_panel.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        
        ttk.Label(control_panel, text="Pilih Format File:").pack(anchor="w", pady=(0, 5))
        self.format_var = tk.StringVar(value="ZIP")
        format_dropdown = ttk.Combobox(control_panel, textvariable=self.format_var, values=["ZIP", "RAR", "PDF", "7Z"], state="readonly")
        format_dropdown.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(control_panel, text="Pilihan Brute Force:").pack(anchor="w", pady=(10, 5))
        self.brute_force_mode = tk.StringVar(value="4 PIN")
        brute_force_dropdown = ttk.Combobox(control_panel, textvariable=self.brute_force_mode, values=["4 PIN", "6 PIN"], state="readonly")
        brute_force_dropdown.pack(fill=tk.X, pady=(0, 10))

        self.add_file_btn = ttk.Button(control_panel, text="Tambah File", command=self.add_file)
        self.add_file_btn.pack(fill=tk.X, pady=(15, 5))
        self.remove_file_btn = ttk.Button(control_panel, text="Hapus File Terpilih", command=self.remove_selected_file)
        self.remove_file_btn.pack(fill=tk.X, pady=5)
        self.clear_all_btn = ttk.Button(control_panel, text="Bersihkan Semua", command=self.clear_all_files)
        self.clear_all_btn.pack(fill=tk.X, pady=5)
        
        self.save_csv_btn = ttk.Button(control_panel, text="Simpan Hasil (CSV)", command=self.save_results_to_csv, state="disabled")
        self.save_csv_btn.pack(fill=tk.X, pady=5)
        
        self.extract_btn = ttk.Button(control_panel, text="Ekstrak Terpilih", command=self.extract_selected_files, state="disabled")
        self.extract_btn.pack(fill=tk.X, pady=(10,5))

        ttk.Separator(control_panel, orient='horizontal').pack(fill=tk.X, pady=15)
        self.deep_crack_var = tk.BooleanVar(value=True)
        self.deep_crack_chk = ttk.Checkbutton(control_panel, text="Deep Crack (Nested)", variable=self.deep_crack_var)
        self.deep_crack_chk.pack(anchor="w", pady=5)
        
        self.action_frame = ttk.Frame(control_panel)
        self.action_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)
        
        self.recovery_options_btn = ttk.Button(self.action_frame, text="Amankan File Terpilih", command=self.show_multi_recovery_dialog, state="disabled")
        self.recovery_options_btn.pack(fill=tk.X, pady=(10, 5))
        
        self.start_btn = ttk.Button(self.action_frame, text="Mulai Uji", command=self.toggle_cracking)
        self.start_btn.pack(fill=tk.X, ipady=5)
        
        right_pane = ttk.Frame(parent_frame)
        right_pane.grid(row=0, column=1, sticky="nsew")
        right_pane.grid_rowconfigure(0, weight=2); right_pane.grid_rowconfigure(2, weight=1)
        
        file_area_frame = ttk.LabelFrame(right_pane, text="Daftar File Uji", padding="10")
        file_area_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        file_area_frame.grid_rowconfigure(0, weight=1); file_area_frame.grid_columnconfigure(0, weight=1)
        
        columns = ('select', 'id', 'filename', 'type', 'status', 'password')
        self.tree = ttk.Treeview(file_area_frame, columns=columns, show='headings')
        self.tree.heading('select', text='Pilih'); self.tree.column('select', width=40, anchor='center', stretch=tk.NO)
        self.tree.heading('id', text='ID'); self.tree.column('id', width=40, anchor='center', stretch=tk.NO)
        self.tree.heading('filename', text='Nama File'); self.tree.column('filename', width=250)
        self.tree.heading('type', text='Tipe'); self.tree.column('type', width=60, stretch=tk.NO)
        self.tree.heading('status', text='Status'); self.tree.column('status', width=150)
        self.tree.heading('password', text='PIN Ditemukan'); self.tree.column('password', width=120)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tree_scrollbar = ttk.Scrollbar(file_area_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scrollbar.set)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.unchecked_char = '☐'
        self.checked_char = '☑'
        self.tree.tag_configure('checked', foreground='green')
        self.tree.bind('<Button-1>', self.toggle_checkbox)
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        
        self.progress_bar = ttk.Progressbar(right_pane, orient='horizontal', mode='determinate')
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(5, 5))

        log_frame = ttk.LabelFrame(right_pane, text="Log Aktivitas Real-time", padding="10")
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1); log_frame.grid_columnconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state='disabled', font=("Consolas", 9), wrap="word")
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def start_cracking(self):
        if self.cracking_in_progress:
            messagebox.showwarning("Proses Berjalan", "Proses pengujian sudah berjalan.")
            return
            
        files_to_process_items = []
        for item_id in self.tree.get_children():
            current_status = self.tree.item(item_id, 'values')[4]
            if "Berhasil" not in current_status and "Tidak Terenkripsi" not in current_status:
                files_to_process_items.append(item_id)
        
        if not files_to_process_items:
            messagebox.showinfo("Informasi", "Semua file dalam daftar sudah berhasil diuji atau tidak terenkripsi.", parent=self)
            return
        
        self.set_ui_state(True)
        self.results_data.clear()
        
        # Mulai monitoring kinerja
        self.cpu_usage_history.clear()
        self.memory_usage_history.clear()
        self.monitoring_active = True
        Thread(target=self._monitor_performance, daemon=True).start()
        
        self.files_processed_count = 0
        self.total_files_to_process = len(files_to_process_items)
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = self.total_files_to_process
        
        self.logger.info("="*40 + " PROSES UJI DIMULAI " + "="*40)
        
        self.active_threads = []
        for item_id in files_to_process_items:
            self.tree.set(item_id, 'status', 'Mengantri...')
            self.tree.set(item_id, 'password', '-')
            file_path = self.tree.item(item_id, 'tags')[0]
            thread = Thread(target=self.crack_file, args=(item_id, file_path), daemon=True)
            self.active_threads.append(thread)
            thread.start()
            
        self.after(100, self.check_all_threads_done)

    def _monitor_performance(self):
        """Thread untuk memonitor penggunaan CPU dan RAM selama pengujian."""
        self.logger.info("Monitoring kinerja sistem dimulai.")
        while self.monitoring_active:
            try:
                cpu = psutil.cpu_percent(interval=1)
                mem = psutil.virtual_memory().percent
                if not self.monitoring_active: break # Cek lagi setelah interval
                self.cpu_usage_history.append(cpu)
                self.memory_usage_history.append(mem)
            except psutil.NoSuchProcess:
                break # Proses utama mungkin sudah ditutup
        self.logger.info("Monitoring kinerja sistem berhenti.")

    def crack_file(self, item_id, file_path):
        self.result_queue.put({'type': 'status_update', 'item_id': item_id, 'status': 'Memproses...'})
        file_type = self.tree.item(item_id, 'values')[3]
        self.logger.info(f"Memulai uji untuk: {os.path.basename(file_path)}")
        start_time = time.time()
        
        password, attempts, encryption_type = None, 0, "Tidak diketahui"
        file_size = 0

        try:
            file_size = os.path.getsize(file_path)
        except FileNotFoundError:
            self.logger.error(f"File tidak ditemukan: {file_path}")
            self.result_queue.put({'type': 'result', 'item_id': item_id, 'password': None, 'duration': 0, 'attempts': 0, 'encryption_type': 'File Hilang', 'file_path': file_path, 'file_type': file_type, 'file_size': 0})
            return

        crack_function_map = {'ZIP': self.brute_force_zip, 'RAR': self.brute_force_rar, 'PDF': self.brute_force_pdf, '7Z': self.brute_force_7z}
        crack_function = crack_function_map.get(file_type)
        
        if crack_function:
            password, attempts, encryption_type = crack_function(file_path)
        
        duration = time.time() - start_time
        
        result_package = {
            'type': 'result', 'item_id': item_id, 'file_path': file_path, 'file_type': file_type,
            'file_size': file_size, 'password': password, 'duration': duration, 'attempts': attempts,
            'encryption_type': encryption_type
        }
        self.result_queue.put(result_package)

    def handle_result(self, message):
        msg_type = message.get('type')
        item_id = message.get('item_id')

        if not self.tree.exists(item_id): return

        if msg_type == 'status_update':
            self.tree.set(item_id, 'status', message.get('status', ''))
            return
            
        if msg_type == 'result':
            self.files_processed_count += 1
            self.progress_bar['value'] = self.files_processed_count
            
            password = message.get('password')
            duration = message.get('duration', 0)
            attempts = message.get('attempts', 0)
            
            status_text = f"Berhasil ({duration:.2f} d)" if password is not None and password != "" else f"Gagal ({duration:.2f} d)"
            if password == "": status_text = "Tidak Terenkripsi"
            if message.get('encryption_type') == 'File Hilang': status_text = 'File Hilang'

            self.tree.set(item_id, 'status', status_text)
            
            if password is not None and password != "":
                self.tree.set(item_id, 'password', password)
                self.logger.info(f"SUKSES! PIN untuk '{os.path.basename(message['file_path'])}' -> '{password}'. Percobaan: {attempts}. Durasi: {duration:.2f} detik.")
            elif password is None:
                self.logger.error(f"GAGAL! PIN untuk '{os.path.basename(message['file_path'])}' tidak ditemukan setelah {attempts} percobaan. Durasi: {duration:.2f} detik.")

            result_for_log = {
                'id': int(item_id),
                'nama_file': os.path.basename(message['file_path']),
                'tipe': message['file_type'],
                'status': "Berhasil" if password is not None and password != "" else "Gagal",
                'pin_ditemukan': password if password is not None and password != "" else "-",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            if status_text == "Tidak Terenkripsi":
                result_for_log['status'] = "Tidak Terenkripsi"

            self.log_result_to_db(result_for_log)

            if os.path.exists(message['file_path']):
                self.results_data.append({
                    'Nama File': result_for_log['nama_file'], 'Tipe File': result_for_log['tipe'],
                    'Ukuran File': f"{message['file_size'] / 1024:.2f} KB", 'Status Uji': result_for_log['status'],
                    'PIN Ditemukan': result_for_log['pin_ditemukan'], 'Durasi Proses': f"{duration:.2f}",
                    'Total Percobaan': attempts, 'Jenis Enkripsi': message['encryption_type'],
                    'Waktu Modifikasi': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(message['file_path'])))
                })
    
    def log_result_to_db(self, data):
        """Menyimpan hasil pengujian ke database SQLite."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO log_hasil_uji (id, nama_file, tipe, status, pin_ditemukan, timestamp)
                VALUES (:id, :nama_file, :tipe, :status, :pin_ditemukan, :timestamp)
            ''', data)
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            self.logger.error(f"Gagal menyimpan log ke database: {e}")

    def load_common_pins(self, mode):
        fallback_pins = ['1234', '0000', '1111', '123456', '654321', 'password']

        if not os.path.exists(DB_PATH):
            self.logger.warning("Database 'pin_dictionary.db' tidak ditemukan. Menggunakan daftar PIN default.")
            return fallback_pins

        table_name = 'pin_4digit' if mode == "4 PIN" else 'pin_6digit'
        
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(f"SELECT pin FROM {table_name}")
            pins = [item[0] for item in cursor.fetchall()]
            conn.close()
            return pins
        except sqlite3.Error as e:
            self.logger.error(f"Gagal mengakses database SQLite: {e}. Menggunakan daftar PIN default.")
            return fallback_pins

    def try_passwords(self, test_function):
        attempts = 0
        common_pins_list = self.load_common_pins(self.brute_force_mode.get())
        common_pins_set = set(map(str, common_pins_list))
        
        self.logger.info("Memulai dengan dictionary list...")
        for pin in common_pins_list:
            if not self.cracking_in_progress: return None, attempts
            attempts += 1
            if test_function(str(pin)):
                self.logger.info("Pin ditemukan dari dictionary list.")
                return str(pin), attempts
        
        mode = self.brute_force_mode.get()
        self.logger.info(f"Pengujian dictionary list selesai. Melanjutkan dengan mode brute force {mode}.")
        pin_range = 10000 if mode == "4 PIN" else 1000000
        pin_format = "{:04d}" if mode == "4 PIN" else "{:06d}"

        for i in range(pin_range):
            if not self.cracking_in_progress: return None, attempts
            pin = pin_format.format(i)
            if pin in common_pins_set:
                continue
            attempts += 1
            if test_function(pin):
                self.logger.info("PIN ditemukan pada tahap brute force.")
                return pin, attempts
        
        return None, attempts

    def brute_force_zip(self, file_path):
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                if not zf.infolist(): return None, 0, "Arsip Kosong"
                info = zf.infolist()[0]
                if not (info.flag_bits & 0x1): return "", 0, "Tidak Terenkripsi"
                encryption_type = "AES-256 (Modern)" if info.flag_bits & 0x40 else "ZipCrypto (Legacy)"
                def test_zip(password):
                    try:
                        zf.read(info.filename, pwd=password.encode('utf-8'))
                        return True
                    except: return False
                password, attempts = self.try_passwords(test_zip)
                return password, attempts, encryption_type
        except Exception as e:
            self.logger.error(f"Error ZIP '{os.path.basename(file_path)}': {e}")
            return None, 0, "Error"

    def brute_force_rar(self, file_path):
        try:
            with rarfile.RarFile(file_path) as rf:
                if not rf.infolist(): return None, 0, "Arsip Kosong"
                if not rf.needs_password(): return "", 0, "Tidak Terenkripsi"
                def test_rar(password):
                    try:
                        rf.testrar(pwd=password)
                        return True
                    except: return False
                password, attempts = self.try_passwords(test_rar)
                return password, attempts, "RAR Encryption"
        except Exception as e:
            self.logger.error(f"Error RAR '{os.path.basename(file_path)}': {e}")
            return None, 0, "Error"

    def brute_force_pdf(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                if not reader.is_encrypted: return "", 0, "Tidak Terenkripsi"
        except Exception as e:
            self.logger.error(f"Error saat membuka PDF '{os.path.basename(file_path)}': {e}")
            return None, 0, "Error Baca File"

        def test_pdf(password):
            try:
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    if reader.decrypt(password) in (1, 2): return True
                return False
            except: return False
        
        password, attempts = self.try_passwords(test_pdf)
        return password, attempts, "Standard PDF Encryption"

    def brute_force_7z(self, file_path):
        try:
            with py7zr.SevenZipFile(file_path, 'r') as z:
                if not any(f.encrypted for f in z.list()): return "", 0, "Tidak Terenkripsi"
            def test_7z(password):
                try:
                    with py7zr.SevenZipFile(file_path, mode='r', password=password) as z:
                        z.test()
                        return True
                except: return False
            password, attempts = self.try_passwords(test_7z)
            return password, attempts, "7z (AES-256)"
        except Exception as e:
            self.logger.error(f"Error 7Z '{os.path.basename(file_path)}': {e}")
            return None, 0, "Error"

    def add_file(self):
        selected_format = self.format_var.get(); ext = selected_format.lower()
        file_paths = filedialog.askopenfilenames(title=f"Pilih File {selected_format}", filetypes=[(f"{selected_format} Files", f"*.{ext}"), ("All Files", "*.*")])
        for fp in file_paths:
            if not any(self.tree.item(i, 'tags')[0] == fp for i in self.tree.get_children()):
                self.file_counter += 1; filename = os.path.basename(fp)
                self.tree.insert('', tk.END, iid=str(self.file_counter), values=(self.unchecked_char, self.file_counter, filename, selected_format, "Menunggu", "-"), tags=(fp,))
        if file_paths: self.logger.info(f"{len(file_paths)} file {selected_format} ditambahkan.")
    
    def remove_selected_file(self):
        selected_items = self.tree.selection()
        if selected_items and messagebox.askyesno("Konfirmasi", f"Yakin ingin menghapus {len(selected_items)} file terpilih?"):
            for item in selected_items:
                self.tree.delete(item)
        self.update_all_button_states()

    def clear_all_files(self):
        if messagebox.askyesno("Konfirmasi", "Yakin ingin membersihkan semua file?"):
            for item in self.tree.get_children(): self.tree.delete(item)
            self.results_data.clear()
            self.update_all_button_states()
            self.view_reports_btn.config(state='disabled')

    def toggle_cracking(self):
        if self.cracking_in_progress: self.cancel_cracking()
        else: self.start_cracking()

    def cancel_cracking(self):
        if messagebox.askyesno("Konfirmasi", "Yakin ingin membatalkan proses?"):
            self.cracking_in_progress = False
            self.monitoring_active = False # Hentikan monitoring
            self.logger.warning("Proses dibatalkan oleh pengguna.")
            self.set_ui_state(False)

    def check_all_threads_done(self):
        if any(t.is_alive() for t in self.active_threads) or not self.result_queue.empty():
            self.after(100, self.check_all_threads_done)
        else:
            self.monitoring_active = False # Hentikan monitoring
            self.logger.info("="*40 + " PROSES UJI SELESAI " + "="*40)
            self.set_ui_state(False)

    def set_ui_state(self, is_cracking):
        self.cracking_in_progress = is_cracking
        state = 'disabled' if is_cracking else 'normal'
        for btn in [self.add_file_btn, self.remove_file_btn, self.clear_all_btn, self.deep_crack_chk]:
            btn.config(state=state)
        self.start_btn.config(text="Batalkan Uji" if is_cracking else "Mulai Uji")
        
        if not is_cracking:
            if self.results_data:
                self.view_reports_btn.config(state='normal')
            else:
                self.view_reports_btn.config(state='disabled')
            self.update_all_button_states()
        else:
            self.view_reports_btn.config(state='disabled')
            self.update_all_button_states(disable_all=True)
    
    def on_tree_select(self, event):
        self.update_all_button_states()

    def toggle_checkbox(self, event):
        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id or col_id != '#1': return
        tags = self.tree.item(row_id, 'tags')
        is_checked = 'checked' in tags
        new_tags = [t for t in tags if t != 'checked'] if is_checked else list(tags) + ['checked']
        self.tree.item(row_id, tags=tuple(new_tags))
        self.tree.set(row_id, 'select', self.checked_char if not is_checked else self.unchecked_char)
        self.update_all_button_states()

    def update_all_button_states(self, disable_all=False):
        if disable_all:
            self.extract_btn.config(state='disabled')
            self.recovery_options_btn.config(state='disabled')
            self.save_csv_btn.config(state='disabled')
            return

        has_results = bool(self.tree.get_children())
        self.save_csv_btn.config(state='normal' if has_results else 'disabled')

        checked_items = [row_id for row_id in self.tree.get_children() if 'checked' in self.tree.item(row_id, 'tags')]
        is_any_securable_checked = any(
            "Berhasil" in self.tree.item(row_id, 'values')[4] or 
            "Tidak Terenkripsi" in self.tree.item(row_id, 'values')[4] 
            for row_id in checked_items
        )
        is_any_successful_checked = any("Berhasil" in self.tree.item(row_id, 'values')[4] for row_id in checked_items)
        
        self.extract_btn.config(state='normal' if is_any_successful_checked else 'disabled')
        self.recovery_options_btn.config(state='normal' if is_any_securable_checked else 'disabled')

    def create_bottom_bar(self):
        self.bottom_bar = ttk.Frame(self)
        self.bottom_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        self.update_bottom_bar("main")

    def update_bottom_bar(self, view_name, report_type=None):
        for widget in self.bottom_bar.winfo_children(): widget.destroy()
        
        if view_name == "main":
            self.view_reports_btn = ttk.Menubutton(self.bottom_bar, text="Lihat Laporan")
            self.view_reports_btn.pack(side=tk.RIGHT)
            
            reports_menu = Menu(self.view_reports_btn, tearoff=0)
            reports_menu.add_command(label="Laporan Hasil Uji", command=self.show_analysis_view)
            reports_menu.add_command(label="Laporan Frekuensi PIN", command=self.show_frequency_view)
            reports_menu.add_command(label="Laporan Kinerja Perangkat", command=self.show_performance_view)
            self.view_reports_btn['menu'] = reports_menu

            if not self.results_data:
                self.view_reports_btn.config(state='disabled')
        else: # Untuk semua halaman laporan
            ttk.Button(self.bottom_bar, text="< Kembali", command=lambda: self.switch_view("main")).pack(side=tk.LEFT)
            
            if report_type == 'analysis':
                ttk.Button(self.bottom_bar, text="Cetak Laporan", command=self.print_report).pack(side=tk.RIGHT)
                ttk.Button(self.bottom_bar, text="Simpan ke PDF", command=self.save_as_pdf).pack(side=tk.RIGHT, padx=5)
            elif report_type == 'frequency':
                ttk.Button(self.bottom_bar, text="Cetak Laporan Frekuensi", command=self.frequency_view_frame.print_report).pack(side=tk.RIGHT)
                ttk.Button(self.bottom_bar, text="Simpan Frekuensi ke PDF", command=self.frequency_view_frame.save_as_pdf).pack(side=tk.RIGHT, padx=5)
            elif report_type == 'performance':
                ttk.Button(self.bottom_bar, text="Cetak Laporan Kinerja", command=self.performance_view_frame.print_report).pack(side=tk.RIGHT)
                ttk.Button(self.bottom_bar, text="Simpan Kinerja ke PDF", command=self.performance_view_frame.save_as_pdf).pack(side=tk.RIGHT, padx=5)

    def switch_view(self, view_name):
        # Sembunyikan semua frame laporan
        self.main_view_frame.pack_forget()
        self.analysis_view_frame.pack_forget()
        self.frequency_view_frame.pack_forget()
        self.performance_view_frame.pack_forget()
        
        if view_name == "analysis":
            self.analysis_view_frame.update_data(self.results_data)
            self.analysis_view_frame.pack(fill=tk.BOTH, expand=True)
            self.update_bottom_bar("report", report_type="analysis")
        elif view_name == "frequency":
            self.frequency_view_frame.update_data()
            self.frequency_view_frame.pack(fill=tk.BOTH, expand=True)
            self.update_bottom_bar("report", report_type="frequency")
        elif view_name == "performance":
            self.performance_view_frame.update_data(self.system_info, self.results_data, self.cpu_usage_history, self.memory_usage_history)
            self.performance_view_frame.pack(fill=tk.BOTH, expand=True)
            self.update_bottom_bar("report", report_type="performance")
        else: # Kembali ke main
            self.main_view_frame.pack(fill=tk.BOTH, expand=True)
            self.update_bottom_bar("main")

    def show_multi_recovery_dialog(self):
        checked_files_info = []
        for row_id in self.tree.get_children():
            if 'checked' in self.tree.item(row_id, 'tags'):
                values = self.tree.item(row_id, 'values')
                tags = self.tree.item(row_id, 'tags')
                status = values[4]
                
                if "Berhasil" in status or "Tidak Terenkripsi" in status:
                    old_password = values[5] if "Berhasil" in status else ""
                    info = {
                        'file_path': tags[0],
                        'old_password': old_password,
                        'file_type': values[3]
                    }
                    checked_files_info.append(info)
        
        if not checked_files_info:
            messagebox.showwarning("Tidak Ada Pilihan", "Centang file yang statusnya 'Berhasil' atau 'Tidak Terenkripsi' untuk diamankan.", parent=self)
            return
        
        MultiRecoveryDialog(parent=self, files_to_recover=checked_files_info)

    def show_analysis_view(self):
        if not self.results_data:
            messagebox.showinfo("Informasi", "Tidak ada data hasil uji untuk ditampilkan.")
            return
        self.switch_view("analysis")

    def show_frequency_view(self):
        self.switch_view("frequency")

    def show_performance_view(self):
        self.switch_view("performance")

    def extract_selected_files(self):
        selected_files = []
        for row_id in self.tree.get_children():
            if 'checked' in self.tree.item(row_id, 'tags'):
                values = self.tree.item(row_id, 'values')
                file_path = self.tree.item(row_id, 'tags')[0]
                password = values[5]
                file_type = values[3]
                if password != '-' and "Berhasil" in values[4]:
                    selected_files.append({'path': file_path, 'pass': password, 'type': file_type})
        
        if not selected_files:
            messagebox.showwarning("Tidak Ada Pilihan", "Pilih file yang statusnya 'Berhasil' untuk diekstrak.")
            return

        dest_dir = filedialog.askdirectory(title="Pilih Folder Tujuan Ekstraksi")
        if not dest_dir: return

        for f in selected_files:
            try:
                self.logger.info(f"Mengekstrak {os.path.basename(f['path'])} ke {dest_dir}")
                if f['type'] == 'ZIP':
                    with zipfile.ZipFile(f['path'], 'r') as zf: zf.extractall(path=dest_dir, pwd=f['pass'].encode('utf-8'))
                elif f['type'] == 'RAR':
                    with rarfile.RarFile(f['path'], 'r') as rf: rf.extractall(path=dest_dir, pwd=f['pass'])
                elif f['type'] == '7Z':
                    with py7zr.SevenZipFile(f['path'], 'r', password=f['pass']) as z: z.extractall(path=dest_dir)
            except Exception as e:
                self.logger.error(f"Gagal ekstrak {os.path.basename(f['path'])}: {e}")
                messagebox.showerror("Ekstraksi Gagal", f"Gagal mengekstrak {os.path.basename(f['path'])}.\n\nError: {e}")
        
        messagebox.showinfo("Selesai", f"Ekstraksi {len(selected_files)} file selesai.")

    def save_results_to_csv(self):
        if not self.tree.get_children():
            messagebox.showinfo("Informasi", "Tidak ada hasil untuk disimpan.", parent=self)
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Simpan Hasil sebagai CSV",
            initialfile=f"hasil_uji_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        if not file_path: return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                csv_writer = csv.writer(csvfile)
                header = ['ID', 'Nama File', 'Tipe', 'Status', 'PIN Ditemukan']
                csv_writer.writerow(header)
                for item_id in self.tree.get_children():
                    item = self.tree.item(item_id, 'values')
                    row_data = [item[1], item[2], item[3], item[4], item[5]]
                    csv_writer.writerow(row_data)
            
            messagebox.showinfo("Berhasil", f"Hasil berhasil disimpan ke:\n{file_path}", parent=self)
            self.logger.info(f"Hasil Treeview disimpan ke file CSV: {file_path}")
        except Exception as e:
            messagebox.showerror("Gagal Menyimpan", f"Terjadi kesalahan saat menyimpan file CSV:\n{e}", parent=self)
            self.logger.error(f"Gagal menyimpan hasil ke CSV: {e}")

    def _create_pdf_header(self, title_text):
        """Membuat header standar untuk semua laporan PDF."""
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='MainTitle', parent=styles['h1'], alignment=TA_CENTER, fontSize=16))
        
        logo_path = os.path.join(ASSET_DIR, "logo.png")
        title = Paragraph(title_text, styles['MainTitle'])
        header_data = [[title]]
        col_widths = ['100%']
        
        if os.path.exists(logo_path):
            logo = ReportlabImage(logo_path, width=50, height=50)
            header_data = [[title, logo]]
            col_widths = ['80%', '20%']
        else:
            self.logger.warning(f"File logo tidak ditemukan di: {logo_path}")

        style_commands = [
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (0,0), 'CENTER'),
            ('LINEBELOW', (0,0), (-1,0), 1, black),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ]
        if not os.path.exists(logo_path):
            style_commands.append(('SPAN', (0,0), (0,0)))

        header_table = Table(header_data, colWidths=col_widths)
        header_table.setStyle(TableStyle(style_commands))
        return header_table

    def _generate_pdf(self, file_path, open_after, title, content_generator):
        """Fungsi generik untuk membuat semua jenis laporan PDF."""
        self.logger.info(f"Memulai pembuatan laporan PDF '{title}' ke: {file_path}")
        try:
            doc = SimpleDocTemplate(file_path, pagesize=legal, topMargin=20*mm, bottomMargin=20*mm, leftMargin=20*mm, rightMargin=20*mm)
            
            header = self._create_pdf_header(title)
            elements = [header, Spacer(1, 12)]
            
            # Panggil fungsi yang disediakan untuk mendapatkan konten spesifik laporan
            report_elements = content_generator()
            elements.extend(report_elements)

            doc.build(elements)
            messagebox.showinfo("Berhasil", f"Laporan PDF disimpan di:\n{file_path}")
            if open_after:
                if platform.system() == "Windows": os.startfile(file_path)
                else: subprocess.call(["open", file_path] if platform.system() == "Darwin" else ["xdg-open", file_path])
        except Exception as e:
            self.logger.error(f"Gagal membuat PDF: {e}", exc_info=True)
            messagebox.showerror("Gagal Membuat PDF", f"Terjadi kesalahan: {e}")

    # --- Metode untuk Laporan Hasil Uji ---
    def save_as_pdf(self):
        if not self.results_data: return
        fp = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Documents", "*.pdf")])
        if fp:
            Thread(target=self._generate_pdf, args=(fp, False, "Laporan Hasil Uji Pemulihan PIN", self.analysis_view_frame.generate_pdf_elements), daemon=True).start()

    def print_report(self):
        if not self.results_data: return
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            Thread(target=self._generate_pdf, args=(tmp_file.name, True, "Laporan Hasil Uji Pemulihan PIN", self.analysis_view_frame.generate_pdf_elements), daemon=True).start()
    
    def collect_system_info(self):
        """Mengumpulkan informasi sistem untuk laporan kinerja."""
        self.logger.info("Mengumpulkan informasi sistem...")
        try:
            info = cpuinfo.get_cpu_info()
            self.system_info['hostname'] = platform.node()
            self.system_info['cpu'] = f"{info.get('brand_raw', 'N/A')}"
            self.system_info['cores'] = f"{psutil.cpu_count(logical=True)} cores ({psutil.cpu_count(logical=False)} physical)"
            self.system_info['ram'] = f"{psutil.virtual_memory().total / (1024**3):.2f} GB"
            self.system_info['os'] = f"{platform.system()} {platform.release()}"

            gpu_info = "Tidak Terdeteksi"
            if platform.system() == "Windows":
                try:
                    command = "wmic path win32_VideoController get name"
                    gpu_info = subprocess.check_output(command, shell=True, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW).decode().split('\n')[1].strip()
                except Exception:
                    gpu_info = "Gagal mendapatkan info GPU (wmic error)"
            self.system_info['gpu'] = gpu_info
            
            self.logger.info("Informasi sistem berhasil dikumpulkan.")
        except Exception as e:
            self.logger.error(f"Gagal mengumpulkan informasi sistem: {e}")
            self.system_info = {k: "Error" for k in ['hostname', 'cpu', 'cores', 'ram', 'os', 'gpu']}


# ==============================================================================
# KELAS-KELAS VIEW (TAMPILAN)
# ==============================================================================
class AnalysisView(ttk.Frame):
    def __init__(self, parent, app_controller, user_name_var):
        super().__init__(parent)
        self.app_controller = app_controller
        self.user_name_var = user_name_var
        self.logo_path = os.path.join(ASSET_DIR, "logo.png")
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(0, weight=1)
        
        self.image_references = []

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas, padding=10)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

    def generate_pdf_elements(self):
        """Menyiapkan semua elemen ReportLab untuk laporan hasil uji."""
        elements = []
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='TimesBody', fontName='Times-Roman', fontSize=11, leading=14))
        styles.add(ParagraphStyle(name='TimesBold', parent=styles['TimesBody'], fontName='Times-Bold'))

        for i, item_data in enumerate(self.app_controller.results_data):
            if i > 0:
                elements.append(PageBreak())
            
            report_parts, signature_text, chart_path, qr_path = self.generate_report_assets(item_data, i)
            
            elements.append(Paragraph(report_parts['part1'], styles['TimesBody']))
            elements.append(Paragraph("<b>4. Visualisasi Analisis Uji</b>", styles['TimesBold']))
            
            if chart_path and os.path.exists(chart_path):
                elements.append(Spacer(1, 8))
                elements.append(ReportlabImage(chart_path, width=150*mm, height=75*mm, hAlign='CENTER'))
            
            elements.append(Paragraph(report_parts['part2'], styles['TimesBody']))
            elements.append(Spacer(1, 18))
            
            if qr_path and os.path.exists(qr_path):
                qr_img_flowable = ReportlabImage(qr_path, width=80, height=80, hAlign='RIGHT')
                clean_signature_text = signature_text.replace("[QR_PLACEHOLDER]", '')
                signature_style = ParagraphStyle('Signature', parent=styles['TimesBody'], alignment=TA_RIGHT)
                signature_content = [
                    [Paragraph(clean_signature_text.replace('\n', '<br/>'), signature_style)],
                    [qr_img_flowable]
                ]
                signature_table = Table(signature_content, colWidths=['100%'])
                signature_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('BOTTOMPADDING', (0, 0), (0, 0), 6)]))
                elements.append(signature_table)
        return elements

    def generate_report_assets(self, item_data, index=0):
        total_kombinasi = 10000 if self.app_controller.brute_force_mode.get() == "4 PIN" else 1000000
        percobaan = item_data.get('Total Percobaan', 0)
        durasi = float(item_data.get('Durasi Proses', 0.0))
        
        kecepatan_str = f"{(percobaan / durasi):.2f} percobaan/detik" if durasi > 0 else "Instan"

        report_parts = {}
        report_parts['part1'] = f"""
<b>1. Metadata File</b><br/>
  Nama File         : {item_data.get('Nama File', '-')}<br/>
  Tipe File         : {item_data.get('Tipe File', '-')}<br/>
  Ukuran File       : {item_data.get('Ukuran File', '-')}<br/>
  Waktu Modifikasi  : {item_data.get('Waktu Modifikasi', '-')}<br/><br/>

<b>2. Hasil Uji Pemulihan</b><br/>
  Status Uji        : {item_data.get('Status Uji', '-')}<br/>
  PIN Ditemukan     : {item_data.get('PIN Ditemukan', '-')}<br/>
  Durasi Proses     : {durasi:.2f} detik<br/>
  Total Percobaan   : {percobaan}<br/>
  Jenis Enkripsi    : {item_data.get('Jenis Enkripsi', '-')}<br/><br/>

<b>3. Statistik Analitis</b><br/>
  Total Kombinasi   : {total_kombinasi}<br/>
  Rata-rata Kecepatan: {kecepatan_str}<br/>
  Kombinasi Diuji   : {(percobaan / total_kombinasi * 100) if item_data['Status Uji'] == 'Berhasil' else 100.0:.2f}%<br/><br/>
"""
        report_parts['part2'] = """
<br/><b>5. Rekomendasi</b><br/>
  Enkripsi          : Disarankan gunakan enkripsi AES-256 untuk keamanan lebih tinggi.<br/>
  PIN               : Hindari PIN numerik pendek, gunakan passphrase yang kuat dan unik.<br/>
"""
        try: locale.setlocale(locale.LC_TIME, 'id_ID')
        except locale.Error: locale.setlocale(locale.LC_TIME, '')
        
        now = datetime.now()
        date_str = now.strftime("%A, %d %B %Y")

        signature_text = f"""
                Jakarta, {date_str}
                
                [QR_PLACEHOLDER]
"""
        timestamp = f"{int(time.time() * 1000)}_{index}"
        qr_path = os.path.join(tempfile.gettempdir(), f"report_qr_{timestamp}.png")
        qrcode.make(self.user_name_var.get()).save(qr_path)

        chart_path = os.path.join(tempfile.gettempdir(), f"report_chart_{timestamp}.png")
        self.create_matplotlib_chart(percobaan, total_kombinasi, chart_path)

        return report_parts, signature_text, chart_path, qr_path

    def create_matplotlib_chart(self, attempts, total_combinations, output_path):
        try:
            fig, ax = plt.subplots(figsize=(6, 3), dpi=100)
            
            safe_attempts = min(attempts, total_combinations)
            remaining = total_combinations - safe_attempts
            
            sizes = [safe_attempts, remaining] if any([safe_attempts, remaining]) else [0, 1]
            labels = [f'Diuji\n({safe_attempts})', f'Sisa\n({remaining})']
            colors = ['#66bb6a', '#E0E0E0']
            explode = (0.05, 0) if any(sizes) else (0, 0)

            wedges, texts, autotexts = ax.pie(sizes, explode=explode, labels=labels, autopct='%1.1f%%',
                                              shadow=False, startangle=90, colors=colors,
                                              pctdistance=0.85, textprops={'color':"w", 'fontweight':'bold'})
            
            centre_circle = plt.Circle((0,0),0.70,fc='white')
            fig.gca().add_artist(centre_circle)

            ax.axis('equal')
            plt.tight_layout()
            plt.savefig(output_path, bbox_inches='tight', transparent=True)
            plt.close(fig)
        except Exception as e:
            self.app_controller.logger.error(f"Gagal membuat grafik Matplotlib: {e}")
            return None

    def update_data(self, data):
        for widget in self.scrollable_frame.winfo_children(): widget.destroy()
        self.image_references.clear()

        self._create_summary_card(data)

        for i, item_data in enumerate(data):
            self._create_report_card(item_data, i)
        
        self.app_controller.update_idletasks()
        self.canvas.yview_moveto(0) # Kembali ke atas
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _create_summary_card(self, data):
        total_files = len(data)
        success_count = sum(1 for item in data if item['Status Uji'] == 'Berhasil')
        fail_count = total_files - success_count

        summary_frame = ttk.LabelFrame(self.scrollable_frame, text="Ringkasan Hasil Uji", padding=15)
        summary_frame.pack(pady=(0, 20), fill='x', expand=True)

        info_frame = ttk.Frame(summary_frame)
        info_frame.pack(fill='x', expand=True)
        
        ttk.Label(info_frame, text=f"Total File Diuji:", font=("Segoe UI", 11)).grid(row=0, column=0, sticky='w', padx=(0, 10))
        ttk.Label(info_frame, text=f"{total_files}", font=("Segoe UI", 11, "bold")).grid(row=0, column=1, sticky='w')
        
        ttk.Label(info_frame, text="Berhasil:", font=("Segoe UI", 11)).grid(row=1, column=0, sticky='w', padx=(0, 10))
        ttk.Label(info_frame, text=f"{success_count}", font=("Segoe UI", 11, "bold"), foreground="green").grid(row=1, column=1, sticky='w')

        ttk.Label(info_frame, text="Gagal:", font=("Segoe UI", 11)).grid(row=2, column=0, sticky='w', padx=(0, 10))
        ttk.Label(info_frame, text=f"{fail_count}", font=("Segoe UI", 11, "bold"), foreground="red").grid(row=2, column=1, sticky='w')

    def _create_report_card(self, item_data, index):
        report_parts, signature_text, chart_path, qr_path = self.generate_report_assets(item_data, index)

        card = ttk.Frame(self.scrollable_frame, padding=15, relief="solid", borderwidth=1)
        card.pack(pady=10, fill='x', expand=True)

        # Header
        title_text = f"Laporan Rinci untuk: {item_data.get('Nama File', 'N/A')}"
        ttk.Label(card, text=title_text, font=("Segoe UI", 14, "bold")).pack(anchor='w', pady=(0, 10))
        ttk.Separator(card, orient='horizontal').pack(fill='x', expand=True, pady=(0, 10))

        # Konten
        content_text = report_parts['part1'].replace('<br/>', '\n').replace('<b>', '').replace('</b>', '')
        ttk.Label(card, text=content_text, font=("Consolas", 10), justify=tk.LEFT).pack(anchor='w', pady=5)

        # Visualisasi
        ttk.Label(card, text="4. Visualisasi Analisis Uji", font=("Segoe UI", 11, "bold")).pack(anchor='w', pady=(10, 5))
        if chart_path and os.path.exists(chart_path):
            try:
                chart_img = PILImage.open(chart_path).resize((500, 250), PILImage.Resampling.LANCZOS)
                chart_photo = ImageTk.PhotoImage(chart_img)
                self.image_references.append(chart_photo)
                ttk.Label(card, image=chart_photo).pack(pady=5)
            except Exception as e:
                self.app_controller.logger.error(f"Gagal memuat gambar chart di UI: {e}")
        
        # Rekomendasi
        rekomendasi_text = report_parts['part2'].replace('<br/>', '\n').replace('<b>', '').replace('</b>', '')
        ttk.Label(card, text=rekomendasi_text, font=("Consolas", 10), justify=tk.LEFT).pack(anchor='w', pady=5)
        
        # Signature
        ttk.Separator(card, orient='horizontal').pack(fill='x', expand=True, pady=(10, 10))
        sig_frame = ttk.Frame(card)
        sig_frame.pack(fill='x', expand=True)

        clean_sig_text = signature_text.replace("[QR_PLACEHOLDER]", "").strip()
        ttk.Label(sig_frame, text=clean_sig_text, font=("Segoe UI", 10), justify=tk.RIGHT).pack(side=tk.LEFT, expand=True, anchor='e')
        
        if qr_path and os.path.exists(qr_path):
            try:
                qr_img = PILImage.open(qr_path).resize((80, 80), PILImage.Resampling.LANCZOS)
                qr_photo = ImageTk.PhotoImage(qr_img)
                self.image_references.append(qr_photo)
                ttk.Label(sig_frame, image=qr_photo).pack(side=tk.RIGHT, padx=(10,0))
            except Exception as e:
                self.app_controller.logger.error(f"Gagal memuat gambar QR di UI: {e}")

class FrequencyView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.app_controller = parent
        self.image_references = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        main_pane = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.plot_frame = ttk.LabelFrame(main_pane, text="Visualisasi Frekuensi")
        main_pane.add(self.plot_frame, weight=1)

        table_frame = ttk.LabelFrame(main_pane, text="Top 10 Data Frekuensi")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        main_pane.add(table_frame, weight=1)
        
        columns = ('rank', 'pin', 'frequency')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings')
        self.tree.heading('rank', text='Peringkat')
        self.tree.column('rank', width=80, anchor='center', stretch=tk.NO)
        self.tree.heading('pin', text='PIN Ditemukan')
        self.tree.column('pin', width=200, anchor='center')
        self.tree.heading('frequency', text='Frekuensi Ditemukan')
        self.tree.column('frequency', width=200, anchor='center')
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

    def update_data(self):
        for widget in self.plot_frame.winfo_children(): widget.destroy()
        for item in self.tree.get_children(): self.tree.delete(item)
        self.image_references.clear()

        all_results = self._fetch_data()
        if not all_results:
            ttk.Label(self.plot_frame, text="Tidak ada data frekuensi yang cukup untuk ditampilkan.").pack(pady=20)
            return
        
        top_10_results = all_results[:10]

        for i, (pin, frequency) in enumerate(top_10_results, 1):
            self.tree.insert('', tk.END, values=(f"#{i}", pin, frequency))
        
        self._create_plots(all_results)

    def _fetch_data(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pin_ditemukan, COUNT(pin_ditemukan) as frequency
                FROM log_hasil_uji
                WHERE status = 'Berhasil' AND pin_ditemukan != '-'
                GROUP BY pin_ditemukan
                ORDER BY frequency DESC
            ''')
            results = cursor.fetchall()
            conn.close()
            return results
        except sqlite3.Error as e:
            messagebox.showerror("Error Database", f"Gagal mengambil data frekuensi PIN: {e}", parent=self)
            return []

    def _create_plots(self, results):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5), dpi=100)
        
        top_5_data = results[:5]
        pins_bar = [item[0] for item in top_5_data]; freq_bar = [item[1] for item in top_5_data]
        pins_bar.reverse(); freq_bar.reverse()

        ax1.barh(pins_bar, freq_bar, color='skyblue')
        ax1.set_title('Top 5 PIN Paling Sering Ditemukan', fontsize=12)
        ax1.set_xlabel('Jumlah Ditemukan', fontsize=10)
        for i, v in enumerate(freq_bar): ax1.text(v + 0.1, i, str(v), color='black', va='center')
        ax1.xaxis.set_major_locator(plt.MaxNLocator(integer=True))

        pins_scatter = [int(p[0]) for p in results if p[0].isdigit()]
        freq_scatter = [p[1] for p in results if p[0].isdigit()]

        if pins_scatter:
            ax2.scatter(pins_scatter, freq_scatter, alpha=0.6, color='coral')
        ax2.set_title('Distribusi Frekuensi PIN', fontsize=12)
        ax2.set_xlabel('PIN (sebagai Angka)', fontsize=10)
        ax2.set_ylabel('Frekuensi', fontsize=10)
        ax2.grid(True)

        fig.tight_layout(pad=3.0)
        
        canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        canvas.draw()
        self.image_references.append(canvas)

    def generate_report_assets(self, index=0):
        """Menghasilkan aset seperti QR code dan signature untuk laporan PDF."""
        try: locale.setlocale(locale.LC_TIME, 'id_ID')
        except locale.Error: locale.setlocale(locale.LC_TIME, '')
        
        now = datetime.now()
        date_str = now.strftime("%A, %d %B %Y")

        signature_text = f"""
                Jakarta, {date_str}
                
                [QR_PLACEHOLDER]
"""
        timestamp = f"{int(time.time() * 1000)}_{index}"
        qr_path = os.path.join(tempfile.gettempdir(), f"freq_qr_{timestamp}.png")
        qrcode.make(self.app_controller.user_name.get()).save(qr_path)

        return signature_text, qr_path

    def generate_pdf_elements(self):
        """Menyiapkan elemen ReportLab untuk laporan frekuensi."""
        elements = []
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='TimesBody', fontName='Times-Roman', fontSize=11, leading=14))
        styles.add(ParagraphStyle(name='TimesBold', parent=styles['TimesBody'], fontName='Times-Bold'))
        
        all_results = self._fetch_data()
        if not all_results:
            elements.append(Paragraph("Tidak ada data untuk ditampilkan.", styles['TimesBody']))
            return elements

        # 1. Ringkasan Analisis
        total_unique_pins = len(all_results)
        most_common_pin = all_results[0][0] if all_results else "N/A"
        
        elements.append(Paragraph("<b>1. Ringkasan Analisis</b>", styles['TimesBold']))
        summary_text = f"""
        Laporan ini menganalisis frekuensi kemunculan PIN yang berhasil ditemukan dari seluruh sesi pengujian. 
        Dari data yang terkumpul, teridentifikasi total <b>{total_unique_pins}</b> PIN unik. 
        PIN yang paling sering muncul adalah <b>'{most_common_pin}'</b>, yang mengindikasikan kemungkinan penggunaan PIN yang lemah atau umum.
        """
        elements.append(Paragraph(summary_text.replace('\n', ''), styles['TimesBody']))
        elements.append(Spacer(1, 8))

        # 2. Visualisasi Data
        elements.append(Paragraph("<b>2. Visualisasi Data</b>", styles['TimesBold']))
        elements.append(Paragraph("Grafik berikut menyajikan 5 PIN teratas yang paling sering ditemukan dan distribusi keseluruhan frekuensi PIN numerik.", styles['TimesBody']))
        elements.append(Spacer(1, 4))

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5), dpi=300)
            top_5_data = all_results[:5]
            pins_bar = [item[0] for item in top_5_data]; freq_bar = [item[1] for item in top_5_data]
            pins_bar.reverse(); freq_bar.reverse()
            ax1.barh(pins_bar, freq_bar, color='skyblue'); ax1.set_title('Top 5 PIN Paling Sering Ditemukan', fontsize=12)
            pins_scatter = [int(p[0]) for p in all_results if p[0].isdigit()]; freq_scatter = [p[1] for p in all_results if p[0].isdigit()]
            if pins_scatter: ax2.scatter(pins_scatter, freq_scatter, alpha=0.6, color='coral')
            ax2.set_title('Distribusi Frekuensi PIN', fontsize=12)
            fig.tight_layout(pad=3.0)
            fig.savefig(tmp_file.name, format='png')
            plt.close(fig)
            elements.append(ReportlabImage(tmp_file.name, width=180*mm, height=81*mm, hAlign='CENTER'))
        elements.append(Spacer(1, 8))

        # 3. Tabel Frekuensi Lengkap
        elements.append(Paragraph("<b>3. Tabel 10 Frekuensi Teratas</b>", styles['TimesBold']))
        elements.append(Spacer(1, 4))
        
        top_10_for_table = all_results[:10]
        table_data = [['Peringkat', 'PIN Ditemukan', 'Frekuensi']] + [[f"#{i}", pin, str(freq)] for i, (pin, freq) in enumerate(top_10_for_table, 1)]
        
        table = Table(table_data, colWidths=[100, 150, 150])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor("#CCCCCC")), ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Times-Bold'), ('FONTNAME', (0,1), (-1,-1), 'Times-Roman'),
            ('GRID', (0,0), (-1,-1), 1, black)
        ]))
        elements.append(table)
        elements.append(Spacer(1, 18))

        # Signature
        signature_text, qr_path = self.generate_report_assets()
        if qr_path and os.path.exists(qr_path):
            qr_img = ReportlabImage(qr_path, width=80, height=80, hAlign='RIGHT')
            clean_signature = signature_text.replace("[QR_PLACEHOLDER]", '')
            sig_style = ParagraphStyle('Signature', parent=styles['TimesBody'], alignment=TA_RIGHT)
            sig_table = Table([[Paragraph(clean_signature.replace('\n', '<br/>'), sig_style)], [qr_img]], colWidths=['100%'])
            sig_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('BOTTOMPADDING', (0, 0), (0, 0), 6)]))
            elements.append(sig_table)
            
        return elements

    def save_as_pdf(self):
        fp = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Documents", "*.pdf")], title="Simpan Laporan Frekuensi")
        if fp:
            Thread(target=self.app_controller._generate_pdf, args=(fp, False, "Laporan Frekuensi PIN", self.generate_pdf_elements), daemon=True).start()

    def print_report(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            Thread(target=self.app_controller._generate_pdf, args=(tmp_file.name, True, "Laporan Frekuensi PIN", self.generate_pdf_elements), daemon=True).start()

class SystemPerformanceView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.app_controller = parent
        self.image_references = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.main_frame = ttk.Frame(self, padding=20)
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        
        self.plot_frame = ttk.LabelFrame(self, text="Grafik Kinerja Real-time", padding=10)
        self.plot_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    def update_data(self, system_info, results_data, cpu_history, mem_history):
        for widget in self.main_frame.winfo_children(): widget.destroy()
        for widget in self.plot_frame.winfo_children(): widget.destroy()
        self.image_references.clear()

        ttk.Label(self.main_frame, text="Laporan Kinerja Perangkat", font=("Segoe UI", 18, "bold")).pack(anchor='w', pady=(0, 20))

        spec_frame = ttk.LabelFrame(self.main_frame, text="Spesifikasi Sistem", padding=15)
        spec_frame.pack(fill='x', expand=True, pady=(0, 15))
        spec_frame.grid_columnconfigure(1, weight=1)

        def create_spec_row(parent, label, value, row):
            ttk.Label(parent, text=label, font=("Segoe UI", 10)).grid(row=row, column=0, sticky='w', padx=(0, 15), pady=4)
            ttk.Label(parent, text=value, font=("Segoe UI", 10, "bold"), wraplength=400, justify=tk.LEFT).grid(row=row, column=1, sticky='w', pady=4)

        create_spec_row(spec_frame, "Nama Perangkat:", system_info.get('hostname', 'N/A'), 0)
        create_spec_row(spec_frame, "Sistem Operasi:", system_info.get('os', 'N/A'), 1)
        create_spec_row(spec_frame, "CPU:", system_info.get('cpu', 'N/A'), 2)
        create_spec_row(spec_frame, "Cores:", system_info.get('cores', 'N/A'), 3)
        create_spec_row(spec_frame, "Total RAM:", system_info.get('ram', 'N/A'), 4)
        create_spec_row(spec_frame, "GPU:", system_info.get('gpu', 'N/A'), 5)
        
        perf_frame = ttk.LabelFrame(self.main_frame, text="Metrik Kinerja Uji", padding=15)
        perf_frame.pack(fill='x', expand=True)
        perf_frame.grid_columnconfigure(1, weight=1)

        total_duration = sum(float(r['Durasi Proses']) for r in results_data)
        total_attempts = sum(r['Total Percobaan'] for r in results_data)
        avg_speed = (total_attempts / total_duration) if total_duration > 0 else 0
        
        create_spec_row(perf_frame, "Total File Diuji:", str(len(results_data)), 0)
        create_spec_row(perf_frame, "Total Durasi Uji:", f"{total_duration:.2f} detik", 1)
        create_spec_row(perf_frame, "Total Percobaan:", f"{total_attempts}", 2)
        create_spec_row(perf_frame, "Rata-rata Kecepatan:", f"{avg_speed:.2f} PIN/detik", 3)

        self._create_plots(cpu_history, mem_history)

    def _create_plots(self, cpu_history, mem_history):
        if not cpu_history:
            ttk.Label(self.plot_frame, text="Tidak ada data kinerja untuk ditampilkan. Jalankan pengujian terlebih dahulu.").pack(pady=20)
            return

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), dpi=100, sharex=True)
        
        ax1.plot(cpu_history, label='CPU Usage', color='royalblue')
        ax1.set_title('Penggunaan CPU Selama Uji', fontsize=12)
        ax1.set_ylabel('Usage (%)')
        ax1.grid(True, linestyle='--', alpha=0.6)
        ax1.fill_between(range(len(cpu_history)), cpu_history, color="royalblue", alpha=0.2)
        ax1.set_ylim(0, 100)

        ax2.plot(mem_history, label='Memory Usage', color='seagreen')
        ax2.set_title('Penggunaan Memori Selama Uji', fontsize=12)
        ax2.set_xlabel('Waktu (detik)')
        ax2.set_ylabel('Usage (%)')
        ax2.grid(True, linestyle='--', alpha=0.6)
        ax2.fill_between(range(len(mem_history)), mem_history, color="seagreen", alpha=0.2)
        ax2.set_ylim(0, 100)

        fig.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        canvas.draw()
        self.image_references.append(canvas)

    def generate_report_assets(self, index=0):
        """Menghasilkan aset seperti QR code dan signature untuk laporan PDF."""
        try: locale.setlocale(locale.LC_TIME, 'id_ID')
        except locale.Error: locale.setlocale(locale.LC_TIME, '')
        
        now = datetime.now()
        date_str = now.strftime("%A, %d %B %Y")

        signature_text = f"""
                Jakarta, {date_str}
                
                [QR_PLACEHOLDER]
"""
        timestamp = f"{int(time.time() * 1000)}_{index}"
        qr_path = os.path.join(tempfile.gettempdir(), f"perf_qr_{timestamp}.png")
        qrcode.make(self.app_controller.user_name.get()).save(qr_path)

        return signature_text, qr_path

    def generate_pdf_elements(self):
        elements = []
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='TimesBody', fontName='Times-Roman', fontSize=11, leading=14))
        styles.add(ParagraphStyle(name='TimesBold', parent=styles['TimesBody'], fontName='Times-Bold'))
        
        # 1. Spesifikasi Sistem
        elements.append(Paragraph("<b>1. Spesifikasi Sistem</b>", styles['TimesBold']))
        sys_info = self.app_controller.system_info
        spec_text = f"""
        Nama Perangkat: {sys_info.get('hostname', 'N/A')}<br/>
        Sistem Operasi: {sys_info.get('os', 'N/A')}<br/>
        CPU: {sys_info.get('cpu', 'N/A')}<br/>
        Cores: {sys_info.get('cores', 'N/A')}<br/>
        Total RAM: {sys_info.get('ram', 'N/A')}<br/>
        GPU: {sys_info.get('gpu', 'N/A')}
        """
        elements.append(Paragraph(spec_text, styles['TimesBody']))
        elements.append(Spacer(1, 8))

        # 2. Hasil Pengujian
        elements.append(Paragraph("<b>2. Hasil Pengujian</b>", styles['TimesBold']))
        results = self.app_controller.results_data
        total_duration = sum(float(r['Durasi Proses']) for r in results)
        total_attempts = sum(r['Total Percobaan'] for r in results)
        avg_speed = (total_attempts / total_duration) if total_duration > 0 else 0
        metric_text = f"""
        Total File Diuji: {len(results)}<br/>
        Total Durasi Uji: {total_duration:.2f} detik<br/>
        Rata-rata Kecepatan: {avg_speed:.2f} PIN/detik
        """
        elements.append(Paragraph(metric_text, styles['TimesBody']))
        elements.append(Spacer(1, 8))

        # 3. Analisis Kinerja & Grafik
        elements.append(Paragraph("<b>3. Analisis Kinerja</b>", styles['TimesBold']))
        cpu_hist = self.app_controller.cpu_usage_history
        if cpu_hist:
            avg_cpu = sum(cpu_hist) / len(cpu_hist)
            max_cpu = max(cpu_hist)
            analysis_text = f"""
            Selama proses pengujian, penggunaan CPU rata-rata tercatat sebesar <b>{avg_cpu:.2f}%</b>, dengan puncak mencapai <b>{max_cpu:.2f}%</b>. 
            Grafik di bawah ini menunjukkan fluktuasi penggunaan sumber daya (CPU dan Memori) dari waktu ke waktu selama pengujian berlangsung. 
            Kinerja yang lebih tinggi pada CPU dan kecepatan I/O disk akan secara signifikan mengurangi durasi pengujian.
            """
            elements.append(Paragraph(analysis_text, styles['TimesBody']))
            elements.append(Spacer(1, 4))

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5), dpi=300)
                ax1.plot(cpu_hist, color='royalblue'); ax1.set_title('Penggunaan CPU Selama Uji'); ax1.set_ylabel('Usage (%)'); ax1.set_ylim(0, 100)
                ax2.plot(self.app_controller.memory_usage_history, color='seagreen'); ax2.set_title('Penggunaan Memori Selama Uji'); ax2.set_ylabel('Usage (%)'); ax2.set_ylim(0, 100)
                fig.tight_layout()
                fig.savefig(tmp_file.name, format='png')
                plt.close(fig)
                elements.append(ReportlabImage(tmp_file.name, width=180*mm, height=112.5*mm, hAlign='CENTER'))
        else:
            elements.append(Paragraph("Tidak ada data monitoring kinerja yang direkam. Jalankan pengujian untuk melihat analisis.", styles['TimesBody']))
        
        elements.append(Spacer(1, 18))

        # Signature
        signature_text, qr_path = self.generate_report_assets()
        if qr_path and os.path.exists(qr_path):
            qr_img = ReportlabImage(qr_path, width=80, height=80, hAlign='RIGHT')
            clean_signature = signature_text.replace("[QR_PLACEHOLDER]", '')
            sig_style = ParagraphStyle('Signature', parent=styles['TimesBody'], alignment=TA_RIGHT)
            sig_table = Table([[Paragraph(clean_signature.replace('\n', '<br/>'), sig_style)], [qr_img]], colWidths=['100%'])
            sig_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('BOTTOMPADDING', (0, 0), (0, 0), 6)]))
            elements.append(sig_table)

        return elements

    def save_as_pdf(self):
        fp = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Documents", "*.pdf")], title="Simpan Laporan Kinerja")
        if fp:
            Thread(target=self.app_controller._generate_pdf, args=(fp, False, "Laporan Kinerja Perangkat", self.generate_pdf_elements), daemon=True).start()

    def print_report(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            Thread(target=self.app_controller._generate_pdf, args=(tmp_file.name, True, "Laporan Kinerja Perangkat", self.generate_pdf_elements), daemon=True).start()


# ==============================================================================
# KELAS-KELAS DIALOG & HANDLER
# ==============================================================================
class MultiRecoveryDialog(Toplevel):
    def __init__(self, parent, files_to_recover):
        super().__init__(parent)
        self.title("Metode Pemulihan Sandi")
        self.geometry("700x500")
        self.transient(parent)
        self.grab_set()
        
        self.files_to_recover = files_to_recover
        self.master_app = parent
        self.securing_thread = None
        
        self.password_vars = {} 
        
        self.build_widgets()

    def build_widgets(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(main_frame, text="Pengaturan Sandi Baru", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky='w', pady=(0, 15))
        
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.grid(row=1, column=0, sticky='nsew')
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=(10,0))

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

        ttk.Label(scrollable_frame, text="Nama File", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, padx=5, pady=5, sticky='w')
        ttk.Label(scrollable_frame, text="Sandi Baru (Dapat Diubah)", font=("Segoe UI", 10, "bold")).grid(row=0, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(scrollable_frame, text="Aksi", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, padx=5, pady=5, sticky='w')
        
        for i, file_info in enumerate(self.files_to_recover, start=1):
            filename = os.path.basename(file_info['file_path'])
            
            pass_var = tk.StringVar(value=self.generate_random_password())
            self.password_vars[file_info['file_path']] = pass_var

            ttk.Label(scrollable_frame, text=filename, wraplength=200).grid(row=i, column=0, padx=5, pady=5, sticky='w')
            
            pass_entry = ttk.Entry(scrollable_frame, textvariable=pass_var, width=25, font=("Consolas", 10))
            pass_entry.grid(row=i, column=1, padx=5, pady=5, sticky='we')
            
            change_btn = ttk.Button(scrollable_frame, text="Ganti", command=lambda v=pass_var: v.set(self.generate_random_password()))
            change_btn.grid(row=i, column=2, padx=5, pady=5)

        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=2, column=0, sticky='ew', pady=(15, 0))
        
        self.status_label = ttk.Label(bottom_frame, text="", font=("Segoe UI", 9))
        self.status_label.pack(side=tk.LEFT, anchor='w')

        self.secure_button = ttk.Button(bottom_frame, text="Amankan & Simpan", command=self.start_securing_files)
        self.secure_button.pack(side=tk.RIGHT)
        self.close_button = ttk.Button(bottom_frame, text="Batal", command=self.destroy)
        self.close_button.pack(side=tk.RIGHT, padx=10)

    def generate_random_password(self, length=14):
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(random.choice(alphabet) for _ in range(length))

    def start_securing_files(self):
        dest_dir = filedialog.askdirectory(title="Pilih Folder Tujuan untuk Menyimpan File Aman")
        if not dest_dir:
            return
            
        passwords_to_use = {}
        for file_path, pass_var in self.password_vars.items():
            password = pass_var.get()
            if not password:
                messagebox.showerror("Sandi Kosong", f"Sandi untuk file {os.path.basename(file_path)} tidak boleh kosong.", parent=self)
                return
            passwords_to_use[file_path] = password

        self.secure_button.config(state="disabled")
        self.close_button.config(state="disabled")
        self.status_label.config(text="Memproses... mohon tunggu.")

        self.securing_thread = Thread(target=self._threaded_secure_task, args=(dest_dir, passwords_to_use), daemon=True)
        self.securing_thread.start()
        self.after(100, self._monitor_securing_thread)

    def _monitor_securing_thread(self):
        if self.securing_thread.is_alive():
            self.after(100, self._monitor_securing_thread)
        else:
            self.secure_button.config(state="normal")
            self.close_button.config(state="normal")
            self.status_label.config(text="Selesai.")

    def _threaded_secure_task(self, dest_dir, passwords_to_use):
        final_passwords_log = {}
        all_success = True
        error_messages = []

        try:
            with tempfile.TemporaryDirectory() as main_temp_dir:
                for file_info in self.files_to_recover:
                    file_path = file_info['file_path']
                    old_password = file_info['old_password']
                    file_type = file_info['file_type']
                    original_filename = os.path.basename(file_path)
                    new_password = passwords_to_use[file_path]
                    
                    self.master_app.logger.info(f"Mengamankan '{original_filename}'...")
                    
                    extract_path = os.path.join(main_temp_dir, os.path.splitext(original_filename)[0] + str(random.randint(1000,9999)))
                    os.makedirs(extract_path, exist_ok=True)

                    # --- LANGKAH 1: Ekstrak Konten ---
                    try:
                        if file_type == 'ZIP':
                            with zipfile.ZipFile(file_path, 'r') as zf:
                                pwd_bytes = old_password.encode('utf-8') if old_password else None
                                zf.extractall(path=extract_path, pwd=pwd_bytes)
                        elif file_type == 'RAR':
                            with rarfile.RarFile(file_path, 'r') as rf:
                                rf.extractall(path=extract_path, pwd=old_password)
                        elif file_type == '7Z':
                            pwd_7z = old_password if old_password else None
                            with py7zr.SevenZipFile(file_path, 'r', password=pwd_7z) as z:
                                z.extractall(path=extract_path)
                        elif file_type == 'PDF':
                             shutil.copy2(file_path, extract_path)
                    except Exception as e:
                        self.master_app.logger.error(f"Gagal mengekstrak '{original_filename}': {e}")
                        error_messages.append(f"Gagal ekstrak {original_filename}: {e}")
                        all_success = False
                        continue

                    # --- LANGKAH 2: Enkripsi Ulang Sesuai Format Asli ---
                    new_save_path = os.path.join(dest_dir, f"AMAN_{original_filename}")
                    new_filename_for_log = os.path.basename(new_save_path)

                    try:
                        if file_type == 'PDF':
                            path_to_process = os.path.join(extract_path, original_filename)
                            reader = PyPDF2.PdfReader(path_to_process)
                            writer = PyPDF2.PdfWriter()
                            if reader.is_encrypted:
                                reader.decrypt(old_password)
                            for page in reader.pages:
                                writer.add_page(page)
                            writer.encrypt(new_password)
                            with open(new_save_path, 'wb') as f:
                                writer.write(f)

                        elif file_type == '7Z':
                            with py7zr.SevenZipFile(new_save_path, 'w', password=new_password) as new_7z:
                                new_7z.writeall(extract_path, arcname='.')
                        
                        elif file_type == 'ZIP':
                            files_to_compress = []
                            arcnames = []
                            for root, _, files in os.walk(extract_path):
                                for file in files:
                                    full_path = os.path.join(root, file)
                                    arcname = os.path.relpath(full_path, extract_path)
                                    files_to_compress.append(full_path)
                                    arcnames.append(arcname)
                            if files_to_compress:
                                pyminizip.compress_multiple(files_to_compress, arcnames, new_save_path, new_password, 9)

                        elif file_type == 'RAR':
                            try:
                                source_content = os.path.join(extract_path, '*')
                                cmd = ['rar', 'a', f'-hp{new_password}', new_save_path, source_content]
                                subprocess.run(cmd, check=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)
                            except (FileNotFoundError, subprocess.CalledProcessError) as rar_e:
                                self.master_app.logger.warning(f"Gagal membuat RAR untuk '{original_filename}' (Error: {rar_e}). Fallback ke format .7z.")
                                new_filename_base = os.path.splitext(original_filename)[0]
                                new_save_path_7z = os.path.join(dest_dir, f"AMAN_{new_filename_base}.7z")
                                new_filename_for_log = os.path.basename(new_save_path_7z)
                                with py7zr.SevenZipFile(new_save_path_7z, 'w', password=new_password) as new_7z:
                                    new_7z.writeall(extract_path, arcname='.')
                        
                        final_passwords_log[new_filename_for_log] = new_password
                        self.master_app.logger.info(f"Berhasil mengamankan '{original_filename}' ke '{new_filename_for_log}'.")

                    except (FileNotFoundError, subprocess.CalledProcessError) as e:
                        tool = 'rar'
                        self.master_app.logger.error(f"Gagal mengamankan '{original_filename}'. Program '{tool}' mungkin tidak terinstal atau ada error: {e}")
                        error_messages.append(f"Gagal amankan {original_filename}: Program '{tool}' tidak ditemukan.")
                        all_success = False
                        continue
                    except Exception as e:
                        self.master_app.logger.error(f"Gagal mengamankan '{original_filename}': {e}", exc_info=True)
                        error_messages.append(f"Gagal amankan {original_filename}: {e}")
                        all_success = False
                        continue

                # --- LANGKAH 3: Buat Laporan dan Tampilkan Hasil ---
                if final_passwords_log:
                    password_file_path = os.path.join(dest_dir, '_Passwords_List.txt')
                    with open(password_file_path, 'a', encoding='utf-8') as f:
                        if f.tell() == 0:
                           f.write(f"Daftar Sandi Baru Dibuat pada: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                           f.write("="*40 + "\n\n")
                        for filename, password in final_passwords_log.items():
                            f.write(f"File      : {filename}\n")
                            f.write(f"Password  : {password}\n")
                            f.write("-" * 20 + "\n")
                
                final_message = []
                if all_success:
                    final_message.append(f"Semua file berhasil diamankan di:\n{dest_dir}")
                else:
                    final_message.append(f"Beberapa file gagal diproses.")
                
                if final_passwords_log:
                     final_message.append(f"\nDaftar sandi baru disimpan di:\n{password_file_path}")

                if error_messages:
                    final_message.append("\n\nDetail Error:\n- " + "\n- ".join(error_messages))
                
                self.master_app.after(0, lambda: messagebox.showinfo("Proses Selesai", "\n".join(final_message), parent=self))
                self.master_app.after(100, self.destroy)

        except Exception as e:
            self.master_app.logger.error(f"Terjadi kesalahan fatal saat proses pengamanan: {e}", exc_info=True)
            self.master_app.after(0, lambda: messagebox.showerror("Kesalahan Fatal", f"Proses pengamanan gagal total.\n\nError: {e}", parent=self))


class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        self.log_queue.put(self.format(record) + '\n')

# ==============================================================================
# BLOK EKSEKUSI UTAMA
# ==============================================================================
if __name__ == "__main__":
    try:
        rarfile.tool_setup()
    except rarfile.RarCannotExec:
        messagebox.showwarning("Dependensi RAR Hilang", "Program 'unrar' atau 'rar' tidak ditemukan di sistem PATH Anda.\nFungsi untuk file .RAR tidak akan bekerja.")
    
    if not os.path.isdir(ASSET_DIR):
        os.makedirs(ASSET_DIR, exist_ok=True)
        messagebox.showinfo("Direktori Aset Dibuat", f"Direktori aset tidak ditemukan dan telah dibuat di:\n{ASSET_DIR}\n\nPastikan 'logo.png' ada di dalam folder 'img' di dalam 'asset'.")

    app = App()
    app.mainloop()
