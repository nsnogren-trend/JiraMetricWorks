"""
JQL Selector Widget
A reusable widget that provides both dropdown selection of saved queries and manual entry.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from jql_manager import JQLManager

class JQLSelectorWidget(ttk.Frame):
    """Widget that allows users to select from saved JQL queries or enter custom ones"""
    
    def __init__(self, master, jql_manager: JQLManager = None, default_value: str = "", **kwargs):
        """Initialize the JQL selector widget
        
        Args:
            master: Parent widget
            jql_manager: JQLManager instance (creates new one if None)
            default_value: Default JQL text to display
            **kwargs: Additional arguments for ttk.Frame
        """
        super().__init__(master, **kwargs)
        
        self.jql_manager = jql_manager or JQLManager()
        self.jql_var = tk.StringVar(value=default_value)
        
        self._build_ui()
        self._refresh_saved_queries()
    
    def _build_ui(self):
        """Build the widget UI"""
        # Top row: Dropdown + Manage button
        top_row = ttk.Frame(self)
        top_row.pack(fill="x", pady=(0, 5))
        
        ttk.Label(top_row, text="Saved Queries:").pack(side="left", padx=(0, 5))
        
        self.query_combo = ttk.Combobox(top_row, state="readonly", width=40)
        self.query_combo.pack(side="left", padx=(0, 5))
        self.query_combo.bind("<<ComboboxSelected>>", self._on_query_selected)
        
        ttk.Button(top_row, text="💾 Save Current", 
                  command=self._save_current_query).pack(side="left", padx=(0, 5))
        ttk.Button(top_row, text="🗑️ Delete", 
                  command=self._delete_selected_query).pack(side="left", padx=(0, 5))
        ttk.Button(top_row, text="✏️ Rename", 
                  command=self._rename_selected_query).pack(side="left")
        
        # Bottom row: JQL text entry
        bottom_row = ttk.Frame(self)
        bottom_row.pack(fill="x")
        
        ttk.Label(bottom_row, text="JQL Query:").pack(side="left", padx=(0, 5))
        
        jql_entry = ttk.Entry(bottom_row, textvariable=self.jql_var, width=80)
        jql_entry.pack(side="left", fill="x", expand=True)
    
    def _refresh_saved_queries(self):
        """Refresh the dropdown list of saved queries"""
        self.jql_manager.load_queries()
        query_names = self.jql_manager.get_query_names()
        
        if query_names:
            self.query_combo['values'] = [""] + query_names  # Empty string for no selection
        else:
            self.query_combo['values'] = [""]
        
        self.query_combo.set("")  # Clear selection
    
    def _on_query_selected(self, event=None):
        """Handle selection of a saved query"""
        selected_name = self.query_combo.get()
        if not selected_name:
            return
        
        query = self.jql_manager.get_query(selected_name)
        if query:
            self.jql_var.set(query['jql'])
            
            # Show description if available
            if query.get('description'):
                messagebox.showinfo("Query Description", 
                                   f"Query: {selected_name}\n\n{query['description']}")
    
    def _save_current_query(self):
        """Save the current JQL query"""
        current_jql = self.jql_var.get().strip()
        if not current_jql:
            messagebox.showwarning("Warning", "Please enter a JQL query first")
            return
        
        # Ask for name
        name = simpledialog.askstring("Save Query", "Enter a name for this query:")
        if not name:
            return
        
        name = name.strip()
        
        # Check if name already exists
        if self.jql_manager.get_query(name):
            if not messagebox.askyesno("Query Exists", 
                                       f"A query named '{name}' already exists.\n\nOverwrite it?"):
                return
            
            # Ask for description
            description = simpledialog.askstring("Query Description (Optional)", 
                                                 "Enter a description for this query:",
                                                 initialvalue=self.jql_manager.get_query(name).get('description', ''))
            description = description or ""
            
            if self.jql_manager.update_query(name, current_jql, description):
                messagebox.showinfo("Success", f"Query '{name}' updated successfully")
                self._refresh_saved_queries()
            else:
                messagebox.showerror("Error", "Failed to update query")
        else:
            # Ask for description
            description = simpledialog.askstring("Query Description (Optional)", 
                                                 "Enter a description for this query:")
            description = description or ""
            
            if self.jql_manager.add_query(name, current_jql, description):
                messagebox.showinfo("Success", f"Query '{name}' saved successfully")
                self._refresh_saved_queries()
            else:
                messagebox.showerror("Error", "Failed to save query")
    
    def _delete_selected_query(self):
        """Delete the currently selected saved query"""
        selected_name = self.query_combo.get()
        if not selected_name:
            messagebox.showwarning("Warning", "Please select a saved query to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", 
                              f"Are you sure you want to delete the query '{selected_name}'?"):
            if self.jql_manager.delete_query(selected_name):
                messagebox.showinfo("Success", f"Query '{selected_name}' deleted")
                self._refresh_saved_queries()
                # Clear the entry if it was showing the deleted query
                query = self.jql_manager.get_query(selected_name)
                if query and self.jql_var.get() == query['jql']:
                    self.jql_var.set("")
            else:
                messagebox.showerror("Error", "Failed to delete query")
    
    def _rename_selected_query(self):
        """Rename the currently selected saved query"""
        selected_name = self.query_combo.get()
        if not selected_name:
            messagebox.showwarning("Warning", "Please select a saved query to rename")
            return
        
        query = self.jql_manager.get_query(selected_name)
        if not query:
            return
        
        # Ask for new name
        new_name = simpledialog.askstring("Rename Query", 
                                         f"Enter new name for '{selected_name}':",
                                         initialvalue=selected_name)
        if not new_name or new_name.strip() == selected_name:
            return
        
        new_name = new_name.strip()
        
        # Check if new name already exists
        if self.jql_manager.get_query(new_name):
            messagebox.showerror("Error", f"A query named '{new_name}' already exists")
            return
        
        # Delete old and add with new name
        if self.jql_manager.delete_query(selected_name):
            if self.jql_manager.add_query(new_name, query['jql'], query.get('description', '')):
                messagebox.showinfo("Success", f"Query renamed to '{new_name}'")
                self._refresh_saved_queries()
            else:
                # Restore old query if add failed
                self.jql_manager.add_query(selected_name, query['jql'], query.get('description', ''))
                messagebox.showerror("Error", "Failed to rename query")
        else:
            messagebox.showerror("Error", "Failed to rename query")
    
    def get(self) -> str:
        """Get the current JQL query text
        
        Returns:
            Current JQL query string
        """
        return self.jql_var.get()
    
    def set(self, value: str):
        """Set the JQL query text
        
        Args:
            value: JQL query string to set
        """
        self.jql_var.set(value)
    
    def get_var(self) -> tk.StringVar:
        """Get the StringVar associated with the JQL text
        
        Returns:
            StringVar containing the JQL query
        """
        return self.jql_var
