import time
import urllib.parse
from typing import Optional, Dict, Any, List

from requests import Request, Session, Response
import hmac
from ciso8601 import parse_datetime
import sys


class FtxClient:
    _ENDPOINT = 'https://ftx.com/api/'

    def __init__(self, api_key=None, api_secret=None, subaccount_name=None) -> None:
        self._session = Session()
        self._api_key = api_key
        self._api_secret = api_secret
        self._subaccount_name = subaccount_name

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('GET', path, params=params)

    def _post(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('POST', path, json=params)

    def _delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('DELETE', path, json=params)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        request = Request(method, self._ENDPOINT + path, **kwargs)
        self._sign_request(request)
        response = self._session.send(request.prepare())
        return self._process_response(response)

    def _sign_request(self, request: Request) -> None:
        ts = int(time.time() * 1000)
        prepared = request.prepare()
        signature_payload = f'{ts}{prepared.method}{prepared.path_url}'.encode()
        if prepared.body:
            signature_payload += prepared.body
        print(signature_payload)
        signature = hmac.new(self._api_secret.encode(), signature_payload, 'sha256').hexdigest()
        request.headers['FTX-KEY'] = self._api_key
        request.headers['FTX-SIGN'] = signature
        request.headers['FTX-TS'] = str(ts)
        if self._subaccount_name:
            request.headers['FTX-SUBACCOUNT'] = urllib.parse.quote(self._subaccount_name)

    def _process_response(self, response: Response) -> Any:
        try:
            data = response.json()
            print (data)
        except ValueError:
            response.raise_for_status()
            raise
        else:
            if not data['success']:
                raise Exception(data['error'])
            return data['result']

    def list_futures(self) -> List[dict]:
        return self._get('futures')

    def list_markets(self) -> List[dict]:
        return self._get('markets')

    def get_orderbook(self, market: str, depth: int = None) -> dict:
        return self._get(f'markets/{market}/orderbook', {'depth': depth})

    def get_trades(self, market: str) -> dict:
        return self._get(f'markets/{market}/trades')

    def get_account_info(self) -> dict:
        return self._get(f'account')

    def get_open_orders(self, market: str = None) -> List[dict]:
        return self._get(f'orders', {'market': market})
    
    def get_order_history(self, market: str = None, side: str = None, order_type: str = None, start_time: float = None, end_time: float = None) -> List[dict]:
        return self._get(f'orders/history', {'market': market, 'side': side, 'orderType': order_type, 'start_time': start_time, 'end_time': end_time})
        
    def get_conditional_order_history(self, market: str = None, side: str = None, type: str = None, order_type: str = None, start_time: float = None, end_time: float = None) -> List[dict]:
        return self._get(f'conditional_orders/history', {'market': market, 'side': side, 'type': type, 'orderType': order_type, 'start_time': start_time, 'end_time': end_time})

    def modify_order(
        self, existing_order_id: Optional[str] = None,
        existing_client_order_id: Optional[str] = None, price: Optional[float] = None,
        size: Optional[float] = None, client_order_id: Optional[str] = None,
    ) -> dict:
        assert (existing_order_id is None) ^ (existing_client_order_id is None), \
            'Must supply exactly one ID for the order to modify'
        assert (price is None) or (size is None), 'Must modify price or size of order'
        path = f'orders/{existing_order_id}/modify' if existing_order_id is not None else \
            f'orders/by_client_id/{existing_client_order_id}/modify'
        return self._post(path, {
            **({'size': size} if size is not None else {}),
            **({'price': price} if price is not None else {}),
            ** ({'clientId': client_order_id} if client_order_id is not None else {}),
        })

    def get_conditional_orders(self, market: str = None) -> List[dict]:
        return self._get(f'conditional_orders', {'market': market})

    def place_order(self, market: str, side: str, price: float, size: float, type: str = 'limit',
                    reduce_only: bool = False, ioc: bool = False, post_only: bool = False,
                    client_id: str = None) -> dict:
        return self._post('orders', {'market': market,
                                     'side': side,
                                     'price': price,
                                     'size': size,
                                     'type': type,
                                     'reduceOnly': reduce_only,
                                     'ioc': ioc,
                                     'postOnly': post_only,
                                     'clientId': client_id,
                                     })

    def place_conditional_order(
        self, market: str, side: str, size: float, type: str = 'stop',
        limit_price: float = None, reduce_only: bool = False, cancel: bool = True,
        trigger_price: float = None, trail_value: float = None
    ) -> dict:
        """
        To send a Stop Market order, set type='stop' and supply a trigger_price
        To send a Stop Limit order, also supply a limit_price
        To send a Take Profit Market order, set type='trailing_stop' and supply a trigger_price
        To send a Trailing Stop order, set type='trailing_stop' and supply a trail_value
        """
        assert type in ('stop', 'take_profit', 'trailing_stop')
        assert type not in ('stop', 'take_profit') or trigger_price is not None, \
            'Need trigger prices for stop losses and take profits'
        assert type not in ('trailing_stop',) or (trigger_price is None and trail_value is not None), \
            'Trailing stops need a trail value and cannot take a trigger price'

        return self._post('conditional_orders',
                          {'market': market, 'side': side, 'triggerPrice': trigger_price,
                           'size': size, 'reduceOnly': reduce_only, 'type': 'stop',
                           'cancelLimitOnTrigger': cancel, 'orderPrice': limit_price})

    def cancel_order(self, order_id: str) -> dict:
        return self._delete(f'orders/{order_id}')

    def cancel_orders(self, market_name: str = None, conditional_orders: bool = False,
                      limit_orders: bool = False) -> dict:
        return self._delete(f'orders', {'market': market_name,
                                        'conditionalOrdersOnly': conditional_orders,
                                        'limitOrdersOnly': limit_orders,
                                        })

    def get_fills(self) -> List[dict]:
        return self._get(f'fills')

    def get_balances(self) -> List[dict]:
        return self._get('wallet/balances')

    def get_deposit_address(self, ticker: str) -> dict:
        return self._get(f'wallet/deposit_address/{ticker}')

    def get_positions(self, show_avg_price: bool = False) -> List[dict]:
        return self._get('positions', {'showAvgPrice': show_avg_price})

    def get_position(self, name: str, show_avg_price: bool = False) -> dict:
        return next(filter(lambda x: x['future'] == name, self.get_positions(show_avg_price)), None)

    def get_all_trades(self, market: str, start_time: float = None, end_time: float = None) -> List:
        ids = set()
        limit = 100
        results = []
        while True:
            response = self._get(f'markets/{market}/trades', {
                'end_time': end_time,
                'start_time': start_time,
            })
            deduped_trades = [r for r in response if r['id'] not in ids]
            results.extend(deduped_trades)
            ids |= {r['id'] for r in deduped_trades}
            print(f'Adding {len(response)} trades with end time {end_time}')
            if len(response) == 0:
                break
            end_time = min(parse_datetime(t['time']) for t in response).timestamp()
            if len(response) < limit:
                break
        return results
    def get_prices(self, coin):
        return self._get("/markets/" + coin + "/orderbook?depth=1")

apiKey = sys.argv[1]
secretKey = sys.argv[2]
coin = sys.argv[3]
number = float(sys.argv[4])
rate = float(sys.argv[5])
uprate = float(sys.argv[6])


fc = FtxClient(apiKey, secretKey)

def get_max_order_price(orders, side):
    sides = list(map(lambda x : x['side'], orders))
    prices = list(map(lambda x: x['price'], orders))
    p = zip(sides, prices)
    max_order_price = 0.0
    for i in p:
        if(i[0] == side and i[1] > max_order_price):
            max_order_price = i[1]
    return max_order_price
            
def get_min_order_price(orders, side):
    sides = list(map(lambda x : x['side'], orders))
    prices = list(map(lambda x : x['price'], orders))
    p = zip(sides, prices)
    min_order_price = 999999
    for i in p:
        if(i[0] == side and i[1] < min_order_price):
            min_order_price = i[1]
    return min_order_price

def get_orders_of_side(orders, side):
    orders_of_side = []
    for order in orders:
        if(order['side'] == side):
            orders_of_side.append(order)
    return orders_of_side

def run_sell(coin, number, rate, uprate):
    while True:
        time.sleep(2)
        try:
            prices = fc.get_prices(coin)
            open_orders = fc.get_open_orders(coin)
            buy_orders = get_orders_of_side(open_orders, 'buy')
        except Exception:
            continue
        if(len(buy_orders) == 0):
            try:
                fc.place_order(coin, "sell", prices['bids'][0][0], number, "limit", False, False, False)
            except Exception:
                continue
            while True:
                try:
                    fc.place_order(coin, "buy", prices['bids'][0][0] * (1 - rate), number, "limit", False, False, False)
                except Exception:
                    time.sleep(1)
                    continue
                break
        else:
            if(len(buy_orders) >= 5):
                continue
            current_price = prices['bids'][0][0]
            sign_price = get_max_order_price(open_orders, 'buy') * (1 + uprate)
            if(current_price > sign_price):
                try:
                    fc.place_order(coin, "sell", current_price, number, "limit", False, False, False)
                except Exception:
                    continue
                while True:
                    try:
                        fc.place_order(coin, "buy", current_price * (1 - rate), number, "limit", False, False, False)
                    except Exception:
                        time.sleep(1)
                        continue;
                    break
                    
def run_buy(coin, number, rate, uprate):
    while True:
        time.sleep(2)
        try:
            prices = fc.get_prices(coin)
            open_orders = fc.get_open_orders(coin)
            sell_orders = get_orders_of_side(open_orders, 'sell')
        except Exception:
            continue
        if(len(sell_orders) == 0):
            try:
                fc.palce_order(coin, "buy", prices['asks'][0][0], number, "limit", False, False, False)
            except Exception:
                continue
            while True:
                try:
                    fc.place_order(coin, "sell", prices['asks'][0][0] * (1 + rate), number, "limit", False, False, False)
                except Exception:
                    time.sleep(1)
                    continue
                break
        else:
            if(len(sell_orders) >= 5):
                continue
            current_price = prices['asks'][0][0]
            sign_price = get_min_order_price(open_orders, 'sell') * (1 - uprate)
            if(current_price < sign_price):
                try:
                    fc.place_order(coin, 'buy', current_price, number, 'limit', False, False, False)
                except Exception:
                    continue
                while True:
                    try:
                        fc.place_order(coin, 'sell', current_price * (1 + rate), number, 'limit', False, False, False)
                    except Exception:
                        time.sleep(1)
                        continue
                    break
run(coin, number, rate, uprate)
