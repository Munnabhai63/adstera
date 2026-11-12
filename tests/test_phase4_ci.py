"""
tests/test_phase4_ci.py — Validation tests for Phase 4 Android B1 CI workflow.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "android_b1_ci.yml"
APK_PROJECT_DIR = REPO_ROOT / "phase3" / "b1_android" / "apk"
APP_BUILD_GRADLE = APK_PROJECT_DIR / "app" / "build.gradle"
INSTRUMENTATION_TEST_FILE = (
    APK_PROJECT_DIR
    / "app"
    / "src"
    / "androidTest"
    / "java"
    / "com"
    / "adsterra"
    / "phoneagent"
    / "PhoneAgentInstrumentationTest.java"
)


@pytest.fixture(scope="module")
def workflow_raw() -> str:
    assert WORKFLOW_PATH.is_file(), f"Missing workflow file: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow_data(workflow_raw: str) -> dict:
    loaded = yaml.safe_load(workflow_raw)
    assert isinstance(loaded, dict), "Workflow YAML must parse to a mapping"
    return loaded


def _get_triggers(workflow: dict) -> dict:
    # PyYAML (YAML 1.1) parses unquoted `on:` as boolean True.
    triggers = workflow.get("on") if "on" in workflow else workflow.get(True)
    assert isinstance(triggers, dict), "Workflow must define `on` triggers"
    return triggers


def test_workflow_triggers_and_paths(workflow_data: dict) -> None:
    triggers = _get_triggers(workflow_data)
    assert "push" in triggers
    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers

    for event_name in ("push", "pull_request"):
        paths = triggers[event_name].get("paths", [])
        assert "phase3/b1_android/apk/**" in paths


def test_workflow_env_config_driven(workflow_data: dict) -> None:
    env = workflow_data.get("env")
    assert isinstance(env, dict), "Workflow must define top-level `env:` config"

    expected_env = {
        "APK_PROJECT_DIR": "phase3/b1_android/apk",
        "JAVA_VERSION": "17",
        "GRADLE_VERSION": "8.5",
        "ANDROID_COMPILE_SDK": "34",
        "ANDROID_BUILD_TOOLS": "34.0.0",
        "EMULATOR_API_LEVEL": "34",
        "EMULATOR_TARGET": "google_apis",
        "EMULATOR_ARCH": "x86_64",
        "INSTRUMENTATION_TEST_CLASS": "com.adsterra.phoneagent.PhoneAgentInstrumentationTest",
    }
    for key, val in expected_env.items():
        assert str(env.get(key)) == val, f"env.{key} must equal {val!r}"

    for path_key in (
        "APK_OUTPUT_DIR",
        "RELEASE_APK_UNSIGNED",
        "RELEASE_APK_SIGNED",
        "DEBUG_APK_PATH",
        "ANDROID_TEST_APK_PATH",
        "KEYSTORE_TMP_PATH",
    ):
        assert env.get(path_key), f"env.{path_key} must be configured"

    assert (REPO_ROOT / env["APK_PROJECT_DIR"]).is_dir()
    assert APP_BUILD_GRADLE.is_file()
    gradle_text = APP_BUILD_GRADLE.read_text(encoding="utf-8")
    assert f"compileSdk {env['ANDROID_COMPILE_SDK']}" in gradle_text
    assert f"targetSdk {env['ANDROID_COMPILE_SDK']}" in gradle_text
    assert INSTRUMENTATION_TEST_FILE.is_file()


def test_build_and_sign_apk_job(workflow_data: dict) -> None:
    jobs = workflow_data.get("jobs", {})
    assert "build_and_sign_apk" in jobs
    job = jobs["build_and_sign_apk"]
    assert job.get("runs-on") == "ubuntu-latest"

    steps = job.get("steps", [])
    uses_list = [step.get("uses", "") for step in steps if "uses" in step]
    assert "actions/checkout@v4" in uses_list
    assert "actions/setup-java@v4" in uses_list
    assert "android-actions/setup-android@v3" in uses_list
    assert "gradle/actions/setup-gradle@v4" in uses_list
    assert "actions/upload-artifact@v4" in uses_list

    java_step = next(s for s in steps if s.get("uses") == "actions/setup-java@v4")
    assert java_step["with"]["java-version"] == "${{ env.JAVA_VERSION }}"

    gradle_step = next(s for s in steps if s.get("uses") == "gradle/actions/setup-gradle@v4")
    assert gradle_step["with"]["gradle-version"] == "${{ env.GRADLE_VERSION }}"

    all_runs = "\n".join(s.get("run", "") for s in steps)
    assert "sdkmanager" in all_runs
    assert "platforms;android-${ANDROID_COMPILE_SDK}" in all_runs
    assert "build-tools;${ANDROID_BUILD_TOOLS}" in all_runs
    assert (
        'gradle -p "$APK_PROJECT_DIR" assembleRelease assembleDebug assembleDebugAndroidTest'
        in all_runs
    )


def test_apksigner_secrets_and_cleanup(workflow_data: dict) -> None:
    steps = workflow_data["jobs"]["build_and_sign_apk"]["steps"]

    sign_steps = [
        s for s in steps if "apksigner" in s.get("run", "")
    ]
    assert len(sign_steps) == 1, "Expected exactly one apksigner signing step"
    sign_step = sign_steps[0]

    step_env = sign_step.get("env", {})
    required_secrets = {
        "ANDROID_KEYSTORE_BASE64": "${{ secrets.ANDROID_KEYSTORE_BASE64 }}",
        "ANDROID_KEYSTORE_PASS": "${{ secrets.ANDROID_KEYSTORE_PASS }}",
        "ANDROID_KEY_ALIAS": "${{ secrets.ANDROID_KEY_ALIAS }}",
        "ANDROID_KEY_PASS": "${{ secrets.ANDROID_KEY_PASS }}",
    }
    for env_key, expr in required_secrets.items():
        assert step_env.get(env_key) == expr

    run_script = sign_step["run"]
    assert "base64 --decode" in run_script
    assert "$ANDROID_HOME/build-tools/${ANDROID_BUILD_TOOLS}/apksigner" in run_script
    assert "apksigner\" sign" in run_script
    assert "env:ANDROID_KEYSTORE_PASS" in run_script
    assert "env:ANDROID_KEY_PASS" in run_script
    assert "skipped signing" in run_script.lower()

    cleanup_steps = [
        s
        for s in steps
        if s.get("if") == "always()" and "rm -f" in s.get("run", "") and "KEYSTORE_TMP_PATH" in s.get("run", "")
    ]
    assert len(cleanup_steps) == 1, "Temp keystore must be deleted with `if: always()`"


def test_zero_hardcoded_secrets_or_scattered_paths(workflow_data: dict, workflow_raw: str) -> None:
    assert "BEGIN PRIVATE KEY" not in workflow_raw
    assert "BEGIN RSA PRIVATE KEY" not in workflow_raw
    assert not re.search(r"--ks-pass\s+pass:", workflow_raw)
    assert not re.search(r"--key-pass\s+pass:", workflow_raw)

    jobs_yaml = yaml.safe_dump(workflow_data["jobs"])
    assert "phase3/b1_android/apk" not in jobs_yaml
    assert "com.adsterra.phoneagent.PhoneAgentInstrumentationTest" not in jobs_yaml
    assert "34.0.0" not in jobs_yaml


def test_instrumentation_tests_job(workflow_data: dict) -> None:
    jobs = workflow_data.get("jobs", {})
    assert "instrumentation_tests" in jobs
    job = jobs["instrumentation_tests"]
    assert job.get("runs-on") in ("ubuntu-latest", "macos-latest")

    steps = job.get("steps", [])
    emulator_steps = [
        s for s in steps if s.get("uses") == "reactivecircus/android-emulator-runner@v2"
    ]
    assert len(emulator_steps) == 1
    emu_with = emulator_steps[0].get("with", {})
    assert emu_with.get("api-level") == "${{ env.EMULATOR_API_LEVEL }}"
    assert emu_with.get("target") == "${{ env.EMULATOR_TARGET }}"
    assert emu_with.get("arch") == "${{ env.EMULATOR_ARCH }}"
    assert (
        'gradle -p "$APK_PROJECT_DIR" connectedDebugAndroidTest '
        '-Pandroid.testInstrumentationRunnerArguments.class="$INSTRUMENTATION_TEST_CLASS"'
        in emu_with.get("script", "")
    )
