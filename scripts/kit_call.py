"""Calling Blueprint functions on a class default object from editor Python (shared by the kit tests): call_method treats the
compiler's temporaries of pure nodes (CallFunc_*_ReturnValue) as inputs; call_pure fills them with dummies of their type."""
import re
import unreal

# call_method treats every property of a Blueprint function as an input, also the temporaries the compiler makes for the pure
# nodes inside it (CallFunc_*_ReturnValue: locals, not parameters); a pure function without such locals does not exist. The
# temporaries get a dummy of their type (the function overwrites them before reading them); names and types come from the
# TypeErrors of the Python wrapper and are kept per function.
_TEMPS = {}
_DUMMY = {"FloatProperty": 0.0, "BoolProperty": False, "IntProperty": 0, "StrProperty": "", "NameProperty": "None",
          "Vector": unreal.Vector(0, 0, 0), "Rotator": unreal.Rotator(0, 0, 0), "LinearColor": unreal.LinearColor(0, 0, 0, 0)}


def call_pure(obj, fn, args):
    kw = _TEMPS.setdefault(fn, {})
    for _ in range(400):
        try: return obj.call_method(fn, args, kw)
        except TypeError as e:
            msg = str(e)
            m = re.search(r"required argument '(\w+)' \(pos \d+\) not found", msg)
            if m and m.group(1).startswith("call_func_"): kw[m.group(1)] = 0.0; continue
            m = re.search(r"Failed to convert parameter '(call_func_\w+)'.*?\((\w+Property)\)(?:.*?as '(\w+)')?", msg, re.S)
            want = m and (m.group(3) if m.group(2) == "StructProperty" else m.group(2))
            if not m or want not in _DUMMY or kw.get(m.group(1)) is _DUMMY[want]: raise
            kw[m.group(1)] = _DUMMY[want]
    raise RuntimeError("%s: too many temporaries" % fn)
