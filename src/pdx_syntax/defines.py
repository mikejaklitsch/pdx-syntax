"""Engine define lookup: vanilla value, mod overrides, and the eu5.exe functions that read each define.

The engine registers every define in a static initializer:
    lea r9, [rip + <value slot in .data>]
    lea r8, [rip + <"DEFINE_NAME" string>]
    jmp <register define>
The index finds that pattern for every name in 00_defines.txt, then finds each
RIP-relative read of the value slot in .text and maps it to its function
through the .pdata unwind table. A function that reads several defines
usually combines them in one formula, so co-read defines are listed together.

The index needs numpy, capstone and pefile. It is cached per exe size and
mtime in ~/.cache/pdx-syntax/, so a game patch rebuilds it once.
"""
import json
import os
import re
from pathlib import Path

GAME_ROOT = Path(os.environ.get(
    "PDX_GAME_ROOT", "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V"))
DEFINES_FILE = GAME_ROOT / "game" / "loading_screen" / "common" / "defines" / "00_defines.txt"
EXE = GAME_ROOT / "binaries" / "eu5.exe"
CACHE_DIR = Path.home() / ".cache" / "pdx-syntax"
INDEX_VERSION = 4

DEFINE_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s*=\s*([^#\n]*?)\s*(?:#\s*(.*))?$")
BLOCK_OPEN = re.compile(r"^\s*(N[A-Za-z0-9_]*)\s*=\s*\{")


def parse_defines(path: Path) -> dict:
    """{NAME: {"ns", "value", "comment", "line"}} from a defines file."""
    out, ns, depth = {}, None, 0
    for i, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
        code = line.split("#", 1)[0]
        m = BLOCK_OPEN.match(code)
        if m and depth == 0:
            ns = m.group(1)
        if depth == 1 and ns:
            d = DEFINE_LINE.match(line)
            if d and "{" not in d.group(2):
                out.setdefault(d.group(1), {"ns": ns, "value": d.group(2), "comment": d.group(3) or "", "line": i})
        depth += code.count("{") - code.count("}")
    return out


def mod_overrides(name: str, start: Path) -> list[tuple[str, int, str]]:
    """Define overrides in the mod that holds start (walks up to loading_screen/common/defines)."""
    for root in [start, *start.parents]:
        d = root / "loading_screen" / "common" / "defines"
        if d.is_dir():
            hits = []
            for f in sorted(d.glob("*.txt")):
                for key, v in parse_defines(f).items():
                    if key == name:
                        hits.append((str(f.relative_to(root)), v["line"], f'{v["ns"]}.{key} = {v["value"]}'))
            return hits
    return []


# ---------------------------------------------------------------- exe index
class _Image:
    def __init__(self, path: Path):
        import numpy as np
        import pefile
        import capstone
        self.np = np
        self.data = path.read_bytes()
        pe = pefile.PE(data=self.data, fast_load=True)
        self.base = pe.OPTIONAL_HEADER.ImageBase
        self.secs = {s.Name.rstrip(b"\0").decode(): s for s in pe.sections}
        t = self.secs[".text"]
        self.text = np.frombuffer(self.data, dtype=np.uint8, count=t.SizeOfRawData, offset=t.PointerToRawData)
        self.text_va = t.VirtualAddress
        p = self.secs[".pdata"]
        pd = np.frombuffer(self.data, dtype=np.uint32, count=p.SizeOfRawData // 12 * 3,
                           offset=p.PointerToRawData).reshape(-1, 3)
        keep = pd[:, 0] > 0
        self.fstart, self.fend = pd[keep, 0].astype(np.int64), pd[keep, 1].astype(np.int64)
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def off(self, rva):
        for s in self.secs.values():
            if s.VirtualAddress <= rva < s.VirtualAddress + s.SizeOfRawData:
                return rva - s.VirtualAddress + s.PointerToRawData
        return None

    def rva(self, off):
        for s in self.secs.values():
            if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
                return off - s.PointerToRawData + s.VirtualAddress
        return None

    def in_section(self, rva, name):
        s = self.secs[name]
        return s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize

    def function_of(self, rva):
        i = int(self.np.searchsorted(self.fstart, rva, side="right")) - 1
        if i >= 0 and self.fstart[i] <= rva < self.fend[i]:
            return int(self.fstart[i]), int(self.fend[i])
        return None

    def rip_target(self, ins):
        m = re.search(r"rip ([+-]) (0x[0-9a-f]+|\d+)\]", ins.op_str)
        if not m:
            return None
        d = int(m.group(2), 0)
        return ins.address - self.base + ins.size + (d if m.group(1) == "+" else -d)

    def insn_at(self, rva):
        o = self.off(rva)
        return next(self.md.disasm(self.data[o:o + 16], self.base + rva, 1), None)

    def disasm(self, start, end):
        o = self.off(start)
        return list(self.md.disasm(self.data[o:o + (end - start)], self.base + start))

    def xrefs(self, targets, imm_sizes=(0, 1, 4)):
        """Verified RIP-relative references: {target: [instruction rva, ...]}."""
        np = self.np
        tset = np.array(sorted(targets), dtype=np.int64)
        cand = []
        n, chunk = len(self.text) - 4, 1 << 24
        for st in range(0, n, chunk):
            en = min(n, st + chunk)
            b = self.text[st:en + 4].astype(np.int64)
            d = b[:-4] | (b[1:-3] << 8) | (b[2:-2] << 16) | (b[3:-1] << 24)
            d = np.where(d >= 1 << 31, d - (1 << 32), d)
            idx = np.arange(st, en, dtype=np.int64)
            for k in imm_sizes:
                tgt = self.text_va + idx + 4 + k + d
                for i in np.nonzero(np.isin(tgt, tset))[0]:
                    cand.append((int(self.text_va + st + i), int(tgt[i]), k))
        out = {}
        for disp_rva, tgt, k in cand:
            # Longest decode first: a shorter one can drop a REX prefix and still hit the target.
            for back in range(11, 0, -1):
                ins = self.insn_at(disp_rva - back)
                if ins and ins.size == back + 4 + k and self.rip_target(ins) == tgt:
                    out.setdefault(tgt, []).append(disp_rva - back)
                    break
        return out


def _strings(img, names):
    """RVAs of each NUL-terminated name in .rdata."""
    s = img.secs[".rdata"]
    blob = img.data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
    want, out = set(names), {}
    for m in re.finditer(rb"(?<=\0)([A-Z][A-Z0-9_]{2,})(?=\0)", blob):
        name = m.group(1).decode()
        if name in want:
            out.setdefault(name, []).append(s.VirtualAddress + m.start(1))
    return out


def build_index(exe: Path = EXE, defines_file: Path = DEFINES_FILE) -> dict:
    img = _Image(exe)
    names = list(parse_defines(defines_file))
    str_rva = _strings(img, names)
    by_str = {r: n for n, rs in str_rva.items() for r in rs}
    slot, reg_funcs = {}, set()
    str_refs = img.xrefs(by_str, imm_sizes=(0,))
    for s_rva, sites in str_refs.items():
        name = by_str[s_rva]
        for site in sites:
            ins = img.insn_at(site)
            if not ins or ins.mnemonic != "lea" or not ins.op_str.startswith("r8,"):
                continue
            # Registration stubs are leaf functions and often have no .pdata entry.
            reg_funcs.add((img.function_of(site) or (site,))[0])
            for prev in img.disasm(site - 0x20, site):
                t = img.rip_target(prev)
                if prev.mnemonic == "lea" and prev.op_str.startswith("r9,") and t and img.in_section(t, ".data"):
                    slot[name] = t
    slot_names = {}
    for name, t in slot.items():
        slot_names.setdefault(t, []).append(name)
    readers = {}
    for t, sites in img.xrefs(slot_names).items():
        for site in sites:
            f = img.function_of(site)
            if not f:
                continue
            for name in slot_names[t]:
                readers.setdefault(name, []).append([site, f[0], f[1]])
    # The registration code and its small helpers (default, copy, reset) sit together in one
    # compiler-generated block; reads there are not game logic.
    import numpy as np
    reg = np.array(sorted(reg_funcs), dtype=np.int64)

    def near_registration(f):
        i = int(np.searchsorted(reg, f))
        return any(0 <= j < len(reg) and abs(int(reg[j]) - f) <= 0x180 for j in (i - 1, i))

    for name in readers:
        readers[name] = sorted(r for r in readers[name] if not near_registration(r[1]))
    readers = {k: v for k, v in readers.items() if v}
    return {"version": INDEX_VERSION, "slots": slot, "readers": readers,
            "unresolved": sorted(set(names) - set(slot))}


def load_index(rebuild: bool = False, exe: Path = EXE) -> dict:
    st = exe.stat()
    cache = CACHE_DIR / f"defines_{st.st_size}_{int(st.st_mtime)}.json"
    if cache.exists() and not rebuild:
        idx = json.loads(cache.read_text())
        if idx.get("version") == INDEX_VERSION:
            return idx
    idx = build_index(exe)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(idx))
    return idx


def co_readers(idx: dict, name: str) -> dict:
    """{function start: {"end", "sites", "others": [defines read by the same function]}}"""
    funcs = {}
    for site, fs, fe in idx["readers"].get(name, []):
        funcs.setdefault(fs, {"end": fe, "sites": [], "others": set()})["sites"].append(site)
    for other, rows in idx["readers"].items():
        if other == name:
            continue
        for _, fs, _ in rows:
            if fs in funcs:
                funcs[fs]["others"].add(other)
    return funcs


def disasm_around(site: int, before: int = 12, after: int = 24, idx: dict | None = None) -> list[str]:
    """Instructions around one read site, with define slots named."""
    img = _Image(EXE)
    names = {}
    if idx:
        for n, t in idx["slots"].items():
            names.setdefault(t, []).append(n)
    f = img.function_of(site)
    insns = img.disasm(f[0], f[1]) if f else img.disasm(site, site + after * 8)
    at = next((i for i, ins in enumerate(insns) if ins.address - img.base == site), 0)
    lines = []
    for ins in insns[max(0, at - before):at + after]:
        rva = ins.address - img.base
        t = img.rip_target(ins)
        note = f"   ; {', '.join(names[t])}" if t in names else ""
        mark = ">>" if rva == site else "  "
        lines.append(f"{mark} {rva:#x}: {ins.mnemonic} {ins.op_str}{note}")
    return lines
