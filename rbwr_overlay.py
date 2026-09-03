import tkinter as tk
from tkinter import ttk
import math
import sys
import os
import threading
import logging
import time
import traceback
import re
from datetime import datetime, timezone
import queue
import urllib.request
import urllib.error
from PIL import Image, ImageDraw, ImageTk

IS_LINUX = sys.platform.startswith('linux')
IS_WINDOWS = sys.platform == 'win32' or os.name == 'nt'
IS_MAC = sys.platform == 'darwin'

__version__ = "2.0.3"

# --- Update Server Configuration ---
BACKEND_SERVER_URL = "https://rbwr.hotment.dev"
UPDATE_HTTP_HEADERS = {'User-Agent': 'Mozilla/5.0'}

try:
    __compiled__  # pyright: ignore[reportUndefinedVariable, reportUnusedExpression]
    _is_compiled = True
except NameError:
    _is_compiled = False

_log_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if _is_compiled else os.path.dirname(os.path.abspath(__file__))
_log_path = os.path.join(_log_dir, "RBWR_APRM_Calculator.log")
_sanitization_mappings = []

def get_sanitization_mappings():
    mappings = []
    sources = [
        ("TEMP", "%temp%"),
        ("TMP", "%temp%"),
        ("LOCALAPPDATA", "%localappdata%"),
        ("APPDATA", "%appdata%"),
        ("USERPROFILE", "%userprofile%"),
    ]
    seen_variants = set()
    for var_name, placeholder in sources:
        path = os.environ.get(var_name)
        if not path:
            continue
        variants = [path]
        if os.name == 'nt':
            try:
                import ctypes
                buf = ctypes.create_unicode_buffer(1024)
                if ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024):
                    short = buf.value
                    if short not in variants:
                        variants.append(short)
            except Exception:
                pass
        for var in variants:
            var = var.rstrip('/\\')
            if not var or len(var) < 4:
                continue
            for slash_var in [var.replace('/', '\\'), var.replace('\\', '/')]:
                if slash_var.lower() not in seen_variants:
                    seen_variants.add(slash_var.lower())
                    pattern = re.compile(re.escape(slash_var), re.IGNORECASE)
                    mappings.append((pattern, placeholder))
    mappings.sort(key=lambda x: len(x[0].pattern), reverse=True)
    return mappings

_sanitization_mappings = get_sanitization_mappings()

def sanitize_string(text: str) -> str:
    if not text:
        return text
    for pattern, placeholder in _sanitization_mappings:
        text = pattern.sub(placeholder, text)
    return text

class SanitizingFormatter(logging.Formatter):
    def format(self, record):
        formatted = super().format(record)
        return sanitize_string(formatted)

file_handler = logging.FileHandler(_log_path, mode="w", encoding="utf-8")
stream_handler = logging.StreamHandler(sys.stdout)

formatter = SanitizingFormatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler],
)
# Silence noisy third-party loggers
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("onnxruntime").setLevel(logging.WARNING)
log = logging.getLogger("rbwr")

def show_crash_dialog(tb_text):
    try:
        crash_win = tk.Tk()
        crash_win.title("Application Crash Detected")
        
        if IS_WINDOWS and os.path.exists("icon.ico"):
            try:
                crash_win.iconbitmap("icon.ico")
            except Exception:
                pass
        else:
            try:
                crash_win.tk_icon = ImageTk.PhotoImage(get_default_icon_image())  # pyright: ignore[reportAttributeAccessIssue]
                crash_win.iconphoto(False, crash_win.tk_icon)  # pyright: ignore[reportArgumentType, reportAttributeAccessIssue]
            except Exception:
                pass

        crash_win.geometry("560x380")
        crash_win.configure(bg="#07080a")
        crash_win.attributes("-topmost", True)
        
        screen_width = crash_win.winfo_screenwidth()
        screen_height = crash_win.winfo_screenheight()
        x = (screen_width - 560) // 2
        y = (screen_height - 380) // 2
        crash_win.geometry(f"560x380+{x}+{y}")
        
        lbl_header = tk.Label(crash_win, text="CRITICAL EXCEPTION ENCOUNTERED", bg="#07080a", fg="#ff003c", font=("Segoe UI", 11, "bold"))
        lbl_header.pack(pady=(15, 5))
        
        lbl_sub = tk.Label(crash_win, text="The application has crashed. A detailed crash log was saved to the log file.\nPlease copy the traceback below to report this issue.", 
                           bg="#07080a", fg="#6c7d93", font=("Segoe UI", 8), justify="center", wraplength=520)
        lbl_sub.pack(pady=(0, 10))
        
        btn_frame = tk.Frame(crash_win, bg="#07080a")
        btn_frame.pack(side="bottom", fill="x", pady=15, padx=20)
        
        txt_frame = tk.Frame(crash_win, bg="#11141a", bd=1, relief="solid")
        txt_frame.pack(fill="both", expand=True, padx=20, pady=5)
        txt_frame.columnconfigure(0, weight=1)
        txt_frame.rowconfigure(0, weight=1)
        
        txt_tb = tk.Text(txt_frame, bg="#11141a", fg="#ffffff", insertbackground="#ffffff", font=("Consolas", 8), bd=0, wrap="none")
        txt_tb.insert("1.0", tb_text)
        txt_tb.config(state="disabled")
        txt_tb.grid(row=0, column=0, sticky="nsew")
        
        from tkinter import ttk
        style = ttk.Style(crash_win)
        style.theme_use('clam')
        style.configure("Dark.Vertical.TScrollbar",
                        gripcount=0,
                        background="#1f2430",
                        troughcolor="#07080a",
                        bordercolor="#11141a",
                        arrowcolor="#6c7d93",
                        lightcolor="#1f2430",
                        darkcolor="#1f2430")
        style.map("Dark.Vertical.TScrollbar",
                  background=[("active", "#3a4659"), ("pressed", "#6c7d93")])
                        
        scroll_y = ttk.Scrollbar(txt_frame, orient="vertical", command=txt_tb.yview, style="Dark.Vertical.TScrollbar")
        
        def scroll_set(first, last):
            first, last = float(first), float(last)
            if first <= 0.0 and last >= 1.0:
                scroll_y.grid_forget()
            else:
                scroll_y.grid(row=0, column=1, sticky="ns")
            scroll_y.set(first, last)
            
        txt_tb.config(yscrollcommand=scroll_set)
        
        def copy_to_clipboard():
            crash_win.clipboard_clear()
            crash_win.clipboard_append(tb_text)
            btn_copy.config(text="Copied!", fg="#39ff14")
            
        def open_github():
            import urllib.parse
            import webbrowser
            body_param = urllib.parse.quote(f"Please describe what you were doing when the crash occurred:\n\n```\n{tb_text}```")
            webbrowser.open(f"https://github.com/Hotment/RBWR-Utility/issues/new?body={body_param}")
            
        def close_app():
            crash_win.destroy()
            os._exit(1)
            
        import queue
        crash_queue = queue.Queue()
        
        def poll_crash_queue():
            try:
                while True:
                    fn, args, kwargs = crash_queue.get_nowait()
                    try:
                        fn(*args, **kwargs)
                    except Exception:
                        pass
                    crash_queue.task_done()
            except queue.Empty:
                pass
            crash_win.after(50, poll_crash_queue)
            
        crash_win.after(0, poll_crash_queue)

        def send_report():
            btn_send.config(text="Sending Report...", fg=ACCENT_GOLD)
            crash_win.update()
            
            log_data = ""
            try:
                if os.path.exists(_log_path):
                    with open(_log_path, "r", encoding="utf-8") as lf:
                        log_data = lf.read()
            except Exception:
                pass
                
            def perform_send():
                import urllib.request
                import platform
                os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
                payload = {
                    "version": __version__,
                    "traceback": tb_text,
                    "log_data": log_data,
                    "os_info": os_info
                }
                
                try:
                    data_bytes = json.dumps(payload).encode('utf-8')
                    req = urllib.request.Request(
                        f"{BACKEND_SERVER_URL}/crashes",
                        data=data_bytes,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "RBWR-Overlay-Client/1.0"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        if resp.status == 200:
                            crash_queue.put((lambda: btn_send.config(text="Report Sent!", fg=ACCENT_GREEN), (), {}))
                        else:
                            crash_queue.put((lambda: btn_send.config(text="Send Failed!", fg=ACCENT_RED), (), {}))
                except Exception:
                    crash_queue.put((lambda: btn_send.config(text="Send Failed!", fg=ACCENT_RED), (), {}))
                    
            threading.Thread(target=perform_send, daemon=True).start()

        btn_copy = tk.Label(btn_frame, text="Copy Traceback", bg="#11141a", fg="#00f0ff", font=("Segoe UI", 8, "bold"), bd=1, relief="solid", padx=10, pady=6, cursor="hand2")
        btn_copy.pack(side="left", padx=3)
        btn_copy.bind("<Button-1>", lambda e: copy_to_clipboard())
        
        btn_issue = tk.Label(btn_frame, text="Report on GitHub", bg="#11141a", fg="#ffaa00", font=("Segoe UI", 8, "bold"), bd=1, relief="solid", padx=10, pady=6, cursor="hand2")
        btn_issue.pack(side="left", padx=3)
        btn_issue.bind("<Button-1>", lambda e: open_github())

        btn_send = tk.Label(btn_frame, text="Send Report (Anon)", bg="#11141a", fg="#00f0ff", font=("Segoe UI", 8, "bold"), bd=1, relief="solid", padx=10, pady=6, cursor="hand2")
        btn_send.pack(side="left", padx=3)
        btn_send.bind("<Button-1>", lambda e: send_report())

        btn_close = tk.Label(btn_frame, text="Exit App", bg="#11141a", fg="#ff003c", font=("Segoe UI", 8, "bold"), bd=1, relief="solid", padx=10, pady=6, cursor="hand2")
        btn_close.pack(side="right", padx=3)
        btn_close.bind("<Button-1>", lambda e: close_app())
        
        crash_win.protocol("WM_DELETE_WINDOW", close_app)
        crash_win.mainloop()
    except Exception:
        if IS_WINDOWS:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, f"Critical Crash:\n{tb_text}", "RBWR Overlay Crash", 0x10)
            except Exception:
                pass
        else:
            print(f"Critical Crash:\n{tb_text}", file=sys.stderr)
        os._exit(1)

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_text = sanitize_string("".join(tb_lines))
    log.critical("Unhandled exception captured:\n" + tb_text)
    show_crash_dialog(tb_text)

def handle_thread_exception(args):
    handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

sys.excepthook = handle_exception
threading.excepthook = handle_thread_exception
tk.Tk.report_callback_exception = lambda self, exc_type, exc_value, exc_traceback: handle_exception(exc_type, exc_value, exc_traceback)  # pyright: ignore[reportAttributeAccessIssue]

log.info(f"=== RBWR APRM Calculator v{__version__} starting ===")
log.info(f"Version: {__version__}")
log.info(f"Python: {sys.version}")
log.info(f"Executable: {sys.executable}")
log.info(f"Script __file__: {__file__}")
log.info(f"Log file: {_log_path}")

def get_default_icon_image():
    try:
        img = Image.new("RGBA", (256, 256), color=(7, 8, 10, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([20, 20, 236, 236], outline=(0, 240, 255, 255), width=10)
        draw.ellipse([32, 32, 224, 224], fill=(17, 20, 26, 255))
        bolt = [(145, 55), (95, 135), (125, 135), (115, 195), (165, 115), (135, 115)]
        draw.polygon(bolt, fill=(57, 255, 20, 255))
        return img
    except Exception:
        return Image.new("RGBA", (64, 64), color=(0, 240, 255, 255))

def generate_default_icon():
    try:
        img = get_default_icon_image()
        img.save("icon.png")
        img.save("icon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except Exception:
        pass

def get_macos_active_app():
    if not IS_MAC:
        return "", ""
    try:
        from ctypes import c_void_p, c_char_p, cdll, util
        appkit_path = util.find_library('AppKit')
        objc_path = util.find_library('objc')
        if not appkit_path or not objc_path:
            return "", ""
        _ = cdll.LoadLibrary(appkit_path)
        objc = cdll.LoadLibrary(objc_path)
        
        objc.objc_getClass.restype = c_void_p
        objc.objc_getClass.argtypes = [c_char_p]
        objc.sel_registerName.restype = c_void_p
        objc.sel_registerName.argtypes = [c_char_p]
        objc.objc_msgSend.restype = c_void_p
        objc.objc_msgSend.argtypes = [c_void_p, c_void_p]
        
        NSWorkspace = objc.objc_getClass(b"NSWorkspace")
        if not NSWorkspace:
            return "", ""
        sharedWS = objc.objc_msgSend(NSWorkspace, objc.sel_registerName(b"sharedWorkspace"))
        if not sharedWS:
            return "", ""
        frontApp = objc.objc_msgSend(sharedWS, objc.sel_registerName(b"frontmostApplication"))
        if not frontApp:
            return "", ""
        
        name = ""
        name_obj = objc.objc_msgSend(frontApp, objc.sel_registerName(b"localizedName"))
        if name_obj:
            utf8_str = objc.objc_msgSend(name_obj, objc.sel_registerName(b"UTF8String"))
            if utf8_str:
                raw_val = c_char_p(utf8_str).value
                if raw_val is not None:
                    name = raw_val.decode('utf-8', errors='ignore')
        
        bundle_id = ""
        bundle_obj = objc.objc_msgSend(frontApp, objc.sel_registerName(b"bundleIdentifier"))
        if bundle_obj:
            utf8_bundle = objc.objc_msgSend(bundle_obj, objc.sel_registerName(b"UTF8String"))
            if utf8_bundle:
                raw_val = c_char_p(utf8_bundle).value
                if raw_val is not None:
                    bundle_id = raw_val.decode('utf-8', errors='ignore')
        
        return name, bundle_id
    except Exception:
        return "", ""

import ctypes
import json

CONFIG_FILE = "settings.json"
if IS_WINDOWS:
    from ctypes import wintypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

BG_MAIN = "#07080a"       # Deep tactical carbon matte
BG_CARD = "#11141a"       # Cyber deck plate dark gray
BG_HEADER = "#030405"     # Pure terminal dark black
TRANS_COLOR = "#010203"   # Pure transparent chroma key for Windows overlay
WIN_BG = TRANS_COLOR if IS_WINDOWS else BG_MAIN
ACCENT_CYAN = "#00f0ff"   # Tactical laser cyan
ACCENT_GREEN = "#39ff14"  # Glow radioactive neon green
TEXT_LIGHT = "#ffffff"    # High contrast display white
TEXT_MUTED = "#6c7d93"    # Muted control-room slate blue
ACCENT_RED = "#ff003c"    # Emergency SCRAM laser red
ACCENT_GOLD = "#ffaa00"   # Warning amber isotope yellow
ACCENT_YELLOW = "#ffaa00" # Warning amber yellow alias

APRMtoRecircTable = { # The numbers in the comments are values i got from the games reactor auto control
    0: 0, #0
    10: 28, #0
    20: 28, #5
    30: 28, #14
    40: 38, #35
    50: 50, #55
    60: 70, #74
    70: 85, #88
    80: 94, #95.5
    90: 97, #99
    100: 100, #100
    110: 100  #100
}

class UsageCalculator:
    def __init__(self, unit=1): # all usages are in MW/1kg or per pump(MW)
        self.unit = unit
        if unit == 1:
            self.feedwater_usage = 0.014
            self.condenser_usage = 0.007 # per kg
            self.condenser_circ_usage = 6.5
            self.recirculation_usage = 0.028
        elif unit == 2:
            self.feedwater_usage = 0.013
            self.condenser_usage = 3.1850 # per pump
            self.condenser_circ_usage = 6.5
            self.recirculation_usage = 0.01
            self.tower_makeup_usage = 0.5
        else:
            raise ValueError("Invalid unit number. Unit must be 1 or 2.")

    def aprm_to_recirc_pump_speed(self, aprm):
        for aprm_value in sorted(APRMtoRecircTable.keys()):
            if aprm_value >= aprm:
                return APRMtoRecircTable[aprm_value]
        return APRMtoRecircTable[max(APRMtoRecircTable.keys())]

    def calculate_usage(self, feedwater_flow, aprm, override_speed=None):
        feedwater_usage = self.feedwater_usage * feedwater_flow
        condenser_usage = self.condenser_usage if self.unit == 2 else self.condenser_usage * feedwater_flow
        
        speed = override_speed if override_speed is not None else self.aprm_to_recirc_pump_speed(aprm)
        recirculation_usage = self.recirculation_usage * speed * 10

        total_usage = feedwater_usage + condenser_usage + self.condenser_circ_usage * 2 + recirculation_usage
        return round(total_usage, 2)

class Calculator:
    def __init__(self, usage=61.32):
        self.usage = usage
        self.selected_unit = 1
        self.usage_calc1 = UsageCalculator(1)
        self.usage_calc2 = UsageCalculator(2)
        self.recirc_override: float|None = None

    def set_usage(self, val_str):
        try:
            val = float(val_str)
            self.usage = 0.0 if val < 0 else val
        except ValueError:
            self.usage = 61.32

    def calc_flow(self, thermal):
        if self.selected_unit == 1:
            return max(0.0, 82.8 + (13.7 * thermal) + (5.87 * 10**-3 * (thermal**2))) + 2
        else:
            return max(0.0, 160.0 + (11.6 * thermal) + (0.0249 * (thermal**2))) + 2

    def calc_gen_load(self, thermal):
        if self.selected_unit == 1:
            return max(0.0, -135 + (13 * thermal) + (5.33 * 10**-3 * (thermal**2)))
        else:
            return max(0.0, -82.3 + (10.9 * thermal) + (0.0238 * (thermal**2)))

    def calc_thermal(self, demand):
        current_usage = self.usage
        thermal = 0.0
        for _ in range(5):
            if self.selected_unit == 1:
                inner = 169 + 0.02132 * (demand + 135 + current_usage)
                if inner < 0:
                    thermal = 0.0
                else:
                    thermal = max(0.0, (-13 + math.sqrt(inner)) / 0.01066)
            else:
                inner = 118.81 + 0.0952 * (82.3 + demand + current_usage)
                if inner < 0:
                    thermal = 0.0
                else:
                    thermal = max(0.0, (-10.9 + math.sqrt(inner)) / 0.0476)
            
            # Calculate dynamic usage for this thermal power
            flow = self.calc_flow(thermal)
            u_calc = self.usage_calc1 if self.selected_unit == 1 else self.usage_calc2
            current_usage = u_calc.calculate_usage(flow, thermal, override_speed=self.recirc_override)
        
        self.usage = current_usage
        return thermal


class OverlayApp:
    def make_popup_draggable(self, popup, *widgets):
        drag_data = {"win_x": 0, "win_y": 0, "mouse_x": 0, "mouse_y": 0}

        def start_drag(event):
            try:
                drag_data["win_x"] = popup.winfo_x()
                drag_data["win_y"] = popup.winfo_y()
                drag_data["mouse_x"] = event.x_root
                drag_data["mouse_y"] = event.y_root
            except Exception:
                pass

        def do_drag(event):
            try:
                if not drag_data.get("mouse_x"):
                    return
                dx = event.x_root - drag_data["mouse_x"]
                dy = event.y_root - drag_data["mouse_y"]
                px = drag_data["win_x"] + dx
                py = drag_data["win_y"] + dy

                if IS_WINDOWS:
                    try:
                        hid = popup.winfo_id()
                        p = ctypes.windll.user32.GetParent(hid)
                        hwnd = p if p else hid
                        SWP_NOSIZE = 0x0001
                        SWP_NOZORDER = 0x0004
                        SWP_NOACTIVATE = 0x0010
                        ctypes.windll.user32.SetWindowPos(hwnd, 0, px, py, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                    except Exception:
                        popup.geometry(f"+{px}+{py}")
                else:
                    popup.geometry(f"+{px}+{py}")
            except Exception:
                pass

        for w in widgets:
            if w:
                w.bind("<Button-1>", start_drag, add="+")
                w.bind("<B1-Motion>", do_drag, add="+")

    def show_custom_message(self, title, message, is_error=False):
        if hasattr(self, 'custom_message_window') and self.custom_message_window and self.custom_message_window.winfo_exists():
            try:
                self.custom_message_window.destroy()
            except Exception:
                pass

        popup = tk.Toplevel(self.win)
        self.custom_message_window = popup
        popup.transient(self.win)
        popup.title(title)
        
        accent_color = ACCENT_RED if is_error else ACCENT_CYAN
        popup.configure(bg=BG_CARD, highlightbackground=accent_color, highlightcolor=accent_color, highlightthickness=1)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        
        w = 360
        h = 180
        if len(message) > 150:
            w = 400
            h = 240

        x = self.win.winfo_x() + (self.win.winfo_width() - w) // 2
        y = self.win.winfo_y() + (self.win.winfo_height() - h) // 2
        
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        x = max(0, min(x, screen_w - w))
        y = max(0, min(y, screen_h - h))
        
        popup.geometry(f"{w}x{h}+{x}+{y}")
        
        title_bar = tk.Frame(popup, bg=BG_HEADER, height=30)
        title_bar.pack(fill="x", side="top")
        
        prefix = " ERROR" if is_error else " INFO"
        title_lbl = tk.Label(title_bar, text=f"{prefix}: {title.upper()}", bg=BG_HEADER, fg=accent_color,
                             font=("Consolas", 9, "bold"))
        title_lbl.pack(side="left", padx=10, pady=5)
        
        self.make_popup_draggable(popup, title_bar, title_lbl)
        
        btn_close_top = tk.Label(title_bar, text="✕", bg=BG_HEADER, fg=TEXT_MUTED, width=3, font=("Segoe UI", 11, "bold"), cursor="hand2")
        btn_close_top.pack(side="right", fill="y")
        btn_close_top.bind("<Button-1>", lambda e: popup.destroy())
        btn_close_top.bind("<Enter>", lambda e: btn_close_top.config(bg=ACCENT_RED, fg=TEXT_LIGHT))
        btn_close_top.bind("<Leave>", lambda e: btn_close_top.config(bg=BG_HEADER, fg=TEXT_MUTED))
        
        content_frame = tk.Frame(popup, bg=BG_CARD, padx=20, pady=15)
        content_frame.pack(fill="both", expand=True)
        
        msg_lbl = tk.Label(content_frame, text=message, bg=BG_CARD, fg=TEXT_LIGHT, 
                           font=("Segoe UI", 9), justify="left", wraplength=w - 40)
        msg_lbl.pack(anchor="nw", fill="both", expand=True, pady=(0, 15))
        
        btn_ok = tk.Label(content_frame, text="OK", bg=BG_MAIN, fg=accent_color,
                          font=("Segoe UI", 9, "bold"), bd=1, relief="solid", padx=25, pady=4, cursor="hand2")
        btn_ok.pack(anchor="se", side="bottom")
        btn_ok.bind("<Button-1>", lambda e: popup.destroy())
        btn_ok.bind("<Enter>", lambda e: btn_ok.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        btn_ok.bind("<Leave>", lambda e: btn_ok.config(bg=BG_MAIN, fg=accent_color))
        
        def on_custom_message_destroy(event):
            if event.widget == popup:
                self.custom_message_window = None
                self.update_topmost_state()

        popup.bind("<Destroy>", on_custom_message_destroy)
        popup.deiconify()
        popup.lift(self.win)
        popup.focus_force()

    def open_server_sync_dialog(self):
        if hasattr(self, 'server_sync_window') and self.server_sync_window and self.server_sync_window.winfo_exists():
            try:
                self.server_sync_window.lift(self.win)
                self.server_sync_window.focus_force()
            except Exception:
                pass
            return

        popup = tk.Toplevel(self.win)
        self.server_sync_window = popup
        popup.transient(self.win)
        popup.title("Server Sync & DTL Calibration")

        popup.configure(bg=BG_CARD, highlightbackground=ACCENT_CYAN, highlightcolor=ACCENT_CYAN, highlightthickness=1)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)

        w = 360
        h = 240
        x = self.win.winfo_x() + (self.win.winfo_width() - w) // 2
        y = self.win.winfo_y() + (self.win.winfo_height() - h) // 2

        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        x = max(0, min(x, screen_w - w))
        y = max(0, min(y, screen_h - h))

        popup.geometry(f"{w}x{h}+{x}+{y}")

        title_bar = tk.Frame(popup, bg=BG_HEADER, height=30)
        title_bar.pack(fill="x", side="top")

        title_lbl = tk.Label(title_bar, text="LIVE SERVER SYNC", bg=BG_HEADER, fg=ACCENT_CYAN, font=("Consolas", 8, "bold"))
        title_lbl.pack(side="left", padx=10, pady=5)

        self.make_popup_draggable(popup, title_bar, title_lbl)

        btn_close_top = tk.Label(title_bar, text="✕", bg=BG_HEADER, fg=TEXT_MUTED, width=3, font=("Segoe UI", 11, "bold"), cursor="hand2")
        btn_close_top.pack(side="right", fill="y")
        btn_close_top.bind("<Button-1>", lambda e: popup.destroy())
        btn_close_top.bind("<Enter>", lambda e: btn_close_top.config(bg=ACCENT_RED, fg=TEXT_LIGHT))
        btn_close_top.bind("<Leave>", lambda e: btn_close_top.config(bg=BG_HEADER, fg=TEXT_MUTED))

        content_frame = tk.Frame(popup, bg=BG_CARD, padx=15, pady=10)
        content_frame.pack(fill="both", expand=True)

        lbl_desc = tk.Label(content_frame, text="Select or enter Job ID or Server ID (e.g. 77f6-4b2f):", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 8))
        lbl_desc.pack(anchor="w", pady=(0, 2))

        if not hasattr(self, 'var_overlay_job_id'):
            self.var_overlay_job_id = tk.StringVar(value="")

        job_frame = tk.Frame(content_frame, bg=BG_CARD)
        job_frame.pack(fill="x", pady=(0, 8))

        self.cmb_overlay_job = ttk.Combobox(job_frame, textvariable=self.var_overlay_job_id, width=22, font=("Consolas", 9))
        self.cmb_overlay_job.pack(side="left", fill="x", expand=True, padx=(0, 5))
        def _on_job_typing(event=None):
            typed = self.var_overlay_job_id.get().strip().lower()
            if hasattr(self, 'overlay_servers_data') and self.overlay_servers_data:
                all_ids = [s.get("jobId", "") for s in self.overlay_servers_data if s and s.get("jobId")]
                if typed:
                    starts = [jid for jid in all_ids if jid.lower().startswith(typed)]
                    contains = [jid for jid in all_ids if typed in jid.lower() and jid not in starts]
                    matching = starts + contains
                else:
                    matching = all_ids
                self.cmb_overlay_job['values'] = matching if matching else all_ids

            self.fetch_overlay_servers_list_async()

        self.cmb_overlay_job.bind("<KeyRelease>", _on_job_typing)
        self.cmb_overlay_job.bind("<Return>", lambda e: self.connect_overlay_server_async(is_user_initiated=True))

        if hasattr(self, 'overlay_servers_data') and self.overlay_servers_data:
            job_ids = [s.get("jobId", "") for s in self.overlay_servers_data if s and s.get("jobId")]
            self.cmb_overlay_job['values'] = job_ids

        self.fetch_overlay_servers_list_async()

        btn_sync = tk.Label(job_frame, text="Sync", bg=BG_MAIN, fg=ACCENT_GREEN, font=("Segoe UI", 9, "bold"), bd=1, relief="solid", padx=10, pady=2, cursor="hand2")
        btn_sync.pack(side="right")
        btn_sync.bind("<Button-1>", lambda e: self.connect_overlay_server_async(is_user_initiated=True))
        btn_sync.bind("<Enter>", lambda e: btn_sync.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        btn_sync.bind("<Leave>", lambda e: btn_sync.config(bg=BG_MAIN, fg=ACCENT_GREEN))

        calib_card = tk.Frame(content_frame, bg=BG_MAIN, bd=1, relief="solid", padx=10, pady=8)
        calib_card.pack(fill="x", pady=(4, 6))

        self.lbl_popup_dtl_countdown = tk.Label(calib_card, text="Demand Time Left: --s", bg=BG_MAIN, fg=ACCENT_GOLD, font=("Consolas", 9, "bold"))
        self.lbl_popup_dtl_countdown.pack(anchor="w", pady=(0, 4))

        calib_controls = tk.Frame(calib_card, bg=BG_MAIN)
        calib_controls.pack(fill="x")

        lbl_cal_title = tk.Label(calib_controls, text="Calibrate:", bg=BG_MAIN, fg=TEXT_MUTED, font=("Segoe UI", 8))
        lbl_cal_title.pack(side="left", padx=(0, 4))

        btn_m1 = tk.Label(calib_controls, text="-1s", bg=BG_CARD, fg=ACCENT_CYAN, font=("Segoe UI", 8, "bold"), bd=1, relief="solid", padx=5, pady=1, cursor="hand2")
        btn_m1.pack(side="left", padx=2)
        btn_m1.bind("<Button-1>", lambda e: self.calibrate_dtl_seconds(-1, is_delta=True))

        btn_p1 = tk.Label(calib_controls, text="+1s", bg=BG_CARD, fg=ACCENT_CYAN, font=("Segoe UI", 8, "bold"), bd=1, relief="solid", padx=5, pady=1, cursor="hand2")
        btn_p1.pack(side="left", padx=2)
        btn_p1.bind("<Button-1>", lambda e: self.calibrate_dtl_seconds(1, is_delta=True))

        self.var_calib_input = tk.StringVar(value="")
        ent_cal = tk.Entry(calib_controls, textvariable=self.var_calib_input, bg=BG_CARD, fg=TEXT_LIGHT, font=("Consolas", 9), width=5, justify="center")
        ent_cal.pack(side="left", padx=(6, 2))

        def apply_exact_calib():
            try:
                v = float(self.var_calib_input.get().strip())
                self.calibrate_dtl_seconds(v, is_delta=False)
                self.var_calib_input.set("")
            except ValueError:
                pass

        btn_set_cal = tk.Label(calib_controls, text="Set", bg=BG_CARD, fg=ACCENT_GREEN, font=("Segoe UI", 8, "bold"), bd=1, relief="solid", padx=6, pady=1, cursor="hand2")
        btn_set_cal.pack(side="left", padx=2)
        btn_set_cal.bind("<Button-1>", lambda e: apply_exact_calib())

        self.lbl_sync_status = tk.Label(content_frame, text="", bg=BG_CARD, fg=ACCENT_RED, font=("Segoe UI", 8), wraplength=320, justify="left")
        self.lbl_sync_status.pack(fill="x", pady=(2, 2))

        btn_footer = tk.Frame(content_frame, bg=BG_CARD)
        btn_footer.pack(fill="x", side="bottom")

        btn_done = tk.Label(btn_footer, text="Close", bg=BG_MAIN, fg=TEXT_MUTED, font=("Segoe UI", 9), bd=1, relief="solid", padx=15, pady=3, cursor="hand2")
        btn_done.pack(side="right")
        btn_done.bind("<Button-1>", lambda e: popup.destroy())

        def on_popup_destroy(event):
            if event.widget == popup:
                self.server_sync_window = None

        popup.bind("<Destroy>", on_popup_destroy)
        popup.deiconify()
        popup.lift(self.win)
        popup.focus_force()

    def poll_gui_queue(self):
        try:
            while True:
                fn, args, kwargs = self.gui_queue.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    log.error(f"Error in queue callback: {e}")
                self.gui_queue.task_done()
        except queue.Empty:
            pass
        self.root.after(50, self.poll_gui_queue)

    def run_on_main_thread(self, fn, *args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            fn(*args, **kwargs)
        else:
            self.gui_queue.put((fn, args, kwargs))
            
    def find_server_by_id_or_job_id(self, servers, query):
        if not query or not servers:
            return None
        query = str(query).strip()
        for s in servers:
            if not s:
                continue
            if s.get("jobId") == query or s.get("id") == query:
                return s

        q_parts = [p.strip() for p in query.split("-") if p.strip()]
        if len(q_parts) >= 2:
            for s in servers:
                if not s:
                    continue
                for candidate in [s.get("jobId"), s.get("id")]:
                    if not candidate:
                        continue
                    j_parts = [p.strip() for p in str(candidate).split("-") if p.strip()]
                    if len(j_parts) >= 3:
                        if j_parts[1].lower() == q_parts[0].lower() and j_parts[2].lower() == q_parts[1].lower():
                            return s
                        if len(q_parts) >= 3 and j_parts[1].lower() == q_parts[1].lower() and j_parts[2].lower() == q_parts[2].lower():
                            return s
        return None

    def parse_servers_from_payload(self, raw_data):
        if not raw_data:
            return []
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except Exception:
                return []
        if isinstance(raw_data, dict):
            if "servers" in raw_data and isinstance(raw_data["servers"], list):
                return raw_data["servers"]
            if "data" in raw_data:
                d = raw_data["data"]
                if isinstance(d, dict):
                    if "servers" in d and isinstance(d["servers"], list):
                        return d["servers"]
                    if "data" in d and isinstance(d["data"], dict) and "servers" in d["data"]:
                        return d["data"]["servers"]
                elif isinstance(d, list):
                    return d
        elif isinstance(raw_data, list):
            return raw_data
        return []

    def fetch_overlay_servers_list_async(self):
        now = time.time()
        last_req = getattr(self, '_last_overlay_servers_fetch', 0.0)
        if (now - last_req) < 10.0:
            return

        self._last_overlay_servers_fetch = now

        def _bg():
            import json
            servers = []

            try:
                req = urllib.request.Request(
                    f"{BACKEND_SERVER_URL}/api/servers/latest",
                    headers={"User-Agent": "RBWR-Overlay-Client/1.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8")
                        payload = json.loads(raw)
                        servers = self.parse_servers_from_payload(payload)
            except Exception as e:
                log.debug(f"Error fetching servers in overlay: {e}")

            if servers:
                job_ids = [s.get("jobId", "") for s in servers if s and s.get("jobId")]
                self.run_on_main_thread(self._update_overlay_job_combobox, job_ids, servers)

        threading.Thread(target=_bg, daemon=True).start()

    def _update_overlay_job_combobox(self, job_ids, servers):
        self.overlay_servers_data = servers
        if hasattr(self, 'cmb_overlay_job') and self.cmb_overlay_job.winfo_exists():
            typed = self.var_overlay_job_id.get().strip().lower() if hasattr(self, 'var_overlay_job_id') else ""
            if typed:
                starts = [j for j in job_ids if j.lower().startswith(typed)]
                contains = [j for j in job_ids if typed in j.lower() and j not in starts]
                matching = starts + contains
                self.cmb_overlay_job['values'] = matching if matching else job_ids
            else:
                self.cmb_overlay_job['values'] = job_ids

    def _validate_overlay_job_input(self, event=None):
        if not hasattr(self, 'cmb_overlay_job') or not self.cmb_overlay_job.winfo_exists():
            return
        typed = self.var_overlay_job_id.get().strip()
        all_servers = getattr(self, 'overlay_servers_data', [])
        job_ids = [s.get("jobId", "") for s in all_servers if s and s.get("jobId")]

        if not typed:
            self.cmb_overlay_job['values'] = job_ids
            return

        starts = [j for j in job_ids if j.lower().startswith(typed.lower())]
        contains = [j for j in job_ids if typed.lower() in j.lower() and j not in starts]
        matching = starts + contains
        self.cmb_overlay_job['values'] = matching if matching else job_ids

    def validate_server_sync(self, srv):
        if not srv:
            return ["Server not found in public list"]
        state = srv.get("state", {})
        if not state or not isinstance(state, dict):
            return ["Telemetry state payload empty"]

        u1_st = state.get("Unit1", {})
        u2_st = state.get("Unit2", {})
        if not u1_st and not u2_st:
            return ["Telemetry state payload empty"]

        missing = []

        u1 = state.get("Unit1")
        if not u1 or not isinstance(u1, dict):
            missing.append("Unit1 state")
        else:
            if u1.get("Demand Time Left") is None and u1.get("dtl") is None:
                missing.append("Unit1.Demand Time Left")
            dem1 = None
            for k in ["DemandU1", "DemandU2", "Demand", "demand"]:
                if k in u1 and u1[k] is not None:
                    dem1 = u1[k]
                    break
            if dem1 is None:
                missing.append("Unit1.Demand")

            next1 = None
            for k in ["NextDemandU1", "NextDemandU2", "Next Demand", "next_demand"]:
                if k in u1 and u1[k] is not None:
                    next1 = u1[k]
                    break
            if next1 is None:
                missing.append("Unit1.NextDemand")

        u2 = state.get("Unit2")
        if not u2 or not isinstance(u2, dict):
            missing.append("Unit2 state")
        else:
            if u2.get("Demand Time Left") is None and u2.get("dtl") is None:
                missing.append("Unit2.Demand Time Left")
            dem2 = None
            for k in ["DemandU1", "DemandU2", "Demand", "demand"]:
                if k in u2 and u2[k] is not None:
                    dem2 = u2[k]
                    break
            if dem2 is None:
                missing.append("Unit2.Demand")

            next2 = None
            for k in ["NextDemandU2", "NextDemandU1", "Next Demand", "next_demand"]:
                if k in u2 and u2[k] is not None:
                    next2 = u2[k]
                    break
            if next2 is None:
                missing.append("Unit2.NextDemand")

        return missing

    def connect_overlay_server_async(self, is_user_initiated=False):
        if is_user_initiated:
            self.overlay_sync_failed = False
            self._demand_changed_waiting_heartbeat = False
            self._last_synced_demand = None
            self._last_synced_heartbeat_timestamp = 0.0

        if getattr(self, 'overlay_sync_failed', False):
            return

        job_id = self.var_overlay_job_id.get().strip() if hasattr(self, 'var_overlay_job_id') else ""
        if not job_id:
            return

        now = time.time()
        last_req = getattr(self, '_last_api_request_timestamp', 0.0)

        if not is_user_initiated and (now - last_req) < 10.0:
            return

        self._last_api_request_timestamp = now
        self.last_job_id = job_id
        self.save_settings()

        def _bg():
            import json

            servers = []
            last_err = None

            try:
                req = urllib.request.Request(
                    f"{BACKEND_SERVER_URL}/api/servers/latest",
                    headers={"User-Agent": "RBWR-Overlay-Client/1.0"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8")
                        payload = json.loads(raw)
                        servers = self.parse_servers_from_payload(payload)
                    else:
                        last_err = f"HTTP {resp.status}"
            except urllib.error.HTTPError as e:
                last_err = f"HTTP Error {e.code}: {e.reason}"
            except Exception as e:
                last_err = str(e)
                log.warning(f"Server API (rbwr.hotment.dev) error: {e}")

            if servers:
                self.overlay_servers_data = servers
                srv = self.find_server_by_id_or_job_id(servers, job_id)
                
                missing = self.validate_server_sync(srv)
                if missing:
                    self.run_on_main_thread(self._on_overlay_server_sync_failed, job_id, missing)
                else:
                    self.run_on_main_thread(self._on_overlay_server_connected, srv, False)
            else:
                err_msg = last_err or "Failed to connect to server API"
                log.error(f"Error connecting overlay server sync: {err_msg}")
                self._handle_async_sync_error(job_id, [err_msg])

        threading.Thread(target=_bg, daemon=True).start()

    def _handle_async_sync_error(self, job_id, err_list):
        cached_servers = getattr(self, 'overlay_servers_data', [])
        srv = self.find_server_by_id_or_job_id(cached_servers, job_id) if cached_servers else getattr(self, 'active_overlay_server', None)
        if srv:
            missing = self.validate_server_sync(srv)
            if not missing:
                self.run_on_main_thread(self._on_overlay_server_connected, srv, True)
                return
        self.run_on_main_thread(self._on_overlay_server_sync_failed, job_id, err_list)

    def _on_overlay_server_sync_failed(self, job_id, missing):
        err_detail = ", ".join(missing)
        log.warning(f"Sync failed for Job ID '{job_id}'. Missing data: {err_detail}")
        self.overlay_sync_failed = True
        self.overlay_next_demand_switched = False
        self.active_overlay_server = None
        if hasattr(self, 'lbl_sync_status') and self.lbl_sync_status and self.lbl_sync_status.winfo_exists():
            self.lbl_sync_status.config(text=f"Sync Failed! Missing data:\n{err_detail}", fg=ACCENT_RED)
        if hasattr(self, 'lbl_sync_dtl') and self.lbl_sync_dtl and self.lbl_sync_dtl.winfo_exists():
            self.lbl_sync_dtl.config(text="Sync Failed", fg=ACCENT_RED)
        if hasattr(self, 'lbl_compact_sync_dtl') and self.lbl_compact_sync_dtl and self.lbl_compact_sync_dtl.winfo_exists():
            self.lbl_compact_sync_dtl.config(text="Err", fg=ACCENT_RED)

    def calibrate_dtl_seconds(self, value, is_delta=True):
        if not hasattr(self, 'active_overlay_server') or not self.active_overlay_server:
            return
        now = time.time()
        elapsed = now - getattr(self, 'overlay_heartbeat_timestamp', now)
        current_offset = getattr(self, 'dtl_calibration_offset', 0.0)

        if is_delta:
            self.dtl_calibration_offset = current_offset + value
        else:
            self.dtl_calibration_offset = value - getattr(self, 'overlay_initial_dtl', 0.0) + elapsed

        self.save_settings()
        self._tick_overlay_dtl_countdown()

    def _on_overlay_server_connected(self, srv, is_cached=False):
        self.active_overlay_server = srv
        self.overlay_sync_failed = False
        
        hb_str = srv.get("lastHeartbeat")
        now = time.time()
        hb_age = 0
        if hb_str:
            try:
                clean_hb = hb_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_hb)
                self.overlay_heartbeat_timestamp = dt.timestamp()
                hb_age = now - self.overlay_heartbeat_timestamp
            except Exception as e:
                log.error(f"Error parsing lastHeartbeat: {e}")

        if hasattr(self, 'lbl_sync_status') and self.lbl_sync_status and self.lbl_sync_status.winfo_exists():
            if is_cached:
                self.lbl_sync_status.config(text="Warning: Server Unreachable (Using Cached Data)", fg=ACCENT_YELLOW)
            elif hb_age > 120:
                self.lbl_sync_status.config(text="Warning: Outdated Data (Heartbeat > 2m ago)", fg=ACCENT_YELLOW)
            else:
                self.lbl_sync_status.config(text="Server Synced Successfully", fg=ACCENT_GREEN)

        st = srv.get("state", {})
        u1_st = st.get("Unit1", {})
        u2_st = st.get("Unit2", {})

        t_health = None
        for key in ["TurbineHealth", "Turbine Health", "turbine_health", "Turbine_Health"]:
            if key in u2_st and u2_st[key] is not None:
                try:
                    t_health = float(u2_st[key])
                    break
                except (ValueError, TypeError):
                    pass
            elif key in u1_st and u1_st[key] is not None:
                try:
                    t_health = float(u1_st[key])
                    break
                except (ValueError, TypeError):
                    pass

        if t_health is not None:
            t_thresh = getattr(self, 'turbine_health_threshold', 65.0)
            if t_health > t_thresh:
                self._turbine_health_alert_triggered = False
            elif t_health <= t_thresh and getattr(self, 'enable_turbine_health_alert', False):
                if not getattr(self, '_turbine_health_alert_triggered', False):
                    self._turbine_health_alert_triggered = True
                    self.trigger_turbine_health_reminder(t_health, t_thresh)

        dtl_val = u1_st.get("Demand Time Left") or u2_st.get("Demand Time Left") or 0
        try:
            self.overlay_initial_dtl = float(dtl_val)
        except (ValueError, TypeError):
            self.overlay_initial_dtl = 0.0

        if hasattr(self, '_overlay_dtl_timer') and self._overlay_dtl_timer:
            try:
                self.root.after_cancel(self._overlay_dtl_timer)
            except Exception:
                pass

        now = time.time()
        elapsed = now - self.overlay_heartbeat_timestamp
        live_dtl = max(0.0, self.overlay_initial_dtl - elapsed)
        if live_dtl > 0.0:
            self.overlay_0s_refetch_done = False
            
        thresh = getattr(self, 'next_demand_threshold_seconds', 60)

        u_st = u1_st if self.calc.selected_unit == 1 else u2_st
        cur_dem = None
        for key in ["DemandU1", "DemandU2", "Demand", "demand"]:
            if key in u_st and u_st[key] is not None:
                try:
                    cur_dem = float(u_st[key])
                    break
                except (ValueError, TypeError):
                    pass

        next_dem = None
        for key in ["NextDemandU1", "NextDemandU2", "Next Demand", "next_demand"]:
            if key in u_st and u_st[key] is not None:
                try:
                    next_dem = float(u_st[key])
                    break
                except (ValueError, TypeError):
                    pass

        if getattr(self, 'overlay_next_demand_switched', False):
            if next_dem is not None and next_dem != getattr(self, '_last_switched_next_demand', None):
                self.overlay_next_demand_switched = False
                log.info(f"New upcoming demand detected ({next_dem} MWe) — updating Next Demand display.")
            elif live_dtl > thresh:
                self.overlay_next_demand_switched = False

        last_hb_ts = getattr(self, '_last_synced_heartbeat_timestamp', 0.0)
        last_synced_dem = getattr(self, '_last_synced_demand', None)
        pending_dem = getattr(self, '_pending_demand_value', None)
        is_waiting = getattr(self, '_demand_changed_waiting_heartbeat', False)

        is_new_heartbeat = (hb_age < 120 and self.overlay_heartbeat_timestamp > (last_hb_ts + 0.001))
        has_new_demand = False
        if cur_dem is not None:
            if last_synced_dem is None:
                has_new_demand = True
            elif cur_dem != last_synced_dem:
                has_new_demand = True
            elif pending_dem is not None and abs(cur_dem - pending_dem) < 1.0:
                has_new_demand = True
            elif live_dtl > thresh and is_new_heartbeat:
                has_new_demand = True

        if is_waiting:
            if is_new_heartbeat and has_new_demand:
                self._demand_changed_waiting_heartbeat = False
                self.overlay_next_demand_switched = False
                self._last_synced_heartbeat_timestamp = self.overlay_heartbeat_timestamp
                self._last_synced_demand = cur_dem
                if cur_dem is not None:
                    calc_val = 0.0 if cur_dem < 0 else max(0.0, cur_dem)
                    self.var_demand.set(str(int(calc_val)))
                    self.update_calculations(source="demand")
            else:
                pass
        else:
            if live_dtl >= thresh:
                if cur_dem is not None:
                    calc_val = 0.0 if cur_dem < 0 else max(0.0, cur_dem)
                    self._last_synced_heartbeat_timestamp = self.overlay_heartbeat_timestamp
                    self._last_synced_demand = cur_dem
                    self.var_demand.set(str(int(calc_val)))
                    self.update_calculations(source="demand")
            else:
                if not getattr(self, 'overlay_next_demand_switched', False):
                    self.overlay_next_demand_switched = True
                    self._demand_changed_waiting_heartbeat = True
                    if next_dem is not None:
                        calc_val = 0.0 if next_dem < 0 else max(0.0, next_dem)
                        self._last_switched_next_demand = next_dem
                        self._pending_demand_value = calc_val
                        self.var_demand.set(str(int(calc_val)))
                        self.update_calculations(source="demand")

        self._tick_overlay_dtl_countdown()

    def _tick_overlay_dtl_countdown(self):
        if not hasattr(self, 'active_overlay_server') or not self.active_overlay_server:
            return

        now = time.time()
        elapsed = now - getattr(self, 'overlay_heartbeat_timestamp', now)
        offset = getattr(self, 'dtl_calibration_offset', 0.0)
        live_dtl = max(0.0, getattr(self, 'overlay_initial_dtl', 0.0) - elapsed + offset)

        st = self.active_overlay_server.get("state", {})
        u_st = st.get("Unit1", {}) if self.calc.selected_unit == 1 else st.get("Unit2", {})

        next_dem = None
        if not getattr(self, 'overlay_next_demand_switched', False):
            for key in ["NextDemandU1", "NextDemandU2", "Next Demand", "next_demand"]:
                if key in u_st and u_st[key] is not None:
                    try:
                        next_dem = float(u_st[key])
                        break
                    except (ValueError, TypeError):
                        pass

        if hasattr(self, 'lbl_popup_dtl_countdown'):
            try:
                if self.lbl_popup_dtl_countdown.winfo_exists():
                    self.lbl_popup_dtl_countdown.config(text=f"Demand Time Left: {int(live_dtl)}s")
            except Exception:
                pass

        def format_overlay_demand_label(dem_val, compact=False):
            if dem_val is None:
                return "---" if compact else "--- MWe"
            try:
                val = float(dem_val)
                if val == -4:
                    return "Evac"
                if val == -3:
                    return "RST"
                if val == -2:
                    return "LOOP"
                if val == -1:
                    return "Maint"
                return f"{int(val)}" if compact else f"{int(val)} MWe"
            except (ValueError, TypeError):
                return str(dem_val)

        next_txt_detailed = f"Next: {format_overlay_demand_label(next_dem)}"
        next_txt_compact = format_overlay_demand_label(next_dem, compact=True)

        if hasattr(self, 'lbl_sync_dtl'):
            try:
                if self.lbl_sync_dtl.winfo_exists():
                    self.lbl_sync_dtl.config(text=next_txt_detailed)
            except Exception:
                pass

        if hasattr(self, 'lbl_compact_sync_dtl'):
            try:
                if self.lbl_compact_sync_dtl.winfo_exists():
                    self.lbl_compact_sync_dtl.config(text=next_txt_compact)
            except Exception:
                pass

        if getattr(self, 'overlay_sync_failed', False):
            self._overlay_dtl_timer = self.root.after(1000, self._tick_overlay_dtl_countdown)
            return

        thresh = getattr(self, 'next_demand_threshold_seconds', 60)
        if live_dtl <= thresh and not getattr(self, 'overlay_next_demand_switched', False):
            self.overlay_next_demand_switched = True
            self._demand_changed_waiting_heartbeat = True
            if next_dem is not None:
                calc_val = 0.0 if next_dem < 0 else max(0.0, next_dem)
                self._last_switched_next_demand = next_dem
                self._pending_demand_value = calc_val
                self.var_demand.set(str(int(calc_val)))
                self.update_calculations(source="demand")
            self.connect_overlay_server_async()

        if live_dtl <= 0.0 and not getattr(self, 'overlay_0s_refetch_done', False):
            self.overlay_0s_refetch_done = True
            self._demand_changed_waiting_heartbeat = True
            self.connect_overlay_server_async()

        if getattr(self, 'overlay_next_demand_switched', False):
            last_poll = getattr(self, '_last_60s_poll_timestamp', 0.0)
            if now - last_poll >= 10.0:
                self._last_60s_poll_timestamp = now
                self.connect_overlay_server_async()

        self._overlay_dtl_timer = self.root.after(1000, self._tick_overlay_dtl_countdown)

    def _sync_topmost_on_roblox(self):
        self.topmost_on_roblox = self.var_topmost_on_roblox.get()

    def __init__(self, root: tk.Tk):
        self.root = root
        self.gui_queue = queue.Queue()
        self.poll_gui_queue()
        self.root.title(f"RBWR APRM Calculator v{__version__}")
        
        settings = self.load_settings()
        
        self.calc = Calculator(usage=settings["usage"])
        self.calc.selected_unit = settings["selected_unit"]
        self.is_topmost = settings["is_topmost"]
        self.is_compact = settings["is_compact"]
        self.show_config = False
        self.updating_fields = False
        self._last_api_request_timestamp: float = 0.0
        self._last_60s_poll_timestamp: float = 0.0
        self._turbine_health_alert_triggered: bool = False
        self._last_synced_heartbeat_timestamp: float = 0.0
        self._last_synced_demand: float | None = None
        self._demand_changed_waiting_heartbeat: bool = False
        self._pending_demand_value: float | None = None
        
        if IS_LINUX:
            self.win = tk.Toplevel(self.root)
            self.win.title(f"RBWR APRM Calculator v{__version__}")
            self.win.overrideredirect(True)
            self.bg_win = None
            self.win.attributes("-topmost", self.is_topmost)
            self.win.attributes("-alpha", settings["opacity"])
            self.win.configure(bg=BG_MAIN, highlightbackground=ACCENT_CYAN, highlightcolor=ACCENT_CYAN, highlightthickness=1)
        elif IS_MAC:
            self.win = self.root
            self.win.title(f"RBWR APRM Calculator v{__version__}")
            self.win.overrideredirect(True)
            self.bg_win = None
            self.win.attributes("-topmost", self.is_topmost)
            self.win.attributes("-alpha", settings["opacity"])
            self.win.configure(bg=BG_MAIN, highlightbackground=ACCENT_CYAN, highlightcolor=ACCENT_CYAN, highlightthickness=1)
        else:
            self.root.withdraw()
            self.bg_win = tk.Toplevel(self.root)
            self.bg_win.title("RBWR Overlay Backdrop")
            self.bg_win.overrideredirect(True)
            self.bg_win.attributes("-topmost", self.is_topmost)
            self.bg_win.attributes("-alpha", settings["opacity"])
            self.bg_win.configure(bg=BG_MAIN, highlightbackground=ACCENT_CYAN, highlightcolor=ACCENT_CYAN, highlightthickness=1)
            self.make_draggable(self.bg_win)
            
            self.win = tk.Toplevel(self.root)
            self.win.title(f"RBWR APRM Calculator v{__version__}")
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", self.is_topmost)
            self.win.attributes("-transparentcolor", WIN_BG)
            self.win.attributes("-alpha", 1.0)
            self.win.configure(bg=WIN_BG, highlightbackground=ACCENT_CYAN, highlightcolor=ACCENT_CYAN, highlightthickness=1)
            self.win.lift(self.bg_win)
        
        self.root.option_add('*TCombobox*Listbox.background', BG_CARD)
        self.root.option_add('*TCombobox*Listbox.foreground', TEXT_LIGHT)
        self.root.option_add('*TCombobox*Listbox.selectBackground', '#2563eb')
        self.root.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
        self.root.option_add('*TCombobox*Listbox.font', ("Consolas", 9))
        self.root.option_add('*TCombobox*Listbox.borderWidth', 1)
        self.root.option_add('*TCombobox*Listbox.relief', 'solid')

        self.root.option_add('*Entry.selectBackground', '#2563eb')
        self.root.option_add('*Entry.selectForeground', '#ffffff')
        self.root.option_add('*Entry.insertBackground', '#ffffff')
        self.root.option_add('*Text.selectBackground', '#2563eb')
        self.root.option_add('*Text.selectForeground', '#ffffff')
        self.root.option_add('*Text.insertBackground', '#ffffff')

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TCombobox",
                             fieldbackground=BG_MAIN,
                             background=BG_CARD,
                             foreground=TEXT_LIGHT,
                             darkcolor=BG_CARD,
                             lightcolor=BG_CARD,
                             selectbackground='#2563eb',
                             selectforeground='#ffffff',
                             insertcolor='#ffffff',
                             arrowcolor=ACCENT_CYAN)
        self.style.map("TCombobox",
                       fieldbackground=[('readonly', BG_MAIN), ('focus', BG_MAIN), ('active', BG_MAIN)],
                       foreground=[('readonly', TEXT_LIGHT), ('focus', TEXT_LIGHT), ('active', TEXT_LIGHT)],
                       selectbackground=[('readonly', '#2563eb'), ('focus', '#2563eb'), ('active', '#2563eb')],
                       selectforeground=[('readonly', '#ffffff'), ('focus', '#ffffff'), ('active', '#ffffff')],
                       insertcolor=[('focus', '#ffffff'), ('active', '#ffffff')])

        self.style.configure("Horizontal.TScale",
                             troughcolor=BG_MAIN,
                             background=ACCENT_CYAN,
                             bordercolor=BG_CARD,
                             lightcolor=ACCENT_CYAN,
                             darkcolor=ACCENT_CYAN,
                             sliderthickness=14,
                             sliderlength=24)
        
        self.width_detailed = 420
        self.height_detailed = 350
        self.width_compact = 435
        self.height_compact = 60
        self.settings_window = None
        self.suggestions_window = None
        self.update_window = None
        self.loading_window = None
        self.custom_message_window = None
        
        self._drag_data = {"x": 0, "y": 0}
        
        self.var_demand = tk.StringVar(value="0")
        self.var_rtp = tk.StringVar(value="0")
        self.var_usage = tk.StringVar(value=f"{self.calc.usage:.2f}")
        self.var_demand.trace_add("write", lambda name, index, mode: self.on_input_update("demand"))
        self.var_rtp.trace_add("write", lambda name, index, mode: self.on_input_update("rtp"))
        self.topmost_on_roblox = settings.get("topmost_on_roblox", True)
        self.var_topmost_on_roblox = tk.BooleanVar(value=self.topmost_on_roblox)
        self.var_topmost_on_roblox.trace_add("write", lambda *args: self._sync_topmost_on_roblox())
        self.var_compact_menu = tk.BooleanVar(value=self.is_compact)
        self.var_topmost_menu = tk.BooleanVar(value=self.is_topmost)
        self.skipped_version = settings.get("skipped_version", "")
        self.next_demand_threshold_seconds = settings.get("next_demand_threshold_seconds", 60)
        self.var_demand_threshold = tk.StringVar(value=str(self.next_demand_threshold_seconds))
        self.var_demand_threshold.trace_add("write", lambda *args: self.on_demand_threshold_change())
        self.last_job_id = settings.get("last_job_id", "")
        self.var_overlay_job_id = tk.StringVar(value=self.last_job_id)
        self.var_overlay_job_id.trace_add("write", lambda *args: self.save_settings())
        self.dtl_calibration_offset = float(settings.get("dtl_calibration_offset", 0.0))
        self.var_recirc_override = tk.StringVar(value="")
        self.var_recirc_override.trace_add("write", lambda *args: self.on_recirc_override_change())
        self.enable_turbine_health_alert = settings.get("enable_turbine_health_alert", False)
        self.turbine_health_threshold = float(settings.get("turbine_health_threshold", 65.0))
        self.var_turbine_health_alert = tk.BooleanVar(value=self.enable_turbine_health_alert)
        self.is_roblox_active: bool = False
        self._last_logged_foreground_hwnd = None
        self._last_logged_roblox_state = None
        self.var_turbine_health_threshold = tk.StringVar(value=str(int(self.turbine_health_threshold)))
        self.var_turbine_health_threshold.trace_add("write", lambda *args: self.on_turbine_health_threshold_change())

        # Icon and Tray Setup (Loads existing icon if present, otherwise uses in-memory generated icon)
        self.icon_image_pil = get_default_icon_image()
        
        if IS_WINDOWS and os.path.exists("icon.ico"):
            try:
                self.root.iconbitmap("icon.ico")
            except Exception:
                log.warning("Failed to load custom icon from icon.ico")
        else:
            try:
                self.tk_icon = ImageTk.PhotoImage(self.icon_image_pil)
                self.root.iconphoto(False, self.tk_icon)  # pyright: ignore[reportArgumentType]
            except Exception as e:
                log.warning(f"Failed to set fallback icon: {e}")
                
        self.setup_tray_icon()
        
        self.context_menu = tk.Menu(self.win, tearoff=0, bg=BG_CARD, fg=TEXT_LIGHT, 
                                    activebackground=BG_HEADER, activeforeground=ACCENT_CYAN, 
                                    bd=1, relief="solid", font=("Segoe UI", 9))
        self.context_menu.add_checkbutton(label="Compact Mode", variable=self.var_compact_menu, command=self.toggle_compact)
        self.context_menu.add_checkbutton(label="Always on Top", variable=self.var_topmost_menu, command=self.toggle_topmost)
        self.context_menu.add_checkbutton(label="Topmost on Roblox", variable=self.var_topmost_on_roblox, command=self.save_settings)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Exit Application", command=self.quit_app)
        
        self.win.bind("<Button-3>", self.show_context_menu)
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            self.bg_win.bind("<Button-3>", self.show_context_menu)
        
        if self.is_compact:
            self.center_window(self.width_compact, self.height_compact)
        else:
            self.center_window(self.width_detailed, self.height_detailed)
        self.create_widgets()
        self.update_calculations(source="demand")

        if self.last_job_id:
            self.root.after(500, self.connect_overlay_server_async)
        
        self.check_for_updates()
        
        self.root.after(10, self.setup_app_window_style)
        self.root.after(100, self.check_focus_loop)

    def center_window(self, w, h):
        screen_width = self.win.winfo_screenwidth()
        screen_height = self.win.winfo_screenheight()

        x = (screen_width - w) // 2
        y = (screen_height - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            self.bg_win.geometry(f"{w}x{h}+{x}+{y}")
        self.start_x = x
        self.start_y = y

    def show_context_menu(self, event):
        try:
            self.win.attributes("-topmost", False)
            if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
                self.bg_win.attributes("-topmost", False)
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
            self.win.attributes("-topmost", self.is_topmost)
            if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
                self.bg_win.attributes("-topmost", self.is_topmost)
            self.ensure_z_order()

    def ensure_z_order(self):
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            try:
                if IS_WINDOWS:
                    def get_hwnd(w):
                        hid = w.winfo_id()
                        p = ctypes.windll.user32.GetParent(hid)
                        return p if p else hid
                    hwnd_bg = get_hwnd(self.bg_win)
                    hwnd_fg = get_hwnd(self.win)
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    SWP_NOACTIVATE = 0x0010
                    ctypes.windll.user32.SetWindowPos(hwnd_bg, hwnd_fg, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
                self.win.lift(self.bg_win)
            except Exception:
                pass

    def sync_bg_window(self, width=None, height=None):
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            try:
                w = width or (self.width_compact if self.is_compact else self.width_detailed)
                h = height or (self.height_compact if self.is_compact else self.height_detailed)
                x = self.win.winfo_x()
                y = self.win.winfo_y()
                self.bg_win.geometry(f"{w}x{h}+{x}+{y}")
                self.win.geometry(f"{w}x{h}+{x}+{y}")
                self.win.update_idletasks()
                self.bg_win.update_idletasks()
                if IS_WINDOWS:
                    try:
                        def get_hwnd(widget):
                            hid = widget.winfo_id()
                            p = ctypes.windll.user32.GetParent(hid)
                            return p if p else hid
                        hwnd_bg = get_hwnd(self.bg_win)
                        hwnd_fg = get_hwnd(self.win)
                        SWP_NOZORDER = 0x0004
                        SWP_NOACTIVATE = 0x0010
                        SWP_FRAMECHANGED = 0x0020
                        hdwp = ctypes.windll.user32.BeginDeferWindowPos(2)
                        hdwp = ctypes.windll.user32.DeferWindowPos(hdwp, hwnd_bg, 0, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
                        hdwp = ctypes.windll.user32.DeferWindowPos(hdwp, hwnd_fg, 0, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
                        ctypes.windll.user32.EndDeferWindowPos(hdwp)

                        flags = 0x0001 | 0x0100 | 0x0080 | 0x0400  # RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN | RDW_FRAME
                        ctypes.windll.user32.RedrawWindow(hwnd_bg, 0, 0, flags)
                        ctypes.windll.user32.RedrawWindow(hwnd_fg, 0, 0, flags)
                    except Exception:
                        pass
                self.ensure_z_order()
            except Exception:
                pass

    def setup_app_window_style(self):
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            self.bg_win.deiconify()
        self.win.deiconify()
        try:
            if IS_WINDOWS:
                GWL_EXSTYLE = -20
                WS_EX_APPWINDOW = 0x00040000
                WS_EX_TOOLWINDOW = 0x00000080
                WS_EX_NOACTIVATE = 0x08000000
                hwnd_to_use = self.win.winfo_id()
                parent = ctypes.windll.user32.GetParent(hwnd_to_use)
                hwnd = parent if parent else hwnd_to_use
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                style = style & ~WS_EX_TOOLWINDOW
                style = style | WS_EX_APPWINDOW
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

                if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
                    bg_hwnd_to_use = self.bg_win.winfo_id()
                    bg_parent = ctypes.windll.user32.GetParent(bg_hwnd_to_use)
                    bg_hwnd = bg_parent if bg_parent else bg_hwnd_to_use
                    bg_style = ctypes.windll.user32.GetWindowLongW(bg_hwnd, GWL_EXSTYLE)
                    bg_style = (bg_style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
                    ctypes.windll.user32.SetWindowLongW(bg_hwnd, GWL_EXSTYLE, bg_style)

                    GWLP_HWNDPARENT = -8
                    ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, bg_hwnd)
            elif IS_LINUX:
                try:
                    self.win.attributes('-type', 'utility')
                except Exception as le:
                    log.warning(f"Linux window attribute note: {le}")
            elif IS_MAC:
                pass
        except Exception as e:
            log.warning(f"Failed to set window style: {e}")
            
        w = self.width_compact if self.is_compact else self.width_detailed
        h = self.height_compact if self.is_compact else self.height_detailed
        x = getattr(self, 'start_x', 0)
        y = getattr(self, 'start_y', 0)
        
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.sync_bg_window(w, h)
        self.ensure_z_order()
        self.win.focus_force()

    def create_widgets(self):
        self.telemetry_frame = None
        for child in self.win.winfo_children():
            if child != getattr(self, 'context_menu', None):
                child.destroy()
            
        if self.is_compact:
            self.build_compact_layout()
        else:
            self.build_detailed_layout()
        self.update_recirc_indicator_ui()

    def make_draggable(self, widget):
        widget.bind("<Button-1>", self.start_drag)
        widget.bind("<B1-Motion>", self.do_drag)

    def start_drag(self, event):
        self._drag_data["win_start_x"] = self.win.winfo_x()
        self._drag_data["win_start_y"] = self.win.winfo_y()
        self._drag_data["mouse_start_x"] = event.x_root
        self._drag_data["mouse_start_y"] = event.y_root

    def do_drag(self, event):
        if "win_start_x" not in self._drag_data or "mouse_start_x" not in self._drag_data:
            return
        dx = event.x_root - self._drag_data["mouse_start_x"]
        dy = event.y_root - self._drag_data["mouse_start_y"]
        x = self._drag_data["win_start_x"] + dx
        y = self._drag_data["win_start_y"] + dy

        if IS_WINDOWS and hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            try:
                def get_hwnd(w):
                    hid = w.winfo_id()
                    p = ctypes.windll.user32.GetParent(hid)
                    return p if p else hid

                hwnd_bg = get_hwnd(self.bg_win)
                hwnd_fg = get_hwnd(self.win)
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                SWP_NOACTIVATE = 0x0010

                hdwp = ctypes.windll.user32.BeginDeferWindowPos(2)
                hdwp = ctypes.windll.user32.DeferWindowPos(hdwp, hwnd_bg, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                hdwp = ctypes.windll.user32.DeferWindowPos(hdwp, hwnd_fg, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                ctypes.windll.user32.EndDeferWindowPos(hdwp)
            except Exception:
                self.win.geometry(f"+{x}+{y}")
                self.bg_win.geometry(f"+{x}+{y}")
        else:
            self.win.geometry(f"+{x}+{y}")
            if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
                self.bg_win.geometry(f"+{x}+{y}")

    def toggle_topmost(self):
        self.is_topmost = not self.is_topmost
        self.win.attributes("-topmost", self.is_topmost)
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            self.bg_win.attributes("-topmost", self.is_topmost)
        self.ensure_z_order()
        symbol = "📌" if self.is_topmost else "📍"
        if hasattr(self, 'btn_topmost') and self.btn_topmost and self.btn_topmost.winfo_exists():
            self.btn_topmost.config(text=symbol)
        self.var_topmost_menu.set(self.is_topmost)
        self.save_settings()
        if hasattr(self, 'tray') and self.tray:
            try:
                self.tray.update_menu()
            except Exception:
                pass

    def toggle_compact(self):
        self.is_compact = not self.is_compact
        self.var_compact_menu.set(self.is_compact)
        self.save_settings()
        if hasattr(self, 'tray') and self.tray:
            try:
                self.tray.update_menu()
            except Exception:
                pass
        w = self.width_compact if self.is_compact else self.width_detailed
        h = self.height_compact if self.is_compact else self.height_detailed
        x = self.win.winfo_x()
        y = self.win.winfo_y()

        self.win.geometry(f"{w}x{h}+{x}+{y}")
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            self.bg_win.geometry(f"{w}x{h}+{x}+{y}")

        self.create_widgets()
        self.update_calculations(source="demand")

        self.win.update_idletasks()
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            self.bg_win.update_idletasks()

        if IS_WINDOWS and hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            try:
                def get_hwnd(widget):
                    hid = widget.winfo_id()
                    p = ctypes.windll.user32.GetParent(hid)
                    return p if p else hid

                hwnd_bg = get_hwnd(self.bg_win)
                hwnd_fg = get_hwnd(self.win)
                SWP_NOZORDER = 0x0004
                SWP_NOACTIVATE = 0x0010
                SWP_FRAMECHANGED = 0x0020

                hdwp = ctypes.windll.user32.BeginDeferWindowPos(2)
                hdwp = ctypes.windll.user32.DeferWindowPos(hdwp, hwnd_bg, 0, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
                hdwp = ctypes.windll.user32.DeferWindowPos(hdwp, hwnd_fg, 0, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
                ctypes.windll.user32.EndDeferWindowPos(hdwp)

                flags = 0x0001 | 0x0100 | 0x0080 | 0x0400  # RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN | RDW_FRAME
                ctypes.windll.user32.RedrawWindow(hwnd_bg, 0, 0, flags)
                ctypes.windll.user32.RedrawWindow(hwnd_fg, 0, 0, flags)
            except Exception:
                pass

    def build_detailed_layout(self):
        title_bar = tk.Frame(self.win, bg=WIN_BG, height=36)
        title_bar.pack(fill="x", side="top", padx=6, pady=(6, 4))
        title_bar.pack_propagate(False)
        self.make_draggable(title_bar)

        title_lbl = tk.Label(title_bar, text=f" APRM Calculator v{__version__}", bg=WIN_BG, fg=ACCENT_CYAN,
                             font=("Consolas", 9, "bold"))
        title_lbl.pack(side="left", padx=(2, 5), pady=(2, 4))
        self.make_draggable(title_lbl)

        btn_close = tk.Label(title_bar, text="✕", bg=BG_CARD, fg=TEXT_MUTED, width=3, font=("Segoe UI", 9, "bold"),
                             cursor="hand2", bd=1, relief="solid", pady=3)
        btn_close.pack(side="right", padx=(2, 0), pady=(2, 4))
        btn_close.bind("<Button-1>", lambda e: self.quit_app())
        btn_close.bind("<Enter>", lambda e: btn_close.config(bg=ACCENT_RED, fg=TEXT_LIGHT))
        btn_close.bind("<Leave>", lambda e: btn_close.config(bg=BG_CARD, fg=TEXT_MUTED))

        btn_settings = tk.Label(title_bar, text="⚙", bg=BG_CARD, fg=TEXT_MUTED, width=3, font=("Segoe UI", 9),
                                cursor="hand2", bd=1, relief="solid", pady=3)
        btn_settings.pack(side="right", padx=2, pady=(2, 4))
        btn_settings.bind("<Button-1>", lambda e: self.open_settings_dialog())
        btn_settings.bind("<Enter>", lambda e: btn_settings.config(bg="#1f2937", fg=ACCENT_CYAN))
        btn_settings.bind("<Leave>", lambda e: btn_settings.config(bg=BG_CARD, fg=TEXT_MUTED))

        btn_server_sync = tk.Label(title_bar, text="🌐", bg=BG_CARD, fg=TEXT_MUTED, width=3, font=("Segoe UI", 10),
                                   cursor="hand2", bd=1, relief="solid", pady=2)
        btn_server_sync.pack(side="right", padx=2, pady=(2, 4))
        btn_server_sync.bind("<Button-1>", lambda e: self.open_server_sync_dialog())
        btn_server_sync.bind("<Enter>", lambda e: btn_server_sync.config(bg="#1f2937", fg=ACCENT_CYAN))
        btn_server_sync.bind("<Leave>", lambda e: btn_server_sync.config(bg=BG_CARD, fg=TEXT_MUTED))

        btn_comp = tk.Label(title_bar, text="⛶", bg=BG_CARD, fg=TEXT_MUTED, width=3, font=("Segoe UI", 9),
                            cursor="hand2", bd=1, relief="solid", pady=3)
        btn_comp.pack(side="right", padx=2, pady=(2, 4))
        btn_comp.bind("<Button-1>", lambda e: self.toggle_compact())
        btn_comp.bind("<Enter>", lambda e: btn_comp.config(bg="#1f2937", fg=ACCENT_CYAN))
        btn_comp.bind("<Leave>", lambda e: btn_comp.config(bg=BG_CARD, fg=TEXT_MUTED))

        symbol = "📌" if self.is_topmost else "📍"
        self.btn_topmost = tk.Label(title_bar, text=symbol, bg=BG_CARD, fg=TEXT_MUTED, width=3, font=("Segoe UI", 10),
                                    cursor="hand2", bd=1, relief="solid", pady=2)
        self.btn_topmost.pack(side="right", padx=2, pady=(2, 4))
        self.btn_topmost.bind("<Button-1>", lambda e: self.toggle_topmost())
        self.btn_topmost.bind("<Enter>", lambda e: self.btn_topmost.config(bg="#1f2937", fg=ACCENT_CYAN))
        self.btn_topmost.bind("<Leave>", lambda e: self.btn_topmost.config(bg=BG_CARD, fg=TEXT_MUTED))

        self.lbl_recirc_indicator = tk.Label(title_bar, text="", bg=BG_CARD, fg=ACCENT_GOLD,
                                             font=("Segoe UI", 8, "bold"), cursor="hand2", bd=1, relief="solid", padx=4, pady=3)
        self.lbl_recirc_indicator.bind("<Button-1>", lambda e: self.reset_recirc_override())

        container = tk.Frame(self.win, bg=WIN_BG, padx=12, pady=10)
        container.pack(fill="both", expand=True)
        self.make_draggable(container)

        unit_frame = tk.Frame(container, bg=WIN_BG)
        unit_frame.pack(fill="x", pady=(0, 8))
        self.make_draggable(unit_frame)

        self.btn_u1 = tk.Label(unit_frame, text="UNIT 1", bg=BG_CARD, fg=ACCENT_CYAN, font=("Segoe UI", 9, "bold"),
                               pady=5, width=13, bd=1, relief="solid", cursor="hand2")
        self.btn_u1.pack(side="left", fill="x", padx=(0, 4))
        self.btn_u1.bind("<Button-1>", lambda e: self.select_unit(1))
        self.btn_u1.bind("<Enter>", lambda e: self.btn_u1.config(bg="#1f2937", fg=TEXT_LIGHT) if self.calc.selected_unit != 1 else None)
        self.btn_u1.bind("<Leave>", lambda e: self.update_unit_ui_state())

        self.btn_u2 = tk.Label(unit_frame, text="UNIT 2", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold"),
                               pady=5, width=13, bd=1, relief="solid", cursor="hand2")
        self.btn_u2.pack(side="left", fill="x", padx=(4, 4))
        self.btn_u2.bind("<Button-1>", lambda e: self.select_unit(2))
        self.btn_u2.bind("<Enter>", lambda e: self.btn_u2.config(bg="#1f2937", fg=TEXT_LIGHT) if self.calc.selected_unit != 2 else None)
        self.btn_u2.bind("<Leave>", lambda e: self.update_unit_ui_state())

        self.lbl_sync_dtl = tk.Label(unit_frame, text="Next: -- MWe", bg=BG_CARD, fg=ACCENT_GOLD, font=("Segoe UI", 8, "bold"),
                                     cursor="hand2", bd=1, relief="solid", padx=6, pady=5)
        self.lbl_sync_dtl.pack(side="right", padx=(4, 0))
        self.lbl_sync_dtl.bind("<Button-1>", lambda e: self.open_server_sync_dialog())
        self.lbl_sync_dtl.bind("<Enter>", lambda e: self.lbl_sync_dtl.config(bg="#1f2937", fg=ACCENT_CYAN))
        self.lbl_sync_dtl.bind("<Leave>", lambda e: self.lbl_sync_dtl.config(bg=BG_CARD, fg=ACCENT_GOLD))

        self.update_unit_ui_state()

        input_card = tk.Frame(container, bg=WIN_BG, bd=0)
        input_card.pack(fill="both", expand=True, pady=(2, 2))
        self.make_draggable(input_card)

        input_card.grid_columnconfigure(0, weight=1)
        input_card.grid_columnconfigure(1, weight=1)

        lbl_in_header = tk.Label(input_card, text="INPUTS", bg=WIN_BG, fg=ACCENT_GREEN, font=("Consolas", 8, "bold"))
        lbl_in_header.grid(row=0, column=0, pady=(4, 4), sticky="w", padx=10)
        self.make_draggable(lbl_in_header)

        lbl_demand = tk.Label(input_card, text="DEMAND LOAD (MWt)", bg=WIN_BG, fg=TEXT_MUTED, font=("Consolas", 8, "bold"))
        lbl_demand.grid(row=1, column=0, sticky="w", pady=2, padx=10)
        self.make_draggable(lbl_demand)

        demand_adj_frame = tk.Frame(input_card, bg=WIN_BG)
        demand_adj_frame.grid(row=2, column=0, sticky="w", pady=(0, 8), padx=10)
        self.make_draggable(demand_adj_frame)

        btn_min10 = tk.Label(demand_adj_frame, text="-10", bg=BG_CARD, fg=ACCENT_CYAN, 
                             font=("Consolas", 8, "bold"), padx=6, pady=3, cursor="hand2", bd=1, relief="solid")
        btn_min10.pack(side="left", padx=(0, 2))
        btn_min10.bind("<Button-1>", lambda e: self.adjust_demand(-10))
        btn_min10.bind("<Enter>", lambda e: btn_min10.config(bg="#1f2937", fg=TEXT_LIGHT))
        btn_min10.bind("<Leave>", lambda e: btn_min10.config(bg=BG_CARD, fg=ACCENT_CYAN))

        self.ent_demand = tk.Entry(demand_adj_frame, textvariable=self.var_demand, bg=BG_CARD, fg=TEXT_LIGHT, 
                                   insertbackground=TEXT_LIGHT, font=("Consolas", 11, "bold"), bd=0, 
                                   highlightthickness=1, highlightcolor=ACCENT_CYAN, highlightbackground=BG_CARD, 
                                   width=8, justify="center")
        self.ent_demand.pack(side="left", padx=2)

        btn_add10 = tk.Label(demand_adj_frame, text="+10", bg=BG_CARD, fg=ACCENT_CYAN, 
                             font=("Consolas", 8, "bold"), padx=6, pady=3, cursor="hand2", bd=1, relief="solid")
        btn_add10.pack(side="left", padx=(2, 0))
        btn_add10.bind("<Button-1>", lambda e: self.adjust_demand(10))
        btn_add10.bind("<Enter>", lambda e: btn_add10.config(bg="#1f2937", fg=TEXT_LIGHT))
        btn_add10.bind("<Leave>", lambda e: btn_add10.config(bg=BG_CARD, fg=ACCENT_CYAN))

        unit_suffix = "APRM" if self.calc.selected_unit == 1 else "RTP"
        self.lbl_rtp_in = tk.Label(input_card, text=f"CORE POWER ({unit_suffix}%)", bg=WIN_BG, fg=TEXT_MUTED, font=("Consolas", 8, "bold"))
        self.lbl_rtp_in.grid(row=3, column=0, sticky="w", pady=2, padx=10)
        self.make_draggable(self.lbl_rtp_in)

        self.ent_rtp = tk.Entry(input_card, textvariable=self.var_rtp, bg=BG_CARD, fg=TEXT_LIGHT, 
                                insertbackground=TEXT_LIGHT, font=("Consolas", 11, "bold"), bd=0, 
                                highlightthickness=1, highlightcolor=ACCENT_CYAN, highlightbackground=BG_CARD, 
                                width=12, justify="center")
        self.ent_rtp.grid(row=4, column=0, sticky="w", pady=(0, 8), padx=10)

        lbl_out_header = tk.Label(input_card, text="OUTPUTS", bg=WIN_BG, fg=ACCENT_CYAN, font=("Consolas", 8, "bold"))
        lbl_out_header.grid(row=0, column=1, pady=(4, 4), sticky="w", padx=10)
        self.make_draggable(lbl_out_header)

        lbl_gen = tk.Label(input_card, text="GENERATOR LOAD", bg=WIN_BG, fg=TEXT_MUTED, font=("Consolas", 8, "bold"))
        lbl_gen.grid(row=1, column=1, sticky="w", pady=2, padx=10)
        self.make_draggable(lbl_gen)
        
        self.lbl_gen_val = tk.Label(input_card, text="0.00 MWe", bg=WIN_BG, fg=TEXT_LIGHT, font=("Consolas", 11, "bold"))
        self.lbl_gen_val.grid(row=2, column=1, sticky="w", pady=(0, 8), padx=10)
        self.make_draggable(self.lbl_gen_val)

        lbl_feed = tk.Label(input_card, text="FEEDWATER FLOW", bg=WIN_BG, fg=TEXT_MUTED, font=("Consolas", 8, "bold"))
        lbl_feed.grid(row=3, column=1, sticky="w", pady=2, padx=10)
        self.make_draggable(lbl_feed)
        
        self.lbl_feed_val = tk.Label(input_card, text="0.00 kg/s", bg=WIN_BG, fg=TEXT_LIGHT, font=("Consolas", 11, "bold"))
        self.lbl_feed_val.grid(row=4, column=1, sticky="w", pady=(0, 8), padx=10)
        self.make_draggable(self.lbl_feed_val)

        self.btn_feedback = tk.Label(container, text="Feedback & Suggestions", bg=BG_CARD, fg=TEXT_MUTED,
                                     font=("Segoe UI", 8, "bold"), cursor="hand2", bd=1, relief="solid", padx=8, pady=3)
        self.btn_feedback.pack(side="bottom", pady=(4, 0))
        self.btn_feedback.bind("<Button-1>", lambda e: self.open_suggestions_dialog())
        self.btn_feedback.bind("<Enter>", lambda e: self.btn_feedback.config(bg="#1f2937", fg=ACCENT_CYAN))
        self.btn_feedback.bind("<Leave>", lambda e: self.btn_feedback.config(bg=BG_CARD, fg=TEXT_MUTED))

        self.neon_frame = tk.Frame(container, bg=WIN_BG, padx=8, pady=6, bd=0)
        self.neon_frame.pack(fill="x", side="bottom", pady=(4, 0))
        self.make_draggable(self.neon_frame)

        unit_suffix = "APRM" if self.calc.selected_unit == 1 else "RTP"
        self.lbl_neon_rtp = tk.Label(self.neon_frame, text=f"0.00% {unit_suffix}", bg=WIN_BG, fg=ACCENT_CYAN, 
                                     font=("Consolas", 18, "bold"))
        self.lbl_neon_rtp.pack(anchor="center")
        self.make_draggable(self.lbl_neon_rtp)

        self.lbl_neon_sub = tk.Label(self.neon_frame, text="APRM REACTOR POWER STATUS", bg=WIN_BG, fg=TEXT_MUTED, 
                                     font=("Consolas", 8, "bold"))
        self.lbl_neon_sub.pack(anchor="center", pady=(2, 0))
        self.make_draggable(self.lbl_neon_sub)

    def build_compact_layout(self):
        compact_frame = tk.Frame(self.win, bg=WIN_BG, padx=6, pady=4)
        compact_frame.pack(fill="both", expand=True)
        self.make_draggable(compact_frame)
        compact_frame.bind("<Double-Button-1>", lambda e: self.toggle_compact())

        # Pack right-side control buttons first so they are never clipped/hidden when layout expands
        btn_close = tk.Label(compact_frame, text="✕", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold"),
                             cursor="hand2", bd=1, relief="solid", padx=5, pady=1)
        btn_close.pack(side="right", padx=(2, 2), pady=2)
        btn_close.bind("<Button-1>", lambda e: self.quit_app())
        btn_close.bind("<Enter>", lambda e: btn_close.config(bg=ACCENT_RED, fg=TEXT_LIGHT))
        btn_close.bind("<Leave>", lambda e: btn_close.config(bg=BG_CARD, fg=TEXT_MUTED))

        btn_exp = tk.Label(compact_frame, text="⛶", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9),
                           cursor="hand2", bd=1, relief="solid", padx=5, pady=1)
        btn_exp.pack(side="right", padx=2, pady=2)
        btn_exp.bind("<Button-1>", lambda e: self.toggle_compact())
        btn_exp.bind("<Enter>", lambda e: btn_exp.config(bg="#1f2937", fg=ACCENT_CYAN))
        btn_exp.bind("<Leave>", lambda e: btn_exp.config(bg=BG_CARD, fg=TEXT_MUTED))

        self.lbl_compact_sync_dtl = tk.Label(compact_frame, text="--", bg=BG_CARD, fg=ACCENT_GOLD,
                                             font=("Consolas", 8, "bold"), cursor="hand2", bd=1, relief="solid", padx=4, pady=1)
        self.lbl_compact_sync_dtl.pack(side="right", padx=2, pady=2)
        self.lbl_compact_sync_dtl.bind("<Button-1>", lambda e: self.open_server_sync_dialog())
        self.lbl_compact_sync_dtl.bind("<Enter>", lambda e: self.lbl_compact_sync_dtl.config(bg="#1f2937", fg=ACCENT_CYAN))
        self.lbl_compact_sync_dtl.bind("<Leave>", lambda e: self.lbl_compact_sync_dtl.config(bg=BG_CARD, fg=ACCENT_GOLD))

        handle = tk.Label(compact_frame, text="⋮⋮", bg=WIN_BG, fg=TEXT_MUTED, font=("Segoe UI", 11, "bold"), cursor="fleur")
        handle.pack(side="left", padx=(2, 4))
        self.make_draggable(handle)
        handle.bind("<Double-Button-1>", lambda e: self.toggle_compact())

        self.btn_compact_u1 = tk.Label(compact_frame, text="U1", bg=BG_CARD, fg=TEXT_MUTED,
                                       font=("Segoe UI", 8, "bold"), padx=4, pady=1, cursor="hand2", bd=1, relief="solid")
        self.btn_compact_u1.pack(side="left", padx=(1, 1), pady=2)
        self.btn_compact_u1.bind("<Button-1>", lambda e: self.select_unit(1))
        self.btn_compact_u1.bind("<Enter>", lambda e: self.btn_compact_u1.config(bg="#1f2937", fg=TEXT_LIGHT) if self.calc.selected_unit != 1 else None)
        self.btn_compact_u1.bind("<Leave>", lambda e: self.update_unit_ui_state())

        self.btn_compact_u2 = tk.Label(compact_frame, text="U2", bg=BG_CARD, fg=TEXT_MUTED,
                                       font=("Segoe UI", 8, "bold"), padx=4, pady=1, cursor="hand2", bd=1, relief="solid")
        self.btn_compact_u2.pack(side="left", padx=(1, 2), pady=2)
        self.btn_compact_u2.bind("<Button-1>", lambda e: self.select_unit(2))
        self.btn_compact_u2.bind("<Enter>", lambda e: self.btn_compact_u2.config(bg="#1f2937", fg=TEXT_LIGHT) if self.calc.selected_unit != 2 else None)
        self.btn_compact_u2.bind("<Leave>", lambda e: self.update_unit_ui_state())

        lbl_mw = tk.Label(compact_frame, text="MWt:", bg=WIN_BG, fg=TEXT_MUTED, font=("Segoe UI", 8, "bold"))
        lbl_mw.pack(side="left", padx=2)
        self.make_draggable(lbl_mw)

        btn_min10 = tk.Label(compact_frame, text="-", bg=BG_CARD, fg=ACCENT_CYAN, 
                             font=("Segoe UI", 9, "bold"), padx=5, pady=1, cursor="hand2", bd=1, relief="solid")
        btn_min10.pack(side="left", padx=(2, 1), pady=2)
        btn_min10.bind("<Button-1>", lambda e: self.adjust_demand(-10))
        btn_min10.bind("<Enter>", lambda e: btn_min10.config(bg="#1f2937", fg=TEXT_LIGHT))
        btn_min10.bind("<Leave>", lambda e: btn_min10.config(bg=BG_CARD, fg=ACCENT_CYAN))

        self.ent_demand = tk.Entry(compact_frame, textvariable=self.var_demand, bg=BG_CARD, fg=TEXT_LIGHT,
                                   insertbackground=TEXT_LIGHT, font=("Consolas", 10, "bold"), bd=0,
                                   highlightthickness=1, highlightcolor=ACCENT_CYAN, highlightbackground=BG_CARD,
                                   width=6, justify="center")
        self.ent_demand.pack(side="left", padx=2, pady=2)

        btn_add10 = tk.Label(compact_frame, text="+", bg=BG_CARD, fg=ACCENT_CYAN, 
                             font=("Segoe UI", 9, "bold"), padx=5, pady=1, cursor="hand2", bd=1, relief="solid")
        btn_add10.pack(side="left", padx=(1, 2), pady=2)
        btn_add10.bind("<Button-1>", lambda e: self.adjust_demand(10))
        btn_add10.bind("<Enter>", lambda e: btn_add10.config(bg="#1f2937", fg=TEXT_LIGHT))
        btn_add10.bind("<Leave>", lambda e: btn_add10.config(bg=BG_CARD, fg=ACCENT_CYAN))

        self.lbl_arrow_ref = tk.Label(compact_frame, text="➔", bg=WIN_BG, fg=ACCENT_CYAN, font=("Segoe UI", 10, "bold"))
        self.lbl_arrow_ref.pack(side="left", padx=2)
        self.make_draggable(self.lbl_arrow_ref)
        self.lbl_arrow_ref.bind("<Double-Button-1>", lambda e: self.toggle_compact())

        # Stack RTP and Flow vertically to save horizontal space
        self.telemetry_frame = tk.Frame(compact_frame, bg=WIN_BG)
        self.telemetry_frame.pack(side="left", padx=(2, 0))
        self.make_draggable(self.telemetry_frame)
        self.telemetry_frame.bind("<Double-Button-1>", lambda e: self.toggle_compact())

        unit_suffix = "APRM" if self.calc.selected_unit == 1 else "RTP"
        self.lbl_compact_rtp = tk.Label(self.telemetry_frame, text=f"0.0% {unit_suffix}", bg=WIN_BG, fg=ACCENT_CYAN,
                                         font=("Consolas", 10, "bold"))
        self.lbl_compact_rtp.pack(side="top", anchor="center")
        self.make_draggable(self.lbl_compact_rtp)
        self.lbl_compact_rtp.bind("<Double-Button-1>", lambda e: self.toggle_compact())

        self.lbl_compact_flow = tk.Label(self.telemetry_frame, text="[0 kg/s]", bg=WIN_BG, fg=TEXT_MUTED,
                                         font=("Consolas", 8))
        self.lbl_compact_flow.pack(side="top", anchor="center")
        self.make_draggable(self.lbl_compact_flow)
        self.lbl_compact_flow.bind("<Double-Button-1>", lambda e: self.toggle_compact())

        self.update_unit_ui_state()

    def adjust_demand(self, amount):
        try:
            val = float(self.var_demand.get() or "0")
        except ValueError:
            val = 0.0
        new_val = max(0.0, val + amount)
        self._demand_changed_waiting_heartbeat = True
        self._pending_demand_value = new_val
        self.var_demand.set(f"{new_val:.2f}" if not self.is_compact else f"{int(new_val)}")

    def select_unit(self, unit):
        self.calc.selected_unit = unit
        self._demand_changed_waiting_heartbeat = False
        if hasattr(self, 'active_overlay_server') and self.active_overlay_server:
            st = self.active_overlay_server.get("state", {})
            u_st = st.get("Unit1", {}) if unit == 1 else st.get("Unit2", {})
            target_keys = ["NextDemandU1", "NextDemandU2", "Next Demand", "next_demand"] if getattr(self, 'overlay_next_demand_switched', False) else ["DemandU1", "DemandU2", "Demand", "demand"]
            dem_val = None
            for key in target_keys:
                if key in u_st and u_st[key] is not None:
                    try:
                        dem_val = float(u_st[key])
                        break
                    except (ValueError, TypeError):
                        pass
            if dem_val is not None:
                self._last_synced_demand = dem_val
                self.var_demand.set(str(dem_val))

        self.update_unit_ui_state()
        self.update_calculations(source="demand")
        self.save_settings()

    def toggle_compact_unit(self):
        next_unit = 2 if self.calc.selected_unit == 1 else 1
        self.select_unit(next_unit)

    def setup_tray_icon(self):
        try:
            import pystray
            from PIL import Image
            
            if os.path.exists("icon.png"):
                image = Image.open("icon.png")
            else:
                image = self.icon_image_pil
            
            menu = pystray.Menu(
                pystray.MenuItem("Show / Restore", lambda icon, item: self.restore_window(), default=True),
                pystray.MenuItem("Compact Mode", lambda icon, item: self.toggle_compact(), checked=lambda item: self.is_compact),
                pystray.MenuItem("Always on Top", lambda icon, item: self.toggle_topmost(), checked=lambda item: self.is_topmost),
                pystray.MenuItem("Topmost on Roblox", lambda icon, item: self.toggle_topmost_on_roblox(), checked=lambda item: self.topmost_on_roblox),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", lambda icon, item: self.quit_app())
            )
            
            self.tray = pystray.Icon("RBWR APRM Calculator", image, f"RBWR APRM Calculator v{__version__}", menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception:
            self.tray = None

    def load_settings(self):
        defaults = {
            "usage": 61.32,
            "opacity": 0.90,
            "selected_unit": 1,
            "is_compact": False,
            "is_topmost": True,
            "topmost_on_roblox": True,
            "skipped_version": "",
            "next_demand_threshold_seconds": 60,
            "last_job_id": "",
            "dtl_calibration_offset": 0.0,
            "enable_turbine_health_alert": False,
            "turbine_health_threshold": 65.0
        }
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    defaults.update(data)
        except Exception:
            pass
        return defaults

    def save_settings(self):
        try:
            current_opacity = self.bg_win.attributes("-alpha") if (hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists()) else self.win.attributes("-alpha")
            data = {
                "usage": self.calc.usage,
                "opacity": current_opacity,
                "selected_unit": self.calc.selected_unit,
                "is_compact": self.is_compact,
                "is_topmost": self.is_topmost,
                "topmost_on_roblox": self.var_topmost_on_roblox.get(),
                "skipped_version": getattr(self, 'skipped_version', ""),
                "next_demand_threshold_seconds": getattr(self, 'next_demand_threshold_seconds', 60),
                "last_job_id": self.var_overlay_job_id.get().strip() if hasattr(self, 'var_overlay_job_id') else getattr(self, 'last_job_id', ""),
                "dtl_calibration_offset": getattr(self, 'dtl_calibration_offset', 0.0),
                "enable_turbine_health_alert": getattr(self, 'enable_turbine_health_alert', False),
                "turbine_health_threshold": getattr(self, 'turbine_health_threshold', 65.0)
            }
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    def restore_window(self):
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            self.bg_win.deiconify()
        self.win.deiconify()
        self.sync_bg_window()
        self.win.attributes("-topmost", self.is_topmost)
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            self.bg_win.attributes("-topmost", self.is_topmost)
        self.ensure_z_order()
        if hasattr(self, 'settings_window') and self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift(self.win)
        if hasattr(self, 'suggestions_window') and self.suggestions_window and self.suggestions_window.winfo_exists():
            self.suggestions_window.lift(self.win)
        if hasattr(self, 'update_window') and self.update_window and self.update_window.winfo_exists():
            self.update_window.lift(self.win)
        if hasattr(self, 'loading_window') and self.loading_window and self.loading_window.winfo_exists():
            self.loading_window.lift(self.win)

    def open_log_file(self):
        try:
            if os.path.exists(_log_path):
                os.startfile(_log_path)
            else:
                self.show_custom_message("Log File", f"Log file not found at:\n{_log_path}")
        except Exception as e:
            log.error(f"Failed to open log file: {e}")

    def quit_app(self):
        if hasattr(self, 'tray') and self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
            try:
                self.bg_win.destroy()
            except Exception:
                pass
        self.root.destroy()
        os._exit(0)

    def update_unit_ui_state(self):
        if hasattr(self, 'btn_u1') and hasattr(self, 'btn_u2') and self.btn_u1.winfo_exists() and self.btn_u2.winfo_exists():
            if self.calc.selected_unit == 1:
                self.btn_u1.config(bg=BG_CARD, fg=ACCENT_CYAN, text="❖ UNIT 01 ❖", bd=1, relief="solid")
                self.btn_u2.config(bg=BG_CARD, fg=TEXT_MUTED, text="  UNIT 02  ", bd=1, relief="solid")
            else:
                self.btn_u1.config(bg=BG_CARD, fg=TEXT_MUTED, text="  UNIT 01  ", bd=1, relief="solid")
                self.btn_u2.config(bg=BG_CARD, fg=ACCENT_CYAN, text="❖ UNIT 02 ❖", bd=1, relief="solid")

        if hasattr(self, 'btn_compact_u1') and hasattr(self, 'btn_compact_u2') and self.btn_compact_u1.winfo_exists() and self.btn_compact_u2.winfo_exists():
            if self.calc.selected_unit == 1:
                self.btn_compact_u1.config(bg=ACCENT_CYAN, fg=BG_MAIN, bd=1, relief="solid")
                self.btn_compact_u2.config(bg=BG_CARD, fg=TEXT_MUTED, bd=1, relief="solid")
            else:
                self.btn_compact_u1.config(bg=BG_CARD, fg=TEXT_MUTED, bd=1, relief="solid")
                self.btn_compact_u2.config(bg=ACCENT_CYAN, fg=BG_MAIN, bd=1, relief="solid")

        unit_suffix = "APRM" if self.calc.selected_unit == 1 else "RTP"
        if hasattr(self, 'lbl_rtp_in') and self.lbl_rtp_in and self.lbl_rtp_in.winfo_exists():
            self.lbl_rtp_in.config(text=f"CORE POWER ({unit_suffix}%)")

    def open_settings_dialog(self):
        if hasattr(self, 'settings_window') and self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.attributes("-topmost", True)
            self.settings_window.focus_force()
            return

        settings_win = tk.Toplevel(self.win)
        self.settings_window = settings_win
        settings_win.transient(self.win)

        settings_win.title("APRM Monitor Settings")
        settings_win.configure(bg=BG_CARD, highlightbackground=ACCENT_CYAN, highlightcolor=ACCENT_CYAN, highlightthickness=1)
        settings_win.overrideredirect(True)
        settings_win.attributes("-topmost", True)

        # Center relative to active overlay window
        w = 380
        h = 480
        x = self.win.winfo_x() + (self.win.winfo_width() - w) // 2
        y = self.win.winfo_y() + (self.win.winfo_height() - h) // 2

        settings_win.geometry(f"{w}x{h}+{x}+{y}")

        title_bar = tk.Frame(settings_win, bg=BG_HEADER, height=30)
        title_bar.pack(fill="x", side="top")

        title_lbl = tk.Label(title_bar, text="CONFIGURATION SETTINGS", bg=BG_HEADER, fg=ACCENT_CYAN,
                             font=("Consolas", 9, "bold"))
        title_lbl.pack(side="left", padx=10, pady=5)

        self.make_popup_draggable(settings_win, title_bar, title_lbl)

        btn_close = tk.Label(title_bar, text="✕", bg=BG_HEADER, fg=TEXT_MUTED, width=3, font=("Segoe UI", 11, "bold"), cursor="hand2")
        btn_close.pack(side="right", fill="y")
        btn_close.bind("<Button-1>", lambda e: settings_win.destroy())
        btn_close.bind("<Enter>", lambda e: btn_close.config(bg=ACCENT_RED, fg=TEXT_LIGHT))
        btn_close.bind("<Leave>", lambda e: btn_close.config(bg=BG_HEADER, fg=TEXT_MUTED))

        content_frame = tk.Frame(settings_win, bg=BG_CARD, padx=15, pady=10)
        content_frame.pack(fill="both", expand=True)

        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)


        lbl_usage = tk.Label(content_frame, text="Site Usage (MWe):", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_usage.grid(row=0, column=0, sticky="w", pady=4)

        self.ent_usage = tk.Entry(content_frame, textvariable=self.var_usage, bg=BG_CARD, fg=ACCENT_CYAN, 
                                  readonlybackground=BG_CARD, insertbackground=TEXT_LIGHT, font=("Consolas", 10, "bold"), 
                                  bd=0, highlightthickness=0, width=10, justify="center", state="readonly")
        self.ent_usage.grid(row=0, column=1, sticky="e", padx=10, pady=4)


        lbl_usage_note = tk.Label(content_frame, text="Use Recirc Speed Override if Site Usage is off by a lot (10-15 MW off)", 
                                  bg=BG_CARD, fg=ACCENT_GOLD, font=("Segoe UI", 7, "italic"), justify="left", wraplength=340)
        lbl_usage_note.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 4))


        lbl_opacity = tk.Label(content_frame, text="Overlay Opacity:", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_opacity.grid(row=2, column=0, sticky="w", pady=4)

        current_opacity = self.bg_win.attributes("-alpha") if (hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists()) else self.win.attributes("-alpha")
        self.slider_opacity = ttk.Scale(content_frame, from_=0.1, to=1.0, value=current_opacity,
                                         orient="horizontal", command=self.on_opacity_change)
        self.slider_opacity.grid(row=2, column=1, sticky="we", padx=10, pady=4)


        lbl_roblox_topmost = tk.Label(content_frame, text="Topmost on Roblox:", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_roblox_topmost.grid(row=3, column=0, sticky="w", pady=4)

        roblox_topmost_status = "ENABLED" if self.var_topmost_on_roblox.get() else "DISABLED"
        roblox_topmost_color = ACCENT_GREEN if self.var_topmost_on_roblox.get() else ACCENT_RED
        self.btn_roblox_topmost_toggle = tk.Label(content_frame, text=roblox_topmost_status, bg=BG_MAIN, fg=roblox_topmost_color,
                                                  font=("Consolas", 9, "bold"), bd=1, relief="solid", padx=10, pady=3, cursor="hand2")
        self.btn_roblox_topmost_toggle.grid(row=3, column=1, sticky="e", padx=10, pady=4)
        self.btn_roblox_topmost_toggle.bind("<Button-1>", lambda e: self.toggle_roblox_topmost_setting())
        self.btn_roblox_topmost_toggle.bind("<Enter>", lambda e: self.btn_roblox_topmost_toggle.config(bg=BG_HEADER))
        self.btn_roblox_topmost_toggle.bind("<Leave>", lambda e: self.btn_roblox_topmost_toggle.config(bg=BG_MAIN))


        lbl_thresh = tk.Label(content_frame, text="Next Demand Switch (s):", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_thresh.grid(row=4, column=0, sticky="w", pady=4)

        self.ent_thresh = tk.Entry(content_frame, textvariable=self.var_demand_threshold, bg=BG_MAIN, fg=ACCENT_CYAN,
                                   insertbackground=TEXT_LIGHT, font=("Consolas", 9, "bold"), bd=1, relief="solid",
                                   width=6, justify="center")
        self.ent_thresh.grid(row=4, column=1, sticky="e", padx=10, pady=4)
        self.ent_thresh.bind("<Button-1>", lambda e: self.ent_thresh.focus_force())


        lbl_recirc = tk.Label(content_frame, text="Recirc Override (%):", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_recirc.grid(row=5, column=0, sticky="w", pady=4)

        recirc_frame = tk.Frame(content_frame, bg=BG_CARD)
        recirc_frame.grid(row=5, column=1, sticky="e", padx=10, pady=4)

        self.ent_recirc = tk.Entry(recirc_frame, textvariable=self.var_recirc_override, bg=BG_MAIN, fg=ACCENT_CYAN,
                                   insertbackground=TEXT_LIGHT, font=("Consolas", 9, "bold"), bd=1, relief="solid",
                                   width=6, justify="center")
        self.ent_recirc.pack(side="left", padx=(0, 5))
        self.ent_recirc.bind("<Button-1>", lambda e: self.ent_recirc.focus_force())
        
        settings_win.bind("<Button-1>", lambda e: settings_win.focus_force() if not isinstance(e.widget, (tk.Entry, tk.Text)) else None)
        content_frame.bind("<Button-1>", lambda e: settings_win.focus_force() if not isinstance(e.widget, (tk.Entry, tk.Text)) else None)

        btn_recirc_reset = tk.Label(recirc_frame, text="Reset", bg=BG_MAIN, fg=TEXT_MUTED,
                                    font=("Segoe UI", 8, "bold"), bd=1, relief="solid", padx=8, pady=2, cursor="hand2")
        btn_recirc_reset.pack(side="left")
        btn_recirc_reset.bind("<Button-1>", lambda e: self.reset_recirc_override())
        btn_recirc_reset.bind("<Enter>", lambda e: btn_recirc_reset.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        btn_recirc_reset.bind("<Leave>", lambda e: btn_recirc_reset.config(bg=BG_MAIN, fg=TEXT_MUTED))

        lbl_recirc_note = tk.Label(content_frame, text="Use this when running SELF-CIRC mode as it doesn't require recirc changes.", 
                                   bg=BG_CARD, fg=ACCENT_GOLD, font=("Segoe UI", 7, "italic"), justify="left")
        lbl_recirc_note.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 4))

        lbl_turbine_alert = tk.Label(content_frame, text="Turbine Health Alert:", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_turbine_alert.grid(row=7, column=0, sticky="w", pady=4)

        t_alert_status = "ENABLED" if self.var_turbine_health_alert.get() else "DISABLED"
        t_alert_color = ACCENT_GREEN if self.var_turbine_health_alert.get() else ACCENT_RED
        self.btn_turbine_health_toggle = tk.Label(content_frame, text=t_alert_status, bg=BG_MAIN, fg=t_alert_color,
                                                  font=("Consolas", 9, "bold"), bd=1, relief="solid", padx=10, pady=3, cursor="hand2")
        self.btn_turbine_health_toggle.grid(row=7, column=1, sticky="e", padx=10, pady=4)
        self.btn_turbine_health_toggle.bind("<Button-1>", lambda e: self.toggle_turbine_health_alert_setting())
        self.btn_turbine_health_toggle.bind("<Enter>", lambda e: self.btn_turbine_health_toggle.config(bg=BG_HEADER))
        self.btn_turbine_health_toggle.bind("<Leave>", lambda e: self.btn_turbine_health_toggle.config(bg=BG_MAIN))

        lbl_turbine_thresh = tk.Label(content_frame, text="Health Threshold (%):", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_turbine_thresh.grid(row=8, column=0, sticky="w", pady=4)

        self.ent_turbine_thresh = tk.Entry(content_frame, textvariable=self.var_turbine_health_threshold, bg=BG_MAIN, fg=ACCENT_CYAN,
                                           insertbackground=TEXT_LIGHT, font=("Consolas", 9, "bold"), bd=1, relief="solid",
                                           width=6, justify="center")
        self.ent_turbine_thresh.grid(row=8, column=1, sticky="e", padx=10, pady=4)
        self.ent_turbine_thresh.bind("<Button-1>", lambda e: self.ent_turbine_thresh.focus_force())


        lbl_log = tk.Label(content_frame, text="Diagnostics:", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_log.grid(row=9, column=0, sticky="w", pady=4)

        self.btn_open_log = tk.Label(content_frame, text="Open Log", bg=BG_MAIN, fg=ACCENT_CYAN,
                                      font=("Consolas", 9, "bold"), bd=1, relief="solid", padx=10, pady=3, cursor="hand2")
        self.btn_open_log.grid(row=9, column=1, sticky="e", padx=10, pady=4)
        self.btn_open_log.bind("<Button-1>", lambda e: self.open_log_file())
        self.btn_open_log.bind("<Enter>", lambda e: self.btn_open_log.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        self.btn_open_log.bind("<Leave>", lambda e: self.btn_open_log.config(bg=BG_MAIN, fg=ACCENT_CYAN))


        lbl_feedback = tk.Label(content_frame, text="Feedback & Help:", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_feedback.grid(row=10, column=0, sticky="w", pady=4)

        btn_feedback_settings = tk.Label(content_frame, text="Feedback", bg=BG_MAIN, fg=ACCENT_CYAN,
                                      font=("Consolas", 9, "bold"), bd=1, relief="solid", padx=10, pady=3, cursor="hand2")
        btn_feedback_settings.grid(row=10, column=1, sticky="e", padx=10, pady=4)
        btn_feedback_settings.bind("<Button-1>", lambda e: self.open_suggestions_dialog())
        btn_feedback_settings.bind("<Enter>", lambda e: btn_feedback_settings.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        btn_feedback_settings.bind("<Leave>", lambda e: btn_feedback_settings.config(bg=BG_MAIN, fg=ACCENT_CYAN))


        lbl_ver = tk.Label(content_frame, text=f"Version: {__version__}", bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 8))
        lbl_ver.grid(row=11, column=0, columnspan=2, sticky="w", pady=(12, 0))

        def on_settings_destroy(event):
            if event.widget == settings_win:
                self.settings_window = None
                self.update_topmost_state()
                self.ensure_z_order()

        settings_win.bind("<Destroy>", on_settings_destroy)
        settings_win.focus_force()

    def on_demand_threshold_change(self):
        try:
            val = int(self.var_demand_threshold.get().strip())
            self.next_demand_threshold_seconds = max(0, val)
            self.save_settings()
        except (ValueError, TypeError):
            pass

    def on_usage_change(self, *args):
        self.calc.set_usage(self.var_usage.get())
        self.update_calculations(source="demand")
        self.save_settings()

    def on_opacity_change(self, value):
        try:
            alpha = float(value)
            if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
                self.bg_win.attributes("-alpha", alpha)
                self.ensure_z_order()
            else:
                self.win.attributes("-alpha", alpha)
            self.save_settings()
        except ValueError:
            pass

    def on_recirc_override_change(self):
        val_str = self.var_recirc_override.get().strip()
        if not val_str:
            self.calc.recirc_override = None
        else:
            try:
                val = float(val_str)
                if val > 100.0:
                    self.var_recirc_override.set("100")
                    val = 100.0
                self.calc.recirc_override = max(0.0, val)
            except ValueError:
                pass
        self.update_calculations(source="demand")

    def trigger_turbine_health_reminder(self, current_health, threshold):
        log.warning(f"[ALERT] Unit 2 Turbine Health ({current_health:.1f}%) is below threshold ({threshold:.1f}%)!")
        
        def play_alert_sound():
            try:
                if IS_WINDOWS:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONWARNING)
                elif IS_MAC:
                    import subprocess
                    subprocess.Popen(["afplay", "/System/Library/Sounds/Ping.aiff"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self.root.bell()
            except Exception:
                pass

        threading.Thread(target=play_alert_sound, daemon=True).start()

        title = "TURBINE HEALTH WARNING"
        msg = f"Unit 2 Turbine Health is LOW!\n\nCurrent Health: {current_health:.1f}%\nAlert Threshold: {threshold:.1f}%."
        self.run_on_main_thread(lambda: self.show_custom_message(title, msg, is_error=True))

    def toggle_turbine_health_alert_setting(self):
        new_val = not self.var_turbine_health_alert.get()
        self.var_turbine_health_alert.set(new_val)
        self.enable_turbine_health_alert = new_val
        if hasattr(self, 'btn_turbine_health_toggle') and self.btn_turbine_health_toggle.winfo_exists():
            self.btn_turbine_health_toggle.config(text="ENABLED" if new_val else "DISABLED",
                                                  fg=ACCENT_GREEN if new_val else ACCENT_RED)
        self.save_settings()

    def on_turbine_health_threshold_change(self):
        try:
            val = float(self.var_turbine_health_threshold.get().strip())
            self.turbine_health_threshold = max(0.0, min(100.0, val))
            self.save_settings()
        except (ValueError, TypeError):
            pass

    def reset_recirc_override(self):
        self.var_recirc_override.set("")
        self.calc.recirc_override = None
        self.update_calculations(source="demand")

    def toggle_topmost_on_roblox(self):
        new_val = not self.var_topmost_on_roblox.get()
        self.var_topmost_on_roblox.set(new_val)
        self.save_settings()
        if hasattr(self, 'tray') and self.tray:
            try:
                self.tray.update_menu()
            except Exception:
                pass

    def toggle_roblox_topmost_setting(self):
        new_val = not self.var_topmost_on_roblox.get()
        self.var_topmost_on_roblox.set(new_val)
        if hasattr(self, 'btn_roblox_topmost_toggle') and self.btn_roblox_topmost_toggle.winfo_exists():
            self.btn_roblox_topmost_toggle.config(text="ENABLED" if new_val else "DISABLED",
                                                  fg=ACCENT_GREEN if new_val else ACCENT_RED)
        self.save_settings()
        if hasattr(self, 'tray') and self.tray:
            try:
                self.tray.update_menu()
            except Exception:
                pass

    def is_any_window_open(self) -> bool:
        window_attrs = [
            'settings_window',
            'suggestions_window',
            'update_window',
            'loading_window',
            'custom_message_window',
            'server_sync_window',
        ]
        for attr in window_attrs:
            if hasattr(self, attr):
                win_obj = getattr(self, attr, None)
                if win_obj and win_obj.winfo_exists():
                    return True

        try:
            for child in self.root.winfo_children():
                if isinstance(child, tk.Toplevel) and child != self.win and child != getattr(self, 'bg_win', None) and child.winfo_exists():
                    return True
        except Exception:
            pass

        return False

    def update_topmost_state(self):
        try:
            if self.is_any_window_open():
                return

            if self.is_topmost:
                if not self.win.attributes("-topmost"):
                    self.win.attributes("-topmost", True)
                    if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
                        self.bg_win.attributes("-topmost", True)
                    self.ensure_z_order()
            elif self.topmost_on_roblox:
                is_roblox = False
                is_ours = False
                our_hwnd = None
                hwnd = None

                if IS_WINDOWS:
                    hwnd = ctypes.windll.user32.GetForegroundWindow()
                    try:
                        hwnd_to_use = self.win.winfo_id()
                        parent = ctypes.windll.user32.GetParent(hwnd_to_use)
                        our_hwnd = parent if parent else hwnd_to_use
                    except Exception:
                        hwnd_to_use = None
                        our_hwnd = None

                    window_title = ""
                    class_name = ""
                    proc_name = ""
                    pid_val = 0

                    if hwnd:
                        buffer_len = ctypes.windll.user32.GetWindowTextLengthW(hwnd) + 1
                        buffer = ctypes.create_unicode_buffer(buffer_len)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, buffer_len)
                        window_title = buffer.value.strip()

                        class_buf = ctypes.create_unicode_buffer(256)
                        ctypes.windll.user32.GetClassNameW(hwnd, class_buf, 256)
                        class_name = class_buf.value.strip()

                        active_pid = wintypes.DWORD(0)  # pyright: ignore[reportPossiblyUnboundVariable]
                        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(active_pid))
                        pid_val = active_pid.value

                        if pid_val:
                            for mask in (0x1000, 0x0410):
                                try:
                                    h_proc = ctypes.windll.kernel32.OpenProcess(mask, False, pid_val)
                                    if h_proc:
                                        pbuf = ctypes.create_unicode_buffer(512)
                                        psize = wintypes.DWORD(512)  # pyright: ignore[reportPossiblyUnboundVariable]
                                        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, pbuf, ctypes.byref(psize)):
                                            proc_name = os.path.basename(pbuf.value).lower()
                                        ctypes.windll.kernel32.CloseHandle(h_proc)
                                        if proc_name:
                                            break
                                except Exception:
                                    pass

                        title_lower = window_title.lower()
                        is_roblox = bool(
                            "roblox" in proc_name or
                            "robloxplayerbeta" in proc_name or
                            class_name in ("WINDOWSCLIENT", "RobloxApp", "RobloxPlayerBeta") or
                            "roblox" in class_name.lower() or
                            "roblox" in title_lower or
                            "realistic" in title_lower or
                            "rbwr" in title_lower
                        )
                        is_ours = bool(pid_val == os.getpid() or (our_hwnd and hwnd == our_hwnd) or (hwnd_to_use and hwnd == hwnd_to_use))

                elif IS_MAC:
                    app_name, bundle_id = get_macos_active_app()
                    app_name_lower = (app_name or "").lower()
                    bundle_id_lower = (bundle_id or "").lower()
                    is_roblox = bool(
                        "roblox" in app_name_lower or
                        "roblox" in bundle_id_lower or
                        "realistic" in app_name_lower or
                        "rbwr" in app_name_lower
                    )
                    is_ours = bool("rbwr" in app_name_lower or "python" in app_name_lower or "tk" in app_name_lower)
                else:
                    is_roblox = True

                prev_roblox_active = getattr(self, 'is_roblox_active', False)
                # Keep active if currently on Roblox, or if user is interacting with our overlay while Roblox was active
                self.is_roblox_active = bool(is_roblox or (is_ours and prev_roblox_active))

                if hwnd != getattr(self, '_last_logged_foreground_hwnd', None) or self.is_roblox_active != getattr(self, '_last_logged_roblox_state', None):
                    self._last_logged_foreground_hwnd = hwnd
                    self._last_logged_roblox_state = self.is_roblox_active

                if self.is_roblox_active:
                    if not self.win.attributes("-topmost"):
                        self.win.attributes("-topmost", True)
                        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
                            self.bg_win.attributes("-topmost", True)
                        self.ensure_z_order()
                else:
                    if self.win.attributes("-topmost"):
                        self.win.attributes("-topmost", False)
                        if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
                            self.bg_win.attributes("-topmost", False)
                            self.bg_win.lower()
                        self.win.lower()
                        if IS_WINDOWS and our_hwnd:
                            ctypes.windll.user32.SetWindowPos(our_hwnd, -2, 0, 0, 0, 0, 0x0010 | 0x0002 | 0x0001)
                            ctypes.windll.user32.SetWindowPos(our_hwnd, 1, 0, 0, 0, 0, 0x0010 | 0x0002 | 0x0001)
            else:
                self.is_roblox_active = False
                if self.win.attributes("-topmost"):
                    self.win.attributes("-topmost", False)
                    if hasattr(self, 'bg_win') and self.bg_win and self.bg_win.winfo_exists():
                        self.bg_win.attributes("-topmost", False)
                        self.bg_win.lower()
                    self.win.lower()
                    if IS_WINDOWS:
                        try:
                            hwnd_to_use = self.win.winfo_id()
                            parent = ctypes.windll.user32.GetParent(hwnd_to_use)
                            our_hwnd = parent if parent else hwnd_to_use
                            if our_hwnd:
                                ctypes.windll.user32.SetWindowPos(our_hwnd, -2, 0, 0, 0, 0, 0x0010 | 0x0002 | 0x0001)
                                ctypes.windll.user32.SetWindowPos(our_hwnd, 1, 0, 0, 0, 0, 0x0010 | 0x0002 | 0x0001)
                        except Exception:
                            pass
        except Exception:
            pass

    def check_focus_loop(self):
        if not self.is_any_window_open():
            self.update_topmost_state()
        self.root.after(200, self.check_focus_loop)

    def check_for_updates(self):
        if not _is_compiled:
            log.info("Update check skipped (not running compiled binary).")
            return
            
        def run_check():
            import urllib.request
            import json
            try:
                threading.Event().wait(1.5)
                
                url = "https://api.github.com/repos/Hotment/RBWR-Utility/releases/latest"
                req = urllib.request.Request(url, headers=UPDATE_HTTP_HEADERS)
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode('utf-8'))
                        tag_name = data.get("tag_name", "")
                        latest_version = tag_name.lstrip('vV')
                        if latest_version and latest_version != __version__:
                            if latest_version != self.skipped_version:
                                release_notes = data.get("body", "No release details available.")
                                download_url = None
                                filename = f"RBWR_APRM_Calculator_v{latest_version}.exe"
                                for asset in data.get("assets", []):
                                    if asset.get("name", "").endswith(".exe"):
                                        filename = asset.get("name")
                                        download_url = asset.get("browser_download_url")
                                        break
                                
                                if download_url:
                                    log.info(f"Update check: New update {latest_version} is available.")
                                    self.run_on_main_thread(lambda: self.show_update_dialog(latest_version, release_notes, filename, download_url))
                                else:
                                    log.warning("Update check: Found update but no .exe asset in the release.")
                            else:
                                log.info(f"Update check: New update {latest_version} matches skipped version. Prompt suppressed.")
                        else:
                            log.info("Update check: Application is up to date.")
                    else:
                        log.warning(f"Update check: Unexpected response status from GitHub: {response.status}")
            except Exception as e:
                log.info(f"Update check skipped/failed (GitHub API offline/error): {e}")
                
        threading.Thread(target=run_check, daemon=True).start()

    def show_update_dialog(self, latest_version, release_notes, download_filename, download_url):
        if hasattr(self, 'update_window') and self.update_window and self.update_window.winfo_exists():
            self.update_window.deiconify()
            self.update_window.lift()
            self.update_window.attributes("-topmost", True)
            self.update_window.focus_force()
            return

        popup = tk.Toplevel(self.win)
        self.update_window = popup
        popup.transient(self.win)

        popup.title("Update Available")
        popup.configure(bg=BG_CARD, highlightbackground=ACCENT_CYAN, highlightcolor=ACCENT_CYAN, highlightthickness=1)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        
        # Center relative to active overlay window
        w = 380
        h = 260
        x = self.win.winfo_x() + (self.win.winfo_width() - w) // 2
        y = self.win.winfo_y() + (self.win.winfo_height() - h) // 2
        
        popup.geometry(f"{w}x{h}+{x}+{y}")
        
        title_bar = tk.Frame(popup, bg=BG_HEADER, height=30)
        title_bar.pack(fill="x", side="top")
        
        title_lbl = tk.Label(title_bar, text="SYSTEM UPDATE AVAILABLE", bg=BG_HEADER, fg=ACCENT_GOLD,
                             font=("Consolas", 9, "bold"))
        title_lbl.pack(side="left", padx=10, pady=5)

        self.make_popup_draggable(popup, title_bar, title_lbl)

        btn_close = tk.Label(title_bar, text="✕", bg=BG_HEADER, fg=TEXT_MUTED, width=3, font=("Segoe UI", 11, "bold"), cursor="hand2")
        btn_close.pack(side="right", fill="y")
        btn_close.bind("<Button-1>", lambda e: popup.destroy())
        btn_close.bind("<Enter>", lambda e: btn_close.config(bg=ACCENT_RED, fg=TEXT_LIGHT))
        btn_close.bind("<Leave>", lambda e: btn_close.config(bg=BG_HEADER, fg=TEXT_MUTED))
        
        content_frame = tk.Frame(popup, bg=BG_CARD, padx=15, pady=15)
        content_frame.pack(fill="both", expand=True)
        
        msg_lbl = tk.Label(content_frame, text=f"A new version (v{latest_version}) is ready!\nYour version: v{__version__}", 
                           bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 10, "bold"), justify="left")
        msg_lbl.pack(anchor="w", pady=(0, 10))
        
        btn_frame = tk.Frame(content_frame, bg=BG_CARD)
        btn_frame.pack(fill="x", side="bottom")

        notes_frame = tk.Frame(content_frame, bg=BG_MAIN, bd=1, relief="solid")
        notes_frame.pack(fill="both", expand=True, pady=(0, 15))
        notes_frame.columnconfigure(0, weight=1)
        notes_frame.rowconfigure(0, weight=1)

        notes_text = tk.Text(notes_frame, bg=BG_MAIN, fg=TEXT_MUTED, 
                             insertbackground=TEXT_LIGHT, font=("Consolas", 8), 
                             bd=0, wrap="word", highlightthickness=0)
        notes_text.insert("1.0", f"Release Notes:\n{release_notes}")
        notes_text.config(state="disabled")
        notes_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        scroll_y = ttk.Scrollbar(notes_frame, orient="vertical", command=notes_text.yview)
        
        def scroll_set(first, last):
            first, last = float(first), float(last)
            if first <= 0.0 and last >= 1.0:
                scroll_y.grid_forget()
            else:
                scroll_y.grid(row=0, column=1, sticky="ns")
            scroll_y.set(first, last)
            
        notes_text.config(yscrollcommand=scroll_set)
        
        def start_update():
            popup.destroy()
            self.execute_self_update(latest_version, download_filename, download_url)
            
        def skip_version():
            popup.destroy()
            self.skipped_version = latest_version
            self.save_settings()
            
        def remind_later():
            popup.destroy()
            
        btn_update = tk.Label(btn_frame, text="Update Now", bg=BG_MAIN, fg=ACCENT_GREEN,
                              font=("Segoe UI", 9, "bold"), bd=1, relief="solid", padx=10, pady=5, cursor="hand2")
        btn_update.pack(side="left", expand=True, fill="x", padx=3)
        btn_update.bind("<Button-1>", lambda e: start_update())
        btn_update.bind("<Enter>", lambda e: btn_update.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        btn_update.bind("<Leave>", lambda e: btn_update.config(bg=BG_MAIN, fg=ACCENT_GREEN))
        
        btn_skip = tk.Label(btn_frame, text="Skip Version", bg=BG_MAIN, fg=ACCENT_RED,
                            font=("Segoe UI", 9, "bold"), bd=1, relief="solid", padx=10, pady=5, cursor="hand2")
        btn_skip.pack(side="left", expand=True, fill="x", padx=3)
        btn_skip.bind("<Button-1>", lambda e: skip_version())
        btn_skip.bind("<Enter>", lambda e: btn_skip.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        btn_skip.bind("<Leave>", lambda e: btn_skip.config(bg=BG_MAIN, fg=ACCENT_RED))
        
        btn_cancel = tk.Label(btn_frame, text="Later", bg=BG_MAIN, fg=TEXT_MUTED,
                              font=("Segoe UI", 9, "bold"), bd=1, relief="solid", padx=10, pady=5, cursor="hand2")
        btn_cancel.pack(side="left", expand=True, fill="x", padx=3)
        btn_cancel.bind("<Button-1>", lambda e: remind_later())
        btn_cancel.bind("<Enter>", lambda e: btn_cancel.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        btn_cancel.bind("<Leave>", lambda e: btn_cancel.config(bg=BG_MAIN, fg=TEXT_MUTED))

        def on_popup_destroy(event):
            if event.widget == popup:
                self.update_window = None
                self.update_topmost_state()

        popup.bind("<Destroy>", on_popup_destroy)

    def open_suggestions_dialog(self):
        if hasattr(self, 'suggestions_window') and self.suggestions_window and self.suggestions_window.winfo_exists():
            self.suggestions_window.deiconify()
            self.suggestions_window.lift()
            self.suggestions_window.attributes("-topmost", True)
            self.suggestions_window.focus_force()
            return

        popup = tk.Toplevel(self.win)
        self.suggestions_window = popup
        popup.transient(self.win)

        popup.title("Submit Feedback & Suggestions")
        popup.configure(bg=BG_CARD, highlightbackground=ACCENT_CYAN, highlightcolor=ACCENT_CYAN, highlightthickness=1)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        
        # Center relative to active overlay window
        w = 380
        h = 370
        x = self.win.winfo_x() + (self.win.winfo_width() - w) // 2
        y = self.win.winfo_y() + (self.win.winfo_height() - h) // 2
        
        popup.geometry(f"{w}x{h}+{x}+{y}")
        
        title_bar = tk.Frame(popup, bg=BG_HEADER, height=30)
        title_bar.pack(fill="x", side="top")
        
        title_lbl = tk.Label(title_bar, text="SUBMIT FEEDBACK & SUGGESTIONS", bg=BG_HEADER, fg=ACCENT_CYAN,
                             font=("Consolas", 9, "bold"))
        title_lbl.pack(side="left", padx=10, pady=5)

        self.make_popup_draggable(popup, title_bar, title_lbl)

        btn_close = tk.Label(title_bar, text="✕", bg=BG_HEADER, fg=TEXT_MUTED, width=3, font=("Segoe UI", 11, "bold"), cursor="hand2")
        btn_close.pack(side="right", fill="y")
        btn_close.bind("<Button-1>", lambda e: popup.destroy())
        btn_close.bind("<Enter>", lambda e: btn_close.config(bg=ACCENT_RED, fg=TEXT_LIGHT))
        btn_close.bind("<Leave>", lambda e: btn_close.config(bg=BG_HEADER, fg=TEXT_MUTED))

        content_frame = tk.Frame(popup, bg=BG_CARD, padx=15, pady=10)
        content_frame.pack(fill="both", expand=True)
        

        lbl_warning = tk.Label(content_frame, text="Warning: Inappropriate feedback/suggestions or spam can result in a permanent or temporary IP ban.",
                               bg=BG_CARD, fg=ACCENT_GOLD, font=("Segoe UI", 8, "bold"), justify="left", wraplength=340)
        lbl_warning.pack(anchor="w", pady=(0, 10))
        

        name_frame = tk.Frame(content_frame, bg=BG_CARD)
        name_frame.pack(fill="x", pady=(0, 5))
        
        lbl_name = tk.Label(name_frame, text="Your Name:", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_name.pack(side="left")
        
        ent_name = tk.Entry(name_frame, bg=BG_MAIN, fg=TEXT_LIGHT, insertbackground=TEXT_LIGHT, 
                            disabledbackground=BG_HEADER, disabledforeground=TEXT_MUTED,
                            font=("Segoe UI", 9), bd=1, relief="solid", width=25)
        ent_name.pack(side="left", padx=(10, 0))
        ent_name.bind("<Button-1>", lambda e: ent_name.focus_force())

        popup.bind("<Button-1>", lambda e: popup.focus_force() if not isinstance(e.widget, (tk.Entry, tk.Text)) else None)
        content_frame.bind("<Button-1>", lambda e: popup.focus_force() if not isinstance(e.widget, (tk.Entry, tk.Text)) else None)
        

        var_anonymous = tk.BooleanVar(value=True)
        
        def toggle_anonymous():
            if var_anonymous.get():
                ent_name.delete(0, tk.END)
                ent_name.config(state="disabled")
            else:
                ent_name.config(state="normal")
                
        chk_anon = tk.Checkbutton(content_frame, text="Submit Anonymously", variable=var_anonymous,
                                  onvalue=True, offvalue=False, command=toggle_anonymous,
                                  bg=BG_CARD, fg=TEXT_LIGHT, selectcolor=BG_MAIN, activebackground=BG_CARD,
                                  activeforeground=TEXT_LIGHT, font=("Segoe UI", 9), bd=0, highlightthickness=0)
        chk_anon.pack(anchor="w", pady=(0, 10))
        

        ent_name.config(state="disabled")
        

        lbl_body = tk.Label(content_frame, text="Feedback / Suggestion details:", bg=BG_CARD, fg=TEXT_LIGHT, font=("Segoe UI", 9))
        lbl_body.pack(anchor="w", pady=(0, 3))
        

        txt_body = tk.Text(content_frame, bg=BG_MAIN, fg=TEXT_LIGHT, insertbackground=TEXT_LIGHT,
                           font=("Segoe UI", 9), bd=1, relief="solid", height=6, wrap="word")
        txt_body.pack(fill="both", expand=True, pady=(0, 10))
        txt_body.bind("<Button-1>", lambda e: txt_body.focus_force())
        

        lbl_status = tk.Label(content_frame, text="", bg=BG_CARD, fg=ACCENT_CYAN, font=("Segoe UI", 9, "bold"), wraplength=340, justify="center")
        lbl_status.pack(pady=(0, 5))
        

        btn_frame = tk.Frame(content_frame, bg=BG_CARD)
        btn_frame.pack(fill="x", side="bottom")
        
        submit_in_progress = False

        def perform_submit():
            nonlocal submit_in_progress
            if submit_in_progress:
                return
            sug_text = txt_body.get("1.0", tk.END).strip()
            if not sug_text:
                lbl_status.config(text="Error: Feedback details cannot be empty.", fg=ACCENT_RED)
                return
            
            name_val = ent_name.get().strip() if not var_anonymous.get() else ""
            is_anon = var_anonymous.get()
            
            lbl_status.config(text="Sending feedback...", fg=ACCENT_CYAN)
            submit_in_progress = True
            
            # Start background thread to submit
            def run_submit():
                nonlocal submit_in_progress
                import json
                
                payload = {
                    "name": name_val,
                    "suggestion": sug_text,
                    "anonymous": is_anon,
                    "target": "overlay",
                    "is_server_checker": False
                }
                
                try:
                    data_bytes = json.dumps(payload).encode('utf-8')
                    req = urllib.request.Request(
                        f"{BACKEND_SERVER_URL}/suggestions",
                        data=data_bytes,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "RBWR-Overlay-Client/1.0"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        if resp.status == 200:
                            def success_ui():
                                lbl_status.config(text="Feedback submitted successfully!", fg=ACCENT_GREEN)
                                txt_body.delete("1.0", tk.END)
                                popup.after(1500, popup.destroy)
                            self.run_on_main_thread(success_ui)
                        else:
                            def fail_ui():
                                nonlocal submit_in_progress
                                lbl_status.config(text=f"Error: Server returned status {resp.status}", fg=ACCENT_RED)
                                submit_in_progress = False
                            self.run_on_main_thread(fail_ui)
                except urllib.error.HTTPError as he:
                    # Read the error body synchronously on the background thread
                    reason = he.reason
                    try:
                        body = he.read().decode('utf-8')
                        detail = json.loads(body).get("detail", reason)
                    except Exception:
                        detail = reason
                    
                    def http_err_ui():
                        nonlocal submit_in_progress
                        lbl_status.config(text=f"Error: {detail}", fg=ACCENT_RED)
                        submit_in_progress = False
                    self.run_on_main_thread(http_err_ui)
                except Exception as ex:
                    def err_ui():
                        nonlocal submit_in_progress
                        lbl_status.config(text="Error: Connection to server failed.", fg=ACCENT_RED)
                        submit_in_progress = False
                    self.run_on_main_thread(err_ui)
                    
            threading.Thread(target=run_submit, daemon=True).start()


        btn_submit = tk.Label(btn_frame, text="Submit", bg=BG_MAIN, fg=ACCENT_GREEN,
                              font=("Segoe UI", 9, "bold"), bd=1, relief="solid", padx=15, pady=5, cursor="hand2")
        btn_submit.pack(side="right", padx=(5, 0))
        btn_submit.bind("<Button-1>", lambda e: perform_submit())
        btn_submit.bind("<Enter>", lambda e: btn_submit.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        btn_submit.bind("<Leave>", lambda e: btn_submit.config(bg=BG_MAIN, fg=ACCENT_GREEN))
        

        btn_cancel = tk.Label(btn_frame, text="Cancel", bg=BG_MAIN, fg=TEXT_MUTED,
                              font=("Segoe UI", 9, "bold"), bd=1, relief="solid", padx=15, pady=5, cursor="hand2")
        btn_cancel.pack(side="right")
        btn_cancel.bind("<Button-1>", lambda e: popup.destroy())
        btn_cancel.bind("<Enter>", lambda e: btn_cancel.config(bg=BG_HEADER, fg=TEXT_LIGHT))
        btn_cancel.bind("<Leave>", lambda e: btn_cancel.config(bg=BG_MAIN, fg=TEXT_MUTED))

        def on_popup_destroy(event):
            if event.widget == popup:
                self.suggestions_window = None
                self.update_topmost_state()

        popup.bind("<Destroy>", on_popup_destroy)
        popup.focus_force()

    def execute_self_update(self, latest_version, download_filename, download_url):
        if hasattr(self, 'loading_window') and self.loading_window and self.loading_window.winfo_exists():
            self.loading_window.lift()
            self.loading_window.attributes("-topmost", True)
            self.loading_window.focus_force()
            return

        loading = tk.Toplevel(self.win)
        self.loading_window = loading
        loading.transient(self.win)

        loading.title("Downloading Update")
        loading.configure(bg=BG_CARD, highlightbackground=ACCENT_CYAN, highlightcolor=ACCENT_CYAN, highlightthickness=1)
        loading.overrideredirect(True)
        loading.attributes("-topmost", True)
        
        # Center relative to active overlay window
        w = 300
        h = 120
        x = self.win.winfo_x() + (self.win.winfo_width() - w) // 2
        y = self.win.winfo_y() + (self.win.winfo_height() - h) // 2
        
        loading.geometry(f"{w}x{h}+{x}+{y}")
        
        lbl_status = tk.Label(loading, text="DOWNLOADING SYSTEM UPDATE...", bg=BG_CARD, fg=ACCENT_CYAN, font=("Consolas", 10, "bold"))
        lbl_status.pack(pady=(25, 5))
        
        lbl_sub = tk.Label(loading, text=f"Fetching v{latest_version}...", bg=BG_CARD, fg=TEXT_MUTED, font=("Consolas", 8))
        lbl_sub.pack(pady=(0, 15))

        self.make_popup_draggable(loading, loading, lbl_status, lbl_sub)
        
        def do_download():
            import urllib.request
            import subprocess
            import sys
            from tkinter import messagebox
            
            try:
                current_exe = sys.argv[0] if _is_compiled else sys.executable
                exe_dir = os.path.dirname(os.path.abspath(current_exe))
                new_exe_path = os.path.join(exe_dir, download_filename)
                
                url = download_url
                req = urllib.request.Request(url, headers=UPDATE_HTTP_HEADERS)
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        with open(new_exe_path, "wb") as f:
                            f.write(response.read())
                
                threading.Event().wait(1.0)
                
                def update_success_ui_and_reboot():
                    lbl_status.config(text="REBOOTING OVERLAY...", fg=ACCENT_GREEN)
                    lbl_sub.config(text="Deleting old version & starting new one...")
                    loading.update()
                    cmd_script = f'timeout /t 2 /nobreak && del "{current_exe}" && start "" "{new_exe_path}"'
                    subprocess.Popen(f'cmd.exe /c {cmd_script}', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    self.quit_app()

                self.run_on_main_thread(update_success_ui_and_reboot)
            except Exception as err:
                log.error(f"Self-update failed: {err}")
                def handle_err():
                    loading.destroy()
                    self.show_custom_message("Update Error", f"Failed to execute self-update:\n{err}", is_error=True)
                self.run_on_main_thread(handle_err)
                
        threading.Thread(target=do_download, daemon=True).start()

        def on_loading_destroy(event):
            if event.widget == loading:
                self.loading_window = None
                self.update_topmost_state()

        loading.bind("<Destroy>", on_loading_destroy)

    def on_input_update(self, source):
        if self.updating_fields:
            return
        if source == "demand":
            self._demand_changed_waiting_heartbeat = True
            try:
                self._pending_demand_value = float(self.var_demand.get())
            except (ValueError, TypeError):
                self._pending_demand_value = None
        self.update_calculations(source=source)

    def update_calculations(self, source="demand"):
        self.updating_fields = True
        try:
            if source == "demand":
                raw_val = self.var_demand.get()
                if not raw_val:
                    demand_val = 0.0
                else:
                    try:
                        demand_val = float(raw_val)
                    except ValueError:
                        demand_val = -1.0

                if demand_val < 0:
                    self.show_error_state()
                else:
                    thermal = self.calc.calc_thermal(demand_val)
                    flow = self.calc.calc_flow(thermal)
                    gen_load = self.calc.calc_gen_load(thermal)
                    
                    self.var_rtp.set(f"{thermal:.3f}")
                    if hasattr(self, 'var_usage') and self.var_usage:
                        self.var_usage.set(f"{self.calc.usage:.2f}")
                    self.render_outputs(thermal, flow, gen_load)
            
            elif source == "rtp":
                raw_val = self.var_rtp.get()
                if not raw_val:
                    thermal_val = 0.0
                else:
                    try:
                        thermal_val = float(raw_val)
                    except ValueError:
                        thermal_val = -1.0

                if thermal_val < 0 or thermal_val > 250:
                    self.show_error_state()
                else:
                    flow = self.calc.calc_flow(thermal_val)
                    gen_load = self.calc.calc_gen_load(thermal_val)
                    
                    # Update dynamic usage
                    u_calc = self.calc.usage_calc1 if self.calc.selected_unit == 1 else self.calc.usage_calc2
                    self.calc.usage = u_calc.calculate_usage(flow, thermal_val, override_speed=self.calc.recirc_override)
                    
                    demand = round(gen_load - self.calc.usage, 2)
                    if demand < 0:
                        demand = 0.0
                    
                    self.var_demand.set(f"{demand:.2f}")
                    if hasattr(self, 'var_usage') and self.var_usage:
                        self.var_usage.set(f"{self.calc.usage:.2f}")
                    
                    self.render_outputs(thermal_val, flow, gen_load)
        except Exception as e:
            self.show_error_state()
        finally:
            self.updating_fields = False

    def render_outputs(self, thermal, flow, gen_load):
        self.update_recirc_indicator_ui()
        limit = 108
        unit_suffix = "APRM" if self.calc.selected_unit == 1 else "RTP"
        if not self.is_compact:
            self.lbl_gen_val.config(text=f"{gen_load:.2f} MWe", fg=ACCENT_CYAN)
            self.lbl_feed_val.config(text=f"{flow:.2f} kg/s", fg=ACCENT_GOLD)
            self.lbl_neon_rtp.config(text=f"{thermal:.2f}% {unit_suffix}")
            
            if thermal > limit:
                self.neon_frame.config(bg="#2a0c0e", highlightbackground=ACCENT_RED, bd=1)
                self.lbl_neon_rtp.config(bg="#2a0c0e", fg=ACCENT_RED)
                self.lbl_neon_sub.config(text=f"OVERPOWER SCRAM RISK (>{limit}%)", bg="#2a0c0e", fg=ACCENT_RED)
            else:
                self.neon_frame.config(bg=WIN_BG, highlightbackground=WIN_BG, bd=0)
                self.lbl_neon_rtp.config(bg=WIN_BG, fg=ACCENT_CYAN)
                self.lbl_neon_sub.config(text="APRM REACTOR POWER STATUS", bg=WIN_BG, fg=TEXT_MUTED)
        else:
            if thermal > limit:
                self.lbl_compact_rtp.config(text=f"{thermal:.1f}% {unit_suffix}", fg=ACCENT_RED)
            else:
                self.lbl_compact_rtp.config(text=f"{thermal:.1f}% {unit_suffix}", fg=ACCENT_CYAN)
            self.lbl_compact_flow.config(text=f"[{int(flow)} kg/s]", fg=TEXT_MUTED)

    def show_error_state(self):
        self.update_recirc_indicator_ui()
        if not self.is_compact:
            self.lbl_gen_val.config(text="ERROR", fg=ACCENT_RED)
            self.lbl_feed_val.config(text="ERROR", fg=ACCENT_RED)
            self.lbl_neon_rtp.config(text="ERR", fg=ACCENT_RED)
            self.neon_frame.config(bg=WIN_BG, bd=0)
            self.lbl_neon_rtp.config(bg=WIN_BG)
            self.lbl_neon_sub.config(text="VALUE OUT OF RANGE", bg=WIN_BG, fg=ACCENT_RED)
        else:
            self.lbl_compact_rtp.config(text="ERR", fg=ACCENT_RED)
            self.lbl_compact_flow.config(text="[---]", fg=TEXT_MUTED)

    def update_recirc_indicator_ui(self):
        override_active = self.calc.recirc_override is not None
        
        if hasattr(self, 'lbl_recirc_indicator') and self.lbl_recirc_indicator and self.lbl_recirc_indicator.winfo_exists():
            if override_active:
                val = self.calc.recirc_override
                self.lbl_recirc_indicator.config(text=f"OVR: {val:.0f}%")
                self.lbl_recirc_indicator.pack(side="right", padx=5, pady=(2, 4))
            else:
                self.lbl_recirc_indicator.pack_forget()
                
        if hasattr(self, 'lbl_arrow_ref') and self.lbl_arrow_ref and self.lbl_arrow_ref.winfo_exists():
            if override_active:
                self.lbl_arrow_ref.config(text="🔄", fg=ACCENT_GOLD, cursor="hand2")
                self.lbl_arrow_ref.bind("<Button-1>", lambda e: self.reset_recirc_override())
            else:
                self.lbl_arrow_ref.config(text="➔", fg=ACCENT_CYAN, cursor="")
                self.lbl_arrow_ref.bind("<Button-1>", self.start_drag)


if __name__ == "__main__":
    root = tk.Tk()
    if IS_LINUX:
        root.geometry("1x1+0+0")
        try:
            root.attributes('-alpha', 0)
        except Exception:
            pass
    elif IS_MAC:
        root.geometry("1x1+0+0")
    else:
        root.withdraw()
    app = OverlayApp(root)
    root.mainloop()