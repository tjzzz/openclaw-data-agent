#!/usr/bin/env python3

import os
from urllib import request
from urllib.parse import urlencode

EMAIL = 'zzzhengds@gmail.com'
PASSWORD = 'zzz142857'

TEXT = "Over the past 10 years, the way people travel in cities has changed. In Guangzhou, buses and metros are still the major public modes of transport. Robotaxis are also being launched in many places in Guangzhou. Reliable transport is helpful for building a society that is inclusive and sustainable. In this essay, we discuss the advantages and challenges of robotaxis in Guangzhou. We claim that robotaxis may make some trips easier, but robotaxis should complement buses and metros rather than replace them."

data = urlencode({"email": EMAIL, "pw": PASSWORD, "text": TEXT}).encode()
req = request.Request(
    "https://ai-text-humanizer.com/api.php",
    data=data,
    method="POST",
)

with request.urlopen(req, timeout=120) as response:
    result = response.read().decode()
    print("HTTP status:", response.status)
    print("Input:", TEXT)
    print("Result:", result)
