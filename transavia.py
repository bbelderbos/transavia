'''Script to check for cheap Transavia flights
between two airport codes for n days duration.
Sends html report to mail set in ENV var'''
from collections import namedtuple
import calendar
import datetime
import os
import re
import socket
import sys
import time

from dateutil.relativedelta import relativedelta
import requests
import requests_cache

from mail import mail_html

API_KEY = os.getenv('TRANSAVIA_KEY')
API_URL = ('https://api.transavia.com/v1/flightoffers'
           '?origin={origin}'
           '&destination={destination}'
           '&origindeparturedate={start_date}'
           '&destinationdeparturedate={end_date}'
           '&origindeparturetime={start_timerange}'
           '&destinationdeparturetime={end_timerange}'
           '&daysatdestination={days_stay}'
           '&directflight=true'
           '&adults=1'
           '&limit=100'
           '&orderby=Price')
REFRESH_CACHE = 3600

LOCAL = 'MacBook' in socket.gethostname()
NOW = datetime.datetime.now()
NUM_MONTHS_TO_CHECK = 4
DEFAULT_SORT = 'price'
DEFAULT_TIMERANGE = '0800-2200'
DEFAULT_MAX_PRICE = 200

Record = namedtuple('Record', 'leave goback price link')

if LOCAL:
    # cache when developing
    requests_cache.install_cache('cache', backend='sqlite',
                                 expire_after=REFRESH_CACHE)

flight_combo_seen = set()


def gen_months():
    '''Month generator starting with current month.
    Format: YYYYMM'''
    i = 0
    while True:
        month = (NOW + relativedelta(months=+i))
        yield month.strftime('%Y%m')
        i += 1


def query_api(params):
    '''Query Transavia API with API_KEY in headers.
    Url is build up from params dict passed in.
    API docs: https://developer.transavia.com'''
    headers = {'apikey': API_KEY}
    url = API_URL.format(**params)
    resp = requests.get(url, headers=headers).json()
    # print(url)
    # print(resp)

    for offer in resp['flightOffer']:
        key = (offer['outboundFlight']['id'], offer['inboundFlight']['id'])
        if key in flight_combo_seen:
            continue
        else:
            flight_combo_seen.add(key)

        leave = offer['outboundFlight']['departureDateTime'][:-3]
        goback = offer['inboundFlight']['departureDateTime'][:-3]

        leave_day = _get_dayname(leave)
        goback_day = _get_dayname(goback)

        price = offer['pricingInfoSum']['totalPriceAllPassengers']
        link = offer['deeplink']['href']

        yield Record(leave=leave + leave_day,
                     goback=goback + goback_day,
                     price=price,
                     link=link)


def _get_dayname(day):
    '''Get weekday (first 3 chars) from date string'''
    try:
        dt = datetime.datetime.strptime(day, '%Y-%m-%dT%H:%M')
    except:
        return ''
    weekday = dt.weekday()
    day_name = calendar.day_name[weekday]
    return ' ({})'.format(day_name[:3])


def gen_output(results, sort_by=DEFAULT_SORT, max_price=DEFAULT_MAX_PRICE):
    '''Builds an html section of the output report'''
    sort = lambda r: getattr(r, sort_by)
    try:
        results.sort(key=sort)
    except AttributeError:
        raise

    output = []
    output.append('<h2>* Sorted by {}</h2>'.format(sort_by))
    output.append('<table>')

    cols = 'Leave Goback Price Link'.split()
    fmt = ('<tr>'
           '<th>{}</th>'
           '<th>{}</th>'
           '<th>{}</th>'
           '<th>{}</th>'
           '</tr>')
    output.append(fmt.format(*cols))

    fmt = ('<tr>'
           '<td>{0.leave}</td>'
           '<td>{0.goback}</td>'
           '<td>{0.price}</td>'
           '<td><a href="{0.link}">book</a></td>'
           '</tr>')
    for rec in results:
        if int(rec.price) > max_price:
            continue
        output.append(fmt.format(rec))

    output.append('</table>')
    return output


if __name__ == '__main__':
    script = sys.argv.pop(0)
    args = sys.argv

    if len(args) < 3:
        usage = ('Usage: {} from_airport to_airport days_stay '.format(script),
                 '(timerange, default={}) '.format(DEFAULT_TIMERANGE),
                 '(maxprice, default={})'.format(DEFAULT_MAX_PRICE))
        print(''.join(usage))
        print('Use airport codes for from / to: http://bit.ly/2ohU0H4')
        sys.exit(1)

    else:
        # TODO: verify against:
        # https://raw.githubusercontent.com/datasets/airport-codes/master/data/airport-codes.csv
        origin = args[0].upper()
        destination = args[1].upper()
        try:
            duration = int(args[2])  # TODO: accept various durations maybe
        except ValueError:
            print('Please provide a number for duration days')
            sys.exit(1)

        if len(args) > 3:
            timerange = args[3]
            if not re.match(r'\d{4}-\d{4}', timerange):
                sys.exit('Please provide a timerange with format like {}'.format(DEFAULT_TIMERANGE))
        else:
            timerange = DEFAULT_TIMERANGE

        if len(args) > 4:
            try:
                max_price = int(args[4])
            except ValueError:
                print('Please provide a numeric max price')
                sys.exit(1)
        else:
            max_price = DEFAULT_MAX_PRICE

    months = gen_months()

    keys = ('origin destination start_date end_date start_timerange '
            'end_timerange days_stay').split()
    values = (origin, destination, 0, 0, timerange, timerange, duration)
    url_params = dict(zip(keys, values))

    results = []
    for _ in range(NUM_MONTHS_TO_CHECK):
        next_month = next(months)

        url_params['start_date'] = next_month
        url_params['end_date'] = next_month

        results += list(query_api(url_params))

        time.sleep(2)

    subject = 'Flights {} - {} ({} days stay)'.format(
        origin, destination, duration)

    content = ['<h1>Results (max price {})</h1>'.format(max_price)]

    sort_orders = ('price', 'leave')
    for sort in sort_orders:
        output = '\n'.join(gen_output(results, sort_by=sort))
        content.append(output)

    if LOCAL:
        print('\n'.join(content))
    else:
        mail_html(subject, '\n'.join(content))
