#!/usr/bin/env python3
"""Patch Java class files to work around d8 8.2.2 NPE on MethodParameters
with unnamed (name_index=0) mandated parameters."""
import struct

def _read_cp(data):
    """Parse constant pool. Returns (utf8 dict, offset after pool)."""
    cp_count = struct.unpack('>H', data[8:10])[0]
    utf8 = {}
    pos = 10
    i = 1
    while i < cp_count:
        tag = data[pos]; pos += 1
        if tag == 1:
            ln = struct.unpack('>H', data[pos:pos+2])[0]
            utf8[i] = data[pos+2:pos+2+ln]
            pos += 2 + ln
        elif tag in (7, 8, 16, 19, 20):
            pos += 2
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            pos += 4
        elif tag in (5, 6):
            pos += 8
            i += 1  # long/double take two slots
        elif tag == 15:
            pos += 3
        else:
            raise ValueError(f"unknown cp tag {tag} at index {i}")
        i += 1
    return utf8, pos

def _skip_members(data, p, count):
    for _ in range(count):
        p += 6  # access, name, descriptor
        ac = struct.unpack('>H', data[p:p+2])[0]; p += 2
        for _ in range(ac):
            alen = struct.unpack('>I', data[p+2:p+6])[0]
            p += 6 + alen
    return p

def _filter_attrs(data, p, count, utf8, drop):
    """Filter a run of `count` attributes at offset p. Returns (new_bytes, new_end, changed)."""
    out = bytearray()
    nc = 0
    changed = False
    for _ in range(count):
        ni = struct.unpack('>H', data[p:p+2])[0]
        alen = struct.unpack('>I', data[p+2:p+6])[0]
        blob = data[p:p+6+alen]
        if utf8.get(ni) in drop and _attr_has_unnamed_param(blob):
            changed = True
        else:
            out += blob
            nc += 1
        p += 6 + alen
    return struct.pack('>H', nc) + bytes(out), p, changed

def _attr_has_unnamed_param(blob):
    """Check if a MethodParameters attribute blob has a name_index==0 entry."""
    # blob: name_index(2) + length(4) + parameters_count(1) + entries(4 each)
    if len(blob) < 7:
        return False
    n = blob[6]
    pos = 7
    for _ in range(n):
        if pos + 4 > len(blob):
            return False
        name_idx = struct.unpack('>H', blob[pos:pos+2])[0]
        if name_idx == 0:
            return True
        pos += 4
    return False

def patch_class(data):
    """Remove method-level MethodParameters attributes with unnamed entries.
    Returns patched bytes, or None if no change needed."""
    if data[:4] != b'\xca\xfe\xba\xbe':
        return None
    utf8, p0 = _read_cp(data)
    drop = {b'MethodParameters'}
    # quick check: is there any MethodParameters attr at all?
    if b'MethodParameters' not in utf8.values():
        return None
    out = bytearray(data[:p0])
    p = p0
    # access, this, super
    seg_end = p + 6
    # interfaces
    ic = struct.unpack('>H', data[p+6:p+8])[0]
    seg_end = p + 8 + 2 * ic
    out += data[p:seg_end]
    p = seg_end
    # fields
    fc = struct.unpack('>H', data[p:p+2])[0]
    f_end = _skip_members(data, p + 2, fc)
    out += data[p:f_end]
    p = f_end
    # methods
    mc = struct.unpack('>H', data[p:p+2])[0]
    out += data[p:p+2]
    p += 2
    changed = False
    for _ in range(mc):
        m_head = data[p:p+8]
        ac = struct.unpack('>H', data[p+6:p+8])[0]
        new_attrs, p, c = _filter_attrs(data, p + 8, ac, utf8, drop)
        # detect change: compare attr count
        new_nc = struct.unpack('>H', new_attrs[:2])[0]
        if new_nc != ac:
            changed = True
        out += m_head[:6] + new_attrs
    # class attributes
    ac = struct.unpack('>H', data[p:p+2])[0]
    new_attrs, p, _ = _filter_attrs(data, p + 2, ac, utf8, set())
    out += new_attrs
    out += data[p:]
    return bytes(out) if changed else None

if __name__ == "__main__":
    import sys, zipfile
    path, member = sys.argv[1], sys.argv[2]
    with zipfile.ZipFile(path) as z:
        raw = z.read(member)
    patched = patch_class(raw)
    print("changed:", patched is not None)
    if patched:
        open("/tmp/patched_test.class", "wb").write(patched)
