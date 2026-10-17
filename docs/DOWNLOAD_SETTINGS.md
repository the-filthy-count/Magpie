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
