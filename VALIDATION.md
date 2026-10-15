# Validation — 15 October 2026

Checks actually executed during development:

- **44 backend tests passed** on host Python 3.14.8.
- **44 backend tests passed** inside the production Python 3.12 image, running as the non-root image user with a read-only filesystem, no capabilities and no-new-privileges.
- **4 frontend tests passed** with Vitest and React Testing Library.
- TypeScript compilation and Vite production build passed.
- The multi-stage **AMD64 `magpie` Docker image built successfully**.
- The image started on localhost port 19080, served the React application, reported a healthy Docker health check, and ran as user `magpie`. Compose configuration validation passed.
- Administrator setup/sign-in and a writable bind-mounted destination were exercised against the running container. The final image served the supplied PNG logo and Bird TTF successfully. Desktop and 390-pixel mobile layouts were inspected in a real browser, and Enter submission cleared the URL and created a completed archive-skipped job. A container restart preserved the configured destination and three completed history entries.
- The real gallery-dl worker downloaded Wikimedia's small public `enwiki.png` image: **1 file, 7,951 bytes**, completed successfully. A subsequent independent worker process returned **1 skipped file** using the persistent native archive.
- A deterministic integration test runs the real gallery-dl extractor/downloader/file finalization and archive code, replacing only HTTP transport with controlled PNG bytes. It proves archive reuse across process restarts, successful retrieval into a separate destination, failure exclusion from the archive, and refusal to follow a media symlink into the separately writable archive directory.
- Queue tests exercise FIFO, two-worker concurrency, interrupted recovery, cancellation, total-job timeout and graceful shutdown using controlled work in real subprocesses.
- Kernel tests attempted traversal and symlink writes outside the selected root and confirmed rejection. Network tests reject private, loopback, metadata, mapped IPv6 and mixed DNS answers, including checks immediately before connect.

One non-failing warning is emitted by the installed Starlette test client about its future migration from httpx to httpx2. Production requests do not use TestClient.

Not certified by these checks:

- Deployment on the user's physical UGREEN NAS: no NAS connection or NAS IP was supplied. Check its firmware/kernel Landlock support and configure real NAS paths and UID/GID before deployment.
- ARM64 execution: the Dockerfile uses multi-architecture base images, but only AMD64 was built/run here.
- Every gallery-dl extractor or authenticated website: sites have different cookie, API, video and rate-limit requirements. Video support was subsequently added through yt-dlp and bundled sandboxed media helpers; see the video integration validation below.
- A native vector rendition of the supplied raster logo: SVG assets embed the original PNG losslessly. The supplied Bird font and illustration retain their original licensing.

To repeat a public-network check against an already configured instance, set `MAGPIE_TEST_PASSWORD` (avoid placing the password in shell history) and run `python scripts/smoke.py`. `MAGPIE_TEST_BASE` defaults to `http://127.0.0.1:9080`. This creates a history entry and may save the small public Wikimedia image in the configured default destination. It never deletes media.


## yt-dlp video integration update

- Host backend suite: **49 passed, 1 skipped** (the bundled Node runtime test runs in Docker).
- Container backend suite with the production restrictions: **50 passed**, including real yt-dlp generic-video extraction and download, video archive reuse, flat organisation, and a real FFmpeg merge verified by FFprobe to contain both audio and video streams.
- Media-helper tests verify that seccomp denies network socket creation, Landlock blocks reads outside media/system-library paths, and Node's permission model denies filesystem reads and child-process execution in challenge JavaScript.
- yt-dlp **2026.8.19**, official **yt-dlp-ejs 0.8.0**, FFmpeg/FFprobe and a sandboxed Node 24 runtime are bundled. Remote challenge-component downloads are disabled.
- **4 frontend tests passed**, and TypeScript/Vite production compilation passed with video-engine status in Settings.
- Live authenticated YouTube downloads and every yt-dlp extractor are not certified by these controlled tests; site changes, sign-in requirements and regional availability still apply.
- The Git ignore rule is now scoped to the root media folder (`/downloads/`) so `backend/app/downloads/` is included in GitHub source checkouts.
