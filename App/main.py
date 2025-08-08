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
from export_json import export_json

APP_DIR = os.path.join(os.path.expanduser("~"), ".jira_metrics")
CREDS_PATH = os.path.join(APP_DIR, "credentials.json")
CONFIG_DIR = os.path.join(APP_DIR, "configs")

def ensure_app_dirs():
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)

def load_credentials():
    if os.path.exists(CREDS_PATH):
        with open(CREDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_credentials(base_url, email, api_token):
    ensure_app_dirs()
    with open(CREDS_PATH, "w", encoding="utf-8") as f:
        json.dump({"base_url": base_url, "email": email, "api_token": api_token}, f)

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
        self.configure(state="disabled", wrap="word")
        self.tag_config("err", foreground="red")
        self.tag_config("info", foreground="black")
    def write(self, msg, level="info"):
        self.configure(state="normal")
        self.insert("end", msg + "\n", level)
        self.see("end")
        self.configure(state="disabled")

class LoginWindow(tk.Toplevel):
    def __init__(self, master, on_success, log_fn):
        super().__init__(master)
        self.title("Jira Metrics - Login")
        self.resizable(False, False)
        self.on_success = on_success
        self.log = log_fn

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Jira URL:").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.url_var, width=40).grid(row=0, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text="Email:").grid(row=1, column=0, sticky="w")
        self.email_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.email_var, width=40).grid(row=1, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text="API Token:").grid(row=2, column=0, sticky="w")
        self.token_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.token_var, width=40, show="*").grid(row=2, column=1, columnspan=2, sticky="we")

        self.btn_login = ttk.Button(frm, text="Login", command=self.do_login)
        self.btn_login.grid(row=3, column=1, sticky="we", pady=(8, 0))
        self.btn_use_saved = ttk.Button(frm, text="Use Saved Credentials", command=self.use_saved)
        self.btn_use_saved.grid(row=3, column=2, sticky="we", pady=(8, 0))

        creds = load_credentials()
        if creds:
            self.url_var.set(creds.get("base_url", ""))
            self.email_var.set(creds.get("email", ""))

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def use_saved(self):
        creds = load_credentials()
        if not creds:
            messagebox.showerror("Error", "No saved credentials found.")
            return
        client = JiraClient(creds["base_url"], creds["email"], creds["api_token"], log_fn=self.log)
        self.log("Testing saved credentials...")
        if client.test_connection():
            self.log("Login success with saved credentials.")
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
                self.log("Login success.")
                save_credentials(base_url, email, token)
                self.on_success(client)
                self.destroy()
            else:
                messagebox.showerror("Login Failed", "Invalid credentials or URL.")
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
        left = ttk.LabelFrame(self, text="Fields", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,8), pady=8)

        ttk.Label(left, text="Enter an Issue Key to load fields:").grid(row=0, column=0, sticky="w")
        self.issue_key_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.issue_key_var, width=25).grid(row=0, column=1, sticky="we")
        ttk.Button(left, text="Load Fields", command=self.load_fields).grid(row=0, column=2, sticky="we", padx=(6,0))

        cols = ("selected", "field", "value")
        self.fields_tree = ttk.Treeview(left, columns=cols, show="headings", height=16)
        self.fields_tree.heading("selected", text="✔")
        self.fields_tree.heading("field", text="Field")
        self.fields_tree.heading("value", text="Example Value")
        self.fields_tree.column("selected", width=40, anchor="center")
        self.fields_tree.column("field", width=260, anchor="w")
        self.fields_tree.column("value", anchor="w")
        self.fields_tree.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(6,0))
        left.grid_columnconfigure(1, weight=1)
        left.grid_rowconfigure(1, weight=1)

        self.fields_tree.bind("<Button-1>", self._on_tree_click)

        right = ttk.LabelFrame(self, text="Metrics", padding=8)
        right.grid(row=0, column=1, sticky="nsew", pady=8)

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

        bottom = ttk.LabelFrame(self, text="Configuration Management", padding=8)
        bottom.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0,8))

        ttk.Label(bottom, text="Config Name:").grid(row=0, column=0, sticky="w")
        self.cfg_name_var = tk.StringVar()
        ttk.Entry(bottom, textvariable=self.cfg_name_var, width=30).grid(row=0, column=1, sticky="w")
        ttk.Button(bottom, text="Save Config", command=self.save_current_config).grid(row=0, column=2, padx=(8,0))
        ttk.Label(bottom, text="Load:").grid(row=0, column=3, padx=(16,4))
        self.cfg_combo = ttk.Combobox(bottom, values=list_configs(), state="readonly", width=30)
        self.cfg_combo.grid(row=0, column=4, sticky="we")
        ttk.Button(bottom, text="Load", command=self.load_selected_config).grid(row=0, column=5, padx=(6,0))

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
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
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self, padding=6)
        top.grid(row=0, column=0, sticky="nsew")
        ttk.Label(top, text="JQL:").grid(row=0, column=0, sticky="w")
        self.jql_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.jql_var, width=80).grid(row=0, column=1, sticky="we")
        ttk.Button(top, text="Search", command=self.search_jql).grid(row=0, column=2, padx=(6,0))
        self.count_var = tk.StringVar(value="Matches: 0")
        ttk.Label(top, textvariable=self.count_var).grid(row=0, column=3, padx=(10,0))
        ttk.Button(top, text="Export CSV", command=self.export_csv).grid(row=0, column=4, padx=(6,0))
        ttk.Button(top, text="Export JSON", command=self.export_json).grid(row=0, column=5, padx=(6,0))

        top.grid_columnconfigure(1, weight=1)

        pb_frame = ttk.Frame(self, padding=(6,0))
        pb_frame.grid(row=1, column=0, sticky="we")
        self.pb = ttk.Progressbar(pb_frame, orient="horizontal", mode="determinate", value=0)
        self.pb.grid(row=0, column=0, sticky="we")
        self.stage_var = tk.StringVar(value="")
        ttk.Label(pb_frame, textvariable=self.stage_var).grid(row=1, column=0, sticky="w", pady=(2,0))
        pb_frame.grid_columnconfigure(0, weight=1)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def search_jql(self):
        jql = self.jql_var.get().strip()
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
        jql = self.jql_var.get().strip()
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
            self.stage_var.set("")
            self.log("Export completed.")
            messagebox.showinfo("Done", "CSV export completed.")

        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()

    def export_json(self):
        jql = self.jql_var.get().strip()
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
            self.stage_var.set("")
            self.log("JSON export completed.")
            messagebox.showinfo("Done", "JSON export completed.")

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

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Jira Metrics")
        self.geometry("1100x720")
        self.minsize(950, 620)
        ensure_app_dirs()

        self.log_console = LogConsole(self, height=8)
        self.nb = ttk.Notebook(self)
        self.nb.grid(row=0, column=0, sticky="nsew")
        self.log_console.grid(row=1, column=0, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self._client = None
        self._config_tab = None
        self._jql_tab = None

        self.after(100, self.open_login)

    def log(self, msg):
        print(msg)
        self.log_console.write(msg)

    def open_login(self):
        LoginWindow(self, on_success=self.on_login, log_fn=self.log)

    def on_login(self, client: JiraClient):
        self._client = client
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

        self._config_tab = ConfigTab(self.nb, jira_client=self._client, log_fn=self.log,
                                     field_id_to_name=field_id_to_name, field_name_to_id=field_name_to_id)
        self._jql_tab = JQLTab(self.nb, jira_client=self._client, config_tab=self._config_tab,
                               log_fn=self.log, field_id_to_name=field_id_to_name)
        self.nb.add(self._config_tab, text="Configuration")
        self.nb.add(self._jql_tab, text="JQL Search")
        self.log("Ready.")

if __name__ == "__main__":
    MainWindow().mainloop()