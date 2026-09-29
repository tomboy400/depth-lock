package com.tomboy.depthlock;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Handler;
import android.os.Looper;
import android.view.MotionEvent;
import android.view.View;

/** Full-screen overlay: depth wallpaper + live clock. Swipe up dismisses it. */
public class LockView extends View {

    public interface Listener {
        void onDismiss();
    }

    private final Bitmap bg;
    private final Bitmap fg;
    private final Listener listener;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private float downY = -1;
    private float dragDy = 0;
    private boolean dismissing = false;
    private String lastMinute = "";

    private final Runnable ticker = new Runnable() {
        @Override public void run() {
            String m = DepthCompose.timeString(getContext());
            if (!m.equals(lastMinute)) {
                lastMinute = m;
                invalidate();
            }
            handler.postDelayed(this, 5000);
        }
    };

    public LockView(Context c, Bitmap bg, Bitmap fg, Listener listener) {
        super(c);
        this.bg = bg;
        this.fg = fg;
        this.listener = listener;
        setClickable(true);
    }

    @Override protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        lastMinute = "";
        handler.post(ticker);
    }

    @Override protected void onDetachedFromWindow() {
        super.onDetachedFromWindow();
        handler.removeCallbacks(ticker);
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        int w = getWidth(), h = getHeight();
        if (w == 0 || h == 0) return;
        canvas.save();
        canvas.translate(0, dragDy);
        DepthCompose.drawFrame(canvas, bg, fg, w, h,
                DepthCompose.timeString(getContext()), DepthCompose.dateString());
        canvas.restore();
    }

    @Override public boolean onTouchEvent(MotionEvent e) {
        if (dismissing) return true;
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downY = e.getY();
                dragDy = 0;
                return true;
            case MotionEvent.ACTION_MOVE:
                if (downY >= 0) {
                    dragDy = Math.min(0, e.getY() - downY);
                    invalidate();
                }
                return true;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                if (downY >= 0 && dragDy < -getHeight() * 0.12f) {
                    dismiss();
                } else {
                    // spring back
                    ValueAnimator anim = ValueAnimator.ofFloat(dragDy, 0);
                    anim.setDuration(180);
                    anim.addUpdateListener(a -> {
                        dragDy = (float) a.getAnimatedValue();
                        invalidate();
                    });
                    anim.start();
                }
                downY = -1;
                return true;
        }
        return super.onTouchEvent(e);
    }

    private void dismiss() {
        dismissing = true;
        ValueAnimator anim = ValueAnimator.ofFloat(0, 1);
        anim.setDuration(220);
        anim.addUpdateListener(a -> {
            float t = (float) a.getAnimatedValue();
            dragDy = -getHeight() * 0.25f * t;
            setAlpha(1 - t);
            invalidate();
        });
        anim.addListener(new android.animation.AnimatorListenerAdapter() {
            @Override public void onAnimationEnd(android.animation.Animator animation) {
                listener.onDismiss();
            }
        });
        anim.start();
    }
}
