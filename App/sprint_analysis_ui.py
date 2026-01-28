"""
Standalone UI for Sprint Analysis feature.
This can be used as a reference or integrated into the main application.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from datetime import datetime, timedelta

from sprint_analysis import analyze_sprint_patterns
from jira_client import JiraClient
from jql_selector_widget import JQLSelectorWidget
from jql_manager import JQLManager

class SprintAnalysisWindow:
    def __init__(self, parent=None, jira_client=None):
        self.jira_client = jira_client
        self.jql_manager = JQLManager()  # Initialize JQL manager
        
        # Create window
        if parent:
            self.window = tk.Toplevel(parent)
        else:
            self.window = tk.Tk()
        
        self.window.title("Sprint Pattern Analysis")
        self.window.geometry("600x400")
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface"""
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # JQL Input
        jql_frame = ttk.LabelFrame(main_frame, text="JQL Query", padding=10)
        jql_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        # Use the JQL selector widget
        self.jql_selector = JQLSelectorWidget(jql_frame, self.jql_manager,
                                               default_value="project = YOUR_PROJECT AND sprint = YOUR_SPRINT")
        self.jql_selector.grid(row=0, column=0, sticky="ew")
        
        # Sprint Dates
        dates_frame = ttk.LabelFrame(main_frame, text="Sprint Dates", padding=10)
        dates_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        ttk.Label(dates_frame, text="Start Date (YYYY-MM-DD):").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.start_date_var = tk.StringVar(value="2024-01-01")
        start_entry = ttk.Entry(dates_frame, textvariable=self.start_date_var, width=15)
        start_entry.grid(row=0, column=1, padx=(0, 20))
        
        ttk.Label(dates_frame, text="End Date (YYYY-MM-DD):").grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.end_date_var = tk.StringVar(value="2024-01-14")
        end_entry = ttk.Entry(dates_frame, textvariable=self.end_date_var, width=15)
        end_entry.grid(row=0, column=3)
        
        # Quick date buttons
        quick_dates_frame = ttk.Frame(dates_frame)
        quick_dates_frame.grid(row=1, column=0, columnspan=4, pady=(10, 0))
        
        ttk.Button(quick_dates_frame, text="Last 2 Weeks", 
                  command=self.set_last_two_weeks).grid(row=0, column=0, padx=(0, 10))
        ttk.Button(quick_dates_frame, text="This Month", 
                  command=self.set_this_month).grid(row=0, column=1, padx=(0, 10))
        
        # Control buttons
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        
        ttk.Button(control_frame, text="🏃 Analyze Sprint Patterns", 
                  command=self.run_analysis).grid(row=0, column=0, padx=(0, 10))
        ttk.Button(control_frame, text="💾 Export to CSV", 
                  command=self.export_csv).grid(row=0, column=1)
        
        # Progress
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding=10)
        progress_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        
        self.progress_var = tk.StringVar(value="Ready")
        progress_label = ttk.Label(progress_frame, textvariable=self.progress_var)
        progress_label.grid(row=0, column=0, sticky="w")
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        
        # Results display
        results_frame = ttk.LabelFrame(main_frame, text="Results", padding=10)
        results_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        
        # Create treeview for results
        columns = ("Issue", "From Status", "To Status", "Date", "Sprint Day", "Progress %")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=8)
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)
        
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Configure grid weights
        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(4, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        jql_frame.grid_columnconfigure(0, weight=1)
        progress_frame.grid_columnconfigure(0, weight=1)
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)
        
        # Store results for export
        self.last_results = []
        self.last_headers = []
    
    def set_last_two_weeks(self):
        """Set dates to last two weeks"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=14)
        
        self.start_date_var.set(start_date.strftime("%Y-%m-%d"))
        self.end_date_var.set(end_date.strftime("%Y-%m-%d"))
    
    def set_this_month(self):
        """Set dates to current month"""
        now = datetime.now()
        start_date = now.replace(day=1)
        
        # Last day of month
        if now.month == 12:
            end_date = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
        
        self.start_date_var.set(start_date.strftime("%Y-%m-%d"))
        self.end_date_var.set(end_date.strftime("%Y-%m-%d"))
    
    def progress_callback(self, stage, done, total):
        """Progress callback for analysis"""
        self.progress_var.set(f"{stage} - {done}/{total}")
        if total > 0:
            self.progress_bar["maximum"] = total
            self.progress_bar["value"] = done
        self.window.update_idletasks()
    
    def run_analysis(self):
        """Run sprint pattern analysis"""
        if not self.jira_client:
            messagebox.showerror("Error", "No Jira client configured")
            return
        
        jql = self.jql_selector.get().strip()
        start_date = self.start_date_var.get().strip()
        end_date = self.end_date_var.get().strip()
        
        if not jql or not start_date or not end_date:
            messagebox.showerror("Error", "Please fill in all fields")
            return
        
        # Clear previous results
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        def worker():
            try:
                headers, row_iter = analyze_sprint_patterns(
                    jira_client=self.jira_client,
                    jql=jql,
                    sprint_start_str=start_date,
                    sprint_end_str=end_date,
                    progress_cb=self.progress_callback
                )
                
                results = list(row_iter())
                self.last_headers = headers
                self.last_results = results
                
                # Update UI in main thread
                self.window.after(0, lambda: self.display_results(results))
                
                return True
            except Exception as e:
                self.window.after(0, lambda: messagebox.showerror("Error", str(e)))
                return False
        
        threading.Thread(target=worker, daemon=True).start()
    
    def display_results(self, results):
        """Display results in the treeview"""
        for result in results:
            values = (
                result.get('issue_key', ''),
                result.get('from_status', ''),
                result.get('to_status', ''),
                result.get('transition_date', '')[:10],  # Just date part
                result.get('sprint_day', ''),
                f"{result.get('sprint_progress_percent', 0):.1f}%"
            )
            self.tree.insert("", "end", values=values)
        
        self.progress_var.set(f"Analysis complete - {len(results)} transitions found")
    
    def export_csv(self):
        """Export results to CSV"""
        if not self.last_results:
            messagebox.showwarning("Warning", "No results to export. Run analysis first.")
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
                
                messagebox.showinfo("Success", f"Results exported to {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Export failed: {e}")

def main():
    """Main function for standalone testing"""
    app = SprintAnalysisWindow()
    app.window.mainloop()

if __name__ == "__main__":
    main()