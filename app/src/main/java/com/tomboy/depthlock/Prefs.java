package com.tomboy.depthlock;

import android.content.Context;
import android.content.SharedPreferences;

public class Prefs {
    private static final String NAME = "depthlock";
    public static final String BG = "bg.jpg";
    public static final String FG = "fg.png";

    private final SharedPreferences p;

    public Prefs(Context c) {
        p = c.getSharedPreferences(NAME, Context.MODE_PRIVATE);
    }

    public boolean hasWallpaper() { return p.getBoolean("has_wallpaper", false); }
    public void setHasWallpaper(boolean v) { p.edit().putBoolean("has_wallpaper", v).apply(); }

    public boolean depthEnabled() { return p.getBoolean("depth", true); }
    public void setDepthEnabled(boolean v) { p.edit().putBoolean("depth", v).apply(); }

    public boolean lockEnabled() { return p.getBoolean("lock", false); }
    public void setLockEnabled(boolean v) { p.edit().putBoolean("lock", v).apply(); }

    public java.io.File file(Context c, String name) {
        return new java.io.File(c.getFilesDir(), name);
    }
}
