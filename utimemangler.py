"""
Time mangler  -- Network time functions

* set the time from an NTP server
* get a timezone offset from TimezoneDB server
"""

import ulogging
import utime
import ntptime
import urequests

_logger = ulogging.getLogger('eng.sw.utime')
_logger.setLevel(ulogging.INFO)


def get_tzone_data(apikey, tzone_name):
    params = []
    params.append('key={}'.format(apikey))
    params.append('format=json')
    params.append('by=zone')
    params.append('zone={}'.format(tzone_name))
    params_str = '&'.join(params)

    url_fmt = 'http://api.timezonedb.com/v2.1/get-time-zone?{params}'
    url = url_fmt.format(params=params_str)
    _logger.info('Requesting {}...'.format(url))
    headers = {}
#   headers['Accept-Encoding'] = 'gzip'

    try:
        req = urequests.get(url, headers=headers, timeout=30)
    except (IndexError, OSError) as exc:  # IndexError is a strange exception to throw if there is no data...
        _logger.info('Requesting {}...failed'.format(url))
        _logger.debug(exc.args[0])
        return None

    # Convert the forecast data from JSON to Python
    try:
        content = req.json()
    except ValueError as exc:
        req.close()
        _logger.debug(exc.args[0])
        return None

    req.close()
    return content


class Time_Mangler:
    #pylint: disable=too-many-instance-attributes
    # Though I cannot seee that there are 10 of them?
    NOT_SET = 0
    CONNECTING = 1
    SETTING_TIME = 2
    WAITING_FOR_TIMEZONE = 3
    DISCONNECTING = 4
    TIME_SET = 5

    def __init__(self, net, tzone_name, tzone_apikey=None):
        self.net = net
        
        self.retry_interval_not_set_s = 300  # 5 minutes
        self.retry_interval_set_s = 3600 # 1 hour
        self._confidence = 0.0

        time_now_ms = utime.ticks_ms()
        self.next_attempt_timestamp_ms = time_now_ms + 2000
        self.network_timeout_ms = 30000 # Keep the network up for 30 s maximum

        self.tzone_name = tzone_name
        self.tzone_apikey = tzone_apikey
        self.tzone_data = None
        self.tzone_offset = None

        self.state_timestamp_ms = None
        self.state = self.NOT_SET

    def confidence(self):
        return self._confidence

    def step(self):
        #pylint: disable=too-many-branches,too-many-statements
        time_now_ms = utime.ticks_ms()
        state_duration = utime.ticks_diff(time_now_ms, self.state_timestamp_ms)

        if self.state == self.NOT_SET:
            remaining_ms = utime.ticks_diff(self.next_attempt_timestamp_ms, time_now_ms)
            if remaining_ms <= 0:
                _logger.info('Time mangler...')
                _logger.debug('Connecting...')
                self.net.connect('timemangler', self.network_timeout_ms)
                self.state_timestamp_ms = time_now_ms
                self.state = self.CONNECTING
            return

        if self.state == self.CONNECTING:
            if self.net.is_connected():
                _logger.debug('Connecting...done')
                _logger.debug('Setting time...')
                self.state_timestamp_ms = time_now_ms
                self.state = self.SETTING_TIME
            else:
                if state_duration >= self.network_timeout_ms:
                    _logger.debug('Connecting...timeout')
                    _logger.debug('Disconnecting...')
                    self.state_timestamp_ms = time_now_ms
                    self.state = self.DISCONNECTING
            return

        if self.state == self.SETTING_TIME:
            try:
                ntptime.settime()
            except (OSError, IndexError):
                _logger.info('Setting time...failed ({})', utime.localtime())
                self.next_attempt_timestamp_ms = utime.ticks_add(time_now_ms, self.retry_interval_set_s * 1000)
                self.state_timestamp_ms = time_now_ms
                self.state = self.DISCONNECTING
                return
                
            _logger.info('Setting time...done ({})', utime.localtime())
            self._confidence = 1.0
            self.time_set_timestamp = time_now_ms
            self.next_attempt_timestamp_ms = utime.ticks_add(time_now_ms, self.retry_interval_set_s * 1000)
            _logger.debug('Getting timezone...')
            self.state_timestamp_ms = time_now_ms
            self.state = self.WAITING_FOR_TIMEZONE
            return

        if self.state == self.WAITING_FOR_TIMEZONE:
            if self.tzone_apikey:
                self.tzone_data = get_tzone_data(self.tzone_apikey, self.tzone_name)
            if self.tzone_data is None:
                _logger.debug('Getting timezone...failed')
                _logger.debug('Disconnecting...')
                self.state_timestamp_ms = time_now_ms
                self.state = self.DISCONNECTING
            else:
                self.tzone_offset = self.tzone_data['gmtOffset']
                _logger.debug('Getting timezone...done')
                _logger.info(self.tzone_data)
                _logger.debug('Disconnecting...')
                self.state_timestamp_ms = time_now_ms
                self.state = self.DISCONNECTING
            return

        if self.state == self.DISCONNECTING:
            self.net.disconnect('timemangler')
            _logger.debug('Disconnecting...done')
            _logger.info('Time mangler...done')
            self.state_timestamp_ms = time_now_ms
            self.state = self.TIME_SET
            return

        if self.state == self.TIME_SET:
            if time_now_ms > self.next_set_timestamp:
                _logger.info('Time mangler...')
                _logger.debug('Connecting...')
                self.net.connect('timemangler', self.network_timeout_ms)
                self.state_timestamp_ms = time_now_ms
                self.state = self.CONNECTING
            return
