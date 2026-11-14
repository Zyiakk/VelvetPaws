"""Locomotion of the cat: Stand (breathing, the blend space's speed 0) and the in-place gaits Walk, Trot, Run (Task 3)."""
import cat_motion as M
import cat_poses as P


def _stand(t):
    """The ribcage (spine_02) rises, spine_03 bends back down so the shoulders stay: the fore legs stand almost straight in the rest
    (0.17 cm reach left), a lifted shoulder would lift the fore paws. The head nods 0.8 deg in all."""
    b = M.breath(t, 2.0, 1.0)                      # two breaths in 4 s
    return dict(P.STAND, sp2_p=-1.2 * b, sp3_p=1.5 * b, hd_p=0.5 * b)


STAND = M.Seq("Stand", 120, _stand, loop=True, start="stand", end="stand", group="gait",
              plants={leg: [(0.0, 4.0)] for leg in M.LEGS})

# Phases: hl touches down at 0. harm(phase, amp, n, off) = amp sin(2 pi (n phase - off)): a peak at phase (0.25 + off) / n.
WALK = M.Gait(
    "Walk", 22, speed=40.0, duty=0.62,
    touchdown={"hl": 0.0, "fl": 5 / 22, "hr": 11 / 22, "fr": 16 / 22},     # on frames: no paw grazes the floor between two
    lift={"h": 3.0, "f": 3.5},
    home={"hl": (3.2, -7.0), "hr": (-3.2, -7.0), "fl": (3.0, 14.0), "fr": (-3.0, 14.0)},
    base=dict(P.GAIT, pel_z=-1.0, nk1_p=-8.0, hd_p=6.0, tl_lift=25.0, tl_curl=12.0),
    body={
        "pel_z": (0.35, 2, 0.37),     # hips highest at each hind mid-stance (0.31, 0.81)
        "pel_r": (2.0, 1, 0.56),      # the swinging hind leg's side drops
        "pel_y": (3.5, 1, 0.25),      # the hip of the swinging hind leg comes forward (most at its touchdown)
        "sp1_y": (-1.75, 1, 0.25), "sp2_y": (-1.75, 1, 0.25), "sp3_y": (3.5, 1, 0.48),   # lateral wave: the chest turns with the fore legs
        "sp1_p": (-0.7, 2, 0.83), "sp2_p": (-0.7, 2, 0.83), "sp3_p": (-0.7, 2, 0.83),    # shoulders highest at fore mid-stance
        "sp_r": (2.0, 1, 0.79),       # the swinging fore leg's side drops
        "tl_side": (20.0, 1, 0.33),    # tail against the hips, lagging
    },
    ankle=20.0, wrist=45.0, toe=25.0, tail_wave=(3.0, 1),
    roll={"h": (-10.0, 30.0), "f": (-5.0, 20.0)}, swing_v=(0.3, 0.4), zpeak={"h": 0.4, "f": 0.45},
    tuck_peak={"h": 0.3, "f": 0.4}, shrug=0.6, steady=(0.8, 0.8, 0.8))

TROT = M.Gait(
    "Trot", 14, speed=90.0, duty=0.45,
    touchdown={"hl": 0.0, "fr": 0.0, "hr": 0.5, "fl": 0.5},
    lift={"h": 3.8, "f": 3.8},
    home={"hl": (3.4, -7.0), "hr": (-3.4, -7.0), "fl": (2.8, 14.0), "fr": (-2.8, 14.0)},
    base=dict(P.GAIT, pel_z=-1.2, nk1_p=-5.0, hd_p=5.0, tl_lift=28.0, tl_curl=25.0),
    body={
        "pel_z": (0.7, 2, 0.70),      # the body sinks at mid-stance of each diagonal, rises into the flight
        "pel_r": (1.5, 1, 0.475), "sp_r": (3.0, 1, 0.975),
        "pel_y": (1.5, 1, 0.25), "sp1_y": (-0.75, 1, 0.25), "sp2_y": (-0.75, 1, 0.25), "sp3_y": (1.5, 1, 0.75),
        "tl_side": (5.0, 1, 0.33),
    },
    ankle=25.0, wrist=60.0, toe=30.0, tail_wave=(2.5, 1),
    roll={"h": (-15.0, 35.0), "f": (-5.0, 25.0)}, swing_v=(0.3, 0.4), zpeak={"h": 0.4, "f": 0.45},
    tuck_peak={"h": 0.3, "f": 0.4}, shrug=0.5, steady=(0.9, 0.8, 0.8))

RUN = M.Gait(
    "Run", 10, speed=300.0, duty=0.20,
    touchdown={"hl": 0.00, "hr": 0.10, "fr": 0.34, "fl": 0.46},
    lift={"h": 5.0, "f": 5.0},
    home={"hl": (2.8, -6.8), "hr": (-2.8, -6.8), "fl": (2.5, 14.2), "fr": (-2.5, 14.2)},
    base=dict(P.GAIT, pel_z=-2.5, nk1_p=-6.0, hd_p=6.0, tl_lift=30.0, tl_curl=5.0, earl_p=15.0, earr_p=15.0),
    body={  # gathered (back arched: pelvis tail-down, spine front-down) around 0.83, stretched around 0.33
        "pel_p": (18.0, 1, 0.08), "sp1_p": (10.0, 1, 0.58), "sp2_p": (8.0, 1, 0.58), "sp3_p": (6.0, 1, 0.58),
        "pel_z": (1.0, 1, 0.40),      # hips lowest in the hind stance
        "tl_lift": (-10.0, 1, 0.16),   # the tail balances against the pelvis' pitch
    },
    ankle=40.0, wrist=70.0, toe=35.0,
    roll={"h": (-25.0, 50.0), "f": (-15.0, 40.0)}, swing_v=(0.4, 0.5), zpeak={"h": 0.35, "f": 0.5},
    tuck_peak={"h": 0.3, "f": 0.4}, shrug=0.4, steady=(0.8, 0.5, 0.5))

SEQS = [STAND, WALK, TROT, RUN]
