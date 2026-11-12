package com.adsterra.phoneagent;

import android.accessibilityservice.GestureDescription;
import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

/**
 * Instrumentation smoke tests verifying manifest service registration,
 * AccessibilityService gesture construction, and LocalControlServer command parsing.
 */
@RunWith(AndroidJUnit4.class)
public class PhoneAgentInstrumentationTest {

    @Test
    public void testServicesRegisteredInManifest() throws Exception {
        Context appContext = InstrumentationRegistry.getInstrumentation().getTargetContext();
        PackageManager pm = appContext.getPackageManager();
        PackageInfo pkg = pm.getPackageInfo(
                appContext.getPackageName(),
                PackageManager.GET_SERVICES
        );

        assertNotNull("Package services must be present", pkg.services);
        boolean foundAccessibility = false;
        boolean foundForeground = false;
        for (ServiceInfo info : pkg.services) {
            if (PhoneAgentAccessibilityService.class.getName().equals(info.name)) {
                foundAccessibility = true;
                assertEquals(
                        "android.permission.BIND_ACCESSIBILITY_SERVICE",
                        info.permission
                );
            } else if (PhoneAgentForegroundService.class.getName().equals(info.name)) {
                foundForeground = true;
            }
        }
        assertTrue("PhoneAgentAccessibilityService must be registered", foundAccessibility);
        assertTrue("PhoneAgentForegroundService must be registered", foundForeground);
    }

    @Test
    public void testGestureBuilders() {
        GestureDescription tapGesture =
                PhoneAgentAccessibilityService.buildTapGesture(320f, 640f, 85L);
        assertNotNull(tapGesture);
        assertEquals(1, tapGesture.getStrokeCount());
        assertEquals(85L, tapGesture.getStroke(0).getDuration());

        GestureDescription swipeGesture =
                PhoneAgentAccessibilityService.buildSwipeGesture(400f, 1200f, 400f, 350f, 420L);
        assertNotNull(swipeGesture);
        assertEquals(1, swipeGesture.getStrokeCount());
        assertEquals(420L, swipeGesture.getStroke(0).getDuration());
    }

    @Test
    public void testLocalControlCommandParsing() {
        LocalControlServer.ParsedCommand pingCmd =
                LocalControlServer.parseCommand("{\"cmd\":\"ping\"}");
        assertTrue(pingCmd.isValid());
        assertEquals("ping", pingCmd.cmd);

        LocalControlServer.ParsedCommand statusCmd =
                LocalControlServer.parseCommand("{\"cmd\":\"status\"}");
        assertTrue(statusCmd.isValid());
        assertEquals("status", statusCmd.cmd);

        LocalControlServer.ParsedCommand tapCmd =
                LocalControlServer.parseCommand("{\"cmd\":\"tap\",\"x\":540,\"y\":960,\"duration_ms\":95}");
        assertTrue(tapCmd.isValid());
        assertEquals("tap", tapCmd.cmd);
        assertEquals(540f, tapCmd.x, 0.01f);
        assertEquals(960f, tapCmd.y, 0.01f);
        assertEquals(95L, tapCmd.durationMs);

        LocalControlServer.ParsedCommand scrollCmd = LocalControlServer.parseCommand(
                "{\"cmd\":\"scroll\",\"x1\":300,\"y1\":1100,\"x2\":300,\"y2\":400,\"duration_ms\":450}"
        );
        assertTrue(scrollCmd.isValid());
        assertEquals("scroll", scrollCmd.cmd);
        assertEquals(450L, scrollCmd.durationMs);

        LocalControlServer.ParsedCommand invalidCmd =
                LocalControlServer.parseCommand("{\"cmd\":\"tap\"}");
        assertFalse(invalidCmd.isValid());
    }
}
