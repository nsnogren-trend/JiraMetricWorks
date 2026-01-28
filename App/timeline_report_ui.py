"""
Timeline Report UI Tab
Provides interface for configuring and generating timeline reports.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import threading
import json
import os
import re
from datetime import datetime

from timeline_report import build_timeline_data, generate_html_report
from jql_selector_widget import JQLSelectorWidget
from jql_manager import JQLManager

class TimelineReportTab(ttk.Frame):
    def __init__(self, master, jira_client, log_fn, field_id_to_name):
        super().__init__(master)
        self.client = jira_client
        self.log = log_fn
        self.field_id_to_name = field_id_to_name
        
        self.projects = []
        self.statuses = []
        self.status_widgets = []  # Track dynamically created widgets
        self.timeline_data = None
        self.jql_manager = JQLManager()  # Initialize JQL manager
        self.last_config_file = os.path.join(os.path.dirname(__file__), 'timeline_last_config.json')
        self.saved_configs_dir = os.path.join(os.path.dirname(__file__), 'saved_timeline_configs')
        
        # Create saved configs directory if it doesn't exist
        os.makedirs(self.saved_configs_dir, exist_ok=True)
        
        self._build_ui()
        self._load_projects()
        self._load_saved_configs_list()
        self._auto_load_last_config()
    
    def _build_ui(self):
        # Main scrollable area
        main_canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=main_canvas.yview)
        scrollable_frame = ttk.Frame(main_canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # --- Project Selection ---
        project_frame = ttk.LabelFrame(scrollable_frame, text="1. Select Project", padding=10)
        project_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        ttk.Label(project_frame, text="Project:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(project_frame, textvariable=self.project_var, width=50, state="readonly")
        self.project_combo.grid(row=0, column=1, sticky="we", padx=(0, 10))
        self.project_combo.bind("<<ComboboxSelected>>", self._on_project_selected)
        
        ttk.Button(project_frame, text="🔄 Refresh", command=self._load_projects).grid(row=0, column=2)
        
        project_frame.columnconfigure(1, weight=1)
        
        # --- JQL Query ---
        jql_frame = ttk.LabelFrame(scrollable_frame, text="2. Define Query", padding=10)
        jql_frame.pack(fill="x", padx=10, pady=5)
        
        # Use the JQL selector widget
        self.jql_selector = JQLSelectorWidget(jql_frame, self.jql_manager, 
                                               default_value="project = YOUR_PROJECT AND sprint = YOUR_SPRINT")
        self.jql_selector.pack(fill="x", pady=(0, 10))
        
        # Test query button
        ttk.Button(jql_frame, text="📋 Test Query", command=self._test_jql).pack(anchor="w")
        
        # --- Date Range (Optional) ---
        date_frame = ttk.LabelFrame(scrollable_frame, text="3. Date Range (Optional)", padding=10)
        date_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(date_frame, text="Leave blank to auto-calculate from data").pack(anchor="w", pady=(0, 10))
        
        date_inputs = ttk.Frame(date_frame)
        date_inputs.pack(fill="x")
        
        ttk.Label(date_inputs, text="Start Date:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.start_date_var = tk.StringVar()
        ttk.Entry(date_inputs, textvariable=self.start_date_var, width=20).grid(row=0, column=1, padx=(0, 20))
        
        ttk.Label(date_inputs, text="End Date:").grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.end_date_var = tk.StringVar()
        ttk.Entry(date_inputs, textvariable=self.end_date_var, width=20).grid(row=0, column=3)
        
        ttk.Label(date_frame, text="Format: YYYY-MM-DD or YYYY-MM-DD HH:MM", font=('Segoe UI', 9, 'italic')).pack(anchor="w", pady=(5, 0))
        
        # --- Status Configuration ---
        status_config_frame = ttk.LabelFrame(scrollable_frame, text="4. Configure Status Tracking", padding=10)
        status_config_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        ttk.Label(status_config_frame, 
                 text="Set integer order for statuses you want to track (lower = earlier in workflow).",
                 wraplength=800).pack(anchor="w", pady=(0, 10))
        
        ttk.Button(status_config_frame, text="🔄 Load Statuses from Project", 
                  command=self._load_statuses).pack(anchor="w", pady=(0, 10))
        
        # Status list container
        self.status_list_frame = ttk.Frame(status_config_frame)
        self.status_list_frame.pack(fill="both", expand=True)
        
        # --- Actions ---
        action_frame = ttk.LabelFrame(scrollable_frame, text="5. Generate Report", padding=10)
        action_frame.pack(fill="x", padx=10, pady=5)
        
        # Saved configurations selector
        saved_config_container = ttk.Frame(action_frame)
        saved_config_container.pack(fill="x", pady=(0, 10))
        
        ttk.Label(saved_config_container, text="Saved Configuration:").pack(side="left", padx=(0, 10))
        self.saved_config_var = tk.StringVar()
        self.saved_config_combo = ttk.Combobox(saved_config_container, textvariable=self.saved_config_var, 
                                                width=40, state="readonly")
        self.saved_config_combo.pack(side="left", padx=(0, 10))
        self.saved_config_combo.bind("<<ComboboxSelected>>", self._on_saved_config_selected)
        
        ttk.Button(saved_config_container, text="🔄 Refresh", 
                  command=self._load_saved_configs_list).pack(side="left", padx=(0, 10))
        ttk.Button(saved_config_container, text="🗑️ Delete", 
                  command=self._delete_saved_config).pack(side="left")
        
        # Action buttons
        btn_container = ttk.Frame(action_frame)
        btn_container.pack(fill="x")
        
        # Primary action button with larger emphasis
        self.run_saved_btn = ttk.Button(btn_container, text="▶️ Run Selected Config", 
                  command=self._run_selected_config, width=20)
        self.run_saved_btn.pack(side="left", padx=(0, 10))
        self.run_saved_btn.config(state="disabled")  # Initially disabled
        
        ttk.Button(btn_container, text="📊 Generate Report", 
                  command=self._generate_report).pack(side="left", padx=(0, 10))
        ttk.Button(btn_container, text="💾 Save as New Config", 
                  command=self._save_new_config).pack(side="left")
        
        # --- Progress ---
        progress_frame = ttk.LabelFrame(scrollable_frame, text="Progress", padding=10)
        progress_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.progress_var).pack(anchor="w", pady=(0, 5))
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(fill="x")
    
    def _load_projects(self):
        """Load available projects"""
        def worker():
            try:
                # Get all projects
                projects = self.client.get_all_projects()
                return projects
            except Exception as e:
                self.log(f"Error loading projects: {e}", "error")
                return None
        
        def on_done(projects):
            self.progress_var.set("Ready")
            if projects:
                self.projects = projects
                project_names = [f"{p['name']} ({p['key']})" for p in projects]
                self.project_combo['values'] = project_names
                self.log(f"Loaded {len(projects)} projects")
            else:
                self.log("Failed to load projects", "error")
        
        self.progress_var.set("Loading projects...")
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()
    
    def _on_project_selected(self, event=None):
        """Handle project selection"""
        selection = self.project_var.get()
        if selection:
            # Extract project key
            try:
                project_key = selection.split("(")[-1].split(")")[0]
                self.log(f"Selected project: {project_key}")
            except:
                pass
    
    def _test_jql(self):
        """Test the JQL query"""
        jql = self.jql_selector.get().strip()
        if not jql:
            messagebox.showwarning("Warning", "Please enter a JQL query")
            return
        
        def worker():
            try:
                keys, total = self.client.search_jql(jql, max_results=10, fields=["key"], expand_changelog=False)
                return keys, total
            except Exception as e:
                return None, str(e)
        
        def on_done(result):
            keys, total = result
            self.progress_var.set("Ready")
            if keys is not None:
                messagebox.showinfo("Query Test", 
                                   f"Query is valid!\n\nFound {total} issues.\n\nFirst 10:\n" + "\n".join(keys[:10]))
                self.log(f"JQL query returned {total} issues", "success")
            else:
                messagebox.showerror("Query Error", f"Query failed:\n\n{total}")
                self.log("JQL query failed", "error")
        
        self.progress_var.set("Testing query...")
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()
    
    def _load_statuses(self):
        """Load statuses for the selected project"""
        selection = self.project_var.get()
        if not selection:
            messagebox.showwarning("Warning", "Please select a project first")
            return
        
        try:
            project_key = selection.split("(")[-1].split(")")[0]
        except:
            messagebox.showerror("Error", "Could not parse project selection")
            return
        
        def worker():
            try:
                # Get statuses for project
                statuses = self.client.get_project_statuses(project_key)
                return statuses
            except Exception as e:
                self.log(f"Error loading statuses: {e}", "error")
                return None
        
        def on_done(statuses):
            self.progress_var.set("Ready")
            if statuses:
                self.statuses = statuses
                self._build_status_list()
                self.log(f"Loaded {len(statuses)} statuses")
            else:
                self.log("Failed to load statuses", "error")
        
        self.progress_var.set("Loading statuses...")
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()
    
    def _build_status_list(self):
        """Build the status configuration list"""
        # Clear existing widgets
        for widget in self.status_widgets:
            widget.destroy()
        self.status_widgets.clear()
        
        # Create header
        header_frame = ttk.Frame(self.status_list_frame)
        header_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(header_frame, text="Status Name", font=('Segoe UI', 9, 'bold'), width=30).pack(side="left")
        ttk.Label(header_frame, text="Order", font=('Segoe UI', 9, 'bold'), width=8).pack(side="left", padx=(10, 0))
        ttk.Label(header_frame, text="Custom Color (optional)", font=('Segoe UI', 9, 'bold'), width=20).pack(side="left", padx=(10, 0))
        self.status_widgets.append(header_frame)
        
        # Create entry for each status
        # Statuses can be either strings or dicts, normalize to dicts
        status_dicts = []
        for status in self.statuses:
            if isinstance(status, str):
                status_dicts.append({'name': status})
            else:
                status_dicts.append(status)
        
        for status in status_dicts:
            status_name = status.get('name', 'Unknown')
            
            row_frame = ttk.Frame(self.status_list_frame)
            row_frame.pack(fill="x", pady=2)
            
            # Status name label
            ttk.Label(row_frame, text=status_name, width=30).pack(side="left")
            
            # Order entry
            order_var = tk.StringVar()
            order_entry = ttk.Entry(row_frame, textvariable=order_var, width=8)
            order_entry.pack(side="left", padx=(10, 0))
            
            # Color entry with validation
            color_var = tk.StringVar()
            color_entry = ttk.Entry(row_frame, textvariable=color_var, width=12)
            color_entry.pack(side="left", padx=(10, 5))
            
            # Color preview/picker button
            color_button = tk.Button(row_frame, text="🎨", width=3, height=1,
                                     command=lambda v=color_var, b=None: self._pick_color(v, b))
            color_button.pack(side="left", padx=(0, 5))
            
            # Store button reference for later color updates
            color_button.config(command=lambda v=color_var, b=color_button: self._pick_color(v, b))
            
            # Update button color when entry changes
            def update_preview(var, btn):
                color = var.get().strip()
                if self._validate_color(color):
                    try:
                        btn.config(bg=color)
                    except:
                        btn.config(bg='SystemButtonFace')
                else:
                    btn.config(bg='SystemButtonFace')
            
            color_var.trace_add('write', lambda *args, v=color_var, b=color_button: update_preview(v, b))
            
            # Store references
            status['order_var'] = order_var
            status['color_var'] = color_var
            status['color_button'] = color_button
            
            self.status_widgets.append(row_frame)

        # Update self.statuses with the dict versions
        self.statuses = status_dicts
        
        # Apply any pending configuration
        self._apply_pending_status_config()
    
    def _validate_color(self, color_str):
        """Validate hex color format (#RRGGBB or #RGB)"""
        if not color_str:
            return False
        return bool(re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color_str))
    
    def _pick_color(self, color_var, button):
        """Open color picker dialog"""
        current_color = color_var.get().strip()
        if not self._validate_color(current_color):
            current_color = '#FFFFFF'
        
        # Open color chooser
        color = colorchooser.askcolor(
            color=current_color,
            title="Choose Status Color"
        )
        
        if color and color[1]:  # color is ((r,g,b), '#RRGGBB')
            hex_color = color[1].upper()
            color_var.set(hex_color)
            button.config(bg=hex_color)
    
    def _get_status_order(self):
        """Get the configured status order mapping and custom colors"""
        status_order = {}
        status_colors = {}
        
        for status in self.statuses:
            status_name = status['name']
            
            # Get order
            order_str = status.get('order_var', tk.StringVar()).get().strip()
            if order_str:
                try:
                    order = int(order_str)
                    status_order[status_name] = order
                except ValueError:
                    pass
            
            # Get custom color
            color_str = status.get('color_var', tk.StringVar()).get().strip()
            if color_str and self._validate_color(color_str):
                status_colors[status_name] = color_str.upper()
        
        return status_order, status_colors
    
    def _generate_report(self):
        """Generate the timeline report"""
        jql = self.jql_selector.get().strip()
        if not jql:
            messagebox.showwarning("Warning", "Please enter a JQL query")
            return
        
        status_order, status_colors = self._get_status_order()
        if not status_order:
            messagebox.showwarning("Warning", "Please configure at least one status with an order number")
            return
        
        # Parse optional date range
        start_date = None
        end_date = None
        
        start_str = self.start_date_var.get().strip()
        end_str = self.end_date_var.get().strip()
        
        if start_str:
            try:
                from dateutil import parser as dtparser, tz
                start_date = dtparser.parse(start_str)
                if start_date.tzinfo is None:
                    start_date = start_date.replace(tzinfo=tz.UTC)
            except Exception as e:
                messagebox.showerror("Error", f"Invalid start date format: {e}")
                return
        
        if end_str:
            try:
                from dateutil import parser as dtparser, tz
                end_date = dtparser.parse(end_str)
                if end_date.tzinfo is None:
                    end_date = end_date.replace(tzinfo=tz.UTC)
            except Exception as e:
                messagebox.showerror("Error", f"Invalid end date format: {e}")
                return
        
        # Get project name for report
        project_name = None
        selection = self.project_var.get()
        if selection:
            try:
                project_name = selection.split(" (")[0]
            except:
                pass
        
        def progress_callback(stage, done, total):
            if total > 0:
                pct = (done / total) * 100
                self.progress_bar['value'] = pct
            self.progress_var.set(f"{stage} ({done}/{total})")
            self.update_idletasks()
        
        def worker():
            try:
                # Build timeline data
                timeline_data = build_timeline_data(
                    self.client, jql, status_order, start_date, end_date, progress_callback, status_colors
                )
                
                # Generate HTML
                progress_callback("Generating HTML...", 0, 1)
                html_content = generate_html_report(timeline_data, jql, project_name)
                progress_callback("Generating HTML...", 1, 1)
                
                return html_content, timeline_data
            except Exception as e:
                self.log(f"Error generating report: {e}", "error")
                import traceback
                traceback.print_exc()
                return None, str(e)
        
        def on_done(result):
            html_content, timeline_data = result
            self.progress_var.set("Ready")
            self.progress_bar['value'] = 0
            
            if html_content and not isinstance(timeline_data, str):
                self.timeline_data = timeline_data
                
                # Save HTML to file
                file_path = filedialog.asksaveasfilename(
                    title="Save Timeline Report",
                    defaultextension=".html",
                    filetypes=[("HTML files", "*.html"), ("All files", "*.*")]
                )
                
                if file_path:
                    try:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                        self.log(f"Report saved to {file_path}", "success")
                        messagebox.showinfo("Success", f"Report saved to:\n{file_path}")
                        
                        # Auto-save current configuration as last used
                        self._auto_save_current_config()
                        
                        # Ask to open
                        if messagebox.askyesno("Open Report", "Would you like to open the report in your browser?"):
                            import webbrowser
                            webbrowser.open('file://' + os.path.abspath(file_path))
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to save report:\n{e}")
                        self.log(f"Failed to save report: {e}", "error")
            else:
                error_msg = timeline_data if isinstance(timeline_data, str) else "Unknown error"
                messagebox.showerror("Error", f"Failed to generate report:\n\n{error_msg}")
                self.log("Report generation failed", "error")
        
        self.log("Generating timeline report...")
        self.progress_var.set("Starting...")
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()
    

    
    def _load_saved_configs_list(self):
        """Load the list of saved configurations"""
        try:
            if not os.path.exists(self.saved_configs_dir):
                os.makedirs(self.saved_configs_dir, exist_ok=True)
            
            config_files = [f[:-5] for f in os.listdir(self.saved_configs_dir) 
                           if f.endswith('.json')]
            config_files.sort()
            
            self.saved_config_combo['values'] = config_files
            
            # Auto-select if there's a last used config
            if os.path.exists(self.last_config_file):
                try:
                    with open(self.last_config_file, 'r', encoding='utf-8') as f:
                        last_config = json.load(f)
                        last_name = last_config.get('_config_name', '')
                        if last_name and last_name in config_files:
                            self.saved_config_var.set(last_name)
                            self.run_saved_btn.config(state="normal")
                except:
                    pass
            
            if config_files:
                self.log(f"Loaded {len(config_files)} saved configurations")
            
        except Exception as e:
            self.log(f"Failed to load saved configurations: {e}", "warning")
    
    def _on_saved_config_selected(self, event=None):
        """Handle saved configuration selection"""
        config_name = self.saved_config_var.get()
        if config_name:
            self.run_saved_btn.config(state="normal")
            self._load_config_by_name(config_name)
    
    def _load_config_by_name(self, config_name):
        """Load a specific saved configuration by name"""
        config_path = os.path.join(self.saved_configs_dir, f"{config_name}.json")
        
        if not os.path.exists(config_path):
            messagebox.showerror("Error", f"Configuration '{config_name}' not found")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self._apply_config(config)
            self.log(f"Loaded configuration: {config_name}", "success")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration:\n{e}")
    
    def _apply_config(self, config, skip_status_load=False):
        """Apply a configuration to the UI"""
        # Apply basic configuration
        if 'project' in config:
            self.project_var.set(config['project'])
        if 'jql' in config:
            self.jql_selector.set(config['jql'])
        if 'start_date' in config:
            self.start_date_var.set(config['start_date'])
        if 'end_date' in config:
            self.end_date_var.set(config['end_date'])
        
        # Store config for status application
        self._pending_config = config
        
        # If config has saved statuses, use them directly
        if 'saved_statuses' in config and config['saved_statuses']:
            # Load statuses from config
            self._load_statuses_from_config(config)
        elif not skip_status_load:
            # Try to auto-load statuses from the project
            selection = self.project_var.get()
            if selection:
                try:
                    project_key = selection.split("(")[-1].split(")")[0]
                    self._auto_load_project_statuses(project_key, config)
                except:
                    # If we can't parse project, load statuses from config if available
                    if 'status_order' in config:
                        self._load_statuses_from_config(config)
    
    def _load_statuses_from_config(self, config):
        """Load statuses directly from saved config"""
        saved_statuses = config.get('saved_statuses', [])
        
        if saved_statuses:
            # Use saved status list
            self.statuses = saved_statuses
        else:
            # Reconstruct from status_order and status_colors
            status_order = config.get('status_order', {})
            status_colors = config.get('status_colors', {})
            all_status_names = set(status_order.keys()) | set(status_colors.keys())
            self.statuses = [{'name': name} for name in sorted(all_status_names)]
        
        # Build the UI
        self._build_status_list()
        
        # Apply the configuration
        self._apply_pending_status_config()
        
        self.log(f"Loaded {len(self.statuses)} statuses from configuration", "success")
    
    def _auto_load_project_statuses(self, project_key, config):
        """Auto-load statuses for a project and apply config"""
        def worker():
            try:
                statuses = self.client.get_project_statuses(project_key)
                return statuses
            except Exception as e:
                self.log(f"Error loading statuses: {e}", "error")
                return None
        
        def on_done(statuses):
            self.progress_var.set("Ready")
            if statuses:
                self.statuses = statuses
                self._build_status_list()
                self._apply_pending_status_config()
                self.log(f"Auto-loaded {len(statuses)} statuses from project", "success")
            else:
                # Fallback to loading from config
                self._load_statuses_from_config(config)
        
        self.progress_var.set("Loading statuses...")
        threading.Thread(target=lambda: self._run_worker(worker, on_done), daemon=True).start()
    
    def _delete_saved_config(self):
        """Delete the selected saved configuration"""
        config_name = self.saved_config_var.get()
        if not config_name:
            messagebox.showwarning("Warning", "Please select a configuration to delete")
            return
        
        if not messagebox.askyesno("Confirm Delete", 
                                   f"Are you sure you want to delete the configuration '{config_name}'?"):
            return
        
        try:
            config_path = os.path.join(self.saved_configs_dir, f"{config_name}.json")
            if os.path.exists(config_path):
                os.remove(config_path)
                self.log(f"Deleted configuration: {config_name}", "success")
                self.saved_config_var.set('')
                self.run_saved_btn.config(state="disabled")
                self._load_saved_configs_list()
            else:
                messagebox.showerror("Error", f"Configuration '{config_name}' not found")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete configuration:\n{e}")
    
    def _run_selected_config(self):
        """Run the report with the selected saved configuration"""
        config_name = self.saved_config_var.get()
        if not config_name:
            messagebox.showwarning("Warning", "Please select a saved configuration first")
            return
        
        # Configuration is already loaded, just generate the report
        self._generate_report()
    
    def _save_new_config(self):
        """Save the current configuration with a new name"""
        # Prompt for configuration name
        dialog = tk.Toplevel(self)
        dialog.title("Save Configuration")
        dialog.geometry("400x150")
        dialog.transient(self)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Configuration Name:", padding=10).pack(anchor="w")
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=50)
        name_entry.pack(padx=10, pady=(0, 10), fill="x")
        name_entry.focus()
        
        ttk.Label(dialog, text="(e.g., 'Sprint 23 - Project X', 'Q4 2024 Report')", 
                 font=('Segoe UI', 9, 'italic'), padding=(10, 0)).pack(anchor="w")
        
        result = {'name': None}
        
        def save_action():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Please enter a configuration name")
                return
            # Sanitize filename
            name = re.sub(r'[<>:"/\\|?*]', '_', name)
            result['name'] = name
            dialog.destroy()
        
        def cancel_action():
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Save", command=save_action).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=cancel_action).pack(side="left", padx=5)
        
        # Bind Enter key
        name_entry.bind('<Return>', lambda e: save_action())
        
        dialog.wait_window()
        
        if not result['name']:
            return
        
        config_name = result['name']
        
        # Build configuration
        config = {
            '_config_name': config_name,
            'project': self.project_var.get(),
            'jql': self.jql_selector.get(),
            'start_date': self.start_date_var.get(),
            'end_date': self.end_date_var.get(),
            'status_order': {},
            'status_colors': {},
            'saved_statuses': []  # Save complete status list
        }
        
        # Save complete status information
        for status in self.statuses:
            status_name = status['name']
            
            # Create a clean status entry
            saved_status = {'name': status_name}
            
            # Save order
            order_str = status.get('order_var', tk.StringVar()).get().strip()
            if order_str:
                config['status_order'][status_name] = order_str
                saved_status['order'] = order_str
            
            # Save custom color
            color_str = status.get('color_var', tk.StringVar()).get().strip()
            if color_str and self._validate_color(color_str):
                config['status_colors'][status_name] = color_str.upper()
                saved_status['color'] = color_str.upper()
            
            config['saved_statuses'].append(saved_status)
        
        # Save to file
        config_path = os.path.join(self.saved_configs_dir, f"{config_name}.json")
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            
            # Also save as last used
            with open(self.last_config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            
            self.log(f"Configuration saved: {config_name}", "success")
            messagebox.showinfo("Success", f"Configuration '{config_name}' saved successfully")
            
            # Refresh the list and select the new config
            self._load_saved_configs_list()
            self.saved_config_var.set(config_name)
            self.run_saved_btn.config(state="normal")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration:\n{e}")
    
    def _auto_save_current_config(self):
        """Automatically save current configuration as last used"""
        try:
            config_name = self.saved_config_var.get()
            
            config = {
                '_config_name': config_name,
                'project': self.project_var.get(),
                'jql': self.jql_selector.get(),
                'start_date': self.start_date_var.get(),
                'end_date': self.end_date_var.get(),
                'status_order': {},
                'status_colors': {},
                'saved_statuses': []  # Save complete status list
            }
            
            # Save complete status information
            for status in self.statuses:
                status_name = status['name']
                
                # Create a clean status entry
                saved_status = {'name': status_name}
                
                # Save order
                order_str = status.get('order_var', tk.StringVar()).get().strip()
                if order_str:
                    config['status_order'][status_name] = order_str
                    saved_status['order'] = order_str
                
                # Save custom color
                color_str = status.get('color_var', tk.StringVar()).get().strip()
                if color_str and self._validate_color(color_str):
                    config['status_colors'][status_name] = color_str.upper()
                    saved_status['color'] = color_str.upper()
                
                config['saved_statuses'].append(saved_status)
            
            with open(self.last_config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            
            # Enable the run button if a config is selected
            if config_name:
                self.run_saved_btn.config(state="normal")
            self.log("Configuration auto-saved", "success")
            
        except Exception as e:
            self.log(f"Failed to auto-save configuration: {e}", "warning")
    
    def _auto_load_last_config(self):
        """Automatically load the last used configuration if it exists"""
        if not os.path.exists(self.last_config_file):
            return
        
        try:
            with open(self.last_config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self._apply_config(config)
            
            # Select the config in dropdown if it has a name
            config_name = config.get('_config_name', '')
            if config_name:
                self.saved_config_var.set(config_name)
                self.run_saved_btn.config(state="normal")
            
            self.log("Last configuration auto-loaded", "success")
            
        except Exception as e:
            self.log(f"Failed to auto-load last configuration: {e}", "warning")
    
    def _apply_pending_status_config(self):
        """Apply pending status configuration after statuses are loaded"""
        if not hasattr(self, '_pending_config') or not self._pending_config:
            return
        
        config = self._pending_config
        status_order = config.get('status_order', {})
        status_colors = config.get('status_colors', {})
        
        for status in self.statuses:
            status_name = status['name']
            
            # Apply order
            if status_name in status_order:
                status.get('order_var', tk.StringVar()).set(status_order[status_name])
            
            # Apply color
            if status_name in status_colors:
                color_var = status.get('color_var', tk.StringVar())
                color_var.set(status_colors[status_name])
                # Update button background
                if 'color_button' in status:
                    try:
                        status['color_button'].config(bg=status_colors[status_name])
                    except:
                        pass
        
        self._pending_config = None
    
    def _load_config(self):
        """Load a configuration from file (legacy support)"""
        file_path = filedialog.askopenfilename(
            title="Load Timeline Configuration",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self._apply_config(config, skip_status_load=False)
            
            self.log(f"Configuration loaded from {file_path}", "success")
            messagebox.showinfo("Success", "Configuration loaded successfully")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration:\n{e}")
    
    def _run_worker(self, worker_fn, on_done_fn):
        """Run a worker function in background and call on_done with result"""
        try:
            result = worker_fn()
            self.after(0, lambda: on_done_fn(result))
        except Exception as e:
            self.after(0, lambda: on_done_fn(None))
