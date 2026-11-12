package com.adsterra.phoneagent;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.Intent;
import android.graphics.Path;
import android.os.Handler;
import android.os.Looper;
import android.view.accessibility.AccessibilityEvent;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/**
 * AccessibilityService executing OS-level tap and scroll gestures over Chrome
 * via Android's GestureDescription / dispatchGesture API.
 */
public class PhoneAgentAccessibilityService extends AccessibilityService {

    private static volatile PhoneAgentAccessibilityService instance;
    private static final long GESTURE_WAIT_TIMEOUT_MS = 5000L;

    public interface GestureCallback {
        void onResult(boolean completed, String message);
    }

    public static PhoneAgentAccessibilityService getInstance() {
        return instance;
    }

    public static boolean isServiceConnected() {
        return instance != null;
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // Passive observer; gestures are explicitly dispatched by local control commands.
    }

    @Override
    public void onInterrupt() {
        // Required AccessibilityService override.
    }

    @Override
    public boolean onUnbind(Intent intent) {
        instance = null;
        return super.onUnbind(intent);
    }

    @Override
    public void onDestroy() {
        instance = null;
        super.onDestroy();
    }

    public static GestureDescription buildTapGesture(float x, float y, long durationMs) {
        if (x < 0f || y < 0f) {
            throw new IllegalArgumentException("Tap coordinates must be non-negative");
        }
        long clampedDuration = Math.max(1L, durationMs);
        Path path = new Path();
        path.moveTo(x, y);
        GestureDescription.StrokeDescription stroke =
                new GestureDescription.StrokeDescription(path, 0L, clampedDuration);
        return new GestureDescription.Builder()
                .addStroke(stroke)
                .build();
    }

    public static GestureDescription buildSwipeGesture(
            float x1, float y1, float x2, float y2, long durationMs
    ) {
        if (x1 < 0f || y1 < 0f || x2 < 0f || y2 < 0f) {
            throw new IllegalArgumentException("Swipe coordinates must be non-negative");
        }
        long clampedDuration = Math.max(1L, durationMs);
        Path path = new Path();
        path.moveTo(x1, y1);
        path.lineTo(x2, y2);
        GestureDescription.StrokeDescription stroke =
                new GestureDescription.StrokeDescription(path, 0L, clampedDuration);
        return new GestureDescription.Builder()
                .addStroke(stroke)
                .build();
    }

    public void tap(float x, float y, long durationMs, GestureCallback callback) {
        GestureDescription gesture;
        try {
            gesture = buildTapGesture(x, y, durationMs);
        } catch (IllegalArgumentException e) {
            if (callback != null) {
                callback.onResult(false, e.getMessage());
            }
            return;
        }
        dispatchWithCallback(gesture, callback);
    }

    public void swipe(
            float x1, float y1, float x2, float y2, long durationMs, GestureCallback callback
    ) {
        GestureDescription gesture;
        try {
            gesture = buildSwipeGesture(x1, y1, x2, y2, durationMs);
        } catch (IllegalArgumentException e) {
            if (callback != null) {
                callback.onResult(false, e.getMessage());
            }
            return;
        }
        dispatchWithCallback(gesture, callback);
    }

    private void dispatchWithCallback(GestureDescription gesture, GestureCallback callback) {
        Handler mainHandler = new Handler(Looper.getMainLooper());
        boolean accepted = dispatchGesture(
                gesture,
                new GestureResultCallback() {
                    @Override
                    public void onCompleted(GestureDescription gestureDescription) {
                        if (callback != null) {
                            callback.onResult(true, "completed");
                        }
                    }

                    @Override
                    public void onCancelled(GestureDescription gestureDescription) {
                        if (callback != null) {
                            callback.onResult(false, "cancelled");
                        }
                    }
                },
                mainHandler
        );
        if (!accepted && callback != null) {
            callback.onResult(false, "dispatch_rejected");
        }
    }

    public LocalControlServer.GestureResult performTapSync(float x, float y, long durationMs) {
        return awaitGesture(cb -> tap(x, y, durationMs, cb), durationMs);
    }

    public LocalControlServer.GestureResult performSwipeSync(
            float x1, float y1, float x2, float y2, long durationMs
    ) {
        return awaitGesture(cb -> swipe(x1, y1, x2, y2, durationMs, cb), durationMs);
    }

    private interface GestureStarter {
        void start(GestureCallback callback);
    }

    private LocalControlServer.GestureResult awaitGesture(
            GestureStarter starter, long durationMs
    ) {
        CountDownLatch latch = new CountDownLatch(1);
        AtomicBoolean completed = new AtomicBoolean(false);
        AtomicReference<String> msgRef = new AtomicReference<>("timeout");

        starter.start((ok, msg) -> {
            completed.set(ok);
            msgRef.set(msg != null ? msg : (ok ? "completed" : "failed"));
            latch.countDown();
        });

        try {
            long waitMs = Math.max(GESTURE_WAIT_TIMEOUT_MS, durationMs + 2000L);
            boolean finished = latch.await(waitMs, TimeUnit.MILLISECONDS);
            if (!finished) {
                return new LocalControlServer.GestureResult(false, "gesture_timeout");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return new LocalControlServer.GestureResult(false, "interrupted");
        }
        return new LocalControlServer.GestureResult(completed.get(), msgRef.get());
    }
}
