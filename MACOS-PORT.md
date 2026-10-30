# FLAVE for Mac: port notes

What differs from the main (Windows + NVIDIA) version of FLAVE: the feature
gaps, the behaviour changes, the Mac-only additions and the gotchas. Read this
before assuming the Mac version behaves like the original.

Status: **0.2.0-alpha**. Developed and tested on one Mac (Intel Core
i7-10700K, AMD Radeon Pro 5700, macOS 26). Nothing here was tested on
Windows.

- The code lives on the branch `macos-cpu-backend` of the fork
  `mtsprout/FLAVE`. The original is `filmladd-sys/FLAVE` (see
  [Staying in step with the original](#staying-in-step-with-the-original)).
- The original is not Mac-aware, and its README says it is not promising a
  Mac port. This is an independent port; nothing in it has been submitted
  to the original.

## Contents

1. [How the Mac version is selected](#how-the-mac-version-is-selected)
2. [What replaces what](#what-replaces-what)
3. [Feature gaps](#feature-gaps)
4. [Behaviour that is different on purpose](#behaviour-that-is-different-on-purpose)
5. [Mac-only additions](#mac-only-additions)
6. [Gotchas](#gotchas)
7. [Project files](#project-files)
8. [Performance](#performance)
9. [Not verified](#not-verified)
10. [Staying in step with the original](#staying-in-step-with-the-original)
11. [Running, building, data locations](#running-building-data-locations)

## How the Mac version is selected

There is one code base. Two switches decide which half runs:

| Switch | Values | Effect |
|---|---|---|
| `FLAVE_BACKEND` | `cpu` / `cuda` | `cpu` is the default on macOS: no CUDA, NVDEC, nvJPEG or OpenGL is touched. `cuda` forces the original GPU path (only meaningful on Windows / Linux with NVIDIA). |
| `FLAVE_UI` | `windows` | The Mac build uses one main window (`workspace.py`). `FLAVE_UI=windows` brings back the original separate windows. |
| `FLAVE_DATA_DIR` | a folder | Where settings and caches go (see the end of this file). |
| `FLAVE_SNAPSHOT_BUTTON` | `1` | Turns the title-bar screenshot button on (off on macOS, see gaps). |

Mac-only code is gated on `cpu_compositor.use_cpu_backend()` (compositing,
decode, preview, encode) and `workspace.enabled()` (UI). With
`FLAVE_BACKEND=cuda FLAVE_UI=windows` the original behaviour is meant to be
intact; that is a design intent, not a tested claim.

## What replaces what

| Original (Windows + NVIDIA) | Mac version |
|---|---|
| CUDA kernels in PTX (`sequence_player_gpu.py`) composite every layer | numpy compositor, `cpu_compositor.py` (`blend_layer`, the same rules as the kernel) |
| NVDEC via PyNvVideoCodec | ffmpeg decoding through a pipe (`cpu_decoder.py`, frame-accurate seek, fast input seek for constant-frame-rate files) |
| nvJPEG for preview frames | Qt (or Pillow) JPEG encode and decode |
| OpenGL Sequence Player window with CUDA interop | `sequence_player_cpu.py`: a QImage painted in a panel of the main window |
| NVENC render (`h264_nvenc`, `hevc_nvenc`) | Apple VideoToolbox (`h264_videotoolbox`, `hevc_videotoolbox`, default) or x264 / x265 on the CPU |
| Preview refresh planned around VRAM | F5 refresh is an ordinary pass over all frames; no VRAM plan |
| Separate windows for every tool | One main window with docked panels |
| Dark title bar through DWM | Not applicable; the Mac appearance and `theme.py` |

## Feature gaps

Things the main version does that this one does not (or does differently in a
way that matters).

1. **Proxy generation.** Proxies are made with `hevc_nvenc` and `scale_cuda`;
   there is no Mac equivalent. The Proxies and Proxy Default columns in the
   Footage panel are hidden by default (header right-click turns them on).
   Proxy files that already exist (for example from a Windows project) are
   decoded through ffmpeg like any footage, if their paths resolve.
2. **Screen capture.** `flave_capture.py` (ddagrab, Win32 monitor calls,
   WASAPI loopback) is a standalone Windows tool; nothing in the app starts
   it. It does nothing on a Mac.
3. **Title-bar screenshot button.** The camera button over every window's
   title bar is placed with Windows title-bar geometry and drifts on
   macOS, so it is not installed. Use Cmd+Shift+4, then Space.
   `FLAVE_SNAPSHOT_BUTTON=1` turns it back on.
4. **Full-screen player (F11).** The player is a panel, not a window, so it
   cannot be made full screen on its own. The whole app can be full screen
   (the green button). Playback Size (Fit / 75 / 50 / 25 %) is a dropdown in
   the transport bar.
5. **GPU memory settings do nothing.** Global Settings values that tune VRAM
   use (Preview Frame Cap, GPU batch size for the preview) do not apply to
   the CPU backend. The render chunk size still uses `previewGpuBatchFrames`.
6. **Captions run on the CPU only** (faster-whisper, int8). There is no CUDA
   cuBLAS / cuDNN setup. Generating captions is much slower than on a GPU.
7. **Replace footage works here** (`relink.py`); in the original it is a stub.
   It is the fix for the first gotcha below.
8. **Not bit-exact with the GPU.** The compositor follows the PTX kernel's
   rules (nearest-pixel sampling, crop, rotate, chroma, colour, outline) but
   rounding can differ in single pixels. A render from the Mac version is not
   guaranteed identical to one from the CUDA version of the same project.

## Behaviour that is different on purpose

- **Opening a timeline:** double-click a sequence (Enter or F2, or the
  right-click Rename, renames it; a press-and-hold also renames).
- **Footage panel:** double-click a footage row to add it at the playhead.
  Rename (F2 or press-and-hold) gives an item its own display name; the file
  name is not changed. Height, Width, Codec, PxA and the proxy columns are
  hidden by default.
- **Timeline:** the Type column is hidden, track rows default to 60% of
  their saved height (slider at the bottom left changes the display only).
- **New clips larger than the sequence** are dropped scaled to fit. Clips
  already in a project keep the old 1:1 centre crop.
- **Dropping footage where there is no track** creates the track or tracks
  it needs. Dropping onto a track of the wrong type is still refused.
- **Menus:** the per-window menu bars are gone. Everything is in the one
  macOS menu bar (File, Edit, Footage, Sequence, Transitions, Mark, Tracks,
  Preview, Settings, Windows). Ctrl shortcuts are Cmd on the Mac; Alt is
  Option (Option+X clears In and Out).
- **Dark mode** follows macOS (and the old Dark Mode setting still forces
  dark).
- **Settings and caches** are in a different folder when running as an app
  (see the end of this file).

## Mac-only additions

None of these exist in the original.

- One main window (Footage and Sequences left, player centre, timelines
  along the bottom as tabs, Render as a side panel); the layout is
  remembered; Windows > Reset Layout.
- A theme (`theme.py`), a transport bar with a fixed-width timecode,
  frame stepping on the arrow keys, K / L pause / play, up and down jump to
  edits, and a Playback Size dropdown.
- Drag and drop from Finder onto the Footage panel, the timeline or the player.
- Footage display names, compact Footage rows and timeline labels, a track
  height slider, a zoom navigator under the tracks, vertical grid lines at the
  ruler's timecodes.
- Fades (in, out, in and out) and cross dissolves in one click
  (`fades.py`: Transitions menu and the clip right-click menu), with a Fade
  Length setting.
- One folder per new project (`project_dirs.py`): File > New Project makes
  `<chosen folder>/<Name>/` holding `<Name>.db` (with its undo, audio cache and
  preview files) and a `render/` folder. Every render defaults to
  `PROJECT_HOME/render/<Name>_<Sequence>_vNN.mp4`; a relative Output path also
  lands there. Existing projects keep their folder as PROJECT_HOME and get
  `render/` the first time they render. Media is referenced, not copied.
  (Windows / CUDA path: unchanged.)
- Replace footage (`relink.py`): relinks a footage item to another file,
  keeping its clips, and offers the other missing files in the same place.
- Text animation (`text_anim.py`: Text menu and a text clip's right-click
  menu): Typewriter, Word by Word, Line by Line, Wipe In / Out reveals (crop
  keyframes on the text layer, so no compositor change), and Add Title / Add
  Lower Third templates. Fades (`fades.py`) now also work on text clips.
- Drop preview (`sequence_timeline_droppreview.py`, extended): ghost boxes also
  for Finder drags (probed with ffprobe), dashed boxes for tracks the drop will
  create, red boxes where it would be refused, and a timecode label.
- Effects (`effects.py`, `cpu_effects.py`): Drop Shadow, Blur, Focus In / Out and
  Remove, from the Effects menu or the clip right-click menu. They are two new
  keyframe types (`blur`, `shadow`). The CPU compositor draws the layer on black
  and on white to recover its exact colour and alpha, then blurs and shadows
  that. **The Windows GPU kernel does not draw these**; a project using them
  opened in the original shows the keyframe clips but no effect.
- Motion presets (`motion.py`: Motion menu and the clip right-click menu):
  slide in / out, pop, zoom, shake on video, image and text clips, with
  easing baked into ordinary keyframes (so projects stay readable by the
  original). Length and easing are settings (`motion_seconds`, `motion_ease`).
- In and Out points (`marks.py`): I and O set them, Shift+I / Shift+O go to
  them, Option+X clears. They show on the ruler as halves of the playhead
  marker and can be dragged. The Render panel can render In to Out only
  (video, audio and captions cut to the range).
- Render: an Encoder choice (Fast with the Mac's video hardware, or High
  quality on the CPU), and bitrates that grow with the Output Size
  (the original has a single resolution: the sequence's).
- Render Output Size: composite at 1080p, 1440p or 4K UHD from a smaller
  sequence (positions, scales and text grow with it).
- A bigger, grabbable playhead handle.
- An application icon, an About box, and a packaged `.app`.

## Gotchas

1. **Windows paths do not resolve.** Project files store the full path of
   every media file. A project made on Windows (`P:/Flave/clip.mp4`) opens on
   a Mac with every clip offline. Fix it with right-click > Replace in the
   Footage panel: pick the new file, and FLAVE offers to relink the other
   missing files that sit in the same place relative to it.
2. **ffmpeg and ffprobe must be installed** (`brew install ffmpeg`). The app
   adds `/opt/homebrew/bin` and `/usr/local/bin` to its PATH, so Finder
   launches find them, but it does not bundle them.
3. **The hardware encoder is picky about size.** The H.264 hardware encoder
   refuses very small frames (it failed at 256 x 144). The Render panel
   tests the real output size first and falls back to the CPU encoder with a
   message. Hardware encoders usually give lower quality than x264 at the
   same bitrate (the two were not compared side by side here); choose High
   quality (CPU) for final output.
4. **Hardware or CPU, the default bitrate is 5 Mbps** until you choose an
   Output Size above the sequence size, then it scales with the pixel count
   (20 Mbps at 4K UHD). Once you type a bitrate it stops changing.
5. **4K sources in a 1080p sequence are slow on the CPU.** Clips dropped
   from now on are scaled to fit, which helps; a clip already in a project at
   100% crops the centre of the 4K picture and is the slow case (upscaling
   at 4K output).
6. **A project is touched when you open it.** Opening a project adds columns
   (see Project files). Keep a copy before moving a project between the
   Mac and Windows versions.
7. **Undo does not cover In / Out changes** (they are saved the moment you
   set them).
8. **The `.app` starts with no project and its own settings.** It does not
   read the settings of a `python project_manager.py` session. Use File >
   Open Project.
9. **The macOS menu bar says "Python"** when run from source unless pyobjc is
   installed (`pip install pyobjc-framework-Cocoa`); the packaged app has
   the right name from its Info.plist.
10. **The ad hoc signed app is blocked by Gatekeeper on other Macs.**
    Right-click, Open, or `xattr -dr com.apple.quarantine "FLAVE for Mac.app"`.
11. **Python 3.11 or newer** is needed for fast preview audio reads (as in the
    original); 3.14 is what this was built and tested on.
12. **Pillow is optional but recommended.** Playback decodes preview JPEGs on
    background threads; with Pillow the decode does not hold the GIL.

## Project files

The Mac version adds three optional pieces of data to a project database.
Older projects get them automatically the first time they are opened.

| Table.column | Meaning |
|---|---|
| `clips.fit_percent` | Fit scale of a clip dropped when larger than the sequence |
| `footage.display_name` | The footage item's own name (the file name is unchanged) |
| `sequences.mark_in`, `sequences.mark_out` | In and Out points (frames, inclusive) |

Fades and dissolves are ordinary keyframe clips (opacity and volume), so the
original version treats them as it treats any keyframe clip.

What to expect, in each direction (reasoned from the code, not tested on
Windows):

- **Original -> Mac:** opens; columns are added. Media paths may need fixing
  (gotcha 1).
- **Mac -> original:** the extra columns are ignored by the original, so fit
  scaling, display names and marks are not seen there (a clip with a fit scale
  shows at 100% in the original). Keyframe fades work.

## Performance

Measured on the machine above; your numbers will differ.

| Task | Result |
|---|---|
| Preview build, 1080p sequence, 4K source | about 15 fps (it was 4.6 fps before the compositor fast paths) |
| Playback from the preview cache | steady 30 fps; median gap 30 ms, 2% of frames over 50 ms |
| 4K UHD render of a 4K clip, hardware encoder | about 19 fps (10.5 fps with x264) |
| 4K UHD render of the same clip, upscaled from a 1:1 crop | about 12 fps |

Where the time goes: at 4K the encoder was the wall with x264 (15 fps alone);
with the hardware encoder the render thread is the limit (about 20 ms of
compositing in isolation, 36 ms inside a live render because it competes with
ffmpeg for memory bandwidth). Faster would mean moving less data per frame
(an ffmpeg-filter fast path for plain-cut timelines, or compositing several
stretches at once), not a lower-level language.

## Not verified

- The CUDA path on this branch (nobody here has an NVIDIA machine).
- Opening Mac-saved projects in the original, and the reverse.
- Text clips rendered at an Output Size other than the sequence size
  (written, never exercised).
- The on-player text move / edit overlay in the docked player.
- The Dock icon and the application-menu name from source on every macOS
  version; the packaged app is the reliable way.
- Multi-monitor layouts, Retina scaling of the player on external displays,
  live switching between light and dark appearance.
- Very long projects and many-layer timelines.
- There is no automated test suite; checks were run headless (Qt offscreen)
  against small generated projects.

## Staying in step with the original

The original keeps changing; this port has to be merged forward regularly.

- Remote setup: `origin` is the fork, `upstream` is the original and is
  read-only (its push address is disabled on purpose).
- Routine: `git fetch upstream`, then merge `upstream/main` into
  `macos-cpu-backend`; small and often. `counter.txt` (the build number)
  conflicts every time: take the original's.
- Mac-only code sits behind seams so shared files stay close to the original:
  `cpu_compositor.py`, `sequence_player_cpu.py`, `workspace.py`, `theme.py`,
  `transport.py`, `timeline_scale.py`, `footage_drop.py`, `footage_names.py`,
  `clip_fit.py`, `fades.py`, `marks.py`, `app_paths.py`, `version.py`,
  `packaging/`, `assets/`.
- Shared files this port edited (merge-conflict hot spots): `render_manager.py`,
  `sequence_timeline.py`, `sequence_timeline_sql.py`,
  `sequence_timeline_ruler.py`, `sequence_timeline_clips.py`,
  `sequence_player.py`, `sequence_player_preview.py`,
  `sequence_preview_worker.py`, `project_manager.py`, `footage_manager.py`,
  `footage_manager_display.py`, `sequence_manager.py`, `new_project.py`,
  `global_settings.py`, `cuda_context.py`, `window_snapshot.py`,
  `cpu_decoder.py`.
- After a merge: a new window or tool must be hooked into the main window
  (`workspace.embed`, the menus), and a new GPU effect or a change to the
  PTX kernel or `SequencePlayer._blend` must be ported to
  `cpu_compositor.blend_layer`. Every effect in the original at the time of
  writing is ported.
- Nothing is sent to the original repository from here.

## Running, building, data locations

- Run from source: `python project_manager.py` in a venv with
  `PySide6 numpy pillow` (and optionally `pyobjc-framework-Cocoa`), with
  ffmpeg installed.
- Build the app: `packaging/build_app.sh` makes `dist/FLAVE for Mac.app`
  (about 155 MB, ad hoc signed). `packaging/README.md` covers Developer ID
  signing and notarization (not done).
- Data: from source, `globalsettings.db` and the Whisper `models` folder sit
  next to the `.py` files, as in the original. As an app, they are in
  `~/Library/Application Support/FLAVE for Mac/`. `FLAVE_DATA_DIR` overrides
  both.
- Project files, preview caches (`*_Preview.db`), audio caches and undo files
  sit beside the project, as in the original.

### Daily upstream check

`tools/upstream_watch.sh` runs every day at 07:00 through a launch agent
(`~/Library/LaunchAgents/io.github.mtsprout.flave-upstream-watch.plist`; the
source copy is in `tools/`). It only runs `git fetch upstream`. If the
original's `main` has new commits, a read-only Claude run writes a triage
report to `upstream-reports/YYYY-MM-DD.md` (what changed, whether it applies,
port work needed, merge forecast) and a macOS notification appears. It never
merges or pushes. The log is `upstream-reports/watch.log`. Run it by hand with
`tools/upstream_watch.sh --force`. The Mac must be awake; a missed run happens
at the next wake. Stop it with
`launchctl bootout gui/$(id -u)/io.github.mtsprout.flave-upstream-watch`.
