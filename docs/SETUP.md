# Setup Guide – Robot Vacuum (Roborock)

This plugin talks **directly** to the Roborock cloud API.  
Roborock no longer accepts a plain password from third-party clients, so you must obtain a long-lived **UserData** token once.

---

## 1. Install the dependency

Inside the FiestaBoard container (or the host that runs FiestaBoard):

```bash
pip install python-roborock
```

---

## 2. Obtain the UserData token (one-time)

### Option A – Official CLI (recommended)

```bash
pip install "python-roborock[cli]"
roborock login --email your@email.com
```

Enter the one-time code that arrives in your inbox.  
Then dump the token:

```bash
python -c "
from roborock.cli import RoborockContext
import json
ctx = RoborockContext()
data = ctx.user_data.as_dict() if hasattr(ctx.user_data, 'as_dict') else ctx.user_data.__dict__
print(json.dumps(data, indent=2, default=str))
"
```

### Option B – Stand-alone script

Save as `get_roborock_token.py`:

```python
#!/usr/bin/env python3
import asyncio
import json
from roborock.web_api import RoborockApiClient

async def main():
    email = input("Roborock account email: ").strip()
    client = RoborockApiClient(username=email)

    print("Requesting login code… check your email.")
    await client.request_code()

    code = input("Enter the code from the email: ").strip()
    user_data = await client.code_login(code)

    print("\n===== COPY EVERYTHING BELOW INTO THE PLUGIN =====")
    data = user_data.as_dict() if hasattr(user_data, "as_dict") else user_data.__dict__
    print(json.dumps(data, indent=2, default=str))
    print("===== END =====")

if __name__ == "__main__":
    asyncio.run(main())
```

```bash
python get_roborock_token.py
```

---

## 3. Configure the plugin in FiestaBoard

1. Open the FiestaBoard web UI → **Integrations**
2. Enable **Robot Vacuum (Roborock)**
3. Fill in:
   - **Roborock account email** – the same address you used above
   - **UserData JSON** – paste the entire JSON block you just obtained
   - **Device name filter** (optional) – useful if you own more than one vacuum
   - **Refresh interval** – default 120 seconds is fine
4. Save

The token is long-lived (months to years). You only need to repeat the login if Roborock invalidates it or you change your password / region.

---

## 4. Create a page

**Note (15×3) example:**

```
{{robot_vacuum.name}}
{{robot_vacuum.formatted}}
{{robot_vacuum.clean_area}} {{robot_vacuum.clean_time}}
```

**Flagship example:**

```
     ROBOT VACUUM
{{robot_vacuum.name}}
{{robot_vacuum.activity}}  {{robot_vacuum.battery}}
FAN {{robot_vacuum.fan_speed}}
{{robot_vacuum.clean_area}}  {{robot_vacuum.clean_time}}
BRUSH {{robot_vacuum.main_brush}}  FILT {{robot_vacuum.filter}}
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| “No matching Roborock vacuum…” | Wrong account or no V1 device | Check email / device filter |
| “user_data_json is not valid JSON” | Copy-paste error | Re-dump the token carefully |
| Rate-limit / too many codes | Requested codes too quickly | Wait 10–15 min and try again |
| Token suddenly stops working | Password change or region change | Repeat the login flow |

Keep the UserData JSON secret – it is equivalent to full account access.
