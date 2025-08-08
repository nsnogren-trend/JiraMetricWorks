import json
from urllib.parse import quote
from datetime import datetime
from dateutil import parser as dtparser
from adf_to_markdown import normalize_description_to_markdown

def export_json(jira_client, jql, field_id_to_name, folder_path, progress_cb):
    keys, _ = jira_client.search_jql(jql, max_results=100, fields=["key"], expand_changelog=False)
    total = len(keys)
    progress_cb("Exporting JSON...", 0, total)

    for idx, key in enumerate(keys):
        issue = jira_client.get_issue(key, expand_changelog=True)

        fields = issue.get("fields", {}) or {}
        comments_block = fields.get("comment")
        total_comments = (comments_block or {}).get("total")
        if comments_block is None or total_comments is None or total_comments > len((comments_block or {}).get("comments", [])):
            full_comments = jira_client.get_all_comments(key)
            fields["comment"] = {
                "comments": full_comments,
                "total": len(full_comments),
                "maxResults": len(full_comments),
                "startAt": 0,
                "self": f"{jira_client.base_url}/rest/api/3/issue/{quote(key)}/comment"
            }

        # Description normalization
        desc_adf_or_text = fields.get("description")
        desc_md = normalize_description_to_markdown(desc_adf_or_text, options={
            "promote_strong_paragraphs_to_headings": True,
            "heading_level": 2,
            "emoji_style": "unicode",
            "list_indent_spaces": 2,
            "escape_strategy": "minimal",
            "ensure_trailing_newline": True
        })

        transformed_fields = {}
        for fid, value in fields.items():
            disp = field_id_to_name.get(fid, fid)
            if fid == "description":
                transformed_fields["description_raw"] = value
                transformed_fields["description_markdown"] = desc_md
            else:
                transformed_fields[disp] = value

        out = {
            "key": issue.get("key"),
            "id": issue.get("id"),
            "self": issue.get("self"),
            "fields": transformed_fields,
            "changelog": issue.get("changelog"),
            "meta": {
                "fieldIdMap": field_id_to_name
            }
        }

        # Save JSON file
        out_path = f"{folder_path}/{key}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

        # Create and save Markdown file
        markdown_content = create_markdown_content(issue, fields, field_id_to_name, desc_md)
        md_path = f"{folder_path}/{key}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        progress_cb("Exporting JSON...", idx + 1, total)

def create_markdown_content(issue, fields, field_id_to_name, description_md):
    """Create markdown content for an issue"""
    
    # Get summary
    summary = fields.get("summary", "No Summary")
    
    # Process comments
    comments = fields.get("comment", {}).get("comments", [])
    
    # Start building markdown
    md_lines = []
    
    # Title (Summary)
    md_lines.append(f"# {summary}")
    md_lines.append("")
    
    # Description section
    md_lines.append("# Description")
    md_lines.append("")
    if description_md.strip():
        # Remove extra newlines and format properly
        desc_clean = description_md.replace('\\n', '\n').strip()
        md_lines.append(desc_clean)
    else:
        md_lines.append("_No description provided_")
    md_lines.append("")
    
    # Related Work Items section
    md_lines.append("# Related Work Items")
    md_lines.append("")
    
    related_items = []
    
    # Check for subtasks
    subtasks = fields.get("subtasks", [])
    if subtasks:
        for subtask in subtasks:
            key = subtask.get("key", "")
            summary = subtask.get("fields", {}).get("summary", "")
            status = subtask.get("fields", {}).get("status", {}).get("name", "")
            if key:
                related_items.append(f"- **Subtask**: [{key}] {summary} ({status})")
    
    # Check for parent (if this is a subtask)
    parent = fields.get("parent")
    if parent:
        parent_key = parent.get("key", "")
        parent_summary = parent.get("fields", {}).get("summary", "")
        if parent_key:
            related_items.append(f"- **Parent**: [{parent_key}] {parent_summary}")
    
    # Check for issue links
    issue_links = fields.get("issuelinks", [])
    if issue_links:
        for link in issue_links:
            link_type = link.get("type", {}).get("name", "Related")
            
            # Check if this issue is the inward or outward link
            if "inwardIssue" in link:
                related_issue = link["inwardIssue"]
                direction = link.get("type", {}).get("inward", "relates to")
            elif "outwardIssue" in link:
                related_issue = link["outwardIssue"]
                direction = link.get("type", {}).get("outward", "relates to")
            else:
                continue
            
            related_key = related_issue.get("key", "")
            related_summary = related_issue.get("fields", {}).get("summary", "")
            related_status = related_issue.get("fields", {}).get("status", {}).get("name", "")
            
            if related_key:
                related_items.append(f"- **{direction.title()}**: [{related_key}] {related_summary} ({related_status})")
    
    # Check for epic link
    epic_link = fields.get("customfield_10014") or fields.get("epic link") or fields.get("Epic Link")
    if epic_link:
        if isinstance(epic_link, dict):
            epic_key = epic_link.get("key", "")
            epic_summary = epic_link.get("fields", {}).get("summary", "")
            if epic_key:
                related_items.append(f"- **Epic**: [{epic_key}] {epic_summary}")
        elif isinstance(epic_link, str) and epic_link.strip():
            related_items.append(f"- **Epic**: {epic_link}")
    
    # Check if this IS an epic with child issues
    # Note: This would require additional API calls to get epic children
    # For now, we'll just note if this issue is an epic
    issue_type = fields.get("issuetype", {}).get("name", "")
    if issue_type.lower() == "epic":
        related_items.append("- **Type**: This is an Epic (child issues not listed)")
    
    if related_items:
        md_lines.extend(related_items)
    else:
        md_lines.append("_No related work items found_")
    
    md_lines.append("")
    
    # Comments section
    if comments:
        md_lines.append("# Comments")
        md_lines.append("")
        
        for comment in comments:
            # Get author info
            author = comment.get("author", {})
            author_name = author.get("displayName") or author.get("name") or author.get("accountId", "Unknown Author")
            
            # Get and format date
            created_str = comment.get("created", "")
            try:
                if created_str:
                    created_dt = dtparser.parse(created_str)
                    date_str = created_dt.strftime("%Y-%m-%d")
                    time_str = created_dt.strftime("%H:%M")
                else:
                    date_str = "Unknown Date"
                    time_str = "Unknown Time"
            except:
                date_str = "Unknown Date"
                time_str = "Unknown Time"
            
            # Comment header
            md_lines.append(f"## {author_name} | {date_str} | {time_str}")
            md_lines.append("")
            
            # Convert comment body to markdown
            comment_body = comment.get("body")
            comment_md = normalize_description_to_markdown(comment_body, options={
                "promote_strong_paragraphs_to_headings": False,  # Don't promote headings in comments
                "heading_level": 4,  # Use smaller headings in comments
                "emoji_style": "unicode",
                "list_indent_spaces": 2,
                "escape_strategy": "minimal",
                "ensure_trailing_newline": True
            })
            
            if comment_md.strip():
                # Clean up the markdown formatting
                comment_clean = comment_md.replace('\\n', '\n').strip()
                md_lines.append(comment_clean)
            else:
                md_lines.append("_No comment body_")
            
            md_lines.append("")
    
    return "\n".join(md_lines)