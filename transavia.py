'''Script to check for cheap Transavia flights between two airport codes.
   Checks 3 months ahead for reasonable travel times (DAYTIME)'''
from collections import namedtuple
import datetime
import os
import sys
import time

from dateutil.relativedelta import relativedelta
import requests
import requests_cache

API_KEY = os.getenv('TRANSAVIA_KEY')
API_URL = ('https://api.transavia.com/v1/flightoffers'
           '?origin={origin}'
           '&destination={destination}'
           '&origindeparturedate={start_date}'
           '&destinationdeparturedate={end_date}'
           '&origindeparturetime={start_timerange}'
           '&destinationarrivaltime={end_timerange}'
           '&daysatdestination={days_stay}'
           '&directflight=true'
           '&adults=1'
           '&limit=100'
           '&orderby=Price')
REFRESH_CACHE = 3600

# look 3 months ahead
NOW = datetime.datetime.now()
NUM_MONTHS_TO_CHECK = 3
DAYTIME = '0800-2200'  # lets travel normal hours for now :)
MAX_PRICE = 200
DEFAULT_SORT = 'price'

Record = namedtuple('Record', 'leave goback price link')

requests_cache.install_cache('cache', backend='sqlite',
                             expire_after=REFRESH_CACHE)

flight_combo_seen = set()


def gen_months():
    i = 0
    while True:
        i += 1
        month = (NOW + relativedelta(months=+i))
        yield month.strftime('%Y%m')


def query_api(params):
    headers = {'apikey': API_KEY}
    url = API_URL.format(**params)
    resp = requests.get(url, headers=headers).json()
    # print(url, resp)

    for offer in resp['flightOffer']:
        key = (offer['outboundFlight']['id'], offer['inboundFlight']['id'])
        if key in flight_combo_seen:
            continue
        else:
            flight_combo_seen.add(key)

        leave = offer['outboundFlight']['departureDateTime'][:-3]
        goback = offer['inboundFlight']['departureDateTime'][:-3]
        price = offer['pricingInfoSum']['totalPriceAllPassengers']
        link = offer['deeplink']['href']

        yield Record(leave=leave, goback=goback, price=price, link=link)


def print_results(results, sort_by=None):
    if sort_by is None:
        sort_by = DEFAULT_SORT

    sort = lambda r: getattr(r, sort_by)
    try:
        results.sort(key=sort)
    except AttributeError:
        raise

    print('Priting results up until max price of {}'.format(MAX_PRICE), end=' ')
    print('sorted by {}\n'.format(sort_by))

    cols = 'Leave Goback EUR'.split()
    print('{:<16} | {:<16} | {}'.format(*cols))
    print('-' * 41)

    fmt = '{0.leave} | {0.goback} | {0.price}' #\n{0.link}\n'
    for rec in results:
        if int(rec.price) > MAX_PRICE:
            continue
        print(fmt.format(rec))


if __name__ == '__main__':
    script = sys.argv.pop(0)
    args = sys.argv

    if len(args) < 3:
        print('Usage: {} from_airport to_airport days'.format(script))
        print('Airport codes: http://bit.ly/2ohU0H4')
        sys.exit(1)

    else:
        # TODO, verify against:
        # https://raw.githubusercontent.com/datasets/airport-codes/master/data/airport-codes.csv
        origin = args[0].upper()
        destination = args[1].upper()
        try:
            duration = int(args[2])  # TODO: accept various durations maybe
        except ValueError:
            print('Please provide a number for duration days')
            sys.exit(1)
        if len(args) == 4:
            sort_by = args[3]
        else:
            sort_by = None

    months = gen_months()

    keys = ('origin destination start_date end_date start_timerange '
            'end_timerange days_stay').split()
    values = (origin, destination, 0, 0, DAYTIME, DAYTIME, duration)
    url_params = dict(zip(keys, values))

    results = []
    for _ in range(NUM_MONTHS_TO_CHECK):
        next_month = next(months)

        url_params['start_date'] = next_month
        url_params['end_date'] = next_month

        results += list(query_api(url_params))

        time.sleep(2)
    
    print_results(results, sort_by)
