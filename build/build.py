#!/usr/bin/env python3
"""Manual Android APK build without Gradle (aapt2 + javac + d8 + apksigner)."""
import os, re, shutil, subprocess, sys, zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_class import patch_class

HOME = os.path.expanduser("~")
SDK = f"{HOME}/android-build/sdk"
BT = f"{SDK}/build-tools/34.0.0"
AAPT2 = f"{BT}/aapt2"
D8 = f"{BT}/d8"
ZIPALIGN = f"{BT}/zipalign"
APKSIGNER = f"{BT}/apksigner"
JAVAC = f"{HOME}/android-build/jdk17/bin/javac"
KEYTOOL = f"{HOME}/android-build/jdk17/bin/keytool"
ANDROID_JAR = f"{SDK}/platforms/android-36/android.jar"

APP_ID = "com.tomboy.depthlock"
PROJECT = f"{HOME}/workspace/apps/depthlock"
APP = f"{PROJECT}/app"
DEPS = f"{PROJECT}/build/deps"
AARS = f"{PROJECT}/build/aars"
BUILD = f"{PROJECT}/build/out"
OUT_APK = "depthlock-debug.apk"
MIN_SDK = "26"
TARGET_SDK = "33"

ANDROID_NS = "http://schemas.android.com/apk/res/android"
TOOLS_NS = "http://schemas.android.com/tools"
ET.register_namespace("android", ANDROID_NS)
ET.register_namespace("tools", TOOLS_NS)

def run(cmd, **kw):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(r.stdout[-3000:]); print(r.stderr[-3000:])
        raise SystemExit(f"FAILED: {cmd[0]}")
    return r

def localname(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag

# ---------- 0. extract AARs ----------
def extract_aars():
    print("== extracting AARs ==")
    os.makedirs(AARS, exist_ok=True)
    for fn in sorted(os.listdir(DEPS)):
        if not fn.endswith(".aar"):
            continue
        dest = os.path.join(AARS, fn[:-4])
        if os.path.isdir(dest):
            continue
        with zipfile.ZipFile(os.path.join(DEPS, fn)) as z:
            z.extractall(dest)
    print("  aar dirs:", len([d for d in os.listdir(AARS)
                              if os.path.isdir(os.path.join(AARS, d))]))

def aar_dirs():
    return sorted(d for d in os.listdir(AARS)
                  if os.path.isdir(os.path.join(AARS, d)))

# ---------- 1. merge resources ----------
def merge_resources():
    print("== merging resources ==")
    app_res = f"{APP}/src/main/res"
    out = f"{BUILD}/merged_res"
    shutil.rmtree(out, ignore_errors=True)
    conflicts = []
    def copy_tree(src_root, first):
        for root, dirs, files in os.walk(src_root):
            rel = os.path.relpath(root, src_root)
            if rel.split(os.sep)[0] == "values":
                continue  # handled separately
            for fn in files:
                src = os.path.join(root, fn)
                dst = os.path.join(out, rel, fn)
                if os.path.exists(dst):
                    if not first:
                        conflicts.append(os.path.join(rel, fn))
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
    copy_tree(app_res, True)
    for d in aar_dirs():
        r = os.path.join(AARS, d, "res")
        if os.path.isdir(r):
            copy_tree(r, False)
    # merge values XMLs
    values = {}
    order = []
    def merge_values_dir(vdir, first):
        for fn in sorted(os.listdir(vdir)):
            if not fn.endswith(".xml"):
                continue
            path = os.path.join(vdir, fn)
            try:
                tree = ET.parse(path)
            except Exception as e:
                print(f"  WARN parse {path}: {e}")
                continue
            root = tree.getroot()
            if fn not in values:
                values[fn] = {}
                order.append(fn)
            bucket = values[fn]
            for el in list(root):
                tag = localname(el.tag)
                name = el.get("name")
                key = (tag, name)
                if key in bucket:
                    conflicts.append(f"values/{fn}:{tag}/{name}")
                    if first:
                        bucket[key] = el
                else:
                    bucket[key] = el
    vdir = os.path.join(app_res, "values")
    if os.path.isdir(vdir):
        merge_values_dir(vdir, True)
    for d in aar_dirs():
        vdir = os.path.join(AARS, d, "res", "values")
        if os.path.isdir(vdir):
            merge_values_dir(vdir, False)
    for fn in order:
        dst = os.path.join(out, "values", fn)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        root = ET.Element("resources")
        for key in values[fn]:
            root.append(values[fn][key])
        ET.indent(root)
        ET.ElementTree(root).write(dst, encoding="utf-8", xml_declaration=True)
    print(f"  values files: {len(order)}, conflicts: {len(conflicts)}")
    for c in conflicts[:20]:
        print("   conflict:", c)

# ---------- 2. merge manifest ----------
def merge_manifest():
    print("== merging manifest ==")
    src = f"{APP}/src/main/AndroidManifest.xml"
    tree = ET.parse(src)
    root = tree.getroot()
    root.set("package", APP_ID)
    app_el = root.find("application")
    def find_app_child(tag, name_attr):
        for c in app_el:
            if localname(c.tag) == tag and c.get(f"{{{ANDROID_NS}}}name") == name_attr:
                return c
        return None
    for d in aar_dirs():
        mp = os.path.join(AARS, d, "AndroidManifest.xml")
        if not os.path.isfile(mp):
            continue
        try:
            lr = ET.parse(mp).getroot()
        except Exception:
            continue
        for child in list(lr):
            tag = localname(child.tag)
            if tag == "uses-permission" or tag == "permission":
                nm = child.get(f"{{{ANDROID_NS}}}name", "").replace("${applicationId}", APP_ID)
                child.set(f"{{{ANDROID_NS}}}name", nm)
                if not any(localname(c.tag) == tag and c.get(f"{{{ANDROID_NS}}}name") == nm for c in root):
                    root.append(child)
            elif tag == "uses-sdk":
                continue
            elif tag == "application":
                for sub in list(child):
                    stag = localname(sub.tag)
                    sname = sub.get(f"{{{ANDROID_NS}}}name", "")
                    if stag in ("receiver", "service", "activity", "provider"):
                        if find_app_child(stag, sname) is None:
                            app_el.append(ET.fromstring(ET.tostring(sub)))
    xml = ET.tostring(root, encoding="unicode")
    xml = xml.replace("${applicationId}", APP_ID)
    out_dir = f"{BUILD}/merged"
    os.makedirs(out_dir, exist_ok=True)
    with open(f"{out_dir}/AndroidManifest.xml", "w") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n' + xml)
    print("  manifest written")

# ---------- 3. compile + link ----------
def compile_link():
    print("== aapt2 compile/link ==")
    os.makedirs(f"{BUILD}/compiled", exist_ok=True)
    run([AAPT2, "compile", "--dir", f"{BUILD}/merged_res", "-o", f"{BUILD}/compiled/res.zip"])
    pkgs = set()
    for d in aar_dirs():
        mp = os.path.join(AARS, d, "AndroidManifest.xml")
        if os.path.isfile(mp):
            try:
                r = ET.parse(mp).getroot()
                p = r.get("package")
                if p:
                    pkgs.add(p)
            except Exception:
                pass
    pkgs.discard(APP_ID)
    extra = ":".join(sorted(pkgs))
    print("  extra packages:", extra)
    os.makedirs(f"{BUILD}/gen", exist_ok=True)
    cmd = [AAPT2, "link", "-o", f"{BUILD}/base.apk",
           "-I", ANDROID_JAR,
           "--manifest", f"{BUILD}/merged/AndroidManifest.xml",
           "--min-sdk-version", MIN_SDK,
           "--target-sdk-version", TARGET_SDK,
           "--version-code", "1", "--version-name", "1.0",
           "--java", f"{BUILD}/gen",
           "-R", f"{BUILD}/compiled/res.zip",
           "--auto-add-overlay"]
    if extra:
        cmd += ["--extra-packages", extra]
    assets = f"{APP}/src/main/assets"
    if os.path.isdir(assets):
        cmd += ["-A", assets]
    run(cmd)

# ---------- 4. javac ----------
def compile_java():
    print("== javac ==")
    srcs = []
    for root, dirs, files in os.walk(f"{APP}/src/main/java"):
        for fn in files:
            if fn.endswith(".java"):
                srcs.append(os.path.join(root, fn))
    for root, dirs, files in os.walk(f"{BUILD}/gen"):
        for fn in files:
            if fn.endswith(".java"):
                srcs.append(os.path.join(root, fn))
    print(f"  {len(srcs)} java files")
    cp = [ANDROID_JAR]
    for d in aar_dirs():
        cj = os.path.join(AARS, d, "classes.jar")
        if os.path.isfile(cj):
            cp.append(cj)
    for fn in os.listdir(DEPS):
        if fn.endswith(".jar"):
            cp.append(os.path.join(DEPS, fn))
    classes = f"{BUILD}/classes"
    shutil.rmtree(classes, ignore_errors=True)
    os.makedirs(classes)
    args_file = f"{BUILD}/sources.txt"
    with open(args_file, "w") as f:
        f.write("\n".join(srcs))
    run([JAVAC, "-source", "17", "-target", "17", "-nowarn",
         "-cp", ":".join(cp), "-d", classes, "@" + args_file])

# ---------- 5. d8 ----------
def dex():
    print("== d8 ==")
    tree = f"{BUILD}/allclasses"
    shutil.rmtree(tree, ignore_errors=True)
    os.makedirs(tree)
    seen = set()
    patched_count = [0]
    def unzip_dedup(jar):
        with zipfile.ZipFile(jar) as z:
            for n in z.namelist():
                if n.endswith("module-info.class"):
                    continue
                if n.endswith(".class") and n not in seen and not n.startswith("META-INF"):
                    seen.add(n)
                    dst = os.path.join(tree, n)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    data = z.read(n)
                    try:
                        p = patch_class(data)
                        if p is not None:
                            data = p
                            patched_count[0] += 1
                    except Exception:
                        pass
                    with open(dst, "wb") as d:
                        d.write(data)
    for d in aar_dirs():
        cj = os.path.join(AARS, d, "classes.jar")
        if os.path.isfile(cj):
            unzip_dedup(cj)
    for fn in sorted(os.listdir(DEPS)):
        if fn.endswith(".jar"):
            unzip_dedup(os.path.join(DEPS, fn))
    for root, dirs, files in os.walk(f"{BUILD}/classes"):
        for fn in files:
            if fn.endswith(".class"):
                src = os.path.join(root, fn)
                rel = os.path.relpath(src, f"{BUILD}/classes")
                if rel not in seen:
                    seen.add(rel)
                    dst = os.path.join(tree, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
    print(f"  {len(seen)} classes ({patched_count[0]} patched for d8)")
    dexout = f"{BUILD}/dex"
    shutil.rmtree(dexout, ignore_errors=True)
    os.makedirs(dexout)
    alljar = f"{BUILD}/allclasses.jar"
    if os.path.exists(alljar):
        os.remove(alljar)
    run(["bash", "-c", f"cd {tree} && '{HOME}/android-build/jdk17/bin/jar' --create --file {alljar} ."])
    env = dict(os.environ, JAVA_HOME=f"{HOME}/android-build/jdk17",
               PATH=f"{HOME}/android-build/jdk17/bin:" + os.environ.get("PATH", ""))
    run([D8, "--lib", ANDROID_JAR, "--min-api", MIN_SDK, "--output", dexout, alljar], env=env)

# ---------- 6. package, align, sign ----------
def package_sign():
    print("== package/align/sign ==")
    apk = f"{BUILD}/base.apk"
    tmp = apk + ".nodex"
    with zipfile.ZipFile(apk, "r") as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename.endswith(".dex"):
                continue
            zout.writestr(item, zin.read(item.filename))
    os.replace(tmp, apk)
    with zipfile.ZipFile(apk, "a", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(f"{BUILD}/dex")):
            if fn.endswith(".dex"):
                z.write(os.path.join(f"{BUILD}/dex", fn), fn)
    ks = f"{BUILD}/debug.keystore"
    if not os.path.isfile(ks):
        run([KEYTOOL, "-genkeypair", "-keystore", ks, "-alias", "androiddebugkey",
             "-storepass", "android", "-keypass", "android", "-keyalg", "RSA",
             "-keysize", "2048", "-validity", "10950",
             "-dname", "CN=Android Debug,O=Android,C=US"])
    aligned = f"{BUILD}/depthlock-aligned.apk"
    if os.path.exists(aligned):
        os.remove(aligned)
    env = dict(os.environ, JAVA_HOME=f"{HOME}/android-build/jdk17",
               PATH=f"{HOME}/android-build/jdk17/bin:" + os.environ.get("PATH", ""))
    run([ZIPALIGN, "-f", "4", apk, aligned], env=env)
    out = f"{BUILD}/{OUT_APK}"
    if os.path.exists(out):
        os.remove(out)
    run([APKSIGNER, "sign", "--ks", ks, "--ks-pass", "pass:android",
         "--key-pass", "pass:android", "--out", out, aligned], env=env)
    r = run([APKSIGNER, "verify", "--print-certs", out], env=env)
    print(r.stdout[:300])
    sz = os.path.getsize(out)
    print(f"  APK ready: {out} ({sz/1024/1024:.1f} MB)")

if __name__ == "__main__":
    os.makedirs(BUILD, exist_ok=True)
    extract_aars()
    merge_resources()
    merge_manifest()
    compile_link()
    compile_java()
    dex()
    package_sign()
    print("BUILD SUCCESS")
