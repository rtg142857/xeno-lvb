#  MIT License
#  
#  Copyright (c) 2023 RoccoDev
#  
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#  
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#  
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.

import struct
import json
import sys
import re
from ext import get_ext_mapper

JSON_INCL_BYTES = False
SPECIAL_MAGIC = [b"INFO", b"XFRM", b"DEBI", b"STRG"]

def ext_import(xc3):
    if xc3:
        # XC3-only modules
        import lvb_xc3_enemy
        pass
    else:
        # XC2-only modules
        pass
    # Common modules
    pass

def u16(data): return struct.unpack('<H', data[0:2])[0]

def u32(data): return struct.unpack('<I', data[0:4])[0]

def f32(data): return struct.unpack('<f', data[0:4])[0]

def u64(data): return struct.unpack('<Q', data[0:8])[0]

def mapper_registry(magic, xc3):
    registry = {
        b"INFO": Info if xc3 else InfoLegacy,
        b"XFRM": Xform,
        b"DEBI": Debug,
        b"STRG": Strings
    }
    test = {}
    ext_import(xc3)

    if magic in registry:
        return registry[magic]
    ext = get_ext_mapper(magic, xc3)
    return ext if ext else Default

class Section():
    def __init__(self, data, xc3, start):
        self._magic = bytes(data[start:start+4])
        mapper = mapper_registry(self._magic, xc3)
        self._size = u32(data[start+4:])
        self._version = u32(data[start+8:])
        count = u32(data[start+12:])
        entry_size = u32(data[start+16:])

        self._info_idx = u32(data[start+20:])
        entry_start = start + 32

        if self._magic != b"STRG":
            self._entries = [Entry(mapper(bytes(data[entry_start + i * entry_size:entry_start + (i + 1) * entry_size]))) for i in range(count)]
        else:
            self._entries = [Entry(mapper(data[entry_start:start + self._size]))]


    def entry(self, i):
        return self._entries[i]

    def size(self):
        return self._size

    def magic(self):
        return self._magic

    def to_json(self):
        return {
            'magic': self._magic.decode('utf-8'),
            'entries': self._entries
        }

class Entry():
    def __init__(self, mapped):
        self._mapped = mapped
        self._info = None
        self._xfrm = None
        self._name = None

    def info(self):
        return self._info

    def xfrm(self):
        return self._xfrm

    def dyn_cast(self):
        return self._mapped

    def to_json(self):
        res = {
            'name': self._name,
            'info': self._info,
            'xform': self._xfrm
        }
        if self._mapped is not None:
            res = dict(res, **self._mapped.to_json())
        return res

# Default sections

# Info table
class Info():
    def __init__(self, entry):
        self.bdat_id = u32(entry)
        self.xfrm_idx = u32(entry[4:])
        self.shape = u16(entry[8:])
        self.sequential_id = u16(entry[10:])
        self.hash_id = u32(entry[12:])

    def to_json(self):
        return {
            'bdat_id': f"{self.bdat_id:08X}",
            'shape': self.shape,
            'sequential_id': self.sequential_id,
            'hash_id': f"{self.hash_id:08X}"
        }

# XC2 info table
class InfoLegacy():
    def __init__(self, entry):
        self.name_id = u32(entry)
        self.xfrm_idx = u32(entry[8:])
        self.shape = u32(entry[12:])

    def to_json(self):
        return { 'shape': self.shape }

# An object's transformation matrix
class Xform():
    def __init__(self, entry):
        # self.matrix = [f32(entry[i:]) for i in range(0, 64, 4)]
        self.matrix = [round(f32(entry[i:]), 2) for i in range(0, 64, 4)]

    def to_json(self):
        return self.matrix

class Strings():
    def __init__(self, entry):
        self._buf = entry

    def read(self, offset):
        data = self._buf[offset:]
        len = data.index(0)
        return data[:len].decode('utf-8')

class Debug():
    def __init__(self, entry):
        # Corresponds to hash_id in Info. Generally it is the murmur3 hash
        # of the gimmick's string name
        self.gimmick_id = u32(entry)
        # Seems to be the same for gimmicks of the same type
        self.type_id = u32(entry[4:])
        self.string_id = u32(entry[8:])
        self.parent_id = u32(entry[12:])

class Default():
    def __init__(self, entry):
        self._data = entry

    def to_json(self):
        if True: #__name__ == "__main__" and JSON_INCL_BYTES:
            return { 'bytes': self._data.hex() }
        return {}

class Lvb():
    def __init__(self, data):
        data = bytes(data)
        assert list(data[0:4]) == [0x4C, 0x56, 0x4C, 0x42]

        file_size = u32(data[4:8])
        self._version = u32(data[8:12])
        xc3 = self._version >= 5
        unk_hash = u32(data[12:16])

        data = data[32:file_size]
        start = 0

        sections = []

        while start < file_size - 32:
            section = Section(data, xc3, start)
            sections.append(section)
            start += section.size()

        info = next(filter(lambda s: s.magic() == b"INFO", sections))
        xfrm = next(filter(lambda s: s.magic() == b"XFRM", sections))
        debi = next(filter(lambda s: s.magic() == b"DEBI", sections), None)
        strings = next(filter(lambda s: s.magic() == b"STRG", sections)).entry(0).dyn_cast()

        gimmick_map = {}
        gimmick_bdat_map = {}

        for sec in sections:
            magic = sec.magic()
            if magic not in SPECIAL_MAGIC:
                base = sec._info_idx
                for i, entry in enumerate(sec._entries):
                    entry._info = info.entry(base + i).dyn_cast()
                    entry._xfrm = xfrm.entry(entry._info.xfrm_idx).dyn_cast()
                    if xc3:
                        gimmick_map[entry._info.hash_id] = entry
                        gimmick_bdat_map[entry._info.bdat_id] = entry
                    else:
                        # XC2
                        name = strings.read(entry._info.name_id)
                        entry._name = name
                        gimmick_map[name] = entry

        # Read debug/unhashed names if present
        if xc3 and debi is not None:
            for entry in debi._entries:
                entry = entry.dyn_cast()
                gimmick = gimmick_map.get(entry.gimmick_id)
                if gimmick is None:
                    continue
                gimmick._name = strings.read(entry.string_id)


        self._gimmick_map = gimmick_map
        self._gimmick_bdat_map = gimmick_bdat_map
        self._sections = list(filter(lambda s: s.magic() not in SPECIAL_MAGIC, sections))

    def section(self, magic):
        return next(filter(lambda s: s.magic() == magic.encode('utf-8'), self._sections), None)

    def gimmick(self, gimmick_id):
        return self._gimmick_map.get(gimmick_id)

    def bdat_gimmick(self, bdat_id):
        return self._gimmick_bdat_map.get(bdat_id)

    def to_json(self):
        return {
            'version': self._version,
            'sections': self._sections
        }

hash_matcher = re.compile(r'^<([0-9A-F]{8})>$')
def name_or_bdat_hash(s):
    m = hash_matcher.match(s)
    if not m:
        return s
    return int(m.group(1), base=16)

if __name__ == "__main__":
    from json import JSONEncoder
    def _default(self, obj):
        return getattr(obj.__class__, "to_json", _default.default)(obj)
    _default.default = JSONEncoder().default
    JSONEncoder.default = _default
    JSON_INCL_BYTES = True

    # Support both XC3 and XC2 for now
    ext_import(True)
    ext_import(False)

    def full(lvb, argv):
        json.dump(lvb, sys.stdout, ensure_ascii=False, indent=1)

    def gimmick(lvb, argv):
        gimmick = lvb.gimmick(name_or_bdat_hash(argv[2]))
        if gimmick is None:
            raise Exception("gimmick not found")
        json.dump(gimmick, sys.stdout, ensure_ascii=False, indent=1)

    def bdat(lvb, argv):
        gimmick = lvb.bdat_gimmick(name_or_bdat_hash(argv[2]))
        if gimmick is None:
            raise Exception("gimmick not found")
        json.dump(gimmick, sys.stdout, ensure_ascii=False, indent=1)

    command = sys.argv[1]
    file_arg, runner = {
        "full": (2, full),
        "gimmick": (3, gimmick),
        "bdat": (3, bdat)
    }[command.lower()]

    file = sys.argv[file_arg]
    file = open(file, "rb")
    data = list(file.read())
    file.close()

    lvb = Lvb(data)
    runner(lvb, sys.argv)
