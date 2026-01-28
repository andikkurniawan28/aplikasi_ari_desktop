import tkinter as tk
from tkinter import ttk, messagebox
import requests
import serial
import threading
import serial.tools.list_ports
import re
import os
import sys

# === ICON SETUP ===
# Coba load icon untuk window (hanya untuk GUI, bukan untuk EXE)
try:
    # Cek jika running sebagai EXE
    if getattr(sys, 'frozen', False):
        # Running sebagai EXE
        base_path = sys._MEIPASS
    else:
        # Running sebagai script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    # Cari file icon
    icon_path = os.path.join(base_path, 'qc.ico')
    if os.path.exists(icon_path):
        icon_available = True
    else:
        icon_available = False
except:
    icon_available = False

API_BASE = "http://192.168.29.231/silab-v4/input_ari_from_python.php"

# === SERIAL CONFIG ===
SERIAL_PORT = "COM5"   # nilai default
BAUDRATE = 9600
serial_thread = None
ser = None
serial_running = False

# Variabel untuk menyimpan data yang belum diisi
pending_data = []
current_data_index = 0

def get_available_ports():
    """Mendapatkan daftar port serial yang tersedia"""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def update_port_list():
    """Memperbarui daftar port di combobox"""
    available_ports = get_available_ports()
    combo_port['values'] = available_ports
    
    # Jika port default tersedia, pilih itu
    if SERIAL_PORT in available_ports:
        combo_port.set(SERIAL_PORT)
    elif available_ports:
        combo_port.set(available_ports[0])
    else:
        combo_port.set("")

def extract_number_from_pattern(pattern_str):
    """
    Jika mengandung '*' → dianggap tidak valid → return 0.0
    """
    if not pattern_str:
        return 0.0

    # Jika ada tanda '*' → INVALID
    if '*' in pattern_str:
        return 0.0

    # Cari angka valid
    match = re.search(r'-?\d+(\.\d+)?', pattern_str)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return 0.0

    return 0.0

def baca_serial():
    """Thread untuk membaca data dari Saccharomat"""
    global ser, serial_running
    selected_port = combo_port.get()
    
    if not selected_port:
        append_raw_response("[SERIAL] Error: Pilih port COM terlebih dahulu!")
        return
    
    try:
        ser = serial.Serial(selected_port, BAUDRATE, timeout=1)
        serial_running = True
        append_raw_response(f"[SERIAL] Koneksi berhasil ke {selected_port}")
    except Exception as e:
        append_raw_response(f"[SERIAL] Gagal buka serial: {e}")
        serial_running = False
        root.after(0, lambda: btn_serial.config(text="Start: OFF", style="Danger.TButton"))
        return

    while serial_running:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

            # tampilkan raw line ke text_raw
            root.after(0, lambda l=line: append_raw_response(f"[SERIAL] {l}"))

            # split berdasarkan spasi
            parts = line.split()
            
            # Debug: tampilkan parts
            append_raw_response(f"[DEBUG] Parts: {parts}")
            
            # Coba parsing format yang ada
            if len(parts) >= 4:
                # Format: "69.78  -0.01  *90****  *90***"
                try:
                    # Ambil angka pertama (69.78) untuk Pol Baca
                    pol_baca_val = float(parts[0])
                    
                    # Ambil angka kedua (-0.01) untuk Brix
                    brix_val = float(parts[1])
                    
                    # Untuk Pol, coba ekstrak dari pola *90**** atau *90***
                    pol_val = float(parts[2])
                    
                    append_raw_response(f"[DEBUG] Parsed: Pol Baca={pol_baca_val}, Brix={brix_val}, Pol={pol_val}")
                    
                    # Update entries
                    root.after(0, lambda pb=pol_baca_val, b=brix_val, p=pol_val: update_entries(pb, b, p))
                    
                except (ValueError, IndexError) as e:
                    append_raw_response(f"[DEBUG] Error parsing: {e}")
                    
            elif len(parts) >= 3:
                # Coba format alternatif
                numbers = []
                for p in parts:
                    try:
                        numbers.append(float(p))
                    except ValueError:
                        continue
                
                if len(numbers) >= 2:
                    # Asumsi: angka pertama adalah Pol Baca, kedua adalah Brix
                    pol_baca_val = numbers[0]
                    brix_val = numbers[1]
                    pol_val = numbers[2]
                    
                    root.after(0, lambda pb=pol_baca_val, b=brix_val, p=pol_val: update_entries(pb, b, p))
                    append_raw_response(f"[DEBUG] Numbers parsed: Pol Baca={pol_baca_val}, Brix={brix_val}, Pol={pol_val}")

        except Exception as e:
            if serial_running:  # Hanya tampilkan error jika masih running
                append_raw_response(f"[SERIAL] Error: {e}")
            break
    
    # Jika keluar dari loop, tutup koneksi
    if ser and ser.is_open:
        ser.close()

def append_raw_response(line):
    """Tambahkan baris baru ke Raw Response"""
    text_raw.config(state="normal")
    text_raw.insert(tk.END, line + "\n")
    text_raw.see(tk.END)  # auto scroll ke bawah
    text_raw.config(state="disabled")

def update_entries(pol_baca_val, brix_val, pol_val):
    """Update entry fields dengan data dari serial"""
    # Pol Baca
    entry_pol_baca.config(state="normal")
    entry_pol_baca.delete(0, tk.END)
    entry_pol_baca.insert(0, str(pol_baca_val))
    entry_pol_baca.config(state="readonly")

    # Brix
    entry_brix.config(state="normal")
    entry_brix.delete(0, tk.END)
    entry_brix.insert(0, str(brix_val))
    entry_brix.config(state="readonly")

    # Pol
    entry_pol.config(state="normal")
    entry_pol.delete(0, tk.END)
    entry_pol.insert(0, str(pol_val))
    entry_pol.config(state="readonly")

    # Hitung rendemen otomatis
    hitung_rendemen()

def hitung_rendemen(*args):
    try:
        brix_val = float(entry_brix.get())
        pol_val = float(entry_pol.get())
    except ValueError:
        # Jika belum valid angka, kosongkan rendemen
        entry_rendemen.config(state="normal")
        entry_rendemen.delete(0, tk.END)
        entry_rendemen.config(state="readonly")
        return

    rendemen_val = 0.7 * (pol_val - 0.5 * (brix_val - pol_val))
    rendemen_str = f"{rendemen_val:.2f}"

    entry_rendemen.config(state="normal")
    entry_rendemen.delete(0, tk.END)
    entry_rendemen.insert(0, rendemen_str)
    entry_rendemen.config(state="readonly")

def load_pending_data():
    """Memuat data yang belum diisi dari API"""
    global pending_data, current_data_index
    
    try:
        append_raw_response("[APP] Memuat data yang belum diisi...")
        response = requests.get(API_BASE, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success':
                pending_data = data['data']
                current_data_index = 0
                
                if pending_data:
                    # Tampilkan data pertama
                    show_current_data()
                    append_raw_response(f"[APP] {len(pending_data)} data ditemukan")
                else:
                    append_raw_response("[APP] Tidak ada data yang belum diisi")
                    entry_nomor_gelas.delete(0, tk.END)
            else:
                append_raw_response(f"[APP] Error: {data.get('message', 'Unknown error')}")
        else:
            append_raw_response(f"[APP] Error: Status {response.status_code}")
            
    except Exception as e:
        append_raw_response(f"[APP] Error loading data: {e}")

def show_current_data():
    """Menampilkan data saat ini ke field kartu_ari"""
    global pending_data, current_data_index
    
    if pending_data and current_data_index < len(pending_data):
        data = pending_data[current_data_index]
        
        # Tampilkan kartu_ari (sebagai barcode)
        entry_nomor_gelas.delete(0, tk.END)
        
        # Tampilkan id atau kartu_ari berdasarkan format data
        if isinstance(data, dict) and 'id' in data:
            # Format baru: {"id": 1, "kartu_ari": "123456"}
            entry_nomor_gelas.insert(0, data['kartu_ari'])
            append_raw_response(f"[DATA] Kartu ARI: {data['kartu_ari']} (ID: {data['id']})")
        else:
            # Format lama: hanya string kartu_ari
            entry_nomor_gelas.insert(0, str(data))
            append_raw_response(f"[DATA] Kartu ARI: {data}")
        
        # Update label status
        lbl_status.config(text=f"Data {current_data_index + 1} dari {len(pending_data)}")
        # btn_prev.config(state="normal" if current_data_index > 0 else "disabled")
        # btn_next.config(state="normal" if current_data_index < len(pending_data) - 1 else "disabled")
    else:
        lbl_status.config(text="Tidak ada data")

def show_api_alert(title, message):
    """Menampilkan alert untuk respon API"""
    # Buat window alert baru
    alert_window = tk.Toplevel(root)
    alert_window.title(title)
    alert_window.geometry("400x300")
    alert_window.transient(root)  # Set sebagai child window
    alert_window.grab_set()  # Modal window
    
    # Center window
    alert_window.update_idletasks()
    width = alert_window.winfo_width()
    height = alert_window.winfo_height()
    x = (alert_window.winfo_screenwidth() // 2) - (width // 2)
    y = (alert_window.winfo_screenheight() // 2) - (height // 2)
    alert_window.geometry(f'{width}x{height}+{x}+{y}')
    
    # Frame untuk konten
    frame = ttk.Frame(alert_window, padding="20")
    frame.pack(fill=tk.BOTH, expand=True)
    
    # Icon/warna berdasarkan judul
    if "BERHASIL" in title or "SUCCESS" in title:
        color = "#28a745"  # Hijau
        icon_text = "✓"
    elif "GAGAL" in title or "ERROR" in title:
        color = "#dc3545"  # Merah
        icon_text = "✗"
    else:
        color = "#007bff"  # Biru
        icon_text = "ℹ"
    
    # Icon
    icon_label = tk.Label(frame, text=icon_text, font=("Arial", 48), fg=color)
    icon_label.pack(pady=(0, 10))
    
    # Judul
    title_label = ttk.Label(frame, text=title, font=("Arial", 14, "bold"))
    title_label.pack(pady=(0, 10))
    
    # Message dengan scrollbar
    msg_frame = ttk.Frame(frame)
    msg_frame.pack(fill=tk.BOTH, expand=True)
    
    text_msg = tk.Text(msg_frame, height=8, wrap="word", font=("Arial", 10))
    text_msg.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    scrollbar = ttk.Scrollbar(msg_frame, command=text_msg.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text_msg.config(yscrollcommand=scrollbar.set)
    
    text_msg.insert("1.0", message)
    text_msg.config(state="disabled")
    
    # Tombol OK
    btn_ok = ttk.Button(frame, text="OK", 
                       command=alert_window.destroy,
                       width=15)
    btn_ok.pack(pady=(20, 0))
    
    # Bind Enter dan Escape untuk menutup window
    alert_window.bind("<Return>", lambda e: alert_window.destroy())
    alert_window.bind("<Escape>", lambda e: alert_window.destroy())
    
    # Fokus ke tombol OK
    alert_window.after(100, btn_ok.focus)

def submit_action():
    """Kirim data ke API"""
    global pending_data, current_data_index
    
    kartu_ari = entry_nomor_gelas.get()
    
    # Validasi input kosong
    if not kartu_ari:
        messagebox.showerror("Error", "Kartu ARI harus diisi!")
        return
    
    try:
        brix_val = float(entry_brix.get())
        pol_val = float(entry_pol.get())
        pol_baca_val = float(entry_pol_baca.get())
        rendemen_val = float(entry_rendemen.get())
    except ValueError:
        messagebox.showerror("Error", "Pastikan semua input berupa angka!")
        return

    # Tampilkan data yang akan dikirim di console (debug only)
    append_raw_response(f"[APP] Mengirim data untuk Kartu ARI: {kartu_ari}")
    append_raw_response(f"[DATA] Brix ARI: {brix_val}")
    append_raw_response(f"[DATA] Pol ARI: {pol_val}")
    append_raw_response(f"[DATA] Pol Baca ARI: {pol_baca_val}")
    append_raw_response(f"[DATA] Rendemen ARI: {rendemen_val}")

    # Kirim ke API dengan GET
    try:
        params = {
            'kartu_ari': kartu_ari,
            'brix_ari': brix_val,
            'pol_ari': pol_val,
            'pol_baca_ari': pol_baca_val,
            'rendemen_ari': rendemen_val
        }
        
        # Jika ada ID dari data yang dipending, tambahkan parameter id
        if pending_data and current_data_index < len(pending_data):
            data = pending_data[current_data_index]
            if isinstance(data, dict) and 'id' in data:
                params['id'] = data['id']
        
        response = requests.get(API_BASE, params=params, timeout=5)
        
        # Tampilkan respon API di console (debug)
        append_raw_response(f"[API] Status Code: {response.status_code}")
        append_raw_response(f"[API] Response: {response.text}")
        
        # Tampilkan alert untuk pengguna
        if response.status_code == 200:
            # Parse response JSON
            try:
                response_data = response.json()
                if response_data['status'] == 'success':
                    title = "BERHASIL"
                    message = f"Data berhasil dikirim!\n\n"
                    message += f"Kartu ARI: {kartu_ari}\n"
                    message += f"Brix ARI: {brix_val}\n"
                    message += f"Pol ARI: {pol_val}\n"
                    message += f"Pol Baca ARI: {pol_baca_val}\n"
                    message += f"Rendemen ARI: {rendemen_val}\n\n"
                    message += f"Response API:\n{response_data['message']}"
                    show_api_alert(title, message)   
                else:
                    title = "GAGAL"
                    message = f"Gagal mengirim data!\n\n"
                    message += f"Error: {response_data.get('message', 'Unknown error')}"
                    show_api_alert(title, message)
            except:
                # Jika response bukan JSON
                title = "PERHATIAN"
                message = f"Data telah dikirim dengan status {response.status_code}\n\n"
                message += f"Response API:\n{response.text}"
                show_api_alert(title, message)
        else:
            title = "GAGAL"
            message = f"Gagal mengirim data!\n"
            message += f"Status Code: {response.status_code}\n"
            message += f"Error: {response.text}"
            show_api_alert(title, message)
            
    except requests.exceptions.Timeout:
        title = "ERROR"
        message = "Timeout: Koneksi ke API terlalu lama.\nPeriksa koneksi jaringan Anda."
        show_api_alert(title, message)
        append_raw_response("[API] Error: Timeout")
    except requests.exceptions.ConnectionError:
        title = "ERROR"
        message = "Tidak dapat terhubung ke server API.\nPeriksa koneksi jaringan atau alamat API."
        show_api_alert(title, message)
        append_raw_response("[API] Error: Connection error")
    except Exception as e:
        title = "ERROR"
        message = f"Terjadi kesalahan:\n{str(e)}"
        show_api_alert(title, message)
        append_raw_response(f"[API] Error: {e}")

def reset_form():
    """Reset semua input field"""
    global pending_data, current_data_index
    
    # Reset field input
    entry_nomor_gelas.delete(0, tk.END)
    
    # Reset field yang dari serial
    entry_brix.config(state="normal")
    entry_brix.delete(0, tk.END)
    entry_brix.config(state="readonly")
    
    entry_pol.config(state="normal")
    entry_pol.delete(0, tk.END)
    entry_pol.config(state="readonly")
    
    entry_pol_baca.config(state="normal")
    entry_pol_baca.delete(0, tk.END)
    entry_pol_baca.config(state="readonly")
    
    entry_rendemen.config(state="normal")
    entry_rendemen.delete(0, tk.END)
    entry_rendemen.config(state="readonly")
    
    # Reset status
    pending_data = []
    current_data_index = 0
    lbl_status.config(text="Tidak ada data")
    # btn_prev.config(state="disabled")
    # btn_next.config(state="disabled")
    
    entry_nomor_gelas.focus()

def prev_data():
    """Pindah ke data sebelumnya"""
    global current_data_index
    if current_data_index > 0:
        current_data_index -= 1
        show_current_data()

def next_data():
    """Pindah ke data berikutnya"""
    global current_data_index
    if current_data_index < len(pending_data) - 1:
        current_data_index += 1
        show_current_data()

def toggle_serial():
    """Toggle koneksi serial ON/OFF"""
    global serial_thread, serial_running
    
    if serial_running and ser and ser.is_open:
        # Matikan serial
        serial_running = False
        ser.close()
        btn_serial.config(text="Start: OFF", style="Danger.TButton")
        append_raw_response("[SERIAL] Koneksi serial dimatikan")
        combo_port.config(state="readonly")
        btn_refresh.config(state="normal")
    else:
        # Cek apakah port dipilih
        selected_port = combo_port.get()
        if not selected_port:
            messagebox.showerror("Error", "Pilih port COM terlebih dahulu!")
            return
            
        # Nonaktifkan combobox saat serial berjalan
        combo_port.config(state="disabled")
        btn_refresh.config(state="disabled")
        
        # Hidupkan serial
        serial_thread = threading.Thread(target=baca_serial, daemon=True)
        serial_thread.start()
        btn_serial.config(text="Start: ON", style="Success.TButton")
        append_raw_response(f"[SERIAL] Menghidupkan koneksi serial ke {selected_port}...")

def refresh_ports():
    """Refresh daftar port COM yang tersedia"""
    update_port_list()
    append_raw_response("[SERIAL] Daftar port COM diperbarui")

# === GUI ===
root = tk.Tk()
root.title("Aplikasi Analisa Rendemen Individu")

# SET ICON UNTUK WINDOW
if icon_available:
    try:
        root.iconbitmap(icon_path)
        print("[APP] Custom icon loaded")
    except:
        print("[APP] Failed to load custom icon")

# Frame untuk kontrol serial
frame_control = ttk.LabelFrame(root, text="Kontrol", padding=10)
frame_control.grid(row=0, column=0, padx=10, pady=10, sticky="ew", columnspan=2)

# Label dan Combobox untuk port COM
ttk.Label(frame_control, text="Port COM:").grid(row=0, column=0, padx=5, pady=5, sticky="w")

combo_port = ttk.Combobox(frame_control, width=15, state="readonly")
combo_port.grid(row=0, column=1, padx=5, pady=5, sticky="w")

# Tombol Refresh Port
btn_refresh = ttk.Button(frame_control, text="Refresh", 
                        command=refresh_ports, width=10)
btn_refresh.grid(row=0, column=2, padx=5, pady=5)

# Tombol Serial
btn_serial = ttk.Button(frame_control, text="Start: OFF", 
                       command=toggle_serial, width=15)
btn_serial.grid(row=0, column=3, padx=5, pady=5)

# Label baudrate
ttk.Label(frame_control, text=f"Baudrate: {BAUDRATE}").grid(row=0, column=4, padx=5, pady=5)

# Frame untuk input data
frame_input = ttk.LabelFrame(root, text="Data", padding=10)
frame_input.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

# Kartu ARI (sebagai barcode)
def limit_6_characters(new_value):
    return len(new_value) <= 6

vcmd = (root.register(limit_6_characters), "%P")
ttk.Label(frame_input, text="Kartu ARI:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
entry_nomor_gelas = ttk.Entry(
    frame_input,
    width=20,
    validate="key",
    validatecommand=vcmd
)
entry_nomor_gelas.grid(row=0, column=1, padx=5, pady=5)
entry_nomor_gelas.focus()

# Status dan navigasi
lbl_status = ttk.Label(frame_input, text="Tidak ada data")
lbl_status.grid(row=0, column=2, padx=10, pady=5)

# Brix
ttk.Label(frame_input, text="Brix (%):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
entry_brix = ttk.Entry(frame_input, width=20)
entry_brix.grid(row=1, column=1, padx=5, pady=5)
entry_brix.config(state="readonly")  # Dibaca dari serial

# Pol
ttk.Label(frame_input, text="Pol (%):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
entry_pol = ttk.Entry(frame_input, width=20)
entry_pol.grid(row=2, column=1, padx=5, pady=5)
entry_pol.config(state="readonly")  # Dibaca dari serial

# Pol Baca
ttk.Label(frame_input, text="Pol Baca:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
entry_pol_baca = ttk.Entry(frame_input, width=20)
entry_pol_baca.grid(row=3, column=1, padx=5, pady=5)
entry_pol_baca.config(state="readonly")  # Dibaca dari serial

# Rendemen
ttk.Label(frame_input, text="Rendemen (%):").grid(row=4, column=0, sticky="w", padx=5, pady=5)
entry_rendemen = ttk.Entry(frame_input, state="readonly", width=20)
entry_rendemen.grid(row=4, column=1, padx=5, pady=5)

# Frame untuk tombol aksi
frame_tombol = ttk.LabelFrame(root, text="Aksi", padding=10)
frame_tombol.grid(row=2, column=0, padx=10, pady=10, sticky="ew", columnspan=2)

# Tombol Load Data
# btn_load = ttk.Button(frame_tombol, text="Load Data", 
#                       command=load_pending_data,
#                       style="Primary.TButton", width=12)
# btn_load.grid(row=0, column=0, padx=5, pady=5)

# Tombol Navigasi
# btn_prev = ttk.Button(frame_tombol, text="← Prev", 
#                       command=prev_data,
#                       width=10)
# btn_prev.grid(row=0, column=1, padx=5, pady=5)
# btn_prev.config(state="disabled")

# btn_next = ttk.Button(frame_tombol, text="Next →", 
#                       command=next_data,
#                       width=10)
# btn_next.grid(row=0, column=2, padx=5, pady=5)
# btn_next.config(state="disabled")

# Tombol Submit
btn_submit = ttk.Button(frame_tombol, text="SEND", 
                       command=submit_action,
                       style="Success.TButton", width=12)
btn_submit.grid(row=0, column=3, padx=5, pady=5)

# Tombol Reset
btn_reset = ttk.Button(frame_tombol, text="Reset", 
                      command=reset_form, width=10)
btn_reset.grid(row=0, column=4, padx=5, pady=5)

# Frame untuk output
frame_output = ttk.LabelFrame(root, text="Console", padding=10)
frame_output.grid(row=3, column=0, padx=10, pady=10, sticky="nsew", columnspan=2)

# Raw Response dengan scrollbar
text_frame = tk.Frame(frame_output)
text_frame.grid(row=0, column=0, sticky="nsew")

text_raw = tk.Text(text_frame, height=8, width=60, state="disabled", wrap="word")
text_raw.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

scrollbar = ttk.Scrollbar(text_frame, command=text_raw.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
text_raw.config(yscrollcommand=scrollbar.set)

# Tombol clear log
btn_clear = ttk.Button(frame_output, text="Clear Log", 
                      command=lambda: text_raw.config(state="normal") or text_raw.delete("1.0", tk.END) or text_raw.config(state="disabled"))
btn_clear.grid(row=1, column=0, pady=5)

# Konfigurasi grid untuk responsive layout
root.grid_rowconfigure(3, weight=1)
root.grid_columnconfigure(0, weight=1)
frame_output.grid_rowconfigure(0, weight=1)
frame_output.grid_columnconfigure(0, weight=1)

# Styling untuk tombol
style = ttk.Style()
style.configure("Primary.TButton", font=('Arial', 10, 'bold'), background='#007bff', foreground='black')
style.configure("Success.TButton", font=('Arial', 10, 'bold'), background='#28a745', foreground='black')
style.configure("Danger.TButton", font=('Arial', 10), background='#dc3545', foreground='black')

# Bind Enter key untuk memudahkan input
def focus_next_widget(event):
    event.widget.tk_focusNext().focus()
    return "break"

entry_nomor_gelas.bind("<Return>", focus_next_widget)

# Fitur auto-submit saat Enter di nomor gelas
def auto_submit_on_enter(event):
    """Auto submit jika field sudah terisi"""
    if entry_brix.get() and entry_pol.get() and entry_pol_baca.get():
        submit_action()
    return "break"

entry_nomor_gelas.bind("<Return>", auto_submit_on_enter)

# Inisialisasi daftar port
update_port_list()

# Pesan startup
append_raw_response("="*60)
append_raw_response("APLIKASI ANALISA RENDEMEN INDIVIDU")
append_raw_response("="*60)
append_raw_response("[APP] Aplikasi Analisa Rendemen Individu dimulai")
append_raw_response(f"[APP] API: {API_BASE}")
append_raw_response("[SERIAL] Pilih port COM dan klik 'Start: OFF' untuk menghidupkan")
append_raw_response("[SERIAL] Klik 'Refresh' untuk memperbarui daftar port COM")
# append_raw_response("[INFO] Klik 'Load Data' untuk mengambil data yang belum diisi")
append_raw_response("[INFO] Console ini hanya untuk debugging")
append_raw_response("[INFO] Respon API akan ditampilkan di popup alert")
append_raw_response("="*60)

# === FOOTER / CREDIT ===
frame_footer = ttk.Frame(root)
frame_footer.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))

lbl_credit = ttk.Label(
    frame_footer,
    text="- Andik Kurniawan -",
    font=("Arial", 9),
    foreground="black"
)
lbl_credit.pack(anchor="center")
root.grid_rowconfigure(4, weight=0)

root.mainloop()