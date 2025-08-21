#!/usr/bin/env python3
"""
Theme Preview - Shows the themed interface without requiring Jira credentials
"""
import tkinter as tk
from tkinter import ttk

class ThemePreview(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Jira Metrics - Theme Preview")
        self.geometry("800x600")
        self.minsize(700, 500)
        
        # Configure modern theme and styling
        self._setup_theme()
        
        # Create notebook (tabs)
        nb = ttk.Notebook(self)
        nb.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        
        # Create sample tabs
        self._create_search_tab(nb)
        self._create_config_tab(nb)
        
        # Create log console
        log_frame = ttk.LabelFrame(self, text="Log Console", padding=8)
        log_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        
        log_text = tk.Text(log_frame, height=6,
                          bg='#ffffff', fg='#333333',
                          font=('Consolas', 9), borderwidth=1, relief='solid')
        log_text.grid(row=0, column=0, sticky="nsew")
        
        # Add sample log entries
        log_text.insert("end", "✅ Theme preview loaded successfully\n", "success")
        log_text.insert("end", "ℹ️ This is a preview of the themed interface\n", "info")
        log_text.insert("end", "🔍 Search functionality ready\n", "info")
        log_text.insert("end", "📊 Export options available\n", "info")
        
        log_text.tag_config("success", foreground="#107c10")
        log_text.tag_config("info", foreground="#333333")
        log_text.configure(state="disabled")
        
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

    def _setup_theme(self):
        """Configure modern theme and styling"""
        style = ttk.Style()
        
        # Try to use a modern theme
        available_themes = style.theme_names()
        preferred_themes = ['vista', 'xpnative', 'winnative', 'clam', 'alt', 'default']
        
        selected_theme = 'default'
        for theme in preferred_themes:
            if theme in available_themes:
                selected_theme = theme
                break
        
        style.theme_use(selected_theme)
        
        # Configure colors for a modern look
        bg_color = '#f0f0f0'
        fg_color = '#333333'
        accent_color = '#0078d4'
        hover_color = '#106ebe'
        
        self.configure(bg=bg_color)
        
        # Style configurations
        style.configure('TNotebook', background=bg_color, borderwidth=0)
        style.configure('TNotebook.Tab', padding=[12, 8], focuscolor='none')
        style.configure('TButton', padding=[8, 4], focuscolor='none')
        style.map('TButton', background=[('active', hover_color), ('pressed', accent_color)])
        style.configure('TFrame', background=bg_color)
        style.configure('TLabelFrame', background=bg_color)
        style.configure('TLabel', background=bg_color, foreground=fg_color)
        style.configure('TEntry', fieldbackground='white', borderwidth=1)
        style.configure('Treeview', background='white', foreground=fg_color, 
                       fieldbackground='white', borderwidth=1)
        style.configure('Treeview.Heading', background=bg_color, foreground=fg_color, borderwidth=1)
        style.configure('TProgressbar', background=accent_color, borderwidth=0)

    def _create_search_tab(self, notebook):
        """Create JQL Search tab preview"""
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="JQL Search")
        
        # Search section
        search_frame = ttk.LabelFrame(frame, text="JQL Search", padding=10)
        search_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        ttk.Label(search_frame, text="JQL Query:", font=('Segoe UI', 10)).grid(row=0, column=0, sticky="w", pady=(0, 5))
        jql_entry = ttk.Entry(search_frame, width=80, font=('Segoe UI', 10))
        jql_entry.insert(0, "project = 'DEMO' AND status = 'In Progress'")
        jql_entry.grid(row=1, column=0, sticky="we", pady=(0, 10))
        
        controls_frame = ttk.Frame(search_frame)
        controls_frame.grid(row=2, column=0, sticky="we")
        
        ttk.Button(controls_frame, text="🔍 Search").grid(row=0, column=0, padx=(0, 10))
        ttk.Label(controls_frame, text="Matches: 42", font=('Segoe UI', 10, 'bold')).grid(row=0, column=1, padx=(0, 20))
        
        search_frame.grid_columnconfigure(0, weight=1)
        
        # Export section
        export_frame = ttk.LabelFrame(frame, text="Export Options", padding=10)
        export_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        
        export_buttons_frame = ttk.Frame(export_frame)
        export_buttons_frame.grid(row=0, column=0)
        
        ttk.Button(export_buttons_frame, text="📊 Export CSV").grid(row=0, column=0, padx=(0, 10), pady=5)
        ttk.Button(export_buttons_frame, text="📄 Export JSON").grid(row=0, column=1, padx=(0, 10), pady=5)
        ttk.Button(export_buttons_frame, text="📝 Export Markdown").grid(row=0, column=2, padx=(0, 10), pady=5)
        
        # Progress section
        pb_frame = ttk.LabelFrame(frame, text="Progress", padding=10)
        pb_frame.grid(row=2, column=0, sticky="we")
        
        pb = ttk.Progressbar(pb_frame, orient="horizontal", mode="determinate", value=65)
        pb.grid(row=0, column=0, sticky="we", pady=(0, 5))
        ttk.Label(pb_frame, text="Exporting data... (65%)", font=('Segoe UI', 9)).grid(row=1, column=0, sticky="w")
        
        pb_frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

    def _create_config_tab(self, notebook):
        """Create Configuration tab preview"""
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Configuration")
        
        # Field selection
        fields_frame = ttk.LabelFrame(frame, text="📋 Field Selection", padding=12)
        fields_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        
        load_frame = ttk.Frame(fields_frame)
        load_frame.grid(row=0, column=0, sticky="we", pady=(0, 10))
        
        ttk.Label(load_frame, text="Issue Key:", font=('Segoe UI', 10)).grid(row=0, column=0, sticky="w")
        key_entry = ttk.Entry(load_frame, width=25, font=('Segoe UI', 10))
        key_entry.insert(0, "DEMO-123")
        key_entry.grid(row=0, column=1, sticky="we", padx=(10, 10))
        ttk.Button(load_frame, text="🔄 Load Fields").grid(row=0, column=2)
        load_frame.grid_columnconfigure(1, weight=1)
        
        # Sample treeview
        cols = ("selected", "field", "value")
        tree = ttk.Treeview(fields_frame, columns=cols, show="headings", height=10)
        tree.heading("selected", text="✔")
        tree.heading("field", text="Field")
        tree.heading("value", text="Example Value")
        tree.column("selected", width=40)
        tree.column("field", width=200)
        tree.column("value", width=300)
        
        # Add sample data
        tree.insert("", "end", values=("✓", "Summary", "Implement new feature"))
        tree.insert("", "end", values=("✓", "Status", "In Progress"))
        tree.insert("", "end", values=("", "Priority", "High"))
        tree.insert("", "end", values=("✓", "Assignee", "John Doe"))
        tree.insert("", "end", values=("", "Epic Link", "EPIC-456"))
        
        tree.grid(row=1, column=0, sticky="nsew")
        fields_frame.grid_columnconfigure(0, weight=1)
        fields_frame.grid_rowconfigure(1, weight=1)
        
        # Configuration options
        config_frame = ttk.LabelFrame(frame, text="⚙️ Configuration", padding=12)
        config_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
        
        # Sample checkboxes
        ttk.Checkbutton(config_frame, text="Comment Count").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Checkbutton(config_frame, text="Time in Status").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Checkbutton(config_frame, text="Commenter Count").grid(row=2, column=0, sticky="w", pady=2)
        
        # Config management
        mgmt_frame = ttk.LabelFrame(frame, text="💾 Configuration Management", padding=12)
        mgmt_frame.grid(row=1, column=0, columnspan=2, sticky="we")
        
        config_controls = ttk.Frame(mgmt_frame)
        config_controls.grid(row=0, column=0, sticky="we")
        
        ttk.Label(config_controls, text="Configuration Name:", font=('Segoe UI', 10)).grid(row=0, column=0, sticky="w")
        name_entry = ttk.Entry(config_controls, width=30, font=('Segoe UI', 10))
        name_entry.insert(0, "default_config")
        name_entry.grid(row=0, column=1, padx=(10, 10))
        ttk.Button(config_controls, text="💾 Save Config").grid(row=0, column=2, padx=(0, 20))
        
        ttk.Label(config_controls, text="Load Configuration:", font=('Segoe UI', 10)).grid(row=0, column=3)
        load_combo = ttk.Combobox(config_controls, values=["default_config", "sprint_analysis", "bug_tracking"], 
                                 state="readonly", width=30, font=('Segoe UI', 10))
        load_combo.set("default_config")
        load_combo.grid(row=0, column=4, padx=(10, 10))
        ttk.Button(config_controls, text="📂 Load").grid(row=0, column=5)
        
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(0, weight=1)

if __name__ == "__main__":
    app = ThemePreview()
    app.mainloop()
