# Using FLAVE for Mac

A walkthrough of the editor, from a blank project to a finished file. It assumes
you have cut video before (tracks, clips, playhead, in and out points, keyframes)
and just need to learn where FLAVE keeps things.

Where the Mac version differs from the original Windows editor, this guide covers
the Mac behavior only. For the full list of gaps and gotchas, see
[MACOS-PORT.md](MACOS-PORT.md).

**Keyboard note.** Menus and this guide write shortcuts the way the code does,
for example `Ctrl+C`. On a Mac, `Ctrl` in those shortcuts is the **Command** key.

## Contents

1. [Starting the app](#1-starting-the-app)
2. [The main window](#2-the-main-window)
3. [Projects](#3-projects)
4. [Importing footage](#4-importing-footage)
5. [Sequences](#5-sequences)
6. [Putting clips on the timeline](#6-putting-clips-on-the-timeline)
7. [Playing and navigating](#7-playing-and-navigating)
8. [Editing clips](#8-editing-clips)
9. [Tracks](#9-tracks)
10. [Fades and cross dissolves](#10-fades-and-cross-dissolves)
11. [Keyframes](#11-keyframes)
12. [Text and captions](#12-text-and-captions)
13. [Preview refresh](#13-preview-refresh)
14. [In and Out points, and rendering](#14-in-and-out-points-and-rendering)
15. [Settings](#15-settings)
16. [Keyboard shortcuts](#16-keyboard-shortcuts)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Starting the app

- **The packaged app:** open `FLAVE for Mac.app` (build it with
  `packaging/build_app.sh`; the result is in `dist/`). Because the app is only
  ad hoc signed, macOS may ask you to approve it the first time: right-click
  it, choose **Open**, and confirm.
- **From source:** in the project folder, run `python project_manager.py` (see
  the README for installing the requirements; FFmpeg must be installed, for
  example with `brew install ffmpeg`).

FLAVE reopens the project you had open last, with your window layout.

## 2. The main window

Everything lives in one window:

```
+----------------------+------------------------------+
| Footage              |                              |
| (your imported       |        Player                |
|  media)              |        (with transport bar)  |
+----------------------+                              |
| Sequences            |                              |
+----------------------+------------------------------+
| Timeline tabs: one tab per open sequence            |
| (tracks, clips, ruler, track height, zoom bar)      |
+-----------------------------------------------------+
```

- **Footage** (top left) lists everything you imported.
- **Sequences** (bottom left) lists your timelines.
- **Player** (center) shows the frame at the playhead. A transport bar sits
  under it.
- **Timelines** (bottom) are tabs. Open as many sequences as you like and switch
  between them. The × on a tab closes it.
- **Render** opens as a panel on the side (File > Render, or the Mark menu).

Drag the dividers to resize panels, and drag a panel's title to move it. Your
layout is remembered. If it gets messy, use **Windows > Reset Layout**.

The menu bar changes with what is in front. The menus you will use most:

| Menu | What is in it |
|---|---|
| File | New Project, Open Project, Close Project, Import Footage, Render, Exit, About |
| Edit | Undo, Redo, then the front timeline's clip editing (copy, cut, paste, find) |
| Footage | Import, Slug (color bar or fill), Sort By (name, type, size, length) |
| Sequence | Add New Sequence |
| Tracks | Add a video, audio, image, caption, keyframe or text track |
| Transitions | Fades, Cross Dissolve, Fade Length |
| Motion | Slide, Pop, Zoom and Shake presets, Motion Options |
| Text | Add Title, Add Lower Third, Reveal Selected Text, Typing Speed |
| Mark | In and Out points, and Render In to Out |
| Preview | Refresh, Clear Video, Clear Audio |
| Settings | Global Settings, Project Settings |
| Windows | Show or hide the panels, Reset Layout |

## 3. Projects

A project is a single `.db` file that holds your footage list, sequences, clips,
keyframes and settings. Your media files stay where they are on disk.

Each new project gets **its own folder**, the project home:

```
My Film/              <- created for you inside the folder you pick
  My Film.db          <- the project (its undo and cache files sit beside it)
  render/             <- every render goes here by default
```

- **New Project:** File > New Project. Choose the folder to create it in, then
  type a name. FLAVE creates `<that folder>/<name>/` with the project and a
  `render` folder inside.
- **Open Project:** File > Open Project, and pick a project file.
- **Close Project:** File > Close Project.

Undo and redo work across the project: `Ctrl+Z` and `Ctrl+Y`. The undo stack
size is a setting (see [Settings](#15-settings)).

## 4. Importing footage

Three ways in:

1. Drag video, audio or image files from **Finder** onto the Footage panel.
2. File > Import Footage (or Footage > Import).
3. Drag files straight onto a timeline or the player (see the next section).
   They are imported and placed in one step.

Importing a file twice reuses the existing footage item instead of making a copy.

In the Footage list:

- **Rename:** press and hold on a row for about half a second, or right-click >
  **Rename**. This sets a display name only; the file on disk keeps its name.
- **Sort:** Footage > Sort By.
- **Columns:** the proxy, size, codec and pixel-aspect columns start hidden.
  Right-click the header to show them.
- **Slug:** Footage > Slug makes a solid color bar or color fill you can use as a
  background or a title card base.
- **Replace** (right-click) points a footage item at a different file and keeps
  its clips. Use it when media moved or a project came from another computer.
  After you pick the file, FLAVE offers to relink the other missing files that
  sit in the same place. **Remove** takes the item out of the project.

## 5. Sequences

A sequence is one timeline with its own size, frame rate and tracks.

- **Create:** Sequence > Add New Sequence, or right-click in the Sequences panel
  and choose **New Sequence**.
- **Open the timeline:** double-click it, or right-click > **Open Timeline**. It
  opens as a tab in the bottom area.
- **Rename:** right-click > Rename, or select it and press Enter or F2.
- **Settings:** right-click > Settings changes its size and frame rate.

Pick the sequence size before you start editing. Footage that is larger than the
sequence is scaled to fit when you drop it (see below).

## 6. Putting clips on the timeline

**Drop footage on the timeline.** Drag from the Footage panel, or from Finder,
onto the timeline.

- If the drop lands on a matching track, the clip goes there.
- If there is no track under the cursor, FLAVE **creates the tracks it needs**.
  A video file makes a video track and an audio track, linked together. An audio
  file makes an audio track. An image makes an image track.
- Footage bigger than the sequence is **fit-scaled** so it fits inside the frame
  (a 4K clip in a 1080p sequence shows whole, not cropped). The scale is stored
  with the clip, and you can still change it with keyframes.

**Drop footage on the player.** This adds the clip at the playhead.

**Double-click a footage row** to add that clip at the playhead.

Video clips with sound arrive as a linked pair. Moving or trimming one moves the
other. Right-click > **Unlink** to separate them, and **Link** to join selected
clips again.

## 7. Playing and navigating

### The transport bar

Under the player: Home, Previous edit, Play/Pause, Next edit, End. Next to those
are the timecode, the sequence length, and a **Size** dropdown that scales the
player picture (it also shows the In and Out marks when set).

The Size dropdown only changes how big the picture is drawn in the player. It
doesn't change what you render.

### Keys (with focus in the player or timeline)

| Key | Action |
|---|---|
| Space | Play / Pause |
| K / L | Pause / Play |
| Left / Right | Back / forward one frame |
| Shift+Left / Shift+Right | Back / forward ten frames |
| Up / Down | Jump to the previous / next edit |
| Home / End | Go to the start / end of the sequence |

### The timeline

- Click or drag in the **ruler** to move the playhead. Grab the handle at the top
  of the playhead to scrub.
- **Zoom:** `+` and `-`, or use the navigator below (next item).
- **Zoom navigator:** the bar at the bottom shows the whole sequence, with a lit
  window for the part you are looking at. Drag the window to scroll, drag either
  end to zoom, click outside it to jump there, and double-click to fit the whole
  sequence.
- **Track height:** the slider at the bottom left of the timeline makes every
  track taller or shorter. This is display only, and it is remembered.
- Vertical lines in the clip area mark timecode steps.

## 8. Editing clips

Select a clip by clicking it. Select several with a rubber band (drag in empty
space) or by clicking several.

| To do this | Do this |
|---|---|
| Move a clip | Drag it. It snaps to neighboring clip edges and the playhead. |
| Trim a clip | Drag its left or right edge. |
| Slice | Press `C` to enter slice mode, click where to cut, press `V` (or Escape, or right-click) to leave. Or right-click a clip > Slice. |
| Copy / Cut | `Ctrl+C` / `Ctrl+X` |
| Paste | `Ctrl+V` pastes at the playhead ("Paste To Tic"). Edit > **Paste to End**, **Paste w/New Tracks** and **Paste Insert w/New Tracks** are also there. |
| Delete | Delete key, or right-click > Delete. Leaves a gap. |
| Ripple delete | Right-click > **Ripple Delete**. Closes the gap. |
| Change speed | Right-click > **Speed...** (1 to 1000 percent). Linked clips change together. |
| Change audio gain | Right-click an audio clip > **Gain...** |
| Rename a clip | Right-click > Rename |
| Disable / Solo | Right-click > Disable (or Enable), Solo |
| Add a marker | Right-click > Marker > Add To Mouse Click, or Add to Time Tick |
| Detect scene cuts | Right-click a video clip > **Scene Detect (Slice)** |

Right-click on a marker to edit or delete it.

## 9. Tracks

Add tracks from the **Tracks** menu or by right-clicking empty timeline space:

`+ Video`, `+ Video/Audio`, `+ Audio`, `+ Image`, `+ Caption`, `+ Keyframe`,
`+ WYSIWYG Text`.

Right-click a track's header for:

- Delete Track
- Move > Up, Down, To Top, To Bottom
- Disable (mute or hide it) and Solo
- Open / Collapse Selected, to show or fold tracks
- Track Display Properties
- Duplicate Track(s) > Above or Below

Tracks higher in the list are drawn on top of tracks below them.

## 10. Fades and cross dissolves

All of these are in the **Transitions** menu, and in a clip's right-click menu
under **Fade**. Each one is a single undo step.

1. Select one or more clips.
2. Choose **Fade In**, **Fade Out**, or **Fade In and Out**.

Video and image clips fade in opacity. Audio clips fade in volume. The fade is a
ready-made keyframe clip on a keyframe track above the clip. You can edit it like
any keyframes ([next section](#11-keyframes)).

**Fade length:** Transitions > **Fade Length...** sets the default, in seconds.
A fade can't be longer than the clip allows. Very short clips get a shorter
fade.

**Cross dissolve:** select two clips of the same kind that **overlap in time on
different tracks**, then choose **Cross Dissolve**. Over the overlap, the upper
video clip fades in (if it starts later) or out (if it ends first). With two audio
clips, the sound crossfades. If you don't meet those conditions, FLAVE says what
to select.

## 10a. Motion presets

The **Motion** menu (and a clip's right-click > **Motion**) adds one-click
animation to the selected video, image or text clips. Like the fades, each
preset is built from ordinary keyframes on keyframe tracks above the clip, in a
single undo step, so you can open and tweak the keys afterward.

| Preset | What it does |
|---|---|
| Slide In (Left, Right, Top, Bottom) | The clip glides in from off screen to where it sits |
| Slide Out (Left, Right, Top, Bottom) | The clip glides off screen at its end |
| Pop In / Pop Out | Scales up with a slight overshoot (or shrinks away) while fading |
| Zoom In / Zoom Out (whole clip) | A slow push in or pull out of about 15 percent |
| Shake | A quick jitter that settles at the start of the clip |

**Motion > Motion Options...** sets the length in seconds (default 0.75) and the
easing (ease out, ease in, ease in and out, overshoot, or linear). Applying a
second preset to the same clip adds to its keys. If two presets overlap, the
newer one replaces the keys in the overlap.

## 11. Keyframes

Keyframes animate a property over time. In FLAVE they live in **keyframe clips**
on **keyframe tracks** above the clip they affect, linked to it.

1. Add a keyframe track (Tracks > + Keyframe), or right-click a clip >
   **Add Keyframe Clip After**. Right-clicking a track also offers **Add Keyframe
   Clip**.
2. Pick the property the keyframe clip controls. One keyframe clip controls one
   property, and you can change it only while it has no keys.
3. Add keys: right-click the keyframe clip > **Key > Add At Playhead** or
   **Add At Mouse Click**, then edit values in the keyframe dialog.

Properties you can animate:

| Group | Properties |
|---|---|
| Position and size | position X, position Y, move (X and Y together), scale |
| Rotation and crop | rotate, crop X, crop Y, crop XY, crop edges (top, bottom, left, right) |
| Look | opacity, gamma, brightness, contrast |
| Effects | border (outline width and color), chroma (key out a color with a tolerance) |
| Audio | volume |

Notes:

- Values hold flat before the first key and after the last, and change in a
  straight line between keys.
- **Key > Paste** puts copied keys At Mouse Click, At Playhead or At Clip Center.
- **Key > Delete Keys Beyond Event Horizon** removes keys outside the clip.
- Keyframe clips can have their speed changed like any other clip.

## 12. Text and captions

### Text clips

1. Add a `+ WYSIWYG Text` track.
2. Right-click the track > **Add Text Clip**.
3. Edit the text on the clip, then set the font, size, color and optional drop
   shadow in the text style window.

The last style you used is the style of every new text clip.

### Titles and text animation

The **Text** menu has ready-made titles and reveals. They use normal text clips
and keyframes, so you can restyle or edit anything afterward.

- **Add Title:** a centered "Title" at the playhead that fades in and out
  (4 seconds). Change the words and style like any text clip.
- **Add Lower Third:** a "Name" and a smaller "Subtitle" at the lower left, which
  slide in from the left and fade out at the end (5 seconds). Each goes on its
  own text track, and new tracks are created on top when none is free.
- **Reveal Selected Text** (also a text clip's right-click > **Text Reveal**):
  - **Typewriter:** one letter at a time (several lines reveal line by line).
  - **Word by Word:** a word at a time, with a short pause after each.
  - **Line by Line:** a line at a time, top down.
  - **Wipe In / Wipe Out:** the text uncovers (or covers up) left to right over
    about a second. Wipe Out sits at the end of the clip.
- **Typing Speed...** sets characters per second for the typewriter (default 16).

Edit the text first, then apply a reveal: the timing follows the words that are
there. If you change the text afterward, apply the reveal again.

The fades in the Transitions menu work on text clips too.

### Captions

1. Add a `+ Caption` track, then right-click > **Add Caption** to type one by
   hand.
2. Or generate them: right-click an audio or video clip > **Generate Captions**.
   This needs the optional `faster-whisper` package (`pip install faster-whisper`)
   and runs on the CPU, so it can take a while on long clips.
3. Right-click a caption > **Edit** to fix the text.
4. **Find:** `Ctrl+F` searches captions, with `F3` and `Shift+F3` for next and
   previous.

When you render, tick **Include captions** to burn them into the picture, or
**Export subtitles as .srt** to get a separate subtitle file.

## 13. Preview refresh

FLAVE builds a preview of your sequence in the background so playback is smooth.
When you change a clip, the frames it affects are marked out of date and rebuilt.

- A small status line at the bottom right of the timeline shows progress.
- **F5** (or Preview > Refresh) rebuilds anything out of date.
- **Preview > Clear Video** and **Clear Audio** mark everything out of date so
  the next refresh rebuilds all of it. Use these if something looks stale.
- **Project Settings > Preview Size** sets how large the preview frames are.
  Smaller is faster.

The ruler shows which parts are ready.

## 14. In and Out points, and rendering

### In and Out points

Marks limit what you render.

| Key | Action |
|---|---|
| `I` | Set In at the playhead |
| `O` | Set Out at the playhead |
| `Shift+I` / `Shift+O` | Go to In / Out |
| `Alt+X` | Clear In and Out |

The marks look like halves of the playhead handle on the ruler: the In mark's
body extends to the right of its edge and the Out mark's to the left, so together
they bracket the range. **Drag** either one to move it. The
transport bar shows the marked span. The marks are saved with the sequence.

### Rendering

1. Open the sequence you want to export, then choose **File > Render** (or
   **Mark > Render In to Out**).
2. In the Render panel, set:

| Option | What it does |
|---|---|
| Output | The file to write. It defaults to the project's `render` folder (`<project home>/render/<project>_<sequence>_v01.mp4`, counting up); a bare name also lands there. |
| Codec | H.264 or H.265 |
| Output Size | The sequence size, or 1080p, 1440p or 4K UHD. Bitrate follows the size until you change it yourself. |
| Range | **Entire sequence**, or **In to Out** (only when marks are set) |
| Encoder | **Fast (hardware)** uses the Mac's video encoder (VideoToolbox). **High quality (CPU)** uses x264 or x265: slower, and generally better quality at a given bitrate. |
| GOP, Target Mbps, Burst Mbps | Standard encoder tuning |
| Fast start (YouTube) | Puts the index at the front of the file for streaming |
| Audio | Mono or Stereo (stereo is the default) |
| Include captions / Export subtitles as .srt | See [captions](#12-text-and-captions) |

3. Start the render. A progress readout and status line show how it is going.

Speed depends on the source and output size. On the test Mac (an Intel
i7-10700K), a 4K clip at 4K output with the hardware encoder rendered around 19
frames per second; with CPU x264 it was about 10. Your Mac will differ.

Hardware encoding needs a reasonably large frame size. If it can't run at the
chosen size, FLAVE shows a warning and uses the CPU encoder instead.

## 15. Settings

**Settings > Global Settings** (applies to every project):

- Current project folder
- Dark Mode (the theme follows it)
- Footage icon size
- Player controls alignment
- Playhead tick heights
- Preview JPEG quality and Preview Frame Cap
- Undo stack max
- Pixel Snap-To (how close an edge must be to snap)

**Settings > Project Settings** (this project only): Preview Size, and the proxy
folder. Proxy generation is not available on the Mac, so the proxy folder does
nothing in this version.

Where FLAVE keeps its settings: from source, in `globalsettings.db` in the code
folder. In the packaged app, in `~/Library/Application Support/FLAVE for Mac`.

## 16. Keyboard shortcuts

On a Mac, read `Ctrl` as **Command**.

| Key | Action |
|---|---|
| Space | Play / Pause |
| K / L | Pause / Play |
| Left / Right | Previous / next frame |
| Shift+Left / Right | Back / forward ten frames |
| Up / Down | Previous / next edit |
| Home / End | Start / end of sequence |
| + / - | Zoom in / out on the timeline |
| I / O | Set In / Out |
| Shift+I / Shift+O | Go to In / Out |
| Alt+X | Clear In and Out |
| C / V | Enter / leave slice mode |
| Delete | Delete the selected clip |
| Ctrl+C / Ctrl+X / Ctrl+V | Copy / Cut / Paste at the playhead |
| Ctrl+Z / Ctrl+Y | Undo / Redo |
| Ctrl+F | Find in captions |
| F3 / Shift+F3 | Next / previous caption match |
| F5 | Refresh preview |

## 17. Troubleshooting

**Clips show as missing, or nothing plays after moving a project between
computers.** Projects store the full path to each media file. Paths from a
Windows machine, such as `P:/footage/a.mov`, don't exist on a Mac. Right-click the
footage > **Replace**, pick the file in its new place, and accept the offer to
relink the rest. See MACOS-PORT.md.

**Playback is choppy or the preview is blank.** Wait for the preview status line
to finish, or press F5. Lower Project Settings > Preview Size. Close other
heavy apps. Playback decodes video on the CPU, so very large or heavily
compressed sources (for example 4K H.265) are the slowest.

**A frame looks wrong after an edit.** Preview > Clear Video, then F5.

**Hardware render fails or is unavailable.** Switch Encoder to **High quality
(CPU)**.

**FFmpeg not found.** Install it (`brew install ffmpeg`). The packaged app also
looks in the usual Homebrew locations.

**Generate Captions is missing or fails.** Install `faster-whisper`.

**The app asks for approval every time it starts.** The app is ad hoc signed, not
notarized. Right-click > Open once, or approve it under System Settings >
Privacy & Security.

**Something I need isn't here.** Check [MACOS-PORT.md](MACOS-PORT.md) for the
list of features the Mac version lacks (proxy generation, screen capture, the
screenshot button, full-screen player, and others).
