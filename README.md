### START HERE
---
to begin running the web for testing, please follow these instructions:
1. change directory to the folder of the cloned repository.
2. run: py -m venv <name> | py -m venv .venv
3. in terminal or powershell, run: .venv\Scripts\Activate.ps1
4. run: py -m pip install -r requirements.txt
5. py main.py
---
once done check if the elements or anything is running just fine. **report back to the gc if there are any bugs found, or create an issue in github.**
#### KNOWN ISSUES
- commuter types dont work properly or display the same output as the car.
- clicking on routes does not do anything. it requires an action basically.
- support for mobile view.

- the ability to concatenate two points of location, e.g., ue caloocan to ue recto then ue recto to cubao.
-- _WHEN FIXED:_ ability to put multiple points of wtv.
### apis
- leafjs (OpenStreetMap)
- https://open-meteo.com (for accurate weather forecast)
- traffic forecast : tomtom or here traffic (used by grab)

- ai resolver : gemini 2.5 flash lite (for unlimited use and fast ai response)
-- ai resolver will be put into another file, since regex will be used. and functions will benefit from regex.
--  _WHEN IMPLEMENTED:_ safety score and hazard info will benefit from this.
---
#### CHANGES NEEDED:
- convert app.js to a python language instead.
