import time
import requests

class JiraClient:
    def __init__(self, base_url, email, api_token, log_fn=lambda msg: None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.log = log_fn

    def test_connection(self):
        try:
            url = f"{self.base_url}/rest/api/3/myself"
            r = self.session.get(url, timeout=15)
            return r.status_code == 200
        except Exception:
            return False

    def get_fields(self):
        url = f"{self.base_url}/rest/api/3/field"
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_issue(self, key, expand_changelog=True):
        url = f"{self.base_url}/rest/api/3/issue/{key}"
        params = {}
        if expand_changelog:
            params["expand"] = "changelog"
        r = self.session.get(url, params=params, timeout=60)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", "2"))
            time.sleep(min(10, max(1, retry_after)))
            r = self.session.get(url, params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def search_jql(self, jql, max_results=50, fields=None, expand_changelog=False):
        url = f"{self.base_url}/rest/api/3/search/jql"
        issue_keys = []
        next_page_token = None
        
        # Build expand list
        expand_list = []
        if expand_changelog:
            expand_list.append("changelog")
        
        # Convert expand list to comma-separated string if not empty
        expand_str = ",".join(expand_list) if expand_list else None
        
        while True:
            # Build payload according to the new API specification
            payload = {
                "jql": jql,
                "maxResults": max_results
            }
            
            # Add optional parameters only if they have values
            if fields is not None:
                payload["fields"] = fields
            
            if expand_str:
                payload["expand"] = expand_str
            
            if next_page_token:
                payload["nextPageToken"] = next_page_token
            
            r = self.session.post(url, json=payload, timeout=60)
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", "2"))
                time.sleep(min(10, max(1, retry_after)))
                r = self.session.post(url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            
            # Extract issues from response
            for issue in data.get("issues", []):
                issue_keys.append(issue["key"])
            
            # Check if there are more pages (new pagination model)
            if data.get("isLast", True):
                break
            
            # The new API doesn't use startAt/total, it uses nextPageToken
            # But if nextPageToken is not provided, break to avoid infinite loop
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break
        
        # Return total count - for the new API, we need to count the issues we got
        return issue_keys, len(issue_keys)

    def get_all_comments(self, issue_key):
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        start_at = 0
        all_comments = []
        while True:
            params = {"startAt": start_at, "maxResults": 100}
            r = self.session.get(url, params=params, timeout=60)
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", "2"))
                time.sleep(min(10, max(1, retry_after)))
                r = self.session.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            comments = data.get("comments", [])
            all_comments.extend(comments)
            if start_at + data.get("maxResults", 0) >= data.get("total", 0):
                break
            start_at += data.get("maxResults", 0)
        return all_comments