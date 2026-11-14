"""Editor script (edtest.sh, in the session of import_cat.py): the cat's sounds (scripts/velvetpaws/sounds.py) as SoundWaves in the
game's SoundClass_SFX (its options menu sets the SFX volume through that class), each with its attenuation asset (ATT_VP_Cat: a small
source heard to about 15 m; ATT_VP_Purr: about 3.6 m); only the purr loops. Source per sound: the prepared recording in assets/sounds/
when there, else the synthesis in build/velvetpaws/sound/. The class is only referenced: a kit without it gets an empty stand-in
(outside /Game/Mod/VelvetPaws, never packed). Everything is read back from the saved assets: EDTEST PASS / EDTEST FAIL."""
import os, sys, wave
import unreal
W = os.environ.get("VELVETPAWS_DEV") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(W, "scripts"))
from velvetpaws import names, sounds as SN
AT = unreal.AssetToolsHelpers.get_asset_tools(); EAL = unreal.EditorAssetLibrary


def fail(msg):
    unreal.log_error("EDTEST FAIL sounds: " + msg); raise SystemExit(1)


def sound_class():
    if not EAL.does_asset_exist(names.SOUND_CLASS_SFX):
        folder, n = names.SOUND_CLASS_SFX.rsplit("/", 1)
        EAL.save_loaded_asset(AT.create_asset(n, folder, unreal.SoundClass, unreal.SoundClassFactory()))
    return unreal.load_asset(names.SOUND_CLASS_SFX)


def attenuation(kind):
    inner, falloff = SN.ATTENUATION[kind]; name = SN.att_asset(kind); path = names.SOUND + "/" + name
    a = unreal.load_asset(path) if EAL.does_asset_exist(path) else AT.create_asset(name, names.SOUND, unreal.SoundAttenuation, unreal.SoundAttenuationFactory())
    s = a.get_editor_property("attenuation")
    s.set_editor_property("attenuate", True); s.set_editor_property("spatialize", True)
    s.set_editor_property("attenuation_shape", unreal.AttenuationShape.SPHERE)
    s.set_editor_property("attenuation_shape_extents", unreal.Vector(inner, 0.0, 0.0))
    s.set_editor_property("falloff_distance", falloff)
    s.set_editor_property("distance_algorithm", unreal.AttenuationDistanceModel.NATURAL_SOUND)
    a.set_editor_property("attenuation", s); EAL.save_loaded_asset(a)
    return a


def seconds(path):
    w = wave.open(path)
    try: return w.getnframes() / float(w.getframerate())
    finally: w.close()


def main():
    sfx = sound_class(); atts = {k: attenuation(k) for k in SN.ATTENUATION}; tasks = []
    for a, _, _ in SN.assets():
        src = SN.source(W, a)
        if not os.path.exists(src): fail("%s: no source %s (did sound_synth.py run?)" % (a, src))
        t = unreal.AssetImportTask()
        for k, v in (("filename", src), ("destination_path", names.SOUND), ("destination_name", a), ("automated", True),
                     ("replace_existing", True), ("save", False)):
            t.set_editor_property(k, v)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    for a, base, _ in SN.assets():
        s = SN.by_name(base); w = unreal.load_asset(names.SOUND + "/" + a)
        if not isinstance(w, unreal.SoundWave): fail("%s imported as %s" % (a, w))
        w.set_editor_property("sound_class_object", sfx); w.set_editor_property("looping", s.loop)
        w.set_editor_property("attenuation_settings", atts[s.att]); EAL.save_loaded_asset(w)
    for a, base, _ in SN.assets():                       # read back what was saved
        s = SN.by_name(base); w = unreal.load_asset(names.SOUND + "/" + a)
        if abs(w.get_editor_property("duration") - seconds(SN.source(W, a))) > 0.02: fail("%s duration %s" % (a, w.get_editor_property("duration")))
        if w.get_editor_property("sound_class_object").get_path_name() != sfx.get_path_name(): fail(a + " class")
        if w.get_editor_property("looping") != s.loop: fail(a + " looping")
        if w.get_editor_property("attenuation_settings").get_path_name() != atts[s.att].get_path_name(): fail(a + " attenuation")
    for k, (inner, falloff) in SN.ATTENUATION.items():
        st = unreal.load_asset(names.SOUND + "/" + SN.att_asset(k)).get_editor_property("attenuation")
        if abs(st.get_editor_property("falloff_distance") - falloff) > 0.01: fail(k + " falloff")
        if abs(st.get_editor_property("attenuation_shape_extents").x - inner) > 0.01: fail(k + " radius")
    rec = [a for a, _, _ in SN.assets() if SN.is_recording(W, a)]
    unreal.log_warning("EDTEST PASS sounds %d (recordings: %s), class %s" % (len(SN.assets()), ",".join(rec) or "none", sfx.get_path_name()))


main()
