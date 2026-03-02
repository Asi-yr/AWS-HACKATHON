### START HERE
to begin running the web for testing, please follow these instructions:
1. change directory to the folder of the cloned repository.
2. run: py -m venv <name> | py -m venv .venv
3. in terminal or powershell, run: .venv\Scripts\Activate.ps1
4. run: py -m pip install -r requirements.txt
5. run the final command: py main.py

when commiting changes to the repository, one must first add elements to .gitignore:
- create a file and name it .gitignore.
  - when creating or adding something to gitignore, one must observe files and folders that the program created. all unnecessary files sent to the repository must be avoided. only the core files that we're actively modifying or creating.
  - e.g., __pycache__, folder of your python environment, backups or your own customized file (e.g., main.py.bck or something...), *.db files or database files, and finally .env file (where your api keys are stored.)
- then hit save :3

using the ai feature or if the program did not run due to missing api key:
1. visit https://aistudio.google.com using your personal account.
2. look for 'Get API key' from the navigation menu.
3. create an api key specific for our project, then create an api key.
4. after creating, look for the project name and at the end there's a copy button.
5. paste it into the folder called 'grounding_tool' and create a file '.env'
6. inside the file insert 'exclusive_genai_key=API_KEY_HERE', then save.
---
once done check if the elements or anything is running just fine. **report back to the gc if there are any bugs found, or create an issue in github.** *also see commits before asking the gc or creating an issue on github.*
### Issues & Fixing
- commuter types dont work properly or display the same output as the car.
- support for mobile view.
- need to convert the app.js to python language!!
- dashboard minimize ability.
- clicking on routes does not do anything. it requires an action basically. (on going fix) 
  - prioritizing location implementation. (DONE)
  - viewing angles implementation for the map (ON-GOING)
  - moving user location towards the path or something.
    - redirection of routes. (PENDING)
- design issues: (or not)
  - text input box, with current location button must alight perfectly with the text box elements.
- the ability to concatenate two points of location, e.g., ue caloocan to ue recto then ue recto to cubao.
  - _WHEN FIXED:_ ability to put multiple points of wtv.
#### Pending fixing
- on live location, it should be always toggled, and never disabled unless the location's permission is disabled or there's no location to begin with.
  - requires removal of live location toggle, or it should be kept as enabled all the time, and it should automatically input the current location instead.
    - this needs to have a pinpoint indicator already.
#### Transition fixing (JS to python)
- pinpointing requires which location is selected. an icon should appear of the selected location, then destination. regardless of which is being chosen (e.g., startling location & destination) [pending fix]
#### Feature request
- implementation of ai, without chatbot.
- offline mode.
- students and woman modes, also lgbtqia+ support, tho idk.
- lrt/mrt mode for commuter types
- settings, and account settings. (delay)
- user data settings, history and account settings. (delay)
#### Improvements to be implemented
- when pinpointing there should be a status like e.g., a toast (that stays) or the text input boxes saying 'select pinpoint in the map' or something. when the pinpointing button is toggled. (DONE) 
  - note: need revisions, but it's ok for a prototype.
- design issues: (or not)
  - text input box, with current location button must alight perfectly with the text box elements.
---
#### APIs
- leafjs (OpenStreetMap) [deprecated]
- python folium (OpenStreetMap)- leafjs (OpenStreetMap)
- https://open-meteo.com (for accurate weather forecast)
- traffic forecast : tomtom or here traffic (used by grab)
- ai resolver : gemini 2.5 flash lite (for unlimited use and fast ai response)
  - ai resolver will be put into another file, since regex will be used. and functions will benefit from regex.
  -  _WHEN IMPLEMENTED:_ safety score and hazard info will benefit from this.
#### CHANGES NEEDED:
- convert app.js to a python language instead. (DONE)
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
