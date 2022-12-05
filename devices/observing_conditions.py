"""
This module contains the weather class. When get_status() is called, the weather situation
is evaluated and self.wx_is_ok and self.open_is_ok are evaluated and published along
with self.status, a dictionary.

This module should be expanded to integrate multiple Wx sources, particularly Davis and
SkyAlert.

Weather holds are counted only when they INITIATE within the Observing window. So if a
hold started just before the window and opening was late that does not count for anti-
flapping purposes.

This module sends 'signals' through the Events layer then TO the enclosure by checking
as sender that an OPEN for example can get through the Events layer. It is Mandatory
the receiver (the enclosure in this case) also checks the Events layer. The events layer
is populated once per observing day with default values. However the dictionary entries
can be modified for debugging or simulation purposes.
"""

import json
import socket
import time

import win32com.client
import redis

from global_yard import g_dev
from site_config import get_ocn_status


def linearize_unihedron(uni_value):  # Need to be coefficients in config.
    #  Based on 20180811 data
    uni_value = float(uni_value)
    if uni_value < -1.9:
        uni_corr = 2.5 ** (-5.85 - uni_value)
    elif uni_value < -3.8:
        uni_corr = 2.5 ** (-5.15 - uni_value)
    elif uni_value <= -12:
        uni_corr = 2.5 ** (-4.88 - uni_value)
    else:
        uni_corr = 6000
    return uni_corr


def f_to_c(f):
    return round(5 * (f - 32) / 9, 2)


class ObservingConditions:
    def __init__(self, driver: str, name: str, config: dict, astro_events):
        # We need a way to specify which computer in the wema in the
        # the singular config file or we have two configurations.

        self.name = name
        self.astro_events = astro_events
        self.site = config["site"]
        g_dev["ocn"] = self
        self.config = config
        g_dev["ocn"] = self
        self.sample_time = 0
        self.ok_to_open = "No"
        self.observing_condtions_message = "-"
        self.wx_is_ok = False
        self.wx_hold = False
        self.wx_to_go = 0.0
        self.wx_hold_last_updated = (
            time.time()
        )  # This is meant for a stale check on the Wx hold report
        self.wx_hold_tally = 0
        self.wx_clamp = False
        self.clamp_latch = False
        self.wait_time = 0  # A countdown to re-open
        self.wx_close = False  # If made true by Wx code, a 15 minute timeout will begin when Wx turns OK
        self.wx_hold_until_time = None
        self.wx_hold_count = 0  # if >=5 inhibits reopening for Wx
        self.wait_time = 0  # A countdown to re-open
        self.wx_close = False  # If made true by Wx code, a 15 minute timeout will begin when Wx turns OK
        self.wx_system_enable = True  # Purely a debugging aid.
        self.wx_test_cycle = 0
        self.prior_status = None
        self.prior_status_2 = None
        self.wmd_fail_counter = 0
        self.temperature = self.config["reference_ambient"]  # Index needs
        self.pressure = self.config["reference_pressure"]  # to be months.
        self.unihedron_connected = (
            True  # NB NB NB His needs improving, driving from config
        )
        self.hostname = socket.gethostname()
        self.site_is_specific = False
        # =============================================================================
        #         Note site_in_automatic found in the Enclosure object.
        # =============================================================================
        if self.hostname in self.config["wema_hostname"]:
            self.is_wema = True
        else:
            self.is_wema = False
        if self.config["wema_is_active"]:
            self.site_has_proxy = True  # NB Site is proxy needs a new name.
        else:
            self.site_has_proxy = False
        if self.config["site_is_specific"]:
            self.site_is_specific = True
            #  Note OCN has no associated commands.
            #  Here we monkey patch
            self.get_status = get_ocn_status
            # Get current ocn status just as a test.
            self.status = self.get_status(g_dev)
        elif self.is_wema or self.site_is_specific:
            #  This is meant to be a generic Observing_condition code
            #  instance that can be accessed by a simple site or by the WEMA,
            #  assuming the transducers are connected to the WEMA.
            self.site_is_generic = True
            win32com.client.pythoncom.CoInitialize()
            self.sky_monitor = win32com.client.Dispatch(driver)
            self.sky_monitor.connected = True  # This is not an ASCOM device.
            driver_2 = config["observing_conditions"]["observing_conditions1"][
                "driver_2"
            ]
            self.sky_monitor_oktoopen = win32com.client.Dispatch(driver_2)
            self.sky_monitor_oktoopen.Connected = True
            driver_3 = config["observing_conditions"]["observing_conditions1"][
                "driver_3"
            ]
            if driver_3 is not None:
                self.sky_monitor_oktoimage = win32com.client.Dispatch(driver_3)
                self.sky_monitor_oktoimage.Connected = True
                print("observing_conditions: sky_monitors connected = True")
            if config["observing_conditions"]["observing_conditions1"]["has_unihedron"]:
                self.unihedron_connected = True
                try:
                    driver = config["observing_conditions"]["observing_conditions1"][
                        "uni_driver"
                    ]
                    port = config["observing_conditions"]["observing_conditions1"][
                        "unihedron_port"
                    ]
                    self.unihedron = win32com.client.Dispatch(driver)
                    self.unihedron.Connected = True
                    print(
                        "observing_conditions: Unihedron connected = True, on COM"
                        + str(port)
                    )
                except:
                    print(
                        "Unihedron on Port 10 is disconnected. Observing will proceed."
                    )
                    self.unihedron_connected = False
                    # NB NB if no unihedron is installed the status code needs to not report it.
        self.last_wx = None

    def get_status(self):
        """
        Regularly calling this routine returns weather status dict for AWS,
        evaluates the Wx reporting and manages temporary closes,
        known as weather-holds

        Returns
        -------
        status : TYPE
            DESCRIPTION.

        """
        # This is purely generic code for a generic site.
        # It may be overwritten with a monkey patch found in the appropriate config.py.

        if not self.is_wema and self.site_has_proxy:  #  EG., this was written first for SRO. Thier                                         #  system is a proxoy for having a WEMA
            if self.config["site_IPC_mechanism"] == "shares":
                try:
                    weather = open(g_dev["wema_share_path"] + "weather.txt", "r")
                    status = json.loads(weather.readline())
                    weather.close()
                    self.status = status
                    self.prior_status = status
                    g_dev["ocn"].status = status
                    return status
                except:
                    try:
                        time.sleep(3)
                        weather = open(g_dev["wema_share_path"] + "weather.txt", "r")
                        status = json.loads(weather.readline())
                        weather.close()
                        self.status = status
                        self.prior_status = status
                        g_dev["ocn"].status = status
                        return status
                    except:
                        try:
                            time.sleep(3)
                            weather = open(
                                g_dev["wema_share_path"] + "weather.txt", "r"
                            )
                            status = json.loads(weather.readline())
                            weather.close()
                            self.status = status
                            self.prior_status = status
                            g_dev["ocn"].status = status
                            return status
                        except:
                            print("Using prior OCN status after 4 failures.")
                            g_dev["ocn"].status = self.prior_status
                            return self.prior_status
            elif self.config["site_IPC_mechanism"] == "redis":
                try:
                    status = eval(g_dev["redis"].get("wx_state"))
                except:
                    status = g_dev["redis"].get("wx_state")
                self.status = status
                self.prior_status = status
                g_dev["ocn"].status = status

                if status['wx_ok'] in ['no', 'No', False]:
                    self.wx_is_ok = False
                if status['wx_ok'] in ['yes', 'Yes', True]:
                    self.wx_is_ok = True
                if status['open_ok'] in ['no', 'No', False]:
                    self.ok_to_open = False
                if status['open_ok'] in ['yes', 'Yes', True]:
                    self.ok_to_open = True
                if status['wx_hold'] in ['no', 'No', False]:
                    self.wx_hold = False
                if status['wx_hold'] in ['yes', 'Yes', True]:
                    self.wx_hold = True
                try:
                    self.current_ambient = self.status["temperature_C"]
                except:
                    pass
                return status
            else:
                try:
                    self.current_ambient = self.status["temperature_C"]
                except:
                    pass
                self.status = status
            try:
                self.current_ambient = self.status["temperature_C"]
            except:
                pass
            return status

        if (
            self.site_is_generic or self.is_wema
        ):  # These operations are common to a generic single computer or wema site.
            status = {}
            illum, mag = self.astro_events.illuminationNow()
            # illum = float(redis_monitor["illum lux"])
            if illum > 500:
                illum = int(illum)
            else:
                illum = round(illum, 3)
            if self.unihedron_connected:
                try:
                    uni_measure = (
                        self.unihedron.SkyQuality
                    )  #  Provenance of 20.01 is dubious 20200504 WER
                except:
                    uni_measure = 0
            if uni_measure == 0:
                uni_measure = round(
                    (mag - 20.01), 2
                )  #  Fixes Unihedron when sky is too bright
                status["meas_sky_mpsas"] = uni_measure
                self.meas_sky_lux = illum
            else:
                self.meas_sky_lux = linearize_unihedron(uni_measure)
                status["meas_sky_mpsas"] = uni_measure

            self.temperature = round(self.sky_monitor.Temperature, 2)
            try:  # NB NB Boltwood vs. SkyAlert difference.  What about SRO?
                self.pressure = (
                    self.sky_monitor.Pressure,
                )  # 978   #Mbar to mmHg  #THIS IS A KLUDGE
            except:
                self.pressure = self.config["reference_pressure"]
            # NB NB NB This is a very odd problem which showed up at MRC.
            try:
                self.new_pressure = round(float(self.pressure[0]), 2)
            except:
                self.new_pressure = round(float(self.pressure), 2)
            try:
                status = {
                    "temperature_C": round(self.temperature, 2),
                    "pressure_mbar": self.new_pressure,
                    "humidity_%": self.sky_monitor.Humidity,
                    "dewpoint_C": self.sky_monitor.DewPoint,
                    "sky_temp_C": round(self.sky_monitor.SkyTemperature, 2),
                    "last_sky_update_s": round(
                        self.sky_monitor.TimeSinceLastUpdate("SkyTemperature"), 2
                    ),
                    "wind_m/s": abs(round(self.sky_monitor.WindSpeed, 2)),
                    "rain_rate": self.sky_monitor.RainRate,
                    "solar_flux_w/m^2": None,
                    "cloud_cover_%": str(self.sky_monitor.CloudCover),
                    "calc_HSI_lux": illum,
                    "calc_sky_mpsas": round(
                        uni_measure, 2
                    ),  # Provenance of 20.01 is dubious 20200504 WER
                    "open_ok": self.ok_to_open,
                    "wx_hold": self.wx_hold,
                    "hold_duration": self.wx_to_go,
                }
            except:
                status = {
                    "temperature_C": round(self.temperature, 2),
                    "pressure_mbar": self.new_pressure,
                    "humidity_%": self.sky_monitor.Humidity,
                    "dewpoint_C": self.sky_monitor.DewPoint,
                    "sky_temp_C": round(self.sky_monitor.SkyTemperature, 2),
                    "last_sky_update_s": round(
                        self.sky_monitor.TimeSinceLastUpdate("SkyTemperature"), 2
                    ),
                    "wind_m/s": abs(round(self.sky_monitor.WindSpeed, 2)),
                    "rain_rate": self.sky_monitor.RainRate,
                    "solar_flux_w/m^2": None,
                    "cloud_cover_%": "unknown",  # str(self.sky_monitor.CloudCover), # Sometimes faults.
                    "calc_HSI_lux": illum,
                    "calc_sky_mpsas": round(
                        uni_measure, 2
                    ),  #  Provenance of 20.01 is dubious 20200504 WER
                    "open_ok": self.ok_to_open,
                    "wx_hold": self.wx_hold,
                    "hold_duration": self.wx_to_go,
                }
            wx_reasons =[]
            rain_limit = self.sky_monitor.RainRate <= 0.001
            if not rain_limit:
                wx_reasons.append('Rain > 0')
            humidity_limit = self.sky_monitor.Humidity < 85
            if not humidity_limit:
                wx_reasons.append('Humidity >= 85%')
            wind_limit = (
                self.sky_monitor.WindSpeed < 25
            )  # sky_monitor reports km/h, Clarity may report in MPH
            if not wind_limit:
                wx_reasons.append('Wind > 25 km/h')
            dewpoint_gap = (
                not (self.sky_monitor.Temperature - self.sky_monitor.DewPoint) < 2
            )
            if not dewpoint_gap:
                wx_reasons.append('Ambient - Dewpoint < 2C')
            sky_amb_limit = (
                self.sky_monitor.Temperature - self.sky_monitor.SkyTemperature 
            ) < -8.5  # NB THIS NEEDS ATTENTION, Sky alert defaults to -17
            if not sky_amb_limit:
                wx_reasons.append('sky - amb < -8.5C')
            try:
                cloud_cover = float(self.sky_monitor.CloudCover)
                status['cloud_cover_%'] = round(cloud_cover, 0)
                if cloud_cover <= 67:
                    cloud_cover = True
                else:
                    cloud_cover = False
                    wx_reasons.append('High Clouds')
            except:
                status['cloud_cover_%'] = "no report"
                cloud_cover = True    #  We cannot use this signal to force a wX hold or close
            self.current_ambient = round(self.temperature, 2)
            temp_bounds = not (self.sky_monitor.Temperature < -15) or (
                self.sky_monitor.Temperature > 42
            )
            if not temp_bounds:
                wx_reasons.append('amb temp')


            # humidity_limit = self.sky_monitor.Humidity < 85
            # if not humidity_limit:
            #     wx_reasons.append('High humidity')
            # rain_limit = self.sky_monitor.RainRate <= 0.001
            # if not rain_limit:
            #     wx_reasons.append('Rain > 0')


            self.wx_is_ok = (
                dewpoint_gap
                and temp_bounds
                and wind_limit
                and sky_amb_limit
                and humidity_limit
                and rain_limit
            )
            #  NB wx_is_ok does not include ambient light or altitude of the Sun
            if self.wx_is_ok:
                wx_str = "Yes"
                status["wx_ok"] = "Yes"
            else:
                wx_str = "No"  # Ideally we add the dominant reason in priority order.
                status["wx_ok"] = "No"

            g_dev["wx_ok"] = self.wx_is_ok
            print('Wx Ok:  ', status["wx_ok"], wx_reasons)
            if self.config["site_IPC_mechanism"] == "shares":
                weather_txt = self.config["wema_write_share_path"] + "weather.txt"
                try:
                    with open(weather_txt, "w", encoding="utf-8") as f:
                        f.write(json.dumps(status))
                except IOError:
                    tries = 1
                    while tries < 5:
                        # Wait 3 seconds and try writing to file again, up to 3 more times.
                        print(
                            f"Attempt {tries} to write weather status failed. Trying again."
                        )
                        time.sleep(3)
                        with open(weather_txt, "w", encoding="utf-8") as f:
                            f.write(json.dumps(status))
                            if not weather_txt.closed:
                                break
                        tries += 1

            elif self.config["site_IPC_mechanism"] == "redis":
                try:   #for MRC look to see if Unihedron sky mag/sq-asec value exists in redis
                    uni_string = g_dev['redis'].get('unihedron1')
                    if uni_string is not None:
                        status['meas_sky_mpsas'] = eval(g_dev['redis'].get('unihedron1'))[0]
                except:
                    pass
                g_dev["redis"].set(
                    "wx_state", status
                )  # This needs to become generalized IP

            # Only write when around dark, put in CSV format, used to calibrate Unihedron.
            sunZ88Op, sunZ88Cl, sunrise, ephemNow = g_dev[
                "obs"
            ].astro_events.getSunEvents()
            two_hours = (
                2 / 24
            )  #  Note changed to 2 hours. NB NB NB The times need changing to bracket skyflats.
            if (sunZ88Op - two_hours < ephemNow < sunZ88Cl + two_hours) and (
                time.time() >= self.sample_time + 60
            ):  #  Once a minute.

                try:
                    wl = open("Q:/ptr/unihedron/wx_log.txt", "a")
                    wl.write(
                        str(time.time())
                        + ", "
                        + str(illum)
                        + ", "
                        + str(mag - 20.01)
                        + ", "
                        + str(uni_measure)
                        + ", \n"
                    )
                    wl.close()
                    self.sample_time = time.time()
                except:
                    self.sample_time = time.time() - 61

            # Now let's compute Wx hold condition. Class is set up to assume Wx has been good.
            # The very first time though at Noon, self.open_is_ok will always be False but the
            # Weather, which does not include ambient light, can be good. We will assume that
            # changes in ambient light are dealt with more by the Events module.

            # We want the wx_hold signal to go up and down as a guage on the quality of the
            # afternoon. If there are a lot of cycles, that indicates unsettled conditons even
            # if any particular instant is perfect. So we set self.wx_hold to false during class
            # __init__().
            # When we get to this point of the code first time we expect self.wx_is_ok to be true

            obs_win_begin, sunset, sunrise, ephemNow = self.astro_events.getSunEvents()
            wx_delay_time = 900
            try:
                multiplier = min(len(wx_reasons),3)
            except:
                multiplier = 1
            wx_delay_time *= multiplier/2   #Stretch out the Wx hold if there are multiple reasons

            if (
                self.wx_is_ok and self.wx_system_enable
            ) and not self.wx_hold:  # Normal condition, possibly nothing to do.
                self.wx_hold_last_updated = time.time()
            elif not self.wx_is_ok and not self.wx_hold:  # Wx bad and no hold yet.
                # Bingo we need to start a cycle
                self.wx_hold = True
                self.wx_hold_until_time = (
                    t := time.time() + wx_delay_time
                )  # 15 minutes   Make configurable
                self.wx_hold_tally += 1  #  This counts all day and night long.
                self.wx_hold_last_updated = t
                if (
                    obs_win_begin <= ephemNow <= sunrise
                ):  # Gate the real holds to be in the Observing window.
                    self.wx_hold_count += 1
                    # We choose to let the enclosure manager handle the close.
                    print(
                        "Wx hold asserted, flap#:",
                        self.wx_hold_count,
                        self.wx_hold_tally,
                    )
                else:
                    print(
                        "Wx Hold -- out of Observing window.",
                        self.wx_hold_count,
                        self.wx_hold_tally,
                    )
            elif not self.wx_is_ok and self.wx_hold:  # WX is bad and we are on hold.
                self.wx_hold_last_updated = time.time()
                # Stay here as long as we need to.
                self.wx_hold_until_time = (t := time.time() + wx_delay_time)
                if self.wx_system_enable:
                    pass
            elif self.wx_is_ok and self.wx_hold:  # Wx now good and still on hold.
                if self.wx_hold_count < 3:
                    if time.time() >= self.wx_hold_until_time and not self.wx_clamp:
                        # Time to release the hold.
                        self.wx_hold = False
                        self.wx_hold_until_time = (
                            time.time() + wx_delay_time
                        )  # Keep pushing the recovery out
                        self.wx_hold_last_updated = time.time()
                        print(
                            "Wx hold released, flap#, tally#:",
                            self.wx_hold_count,
                            self.wx_hold_tally,
                        )
                        # We choose to let the enclosure manager diecide it needs to re-open.
                else:
                    # Never release the THIRD hold without some special high level intervention.
                    if not self.clamp_latch:
                        print("Sorry, Tobor is clamping enclosure shut for the night.")
                    self.clamp_latch = True
                    self.wx_clamp = True

                self.wx_hold_last_updated = time.time()
            if self.wx_hold:
                self.wx_to_go = round((self.wx_hold_until_time - time.time()), 0)
                status["hold_duration"] = self.wx_to_go
                try:
                    g_dev['obs'].send_to_user(wx_reasons)
                except:
                    pass
            else:
                status["hold_duration"] = 0.0
            self.status = status
            g_dev["ocn"].status = status

            return status

    def get_quick_status(self, quick):

        if self.site_is_specific:
            self.status = self.get_status(g_dev)  # Get current state.
        else:
            self.status = self.get_status()
        illum, mag = g_dev["evnt"].illuminationNow()
        # NB NB NB it is safer to make this a dict rather than a positionally dependant list.
        quick.append(time.time())
        quick.append(float(self.status["sky_temp_C"]))
        quick.append(float(self.status["temperature_C"]))
        quick.append(float(self.status["humidity_%"]))
        quick.append(float(self.status["dewpoint_C"]))
        quick.append(float(abs(self.status["wind_m/s"])))
        quick.append(float(self.status["pressure_mbar"]))  # 20200329 a SWAG!
        quick.append(float(illum))  # Add Solar, Lunar elev and phase
        if self.unihedron_connected:
            uni_measure = 0  # wx['meas_sky_mpsas']   #NB NB note we are about to average logarithms.
        else:
            uni_measure = 0
        if uni_measure == 0:
            uni_measure = round(
                (mag - 20.01), 2
            )  #  Fixes Unihedron when sky is too bright
            quick.append(float(uni_measure))
            self.meas_sky_lux = illum
        else:
            self.meas_sky_lux = linearize_unihedron(uni_measure)
            quick.append(float(self.meas_sky_lux))  # intended for Unihedron
        return quick

    def get_average_status(self, pre, post):
        average = []
        average.append(round((pre[0] + post[0]) / 2, 3))
        average.append(round((pre[1] + post[1]) / 2, 1))
        average.append(round((pre[2] + post[2]) / 2, 1))
        average.append(round((pre[3] + post[3]) / 2, 1))
        average.append(round((pre[4] + post[4]) / 2, 1))
        average.append(round((pre[5] + post[5]) / 2, 1))
        average.append(round((pre[6] + post[6]) / 2, 2))
        average.append(round((pre[7] + post[7]) / 2, 3))
        average.append(round((pre[8] + post[8]) / 2, 1))
        return average

    def parse_command(self, command):
        # The only possible Wx command is test Wx hold.
        req = command["required_params"]
        opt = command["optional_params"]
        action = command["action"]
        if action is not None:
            pass
            # self.move_relative_command(req, opt)   ???
        else:
            print(f"Command <{action}> not recognized.")

    # ###################################
    #   Observing Conditions Commands  #
    # ###################################


if __name__ == "__main__":
    pass
