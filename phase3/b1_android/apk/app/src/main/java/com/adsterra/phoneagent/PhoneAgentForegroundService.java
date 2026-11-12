package com.adsterra.phoneagent;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

import java.io.IOException;

/**
 * Foreground service hosting the persistent notification and lifecycle of
 * {@link LocalControlServer} bound to 127.0.0.1.
 */
public class PhoneAgentForegroundService extends Service implements LocalControlServer.CommandHandler {

    public static final String CHANNEL_ID = "phone_agent_control_channel";
    public static final int NOTIFICATION_ID = 1001;
    public static final String EXTRA_LISTEN_PORT = "listen_port";

    private LocalControlServer controlServer;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        startAsForeground();
        startControlServer(LocalControlServer.DEFAULT_PORT);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        int requestedPort = LocalControlServer.DEFAULT_PORT;
        if (intent != null && intent.hasExtra(EXTRA_LISTEN_PORT)) {
            requestedPort = intent.getIntExtra(EXTRA_LISTEN_PORT, LocalControlServer.DEFAULT_PORT);
        }
        if (controlServer == null || !controlServer.isRunning()) {
            startControlServer(requestedPort);
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        stopControlServer();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.fg_channel_name),
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription(getString(R.string.fg_channel_description));
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private void startAsForeground() {
        Notification notification = new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle(getString(R.string.fg_notification_title))
                .setContentText(getString(R.string.fg_notification_text))
                .setSmallIcon(android.R.drawable.ic_menu_compass)
                .setOngoing(true)
                .build();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            );
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
    }

    private synchronized void startControlServer(int port) {
        if (controlServer != null && controlServer.isRunning()) {
            return;
        }
        controlServer = new LocalControlServer(port, this);
        try {
            controlServer.start();
        } catch (IOException e) {
            controlServer = null;
        }
    }

    private synchronized void stopControlServer() {
        if (controlServer != null) {
            controlServer.stop();
            controlServer = null;
        }
    }

    @Override
    public LocalControlServer.StatusResult onStatus() {
        boolean connected = PhoneAgentAccessibilityService.isServiceConnected();
        String details = connected ? "accessibility_ready" : "accessibility_not_enabled";
        return new LocalControlServer.StatusResult(connected, details);
    }

    @Override
    public LocalControlServer.GestureResult onTap(float x, float y, long durationMs) {
        PhoneAgentAccessibilityService svc = PhoneAgentAccessibilityService.getInstance();
        if (svc == null) {
            return new LocalControlServer.GestureResult(false, "accessibility_service_not_connected");
        }
        return svc.performTapSync(x, y, durationMs);
    }

    @Override
    public LocalControlServer.GestureResult onScroll(
            float x1, float y1, float x2, float y2, long durationMs
    ) {
        PhoneAgentAccessibilityService svc = PhoneAgentAccessibilityService.getInstance();
        if (svc == null) {
            return new LocalControlServer.GestureResult(false, "accessibility_service_not_connected");
        }
        return svc.performSwipeSync(x1, y1, x2, y2, durationMs);
    }
}
