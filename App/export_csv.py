import csv
import threading
from queue import Queue
from datetime import datetime
from dateutil import parser as dtparser, tz

CONCURRENT_WORKERS = 12  # keep default

def extract_status_changes(issue):
    changes = []
    histories = issue.get("changelog", {}).get("histories", [])
    for h in histories:
        when = dtparser.parse(h.get("created"))
        for item in h.get("items", []):
            if item.get("field") == "status":
                frm = item.get("fromString")
                to = item.get("toString")
                changes.append((frm, to, when))
    changes.sort(key=lambda x: x[2])
    return changes

def compute_time_in_status(issue, bh_overlap_fn, bh_cfg=None):
    changes = extract_status_changes(issue)
    fields = issue.get("fields", {})
    created = dtparser.parse(fields.get("created")) if fields.get("created") else None
    current_status = fields.get("status", {}).get("name")
    segments = []
    if changes:
        first_change_time = changes[0][2]
        initial_status = changes[0][0] or fields.get("status", {}).get("name")
        if created:
            segments.append((initial_status, created, first_change_time))
        for (frm, to, when), nxt in zip(changes, changes[1:] + [(None, None, None)]):
            next_time = nxt[2] if nxt != (None, None, None) else datetime.now(tz=when.tzinfo or tz.UTC)
            segments.append((to, when, next_time))
    else:
        if created and current_status:
            segments.append((current_status, created, datetime.now(tz=created.tzinfo or tz.UTC)))
    totals = {}
    for status, s, e in segments:
        if not status or not s or not e:
            continue
        hours = (e - s).total_seconds() / 3600.0
        if bh_cfg and bh_overlap_fn:
            hours = bh_overlap_fn(s, e, bh_cfg)
        totals[status] = totals.get(status, 0.0) + max(0.0, hours)
    return totals

def count_sequence_occurrences(changes, sequence):
    if not sequence or len(sequence) < 2:
        return 0
    count = 0
    i = 0
    n = len(changes)
    pair_index = 0
    needed_pairs = [(sequence[k], sequence[k+1]) for k in range(len(sequence)-1)]
    while i < n:
        frm, to, when = changes[i]
        need_from, need_to = needed_pairs[pair_index]
        if frm == need_from and to == need_to:
            pair_index += 1
            if pair_index == len(needed_pairs):
                count += 1
                pair_index = 0
        else:
            pair_index = 0
            first_from, first_to = needed_pairs[0]
            if frm == first_from and to == first_to:
                pair_index = 1
        i += 1
    return count

def get_comment_metrics(issue):
    comments = issue.get("fields", {}).get("comment", {}).get("comments", [])
    count = len(comments)
    total_length = 0
    commenters = set()
    for c in comments:
        body = c.get("body")
        if isinstance(body, dict) and "content" in body:
            import json as _json
            body_str = _json.dumps(body)
        else:
            body_str = str(body) if body is not None else ""
        total_length += len(body_str)
        author = c.get("author", {}).get("displayName") or c.get("author", {}).get("accountId")
        if author:
            commenters.add(author)
    return {
        "comment_count": count,
        "comment_length": total_length,
        "commenter_count": len(commenters),
    }

def export_csv(jira_client, jql, cfg, field_id_to_name, format_field_fn, business_hours_overlap, progress_cb):
    """
    progress_cb(stage: str, done: int, total: int)
    """
    # Stage 0: resolve keys
    keys, _ = jira_client.search_jql(jql, max_results=100, fields=["key"], expand_changelog=False)
    total = len(keys)

    q = Queue()
    for key in keys:
        q.put(key)
    results = []
    all_statuses = set()
    lock = threading.Lock()
    done_count = 0

    m = cfg.get("metrics", {})
    bh_cfg = cfg.get("business_hours", {})
    sel_ids = cfg.get("selected_field_ids") or cfg.get("selected_fields", [])
    trules = cfg.get("transition_rules", [])

    progress_cb("Stage 1/2: Downloading issues...", 0, total)

    def worker():
        nonlocal done_count
        while True:
            try:
                key = q.get_nowait()
            except Exception:
                return
            try:
                issue = jira_client.get_issue(key, expand_changelog=True)
                fields = issue.get("fields", {}) or {}

                row_fields = {}
                for fid in sel_ids:
                    row_fields[field_id_to_name.get(fid, fid)] = format_field_fn(fid, fields.get(fid))

                changes = extract_status_changes(issue)
                tr_counts = {}
                for tr in trules:
                    seq = tr.get("sequence", [])
                    tr_counts[tr["name"]] = count_sequence_occurrences(changes, seq)

                cm = get_comment_metrics(issue) if m.get("comment_count") or m.get("comment_length") or m.get("commenter_count") else {}
                tis = compute_time_in_status(issue, business_hours_overlap, bh_cfg) if m.get("time_in_status") else {}

                with lock:
                    if tis:
                        all_statuses.update(tis.keys())
                    results.append({
                        "key": issue.get("key"),
                        "fields": row_fields,
                        "tr": tr_counts,
                        "cm": cm,
                        "tis": tis
                    })
                    done_count += 1
            except Exception as e:
                with lock:
                    results.append({
                        "key": key,
                        "fields": {},
                        "tr": {},
                        "cm": {},
                        "tis": {},
                        "error": str(e)
                    })
                    done_count += 1
            finally:
                q.task_done()
                progress_cb("Stage 1/2: Downloading issues...", done_count, total)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(CONCURRENT_WORKERS)]
    for t in threads:
        t.start()
    q.join()

    # Stage 2: Build CSV content in-memory and return it to caller to write
    progress_cb("Stage 2/2: Writing CSV...", 0, total)

    sel_names = [field_id_to_name.get(fid, fid) for fid in sel_ids]
    headers = ["key"]
    headers.extend(sel_names)
    for tr in trules:
        headers.append(tr["name"])
    if m.get("comment_count"): headers.append("comment_count")
    if m.get("comment_length"): headers.append("comment_length")
    if m.get("commenter_count"): headers.append("commenter_count")
    all_statuses_sorted = sorted(list(all_statuses))
    if m.get("time_in_status"):
        headers.extend([f"TIS: {st}" for st in all_statuses_sorted])

    # Return a generator of rows so UI can stream-write and update progress
    def row_iter():
        for idx, rec in enumerate(sorted(results, key=lambda r: r.get("key") or "")):
            row = {"key": rec.get("key")}
            for name in sel_names:
                row[name] = rec["fields"].get(name, "")
            for tr in trules:
                row[tr["name"]] = rec["tr"].get(tr["name"], 0)
            if m.get("comment_count"): row["comment_count"] = rec["cm"].get("comment_count", 0)
            if m.get("comment_length"): row["comment_length"] = rec["cm"].get("comment_length", 0)
            if m.get("commenter_count"): row["commenter_count"] = rec["cm"].get("commenter_count", 0)
            if m.get("time_in_status"):
                for st in all_statuses_sorted:
                    row[f"TIS: {st}"] = round(rec["tis"].get(st, 0.0), 2)
            progress_cb("Stage 2/2: Writing CSV...", idx + 1, total)
            yield row

    return headers, row_iter