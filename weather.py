import PIL.Image
import PIL.ImageTk
import os
import requests
import tkinter as tk
import glob
import datetime
from time import strftime
import simpleaudio as sa
from apscheduler.schedulers.background import BackgroundScheduler
from lxml import html, etree

# For now going to manually assign the setting here in a dict. Plan on saving and loading these settings in a XML
# file in the future.

settings = {"resolution": "1280x720", "apptitle": "Weather Forecast Display alpha 1", "background_color": "#FF00FF",
            "panel_color": "#000000", "foreground_color": "#FFFFFF",
            "forecastZone": "NCZ061", "fireWeatherZone": "NCZ061", "latitude": 35.038,
            "longitude": -83.826, "apiurl": "https://api.weather.gov/", "font": "Franklin Gothic", "fontpts": 32,
            "radarurl": "https://radar.weather.gov/ridge/RadarImg/N0R/", "radar": "MRX", "radarurlXpath": "//tr",
            "radartopoImage": os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images'), 'MRX_Topo.png'),
            "cwd": os.path.dirname(os.path.abspath(__file__)), "gridX": 87, "gridY": 10, "nwsoffice": "MRX", "nwsname": "NWS Morristown TN",
            "useragent": {"User-Agent": "Weather Forecast Display alpha", "From": "axle86@fastmail.com"},
            "primary_wx_station": "KRHP", "primary_city": "Andrews",
            "wx_station_0": "KDZJ", "wx_city_0": "Blairsville",
            "wx_station_1": "K1A5", "wx_city_1": "Franklin",
            "wx_station_2": "KMMI", "wx_city_2": "Athens",
            "wx_station_3": "KTYS", "wx_city_3": "Knoxville",
            "wx_station_4": "KCEU", "wx_city_4": "Clemson",
            "wx_station_5": "KGVL", "wx_city_5": "Gainesville",
            "wx_station_6": "KRZR", "wx_city_6": "Cleveland",
            "wx_station_7": "KAND", "wx_city_7": "Anderson",
            "wx_station_8": "KAVL", "wx_city_8": "Asheville",
            "wx_station_9": "KCHA", "wx_city_9": "Chattanooga",
            "tabs": ['3c', '7.5c', '9.5c', '16c', '19c', '21c'], "warn_area": "NC",
            "county_codes": ['NCC039', 'NCC043', 'NCC075', 'NCC113', 'GAC281', 'GAC291', 'GAC111', 'GAC311', 'TNC011',
                             'TNC123', 'TNC009', 'TNC107'],
            "zone_codes": ['NCZ060', 'NCZ061', 'NCZ058', 'NCZ062', 'GAZ009', 'GAZ008', 'GAZ006', 'GAZ016', 'TNZ100',
                           'TNZ087', 'TNZ072', 'TNZ071', 'TNZ085', 'TNZ086']}

sched = BackgroundScheduler()


def convert_temp(temp_c):
    temp_f = int(temp_c * (9 / 5) + 32)
    return temp_f


def cardinaldir(winddirection):
    if 348.75 < winddirection <= 360:
        cardinaldirection = "N"
    if 0 <= winddirection <= 11.25:
        cardinaldirection = "N"
    if 11.25 < winddirection <= 33.75:
        cardinaldirection = "NNE"
    if 33.75 < winddirection <= 56.25:
        cardinaldirection = "NE"
    if 56.25 < winddirection <= 78.75:
        cardinaldirection = "ENE"
    if 78.75 < winddirection <= 101.25:
        cardinaldirection = "E"
    if 101.25 < winddirection <= 123.75:
        cardinaldirection = "ESE"
    if 123.75 < winddirection <= 146.25:
        cardinaldirection = "SE"
    if 146.25 < winddirection <= 168.75:
        cardinaldirection = "SSE"
    if 168.75 < winddirection <= 191.25:
        cardinaldirection = "S"
    if 191.25 < winddirection <= 213.75:
        cardinaldirection = "SSW"
    if 213.75 < winddirection <= 236.25:
        cardinaldirection = "SW"
    if 236.25 < winddirection <= 258.75:
        cardinaldirection = "WSW"
    if 258.25 < winddirection <= 281.25:
        cardinaldirection = "W"
    if 281.25 < winddirection <= 303.75:
        cardinaldirection = "WNW"
    if 303.75 < winddirection <= 326.25:
        cardinaldirection = "NW"
    if 326.25 < winddirection <= 348.75:
        cardinaldirection = "NNW"
    return cardinaldirection


def convert_speed(speed_kmh):
    speed_mph = int(float(speed_kmh) * 0.621371)
    return speed_mph


def convert_pressure(pascals):
    pressure = pascals * 0.0002953
    return pressure


def convert_visibility(meters):
    if meters > 404:  # use miles
        visibility = str(round(meters / 1609.34, 1)) + " Miles"
    elif meters < 404:  # use feet
        visibility = str(round(meters * 3.281, 1)) + "ft"
    return visibility


class MyApp:
    def warning_test(self):
        self.warning_status = True
        self.warning_text = "***This is a test of the warning ticker.*** There is not a weather warning in your area." \
                            " This software is primarily for entertainment only and should not be used as a primary " \
                            "source for weather information and warnings. Internet outages may cause warnings and " \
                            "other information not to display. Use a reliable source for weather information and " \
                            "warnings such as NOAA Weather Radio."
        sched.remove_job('warning_test')

    def radar_loop(self):
        self.topmessage = 'Doppler Radar'
        self.clock()
        self.extd0.pack_forget()
        self.extd1.pack_forget()
        self.extd2.pack_forget()
        self.extd3.pack_forget()
        self.fcasttext.pack(side=tk.TOP, fill=tk.X, padx=50, pady=20)
        self.fcasttext.delete('1.0', tk.END)
        self.fcasttext.tag_config('radar', justify='center')
        self.loops = 0
        self.frames = 0

        def animate():
            self.fcasttext.delete('1.0', tk.END)
            try:
                self.fcasttext.image_create(tk.END, image=self.radar_images[self.frames])
                self.fcasttext.tag_add('radar', '1.0', tk.END)
                #  print(self.loops, self.frames)
                self.frames += 1
                if self.frames == len(self.radar_images):
                    self.frames = 0
                    self.loops += 1
                    if self.loops < 4:
                        self.fcasttext.after(4000, animate)
                    else:
                        self.fcasttext.after(4000, self.forecast_loop)
                else:
                    self.fcasttext.after(60, animate)
            except IndexError:
                print('Index error on radar')
                self.fcasttext.insert(tk.END, 'Doppler Radar Temporarily Unavailable')
                self.fcasttext.after(4000, self.forecast_loop)
        animate()

    def radar_download(self):
        url = settings['radarurl'] + settings['radar'] + '/'
        page = requests.get(url)
        elements = []
        filelist = []
        self.frame_timestamp = []
        self.radar_images = []

        def build_lxml_tree(_html):
            tree = html.fromstring(_html.text)
            tree = etree.ElementTree(tree)
            return tree
        tree = build_lxml_tree(page)
        result = tree.xpath("//table")
        for r in range(len(result)):
            element = str(result[r].text_content()).split('gif')
        for e in range(len(element)):
            elements += str(element[e]).split('\n')
        for e in range(0, len(elements),2):
            if not os.path.exists(os.path.join(os.path.join(settings['cwd'], 'radar'), elements[e] + 'ren.png')):
                with open(os.path.join(os.path.join(settings['cwd'], 'radar'), elements[e] + 'gif'), 'wb') as handle:
                    gifurl = url + elements[e] + 'gif'
                    response = requests.get(gifurl, stream=True)
                    if not response.ok:
                        print(response, gifurl)
                    for block in response.iter_content(1024):
                        if not block:
                            break
                        handle.write(block)
                print('downloaded ' + elements[e] + 'gif')
            else:
                pass  # we could print a success here
            filelist.append(elements[e])
        print('now converting...')
        for file in filelist:
            try:
                newfile = file + 'ren.png'
                if not os.path.exists(os.path.join(os.path.join(settings['cwd'], 'radar'), newfile)):
                    background_radar = PIL.Image.open(settings['radartopoImage'])
                    img = PIL.Image.open(os.path.join(os.path.join(settings['cwd'], 'radar'), file + 'gif'))
                    # transparency = img.info['transparency']
                    img = PIL.Image.alpha_composite(background_radar.convert('RGBA'), img.convert('RGBA'))
                    img = img.crop((0, 240, 600, 550))
                    img = img.resize((900, 555), PIL.Image.ANTIALIAS)
                    img.save(os.path.join(os.path.join(settings['cwd'], 'radar'), newfile))
                else:
                    pass  # we could print a success here
            except PIL.UnidentifiedImageError:
                print(file + ' appears to be corrupt')
            except FileNotFoundError:
                print(file + ' not found')
            except AttributeError:
                print('attribute error ' + file)
        for f in range(len(filelist)):
            try:
                img = PIL.Image.open(os.path.join(os.path.join(settings['cwd'], 'radar'), filelist[f] + 'ren.png'))
                self.radar_images.append(PIL.ImageTk.PhotoImage(img))
            except FileNotFoundError:
                print(filelist[f] + ' not found')
            except OSError:
                print('image is truncated ' + str(filelist[f]))
        print('cleaning up...')
        for f in filelist:
            try:
                os.remove(os.path.join(os.path.join(settings['cwd'], 'radar'), f + 'gif'))
            except FileNotFoundError:
                print('could not remove ' + os.path.join(os.path.join(settings['cwd'], 'radar'), f + 'gif'))
        del_list = []
        dirlist = glob.glob('radar/*')
        for item in dirlist:
            if datetime.datetime.fromtimestamp(os.path.getmtime(settings['cwd'] + '\\' + item)) < \
                    datetime.datetime.now() - datetime.timedelta(hours=4):
                del_list.append(item)
        for d in del_list:
            try:
                os.remove(os.path.join(os.path.dirname(os.path.abspath(__file__)), d))
                print('removed ' + d)
            except FileNotFoundError:
                print('could not remove ' + str(os.path.join(os.path.dirname(os.path.abspath(__file__)), '\\' + d)))

    def forecast_loop(self):
        def extended_loop():
            self.fcasttext.pack_forget()
            self.topmessage = 'The Extended Forecast'
            self.clock()
            self.extd0.delete('1.0', tk.END)
            self.extd1.delete('1.0', tk.END)
            self.extd2.delete('1.0', tk.END)
            self.extd3.delete('1.0', tk.END)
            self.extd0.pack(side=tk.LEFT, fill=tk.BOTH, padx=20, pady=20, expand=1)
            self.extd1.pack(side=tk.LEFT, fill=tk.BOTH, padx=20, pady=20, expand=1)
            self.extd2.pack(side=tk.LEFT, fill=tk.BOTH, padx=20, pady=20, expand=1)
            self.extd3.pack(side=tk.LEFT, fill=tk.BOTH, padx=20, pady=20, expand=1)
            try:
                if not self.areaforecast['properties']['periods'][6]['isDaytime']:
                    try:
                        self.extd0.insert(tk.END,
                                          str(self.areaforecast['properties']['periods'][7]['name'])[:12] + '\n')
                        self.extd0.image_create(tk.END, image=self.icons[7])
                        lo_temp = str(self.areaforecast['properties']['periods'][6]['temperature']) + '°F'
                        hi_temp = str(self.areaforecast['properties']['periods'][7]['temperature']) + '°F'
                        wind_dir = self.areaforecast['properties']['periods'][7]['windDirection']
                        wind_speed = self.areaforecast['properties']['periods'][7]['windSpeed']
                        self.extd0.insert(tk.END, '\n\nHi: ' + hi_temp)
                        self.extd0.insert(tk.END, '\nLo: ' + lo_temp)
                        self.extd0.insert(tk.END, '\nWinds ' + wind_dir)
                        self.extd0.insert(tk.END, '\n' + wind_speed)
                    except IndexError:
                        self.extd0.insert(tk.END, 'Unavailable')
                    try:
                        self.extd1.insert(tk.END,
                                          str(self.areaforecast['properties']['periods'][9]['name'])[:12] + '\n')
                        self.extd1.image_create(tk.END, image=self.icons[9])
                        lo_temp = str(self.areaforecast['properties']['periods'][8]['temperature']) + '°F'
                        hi_temp = str(self.areaforecast['properties']['periods'][9]['temperature']) + '°F'
                        wind_dir = self.areaforecast['properties']['periods'][9]['windDirection']
                        wind_speed = self.areaforecast['properties']['periods'][9]['windSpeed']
                        self.extd1.insert(tk.END, '\n\nHi: ' + hi_temp)
                        self.extd1.insert(tk.END, '\nLo: ' + lo_temp)
                        self.extd1.insert(tk.END, '\nWinds ' + wind_dir)
                        self.extd1.insert(tk.END, '\n' + wind_speed)
                    except IndexError:
                        self.extd1.insert(tk.END, 'Unavailable')
                    try:
                        self.extd2.insert(tk.END,
                                          str(self.areaforecast['properties']['periods'][11]['name'])[:12] + '\n')
                        self.extd2.image_create(tk.END, image=self.icons[11])
                        lo_temp = str(self.areaforecast['properties']['periods'][10]['temperature']) + '°F'
                        hi_temp = str(self.areaforecast['properties']['periods'][11]['temperature']) + '°F'
                        wind_dir = self.areaforecast['properties']['periods'][11]['windDirection']
                        wind_speed = self.areaforecast['properties']['periods'][11]['windSpeed']
                        self.extd2.insert(tk.END, '\n\nHi: ' + hi_temp)
                        self.extd2.insert(tk.END, '\nLo: ' + lo_temp)
                        self.extd2.insert(tk.END, '\nWinds ' + wind_dir)
                        self.extd2.insert(tk.END, '\n' + wind_speed)
                    except IndexError:
                        self.extd2.insert(tk.END, 'Unavailable')
                    try:
                        self.extd3.insert(tk.END,
                                          str(self.areaforecast['properties']['periods'][13]['name'])[:12] + '\n')
                        self.extd3.image_create(tk.END, image=self.icons[13])
                        lo_temp = str(self.areaforecast['properties']['periods'][12]['temperature']) + '°F'
                        hi_temp = str(self.areaforecast['properties']['periods'][13]['temperature']) + '°F'
                        wind_dir = self.areaforecast['properties']['periods'][13]['windDirection']
                        wind_speed = self.areaforecast['properties']['periods'][13]['windSpeed']
                        self.extd3.insert(tk.END, '\n\nHi: ' + hi_temp)
                        self.extd3.insert(tk.END, '\nLo: ' + lo_temp)
                        self.extd3.insert(tk.END, '\nWinds ' + wind_dir)
                        self.extd3.insert(tk.END, '\n' + wind_speed)
                    except IndexError:
                        self.extd3.insert(tk.END, 'Unavailable')
                        print(len(self.icons))
                else:
                    try:
                        self.extd0.insert(tk.END, self.areaforecast['properties']['periods'][6]['name'][:12] + '\n')
                        self.extd0.image_create(tk.END, image=self.icons[6])
                        lo_temp = str(self.areaforecast['properties']['periods'][7]['temperature']) + '°F'
                        hi_temp = str(self.areaforecast['properties']['periods'][6]['temperature']) + '°F'
                        wind_dir = self.areaforecast['properties']['periods'][6]['windDirection']
                        wind_speed = self.areaforecast['properties']['periods'][6]['windSpeed']
                        self.extd0.insert(tk.END, '\n\nHi: ' + hi_temp)
                        self.extd0.insert(tk.END, '\nLo: ' + lo_temp)
                        self.extd0.insert(tk.END, '\nWinds ' + wind_dir)
                        self.extd0.insert(tk.END, '\n' + wind_speed)
                    except IndexError:
                        self.extd0.insert(tk.END, 'Unavailable')
                    try:
                        self.extd1.insert(tk.END,
                                          str(self.areaforecast['properties']['periods'][8]['name'])[:12] + '\n')
                        self.extd1.image_create(tk.END, image=self.icons[8])
                        lo_temp = str(self.areaforecast['properties']['periods'][9]['temperature']) + '°F'
                        hi_temp = str(self.areaforecast['properties']['periods'][8]['temperature']) + '°F'
                        wind_dir = self.areaforecast['properties']['periods'][8]['windDirection']
                        wind_speed = self.areaforecast['properties']['periods'][8]['windSpeed']
                        self.extd1.insert(tk.END, '\n\nHi: ' + hi_temp)
                        self.extd1.insert(tk.END, '\nLo: ' + lo_temp)
                        self.extd1.insert(tk.END, '\nWinds ' + wind_dir)
                        self.extd1.insert(tk.END, '\n' + wind_speed)
                    except IndexError:
                        self.extd1.insert(tk.END, 'Unavailable')
                    try:
                        self.extd2.insert(tk.END,
                                          str(self.areaforecast['properties']['periods'][10]['name'])[:12] + '\n')
                        self.extd2.image_create(tk.END, image=self.icons[10])
                        lo_temp = str(self.areaforecast['properties']['periods'][9]['temperature']) + '°F'
                        hi_temp = str(self.areaforecast['properties']['periods'][10]['temperature']) + '°F'
                        wind_dir = self.areaforecast['properties']['periods'][10]['windDirection']
                        wind_speed = self.areaforecast['properties']['periods'][10]['windSpeed']
                        self.extd2.insert(tk.END, '\n\nHi: ' + hi_temp)
                        self.extd2.insert(tk.END, '\nLo: ' + lo_temp)
                        self.extd2.insert(tk.END, '\nWinds ' + wind_dir)
                        self.extd2.insert(tk.END, '\n' + wind_speed)
                    except IndexError:
                        self.extd2.insert(tk.END, 'Unavailable')
                    try:
                        self.extd3.insert(tk.END,
                                          str(self.areaforecast['properties']['periods'][12]['name'])[:12] + '\n')
                        self.extd3.image_create(tk.END, image=self.icons[12])
                        lo_temp = str(self.areaforecast['properties']['periods'][11]['temperature']) + '°F'
                        hi_temp = str(self.areaforecast['properties']['periods'][12]['temperature']) + '°F'
                        wind_dir = self.areaforecast['properties']['periods'][12]['windDirection']
                        wind_speed = self.areaforecast['properties']['periods'][12]['windSpeed']
                        self.extd3.insert(tk.END, '\n\nHi: ' + hi_temp)
                        self.extd3.insert(tk.END, '\nLo: ' + lo_temp)
                        self.extd3.insert(tk.END, '\nWinds ' + wind_dir)
                        self.extd3.insert(tk.END, '\n' + wind_speed)
                    except IndexError:
                        self.extd3.insert(tk.END, 'Unavailable-2')
                self.extd0.tag_configure("center", justify='center')
                self.extd0.tag_configure("left", justify='left')
                self.extd0.tag_add('center', '1.0', '3.0')
                self.extd0.tag_add('left', '3.0', tk.END)
                self.extd1.tag_configure("center", justify='center')
                self.extd1.tag_configure('left', justify='left')
                self.extd1.tag_add('center', '1.0', '3.0')
                self.extd1.tag_add('left', '3.0', tk.END)
                self.extd2.tag_configure("center", justify='center')
                self.extd2.tag_configure('left', justify='left')
                self.extd2.tag_add('center', '1.0', '3.0')
                self.extd2.tag_add('left', '3.0', tk.END)
                self.extd3.tag_configure("center", justify='center')
                self.extd3.tag_configure('left', justify='left')
                self.extd3.tag_add('center', '1.0', '3.0')
                self.extd3.tag_add('left', '3.0', tk.END)
                self.fcasttext.after(12000, self.radar_loop)
            except TypeError:
                print('Type Error, can\'t show the extended forecast')
                self.extd0.insert(tk.END, 'Unavailable')
                self.extd1.insert(tk.END, 'Unavailable')
                self.extd2.insert(tk.END, 'Unavailable')
                self.extd3.insert(tk.END, 'Unavailable')
                self.extd0.tag_configure("center", justify='center')
                self.extd0.tag_configure("left", justify='left')
                self.extd0.tag_add('center', '1.0', '3.0')
                self.extd0.tag_add('left', '3.0', tk.END)
                self.extd1.tag_configure("center", justify='center')
                self.extd1.tag_configure('left', justify='left')
                self.extd1.tag_add('center', '1.0', '3.0')
                self.extd1.tag_add('left', '3.0', tk.END)
                self.extd2.tag_configure("center", justify='center')
                self.extd2.tag_configure('left', justify='left')
                self.extd2.tag_add('center', '1.0', '3.0')
                self.extd2.tag_add('left', '3.0', tk.END)
                self.extd3.tag_configure("center", justify='center')
                self.extd3.tag_configure('left', justify='left')
                self.extd3.tag_add('center', '1.0', '3.0')
                self.extd3.tag_add('left', '3.0', tk.END)
                self.fcasttext.after(12000, self.radar_loop)

        def observation_loop():
            self.topmessage = 'Local Observations'
            self.clock()
            self.fcasttext.delete('1.0', tk.END)
            obs_city_list = [settings['wx_city_0'], settings['wx_city_1'], settings['wx_city_2'],
                             settings['wx_city_3'], settings['wx_city_4'], settings['wx_city_5'],
                             settings['wx_city_6'], settings['wx_city_7'], settings['wx_city_8'],
                             settings['wx_city_9']]
            for i in range(0, 10):
                try:
                    if self.observations[i] is not None:
                        self.fcasttext.insert(tk.END, obs_city_list[i] + '\t\t')
                        try:
                            self.fcasttext.image_create(tk.END, image=self.obsicons[i])
                        except IndexError:
                            img = PIL.Image.open(os.path.join(os.path.join(settings['cwd'], 'images'), 'not_found.png'))
                            img = img.resize((50, 50), PIL.Image.ANTIALIAS)
                            img = PIL.ImageTk.PhotoImage(img)
                            self.fcasttext.image_create(tk.END, image=img)
                        if self.observations[i]['properties']['temperature']['value'] is not None:
                            temp = str(convert_temp(self.observations[i]['properties']['temperature']['value'])) + "°F"
                        else:
                            temp = 'N/A  '
                        if self.observations[i]['properties']['windDirection']['value'] is not None and \
                                self.observations[i]['properties']['windSpeed']['value'] is not None:
                            if self.observations[i]['properties']['windSpeed']['value'] == 0:
                                winds = "Calm"
                            else:
                                cardinal = cardinaldir(self.observations[i]['properties']['windDirection']['value'])
                                winds = str(convert_speed(self.observations[i]['properties']['windSpeed']['value']))
                                winds = cardinal + ' at ' + winds
                                if self.observations[i]['properties']['windGust']['value'] is not None:
                                    gusts = str(convert_speed(self.observations[i]['properties']['windGust']['value']))
                                    winds += ' Gusts to ' + gusts
                        else:
                            winds = 'No Report'
                        self.fcasttext.insert(tk.END, '\t' + temp + '\t' + winds + '\n')
                        # self.fcasttext.insert(tk.END, condition[:13] + '\t\t' + temp + '\t' + winds + '\n')
                    else:
                        self.fcasttext.insert(tk.END, obs_city_list[i] + '\t\tNo Report\n')
                except IndexError:
                    print('index error on ' + str(obs_city_list[i]))
                    self.fcasttext.insert(tk.END, obs_city_list[i] + '\t\tNo Report\n')
            self.fcasttext.after(12000, extended_loop)

        def advisory_loop():
            self.extd0.pack_forget()
            self.extd1.pack_forget()
            self.extd2.pack_forget()
            self.extd3.pack_forget()
            self.fcasttext.pack(side=tk.TOP, fill=tk.X, padx=50, pady=20)
            self.fcasttext.delete('1.0', tk.END)
            self.topmessage = 'Special Weather Statement'
            self.clock()
            advisory_message = self.advisory_text.split('\n')

            def page1():
                if len(advisory_message) >= 9:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[:9]).strip('[]{}')
                                          .replace("\'", "").replace(',,', ',').replace(', ,', ' ').replace('.,', '.'))
                    self.fcasttext.after(12000, page2)
                elif len(advisory_message) < 9:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,', ' ').replace('.,', '.'))
                    self.fcasttext.after(12000, forecast_loop_1)

            def page2():
                if len(advisory_message) >= 18:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[9:18])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, page3)
                elif len(advisory_message) < 18:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[9:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)

            def page3():
                if len(advisory_message) >= 27:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[19:27])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, page4)
                elif len(advisory_message) < 27:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[19:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)

            def page4():
                if len(advisory_message) >= 36:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[28:36])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, page5)
                elif len(advisory_message) < 36:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[28:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)


            def page5():
                if len(advisory_message) >= 45:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[37:45])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, page6)
                elif len(advisory_message) < 45:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[37:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)

            def page6():
                if len(advisory_message) >= 54:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[46:54])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, page7)
                elif len(advisory_message) < 54:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[46:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)

            def page7():
                if len(advisory_message) >= 63:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[55:63])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, page8)
                elif len(advisory_message) < 63:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[55:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)

            def page8():
                if len(advisory_message) >= 72:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[64:72])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, page9)
                elif len(advisory_message) < 72:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[64:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)

            def page9():
                if len(advisory_message) >= 73:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[73:73])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, page10)
                elif len(advisory_message) < 73:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[73:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)

            def page10():
                if len(advisory_message) >= 90:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[82:90])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)
                elif len(advisory_message) < 90:
                    self.fcasttext.delete('1.0', tk.END)
                    self.fcasttext.insert(tk.END,
                                          str(advisory_message[82:len(advisory_message)])
                                          .strip('[]{}').replace("\'", "").replace(',,',',')
                                          .replace(', ,',' ').replace('.,','.'))
                    self.fcasttext.after(12000, forecast_loop_1)
            page1()

        def forecast_loop_6():
            self.fcasttext.delete('1.0', tk.END)
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][5]['name'] + ',\n\t')
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][5]['detailedForecast'])
            self.fcasttext.after(12000, observation_loop)  # we'll change

        def forecast_loop_5():
            self.fcasttext.delete('1.0', tk.END)
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][4]['name'] + ',\n\t')
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][4]['detailedForecast'])
            self.fcasttext.after(12000, forecast_loop_6)

        def forecast_loop_4():
            self.fcasttext.delete('1.0', tk.END)
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][3]['name'] + ',\n\t')
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][3]['detailedForecast'])
            self.fcasttext.after(12000, forecast_loop_5)

        def forecast_loop_3():
            self.fcasttext.delete('1.0', tk.END)
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][2]['name'] + ',\n\t')
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][2]['detailedForecast'])
            self.fcasttext.after(12000, forecast_loop_4)

        def forecast_loop_2():
            self.fcasttext.delete('1.0', tk.END)
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][1]['name'] + ',\n\t')
            self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][1]['detailedForecast'])
            self.fcasttext.after(12000, forecast_loop_3)

        def forecast_loop_1():
            self.topmessage = "The 36 Hour Forecast"
            self.clock()
            self.fcasttext.delete('1.0', tk.END)
            if self.areaforecast is not None:
                self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][0]['name'] + ',\n\t')
                self.fcasttext.insert(tk.END, self.areaforecast['properties']['periods'][0]['detailedForecast'])
                self.fcasttext.after(12000, forecast_loop_2)
            else:
                self.fcasttext.insert(tk.END, "Forecast Not Available")
                self.fcasttext.after(12000, observation_loop)
        self.extd0.pack_forget()
        self.extd1.pack_forget()
        self.extd2.pack_forget()
        self.extd3.pack_forget()
        self.fcasttext.pack(side=tk.TOP, fill=tk.X, padx=50, pady=20)
        if self.advisory_status == True:
            print('there is an advisory, entering the advisory loop')
            advisory_loop()
        else:
            forecast_loop_1()

    def warning_check(self):
        if self.warning_status:
            if self.isMarqueeRunning:
                pass
            else:
                self.ldtext.pack_forget()
                self.marquee()

    def last_pressure_record(self):
        # run this every 3 hours
        print('recording pressure history')
        if self.pressure is not None:
            self.last_pressure = self.pressure

    def ldloop(self):
        def ldreset():
            if not self.isMarqueeRunning:
                try:
                    self.mkcanvas.pack_forget()
                except RuntimeError:
                    print('There was a runtime error')
                    pass
                self.ldtext.delete('1.0', tk.END)
                self.ldtext.pack(side=tk.TOP, padx=0, pady=0)
                slide_1()
            else:
                self.ldtext.delete('1.0', tk.END)

        def slide_8():
            self.warning_check()
            self.ldtext.delete('1.0', tk.END)
            try:
                if self.observations[10]['properties']['visibility']['value'] is not None:
                    visibility = convert_visibility(self.observations[10]['properties']['visibility']['value'])
                    self.ldtext.insert(tk.END, "Visibility: " + visibility)
                    self.ldtext.after(6000, ldreset)
                else:
                    self.ldtext.insert(tk.END, "Visibility: N/A")
                    self.ldtext.after(6000, ldreset)
            except IndexError:
                self.ldtext.insert(tk.END, 'Visibility: N/A')
                self.ldtext.after(6000, ldreset)

        def slide_7():
            self.warning_check()
            self.ldtext.delete('1.0', tk.END)
            try:
                if self.observations[10]['properties']['heatIndex']['value'] is not None:
                    heatindex = convert_temp(self.observations[10]['properties']['heatIndex']['value'])
                    self.ldtext.insert(tk.END, 'Heat Index: ' + str(heatindex) + '°F')
                    self.ldtext.after(6000, slide_8)
                elif self.observations[10]['properties']['windChill']['value'] is not None:
                    windchill = convert_temp(self.observations[10]['properties']['windChill']['value'])
                    self.ldtext.insert(tk.END, 'Wind Chill: ' + str(windchill) + '°F')
                    self.ldtext.after(6000, slide_8)
                else:
                    slide_8()
            except IndexError:
                slide_8()

        def slide_6():
            self.warning_check()
            self.ldtext.delete('1.0', tk.END)
            try:
                if self.observations[10]['properties']['barometricPressure']['value'] is not None:
                    self.pressure = convert_pressure(self.observations[10]['properties']['barometricPressure']['value'])
                    self.ldtext.insert(tk.END, "Barometric Pressure: " + str(round(self.pressure, 2)) + " in")
                    if self.last_pressure is not None:
                        if abs(self.last_pressure - self.pressure) <= 0.003:  # we will schedule a job to record the
                            self.ldtext.insert(tk.END, ' and Steady')  # pressure every 3 hours so that we can
                        elif self.pressure - self.last_pressure > 0.003:  # determine if the pressure is rising or
                            self.ldtext.insert(tk.END, ' and Rising')  # falling. Not sure how well it will work
                        else:  # since the program will need to be stable
                            self.ldtext.insert(tk.END, ' and Falling')
                    self.ldtext.after(6000, slide_7)
                else:
                    self.ldtext.insert(tk.END, 'Barometric Pressure: Not Reported')
                    self.ldtext.after(6000, slide_7)
            except IndexError:
                self.ldtext.insert(tk.END, "Barometirc Pressure: Not Reported")
                self.ldtext.after(6000, slide_7)

        def slide_5():  # displays the winds and gusts
            self.warning_check()
            self.ldtext.delete('1.0', tk.END)
            try:
                if self.observations[10]['properties']['windSpeed']['value'] is not None and \
                        self.observations[10]['properties']['windDirection']['value'] is not None:
                    cardinal = cardinaldir(self.observations[10]['properties']['windDirection']['value'])
                    winds = convert_speed(self.observations[10]['properties']['windSpeed']['value'])
                    if winds == 0:
                        self.ldtext.insert(tk.END, 'Winds: Calm')
                    else:
                        self.ldtext.insert(tk.END, 'Winds: ' + cardinal + " at " + str(winds) + " MPH")
                    if self.observations[10]['properties']['windGust']['value'] is not None:
                        gusts = convert_speed(self.observations[10]['properties']['windGust']['value'])
                        self.ldtext.insert(tk.END, "|\tGusts to " + str(gusts) + " MPH")
                    self.ldtext.after(6000, slide_6)
                else:
                    self.ldtext.insert(tk.END, 'Winds: Not Reported')
                    self.ldtext.after(6000, slide_6)
            except IndexError:
                self.ldtext.insert(tk.END, 'Winds: Not Reported')
                self.ldtext.after(6000, slide_6)

        def slide_4():  # displays the dewpoint in F and humidity
            self.warning_check()
            self.ldtext.delete('1.0', tk.END)
            try:
                if self.observations[10]['properties']['dewpoint']['value'] is not None:
                    dewpoint = convert_temp(self.observations[10]['properties']['dewpoint']['value'])
                    self.ldtext.insert(tk.END, 'Dewpoint: ' + str(dewpoint) + '°F  |  ')
                else:
                    self.ldtext.insert(tk.END, 'Dewpoint: N/A  |  ')
            except IndexError:
                self.ldtext.insert(tk.END, 'Dewpoint: N/A  |  ')
            try:
                if self.observations[10]['properties']['relativeHumidity']['value'] is not None:
                    humidity = int(self.observations[10]['properties']['relativeHumidity']['value'])
                    self.ldtext.insert(tk.END, 'Humidity: ' + str(humidity) + '%')
                    self.ldtext.after(6000, slide_5)
                else:
                    self.ldtext.insert(tk.END, 'Humidity: N/A')
                    self.ldtext.after(6000, slide_5)
            except IndexError:
                self.ldtext.insert(tk.END, 'Humidity: N/A')
                self.ldtext.after(6000, slide_5)

        def slide_3():  # displays the temperature in F
            self.warning_check()
            self.ldtext.delete('1.0', tk.END)
            try:
                if self.observations[10]['properties']['temperature']['value'] is not None:
                    temp = convert_temp(self.observations[10]['properties']['temperature']['value'])
                    self.ldtext.insert(tk.END, 'Temp: ' + str(temp) + '°F')
                    self.ldtext.after(6000, slide_4)
                else:
                    self.ldtext.insert(tk.END, 'Temp: N/A')
                    self.ldtext.after(6000, slide_4)
            except IndexError:
                self.ldtext.insert(tk.END, 'Temp: Not Reported')
                self.ldtext.after(6000, slide_4)

        def slide_2():  # displays the sky conditions
            self.warning_check()
            self.ldtext.delete('1.0', tk.END)
            try:
                if self.observations[10]['properties']['textDescription'] is not None:
                    condition = self.observations[10]['properties']['textDescription']
                    self.ldtext.insert(tk.END, condition)
                else:
                    self.ldtext.insert('Condition Not Reported')
                self.ldtext.after(6000, slide_3)
            except:
                self.ldtext.insert(tk.END, "No Report 2")
                self.ldtext.after(6000, slide_1)

        def slide_1():  # just displays conditions at whatever city
            self.warning_check()
            self.ldtext.delete('1.0', tk.END)
            self.ldtext.insert(tk.END, 'Conditions at ' + settings['primary_city'])
            self.ldtext.after(6000, slide_2)

        ldreset()

    def checkalerts(self):
        warn_list = settings['county_codes'] + settings['zone_codes']
        attempts = 0
        print('Checking for alerts...')
        url = settings['apiurl'] + 'alerts/active?area=' + settings['warn_area']
        while attempts < 3:
            response = requests.get(url)
            if response.ok:
                attempts = 4
            if not response.ok:
                attempts += 1
                print('Unable to check for alerts... status code ' + str(response.status_code))
        if response.ok:
            alerts = response.json()
            self.warning_text = ""
            self.isMarqueeRunning = False
            self.advisory_text = ""
            for a in range(len(alerts['features'])):
                if alerts['features'][a]['properties']['severity'] == "Severe" \
                        and alerts['features'][a]['properties']['urgency'] == "Immediate" \
                        and any(b in alerts['features'][a]['properties']['geocode']['UGC'] for b in warn_list):
                    self.warning_text += alerts['features'][a]['properties']['description'] + '\t'
                    self.warning_text = self.warning_text.replace('\n', ' ')
                    self.warning_status = True
                    self.isMarqueeRunning = True
                elif alerts['features'][a]['properties']['severity'] != "Severe" \
                        and alerts['features'][a]['properties']['urgency'] != "Immediate" \
                        and alerts['features'][a]['properties']['senderName'] == settings["nwsname"] \
                        and any(b in alerts['features'][a]['properties']['geocode']['UGC'] for b in warn_list):
                    self.advisory_text += alerts['features'][a]['properties']['headline'] + "\n"
                    self.advisory_text += alerts['features'][a]['properties']['description'] + '\n'
                    self.advisory_status = True
                else:
                    self.warning_status = False
                    self.warning_text = ""
                    self.advisory_status = False
                    self.advisory_text = ""
        elif not response.ok:
            if self.warning_text:
                print('Warning Status is true, but could not check for updated alerts')
            if self.advisory_status:
                print('Advisory Status is true, but could not check for updated alerts')
            print('Got a bad response when checking for alerts')
        if self.warning_status:
            sched.reschedule_job('check_alerts', trigger='interval', minutes=2)
            print('Warning Active')
        elif self.advisory_status:
            sched.reschedule_job('check_alerts', trigger='interval', minutes=5)
            print('Advisory Active')
        else:
            sched.reschedule_job('check_alerts', trigger='interval', minutes=10)
            if not self.ldtext.winfo_ismapped():
                self.ldtext.pack(side=tk.TOP, padx=0, pady=0)
                self.ldloop()
            print('No Warning or Advisory Active')

            # the behavior is if the was a warning or advisory and we could not check the api we keep displaying the
            # message until we can and the alert is removed. Ideally we need to track each warning and advisory and
            # only continue to display it as long as it is valid
            # for the scheduler, if there is a thunderstorm warning for example we will check for updates every 2
            # minutes. If there is a thunderstorm watch, or a wind advisory we will check for updates every 5 minutes
            # the default frequency is 15 minutes.

    def mkanimate(self):
        (self.x0, self.y0, self.x1, self.y1) = self.mkcanvas.bbox("text")
        if self.x1 < 0 or self.y0 < 0:
            self.x0 = self.mkcanvas.winfo_width()
            self.y0 = int(self.mkcanvas.winfo_height() / 2)
            self.mkcanvas.coords("text", self.x0, self.y0)
            try:
                play_obj = self.beep.play()
            except:
                print('could not play beep, make sure you have an audio device')
        else:
            self.mkcanvas.move("text", -2, 0)
            # print("animating! " + str(self.x0) + "," + str(self.y0) + "," + str(self.x1) + ", " + str(self.y1))
        if self.warning_status == True:
            self.mkcanvas.after(13, self.mkanimate)
        else:
            self.mkcanvas.pack_forget()
            self.ldtext.pack(side=tk.TOP, padx=0, pady=0)

    def marquee(self):
        print('the warning marquee is now running')
        self.isMarqueeRunning = True
        self.mkcanvas.pack(side=tk.BOTTOM, fill=tk.X, pady=0)
        self.mkcanvas.create_text(0, -1000, text=self.warning_text, anchor=tk.W, tags=("text",),
                                  font=('Franklin Gothic', 32), fill='#ffffff')
        (self.x0, self.y0, self.x1, self.y1) = self.mkcanvas.bbox("text")
        width = 1280
        height = 50
        self.mkcanvas.configure(width=width, height=height)
        self.mkanimate()

    def getobservations(self):
        print('Getting Observations for...')
        self.obsicons = []
        self.observations = []
        obs_station_list = [settings.get('wx_station_0'), settings.get('wx_station_1'), settings.get('wx_station_2'),
                            settings.get('wx_station_3'), settings.get('wx_station_4'), settings.get('wx_station_5'),
                            settings.get('wx_station_6'), settings.get('wx_station_7'), settings.get('wx_station_8'),
                            settings.get('wx_station_9'), settings.get('primary_wx_station')]
        obs_city_list = [settings.get('wx_city_0'), settings.get('wx_city_1'), settings.get('wx_city_2'),
                         settings.get('wx_city_3'), settings.get('wx_city_4'), settings.get('wx_city_5'),
                         settings.get('wx_city_6'), settings.get('wx_city_7'), settings.get('wx_city_8'),
                         settings.get('wx_city_9'), settings.get('primary_city')]
        for o in range(len(obs_station_list)):
            if obs_station_list[o] is not None:
                url = settings['apiurl'] + "stations/" + obs_station_list[o] + "/observations/latest"
                attempts = 0
                while attempts < 3:
                    try:
                        observation = requests.get(url, headers=settings['useragent'])
                        print(obs_city_list[o] + " Status: " + str(observation.status_code))
                        if observation.ok:
                            attempts = 4
                        else:
                            attempts += 1
                    except:
                        attempts += 1
                if observation.ok:
                    observation = observation.json()
                    self.observations.insert(o, observation)
                else:
                    self.observations.insert(o, None)
        try:
            for i in range(len(self.observations)):
                try:
                    url = str(self.observations[i]['properties']['icon'])
                    with open(os.path.join(os.path.join(settings['cwd'], 'images'), 'obs' + str(i) + '.png'), 'wb') as handle:
                        response = requests.get(url, stream=True)
                        if not response.ok:
                            print(response)
                        for block in response.iter_content(1024):
                            if not block:
                                break
                            handle.write(block)
                    img = PIL.Image.open(os.path.join(os.path.join(settings['cwd'], 'images'), 'obs' + str(i) + '.png'))
                    img = img.resize((50, 50), PIL.Image.ANTIALIAS)
                    img = PIL.ImageTk.PhotoImage(img)
                    self.obsicons.append(img)
                except:
                    print('Index Error, skipping')
                    img = PIL.Image.open(os.path.join(os.path.join(settings['cwd'], 'images'), 'not_found.png'))
                    img = img.resize((50, 50), PIL.Image.ANTIALIAS)
                    img = PIL.ImageTk.PhotoImage(img)
                    self.obsicons.append(img)
                try:
                    if not response.ok:
                        img = PIL.Image.open(os.path.join(os.path.join(settings['cwd'], 'images'), 'not_found.png'))
                        img = img.resize((50, 50), PIL.Image.ANTIALIAS)
                        img = PIL.ImageTk.PhotoImage(img)
                        self.obsicons.append(img)
                except UnboundLocalError:
                    img = PIL.Image.open(os.path.join(os.path.join(settings['cwd'], 'images'), 'not_found.png'))
                    img = img.resize((50, 50), PIL.Image.ANTIALIAS)
                    img = PIL.ImageTk.PhotoImage(img)
                    self.obsicons.append(img)
        except TypeError:
            print('Type error, did not get any observations')

    def getforecast(self):
        print('Getting Forecast...')

        def geticons():
            path = os.path.join(settings['cwd'], "images")
            self.icons = []
            print('generating icons...')
            for p in range(0, 14):
                try:
                    icon_url = self.areaforecast['properties']['periods'][p]['icon']
                    filename = "period" + str(p) + "_icon.png"
                    with open(os.path.join(path, filename), 'wb') as handle:
                        reply = requests.get(icon_url, stream=True)
                        if not reply.ok:
                            print(reply)
                        for block in reply.iter_content(1024):
                            if not block:
                                break
                            handle.write(block)
                except IndexError:
                    print('Index Error on icon list...skipping')
                if os.path.exists(os.path.join(path, filename)):
                    img = PIL.Image.open(os.path.join(path, filename))
                    img = img.resize((180, 180), PIL.Image.ANTIALIAS)
                    img = PIL.ImageTk.PhotoImage(img)
                    self.icons.append(img)
                else:
                    img = PIL.Image.open(os.path.join(path, 'not_found.png'))
                    img = PIL.ImageTk.PhotoImage(img)
                    self.icons.append(img)
            print('generated icons successfully')

        url = settings['apiurl'] + "gridpoints/" + settings['nwsoffice'] + "/" + str(settings['gridX']) + "," + \
                str(settings['gridY']) + "/forecast"
        attempts = 0
        while attempts < 3:
            response = requests.get(url, headers=settings['useragent'])
            if response.ok:
                attempts = 4
                self.areaforecast = response.json()  # this has all the forecasts
                print('Got forecast successfully...')
                geticons()
            if not response.ok:
                attempts += 1
                print('Got status ' + str(response.status_code) + ' when trying to get ' + url)
        if not response.ok and attempts >= 4:
            print('Was unable to get ' + url)
            self.areaforecast = None

    def clock(self):
        today = datetime.date.today()
        todaysdate = today.strftime("%B %d, %Y")
        hour = strftime('%I')
        minute = strftime('%M')
        second = strftime('%S')
        ap = strftime('%p')
        clockstring = '  ' + todaysdate + "   " + hour + ":" + minute + ":" + second + " " + ap
        self.clocktext.delete('1.0', tk.END)
        self.clocktext.insert(tk.END, ' ')
        # self.clocktext.image_create(tk.END, image=self.nwsicon)
        self.clocktext.insert(tk.END, clockstring + '\t● ')
        self.clocktext.insert(tk.END, self.topmessage)
        self.clocktext.after(1000, self.clock)

    def __init__(self, main):
        self.settings = settings
        self.mainwindow = main
        self.topmessage = ""  # this is the text area to the right of the clock
        self.observations = []
        self.obsicons = []
        self.icons = []  # this is the list where we will store PIL PhotoImages for the extended forecast
        self.warning_status = False  # on start up set as false. This is the "flag" that determines whether to display
        self.advisory_status = False  # the red ticker. The advisory appears in the forecast area (frame1) during loop
        self.isMarqueeRunning = False
        self.warning_text = ""
        self.pressure = None
        self.last_pressure = None
        self.areaforecast = None
        self.radar_images = []
        self.frame_timestamp = []
        self.beep = sa.WaveObject.from_wave_file(os.path.dirname(os.path.abspath(__file__)) + '\\audio\\beep.wav')
        self.frame0 = tk.Frame(root, bg=self.settings['background_color'], bd=0, relief=tk.SOLID)
        self.frame1 = tk.Frame(root, bg=self.settings['background_color'], bd=0, relief=tk.SOLID)
        self.frame2 = tk.Frame(root, bg=self.settings['background_color'], bd=0, relief=tk.SOLID)
        self.frame0.pack(side=tk.TOP, expand=1, fill=tk.BOTH)
        self.frame1.pack(side=tk.TOP, expand=1, fill=tk.BOTH)
        self.frame2.pack(side=tk.TOP, expand=1, fill=tk.BOTH)
        # Extended Forecast elements
        self.extd0 = tk.Text(self.frame1, bg=self.settings['panel_color'], fg=self.settings['foreground_color'],
                             width=10, height=10)
        self.extd1 = tk.Text(self.frame1, bg=self.settings['panel_color'], fg=self.settings['foreground_color'],
                             width=10, height=10)
        self.extd2 = tk.Text(self.frame1, bg=self.settings['panel_color'], fg=self.settings['foreground_color'],
                             width=10, height=10)
        self.extd3 = tk.Text(self.frame1, bg=self.settings['panel_color'], fg=self.settings['foreground_color'],
                             width=10, height=10)
        self.extd0.config(font=(self.settings['font'], self.settings['fontpts']))
        self.extd1.config(font=(self.settings['font'], self.settings['fontpts']))
        self.extd2.config(font=(self.settings['font'], self.settings['fontpts']))
        self.extd3.config(font=(self.settings['font'], self.settings['fontpts']))
        # Radar Screen Elements
        self.rdartext = tk.Text(self.frame1, bg=self.settings['panel_color'], fg=self.settings['foreground_color'],
                                width=10, height=10)
        self.rdartext.config(font=(self.settings['font'], self.settings['fontpts']))
        # Lower Display Elements
        self.ldtext = tk.Text(self.frame2, bg=self.settings['panel_color'], fg=self.settings['foreground_color'])
        self.ldtext.config(font=(self.settings['font'], self.settings['fontpts']), height=1)
        # notice we didn't pack it here, the func needs to do that
        self.fcasttext = tk.Text(self.frame1, tabs=self.settings['tabs'], bg=self.settings['panel_color'],
                                 width=12, height=10, wrap=tk.WORD)
        self.fcasttext.config(font=(self.settings['font'], self.settings['fontpts']),
                              fg=self.settings['foreground_color'])
        self.fcasttext.pack(side=tk.TOP, fill=tk.X, padx=50, pady=20)
        # call forecast here
        self.clocktext = tk.Text(self.frame0, bg=self.settings['panel_color'], fg=self.settings['foreground_color'])
        self.clocktext.config(font=(self.settings['font'], self.settings['fontpts']), height=1)
        self.nwsicon = PIL.Image.open(os.path.join(os.path.join(settings['cwd'], 'images'), 'nws.png'))
        self.nwsicon = PIL.ImageTk.PhotoImage(self.nwsicon)
        self.mkcanvas = tk.Canvas(self.frame2, borderwidth=0, relief=tk.SOLID, bg='#ff0000')
        self.clocktext.pack(side=tk.LEFT, fill=tk.X, expand=1, padx=0, pady=0)
        self.clock()
        self.getforecast()
        self.getobservations()
        self.radar_download()
        sched.add_job(func=self.getforecast, trigger='interval', minutes=60, id='check_forecast')
        sched.add_job(func=self.getobservations, trigger='interval', minutes=15, id='check_observations')
        sched.add_job(func=self.checkalerts, trigger='interval', minutes=15, id='check_alerts')
        sched.add_job(func=self.last_pressure_record, trigger='interval', minutes=180, id='last_pressure')
        sched.add_job(func=self.radar_download, trigger='interval', minutes=5, id='radar_download')
        # sched.add_job(func=self.warning_test, trigger='interval', minutes=2, id='warning_test')
        self.ldtext.after(2000, self.ldloop)
        sched.start()
        self.checkalerts()
        self.warning_check()
        print('now beginning the regular loop...')
        self.forecast_loop()

        # Scheduler
        # shcedule to get obs every 15 minutes in background
        # schedule to get forecast every 60 minutes in background
        # schedule to reset the lower text every 60 seconds, we may change this
        # schedule garbage collection every 150 seconds, if memory leak is still an issue -- we'll definitely need to
        # revisit this issue.
        # schedule to download radar imagery every 5 minutes in background.
        #


if __name__ == "__main__":
    root = tk.Tk()
    root.title(settings["apptitle"])
    root.geometry(settings["resolution"])
    root.resizable(0, 0)
    app = MyApp(root)
    root.mainloop()
