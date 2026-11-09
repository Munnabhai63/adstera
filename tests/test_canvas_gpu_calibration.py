"""
tests/test_canvas_gpu_calibration.py — Tests for Step 3.5: Canvas Noise Calibration per GPU.
Verifies calibrated LSB steps, stride modulus, and canvas consistency.
"""
import pytest
from pool import Proxy, GeoInfo
import fingerprint as fp_mod


def test_gpu_noise_calibration():
    # Intel Iris Xe
    lsb_intel, stride_intel = fp_mod._calibrate_gpu_noise("ANGLE (Intel, Intel(R) Iris(R) Xe)", False)
    assert lsb_intel == 1
    assert stride_intel == 6

    # NVIDIA GeForce
    lsb_nv, stride_nv = fp_mod._calibrate_gpu_noise("ANGLE (NVIDIA, NVIDIA GeForce RTX 3070)", False)
    assert lsb_nv == 2
    assert stride_nv == 4

    # Mobile Adreno
    lsb_mob, stride_mob = fp_mod._calibrate_gpu_noise("Qualcomm Adreno (TM) 740", True)
    assert lsb_mob == 2
    assert stride_mob == 3


def test_canvas_seed_stability_with_gpu_calibration():
    proxy = Proxy(host="10.0.0.1", port=8080)
    proxy.geo = GeoInfo(country="US", region="NY", city="New York", timezone="America/New_York", locale="en-US")

    fp1 = fp_mod.build(proxy)
    fp2 = fp_mod.build(proxy)
    assert fp1.canvas_seed == fp2.canvas_seed
    assert fp1.webgl_renderer == fp2.webgl_renderer
