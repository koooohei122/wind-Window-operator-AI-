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
