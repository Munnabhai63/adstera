package com.adsterra.phoneagent;

import android.app.Activity;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Simple launcher activity explaining the AccessibilityService rationale and
 * providing buttons to open Accessibility Settings and start the local control service.
 */
public class MainActivity extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(48, 64, 48, 48);

        TextView title = new TextView(this);
        title.setText(R.string.accessibility_rationale_title);
        title.setTextSize(20f);
        layout.addView(title);

        TextView body = new TextView(this);
        body.setText(R.string.accessibility_rationale_body);
        body.setPadding(0, 24, 0, 32);
        layout.addView(body);

        Button accessibilityBtn = new Button(this);
        accessibilityBtn.setText(R.string.btn_open_accessibility_settings);
        accessibilityBtn.setOnClickListener(v ->
                startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        );
        layout.addView(accessibilityBtn);

        Button startServiceBtn = new Button(this);
        startServiceBtn.setText(R.string.btn_start_foreground_service);
        startServiceBtn.setOnClickListener(v -> startLocalForegroundService());
        layout.addView(startServiceBtn);

        setContentView(layout);
    }

    private void startLocalForegroundService() {
        Intent svcIntent = new Intent(this, PhoneAgentForegroundService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(svcIntent);
        } else {
            startService(svcIntent);
        }
    }
}
