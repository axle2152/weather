# weather

A local weather display in the spirit of a cable weather channel's "local
forecast" segment: current conditions, local observations, the 36-hour and
extended forecasts, an almanac and a Doppler radar loop, cycling over your own
photos with see-through "frosted glass" panels. Made to run all day and be
streamed.

> **⚠️ For entertainment only. Not for weather emergencies.**
> This program has no redundancy: if the internet, the computer or the
> National Weather Service's servers have a problem, warnings can be late or
> missing with no sign that anything is wrong. Never use it to alert the
> public or as anyone's main source of warnings. Get alerts from NOAA Weather
> Radio, Wireless Emergency Alerts, local media and weather.gov.
> It comes with no warranty and no liability; see [DISCLAIMER.md](DISCLAIMER.md).

![Current conditions](docs/current.jpg)
![Extended forecast](docs/extended.jpg)
![Doppler radar](docs/radar.jpg)

It works anywhere in the US: set a ZIP code or city and everything else
(forecast office, zones, radar, time zone, nearby cities) is looked up
automatically.

## Quick start

1. Install [Python](https://www.python.org/downloads/) 3.11 or newer.
   On Windows, tick "Add python.exe to PATH" in the installer.
2. Download this repository, open a terminal in its folder and install the
   libraries:

   ```
   pip install -r requirements.txt
   ```

3. Run it:

   ```
   python weather.py
   ```

The first time, it shows a short disclaimer. Tick the box to say you've read
it and press Continue; it won't ask again on that computer. Then the settings
window opens so you can enter your location (a ZIP code, "City, ST" or
latitude/longitude) and your contact email. Press **Save** and the display
switches to your area. The first time for each location takes a few extra
seconds to build the radar map, which is cached in `cache/` after that.

## Settings

Press **S** or right-click the display to open the settings window. It opens
as a separate window, so it never shows up in the picture you're displaying
or streaming. When you press **Save**, the display restarts with the new
settings a few seconds later. You can also open it on its own with
`python weather.py --settings`.

| Tab | What you can change |
| --- | --- |
| Location | Where the forecast is for (with a **Check location** button), the name on screen, your contact email |
| Display | Resolution, full screen, timing, background photo folder, panel color and opacity |
| Slides | Which slides to show and in what order |
| Observations | The Current Conditions station; Local Observations cities picked automatically or chosen by you |
| Radar | Radar source, zoom, map center, loop length and speed, clutter filter, map lines, extra city labels |
| Alerts | How far away storm warnings count, the beep, a test warning, extra NWS zones to watch |

Settings are saved in `config.toml` (which git ignores, so your contact info
stays private). It's plain text with comments, so you can edit it by hand
too; the display picks up changes a few seconds after the file is saved.

The settings window uses Tkinter, which comes with Python from python.org.
On Linux you may need to install your distribution's `python3-tk` package.

## Command-line options

| Command | What it does |
| --- | --- |
| `python weather.py --settings` | Open the settings window without starting the display |
| `python weather.py --check` | Show what it found for your location and exit |
| `python weather.py --place "Denver, CO"` | Try another location without editing the config |
| `python weather.py --resolution 720p` | Run at 720p (or `480p`, or e.g. `1600x900`) |
| `python weather.py --fullscreen` | Full screen |
| `python weather.py --test-warning` | Show a test message in the red warning crawl |
| `python weather.py --screenshots shots` | Save a picture of every slide to `shots/` and exit |
| `python weather.py --accept-disclaimer` | Read and accept the disclaimer in the terminal instead (for a computer with no screen) |

While it's running: **S** or right-click opens settings, **Esc** quits,
**F11** toggles full screen, **Right arrow** skips to the next slide, **B**
changes the background photo.

## Backgrounds

Put your own photos (`.jpg` or `.png`) in the `backgrounds/` folder. They're
cropped to fill the screen and rotated, one per cycle of slides. The panels
blur and tint whatever's behind them; change the folder, panel color and
opacity on the Display tab in settings.

## Slides

| Slide | Shows |
| --- | --- |
| Weather Bulletin | Full text of any watch, warning or advisory for your area (only when there is one) |
| Current Conditions | Temperature, sky, humidity, dewpoint, wind, pressure and trend, visibility, wind chill / heat index |
| Local Observations | Nearby cities' temperature, weather and wind |
| The 36 Hour Forecast | The NWS forecast text for the next three periods |
| The Extended Forecast | Four days of highs, lows, sky and wind |
| Almanac | Sunrise, sunset, twilight, daylight length and the next four moon phases |
| Doppler Radar | An animated loop over a map of your area, with warning boxes drawn on it |

The bottom bar cycles through the current conditions. When a warning is in
effect for your area, it turns red and crawls the warning text, with a beep
each time it starts over.

Pick and order the slides with `slides = [...]` in `config.toml`.

## Where the data comes from

- **Forecasts, observations, alerts:** the [National Weather Service API](https://www.weather.gov/documentation/services-web-api) (public domain)
- **Radar:** the [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/) NEXRAD composite, with the NWS radar loop images as a fallback
- **Map:** [USGS National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map) shaded relief (public domain),
  [US Census Bureau](https://www.census.gov/geographies/mapping-files.html) state, county and Interstate outlines (public domain),
  and [Natural Earth](https://www.naturalearthdata.com/) for Canada and Mexico (public domain)
- **ZIP code and city lookup:** US Census Bureau Gazetteer files and population estimates (public domain),
  bundled in `assets/geo/` (rebuild with `tools/build_geodata.py`)
- **Font:** [Libre Franklin](https://github.com/googlefonts/Libre-Franklin), SIL Open Font License (`assets/fonts/OFL.txt`)

## Known limitations

- Some stations (Chattanooga and Gainesville, GA, for example) report
  temperature and wind but no sky condition, so their weather shows as "--".
- The weather icons come from the NWS, which has marked its icon service as
  deprecated. They work today, but will need replacing eventually.
- US only, °F/mph only.

## Disclaimer

This software is for entertainment and hobby use only. It is **not** a weather
alerting system, must not be used to alert the public, and must not be relied
on in a weather emergency. It is provided "as is", with no warranty, and the
author accepts no liability for any damages, injury or loss of life from its
use or failure. Read the full [DISCLAIMER.md](DISCLAIMER.md).

The program asks you to acknowledge this the first time it runs, and a line in
the conditions ticker reminds viewers. If you modify it or remove those
notices, you're responsible for the result.

## License

MIT; see [LICENSE](LICENSE). Use it, change it and share it freely. The
bundled font and data have their own (open) terms, listed under
[Where the data comes from](#where-the-data-comes-from).
