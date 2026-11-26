# Setup – Robot Vacuum (Note 3×15)

## 1. Install dependency

```bash
pip install python-roborock
```

## 2. Get the long-lived UserData token (once)

```bash
pip install "python-roborock[cli]"
roborock login --email your@email.com
```

Enter the code from your email, then dump the token:

```bash
python -c "
from roborock.cli import RoborockContext
import json
ctx = RoborockContext()
data = ctx.user_data.as_dict() if hasattr(ctx.user_data,'as_dict') else ctx.user_data.__dict__
print(json.dumps(data, indent=2, default=str))
"
```

Or use this script:

```python
import asyncio, json
from roborock.web_api import RoborockApiClient

async def main():
    email = input("Email: ").strip()
    client = RoborockApiClient(username=email)
    await client.request_code()
    code = input("Code from email: ").strip()
    ud = await client.code_login(code)
    data = ud.as_dict() if hasattr(ud,"as_dict") else ud.__dict__
    print(json.dumps(data, indent=2, default=str))

asyncio.run(main())
```

## 3. Configure plugin

1. FiestaBoard → Integrations → enable **Robot Vacuum (Roborock)**
2. Paste **email** and the full **UserData JSON**
3. Optional: device name filter
4. Save

## 4. Create the Note page

Exactly three lines:

```
{{robot_vacuum.line1}}
{{robot_vacuum.line2}}
{{robot_vacuum.line3}}
```

That is the complete, guaranteed-to-fit layout.
