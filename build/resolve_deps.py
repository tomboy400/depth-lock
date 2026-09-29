#!/usr/bin/env python3
"""Resolve Maven transitive dependencies via POM parsing (no Gradle needed)."""
import os, re, sys, urllib.request, xml.etree.ElementTree as ET

REPOS = [
    "https://dl.google.com/dl/android/maven2",
    "https://repo.maven.apache.org/maven2",
]
NS = {"m": "http://maven.apache.org/POM/4.0.0"}
_cache = {}

def fetch(url):
    if url in _cache:
        return _cache[url]
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            _cache[url] = data
            return data
        except Exception as e:
            last = e
    _cache[url] = None
    print(f"  WARN fetch failed: {url} ({last})", file=sys.stderr)
    return None

def pom_url(g, a, v, repo):
    return f"{repo}/{g.replace('.', '/')}/{a}/{v}/{a}-{v}.pom"

def get_pom(g, a, v):
    for repo in REPOS:
        data = fetch(pom_url(g, a, v, repo))
        if data:
            return data, repo
    return None, None

def text(el, tag):
    c = el.find(f"m:{tag}", NS)
    if c is None:
        c = el.find(tag)
    return c.text.strip() if c is not None and c.text else None

def parse_pom(data):
    root = ET.fromstring(data)
    parent = root.find("m:parent", NS)
    pinfo = {}
    if parent is not None:
        pinfo = {"groupId": text(parent, "groupId"), "artifactId": text(parent, "artifactId"),
                 "version": text(parent, "version")}
    props = {}
    for pe in root.findall("m:properties", NS):
        for child in pe:
            tag = child.tag
            if tag.startswith("{"):
                tag = tag.split("}", 1)[1]
            props[tag] = (child.text or "").strip()
    model = {
        "groupId": text(root, "groupId") or pinfo.get("groupId"),
        "artifactId": text(root, "artifactId"),
        "version": text(root, "version") or pinfo.get("version"),
        "packaging": text(root, "packaging") or "jar",
        "parent": pinfo if parent is not None else None,
        "props": props,
        "depMgmt": {},
        "deps": [],
    }
    for dm in root.findall("m:dependencyManagement/m:dependencies/m:dependency", NS):
        key = (text(dm, "groupId"), text(dm, "artifactId"))
        model["depMgmt"][key] = {
            "version": text(dm, "version"), "scope": text(dm, "scope"),
            "type": text(dm, "type"), "optional": text(dm, "optional") == "true",
        }
    for d in root.findall("m:dependencies/m:dependency", NS):
        model["deps"].append({
            "groupId": text(d, "groupId"), "artifactId": text(d, "artifactId"),
            "version": text(d, "version"), "scope": text(d, "scope"),
            "type": text(d, "type") or "jar",
            "optional": text(d, "optional") == "true",
            "exclusions": {(text(e, "groupId"), text(e, "artifactId"))
                           for e in d.findall("m:exclusions/m:exclusion", NS)},
        })
    return model

PROP_RE = re.compile(r"\$\{([^}]+)\}")

def subst(val, props):
    if not val:
        return val
    def rep(m):
        k = m.group(1)
        return props.get(k, m.group(0))
    for _ in range(5):
        nv = PROP_RE.sub(rep, val)
        if nv == val:
            break
        val = nv
    return val

def merged_model(g, a, v, seen_parents=None):
    """Return (props, depMgmt, deps, packaging) with parent inheritance applied."""
    chain = []
    cg, ca, cv = g, a, v
    seen_parents = seen_parents or set()
    while cg and ca and cv:
        key = (cg, ca, cv)
        if key in seen_parents:
            break
        seen_parents.add(key)
        data, _ = get_pom(cg, ca, cv)
        if not data:
            break
        m = parse_pom(data)
        chain.append(m)
        p = m["parent"]
        if p and p.get("groupId") and p.get("artifactId") and p.get("version"):
            cg, ca, cv = p["groupId"], p["artifactId"], p["version"]
        else:
            break
    props, depMgmt, deps, packaging = {}, {}, [], "jar"
    for m in reversed(chain):  # parent first so child overrides
        props.update(m["props"])
        depMgmt.update(m["depMgmt"])
    top = chain[0] if chain else None
    if top:
        deps = top["deps"]
        packaging = top["packaging"]
    props["project.groupId"] = top["groupId"] if top else g
    props["project.artifactId"] = top["artifactId"] if top else a
    props["project.version"] = top["version"] if top else v
    return props, depMgmt, deps, packaging

def ver_key(v):
    parts = re.split(r"[.\-]", v or "0")
    out = []
    for p in parts:
        out.append((0, int(p)) if p.isdigit() else (1, p))
    return out

def resolve(roots):
    """roots: list of (g, a, v). Returns dict (g,a) -> (v, packaging)."""
    resolved = {}
    queue = [(g, a, v, set()) for g, a, v in roots]
    while queue:
        g, a, v, exclusions = queue.pop(0)
        key = (g, a)
        if key in resolved and ver_key(resolved[key][0]) >= ver_key(v):
            continue
        props, depMgmt, deps, packaging = merged_model(g, a, v)
        if not deps and packaging == "jar" and key not in resolved:
            # couldn't fetch pom; keep requested version
            pass
        if key in resolved and ver_key(resolved[key][0]) >= ver_key(v):
            continue
        resolved[key] = (v, packaging)
        for d in deps:
            dg, da = subst(d["groupId"], props), subst(d["artifactId"], props)
            if not dg or not da or (dg, da) in exclusions or (dg, da) in d["exclusions"]:
                continue
            if d["optional"]:
                continue
            scope = (d["scope"] or "compile").strip()
            if scope not in ("compile", "runtime"):
                continue
            dv = subst(d["version"], props)
            if not dv:
                dm = depMgmt.get((dg, da))
                dv = subst(dm["version"], props) if dm and dm.get("version") else None
            if not dv or "${" in dv or dv.startswith("["):
                print(f"  WARN skipping unresolvable version: {dg}:{da}:{dv}", file=sys.stderr)
                continue
            queue.append((dg, da, dv, exclusions | d["exclusions"]))
    return resolved

def artifact_urls(g, a, v, packaging, repo):
    base = f"{repo}/{g.replace('.', '/')}/{a}/{v}/{a}-{v}"
    urls = []
    if packaging == "aar":
        urls.append(base + ".aar")
    urls.append(base + ".jar")
    return urls

def download(g, a, v, packaging, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    for repo in REPOS:
        for url in artifact_urls(g, a, v, packaging, repo):
            ext = url.rsplit(".", 1)[1]
            dest = os.path.join(dest_dir, f"{g}__{a}__{v}.{ext}")
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                return dest, ext
            data = fetch(url)
            if data and len(data) > 1000:
                with open(dest, "wb") as f:
                    f.write(data)
                return dest, ext
    print(f"  WARN could not download {g}:{a}:{v}", file=sys.stderr)
    return None, None

if __name__ == "__main__":
    roots = [
        ("androidx.appcompat", "appcompat", "1.7.1"),
        ("androidx.coordinatorlayout", "coordinatorlayout", "1.3.0"),
        ("androidx.core", "core-splashscreen", "1.2.0"),
        ("androidx.core", "core", "1.17.0"),
        ("androidx.activity", "activity", "1.11.0"),
        ("androidx.fragment", "fragment", "1.8.9"),
        ("androidx.webkit", "webkit", "1.14.0"),
        ("org.apache.cordova", "framework", "14.0.1"),
    ]
    print("Resolving...")
    resolved = resolve(roots)
    print(f"Resolved {len(resolved)} artifacts:")
    dl_dir = sys.argv[1] if len(sys.argv) > 1 else "deps"
    results = []
    for (g, a), (v, packaging) in sorted(resolved.items()):
        print(f"  {g}:{a}:{v} ({packaging})")
        dest, ext = download(g, a, v, packaging, dl_dir)
        results.append(f"{g}:{a}:{v}:{ext or 'MISSING'}:{dest or ''}")
    with open(os.path.join(dl_dir, "artifacts.txt"), "w") as f:
        f.write("\n".join(results) + "\n")
    print("done ->", dl_dir)
