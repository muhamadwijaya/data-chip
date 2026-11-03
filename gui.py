from __future__ import annotations

import os
import queue
import re
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__
from .analysis import DEFAULT_DUMP_DIR, analyze, format_info, load_dump_dir
from .card import MAX_COUNTER, Card, load_card
from .clone import (
    CloneResult,
    CloneSpec,
    derive_uid,
    format_results,
    write_clone_result,
    write_recommended,
)
from .paths import resolve_existing
from .proxmark import ProxmarkClient, find_port, list_serial_ports
from .selftest import run_selftest


HELP_TEXT = r"""GTInk - panduan singkat
========================

APLIKASI INI
  Membaca, menganalisis, mengedit, dan mengkloning chip kartrid EAJet/GT1000.
  Chip yang dipakai adalah MIFARE Classic 1K (64 blok x 16 byte = 1024 byte).

TEMUAN DATA
  - Ada 4 dump: 1EB75C2C, 5EEFAB9B, BE8AAA9B, FE7EA17E.
  - Tiap kartu menyimpan dua record: blok 4..32 dan 33..61.
  - Tiap record berisi 12 blok payload (192 byte) + 10 blok tail (160 byte).
  - Payload record 1 dan 2 selalu sama; tail juga sama.
  - Counter ada di blok 29 dan 58, offset 10, 16-bit little-endian.
  - Chip penuh: counter 64016..64606, fill tail FF.
  - Chip low-ink: counter 12107, fill tail 00.
  - Nominal penuh yang paling mungkin: 65000 (0xFDE8). Maksimum: 65535.
  - Tidak ditemukan checksum/signature yang menghubungkan counter ke payload.

URUTAN UJI YANG DISARANKAN
  1. Tulis clone EXACT (kontrol) ke kartu magic, pasang ke printer.
     Jika printer menolak exact, masalahnya bukan counter.
  2. Tulis clone counter 65000.
  3. Jika ditolak, coba 65535.
  4. Jika UID sumber ditolak, coba clone dengan UID baru.
  5. Coba sumber 5EEFAB9B atau FE7EA17E dengan counter 65000.
  6. Untuk chip low-ink, coba keep00 lalu fillFF.

PERINTAH CLI
  py gtink.py info --detail
  py gtink.py analyze
  py gtink.py clone --recommended --out clones
  py gtink.py write --file clones\1EB75C2C_full_65000.bin --backend gen1a --port COM11 --yes
  py gtink.py read --out readback.bin --port COM11
  py gtink.py selftest

PROXMARK3
  - Client yang dipakai: C:\ProxSpace\pm3\proxmark3\client\proxmark3.exe
  - Folder C:\ProxSpace\msys2\mingw64\bin harus ada di PATH agar client
    tidak keluar diam-diam. Aplikasi menambahkannya otomatis.
  - Gen1a  : hf mf cload -f file.bin --1k
  - Gen2  : hf mf wrbl --blk N -k FFFFFFFFFFFF -d <32 hex> (64 perintah)
  - Gen4  : hf mf gload -f file.bin --1k
  - Script siap pakai ada di folder clones/scripts.
  - Jalur printer sebenarnya ISO14443-4 (FM1208/FMCOS), bukan MIFARE.
    Replay emulator: py gtink.py replay --set C
    Build/flash: py proxmark_patch\build_flash.py --set C --flash
    Set C sudah diuji dan diterima printer ("Cek berhasil / printer siap").

PERINGATAN
  - Menulis kartu akan menimpa seluruh isi, termasuk blok 0/UID.
  - Hanya gunakan pada kartu dan printer milik sendiri.
  - Cadangkan dump asli sebelum menulis.
  - Kartu magic Gen1a/Gen2/Gen4 bisa terdeteksi sebagai kartu palsu oleh
    printer; hasil clone tidak dijamin diterima.
  - Menulis blok 0 dengan data yang salah dapat membuat kartu tidak terbaca.

MEMBACA PESAN PRINTER
  - "Chip is invalid" / "Chip mismatch" / "Cartridge authentication error":
    printer menolak kartu. Jika exact clone juga ditolak, penyebabnya bukan
    counter; kemungkinan deteksi kartu magic, UID binding, atau signature.
  - "Ink Box Check-01..05": pemeriksaan isi/counter gagal.
  - Jika printer menerima exact tetapi menolak 65000, coba 65535 atau nilai
    asli dari dump lain; kemungkinan ada batas nominal/rollback.
"""


class GtInkApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"GTInk {__version__} - EAJet/GT1000 Chip Tool")
        self.geometry("1180x820")
        self.minsize(980, 680)
        self.cards: list[Card] = []
        self.card_labels: dict[str, Card] = {}
        self.card_by_uid: dict[str, Card] = {}
        self.clone_results: list[CloneResult] = []
        self.busy = False
        self._buttons: list[ttk.Button] = []

        self._configure_style()
        self._build_menu()
        self._build_ui()
        self.after(150, self._load_dumps)

    # ------------------------------------------------------------------
    # Utilitas UI
    # ------------------------------------------------------------------
    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        style.configure("Danger.TLabel", foreground="#a00000")
        style.configure("Ok.TLabel", foreground="#006000")

    def _button(self, parent: tk.Misc, text: str, command: Callable[[], None]) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command)
        self._buttons.append(button)
        return button

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        self.busy = busy
        for button in self._buttons:
            try:
                button.configure(state="disabled" if busy else "normal")
            except tk.TclError:
                pass
        if status:
            self.status_var.set(status)
        self.update_idletasks()

    def _current_log(self) -> ScrolledText:
        try:
            index = self.notebook.index(self.notebook.select())
        except tk.TclError:
            index = 0
        if index == 0:
            return self.info_text
        if index == 1:
            return self.clone_log
        return self.write_log

    def _log(self, widget: ScrolledText, text: str) -> None:
        widget.configure(state="normal")
        widget.insert("end", text.rstrip() + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _clear(self, widget: ScrolledText) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _set_text(self, widget: ScrolledText, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _run_task(
        self,
        description: str,
        func: Callable[[], Any],
        on_done: Callable[[Any], None] | None = None,
    ) -> None:
        if self.busy:
            messagebox.showinfo("Sibuk", "Tunggu operasi sebelumnya selesai.")
            return
        log = self._current_log()
        self._log(log, f"\n=== {description} ===")
        self._set_busy(True, description)
        result_queue: queue.Queue[tuple[str, Any, str]] = queue.Queue()

        def worker() -> None:
            try:
                value = func()
            except Exception as exc:  # sengaja ditangkap untuk ditampilkan di UI
                result_queue.put(("error", exc, traceback.format_exc()))
            else:
                result_queue.put(("ok", value, ""))

        threading.Thread(target=worker, daemon=True).start()

        def poll() -> None:
            try:
                kind, payload, details = result_queue.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            if kind == "error":
                self._set_busy(False, "Gagal")
                self._log(log, f"ERROR: {payload}")
                if details:
                    self._log(log, details)
                messagebox.showerror("Operasi gagal", str(payload))
                return
            self._set_busy(False, "Selesai")
            if on_done is not None:
                on_done(payload)
            else:
                self._log(log, "Selesai.")

        self.after(100, poll)

    # ------------------------------------------------------------------
    # Menu dan tata letak
    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Muat ulang dump", command=self._load_dumps)
        file_menu.add_command(
            label="Buka folder clone",
            command=lambda: self._open_folder(self.out_dir_var.get()),
        )
        file_menu.add_separator()
        file_menu.add_command(label="Keluar", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Selftest offline", command=self._run_selftest)
        tools_menu.add_command(label="Deteksi port serial", command=self._detect_ports)
        menubar.add_cascade(label="Alat", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Panduan", command=lambda: self._show_help())
        help_menu.add_command(label="Tentang", command=self._about)
        menubar.add_cascade(label="Bantuan", menu=help_menu)
        self.config(menu=menubar)

    def _build_ui(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self._build_dump_tab()
        self._build_clone_tab()
        self._build_write_tab()
        self._build_help_tab()

        self.status_var = tk.StringVar(value="Siap")
        status = ttk.Label(
            self,
            textvariable=self.status_var,
            relief="sunken",
            anchor="w",
            padding=(6, 2),
        )
        status.pack(fill="x", side="bottom")

    def _build_dump_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="Dump && Analisis")

        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Label(top, text="Folder dump:").pack(side="left")
        self.dump_dir_var = tk.StringVar(value=str(DEFAULT_DUMP_DIR))
        entry = ttk.Entry(top, textvariable=self.dump_dir_var)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        self._button(top, "Pilih...", self._browse_dump_dir).pack(side="left")
        self._button(top, "Muat", self._load_dumps).pack(side="left", padx=(6, 0))

        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill="both", expand=True, pady=8)
        columns = ("uid", "c1", "c2", "hex", "fill", "payload", "tail", "file")
        headings = {
            "uid": "UID",
            "c1": "Counter R1",
            "c2": "Counter R2",
            "hex": "Hex",
            "fill": "Fill",
            "payload": "Payload",
            "tail": "Tail",
            "file": "Sumber",
        }
        widths = {
            "uid": 90,
            "c1": 90,
            "c2": 90,
            "hex": 80,
            "fill": 55,
            "payload": 65,
            "tail": 55,
            "file": 260,
        }
        self.dump_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=8
        )
        for column in columns:
            self.dump_tree.heading(column, text=headings[column])
            self.dump_tree.column(column, width=widths[column], anchor="center")
        ysb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.dump_tree.yview)
        xsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.dump_tree.xview)
        self.dump_tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.dump_tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.dump_tree.bind("<<TreeviewSelect>>", self._on_dump_select)

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=(0, 6))
        self._button(actions, "Info Detail", self._show_detail).pack(side="left")
        self._button(actions, "Analisis Lengkap", self._show_analysis).pack(
            side="left", padx=6
        )
        self._button(actions, "Simpan Laporan", self._save_report).pack(side="left")
        ttk.Label(
            actions,
            text="Klik baris untuk melihat rincian.",
            style="Hint.TLabel",
        ).pack(side="right")

        self.info_text = ScrolledText(tab, height=18, wrap="word", font=("Consolas", 9))
        self.info_text.pack(fill="both", expand=True)
        self.info_text.configure(state="disabled")

    def _build_clone_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="Buat Clone")

        form = ttk.LabelFrame(tab, text="Parameter clone", padding=8)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(form, text="Sumber dump:").grid(row=row, column=0, sticky="w", pady=3)
        self.source_combo = ttk.Combobox(form, state="readonly")
        self.source_combo.grid(row=row, column=1, sticky="ew", padx=6, pady=3)

        row += 1
        ttk.Label(form, text="Counter:").grid(row=row, column=0, sticky="w", pady=3)
        counter_frame = ttk.Frame(form)
        counter_frame.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        self.counter_var = tk.StringVar(value=str(65000))
        ttk.Entry(counter_frame, textvariable=self.counter_var, width=12).pack(
            side="left"
        )
        ttk.Label(
            counter_frame,
            text=f"0..{MAX_COUNTER}; 65000 = nominal penuh, 65535 = maksimum",
            style="Hint.TLabel",
        ).pack(side="left", padx=8)

        row += 1
        ttk.Label(form, text="Fill tail:").grid(row=row, column=0, sticky="w", pady=3)
        self.fill_var = tk.StringVar(value="asli (dari sumber)")
        fill_combo = ttk.Combobox(
            form,
            textvariable=self.fill_var,
            state="readonly",
            values=(
                "asli (dari sumber)",
                "00 (chip low-ink)",
                "FF (chip penuh)",
            ),
        )
        fill_combo.grid(row=row, column=1, sticky="w", padx=6, pady=3)

        row += 1
        ttk.Label(form, text="UID baru:").grid(row=row, column=0, sticky="w", pady=3)
        uid_frame = ttk.Frame(form)
        uid_frame.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        self.new_uid_var = tk.StringVar()
        ttk.Entry(uid_frame, textvariable=self.new_uid_var, width=14).pack(side="left")
        self._button(uid_frame, "UID acak", self._random_uid).pack(side="left", padx=6)
        ttk.Label(
            uid_frame,
            text="kosongkan = UID sumber; BCC dihitung otomatis",
            style="Hint.TLabel",
        ).pack(side="left", padx=8)

        row += 1
        ttk.Label(form, text="Folder output:").grid(row=row, column=0, sticky="w", pady=3)
        out_frame = ttk.Frame(form)
        out_frame.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        self.out_dir_var = tk.StringVar(value="clones")
        ttk.Entry(out_frame, textvariable=self.out_dir_var).pack(
            side="left", fill="x", expand=True
        )
        self._button(out_frame, "Pilih...", self._browse_out_dir).pack(
            side="left", padx=(6, 0)
        )
        self._button(out_frame, "Buka", lambda: self._open_folder(self.out_dir_var.get())).pack(
            side="left", padx=(6, 0)
        )

        row += 1
        ttk.Label(form, text="Backend script:").grid(
            row=row, column=0, sticky="nw", pady=3
        )
        backend_frame = ttk.Frame(form)
        backend_frame.grid(row=row, column=1, sticky="w", padx=6, pady=3)
        self.backend_vars: dict[str, tk.BooleanVar] = {
            "gen1a": tk.BooleanVar(value=True),
            "gen2": tk.BooleanVar(value=True),
            "gen4": tk.BooleanVar(value=True),
        }
        for key, label in (
            ("gen1a", "Gen1a (magic biasa)"),
            ("gen2", "Gen2 / CUID"),
            ("gen4", "Gen4 / Ultimate"),
        ):
            ttk.Checkbutton(
                backend_frame, text=label, variable=self.backend_vars[key]
            ).pack(side="left", padx=(0, 12))

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=6)
        self._button(actions, "Buat Clone", self._make_clone).pack(side="left")
        self._button(actions, "Buat Paket Rekomendasi", self._make_recommended).pack(
            side="left", padx=6
        )

        result_frame = ttk.LabelFrame(tab, text="Hasil", padding=4)
        result_frame.pack(fill="both", expand=True)
        columns = ("file", "uid", "counter", "fill", "valid")
        self.clone_tree = ttk.Treeview(
            result_frame, columns=columns, show="headings", height=6
        )
        for column, title, width in (
            ("file", "File", 440),
            ("uid", "UID", 90),
            ("counter", "Counter", 150),
            ("fill", "Fill", 60),
            ("valid", "Valid", 60),
        ):
            self.clone_tree.heading(column, text=title)
            self.clone_tree.column(column, width=width, anchor="center")
        clone_ysb = ttk.Scrollbar(
            result_frame, orient="vertical", command=self.clone_tree.yview
        )
        self.clone_tree.configure(yscrollcommand=clone_ysb.set)
        self.clone_tree.pack(side="left", fill="both", expand=True)
        clone_ysb.pack(side="right", fill="y")

        log_frame = ttk.LabelFrame(tab, text="Log", padding=4)
        log_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.clone_log = ScrolledText(
            log_frame, height=9, wrap="word", font=("Consolas", 9)
        )
        self.clone_log.pack(fill="both", expand=True)
        self.clone_log.configure(state="disabled")

    def _build_write_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="Tulis / Verifikasi")

        form = ttk.LabelFrame(tab, text="Proxmark3", padding=8)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(form, text="File clone:").grid(row=row, column=0, sticky="w", pady=3)
        file_frame = ttk.Frame(form)
        file_frame.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        self.write_file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.write_file_var).pack(
            side="left", fill="x", expand=True
        )
        self._button(file_frame, "Pilih...", self._browse_write_file).pack(
            side="left", padx=(6, 0)
        )

        row += 1
        ttk.Label(form, text="Jenis kartu:").grid(row=row, column=0, sticky="w", pady=3)
        self.backend_var = tk.StringVar(value="gen1a")
        ttk.Combobox(
            form,
            textvariable=self.backend_var,
            state="readonly",
            values=("gen1a", "gen2", "gen4"),
        ).grid(row=row, column=1, sticky="w", padx=6, pady=3)

        row += 1
        ttk.Label(form, text="Port:").grid(row=row, column=0, sticky="w", pady=3)
        port_frame = ttk.Frame(form)
        port_frame.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        self.port_var = tk.StringVar(value="COM11")
        ttk.Entry(port_frame, textvariable=self.port_var, width=12).pack(side="left")
        self._button(port_frame, "Deteksi port", self._detect_ports).pack(
            side="left", padx=6
        )

        row += 1
        ttk.Label(form, text="Client Proxmark3:").grid(
            row=row, column=0, sticky="w", pady=3
        )
        client_frame = ttk.Frame(form)
        client_frame.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        self.client_var = tk.StringVar()
        ttk.Entry(client_frame, textvariable=self.client_var).pack(
            side="left", fill="x", expand=True
        )
        self._button(client_frame, "Pilih...", self._browse_client).pack(
            side="left", padx=(6, 0)
        )

        row += 1
        ttk.Label(form, text="File key (opsional):").grid(
            row=row, column=0, sticky="w", pady=3
        )
        key_frame = ttk.Frame(form)
        key_frame.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        self.keys_var = tk.StringVar()
        ttk.Entry(key_frame, textvariable=self.keys_var).pack(
            side="left", fill="x", expand=True
        )
        self._button(key_frame, "Pilih...", self._browse_keys).pack(
            side="left", padx=(6, 0)
        )

        row += 1
        options = ttk.Frame(form)
        options.grid(row=row, column=1, sticky="w", padx=6, pady=3)
        self.verify_var = tk.BooleanVar(value=True)
        self.backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options, text="Verifikasi setelah menulis", variable=self.verify_var
        ).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(
            options, text="Backup kartu sebelum menulis", variable=self.backup_var
        ).pack(side="left")

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=6)
        self._button(actions, "Baca Kartu", self._read_card).pack(side="left")
        self._button(actions, "Tulis ke Kartu", self._write_card).pack(
            side="left", padx=6
        )
        ttk.Label(
            actions,
            text="Menulis menimpa seluruh kartu, termasuk UID.",
            style="Danger.TLabel",
        ).pack(side="right")

        log_frame = ttk.LabelFrame(tab, text="Log", padding=4)
        log_frame.pack(fill="both", expand=True)
        self.write_log = ScrolledText(
            log_frame, height=20, wrap="word", font=("Consolas", 9)
        )
        self.write_log.pack(fill="both", expand=True)
        self.write_log.configure(state="disabled")

    def _build_help_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="Bantuan")
        self.help_text = ScrolledText(
            tab, wrap="word", font=("Consolas", 9), padx=8, pady=8
        )
        self.help_text.pack(fill="both", expand=True)
        self.help_text.insert("1.0", HELP_TEXT)
        self.help_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Tab dump
    # ------------------------------------------------------------------
    def _browse_dump_dir(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.dump_dir_var.get() or ".")
        if folder:
            self.dump_dir_var.set(folder)
            self._load_dumps()

    def _load_dumps(self) -> None:
        folder = self.dump_dir_var.get().strip() or str(DEFAULT_DUMP_DIR)
        try:
            cards = load_dump_dir(folder)
        except Exception as exc:
            self._log(self.info_text, f"ERROR memuat dump: {exc}")
            messagebox.showerror("Gagal memuat dump", str(exc))
            return
        self.cards = cards
        self.card_by_uid = {card.uid_hex: card for card in cards}
        self._refresh_dump_tree()
        self._refresh_source_combo()
        self._log(
            self.info_text,
            f"Dimuat {len(cards)} dump dari {resolve_existing(folder)}",
        )
        self.status_var.set(f"{len(cards)} dump dimuat")

    def _refresh_dump_tree(self) -> None:
        for item in self.dump_tree.get_children():
            self.dump_tree.delete(item)
        for card in self.cards:
            self.dump_tree.insert(
                "",
                "end",
                values=(
                    card.uid_hex,
                    card.counters[0],
                    card.counters[1],
                    f"0x{card.counter:04X}",
                    f"{card.counter_fill:02X}"
                    if card.counter_fill is not None
                    else "?",
                    "ya" if card.payloads_equal else "tidak",
                    "ya" if card.tails_equal_without_counter else "tidak",
                    card.source.name if card.source else "-",
                ),
            )

    def _refresh_source_combo(self) -> None:
        labels = []
        self.card_labels = {}
        for card in self.cards:
            label = (
                f"{card.uid_hex}  |  counter {card.counter}  |  "
                f"{card.source.name if card.source else ''}"
            )
            labels.append(label)
            self.card_labels[label] = card
        self.source_combo["values"] = labels
        if labels:
            self.source_combo.current(0)
        else:
            self.source_combo.set("")

    def _on_dump_select(self, _event: tk.Event) -> None:
        selection = self.dump_tree.selection()
        if not selection:
            return
        values = self.dump_tree.item(selection[0], "values")
        if not values:
            return
        card = self.card_by_uid.get(str(values[0]))
        if card is not None:
            self._set_text(
                self.info_text,
                format_info(card, title=str(card.source or card.uid_hex)),
            )

    def _show_detail(self) -> None:
        if not self.cards:
            messagebox.showinfo("Belum ada dump", "Muat dump terlebih dahulu.")
            return
        selection = self.dump_tree.selection()
        if selection:
            self._on_dump_select(tk.Event())
            return
        self._set_text(
            self.info_text,
            "\n\n".join(
                format_info(card, title=str(card.source or card.uid_hex))
                for card in self.cards
            ),
        )

    def _show_analysis(self) -> None:
        if not self.cards:
            messagebox.showinfo("Belum ada dump", "Muat dump terlebih dahulu.")
            return
        self._set_text(self.info_text, analyze(self.cards))

    def _save_report(self) -> None:
        text = self.info_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showinfo("Laporan kosong", "Tampilkan info/analisis dulu.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Semua file", "*.*")],
            initialfile="gtink_report.txt",
        )
        if not path:
            return
        try:
            Path(path).write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Gagal menyimpan", str(exc))
            return
        self.status_var.set(f"Laporan disimpan: {path}")

    # ------------------------------------------------------------------
    # Tab clone
    # ------------------------------------------------------------------
    def _browse_out_dir(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.out_dir_var.get() or ".")
        if folder:
            self.out_dir_var.set(folder)

    def _selected_source(self) -> Card:
        label = self.source_combo.get()
        card = self.card_labels.get(label)
        if card is None:
            if self.cards:
                return self.cards[0]
            raise ValueError("Belum ada dump. Muat dump di tab Dump && Analisis.")
        return card

    def _parse_counter(self) -> int:
        text = self.counter_var.get().strip()
        try:
            value = int(text, 16) if text.lower().startswith("0x") else int(text, 10)
        except ValueError as exc:
            raise ValueError("Counter harus angka 0..65535") from exc
        if not 0 <= value <= MAX_COUNTER:
            raise ValueError(f"Counter harus 0..{MAX_COUNTER}")
        return value

    def _parse_new_uid(self) -> bytes | None:
        text = re.sub(r"[\s:_-]", "", self.new_uid_var.get())
        if not text:
            return None
        if len(text) != 8:
            raise ValueError("UID baru harus 8 digit hex (4 byte)")
        try:
            return bytes.fromhex(text)
        except ValueError as exc:
            raise ValueError("UID baru bukan hex yang valid") from exc

    def _fill_value(self) -> int | None:
        choice = self.fill_var.get()
        if choice.startswith("00"):
            return 0x00
        if choice.startswith("FF"):
            return 0xFF
        return None

    def _selected_backends(self) -> tuple[str, ...]:
        backends = tuple(
            key for key, variable in self.backend_vars.items() if variable.get()
        )
        if not backends:
            raise ValueError("Pilih minimal satu backend script.")
        return backends

    def _random_uid(self) -> None:
        try:
            source = self._selected_source()
        except Exception as exc:
            messagebox.showerror("Sumber belum dipilih", str(exc))
            return
        uid = derive_uid(source)
        self.new_uid_var.set(uid.hex().upper())
        self._log(
            self.clone_log,
            f"UID acak dari payload {source.uid_hex}: {uid.hex().upper()}",
        )

    def _make_clone(self) -> None:
        try:
            source = self._selected_source()
            counter = self._parse_counter()
            fill = self._fill_value()
            new_uid = self._parse_new_uid()
            backends = self._selected_backends()
            out_dir = Path(self.out_dir_var.get().strip() or "clones").expanduser()
        except Exception as exc:
            messagebox.showerror("Parameter tidak valid", str(exc))
            return

        label = f"gui_{counter}"
        if fill is not None:
            label += f"_fill{fill:02X}"
        if new_uid is not None:
            label += f"_uid{new_uid.hex().upper()}"
        spec = CloneSpec(
            source=source,
            counter=counter,
            label=label,
            description="Clone dari GUI.",
            fill=fill,
            uid=new_uid,
        )

        def task() -> CloneResult:
            return write_clone_result(spec, out_dir, script_backends=backends)

        def done(result: CloneResult) -> None:
            self._add_clone_result(result)
            self._log(self.clone_log, format_results([result]))
            self._log(self.clone_log, f"BIN: {result.bin_path.resolve()}")
            messagebox.showinfo(
                "Clone dibuat",
                f"{result.bin_path.name}\n\n{result.bin_path.parent.resolve()}",
            )

        self._run_task(f"Membuat clone counter {counter}...", task, done)

    def _make_recommended(self) -> None:
        if not self.cards:
            messagebox.showinfo("Belum ada dump", "Muat dump terlebih dahulu.")
            return
        try:
            backends = self._selected_backends()
            out_dir = Path(self.out_dir_var.get().strip() or "clones").expanduser()
        except Exception as exc:
            messagebox.showerror("Parameter tidak valid", str(exc))
            return

        def task() -> list[CloneResult]:
            return write_recommended(self.cards, out_dir, script_backends=backends)

        def done(results: list[CloneResult]) -> None:
            for item in self.clone_tree.get_children():
                self.clone_tree.delete(item)
            self.clone_results = list(results)
            for result in results:
                self._add_clone_result(result, log=False)
            self._log(self.clone_log, format_results(results))
            self._log(
                self.clone_log,
                f"Manifest: {(out_dir / 'manifest.json').resolve()}",
            )
            messagebox.showinfo(
                "Paket dibuat",
                f"{len(results)} clone dibuat di\n{out_dir.resolve()}",
            )

        self._run_task("Membuat paket rekomendasi...", task, done)

    def _add_clone_result(self, result: CloneResult, log: bool = True) -> None:
        if log:
            self.clone_results.append(result)
        fill = f"{result.spec.fill:02X}" if result.spec.fill is not None else "asli"
        self.clone_tree.insert(
            "",
            "end",
            values=(
                result.bin_path.name,
                result.card.uid_hex,
                f"{result.spec.counter} (0x{result.spec.counter:04X})",
                fill,
                "ya" if not result.card.has_errors() else "TIDAK",
            ),
        )

    # ------------------------------------------------------------------
    # Tab tulis / verifikasi
    # ------------------------------------------------------------------
    def _browse_write_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("Dump BIN", "*.bin"),
                ("JSON", "*.json"),
                ("EML", "*.eml"),
                ("Semua file", "*.*"),
            ],
            initialdir=str(resolve_existing("clones")),
        )
        if path:
            self.write_file_var.set(path)

    def _browse_client(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Executable", "*.exe"), ("Semua file", "*.*")],
            initialdir=r"C:\ProxSpace\pm3\proxmark3\client",
        )
        if path:
            self.client_var.set(path)

    def _browse_keys(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Key file", "*.bin"), ("Semua file", "*.*")],
            initialdir=str(resolve_existing(".")),
        )
        if path:
            self.keys_var.set(path)

    def _detect_ports(self) -> None:
        log = self._current_log()
        try:
            ports = list_serial_ports()
        except Exception as exc:
            self._log(log, f"ERROR mendeteksi port: {exc}")
            messagebox.showerror("Gagal", str(exc))
            return
        if not ports:
            self._log(log, "Tidak ada port serial terdeteksi.")
        for item in ports:
            device = str(item.get("DeviceID", "")).strip()
            name = str(item.get("Name", "")).strip()
            self._log(log, f"Port: {device}  {name}")
        try:
            port = find_port()
        except Exception:
            port = "COM11"
        self.port_var.set(port)
        self._log(log, f"Port Proxmark3 yang dipilih: {port}")

    def _client_kwargs(self) -> dict[str, Any]:
        return {
            "client": self.client_var.get().strip() or None,
            "port": self.port_var.get().strip() or None,
            "timeout": 300,
        }

    def _read_card(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            filetypes=[
                ("Dump BIN", "*.bin"),
                ("JSON", "*.json"),
                ("EML", "*.eml"),
                ("Semua file", "*.*"),
            ],
            initialfile=f"readback_{datetime.now():%Y%m%d_%H%M%S}.bin",
        )
        if not path:
            return
        out_path = Path(path)
        keys = self.keys_var.get().strip() or None
        if keys:
            keys = str(resolve_existing(keys))

        def task() -> tuple[Any, Card, str]:
            with ProxmarkClient(**self._client_kwargs()) as client:
                info = client.search()
                card, output = client.read_card(keys=keys, timeout=300)
                if out_path.suffix.lower() == ".json":
                    card.save_json(out_path)
                elif out_path.suffix.lower() == ".eml":
                    card.save_eml(out_path)
                else:
                    card.save(out_path)
                    card.save_json(out_path.with_suffix(".json"))
                return info, card, output

        def done(result: tuple[Any, Card, str]) -> None:
            info, card, output = result
            self._log(
                self.write_log,
                f"Kartu: UID {info.uid_hex}"
                + (f", SAK {info.sak}" if info.sak else "")
                + (f", magic: {info.magic}" if info.magic else ""),
            )
            tail = "\n".join(output.splitlines()[-12:])
            if tail:
                self._log(self.write_log, tail)
            self._log(
                self.write_log,
                format_info(card, title="Hasil baca kartu"),
            )
            messagebox.showinfo(
                "Baca selesai",
                f"UID {card.uid_hex}\nCounter {card.counter}\n\n{out_path.resolve()}",
            )

        self._run_task("Membaca kartu...", task, done)

    def _write_card(self) -> None:
        file_text = self.write_file_var.get().strip()
        if not file_text:
            messagebox.showerror("File kosong", "Pilih file clone terlebih dahulu.")
            return
        source = resolve_existing(file_text)
        if not source.is_file():
            messagebox.showerror("File tidak ditemukan", str(source))
            return
        try:
            card = load_card(source)
        except Exception as exc:
            messagebox.showerror("File tidak valid", str(exc))
            return
        if card.has_errors():
            if not messagebox.askyesno(
                "Clone tidak valid",
                "Clone memiliki error validasi. Tetap tulis?",
            ):
                return

        backend = self.backend_var.get()
        confirm = messagebox.askyesno(
            "Konfirmasi tulis",
            "Tulis clone ke kartu magic?\n\n"
            f"File    : {source.name}\n"
            f"UID     : {card.uid_hex}\n"
            f"Counter : {card.counter}\n"
            f"Backend : {backend}\n\n"
            "Seluruh isi kartu, termasuk UID, akan ditimpa.",
        )
        if not confirm:
            return

        keys = self.keys_var.get().strip() or None
        if keys:
            keys = str(resolve_existing(keys))
        verify = self.verify_var.get()
        backup = self.backup_var.get()

        def task() -> tuple[Any, Path | None, str, Any]:
            with ProxmarkClient(**self._client_kwargs()) as client:
                info = client.search()
                backup_path: Path | None = None
                if backup:
                    backup_card, _ = client.read_card(keys=keys, timeout=300)
                    backup_dir = Path("backups").expanduser()
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    backup_path = (
                        backup_dir
                        / f"{backup_card.uid_hex}_{datetime.now():%Y%m%d_%H%M%S}.bin"
                    )
                    backup_card.save(backup_path)
                    backup_card.save_json(backup_path.with_suffix(".json"))
                output = client.write_card(source, backend=backend, timeout=300)
                result = (
                    client.verify_card(source, keys=keys, timeout=300)
                    if verify
                    else None
                )
                return info, backup_path, output, result

        def done(result: tuple[Any, Path | None, str, Any]) -> None:
            info, backup_path, output, verify_result = result
            self._log(
                self.write_log,
                f"Target: UID {info.uid_hex}, magic: {info.magic or 'tidak terdeteksi'}",
            )
            if backup_path is not None:
                self._log(self.write_log, f"Backup: {backup_path.resolve()}")
            tail = "\n".join(output.splitlines()[-15:])
            if tail:
                self._log(self.write_log, tail)
            if verify_result is not None:
                self._log(self.write_log, verify_result.summary())
                if not verify_result.ok:
                    for block, expected, actual in verify_result.diff_blocks:
                        self._log(
                            self.write_log,
                            f"  blok {block:2d}: harap {expected.hex().upper()} "
                            f"baca {actual.hex().upper()}",
                        )
                    messagebox.showwarning(
                        "Verifikasi gagal",
                        verify_result.summary(),
                    )
                    return
                messagebox.showinfo(
                    "Selesai",
                    f"Verifikasi OK: {card.uid_hex}, 64 blok sama.",
                )
            else:
                messagebox.showinfo("Selesai", "Tulis selesai; verifikasi dilewati.")

        self._run_task("Menulis kartu...", task, done)

    # ------------------------------------------------------------------
    # Lain-lain
    # ------------------------------------------------------------------
    def _run_selftest(self) -> None:
        def task() -> tuple[bool, list[tuple[bool, str, str]]]:
            return run_selftest(verbose=False)

        def done(result: tuple[bool, list[tuple[bool, str, str]]]) -> None:
            ok, checks = result
            log = self._current_log()
            for passed, name, detail in checks:
                status = "OK" if passed else "GAGAL"
                self._log(
                    log,
                    f"[{status}] {name}" + (f" - {detail}" if detail else ""),
                )
            messagebox.showinfo(
                "Selftest",
                ("SELFTEST LULUS" if ok else "SELFTEST GAGAL")
                + f" ({sum(1 for item in checks if item[0])}/{len(checks)})",
            )

        self._run_task("Selftest offline...", task, done)

    def _show_help(self) -> None:
        self.notebook.select(3)
        self._set_text(self.help_text, HELP_TEXT)

    def _about(self) -> None:
        messagebox.showinfo(
            "Tentang GTInk",
            f"GTInk {__version__}\n\n"
            "Analisis dan kloning chip kartrid EAJet/GT1000.\n"
            "MIFARE Classic 1K, Python standard library, Tkinter.\n\n"
            "Gunakan hanya pada kartu/printer milik sendiri.",
        )

    def _open_folder(self, path_text: str) -> None:
        path = Path(path_text).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Gagal membuka folder", str(exc))
            return
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except AttributeError:
            import subprocess

            subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("Gagal membuka folder", str(exc))


def main() -> int:
    app = GtInkApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
