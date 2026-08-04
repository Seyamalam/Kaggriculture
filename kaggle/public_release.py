"""Public-code notice for the Kaggriculture competition.

The complete MIT-licensed agent, evaluation harness, experiment reports, and
history are maintained at:

    https://github.com/Seyamalam/Kaggriculture

The exact source submitted as Kaggle submission 55245711 is tagged
``submission-55245711``. Development candidates remain separate from
``main.py`` until they pass the documented promotion gates.
"""

from hashlib import sha256
from urllib.request import urlopen


SOURCE_URL = "https://raw.githubusercontent.com/Seyamalam/Kaggriculture/main/main.py"


with urlopen(SOURCE_URL, timeout=30) as response:
    source = response.read()

print("Public repository: https://github.com/Seyamalam/Kaggriculture")
print(f"Current main.py SHA-256: {sha256(source).hexdigest()}")
print(source.decode("utf-8"))
