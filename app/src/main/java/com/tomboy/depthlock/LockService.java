package com.tomboy.depthlock;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.IBinder;
import android.provider.Settings;
import android.view.WindowManager;

/** Foreground service: shows the depth lockscreen overlay whenever the screen turns on. */
public class LockService extends Service {

    private static final int NOTIF_ID = 1;
    private static final String CHANNEL = "depthlock";

    private WindowManager wm;
    private LockView overlay;

    private final BroadcastReceiver screenReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent intent) {
            String a = intent.getAction();
            if (Intent.ACTION_SCREEN_ON.equals(a)) {
                showOverlay();
            } else if (Intent.ACTION_SCREEN_OFF.equals(a)
                    || Intent.ACTION_USER_PRESENT.equals(a)) {
                hideOverlay();
            }
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        IntentFilter f = new IntentFilter();
        f.addAction(Intent.ACTION_SCREEN_ON);
        f.addAction(Intent.ACTION_SCREEN_OFF);
        f.addAction(Intent.ACTION_USER_PRESENT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(screenReceiver, f, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(screenReceiver, f);
        }
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        createChannel();
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(this, CHANNEL)
                .setContentTitle("Depth Lock active")
                .setContentText("Your depth wallpaper shows on the lock screen")
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setContentIntent(pi)
                .setOngoing(true)
                .build();
        startForeground(NOTIF_ID, n);
        return START_STICKY;
    }

    @Override public void onDestroy() {
        super.onDestroy();
        try { unregisterReceiver(screenReceiver); } catch (Exception ignored) {}
        hideOverlay();
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    private void createChannel() {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        NotificationChannel ch = new NotificationChannel(CHANNEL, "Depth Lock",
                NotificationManager.IMPORTANCE_MIN);
        nm.createNotificationChannel(ch);
    }

    private void showOverlay() {
        if (overlay != null) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) return;
        Prefs prefs = new Prefs(this);
        if (!prefs.lockEnabled() || !prefs.hasWallpaper()) return;

        Bitmap bg = DepthCompose.loadBg(this);
        if (bg == null) return;
        Bitmap fg = DepthCompose.loadFg(this);

        LockView view = new LockView(this, bg, fg, this::hideOverlay);
        WindowManager.LayoutParams p = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                        | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED,
                PixelFormat.TRANSLUCENT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            p.layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
        }
        try {
            wm.addView(view, p);
            overlay = view;
        } catch (Exception ignored) {}
    }

    private void hideOverlay() {
        if (overlay != null) {
            try { wm.removeView(overlay); } catch (Exception ignored) {}
            overlay = null;
        }
    }
}
