"""Measured API percentages shared by REST serialization and SSE snapshots."""
def percentage(done, total):
    if done is None or total is None or total <= 0 or done < 0 or done > total:
        return None
    return round(done * 100.0 / total, 2)


def progress_fields(row):
    file_percent=percentage(row.get('file_bytes'),row.get('file_total'))
    handled=row.get('files',0)+row.get('skipped',0)
    if row.get('total_files')==1:
        # A confirmed single-file job has one shared measure. Once downloaded
        # or archived, both remain complete even after byte counters clear.
        shared=100.0 if handled==1 else file_percent if handled==0 else None
        return {'file_progress_percent':shared,'album_progress_percent':shared}
    return {
        'file_progress_percent':file_percent,
        'album_progress_percent':percentage(handled,row.get('total_files')),
    }
