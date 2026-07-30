from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk


ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
PROJECT_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
GIT = Path(r"C:\Users\pgzdv\AppData\Local\GitHubDesktop\app-3.5.9\resources\app\git\cmd\git.exe")
PAGES_URL = "https://saint-chinu.github.io/majsoul-league/"


COLORS = {
    "bg": "#eef3f6",
    "surface": "#ffffff",
    "surface_alt": "#f7fafb",
    "ink": "#102027",
    "muted": "#63717a",
    "line": "#d9e3e8",
    "primary": "#0f8b7f",
    "primary_dark": "#0a6c63",
    "accent": "#e98f37",
    "danger": "#d94c4c",
    "log_bg": "#0d1b22",
    "log_fg": "#d7eef0",
}


TASKS = {
    "single": {
        "title": "単一シーズン更新",
        "subtitle": "シーズンを1つ選んで、牌譜取得から公開まで実行",
        "script": "run_manual_season.py",
        "interactive": True,
    },
    "all": {
        "title": "まとめて更新",
        "subtitle": "全シーズン取得、牌譜DL、集計、HTML公開をまとめて実行",
        "script": "run_all.py",
        "interactive": True,
    },
    "team": {
        "title": "チーム情報更新",
        "subtitle": "管理画面からチーム名とメンバーを取得して公開",
        "script": "run_team_publish.py",
        "interactive": True,
    },
    "stats_site": {
        "title": "集計とHTML再作成",
        "subtitle": "既存牌譜からCSVとサイトを作り直す",
        "commands": [["aggregate_league.py"], ["make_site.py"]],
        "interactive": False,
    },
    "stats": {
        "title": "集計CSVだけ再作成",
        "subtitle": "summary.csv、yakuman系CSVを再生成",
        "commands": [["aggregate_league.py"]],
        "interactive": False,
    },
    "site": {
        "title": "HTMLだけ再作成",
        "subtitle": "docs/index.htmlを再生成",
        "commands": [["make_site.py"]],
        "interactive": False,
    },
}


PLAYER_LOGS = [
    ("流れ者金融", "nagaremono_table_event_log_with_hands.csv"),
    ("葡萄海ぶどう", "budou_table_event_log_with_hands.csv"),
    ("29ちゃん", "29chan_table_event_log_with_hands.csv"),
    ("ひなんじょ", "hinanjo_table_event_log_with_hands.csv"),
    ("アリスkey", "alicekey_table_event_log_with_hands.csv"),
    ("鯛ofカルピス", "taiofcalpis_table_event_log_with_hands.csv"),
]


def project_python() -> Path:
    if not PROJECT_PYTHON.exists():
        raise RuntimeError(f"Pythonが見つかりません: {PROJECT_PYTHON}")
    return PROJECT_PYTHON


class LeagueApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("魚群リーグ 集計ツール")
        self.geometry("1120x760")
        self.minsize(980, 680)
        self.configure(bg=COLORS["bg"])
        self.running = False
        self.status_var = tk.StringVar(value="待機中")
        self._build_styles()
        self._build_ui()

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Muted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=("Yu Gothic UI", 10))
        style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=("Yu Gothic UI", 24, "bold"))
        style.configure("CardTitle.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=("Yu Gothic UI", 13, "bold"))
        style.configure("Card.TFrame", background=COLORS["surface"], relief="flat")
        style.configure("Primary.TButton", font=("Yu Gothic UI", 10, "bold"), padding=(16, 10))
        style.configure("Quiet.TButton", font=("Yu Gothic UI", 10), padding=(14, 9))
        style.configure("TCombobox", padding=7)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=22)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 18))

        title_area = ttk.Frame(header)
        title_area.pack(side="left", fill="x", expand=True)
        ttk.Label(title_area, text="魚群リーグ 集計ツール", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_area,
            text="シーズン取得、牌譜DL、集計、HTML公開、手牌ログ作成をここから実行",
            background=COLORS["bg"],
            foreground=COLORS["muted"],
            font=("Yu Gothic UI", 11),
        ).pack(anchor="w", pady=(4, 0))

        top_actions = ttk.Frame(header)
        top_actions.pack(side="right")
        ttk.Button(top_actions, text="公開ページを開く", style="Quiet.TButton", command=lambda: webbrowser.open(PAGES_URL)).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(top_actions, text="フォルダを開く", style="Quiet.TButton", command=self.open_folder).pack(side="left")

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")

        self._build_task_grid(left)
        self._build_log_panel(right)
        self._build_status_bar(outer)

    def _build_task_grid(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        tasks = [
            ("single", "1"),
            ("team", "3"),
            ("stats_site", "4"),
            ("all", "2"),
            ("stats", "5"),
            ("site", "6"),
        ]

        for index, (key, badge) in enumerate(tasks):
            row = index // 2
            column = index % 2
            self._task_card(parent, key, badge).grid(row=row, column=column, sticky="nsew", padx=8, pady=8)

        utilities = ttk.Frame(parent, style="Card.TFrame", padding=18)
        utilities.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(14, 8))
        utilities.columnconfigure(0, weight=1)

        ttk.Label(utilities, text="公開・ログ作成", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            utilities,
            text="HTMLだけ公開したい時や、プレイヤー別の手牌つき完全ログを作る時はこちら。",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        buttons = ttk.Frame(utilities, style="Surface.TFrame")
        buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(buttons, text="GitHub Pagesへ公開", style="Primary.TButton", command=self.publish_site).pack(side="left", padx=(0, 10))
        ttk.Button(buttons, text="手牌つき完全ログを作る", style="Quiet.TButton", command=self.open_log_dialog).pack(side="left")

    def _task_card(self, parent: ttk.Frame, key: str, badge: str) -> ttk.Frame:
        info = TASKS[key]
        card = ttk.Frame(parent, style="Card.TFrame", padding=18)
        card.columnconfigure(1, weight=1)

        badge_label = tk.Label(
            card,
            text=badge,
            bg=COLORS["primary"],
            fg="white",
            font=("Yu Gothic UI", 11, "bold"),
            width=3,
            height=1,
        )
        badge_label.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 12))
        ttk.Label(card, text=info["title"], style="CardTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(card, text=info["subtitle"], style="Muted.TLabel", wraplength=280).grid(row=1, column=1, sticky="w", pady=(3, 12))

        button_text = "別ウィンドウで実行" if info.get("interactive") else "実行"
        ttk.Button(card, text=button_text, style="Primary.TButton", command=lambda: self.run_task(key)).grid(
            row=2, column=0, columnspan=2, sticky="ew"
        )
        return card

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=16)
        panel.pack(fill="both", expand=True)
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text="実行ログ", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.log = tk.Text(
            panel,
            bg=COLORS["log_bg"],
            fg=COLORS["log_fg"],
            insertbackground=COLORS["log_fg"],
            relief="flat",
            font=("Consolas", 10),
            wrap="word",
            padx=12,
            pady=12,
            height=22,
        )
        self.log.grid(row=1, column=0, sticky="nsew")
        self.log_insert("GUIを起動しました。\n対話が必要な処理はPowerShellを開きます。完了までその画面を閉じないでください。\n")

        bottom = ttk.Frame(panel, style="Surface.TFrame")
        bottom.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(bottom, text="ログを消す", style="Quiet.TButton", command=lambda: self.log.delete("1.0", "end")).pack(side="left")
        ttk.Button(bottom, text="公開ページ", style="Quiet.TButton", command=lambda: webbrowser.open(PAGES_URL)).pack(side="right")

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent, padding=(4, 14, 4, 0))
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status_var, background=COLORS["bg"], foreground=COLORS["muted"], font=("Yu Gothic UI", 10)).pack(
            side="left"
        )
        ttk.Label(
            bar,
            text=str(ROOT),
            background=COLORS["bg"],
            foreground=COLORS["muted"],
            font=("Yu Gothic UI", 9),
        ).pack(side="right")

    def log_insert(self, text: str) -> None:
        self.log.insert("end", text)
        self.log.see("end")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def open_folder(self) -> None:
        os.startfile(ROOT)

    def start_terminal(self, script_name: str, *args: str) -> None:
        if not POWERSHELL.exists():
            messagebox.showerror("PowerShellなし", f"PowerShellが見つかりません: {POWERSHELL}")
            return
        try:
            python = project_python()
        except RuntimeError as exc:
            messagebox.showerror("Pythonなし", str(exc))
            return

        script = ROOT / script_name
        command = (
            f"cd /d '{ROOT}'; "
            f"& '{python}' '{script}' {' '.join(repr(arg) for arg in args)}; "
            "Write-Host ''; Read-Host '終了しました。Enterで閉じます'"
        )
        subprocess.Popen([str(POWERSHELL), "-NoExit", "-Command", command], cwd=ROOT)
        self.log_insert(f"\n[OPEN] {script_name} をPowerShellで起動しました。\n")
        self.set_status(f"{script_name} を別ウィンドウで実行中")

    def run_task(self, key: str) -> None:
        info = TASKS[key]
        if info.get("interactive"):
            self.start_terminal(info["script"])
            return

        commands = info.get("commands", [])
        self.run_background(info["title"], commands)

    def run_background(self, title: str, commands: list[list[str]]) -> None:
        if self.running:
            messagebox.showinfo("実行中", "いま別の処理を実行中です。終わってから押してください。")
            return

        try:
            python = project_python()
        except RuntimeError as exc:
            messagebox.showerror("Pythonなし", str(exc))
            return

        def worker() -> None:
            self.running = True
            self.after(0, self.set_status, f"{title} 実行中")
            self.after(0, self.log_insert, f"\n[START] {title}\n")
            try:
                for command in commands:
                    script = ROOT / command[0]
                    args = [str(python), str(script), *command[1:]]
                    self.after(0, self.log_insert, ">>> " + " ".join(args) + "\n")
                    process = subprocess.Popen(
                        args,
                        cwd=ROOT,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    assert process.stdout is not None
                    for line in process.stdout:
                        self.after(0, self.log_insert, line)
                    code = process.wait()
                    if code != 0:
                        raise RuntimeError(f"{script.name} が失敗しました。終了コード: {code}")
                self.after(0, self.log_insert, f"[DONE] {title}\n")
                self.after(0, self.set_status, "完了")
            except Exception as exc:
                self.after(0, self.log_insert, f"[ERROR] {exc}\n")
                self.after(0, self.set_status, "エラー")
            finally:
                self.running = False

        threading.Thread(target=worker, daemon=True).start()

    def publish_site(self) -> None:
        if not GIT.exists():
            messagebox.showerror("Gitなし", f"GitHub Desktop のgit.exeが見つかりません: {GIT}")
            return
        files = [
            "admin_paifu_ids.csv",
            "summary.csv",
            "yakuman_summary.csv",
            "yakuman_details.csv",
            "team_members.csv",
            "docs/index.html",
        ]
        existing = [name for name in files if (ROOT / name).exists()]
        if not existing:
            messagebox.showinfo("対象なし", "公開対象ファイルがありません。")
            return
        commands = [
            [str(GIT), "add", *existing],
            [str(GIT), "commit", "-m", "Update majsoul league site"],
            [str(GIT), "push", "origin", "main"],
        ]
        self.run_raw_commands("GitHub Pagesへ公開", commands)

    def run_raw_commands(self, title: str, commands: list[list[str]]) -> None:
        if self.running:
            messagebox.showinfo("実行中", "いま別の処理を実行中です。")
            return

        def worker() -> None:
            self.running = True
            self.after(0, self.set_status, f"{title} 実行中")
            self.after(0, self.log_insert, f"\n[START] {title}\n")
            try:
                for args in commands:
                    self.after(0, self.log_insert, ">>> " + " ".join(args) + "\n")
                    process = subprocess.Popen(
                        args,
                        cwd=ROOT,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    assert process.stdout is not None
                    output = []
                    for line in process.stdout:
                        output.append(line)
                        self.after(0, self.log_insert, line)
                    code = process.wait()
                    if "commit" in args and code != 0 and any("nothing to commit" in line for line in output):
                        self.after(0, self.log_insert, "コミットする変更はありません。\n")
                        continue
                    if code != 0:
                        raise RuntimeError(f"コマンドが失敗しました。終了コード: {code}")
                self.after(0, self.log_insert, f"[DONE] {title}\n{PAGES_URL}\n")
                self.after(0, self.set_status, "完了")
            except Exception as exc:
                self.after(0, self.log_insert, f"[ERROR] {exc}\n")
                self.after(0, self.set_status, "エラー")
            finally:
                self.running = False

        threading.Thread(target=worker, daemon=True).start()

    def open_log_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("手牌つき完全ログCSV")
        dialog.geometry("520x500")
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=20, style="Surface.TFrame")
        frame.pack(fill="both", expand=True, padx=18, pady=18)
        ttk.Label(frame, text="作成するプレイヤーを選択", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(frame, text="生成は重いので、必要な人だけ選ぶのがおすすめ。", style="Muted.TLabel").pack(anchor="w", pady=(4, 12))

        selected = {name: tk.BooleanVar(value=False) for name, _output in PLAYER_LOGS}
        for name, _output in PLAYER_LOGS:
            ttk.Checkbutton(frame, text=name, variable=selected[name]).pack(anchor="w", pady=3)

        def run_selected() -> None:
            targets = [(name, output) for name, output in PLAYER_LOGS if selected[name].get()]
            if not targets:
                messagebox.showinfo("未選択", "プレイヤーを選んでください。")
                return
            dialog.destroy()
            commands = [["export_table_event_log_with_hands_for_player.py", name, output] for name, output in targets]
            self.run_background("手牌つき完全ログCSV作成", commands)

        ttk.Button(frame, text="作成する", style="Primary.TButton", command=run_selected).pack(fill="x", pady=(18, 8))
        ttk.Button(frame, text="キャンセル", style="Quiet.TButton", command=dialog.destroy).pack(fill="x")


def main() -> None:
    os.chdir(ROOT)
    app = LeagueApp()
    app.mainloop()


if __name__ == "__main__":
    main()
