# लैंडिंग पेज को setup करने के steps

दो files तैयार हैं — दोनों `design_preview/` folder में:
```
login_branded.py   ← असली Python file (tested)
landing.html       ← वही design, plain HTML preview
```

---

## Step 1 — File को सही जगह रखो

Windows CMD:
```cmd
copy F:\UserData\Downloads\adstera\design_preview\login_branded.py F:\UserData\Downloads\adstera\admin_ui\views\login_branded.py
```

या manually copy-paste कर दीजिए।

---

## Step 2 — `__init__.py` में export जोड़ो

File: `admin_ui/views/__init__.py`

**जोड़ना है** (कहीं भी, existing lines न हटाएँ):
```python
from admin_ui.views.login_branded import render_login_branded
```
और `__all__` list में:
```python
    "render_login_branded",
```

---

## Step 3 — `ui.py` में 2 lines बदलो

### पहला: import

Line ~3110 के आसपास, `/crm/login` block है:
```python
        if path in ("/crm/login", "/crm/login/"):
            from admin_ui import profile_auth
            from admin_ui.views import render_login_view      # ← यह बदलना है
```

बदलकर:
```python
        if path in ("/crm/login", "/crm/login/"):
            from admin_ui import profile_auth
            from admin_ui.views import render_login_branded    # ← नया
```

### दूसरा: render call

लगभग 8 lines नीचे:
```python
            self._send_html(render_login_view(prof, error_msg=err), extra_headers=[("Cache-Control", "no-store")])
```

बदलकर:
```python
            self._send_html(render_login_branded(prof, error_msg=err), extra_headers=[("Cache-Control", "no-store")])
```

**बस। 2 lines।** `admin_ui/views/login.py` file जैसी है वैसी रहेगी — कुछ नहीं मिटेगा।

---

## Step 4 — चलाओ और देखो

```cmd
cd /d F:\UserData\Downloads\adstera
py -3.12 ui.py 5050
```

Browser में: `http://localhost:5050/crm/login`

---

## Step 5 — Lock ऑन करो (वरना login आएगा ही नहीं)

```cmd
py -3.12 -c "import sys; sys.path.insert(0,'.'); from admin_ui import profile_auth as pa; pa.set_password('YOUR_PASSWORD','YOUR_PASSWORD',require_login=True); pa.set_require_login(True); print('LOCKED:', pa.is_crm_locked(None))"
```

---

# ध्यान रखने की बातें

**1. `error_msg` कैसे आएगा**
`ui.py` पहले से `?error=invalid` पढ़ता है:
```python
err = "Invalid operator credentials. Please try again." if q.get("error") else ""
```
यह अपने आप alert box में आ जाएगा। कुछ नहीं करना।

**2. Email pre-fill**
अगर profile में email set है, वो field में भरा आएगा। अगर password set नहीं है, खाली रहेगा।

**3. First-run (कोई password नहीं)**
अभी `/api/auth/unlock-dev` button नहीं है नए page में। अगर पहली बार password सेट करना है तो **Step 5 की command** चलाइए, या पुराना page अस्थायी रूप से इस्तेमाल कीजिए।

**4. Tunnel से पहले**
⚠️ `/crm/login` अभी **केवल 4 routes** पर auth है। Tunnel खोलने से पहले Round 21 का **deny-by-default guard** लगाना ज़रूरी है, वरना बाकी 59 endpoints खुले रहेंगे।

---

# जो मैंने test किया

```
render bytes        : 24,902
external requests   : 0
<img> tags          : 0
cards               : 8
wires               : 8
error block         : renders when error_msg non-empty
HTML tags           : सब balanced (div 24/24, svg 10/10, ...)
XSS                 : escaped (raw <script> नहीं, &lt;script&gt; हाँ)
```
