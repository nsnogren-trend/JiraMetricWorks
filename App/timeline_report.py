"""
Timeline Report Generator
Creates visual timeline reports showing status transitions over time.
"""

import threading
from queue import Queue
from datetime import datetime, timedelta
from dateutil import parser as dtparser, tz
from collections import defaultdict
import html

from export_csv import extract_status_changes

CONCURRENT_WORKERS = 12

def interpolate_color(start_color, end_color, factor):
    """Interpolate between two RGB colors"""
    return tuple(int(start + (end - start) * factor) for start, end in zip(start_color, end_color))

def rgb_to_hex(rgb):
    """Convert RGB tuple to hex color string"""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

def generate_color_palette(num_colors):
    """Generate a perceptually distinct red-to-green progression palette"""
    if num_colors == 1:
        return ["#36B37E"]  # Just green for single status
    
    if num_colors == 2:
        return ["#E53935", "#43A047"]  # Red and Green
    
    # Carefully curated colors with maximum perceptual distance
    # Each color is notably different from its neighbors
    distinct_progression = [
        "#D32F2F",  # Red (bad)
        "#F4511E",  # Deep Orange
        "#FB8C00",  # Orange
        "#FDD835",  # Yellow
        "#C0CA33",  # Lime
        "#7CB342",  # Light Green
        "#43A047",  # Green
        "#2E7D32",  # Dark Green (good)
    ]
    
    if num_colors <= len(distinct_progression):
        # Always pick from the curated list for maximum distinction
        step = len(distinct_progression) / num_colors
        indices = [int(i * step) for i in range(num_colors)]
        # Ensure we get the last color if it's the full range
        if num_colors > 1:
            indices[-1] = len(distinct_progression) - 1
        return [distinct_progression[i] for i in indices]
    
    # For more than 8 statuses, interpolate but use larger segments
    # This ensures we don't create too-similar colors
    colors_rgb = [
        (211, 47, 47),    # Red
        (244, 81, 30),    # Deep Orange
        (251, 140, 0),    # Orange
        (253, 216, 53),   # Yellow
        (192, 202, 51),   # Lime
        (124, 179, 66),   # Light Green
        (67, 160, 71),    # Green
        (46, 125, 50),    # Dark Green
    ]
    
    result = []
    for i in range(num_colors):
        # Map to color space
        position = i * (len(colors_rgb) - 1) / (num_colors - 1)
        segment = int(position)
        if segment >= len(colors_rgb) - 1:
            result.append(rgb_to_hex(colors_rgb[-1]))
        else:
            local_factor = position - segment
            color = interpolate_color(colors_rgb[segment], colors_rgb[segment + 1], local_factor)
            result.append(rgb_to_hex(color))
    
    return result

def build_timeline_data(jira_client, jql, status_order, start_date=None, end_date=None, progress_cb=None, custom_colors=None):
    """
    Build timeline data for all issues matching the JQL query.
    
    Args:
        jira_client: JiraClient instance
        jql: JQL query string
        status_order: Dict mapping status name to integer order (only tracked statuses)
        start_date: Optional datetime for timeline start (timezone-aware)
        end_date: Optional datetime for timeline end (timezone-aware)
        progress_cb: Progress callback function(stage, done, total)
        custom_colors: Optional dict mapping status name to hex color (e.g., {'In Progress': '#FF5733'})
    
    Returns:
        dict with:
            - issues: List of issue data with timeline segments
            - timeline_start: datetime
            - timeline_end: datetime
            - status_order: Original status order dict
            - status_colors: Dict mapping status name to color
    """
    
    def log(msg, done=0, total=1):
        if progress_cb:
            progress_cb(msg, done, total)
    
    # Get issue keys
    log("Fetching issues...", 0, 1)
    keys, _ = jira_client.search_jql(jql, max_results=1000, fields=["key"], expand_changelog=False)
    total = len(keys)
    
    if total == 0:
        return {
            'issues': [],
            'timeline_start': None,
            'timeline_end': None,
            'status_order': status_order,
            'status_colors': {}
        }
    
    # Fetch all issue data with changelog
    q = Queue()
    for key in keys:
        q.put(key)
    
    issues_data = []
    lock = threading.Lock()
    done_count = 0
    
    log("Analyzing issue history...", 0, total)
    
    def worker():
        nonlocal done_count
        while True:
            try:
                key = q.get_nowait()
            except Exception:
                return
            
            try:
                issue = jira_client.get_issue(key, expand_changelog=True)
                transitions = extract_status_changes(issue)
                
                with lock:
                    issues_data.append({
                        'key': key,
                        'transitions': transitions,
                        'issue': issue
                    })
                    done_count += 1
                    
            except Exception as e:
                with lock:
                    issues_data.append({
                        'key': key,
                        'transitions': [],
                        'issue': None,
                        'error': str(e)
                    })
                    done_count += 1
            finally:
                q.task_done()
                log("Analyzing issue history...", done_count, total)
    
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(CONCURRENT_WORKERS)]
    for t in threads:
        t.start()
    q.join()
    
    # Process timeline data
    log("Building timeline...", 0, 1)
    
    # Build timeline for each issue
    processed_issues = []
    all_dates = []
    
    for issue_data in issues_data:
        if issue_data.get('error'):
            continue
            
        key = issue_data['key']
        transitions = issue_data['transitions']
        
        # Find first transition to a tracked status
        first_tracked_idx = None
        for idx, (from_status, to_status, trans_date) in enumerate(transitions):
            if to_status in status_order:
                first_tracked_idx = idx
                break
        
        if first_tracked_idx is None:
            # No tracked statuses for this issue
            continue
        
        # Build segments from first tracked status onward
        segments = []
        current_status = None
        segment_start = None
        
        # Start with the first tracked status
        _, first_status, first_date = transitions[first_tracked_idx]
        current_status = first_status
        segment_start = first_date
        all_dates.append(first_date)
        
        # Process subsequent transitions
        for from_status, to_status, trans_date in transitions[first_tracked_idx + 1:]:
            # Close current segment
            segments.append({
                'status': current_status,
                'start': segment_start,
                'end': trans_date,
                'tracked': current_status in status_order
            })
            all_dates.append(trans_date)
            
            # Start new segment
            current_status = to_status
            segment_start = trans_date
        
        # Close final segment (use end_date or current time)
        final_end = end_date or datetime.now(tz.UTC)
        segments.append({
            'status': current_status,
            'start': segment_start,
            'end': final_end,
            'tracked': current_status in status_order
        })
        all_dates.append(final_end)
        
        processed_issues.append({
            'key': key,
            'segments': segments
        })
    
    # Determine timeline bounds
    if not all_dates:
        return {
            'issues': [],
            'timeline_start': None,
            'timeline_end': None,
            'status_order': status_order,
            'status_colors': {}
        }
    
    timeline_start = start_date or min(all_dates)
    timeline_end = end_date or max(all_dates)
    
    # Ensure timezone awareness
    if timeline_start.tzinfo is None:
        timeline_start = timeline_start.replace(tzinfo=tz.UTC)
    if timeline_end.tzinfo is None:
        timeline_end = timeline_end.replace(tzinfo=tz.UTC)
    
    # Generate color palette based on sorted status order
    sorted_statuses = sorted(status_order.items(), key=lambda x: x[1])
    status_names = [s[0] for s in sorted_statuses]
    
    # Use custom colors if provided, otherwise auto-generate
    if custom_colors is None:
        custom_colors = {}
    
    # Build final status_colors dict: custom colors take priority, auto-generate for the rest
    status_colors = {}
    auto_colors = generate_color_palette(len(status_names))
    
    for idx, status_name in enumerate(status_names):
        if status_name in custom_colors:
            status_colors[status_name] = custom_colors[status_name]
        else:
            status_colors[status_name] = auto_colors[idx]
    
    log("Timeline built successfully", 1, 1)
    
    return {
        'issues': processed_issues,
        'timeline_start': timeline_start,
        'timeline_end': timeline_end,
        'status_order': status_order,
        'status_colors': status_colors
    }

def calculate_time_in_status(segments, timeline_start, timeline_end, status_order):
    """
    Calculate total time spent in each tracked status within the timeline bounds.
    
    Returns:
        dict mapping status name to total seconds
    """
    time_by_status = defaultdict(float)
    
    for segment in segments:
        if not segment['tracked']:
            continue
            
        status = segment['status']
        seg_start = max(segment['start'], timeline_start)
        seg_end = min(segment['end'], timeline_end)
        
        if seg_end > seg_start:
            duration = (seg_end - seg_start).total_seconds()
            time_by_status[status] += duration
    
    return dict(time_by_status)

def format_duration(seconds):
    """Format duration in seconds to human-readable string"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}h"
    else:
        days = seconds / 86400
        return f"{days:.1f}d"

def generate_html_report(timeline_data, jql_query, project_name=None):
    """
    Generate HTML report from timeline data.
    
    Args:
        timeline_data: Output from build_timeline_data()
        jql_query: The JQL query used
        project_name: Optional project name
    
    Returns:
        str: Complete HTML document
    """
    
    issues = timeline_data['issues']
    timeline_start = timeline_data['timeline_start']
    timeline_end = timeline_data['timeline_end']
    status_order = timeline_data['status_order']
    status_colors = timeline_data['status_colors']
    
    if not issues or not timeline_start or not timeline_end:
        return "<html><body><h1>No data to display</h1></body></html>"
    
    timeline_duration = (timeline_end - timeline_start).total_seconds()
    
    # Generate CSS for status colors
    color_css = []
    for status, color in status_colors.items():
        safe_class = f"status-{abs(hash(status)) % 10000}"
        color_css.append(f".{safe_class} {{ background-color: {color}; }}")
    
    # Build status class mapping
    status_to_class = {status: f"status-{abs(hash(status)) % 10000}" for status in status_colors.keys()}
    
    # Generate timeline scale labels with adaptive intervals (daily, every N days, or hourly)
    scale_points = []
    duration_hours = timeline_duration / 3600
    
    if duration_hours < 24:
        # For sub-day timelines, use hourly intervals
        num_hours = int(duration_hours) + 1
        interval_hours = max(1, num_hours // 8)  # Show ~8 labels
        for i in range(0, num_hours, interval_hours):
            point_time = timeline_start + timedelta(hours=i)
            if point_time <= timeline_end:
                offset = (point_time - timeline_start).total_seconds()
                position_pct = (offset / timeline_duration) * 100
                scale_points.append({
                    'label': point_time.strftime("%b %d %H:%M"),
                    'position': position_pct,
                    'is_weekend': False  # Not relevant for hourly view
                })
    else:
        # For multi-day timelines, use daily intervals at midnight
        duration_days = (timeline_end - timeline_start).days + 1
        
        # Determine interval: daily, every 3 days, or weekly
        if duration_days <= 30:
            interval_days = 1  # Show every day
        elif duration_days <= 90:
            interval_days = 3  # Every 3 days
        else:
            interval_days = 7  # Weekly
        
        # Start from the first midnight at or after timeline_start
        current_day = timeline_start.replace(hour=0, minute=0, second=0, microsecond=0)
        if current_day < timeline_start:
            current_day += timedelta(days=1)
        
        # Generate labels for each interval
        day_counter = 0
        while current_day <= timeline_end:
            if day_counter % interval_days == 0:
                offset = (current_day - timeline_start).total_seconds()
                position_pct = (offset / timeline_duration) * 100
                is_weekend = current_day.weekday() >= 5  # Saturday=5, Sunday=6
                scale_points.append({
                    'label': current_day.strftime("%b %d"),
                    'position': position_pct,
                    'is_weekend': is_weekend
                })
            current_day += timedelta(days=1)
            day_counter += 1
        
        # Add the end date if it's not already the last label (check by date, not position)
        if scale_points:
            last_label_date = scale_points[-1]['label']
            end_label = timeline_end.strftime("%b %d")
            if last_label_date != end_label:
                is_weekend = timeline_end.weekday() >= 5
                scale_points.append({
                    'label': end_label,
                    'position': 100.0,
                    'is_weekend': is_weekend
                })
    
    # Generate weekend divider lines (only for multi-day timelines)
    weekend_dividers = []
    if duration_hours >= 24:
        # Find all weekend boundaries (Friday->Saturday and Sunday->Monday transitions)
        current = timeline_start.replace(hour=0, minute=0, second=0, microsecond=0)
        while current <= timeline_end:
            weekday = current.weekday()
            
            # Saturday start (Friday->Saturday boundary)
            if weekday == 5:  # Saturday
                offset = (current - timeline_start).total_seconds()
                if offset >= 0:  # Within timeline
                    position_pct = (offset / timeline_duration) * 100
                    if position_pct <= 100:
                        weekend_dividers.append(position_pct)
            
            # Monday start (Sunday->Monday boundary, end of weekend)
            elif weekday == 0 and current > timeline_start:  # Monday (not the first day)
                offset = (current - timeline_start).total_seconds()
                if offset >= 0:  # Within timeline
                    position_pct = (offset / timeline_duration) * 100
                    if position_pct <= 100:
                        weekend_dividers.append(position_pct)
            
            current += timedelta(days=1)
    
    # Generate timeline rows
    timeline_rows = []
    time_summary_rows = []
    
    # Track totals
    status_totals = defaultdict(float)
    
    # Sort issues by first tracked status entry date (earliest to latest)
    issues_sorted = sorted(issues, key=lambda x: x['segments'][0]['start'] if x['segments'] else datetime.max.replace(tzinfo=tz.UTC))
    
    for issue_data in issues_sorted:
        key = issue_data['key']
        segments = issue_data['segments']
        
        # Generate segments HTML
        segments_html = []
        for segment in segments:
            seg_start = max(segment['start'], timeline_start)
            seg_end = min(segment['end'], timeline_end)
            
            if seg_end <= seg_start:
                continue
            
            # Calculate position and width as percentage
            start_offset = (seg_start - timeline_start).total_seconds()
            duration = (seg_end - seg_start).total_seconds()
            
            left_pct = (start_offset / timeline_duration) * 100
            width_pct = (duration / timeline_duration) * 100
            
            status = segment['status']
            
            if segment['tracked']:
                css_class = status_to_class[status]
                title = f"{html.escape(status)}: {seg_start.strftime('%b %d %H:%M')} - {seg_end.strftime('%b %d %H:%M')}"
                label = html.escape(status) if width_pct > 5 else ""  # Only show label if wide enough
                
                segments_html.append(
                    f'<div class="status-segment {css_class}" '
                    f'style="left: {left_pct:.2f}%; width: {width_pct:.2f}%;" '
                    f'title="{title}">{label}</div>'
                )
            else:
                # Untracked status - show as grey with status name
                title = f"Untracked: {html.escape(status)}: {seg_start.strftime('%b %d %H:%M')} - {seg_end.strftime('%b %d %H:%M')}"
                label = html.escape(status) if width_pct > 5 else ""  # Only show label if wide enough
                
                segments_html.append(
                    f'<div class="status-segment status-untracked" '
                    f'data-status="{html.escape(status)}" '
                    f'style="left: {left_pct:.2f}%; width: {width_pct:.2f}%;" '
                    f'title="{title}">{label}</div>'
                )
        
        timeline_rows.append(f'''
        <div class="timeline-row">
            <div class="issue-key">{html.escape(key)}</div>
            <div class="timeline-bar-container">
                {''.join(segments_html)}
            </div>
        </div>
        ''')
        
        # Calculate time in each status for summary table
        time_in_status = calculate_time_in_status(segments, timeline_start, timeline_end, status_order)
        
        # Build summary row
        row_total = sum(time_in_status.values())
        sorted_statuses = sorted(status_order.items(), key=lambda x: x[1])
        
        cells = [f'<td class="issue-cell">{html.escape(key)}</td>']
        for status, _ in sorted_statuses:
            seconds = time_in_status.get(status, 0)
            status_totals[status] += seconds
            cells.append(f'<td class="time-cell">{format_duration(seconds)}</td>')
        cells.append(f'<td class="total-cell">{format_duration(row_total)}</td>')
        
        time_summary_rows.append('<tr>' + ''.join(cells) + '</tr>')
    
    # Build summary table totals row
    sorted_statuses = sorted(status_order.items(), key=lambda x: x[1])
    total_cells = ['<th class="total-header">Total</th>']
    grand_total = 0
    for status, _ in sorted_statuses:
        seconds = status_totals[status]
        grand_total += seconds
        total_cells.append(f'<th class="total-cell">{format_duration(seconds)}</th>')
    total_cells.append(f'<th class="total-cell">{format_duration(grand_total)}</th>')
    
    totals_row = '<tr class="totals-row">' + ''.join(total_cells) + '</tr>'
    
    # Build summary table headers
    summary_headers = ['<th>Issue</th>']
    for status, _ in sorted_statuses:
        summary_headers.append(f'<th>{html.escape(status)}</th>')
    summary_headers.append('<th>Total</th>')
    
    # Build legend
    legend_items = []
    for status, _ in sorted_statuses:
        css_class = status_to_class[status]
        legend_items.append(f'''
        <div class="legend-item">
            <div class="legend-color {css_class}"></div>
            <div class="legend-label">{html.escape(status)}</div>
        </div>
        ''')
    
    # Build complete HTML
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Timeline Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #333;
            border-bottom: 3px solid #0052CC;
            padding-bottom: 10px;
        }}
        
        h2 {{
            color: #333;
            margin-top: 30px;
            border-bottom: 2px solid #ddd;
            padding-bottom: 8px;
        }}
        
        .info {{
            background-color: #E3FCEF;
            border-left: 4px solid #00875A;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        
        .info h3 {{
            margin-top: 0;
            color: #00875A;
        }}
        
        .info p {{
            margin: 5px 0;
        }}
        
        .timeline-header {{
            display: flex;
            align-items: center;
            margin: 20px 0 10px 0;
            padding-left: 200px;
        }}
        
        .timeline-scale {{
            flex: 1;
            position: relative;
            height: 20px;
            font-size: 12px;
            color: #666;
            border-bottom: 2px solid #ddd;
        }}
        
        .timeline-scale span {{
            position: absolute;
            transform: translateX(-50%);
            white-space: nowrap;
        }}
        
        .timeline-scale span.weekend {{
            font-style: italic;
            color: #999;
        }}
        
        .weekend-divider {{
            position: absolute;
            top: 0;
            bottom: 0;
            width: 1px;
            background-color: #999;
            pointer-events: none;
        }}
        
        .timeline-row {{
            display: flex;
            align-items: center;
            margin-bottom: 8px;
            min-height: 40px;
        }}
        
        .issue-key {{
            width: 180px;
            font-weight: bold;
            color: #0052CC;
            padding-right: 20px;
            text-align: right;
            font-size: 14px;
        }}
        
        .timeline-bar-container {{
            flex: 1;
            height: 30px;
            background-color: #f8f8f8;
            border: 1px solid #e0e0e0;
            position: relative;
            border-radius: 4px;
        }}
        
        .status-segment {{
            position: absolute;
            height: 100%;
            border-right: 1px solid rgba(255,255,255,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 600;
            color: white;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
            overflow: hidden;
            white-space: nowrap;
        }}
        
        .status-segment:hover {{
            opacity: 0.8;
            cursor: pointer;
            outline: 2px solid #333;
            z-index: 10;
        }}
        
        .status-untracked {{
            background-color: #ddd;
            color: #666;
        }}
        
        {chr(10).join(color_css)}
        
        .legend {{
            margin-top: 30px;
            padding: 15px;
            background-color: #f8f8f8;
            border-radius: 4px;
        }}
        
        .legend h3 {{
            margin-top: 0;
            color: #333;
        }}
        
        .legend-items {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .legend-color {{
            width: 40px;
            height: 20px;
            border-radius: 3px;
            border: 1px solid #ddd;
        }}
        
        .legend-label {{
            font-size: 13px;
            color: #333;
        }}
        
        .summary-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        
        .summary-table th,
        .summary-table td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        
        .summary-table th {{
            background-color: #f8f8f8;
            font-weight: 600;
        }}
        
        .issue-cell {{
            font-weight: bold;
            color: #0052CC;
        }}
        
        .time-cell {{
            text-align: right;
        }}
        
        .total-cell {{
            font-weight: bold;
            text-align: right;
        }}
        
        .totals-row {{
            background-color: #f0f0f0;
            font-weight: bold;
        }}
        
        .total-header {{
            text-align: left !important;
        }}
        
        /* Color Customization Panel Styles */
        .color-panel {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: white;
            border: 2px solid #0052CC;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            z-index: 1000;
            max-width: 400px;
        }}
        
        .color-panel.collapsed {{
            width: auto;
        }}
        
        .color-panel-header {{
            background: #0052CC;
            color: white;
            padding: 12px 15px;
            border-radius: 6px 6px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }}
        
        .color-panel-header h3 {{
            margin: 0;
            font-size: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .color-panel-toggle {{
            background: none;
            border: none;
            color: white;
            font-size: 20px;
            cursor: pointer;
            padding: 0;
            line-height: 1;
        }}
        
        .color-panel-body {{
            padding: 15px;
            max-height: 70vh;
            overflow-y: auto;
        }}
        
        .color-panel.collapsed .color-panel-body {{
            display: none;
        }}
        
        .untracked-status-item {{
            margin-bottom: 12px;
            padding: 10px;
            background: #f8f8f8;
            border-radius: 4px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .untracked-status-item label {{
            flex: 1;
            font-size: 13px;
            font-weight: 500;
            color: #333;
        }}
        
        .untracked-status-item input[type="color"] {{
            width: 50px;
            height: 35px;
            border: 1px solid #ddd;
            border-radius: 4px;
            cursor: pointer;
        }}
        
        .untracked-count {{
            background: #0052CC;
            color: white;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: bold;
        }}
        
        .color-panel-actions {{
            display: flex;
            gap: 8px;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
        }}
        
        .color-panel-actions button {{
            flex: 1;
            padding: 8px 12px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
        }}
        
        .btn-apply {{
            background: #00875A;
            color: white;
        }}
        
        .btn-apply:hover {{
            background: #006644;
        }}
        
        .btn-reset {{
            background: #FF5630;
            color: white;
        }}
        
        .btn-reset:hover {{
            background: #DE350B;
        }}
        
        .btn-export {{
            background: #6554C0;
            color: white;
        }}
        
        .btn-export:hover {{
            background: #5243AA;
        }}
        
        .btn-import {{
            background: #00B8D9;
            color: white;
        }}
        
        .btn-import:hover {{
            background: #00A3BF;
        }}
        
        .no-untracked {{
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 14px;
        }}
        
        .status-info {{
            background: #E3FCEF;
            border-left: 4px solid #00875A;
            padding: 10px;
            margin-bottom: 15px;
            border-radius: 4px;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Timeline Report</h1>
        
        <div class="info">
            <h3>Report Information</h3>
            <p><strong>Query:</strong> {html.escape(jql_query)}</p>
            {f'<p><strong>Project:</strong> {html.escape(project_name)}</p>' if project_name else ''}
            <p><strong>Timeline:</strong> {timeline_start.strftime("%b %d, %Y %H:%M")} - {timeline_end.strftime("%b %d, %Y %H:%M")}</p>
            <p><strong>Duration:</strong> {format_duration(timeline_duration)}</p>
            <p><strong>Issues:</strong> {len(issues)}</p>
        </div>
        
        <h2>Status Timeline</h2>
        
        <div class="timeline-header">
            <div class="timeline-scale">
                {''.join(f'<span class="{"weekend" if point.get("is_weekend", False) else ""}" style="left: {point["position"]:.2f}%;">{point["label"]}</span>' for point in scale_points)}
                {''.join(f'<div class="weekend-divider" style="left: {pos:.2f}%;"></div>' for pos in weekend_dividers)}
            </div>
        </div>
        
        {''.join(timeline_rows)}
        
        <div class="legend">
            <h3>Status Legend</h3>
            <p style="margin-bottom: 10px; color: #666; font-size: 13px;">
                Colors represent workflow progression from early (red) to complete (green).
            </p>
            <div class="legend-items">
                {''.join(legend_items)}
                <div class="legend-item">
                    <div class="legend-color status-untracked"></div>
                    <div class="legend-label">Untracked Status</div>
                </div>
            </div>
        </div>
        
        <h2>Time Summary</h2>
        
        <table class="summary-table">
            <thead>
                <tr>
                    {''.join(summary_headers)}
                </tr>
            </thead>
            <tbody>
                {''.join(time_summary_rows)}
            </tbody>
            <tfoot>
                {totals_row}
            </tfoot>
        </table>
    </div>
    
    <!-- Color Customization Panel -->
    <div class="color-panel" id="colorPanel">
        <div class="color-panel-header" onclick="togglePanel()">
            <h3>🎨 Customize Colors</h3>
            <button class="color-panel-toggle" id="toggleBtn">▼</button>
        </div>
        <div class="color-panel-body" id="panelBody">
            <div class="status-info">
                <strong>💡 Tip:</strong> Customize colors for untracked statuses below. Changes apply instantly!
            </div>
            <div id="untrackedStatusList"></div>
            <div class="color-panel-actions">
                <button class="btn-apply" onclick="applyColors()" title="Apply selected colors">✓ Apply</button>
                <button class="btn-reset" onclick="resetColors()" title="Reset to default grey">↺ Reset</button>
            </div>
            <div class="color-panel-actions">
                <button class="btn-export" onclick="exportColors()" title="Export color configuration">⬇ Export</button>
                <button class="btn-import" onclick="importColors()" title="Import color configuration">⬆ Import</button>
            </div>
        </div>
    </div>
    
    <script>
        // Predefined color palette for common status types
        const STATUS_COLOR_SUGGESTIONS = {{
            'awaiting code review': '#9C27B0',  // Purple
            'code review': '#9C27B0',
            'awaiting deployment': '#FF9800',   // Orange
            'deployment': '#FF9800',
            'awaiting qa': '#2196F3',           // Blue
            'qa': '#2196F3',
            'testing': '#2196F3',
            'blocked': '#F44336',               // Red
            'on hold': '#FFC107',               // Amber
            'in review': '#4CAF50',             // Green
            'review': '#4CAF50',
            'awaiting approval': '#E91E63',     // Pink
            'approval': '#E91E63',
            'awaiting merge': '#00BCD4',        // Cyan
            'merge': '#00BCD4',
            'ready for qa': '#03A9F4',          // Light Blue
            'ready for deployment': '#FF6F00',  // Dark Orange
            'pending': '#9E9E9E',               // Grey
            'backlog': '#795548',               // Brown
        }};
        
        // Store color configurations
        let colorConfig = {{}};
        
        // Discover untracked statuses on page load
        function discoverUntrackedStatuses() {{
            const statusCounts = {{}};
            
            document.querySelectorAll('.status-untracked').forEach(el => {{
                const status = el.getAttribute('data-status');
                if (status) {{
                    statusCounts[status] = (statusCounts[status] || 0) + 1;
                }}
            }});
            
            return statusCounts;
        }}
        
        // Get suggested color for a status
        function getSuggestedColor(status) {{
            const lowerStatus = status.toLowerCase();
            
            // Direct match
            if (STATUS_COLOR_SUGGESTIONS[lowerStatus]) {{
                return STATUS_COLOR_SUGGESTIONS[lowerStatus];
            }}
            
            // Partial match
            for (const [key, color] of Object.entries(STATUS_COLOR_SUGGESTIONS)) {{
                if (lowerStatus.includes(key) || key.includes(lowerStatus)) {{
                    return color;
                }}
            }}
            
            // Default grey
            return '#999999';
        }}
        
        // Initialize the color panel
        function initializeColorPanel() {{
            const statusCounts = discoverUntrackedStatuses();
            const listContainer = document.getElementById('untrackedStatusList');
            
            if (Object.keys(statusCounts).length === 0) {{
                listContainer.innerHTML = '<div class="no-untracked">✓ No untracked statuses found</div>';
                return;
            }}
            
            // Sort by count (descending)
            const sortedStatuses = Object.entries(statusCounts)
                .sort((a, b) => b[1] - a[1]);
            
            // Create color picker for each status
            sortedStatuses.forEach(([status, count]) => {{
                const suggestedColor = getSuggestedColor(status);
                colorConfig[status] = suggestedColor;
                
                const item = document.createElement('div');
                item.className = 'untracked-status-item';
                item.innerHTML = `
                    <label>
                        ${{status}}
                        <span class="untracked-count">${{count}}</span>
                    </label>
                    <input type="color" 
                           value="${{suggestedColor}}" 
                           data-status="${{status}}"
                           onchange="updateColorConfig(this)">
                `;
                listContainer.appendChild(item);
            }});
            
            // Apply suggested colors immediately on load
            applyColors();
        }}
        
        // Update color configuration when picker changes
        function updateColorConfig(input) {{
            const status = input.getAttribute('data-status');
            colorConfig[status] = input.value;
        }}
        
        // Apply colors to all matching segments
        function applyColors() {{
            let appliedCount = 0;
            
            Object.entries(colorConfig).forEach(([status, color]) => {{
                const segments = document.querySelectorAll(`.status-untracked[data-status="${{status}}"]`);
                
                segments.forEach(el => {{
                    el.style.backgroundColor = color;
                    el.style.color = '#ffffff';
                    el.style.fontWeight = 'bold';
                    el.style.textShadow = '1px 1px 2px rgba(0,0,0,0.5)';
                    appliedCount++;
                }});
            }});
            
            console.log(`✅ Applied custom colors to ${{appliedCount}} segments`);
        }}
        
        // Reset all untracked statuses to default grey
        function resetColors() {{
            if (!confirm('Reset all untracked statuses to default grey color?')) {{
                return;
            }}
            
            document.querySelectorAll('.status-untracked').forEach(el => {{
                el.style.backgroundColor = '#ddd';
                el.style.color = '#666';
                el.style.fontWeight = '';
                el.style.textShadow = '';
            }});
            
            // Reset color pickers
            document.querySelectorAll('input[type="color"]').forEach(input => {{
                const status = input.getAttribute('data-status');
                const defaultColor = '#999999';
                input.value = defaultColor;
                colorConfig[status] = defaultColor;
            }});
            
            console.log('↺ Reset to default colors');
        }}
        
        // Toggle panel open/closed
        function togglePanel() {{
            const panel = document.getElementById('colorPanel');
            const toggleBtn = document.getElementById('toggleBtn');
            
            panel.classList.toggle('collapsed');
            toggleBtn.textContent = panel.classList.contains('collapsed') ? '▲' : '▼';
        }}
        
        // Export color configuration as JSON
        function exportColors() {{
            const config = {{
                version: '1.0',
                exportDate: new Date().toISOString(),
                colors: colorConfig
            }};
            
            const blob = new Blob([JSON.stringify(config, null, 2)], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'timeline-colors.json';
            a.click();
            URL.revokeObjectURL(url);
            
            console.log('⬇ Exported color configuration');
        }}
        
        // Import color configuration from JSON
        function importColors() {{
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.json';
            
            input.onchange = (e) => {{
                const file = e.target.files[0];
                const reader = new FileReader();
                
                reader.onload = (event) => {{
                    try {{
                        const config = JSON.parse(event.target.result);
                        
                        if (config.colors) {{
                            // Update color pickers and config
                            Object.entries(config.colors).forEach(([status, color]) => {{
                                const input = document.querySelector(`input[data-status="${{status}}"]`);
                                if (input) {{
                                    input.value = color;
                                    colorConfig[status] = color;
                                }}
                            }});
                            
                            applyColors();
                            console.log('⬆ Imported color configuration');
                            alert('✓ Colors imported successfully!');
                        }} else {{
                            alert('⚠️ Invalid configuration file');
                        }}
                    }} catch (error) {{
                        alert('❌ Error reading configuration file: ' + error.message);
                    }}
                }};
                
                reader.readAsText(file);
            }};
            
            input.click();
        }}
        
        // Initialize when page loads
        document.addEventListener('DOMContentLoaded', function() {{
            initializeColorPanel();
        }});
    </script>
</body>
</html>'''
    
    return html_content
