"""
Main GUI window for Wind Window Operator AI.
Built with tkinter (Python built-in).
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, font as tkfont
import threading
import datetime
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


class MainWindow:
    """
    Main application window with:
    - Start/Stop capture button
    - Mode selector (screenshot/recording/both)
    - Live analysis feed
    - Memory viewer (short/long term)
    - Recommendation area
    - Instruction input (for user commands to AI)
    - Skill browser
    - Statistics panel
    """

    COLORS = {
        "bg": "#1e1e2e",
        "fg": "#cdd6f4",
        "accent": "#89b4fa",
        "green": "#a6e3a1",
        "red": "#f38ba8",
        "yellow": "#f9e2af",
        "surface": "#313244",
        "surface2": "#45475a",
        "button_start": "#a6e3a1",
        "button_stop": "#f38ba8",
        "button_normal": "#89b4fa",
    }

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Wind Window Operator AI")
        self.root.geometry("1100x750")
        self.root.configure(bg=self.COLORS["bg"])
        self.root.minsize(900, 600)

        # Orchestrator (loaded lazily to avoid import errors at startup)
        self._orchestrator = None
        self._running = False

        self._setup_fonts()
        self._build_ui()
        self._setup_orchestrator()

        # Periodic UI refresh
        self._refresh_ui()

    def _setup_fonts(self):
        self.font_normal = tkfont.Font(family="Helvetica", size=11)
        self.font_small = tkfont.Font(family="Helvetica", size=9)
        self.font_bold = tkfont.Font(family="Helvetica", size=11, weight="bold")
        self.font_mono = tkfont.Font(family="Courier", size=10)
        self.font_title = tkfont.Font(family="Helvetica", size=14, weight="bold")

    def _setup_orchestrator(self):
        """Initialize orchestrator with UI callbacks."""
        try:
            from core.orchestrator import Orchestrator
            self._orchestrator = Orchestrator(
                on_status_update=self._on_status,
                on_recommendation=self._on_recommendation,
                on_analysis_done=self._on_analysis,
                on_capture=self._on_capture,
                on_action=self._on_action,
                on_job_start=self._on_job_start,
                on_job_done=self._on_job_done,
                on_task_start=self._on_task_start,
                on_task_done=self._on_task_done,
                capture_mode=self.mode_var.get(),
            )
        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {e}")
            self._on_status(f"初期化エラー: {e}")

    def _build_ui(self):
        """Build the full UI layout."""
        # ── Title bar ──────────────────────────────────────────────────────
        title_frame = tk.Frame(self.root, bg=self.COLORS["bg"], pady=8)
        title_frame.pack(fill=tk.X, padx=10)

        tk.Label(
            title_frame,
            text="Wind Window Operator AI",
            font=self.font_title,
            bg=self.COLORS["bg"],
            fg=self.COLORS["accent"],
        ).pack(side=tk.LEFT)

        # Status indicator
        self.status_dot = tk.Label(
            title_frame, text="●", font=self.font_title,
            bg=self.COLORS["bg"], fg=self.COLORS["red"]
        )
        self.status_dot.pack(side=tk.RIGHT, padx=5)

        self.status_label = tk.Label(
            title_frame, text="停止中",
            font=self.font_small,
            bg=self.COLORS["bg"], fg=self.COLORS["fg"]
        )
        self.status_label.pack(side=tk.RIGHT, padx=2)

        # ── Control bar ────────────────────────────────────────────────────
        ctrl_frame = tk.Frame(self.root, bg=self.COLORS["surface"], pady=6)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=(0, 6))

        # Mode selector
        tk.Label(
            ctrl_frame, text="モード:",
            font=self.font_normal, bg=self.COLORS["surface"], fg=self.COLORS["fg"]
        ).pack(side=tk.LEFT, padx=(10, 2))

        self.mode_var = tk.StringVar(value="screenshot")
        mode_combo = ttk.Combobox(
            ctrl_frame, textvariable=self.mode_var,
            values=["screenshot", "recording", "both"],
            width=12, state="readonly",
        )
        mode_combo.pack(side=tk.LEFT, padx=(0, 10))

        # Interval
        tk.Label(
            ctrl_frame, text="間隔(秒):",
            font=self.font_normal, bg=self.COLORS["surface"], fg=self.COLORS["fg"]
        ).pack(side=tk.LEFT, padx=(0, 2))

        self.interval_var = tk.IntVar(value=config.SCREENSHOT_INTERVAL_SECONDS)
        interval_spin = tk.Spinbox(
            ctrl_frame, from_=5, to=300, increment=5,
            textvariable=self.interval_var, width=6,
            bg=self.COLORS["surface2"], fg=self.COLORS["fg"],
            buttonbackground=self.COLORS["surface2"],
        )
        interval_spin.pack(side=tk.LEFT, padx=(0, 15))

        # Start/Stop button
        self.start_btn = tk.Button(
            ctrl_frame,
            text="▶ スタート",
            font=self.font_bold,
            bg=self.COLORS["button_start"],
            fg=self.COLORS["bg"],
            relief=tk.FLAT,
            padx=20, pady=4,
            command=self._toggle_capture,
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)

        # Manual capture button
        tk.Button(
            ctrl_frame,
            text="📷 今すぐキャプチャ",
            font=self.font_normal,
            bg=self.COLORS["button_normal"],
            fg=self.COLORS["bg"],
            relief=tk.FLAT, padx=10, pady=4,
            command=self._capture_now,
        ).pack(side=tk.LEFT, padx=5)

        # Cleanup button
        tk.Button(
            ctrl_frame,
            text="🗑 クリーンアップ",
            font=self.font_normal,
            bg=self.COLORS["yellow"],
            fg=self.COLORS["bg"],
            relief=tk.FLAT, padx=10, pady=4,
            command=self._run_cleanup,
        ).pack(side=tk.LEFT, padx=5)

        # Job manager button
        tk.Button(
            ctrl_frame,
            text="⚙ ジョブ管理",
            font=self.font_normal,
            bg=self.COLORS["green"],
            fg=self.COLORS["bg"],
            relief=tk.FLAT, padx=10, pady=4,
            command=self._open_job_manager,
        ).pack(side=tk.LEFT, padx=5)

        # Export memory button
        tk.Button(
            ctrl_frame,
            text="💾 メモリ出力",
            font=self.font_normal,
            bg=self.COLORS["surface2"],
            fg=self.COLORS["fg"],
            relief=tk.FLAT, padx=10, pady=4,
            command=self._export_memory,
        ).pack(side=tk.RIGHT, padx=10)

        # ── Main content area ──────────────────────────────────────────────
        main_frame = tk.Frame(self.root, bg=self.COLORS["bg"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        # Left panel
        left_panel = tk.Frame(main_frame, bg=self.COLORS["bg"])
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # Recommendation area
        rec_frame = self._labeled_frame(left_panel, "💡 AIレコメンド")
        rec_frame.pack(fill=tk.X, pady=(0, 5))

        self.recommendation_text = tk.Text(
            rec_frame, height=3, wrap=tk.WORD,
            font=self.font_normal,
            bg=self.COLORS["surface"],
            fg=self.COLORS["yellow"],
            insertbackground=self.COLORS["fg"],
            relief=tk.FLAT, padx=6, pady=4,
        )
        self.recommendation_text.pack(fill=tk.X)
        self.recommendation_text.insert("1.0", "AIレコメンドがここに表示されます...")
        self.recommendation_text.config(state=tk.DISABLED)

        # Analysis feed
        analysis_frame = self._labeled_frame(left_panel, "🔍 分析フィード")
        analysis_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.analysis_text = scrolledtext.ScrolledText(
            analysis_frame, wrap=tk.WORD,
            font=self.font_mono,
            bg=self.COLORS["surface"],
            fg=self.COLORS["fg"],
            insertbackground=self.COLORS["fg"],
            relief=tk.FLAT, padx=6, pady=4,
        )
        self.analysis_text.pack(fill=tk.BOTH, expand=True)

        # Instruction input area (tabs: Standard / Computer Use)
        inst_frame = self._labeled_frame(left_panel, "⌨️ 指示入力")
        inst_frame.pack(fill=tk.X)

        # Mode selector
        mode_bar = tk.Frame(inst_frame, bg=self.COLORS["surface"])
        mode_bar.pack(fill=tk.X, pady=(0, 4))

        self._input_mode = tk.StringVar(value="standard")

        tk.Radiobutton(
            mode_bar, text="標準モード", variable=self._input_mode, value="standard",
            font=self.font_small, bg=self.COLORS["surface"], fg=self.COLORS["fg"],
            selectcolor=self.COLORS["surface2"], activebackground=self.COLORS["surface"],
            activeforeground=self.COLORS["fg"], relief=tk.FLAT,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT)

        tk.Radiobutton(
            mode_bar, text="★ Computer Use (最先端)", variable=self._input_mode, value="computer_use",
            font=self.font_small, bg=self.COLORS["surface"], fg=self.COLORS["yellow"],
            selectcolor=self.COLORS["surface2"], activebackground=self.COLORS["surface"],
            activeforeground=self.COLORS["yellow"], relief=tk.FLAT,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT, padx=(8, 0))

        inst_input_frame = tk.Frame(inst_frame, bg=self.COLORS["surface"])
        inst_input_frame.pack(fill=tk.X)

        self.instruction_entry = tk.Entry(
            inst_input_frame,
            font=self.font_normal,
            bg=self.COLORS["surface2"],
            fg=self.COLORS["fg"],
            insertbackground=self.COLORS["fg"],
            relief=tk.FLAT,
        )
        self.instruction_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 5))
        self.instruction_entry.bind("<Return>", lambda e: self._send_instruction())

        # Auto-execute toggle
        self.auto_exec_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            inst_input_frame,
            text="自動実行",
            variable=self.auto_exec_var,
            font=self.font_small,
            bg=self.COLORS["surface"],
            fg=self.COLORS["fg"],
            selectcolor=self.COLORS["surface2"],
            activebackground=self.COLORS["surface"],
            activeforeground=self.COLORS["fg"],
            relief=tk.FLAT,
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            inst_input_frame,
            text="▶ 実行",
            font=self.font_bold,
            bg=self.COLORS["accent"],
            fg=self.COLORS["bg"],
            relief=tk.FLAT, padx=10,
            command=self._send_instruction,
        ).pack(side=tk.LEFT)

        # Abort button
        self.abort_btn = tk.Button(
            inst_input_frame,
            text="⏹ 中断",
            font=self.font_normal,
            bg=self.COLORS["button_stop"],
            fg=self.COLORS["bg"],
            relief=tk.FLAT, padx=8,
            command=self._abort_execution,
            state=tk.DISABLED,
        )
        self.abort_btn.pack(side=tk.LEFT, padx=(4, 0))

        # Right panel
        right_panel = tk.Frame(main_frame, bg=self.COLORS["bg"], width=320)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH)
        right_panel.pack_propagate(False)

        # Tabbed right panel
        notebook = ttk.Notebook(right_panel)
        notebook.pack(fill=tk.BOTH, expand=True)
        self._notebook = notebook

        # ── Computer Use Thinking tab ──────────────────────────────────────
        thinking_tab = tk.Frame(notebook, bg=self.COLORS["bg"])
        notebook.add(thinking_tab, text="🧠 Thinking")

        tk.Label(
            thinking_tab, text="Claude の思考プロセス (Computer Use)",
            font=self.font_small, bg=self.COLORS["bg"], fg=self.COLORS["yellow"],
        ).pack(anchor=tk.W, padx=5, pady=(5, 0))

        self.thinking_text = scrolledtext.ScrolledText(
            thinking_tab, wrap=tk.WORD,
            font=("Courier", 9),
            bg="#1a1a2e",
            fg="#a0c4ff",
            insertbackground=self.COLORS["fg"],
            relief=tk.FLAT, padx=6, pady=4,
        )
        self.thinking_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # CU action log
        tk.Label(
            thinking_tab, text="アクション履歴",
            font=self.font_small, bg=self.COLORS["bg"], fg=self.COLORS["accent"],
        ).pack(anchor=tk.W, padx=5)

        self.cu_action_text = scrolledtext.ScrolledText(
            thinking_tab, height=8, wrap=tk.WORD,
            font=self.font_mono,
            bg=self.COLORS["surface"],
            fg=self.COLORS["fg"],
            relief=tk.FLAT, padx=4,
        )
        self.cu_action_text.pack(fill=tk.X, padx=5, pady=(0, 5))

        # Memory tab
        mem_tab = tk.Frame(notebook, bg=self.COLORS["bg"])
        notebook.add(mem_tab, text="📝 メモリ")

        tk.Label(
            mem_tab, text="短期メモリ",
            font=self.font_small, bg=self.COLORS["bg"], fg=self.COLORS["accent"]
        ).pack(anchor=tk.W, padx=5, pady=(5, 0))

        self.short_mem_text = scrolledtext.ScrolledText(
            mem_tab, height=8, wrap=tk.WORD,
            font=self.font_small,
            bg=self.COLORS["surface"],
            fg=self.COLORS["fg"],
            relief=tk.FLAT, padx=4,
        )
        self.short_mem_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 3))

        tk.Label(
            mem_tab, text="長期メモリ",
            font=self.font_small, bg=self.COLORS["bg"], fg=self.COLORS["green"]
        ).pack(anchor=tk.W, padx=5)

        self.long_mem_text = scrolledtext.ScrolledText(
            mem_tab, height=8, wrap=tk.WORD,
            font=self.font_small,
            bg=self.COLORS["surface"],
            fg=self.COLORS["fg"],
            relief=tk.FLAT, padx=4,
        )
        self.long_mem_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # Skills tab
        skills_tab = tk.Frame(notebook, bg=self.COLORS["bg"])
        notebook.add(skills_tab, text="🛠 スキル")

        self.skills_text = scrolledtext.ScrolledText(
            skills_tab, wrap=tk.WORD,
            font=self.font_small,
            bg=self.COLORS["surface"],
            fg=self.COLORS["fg"],
            relief=tk.FLAT, padx=4,
        )
        self.skills_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Stats tab
        stats_tab = tk.Frame(notebook, bg=self.COLORS["bg"])
        notebook.add(stats_tab, text="📊 統計")

        self.stats_text = scrolledtext.ScrolledText(
            stats_tab, wrap=tk.WORD,
            font=self.font_mono,
            bg=self.COLORS["surface"],
            fg=self.COLORS["fg"],
            relief=tk.FLAT, padx=4,
        )
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Jobs status tab
        jobs_tab = tk.Frame(notebook, bg=self.COLORS["bg"])
        notebook.add(jobs_tab, text="⚙ ジョブ")

        tk.Label(
            jobs_tab, text="実行中 / 直近のジョブ",
            font=self.font_small, bg=self.COLORS["bg"], fg=self.COLORS["green"],
        ).pack(anchor=tk.W, padx=5, pady=(5, 0))

        self.jobs_status_text = scrolledtext.ScrolledText(
            jobs_tab, wrap=tk.WORD,
            font=self.font_mono,
            bg=self.COLORS["surface"],
            fg=self.COLORS["fg"],
            relief=tk.FLAT, padx=4,
        )
        self.jobs_status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Abort job button
        tk.Button(
            jobs_tab,
            text="⏹ 実行中ジョブを中断",
            font=self.font_normal,
            bg=self.COLORS["button_stop"],
            fg=self.COLORS["bg"],
            relief=tk.FLAT, padx=8, pady=3,
            command=self._abort_job,
        ).pack(pady=(0, 5))

        # ── Status bar ─────────────────────────────────────────────────────
        self.status_bar = tk.Label(
            self.root,
            text="Ready",
            font=self.font_small,
            bg=self.COLORS["surface"],
            fg=self.COLORS["fg"],
            anchor=tk.W,
            padx=10,
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _labeled_frame(self, parent, title: str) -> tk.Frame:
        """Create a labeled frame widget."""
        outer = tk.Frame(parent, bg=self.COLORS["bg"])
        tk.Label(
            outer, text=title,
            font=self.font_small,
            bg=self.COLORS["bg"],
            fg=self.COLORS["accent"],
        ).pack(anchor=tk.W, pady=(2, 0))
        inner = tk.Frame(outer, bg=self.COLORS["surface"], padx=4, pady=4)
        inner.pack(fill=tk.BOTH, expand=True)
        return inner

    # ─── Event handlers ───────────────────────────────────────────────────

    def _toggle_capture(self):
        if not self._orchestrator:
            messagebox.showerror("エラー", "システムが初期化されていません。")
            return

        if self._running:
            self._orchestrator.stop()
            self._running = False
            self.start_btn.config(
                text="▶ スタート",
                bg=self.COLORS["button_start"],
            )
            self.status_dot.config(fg=self.COLORS["red"])
            self.status_label.config(text="停止中")
        else:
            # Apply settings
            config.CAPTURE_MODE = self.mode_var.get()
            config.SCREENSHOT_INTERVAL_SECONDS = self.interval_var.get()
            self._orchestrator.capture.mode = config.CAPTURE_MODE
            self._orchestrator.capture._screenshot_capture.interval = (
                config.SCREENSHOT_INTERVAL_SECONDS
            )

            self._orchestrator.start()
            self._running = True
            self.start_btn.config(
                text="⏹ ストップ",
                bg=self.COLORS["button_stop"],
            )
            self.status_dot.config(fg=self.COLORS["green"])
            self.status_label.config(text="稼働中")

    def _capture_now(self):
        if not self._orchestrator:
            return
        threading.Thread(
            target=lambda: self._orchestrator.capture_now(),
            daemon=True,
        ).start()
        self._on_status("手動キャプチャ実行中...")

    def _run_cleanup(self):
        if not self._orchestrator:
            return
        threading.Thread(
            target=self._do_cleanup,
            daemon=True,
        ).start()

    def _do_cleanup(self):
        stats = self._orchestrator.cleanup.run_now()
        self._on_status(
            f"クリーンアップ完了: {stats['deleted']}件削除、{stats['freed_mb']:.1f}MB解放"
        )

    def _export_memory(self):
        if not self._orchestrator:
            return
        report = self._orchestrator.memory.export_text_report()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(config.LOGS_DIR, f"memory_report_{timestamp}.txt")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report)
            self._on_status(f"メモリレポート保存: {filepath}")
        except Exception as e:
            self._on_status(f"保存エラー: {e}")

    def _on_mode_change(self):
        """Update UI hint when mode changes."""
        if self._input_mode.get() == "computer_use":
            self.instruction_entry.config(
                fg=self.COLORS["yellow"],
            )
        else:
            self.instruction_entry.config(
                fg=self.COLORS["fg"],
            )

    def _send_instruction(self):
        instruction = self.instruction_entry.get().strip()
        if not instruction:
            return

        self.instruction_entry.delete(0, tk.END)
        self._append_analysis(
            f"\n{'='*40}\n"
            f"[指示] {instruction}\n"
        )

        if not self._orchestrator:
            self._append_analysis("エラー: システムが初期化されていません\n")
            return

        self.abort_btn.config(state=tk.NORMAL)

        mode = self._input_mode.get()
        if mode == "computer_use":
            self._start_computer_use(instruction)
        else:
            threading.Thread(
                target=self._process_instruction,
                args=(instruction,),
                daemon=True,
            ).start()

    def _start_computer_use(self, goal: str):
        """Start the Computer Use agentic loop."""
        self._append_analysis("[Computer Use] 開始...\n")
        # Switch to Thinking tab
        self.root.after(0, lambda: self._notebook.select(0))

        self._orchestrator.execute_with_computer_use(
            goal=goal,
            on_thinking=self._on_cu_thinking,
            on_cu_action=self._on_cu_action_event,
            on_complete=self._on_cu_complete,
        )

    def _on_cu_thinking(self, text: str):
        """Called when Claude emits thinking content."""
        def update():
            self.thinking_text.insert(tk.END, f"\n{'─'*40}\n{text}\n")
            self.thinking_text.see(tk.END)
            # Keep max 200 lines
            lines = int(self.thinking_text.index(tk.END).split(".")[0])
            if lines > 200:
                self.thinking_text.delete("1.0", f"{lines-200}.0")
        self.root.after(0, update)

    def _on_cu_action_event(self, action: dict, success: bool, msg: str):
        """Called after each Computer Use action."""
        icon = "✓" if success else "✗"
        act_type = action.get("action", "")
        line = f"  {icon} {act_type}: {msg}\n"
        def update():
            self.cu_action_text.insert(tk.END, line)
            self.cu_action_text.see(tk.END)
            self._append_analysis(line)
        self.root.after(0, update)

    def _on_cu_complete(self, summary: str):
        """Called when Computer Use agent finishes."""
        def update():
            self._append_analysis(f"\n[Computer Use 完了] {summary}\n")
            self.abort_btn.config(state=tk.DISABLED)
        self.root.after(0, update)

    def _abort_execution(self):
        if self._orchestrator:
            self._orchestrator.abort_execution()
            self._orchestrator.abort_computer_use()
        self.abort_btn.config(state=tk.DISABLED)

    def _process_instruction(self, instruction: str):
        auto_exec = self.auto_exec_var.get()
        result = self._orchestrator.execute_instruction(
            instruction,
            auto_execute=auto_exec,
        )
        steps = result.get("steps", [])
        actions = result.get("actions", [])
        results = result.get("results", [])
        skill = result.get("skill_name", "")
        success = result.get("success_count", 0)
        total = result.get("total_actions", 0)

        output = []
        if skill:
            output.append(f"[スキル記録] {skill}")
        output.append("[実行手順]")
        for i, step in enumerate(steps, 1):
            output.append(f"  {i}. {step}")

        if actions:
            output.append(f"[アクション: {success}/{total} 成功]")
            for r in results:
                icon = "✓" if r.get("success") else "✗"
                act = r.get("action", {})
                msg = r.get("message", "")
                output.append(f"  {icon} [{act.get('type','')}] {msg}")

        self.root.after(0, self._append_analysis, "\n".join(output) + "\n")
        self.root.after(0, lambda: self.abort_btn.config(state=tk.DISABLED))

    # ─── Orchestrator callbacks ───────────────────────────────────────────

    def _on_status(self, message: str):
        """Called when orchestrator sends a status update."""
        self.root.after(0, self._update_status_bar, message)

    def _on_recommendation(self, text: str):
        """Called when AI generates a recommendation."""
        self.root.after(0, self._update_recommendation, text)

    def _on_analysis(self, analysis: dict):
        """Called when analysis is complete."""
        self.root.after(0, self._display_analysis, analysis)

    def _on_capture(self, paths: list, timestamp: datetime.datetime):
        """Called when new capture is saved."""
        ts = timestamp.strftime("%H:%M:%S")
        msg = f"[{ts}] キャプチャ: {len(paths)}件"
        self.root.after(0, self._update_status_bar, msg)

    def _on_action(self, result):
        """Called after each individual action is executed."""
        icon = "✓" if result.success else "✗"
        act_type = result.action.get("type", "")
        msg = result.message
        line = f"  {icon} {act_type}: {msg}\n"
        self.root.after(0, self._append_analysis, line)

    def _on_job_start(self, job, run):
        def update():
            self._append_job_status(
                f"\n{'='*36}\n▶ ジョブ開始: {job.name}\n"
                f"  ID: {run.id}  トリガー: {run.triggered_by}\n"
            )
        self.root.after(0, update)

    def _on_job_done(self, job, run):
        icons = {"completed": "✓", "failed": "✗", "aborted": "⏹"}
        icon = icons.get(run.status, "?")
        completed_tasks = sum(1 for r in run.task_results if r.status == "completed")
        def update():
            self._append_job_status(
                f"{icon} ジョブ完了: {job.name} → {run.status} "
                f"({completed_tasks}/{len(run.task_results)} タスク)\n"
            )
            self._refresh_jobs_status()
        self.root.after(0, update)

    def _on_task_start(self, task, task_result):
        def update():
            self._append_job_status(f"  → タスク: {task.name}\n")
        self.root.after(0, update)

    def _on_task_done(self, task, task_result):
        icon = "✓" if task_result.status == "completed" else "✗"
        def update():
            self._append_job_status(
                f"  {icon} {task.name}: {task_result.summary[:80]}\n"
            )
        self.root.after(0, update)

    def _abort_job(self):
        if self._orchestrator:
            self._orchestrator.abort_job()

    def _open_job_manager(self):
        if not self._orchestrator:
            messagebox.showerror("エラー", "システムが初期化されていません。")
            return
        JobManagerWindow(self.root, self._orchestrator, self.COLORS, self.font_normal, self.font_small, self.font_bold, self.font_mono)

    # ─── UI update methods ────────────────────────────────────────────────

    def _update_status_bar(self, message: str):
        self.status_bar.config(text=message)

    def _update_recommendation(self, text: str):
        self.recommendation_text.config(state=tk.NORMAL)
        self.recommendation_text.delete("1.0", tk.END)
        self.recommendation_text.insert("1.0", text)
        self.recommendation_text.config(state=tk.DISABLED)

    def _display_analysis(self, analysis: dict):
        ts = analysis.get("timestamp", "")[:16].replace("T", " ")
        state = analysis.get("state", "")
        purpose = analysis.get("purpose", "")
        suggestion = analysis.get("suggestion", "")

        line = (
            f"[{ts}] {state}"
            + (f" | 目的:{purpose}" if purpose else "")
            + (f"\n  → {suggestion}" if suggestion else "")
            + "\n"
        )
        self._append_analysis(line)

    def _append_analysis(self, text: str):
        self.analysis_text.insert(tk.END, text)
        self.analysis_text.see(tk.END)
        # Keep max 500 lines
        lines = int(self.analysis_text.index(tk.END).split(".")[0])
        if lines > 500:
            self.analysis_text.delete("1.0", f"{lines - 500}.0")

    def _append_job_status(self, text: str):
        self.jobs_status_text.insert(tk.END, text)
        self.jobs_status_text.see(tk.END)
        lines = int(self.jobs_status_text.index(tk.END).split(".")[0])
        if lines > 300:
            self.jobs_status_text.delete("1.0", f"{lines - 300}.0")

    def _refresh_jobs_status(self):
        if not self._orchestrator:
            return
        runs = self._orchestrator.task_manager.get_recent_runs(limit=10)
        lines = ["直近のジョブ実行:\n"]
        for run in runs:
            icons = {"completed": "✓", "failed": "✗", "aborted": "⏹", "running": "▶"}
            icon = icons.get(run.status, "?")
            ts = run.started_at[:16].replace("T", " ")
            lines.append(f"{icon} [{ts}] {run.job_name} ({run.status})")
        # Don't clear the log area - this is just for the initial load
        # The live appended text is more useful

    def _refresh_ui(self):
        """Periodically refresh memory and stats panels."""
        if self._orchestrator:
            self._refresh_memory()
            self._refresh_skills()
            self._refresh_stats()
        self.root.after(10000, self._refresh_ui)  # Every 10s

    def _refresh_memory(self):
        if not self._orchestrator:
            return

        # Short-term
        short = self._orchestrator.memory.short_term.get_recent(15)
        self.short_mem_text.config(state=tk.NORMAL)
        self.short_mem_text.delete("1.0", tk.END)
        for entry in short:
            ts = entry.get("timestamp", "")[:16].replace("T", " ")
            content = entry.get("content", "")[:120]
            self.short_mem_text.insert(
                tk.END,
                f"[{ts}]\n{content}\n\n"
            )
        self.short_mem_text.config(state=tk.DISABLED)

        # Long-term
        long = self._orchestrator.memory.long_term.get_recent(15)
        self.long_mem_text.config(state=tk.NORMAL)
        self.long_mem_text.delete("1.0", tk.END)
        for entry in long:
            ts = entry.get("timestamp", "")[:16].replace("T", " ")
            content = entry.get("content", "")[:120]
            count = entry.get("count", 1)
            self.long_mem_text.insert(
                tk.END,
                f"[{ts}] (×{count})\n{content}\n\n"
            )
        self.long_mem_text.config(state=tk.DISABLED)

    def _refresh_skills(self):
        if not self._orchestrator:
            return

        skills = self._orchestrator.skills.get_all()
        self.skills_text.config(state=tk.NORMAL)
        self.skills_text.delete("1.0", tk.END)

        if not skills:
            self.skills_text.insert(tk.END, "スキルはまだ記録されていません\n")
        else:
            for skill in skills:
                self.skills_text.insert(
                    tk.END,
                    f"[{skill['category']}] {skill['name']} (×{skill['use_count']})\n"
                    f"  {skill['description'][:100]}\n\n"
                )
        self.skills_text.config(state=tk.DISABLED)

    def _refresh_stats(self):
        if not self._orchestrator:
            return

        stats = self._orchestrator.get_stats()
        mem = stats.get("memory", {})
        disk = stats.get("disk", {})

        lines = [
            f"稼働状態: {'稼働中' if stats['running'] else '停止中'}",
            f"モード: {stats['capture_mode']}",
            f"",
            f"キャプチャ数: {stats['screenshots_captured']}",
            f"分析回数: {stats['analyses_done']}",
            f"レコメンド数: {stats['recommendations_sent']}",
            f"スキル数: {stats['skills_recorded']}",
            f"",
            f"短期メモリ: {mem.get('short_term_count',0)}/{config.MAX_MEMORY_ENTRIES}",
            f"長期メモリ: {mem.get('long_term_count',0)}/{config.MAX_MEMORY_ENTRIES}",
            f"",
            "ディスク使用量:",
        ]
        for k, v in disk.items():
            if isinstance(v, dict):
                lines.append(f"  {k}: {v['files']}件 ({v['size_mb']:.1f}MB)")

        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete("1.0", tk.END)
        self.stats_text.insert("1.0", "\n".join(lines))
        self.stats_text.config(state=tk.DISABLED)

    def run(self):
        """Start the GUI event loop."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self._running and self._orchestrator:
            if messagebox.askyesno(
                "確認",
                "システムが稼働中です。終了しますか？"
            ):
                self._orchestrator.stop()
                self.root.destroy()
        else:
            if self._orchestrator:
                self._orchestrator.stop()
            self.root.destroy()


# ──────────────────────────────────────────────────────────────────────────────
# Job Manager Window
# ──────────────────────────────────────────────────────────────────────────────

class JobManagerWindow:
    """
    Toplevel window for creating, editing, and running Jobs and Tasks.

    Layout (left → right):
      [Task list]  [Job list]  [Job detail / run history]
    """

    TRIGGER_LABELS = {
        "manual":  "手動のみ",
        "interval": "インターバル (N分ごと)",
        "daily":    "毎日 HH:MM",
        "weekday":  "曜日指定 HH:MM",
    }
    WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]

    def __init__(self, parent, orchestrator, colors, font_normal, font_small, font_bold, font_mono):
        self._orch = orchestrator
        self._tm = orchestrator.task_manager
        self._colors = colors
        self._fn = font_normal
        self._fs = font_small
        self._fb = font_bold
        self._fm = font_mono

        self.win = tk.Toplevel(parent)
        self.win.title("ジョブ管理")
        self.win.geometry("1000x650")
        self.win.configure(bg=colors["bg"])
        self.win.minsize(800, 500)

        self._sel_job_id = None
        self._sel_task_id = None

        self._build()
        self._refresh()

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build(self):
        C = self._colors

        # ── Top button bar ────────────────────────────────────────────────
        bar = tk.Frame(self.win, bg=C["surface"], pady=4)
        bar.pack(fill=tk.X, padx=8, pady=(8, 4))

        def btn(text, color, cmd, side=tk.LEFT):
            tk.Button(
                bar, text=text, font=self._fs,
                bg=color, fg=C["bg"],
                relief=tk.FLAT, padx=8, pady=3,
                command=cmd,
            ).pack(side=side, padx=3)

        btn("＋ タスク追加", C["accent"], self._add_task)
        btn("✎ タスク編集", C["surface2"], self._edit_task)
        btn("✕ タスク削除", C["red"], self._delete_task)
        tk.Label(bar, text="│", bg=C["surface"], fg=C["surface2"]).pack(side=tk.LEFT, padx=4)
        btn("＋ ジョブ追加", C["green"], self._add_job)
        btn("✎ ジョブ編集", C["surface2"], self._edit_job)
        btn("✕ ジョブ削除", C["red"], self._delete_job)
        tk.Label(bar, text="│", bg=C["surface"], fg=C["surface2"]).pack(side=tk.LEFT, padx=4)
        btn("▶ 今すぐ実行", C["yellow"], self._run_job_now)
        btn("⏹ 中断", C["button_stop"], self._abort_job, side=tk.RIGHT)
        btn("↻ 更新", C["surface2"], self._refresh, side=tk.RIGHT)

        # ── Main area ─────────────────────────────────────────────────────
        pane = tk.Frame(self.win, bg=C["bg"])
        pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Task panel (left)
        task_panel = tk.Frame(pane, bg=C["bg"], width=230)
        task_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 4))
        task_panel.pack_propagate(False)

        tk.Label(task_panel, text="タスク一覧", font=self._fs,
                 bg=C["bg"], fg=C["accent"]).pack(anchor=tk.W)

        self._task_lb = tk.Listbox(
            task_panel, font=self._fs,
            bg=C["surface"], fg=C["fg"],
            selectbackground=C["accent"], selectforeground=C["bg"],
            relief=tk.FLAT, activestyle="none",
        )
        self._task_lb.pack(fill=tk.BOTH, expand=True)
        self._task_lb.bind("<<ListboxSelect>>", self._on_task_select)

        # Job panel (center)
        job_panel = tk.Frame(pane, bg=C["bg"], width=260)
        job_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 4))
        job_panel.pack_propagate(False)

        tk.Label(job_panel, text="ジョブ一覧", font=self._fs,
                 bg=C["bg"], fg=C["green"]).pack(anchor=tk.W)

        self._job_lb = tk.Listbox(
            job_panel, font=self._fs,
            bg=C["surface"], fg=C["fg"],
            selectbackground=C["green"], selectforeground=C["bg"],
            relief=tk.FLAT, activestyle="none",
        )
        self._job_lb.pack(fill=tk.BOTH, expand=True)
        self._job_lb.bind("<<ListboxSelect>>", self._on_job_select)

        # Detail panel (right)
        detail_panel = tk.Frame(pane, bg=C["bg"])
        detail_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(detail_panel, text="ジョブ詳細 / 実行履歴", font=self._fs,
                 bg=C["bg"], fg=C["yellow"]).pack(anchor=tk.W)

        self._detail_text = scrolledtext.ScrolledText(
            detail_panel, wrap=tk.WORD,
            font=self._fm,
            bg=C["surface"], fg=C["fg"],
            relief=tk.FLAT, padx=6, pady=4,
        )
        self._detail_text.pack(fill=tk.BOTH, expand=True)

    # ── Refresh ───────────────────────────────────────────────────────────

    def _refresh(self):
        self._refresh_tasks()
        self._refresh_jobs()
        self._refresh_detail()

    def _refresh_tasks(self):
        self._task_lb.delete(0, tk.END)
        self._task_ids = []
        for t in self._tm.list_tasks():
            label = ("✓ " if t.enabled else "✗ ") + t.name
            self._task_lb.insert(tk.END, label)
            self._task_ids.append(t.id)

    def _refresh_jobs(self):
        self._job_lb.delete(0, tk.END)
        self._job_ids = []
        status_icons = {"completed": "✓", "failed": "✗", "running": "▶", "aborted": "⏹", "": "○"}
        for j in self._tm.list_jobs():
            icon = status_icons.get(j.last_run_status, "○")
            ena = "" if j.enabled else " [停止]"
            label = f"{icon} {j.name}{ena}"
            self._job_lb.insert(tk.END, label)
            self._job_ids.append(j.id)

    def _refresh_detail(self):
        self._detail_text.delete("1.0", tk.END)
        if not self._sel_job_id:
            self._detail_text.insert(tk.END, "ジョブを選択してください\n")
            return

        job = self._tm.get_job(self._sel_job_id)
        if not job:
            return

        sched = self._orch.job_scheduler.next_run_str(job)
        tasks = self._tm.get_job_tasks(job)

        lines = [
            f"ジョブ: {job.name}",
            f"説明: {job.description or '（なし）'}",
            f"スケジュール: {sched}",
            f"失敗時停止: {'はい' if job.stop_on_task_failure else 'いいえ'}",
            f"最終実行: {job.last_run_at[:16].replace('T',' ') if job.last_run_at else '未実行'}",
            f"最終状態: {job.last_run_status or '―'}",
            f"",
            f"タスク ({len(tasks)}件):",
        ]
        for i, t in enumerate(tasks, 1):
            ena = "✓" if t.enabled else "✗"
            lines.append(f"  {i}. [{ena}] {t.name}  ({t.mode}, timeout={t.timeout_seconds}s)")
            if t.goal:
                lines.append(f"     目標: {t.goal[:80]}")

        lines.append("")
        lines.append("── 実行履歴 (直近10件) ──")
        runs = self._tm.get_recent_runs(self._sel_job_id, limit=10)
        if not runs:
            lines.append("  （履歴なし）")
        else:
            for run in runs:
                ts = run.started_at[:16].replace("T", " ")
                icon = {"completed": "✓", "failed": "✗", "aborted": "⏹", "running": "▶"}.get(run.status, "?")
                ok = sum(1 for r in run.task_results if r.status == "completed")
                total = len(run.task_results)
                lines.append(f"  {icon} [{ts}] {run.status}  ({ok}/{total} タスク, by={run.triggered_by})")
                for tr in run.task_results:
                    s_icon = {"completed": "✓", "failed": "✗", "skipped": "—"}.get(tr.status, "?")
                    lines.append(f"      {s_icon} {tr.task_name}: {tr.summary[:60]}")

        self._detail_text.insert("1.0", "\n".join(lines))

    # ── Selection ─────────────────────────────────────────────────────────

    def _on_task_select(self, _event=None):
        sel = self._task_lb.curselection()
        if sel and sel[0] < len(self._task_ids):
            self._sel_task_id = self._task_ids[sel[0]]

    def _on_job_select(self, _event=None):
        sel = self._job_lb.curselection()
        if sel and sel[0] < len(self._job_ids):
            self._sel_job_id = self._job_ids[sel[0]]
            self._refresh_detail()

    # ── Task CRUD dialogs ─────────────────────────────────────────────────

    def _add_task(self):
        from core.task_manager import Task
        self._task_dialog(Task())

    def _edit_task(self):
        if not self._sel_task_id:
            messagebox.showinfo("選択", "タスクを選択してください")
            return
        task = self._tm.get_task(self._sel_task_id)
        if task:
            self._task_dialog(task)

    def _delete_task(self):
        if not self._sel_task_id:
            messagebox.showinfo("選択", "タスクを選択してください")
            return
        task = self._tm.get_task(self._sel_task_id)
        if task and messagebox.askyesno("削除確認", f"タスク「{task.name}」を削除しますか？"):
            self._tm.delete_task(self._sel_task_id)
            self._sel_task_id = None
            self._refresh()

    def _task_dialog(self, task):
        """Show Task create/edit dialog."""
        C = self._colors
        dlg = tk.Toplevel(self.win)
        dlg.title("タスク編集")
        dlg.geometry("540x420")
        dlg.configure(bg=C["bg"])
        dlg.grab_set()

        fields = {}

        def row(label, widget):
            f = tk.Frame(dlg, bg=C["bg"])
            f.pack(fill=tk.X, padx=16, pady=3)
            tk.Label(f, text=label, width=14, anchor=tk.W, font=self._fs,
                     bg=C["bg"], fg=C["fg"]).pack(side=tk.LEFT)
            widget(f).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def entry_field(name, initial=""):
            def make(parent):
                v = tk.StringVar(value=initial)
                fields[name] = v
                return tk.Entry(parent, textvariable=v, font=self._fs,
                                bg=C["surface2"], fg=C["fg"],
                                insertbackground=C["fg"], relief=tk.FLAT)
            return make

        row("タスク名 *", entry_field("name", task.name))
        row("説明", entry_field("description", task.description))

        # Goal (multiline)
        gf = tk.Frame(dlg, bg=C["bg"])
        gf.pack(fill=tk.X, padx=16, pady=3)
        tk.Label(gf, text="目標（AI指示）*", width=14, anchor=tk.NW, font=self._fs,
                 bg=C["bg"], fg=C["yellow"]).pack(side=tk.LEFT, anchor=tk.N)
        goal_text = tk.Text(gf, height=4, font=self._fs,
                            bg=C["surface2"], fg=C["yellow"],
                            insertbackground=C["fg"], relief=tk.FLAT, wrap=tk.WORD)
        goal_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        goal_text.insert("1.0", task.goal)

        # Mode
        mode_v = tk.StringVar(value=task.mode)
        fields["mode"] = mode_v
        mf = tk.Frame(dlg, bg=C["bg"])
        mf.pack(fill=tk.X, padx=16, pady=3)
        tk.Label(mf, text="実行モード", width=14, anchor=tk.W, font=self._fs,
                 bg=C["bg"], fg=C["fg"]).pack(side=tk.LEFT)
        for val, lbl in [("computer_use", "★ Computer Use"), ("standard", "標準")]:
            tk.Radiobutton(mf, text=lbl, variable=mode_v, value=val,
                           font=self._fs, bg=C["bg"], fg=C["fg"],
                           selectcolor=C["surface2"], relief=tk.FLAT,
                           activebackground=C["bg"], activeforeground=C["fg"]
                           ).pack(side=tk.LEFT, padx=4)

        row("タイムアウト(秒)", entry_field("timeout", str(task.timeout_seconds)))
        row("リトライ回数", entry_field("retry", str(task.retry_count)))

        enabled_v = tk.BooleanVar(value=task.enabled)
        ef = tk.Frame(dlg, bg=C["bg"])
        ef.pack(fill=tk.X, padx=16, pady=3)
        tk.Checkbutton(ef, text="有効", variable=enabled_v, font=self._fn,
                       bg=C["bg"], fg=C["fg"], selectcolor=C["surface2"],
                       activebackground=C["bg"], activeforeground=C["fg"], relief=tk.FLAT,
                       ).pack(side=tk.LEFT)

        def save():
            name = fields["name"].get().strip()
            if not name:
                messagebox.showwarning("入力エラー", "タスク名を入力してください", parent=dlg)
                return
            goal = goal_text.get("1.0", tk.END).strip()
            if not goal:
                messagebox.showwarning("入力エラー", "目標（AI指示）を入力してください", parent=dlg)
                return
            try:
                timeout = int(fields["timeout"].get())
                retry = int(fields["retry"].get())
            except ValueError:
                messagebox.showwarning("入力エラー", "数値を正しく入力してください", parent=dlg)
                return

            task.name = name
            task.description = fields["description"].get().strip()
            task.goal = goal
            task.mode = fields["mode"].get()
            task.timeout_seconds = timeout
            task.retry_count = retry
            task.enabled = enabled_v.get()

            if task.id in self._tm._tasks:
                self._tm.update_task(task)
            else:
                self._tm.add_task(task)
            dlg.destroy()
            self._refresh()

        bf = tk.Frame(dlg, bg=C["bg"])
        bf.pack(pady=8)
        tk.Button(bf, text="保存", font=self._fb, bg=C["green"], fg=C["bg"],
                  relief=tk.FLAT, padx=16, command=save).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="キャンセル", font=self._fn, bg=C["surface2"], fg=C["fg"],
                  relief=tk.FLAT, padx=12, command=dlg.destroy).pack(side=tk.LEFT)

    # ── Job CRUD dialogs ──────────────────────────────────────────────────

    def _add_job(self):
        from core.task_manager import Job
        self._job_dialog(Job())

    def _edit_job(self):
        if not self._sel_job_id:
            messagebox.showinfo("選択", "ジョブを選択してください")
            return
        job = self._tm.get_job(self._sel_job_id)
        if job:
            self._job_dialog(job)

    def _delete_job(self):
        if not self._sel_job_id:
            messagebox.showinfo("選択", "ジョブを選択してください")
            return
        job = self._tm.get_job(self._sel_job_id)
        if job and messagebox.askyesno("削除確認", f"ジョブ「{job.name}」を削除しますか？"):
            self._tm.delete_job(self._sel_job_id)
            self._sel_job_id = None
            self._refresh()

    def _job_dialog(self, job):
        """Show Job create/edit dialog."""
        C = self._colors
        dlg = tk.Toplevel(self.win)
        dlg.title("ジョブ編集")
        dlg.geometry("580x560")
        dlg.configure(bg=C["bg"])
        dlg.grab_set()

        def lbl_entry(parent, label, initial="", fg=None):
            f = tk.Frame(parent, bg=C["bg"])
            f.pack(fill=tk.X, padx=16, pady=3)
            tk.Label(f, text=label, width=16, anchor=tk.W, font=self._fs,
                     bg=C["bg"], fg=fg or C["fg"]).pack(side=tk.LEFT)
            v = tk.StringVar(value=initial)
            tk.Entry(f, textvariable=v, font=self._fs,
                     bg=C["surface2"], fg=C["fg"],
                     insertbackground=C["fg"], relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True)
            return v

        name_v = lbl_entry(dlg, "ジョブ名 *", job.name)
        desc_v = lbl_entry(dlg, "説明", job.description)

        # Trigger type
        tf = tk.Frame(dlg, bg=C["bg"])
        tf.pack(fill=tk.X, padx=16, pady=3)
        tk.Label(tf, text="トリガー", width=16, anchor=tk.W, font=self._fs,
                 bg=C["bg"], fg=C["accent"]).pack(side=tk.LEFT)
        trig_v = tk.StringVar(value=job.trigger.type)
        trig_cb = ttk.Combobox(tf, textvariable=trig_v,
                               values=list(self.TRIGGER_LABELS.keys()),
                               width=20, state="readonly")
        trig_cb.pack(side=tk.LEFT)

        # Trigger value (time or interval)
        val_v = lbl_entry(dlg, "値 (例: 09:00 / 30)", job.trigger.value)
        val_v.set(job.trigger.value)

        # Weekday checkboxes
        wd_frame = tk.Frame(dlg, bg=C["bg"])
        wd_frame.pack(fill=tk.X, padx=16, pady=3)
        tk.Label(wd_frame, text="曜日 (weekday)", width=16, anchor=tk.W,
                 font=self._fs, bg=C["bg"], fg=C["fg"]).pack(side=tk.LEFT)
        wd_vars = {}
        for wd, jp in zip(self.WEEKDAYS, self.WEEKDAY_JP):
            v = tk.BooleanVar(value=wd in (job.trigger.days or []))
            wd_vars[wd] = v
            tk.Checkbutton(wd_frame, text=jp, variable=v, font=self._fs,
                           bg=C["bg"], fg=C["fg"], selectcolor=C["surface2"],
                           activebackground=C["bg"], relief=tk.FLAT).pack(side=tk.LEFT)

        # Task selection
        tk.Label(dlg, text="タスクを選択 (順序=上から)", font=self._fs,
                 bg=C["bg"], fg=C["accent"]).pack(anchor=tk.W, padx=16, pady=(8, 0))

        task_list_frame = tk.Frame(dlg, bg=C["bg"])
        task_list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=3)

        all_tasks = self._tm.list_tasks()
        task_lb = tk.Listbox(
            task_list_frame, font=self._fs,
            bg=C["surface"], fg=C["fg"],
            selectbackground=C["accent"], selectforeground=C["bg"],
            relief=tk.FLAT, activestyle="none",
            selectmode=tk.MULTIPLE, height=6,
        )
        task_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        task_id_map = []
        for t in all_tasks:
            task_lb.insert(tk.END, t.name)
            task_id_map.append(t.id)

        # Pre-select tasks already in job (in order)
        for i, tid in enumerate(task_id_map):
            if tid in job.task_ids:
                task_lb.selection_set(i)

        # Move up/down buttons
        order_btns = tk.Frame(task_list_frame, bg=C["bg"])
        order_btns.pack(side=tk.LEFT, padx=4)
        tk.Button(order_btns, text="↑", font=self._fn, bg=C["surface2"], fg=C["fg"],
                  relief=tk.FLAT, width=2,
                  command=lambda: self._move_task_up(task_lb)).pack(pady=2)
        tk.Button(order_btns, text="↓", font=self._fn, bg=C["surface2"], fg=C["fg"],
                  relief=tk.FLAT, width=2,
                  command=lambda: self._move_task_down(task_lb)).pack(pady=2)

        # Stop on failure
        stop_v = tk.BooleanVar(value=job.stop_on_task_failure)
        sf = tk.Frame(dlg, bg=C["bg"])
        sf.pack(fill=tk.X, padx=16, pady=3)
        tk.Checkbutton(sf, text="タスク失敗時に停止", variable=stop_v, font=self._fn,
                       bg=C["bg"], fg=C["fg"], selectcolor=C["surface2"],
                       activebackground=C["bg"], relief=tk.FLAT).pack(side=tk.LEFT)

        enabled_v = tk.BooleanVar(value=job.enabled)
        tk.Checkbutton(sf, text="有効", variable=enabled_v, font=self._fn,
                       bg=C["bg"], fg=C["fg"], selectcolor=C["surface2"],
                       activebackground=C["bg"], relief=tk.FLAT).pack(side=tk.LEFT, padx=12)

        def save():
            name = name_v.get().strip()
            if not name:
                messagebox.showwarning("入力エラー", "ジョブ名を入力してください", parent=dlg)
                return

            # Collect selected tasks in Listbox order
            sel_indices = list(task_lb.curselection())
            selected_task_ids = [task_id_map[i] for i in sel_indices]

            from core.task_manager import Trigger
            days = [wd for wd, v in wd_vars.items() if v.get()]

            job.name = name
            job.description = desc_v.get().strip()
            job.trigger = Trigger(
                type=trig_v.get(),
                value=val_v.get().strip(),
                days=days,
            )
            job.task_ids = selected_task_ids
            job.stop_on_task_failure = stop_v.get()
            job.enabled = enabled_v.get()

            if job.id in self._tm._jobs:
                self._tm.update_job(job)
            else:
                self._tm.add_job(job)
            dlg.destroy()
            self._refresh()

        bf = tk.Frame(dlg, bg=C["bg"])
        bf.pack(pady=6)
        tk.Button(bf, text="保存", font=self._fb, bg=C["green"], fg=C["bg"],
                  relief=tk.FLAT, padx=16, command=save).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="キャンセル", font=self._fn, bg=C["surface2"], fg=C["fg"],
                  relief=tk.FLAT, padx=12, command=dlg.destroy).pack(side=tk.LEFT)

    def _move_task_up(self, lb):
        sel = lb.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        text = lb.get(i)
        lb.delete(i)
        lb.insert(i - 1, text)
        lb.selection_set(i - 1)

    def _move_task_down(self, lb):
        sel = lb.curselection()
        if not sel or sel[0] >= lb.size() - 1:
            return
        i = sel[0]
        text = lb.get(i)
        lb.delete(i)
        lb.insert(i + 1, text)
        lb.selection_set(i + 1)

    # ── Run / Abort ───────────────────────────────────────────────────────

    def _run_job_now(self):
        if not self._sel_job_id:
            messagebox.showinfo("選択", "ジョブを選択してください")
            return
        job = self._tm.get_job(self._sel_job_id)
        if not job:
            return
        self._orch.run_job(job, triggered_by="manual")
        messagebox.showinfo("実行開始", f"ジョブ「{job.name}」を開始しました\nメインウィンドウの「⚙ ジョブ」タブで進捗を確認できます")
        self._refresh()

    def _abort_job(self):
        self._orch.abort_job()
        messagebox.showinfo("中断", "実行中のジョブを中断しました")
