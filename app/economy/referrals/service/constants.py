from __future__ import annotations

import re

START_PAYLOAD_REFERRAL_RE = re.compile(r"^ref_([A-Za-z0-9]{3,16})$")
