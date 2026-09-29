package com.tomboy.depthlock;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Matrix;
import android.os.Handler;
import android.os.Looper;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.segmentation.subject.SubjectSegmentation;
import com.google.mlkit.vision.segmentation.subject.SubjectSegmenter;
import com.google.mlkit.vision.segmentation.subject.SubjectSegmenterOptions;

import java.io.File;
import java.io.FileOutputStream;

/** Cuts the wallpaper's subject out with ML Kit and caches bg + foreground layers. */
public class Segmenter {

    public interface Callback {
        void onDone(boolean subjectFound);
        void onError(String msg);
    }

    public static void process(Context ctx, Bitmap src, int sw, int sh, Callback cb) {
        Handler main = new Handler(Looper.getMainLooper());
        try {
            // 1. background: center-crop source to screen size
            Bitmap bg = Bitmap.createBitmap(sw, sh, Bitmap.Config.ARGB_8888);
            Canvas c = new Canvas(bg);
            Matrix m = DepthCompose.centerCropMatrix(src.getWidth(), src.getHeight(), sw, sh);
            c.drawBitmap(src, m, null);
            saveJpeg(new File(ctx.getFilesDir(), Prefs.BG), bg, 92);
            bg.recycle();

            // 2. downscaled copy for the segmenter
            int tw = 640;
            int th = Math.max(1, (int) (640f * src.getHeight() / src.getWidth()));
            Bitmap small = Bitmap.createScaledBitmap(src, tw, th, true);

            SubjectSegmenterOptions options = new SubjectSegmenterOptions.Builder()
                    .enableForegroundBitmap()
                    .build();
            SubjectSegmenter segmenter = SubjectSegmentation.getClient(options);
            segmenter.process(InputImage.fromBitmap(small, 0))
                    .addOnSuccessListener(result -> {
                        try {
                            Bitmap fgSmall = result.getForegroundBitmap();
                            File fgFile = new File(ctx.getFilesDir(), Prefs.FG);
                            boolean found = false;
                            if (fgSmall != null) {
                                // scale the cut-out up to screen size with the same
                                // center-crop so it aligns with the background
                                Bitmap fg = Bitmap.createBitmap(sw, sh, Bitmap.Config.ARGB_8888);
                                Canvas fc = new Canvas(fg);
                                Matrix fm = DepthCompose.centerCropMatrix(
                                        fgSmall.getWidth(), fgSmall.getHeight(), sw, sh);
                                fc.drawBitmap(fgSmall, fm, null);
                                savePng(fgFile, fg);
                                fg.recycle();
                                found = true;
                            } else {
                                fgFile.delete();
                            }
                            segmenter.close();
                            boolean f = found;
                            main.post(() -> cb.onDone(f));
                        } catch (Exception e) {
                            segmenter.close();
                            main.post(() -> cb.onError("Couldn't save the cut-out."));
                        }
                    })
                    .addOnFailureListener(e -> {
                        // model download failed / no Play Services: fall back to plain wallpaper
                        new File(ctx.getFilesDir(), Prefs.FG).delete();
                        segmenter.close();
                        main.post(() -> cb.onDone(false));
                    });
        } catch (Exception e) {
            main.post(() -> cb.onError("Couldn't process that image."));
        }
    }

    private static void saveJpeg(File f, Bitmap b, int q) throws Exception {
        FileOutputStream out = new FileOutputStream(f);
        try {
            b.compress(Bitmap.CompressFormat.JPEG, q, out);
        } finally {
            out.close();
        }
    }

    private static void savePng(File f, Bitmap b) throws Exception {
        FileOutputStream out = new FileOutputStream(f);
        try {
            b.compress(Bitmap.CompressFormat.PNG, 100, out);
        } finally {
            out.close();
        }
    }
}
