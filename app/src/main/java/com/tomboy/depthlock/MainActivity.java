package com.tomboy.depthlock;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Display;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;

public class MainActivity extends Activity {

    private static final int PICK_IMAGE = 1001;

    private Prefs prefs;
    private ImageView preview;
    private TextView status;
    private Button btnOverlay;
    private Switch switchDepth;
    private Switch switchLock;
    private int screenW, screenH;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);

        // Edge-to-edge (required look on Android 15+): draw under the system
        // bars and pad the content by the real inset sizes.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            getWindow().setDecorFitsSystemWindows(false);
            getWindow().setStatusBarColor(android.graphics.Color.TRANSPARENT);
            getWindow().setNavigationBarColor(android.graphics.Color.TRANSPARENT);
        }

        setContentView(R.layout.activity_main);
        prefs = new Prefs(this);

        android.widget.ScrollView root = findViewById(R.id.root);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int top, bottom;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                android.graphics.Insets si = insets.getInsets(
                        android.view.WindowInsets.Type.systemBars());
                top = si.top;
                bottom = si.bottom;
            } else {
                top = insets.getSystemWindowInsetTop();
                bottom = insets.getSystemWindowInsetBottom();
            }
            v.setPadding(v.getPaddingLeft(), top, v.getPaddingRight(), bottom);
            return insets;
        });

        // Android 13+: ask to show the service's status notification.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                    != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                requestPermissions(
                        new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 2001);
            }
        }

        Display d = getWindowManager().getDefaultDisplay();
        android.graphics.Point pt = new android.graphics.Point();
        d.getRealSize(pt);
        screenW = pt.x; screenH = pt.y;

        preview = findViewById(R.id.preview);
        status = findViewById(R.id.status);
        btnOverlay = findViewById(R.id.btn_overlay);
        switchDepth = findViewById(R.id.switch_depth);
        switchLock = findViewById(R.id.switch_lock);

        findViewById(R.id.btn_wallpaper).setOnClickListener(v -> pickWallpaper());
        btnOverlay.setOnClickListener(v -> openOverlaySettings());

        switchDepth.setChecked(prefs.depthEnabled());
        switchDepth.setOnCheckedChangeListener((v, checked) -> {
            prefs.setDepthEnabled(checked);
            refreshPreview();
        });

        switchLock.setChecked(prefs.lockEnabled());
        switchLock.setOnCheckedChangeListener((v, checked) -> {
            if (checked && !prefs.hasWallpaper()) {
                Toast.makeText(this, R.string.need_wallpaper, Toast.LENGTH_SHORT).show();
                switchLock.setChecked(false);
                return;
            }
            prefs.setLockEnabled(checked);
            toggleService(checked);
        });

        refreshPreview();
        updateStatus();
    }

    @Override protected void onResume() {
        super.onResume();
        updateOverlayButton();
    }

    private void updateOverlayButton() {
        boolean granted = Build.VERSION.SDK_INT < Build.VERSION_CODES.M
                || Settings.canDrawOverlays(this);
        btnOverlay.setVisibility(granted ? View.GONE : View.VISIBLE);
        findViewById(R.id.overlay_hint).setVisibility(granted ? View.GONE : View.VISIBLE);
    }

    private void openOverlaySettings() {
        Intent i = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + getPackageName()));
        startActivity(i);
    }

    private void pickWallpaper() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.setType("image/*");
        i.addCategory(Intent.CATEGORY_OPENABLE);
        startActivityForResult(i, PICK_IMAGE);
    }

    @Override protected void onActivityResult(int req, int code, Intent data) {
        super.onActivityResult(req, code, data);
        if (req == PICK_IMAGE && code == RESULT_OK && data != null && data.getData() != null) {
            Uri uri = data.getData();
            try {
                getContentResolver().takePersistableUriPermission(uri,
                        Intent.FLAG_GRANT_READ_URI_PERMISSION);
            } catch (Exception ignored) {}
            processWallpaper(uri);
        }
    }

    private void processWallpaper(Uri uri) {
        status.setText(R.string.working);
        new Thread(() -> {
            try {
                Bitmap src = decodeBounded(uri, 2048);
                if (src == null) throw new Exception("decode failed");
                runOnUiThread(() -> Segmenter.process(this, src, screenW, screenH,
                        new Segmenter.Callback() {
                            @Override public void onDone(boolean subjectFound) {
                                prefs.setHasWallpaper(true);
                                refreshPreview();
                                status.setText(subjectFound ? R.string.ready : R.string.no_subject);
                            }
                            @Override public void onError(String msg) {
                                status.setText(msg);
                            }
                        }));
            } catch (Exception e) {
                runOnUiThread(() -> status.setText("Couldn't read that image."));
            }
        }).start();
    }

    private Bitmap decodeBounded(Uri uri, int maxDim) throws Exception {
        InputStream in = getContentResolver().openInputStream(uri);
        BitmapFactory.Options o = new BitmapFactory.Options();
        o.inJustDecodeBounds = true;
        BitmapFactory.decodeStream(in, null, o);
        in.close();
        int scale = 1;
        while (Math.max(o.outWidth, o.outHeight) / scale > maxDim) scale *= 2;
        o.inJustDecodeBounds = false;
        o.inSampleSize = scale;
        in = getContentResolver().openInputStream(uri);
        Bitmap bmp = BitmapFactory.decodeStream(in, null, o);
        in.close();
        return bmp;
    }

    private void refreshPreview() {
        Bitmap bg = DepthCompose.loadBg(this);
        Bitmap fg = DepthCompose.loadFg(this);
        if (bg == null) {
            preview.setImageDrawable(null);
            return;
        }
        int pw = 540, ph = (int) (540f * bg.getHeight() / bg.getWidth());
        // scale the stored screen-size bitmaps down for preview
        Matrix m = new Matrix();
        float s = pw / (float) bg.getWidth();
        m.setScale(s, s);
        Bitmap bgSmall = Bitmap.createBitmap(bg, 0, 0, bg.getWidth(), bg.getHeight(), m, true);
        Bitmap fgSmall = fg == null ? null
                : Bitmap.createBitmap(fg, 0, 0, fg.getWidth(), fg.getHeight(), m, true);
        preview.setImageBitmap(DepthCompose.renderPreview(this, bgSmall, fgSmall, pw, ph));
    }

    private void updateStatus() {
        if (prefs.hasWallpaper()) {
            status.setText(R.string.ready);
        }
    }

    private void toggleService(boolean on) {
        Intent i = new Intent(this, LockService.class);
        if (on) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(i);
            } else {
                startService(i);
            }
        } else {
            stopService(i);
        }
    }
}
