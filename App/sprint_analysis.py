import csv
import threading
from queue import Queue
from datetime import datetime, timedelta
from dateutil import parser as dtparser, tz

from export_csv import extract_status_changes

CONCURRENT_WORKERS = 12

def filter_transitions_by_sprint_dates(transitions, sprint_start, sprint_end):
    """Filter status transitions to only include those within the sprint timeframe"""
    filtered = []
    for from_status, to_status, transition_date in transitions:
        if sprint_start <= transition_date <= sprint_end:
            filtered.append((from_status, to_status, transition_date))
    return filtered

def calculate_sprint_metrics(transition_date, sprint_start, sprint_end):
    """Calculate sprint-relative metrics for a transition"""
    sprint_duration = (sprint_end - sprint_start).days
    days_from_start = (transition_date.date() - sprint_start.date()).days
    days_to_end = (sprint_end.date() - transition_date.date()).days
    
    # Calculate which sprint day (1-based)
    sprint_day = days_from_start + 1
    
    # Calculate progress percentage
    progress_percent = (days_from_start / sprint_duration * 100) if sprint_duration > 0 else 0
    
    return {
        'sprint_day': sprint_day,
        'days_from_sprint_start': days_from_start,
        'days_to_sprint_end': days_to_end,
        'sprint_progress_percent': round(progress_percent, 1)
    }

def analyze_sprint_patterns(jira_client, jql, sprint_start_str, sprint_end_str, progress_cb):
    """
    Analyze sprint patterns for status transitions within the given timeframe.
    
    Args:
        jira_client: JiraClient instance
        jql: JQL query string
        sprint_start_str: Sprint start date string (will be parsed)
        sprint_end_str: Sprint end date string (will be parsed)
        progress_cb: Progress callback function(stage, done, total)
    
    Returns:
        tuple: (headers, row_iter) where row_iter is a generator of row dictionaries
    """
    
    # Parse sprint dates
    try:
        sprint_start = dtparser.parse(sprint_start_str)
        sprint_end = dtparser.parse(sprint_end_str)
        
        # Ensure dates are timezone-aware (use UTC if no timezone)
        if sprint_start.tzinfo is None:
            sprint_start = sprint_start.replace(tzinfo=tz.UTC)
        if sprint_end.tzinfo is None:
            sprint_end = sprint_end.replace(tzinfo=tz.UTC)
            
        # Ensure sprint_end includes the full day
        if sprint_end.time() == sprint_end.time().replace(hour=0, minute=0, second=0, microsecond=0):
            sprint_end = sprint_end.replace(hour=23, minute=59, second=59)
            
    except Exception as e:
        raise ValueError(f"Invalid date format: {e}")
    
    if sprint_start >= sprint_end:
        raise ValueError("Sprint start date must be before end date")
    
    # Get issue keys first
    progress_cb("Getting issue list...", 0, 1)
    keys, _ = jira_client.search_jql(jql, max_results=100, fields=["key"], expand_changelog=False)
    total = len(keys)
    
    if total == 0:
        return ["issue_key"], iter([])
    
    q = Queue()
    for key in keys:
        q.put(key)
    
    results = []
    lock = threading.Lock()
    done_count = 0
    
    progress_cb("Stage 1/2: Analyzing sprint transitions...", 0, total)
    
    def worker():
        nonlocal done_count
        while True:
            try:
                key = q.get_nowait()
            except Exception:
                return
            
            try:
                # Get issue with changelog
                issue = jira_client.get_issue(key, expand_changelog=True)
                
                # Extract all status changes
                all_transitions = extract_status_changes(issue)
                
                # Filter transitions to sprint timeframe
                sprint_transitions = filter_transitions_by_sprint_dates(
                    all_transitions, sprint_start, sprint_end
                )
                
                # Process each sprint transition
                issue_results = []
                for from_status, to_status, transition_date in sprint_transitions:
                    sprint_metrics = calculate_sprint_metrics(
                        transition_date, sprint_start, sprint_end
                    )
                    
                    issue_results.append({
                        'issue_key': issue.get('key'),
                        'from_status': from_status or '',
                        'to_status': to_status or '',
                        'transition_date': transition_date.isoformat(),
                        **sprint_metrics
                    })
                
                with lock:
                    results.extend(issue_results)
                    done_count += 1
                    
            except Exception as e:
                # Log error but continue processing other issues
                with lock:
                    results.append({
                        'issue_key': key,
                        'from_status': 'ERROR',
                        'to_status': 'ERROR',
                        'transition_date': '',
                        'sprint_day': 0,
                        'days_from_sprint_start': 0,
                        'days_to_sprint_end': 0,
                        'sprint_progress_percent': 0,
                        'error': str(e)
                    })
                    done_count += 1
            finally:
                q.task_done()
                progress_cb("Stage 1/2: Analyzing sprint transitions...", done_count, total)
    
    # Start worker threads
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(CONCURRENT_WORKERS)]
    for t in threads:
        t.start()
    q.join()
    
    # Sort results by transition date
    results.sort(key=lambda x: x.get('transition_date', ''))
    
    # Define headers
    headers = [
        'issue_key',
        'from_status', 
        'to_status',
        'transition_date',
        'sprint_day',
        'days_from_sprint_start',
        'days_to_sprint_end', 
        'sprint_progress_percent'
    ]
    
    # Return row iterator for streaming output
    def row_iter():
        for idx, result in enumerate(results):
            progress_cb("Stage 2/2: Writing CSV...", idx + 1, len(results))
            yield result
    
    return headers, row_iter


def analyze_sprint_patterns_by_sprint(jira_client, sprint_id, progress_cb):
    """
    Analyze sprint patterns for a specific sprint using sprint issues directly.
    
    Args:
        jira_client: JiraClient instance
        sprint_id: Sprint ID to analyze
        progress_cb: Progress callback function(stage, done, total)
    
    Returns:
        tuple: (headers, row_iter) where row_iter is a generator of row dictionaries
    """
    
    # Get sprint details first
    progress_cb("Getting sprint details...", 0, 1)
    try:
        sprint_data = jira_client.get_sprint(sprint_id)
    except Exception as e:
        raise ValueError(f"Could not retrieve sprint {sprint_id}: {e}")
    
    # Extract sprint dates
    sprint_start_str = sprint_data.get('startDate')
    sprint_end_str = sprint_data.get('endDate')
    
    if not sprint_start_str or not sprint_end_str:
        raise ValueError(f"Sprint {sprint_id} does not have start and end dates set")
    
    # Parse sprint dates
    try:
        sprint_start = dtparser.parse(sprint_start_str)
        sprint_end = dtparser.parse(sprint_end_str)
        
        # Ensure dates are timezone-aware (use existing timezone or UTC)
        if sprint_start.tzinfo is None:
            sprint_start = sprint_start.replace(tzinfo=tz.UTC)
        if sprint_end.tzinfo is None:
            sprint_end = sprint_end.replace(tzinfo=tz.UTC)
            
    except Exception as e:
        raise ValueError(f"Invalid date format in sprint data: {e}")
    
    if sprint_start >= sprint_end:
        raise ValueError("Sprint start date must be before end date")
    
    # Get issues in the sprint
    progress_cb("Getting sprint issues...", 0, 1)
    try:
        issues = jira_client.get_sprint_issues(sprint_id)
    except Exception as e:
        raise ValueError(f"Could not retrieve issues for sprint {sprint_id}: {e}")
    
    total = len(issues)
    
    if total == 0:
        return ["issue_key"], iter([])
    
    results = []
    
    progress_cb("Analyzing sprint transitions...", 0, total)
    
    for idx, issue in enumerate(issues):
        try:
            # Extract all status changes
            all_transitions = extract_status_changes(issue)
            
            # Filter transitions to sprint timeframe
            sprint_transitions = filter_transitions_by_sprint_dates(
                all_transitions, sprint_start, sprint_end
            )
            
            # Process each sprint transition
            for from_status, to_status, transition_date in sprint_transitions:
                sprint_metrics = calculate_sprint_metrics(
                    transition_date, sprint_start, sprint_end
                )
                
                results.append({
                    'issue_key': issue.get('key'),
                    'from_status': from_status or '',
                    'to_status': to_status or '',
                    'transition_date': transition_date.isoformat(),
                    **sprint_metrics
                })
                
        except Exception as e:
            # Log error but continue processing other issues
            results.append({
                'issue_key': issue.get('key', 'UNKNOWN'),
                'from_status': 'ERROR',
                'to_status': 'ERROR',
                'transition_date': '',
                'sprint_day': 0,
                'days_from_sprint_start': 0,
                'days_to_sprint_end': 0,
                'sprint_progress_percent': 0,
                'error': str(e)
            })
        
        progress_cb("Analyzing sprint transitions...", idx + 1, total)
    
    # Sort results by transition date
    results.sort(key=lambda x: x.get('transition_date', ''))
    
    # Define headers
    headers = [
        'issue_key',
        'from_status', 
        'to_status',
        'transition_date',
        'sprint_day',
        'days_from_sprint_start',
        'days_to_sprint_end', 
        'sprint_progress_percent'
    ]
    
    # Return row iterator for streaming output
    def row_iter():
        for idx, result in enumerate(results):
            progress_cb("Writing CSV...", idx + 1, len(results))
            yield result
    
    return headers, row_iter
    """
    Analyze sprint patterns for status transitions within the given timeframe.
    
    Args:
        jira_client: JiraClient instance
        jql: JQL query string
        sprint_start_str: Sprint start date string (will be parsed)
        sprint_end_str: Sprint end date string (will be parsed)
        progress_cb: Progress callback function(stage, done, total)
    
    Returns:
        tuple: (headers, row_iter) where row_iter is a generator of row dictionaries
    """
    
    # Parse sprint dates
    try:
        sprint_start = dtparser.parse(sprint_start_str)
        sprint_end = dtparser.parse(sprint_end_str)
        
        # Ensure dates are timezone-aware (use UTC if no timezone)
        if sprint_start.tzinfo is None:
            sprint_start = sprint_start.replace(tzinfo=tz.UTC)
        if sprint_end.tzinfo is None:
            sprint_end = sprint_end.replace(tzinfo=tz.UTC)
            
        # Ensure sprint_end includes the full day
        if sprint_end.time() == sprint_end.time().replace(hour=0, minute=0, second=0, microsecond=0):
            sprint_end = sprint_end.replace(hour=23, minute=59, second=59)
            
    except Exception as e:
        raise ValueError(f"Invalid date format: {e}")
    
    if sprint_start >= sprint_end:
        raise ValueError("Sprint start date must be before end date")
    
    # Get issue keys first
    progress_cb("Getting issue list...", 0, 1)
    keys, _ = jira_client.search_jql(jql, max_results=100, fields=["key"], expand_changelog=False)
    total = len(keys)
    
    if total == 0:
        return ["issue_key"], iter([])
    
    q = Queue()
    for key in keys:
        q.put(key)
    
    results = []
    lock = threading.Lock()
    done_count = 0
    
    progress_cb("Stage 1/2: Analyzing sprint transitions...", 0, total)
    
    def worker():
        nonlocal done_count
        while True:
            try:
                key = q.get_nowait()
            except Exception:
                return
            
            try:
                # Get issue with changelog
                issue = jira_client.get_issue(key, expand_changelog=True)
                
                # Extract all status changes
                all_transitions = extract_status_changes(issue)
                
                # Filter transitions to sprint timeframe
                sprint_transitions = filter_transitions_by_sprint_dates(
                    all_transitions, sprint_start, sprint_end
                )
                
                # Process each sprint transition
                issue_results = []
                for from_status, to_status, transition_date in sprint_transitions:
                    sprint_metrics = calculate_sprint_metrics(
                        transition_date, sprint_start, sprint_end
                    )
                    
                    issue_results.append({
                        'issue_key': issue.get('key'),
                        'from_status': from_status or '',
                        'to_status': to_status or '',
                        'transition_date': transition_date.isoformat(),
                        **sprint_metrics
                    })
                
                with lock:
                    results.extend(issue_results)
                    done_count += 1
                    
            except Exception as e:
                # Log error but continue processing other issues
                with lock:
                    results.append({
                        'issue_key': key,
                        'from_status': 'ERROR',
                        'to_status': 'ERROR',
                        'transition_date': '',
                        'sprint_day': 0,
                        'days_from_sprint_start': 0,
                        'days_to_sprint_end': 0,
                        'sprint_progress_percent': 0,
                        'error': str(e)
                    })
                    done_count += 1
            finally:
                q.task_done()
                progress_cb("Stage 1/2: Analyzing sprint transitions...", done_count, total)
    
    # Start worker threads
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(CONCURRENT_WORKERS)]
    for t in threads:
        t.start()
    q.join()
    
    # Sort results by transition date
    results.sort(key=lambda x: x.get('transition_date', ''))
    
    # Define headers
    headers = [
        'issue_key',
        'from_status', 
        'to_status',
        'transition_date',
        'sprint_day',
        'days_from_sprint_start',
        'days_to_sprint_end', 
        'sprint_progress_percent'
    ]
    
    # Return row iterator for streaming output
    def row_iter():
        for idx, result in enumerate(results):
            progress_cb("Stage 2/2: Writing CSV...", idx + 1, len(results))
            yield result
    
    return headers, row_iter