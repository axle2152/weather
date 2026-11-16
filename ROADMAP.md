# Roadmap

Bringing the 2020 version back to life. Checked items are done.

## 1. Data (done)

- [x] Settings in `config.toml` instead of hard-coded in the source
- [x] Location from a ZIP code, "City, ST" or lat/lon, anywhere in the US (offline lookup)
- [x] NWS office, grid, zones, county, radar and time zone found automatically from the location
- [x] Local Observations cities picked automatically (well spread, biggest towns first), or listed by hand
- [x] NWS requests send a User-Agent, time out and retry; last good data stays up during outages
- [x] Alert checking rewritten: home zone and county plus storm warnings near you. The 2020
      version cleared real warnings, missed watches, and only checked North Carolina.
- [x] Stale and incomplete station reports handled (fall back to recent reports and cloud codes)
- [x] Pressure trend from the last three hours of reports (no need to keep the app running for hours first)
- [x] Almanac in the location's time zone, with moon phases sorted by date

## 2. Radar (done)

- [x] Iowa Environmental Mesonet NEXRAD frames for exactly our map view, cached by time
- [x] Light clutter filtered out by dBZ (configurable)
- [x] Basemap built once per location: USGS shaded relief, land/water, state and county lines,
      Interstates, city labels
- [x] Warning polygons drawn on the radar
- [x] Falls back to the NWS loop GIF if IEM is unreachable (or `source = "nws"`)

## 3. Display (done)

- [x] pygame renderer at 1080p, 720p or 480p (or any size)
- [x] Your photos as backgrounds, rotating, with frosted-glass translucent panels
- [x] Slides: Current Conditions, Local Observations, 36-Hour, Extended, Almanac, Radar, Weather Bulletins
- [x] Bottom bar: conditions ticker, red warning crawl with beep
- [x] One clock (the 2020 version started a new clock timer every slide)
- [x] All network work on a background thread (Tk was being touched from other threads)
- [x] Bundled open-license font (Libre Franklin), so it looks the same on every computer
- [x] `--screenshots` mode for previewing without opening a window

## 4. More slides and screens (in progress)

- [x] 4:3 screens (e.g. 1024x768, 1440x1080), with layouts that adapt to the shape, and a
      resolution check so a bad value can't crash the app
- [x] Regional radar and satellite: cycle through US regions (Southeast, Midwest, Pacific
      Northwest and so on)
- [x] Regional map: current conditions and the forecast for cities from your region down to
      your area, as temperatures and icons on a map
- [x] Travel Cities: a slowly scrolling list of popular US cities with an icon, low and high
- [ ] 30-day outlook from the Climate Prediction Center (above/below normal temperature and
      precipitation for your area)

## 5. Ideas (not started)

- [ ] Almanac: normal and record highs and lows for today, plus yesterday's high, low and
      rainfall (NOAA ACIS, free, no key)
- [ ] Hourly forecast: a graph of temperature and rain chance for the next 12 to 24 hours
- [ ] Your Weekend: a Friday-to-Sunday forecast slide
- [ ] Severe weather outlook map (Storm Prediction Center), shown only when your area has a risk
- [ ] Tropical outlook (National Hurricane Center), shown only during hurricane season when
      something is brewing
- [ ] UV index (EPA, free), during the day
- [ ] Optional background music playlist in the app, with a separate track during bulletins
- [ ] Windows launcher: double-click to start, optional start with Windows
- [ ] Air quality (AirNow needs a free API key)

Not planned: built-in streaming. Use OBS or similar to capture the window.

## 6. Polish (later)

- [ ] Replace the NWS icons (their icon service is deprecated) with a sharper open-license set
- [ ] Pick a background photo by weather, season or time of day
- [ ] Short transitions between slides
- [x] Settings window (press S): separate from the display, applies changes by restarting it
- [x] Fixed-width clock digits, so the time doesn't shift as it ticks
- [ ] Optional metric units
