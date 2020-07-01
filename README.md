# weather
A Weather Display that pulls data from NWS's API and doppler radar imagery written in Python.

This is a program I've been working on, right now it is scripted to pull data related to Western NC. However I do plan on adding a settings/control window to allow setting changes and control window elements. The idea is this program can be used with a green screen (pink in this case since doppler radar appears to use similar colors).

All data including forecasts, local observations, doppler radar imagery are through the National Weather Service's API (https://api.weather.gov). 

Currently the program checks for observation updates every 15 minutes, forecast updates every 60 minutes, warnings and advisories every 10 minutes (5 minutes if there is an active adisory and 1 minute if there is an active warning). Doppler radar updates every 5 minutes and deletes imagery older than 4 hours (anything in the radar directory).

In order to run this program you will need the following:

Python 3.8 (Haven't tested older versions of Python 3.x)

Need the following libraries in Python (you can install with pip)
PIL
simpleaudio
apscheduler
lxml
requests

Other libraries used (which if I can recall are built-in)
os
tkinter
glob
datetime
tim

That being said. I'm not really a programmer and have no real background in programming, so there are likely to be many issues and bugs in the code and other many many "sins" and I'm learning as I go along. This is really "pre-alpha" considering I am not done with adding all the features I plan on adding.

Other things to consider. I accept no liability for any damages, loss of life, personal injury resulting from the failure of the program to display weather warnings, advisories, forecasts and other information. The NWS API can be very slow to update at times and likewise severe weather can cause internet outages.

This program is for entertainment and should not be your primary source to recieve important weather information such as a Tornado Warning. You should get your weather alerts from local media outlets including NOAA Weather Radio. 

