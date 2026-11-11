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

## 4. Streaming without OBS (next)

- [ ] Pipe frames straight into ffmpeg and send them to YouTube Live (RTMP)
- [ ] Music: loop a folder of tracks (e.g. from the YouTube Audio Library) under the video
- [ ] Mix the warning beep into the stream audio
- [ ] Headless mode (no window) and automatic restart, for running all day
- [ ] Stream key kept in `config.toml` (never committed)

## 5. Polish (later)

- [ ] Replace the NWS icons (their icon service is deprecated) with a sharper open-license set
- [ ] Pick a background photo by weather, season or time of day
- [ ] Short transitions between slides
- [ ] Hourly forecast or "Your Weekend" slide; air quality; regional temperature map
- [ ] Settings window instead of editing the file
- [ ] Optional metric units
