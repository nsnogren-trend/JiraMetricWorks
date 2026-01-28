import os
import json
import threading
from datetime import datetime, timedelta
from dateutil import parser as dtparser, tz
import pytz
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re

from jira_client import JiraClient
from export_csv import export_csv
from export_json import export_json, export_markdown
from sprint_analysis import analyze_sprint_patterns, analyze_sprint_patterns_by_sprint
from timeline_report_ui import TimelineReportTab
from jql_selector_widget import JQLSelectorWidget
from jql_manager import JQLManager

APP_DIR = os.path.join(os.path.expanduser("~"), ".jira_metrics")
CREDS_PATH = os.path.join(APP_DIR, "credentials.json")
CONFIG_DIR = os.path.join(APP_DIR, "configs")
CONNECTIONS_PATH = os.path.join(APP_DIR, "connections.json")

def ensure_app_dirs():
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)

def load_credentials():
    """Load the last used credentials (for backward compatibility)"""
    if os.path.exists(CREDS_PATH):
        with open(CREDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_credentials(base_url, email, api_token):
    """Save credentials as the default (for backward compatibility)"""
    ensure_app_dirs()
    with open(CREDS_PATH, "w", encoding="utf-8") as f:
        json.dump({"base_url": base_url, "email": email, "api_token": api_token}, f)

def load_saved_connections():
    """Load all saved connections"""
    if os.path.exists(CONNECTIONS_PATH):
        try:
            with open(CONNECTIONS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_connection(base_url, email, api_token, name=None):
    """Save a connection with a friendly name"""
    ensure_app_dirs()
    connections = load_saved_connections()
    
    # Generate a name if not provided
    if not name:
        name = base_url.replace('https://', '').replace('http://', '').split('.')[0]
    
    # Ensure unique name
    original_name = name
    counter = 1
    while name in connections:
        name = f"{original_name} ({counter})"
        counter += 1
    
    connections[name] = {
        "base_url": base_url,
        "email": email,
        "api_token": api_token,
        "last_used": datetime.now().isoformat()
    }
    
    with open(CONNECTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(connections, f, indent=2)
    
    return name

def list_configs():
    ensure_app_dirs()
    names = []
    for fn in os.listdir(CONFIG_DIR):
        if fn.endswith(".json"):
            names.append(fn[:-5])
    return sorted(names)

def load_config(name):
    path = os.path.join(CONFIG_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg):
    ensure_app_dirs()
    name = cfg.get("name", "config")
    path = os.path.join(CONFIG_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def parse_time_hhmm(s):
    return datetime.strptime(s, "%H:%M").time()

def business_hours_overlap(start_dt, end_dt, bh):
    import pytz as _pytz
    tzname = bh.get("timezone", "UTC")
    tzinfo = _pytz.timezone(tzname)
    start_dt = start_dt.astimezone(tzinfo)
    end_dt = end_dt.astimezone(tzinfo)
    if end_dt <= start_dt:
        return 0.0
    start_time = parse_time_hhmm(bh.get("start", "09:00"))
    end_time = parse_time_hhmm(bh.get("end", "17:00"))
    exclude_weekends = bh.get("exclude_weekends", True)
    holidays = set()
    for h in bh.get("holidays", []):
        try:
            holidays.add(datetime.strptime(h, "%Y-%m-%d").date())
        except Exception:
            pass

    total = 0.0
    cur = start_dt.date()
    while cur <= end_dt.date():
        if not (exclude_weekends and cur.weekday() >= 5) and cur not in holidays:
            day_start = tzinfo.localize(datetime.combine(cur, start_time))
            day_end = tzinfo.localize(datetime.combine(cur, end_time))
            seg_start = max(start_dt, day_start)
            seg_end = min(end_dt, day_end)
            if seg_end > seg_start:
                total += (seg_end - seg_start).total_seconds() / 3600.0
        cur += timedelta(days=1)
    return total

class LogConsole(tk.Text):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        # Modern styling for the log console
        self.configure(
            state="disabled", 
            wrap="word",
            bg='#ffffff',           # White background
            fg='#333333',           # Dark gray text
            insertbackground='#333333',  # Cursor color
            selectbackground='#0078d4',  # Selection background
            selectforeground='white',    # Selection text color
            borderwidth=1,
            relief='solid',
            font=('Consolas', 9)    # Monospace font for better readability
        )
        self.tag_config("err", foreground="#d13438")    # Red for errors
        self.tag_config("info", foreground="#333333")   # Dark gray for info
        self.tag_config("success", foreground="#107c10") # Green for success
    
    def write(self, msg, level="info"):
        self.configure(state="normal")
        self.insert("end", msg + "\n", level)
        self.see("end")
        self.configure(state="disabled")

class LoginWindow(tk.Toplevel):
    def __init__(self, master, on_success, log_fn, switching_instance=False):
        super().__init__(master)
        self.title("Jira Metrics - Login")
        self.resizable(False, False)
        self.on_success = on_success
        self.log = log_fn
        self.switching_instance = switching_instance
        
        # Apply modern styling to login window
        self.configure(bg='#f0f0f0')

        frm = ttk.Frame(self, padding=20)
        frm.grid(row=0, column=0, sticky="nsew")

        # Add a title label that changes based on context
        title_text = "Switch Jira Instance" if switching_instance else "Connect to Jira"
        title_label = ttk.Label(frm, text=title_text, font=('Segoe UI', 14, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        ttk.Label(frm, text="Jira URL:", font=('Segoe UI', 10)).grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(frm, textvariable=self.url_var, width=40, font=('Segoe UI', 10))
        url_entry.grid(row=1, column=1, columnspan=2, sticky="we", pady=(0, 8))

        ttk.Label(frm, text="Email:", font=('Segoe UI', 10)).grid(row=2, column=0, sticky="w", pady=(0, 8))
        self.email_var = tk.StringVar()
        email_entry = ttk.Entry(frm, textvariable=self.email_var, width=40, font=('Segoe UI', 10))
        email_entry.grid(row=2, column=1, columnspan=2, sticky="we", pady=(0, 8))

        ttk.Label(frm, text="API Token:", font=('Segoe UI', 10)).grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.token_var = tk.StringVar()
        token_entry = ttk.Entry(frm, textvariable=self.token_var, width=40, show="*", font=('Segoe UI', 10))
        token_entry.grid(row=3, column=1, columnspan=2, sticky="we", pady=(0, 8))

        # Save credentials checkbox
        self.save_creds_var = tk.BooleanVar(value=True)
        save_check = ttk.Checkbutton(frm, text="Save credentials for future use", variable=self.save_creds_var)
        save_check.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # Button frame for better layout
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=(20, 0))
        
        self.btn_login = ttk.Button(btn_frame, text="Connect", command=self.do_login)
        self.btn_login.pack(side="left", padx=(0, 10))
        
        # Only show "Use Saved Credentials" if we have saved credentials and not switching
        creds = load_credentials()
        saved_connections = load_saved_connections()
        
        if (creds or saved_connections) and not switching_instance:
            # Saved connections dropdown
            if saved_connections:
                ttk.Label(btn_frame, text="Saved Connections:", font=('Segoe UI', 10)).pack(side="left", padx=(0, 5))
                connection_names = list(saved_connections.keys())
                self.connection_var = tk.StringVar()
                connection_combo = ttk.Combobox(btn_frame, textvariable=self.connection_var, 
                                              values=connection_names, state="readonly", width=20)
                connection_combo.pack(side="left", padx=(0, 10))
                connection_combo.bind('<<ComboboxSelected>>', self.on_connection_selected)
                
                self.btn_use_saved = ttk.Button(btn_frame, text="Use Selected", command=self.use_selected_connection)
                self.btn_use_saved.pack(side="left", padx=(0, 10))
            elif creds:
                self.btn_use_saved = ttk.Button(btn_frame, text="Use Saved Credentials", command=self.use_saved)
                self.btn_use_saved.pack(side="left", padx=(0, 10))
        
        # Cancel button for when switching instances
        if switching_instance:
            self.btn_cancel = ttk.Button(btn_frame, text="Cancel", command=self.destroy)
            self.btn_cancel.pack(side="left")

        # Pre-fill form with saved credentials if available and not switching
        if creds and not switching_instance:
            self.url_var.set(creds.get("base_url", ""))
            self.email_var.set(creds.get("email", ""))

        # Center the window on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        
        # Focus on the first empty field
        if not self.url_var.get():
            url_entry.focus()
        elif not self.email_var.get():
            email_entry.focus()
        else:
            token_entry.focus()

    def on_connection_selected(self, event=None):
        """Handle selection of a saved connection"""
        selected = self.connection_var.get()
        if selected:
            saved_connections = load_saved_connections()
            conn = saved_connections.get(selected)
            if conn:
                self.url_var.set(conn.get("base_url", ""))
                self.email_var.set(conn.get("email", ""))
                # Don't pre-fill the token for security reasons

    def use_selected_connection(self):
        """Use the selected saved connection"""
        selected = self.connection_var.get()
        if not selected:
            messagebox.showerror("Error", "Please select a connection.")
            return
            
        saved_connections = load_saved_connections()
        conn = saved_connections.get(selected)
        if not conn:
            messagebox.showerror("Error", "Selected connection not found.")
            return
            
        client = JiraClient(conn["base_url"], conn["email"], conn["api_token"], log_fn=self.log)
        self.log(f"Testing saved connection '{selected}'...")
        
        def test_connection():
            return client.test_connection()
            
        def on_done(ok):
            if ok:
                self.log(f"Login success with saved connection '{selected}'.", "success")
                # Update last used time
                conn["last_used"] = datetime.now().isoformat()
                with open(CONNECTIONS_PATH, "w", encoding="utf-8") as f:
                    json.dump(saved_connections, f, indent=2)
                self.on_success(client)
                self.destroy()
            else:
                messagebox.showerror("Login Failed", f"Saved connection '{selected}' is invalid.")
                
        threading.Thread(target=lambda: self._run_worker(test_connection, on_done), daemon=True).start()

    def use_saved(self):
        creds = load_credentials()
        if not creds:
            messagebox.showerror("Error", "No saved credentials found.")
            return
        client = JiraClient(creds["base_url"], creds["email"], creds["api_token"], log_fn=self.log)
        self.log("Testing saved credentials...")
        if client.test_connection():
            self.log("Login success with saved credentials.", "success")
            self.on_success(client)
            self.destroy()
        else:
            messagebox.showerror("Login Failed", "Saved credentials are invalid.")

    def do_login(self):
        base_url = self.url_var.get().strip()
        email = self.email_var.get().strip()
        token = self.token_var.get().strip()
        if not base_url or not email or not token:
            messagebox.showerror("Error", "Please enter URL, Email, and API Token.")
            return
        client = JiraClient(base_url, email, token, log_fn=self.log)
        self.log("Testing credentials...")
        self.btn_login.configure(state="disabled")
        def worker():
            return client.test_connection()
        def on_done(ok):
            self.btn_login.configure(state="normal")
            if ok:
                self.log("Connection successful.", "success")
                # Save credentials if the checkbox is checked
                if self.save_creds_var.get():
                    # Save to both old format (for compatibility) and new format
                    save_credentials(base_url, email, token)
                    connection_name = save_connection(base_url, email, token)
                    self.log(f"Connection saved as '{connection_name}' for future use.")
                else:
                    self.log("Credentials not saved (as requested).")
                self.on_success(client)
                self.destroy()
            else:
                messagebox.showerror("Connection Failed", "Invalid credentials or URL.")
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def _run_worker(self, worker, on_done):
        try:
            ok = worker()
        except Exception as e:
            self.log(f"Login error: {e}")
            ok = False
        finally:
            self.after(0, lambda: on_done(ok))

class ConfigTab(ttk.Frame):
    def __init__(self, master, jira_client: JiraClient, log_fn, field_id_to_name, field_name_to_id):
        super().__init__(master)
        self.client = jira_client
        self.log = log_fn
        self.field_id_to_name = field_id_to_name
        self.field_name_to_id = field_name_to_id

        self.available_field_ids = []
        self.selected_field_ids = set()

        self.transition_rules = []
        self.metrics_flags = {
            "comment_count": tk.BooleanVar(value=True),
            "comment_length": tk.BooleanVar(value=True),
            "commenter_count": tk.BooleanVar(value=True),
            "time_in_status": tk.BooleanVar(value=True),
        }

        self._build_ui()

    def _build_ui(self):
        # Create main container with padding
        main_container = ttk.Frame(self, padding=10)
        main_container.grid(row=0, column=0, sticky="nsew")
        
        left = ttk.LabelFrame(main_container, text="📋 Field Selection", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,10), pady=(0, 10))

        # Field loading section
        load_frame = ttk.Frame(left)
        load_frame.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 10))
        
        ttk.Label(load_frame, text="Issue Key:", font=('Segoe UI', 10)).grid(row=0, column=0, sticky="w")
        self.issue_key_var = tk.StringVar()
        ttk.Entry(load_frame, textvariable=self.issue_key_var, width=25, font=('Segoe UI', 10)).grid(row=0, column=1, sticky="we", padx=(10, 10))
        ttk.Button(load_frame, text="🔄 Load Fields", command=self.load_fields).grid(row=0, column=2, sticky="we")
        load_frame.grid_columnconfigure(1, weight=1)

        cols = ("selected", "field", "value")
        self.fields_tree = ttk.Treeview(left, columns=cols, show="headings", height=16)
        self.fields_tree.heading("selected", text="✔")
        self.fields_tree.heading("field", text="Field")
        self.fields_tree.heading("value", text="Example Value")
        self.fields_tree.column("selected", width=40, anchor="center")
        self.fields_tree.column("field", width=260, anchor="w")
        self.fields_tree.column("value", anchor="w")
        self.fields_tree.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 0))
        left.grid_columnconfigure(1, weight=1)
        left.grid_rowconfigure(1, weight=1)

        self.fields_tree.bind("<Button-1>", self._on_tree_click)

        right = ttk.LabelFrame(main_container, text="⚙️ Configuration", padding=12)
        right.grid(row=0, column=1, sticky="nsew", pady=(0, 10))

        trlf = ttk.LabelFrame(right, text="Custom Status Transition Rules")
        trlf.grid(row=0, column=0, sticky="nsew", pady=(0,8))
        self.tr_container = ttk.Frame(trlf)
        self.tr_container.grid(row=0, column=0, sticky="nsew")
        self.tr_rows = []

        def add_rule_row(prefill=None):
            row = ttk.Frame(self.tr_container)
            name_var = tk.StringVar(value=(prefill.get("name") if prefill else ""))
            ttk.Label(row, text="Name:").grid(row=0, column=0, sticky="w")
            name_entry = ttk.Entry(row, textvariable=name_var, width=20)
            name_entry.grid(row=0, column=1, sticky="w")
            seq_frame = ttk.Frame(row)
            seq_frame.grid(row=0, column=2, padx=(8,8))
            seq_vars = []
            def add_box(value=""):
                v = tk.StringVar(value=value)
                ent = ttk.Entry(seq_frame, textvariable=v, width=18)
                if len(seq_vars) > 0:
                    ttk.Label(seq_frame, text="→").pack(side="left")
                ent.pack(side="left")
                seq_vars.append(v)
            def on_plus():
                add_box("")
            plus_btn = ttk.Button(row, text="+", width=3, command=on_plus)
            plus_btn.grid(row=0, column=3)
            def on_delete():
                row.destroy()
                self.tr_rows.remove((name_var, seq_vars, row))
            del_btn = ttk.Button(row, text="X", width=3, command=on_delete)
            del_btn.grid(row=0, column=4, padx=(4,0))
            row.pack(fill="x", pady=3)
            self.tr_rows.append((name_var, seq_vars, row))
            if prefill and prefill.get("sequence"):
                for st in prefill["sequence"]:
                    add_box(st)
            else:
                add_box("")
                add_box("")
        self.add_rule_row = add_rule_row
        ttk.Button(trlf, text="Add Rule", command=lambda: add_rule_row()).grid(row=1, column=0, sticky="w", pady=(6,0))

        toggles = ttk.LabelFrame(right, text="Other Metrics")
        toggles.grid(row=1, column=0, sticky="nsew")
        for i, (k, var) in enumerate(self.metrics_flags.items()):
            ttk.Checkbutton(toggles, text=k.replace("_", " ").title(), variable=var).grid(row=i//2, column=i%2, sticky="w")

        bh = ttk.LabelFrame(right, text="Business Hours")
        bh.grid(row=2, column=0, sticky="nsew", pady=(8,0))
        self.bh_start = tk.StringVar(value="09:00")
        self.bh_end = tk.StringVar(value="17:00")
        self.bh_tz = tk.StringVar(value="UTC")
        self.bh_excl_wknd = tk.BooleanVar(value=True)
        self.bh_holidays = tk.StringVar(value="")
        ttk.Label(bh, text="Start (HH:MM):").grid(row=0, column=0, sticky="w")
        ttk.Entry(bh, textvariable=self.bh_start, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(bh, text="End (HH:MM):").grid(row=0, column=2, sticky="w")
        ttk.Entry(bh, textvariable=self.bh_end, width=8).grid(row=0, column=3, sticky="w")
        ttk.Label(bh, text="Timezone:").grid(row=1, column=0, sticky="w")
        tz_combo = ttk.Combobox(bh, textvariable=self.bh_tz, values=sorted(pytz.all_timezones), width=28)
        tz_combo.grid(row=1, column=1, columnspan=3, sticky="we")
        ttk.Checkbutton(bh, text="Exclude weekends", variable=self.bh_excl_wknd).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(bh, text="Holidays (YYYY-MM-DD, comma separated):").grid(row=3, column=0, columnspan=4, sticky="w")
        ttk.Entry(bh, textvariable=self.bh_holidays, width=40).grid(row=4, column=0, columnspan=4, sticky="we")

        bottom = ttk.LabelFrame(main_container, text="💾 Configuration Management", padding=12)
        bottom.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 0))

        # Config management with better layout
        config_frame = ttk.Frame(bottom)
        config_frame.grid(row=0, column=0, sticky="we")
        
        ttk.Label(config_frame, text="Configuration Name:", font=('Segoe UI', 10)).grid(row=0, column=0, sticky="w")
        self.cfg_name_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.cfg_name_var, width=30, font=('Segoe UI', 10)).grid(row=0, column=1, sticky="w", padx=(10, 10))
        ttk.Button(config_frame, text="💾 Save Config", command=self.save_current_config).grid(row=0, column=2, padx=(0, 20))
        
        ttk.Label(config_frame, text="Load Configuration:", font=('Segoe UI', 10)).grid(row=0, column=3, sticky="w")
        self.cfg_combo = ttk.Combobox(config_frame, values=list_configs(), state="readonly", width=30, font=('Segoe UI', 10))
        self.cfg_combo.grid(row=0, column=4, sticky="we", padx=(10, 10))
        ttk.Button(config_frame, text="📂 Load", command=self.load_selected_config).grid(row=0, column=5)

        # Grid configuration for the main container
        main_container.grid_columnconfigure(0, weight=1)
        main_container.grid_columnconfigure(1, weight=1)
        main_container.grid_rowconfigure(0, weight=1)
        
        # Grid configuration for the parent frame
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _preview_value(self, v):
        if isinstance(v, dict):
            if "displayName" in v: return v["displayName"]
            if "name" in v: return v["name"]
            if "value" in v: return v["value"]
            return "{...}"
        if isinstance(v, list):
            return f"[{len(v)} item(s)]"
        if v is None:
            return ""
        s = str(v)
        return s if len(s) <= 200 else s[:197] + "..."

    def _on_tree_click(self, event):
        region = self.fields_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.fields_tree.identify_column(event.x)
        if col != "#1":
            return
        row_id = self.fields_tree.identify_row(event.y)
        if not row_id:
            return
        fid = row_id
        if fid in self.selected_field_ids:
            self.selected_field_ids.remove(fid)
            self.fields_tree.set(row_id, "selected", "")
        else:
            self.selected_field_ids.add(fid)
            self.fields_tree.set(row_id, "selected", "✓")

    def load_fields(self):
        key = self.issue_key_var.get().strip()
        if not key:
            messagebox.showerror("Error", "Enter an issue key.")
            return
        self.log(f"Loading issue {key} to fetch fields...")
        def worker():
            return self.client.get_issue(key, expand_changelog=False)
        def on_done(issue):
            fields = issue.get("fields", {})
            for item in self.fields_tree.get_children():
                self.fields_tree.delete(item)
            self.available_field_ids = list(fields.keys())
            for fid in self.available_field_ids:
                disp = self.field_id_to_name.get(fid, fid)
                val = self._preview_value(fields.get(fid))
                sel_mark = "✓" if fid in self.selected_field_ids else ""
                self.fields_tree.insert("", "end", iid=fid, values=(sel_mark, disp, val))
            self.log(f"Loaded {len(self.available_field_ids)} fields.")
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def _run_worker(self, worker, on_done):
        try:
            res = worker()
        except Exception as e:
            self.log(f"Error: {e}")
            messagebox.showerror("Error", str(e))
            return
        self.after(0, lambda: on_done(res))

    def save_current_config(self):
        name = self.cfg_name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a configuration name.")
            return

        selected_ids = list(self.selected_field_ids)
        selected_names = [self.field_id_to_name.get(fid, fid) for fid in selected_ids]

        trules = []
        for name_var, seq_vars, _row in self.tr_rows:
            rule_name = name_var.get().strip()
            if not rule_name:
                continue
            seq = [v.get().strip() for v in seq_vars if v.get().strip()]
            if len(seq) < 2:
                continue
            trules.append({"name": rule_name, "sequence": seq})
        bh_cfg = {
            "start": self.bh_start.get().strip(),
            "end": self.bh_end.get().strip(),
            "timezone": self.bh_tz.get().strip() or "UTC",
            "exclude_weekends": bool(self.bh_excl_wknd.get()),
            "holidays": [h.strip() for h in self.bh_holidays.get().split(",") if h.strip()]
        }
        cfg = {
            "name": name,
            "selected_field_ids": selected_ids,
            "selected_field_names": selected_names,
            "transition_rules": trules,
            "metrics": {k: bool(v.get()) for k, v in self.metrics_flags.items()},
            "business_hours": bh_cfg
        }
        save_config(cfg)
        self.cfg_combo["values"] = list_configs()
        self.log(f"Saved configuration '{name}'.")

    def load_selected_config(self):
        name = self.cfg_combo.get()
        if not name:
            messagebox.showerror("Error", "Select a configuration to load.")
            return
        cfg = load_config(name)
        self.cfg_name_var.set(cfg.get("name", name))

        ids_from_cfg = cfg.get("selected_field_ids")
        if not ids_from_cfg:
            ids_from_cfg = cfg.get("selected_fields", [])
        self.selected_field_ids = set(ids_from_cfg)

        for iid in self.fields_tree.get_children():
            fid = iid
            self.fields_tree.set(iid, "selected", "✓" if fid in self.selected_field_ids else "")

        for _ in list(getattr(self, "tr_rows", [])):
            _[2].destroy()
        self.tr_rows = []
        for tr in cfg.get("transition_rules", []):
            self.add_rule_row(prefill=tr)

        m = cfg.get("metrics", {})
        for k, var in self.metrics_flags.items():
            var.set(bool(m.get(k, False)))

        bh = cfg.get("business_hours", {})
        self.bh_start.set(bh.get("start", "09:00"))
        self.bh_end.set(bh.get("end", "17:00"))
        self.bh_tz.set(bh.get("timezone", "UTC"))
        self.bh_excl_wknd.set(bool(bh.get("exclude_weekends", True)))
        self.bh_holidays.set(", ".join(bh.get("holidays", [])))

        self.log(f"Loaded configuration '{name}'.")

    def get_current_config(self):
        selected_ids = list(self.selected_field_ids)
        selected_names = [self.field_id_to_name.get(fid, fid) for fid in selected_ids]
        trules = []
        for name_var, seq_vars, _row in self.tr_rows:
            rule_name = name_var.get().strip()
            seq = [v.get().strip() for v in seq_vars if v.get().strip()]
            if rule_name and len(seq) >= 2:
                trules.append({"name": rule_name, "sequence": seq})
        return {
            "selected_field_ids": selected_ids,
            "selected_field_names": selected_names,
            "transition_rules": trules,
            "metrics": {k: bool(v.get()) for k, v in self.metrics_flags.items()},
            "business_hours": {
                "start": self.bh_start.get().strip(),
                "end": self.bh_end.get().strip(),
                "timezone": self.bh_tz.get().strip() or "UTC",
                "exclude_weekends": bool(self.bh_excl_wknd.get()),
                "holidays": [h.strip() for h in self.bh_holidays.get().split(",") if h.strip()]
            }
        }

class JQLTab(ttk.Frame):
    SPRINT_NAME_RE = re.compile(r"name=([^,\]]+)")

    def __init__(self, master, jira_client: JiraClient, config_tab: ConfigTab, log_fn, field_id_to_name):
        super().__init__(master)
        self.client = jira_client
        self.config_tab = config_tab
        self.log = log_fn
        self.field_id_to_name = field_id_to_name
        self.jql_manager = JQLManager()  # Initialize JQL manager
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.grid(row=0, column=0, sticky="nsew")
        
        # Search section
        search_frame = ttk.LabelFrame(top, text="JQL Search", padding=10)
        search_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        # Use the JQL selector widget
        self.jql_selector = JQLSelectorWidget(search_frame, self.jql_manager)
        self.jql_selector.grid(row=0, column=0, sticky="we", pady=(0, 10))
        
        # Button and results frame
        controls_frame = ttk.Frame(search_frame)
        controls_frame.grid(row=1, column=0, sticky="we")
        
        ttk.Button(controls_frame, text="🔍 Search", command=self.search_jql).grid(row=0, column=0, padx=(0, 10))
        
        self.count_var = tk.StringVar(value="Matches: 0")
        count_label = ttk.Label(controls_frame, textvariable=self.count_var, font=('Segoe UI', 10, 'bold'))
        count_label.grid(row=0, column=1, padx=(0, 20))
        
        # Export section
        export_frame = ttk.LabelFrame(top, text="Export Options", padding=10)
        export_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        
        # Export buttons with icons and better styling
        export_buttons_frame = ttk.Frame(export_frame)
        export_buttons_frame.grid(row=0, column=0)
        
        ttk.Button(export_buttons_frame, text="📊 Export CSV", command=self.export_csv).grid(row=0, column=0, padx=(0, 10), pady=5)
        ttk.Button(export_buttons_frame, text="📄 Export JSON", command=self.export_json).grid(row=0, column=1, padx=(0, 10), pady=5)
        ttk.Button(export_buttons_frame, text="📝 Export Markdown", command=self.export_markdown).grid(row=0, column=2, padx=(0, 10), pady=5)

        search_frame.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(0, weight=1)

        # Progress section
        pb_frame = ttk.LabelFrame(self, text="Progress", padding=10)
        pb_frame.grid(row=1, column=0, sticky="we", padx=10, pady=(0, 10))
        
        self.pb = ttk.Progressbar(pb_frame, orient="horizontal", mode="determinate", value=0)
        self.pb.grid(row=0, column=0, sticky="we", pady=(0, 5))
        
        self.stage_var = tk.StringVar(value="Ready")
        stage_label = ttk.Label(pb_frame, textvariable=self.stage_var, font=('Segoe UI', 9))
        stage_label.grid(row=1, column=0, sticky="w")
        
        pb_frame.grid_columnconfigure(0, weight=1)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def search_jql(self):
        jql = self.jql_selector.get().strip()
        if not jql:
            messagebox.showerror("Error", "Enter JQL.")
            return
        self.log(f"Searching JQL: {jql}")
        def worker():
            keys, total = self.client.search_jql(jql, max_results=100, fields=["key"], expand_changelog=False)
            return keys, total
        def on_done(res):
            keys, total = res
            self.count_var.set(f"Matches: {total}")
            self.log(f"Found {total} issue(s).")
            self._last_keys = keys
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def export_csv(self):
        jql = self.jql_selector.get().strip()
        if not jql:
            messagebox.showerror("Error", "Enter JQL.")
            return
        cfg = self.config_tab.get_current_config()
        filepath = filedialog.asksaveasfilename(
            title="Save CSV",
            defaultextension=".csv",
            filetypes=[("CSV files","*.csv")]
        )
        if not filepath:
            return
        self.log("Starting export...")
        self.pb["value"] = 0
        self.pb.update_idletasks()

        def progress_cb(stage, done, total):
            self.stage_var.set(stage)
            self.pb["maximum"] = total if total else 1
            self.pb["value"] = min(done, total) if total else done

        def worker():
            headers, row_iter = export_csv(
                jira_client=self.client,
                jql=jql,
                cfg=cfg,
                field_id_to_name=self.field_id_to_name,
                format_field_fn=self._format_field,
                business_hours_overlap=business_hours_overlap,
                progress_cb=progress_cb
            )
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                import csv as _csv
                writer = _csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for _row in row_iter():
                    writer.writerow(_row)
            return True

        def on_done(_):
            self.stage_var.set("Ready")
            self.log("Export completed.", "success")
            messagebox.showinfo("Done", "CSV export completed.")

        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def export_json(self):
        jql = self.jql_selector.get().strip()
        if not jql:
            messagebox.showerror("Error", "Enter JQL.")
            return
        folder = filedialog.askdirectory(title="Select folder to save JSON issues")
        if not folder:
            return
        self.log("Starting JSON export...")
        self.pb["value"] = 0
        self.pb.update_idletasks()

        def progress_cb(stage, done, total):
            self.stage_var.set(stage)
            self.pb["maximum"] = total if total else 1
            self.pb["value"] = min(done, total) if total else done

        def worker():
            export_json(
                jira_client=self.client,
                jql=jql,
                field_id_to_name=self.field_id_to_name,
                folder_path=folder,
                progress_cb=progress_cb
            )
            return True

        def on_done(_):
            self.stage_var.set("Ready")
            self.log("JSON export completed.", "success")
            messagebox.showinfo("Done", "JSON export completed.")

        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def export_markdown(self):
        jql = self.jql_selector.get().strip()
        if not jql:
            messagebox.showerror("Error", "Enter JQL.")
            return
        folder = filedialog.askdirectory(title="Select folder to save Markdown files")
        if not folder:
            return
        self.log("Starting Markdown export...")
        self.pb["value"] = 0
        self.pb.update_idletasks()

        def progress_cb(stage, done, total):
            self.stage_var.set(stage)
            self.pb["maximum"] = total if total else 1
            self.pb["value"] = min(done, total) if total else done

        def worker():
            export_markdown(
                jira_client=self.client,
                jql=jql,
                field_id_to_name=self.field_id_to_name,
                folder_path=folder,
                progress_cb=progress_cb
            )
            return True

        def on_done(_):
            self.stage_var.set("Ready")
            self.log("Markdown export completed.", "success")
            messagebox.showinfo("Done", "Markdown export completed.")

        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def _parse_sprint_blob(self, s):
        m = self.SPRINT_NAME_RE.search(s or "")
        return m.group(1) if m else s

    def _format_field(self, fid, val):
        name = self.field_id_to_name.get(fid, fid)
        if isinstance(val, list) and name.lower() == "sprint":
            sprints = []
            for s in val:
                if isinstance(s, dict):
                    nm = s.get("name") or s.get("id")
                    if s.get("state"):
                        nm = f"{nm} ({s['state']})"
                    sprints.append(str(nm))
                else:
                    sprints.append(self._parse_sprint_blob(str(s)))
            return " | ".join(sprints)
        if name.lower() == "fix versions" and isinstance(val, list):
            return ", ".join([v.get("name") for v in val if isinstance(v, dict) and v.get("name")])
        if name.lower() == "affects versions" and isinstance(val, list):
            return ", ".join([v.get("name") for v in val if isinstance(v, dict) and v.get("name")])
        if name.lower() == "components" and isinstance(val, list):
            return ", ".join([v.get("name") for v in val if isinstance(v, dict) and v.get("name")])
        if isinstance(val, list):
            items = []
            for x in val:
                if isinstance(x, dict):
                    items.append(x.get("displayName") or x.get("name") or x.get("value") or x.get("key") or str(x))
                else:
                    items.append(str(x))
            return ", ".join(items)
        if isinstance(val, dict):
            if "displayName" in val: return val["displayName"]
            if "name" in val: return val["name"]
            if "value" in val: return val["value"]
            if "key" in val: return val["key"]
            return json.dumps(val, ensure_ascii=False)
        return "" if val is None else str(val)

    def _run_worker(self, worker, on_done):
        try:
            res = worker()
        except Exception as e:
            self.log(f"Error: {e}")
            messagebox.showerror("Error", str(e))
            return
        self.after(0, lambda: on_done(res))

class ConnectionManagerWindow(tk.Toplevel):
    def __init__(self, master, log_fn):
        super().__init__(master)
        self.title("Manage Saved Connections")
        self.geometry("600x400")
        self.resizable(True, True)
        self.log = log_fn
        
        # Apply modern styling
        self.configure(bg='#f0f0f0')
        
        # Main frame
        main_frame = ttk.Frame(self, padding=20)
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Title
        title_label = ttk.Label(main_frame, text="Saved Jira Connections", font=('Segoe UI', 14, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Connection list
        columns = ("name", "url", "email", "last_used")
        self.tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=12)
        
        self.tree.heading("name", text="Name")
        self.tree.heading("url", text="Jira URL")
        self.tree.heading("email", text="Email")
        self.tree.heading("last_used", text="Last Used")
        
        self.tree.column("name", width=150)
        self.tree.column("url", width=200)
        self.tree.column("email", width=150)
        self.tree.column("last_used", width=100)
        
        self.tree.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        
        # Scrollbar for the tree
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=3, sticky="ns", pady=(0, 10))
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, columnspan=3, sticky="we")
        
        ttk.Button(btn_frame, text="Delete Selected", command=self.delete_selected).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Test Connection", command=self.test_selected).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Refresh", command=self.refresh_list).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side="right")
        
        # Configure grid weights
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # Load connections
        self.refresh_list()
        
        # Center the window
        self.transient(master)
        self.grab_set()
        
    def refresh_list(self):
        """Refresh the connections list"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Load and display connections
        connections = load_saved_connections()
        for name, conn in connections.items():
            last_used = conn.get("last_used", "Never")
            if last_used != "Never":
                try:
                    dt = datetime.fromisoformat(last_used)
                    last_used = dt.strftime("%Y-%m-%d")
                except Exception:
                    last_used = "Unknown"
                    
            self.tree.insert("", "end", values=(
                name,
                conn.get("base_url", ""),
                conn.get("email", ""),
                last_used
            ))
    
    def delete_selected(self):
        """Delete the selected connection"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a connection to delete.")
            return
            
        item = selection[0]
        name = self.tree.item(item)['values'][0]
        
        result = messagebox.askyesno(
            "Confirm Delete", 
            f"Are you sure you want to delete the connection '{name}'?\n\nThis action cannot be undone.",
            icon='warning'
        )
        
        if result:
            connections = load_saved_connections()
            if name in connections:
                del connections[name]
                with open(CONNECTIONS_PATH, "w", encoding="utf-8") as f:
                    json.dump(connections, f, indent=2)
                self.log(f"Deleted saved connection '{name}'.")
                self.refresh_list()
            else:
                messagebox.showerror("Error", "Connection not found.")
    
    def test_selected(self):
        """Test the selected connection"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a connection to test.")
            return
            
        item = selection[0]
        name = self.tree.item(item)['values'][0]
        
        connections = load_saved_connections()
        conn = connections.get(name)
        if not conn:
            messagebox.showerror("Error", "Connection not found.")
            return
        
        self.log(f"Testing connection '{name}'...")
        
        def test_connection():
            client = JiraClient(conn["base_url"], conn["email"], conn["api_token"], log_fn=self.log)
            return client.test_connection()
            
        def on_done(ok):
            if ok:
                self.log(f"Connection '{name}' test successful.", "success")
                messagebox.showinfo("Test Successful", f"Connection '{name}' is working correctly.")
            else:
                self.log(f"Connection '{name}' test failed.", "err")
                messagebox.showerror("Test Failed", f"Connection '{name}' failed. Please check credentials.")
                
        threading.Thread(target=lambda: self._run_worker(test_connection, on_done), daemon=True).start()
    
    def _run_worker(self, worker, on_done):
        try:
            result = worker()
        except Exception as e:
            self.log(f"Error: {e}")
            result = False
        self.after(0, lambda: on_done(result))


class SprintAnalysisTab(ttk.Frame):
    def __init__(self, master, jira_client: JiraClient, log_fn, field_id_to_name):
        super().__init__(master)
        self.client = jira_client
        self.log = log_fn
        self.field_id_to_name = field_id_to_name
        self.boards = []
        self.sprints = []
        self.selected_board = None
        self.selected_sprint = None
        self._build_ui()
        self._load_boards()

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.grid(row=0, column=0, sticky="nsew")
        
        # Board selection section
        board_frame = ttk.LabelFrame(top, text="Board Selection", padding=10)
        board_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        ttk.Label(board_frame, text="Select Board:", font=('Segoe UI', 10)).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        self.board_var = tk.StringVar()
        self.board_combo = ttk.Combobox(board_frame, textvariable=self.board_var, width=60, state="readonly")
        self.board_combo.grid(row=1, column=0, sticky="we", pady=(0, 10))
        self.board_combo.bind("<<ComboboxSelected>>", self._on_board_selected)
        
        ttk.Button(board_frame, text="🔄 Refresh Boards", command=self._load_boards).grid(row=1, column=1, padx=(10, 0))
        
        # Sprint selection section
        sprint_frame = ttk.LabelFrame(top, text="Sprint Selection", padding=10)
        sprint_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        
        ttk.Label(sprint_frame, text="Select Sprint:", font=('Segoe UI', 10)).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        self.sprint_var = tk.StringVar()
        self.sprint_combo = ttk.Combobox(sprint_frame, textvariable=self.sprint_var, width=60, state="readonly")
        self.sprint_combo.grid(row=1, column=0, sticky="we", pady=(0, 10))
        self.sprint_combo.bind("<<ComboboxSelected>>", self._on_sprint_selected)
        
        # Sprint info display
        self.sprint_info_var = tk.StringVar(value="No sprint selected")
        sprint_info_label = ttk.Label(sprint_frame, textvariable=self.sprint_info_var, font=('Segoe UI', 9))
        sprint_info_label.grid(row=2, column=0, sticky="w", pady=(5, 0))
        
        # Analysis section
        analysis_frame = ttk.LabelFrame(top, text="Sprint Analysis", padding=10)
        analysis_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        
        self.analyze_button = ttk.Button(analysis_frame, text="🏃 Analyze Sprint Patterns", 
                                       command=self.analyze_sprint, state="disabled")
        self.analyze_button.grid(row=0, column=0, pady=5)
        
        ttk.Button(analysis_frame, text="💾 Export to CSV", 
                  command=self.export_csv, state="normal").grid(row=0, column=1, padx=(10, 0), pady=5)
        
        # Results preview section
        results_frame = ttk.LabelFrame(top, text="Analysis Results Preview", padding=10)
        results_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
        
        # Create treeview for results preview
        columns = ("Issue", "From Status", "To Status", "Date", "Sprint Day", "Progress %")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=6)
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)
        
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Progress section
        pb_frame = ttk.LabelFrame(self, text="Progress", padding=10)
        pb_frame.grid(row=1, column=0, sticky="we", padx=10, pady=(0, 10))
        
        self.pb = ttk.Progressbar(pb_frame, orient="horizontal", mode="determinate", value=0)
        self.pb.grid(row=0, column=0, sticky="we", pady=(0, 5))
        
        self.stage_var = tk.StringVar(value="Ready")
        stage_label = ttk.Label(pb_frame, textvariable=self.stage_var, font=('Segoe UI', 9))
        stage_label.grid(row=1, column=0, sticky="w")
        
        # Configure grid weights
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        top.grid_rowconfigure(3, weight=1)
        top.grid_columnconfigure(0, weight=1)
        board_frame.grid_columnconfigure(0, weight=1)
        sprint_frame.grid_columnconfigure(0, weight=1)
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)
        pb_frame.grid_columnconfigure(0, weight=1)
        
        # Store analysis results
        self.last_results = []
        self.last_headers = []

    def _load_boards(self):
        """Load available boards"""
        def worker():
            try:
                self.boards = self.client.get_all_boards()
                return True
            except Exception as e:
                self.log(f"Error loading boards: {e}")
                return False
        
        def on_done(success):
            self.stage_var.set("Ready")
            if success:
                board_names = [f"{board['name']} (ID: {board['id']})" for board in self.boards]
                self.board_combo['values'] = board_names
                self.log(f"Loaded {len(self.boards)} boards.")
            else:
                self.log("Failed to load boards.", "error")
        
        self.stage_var.set("Loading boards...")
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def _on_board_selected(self, event=None):
        """Handle board selection"""
        selection = self.board_var.get()
        if not selection:
            return
        
        # Extract board ID from selection
        try:
            board_id = int(selection.split("(ID: ")[1].split(")")[0])
            self.selected_board = next(board for board in self.boards if board['id'] == board_id)
            self._load_sprints(board_id)
        except (ValueError, IndexError, StopIteration):
            self.log("Error parsing board selection", "error")

    def _load_sprints(self, board_id):
        """Load sprints for the selected board"""
        def worker():
            try:
                self.sprints = self.client.get_board_sprints(board_id)
                return True
            except Exception as e:
                self.log(f"Error loading sprints: {e}")
                return False
        
        def on_done(success):
            self.stage_var.set("Ready")
            if success:
                # Sort sprints by state (active first, then closed, then future) and name
                sprint_order = {'active': 0, 'closed': 1, 'future': 2}
                self.sprints.sort(key=lambda s: (sprint_order.get(s.get('state', 'future'), 3), s.get('name', '')))
                
                sprint_names = []
                for sprint in self.sprints:
                    state_emoji = {'active': '🔄', 'closed': '✅', 'future': '📅'}.get(sprint.get('state'), '❓')
                    sprint_names.append(f"{state_emoji} {sprint['name']} (ID: {sprint['id']})")
                
                self.sprint_combo['values'] = sprint_names
                self.sprint_var.set("")  # Clear selection
                self.sprint_info_var.set("No sprint selected")
                self.analyze_button.config(state="disabled")
                self.log(f"Loaded {len(self.sprints)} sprints.")
            else:
                self.log("Failed to load sprints.", "error")
        
        self.stage_var.set("Loading sprints...")
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def _on_sprint_selected(self, event=None):
        """Handle sprint selection"""
        selection = self.sprint_var.get()
        if not selection:
            return
        
        # Extract sprint ID from selection
        try:
            sprint_id = int(selection.split("(ID: ")[1].split(")")[0])
            self.selected_sprint = next(sprint for sprint in self.sprints if sprint['id'] == sprint_id)
            
            # Update sprint info display
            sprint = self.selected_sprint
            info_parts = [f"State: {sprint.get('state', 'Unknown')}"]
            
            if sprint.get('startDate'):
                start_date = dtparser.parse(sprint['startDate']).strftime('%Y-%m-%d')
                info_parts.append(f"Start: {start_date}")
            
            if sprint.get('endDate'):
                end_date = dtparser.parse(sprint['endDate']).strftime('%Y-%m-%d')
                info_parts.append(f"End: {end_date}")
            
            if sprint.get('goal'):
                info_parts.append(f"Goal: {sprint['goal']}")
            
            self.sprint_info_var.set(" | ".join(info_parts))
            self.analyze_button.config(state="normal")
            
        except (ValueError, IndexError, StopIteration):
            self.log("Error parsing sprint selection", "error")

    def analyze_sprint(self):
        """Analyze the selected sprint"""
        if not self.selected_sprint:
            messagebox.showerror("Error", "Please select a sprint first.")
            return
        
        # Clear previous results
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.log("Starting sprint analysis...")
        self.pb["value"] = 0
        self.pb.update_idletasks()

        def progress_cb(stage, done, total):
            self.stage_var.set(stage)
            self.pb["maximum"] = total if total else 1
            self.pb["value"] = min(done, total) if total else done

        def worker():
            try:
                headers, row_iter = analyze_sprint_patterns_by_sprint(
                    jira_client=self.client,
                    sprint_id=self.selected_sprint['id'],
                    progress_cb=progress_cb
                )
                
                results = list(row_iter())
                self.last_headers = headers
                self.last_results = results
                
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Sprint analysis failed: {e}")
                return False

        def on_done(success):
            self.stage_var.set("Ready")
            if success:
                self._display_results()
                self.log("Sprint analysis completed.", "success")
            else:
                self.log("Sprint analysis failed.", "error")

        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def _display_results(self):
        """Display analysis results in the preview tree"""
        for result in self.last_results[:20]:  # Show first 20 results
            values = (
                result.get('issue_key', ''),
                result.get('from_status', ''),
                result.get('to_status', ''),
                result.get('transition_date', '')[:10] if result.get('transition_date') else '',  # Just date part
                result.get('sprint_day', ''),
                f"{result.get('sprint_progress_percent', 0):.1f}%"
            )
            self.tree.insert("", "end", values=values)
        
        if len(self.last_results) > 20:
            self.tree.insert("", "end", values=("...", f"({len(self.last_results) - 20} more transitions)", "", "", "", ""))

    def export_csv(self):
        """Export analysis results to CSV"""
        if not self.last_results:
            messagebox.showwarning("Warning", "No analysis results to export. Run analysis first.")
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Save Sprint Analysis CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        
        if filepath:
            try:
                import csv
                with open(filepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=self.last_headers)
                    writer.writeheader()
                    writer.writerows(self.last_results)
                
                self.log(f"Results exported to {filepath}", "success")
                messagebox.showinfo("Success", f"Results exported to {filepath}")
            except Exception as e:
                self.log(f"Export failed: {e}", "error")
                messagebox.showerror("Error", f"Export failed: {e}")

    def _run_worker(self, worker, on_done):
        """Run a worker function in a thread and call on_done with the result"""
        try:
            result = worker()
        except Exception as e:
            self.log(f"Error: {e}")
            result = False
        self.after(0, lambda: on_done(result))


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Jira Metrics")
        self.geometry("1100x720")
        self.minsize(950, 620)
        ensure_app_dirs()

        # Configure modern theme and styling
        self._setup_theme()

        # Create menu bar
        self._create_menu()

        self.log_console = LogConsole(self, height=8)
        self.nb = ttk.Notebook(self)
        self.nb.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        self.log_console.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self._client = None
        self._config_tab = None
        self._jql_tab = None
        self._current_connection_info = None

        self.after(100, self.open_login)

    def _setup_theme(self):
        """Configure modern theme and styling"""
        style = ttk.Style()
        
        # Try to use a modern theme - these are available on different platforms
        available_themes = style.theme_names()
        
        # Preferred themes in order of preference
        preferred_themes = ['vista', 'xpnative', 'winnative', 'clam', 'alt', 'default']
        
        selected_theme = 'default'
        for theme in preferred_themes:
            if theme in available_themes:
                selected_theme = theme
                break
        
        style.theme_use(selected_theme)
        
        # Configure colors for a modern look
        bg_color = '#f0f0f0'  # Light gray background
        fg_color = '#333333'  # Dark gray text
        accent_color = '#0078d4'  # Microsoft blue accent
        hover_color = '#106ebe'  # Darker blue for hover
        
        # Configure the main window
        self.configure(bg=bg_color)
        
        # Style the notebook (tabs)
        style.configure('TNotebook', 
                       background=bg_color,
                       borderwidth=0)
        style.configure('TNotebook.Tab',
                       padding=[12, 8],
                       focuscolor='none')
        
        # Style buttons with modern look
        style.configure('TButton',
                       padding=[8, 4],
                       focuscolor='none')
        style.map('TButton',
                 background=[('active', hover_color),
                           ('pressed', accent_color)])
        
        # Style frames
        style.configure('TFrame', background=bg_color)
        style.configure('TLabelFrame', background=bg_color)
        
        # Style labels
        style.configure('TLabel', background=bg_color, foreground=fg_color)
        
        # Style entry fields
        style.configure('TEntry', fieldbackground='white', borderwidth=1)
        
        # Style treeview
        style.configure('Treeview',
                       background='white',
                       foreground=fg_color,
                       fieldbackground='white',
                       borderwidth=1)
        style.configure('Treeview.Heading',
                       background=bg_color,
                       foreground=fg_color,
                       borderwidth=1)
        
        # Style progressbar
        style.configure('TProgressbar',
                       background=accent_color,
                       borderwidth=0,
                       lightcolor=accent_color,
                       darkcolor=accent_color)

    def _create_menu(self):
        """Create the menu bar"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # Connection menu
        connection_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Connection", menu=connection_menu)
        connection_menu.add_command(label="Switch Jira Instance...", command=self.switch_jira_instance)
        connection_menu.add_command(label="Reconnect", command=self.reconnect)
        connection_menu.add_separator()
        connection_menu.add_command(label="Manage Saved Connections...", command=self.manage_connections)
        connection_menu.add_command(label="Connection Info", command=self.show_connection_info)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    def switch_jira_instance(self):
        """Open login dialog to switch to a different Jira instance"""
        if self._client is not None:
            # Ask for confirmation before switching
            result = messagebox.askyesno(
                "Switch Jira Instance", 
                "Are you sure you want to switch to a different Jira instance?\n\n"
                "This will disconnect from the current instance and any unsaved work may be lost.",
                icon='question'
            )
            if not result:
                return
        
        self.log("Switching Jira instance...")
        self.open_login()

    def reconnect(self):
        """Reconnect to the current Jira instance"""
        if self._current_connection_info is None:
            messagebox.showwarning("No Connection", "No previous connection to reconnect to.")
            return
        
        self.log("Reconnecting to Jira instance...")
        
        # Try to reconnect with saved credentials
        client = JiraClient(
            self._current_connection_info['base_url'],
            self._current_connection_info['email'], 
            self._current_connection_info['api_token'],
            log_fn=self.log
        )
        
        def test_and_reconnect():
            if client.test_connection():
                self.log("Reconnection successful.", "success")
                # Update the client reference without recreating tabs
                self._client = client
                if self._config_tab:
                    self._config_tab.client = client
                if self._jql_tab:
                    self._jql_tab.client = client
            else:
                self.log("Reconnection failed. Please check your connection.", "err")
                messagebox.showerror("Reconnection Failed", "Could not reconnect to Jira. Please switch instance or check your connection.")
        
        threading.Thread(target=test_and_reconnect, daemon=True).start()

    def manage_connections(self):
        """Open the connection management dialog"""
        ConnectionManagerWindow(self, log_fn=self.log)

    def show_connection_info(self):
        """Show information about the current connection"""
        if self._current_connection_info is None:
            messagebox.showinfo("Connection Info", "Not connected to any Jira instance.")
            return
        
        info = self._current_connection_info
        message = f"""Current Jira Connection:

URL: {info['base_url']}
Email: {info['email']}
Connected: {'Yes' if self._client else 'No'}"""
        
        messagebox.showinfo("Connection Info", message)

    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo("About", "Jira Metrics Tool\n\nA tool for analyzing Jira issues and generating metrics.")

    def _clear_tabs(self):
        """Clear existing tabs when switching instances"""
        # Remove all tabs except log
        for tab_id in self.nb.tabs():
            self.nb.forget(tab_id)
        
        # Reset tab references
        self._config_tab = None
        self._jql_tab = None

    def log(self, msg, level="info"):
        print(msg)
        self.log_console.write(msg, level)

    def open_login(self):
        """Open login window for initial connection or switching instances"""
        switching = self._client is not None
        
        # Clear existing tabs if switching instances
        if switching:
            self._clear_tabs()
            self._client = None
            self._current_connection_info = None
        
        LoginWindow(self, on_success=self.on_login, log_fn=self.log, switching_instance=switching)

    def on_login(self, client: JiraClient):
        """Handle successful login"""
        self._client = client
        
        # Store connection info for reconnection
        self._current_connection_info = {
            'base_url': client.base_url,
            'email': client.session.auth[0],  # Get email from session auth
            'api_token': client.session.auth[1]  # Get token from session auth
        }
        
        # Update window title to show connected instance
        instance_name = client.base_url.replace('https://', '').replace('http://', '')
        self.title(f"Jira Metrics - Connected to {instance_name}")
        
        try:
            fields = self._client.get_fields()
        except Exception as e:
            self.log(f"Failed to load fields metadata: {e}")
            fields = []
        field_id_to_name = {}
        field_name_to_id = {}
        for f in fields:
            fid = f.get("id")
            fname = f.get("name")
            if fid and fname:
                field_id_to_name[fid] = fname
                field_name_to_id.setdefault(fname, fid)

        # Clear existing tabs before creating new ones
        self._clear_tabs()

        self._config_tab = ConfigTab(self.nb, jira_client=self._client, log_fn=self.log,
                                     field_id_to_name=field_id_to_name, field_name_to_id=field_name_to_id)
        self._jql_tab = JQLTab(self.nb, jira_client=self._client, config_tab=self._config_tab,
                               log_fn=self.log, field_id_to_name=field_id_to_name)
        self._sprint_tab = SprintAnalysisTab(self.nb, jira_client=self._client, 
                                           log_fn=self.log, field_id_to_name=field_id_to_name)
        self._timeline_tab = TimelineReportTab(self.nb, jira_client=self._client, 
                                             log_fn=self.log, field_id_to_name=field_id_to_name)
        self.nb.add(self._config_tab, text="Configuration")
        self.nb.add(self._jql_tab, text="JQL Search")
        self.nb.add(self._sprint_tab, text="Sprint Analysis")
        self.nb.add(self._timeline_tab, text="Timeline Report")
        self.log(f"Connected to {instance_name} - Ready.")

if __name__ == "__main__":
    MainWindow().mainloop()