# Depth Lock

An Android lockscreen app with the iOS-style **depth effect**: your wallpaper's
subject (a person, a pet, anything that stands out) is cut out with on-device AI,
and the big clock renders *behind* it — just like the iPhone lock screen.

**Download the app:** [`DepthLock.apk`](DepthLock.apk) in this repo
(v1.1 debug build — targets **Android 16**, installs on Android 8+;
you may need to allow "install from unknown sources").

## How it works

1. **Pick a wallpaper** in the app. ML Kit's subject segmentation
   (`play-services-mlkit-subject-segmentation`) cuts the subject out and the app
   saves two layers: the full wallpaper and the transparent subject cut-out.
2. A foreground service watches for the screen turning on and shows a
   full-screen overlay (`TYPE_APPLICATION_OVERLAY`) above the system lock screen.
3. The overlay draws wallpaper → clock → subject, so the clock slides behind
   the subject's head. Swipe up to dismiss into your normal lock screen.

One honest note: Android doesn't let any app replace the real PIN/pattern lock,
so this is a visual lockscreen that sits on top of it.

## Project layout

```
app/                        Android app source (no Gradle needed)
  src/main/AndroidManifest.xml
  src/main/java/com/tomboy/depthlock/
    MainActivity.java       settings screen: pick wallpaper, toggles, preview
    Segmenter.java          ML Kit cut-out, caches bg + foreground layers
    DepthCompose.java       draws one lockscreen frame (bg, clock, subject)
    LockView.java           full-screen overlay view, swipe-up to dismiss
    LockService.java        foreground service, shows overlay on screen-on
    Prefs.java              tiny SharedPreferences helper
  src/main/res/             layout, strings, colors, theme
build/
  build.py                  builds the APK with aapt2 + javac + d8 (no Gradle)
  resolve_deps.py           downloads the ML Kit libraries from Maven
  patch_class.py            bytecode tweak so old class files work with d8
DepthLock.apk               ready-to-install debug build (v1.0)
```

## Building it yourself

You need the Android SDK build-tools, platform `android-36`, and JDK 17.
Then:

```bash
cd build
python3 resolve_deps.py deps      # downloads the libraries (~12 MB)
python3 build.py                  # builds out/depthlock-debug.apk
```

The first wallpaper you pick needs internet for a minute — the AI model
downloads once, then everything runs offline.

## Android 16 notes (v1.1)

- `targetSdk 36`, `minSdk 26`
- The lockscreen service is declared as a `specialUse` foreground service
  (with the required subtype property and `FOREGROUND_SERVICE_SPECIAL_USE`
  permission)
- Screen-on receiver is registered `NOT_EXPORTED` on Android 13+
- Settings screen draws edge-to-edge with real system-bar insets
