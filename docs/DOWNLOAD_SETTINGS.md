# Download settings

Settings → Download engine contains the global defaults. Changes apply when a
worker starts, not to already running downloads. Existing media is never moved.
The chosen destination path and destination organisation override are saved when
a job is submitted, including API jobs.

## Organisation

- **Organised** uses the extractor's native directory structure.
- **Flat** saves directly in the selected destination.
- **Flat with gallery name** also saves directly in the destination, with names
  such as `Summer gallery - original_filename.jpg`. The gallery title is taken
  from available album/gallery/playlist metadata. Missing titles fall back to the
  native filename. Unsafe filename characters are sanitised and excessively long
  names shortened with a stable hash. No title can create a directory or escape
  the selected destination. Custom filename templates are still prefixed.
- **Custom** uses the shared directory components, one per line, and optional
  filename template. Fields must exist in the source extractor's metadata.

Each destination has an organisation selector in Destinations → Edit. **Use
global / website default** follows normal defaults. An explicit destination mode
wins over the website rule and global mode. The override is saved with each job;
changing the destination later affects new submissions, not queued jobs. Custom
mode uses the shared directory template.

Archives remain scoped to destination IDs. Changing naming/layout does not force
archived files to download again or rearrange existing files. Flat naming can
cause collisions if your own filename template omits unique source identifiers.
Keep native filenames where possible.

## Video preferences

These options apply to videos handled by yt-dlp, not direct image/video HTTP
files. Maximum quality supports best available, 1080p, 720p or 480p. A height cap
selects streams at or below that size; it does not upscale/downscale or transcode.
If no suitable stream exists, the engine reports failure rather than silently
exceeding the cap. **Prefer MP4** prefers available MP4/M4A streams and falls back
to another available format; it is not a promise to convert every source to MP4.
FFmpeg joins separate audio/video streams as before.

**First / single video only** processes the first video in a playlist (or the
selected video when the site offers that choice). **Entire playlist** follows all
available videos. Ordinary image galleries are unaffected by this video-only
setting.

Subtitles may be off, published subtitles only, or published plus automatic
captions. Enter language codes such as `en, en-US`. Only tracks supplied by the
site are downloaded, as separate subtitle files. No caption generation or
translation is performed. Subtitle sidecars do not count as additional media
files in the job's file counter.

## Filters and limits

Choose all media, images, videos, or an extension allowlist. Extensions are entered
without dots, separated by commas. Filters use extractor metadata; unknown
extensions are excluded when filtering. Excluded files are not archived, so a
later job with different filters can retrieve them. Album totals still describe
the source album, including files excluded by filters.

Maximum new files per job excludes archived/existing skips; 0 is unlimited.
The limit spans gallery-dl child jobs in the same worker. Maximum file size is
entered in MiB; 0 is unlimited. Known oversized HTTP/video files are rejected by
the engine. Stream progress also checks the limit, and finalisation checks the
actual media size before recording success. Files that exceed the limit after
starting can leave partial data for inspection or a later retry with a larger
limit; they are not finalised or archived. Retrying does not automatically delete
partial data. Subtitles are not covered by the media-size limit.

## Daily hours and restart recovery

Daily hours gate starting queued jobs, using the container's `TZ` timezone.
Overnight windows work (e.g. 22:00–06:00); equal start/end means all day. Active
jobs finish normally outside the window. There is no browser dependency.

Automatic recovery is off by default. When enabled, startup requeues interrupted
jobs, resets attempt progress, and uses the same destination archive and partial
files. Previously completed media is skipped. `.part` downloads are enabled;
resumption depends on the source supporting it. No resumption guarantee is made
for expired links, changed media or unsupported server Range responses.

## Website defaults

The Advanced website section can override organisation, filename template,
request delay, retries, timeout and rate limit. Enter a hostname such as
`bunkr.cr`, not a full URL. Rules apply to that hostname and subdomains; the most
specific matching hostname wins. Matching uses the submitted URL's hostname,
not a redirected CDN or gallery-dl category name. Empty controls inherit global
values. A destination's explicit organisation mode has the final say.

All options are validated and translated by Magpie. Arbitrary gallery-dl/yt-dlp
configuration, executable hooks, shell commands and external filesystem paths
remain unavailable.

## Changing a destination path

Edit the container path under Destinations → Edit, with typing, autocomplete or Browse. The target must already exist and be writable under a permitted download root. Finish or cancel active jobs before changing it. Files stay in their original folder. New jobs use a fresh archive for the new path; history and retries keep their original path and archive.


## In Progress storage

New jobs default to **Publish only when the whole download completes**. Settings → Download engine → More download options → In Progress storage lets you browse/type a dedicated container folder. Leave the location empty to use `<destination>/.magpie-in-progress/<job-id>/`; each job is isolated. Disable the option to restore immediate per-file publication. Settings changes affect new jobs, while queued/failed jobs retain their staging and destination snapshots. Existing jobs without a snapshot adopt the current setting when first executed after upgrading.

A custom location must already exist, be writable, and sit inside an explicitly permitted root. A destination cannot be inside In Progress storage. For a separate Docker bind mount, uncomment the `/in-progress` volume in Compose, set `IN_PROGRESS_PATH` to the host directory and include `/in-progress` in `MAGPIE_DOWNLOAD_ROOTS`; give the configured container UID/GID write access. Then select `/in-progress` in settings. No additional mount is needed for the default hidden folder.

Files retain normal extensions inside staging once their `.part` transfer finishes, allowing video merging and subtitles to work normally. If downloading fails, is cancelled or is interrupted, completed and partial files remain there for retry. Each job keeps its native archive under `/config/archives/<destination-archive>/jobs/<job-id>/`; entries reach the shared destination archive only after publication. Thus an unfinished job cannot make a separate job skip unpublished files. Existing destination archives still prevent repeat downloads. Archives describe files retrieved successfully; do not manually remove staged files while a job is recoverable.

After a successful engine run, the job remains `downloading` with `phase: "publishing"` until all files are published and the shared archive commits. The interface shows **Publishing**. File/album percentages still describe downloads and may reach 100 before publication completes. Publication has no invented percentage or speed.

On the same filesystem, files publish via fast, non-overwriting hard links before staging copies are removed. Across filesystems, complete files copy to hidden `.magpie-transfer-<job-id>` files in the target directory, sync and then publish atomically per file. This needs space on both disks. The destination filesystem must support hard links. Existing files with identical contents are accepted when retrying an interrupted publication; conflicting contents fail safely without replacement. Failed publication keeps the source files, though any files already published remain visible. Albums publish per file, including organised layouts; publication of an entire album is not atomic.

Exclude `.magpie-in-progress`, custom staging storage and `.magpie-transfer-*` from library scans. Removing history or destinations never deletes staged files or media; deleting history removes the job's retry control, so retry first if you want to finish it. Cancel before manually cleaning abandoned staging folders. Per-job archive metadata remains under `/config` for recovery.
