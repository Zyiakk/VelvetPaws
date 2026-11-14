"""The cat's sounds (plan Etappe 4): one table for the synthesis, the kit import, BP_VP_Cat and the checks. Plain Python 3.7 (the
editor's Python reads it too), no NumPy. A sound's WAV is assets/sounds/<asset>.wav when that file exists (the user's prepared
recording, scripts/velvetpaws/sound_prep.py), else the synthesis in build/velvetpaws/sound/ (sound_synth.py). Swapping in
recordings: put the prepared files there under the same asset names and rebuild; another number of takes: `variants` below."""
import os
from collections import namedtuple
from velvetpaws import names

RATE = 44100
Sound = namedtuple("Sound", "name variants loop gain att")
# gain: VolumeMultiplier at Volume 100 % (the game's SFX volume comes on top through SoundClass_SFX); att: key of ATTENUATION
SOUNDS = [Sound("Meow", 4, False, 0.9, "Cat"), Sound("Purr", 1, True, 0.55, "Purr"), Sound("Hiss", 1, False, 1.0, "Cat"),
          Sound("Yawn", 1, False, 0.55, "Cat"), Sound("Land", 2, False, 0.45, "Cat")]
PEAK = {"Meow": 0.89, "Purr": 0.7, "Hiss": 0.8, "Yawn": 0.7, "Land": 0.8}     # sample peak of the WAV (synthesis and sound_prep.py)
ATTENUATION = {"Cat": (150.0, 1500.0), "Purr": (40.0, 360.0)}                 # sphere radius, falloff distance (cm)
ATTACH_BONE = "head"                                                          # tools/blender/cat_rig.py
RECORDINGS_REL = os.path.join("assets", "sounds")


def by_name(name): return next(s for s in SOUNDS if s.name == name)


def variants(name): return by_name(name).variants


def gain(name): return by_name(name).gain


def asset(name, i=0): return "S_VP_%s" % name if variants(name) == 1 else "S_VP_%s_%d" % (name, i + 1)


def assets(): return [(asset(s.name, i), s.name, i) for s in SOUNDS for i in range(s.variants)]


def att_asset(kind): return "ATT_VP_" + kind


def path(name, i=0): return names.SOUND + "/" + asset(name, i)


def obj_path(name, i=0): return names.obj(path(name, i))


def source(w, a):
    rec = os.path.join(w, RECORDINGS_REL, a + ".wav")
    return rec if os.path.exists(rec) else os.path.join(names.build_dir(w), "sound", a + ".wav")


def is_recording(w, a): return source(w, a) == os.path.join(w, RECORDINGS_REL, a + ".wav")


def pak_assets():
    return ["Sound/" + a for a, _, _ in assets()] + ["Sound/" + att_asset(k) for k in sorted(ATTENUATION)]
