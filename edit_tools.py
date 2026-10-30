# edit_tools.py
# The Ripple (B), Roll (N) and Slip (Y) tools of the unified window's tool bar
# (timeline_tools.py). They ride on the timeline's own edge-drag machinery
# (sequence_timeline_clips: _edge_drag, _drag_group, _edge_drag_move,
# _edge_drag_release): a press with one of these tools active starts a drag
# there with a "tool" in it, and the saved result is the same kind of change
# a trim makes (start_frame / length_frames / in_frame), in one undo step.
#   Ripple  drag a clip edge: the clip (and its linked clips) is trimmed and
#           everything after it, on every track, moves by the same amount, so
#           no gap opens and none is lost. A left edge keeps the clip's start
#           and changes what it shows (its in-point).
#   Roll    drag the cut between two clips that touch: the first clip's end
#           and the second one's start move together, so the total length
#           does not change. Linked clips roll with it.
#   Slip    drag inside a video or audio clip: the clip keeps its place and
#           length and shows an earlier or later part of its source.
# ASCII only.

TOOL_IDS = ("select", "razor", "ripple", "roll", "slip")
KEYS = (("B", "ripple"), ("N", "roll"), ("Y", "slip"))
STATUS = {
    "ripple": "Ripple: drag a clip edge",
    "roll": "Roll: drag the cut between two clips",
    "slip": "Slip: drag inside a video or audio clip",
}


def current(tl):
    return getattr(tl, "_edit_tool", "select")


def _notify(tl):
    for fn in list(getattr(tl, "_tool_listeners", None) or []):
        try:
            fn()
        except Exception:
            pass


def set_tool(tl, name):
    # Make name the tool. razor is the slice mode (sequence_timeline_slice);
    # every other tool leaves it.
    import sequence_timeline_slice as sl
    if name not in TOOL_IDS or getattr(tl, "_edge_drag", None) is not None:
        return False
    if name == "razor":
        tl._edit_tool = "select"
        sl.enter_slice_mode(tl)
    else:
        sl.exit_slice_mode(tl)
        tl._edit_tool = name
    if name in STATUS:
        try:
            tl.status_bar.showMessage(STATUS[name], 4000)
        except Exception:
            pass
    _notify(tl)
    return True


def reset(tl):
    # Back to Select (V / Esc). True when a tool was active.
    if current(tl) == "select":
        return False
    tl._edit_tool = "select"
    _notify(tl)
    return True


def key_pressed(tl, name):
    from sequence_timeline_slice import text_input_focused
    if text_input_focused(tl):
        return False
    return set_tool(tl, name)


# ---------------------------------------------------------------- press

def _all_clips(tl):
    return [c for clips in tl.clips_by_track.values() for c in clips]


def press(tl, event):
    # A left press with Ripple, Roll or Slip active. True = consumed (a drag
    # may have started in tl._edge_drag).
    from sequence_timeline_clips import _add_source_caps
    tool = current(tl)
    pos = event.position().toPoint()
    if tool == "slip":
        clip = tl._clip_at(pos)
        if clip is None:
            return True
        group = [m for m in tl._drag_group(clip, "slip") if not m["free_in"]]
        _add_source_caps(tl, group)
        if not group or all(m["clip"][0] != clip[0] for m in group):
            tl.status_bar.showMessage("Slip works on video and audio clips", 3000)
            return True
        tl._edge_drag = {
            "clip": clip, "edge": "slip", "tool": "slip", "label": "Slip clip",
            "orig_start": clip[2], "orig_length": clip[3], "orig_in": clip[7],
            "press_frame": tl._frame_at_clips_x(tl._x_in_clips(pos)),
            "snap_px": 0, "group": group}
        return True
    hit = tl._clip_edge_at(pos)
    if hit is None:
        return True
    clip, edge = hit
    if tool == "ripple":
        group = tl._drag_group(clip, edge)
        ids = {m["clip"][0] for m in group}
        e0 = int(clip[2]) + int(clip[3])
        right = [c for c in _all_clips(tl) if c[0] not in ids and int(c[2]) >= e0]
        moving, lowest = ({}, 0)
        if right:
            from sequence_timeline_sql import ripple_moving
            moving, lowest = ripple_moving(tl, right, -10 ** 9, ids)
            moving = dict((k, v) for k, v in moving.items() if k not in ids)
        tl._edge_drag = {
            "clip": clip, "edge": edge, "tool": "ripple", "label": "Ripple trim",
            "orig_start": clip[2], "orig_length": clip[3], "orig_in": clip[7],
            "snap_px": tl._snap_pixels(), "group": group,
            "ripple": {"moving": moving, "min": min(0, lowest),
                       "orig": dict((k, int(v[2])) for k, v in moving.items())}}
        return True
    if tool == "roll":
        pair = _roll_pair(tl, clip, edge)
        if pair is None:
            tl.status_bar.showMessage(
                "Roll needs two clips that touch: drag the cut between them", 3000)
            return True
        a, b = pair
        ga = tl._drag_group(a, "right")
        gb = tl._drag_group(b, "left")
        have = {m["clip"][0] for m in ga}
        gb = [m for m in gb if m["clip"][0] not in have]
        group = ga + gb
        ids = {m["clip"][0] for m in group}
        for m in group:
            c = m["clip"]
            m["prev_end"], m["next_start"] = tl._neighbor_bounds(
                c, c[2], c[3], ignore_ids=ids)
            m["side"] = "a" if m in ga else "b"
        tl._edge_drag = {
            "clip": a, "edge": "roll", "tool": "roll", "label": "Roll edit",
            "orig_start": a[2], "orig_length": a[3], "orig_in": a[7],
            "boundary": int(a[2]) + int(a[3]), "snap_px": 0, "group": group}
        return True
    return True


def _roll_pair(tl, clip, edge):
    # (a, b): the clip ending at the cut and the clip starting there, on the
    # dragged edge's track; None when the edge has no touching neighbour
    track = tl._clip_track_id(clip)
    others = [c for c in tl.clips_by_track.get(track, []) if c[0] != clip[0]]
    if edge == "right":
        end = int(clip[2]) + int(clip[3])
        nxt = [c for c in others if int(c[2]) == end]
        return (clip, nxt[0]) if nxt else None
    prev = [c for c in others if int(c[2]) + int(c[3]) == int(clip[2])]
    return (prev[0], clip) if prev else None


# ---------------------------------------------------------------- move

def _snap(tl, frame):
    try:
        import ruler_grid
        return ruler_grid.snap_frame(tl, frame)[0]
    except Exception:
        return frame


def drag_move(tl, drag, frame):
    # Roll and Slip: frame is the frame under the mouse. Updates the live
    # clips of the group.
    from clip_speed import source_offset
    group = drag["group"]
    if drag["tool"] == "roll":
        delta = _snap(tl, frame) - drag["boundary"]
        lo, hi = -10 ** 9, 10 ** 9
        for m in group:
            start, length, in_f = m["start"], m["length"], m["in"]
            if m["side"] == "a":
                lo = max(lo, 1 - length)
                if m["next_start"] is not None:
                    hi = min(hi, m["next_start"] - (start + length))
                speed = m.get("speed", 100)
                if m.get("src_end") and speed == 100:
                    hi = min(hi, max(0, m["src_end"] - (in_f + length)))
                elif m.get("src_end"):
                    from clip_speed import max_length_for_source
                    hi = min(hi, max(0, max_length_for_source(
                        m["src_end"] - in_f, speed) - length))
            else:
                lo = max(lo, max(0, m["prev_end"]) - start)
                speed = m.get("speed", 100)
                if not m.get("free_in"):
                    lo = max(lo, -in_f if speed == 100 else -((in_f * 100) // speed))
                hi = min(hi, length - 1)
        delta = max(lo, min(hi, delta)) if lo <= hi else 0
        for m in group:
            c = m["clip"]
            if m["side"] == "a":
                c[3] = m["length"] + delta
            else:
                c[2] = m["start"] + delta
                c[3] = m["length"] - delta
                c[7] = m["in"] + source_offset(delta, m.get("speed", 100))
        tl.status_bar.showMessage("Roll %+d frames" % delta)
        return
    # slip
    delta = frame - drag["press_frame"]
    lo, hi = -10 ** 9, 10 ** 9
    from clip_speed import source_span
    for m in group:
        speed = max(1, m.get("speed", 100))
        in_f, length = m["in"], m["length"]
        hi = min(hi, (in_f * 100) // speed)                  # in-point stays >= 0
        if m.get("src_end"):
            over = in_f + source_span(length, speed) - m["src_end"]
            lo = max(lo, -((-over * 100) // speed))          # out stays inside the media
    delta = max(lo, min(hi, delta)) if lo <= hi else 0
    for m in group:
        m["clip"][7] = m["in"] - source_offset(delta, m.get("speed", 100))
    tl.status_bar.showMessage("Slip %+d frames (in-point %d)" % (
        delta, drag["clip"][7]))
    return


def ripple_apply(tl, drag, delta):
    # After a Ripple trim of delta (the group's own change): the clips after
    # it move by the same amount. Returns the allowed delta (the caller has
    # already applied it to the group).
    rp = drag["ripple"]
    d = delta if drag["edge"] == "right" else -delta
    for cid, clip in rp["moving"].items():
        clip[2] = rp["orig"][cid] + d
    return d
