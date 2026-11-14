"""Byte-stable FBX export from Blender: pin the exporter's timestamp and make its object ids independent of Python's salted hash().
Used by cat_animlib.py (cat_anims.py). The bytes still depend on the absolute path of the opened .blend (the exporter writes
it into the file): fbx_sha1 values hold only for builds from this repo's build/velvetpaws/cat.blend at its current location."""
import datetime, hashlib


def fixed_fbx_time():
    import io_scene_fbx.export_fbx_bin as efb
    import io_scene_fbx.fbx_utils as fu

    class _DT(datetime.datetime):
        @classmethod
        def now(cls, tz=None): return cls(2026, 11, 14, 0, 0, 0)

    class _Mod: datetime = _DT
    efb.datetime = _Mod
    if not getattr(fu, "_vp_stable", False):
        orig = fu._key_to_uuid

        def stable(uuids, key):
            k = key if isinstance(key, int) and 0 <= key < 2 ** 63 else int.from_bytes(hashlib.sha1(repr(key).encode()).digest()[:7], "little")
            return orig(uuids, k)
        fu._key_to_uuid = stable; fu._vp_stable = True
