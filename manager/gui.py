import os
import sys
import json
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from config import (
    MANAGER_HOST, MANAGER_PORT, STORAGE_NODES, AES_KEY_HEX, STATE_FILE,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
STORAGE_DIR = os.path.join(PROJECT_ROOT, "storage")
CLIENT_EXE = os.path.join(PROJECT_ROOT, "client", "client.exe")

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ---------------------------------------------------------------------------
# aes decrypt (for download path)
# ---------------------------------------------------------------------------
def aes_decrypt(payload: bytes) -> bytes:
    key = bytes.fromhex(AES_KEY_HEX)
    iv, ciphertext = payload[:16], payload[16:]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


# ---------------------------------------------------------------------------
# tcp helper
# ---------------------------------------------------------------------------
def tcp_request(header_dict: dict, payload: bytes = b""):
    header_json = json.dumps(header_dict)
    packet = header_json.encode("utf-8") + b"\n\n" + payload

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect((MANAGER_HOST, MANAGER_PORT))
    sock.sendall(packet)

    buf = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf.extend(chunk)
        if b"\n\n" in buf:
            sep = buf.index(b"\n\n")
            resp_header = json.loads(buf[:sep].decode("utf-8"))
            data_after = bytearray(buf[sep + 2:])
            p_size = int(resp_header.get("payloadSize", 0))
            while len(data_after) < p_size:
                more = sock.recv(65536)
                if not more:
                    break
                data_after.extend(more)
            sock.close()
            return resp_header, bytes(data_after[:p_size])
        if buf.endswith(b"\n"):
            sock.close()
            return json.loads(buf.decode("utf-8").strip()), b""

    sock.close()
    if buf:
        return json.loads(buf.decode("utf-8").strip()), b""
    return {"status": "error", "reason": "empty response"}, b""


# ---------------------------------------------------------------------------
# service manager
# ---------------------------------------------------------------------------
class ServiceManager:
    def __init__(self, log_cb=None):
        self._procs: list = []
        self._log = log_cb or print

    def _compile_java(self):
        class_file = os.path.join(STORAGE_DIR, "out", "StorageDaemon.class")
        if os.path.exists(class_file):
            return True
        self._log("compiling java storage daemons...")
        src = [os.path.join(STORAGE_DIR, "src", f) for f in
               ("StorageDaemon.java", "ConnectionHandler.java",
                "PacketParser.java", "CryptoUtil.java", "PathSanitizer.java")]
        out = os.path.join(STORAGE_DIR, "out")
        os.makedirs(out, exist_ok=True)
        r = subprocess.run(["javac", "-d", out] + src, capture_output=True, text=True)
        if r.returncode != 0:
            self._log(f"java compile failed: {r.stderr}")
            return False
        self._log("java compiled")
        return True

    def start_all(self):
        if not self._compile_java():
            return False
        cp = os.path.join(STORAGE_DIR, "out")
        for _, port in STORAGE_NODES:
            p = subprocess.Popen(
                ["java", "-cp", cp, "StorageDaemon", str(port)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW)
            self._procs.append(p)
            self._log(f"java node :{port} started (pid {p.pid})")
        time.sleep(1)
        p = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, "server.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW)
        self._procs.append(p)
        self._log(f"manager :9000 started (pid {p.pid})")
        time.sleep(0.5)
        return True

    def stop_all(self):
        for p in self._procs:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        self._procs.clear()

    def is_running(self):
        return any(p.poll() is None for p in self._procs)


# ---------------------------------------------------------------------------
# app (composition -- does not subclass the root)
# ---------------------------------------------------------------------------
class App:
    def __init__(self):
        self._dnd_available = False
        try:
            from tkinterdnd2 import TkinterDnD
            self.root = TkinterDnD.Tk()
            self._dnd_available = True
        except Exception:
            self.root = tk.Tk()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root.title("Distributed File Sharing System")
        self.root.geometry("900x620")
        self.root.minsize(800, 550)
        self.root.configure(bg="#1a1a2e")

        self.services = ServiceManager(log_cb=self._svc_log)
        self._build_ui()
        self._start_services()
        self._tick_monitor()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def run(self):
        self.root.mainloop()

    # ---- ui ---------------------------------------------------------------

    def _build_ui(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(self.root, anchor="nw")
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self._build_upload_tab(self.tabs.add("Upload"))
        self._build_download_tab(self.tabs.add("Download"))
        self._build_monitor_tab(self.tabs.add("Monitor"))

        self.status_bar = ctk.CTkLabel(self.root, text="Starting services...", anchor="w")
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 6))

    # -- upload --

    def _build_upload_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="Upload a File",
                     font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, pady=(10, 2), sticky="w")

        ctk.CTkLabel(tab, text="Browse for a file or drag & drop onto the zone below.").grid(
            row=1, column=0, sticky="w")

        self.browse_btn = ctk.CTkButton(tab, text="Browse File...",
                                        command=self._browse_upload)
        self.browse_btn.grid(row=2, column=0, pady=10, sticky="w")

        self.drop_frame = ctk.CTkFrame(tab, height=140, border_width=2)
        self.drop_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        tab.grid_rowconfigure(3, weight=1)

        self.drop_label = ctk.CTkLabel(self.drop_frame,
                                       text="Drag & Drop Files Here",
                                       font=ctk.CTkFont(size=14))
        self.drop_label.place(relx=0.5, rely=0.5, anchor="center")

        self._setup_dnd()

        self.upload_log = ctk.CTkTextbox(tab, height=120, state="disabled")
        self.upload_log.grid(row=4, column=0, sticky="ew", pady=(0, 4))

    def _setup_dnd(self):
        if not self._dnd_available:
            self.drop_label.configure(
                text="Drag & Drop not available — use Browse button")
            return
        try:
            from tkinterdnd2 import DND_FILES
            # register on the underlying tk widget id
            wid = self.drop_frame.winfo_id()
            tk_path = str(self.drop_frame)
            self.root.tk.call("tkdnd::drop_target", "register", tk_path, ("DND_Files",))

            def _on_drop(event):
                self._handle_drop(event.data)
                return event.action

            self.drop_frame.bind("<<Drop>>", _on_drop)
            self.drop_label.bind("<<Drop>>", _on_drop)
        except Exception as e:
            self.drop_label.configure(text=f"DnD init error — use Browse button")

    def _handle_drop(self, raw):
        raw = raw.strip()
        if raw.startswith("{"):
            paths = [raw.strip("{}")]
        else:
            paths = raw.split()
        for p in paths:
            p = p.strip().strip('"')
            if os.path.isfile(p):
                self._do_upload(p)
                return
        self._log_upload("dropped item is not a valid file")

    def _browse_upload(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Select a file to upload")
        if path:
            self._do_upload(path)

    def _do_upload(self, filepath):
        basename = os.path.basename(filepath)
        self._log_upload(f"uploading: {basename} ...")
        self.browse_btn.configure(state="disabled")

        def task():
            try:
                result = subprocess.run(
                    [CLIENT_EXE, filepath],
                    capture_output=True, text=True, timeout=60,
                    creationflags=CREATE_NO_WINDOW)
                output = (result.stdout + result.stderr).strip()
                for line in reversed(output.splitlines()):
                    if "server response:" in line.lower():
                        resp_text = line.split(":", 1)[1].strip()
                        self.root.after(0, self._log_upload,
                                        f"success: {resp_text}")
                        self.root.after(500, self._refresh_file_list)
                        self.root.after(500, self._tick_monitor)
                        break
                else:
                    self.root.after(0, self._log_upload,
                                    f"client: {output[-300:]}")
            except Exception as e:
                self.root.after(0, self._log_upload, f"error: {e}")
            finally:
                self.root.after(0,
                                lambda: self.browse_btn.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def _log_upload(self, msg):
        self.upload_log.configure(state="normal")
        self.upload_log.insert("end",
                               f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.upload_log.see("end")
        self.upload_log.configure(state="disabled")

    # -- download --

    def _build_download_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="Download Files",
                     font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, pady=(10, 2), sticky="w")

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="w", pady=(0, 6))

        self.refresh_btn = ctk.CTkButton(btn_row, text="Refresh List",
                                         width=120,
                                         command=self._refresh_file_list)
        self.refresh_btn.pack(side="left", padx=(0, 8))

        self.dl_btn = ctk.CTkButton(btn_row, text="Download Selected",
                                    width=150,
                                    command=self._download_selected)
        self.dl_btn.pack(side="left")

        self.file_list_frame = ctk.CTkScrollableFrame(
            tab, label_text="Available Files")
        self.file_list_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 6))
        tab.grid_rowconfigure(2, weight=1)
        self.file_list_frame.grid_columnconfigure(1, weight=1)

        self._file_entries = []
        self._radio_var = tk.StringVar(value="")

        self.dl_status = ctk.CTkLabel(tab, text="", anchor="w")
        self.dl_status.grid(row=3, column=0, sticky="w", pady=(0, 4))

    def _refresh_file_list(self):
        def task():
            try:
                resp, _ = tcp_request({"type": "list", "payloadSize": 0})
                files = resp.get("files", [])
                self.root.after(0, self._populate_files, files)
            except Exception as e:
                self.root.after(0, lambda: self.dl_status.configure(
                    text=f"error: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def _populate_files(self, files):
        for w in self.file_list_frame.winfo_children():
            w.destroy()
        self._file_entries = files
        self._radio_var.set("")

        if not files:
            ctk.CTkLabel(self.file_list_frame,
                         text="No files on server yet.").grid(
                row=0, column=0, columnspan=3, pady=10)
            self.dl_status.configure(text="")
            return

        for i, f in enumerate(files):
            val = f"{f['id']}||{f['filename']}"
            rb = ctk.CTkRadioButton(
                self.file_list_frame, text="",
                variable=self._radio_var, value=val, width=20)
            rb.grid(row=i, column=0, padx=(4, 6), pady=2)

            ctk.CTkLabel(self.file_list_frame, text=f["filename"],
                         anchor="w").grid(row=i, column=1, sticky="w")

            ctk.CTkLabel(self.file_list_frame, text=f["timestamp"],
                         text_color="gray", anchor="e").grid(
                row=i, column=2, padx=(10, 4))

        self.dl_status.configure(text=f"{len(files)} file(s) available")

    def _download_selected(self):
        sel = self._radio_var.get()
        if not sel:
            self.dl_status.configure(text="select a file first")
            return
        file_id, filename = sel.split("||", 1)

        save_path = filedialog.asksaveasfilename(
            parent=self.root, title="Save file as...",
            initialfile=filename)
        if not save_path:
            return

        self.dl_status.configure(text=f"downloading {filename}...")
        self.dl_btn.configure(state="disabled")

        def task():
            try:
                resp, payload = tcp_request({
                    "type": "download", "filename": filename,
                    "id": file_id, "payloadSize": 0})
                if resp.get("status") != "ok":
                    reason = resp.get("reason", "download failed")
                    self.root.after(0, lambda: self.dl_status.configure(
                        text=f"error: {reason}"))
                    return
                plaintext = aes_decrypt(payload)
                with open(save_path, "wb") as fh:
                    fh.write(plaintext)
                size = len(plaintext)
                name = os.path.basename(save_path)
                self.root.after(0, lambda: self.dl_status.configure(
                    text=f"saved: {name} ({size} bytes)"))
            except Exception as e:
                self.root.after(0, lambda: self.dl_status.configure(
                    text=f"download error: {e}"))
            finally:
                self.root.after(0,
                                lambda: self.dl_btn.configure(state="normal"))
        threading.Thread(target=task, daemon=True).start()

    # -- monitor --

    def _build_monitor_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="System Monitor",
                     font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, pady=(10, 6), sticky="w")

        self.metrics = ctk.CTkFrame(tab)
        self.metrics.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.metrics.grid_columnconfigure((0, 1, 2), weight=1)

        self.lbl_mode = ctk.CTkLabel(self.metrics, text="Mode: --",
                                     font=ctk.CTkFont(size=13))
        self.lbl_mode.grid(row=0, column=0, padx=10, pady=8)

        self.lbl_uploads = ctk.CTkLabel(self.metrics, text="Uploads: --",
                                        font=ctk.CTkFont(size=13))
        self.lbl_uploads.grid(row=0, column=1, padx=10, pady=8)

        self.lbl_nodes = ctk.CTkLabel(self.metrics, text="Nodes: --",
                                      font=ctk.CTkFont(size=13))
        self.lbl_nodes.grid(row=0, column=2, padx=10, pady=8)

        self.health_frame = ctk.CTkFrame(tab)
        self.health_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.health_frame.grid_columnconfigure(
            tuple(range(len(STORAGE_NODES))), weight=1)

        self.health_labels = {}
        for i, (_, port) in enumerate(STORAGE_NODES):
            lbl = ctk.CTkLabel(self.health_frame,
                               text=f"Node :{port}\n-- unknown",
                               font=ctk.CTkFont(size=12))
            lbl.grid(row=0, column=i, padx=10, pady=8)
            self.health_labels[port] = lbl

        ctk.CTkLabel(tab, text="Replication Log",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=3, column=0, sticky="w")

        self.mon_log = ctk.CTkTextbox(tab, state="disabled")
        self.mon_log.grid(row=4, column=0, sticky="nsew", pady=(4, 4))
        tab.grid_rowconfigure(4, weight=1)

    def _tick_monitor(self):
        try:
            path = os.path.join(SCRIPT_DIR, STATE_FILE)
            if os.path.exists(path):
                with open(path, "r") as f:
                    state = json.load(f)
                self._render_monitor(state)
        except Exception:
            pass
        self.root.after(3000, self._tick_monitor)

    def _render_monitor(self, state):
        from config import CONSISTENCY_MODE
        health = state.get("node_health", {})
        meta = state.get("metadata", {})
        log_entries = state.get("replication_log", [])

        up = sum(1 for v in health.values() if v == "up")
        self.lbl_mode.configure(text=f"Mode: {CONSISTENCY_MODE.upper()}")
        self.lbl_uploads.configure(text=f"Uploads: {len(meta)}")
        self.lbl_nodes.configure(text=f"Nodes: {up}/{len(STORAGE_NODES)}")

        icons = {"up": "UP", "down": "DOWN"}
        for _, port in STORAGE_NODES:
            s = health.get(str(port), "unknown")
            self.health_labels[port].configure(
                text=f"Node :{port}\n{icons.get(s, '--')} {s}")

        self.mon_log.configure(state="normal")
        self.mon_log.delete("1.0", "end")
        for e in reversed(log_entries[-30:]):
            self.mon_log.insert(
                "end",
                f"[{e.get('time','?')}] {e.get('filename','?')} -> "
                f"node:{e.get('node','?')} = {e.get('status','?')}\n")
        self.mon_log.configure(state="disabled")

    # -- services -----------------------------------------------------------

    def _svc_log(self, msg):
        try:
            self.root.after(0, lambda: self.status_bar.configure(text=msg))
        except Exception:
            pass

    def _start_services(self):
        def task():
            ok = self.services.start_all()
            msg = "All services running" if ok else "Service startup failed"
            self.root.after(0, lambda: self.status_bar.configure(text=msg))
            if ok:
                time.sleep(1)
                self.root.after(0, self._refresh_file_list)
        threading.Thread(target=task, daemon=True).start()

    def _on_close(self):
        self.services.stop_all()
        self.root.destroy()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.run()
