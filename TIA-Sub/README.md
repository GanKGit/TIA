# AlgoEngine

Standalone local TCP trading engine for compliance validation demos.

## Ports

```text
9500  Client FIX 4.4 order entry. Accepts 35=D, 35=F, and 35=G.
9601  Exchange outbound destination. The engine connects to a simulated local exchange here.
9501  Market data input. Accepts newline-delimited JSON or key=value L1/L2 updates.
9502  Admin control. Supports STATUS, SNAPSHOT, HALT, RESUME, RESET, STOP, and HELP.
```

## Run

From the repository root:

```bash
python -m AlgoEngine
```

Or:

```bash
python -m AlgoEngine.local_engine
```

## Configuration

```env
TRADING_ENGINE_SYSTEM_ID=local-trading-engine
TRADING_ENGINE_HOST=127.0.0.1
TRADING_CLIENT_PORT=9500
TRADING_EXCHANGE_HOST=127.0.0.1
TRADING_EXCHANGE_PORT=9601
TRADING_MARKET_DATA_PORT=9501
TRADING_ADMIN_PORT=9502
TRADING_EXCHANGE_CONNECT_TIMEOUT_SECONDS=3
```

## Example Inputs

Client FIX order:

```text
8=FIX.4.4|35=D|49=CLIENT1|56=ENGINE|11=ORD-1|55=AAPL|54=1|38=100|40=2|44=175.25|10=000|
```

Market data JSON:

```json
{"symbol":"AAPL","bid":175.10,"ask":175.20,"level":1}
```

Market data key-value:

```text
symbol=AAPL bid=175.10 ask=175.20 bid_size=100 ask_size=200 level=1
```

## Client Simulator

Start the exchange simulator from the repository root:

```bash
python -m AlgoEngine.exchange_simulator
```

Start the engine in another terminal:

```bash
python -m AlgoEngine
```

In another terminal, send a new order and read the execution report:

```bash
python -m AlgoEngine.client_simulator --order-id ORD-1 --symbol AAPL --side 1 --quantity 100 --price 175.25
```

Send a cancel request:

```bash
python -m AlgoEngine.client_simulator --message-type F --order-id CXL-1 --original-order-id ORD-1
```

Send a cancel/replace request:

```bash
python -m AlgoEngine.client_simulator --message-type G --order-id RPL-1 --original-order-id ORD-1 --quantity 150 --price 176.00
```

When the exchange simulator is running, the engine forwards orders to the exchange, waits for the exchange execution report, and returns that fill or cancel report to the client.

Useful simulator options:

```text
--host 127.0.0.1
--port 9500
--message-type D|F|G
--order-id ORD-1
--original-order-id ORD-1
--symbol AAPL
--side 1|2
--quantity 100
--order-type 1|2
--price 175.25
--count 5
```

Run the client simulator as a long-running listener for `nc`:

```bash
python -m AlgoEngine.client_simulator --listen --listen-port 9890
```

Then connect with `nc`:

```bash
nc 127.0.0.1 9890
```

Type one order command per line:

```text
NEW order-id=ORD-1 symbol=AAPL side=1 quantity=100 price=175.25
SELL order-id=ORD-2 symbol=MSFT quantity=50 price=410.00
CANCEL order-id=CXL-1 original-order-id=ORD-1 symbol=AAPL side=1
REPLACE order-id=RPL-1 original-order-id=ORD-1 symbol=AAPL side=1 quantity=150 price=176.00
```

Raw FIX input is also accepted:

```text
8=FIX.4.4|35=D|49=CLIENT1|56=ENGINE|11=ORD-3|55=AAPL|54=1|38=100|40=2|44=175.25|10=000|
```

The listener sends each order to the engine client port, waits for the engine response, and writes the execution report plus a short summary back to your `nc` session. Use `HELP` for examples and `QUIT` to close a session.

AlgoEngine validates parent-child update relationships before routing to the exchange. A cancel/replace update (`35=G`) must send its new client order id in tag `11` and the previous known order id in tag `41`.

Valid update:

```text
REPLACE order-id=ORD-2 original-order-id=ORD-1 symbol=AAPL side=1 quantity=100 price=176.00
```

Equivalent raw FIX:

```text
8=FIX.4.4|35=G|49=CLIENT1|56=ENGINE|11=ORD-2|41=ORD-1|55=AAPL|54=1|38=100|40=2|44=176.00|10=000|
```

Invalid updates are rejected before exchange routing when tag `41` is missing or unknown.

## Exchange Simulator

The exchange simulator listens on the engine exchange port, default `9601`, and maintains an in-memory price-time order book per symbol.

```bash
python -m AlgoEngine.exchange_simulator --host 127.0.0.1 --port 9601
```

Non-crossing limit orders rest on the book and receive accepted reports:

```text
35=8, 150=0, 39=0
```

When a buy price is greater than or equal to the best ask, or a sell price is less than or equal to the best bid, the exchange sends fill reports to both the incoming and resting order connections:

```text
35=8, 150=2, 39=2
```

Cancel requests receive canceled reports:

```text
35=8, 150=4, 39=4
```

Useful exchange options:

```text
--host 127.0.0.1
--port 9601
--sender SIM_EXCHANGE
--fill-price 175.25
```

