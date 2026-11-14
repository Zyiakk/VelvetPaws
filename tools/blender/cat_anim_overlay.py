"""Overlay loop of the cat (Task 7): an additive that only moves the tail (a slow travelling wave and sway) and the ears (twitches
at 1.7 s left, 4.1 s right, 5.2 s a double on the left). Every other channel stays at rest; the kit blends it over any pose.
tl_ph runs 0 -> 2 cycles in 6 s, so the loop closes."""
import math
import cat_motion as M


def _pulse(t, at, width=0.06): return math.exp(-((t - at) / width) ** 2)


def _overlay(t):
    P = M.zero_pose()
    P["tl_wave"] = 5.0; P["tl_ph"] = t / 3.0; P["tl_side"] = M.harm(t / 6.0, 6.0, 2, 0.0)
    l = _pulse(t, 1.7) + _pulse(t, 5.2) + _pulse(t, 5.42); r = _pulse(t, 4.1)
    P["earl_p"], P["earl_y"], P["earr_p"], P["earr_y"] = 15 * l, 10 * l, 15 * r, 10 * r
    return P


OVERLAY = M.Seq("Overlay", 180, _overlay, loop=True, overlay=True, group="overlay")
SEQS = [OVERLAY]
