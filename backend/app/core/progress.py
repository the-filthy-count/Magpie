"""Measured API percentages shared by REST serialization and SSE snapshots."""
def percentage(done, total):
    if done is None or total is None or total <= 0 or done < 0 or done > total:
        return None
    return round(done * 100.0 / total, 2)


def progress_fields(row):
    return {
        'file_progress_percent': percentage(row.get('file_bytes'), row.get('file_total')),
        'album_progress_percent': percentage(row.get('files', 0) + row.get('skipped', 0), row.get('total_files')),
    }
