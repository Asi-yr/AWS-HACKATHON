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
- commuter types dont work properly or display the same output as the car. (ON-GOING)
- clicking on routes does not do anything. it requires an action basically. (on going fix)
  - prioritizing location implementation. (DONE)
  - viewing angles implementation for the map (ON-GOING)
  - moving user location towards the path or something.
    - redirection of routes. (PENDING)
#### Pending fixing
- on live location, it should be always toggled, and never disabled unless the location's permission is disabled or there's no location to begin with.
  - requires removal of live location toggle, or it should be kept as enabled all the time, and it should automatically input the current location instead.
    - this needs to have a pinpoint indicator already.
- the ability to concatenate two points of location, e.g., ue caloocan to ue recto then ue recto to cubao. (PRIORITIZING)
  - _WHEN FIXED:_ ability to put multiple points of wtv.
#### Feature request
- implementation of ai, without chatbot.
- offline mode.
- students and woman modes, also lgbtqia+ support, tho idk.
- settings, and account settings. (delay)
- user data settings, history and account settings. (delay)
#### Improvements to be implemented
- support for mobile view.
- dashboard minimize ability.
- design issues: (or not)
  - text input box, with current location button must alight perfectly with the text box elements.
---
#### Now Working Features.
1. LRT/MRT mode as a commuter type. (took 4 fucking days bro)
#### Modules
1. beautifulsoup4: for web scraping.
2. ddgs: duckduckgo web and url searching.
#### APIs
- python folium (OpenStreetMap) as leafjs (OpenStreetMap)
- https://open-meteo.com (for accurate weather forecast)
- traffic forecast : tomtom or here traffic (used by grab)
- ai resolver : currently looking for an api model to benefit from this.
#### CHANGES NEEDED:
- _no modifications needed_
##### Core Features:
-	Three-Mode Route Display 
-	Safety Score Engine
-	NOAA Flood Zone Overlay (Flood Data Across the Philippines)
-	Weather Risk
-	Baha Watch Community Flood Reporting (incl. Web Scraper for Multiple Affected Areas)
-	Commute Option (e.g., https://sakay.ph) 
-	Score Explanation with RSS Feature (not explanation.) 
- Ligtas Mode Toggle 
- Approx. Fare Display
##### QoL Features:
- Typhoon Signal Banner 
- Photo Baha Watch Reports (RSS Only, unless correctly implemented by the LLM)
-	Report Verification Upvote 
-	Report Categories Expanded 
-	Safety Score Color Coding 
-	Night Mode Auto-Detection
- Real-Time Crime Data (This is just Web Scraping...)
##### Could count as QoL Features:
-	Panic Button / SOS Feature 
-	Offline Mode
-	User Accounts and Login 
-	Machine Learning 