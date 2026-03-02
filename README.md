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
#### KNOWN ISSUES OR IMPLEMENTATION
- commuter types dont work properly or display the same output as the car.
- support for mobile view.
- need to convert the app.js to python language!!
- dashboard minimize ability.

- clicking on routes does not do anything. it requires an action basically. (on going fix) 
  - (prioritizing location implementation) :: DONE
  - viewing angles implementation for the map :: ON-GOING

  - moving user location towards the path or something.
    - redirection of routes. :: PENDING

- design issues: (or not)
  - text input box, with current location button must alight perfectly with the text box elements.

- the ability to concatenate two points of location, e.g., ue caloocan to ue recto then ue recto to cubao.
-- _WHEN FIXED:_ ability to put multiple points of wtv.
#### APIs
- leafjs (OpenStreetMap) [deprecated]
- python folium (OpenStreetMap)- leafjs (OpenStreetMap)
- https://open-meteo.com (for accurate weather forecast)
- traffic forecast : tomtom or here traffic (used by grab)

- ai resolver : gemini 2.5 flash lite (for unlimited use and fast ai response)
-- ai resolver will be put into another file, since regex will be used. and functions will benefit from regex.
--  _WHEN IMPLEMENTED:_ safety score and hazard info will benefit from this.
---
#### CHANGES NEEDED:
- convert app.js to a python language instead.
---
##### Core Features:
-	Three-Mode Route Display — Build This
-	Safety Score Engine — Build This
-	NOAH Flood Zone Overlay — Build This
-	Live Weather Risk — Build This
-	Baha Watch Community Flood Reporting — Build This
-	Commuter Type Selection — Build This
-	Score Explanation Panel — Build This
- Ligtas Mode Toggle — Build This
##### QoL Features:
- Typhoon Signal Banner — Nice to Have
- Photo Baha Watch Reports — Nice to Have
-	Report Verification Upvote — Nice to Have
-	Report Categories Expanded — Nice to Have
-	Safety Score Color Coding — Nice to Have
-	Night Mode Auto-Detection — Nice to Have
-	Estimated Fare Display — Nice to Have
##### Could count as QoL Features:
-	Panic Button / SOS Feature — Skip
-	Real-Time Crime Data — Skip
-	Offline Mode — Skip
-	Live Jeepney Tracking — Skip
-	User Accounts and Login — Skip
-	Route History — Skip
-	Machine Learning — Skip
