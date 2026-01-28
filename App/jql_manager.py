"""
JQL Query Manager
Handles saving, loading, and managing JQL queries.
"""

import json
import os
from typing import List, Dict, Optional

class JQLManager:
    """Manager for saving and loading JQL queries"""
    
    def __init__(self, config_file: str = None):
        """Initialize the JQL manager
        
        Args:
            config_file: Path to the JSON file storing saved queries.
                        Defaults to 'saved_jql_queries.json' in the App directory.
        """
        if config_file is None:
            # Default to saved_jql_queries.json in the App directory
            app_dir = os.path.dirname(os.path.abspath(__file__))
            config_file = os.path.join(app_dir, 'saved_jql_queries.json')
        
        self.config_file = config_file
        self.queries = []
        self.load_queries()
    
    def load_queries(self) -> List[Dict[str, str]]:
        """Load queries from the config file
        
        Returns:
            List of query dictionaries with 'name', 'jql', and optional 'description'
        """
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.queries = json.load(f)
                return self.queries
            except Exception as e:
                print(f"Error loading JQL queries: {e}")
                self.queries = []
        else:
            self.queries = []
        return self.queries
    
    def save_queries(self) -> bool:
        """Save queries to the config file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.queries, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving JQL queries: {e}")
            return False
    
    def add_query(self, name: str, jql: str, description: str = "") -> bool:
        """Add a new query
        
        Args:
            name: Name/label for the query
            jql: The JQL query string
            description: Optional description of the query
            
        Returns:
            True if successful, False if name already exists
        """
        # Check if name already exists
        if any(q['name'] == name for q in self.queries):
            return False
        
        query = {
            'name': name,
            'jql': jql,
            'description': description
        }
        self.queries.append(query)
        return self.save_queries()
    
    def update_query(self, name: str, jql: str, description: str = "") -> bool:
        """Update an existing query
        
        Args:
            name: Name/label of the query to update
            jql: The new JQL query string
            description: Optional new description
            
        Returns:
            True if successful, False if query not found
        """
        for query in self.queries:
            if query['name'] == name:
                query['jql'] = jql
                query['description'] = description
                return self.save_queries()
        return False
    
    def delete_query(self, name: str) -> bool:
        """Delete a query by name
        
        Args:
            name: Name of the query to delete
            
        Returns:
            True if successful, False if query not found
        """
        original_length = len(self.queries)
        self.queries = [q for q in self.queries if q['name'] != name]
        
        if len(self.queries) < original_length:
            return self.save_queries()
        return False
    
    def get_query(self, name: str) -> Optional[Dict[str, str]]:
        """Get a query by name
        
        Args:
            name: Name of the query
            
        Returns:
            Query dictionary or None if not found
        """
        for query in self.queries:
            if query['name'] == name:
                return query
        return None
    
    def get_all_queries(self) -> List[Dict[str, str]]:
        """Get all saved queries
        
        Returns:
            List of all query dictionaries
        """
        return self.queries.copy()
    
    def get_query_names(self) -> List[str]:
        """Get names of all saved queries
        
        Returns:
            List of query names
        """
        return [q['name'] for q in self.queries]
