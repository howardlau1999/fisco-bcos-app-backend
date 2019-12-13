from sanic import Sanic
from sanic.request import Request
from sanic.response import json
from client.datatype_parser import DatatypeParser
from client.common import transaction_common
from client.common import common
from client.bcoserror import BcosError, CompileError, PrecompileError, ArgumentsError, BcosException
from client.common.transaction_exception import TransactionException
from sanic_session import Session, InMemorySessionInterface
from console import default_abi_file, encode_hex
from databases import Database
from client_config import client_config
from eth_account.account import (
    Account
)
import sqlalchemy
import bcrypt
import os
from sqlalchemy.sql import select

app = Sanic()
session = Session(app)
contracts_dir = "contracts"
DB_URL = "sqlite:///db.sqlite"
CONTRACT_ADDR = "0xbcd8358eb85d818694dbbe6e898e3c71f91649fa"
CONTRACT_NAME = "SmartContract8"
accounts = {}


def parse_transaction(tx, contractname, parser=None):
    if parser is None:
        parser = DatatypeParser(default_abi_file(contractname))
    inputdata = tx["input"]
    inputdetail = parser.parse_transaction_input(inputdata)
    return (inputdetail)


def sendtx_contract(contractname, address, fn_name, *fn_args, account=None):
    tx_client = transaction_common.TransactionCommon(
        address, contracts_dir, contractname)
    if account is not None:
        tx_client.client_account = account
    receipt = tx_client.send_transaction_getReceipt(fn_name, fn_args)[0]
    data_parser = DatatypeParser(default_abi_file(contractname))
    logresult = data_parser.parse_event_logs(receipt["logs"])
    events = [{'name': log['eventname'], 'data': log['eventdata']}
              for log in logresult if 'eventname' in log]
    i = 0
    for log in logresult:
        if 'eventname' in log:
            i = i + 1
            print("{}): log name: {} , data: {}".format(i, log['eventname'], log['eventdata']))
    txhash = receipt["transactionHash"]
    txresponse = tx_client.getTransactionByHash(txhash)
    inputdetail = parse_transaction(txresponse, "", data_parser)
    # 解析该交易在receipt里输出的output,即交易调用的方法的return值
    outputresult = data_parser.parse_receipt_output(inputdetail['name'], receipt['output'])
    return {'events': events, 'returns': outputresult}


def call_contract(contractname, address, fn_name, *fn_args, account=None):
    tx_client = transaction_common.TransactionCommon(
        address, contracts_dir, contractname)
    if account is not None:
        tx_client.client_account = account
    result = tx_client.call_and_decode(fn_name, fn_args)
    return {"result": result}


metadata = sqlalchemy.MetaData()
users = sqlalchemy.Table(
    'users',
    metadata,
    sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column('username', sqlalchemy.String(length=100)),
    sqlalchemy.Column('password', sqlalchemy.String(length=255)),
    sqlalchemy.Column('address', sqlalchemy.String(length=255)),
    sqlalchemy.Column('is_bank', sqlalchemy.Integer),
)
inventories = sqlalchemy.Table(
    'inventories',
    metadata,
    sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column('sku', sqlalchemy.String(length=100)),
    sqlalchemy.Column('user_id', sqlalchemy.Integer),
)

payables = sqlalchemy.Table(
    'payables',
    metadata,
    sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column('payable_id', sqlalchemy.Integer),
    sqlalchemy.Column('user_id', sqlalchemy.Integer),
)

receivables = sqlalchemy.Table(
    'receivables',
    metadata,
    sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column('receivable_id', sqlalchemy.Integer),
    sqlalchemy.Column('user_id', sqlalchemy.Integer),
)


def get_account(username: str, password: str):
    keyfile = "{}/{}.keystore".format(client_config.account_keyfile_path, username)
    with open(keyfile, "r") as dump_f:
        import json
        keytext = json.load(dump_f)
        privkey = Account.decrypt(keytext, password)
        ac2 = Account.from_key(privkey)
        dump_f.close()
    return ac2


def new_account(username: str, password: str):
    account = Account.create(password)
    address = account.address
    private_key = encode_hex(account.key)
    public_key = account.publickey
    kf = Account.encrypt(account.privateKey, password)
    keyfile = "{}/{}.keystore".format(client_config.account_keyfile_path, username)
    with open(keyfile, "w") as dump_f:
        import json
        json.dump(kf, dump_f)
        dump_f.close()
    return (address, private_key, public_key, account)


def setup_database():
    db = Database(DB_URL)
    app.db = db


@app.listener('after_server_start')
async def connect_to_db(*args, **kwargs):
    await app.db.connect()
    query = """CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, 
    username VARCHAR(100), 
    address VARCHAR(255), 
    password VARCHAR(255),
    is_bank INTEGER DEFAULT 0
    )"""
    await app.db.execute(query=query)
    query = """CREATE TABLE IF NOT EXISTS inventories (id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku VARCHAR(255), 
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES user(id))"""
    await app.db.execute(query=query)
    query = """CREATE TABLE IF NOT EXISTS receivables (id INTEGER PRIMARY KEY AUTOINCREMENT,
    receivable_id INTEGER, 
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES user(id))"""
    await app.db.execute(query=query)
    query = """CREATE TABLE IF NOT EXISTS payables (id INTEGER PRIMARY KEY AUTOINCREMENT,
    payable_id INTEGER, 
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES user(id))"""
    await app.db.execute(query=query)


@app.listener('after_server_stop')
async def disconnect_from_db(*args, **kwargs):
    await app.db.disconnect()


@app.route("/register", methods={"POST"})
async def register(request: Request):
    body = request.json
    username, password, company_name = body['username'], body['password'], body['company_name']

    query = users.select().where(users.c.username == username)

    user = await request.app.db.fetch_all(query)
    if len(user) != 0:
        return json({"error": f"user {username} exists"}, 400)

    query = users.insert()
    address, private_key, public_key, account = new_account(username, password)
    values = {"username": username, "password": bcrypt.hashpw(
        password.encode('UTF-8'), bcrypt.gensalt()).decode('UTF-8'), "address": address}
    sendtx_contract(CONTRACT_NAME, CONTRACT_ADDR, "registerCompany", company_name, account=account)
    if body.get("is_bank") is True:
        sendtx_contract(CONTRACT_NAME, CONTRACT_ADDR, "addBank", address)
        values["is_bank"] = 1
    await request.app.db.execute_many(query, [values])
    del values["password"]
    values['private_key'] = private_key
    values['public_key'] = public_key
    values['company_name'] = company_name
    return json(values)


@app.route("/sendtx", methods={"POST"})
async def sendtx(request: Request):
    if request['session'].get('user') is None:
        return json({"error": "not logined"}, 401)
    body = request.json
    if body['fn_name'] == 'publishInventory':
        query = inventories.insert()
        values = {"sku": body['fn_args'][0], "user_id": request['session'].get('user')[0]}
        await request.app.db.execute_many(query, [values])
    result = sendtx_contract(CONTRACT_NAME, CONTRACT_ADDR,
                             body['fn_name'], *body['fn_args'], account=accounts[request['session'].get('username')])
    events = result['events']
    for event in events:
        if event['name'] == 'Sold':
            data = event['data']
            buyer, seller, payable_id, receivable_id = data[0], data[1], data[-2], data[-1]
            query = f"SELECT id FROM users WHERE address = '{buyer}' COLLATE NOCASE"
            buyer_id = (await request.app.db.fetch_one(query))[0]
            query = f"SELECT id FROM users WHERE address = '{seller}' COLLATE NOCASE"
            seller_id = (await request.app.db.fetch_one(query))[0]
            query = payables.select(payables.c.payable_id == payable_id and payables.c.user_id == buyer_id)
            if (await request.app.db.fetch_one(query)) is None:
                query = payables.insert()
                await request.app.db.execute_many(query, [{'payable_id': payable_id, 'user_id': buyer_id}])
            query = receivables.select(receivables.c.receivable_id == receivable_id and receivables.c.user_id == seller_id)
            if (await request.app.db.fetch_one(query)) is None:
                query = receivables.insert()
                await request.app.db.execute_many(query, [{'receivable_id': receivable_id, 'user_id': seller_id}])
        elif event['name'] == 'ReceivableTransferred':
            data = event['data']
            to_address, receivable_id = data[1], data[-2]
            query = f"SELECT id FROM users WHERE address = '{to_address}' COLLATE NOCASE"
            user_id = (await request.app.db.fetch_one(query))[0]
            query = receivables.insert()
            await request.app.db.execute_many(query, [{'receivable_id': receivable_id, 'user_id': user_id}])
    return json(result)


@app.route("/call", methods={"POST"})
async def call(request: Request):
    if request['session'].get('user') is None:
        return json({"error": "not logined"}, 401)
    body = request.json
    print(accounts[request['session'].get('username')].address)
    result = call_contract(CONTRACT_NAME, CONTRACT_ADDR,
                           body['fn_name'], *body['fn_args'], account=accounts[request['session'].get('username')])
    return json(result)


@app.route("/inventories", methods={"POST"})
async def _inventories(request: Request):
    body = request.json
    query = users.join(inventories, inventories.c.user_id == users.c.id)

    if body.get('username') is not None:
        query = select([users, inventories]).where(
            users.c.username == body.get('username')).select_from(query)
    else:
        query = select([users, inventories]).select_from(query)
    print(query)
    rows = await request.app.db.fetch_all(query)
    return json(rows)


@app.route("/payables", methods={"GET"})
async def _payables(request: Request):
    if request['session'].get('user') is None:
        return json({"error": "not logined"}, 401)
    query = payables.select(payables.c.user_id == request['session'].get('user')[0])
    result = await request.app.db.fetch_all(query)
    return json(result)

@app.route("/receivables", methods={"GET"})
async def _receivables(request: Request):
    if request['session'].get('user') is None:
        return json({"error": "not logined"}, 401)
    query = receivables.select(receivables.c.user_id == request['session'].get('user')[0])
    result = await request.app.db.fetch_all(query)
    return json(result)

@app.route("/banks", methods={"GET"})
async def _banks(request: Request):
    query = users.select(users.c.is_bank != 0)
    result = await request.app.db.fetch_all(query)
    return json(result)

@app.route("/companies", methods={"GET"})
async def companies(request: Request):
    query = select([users.c.username, users.c.address])
    rows = await request.app.db.fetch_all(query)
    result = [{"address": row[1], "username": row[0]} for row in rows]
    return json(result)


@app.route("/profile", methods={"GET"})
async def profile(request: Request):
    if request['session'].get('user') is None:
        return json({"error": "not logined"}, 401)
    result = call_contract(CONTRACT_NAME, CONTRACT_ADDR, "companies", request['session']['user'][3])
    result = {**result, **{
        "username": request['session']['user'][1],
        "address": request['session']['user'][3],
        "is_bank": request['session']['user'][4],
    }}
    return json(result)


@app.route("/login", methods={"POST"})
async def login(request: Request):
    body = request.json
    username, password = body['username'], body['password']
    query = users.select().where(users.c.username == username)
    user = await request.app.db.fetch_one(query)
    if user is None:
        return json({"error": "wrong password or username"}, 401)
    id, username, hashed_password, address, is_bank = user
    if not bcrypt.checkpw(password.encode('UTF-8'), hashed_password.encode('UTF-8')):
        return json({"error": "wrong password or username"}, 401)
    account = get_account(username, password)
    request['session']['user'] = user
    request['session']['username'] = username
    accounts[username] = account
    return json({"username": username, "address": address})


@app.route("/logout", methods={"POST"})
async def logout(request: Request):
    request['session']['user'] = None
    return json({"status": "logged out"})

if __name__ == "__main__":
    setup_database()
    app.run(host="0.0.0.0", port=8000, debug=True, auto_reload=True)
