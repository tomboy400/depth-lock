package com.tomboy.depthlock;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.text.format.DateFormat;

import java.io.File;
import java.util.Calendar;

/** Draws one lockscreen frame: wallpaper, clock, then the subject on top (depth effect). */
public class DepthCompose {

    /** Center-crop matrix mapping a source of (sw,sh) onto a target of (tw,th). */
    public static android.graphics.Matrix centerCropMatrix(int sw, int sh, int tw, int th) {
        float scale = Math.max(tw / (float) sw, th / (float) sh);
        float dx = (tw - sw * scale) / 2f;
        float dy = (th - sh * scale) / 2f;
        android.graphics.Matrix m = new android.graphics.Matrix();
        m.setScale(scale, scale);
        m.postTranslate(dx, dy);
        return m;
    }

    public static Bitmap loadBg(Context c) {
        File f = new File(c.getFilesDir(), Prefs.BG);
        return f.exists() ? BitmapFactory.decodeFile(f.getAbsolutePath()) : null;
    }

    public static Bitmap loadFg(Context c) {
        Prefs prefs = new Prefs(c);
        if (!prefs.depthEnabled()) return null;
        File f = new File(c.getFilesDir(), Prefs.FG);
        return f.exists() ? BitmapFactory.decodeFile(f.getAbsolutePath()) : null;
    }

    public static String timeString(Context c) {
        Calendar cal = Calendar.getInstance();
        boolean is24 = DateFormat.is24HourFormat(c);
        int h = cal.get(Calendar.HOUR_OF_DAY);
        int m = cal.get(Calendar.MINUTE);
        if (is24) return String.format(java.util.Locale.US, "%02d:%02d", h, m);
        int h12 = h % 12 == 0 ? 12 : h % 12;
        return String.format(java.util.Locale.US, "%d:%02d", h12, m);
    }

    public static String dateString() {
        Calendar cal = Calendar.getInstance();
        java.text.SimpleDateFormat f =
                new java.text.SimpleDateFormat("EEEE, d MMMM", java.util.Locale.getDefault());
        return f.format(cal.getTime());
    }

    public static void drawFrame(Canvas canvas, Bitmap bg, Bitmap fg, int w, int h,
                                 String time, String date) {
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

        // 1. background wallpaper
        if (bg != null) {
            canvas.drawBitmap(bg, 0, 0, paint);
        } else {
            canvas.drawColor(0xFF101014);
        }

        // 2. subtle top scrim so the clock reads on bright wallpapers
        Paint scrim = new Paint();
        scrim.setShader(new LinearGradient(0, 0, 0, h * 0.42f,
                0x59000000, 0x00000000, Shader.TileMode.CLAMP));
        canvas.drawRect(0, 0, w, h * 0.42f, scrim);

        paint.setColor(0xFFFFFFFF);
        paint.setTextAlign(Paint.Align.CENTER);

        // 3. date
        paint.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        paint.setTextSize(h * 0.024f);
        paint.setAlpha(230);
        canvas.drawText(date, w / 2f, h * 0.105f, paint);

        // 4. big clock (goes BEHIND the subject)
        paint.setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL));
        paint.setTextSize(w * 0.235f);
        paint.setAlpha(255);
        canvas.drawText(time, w / 2f, h * 0.30f, paint);

        // 5. foreground subject on top -> the depth effect
        if (fg != null) {
            canvas.drawBitmap(fg, 0, 0, null);
        }

        // 6. unlock hint + home indicator
        paint.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        paint.setTextSize(h * 0.019f);
        paint.setAlpha(180);
        canvas.drawText("Swipe up to unlock", w / 2f, h * 0.925f, paint);

        paint.setAlpha(200);
        float bw = w * 0.34f, bh = Math.max(6f, h * 0.006f);
        canvas.drawRoundRect(new RectF(w / 2f - bw / 2f, h - bh * 3f,
                w / 2f + bw / 2f, h - bh * 2f), bh, bh, paint);
    }

    /** Render a preview bitmap for the settings screen. */
    public static Bitmap renderPreview(Context c, Bitmap bg, Bitmap fg, int w, int h) {
        Bitmap out = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(out);
        drawFrame(canvas, bg, fg, w, h, timeString(c), dateString());
        return out;
    }
}
