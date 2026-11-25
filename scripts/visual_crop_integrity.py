"""Reject persistent black pillarbox strips inside an actual 9:16 source crop.

V5 #106 octopus scene 3 rendered with its right ~half entirely black even
though whole-frame darkness QA passed. Inspect locally decoded source *crop*
before reserving a candidate. This is not a sky/night brightness gate.
"""
from __future__ import annotations


def _edge_stats(frame):
    frame = frame.convert("RGB").resize((96, 168))
    raw = frame.tobytes()
    width, height = frame.size
    stats = []
    for left, right in ((0, width // 4), (width - width // 4, width)):
        dark, total, bright_sum = 0, 0, 0
        for row in range(height):
            for col in range(left, right):
                idx = 3 * (row * width + col)
                rr, gg, bb = raw[idx:idx + 3]
                dark += max(rr, gg, bb) <= 12
                bright_sum += (int(rr) + int(gg) + int(bb)) / 3
                total += 1
        stats.append((dark / total, bright_sum / total))
    return stats


def _white_frame(frame):
    """Detect a baked-in bright rectangular matte, not a bright sky alone."""
    frame=frame.convert("RGB").resize((96,168))
    def white_fraction(rect):
        pixels=list(frame.crop(rect).getdata())
        return sum(min(p)>=238 and max(p)-min(p)<=12 for p in pixels)/len(pixels)
    # A continuous bright border on four edges, but not the image interior.
    edges=[(0,0,6,168),(90,0,96,168),(0,0,96,10),(0,158,96,168)]
    return all(white_fraction(r)>=.94 for r in edges) and white_fraction((24,42,72,126))<.6


def assess_portrait_pillarbox(frames) -> dict:
    """Return FAIL only for a persistent near-black flat side band.

    Two of three cropped source frames must exhibit a near-black >=25%
    vertical side while the OPPOSITE edge clearly contains photographed
    content. Fully dark nighttime shots are *not* pillarboxed by this rule.
    """
    if len(frames) < 3:
        return {"verified": False, "reason": "portrait_crop_frames_missing",
                "black_side_frames": 0}
    white_frames=sum(_white_frame(frame) for frame in frames[:3])
    failures, sides = 0, []
    for frame in frames[:3]:
        left, right = _edge_stats(frame)
        bad_left = left[0] >= .94 and right[1] >= 28
        bad_right = right[0] >= .94 and left[1] >= 28
        if bad_left or bad_right:
            failures += 1
            sides.append("left" if bad_left else "right")
    return {
        "verified": failures < 2 and white_frames < 2,
        "reason": ("persistent_white_picture_frame" if white_frames >= 2 else
                   "portrait_crop_visible" if failures < 2 else "persistent_black_side_pillarbox"),
        "white_frame_count": white_frames,
        "black_side_frames": failures,
        "problem_sides": sides,
        "method": "three_actual_ffmpeg_portrait_crops_edge_content",
        "limitation": "A crop-border heuristic, not an image authenticity test",
    }
