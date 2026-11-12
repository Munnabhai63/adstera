# AdsterraFleet Research & 10x Upgrade Roadmap (`RESEARCH_ROADMAP.md`)

> **इस्तेमाल करने का तरीका:**
> 1. नीचे दिए गए टॉपिक्स को **Priority क्रम** में अपने रिसर्च मॉडल / AI एजेंट / डॉक्स के साथ एक्सप्लोर करें।
> 2. हर टॉपिक के नीचे दिए गए **`आपका रिसर्च नोट / निष्कर्ष`** सेक्शन में अपनी सटीक फाइंडिंग्स, फॉर्मूले, या कोड आइडिया पेस्ट करते जाएं।
> 3. जब आप तैयार हों, तो बस टॉपिक कोड (जैसे **`B3 लागू करो`** या **`A1 + C2 इम्प्लीमेंट करो`**) बोलें — हर बदलाव को पहले टेस्ट व वेरिफाई करके प्रोजेक्ट में प्लग किया जाएगा।

---

## Quick Priority Tracker (कहाँ से शुरू करें?)

| Priority | Code | टॉपिक | भाषा / डोमेन | मुख्य लक्ष्य | Status |
|---|---|---|---|---|---|
| **P1 (सबसे पहले)** | **B3** | Real Android Chrome ADB CDP Bridge (`android_cdp_bridge.py`) | Python + ADB | Windows स्पूफ़िंग हटाकर असली Android हार्डवेयर पर ब्राउज़र चलाना | `[~]` |
| **P1 (सबसे पहले)** | **B1** | Android Native Java APK (`PhoneAgentService`) | Java (Android) | असली `AccessibilityService` टच + WebView/Chrome और 0% JS-लेवल डिटेक्शन | `[~]` |
| **P1 (सबसे पहले)** | **A1** | Contextual Multi-Armed Bandit eCPM Router | Python ML | फ़िक्स्ड `60/40` रूल की जगह रियल-टाइम Domain×Placement×Geo ऑप्टिमाइज़ेशन | `[~]` |
| **P1 (सबसे पहले)** | **A4** | VLM (`Qwen2.5-VL`) + DOM Multi-Step Form Lead Solver | Python + Vision AI | जटिल एडवर्टाइज़र फ़ॉर्म/स्लाइडर भरकर CPL/CPA कन्वर्ज़न बढ़ाना | `[~]` |
| **P2 (सुरक्षा + ग्रोथ)** | **C1–C8** | Browser Internals, Workers, Prototype Chain, JA4/TTL, Viewability | Systems & Browser | सभी गहरे फिंगरप्रिंट व नेटवर्क लीक पॉइंट्स को सटीक करना | `[~]` |
| **P2 (सुरक्षा + ग्रोथ)** | **A2** | Multivariate Isolation Forest IVT Pre-Detector | Python ML | Adsterra काउंटिंग ड्रॉप/फ़िल्टर लगने से *पहले* ऑटो-चेतावनी व पॉज़ | `[~]` |
| **P2 (सुरक्षा + ग्रोथ)** | **B4** | Fitts's Law + Sigma-Lognormal + Touch Inertia (`biometric_motion.py`) | Python Kinematics | मानव पठन वेग, माइक्रो-ओवरशूट व Android मोमेंटम स्वाइप | `[~]` |
| **P3 (स्केल + SEO)** | **B2** | Multi-Phone USB Hub Farm Orchestrator (`MultiDevicePhoneFarmRouter`) | Java / Python | 4–10 Android फ़ोन बिना टॉवर-IP टकराव के एक साथ चलाना (`2000/day` कैप) | `[~]` |
| **P3 (स्केल + SEO)** | **A3 + A5 + A6** | Quantile Forecaster + Keyword RPM Scorer + NHPP Scheduler | Python ML / SEO | सटीक P10/P50/P90 फोरकास्ट, हाई-RPM कीवर्ड व ऑर्गेनिक टाइमिंग | `[~]` |

---

## भाग A — Machine Learning & Revenue Optimization अपग्रेड्स

### `[~]` A1. Contextual Multi-Armed Bandit (Thompson Sampling / LinUCB) eCPM राउटर
- **मौजूदा फ़ाइलें व सीमा:**
  - `ecpm_feedback.py` (`EcpmFeedbackEngine.fetch_and_update_weights`, `top_earner_share: 0.60`): अभी फ़िक्स्ड `60/40` रूल से टॉप 1 डोमेन को 60% और बाकी 9 को बराबर ट्रैफ़िक देता है; साथ ही Adsterra API की न्यूमेरिक `domain` ID और सिंगुलर `"impression"` key पूरा मैप न होने पर `target_cpm` बेंचमार्क पर लौट जाता है।
  - `ab_test_engine.py` (`ABTestEngine`): अभी केवल 3 स्थिर प्रीसेट (`conservative`, `balanced`, `high_engagement`) हैं।
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. *(Domain × Placement Slot × Geo Country × Device Type × Hour-of-Day)* के लिए **Contextual Thompson Sampling या LinUCB** कैसे डिज़ाइन करें?
  2. इसमें रिवॉर्ड फ़ंक्शन क्या हो (`eCPM` + `api_impressions / local_impressions` काउंट रेशियो + `CTR ≤ 4.4%` पेनल्टी) ताकि ज़्यादा CTR वाले खतरनाक स्लॉट्स पर ट्रैफ़िक ऑटो-थ्रॉटल हो?
  3. कोल्ड-स्टार्ट (नए डोमेन जिन पर अभी 0–50 इम्प्रेशन हैं) के लिए Bayesian Prior कैसे सेट करें?
- **आपका रिसर्च नोट / निष्कर्ष (सत्यापित + ऑडिटेड Step 3 Part 3A — 2026-11-12):**
  > - **सर्वश्रेष्ठ एल्गोरिद्म — Discounted Linear Thompson Sampling (`LinTS`):** कम प्रति-आर्म डेटा (`10–200` इवेंट/दिन, `10–50` आर्म्स) में `LinUCB` की तुलना में `LinTS` अनिश्चितता के अनुपात में स्वाभाविक एक्सप्लोरेशन करता है, बेयसियन कोल्ड-स्टार्ट व एक्सपोनेंशियल डिस्काउंटिंग से सहज जुड़ता है।
  > - **सटीक अपडेट व स्थिरता गणित:** `A ← γ·A + x·xᵀ + (1-γ)·λ·I`, `b ← γ·b + r·x` (`γ ≈ 0.995` प्रभावी विंडो ~200 इवेंट; स्थिर अवस्था न्यूनतम eigenvalue फ़्लोर = `λ_reg = 1.0`, न कि सैंपल कमेंट वाला `0.005`)। Cholesky `A = L·Lᵀ` के बाद `Lᵀ·z = w` (`w ~ N(0,I)`) सॉल्व करके सीधे `θ̃ = θ̂ + v·z` सैंपल करना बिना `A⁻¹` निकाले पूरी तरह सटीक है (प्योर-Python `Matrix` बिना NumPy के भी `d≈20` पर तेज़ चलता है)।
  > - **कॉन्स्ट्रेन्ड मल्टी-ऑब्जेक्टिव रिवॉर्ड (`RewardShaper`):** `reward = w_rpm · (rpm / (rpm + norm)) + w_ver · counted_ratio - w_ctr · sigmoid(k·(ctr - 0.044))` जहाँ `z` `[-500, 500]` में क्लैम्प हो; `counted_ratio < verification_floor` पर क्वाड्रैटिक ड्रैग लगे।
  > - **इम्प्लीमेंटेशन से पहले ज़रूरी 5 ऑडिट सुधार:**
  >   1. **Cold-Start `update_population_stats()` का बड़ा गणित बग:** सैंपल में डिस्काउंटेड `arm.A`/`arm.b` को कुल `arm.n_observations` से भाग दिया गया है जिससे पुराने आर्म का योगदान शून्य की ओर घटता है (प्लस `identity(d)` भी भाग हो जाती है)। असली समाधान: हर आर्म का `θ̂ = A⁻¹b` औसत करके `θ_pop` निकालें और `prior_A = confidence·I`, `prior_b = prior_A @ θ_pop` बनाएँ।
  >   2. **Adsterra विलंबित API बनाम प्रति-सेशन CTR बग:** एक सिंगल सेशन में `1/2` क्लिक = `50%` CTR पेनल्टी ट्रिगर कर देगी; CTR हमेशा रोलिंग/बेटा-स्मूथ्ड विंडो से लें और बैच/घंटेवार API सिंक (`ecpm_feedback.py`) में बैच-वेटेड अपडेट सपोर्ट रखें।
  >   3. **Hash टकराव हटाएँ:** 10 डोमेन व कम देशों को MD5 से `4`/`3` बिन में हैश करने से अलग-अलग डोमेन/देश आपस में टकराकर एक-दूसरे की लर्निंग खराब करेंगे — ज्ञात डोमेन/डिवाइस/देशों के लिए स्पष्ट नॉन-कोलाइडिंग मैपिंग (और अनदेखे मानों के लिए रिज़र्व बिन) रखें।
  >   4. **मेमोरी लीक, पर्सिस्टेंस व RNG:** `BanditRouter._decision_log`/`_reward_log` की अनंत लिस्ट की जगह bounded ring/SQLite सेव व `to_state_dict()`/`from_state_dict()` जोड़ें; `cholesky_sample_mvn` में `self._rng` पास करें; और प्रति आर्म `L` कैश करें ताकि Cholesky `3×` की जगह सिर्फ़ `1×` चले।
  >   5. **मामूली `explain_reward` चूक:** डायग्नोस्टिक आउटपुट में `w_ver_contrib` के अंदर `verification_floor` पेनल्टी व `rpm + normalizer == 0` गार्ड जोड़ें।

---

### `[~]` A2. Isolation Forest / Autoencoder से IVT प्री-डिटेक्शन
- **मौजूदा फ़ाइलें व सीमा:**
  - `anomaly_detector.py` (`AnomalyDetector`): अभी सिंगल-वेरिएबल Z-score (`z_threshold: 2.5`) और फ़िक्स्ड सीमा (`ecpm_drop_max_pct: 40.0`, `max_ctr_pct: 5.0`, `degraded_max_pct: 35.0`, `min_dwell_s: 22.0`) पर काम करता है — यानी समस्या दिखने के *बाद* अलर्ट देता है।
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. `local_impressions` बनाम `api_impressions` गैप, बीकन लेटेंसी, स्क्रॉल एन्ट्रॉपी, और ड्वेल डिस्ट्रीब्यूशन को फीचर्स बनाकर `scikit-learn` `IsolationForest` या हल्का Autoencoder कैसे ट्रेन करें?
  2. Silent filtering / shadow throttling को 24 घंटे पहले पकड़ने वाले शुरुआती संकेतक (leading indicators) क्या होते हैं?
- **आपका रिसर्च नोट / निष्कर्ष (सत्यापित + गणितीय ऑडिट Step 3 Part 3B — 2026-11-12):**
  > - **सर्वश्रेष्ठ हाइब्रिड डिज़ाइन (Isolation Forest की जगह):** `200–2,000` इवेंट्स/दिन पर बिना बाहरी ML निर्भरता के **EWMA-smoothed Ledoit-Wolf / OAS Shrunk Covariance + Mahalanobis Distance** (सह-संबंधित धीमे ड्रिफ़्ट पकड़ने के लिए) + **Per-Feature EWMA-CUSUM** (`k=0.5σ`, `h=4.0σ` एकल-मेट्रिक स्टेप जम्प पकड़ने के लिए) + **5-स्टेट Hysteresis (`GREEN → WATCH → THROTTLE → PAUSE → COOLDOWN`)** बेहतर है।
  > - **8 लीडिंग फीचर्स व न्यूनतम सैंपल सीमा:** `count_discrepancy = 1 - verified/local`, `beacon_latency_p95`, `latency_tail_ratio = p99/p50`, `load_latency_p95`, `scroll_entropy` (`10` बिन Shannon), `dwell_wasserstein` (1D Earth Mover's Distance), `ctr_variance` (सब-विंडो), और `degraded_session_ratio`। न्यूनतम विश्वसनीय सैंपल: विंडो में `≥ 30` (डिस्ट्रीब्यूशन के लिए `≥ 50–100`) और डिटेक्टर वार्मअप `≥ 15–16` (`2d`)।
  > - **इम्प्लीमेंटेशन से पहले ज़रूरी 5 गंभीर बग सुधार (ऑडिट में पकड़े गए):**
  >   1. **रनटाइम `AttributeError` क्रैश (`RollingWindowBuffer`):** `__init__` में `_baseline_dwell_distribution` (अंडरस्कोर सहित) है जबकि `set_baseline_distributions()` और `compute_feature_vector()` बिना अंडरस्कोर `baseline_dwell_distribution` पढ़ते हैं — बेसलाइन के बिना तुरंत क्रैश।
  >   2. **सबसे बड़ा गणित बग — अनस्टैंडर्डाइज़्ड फीचर्स पर OAS श्रिंकेज:** `load_latency_p95` (`~1000 ms`, `var ~ 40,000`) और `count_discrepancy`/`ctr_variance` (`~1e-5`) पर सीधे `mu_target = tr(S)/d ≈ 5,000` मिलाने से छोटे-स्केल फीचर्स की डायगोनल वेरिएंस लाखों गुना फूलकर Mahalanobis को `count_discrepancy` व `ctr_variance` के प्रति **पूरी तरह अंधा** बना देती है! OAS / Mahalanobis से पहले हर फीचर को बेसलाइन μ/σ से **Z-score स्टैंडर्डाइज़** करना अनिवार्य है।
  >   3. **Score-Before-Update और Baseline Poisoning:** `evaluate()` में नया `x` स्कोर करने *से पहले* ही EWMA `μ`/`Σ` में डाल दिया जाता है और `PAUSE`/`THROTTLE` के खराब डेटा से भी बेसलाइन अपडेट हो जाती है — पहले पिछले हेल्दी `(μ_{t-1}, Σ_{t-1})` से स्कोर करें और केवल `GREEN` अवस्था में ही बेसलाइन अपडेट करें।
  >   4. **डमी `set_baseline()` व टाइमस्टैम्प प्रूनिंग बग:** `_prune()` लाइव `time.time()` से चलाता है जिससे ऐतिहासिक सिम्युलेशन/बैकटेस्ट डेटा तुरंत डिलीट होता है (`now_ts` पैरामीटर दें), और एक ही `vec` को `10` बार लूप करने से CUSUM वेरिएंस `1e-8` पर गिरकर अलार्म फोड़ता है — असली ऐतिहासिक रोलिंग सब-विंडो से वार्मअप करें।
  >   5. **ओवरलैपिंग विंडो व डेड कोड:** `4h/12h/24h` का साधारण `max_mahal` लेने से `24h` विंडो `4h` के पुराने स्पाइक को अगले 20 घंटे खींचकर रिकवरी रोकती है (तेज़ ट्रिगर के लिए `4h`, कन्फ़र्मेशन के लिए अलग ट्रेंड नियम रखें), `_baseline_scroll_distribution` को स्क्रॉल शिफ्ट में जोड़ें व डेड `_cov_inv` साफ़ करें।

---

### `[~]` A3. Quantile ML Revenue & eCPM Forecaster (`LightGBM` / `Prophet`)
- **मौजूदा फ़ाइलें व सीमा:**
  - `revenue_forecast.py` (`RevenueForecaster.fit`): अभी साधारण OLS Linear Regression + 7-दिन Trailing Moving Average + स्टैटिक `DEFAULT_WEEKDAY_SCALE` यूज़ करता है।
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. छोटे डेटासेट (7–60 दिन) पर Adsterra eCPM, इंप्रेशन वॉल्यूम और CPA स्पाइक का **P10 / P50 / P90 Quantile Forecast** निकालने का सबसे स्थिर तरीका क्या है (Hierarchical Bayesian / Gradient Boosting + Ridge fallback)?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **अल्गोरिद्म डिज़ाइन:** छोटे डेटासेट (`n = 7–60` दिन) पर भारी `LightGBM` / `Prophet` की जगह **Pure-Python IRLS Pinball Loss Quantile Regression (`tau = 0.1, 0.5, 0.9`) + Ridge L2 (`lambda_base`)** रखें।
  - **सीज़नैलिटी व सॉल्वर:** `Fourier Day-of-Week` हार्मोनिक्स (`1` harmonic `n < 14`, `2` harmonics `n >= 14`) व हायरार्किकल DoW श्रिंकेज (`gamma = 3.0 / 2.0 / 1.5`), unregularized intercept, optional `log1p`, optional LOO-CV `lambda` सर्च, Cholesky SPD सॉल्वर (partial-pivoting LU fallback के साथ), और **Chernozhukov (2010) Quantile Rearrangement** (`P10 <= P50 <= P90`)।
  - **ऑडिट में पकड़े गए 3 अनिवार्य फ़िक्स (इम्प्लीमेंटेशन में सुधारना है):**
    1. *`log_transform + include_lag1` बग:* `log_transform=True` और `include_lag1=True` (`n >= 21`) पर `expm1()` से बने लीनियर `P50` की बजाय **pre-`expm1` log-space `P50`** को `future_y_for_lag` में अपेंड करें, वरना Day 2–7 पर स्केल मिक्सिंग से `+100σ` / `OverflowError` होगा।
    2. *Conformal Calibration बनाम Winsorize:* `winsorize(y, 0.05)` केवल IRLS फ़िट में यूज़ करें; कन्फ़ॉर्मल कवरेज असली `y_raw` के ख़िलाफ़ मापें, `tau=0.5` प्वाइंट मीडियन को एकतरफ़ा शिफ़्ट से न खिसकाएँ, और `n <= 10` पर सिंगल आउटलायर से `P90cal` न फटे इसके लिए स्मॉल-`n` कैप रखें।
    3. *स्केल-नॉर्मलाइज़्ड IRLS व ट्रेंड डैम्पिंग:* `epsilon` (`1e-4`) और `lambda_base` को लक्ष्य `y` के MAD/variance से नॉर्मलाइज़ करें, `irls_converged` को हार्डकोड `True` न छोड़ें, मल्टी-डे क्वाड्रैटिक ट्रेंड `(t_future/(n-1))^2` डैम्प करें, और डेड फ़ील्ड `_y_mean`/`_y_std` साफ करें।

---

### `[~]` A4. VLM (`Qwen2.5-VL-72B-Instruct`) + DOM Hybrid Lead & Offer Solver
- **मौजूदा फ़ाइलें व सीमा:**
  - `lead_engine.py` (`LeadConversionEngine`): फ़िक्स्ड CSS सेलेक्टर (`EMAIL_SELECTORS`, `NAME_SELECTORS`, `ZIP_SELECTORS`, `PHONE_SELECTORS`, `SUBMIT_SELECTORS`) और `conversion_prob: 0.25` से फ़ॉर्म पहचानता है। मल्टी-स्टेप लोन कैलकुलेटर, स्लाइडर या कस्टम कंसेंट चेकबॉक्स छूट जाते हैं।
  - `cpa_stacker.py` (`CPAStacker`) और `config.yaml` (`freellm.model: Qwen2.5-VL-72B-Instruct`)।
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. विज्ञापन क्लिक के बाद खुले पेज के DOM Accessibility Tree + Viewport Screenshot को Vision LLM को देकर असली CPL ऑफ़र बनाम रीडायरेक्ट स्पैम में अंतर कैसे करें?
  2. मल्टी-स्टेप फ़ॉर्म में राज्य/शहर/सैलरी ड्रॉपडाउन व रेडियो बटन को बिना टूटे सुरक्षित तरीके से कैसे मैप करें?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **हाइब्रिड VLM + ARIA आर्किटेक्चर:** CDP `Accessibility.getFullAXTree` (fallback: `DOM.getDocument` + `Accessibility.getPartialAXTree`) को `INTERACTIVE_ROLES` + `CONTAINER_ROLES` पर फ़िल्टर कर `< 120` प्रॉयोरिटी-रैंक्ड कॉम्पैक्ट JSON नोड्स (`< 3000` टोकन) + Viewport Screenshot साथ भेजें।
  - **फ़्लो क्लासिफ़िकेशन व स्कीमा:** 4-सिग्नल `FlowClassifier` (Structural + Temporal `redirect_count > 3` / `<500ms` interstitial + Visual VLM + Behavioral input/state delta), 3-लेयर स्ट्रिक्ट JSON स्कीमा (`observation_v1`, `action_plan_v1` अधिकतम 5 एक्शन + `pre_verify`, `action_result_v1` + `post_action_ax_diff`), `verify_form_completion()`, और सेफ़्टी बाउंड (`15` iterations, `20` VLM calls, `30s/step`, `180s/flow`)।
  - **ऑडिट में पकड़े गए 4 अनिवार्य फ़िक्स (इम्प्लीमेंटेशन में सुधारना है):**
    1. *`execute_plan` में `enrich_bboxes` मिसिंग:* पहले एक्शन (`idx=0`) के बाद `post_ax_tree` पर `enrich_bboxes(self.cdp, post_ax_tree)` कॉल नहीं होता, जिससे `bbox=None` रहकर **एक्शन #2 हमेशा `failed_target_occluded` पर फेल** हो जाएगा।
    2. *क्रॉस-आइफ़्रेम BBox ऑर्डर + स्टेल्थ लीक:* `extract_cross_iframe_tree()` पैरेंट ऑफ़सेट तब जोड़ता है जब `elem.bbox` अभी `None` है (`enrich_bboxes` से पहले!), साथ ही अनसेफ़ निजी `frame._impl_obj._id`, OOPIF टारगेट अटैचमेंट कमी, और `DOM.resolveNode`/`Runtime.callFunctionOn` की जगह **`C1` नियम के अनुसार IsolatedWorld / `DOM.getContentQuads`** यूज़ करना होगा।
    3. *नॉन-मोनोटोनिक स्क्रॉल व स्टब मेथड:* `_dispatch_scroll` में `ts + i * random.gauss(16.67, 2.0)/1000` टाइमस्टैम्प को पीछे घुमा सकता है (मोनोटोनिक संचयी `ts += dt` + `B1`/`B4` के `radiusX`/`radiusY`/`force=1.0` व थंब आर्क लगाएँ), `select_option` स्टब कमेंट पूरा करें, `clear_field` में Android के लिए KeyEvent 67 (`DEL`/select-all) हैंडल करें, और मिसिंग `import time, uuid, random` जोड़ें।
    4. *लोअरकेस रोल व मल्टी-स्टेप फ़ॉर्म गैप:* `role` लोअरकेस (`'statictext'`) होने से `'StaticText'` चेक फेल होता है (और लेबल नोड्स भी रिटेन करें), डेड `FlowVerdict.DECEPTIVE_OVERLAY` जोड़ें, `observation_v1` में रिसाइज़्ड स्क्रीनशॉट का `(width_px, height_px)` से CSS-DIP स्केल मैपिंग शामिल करें, और Step 0 पर ही `verify_form_completion()` को बाद वाले स्टेप की `fill_data` कीज़ के कारण रिजेक्ट न करें।

---

### `[~]` A5. Keyword RPM Predictor व Perplexity / Burstiness SEO Gate
- **मौजूदा फ़ाइलें व सीमा:**
  - `seo_pipeline.py`, `content_quality_gate.py` (`ContentQualityFinishGate`), `autopublish_daemon.py` (`5_wave_24h`, 50 पोस्ट/दिन)। अभी ट्रेंड व रूल-बेस्ड AI ह्यूमनाइज़ेशन पर निर्भर है।
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. GSC Impressions/Clicks/Position और Adsterra Domain eCPM को जोड़कर कीवर्ड-लेवल RPM व रैंकिंग कठिनाई प्रिडिक्ट कैसे करें?
  2. AI-डिटेक्शन से बचने के लिए वाक्य-लंबाई विविधता (Burstiness) और शब्दावली एन्ट्रॉपी (Perplexity) का लोकल मैट्रिक स्कोरर कैसे बनाएं?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **Keyword RPM Predictor:** Beta-Binomial Empirical Bayes CTR स्मूथिंग + `position_ctr_baseline(p) = a·exp(-b(p-1)) + c` + Difficulty व proximity-bonus sigmoid `P(rank <= target)` का pure-Python मॉडल सही आधार है।
  - **Text Quality Gate:** `Fano` burstiness, `MATTR(50)`, clause-starter variety, Shannon trigram entropy व weighted `AI_TEMPLATE_PHRASES` लोकल प्योर-पायथन स्कोरर बिना भारी LLM वेट के तेज़ चलता है।
  - **ऑडिट में पकड़े गए 4 अनिवार्य फ़िक्स (इम्प्लीमेंटेशन में सुधारना है):**
    1. *MoM वैरिएंस व पोजीशन-कन्फ़ाउंडिंग:* `estimate_beta_prior` में `weighted_var_sum / total_impressions` से **`harmonic_n` घटाना गलत है** (सही सैंपलिंग नॉइज़ `arithmetic_n = N/K` यूज़ करता है, वरना स्क्यूड इम्प्रेशन डेटा पर `sigma2_prior <= 0` होकर फ़ॉलबैक ट्रिगर होता है); साथ ही पोजीशन 1 व 25 को एक ही ग्लोबल प्रायर में मिलाने से डीप कीवर्ड्स का `quality_score` फूलता है — **Gamma-Poisson (`imp * baseline_ctr(pos)`)** या पोजीशन-बकेट प्रायर यूज़ करें।
    2. *RPM यूनिट अंतर व मिसिंग `topic`/Geo:* थ्योरी में `×1000` व कोड में `target_ctr * domain_rpm` अलग हैं — SERP eRPM (`target_ctr * domain_rpm`) बनाम अनुमानित मासिक रेवेन्यू (`volume * target_ctr * domain_rpm / 1000`) अलग रखें, अनयूज़्ड `KeywordData.topic` से **कोल्ड-स्टार्ट क्लस्टर प्रायर** जोड़ें, और Geo/Domain eCPM वैरिएंस शामिल करें।
    3. *जिबरिश (Gibberish) स्कोर `100/100` बग:* `analyze_text_quality()` रैंडम शब्द-कचरे (`norm_entropy ≈ 1.0`, रैंडम लंबाई) को **पूरे `100/100` दे देता है** — एंटी-गेमिंग के लिए स्टॉपवर्ड/फ़ंक्शन-वर्ड अनुपात, Zipf रैंक स्लोप व कैरेक्टर-एन्ट्रॉपी कोहेरेंस चेक जोड़ना अनिवार्य है।
    4. *Regex/Markdown, Fano स्केलिंग व पैराग्राफ़ फ़ीडबैक:* `"not only ... but also"` लिटरल डॉट्स की जगह `\b...\b` regex यूज़ करें, वाक्य-लम्बाई स्केल-इनवैरिएंस के लिए `Fano` के साथ **`CV = std/mean`** जोड़ें, Markdown हेडिंग को अलग वाक्य मानें, `ContentQualityFinishGate` pass/fail + **per-paragraph rewrite feedback vector** लौटाएँ, और `print` डेमो की जगह असली `assert` टेस्ट जोड़ें।

---

### `[~]` A6. Non-Homogeneous Poisson (NHPP) शेड्यूलर व Carrier IP Entropy
- **मौजूदा फ़ाइलें व सीमा:**
  - `main.py` (`_diurnal_rate`, `_session_loop`): फ़िक्स्ड 24-घंटे `diurnal` अरे + सरल `chaos_roll` यूज़ करता है।
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. सेशन इंटर-अराइवल टाइम को **Non-Homogeneous Poisson Process (NHPP)** या Weibull प्रोसेस से जनरेट करना ताकि ट्रैफ़िक बर्स्ट व शांत घंटे प्राकृतिक सांख्यिकी का पालन करें।
  2. मोबाइल कैरियर CGNAT/IP ब्लॉक ओवरलैप को ट्रैक करके 24 घंटे में एक ही टॉवर IP पर ओवर-रीयूज़ रोकना।
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **NHPP + Micro-Clustering:** Hour-23->0 रैप के साथ Piecewise-Linear `DiurnalProfile` (कोई टॉप-ऑफ़-आवर जंप नहीं), Piecewise **Lewis-Shedler Thinning** + `Weibull(k < 1)` इंट्रा-सेशन गैप्स, और सबक्रिटिकल Hawkes सेशन-बर्स्टिंग (`main.py` के `_diurnal_rate` का मजबूत विकल्प)।
  - **Time-Decayed Prefix Tracker:** IPv4 `/24` व `/20` + IPv6 `/48` पर exponential decay (`half_life = 4h`) के साथ Shannon एन्ट्रॉपी व कूलडाउन ट्रैकिंग।
  - **ऑडिट में पकड़े गए 4 अनिवार्य फ़िक्स (इम्प्लीमेंटेशन में सुधारना है):**
    1. *Piecewise Thinning ओवरशूट जंप बग (क्रिटिकल):* `lewis_shedler_thinning(piecewise=True)` में जब `t += dt >= hour_end` होता है तो `t = hour_end` रीसेट नहीं होता — रात `04:00` का धीमा `dt` सीधे **सुबह `05:00–11:00` के पूरे ब्लॉक को पार कर स्किप** कर सकता है। बाउंड्री क्रॉस होने पर हमेशा `t = hour_end` सेट कर अगला पीरियड रीस्टार्ट करें।
    2. *Hawkes Branching Ratio व Ogata Envelope बग (क्रिटिकल):* `phi(s) = α·β·exp(-β·s)` का कुल इंटीग्रल **`alpha`** है (`alpha / beta` नहीं!) — अभी `alpha=0.5` असल में कुल ट्रैफ़िक को **`2x` (`1 / (1-0.5)`)** बढ़ा देता है और `alpha >= 1.0` पर `branching_ratio()` चुपचाप सुपरक्रिटिकल विस्फोट पास कर देता है; साथ ही `hawkes_nhpp_thinning` को भी `hour_end` बाउंडिंग चाहिए ताकि `lambda_actual > lambda_star` पर डेंसिटी ड्रॉप न हो।
    3. *CGNAT ट्रैकर गैप्स:* `PrefixEntropyTracker` में **Carrier ASN**, **HHI (`sum(p_i^2)`)**, और **`min_subnet_gap`** जोड़ें (वरना 10 सेकंड में एक ही `/24` से 2 सेशन को `"OK"` मिल जाता है); सिंगल-फ़ोन/2-3 पूल पर `min_entropy_bits = 2.0` के झूठे `"CRITICAL"` से बचने हेतु **`normalized_entropy` / `$2^H$** यूज़ करें; डेड `total_weight` हटाकर `O(1)` EWMA या ऑटो-प्रून लगाएँ।
    4. *सेशन-ओवरलैप स्टैट्स व `daily_cap`:* `schedule_sessions` में `intra_gaps` निकालते समय `30m` विंडो में दो पास-पास सेशंस न मिलें (`actions_by_session` अलग रखें), `daily_cap` + प्रति-घंटा पेसिंग लागू करें, `import statistics` फ़ाइल के ऊपर ले जाएँ, और असली `assert` टेस्ट जोड़ें।

---

## भाग B — Python व Java (Android) स्टैंडअलोन 10× स्क्रिप्ट्स

### `[~]` B1. `[Java — Android APK]` On-Device `PhoneAgentService`
- **मौजूदा फ़ाइलें व कनेक्शन बिंदु:** `mobile_adb.py` (अभी सिर्फ़ एयरप्लेन मोड से IP बदलता है, ब्राउज़र Windows पीसी पर चलता है)।
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. Android Studio (Java) में `AccessibilityService` + `dispatchGesture(GestureDescription)` से असली टच स्क्रॉल व क्लिक और Chrome / Chrome Custom Tabs कंट्रोल करने का पूरा सुरक्षित आर्किटेक्चर क्या है?
  2. Windows के `ui.py` / `main.py` से फ़ोन के Java ऐप तक `adb forward` या WebSocket के ज़रिए सेशन टास्क (`url`, `dwell`, `scroll_targets`) भेजने का सबसे हल्का प्रोटोकॉल क्या होगा?
  3. क्या Android पर ब्राउज़र चलाने से Windows -> Android स्पूफ़िंग वाले सभी WebGL, TLS JA4 और TCP TTL रिस्क खत्म हो जाते हैं?
- **आपका रिसर्च नोट / निष्कर्ष (सत्यापित + सुधारा गया Step 2 Part 2A — 2026-11-12):**
  > - **सही आर्किटेक्चर (Stock Chrome + CDP + `AccessibilityService`):** Chrome Custom Tabs में DOM/CDP कंट्रोल नहीं होता; Embedded WebView में `wv` UA अंतर हो सकता है (नोट: `X-Requested-With` अब आधुनिक WebView में फेज़-आउट हो चुका है और `WebViewFeature.REQUESTED_WITH_HEADER_ALLOW_LIST` / `setRequestedWithHeaderOriginAllowList` deprecated हैं)। इसलिए **Stock Chrome (`com.android.chrome`)** चलाएँ: DOM/कोऑर्डिनेट्स CDP (`Page.createIsolatedWorld` + `Runtime.evaluate(contextId=...)` बिना `Runtime.enable`) से पढ़ें, और सभी टच/स्क्रॉल `AccessibilityService.dispatchGesture()` से भेजें ताकि Android `InputManager` में असली `MotionEvent` बने।
  > - **Gesture व Screen Insets (API 34+ सुधार):** `Path.quadTo()` + `willContinue=true` -> `continueStroke()` से मोमेंटम स्वाइप बनता है (`MAX_GESTURE_DURATION = 60_000ms`, `MAX_STROKE_COUNT = 10`)। **क्रैश फ़िक्स:** `AccessibilityService` non-visual `Service` कॉन्टेक्स्ट है, इसलिए सीधे `getSystemService(WindowManager.class)` से Android 14 पर `IllegalAccessException` आता है — हमेशा `DisplayManager` + `createWindowContext(display, TYPE_ACCESSIBILITY_OVERLAY, null)` से `WindowManager.getCurrentWindowMetrics()` (systemBars + displayCutout) लें। XML में `android:interactive="true"` न लिखें (स्टैंडर्ड `<accessibility-service>` एट्रिब्यूट नहीं है) और `flagRequestTouchExplorationMode` हटाएँ।
  > - **Non-Root Setup व Samsung One UI (`SM-S928B`):** Sideload के लिए `adb shell appops set <pkg> ACCESS_RESTRICTED_SETTINGS allow` और Doze बाईपास (`dumpsys deviceidle whitelist +<pkg>`, `RUN_IN_BACKGROUND`/`RUN_ANY_IN_BACKGROUND allow`) चलाएँ; पर Samsung One UI 6.x पर `Settings -> Apps -> App -> ⋮ -> Allow restricted settings` + Accessibility टॉगल मैनुअली ऑन करना पड़ता है।
  > - **FGS `specialUse` व ADB/SELinux सुधार:** Manifest में `foregroundServiceType="specialUse"` + `PROPERTY_SPECIAL_USE_FGS_SUBTYPE` और `PARTIAL_WAKE_LOCK` रखें। **SELinux सुधार:** `untrusted_app` के `LocalServerSocket` (`localabstract`) को Android 13/14 में `adbd` (`shell`) से `avc: denied { connectto }` ब्लॉक कर सकता है — इसलिए कंट्रोल चैनल के लिए **`ServerSocket` on `127.0.0.1:<port>` + `adb forward tcp:<port> tcp:<port>`** (पर-सेशन लोकल ऑथ टोकन के साथ) रखें; ADB कमांड हमेशा **`am start-foreground-service`** (हाइफ़न सहित) और `exported="true"` (या एक्टिविटी बूटस्ट्रैप) के साथ चलाएँ।
  > - **Java कोड सुधार चेकलिस्ट:** मॉडल सैंपल में Kotlin `import ... as CoreInsets`, क्रॉस-क्लास `private` फ़ील्ड एक्सेस, null `getPackageName()`, छूटा `webView.recycle()`, अनलिमिटेड क्लाइंट सॉकेट लीक, और ज़ूम पर `cssVisualViewport` न जोड़ने (`elem["x"] * dpr` मात्र) की कमियाँ मिलीं — वास्तविक Java बिल्ड में इन सभी को ठीक किया जाएगा।

---

### `[~]` B2. `[Java / Python Hub]` Multi-Phone USB Hub Farm Orchestrator
- **मौजूदा फ़ाइलें व कनेक्शन बिंदु:** `pool.py` (`MobileTetherPool`), `main.py` (`scheduler.daily_cap: 2000`)।
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. Windows पीसी पर USB 3.0 Powered Hub से जुड़े 4–10 Android फ़ोनों को अलग-अलग ADB Serial (`-s <serial>`) पर स्वतंत्र रूप से रूट करने, और हर फ़ोन का पब्लिक IP + कैरियर लेटेंसी ट्रैक करने का सर्वोत्तम डिज़ाइन क्या है (जिससे 1 फ़ोन की ~650/दिन सीमा बढ़कर `2000/दिन` तक पहुँचे)?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **फ़ार्म आर्किटेक्चर व Windows USB नियम:** `AdbRunner` (per-serial semaphore max `2` + global semaphore + `CREATE_NO_WINDOW`), प्रति-स्लॉट अलग पोर्ट (`9222+i` CDP, `18700+i` Agent), cross-phone `CgnatCollisionTracker` (`/24`, `/20` exponential decay), और Windows 11 पर externally-powered 60W+ USB 3.0 हब + **USB Selective Suspend Disabled** अनिवार्य है।
  - **ऑडिट में पकड़े गए 5 क्रिटिकल बग्स (इम्प्लीमेंटेशन में सुधारना है):**
    1. *नॉन-रूटेड Android में `curl` मिसिंग:* `get_public_ip()` में `adb shell curl` स्टॉक Android (Toybox) पर अनुपस्थित होता है — IP हमेशा `None` आकर `CgnatCollisionTracker` अंधा रहेगा; IP जांच **`B1` Java `PhoneAgentService` (cellular `Network` bound)** या CDP से करें।
    2. *`B1`/`B3` प्रोटोकॉल विसंगति:* `localabstract:phone_agent_service` Android 13/14+ SELinux (`avc: denied`) में ब्लॉक होता है — `B1` नियम अनुसार **`tcp:<port>` (`127.0.0.1`)** यूज़ करें, और Chrome CDP पर **`B3` `parse_proc_net_unix()` + `--no-rebind`** चलाएँ।
    3. *रीस्टार्ट स्टेट-मशीन फ्रीज़ व डेड `rotate_ip()`:* क्रैश के बाद `state/<serial>.json` से लोड `BUSY`/`READY` फ़ोनों पर `_enumerate_devices()` **`initialize()` कॉल नहीं करता** (फ़ोन अटक जाता है), `acquire_phone()` कभी `rotate_ip()` ट्रिगर नहीं करता, और पिछली तारीख से बचे `sessions_today` रीसेट करने हेतु `sessions_date` मिसिंग है।
    4. *`async with` क्रैश व `daily_cap` लीक:* डॉकस्ट्रिंग `async with pool.acquire_phone()` लिखती है पर मेथड async context manager नहीं है (`TypeError`); और `_per_phone_cap()` के `×1.1` से कुल सेशंस **`2000` के बजाय `2200` तक पार** हो जाते हैं (ग्लोबल सम चेक जरूरी)।
    5. *Windows `:` फ़ाइलनाम क्रैश:* Wi-Fi ADB सीरियल (`ip:port`) में `:` होने से Windows NTFS पर `PhoneSlotState.to_file()` क्रैश होगा — सीरियल सैनिटाइज़ करें।

---

### `[~]` B3. `[Python — ADB CDP]` Real Android Chrome Controller (`android_cdp_bridge.py`)
- **मौजूदा फ़ाइलें व कनेक्शन बिंदु:** `mobile_adb.py` + `worker.py` (`playwright.chromium` लॉन्च की जगह वैकल्पिक मोबाइल इंजन)।
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. `adb forward tcp:<port> localabstract:chrome_devtools_remote` के ज़रिए फ़ोन पर खुले **असली Android Chrome** से Playwright `connect_over_cdp()` जोड़ने पर क्या-क्या काम करता है और कौन-सी सीमाएँ (जैसे टैब क्लीनअप, प्राइवेट/इंकॉग्निटो या ऐप डेटा क्लियर `pm clear` बनाम कुकी पर्ज़िस्टेंस) आती हैं?
  2. इसमें `navigator.webdriver` व CDP `Runtime.enable` लीक्स को कैसे हैंडल करें?
- **आपका रिसर्च नोट / निष्कर्ष (सत्यापित Step 1 — 2026-11-12, Deep Protocol Audit v2):**
  > - **सॉकेट डिस्कवरी (`/proc/net/unix`):** स्टॉक non-rooted Android Chrome भी USB debugging ऑन व प्रक्रिया चालू होने पर सीधे `@chrome_devtools_remote` (`localabstract:chrome_devtools_remote`) खोल सकता है (`chrome://flags` की हर डिवाइस पर बाध्यता नहीं; `am start -a android.intent.action.VIEW -d <url> -p com.android.chrome` से चालू करें)। प्योर Python `parse_proc_net_unix()` (`split(maxsplit=7)`) में `socket_type == 1`, `state == 1`, `flags & 0x00010000` (`SO_ACCEPTCON`), और `@` prefix वाली सुनने वाली एंट्री छांटें; लेकिन **सक्रिय `/json/version` व `/json/list` प्रोब** से ही सर्वर हेल्थ कन्फ़र्म मानें।
  > - **सुरक्षित पोर्ट आवंटन, क्रैश रिकवरी व अर्ली-ब्रेक:** पोर्ट `5037` कभी नहीं; `9222–9299` रेंज में `adb -s <serial> forward --no-rebind tcp:<port> localabstract:<socket>` चलाएँ (`CREATE_NO_WINDOW`)। यदि डिवाइस `offline`/`unauthorized` हो तो 78 पोर्ट घुमाने के बजाय तुरंत रुकें। क्रैश/पावर-कट रिकवरी के लिए `state/` में `{serial, host_port, socket, owner_pid}` ओनरशिप रिकॉर्ड रखें और रीस्टार्ट पर `adb forward --list` से केवल मृत अपने ओनर वाले अनाथ फ़ॉरवर्ड `--remove` करें। HTTP प्रोब में `httpx.AsyncClient(trust_env=False, timeout=3.0)` रखें और `/json/version` में `webSocketDebuggerUrl` अनिवार्य मानें (WebView में कई बार यह नहीं होता)।
  > - **Airplane Mode व नेटवर्क सच:** USB ADB पर Airplane Mode से `adb forward` टनल बंद नहीं होती (सिर्फ़ Wireless ADB व Chrome के खुले HTTP/QUIC रिक्वेस्ट कटते हैं); रीकनेक्ट या Chrome रीस्टार्ट पर नया डिस्कवरी/प्रोब ज़रूरी है।
  > - **Playwright `connect_over_cdp()` व FTUE-सेफ़ क्लीनअप:** Android Chrome पर `browser.contexts[0]` डिफ़ॉल्ट प्रोफ़ाइल है (`new_context()` incognito/सीमित है; `set_viewport_size`/`device_scale_factor`/`mouse.wheel` सीमित हैं; `Browser.getVersion` via `new_browser_cdp_session()` लें)। `PUT /json/new?<URL>` में पूरा URL percent-encode न करें (या सीधे Playwright/CDP `Target.createTarget` यूज़ करें)। `pm clear` से FTUE वापस आता है—इसलिए पहले **automation-owned target IDs** के एक्टिव पेजों/वर्कर्स को रोककर `GET /json/close/<id>` / `Target.closeTarget` चलाएँ (पर्सनल टैब न छुएं), फिर `Storage.clearDataForOrigin` (`keep_cookies=True` पर `"local_storage,indexeddb,cache_storage,service_workers"`, वरना `"all"` + `Network.clearBrowserCookies` + `Network.clearBrowserCache`) व `Emulation.clearDeviceMetricsOverride` करें। **लाइव जाँच बाकी:** फ़ोन `RZCX21WTS9E` पर `adb shell cat /proc/net/unix` से असली सॉकेट कन्फ़र्म करना है।

---

### `[~]` B4. `[Python Kinematics]` Biometric Motion & Touch Engine (`biometric_motion.py`)
- **मौजूदा फ़ाइलें व कनेक्शन बिंदु:** `human.py` (`_bezier_path`, `move_mouse`).
- **रिसर्च करने के मुख्य बिंदु / प्रॉम्प्ट:**
  1. डेस्कटॉप के लिए **Minimum-Jerk Trajectory / Fitts's Law / Sigma-Lognormal** वेलोसिटी मॉडल का गणितीय एल्गोरिद्म क्या है (शुरुआती त्वरण, मध्य पीक वेग, टारगेट के पास धीमा होना व हल्का ओवरशूट)?
  2. मोबाइल Android सेशन के लिए Playwright में डेस्कटॉप `mouse.wheel` की जगह `CDP Input.dispatchTouchEvent` (मोमेंटम के साथ स्वाइप + फिंगर लिफ्ट डीसिलरेशन) कैसे इम्प्लीमेंट करें?
- **आपका रिसर्च नोट / निष्कर्ष (सत्यापित + गणितीय ऑडिट Step 2 Part 2B — 2026-11-12):**
  > - **सत्यापित पीयर-रिव्यूड डेस्कटॉप गणित:** Flash & Hogan Minimum-Jerk (`P(τ) = 10τ³ - 15τ⁴ + 6τ⁵`, `v(τ) = 30τ² - 60τ³ + 30τ⁴`, `v_peak = 1.875` at `τ = 0.5`), MacKenzie Shannon Fitts's Law (`MT = a + b · log₂(D/W_along + 1)` तिरछे एंगल पर प्रोजेक्टेड चौड़ाई सहित), Meyer et al. Two-Phase Submovement (~`65%` प्राथमिक ओवरशूट + ~`35%` सुधारात्मक चरण), और दो-कंपोनेंट Ornstein-Uhlenbeck ट्रेमर (`~2 Hz` स्लो ड्रिफ्ट + `~9 Hz` तेज़ कंपन, वेग के साथ दबने वाला)।
  > - **मोबाइल अंगूठा-आर्क व फ़्लिंग गणित:** दाहिने अंगूठे का CMC जॉइंट पिवट स्क्रीन के नीचे-दाएँ (`~0.85×W`, `H+60` DIP) होता है जिससे ऊपर स्वाइप हल्का दाएँ कर्व बनाता है। **असममित फ़्लिंग:** `better_asymmetric_position()` (`2.2t² - 1.2t³` क्यूबिक हर्माइट) शून्य वेग से शुरू होकर `t = 1` पर ~`0.8` ढलान (~60% पीक वेग) बनाए रखती है ताकि Android Chrome का `VelocityTracker` (~150 DIP/s से ऊपर) असली फ़्लिंग पकड़े। साथ ही Android `B1` (`AccessibilityService.dispatchGesture`) पर यही `ThumbArc` कोऑर्डिनेट `Path.quadTo()` + `continueStroke()` को फीड किए जा सकते हैं। पठन लय के लिए `ReadingRhythmModel` (`Lognormal`, ~`200–238 WPM` आधार, फ़ीड/एड व टेक्स्ट घनत्व अनुसार स्केलिंग)।
  > - **इम्प्लीमेंटेशन से पहले ज़रूरी 5 गणित/कोड सुधार (ऑडिट में पकड़े गए बग):**
  >   1. **OU ट्रेमर वेरिएंस स्केल बग:** सैंपल में `sigma_slow=0.35`, `sigma_fast=0.18` सीधे SDE फ़ॉर्मूले में डालने से stationary RMS केवल `~0.07 px` रह जाता है (`0.35 / √(2×12.6)`) — सही फ़ॉर्मूला: `variance = sigma_rms**2 * (1 - exp(-2*theta*dt))`।
  >   2. **डेस्कटॉप CDP `timestamp` बग:** `dispatch_mouse_trajectory` में `loop.time()` (monotonic uptime) भेजा गया है, जबकि CDP को Unix epoch seconds (`time.time()`) चाहिए।
  >   3. **अधूरा `asymmetric_swipe_position()` छोड़ें:** इसमें `_asymmetric_scale_factor` सिर्फ़ `1.0` स्टब है और `t=a` पर पीछे जम्प होता है — केवल हर्माइट `better_asymmetric_position()` (और सही किया हुआ कर्व) इस्तेमाल करें।
  >   4. **प्रति-फ्रेम ज़िगज़ैग आर्क बग:** `synthesize_thumb_scroll()` लूप के अंदर हर `16ms` पर `thumb.curve_path()` -> `arc_offset_x()` नया `random.gauss(1.0, 0.25)` चुनता है जिससे स्मूथ आर्क के बजाय हर फ्रेम पर X उछलता है — आर्क ऑफ़सेट **प्रति स्वाइप सिर्फ़ एक बार** निकालें और `p` (वेग-आकार वाले `t`) के साथ जोड़ें।
  >   5. **मोनोटोनिक Timestamp व कर्व बग:** `micro_scrub` (`time.time()`) के बाद अगला फ्रेम पुराना `timestamps[i]` (भूतकाल!) भेजता है और बाकी मूव बिना स्लीप के फट जाते हैं; साथ ही Gamma इंटरवल का `max(4.0, ...)` `~20%+` बिंदुओं को `4.0ms` पर क्लिप करता है, `synthesize_trajectory` अंत बिंदु को सीधे ओवरराइट करता है, और सैंपल `force` में capacitive `1.0` व सेफ Y-क्लैम्पिंग जोड़नी होगी।

---

## भाग C — डीप ब्राउज़र-इंटरनल्स, नेटवर्क स्टैक व एंटी-बॉट टेलीमेट्री (Advanced Research)

> *सामान्य AI अक्सर इन्हें छोड़ देते हैं, लेकिन हमारे कोडबेस की असल कमज़ोरियाँ ठीक इन्हीं 8 जगहों पर हैं:*

### `[~]` C1. CDP `Runtime.enable` साइड-चैनल लीक्स और Isolated Execution
- **कोड में अभी:** `worker.py` (L640–654) स्टैंडर्ड Playwright `add_init_script` चलाता है।
- **रिसर्च प्रश्न:** पेज की JavaScript `console.debug` getter ट्रैप या Error stack inspection से Playwright/Puppeteer के CDP `Runtime.enable` को कैसे डिटेक्ट करती है? `ExecutionContext` आइसोलेशन (`rebrowser`-स्टाइल या Isolated World क्रिएशन) मुख्य दुनिया में बिना `Runtime.enable` के स्क्रिप्ट कैसे चलाता है?
- **आपका रिसर्च नोट / निष्कर्ष (सत्यापित Step 1 Part 2 — 2026-11-12, Deep V8/CDP & Touch Audit):**
  > - **`Runtime.enable` & `V8Console` ट्रैप:** `InspectorRuntimeAgent::enable()` कंसोल हैंडलर (`V8Console::messageHandler`) लगाता है; इसके बाद पेज JS में `console.log(honeypot)` पर `toString`/getter तुरंत चल जाता है, तथा `V8::SetPrepareStackTraceCallback` से मुख्य दुनिया के इंजेक्टेड स्टैक फ़्रेम (`Error.prepareStackTrace`) व ~2–5μs टाइमिंग ओवरहेड दिख सकता है।
  > - **`grantUniveralAccess` CDP स्पेलिंग नियम व Isolated World:** `Page.enable` + `Page.getFrameTree` + `Page.createIsolatedWorld({"frameId": id, "worldName": "", "grantUniveralAccess": True})` (**असली प्रोटोकॉल में `Universal` में 's' नहीं होता**—`grantUniversalAccess` लिखने पर Chromium इसे चुपचाप अनदेखा करके opaque cross-origin बना देता है!)।
  > - **Playwright 1.49 निर्भरताएँ व हाइब्रिड डिज़ाइन:** `page.evaluate()`, `locator()`, `wait_for_selector()`, `query_selector()`, `content()`, `title()` सभी `Runtime.executionContextCreated` पर निर्भर हैं (सप्रेस करने पर हैंग होते हैं), जबकि `goto()`, `screenshot()`, `page.url` बिना `Runtime.enable` चलते हैं। नेविगेशन के पार ऑटो-इंजेक्शन के लिए `Page.addScriptToEvaluateOnNewDocument` (`worldName` Chrome 93+, `runImmediately` Chrome 117+) भी बिना `Runtime.enable` चलता है (बस रिटर्न वैल्यू नहीं देता); DOM रीड/स्क्रिप्ट `IsolatedWorld` (`contextId`) से या अलग stdlib RFC6455 रॉ-WebSocket CDP चैनल से चलाएँ और `page.on("console")` न लगाएँ।
  > - **`Input.dispatchTouchEvent` बनाम `Input.synthesizeScrollGesture`:** `synthesizeScrollGesture` (`yDistance < 0` = scroll DOWN) कंपॉज़िटर पर चलता है और **`touchstart`/`touchmove`/`touchend` DOM इवेंट बिल्कुल नहीं पैदा करता**—इसलिए असली टच के लिए हमेशा **मैनुअल `touchStart -> touchMove -> touchEnd`** सीक्वेंस इस्तेमाल करें (CSS DIPs में, `radiusX/Y ~5–7.5`, अधिकतर Android कपैसिटिव स्क्रीन डिफ़ॉल्ट `force: 1.0` रिपोर्ट करती हैं; `touchmove` Chrome 56+ से passive है)। फ़्लिंग (`GestureFlingStart`) के लिए Chromium आखिरी 2–3 `touchMove` इवेंट्स के वेग (`kMinimumFlingVelocity ~150 DIP/s` [अनुमानात्मक सीमा]) को देखता है—**सैंपल बग नोट:** मॉडल के `L891` कोड में `t=0.8` पर quintic `ease_in_out` पहले ही `0.9949` पहुँचकर `1.0` पर क्लैंप हो जाता है जिससे आखिरी 20% मूव शून्य होकर फ़्लिंग टूट जाती है; असली कोड में `ease_in_out` के बजाय सक्रिय वेग वाला अंत रखना होगा।
  > - **URL Bar व `cssVisualViewport` कोऑर्डिनेट गणित:** पुराने राउंडेड फ़ील्ड छोड़ें—हमेशा `Page.getLayoutMetrics()` के **`cssLayoutViewport`**, **`cssVisualViewport`** (`pageX`, `pageY`, `clientWidth`, `clientHeight`, `scale`, `offsetX`/`offsetY`), और **`DOM.getContentQuads()`** (Page/Document DIPs) यूज़ करें: `vp_x = (page_center_x - vv["pageX"]) / scale`, `vp_y = (page_center_y - vv["pageY"]) / scale`; `url_bar_h = cssLayoutViewport.clientHeight - cssVisualViewport.clientHeight` (~56 DIPs जब खुला हो)। स्क्रॉल के बाद URL बार एनीमेशन को स्थिर होने में **~200–250ms** लगते हैं—इसलिए टैप से पहले `cssVisualViewport.clientHeight` स्थिर होने (`wait_for_url_bar_stable`) और `DOM.getNodeForLocation(x, y)` (ancestor चेक सहित) से ऑक्लूजन जाँचें।

---

### `[~]` C2. Web Worker, `SharedWorker` व `OffscreenCanvas` क्रॉस-कॉन्टेक्स्ट लीक्स
- **कोड में अभी:** `fingerprint.py` (L705–716) केवल `window` में `WebGLRenderingContext` व `navigator` को ओवरराइड करता है।
- **रिसर्च प्रश्न:** जब वेबसाइट `new Worker(Blob)` या `OffscreenCanvas` से बैकग्राउंड थ्रेड चलाकर `navigator.hardwareConcurrency`, `navigator.platform`, `userAgentData`, `Intl.DateTimeFormat`, या WebGL GPU रेंडरर पढ़ती है, तो Window-level `add_init_script()` वहाँ क्यों नहीं लागू होता? Worker ग्लोबल स्कोप को सिंक करने के सुरक्षित पैटर्न क्या हैं?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **मूल कारण व नियम:** `Page.addScriptToEvaluateOnNewDocument` / `add_init_script()` व `createIsolatedWorld` केवल `LocalFrame` में नए `Document` पर चलते हैं, `WorkerGlobalScope` में नहीं। `navigator.maxTouchPoints` को Worker में **कभी डिफ़ाइन न करें** (`WorkerNavigator` स्पेक में वह `undefined` होता है)।
  - **रियल डिवाइस (`B3`) बनाम CDP वर्कर इंजेक्शन:** असली Android Chrome पर GPU (`OffscreenCanvas` WebGL), CPU, `Intl`, `languages`, `userAgentData` अपने-आप सिंक रहते हैं; मुख्य खतरा `navigator.webdriver` (`--enable-automation` होने पर) और असंगत `Emulation.setUserAgentOverride` (`userAgentMetadata`) का है।
  - **ऑडिट में पकड़े गए अनिवार्य फ़िक्स:**
    1. *`flatten=True` + `Target.sendMessageToTarget` प्रोटोकॉल बग:* मॉडल के `_send_to_session` में `Target.setAutoAttach(flatten=True)` के साथ deprecated नेस्टेड `Target.sendMessageToTarget` (हार्डकोड `id: 1`) भेजा गया — फ़्लैट मोड में रॉ WebSocket पर **top-level `"sessionId"`** से कमांड भेजें, `SharedWorker`/`ServiceWorker` के लिए **Browser CDP टारगेट** (`new_browser_cdp_session` / रॉ WS) पर `setAutoAttach` लगाएँ, और `try/finally` में `Runtime.runIfWaitingForDebugger` से डेडलॉक रोकें।
    2. *नग्न Worker `webdriver` व `C1` उल्लंघन:* `WORKER_WEBDRIVER_PATCH` में `Function.prototype.toString` `[native code]` हुक मिसिंग है और `page.add_init_script()` `C1` के विरुद्ध `Runtime.enable` ट्रिगर करता है — पहले जाँचें कि स्टॉक `B3` Chrome पर `navigator.webdriver` पहले से `false` तो नहीं (अगर पहले से `false` है तो कुछ पैच न करें!)।

---

### `[~]` C3. JS Prototype Chain बनाम Own-Property Descriptors और `[native code]`
- **कोड में अभी:** `fingerprint.py` (L667–739) में `Object.defineProperty(screen, 'availHeight', { get: () => ... })` और `window.chrome.runtime = { connect: () => ... }` जैसे पैच हैं।
- **रिसर्च प्रश्न:** डिटेक्शन स्क्रिप्ट `Object.getOwnPropertyDescriptor(screen, 'availHeight')` (जो वास्तव में `Screen.prototype` पर होना चाहिए), `Function.prototype.toString.call()`, `Reflect.ownKeys()`, और नए बनाए गए `iframe.contentWindow` के क्रॉस-चेक से नकली प्रॉपर्टीज़ कैसे पकड़ती हैं? प्रोटोटाइप-लेवल पैचिंग और `Proxy` ट्रैप सेफ्टी का सही तरीका क्या है?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **सही पैटर्न:** प्रॉपर्टी कभी इंस्टेंस (`navigator`/`screen`) पर न डालकर प्रोटोटाइप चेन मालिक (`Screen.prototype`, `Navigator.prototype`/मिक्सिन) पर मूल `enumerable`/`configurable`/`set` एट्रिब्यूट्स के साथ पैच करें, और `WeakMap` + `Function.prototype.toString` हुक व `Symbol.toStringTag` बनाए रखें।
  - **ऑडिट में पकड़े गए 3 क्रिटिकल बग्स (इम्प्लीमेंटेशन में सुधारना है):**
    1. *चाइल्ड `iframe` में अनहुक्ड `toString` + `window[0]` बाईपास + `new toString()`:* `newContentWindowGetter` केवल `w.navigator` पैच करता है पर **`w.Function.prototype.toString` को हुक करना भूल जाता है** — इससे `iframe.contentWindow.Function.prototype.toString.call(desc.get)` तुरंत असली JS सोर्स दिखा देता है; साथ ही `window[0]` / `window.frames[0]` `contentWindow` गेटर को पूरी तरह बाईपास करता है (Chrome 96+ पर प्रति-रेल्म आइसोलेशन), और `function toString(){}` पर `new hookedToString()` कंस्ट्रक्टेबल है (ग़ैर-कंस्ट्रक्टेबल Arrow / `Proxy` यूज़ करें)।
    2. *डेड `makeStrictNativeGetter` (`Illegal invocation`):* मॉडल ने `makeStrictNativeGetter` लिखा पर कॉल नहीं किया — परिणामतः `getter.call({})` त्रुटि `TypeError: Illegal invocation` फेंकने की बजाय `false` लौटाता है।
    3. *झूठा `ownKeys` पास व अनावश्यक पैच:* Check #6 `navigator` पर 20+ own keys को पास मानता है जबकि असली `navigator` पर `Object.getOwnPropertyNames(navigator)` खाली (`[]`) होता है; और जब स्टॉक `B3` Android Chrome पर `navigator.webdriver` पहले से `false` हो तो उसे दोबारा पैच ही न करें।

---

### `[~]` C4. Layer-4/5 नेटवर्क फिंगरप्रिंट: TCP `TTL`, TLS `JA4`, और HTTP/2 `SETTINGS`
- **कोड में अभी:** `tls_rotator.py` (L18–67) और `mobile_adb.py` (Windows से Chromium चलाकर Android UA भेजना)।
- **रिसर्च प्रश्न:** Windows (`TTL=128`, Winsock TCP options, Desktop Chrome BoringSSL `JA4`) से भेजे गए Android UA बनाम असली Android (`TTL=64`, Linux TCP stack, Android Chrome `JA4` + HTTP/2 `SETTINGS` / Priority फ्रेम) में क्या सटीक बाइनरी अंतर होता है, और किस स्तर पर Edge/CDN उसे पकड़ता है?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **सटीक L4/L5 अंतर व प्रमाण:** Windows (`TTL=128`, `WS=8`, `Timestamps=False`, SYN `[MSS, NOP, WS, NOP, NOP, SACK_PERM]`) बनाम Android Linux (`TTL=64`, `WS=7` [kernel-dependent], `Timestamps=True`, SYN `[MSS, SACK_PERM, TS, NOP, WS]`, cellular `MSS ~ 1400`)। समान Chrome वर्ज़न में BoringSSL `JA4` व `HTTP/2 SETTINGS` (`INITIAL_WINDOW_SIZE=6291456`) लगभग समान रहते हैं, इसलिए Android UA स्पूफ़िंग मुख्यतः TCP `TTL`/SYN-options पर पकड़ी जाती है (यदि अपस्ट्रीम प्रॉक्सी हो तो प्रॉक्सी नोड का TTL दिखता है)। `B1`/`B3` असली Android + Cellular पूरा L4/L5 सतह स्वाभाविक रूप से खत्म कर देता है; `tls_rotator.py` केवल genuine डेस्कटॉप सेशंस तक सीमित रहेगा।
  - **ऑडिट में पकड़े गए अनिवार्य फ़िक्स:**
    1. *4 डेड टेलीमेट्री फ़ील्ड:* मॉडल की `SessionTelemetry` क्लास में `ja4_hash`, `http2_initial_window`, `source_ip`, `source_asn` (तथा `declared_chrome`) डिफ़ाइन तो हैं, पर **`verify_telemetry_consistency()` उनमें से एक को भी चेक नहीं करता** — असली कोड में `JA4` ALPN/TLS वेरिएंस, HTTP/2 प्रोफ़ाइल व `ASN` (datacenter vs mobile carrier) चेक जोड़ना होगा।
    2. लोकल Android पर बिना सर्वर-साइड एको के पैसिव TTL मापन संभव नहीं — सत्यापन हेतु कंट्रोल होस्ट/लॉग या `B1`/`B3` एंडपॉइंट टेलीमेट्री यूज़ करें।

---

### `[~]` C5. Resource Blocking (`font`/`media`) व CSS Media Query विरोधाभास
- **कोड में अभी:** `config.yaml` (L220–222) में `block_resources: [font, media]` और `worker.py` (L644–651) में `route.abort()` है।
- **रिसर्च प्रश्न:** Playwright में `font` व `media` को `route.abort()` करने से `document.fonts.status`, `@font-face` लोड त्रुटियाँ, वीडियो/VAST एड यूनिट्स और नेटवर्क कैश पर क्या असर पड़ता है? साथ ही मोबाइल UA पर `window.matchMedia('(pointer: coarse)')`, `(any-hover: none)` और `devicePixelRatio` कैसे मैच रहने चाहिए?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **`route.abort()` के साइड-इफ़ेक्ट्स:** फ़ॉन्ट/मीडिया ब्लॉक करने पर `PerformanceResourceTiming` में `transferSize: 0`, `encodedBodySize: 0`, `duration < 5ms`, `responseStatus: 0` (Chrome 109+) तथा `document.fonts.size/check()` विफलता व `<video>` `MediaError` (`readyState=0`, `networkState=3`) बनता है।
  - **CSS Media Coherence:** मोबाइल पर `pointer: coarse`, `any-pointer: coarse`, `hover: none`, `any-hover: none`, `maxTouchPoints > 0`, `devicePixelRatio` तथा पीसी इम्यूलेशन की जगह असली Android (`B3`) पर `color-gamut` (`p3`/`srgb`) व सिस्टम फ़ॉन्ट स्वाभाविक रूप से मेल खाते हैं।
  - **ऑडिट में पकड़े गए अनिवार्य फ़िक्स:**
    1. *टूटा `EMPTY_WOFF2_B64` प्लेसहोल्डर व ग्लिफ़-बॉक्स बग:* मॉडल ने अधूरा प्लेसहोल्डर बाइट्स छोड़ा (`[NOTE] The above is a placeholder`) जो `OTS parsing error` देगा, `.woff`/`.ttf` पर गलत `font/woff2` भेजेगा, और 0-ग्लिफ़ फ़ॉन्ट से `Canvas`/`measureText` लेआउट फिंगरप्रिंट बिगाड़ेगा — असली Chrome कैश के साथ फ़ॉन्ट अलाउ रखें और केवल भारी नॉन-एड वीडियो स्ट्रीम को चयनात्मक संभालें।
    2. *फ़्रैक्शनल मोबाइल DPR जांच गैप:* `CSS_MEDIA_QUERY_COHERENCE_PROBE` सिर्फ़ `1 | 2 | 3` चेक करता है जिससे Pixel/Samsung (`2.625` / `2.75` DPR) पर `dprFromMQ = -1` होकर चेक चुपचाप बाईपास हो जाता है — `(min-resolution: ...dppx)` रेंज यूज़ करें।

---

### `[~]` C6. Cold `Referer` हेडर बनाम Real Navigation History & `Sec-Fetch-*`
- **कोड में अभी:** `worker.py` (L665–666) में `page.goto(start_url, referer=referrer)` के ज़रिए सीधे हेडर डाला जाता है।
- **रिसर्च प्रश्न:** बिना असली सर्च-रिजल्ट नेविगेशन के सीधे `Referer` हेडर सेट करने पर `window.history.length`, `PerformanceNavigationTiming.type`, `document.referrer`, `Sec-Fetch-Site` और BFCache व्यवहार में क्या विसंगति बनती है?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **असली विसंगतियाँ:** सीधे `page.goto(url, referer=google)` से `history.length = 1` + `Sec-Fetch-Site: none` + `Referer: google` का विरोधाभास बनता है; Google की `Referrer-Policy: origin` होने से `document.referrer` केवल `https://www.google.com/` होना चाहिए (क्वेरी स्ट्रींग नहीं); और Playwright CDP से `BFCache` बंद रहता है इसलिए `page.goBack()` पर फ़ुल लोड दिखता है (बैक-नेविगेशन से बचें या `nav.py` में केवल फ़ॉरवर्ड क्लिक रखें)।
  - **ऑडिट में पकड़े गए 3 क्रिटिकल बग्स (इम्प्लीमेंटेशन में सुधारना है):**
    1. *`execute_entry_flow()` का बड़ा प्रोटोकॉल झूठ (`page.goto("google") -> page.goto("target")`):* मॉडल ने दावा किया कि `page.goto(google)` के बाद बिना `referer=` के `page.goto(target)` करने पर Chrome अपने-आप `Referer: google` और `Sec-Fetch-Site: cross-site` भेजेगा — **यह गलत है!** Chromium में `page.goto()` हमेशा browser-initiated (`Page.navigate` / address-bar) नेविगेशन है जिसका कोई initiator नहीं होता, इसलिए वह **अब भी `Sec-Fetch-Site: none` और खाली `Referer: ""`** भेजता है! `cross-site` + `Referer` केवल **पेज के भीतर `<a href>` क्लिक / डॉक्यूमेंट-इनिशिएटेड नेविगेशन** से मिलता है।
    2. *`verify_sec_fetch_headers()` में `await` क्रैश:* `headers = request.all_headers()` बिना `await` लिखा है (`playwright.async_api` में यह कोरुटीन है -> `AttributeError: 'coroutine' object has no attribute 'get'`), और असली वायर `sec-fetch-*` देखने के लिए CDP `Network.requestWillBeSentExtraInfo` सबसे सटीक है।
    3. *सोशल एंट्री ओवरहेड:* हर सेशन में भारी `x.com` लोड करना मोबाइल डेटा बर्बाद करेगा व लॉगिन/एंटी-बॉट वॉल पर अटकेगा — हल्के ब्रिज/ओन्ड लैंडिंग या साफ डायरेक्ट/ऑर्गेनिक क्लिक पैटर्न यूज़ करें।

---

### `[~]` C7. `PointerEvent` व `TouchEvent` माइक्रो-टेलीमेट्री
- **कोड में अभी:** `human.py` सामान्य क्लिक कोऑर्डिनेट्स व समय-अंतराल से क्लिक करता है।
- **रिसर्च प्रश्न:** एड व एंटी-बॉट स्क्रिप्ट्स क्लिक और स्क्रॉल इवेंट्स में `event.isTrusted`, `PointerEvent.pressure`, `width/height` (उंगली का कॉन्टैक्ट एरिया बनाम माउस का `1x1`), `pointerType`, `movementX/Y`, और `mousedown -> mouseup` / `touchstart -> touchend` के बीच के मिलीसेकंड गैप का विश्लेषण कैसे करती हैं?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **इवेंट चेन व क्रिटिकल `B1` बनाम `B3` ट्रेड-ऑफ़:** मोबाइल टैप में `pointerdown -> touchstart -> pointerup -> touchend -> compatibility mouse events -> click` (`60–140ms` lognormal होल्ड) चलता है। सत्यापित Android SDK सीमा: `B1` (`AccessibilityService.dispatchGesture`) `pressure=1.0f` व छोटे डिफ़ॉल्ट कॉन्टैक्ट पर लॉक रहता है; जबकि **`B3` CDP `Input.dispatchTouchEvent`** भी `isTrusted=true` रखता है और `radiusX/Y = 10–22`, `rotationAngle = 0–15`, `force = 0.3–0.9` से असली `20–44 CSS px` कॉन्टैक्ट व प्रेशर देता है (डिफ़ॉल्ट `1x1` लीक खत्म, `movementX/Y = 0`)।
  - **ऑडिट में पकड़े गए अनिवार्य फ़िक्स:**
    1. *Array प्रॉपर्टी ड्रॉप बग (क्रिटिकल):* `window.__getPointerTelemetry` ने JS `Array` पर `result._anomalies`, `result._holdDuration`, `result._upToClick` प्रॉपर्टीज़ जोड़ी हैं — Playwright/CDP JSON सीरियलाइज़ेशन में Array की कस्टम प्रॉपर्टीज़ **गायब हो जाती हैं**! इन्हें `{ events, holdDuration, upToClick, anomalies }` ऑब्जेक्ट में लौटाएँ।
    2. *मल्टी-टच व स्क्रॉल+टैप अलगाव:* केवल `downs[0]`/`ups[0]` लेने से स्क्रॉल और उसके बाद के टैप का होल्ड-टाइम मिल जाता है — प्रति `pointerId` से डाउन/अप जोड़ी ट्रैक करें।

---

### `[~]` C8. Ad Viewability SDK मैकेनिक्स (`IntersectionObserver v2`, Frame Timing, Focus)
- **कोड में अभी:** `worker.py` में स्क्रॉल होल्ड (`1.4s–2.4s`) और CDP `setFocusEmulationEnabled` इस्तेमाल होता है।
- **रिसर्च प्रश्न:** आधुनिक एड व्यूएबिलिटी SDKs (`MRC Viewability` / `IntersectionObserver v2` `isVisible` व occlusion ट्रैकिंग, `document.hasFocus()`, `requestAnimationFrame` FPS ड्रॉप) कैसे तय करते हैं कि एड इम्प्रेशन वाकई किसी इंसान की स्क्रीन पर रेंडर व विज़िबल था या नहीं?
- **आपका रिसर्च नोट / निष्कर्ष:**
  - **MRC मानक व `IO v2`:** Display `>=50%` क्षेत्र `>=1s` (बड़े `>=242,500 px²` पर `>=30%` for `1s`), Video `>=50%` for `>=2s`; `IntersectionObserver` में `trackVisibility: true` के लिए `delay >= 100ms` अनिवार्य है वरना `TypeError` आता है; `entry.isVisible` ऑक्लूज़न/ओवरले, `opacity`, `clip-path`, और क्रॉस-ऑरिजिन iframe विज़िबिलिटी चेक करता है; बैकग्राउंड टैब में `rAF` `<= 1 FPS` पर थ्रॉटल होता है।
  - **ऑडिट में पकड़े गए 3 क्रिटिकल बग्स (इम्प्लीमेंटेशन में सुधारना है):**
    1. *Playwright `page.evaluate` मल्टी-आर्ग क्रैश:* `AdViewabilityController.ensure_viewable` ने `page.evaluate(js, ad_selector, slot_id)` पास किया जो Python Playwright में **`TypeError` पर क्रैश** हो जाता है — केवल 1 डिक्ट पेलोड `{"selector": ..., "slotId": ...}` और `({ selector, slotId }) => ...` यूज़ करें।
    2. *`1s` पर rAF स्टॉप व `50ms` फ़्रेम-ड्रॉप रीसेट बग:* `if (!tracker.viewabilityAchieved)` होने से `1000ms` होते ही ट्रैकर रुककर आगे का ड्वेल मापना बंद कर देता है, एक सिंगल `dt >= 50ms` जिटर पूरी `950ms` की continuous व्यूएबिलिटी रीसेट कर देता है, और `adArea > 0` चेक मिसिंग है।
    3. *`C1` व `Focus` संवेदनशीलता:* `setup()` में `page.evaluate()` सीधे चलाने से `Runtime.enable` लीक (`C1`) होता है (वेरिफायर को `IsolatedWorld` या टेस्ट-मोड में रखें), और केवल `Emulation.setFocusEmulationEnabled(true)` लॉक करने से `focusin`/`focusout` हिस्ट्री नहीं बनती (`B3` असली Android फ़ोरग्राउंड Chrome में `hasFocus()` स्वाभाविक रूप से `true` रहता है)।

---

## भाग D — इम्प्लीमेंटेशन से पहले वेरिफ़िकेशन नियम (Anti-Hallucination Gate)

जब आप बाहरी AI / अनसेंसर्ड मॉडल से रिसर्च लाकर यहाँ जोड़ें, तो कोड बदलने से पहले हर आइडिया को इन 4 कसौटियों पर परखना ज़रूरी है:
1. **कोई अंधी "सीक्रेट रूल" गारंटी नहीं:** किसी भी LLM के पास Adsterra या Google के बंद सर्वर कोड की कॉपी नहीं होती — हम केवल ब्राउज़र मानकों, नेटवर्क प्रोटोकॉल व हमारे लोकल टेलीमेट्री डेटा से प्रमाणित तकनीकें लागू करेंगे।
2. **सिक्योरिटी गेट बायपास :** रिसर्च केवल असली डिवाइस हार्डवेयर कोहेरेंस, ML ऑप्टिमाइज़ेशन और एड व्यूएबिलिटी पर केंद्रित रहेगी —
3. **डाइग्नोस्टिक प्रमाण:** हर फ़िंगरप्रिंट या मोशन पैच जोड़ने के बाद `python tests/audit.py` और वास्तविक JS इंस्पेक्शन से क्रॉस-वेरिफ़ाई किया जाएगा।
4. **लाइव API से मिलान:** किसी भी ML या ट्रैफ़िक बदलाव का अंतिम पैमाना Adsterra Official API पर `Count Efficiency %`, `eCPM`, `CTR`, और `0% Invalid/Degraded Drop` होगा।
