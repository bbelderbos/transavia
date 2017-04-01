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

from mail import mail_html

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
LIMIT = 20

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
        price = offer['pricingInfoSum']['totalPriceAllPassengers']
        link = offer['deeplink']['href']

        yield Record(leave=leave, goback=goback, price=price, link=link)


def gen_output(results, sort_by=None, limit=LIMIT):
    if sort_by is None:
        sort_by = DEFAULT_SORT

    sort = lambda r: getattr(r, sort_by)
    try:
        results.sort(key=sort)
    except AttributeError:
        raise
    
    output = []
    output.append('<h2>* Sorted by {}</h2>'.format(sort_by))
    output.append('<table>')

    cols = 'Leave Goback Eur Link'.split()
    fmt = ('<tr>'
           '<th>{:<16}</th>'
           '<th>{:<16}</th>'
           '<th>{:<3}</th>'
           '<th>{}</th>'
           '</tr>')
    output.append(fmt.format(*cols))

    fmt = ('<tr>'
           '<td>{0.leave}</td>'
           '<td>{0.goback}</td>'
           '<td>{0.price}</td>'
           '<td><a href="{0.link}">book</a></td>'
           '</tr>')
    i = 0
    for rec in results:
        if int(rec.price) > MAX_PRICE:
            continue
        i += 1
        output.append(fmt.format(rec))
        if i == limit:
            break

    output.append('</table>')
    return output


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

    subject = 'Flights {} - {} ({} days stay)'.format(
        origin, destination, duration) 

    content = ['<h1>Results (max price {})</h1>'.format(MAX_PRICE)]
    for sort, limit in dict(zip(['price', 'leave'], [20, 100])).items():
        output = '\n'.join(gen_output(results, sort_by=sort, limit=limit))
        content.append(output)

    print('\n'.join(content))
    #mail_html(subject, '\n'.join(content))
