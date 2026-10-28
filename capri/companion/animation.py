"""Continuous frame playback is independent of choosing a different loop."""
import math
from bisect import bisect_right

def timed_frame_index(elapsed, durations_ms, repeat=True):
    """Honor authored hold times; once clips hold their final frame."""
    if not durations_ms or any(not math.isfinite(t) or t<=0 for t in durations_ms):
        raise ValueError('Frame durations must be positive finite milliseconds')
    total=sum(durations_ms)
    milliseconds=max(0.,elapsed)*1000
    if repeat:milliseconds%=total
    elif milliseconds>=total:return len(durations_ms)-1
    ends=[]
    accumulated=0
    for duration in durations_ms:
        accumulated+=duration
        ends.append(accumulated)
    return min(len(durations_ms)-1,bisect_right(ends,milliseconds+1e-6))

def frame_index(elapsed, fps, count):
    if count < 2 or not math.isfinite(fps) or fps <= 0:
        raise ValueError('Animation loops require at least two frames and a positive FPS')
    return math.floor(max(0., elapsed) * fps) % count
